"""
Pydantic schemas for request/response validation and serialisation.

This module defines the data contracts for the entire API surface.
Every endpoint's input and output is validated against these models,
providing:
    - Automatic request parsing and type coercion
    - Automatic response serialisation with exclusion of sensitive fields
    - OpenAPI documentation generation
    - Runtime validation with clear error messages

Architecture Decision:
    We keep schemas separate from ORM models to enforce a clean boundary
    between the API layer and the persistence layer. This allows each to
    evolve independently — for example, adding a field to the database
    doesn't automatically expose it to clients.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ═══════════════════════════════════════════════════════════════════════════
# Generic API Response Wrapper
# ═══════════════════════════════════════════════════════════════════════════

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """
    Standardised response envelope for all API endpoints.

    Wrapping every response in a consistent structure makes it easy for
    clients to handle success/error uniformly:

        {
            "success": true,
            "data": { ... },
            "message": "Operation completed",
            "timestamp": "2024-01-15T10:30:00Z"
        }

    Attributes:
        success: Whether the operation succeeded.
        data: The response payload (generic type).
        message: Human-readable description of the result.
        timestamp: ISO 8601 timestamp of the response.
    """
    success: bool = True
    data: Optional[T] = None
    message: str = "Operation completed successfully"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════════════════
# Authentication Schemas
# ═══════════════════════════════════════════════════════════════════════════

class UserCreate(BaseModel):
    """
    Schema for user registration.

    Attributes:
        email: User's email address (used as login identifier).
        username: Display name (must be unique).
        password: Plaintext password — hashed before storage.
    """
    email: str = Field(..., description="User email address")
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    password: str = Field(..., min_length=8, max_length=128, description="Password (min 8 chars)")


class UserLogin(BaseModel):
    """
    Schema for user login.

    Supports login by either email or username.
    """
    email: Optional[str] = Field(None, description="Email address")
    username: Optional[str] = Field(None, description="Username")
    password: str = Field(..., description="Password")


class UserResponse(BaseModel):
    """
    Schema for user data returned to clients.

    Never includes the password hash — the model_config explicitly
    prevents accidental leakage via ORM model population.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None


