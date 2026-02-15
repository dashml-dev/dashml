# DashML User Guide

## Specification Format

DashML specs are YAML files with the `.dashml` extension. A spec defines a data source, charts, and optional theming.

### Minimal Example

```yaml
version: 0.1
title: "My Dashboard"

data:
  type: csv
  path: "data/sales.csv"

charts:
  - id: "sales_chart"
    type: "bar"
    x: "country"
    y: "revenue"
    agg: "sum"
```

### Top-Level Fields

| Field | Required | Description |
|-------|----------|-------------|
| `version` | Yes | Spec version (string or number) |
| `title` | No | Dashboard title |
| `style` | No | Path to a `.dmls` theme file |
| `data` | Yes | Data source configuration |
| `charts` | Yes* | Array of chart specs (single-page mode) |
| `pages` | Yes* | Array of page specs (multi-page mode) |

*Must have either `charts` or `pages`, not both.

---

## Data Sources

### CSV

```yaml
data:
  type: csv
  path: "data/sales.csv"
```

Generates a single output file. The generated code loads the CSV at runtime.

### SQL (PostgreSQL, MySQL, SQLite)

```yaml
data:
  type: sql
  path: "public.orders"  # schema.table format
```

Build with database credentials:

```bash
python -m dashml_new.cli build dashboard.dashml --target plotly --output ./output \
  --db-type postgresql --db-host localhost --db-port 5432 \
  --db-name mydb --db-user user --db-password pass
```

Generates a multi-file output: a Flask backend (`app.py`) that queries the database and serves `/api/data`, plus a frontend (`index.html`).

### BigQuery

```yaml
data:
  type: bigquery
  path: "dataset.table_name"  # dataset.table format
```

Build with project credentials:

```bash
python -m dashml_new.cli build dashboard.dashml --target plotly --output ./output \
  --bq-project my-gcp-project --bq-credentials /path/to/service-account.json
```

Same multi-file output as SQL. Row limit: 10,000.

### Schema Auto-Detection

For SQL and BigQuery, column types are auto-detected from `INFORMATION_SCHEMA.COLUMNS` and mapped to `date`, `number`, or `string`. For CSV, pandas dtype inference is used with fallback date-string detection. You can override with explicit `x_type` / `y_type` on individual charts.

---

## Chart Types

DashML supports 12 chart types across all 4 backends.

### Charts That Use Aggregation

These charts group data by the `x` field and aggregate the `y` field. The `agg` field is required.

| Type | Description | Required Fields |
|------|-------------|-----------------|
| `bar` | Vertical bar chart | `x`, `y`, `agg` |
| `line` | Line chart with markers | `x`, `y`, `agg` |
| `scatter` | Scatter plot | `x`, `y`, `agg` |
| `pie` | Pie chart | `x`, `y`, `agg` |
| `area` | Filled area chart | `x`, `y`, `agg` |
| `bubble` | Scatter with size encoding | `x`, `y`, `agg`, `size` |
| `heatmap` | 2D grid with color intensity | `x`, `y`, `agg`, `group` |
| `geo` | Choropleth world map | `x`, `y`, `agg` |
| `stacked_bar` | Stacked bar chart | `x`, `y`, `agg`, `group` |
| `grouped_bar` | Clustered bar chart | `x`, `y`, `agg`, `group` |

### Charts That Use Raw Data

These charts operate on raw (unaggregated) data. They compute their own statistics.

| Type | Description | Required Fields |
|------|-------------|-----------------|
| `histogram` | Distribution histogram | `x`, `y` |
| `box` | Box plot (min, Q1, median, Q3, max) | `x`, `y` |

### Chart Field Reference

```yaml
- id: "my_chart"              # Required. Unique identifier (alphanumeric, hyphens, underscores)
  type: "bar"                  # Required. One of the 12 types above
  title: "Chart Title"         # Optional. Display title
  x: "column_name"             # Required. X-axis column
  y: "column_name"             # Required. Y-axis column
  agg: "sum"                   # Aggregation function: sum, mean, count
  group: "category_column"     # Grouping column (required for stacked_bar, grouped_bar, heatmap)
  size: "numeric_column"       # Size encoding column (required for bubble)
  x_type: "date"               # Explicit axis type override: date, number, string
  y_type: "number"             # Explicit y-axis type override
  bins: 20                     # Number of bins (histogram only, default: 20)
  sort: "y"                    # Sort by: "x" or "y"
  sort_order: "desc"           # Sort direction: "asc" (default) or "desc"
  limit: 10                    # Max rows after aggregation
  filters:                     # Array of filter conditions
    - field: "date"
      op: "gte"
      value: "2025-01-01"
```

