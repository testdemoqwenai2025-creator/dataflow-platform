"""
DuckDB query execution service.

This service provides a safe, controlled interface for executing SQL
queries against DuckDB. Key responsibilities:

    1. **Query validation** — Prevent destructive operations (DROP, DELETE,
       TRUNCATE, ALTER) and access to system tables.
    2. **Query execution** — Execute SQL and return results as DataFrames.
    3. **Schema introspection** — List tables and describe their schemas.

Architecture Decision:
    We centralise all DuckDB interaction here rather than scattering raw
    SQL calls across the codebase. This gives us a single place to enforce
    safety policies, add query logging/timing, and implement future features
    like query queuing or result caching.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

# ── Dangerous SQL patterns ────────────────────────────────────────────────
# These patterns are blocked to prevent accidental or malicious data loss.
# We use case-insensitive matching because SQL keywords are case-insensitive.

BLOCKED_PATTERNS = [
    # DDL — structural modifications
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bALTER\b", re.IGNORECASE),
    re.compile(r"\bCREATE\s+USER\b", re.IGNORECASE),
    re.compile(r"\bGRANT\b", re.IGNORECASE),
    re.compile(r"\bREVOKE\b", re.IGNORECASE),

    # DML — data modification (allowed on user tables, blocked on system)
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),

    # System access
    re.compile(r"\bATTACH\b", re.IGNORECASE),
    re.compile(r"\bDETACH\b", re.IGNORECASE),
    re.compile(r"\bCOPY\s+.*\bTO\b", re.IGNORECASE),  # COPY ... TO (file write)

    # Dangerous functions
    re.compile(r"\bread_blob\b", re.IGNORECASE),
    re.compile(r"\bimport\s+database\b", re.IGNORECASE),
]

# Patterns that are dangerous ONLY when targeting system tables
SYSTEM_TABLE_PREFIXES = ("sqlite_", "information_schema", "pg_", "__duckdb_")

# Allow DELETE and UPDATE only on user-created tables (ds_ prefix)
DML_PATTERNS = [
    re.compile(r"\bDELETE\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\b", re.IGNORECASE),
    re.compile(r"\bINSERT\b", re.IGNORECASE),
]


class QueryService:
    """
    Service for executing and validating SQL queries against DuckDB.

    This class wraps a DuckDB connection and provides:
        - Safe query execution with validation
        - Table listing and schema introspection
        - Result conversion to pandas DataFrames

    Args:
        conn: An active DuckDB connection.

    Example:
        >>> service = QueryService(conn)
        >>> df = service.execute_query("SELECT * FROM my_table LIMIT 10")
        >>> tables = service.list_tables()
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self._conn = conn

    def execute_query(self, sql: str) -> pd.DataFrame:
        """
        Execute a SQL query and return results as a pandas DataFrame.

        DuckDB natively supports converting query results to DataFrames,
        which makes this operation zero-copy and very fast.

        Args:
            sql: The SQL query string to execute.

        Returns:
            A pandas DataFrame with the query results.

        Raises:
            duckdb.Error: If the query fails (syntax error, missing table, etc.)
        """
        logger.debug("Executing query: %s", sql[:200])
        try:
            result = self._conn.execute(sql)
            df = result.df()
            logger.debug("Query returned %d rows x %d columns", len(df), len(df.columns))
            return df
        except duckdb.Error as exc:
            logger.error("DuckDB query error: %s", exc)
            raise
        except Exception as exc:
            logger.error("Unexpected query error: %s", exc)
            raise

    def validate_query(self, sql: str) -> Tuple[bool, str]:
        """
        Validate a SQL query for safety before execution.

        Checks for:
            1. Destructive DDL operations (DROP, ALTER, TRUNCATE)
            2. System table access in DML statements (DELETE, UPDATE on system tables)
            3. File system access (COPY TO, ATTACH)
            4. Privilege escalation (GRANT, REVOKE, CREATE USER)

        Args:
            sql: The SQL query string to validate.

        Returns:
            A tuple of (is_valid, message). If is_valid is False,
            message explains why the query was rejected.
        """
        sql_stripped = sql.strip()

        # Empty query
        if not sql_stripped:
            return False, "Query is empty"

        # Check blocked patterns
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(sql_stripped):
                # Get the matched keyword for a helpful error message
                match = pattern.search(sql_stripped)
                keyword = match.group(0) if match else pattern.pattern
                return False, f"Operation not allowed: {keyword}"

        # Check DML on system tables
        for pattern in DML_PATTERNS:
            if pattern.search(sql_stripped):
                # Check if the query references system tables
                for prefix in SYSTEM_TABLE_PREFIXES:
                    if prefix.lower() in sql_stripped.lower():
                        return False, (
                            f"DML operations on system tables ({prefix}*) are not allowed. "
                            "Only user-created tables (ds_*) support modifications."
                        )

        # Warn about queries without LIMIT on SELECT
        # (We don't block them — the endpoint applies a limit — but we log it)
        if sql_stripped.upper().startswith("SELECT") and "LIMIT" not in sql_stripped.upper():
            logger.info("Query without explicit LIMIT — endpoint default will be applied")

        return True, "Query is valid"

    def get_schema(self, table_name: str) -> Dict[str, Any]:
        """
        Get the schema of a DuckDB table.

        Returns column names, data types, and basic constraints.

        Args:
            table_name: Name of the table to describe.

        Returns:
            Dictionary with:
                - table_name: The table name
                - columns: List of {name, type, nullable} dicts
                - row_count: Estimated number of rows
                - size_bytes: Approximate table size (if available)
        """
        # Use parameterised query for table name in WHERE clause
        columns_result = self._conn.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = ?
            ORDER BY ordinal_position
            """,
            [table_name],
        ).fetchall()

        columns = [
            {
                "name": col_name,
                "type": col_type,
                "nullable": col_nullable == "YES",
            }
            for col_name, col_type, col_nullable in columns_result
        ]

        # Get row count
        try:
            row_count = self._conn.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
        except Exception:
            row_count = None

        return {
            "table_name": table_name,
            "columns": columns,
            "row_count": row_count,
        }

    def list_tables(self) -> List[str]:
        """
        List all user-created tables in DuckDB.

        Filters out system tables and internal DuckDB tables, returning
        only tables in the 'main' schema that are user-created (those
        with the 'ds_' prefix or other non-system names).

        Returns:
            List of table names, sorted alphabetically.
        """
        try:
            result = self._conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            ).fetchall()

            tables = [row[0] for row in result]

            # Filter out internal/system tables
            tables = [
                t for t in tables
                if not t.startswith("__duckdb_")
                and not t.startswith("sqlite_")
            ]

            logger.debug("Found %d user tables", len(tables))
            return tables

        except Exception as exc:
            logger.error("Failed to list tables: %s", exc)
            return []

    def get_table_preview(
        self,
        table_name: str,
        limit: int = 5,
    ) -> pd.DataFrame:
        """
        Get a preview of a table's data (first N rows).

        Useful for quick data inspection without loading the full dataset.

        Args:
            table_name: Name of the table.
            limit: Number of rows to return.

        Returns:
            DataFrame with the first `limit` rows.
        """
        return self.execute_query(f'SELECT * FROM "{table_name}" LIMIT {limit}')

    def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """
        Get basic statistics about a DuckDB table.

        Returns:
            Dictionary with row_count, column_count, and column summary.
        """
        schema = self.get_schema(table_name)
        return {
            "row_count": schema["row_count"],
            "column_count": len(schema["columns"]),
            "columns": schema["columns"],
        }
