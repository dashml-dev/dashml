"""
DashML Type Definitions - TypedDict for IDE support and type checking

These types define the STRUCTURE of DashML specs, not valid values.
Validation of values (e.g., supported chart types) happens in the validator.
"""
from typing import TypedDict, List, Union


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


class DataSpec(TypedDict):
    """Data source specification"""
    type: str
    path: str


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
    - stacked_bar: Stacked bars (requires grouping - not yet fully supported)
    - grouped_bar: Grouped/clustered bars (requires grouping - not yet fully supported)

    Note: Using total=False allows optional fields like 'title' and 'agg'.
    The validator ensures required fields are present.
    """
    id: str
    type: str  # One of the supported chart types above
    title: str
    x: str
    y: str
    agg: str  # sum, mean, or count


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
