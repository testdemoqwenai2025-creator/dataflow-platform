"""
Analytics computation service.

This service provides high-level analytics computations on pandas DataFrames:

    1. **Descriptive statistics** — mean, median, std, percentiles, missing counts
    2. **Aggregation** — GROUP BY with configurable metrics
    3. **Pivot tables** — Flexible pivot table generation
    4. **Chart type detection** — Auto-suggest appropriate visualisation

Architecture Decision:
    We perform analytics in-memory using pandas/numpy. For large datasets,
    DuckDB's native aggregation functions should be used instead (via
    query_service.execute_query). This service is optimised for moderate-
    sized results (up to ~1M rows) where pandas provides a rich, ergonomic
    API with minimal overhead.

    For chart type detection, we use simple heuristics based on column
    data types and value distributions. A more sophisticated approach
    would use a trained model, but heuristics are fast and interpretable.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Service for computing analytics on DataFrames.

    All methods are stateless — they take a DataFrame and return
    computed results. This makes the service easy to test and
    safe to use from multiple concurrent requests.
    """

    def compute_statistics(self, df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Compute descriptive statistics for each column in a DataFrame.

        For numeric columns: count, mean, median, std, min, max,
        25th/75th percentiles, missing count, dtype.
        For non-numeric columns: count, missing count, dtype,
        unique count, most frequent value.

        Args:
            df: Input DataFrame to analyze.

        Returns:
            Dictionary mapping column names to their statistics.
            Example:
                {
                    "revenue": {
                        "count": 1000, "mean": 5234.5, "median": 4321.0,
                        "std": 2100.3, "min": 100.0, "max": 15000.0,
                        "q25": 3100.0, "q75": 6800.0, "missing_count": 5,
                        "dtype": "float64"
                    },
                    "category": {
                        "count": 1000, "missing_count": 2,
                        "dtype": "object", "unique_count": 12,
                        "top_value": "Electronics", "top_freq": 150
                    }
                }
        """
        result: Dict[str, Dict[str, Any]] = {}

        for col in df.columns:
            series = df[col]
            missing = int(series.isna().sum())
            col_stats: Dict[str, Any] = {
                "count": int(len(series)),
                "missing_count": missing,
                "dtype": str(series.dtype),
            }

            if pd.api.types.is_numeric_dtype(series):
                # Drop NaNs for numeric computations
                clean = series.dropna()

                if len(clean) > 0:
                    col_stats["mean"] = float(clean.mean())
                    col_stats["median"] = float(clean.median())
                    col_stats["std"] = float(clean.std()) if len(clean) > 1 else 0.0
                    col_stats["min"] = float(clean.min())
                    col_stats["max"] = float(clean.max())
                    col_stats["q25"] = float(clean.quantile(0.25))
                    col_stats["q75"] = float(clean.quantile(0.75))
                else:
                    col_stats.update({
                        "mean": None, "median": None, "std": None,
                        "min": None, "max": None, "q25": None, "q75": None,
                    })

            else:
                # Non-numeric: provide categorical statistics
                clean = series.dropna()
                col_stats["unique_count"] = int(clean.nunique())

                if len(clean) > 0:
                    value_counts = clean.value_counts()
                    col_stats["top_value"] = str(value_counts.index[0])
                    col_stats["top_freq"] = int(value_counts.iloc[0])
                else:
                    col_stats["top_value"] = None
                    col_stats["top_freq"] = None

            result[col] = col_stats

        return result

    def compute_aggregation(
        self,
        df: pd.DataFrame,
        group_by: List[str],
        metrics: Dict[str, str],
    ) -> pd.DataFrame:
        """
        Compute a grouped aggregation on a DataFrame.

        Args:
            df: Input DataFrame.
            group_by: Column names to group by.
            metrics: Mapping of output column name → aggregation expression.
                Supported expressions: 'sum', 'mean', 'count', 'min', 'max',
                'std', 'var', 'median', 'nunique', or a column name with
                function like 'revenue:sum'.

        Returns:
            Aggregated DataFrame with group_by columns and metric columns.

        Example:
            >>> service.compute_aggregation(
            ...     df,
            ...     group_by=["region"],
            ...     metrics={"total_revenue": "sum", "avg_price": "mean"},
            ... )
        """
        # Build aggregation dictionary for pandas
        agg_dict: Dict[str, List[str]] = {}

        for alias, expr in metrics.items():
            # Parse expression: either a plain function name or "column:function"
            if ":" in expr:
                col_name, func = expr.split(":", 1)
                if col_name not in df.columns:
                    logger.warning("Column '%s' not found, skipping metric '%s'", col_name, alias)
                    continue
                if col_name not in agg_dict:
                    agg_dict[col_name] = []
                agg_dict[col_name].append(func)
            else:
                # Plain function — apply to all numeric columns
                func = expr
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                for col in numeric_cols:
                    if col not in group_by and col not in agg_dict:
                        agg_dict[col] = []
                    if col not in group_by:
                        agg_dict[col].append(func)

        if not agg_dict:
            logger.warning("No valid aggregation metrics found")
            return pd.DataFrame()

        # Perform groupby aggregation
        try:
            grouped = df.groupby(group_by, dropna=False).agg(agg_dict)

            # Flatten multi-level column index
            grouped.columns = [
                f"{col}_{func}" if func else col
                for col, func in grouped.columns
            ]
            grouped = grouped.reset_index()

            return grouped

        except Exception as exc:
            logger.error("Aggregation computation error: %s", exc)
            raise

    def generate_pivot(
        self,
        df: pd.DataFrame,
        index: List[str],
        columns: str,
        values: List[str],
        aggfunc: str = "sum",
    ) -> pd.DataFrame:
        """
        Generate a pivot table from a DataFrame.

        Args:
            df: Input DataFrame.
            index: Column(s) to use as row index.
            columns: Column whose unique values become pivot columns.
            values: Column(s) to aggregate in the pivot cells.
            aggfunc: Aggregation function — sum, mean, count, min, max, std, var.

        Returns:
            Pivoted DataFrame with index columns as rows and
            unique values of `columns` as columns.

        Example:
            >>> service.generate_pivot(
            ...     df,
            ...     index=["region"],
            ...     columns="year",
            ...     values=["revenue"],
            ...     aggfunc="sum",
            ... )
        """
        # Map string aggfunc to pandas-compatible function
        agg_map = {
            "sum": "sum",
            "mean": "mean",
            "count": "count",
            "min": "min",
            "max": "max",
            "std": "std",
            "var": "var",
        }

        pandas_aggfunc = agg_map.get(aggfunc, "sum")

        try:
            pivot = pd.pivot_table(
                df,
                index=index,
                columns=columns,
                values=values,
                aggfunc=pandas_aggfunc,
                fill_value=0,
            )

            # Flatten multi-level column index if single value column
            if len(values) == 1:
                pivot.columns = [str(col) for col in pivot.columns]

            return pivot

        except Exception as exc:
            logger.error("Pivot generation error: %s", exc)
            raise

    def auto_detect_chart_type(
        self,
        df: pd.DataFrame,
        x: Optional[str] = None,
        y: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Auto-detect the most appropriate chart type for given data.

        Uses heuristics based on:
            - Number of data points
            - Data types of x and y columns
            - Cardinality of categorical columns
            - Temporal patterns in the data

        Args:
            df: Input DataFrame.
            x: Column name for x-axis (optional — auto-selected if None).
            y: Column name for y-axis (optional — auto-selected if None).

        Returns:
            Dictionary with:
                - chart_type: Suggested chart type (bar, line, scatter, pie, histogram, area)
                - confidence: Confidence score (0.0 to 1.0)
                - reasoning: Explanation of the suggestion
                - x_column: Suggested x-axis column
                - y_column: Suggested y-axis column
        """
        n_rows = len(df)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()

        # If x/y not specified, make best guesses
        if x is None and categorical_cols:
            x = categorical_cols[0]
        elif x is None and numeric_cols:
            x = numeric_cols[0]

        if y is None and numeric_cols:
            y = numeric_cols[0] if numeric_cols[0] != x else (
                numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0]
            )

        # Determine chart type based on data characteristics
        if x is None or y is None:
            # Insufficient columns for a chart
            return {
                "chart_type": "table",
                "confidence": 0.9,
                "reasoning": "Insufficient numeric or categorical columns for visualisation; tabular display recommended",
                "x_column": x,
                "y_column": y,
            }

        x_is_categorical = x in categorical_cols
        y_is_numeric = y in numeric_cols
        x_nunique = df[x].nunique() if x in df.columns else 0

        # Decision logic
        if x_is_categorical and y_is_numeric:
            if x_nunique <= 6:
                return {
                    "chart_type": "pie",
                    "confidence": 0.75,
                    "reasoning": f"Low-cardinality categorical x ({x_nunique} unique values) with numeric y — pie chart shows proportions clearly",
                    "x_column": x,
                    "y_column": y,
                }
            elif x_nunique <= 20:
                return {
                    "chart_type": "bar",
                    "confidence": 0.85,
                    "reasoning": f"Categorical x ({x_nunique} unique) with numeric y — bar chart enables comparison across categories",
                    "x_column": x,
                    "y_column": y,
                }
            else:
                return {
                    "chart_type": "bar",
                    "confidence": 0.6,
                    "reasoning": f"High-cardinality categorical x ({x_nunique} unique) — consider filtering or grouping; horizontal bar chart may be more readable",
                    "x_column": x,
                    "y_column": y,
                }

        elif not x_is_categorical and y_is_numeric:
            # Check if x looks like a date/time series
            x_col = df[x]
            if pd.api.types.is_datetime64_any_dtype(x_col):
                return {
                    "chart_type": "line",
                    "confidence": 0.9,
                    "reasoning": "Datetime x-axis with numeric y — line chart shows trends over time",
                    "x_column": x,
                    "y_column": y,
                }
            elif n_rows > 50:
                return {
                    "chart_type": "scatter",
                    "confidence": 0.8,
                    "reasoning": f"Numeric x and y with {n_rows} data points — scatter plot reveals correlations and distributions",
                    "x_column": x,
                    "y_column": y,
                }
            else:
                return {
                    "chart_type": "line",
                    "confidence": 0.7,
                    "reasoning": f"Numeric x and y with few data points ({n_rows}) — line chart shows the progression",
                    "x_column": x,
                    "y_column": y,
                }

        elif x_is_categorical and not y_is_numeric:
            return {
                "chart_type": "table",
                "confidence": 0.8,
                "reasoning": "Both x and y are categorical — tabular display is more informative than charts",
                "x_column": x,
                "y_column": y,
            }

        else:
            # Both numeric
            return {
                "chart_type": "scatter",
                "confidence": 0.75,
                "reasoning": "Both x and y are numeric — scatter plot reveals relationships between variables",
                "x_column": x,
                "y_column": y,
            }

    def compute_correlation_matrix(
        self,
        df: pd.DataFrame,
        method: str = "pearson",
    ) -> pd.DataFrame:
        """
        Compute correlation matrix for numeric columns.

        Args:
            df: Input DataFrame.
            method: Correlation method — 'pearson', 'kendall', or 'spearman'.

        Returns:
            Correlation matrix as a DataFrame.
        """
        numeric_df = df.select_dtypes(include=[np.number])
        return numeric_df.corr(method=method)

    def detect_outliers(
        self,
        df: pd.DataFrame,
        column: str,
        method: str = "iqr",
        threshold: float = 1.5,
    ) -> pd.DataFrame:
        """
        Detect outliers in a numeric column using IQR or z-score method.

        Args:
            df: Input DataFrame.
            column: Column name to check for outliers.
            method: 'iqr' (interquartile range) or 'zscore' (standard deviations).
            threshold: For IQR: multiplier for IQR range. For zscore: number of std devs.

        Returns:
            DataFrame containing only the outlier rows.
        """
        if column not in df.columns or not pd.api.types.is_numeric_dtype(df[column]):
            raise ValueError(f"Column '{column}' is not numeric or does not exist")

        series = df[column].dropna()

        if method == "iqr":
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
            outlier_mask = (df[column] < lower) | (df[column] > upper)

        elif method == "zscore":
            mean = series.mean()
            std = series.std()
            if std == 0:
                return pd.DataFrame()
            z_scores = (df[column] - mean) / std
            outlier_mask = z_scores.abs() > threshold

        else:
            raise ValueError(f"Unknown outlier detection method: {method}")

        return df[outlier_mask]
