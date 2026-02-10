"""
DashML Type Definitions - TypedDict for IDE support and type checking

These types define the STRUCTURE of DashML specs, not valid values.
Validation of values (e.g., supported chart types) happens in the validator.
"""
from typing import TypedDict, List, Union, Dict, Any


class StyleColors(TypedDict, total=False):
    """Color definitions for dashboard styling"""
    background: str
    card: str
    primary: str
    text: str
    buttons: str
    secondary: List[str]


class StyleSpec(TypedDict):
    """DashML Style specification (.dmls file)"""
    version: Union[str, int, float]
    colors: StyleColors


class DataSpec(TypedDict, total=False):
    """
    Data source specification.

    Supports three data source types:
    - CSV: Requires 'path' field pointing to CSV file (e.g., "./data/sales.csv")
    - SQL: Requires 'path' field with schema.table format:
           - Simple: "public.sales_data"
           - With spaces/special chars: "[Public Data].[Sales Data]"
           Optional 'database_id' (can be auto-created via CLI args)
    - BigQuery: Requires 'path' field with dataset.table format:
           - Example: "products_postresql.orders_one_week"
           Requires --bq-project CLI arg for project ID

    Note: Using total=False allows type-specific fields to be optional.
    The validator ensures required fields are present for each type.
    """
    type: str              # "csv", "sql", or "bigquery" (required)
    path: str              # CSV: file path, SQL: schema.table, BigQuery: dataset.table (required)
    # SQL-specific fields
    database_id: int       # Superset database ID (optional - auto-created from CLI if not provided)
    # Legacy SQL fields (deprecated - use path instead)
    schema: str            # DEPRECATED: Use path="schema.table" instead
    table_name: str        # DEPRECATED: Use path="schema.table" instead


class FilterSpec(TypedDict, total=False):
    """
    Filter specification for chart data.

    Filters are applied before aggregation to reduce the dataset.

    Example:
        filters:
          - field: "country"
            op: "eq"
            value: "USA"
          - field: "amount"
            op: "gte"
            value: 100
    """
    field: str  # Column name to filter on
    op: str     # Operator: eq, ne, gt, lt, gte, lte, in, contains
    value: Any  # Value to compare against (type depends on op)


class ChartSpec(TypedDict, total=False):
    """
    Chart specification.

    Supported chart types:
    - bar: Vertical bar chart
    - line: Line chart with points
    - scatter: Scatter plot
    - pie: Pie chart (uses secondary colors)
    - area: Filled area chart
    - histogram: Distribution histogram
    - stacked_bar: Stacked bars (requires 'group' field)
    - grouped_bar: Grouped/clustered bars (requires 'group' field)
    - geo: Choropleth map (countries colored by value)

    Type hints (optional):
    - x_type: Explicit type for x-axis values ("date", "number", "string")
    - y_type: Explicit type for y-axis values ("number", "string")
              Used to cast y values before aggregation (e.g., parse strings as numbers)

    Histogram options:
    - bins: Number of bins for histogram (default: 20)

    Data processing (applied in order: filter -> aggregate -> sort -> limit):
    - filters: List of filter conditions applied before aggregation
    - sort: Field to sort by after aggregation ("x" or "y")
    - sort_order: Sort direction ("asc" or "desc", default: "asc")
    - limit: Maximum number of rows after aggregation

    When x_type: "date" is specified, data is sorted chronologically.

    Note: Using total=False allows optional fields like 'title' and 'agg'.
    The validator ensures required fields are present.
    """
    id: str
    type: str  # One of the supported chart types above
    title: str
    x: str
    y: str
    agg: str  # sum, mean, or count
    group: str  # Field to group/stack by (required for stacked_bar and grouped_bar)
    x_type: str  # Optional: "date", "number", or "string" - controls sorting/formatting
    y_type: str  # Optional: "number" or "string" - cast y values before aggregation
    bins: int  # Optional: Number of bins for histogram charts (default: 20)
    # Data processing fields
    filters: List[FilterSpec]  # Optional: Filter conditions applied before aggregation
    sort: str                  # Optional: Field to sort by ("x" or "y") after aggregation
    sort_order: str            # Optional: "asc" or "desc" (default: "asc")
    limit: int                 # Optional: Max rows after aggregation


class PageSpec(TypedDict, total=False):
    """
    Page specification for multi-page dashboards.

    A page groups multiple charts together with metadata.
    """
    id: str
    title: str
    description: str
    charts: List[ChartSpec]


class DashMLSpec(TypedDict, total=False):
    """
    Complete DashML specification.

    This is the canonical format that all transformers receive.
    Version can be string, int, or float (YAML parses 0.000000001 as float).

    Supports two formats:
    - Legacy: top-level 'charts' array (single implicit page)
    - New: 'pages' array with embedded charts (multi-page dashboards)
    """
    version: Union[str, int, float]
    title: str
    style: str                # Path to .dmls file or built-in theme name
    data: DataSpec
    charts: List[ChartSpec]   # Legacy format (backward compatible)
    pages: List[PageSpec]     # New format (multi-page)