class Token(BaseModel):
    """
    Schema for JWT token response.

    Returned after successful login or token refresh.
    """
    access_token: str = Field(..., description="JWT access token")
    refresh_token: Optional[str] = Field(None, description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token lifetime in seconds")


class TokenRefresh(BaseModel):
    """Schema for token refresh request."""
    refresh_token: str = Field(..., description="Valid refresh token")


# ═══════════════════════════════════════════════════════════════════════════
# Data / Query Schemas
# ═══════════════════════════════════════════════════════════════════════════

class QueryRequest(BaseModel):
    """
    Schema for SQL query execution requests against DuckDB.

    The SQL is validated before execution to prevent destructive
    operations (DROP, DELETE on system tables, etc.).

    Attributes:
        sql: The SQL query string to execute.
        limit: Maximum number of rows to return (safety cap).
        format: Desired output format — 'json' or 'csv'.
    """
    sql: str = Field(..., min_length=1, max_length=10000, description="SQL query to execute")
    limit: int = Field(default=1000, ge=1, le=100000, description="Maximum rows to return")
    format: str = Field(default="json", pattern="^(json|csv)$", description="Output format")


class QueryResponse(BaseModel):
    """
    Schema for SQL query results.

    Attributes:
        columns: List of column names in the result set.
        rows: List of row dictionaries (column_name → value).
        row_count: Total number of rows returned.
        execution_time_ms: Query execution time in milliseconds.
        truncated: Whether the result was truncated due to the limit.
    """
    columns: List[str]
    rows: List[dict[str, Any]]
    row_count: int
    execution_time_ms: float
    truncated: bool = False


class DatasetUpload(BaseModel):
    """
    Schema for dataset upload metadata.

    The actual file is sent as multipart/form-data; this schema
    captures the accompanying metadata.

    Attributes:
        name: Human-readable dataset name.
        description: Optional description.
        tags: Optional tags for categorisation.
    """
    name: str = Field(..., min_length=1, max_length=200, description="Dataset name")
    description: Optional[str] = Field(None, max_length=2000, description="Dataset description")
    tags: Optional[List[str]] = Field(None, description="Tags for categorisation")


class DatasetInfo(BaseModel):
    """
    Schema for dataset metadata returned to clients.

    Includes both user-provided metadata and system-computed
    statistics (row count, column info, file size).
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    table_name: str = Field(..., description="DuckDB table name storing this dataset")
    row_count: int = 0
    column_count: int = 0
    columns: Optional[List[dict[str, Any]]] = None
    file_size_bytes: Optional[int] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class DatasetExportRequest(BaseModel):
    """Schema for dataset export configuration."""
    format: str = Field(default="csv", pattern="^(csv|parquet|json)$", description="Export format")
    columns: Optional[List[str]] = Field(None, description="Specific columns to export")
    filter_sql: Optional[str] = Field(None, description="WHERE clause to filter rows")


# ═══════════════════════════════════════════════════════════════════════════
# Analytics Schemas
# ═══════════════════════════════════════════════════════════════════════════

class AggregationRequest(BaseModel):
    """
    Schema for aggregation query requests.

    Attributes:
        table_name: DuckDB table to aggregate.
        group_by: Columns to group by.
        metrics: Aggregation expressions, e.g. {"total_revenue": "SUM(revenue)"}.
        filter_sql: Optional WHERE clause for pre-filtering.
        having_sql: Optional HAVING clause for post-filtering groups.
    """
    table_name: str = Field(..., description="Source table name")
    group_by: List[str] = Field(..., min_length=1, description="Columns to group by")
    metrics: dict[str, str] = Field(
        ..., description="Metric alias → SQL expression, e.g. {'avg_price': 'AVG(price)'}"
    )
    filter_sql: Optional[str] = Field(None, description="Optional WHERE clause")
    having_sql: Optional[str] = Field(None, description="Optional HAVING clause")


class PivotRequest(BaseModel):
    """
    Schema for pivot table generation.

    Attributes:
        table_name: Source DuckDB table.
        index: Column(s) for the pivot rows.
        columns: Column whose unique values become pivot columns.
        values: Column(s) to aggregate in the pivot cells.
        aggfunc: Aggregation function — sum, mean, count, min, max.
    """
    table_name: str = Field(..., description="Source table name")
    index: List[str] = Field(..., min_length=1, description="Row index columns")
    columns: str = Field(..., description="Column to pivot on")
    values: List[str] = Field(..., min_length=1, description="Value columns to aggregate")
    aggfunc: str = Field(
        default="sum",
        pattern="^(sum|mean|count|min|max|std|var)$",
        description="Aggregation function",
    )


class AnalyticsResult(BaseModel):
    """
    Schema for analytics computation results.

    Attributes:
        result_type: What kind of analysis was performed.
        data: The computed result (flexible structure).
        metadata: Additional context (execution time, row counts, etc.).
    """
    result_type: str = Field(..., description="Type of analysis performed")
    data: Any = Field(..., description="Analysis result data")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class StatisticalSummary(BaseModel):
    """
    Schema for statistical summary of a dataset column.

    Provides common descriptive statistics computed by the
    analytics service.
    """
    column_name: str
    count: int
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    q25: Optional[float] = Field(None, description="25th percentile")
    q75: Optional[float] = Field(None, description="75th percentile")
    missing_count: int = 0
    dtype: str = "unknown"


class ChartTypeSuggestion(BaseModel):
    """Schema for auto-detected chart type suggestion."""
    chart_type: str = Field(..., description="Suggested chart type")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    reasoning: str = Field(..., description="Why this chart type was suggested")


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard Schemas
# ═══════════════════════════════════════════════════════════════════════════

class DashboardWidget(BaseModel):
    """Schema for a single dashboard widget."""
    id: str = Field(..., description="Unique widget identifier")
    type: str = Field(..., description="Widget type: chart, table, metric, text")
    title: str = Field(..., description="Widget title")
    config: dict[str, Any] = Field(default_factory=dict, description="Widget configuration")
    position: dict[str, int] = Field(
        default_factory=lambda: {"x": 0, "y": 0, "w": 6, "h": 4},
        description="Grid position {x, y, w, h}",
    )


class DashboardConfig(BaseModel):
    """
    Schema for dashboard configuration.

    A dashboard is a collection of widgets arranged in a grid layout.
    The config is stored as JSON and can be updated piecemeal.

    Attributes:
        id: Dashboard identifier.
        name: Dashboard display name.
        description: Optional description.
        widgets: Ordered list of dashboard widgets.
        layout: Grid layout configuration.
        filters: Global filters applied to all widgets.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=200, description="Dashboard name")
    description: Optional[str] = None
    widgets: List[DashboardWidget] = Field(default_factory=list)
    layout: dict[str, Any] = Field(default_factory=dict, description="Grid layout config")
    filters: dict[str, Any] = Field(default_factory=dict, description="Global filters")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DashboardUpdate(BaseModel):
    """Schema for partial dashboard update."""
    name: Optional[str] = None
    description: Optional[str] = None
    widgets: Optional[List[DashboardWidget]] = None
    layout: Optional[dict[str, Any]] = None
    filters: Optional[dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════════════════
# Enumerations
# ═══════════════════════════════════════════════════════════════════════════

class DatasetFormat(str, Enum):
    """Supported dataset file formats."""
    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"
    TSV = "tsv"


class ExportFormat(str, Enum):
    """Supported export formats."""
    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"


class ChartType(str, Enum):
    """Supported chart types for auto-detection."""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    HEATMAP = "heatmap"
    AREA = "area"
    TABLE = "table"


# ═══════════════════════════════════════════════════════════════════════════
# Health / Info Schemas
# ═══════════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    """Schema for health check endpoint."""
    status: str = "healthy"
    version: str
    environment: str
    duckdb_status: str = "unknown"
    postgres_status: str = "unknown"
    uptime_seconds: Optional[float] = None


class APIInfoResponse(BaseModel):
    """Schema for API information endpoint."""
    name: str
    version: str
    description: str
    endpoints: List[dict[str, Any]]
