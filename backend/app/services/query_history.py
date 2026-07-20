"""
Query history tracking service.

This service provides an in-memory record of recent SQL queries executed
through the platform. It supports:

    1. **Recording queries** — Track every query with metadata (SQL, status,
       timing, row counts, errors).
    2. **Retrieving recent queries** — Return the last N queries for display
       in monitoring UIs.
    3. **Looking up by ID** — Retrieve the full status and results of a
       specific query.

Architecture Decision:
    We use a bounded in-memory list (ring buffer of 100 entries) rather than
    a database table because:
        - Query history is ephemeral — it resets on server restart
        - The write pattern is append-only with a fixed size limit
        - No complex queries are needed on the history itself
        - Avoids polluting the analytical database with operational data

    For production deployments needing persistent history, this should be
    migrated to PostgreSQL or a time-series store.
"""

import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum number of queries to retain in memory
MAX_HISTORY_SIZE = 100


class QueryRecord:
    """
    Represents a single query execution record.

    Attributes:
        query_id: Unique identifier for this query execution.
        sql: The SQL statement that was executed.
        status: Current status — 'running', 'completed', or 'failed'.
        execution_time_ms: Time taken to execute (None if still running).
        created_by: Username or ID of the user who submitted the query.
        created_at: ISO 8601 timestamp when the query was submitted.
        row_count: Number of rows returned (None if still running or failed).
        error_message: Error detail if the query failed (None otherwise).
        columns: Column names from the result set.
        rows: Result rows (stored for completed queries, limited to 100).
        truncated: Whether the result was truncated.
    """

    def __init__(
        self,
        sql: str,
        created_by: str = "anonymous",
    ) -> None:
        self.query_id: str = uuid.uuid4().hex[:12]
        self.sql: str = sql
        self.status: str = "running"
        self.execution_time_ms: Optional[float] = None
        self.created_by: str = created_by
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.row_count: Optional[int] = None
        self.error_message: Optional[str] = None
        self.columns: Optional[List[str]] = None
        self.rows: Optional[List[Dict[str, Any]]] = None
        self.truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert the query record to a dictionary for serialisation."""
        return {
            "query_id": self.query_id,
            "sql": self.sql,
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "row_count": self.row_count,
            "error_message": self.error_message,
            "columns": self.columns,
            "rows": self.rows,
            "truncated": self.truncated,
        }

    def summary_dict(self) -> Dict[str, Any]:
        """Convert to a lightweight dict without full result rows."""
        return {
            "query_id": self.query_id,
            "sql": self.sql,
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "row_count": self.row_count,
            "error_message": self.error_message,
            "truncated": self.truncated,
        }


class QueryHistory:
    """
    Thread-safe in-memory store for recent query executions.

    Maintains a bounded deque of QueryRecord objects. Oldest entries
    are automatically evicted when the capacity is exceeded.

    All public methods are thread-safe via an internal lock, making
    this safe for concurrent FastAPI request handlers.
    """

    def __init__(self, max_size: int = MAX_HISTORY_SIZE) -> None:
        self._records: deque[QueryRecord] = deque(maxlen=max_size)
        self._index: Dict[str, QueryRecord] = {}
        self._lock = threading.Lock()

    def add_query(self, sql: str, created_by: str = "anonymous") -> QueryRecord:
        """
        Record a new query execution.

        Creates a QueryRecord with status 'running' and adds it to the
        history. The caller should later call mark_completed() or
        mark_failed() to update the record.

        Args:
            sql: The SQL query string.
            created_by: Identifier of the user who submitted the query.

        Returns:
            The newly created QueryRecord (with query_id assigned).
        """
        record = QueryRecord(sql=sql, created_by=created_by)
        with self._lock:
            # If we're at capacity, the deque will evict the oldest;
            # we must also remove it from the index.
            if len(self._records) == self._records.maxlen:
                oldest = self._records[0]
                self._index.pop(oldest.query_id, None)

            self._records.append(record)
            self._index[record.query_id] = record

        logger.debug("Query recorded: %s (user=%s)", record.query_id, created_by)
        return record

    def mark_completed(
        self,
        query_id: str,
        execution_time_ms: float,
        row_count: int,
        columns: Optional[List[str]] = None,
        rows: Optional[List[Dict[str, Any]]] = None,
        truncated: bool = False,
    ) -> Optional[QueryRecord]:
        """
        Mark a query as successfully completed.

        Args:
            query_id: The query identifier returned by add_query().
            execution_time_ms: Query execution time in milliseconds.
            row_count: Number of rows in the result set.
            columns: List of column names in the result.
            rows: Result rows (limited to 100 for memory safety).
            truncated: Whether the result was truncated.

        Returns:
            The updated QueryRecord, or None if query_id not found.
        """
        with self._lock:
            record = self._index.get(query_id)
            if record is None:
                logger.warning("Cannot mark completed — query %s not found", query_id)
                return None

            record.status = "completed"
            record.execution_time_ms = round(execution_time_ms, 2)
            record.row_count = row_count
            record.columns = columns
            # Store at most 100 rows to avoid excessive memory use
            if rows is not None:
                record.rows = rows[:100]
            record.truncated = truncated

        logger.debug(
            "Query completed: %s (%d rows in %.1fms)",
            query_id, row_count, execution_time_ms,
        )
        return record

    def mark_failed(
        self,
        query_id: str,
        execution_time_ms: float,
        error_message: str,
    ) -> Optional[QueryRecord]:
        """
        Mark a query as failed.

        Args:
            query_id: The query identifier returned by add_query().
            execution_time_ms: Time elapsed before failure.
            error_message: Description of the error.

        Returns:
            The updated QueryRecord, or None if query_id not found.
        """
        with self._lock:
            record = self._index.get(query_id)
            if record is None:
                logger.warning("Cannot mark failed — query %s not found", query_id)
                return None

            record.status = "failed"
            record.execution_time_ms = round(execution_time_ms, 2)
            record.row_count = 0
            record.error_message = error_message

        logger.debug("Query failed: %s — %s", query_id, error_message[:200])
        return record

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Return the most recent query records (summary only, no result rows).

        Args:
            limit: Maximum number of records to return (1-100).

        Returns:
            List of query record summary dicts, newest first.
        """
        limit = max(1, min(limit, 100))
        with self._lock:
            # Return newest first
            records = list(self._records)
            records.reverse()
            return [r.summary_dict() for r in records[:limit]]

    def get_by_id(self, query_id: str) -> Optional[Dict[str, Any]]:
        """
        Look up a query record by its ID.

        Returns the full record including result rows (if completed),
        making it suitable for polling query status.

        Args:
            query_id: The unique query identifier.

        Returns:
            Full query record dict, or None if not found.
        """
        with self._lock:
            record = self._index.get(query_id)
            if record is None:
                return None
            return record.to_dict()


# ── Global singleton instance ─────────────────────────────────────────────

query_history = QueryHistory()
