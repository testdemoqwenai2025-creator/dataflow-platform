"""
Analytics endpoints: aggregation, pivot tables, dashboards, and statistics.

This module provides analytical capabilities built on top of DuckDB's
high-performance columnar engine:

    - Aggregation queries (GROUP BY with configurable metrics)
    - Pivot table generation
    - Statistical summaries (mean, median, std, percentiles)
    - Dashboard configuration CRUD

Architecture Decision:
    Analytics computations use DuckDB's native SQL aggregation functions
    wherever possible (DuckDB's columnar engine is optimised for these),
    falling back to pandas/numpy for statistics that DuckDB doesn't
    natively support (e.g., median via percentile_cont).

    Dashboard configs are stored in DuckDB as JSON strings, keeping
    all analytical artefacts in the same engine for simplicity.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import duckdb
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_duckdb_connection
from app.core.security import get_current_user
from app.models.schemas import (
    AggregationRequest,
    AnalyticsResult,
    APIResponse,
    DashboardConfig,
    DashboardUpdate,
    DashboardWidget,
    PivotRequest,
    StatisticalSummary,
)
from app.services.analytics_service import AnalyticsService
from app.services.query_service import QueryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# In-memory dashboard store (replaced by DB storage when available)
_dashboards: Dict[str, DashboardConfig] = {
    "default": DashboardConfig(
        id=1,
        name="Default Dashboard",
        description="Auto-generated default dashboard",
        widgets=[
            DashboardWidget(
                id="w1",
                type="metric",
                title="Total Datasets",
                config={"query": "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"},
                position={"x": 0, "y": 0, "w": 3, "h": 2},
            ),
        ],
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
}


# ── Aggregation ───────────────────────────────────────────────────────────


@router.post(
    "/aggregate",
    response_model=APIResponse[AnalyticsResult],
    summary="Run aggregation query",
    description="Execute a GROUP BY aggregation with configurable metrics on a DuckDB table.",
)
async def aggregate(
    request: AggregationRequest,
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb_connection),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[AnalyticsResult]:
    """
    Execute an aggregation query against a DuckDB table.

    Builds a SQL GROUP BY query from the request parameters:
        - group_by: Columns to group by
        - metrics: Alias → SQL expression mapping (e.g. {"total": "SUM(amount)"})
        - filter_sql: Optional WHERE clause
        - having_sql: Optional HAVING clause

    Example request:
        {
            "table_name": "ds_sales_abc123",
            "group_by": ["region", "year"],
            "metrics": {"total_revenue": "SUM(revenue)", "avg_price": "AVG(price)"},
            "filter_sql": "year >= 2020"
        }
    """
    query_service = QueryService(conn)

    # Verify table exists
    tables = query_service.list_tables()
    if request.table_name not in tables:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{request.table_name}' not found. Available: {tables}",
        )

    # Build SQL
    select_parts = [f'"{col}"' for col in request.group_by]
    for alias, expr in request.metrics.items():
        select_parts.append(f"{expr} AS {alias}")

    select_clause = ", ".join(select_parts)
    group_clause = ", ".join(f'"{col}"' for col in request.group_by)

    sql = f'SELECT {select_clause} FROM "{request.table_name}"'

    if request.filter_sql:
        # Basic validation
        is_valid, msg = query_service.validate_query(f"SELECT {request.filter_sql}")
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid filter: {msg}")
        sql += f" WHERE {request.filter_sql}"

    sql += f" GROUP BY {group_clause}"

    if request.having_sql:
        sql += f" HAVING {request.having_sql}"

    try:
        start_time = time.time()
        df = query_service.execute_query(sql)
        execution_time = (time.time() - start_time) * 1000

        rows = df.to_dict(orient="records")
        # Clean numpy types for JSON serialisation
        clean_rows = []
        for row in rows:
            clean_row = {}
            for key, value in row.items():
                if hasattr(value, "item"):
                    clean_row[key] = value.item()
                elif str(value) == "nan":
                    clean_row[key] = None
                else:
                    clean_row[key] = value
            clean_rows.append(clean_row)

        result = AnalyticsResult(
            result_type="aggregation",
            data=clean_rows,
            metadata={
                "row_count": len(clean_rows),
                "execution_time_ms": round(execution_time, 2),
                "sql": sql,
            },
        )

        return APIResponse(
            success=True,
            data=result,
            message=f"Aggregation completed ({len(clean_rows)} groups in {execution_time:.1f}ms)",
        )

    except Exception as exc:
        logger.error("Aggregation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Aggregation failed: {str(exc)}",
        )


# ── Pivot Table ───────────────────────────────────────────────────────────


@router.post(
    "/pivot",
    response_model=APIResponse[AnalyticsResult],
    summary="Generate pivot table",
    description="Create a pivot table from a DuckDB table with flexible configuration.",
)
async def pivot(
    request: PivotRequest,
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb_connection),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[AnalyticsResult]:
    """
    Generate a pivot table from a DuckDB table.

    Uses the AnalyticsService to compute the pivot, which leverages
    pandas' pivot_table function after fetching the raw data from DuckDB.

    Example request:
        {
            "table_name": "ds_sales_abc123",
            "index": ["region"],
            "columns": "year",
            "values": ["revenue"],
            "aggfunc": "sum"
        }
    """
    query_service = QueryService(conn)
    analytics_service = AnalyticsService()

    # Verify table exists
    tables = query_service.list_tables()
    if request.table_name not in tables:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{request.table_name}' not found. Available: {tables}",
        )

    # Fetch data from DuckDB
    try:
        df = query_service.execute_query(f'SELECT * FROM "{request.table_name}"')
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch data: {str(exc)}",
        )

    # Generate pivot table
    try:
        pivot_df = analytics_service.generate_pivot(
            df=df,
            index=request.index,
            columns=request.columns,
            values=request.values,
            aggfunc=request.aggfunc,
        )

        # Convert pivot to dict for response
        pivot_data = pivot_df.reset_index().to_dict(orient="records")
        clean_rows = []
        for row in pivot_data:
            clean_row = {}
            for key, value in row.items():
                if hasattr(value, "item"):
                    clean_row[str(key)] = value.item()
                elif str(value) == "nan":
                    clean_row[str(key)] = None
                else:
                    clean_row[str(key)] = value
            clean_rows.append(clean_row)

        result = AnalyticsResult(
            result_type="pivot",
            data=clean_rows,
            metadata={
                "index": request.index,
                "columns": request.columns,
                "values": request.values,
                "aggfunc": request.aggfunc,
                "row_count": len(clean_rows),
            },
        )

        return APIResponse(
            success=True,
            data=result,
            message=f"Pivot table generated ({len(clean_rows)} rows x {len(pivot_df.columns)} columns)",
        )

    except Exception as exc:
        logger.error("Pivot generation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pivot table generation failed: {str(exc)}",
        )


# ── Dashboard ─────────────────────────────────────────────────────────────


@router.get(
    "/dashboard/stats",
    response_model=APIResponse[dict],
    summary="Get dashboard statistics",
    description="Retrieve real-time analytics statistics from DuckDB for the dashboard.",
)
async def get_dashboard_stats(
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb_connection),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[dict]:
    """
    Get real-time dashboard statistics by querying DuckDB.

    Returns:
        - dataset_count: Number of user tables in DuckDB
        - total_rows: Sum of rows across all tables
        - duckdb_version: DuckDB version string
        - duckdb_status: Connection status
        - memory_usage: Current DuckDB memory limit setting
        - sales_summary: Aggregated stats from sales_data if it exists
          (total_revenue, unique_customers, top_category, avg_order_value)
    """
    stats: Dict[str, Any] = {}

    try:
        # Dataset count from information_schema
        dataset_count = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()[0]
        stats["dataset_count"] = dataset_count
    except Exception as exc:
        logger.warning("Failed to query dataset count: %s", exc)
        stats["dataset_count"] = 0

    try:
        # Total rows across all user tables
        tables_result = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        total_rows = 0
        for (table_name,) in tables_result:
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
                total_rows += count
            except Exception:
                pass
        stats["total_rows"] = total_rows
    except Exception as exc:
        logger.warning("Failed to compute total rows: %s", exc)
        stats["total_rows"] = 0

    try:
        # DuckDB system info
        version_result = conn.execute("SELECT version()").fetchone()
        stats["duckdb_version"] = version_result[0] if version_result else "unknown"
    except Exception:
        stats["duckdb_version"] = "unknown"

    stats["duckdb_status"] = "connected"

    try:
        # Memory usage info
        memory_setting = conn.execute("SELECT current_setting('memory_limit')").fetchone()
        stats["memory_limit"] = memory_setting[0] if memory_setting else "unknown"
    except Exception:
        stats["memory_limit"] = "unknown"

    try:
        threads_setting = conn.execute("SELECT current_setting('threads')").fetchone()
        stats["threads"] = threads_setting[0] if threads_setting else "unknown"
    except Exception:
        stats["threads"] = "unknown"

    # Sales data aggregations — only if a sales_data-like table exists
    stats["sales_summary"] = None
    try:
        sales_table = None
        for (table_name,) in tables_result:
            if "sales" in table_name.lower():
                sales_table = table_name
                break

        if sales_table is not None:
            # Determine column names available in the sales table
            col_result = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                [sales_table],
            ).fetchall()
            available_cols = {row[0].lower() for row in col_result}

            sales_summary: Dict[str, Any] = {}

            # Total revenue
            if "revenue" in available_cols or "amount" in available_cols or "total" in available_cols:
                rev_col = "revenue" if "revenue" in available_cols else ("amount" if "amount" in available_cols else "total")
                try:
                    total_rev = conn.execute(
                        f'SELECT SUM("{rev_col}") FROM "{sales_table}"'
                    ).fetchone()[0]
                    sales_summary["total_revenue"] = float(total_rev) if total_rev is not None else 0.0
                except Exception:
                    sales_summary["total_revenue"] = None

            # Unique customers
            if "customer" in available_cols or "customer_id" in available_cols:
                cust_col = "customer_id" if "customer_id" in available_cols else "customer"
                try:
                    unique_cust = conn.execute(
                        f'SELECT COUNT(DISTINCT "{cust_col}") FROM "{sales_table}"'
                    ).fetchone()[0]
                    sales_summary["unique_customers"] = int(unique_cust)
                except Exception:
                    sales_summary["unique_customers"] = None

            # Top category
            if "category" in available_cols:
                try:
                    top_cat = conn.execute(
                        f'SELECT "category", COUNT(*) as cnt FROM "{sales_table}" GROUP BY "category" ORDER BY cnt DESC LIMIT 1',
                    ).fetchone()
                    if top_cat:
                        sales_summary["top_category"] = {"name": top_cat[0], "count": int(top_cat[1])}
                except Exception:
                    pass

            # Average order value
            if "revenue" in available_cols or "amount" in available_cols or "total" in available_cols:
                rev_col = "revenue" if "revenue" in available_cols else ("amount" if "amount" in available_cols else "total")
                try:
                    avg_val = conn.execute(
                        f'SELECT AVG("{rev_col}") FROM "{sales_table}"'
                    ).fetchone()[0]
                    sales_summary["avg_order_value"] = float(avg_val) if avg_val is not None else 0.0
                except Exception:
                    sales_summary["avg_order_value"] = None

            if sales_summary:
                sales_summary["source_table"] = sales_table
                stats["sales_summary"] = sales_summary
    except Exception as exc:
        logger.warning("Failed to compute sales summary: %s", exc)

    return APIResponse(
        success=True,
        data=stats,
        message="Dashboard statistics retrieved",
    )


@router.get(
    "/dashboard",
    response_model=APIResponse[DashboardConfig],
    summary="Get dashboard configuration",
    description="Retrieve the current dashboard configuration.",
)
async def get_dashboard(
    current_user: dict = Depends(get_current_user),
) -> APIResponse[DashboardConfig]:
    """
    Get the default dashboard configuration.

    In a full implementation, this would support multiple dashboards
    per user with sharing capabilities.
    """
    dashboard = _dashboards.get("default")
    if dashboard is None:
        dashboard = DashboardConfig(
            id=0,
            name="Empty Dashboard",
            widgets=[],
        )

    return APIResponse(
        success=True,
        data=dashboard,
        message="Dashboard configuration retrieved",
    )


@router.put(
    "/dashboard",
    response_model=APIResponse[DashboardConfig],
    summary="Update dashboard configuration",
    description="Update the dashboard layout, widgets, or filters.",
)
async def update_dashboard(
    update: DashboardUpdate,
    current_user: dict = Depends(get_current_user),
) -> APIResponse[DashboardConfig]:
    """
    Update the dashboard configuration.

    Supports partial updates — only provided fields are changed.
    """
    dashboard = _dashboards.get("default", DashboardConfig(id=1, name="Dashboard"))

    # Apply partial updates
    if update.name is not None:
        dashboard.name = update.name
    if update.description is not None:
        dashboard.description = update.description
    if update.widgets is not None:
        dashboard.widgets = update.widgets
    if update.layout is not None:
        dashboard.layout = update.layout
    if update.filters is not None:
        dashboard.filters = update.filters

    # Update timestamp
    dashboard.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    _dashboards["default"] = dashboard

    return APIResponse(
        success=True,
        data=dashboard,
        message="Dashboard updated successfully",
    )


# ── Statistical Summary ──────────────────────────────────────────────────


@router.get(
    "/stats/{dataset_id}",
    response_model=APIResponse[List[StatisticalSummary]],
    summary="Get statistical summary",
    description="Compute descriptive statistics for all numeric columns in a dataset.",
)
async def get_statistics(
    dataset_id: int,
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb_connection),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[List[StatisticalSummary]]:
    """
    Compute statistical summary for a dataset.

    Returns descriptive statistics (count, mean, median, std, min, max,
    percentiles, missing count) for each column. Numeric columns get
    full statistics; non-numeric columns get count and type info only.
    """
    query_service = QueryService(conn)
    analytics_service = AnalyticsService()

    # Find the table by dataset_id
    tables = query_service.list_tables()
    target_table = None
    for table_name in tables:
        if hash(table_name) % (10**8) == dataset_id:
            target_table = table_name
            break

    if target_table is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} not found",
        )

    # Fetch data
    try:
        df = query_service.execute_query(f'SELECT * FROM "{target_table}"')
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dataset: {str(exc)}",
        )

    # Compute statistics
    try:
        stats = analytics_service.compute_statistics(df)
    except Exception as exc:
        logger.error("Statistics computation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute statistics: {str(exc)}",
        )

    # Convert to response schema
    summaries = []
    for col_name, col_stats in stats.items():
        summaries.append(
            StatisticalSummary(
                column_name=col_name,
                count=col_stats.get("count", 0),
                mean=col_stats.get("mean"),
                median=col_stats.get("median"),
                std=col_stats.get("std"),
                min=col_stats.get("min"),
                max=col_stats.get("max"),
                q25=col_stats.get("q25"),
                q75=col_stats.get("q75"),
                missing_count=col_stats.get("missing_count", 0),
                dtype=col_stats.get("dtype", "unknown"),
            )
        )

    return APIResponse(
        success=True,
        data=summaries,
        message=f"Statistics computed for {len(summaries)} columns",
    )
