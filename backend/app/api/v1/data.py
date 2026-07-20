"""
Data management endpoints: dataset CRUD, SQL queries, and exports.

This module provides the core data operations of the DataFlow Platform:

    - List, upload, inspect, and delete datasets stored in DuckDB
    - Execute arbitrary SQL queries against DuckDB tables
    - Export datasets in multiple formats (CSV, Parquet, JSON)

Architecture Decision:
    All analytical data lives in DuckDB, which excels at columnar scans
    on Parquet/CSV data. Dataset metadata (name, description, row count)
    is tracked both in DuckDB's information_schema and, when PostgreSQL
    is available, in a dedicated datasets table for durable metadata.

    File uploads are written to disk first, then loaded into DuckDB via
    its native Parquet/CSV reader, which is orders of magnitude faster
    than row-by-row insertion.
"""

import io
import os
import uuid
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.database import get_duckdb
from app.core.security import get_current_user
from app.models.schemas import (
    APIResponse,
    DatasetExportRequest,
    DatasetInfo,
    DatasetUpload,
    QueryRequest,
    QueryResponse,
)
from app.services.query_service import QueryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["Data Management"])

# Directory for uploaded files
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _generate_table_name(dataset_name: str) -> str:
    """
    Generate a safe DuckDB table name from a dataset name.

    Replaces non-alphanumeric characters with underscores and adds
    a short UUID suffix to avoid collisions.
    """
    safe_name = "".join(c if c.isalnum() else "_" for c in dataset_name.lower())
    safe_name = safe_name.strip("_")[:40]  # Truncate long names
    suffix = uuid.uuid4().hex[:8]
    return f"ds_{safe_name}_{suffix}"


def _get_dataset_info_from_duckdb(conn: duckdb.DuckDBPyConnection, table_name: str) -> Dict[str, Any]:
    """
    Retrieve metadata about a DuckDB table using information_schema.

    Returns column names, types, row count, and approximate size.
    """
    # Column information
    columns_result = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?",
        [table_name],
    ).fetchall()

    columns_info = [
        {"name": col_name, "type": col_type}
        for col_name, col_type in columns_result
    ]

    # Row count (exact for small tables, estimated for large)
    try:
        row_count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    except Exception:
        row_count = 0

    return {
        "columns": columns_info,
        "column_count": len(columns_info),
        "row_count": row_count,
    }


# ── Dataset CRUD ──────────────────────────────────────────────────────────