### Aggregation Functions

| Function | Description |
|----------|-------------|
| `sum` | Sum of values |
| `mean` | Average of values |
| `count` | Count of rows |

### Filter Operators

Filters are applied before aggregation.

| Operator | Description | Example Value |
|----------|-------------|---------------|
| `eq` | Equal | `"Poland"` |
| `ne` | Not equal | `"Germany"` |
| `gt` | Greater than | `100` |
| `lt` | Less than | `50` |
| `gte` | Greater than or equal | `"2025-01-01"` |
| `lte` | Less than or equal | `"2025-12-31"` |
| `in` | In list | `["Poland", "Germany"]` |
| `contains` | Substring match | `"land"` |

### Sorting

If no explicit `sort` is specified, data is sorted automatically based on the detected type of the x-axis: dates sort chronologically, numbers sort numerically, strings sort alphabetically. Use `sort` and `sort_order` to override.

### Chart Type Details

**bubble** - Uses a `size` field to encode a third dimension as circle radius. The validator requires the `size` field to be present.

**heatmap** - Uses `group` as the y-axis of the grid and `y` as the value for color intensity. Both `x` and `group` should be categorical.

**geo** - Renders a choropleth world map. The `x` field should contain country names. Includes built-in normalization for common country name variations (e.g. "USA" to "United States of America").

**box** - Shows distribution statistics. The `x` field is used as a categorical grouping variable, `y` is the continuous variable whose distribution is shown.

**histogram** - Bins the `x` field and counts occurrences. The `bins` parameter controls the number of bins (default: 20).

---

## Multi-Page Dashboards

Use `pages` instead of `charts` to organize charts into tabbed pages:

```yaml
version: 0.1
title: "Analytics Dashboard"
style: "styles/nord.dmls"

data:
  type: csv
  path: "data/sales.csv"

pages:
  - id: "overview"
    title: "Overview"
    description: "High-level metrics"
    charts:
      - id: "total_sales"
        type: "bar"
        x: "country"
        y: "sales"
        agg: "sum"

  - id: "trends"
    title: "Trends"
    description: "Sales over time"
    charts:
      - id: "sales_trend"
        type: "line"
        x: "date"
        y: "sales"
        agg: "sum"
```

Each page has `id`, `title`, optional `description`, and a `charts` array. Streamlit renders pages as tabs. Plotly and Observable render them as tab navigation. Superset flattens all pages into a single dashboard with chart IDs prefixed by page ID.

---

## Themes

DashML uses `.dmls` (DashML Style) files for theming. Reference a theme in your spec:

```yaml
style: "styles/dracula.dmls"
```

### Built-In Themes

| Theme | File | Description |
|-------|------|-------------|
| Dracula | `styles/dracula.dmls` | Dark purple |
| Nord | `styles/nord.dmls` | Cool blue-gray |
| Gruvbox | `styles/gruvbox.dmls` | Warm retro |
| Monokai | `styles/monokai.dmls` | Classic dark |
| One Dark | `styles/onedark.dmls` | Atom-inspired dark |
| Solarized Light | `styles/solarized_light.dmls` | Light beige |

### Theme File Format

```yaml
version: 0.1
colors:
  background: "#282a36"    # Dashboard background
  card: "#313343"          # Chart card background
  primary: "#bd93f9"       # Primary chart color (single-series)
  text: "#f8f8f2"          # Text color
  secondary:               # Colors for multi-series charts (pie, stacked_bar, grouped_bar)
    - "#50fa7b"
    - "#ffb86c"
    - "#ff5555"
    - "#8be9fd"
    - "#f1fa8c"
```

### Color Support by Backend

| Color | Streamlit | Plotly | Observable | Superset |
|-------|-----------|--------|------------|----------|
| `background` | Yes | Yes | Yes | N/A |
| `card` | No (platform limitation) | Yes | Yes | N/A |
| `primary` | Yes | Yes | Yes | Yes |
| `text` | Yes | Yes | Yes | N/A |
| `secondary` | Yes | Yes | Yes | Yes |

