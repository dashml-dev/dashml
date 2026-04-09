"""
Matched prompt templates for the DashML vs Plotly PandasPlotBench benchmark.

Two arms with equivalent information density:
- Arm A: NL → .dashml YAML → Plotly (via PlotlyTransformer)
- Arm B: NL → raw Plotly Python code (direct)
"""
from __future__ import annotations

import io
import json
from typing import Any, Dict, List


# ── Arm A: DashML system prompt (full DSL spec, CSV-focused) ─────────────────

DASHML_SYSTEM_PROMPT = """\
You are a visualization specification generator. Given a plot description, \
style requirements, and CSV data schema, output a valid .dashml YAML specification.

## DashML Format

```yaml
version: "1.0"
title: "my_chart"
data:
  type: csv
  path: data.csv
charts:
  - id: chart1
    type: bar
    title: "Sales by Region"
    x: region
    y: sales
    agg: sum
```

## Chart Types (12 types)

| Type | Visual | Requires agg? | Notes |
|------|--------|---------------|-------|
| bar | vertical bars | yes | categorical x, quantitative y |
| line | line chart | yes | continuous/temporal x, quantitative y |
| pie | pie/donut | yes | x = category, y = value |
| scatter | point cloud | no | quantitative x and y |
| heatmap | colored grid | yes | x and y categorical, requires group |
| box | box plot | no | categorical x, quantitative y distribution |
| histogram | distribution | no | single numeric field on x, no y needed |
| area | filled area | yes | like line but filled |
| stacked_bar | stacked bars | yes | requires group field |
| grouped_bar | side-by-side bars | yes | requires group field |
| bubble | sized scatter | no | like scatter with size field |
| geo | map | yes | x = country/region name, y = value |

## Aggregations
- `sum` - total of y values per x group
- `mean` - average of y values per x group
- `count` - count of rows per x group (y is optional)

## Optional Fields
- `group`: second categorical field for color encoding (required for heatmap, stacked_bar, grouped_bar)
- `size`: numeric field for bubble size (bubble chart)
- `sort`: sort by "x" or "y" after aggregation
- `sort_order`: "asc" or "desc"
- `limit`: integer, show only top/bottom N after sort
- `bin`: true - bin the x-axis into ranges
- `x_type`: "temporal" if x is a date/time column
- `title`: chart title string

## Filter Format
```yaml
filters:
  - field: column_name
    op: eq
    value: 100
  - field: status
    op: in
    value: ["A", "B"]
  - field: score
    op: range
    value: [10, 50]
```
Filter operators: eq, ne, gt, lt, gte, lte, in, contains, range

## Rules
1. Every chart needs: id, type, x (except histogram uses x only), y (for most types)
2. Charts needing aggregation (bar, line, pie, heatmap, area, stacked_bar, grouped_bar) must have agg
3. Raw data charts (scatter, box, histogram, bubble) must NOT have agg
4. For heatmap: x = one category, group = second category, y = value field
5. For pie: x = category, y = value
6. For histogram: x = numeric field, no y needed
7. Always use data: {type: csv, path: data.csv}
8. Filters go INSIDE the chart object, not at top level

## Output
Output ONLY a single .dashml YAML spec. No explanation, no markdown fences, no comments.
"""

# ── Arm B: Plotly system prompt (matched information density) ────────────────

PLOTLY_SYSTEM_PROMPT = """\
You are a visualization code generator. Given a plot description, \
style requirements, and CSV data schema, write Python code using pandas \
and plotly to create the visualization.

## Requirements
- Data is pre-loaded as `df = pd.read_csv("data.csv")`
- Use plotly.express (px) or plotly.graph_objects (go) as appropriate
- Save the final figure: `fig.write_image("output.png")`
- Include ALL necessary imports at the top
- Handle data types and aggregation in code

## Chart Type Selection

| Chart | plotly.express function | Notes |
|-------|----------------------|-------|
| bar | px.bar() | categorical x, numeric y |
| line | px.line() | continuous x, numeric y |
| pie | px.pie() | names = category, values = numeric |
| scatter | px.scatter() | numeric x and y |
| heatmap | px.density_heatmap() or go.Heatmap | 2D grid |
| box | px.box() | categorical x, numeric y |
| histogram | px.histogram() | single numeric column |
| area | px.area() | like line but filled |
| bubble | px.scatter(size=col) | scatter with size encoding |

## Aggregation
- When the task requires aggregated data, use `df.groupby().agg()` before plotting
- Common aggregations: sum, mean, count, min, max

## Styling
- Set figure title with `fig.update_layout(title="...")`
- Set axis labels with `fig.update_xaxes(title_text="...")` and `fig.update_yaxes(title_text="...")`
- For colors, use plotly's built-in color sequences or specify hex colors

## Output
Output ONLY Python code. No explanation, no markdown fences, no comments outside the code.
The code must be complete and runnable.
"""


def build_user_prompt(
    task_description: str,
    style_description: str,
    csv_data: str,
    max_sample_rows: int = 3,
    max_csv_chars: int = 1000,
) -> str:
    """Build user prompt from PandasPlotBench entry data.

    Parses CSV to extract schema info instead of sending raw data.
    """
    import pandas as pd

    # Parse CSV to get schema info
    try:
        df = pd.read_csv(io.StringIO(csv_data))
        columns = list(df.columns)
        dtypes = {col: str(df[col].dtype) for col in columns}
        row_count = len(df)
        sample_rows = df.head(max_sample_rows).to_dict("records")
        sample_str = json.dumps(sample_rows, default=str)
        if len(sample_str) > max_csv_chars:
            sample_str = sample_str[:max_csv_chars] + "..."
    except Exception:
        # Fallback: send raw CSV header
        lines_raw = csv_data.strip().split("\n")
        columns = lines_raw[0].split(",") if lines_raw else []
        dtypes = {}
        row_count = len(lines_raw) - 1
        sample_str = "\n".join(lines_raw[:4])

    parts = [
        f"Plot Description: {task_description}",
        f"\nStyle Requirements: {style_description}",
        f"\nData file: data.csv",
        f"Columns: {columns}",
        f"Column types: {dtypes}",
        f"Row count: {row_count}",
        f"Sample rows: {sample_str}",
    ]
    return "\n".join(parts)


def get_system_prompt(arm: str) -> str:
    """Get the system prompt for the given arm."""
    if arm == "dashml":
        return DASHML_SYSTEM_PROMPT
    elif arm == "plotly":
        return PLOTLY_SYSTEM_PROMPT
    else:
        raise ValueError(f"Unknown arm: {arm}. Use 'dashml' or 'plotly'.")