@router.get(
    "/datasets",
    response_model=APIResponse[List[DatasetInfo]],
    summary="List all datasets",
    description="Returns metadata for all datasets currently loaded in DuckDB.",
)
async def list_datasets(
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[List[DatasetInfo]]:
    """
    List all datasets (DuckDB tables) available for querying.

    Only shows user-created tables (prefixed with 'ds_'), not system tables.
    """
    query_service = QueryService(conn)

    try:
        tables = query_service.list_tables()
    except Exception as exc:
        logger.error("Failed to list tables: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dataset list",
        )

    datasets: List[DatasetInfo] = []
    for table_name in tables:
        try:
            info = _get_dataset_info_from_duckdb(conn, table_name)
            datasets.append(
                DatasetInfo(
                    id=hash(table_name) % (10**8),  # Pseudo-ID from table name
                    name=table_name,
                    table_name=table_name,
                    row_count=info["row_count"],
                    column_count=info["column_count"],
                    columns=info["columns"],
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                )
            )
        except Exception as exc:
            logger.warning("Skipping table %s: %s", table_name, exc)
            continue

    return APIResponse(
        success=True,
        data=datasets,
        message=f"Found {len(datasets)} datasets",
    )


@router.post(
    "/upload",
    response_model=APIResponse[DatasetInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a dataset",
    description="Upload a CSV or Parquet file and load it into DuckDB for querying.",
)
async def upload_dataset(
    file: UploadFile = File(..., description="CSV or Parquet file"),
    name: Optional[str] = Query(None, description="Dataset name (defaults to filename)"),
    description: Optional[str] = Query(None, description="Dataset description"),
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[DatasetInfo]:
    """
    Upload a CSV or Parquet file and load it into DuckDB.

    The file is first saved to disk, then DuckDB's native CSV/Parquet
    reader loads it directly into a table. This is significantly faster
    than row-by-row insertion.

    Supported formats: .csv, .tsv, .parquet, .json
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    ext = Path(file.filename).suffix.lower()
    supported = {".csv", ".tsv", ".parquet", ".json"}
    if ext not in supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Supported: {sorted(supported)}",
        )

    # Determine dataset name and table name
    dataset_name = name or Path(file.filename).stem
    table_name = _generate_table_name(dataset_name)

    # Save uploaded file to disk
    file_path = UPLOAD_DIR / f"{table_name}{ext}"
    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        logger.info("File saved: %s (%d bytes)", file_path, len(contents))
    except Exception as exc:
        logger.error("Failed to save upload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file",
        )

    # Load into DuckDB using native reader
    try:
        if ext in (".csv", ".tsv"):
            delimiter = "\t" if ext == ".tsv" else ","
            conn.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_csv_auto('{file_path}', delim='{delimiter}')"
            )
        elif ext == ".parquet":
            conn.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_parquet('{file_path}')"
            )
        elif ext == ".json":
            conn.execute(
                f"CREATE TABLE \"{table_name}\" AS SELECT * FROM read_json_auto('{file_path}')"
            )

        logger.info("Dataset loaded into DuckDB table: %s", table_name)

    except Exception as exc:
        # Clean up file on failure
        if file_path.exists():
            file_path.unlink()
        logger.error("Failed to load dataset into DuckDB: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse file: {str(exc)}",
        )

    # Retrieve dataset metadata
    info = _get_dataset_info_from_duckdb(conn, table_name)

    dataset_info = DatasetInfo(
        id=hash(table_name) % (10**8),
        name=dataset_name,
        description=description,
        table_name=table_name,
        row_count=info["row_count"],
        column_count=info["column_count"],
        columns=info["columns"],
        file_size_bytes=len(contents),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    return APIResponse(
        success=True,
        data=dataset_info,
        message=f"Dataset '{dataset_name}' uploaded successfully with {info['row_count']} rows",
    )


@router.get(
    "/datasets/{dataset_id}",
    response_model=APIResponse[DatasetInfo],
    summary="Get dataset details",
    description="Retrieve detailed metadata for a specific dataset.",
)
async def get_dataset(
    dataset_id: int,
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[DatasetInfo]:
    """
    Get detailed information about a dataset by its ID.

    Since dataset IDs are derived from table names, we scan all
    user tables to find a matching one.
    """
    query_service = QueryService(conn)
    tables = query_service.list_tables()

    for table_name in tables:
        table_id = hash(table_name) % (10**8)
        if table_id == dataset_id:
            info = _get_dataset_info_from_duckdb(conn, table_name)

            # Check for associated file
            file_size = None
            for ext in [".csv", ".parquet", ".json", ".tsv"]:
                file_path = UPLOAD_DIR / f"{table_name}{ext}"
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    break

            dataset_info = DatasetInfo(
                id=table_id,
                name=table_name,
                table_name=table_name,
                row_count=info["row_count"],
                column_count=info["column_count"],
                columns=info["columns"],
                file_size_bytes=file_size,
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            return APIResponse(success=True, data=dataset_info, message="Dataset found")

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Dataset with ID {dataset_id} not found",
    )


@router.delete(
    "/datasets/{dataset_id}",
    response_model=APIResponse[None],
    summary="Delete a dataset",
    description="Remove a dataset from DuckDB and delete its source file.",
)
async def delete_dataset(
    dataset_id: int,
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[None]:
    """
    Delete a dataset by dropping its DuckDB table and removing
    any associated uploaded file.
    """
    query_service = QueryService(conn)
    tables = query_service.list_tables()

    for table_name in tables:
        table_id = hash(table_name) % (10**8)
        if table_id == dataset_id:
            try:
                # Drop the DuckDB table
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                logger.info("Dropped DuckDB table: %s", table_name)

                # Remove associated files
                for ext in [".csv", ".parquet", ".json", ".tsv"]:
                    file_path = UPLOAD_DIR / f"{table_name}{ext}"
                    if file_path.exists():
                        file_path.unlink()
                        logger.info("Deleted file: %s", file_path)

                return APIResponse(
                    success=True,
                    data=None,
                    message=f"Dataset '{table_name}' deleted successfully",
                )
            except Exception as exc:
                logger.error("Failed to delete dataset: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to delete dataset",
                )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Dataset with ID {dataset_id} not found",
    )


# ── SQL Query ─────────────────────────────────────────────────────────────


@router.post(
    "/query",
    response_model=APIResponse[QueryResponse],
    summary="Execute SQL query",
    description="Execute a SQL query against DuckDB and return the results.",
)
async def execute_query(
    request: QueryRequest,
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
    current_user: dict = Depends(get_current_user),
) -> APIResponse[QueryResponse]:
    """
    Execute a SQL query against the DuckDB analytical engine.

    The query is first validated for safety (no destructive operations
    on system tables), then executed with a row limit to prevent
    excessive memory consumption.
    """
    query_service = QueryService(conn)

    # Validate query safety
    is_valid, validation_msg = query_service.validate_query(request.sql)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query validation failed: {validation_msg}",
        )

    # Execute query
    try:
        start_time = time.time()
        df = query_service.execute_query(request.sql)
        execution_time_ms = (time.time() - start_time) * 1000

        # Apply row limit
        truncated = len(df) > request.limit
        if truncated:
            df = df.head(request.limit)

        # Build response
        columns = df.columns.tolist()
        rows = df.to_dict(orient="records")

        # Convert numpy/pandas types to native Python for JSON serialisation
        clean_rows = []
        for row in rows:
            clean_row = {}
            for key, value in row.items():
                if pd.isna(value):
                    clean_row[key] = None
                elif hasattr(value, "item"):
                    # numpy scalar → Python scalar
                    clean_row[key] = value.item()
                else:
                    clean_row[key] = value
            clean_rows.append(clean_row)

        query_response = QueryResponse(
            columns=columns,
            rows=clean_rows,
            row_count=len(clean_rows),
            execution_time_ms=round(execution_time_ms, 2),
            truncated=truncated,
        )

        return APIResponse(
            success=True,
            data=query_response,
            message=f"Query executed successfully ({len(clean_rows)} rows in {execution_time_ms:.1f}ms)",
        )

    except Exception as exc:
        logger.error("Query execution error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Query execution failed: {str(exc)}",
        )


# ── Export ────────────────────────────────────────────────────────────────


@router.get(
    "/export/{dataset_id}",
    summary="Export a dataset",
    description="Download a dataset in CSV, Parquet, or JSON format.",
)
async def export_dataset(
    dataset_id: int,
    format: str = Query("csv", description="Export format: csv, parquet, json"),
    columns: Optional[str] = Query(None, description="Comma-separated list of columns"),
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """
    Export a dataset as a downloadable file.

    Supports CSV, Parquet, and JSON output formats. Optionally,
    specific columns can be selected.
    """
    if format not in ("csv", "parquet", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format: {format}. Use csv, parquet, or json.",
        )

    query_service = QueryService(conn)
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

    # Build query
    select_clause = "*"
    if columns:
        col_list = [c.strip() for c in columns.split(",")]
        # Validate columns exist
        info = _get_dataset_info_from_duckdb(conn, target_table)
        valid_cols = {c["name"] for c in info["columns"]}
        invalid = set(col_list) - valid_cols
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown columns: {sorted(invalid)}",
            )
        select_clause = ", ".join(f'"{c}"' for c in col_list)

    sql = f'SELECT {select_clause} FROM "{target_table}"'
    df = query_service.execute_query(sql)

    # Convert to requested format
    buffer = io.BytesIO()
    media_type = "text/csv"
    file_extension = "csv"

    if format == "csv":
        df.to_csv(buffer, index=False)
        media_type = "text/csv"
        file_extension = "csv"
    elif format == "parquet":
        df.to_parquet(buffer, index=False)
        media_type = "application/octet-stream"
        file_extension = "parquet"
    elif format == "json":
        df.to_json(buffer, orient="records", force_ascii=False)
        media_type = "application/json"
        file_extension = "json"

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={target_table}.{file_extension}"
        },
    )