---

## Command-Line Interface

### Commands

```bash
# Build a dashboard
python -m dashml_new.cli build <input.dashml> --target <target> [--output <path>]

# List available transformers
python -m dashml_new.cli list

# Watch for changes and rebuild automatically
python -m dashml_new.cli watch <input.dashml> --target <target> --output <path>
```

### Build Options

| Flag | Description |
|------|-------------|
| `--target`, `-t` | Target platform: `streamlit`, `plotly`, `observable`, `superset` |
| `--output`, `-o` | Output file or directory (not needed for `superset`) |
| `--run`, `-r` | Run the dashboard after building |

### SQL Options

| Flag | Description |
|------|-------------|
| `--db-type` | `postgresql`, `mysql`, or `sqlite` |
| `--db-host` | Database host (default: `localhost`) |
| `--db-port` | Database port (default: `5432`) |
| `--db-name` | Database name |
| `--db-user` | Database username |
| `--db-password` | Database password |

### BigQuery Options

| Flag | Description |
|------|-------------|
| `--bq-project` | Google Cloud project ID |
| `--bq-credentials` | Path to service account JSON (optional; uses default credentials if omitted) |

### Superset Options

| Flag | Description |
|------|-------------|
| `--superset-url` | Superset instance URL (default: `http://localhost:8088`) |
| `--superset-user` | Superset username |
| `--superset-password` | Superset password |

### Watch Mode

```bash
python -m dashml_new.cli watch dashboard.dashml --target streamlit --output app.py --run
```

Polls the `.dashml` file for changes and rebuilds automatically. With `--run`, restarts the generated app after each rebuild.

---

## Backend Details

### Streamlit

Generates Python code using Streamlit and Altair. Best for interactive data apps.

```bash
python -m dashml_new.cli build dashboard.dashml --target streamlit --output app.py
streamlit run app.py
```

Output: single `.py` file (CSV) or multi-file directory (SQL/BigQuery).

### Plotly

Generates standalone HTML with Plotly.js. Best for shareable dashboards and embedding.

```bash
python -m dashml_new.cli build dashboard.dashml --target plotly --output dashboard.html
```

Output: single `.html` file (CSV) or multi-file directory with Flask backend (SQL/BigQuery).

### Observable Plot

Generates HTML with Observable Plot and D3.js. Best for lightweight, modern web visualizations.

```bash
python -m dashml_new.cli build dashboard.dashml --target observable --output dashboard.html
```

Output: single `.html` file (CSV) or multi-file directory with Flask backend (SQL/BigQuery). Pie charts use D3 directly since Observable Plot has no native pie support.

### Superset

Creates dashboards directly in Apache Superset via REST API. No files are generated.

```bash
python -m dashml_new.cli build dashboard.dashml --target superset \
  --superset-user admin --superset-password admin
```

The transformer authenticates, uploads CSV (or connects to existing SQL/BigQuery datasets), creates all charts, and assembles the dashboard. Running the command again updates the existing dashboard instead of creating duplicates.

Superset chart type mappings:

| DashML Type | Superset Viz Type |
|-------------|-------------------|
| `bar` | `echarts_timeseries` (bar) |
| `line` | `echarts_timeseries` (line) |
| `scatter` | `echarts_timeseries_scatter` |
| `pie` | `pie` |
| `area` | `echarts_area` |
| `histogram` | `histogram_v2` |
| `stacked_bar` | `echarts_timeseries` (stacked) |
| `grouped_bar` | `echarts_timeseries` (grouped) |
| `bubble` | `echarts_bubble` |
| `heatmap` | `heatmap` |
| `box` | `box_plot` |
| `geo` | `world_map` |

Requires the `requests` library: `pip install requests`.

---

## Chart Support Matrix

All 12 chart types are implemented in all 4 backends.

