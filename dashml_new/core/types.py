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
    # Normalizer-resolved fields (populated by normalizer, not by user):
    csv_path: str       # for CSV: resolved absolute file path
    sql_schema: str     # for SQL: parsed schema from path
    sql_table: str      # for SQL: parsed table from path
    bq_dataset: str     # for BigQuery: parsed dataset from path
    bq_table: str       # for BigQuery: parsed table from path


class DerivedFieldSpec(TypedDict, total=False):
    """
    Derived (calculated) column spec.

    Creates a new column computed from existing columns.
    Available to all charts as if it were a raw column in the data source.

    Example:
        derived_fields:
          - name: "on_time_rate"
            expression: "100 - {pct_delayed_15plus}"
          - name: "delay_index"
            expression: "({average_delay_mins} + {pct_delayed_15plus}) / 2"
    """
    name: str          # Column name to create (required, valid identifier)
    expression: str    # Arithmetic expression with {col_ref} placeholders (required)


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
    op: str     # Operator: eq, ne, gt, lt, gte, lte, in, contains, range
    value: Any  # Value to compare against (type depends on op; list for in/range)


class ChartSpec(TypedDict, total=False):
    """
    Chart specification.

    Supported chart types:
    - bar: Vertical bar chart
    - line: Line chart with points
    - scatter: Scatter plot
    - bubble: Bubble chart (scatter with size encoding, requires 'size' field)
    - heatmap: Heatmap (2D grid with color intensity, x and y are both categorical)
    - box: Box plot (shows distribution: min, Q1, median, Q3, max)
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
    group: str  # Field to group/stack by (required for stacked_bar, grouped_bar, and bubble)
    size: str   # Field for bubble size (required for bubble chart)
    x_type: str  # Optional: "date", "number", or "string" - controls sorting/formatting
    y_type: str  # Optional: "number" or "string" - cast y values before aggregation
    bins: int  # Optional: Number of bins for histogram charts (default: 20)
    bin: bool  # Optional: Enable binning on x-axis for non-histogram charts (default: false)
    # Data processing fields
    filters: List[FilterSpec]  # Optional: Filter conditions applied before aggregation
    sort: str                  # Optional: Field to sort by ("x" or "y") after aggregation
    sort_order: str            # Optional: "asc" or "desc" (default: "asc")
    limit: int                 # Optional: Max rows after aggregation
    # Metric widget fields (type: "metric" only):
    format: str  # Optional: Python/D3 format string e.g. ",.0f", ".1f", "$,.2f"
    suffix: str  # Optional: text appended after value e.g. " mins", "%"
    geo_encoding: str  # Optional: "iso2", "iso3", or "name" — auto-detected if omitted
    # Axis scale and decoration fields:
    x_scale: str  # Optional: "linear" (default) or "log"
    y_scale: str  # Optional: "linear" (default) or "log"
    annotations: list  # Optional: list of {"text": str, "x": any, "y": any, "color": str}
    reference_lines: list  # Optional: list of {"axis": "x"|"y", "value": number, "label": str, "style": str}
    # Normalizer-resolved fields:
    needs_aggregation: bool   # True if chart type in CHARTS_NEED_AGGREGATION
    uses_raw_data: bool       # True if chart type in CHARTS_USE_RAW_DATA
    sql: str                  # SQL template with {table_ref} and {filter_clause} placeholders (sql/bigquery only)
    static_conditions: List[str]  # Compile-time SQL conditions from chart filters (sql/bigquery only)


class DashboardFilterSpec(TypedDict, total=False):
    """
    Dashboard-level runtime filter widget spec.

    Renders as a selectbox (select) or multiselect above all charts on a page.
    Filter values are applied to every chart on that page at request time.

    Example:
        filters:
          - field: "scheduled_charter"
            type: "select"
            label: "Flight Type"
          - field: "origin_destination_country"
            type: "multiselect"
            label: "Country"
            values: ["UK", "US", "DE"]   # optional; omit → fetch DISTINCT at runtime
    """
    field: str           # Column name to filter on (required)
    type: str            # Widget type: "select" | "multiselect" (required)
    label: str           # Display label (optional; defaults to humanized field name)
    values: List[Any]    # Static option list (optional; omit → DISTINCT query at runtime)


class PageSpec(TypedDict, total=False):
    """
    Page specification for multi-page dashboards.

    A page groups multiple charts together with metadata.
    Supports optional grid layout for subplot-style arrangements.
    """
    id: str
    title: str
    description: str
    charts: List[ChartSpec]
    filters: List[DashboardFilterSpec]   # Optional: dashboard-level runtime filter widgets
    layout: dict  # Optional: {"columns": int} — grid layout for charts on this page


class DashMLSpec(TypedDict, total=False):
    """
    Complete DashML specification — describes the .dashml file format.

    This is a documentation type for what users write in .dashml files.
    The pipeline output that transformers consume is NormalizedSpec.

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
    derived_fields: List[DerivedFieldSpec]  # Global calculated columns (optional)


class ResolvedStyle(TypedDict, total=False):
    """Fully resolved style colors — loaded from .dmls and merged with defaults."""
    background: str
    card: str
    primary: str
    text: str
    buttons: str
    sequential: str
    secondary: List[str]


class NormalizedSpec(TypedDict, total=False):
    """
    Normalized DashML spec — the pipeline output that transformers consume.

    Guarantees:
    - pages[] always exists (single-page specs are wrapped)
    - style is fully resolved (colors dict, not a filename)
    - data has pre-parsed path components (sql_schema, bq_dataset, etc.)
    - charts have needs_aggregation/uses_raw_data annotations
    - version is coerced to string
    - db_config is attached (not stored on transformer instance)
    """
    version: str                 # coerced to string
    title: str
    data: DataSpec               # same DataSpec, with parsed fields filled
    pages: List[PageSpec]        # ALWAYS pages (single-page wrapped)
    style: ResolvedStyle         # resolved colors, not a filename
    db_config: Dict[str, Any]    # from CLI args (SQL/BigQuery config)
    source_file: str             # absolute path to the .dashml file
    derived_fields: List[DerivedFieldSpec]  # passed through from spec
