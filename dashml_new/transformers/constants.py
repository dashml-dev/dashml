"""
DashML Transformers - Shared Constants

These constants are used across all transformers to ensure consistent behavior.
"""

# Chart type categorization by data requirements
# Charts that need data aggregation (groupby + agg function)
CHARTS_NEED_AGGREGATION = frozenset({
    "bar", "line", "area", "pie", "stacked_bar", "grouped_bar", "scatter", "bubble", "heatmap", "geo"
})

# Charts that work with raw data points (no aggregation)
# These compute their own statistics (bins for histogram, quartiles for box)
CHARTS_USE_RAW_DATA = frozenset({"histogram", "box"})

# Scalar widgets: return a single aggregated value, no x-axis
CHARTS_SCALAR = frozenset({"metric"})

# Default number of bins for histogram charts
DEFAULT_HISTOGRAM_BINS = 20

# Supported filter operators
# Used in chart.filters[].op field
SUPPORTED_FILTER_OPS = frozenset({
    "eq",       # Equal: field == value
    "ne",       # Not equal: field != value
    "gt",       # Greater than: field > value
    "lt",       # Less than: field < value
    "gte",      # Greater than or equal: field >= value
    "lte",      # Less than or equal: field <= value
    "in",       # In list: field in [value1, value2, ...]
    "contains", # Contains substring: value in field (for strings)
})

# Supported sort orders
SUPPORTED_SORT_ORDERS = frozenset({"asc", "desc"})

# Default sort order when not specified
DEFAULT_SORT_ORDER = "asc"

# Aggregation methods mapping
# Maps DashML agg names to common implementations
AGG_METHODS = {
    "sum": "sum",
    "mean": "mean",
    "count": "count",
}

# Default primary color (used across transformers)
DEFAULT_PRIMARY_COLOR = "#29b5e8"

# Default secondary colors for categorical data
DEFAULT_SECONDARY_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
]

def resolve_metric_format(fmt: str) -> str:
    """Convert human-friendly metric format names to Python/D3 format spec.

    Friendly names:
      "integer"    -> ",.0f"   e.g. 8,235,908
      "decimal"    -> ",.2f"   e.g. 14.82
      "decimal:1"  -> ",.1f"   e.g. 14.8
      "decimal:2"  -> ",.2f"   e.g. 14.82
      "decimal:N"  -> ",.Nf"   N decimal places with thousands separator
    Raw Python/D3 specs (e.g. ",.0f") are passed through unchanged for
    backward compatibility.
    """
    if fmt == "integer":
        return ",.0f"
    if fmt == "decimal":
        return ",.2f"
    if fmt.startswith("decimal:"):
        try:
            n = int(fmt.split(":")[1])
            return f",.{n}f"
        except (IndexError, ValueError):
            pass
    return fmt  # pass-through for raw format specs


# Column types for x_type/y_type hints
COLUMN_TYPES = frozenset({"date", "number", "string"})

# Date-related column names (heuristic for auto-detection)
TEMPORAL_FIELD_NAMES = frozenset({
    'date', 'time', 'timestamp', 'datetime',
    'created_at', 'updated_at', 'created', 'updated',
    'order_date', 'ship_date', 'start_date', 'end_date'
})