| Type | Streamlit (Altair) | Plotly (Plotly.js) | Observable (Plot/D3) | Superset |
|------|--------------------|--------------------|----------------------|----------|
| `bar` | `mark_bar` | `type: 'bar'` | `Plot.barY` | `echarts_timeseries` |
| `line` | `mark_line` | `type: 'scatter'` (lines+markers) | `Plot.line` + `Plot.dot` | `echarts_timeseries` |
| `scatter` | `mark_circle` | `type: 'scatter'` (markers) | `Plot.dot` | `echarts_timeseries_scatter` |
| `pie` | `mark_arc` | `type: 'pie'` | D3 `d3.pie()` | `pie` |
| `area` | `mark_area` | `type: 'scatter'` (fill) | `Plot.areaY` | `echarts_area` |
| `histogram` | `mark_bar` (binned) | `type: 'histogram'` | `Plot.rectY` + `Plot.binX` | `histogram_v2` |
| `stacked_bar` | `mark_bar` (stack) | Multiple `bar` traces (stack) | `Plot.barY` (fill) | `echarts_timeseries` |
| `grouped_bar` | `mark_bar` (xOffset) | Multiple `bar` traces (group) | `Plot.barY` (faceted) | `echarts_timeseries` |
| `bubble` | `mark_circle` (sized) | `type: 'scatter'` (sized markers) | `Plot.dot` (dynamic radius) | `echarts_bubble` |
| `heatmap` | `mark_rect` | `type: 'heatmap'` | `Plot.cell` | `heatmap` |
| `box` | `mark_boxplot` | `type: 'box'` | `Plot.boxY` | `box_plot` |
| `geo` | `mark_geoshape` (topojson) | `type: 'choropleth'` | `Plot.geo` (topojson) | `world_map` |

---

## Output Structure

### CSV Data Source

Single file output: one `.py` (Streamlit) or `.html` (Plotly/Observable).

### SQL / BigQuery Data Source

Multi-file output directory:

```
output_dir/
  app.py       # Flask backend (database queries, /api/data and /api/schema endpoints)
  index.html   # Frontend (fetches from Flask, renders charts)
```

### Superset

No files generated. Dashboard is created directly in the Superset instance.

---

## Examples

### Filtering and Sorting

```yaml
charts:
  - id: "top_countries"
    type: "bar"
    title: "Top 5 Countries by Sales (2025)"
    x: "country"
    y: "sales"
    agg: "sum"
    sort: "y"
    sort_order: "desc"
    limit: 5
    filters:
      - field: "date"
        op: "gte"
        value: "2025-01-01"
      - field: "date"
        op: "lte"
        value: "2025-12-31"
```

### Bubble Chart

```yaml
charts:
  - id: "sales_bubble"
    type: "bubble"
    title: "Sales by Country"
    x: "country"
    y: "revenue"
    size: "num_orders"
    agg: "sum"
```

### Heatmap

```yaml
charts:
  - id: "sales_heatmap"
    type: "heatmap"
    title: "Sales by Country and Product"
    x: "country"
    y: "sales"
    group: "product"
    agg: "sum"
```

### Box Plot

```yaml
charts:
  - id: "price_distribution"
    type: "box"
    title: "Price Distribution by Category"
    x: "category"
    y: "price"
```

### Choropleth Map

```yaml
charts:
  - id: "world_sales"
    type: "geo"
    title: "Sales by Country"
    x: "country"
    y: "revenue"
    agg: "sum"
```

### SQL Dashboard

```yaml
version: 0.1
title: "Order Analytics"
style: "styles/dracula.dmls"

data:
  type: sql
  path: "public.orders"

charts:
  - id: "orders_trend"
    type: "line"
    title: "Orders Over Time"
    x: "created_at"
    x_type: "date"
    y: "quantity"
    agg: "sum"

  - id: "top_products"
    type: "bar"
    title: "Top Products"
    x: "product_name"
    y: "quantity"
    agg: "sum"
    sort: "y"
    sort_order: "desc"
    limit: 10
```

```bash
python -m dashml_new.cli build orders.dashml --target plotly --output ./output \
  --db-type postgresql --db-host localhost --db-port 5432 \
  --db-name mydb --db-user admin --db-password secret --run
```

---

## Creating Custom Transformers

```python
from dashml_new.transformers.base import Transformer

class MyTransformer(Transformer):
    @property
    def name(self) -> str:
        return "my-platform"

    @property
    def description(self) -> str:
        return "Generates code for My Platform"

    def build(self, spec):
        title = spec.get("title", "Dashboard")
        charts = spec.get("charts", [])
        # Generate platform-specific code...
        return generated_code

    def get_run_command(self, output_path):
        return f"my-platform run {output_path}"
```

Register the transformer in `cli.py` and it becomes available as a `--target` option.

Transformers can emit warnings for unsupported features via `self.warn("message")`. Warnings are displayed after the build completes.
