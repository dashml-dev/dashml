# DashML - Declarative Dashboard Markup Language

DashML is a declarative language for defining analytics dashboards that can be compiled to multiple visualization platforms (Streamlit, Plotly, Observable Plot).

## Philosophy

- **Write once, deploy anywhere**: Single `.dashml` spec generates code for multiple platforms
- **No runtime dependencies**: Generated code is standalone and self-contained
- **Build-time compilation**: DashML is a compiler, not a runtime framework
- **Hexagonal architecture**: Clean separation between core engine and platform transformers

## Quick Start

```bash
# Generate Streamlit app
python -m dashml_new.cli dashboard.dashml --backend streamlit --output app.py
streamlit run app.py

# Generate Plotly HTML
python -m dashml_new.cli dashboard.dashml --backend plotly --output dashboard.html

# Generate Observable Plot HTML
python -m dashml_new.cli dashboard.dashml --backend observable --output dashboard.html
```

## DashML Specification

### Basic Structure

```yaml
version: 0.1
title: "My Dashboard"
style: "styles/dracula.dmls"

data:
  type: csv
  path: "data/sales.csv"

charts:
  - id: "sales_by_country"
    type: "bar"
    title: "Sales by Country"
    x: "country"
    y: "sales"
    agg: "sum"
```

### Data Sources

DashML supports multiple data source types:

#### CSV (Default)
```yaml
data:
  type: csv
  path: "data/sales.csv"
```

#### SQL (PostgreSQL, MySQL, SQLite)
```yaml
data:
  type: sql
  path: "public.orders"  # schema.table format
```

Run with database credentials:
```bash
python -m dashml_new.cli build dashboard.dashml --target plotly --output ./output \
  --db-type postgresql --db-host localhost --db-port 5432 \
  --db-name mydb --db-user user --db-password pass
```

#### BigQuery
```yaml
data:
  type: bigquery
  path: "dataset.table_name"  # dataset.table format
```

Run with BigQuery project:
```bash
python -m dashml_new.cli build dashboard.dashml --target plotly --output ./output \
  --bq-project my-gcp-project

# Or with service account credentials
python -m dashml_new.cli build dashboard.dashml --target plotly --output ./output \
  --bq-project my-gcp-project --bq-credentials /path/to/service-account.json
```

**Note**: For SQL and BigQuery, the generated output includes a Flask backend (`app.py`) that connects to the database and serves data via `/api/data`.

### Multi-Page Dashboards

```yaml
version: 0.1
title: "Multi-Page Dashboard"
style: "styles/nord.dmls"

data:
  type: csv
  path: "data/sales.csv"

pages:
  - id: "overview"
    title: "📊 Overview"
    description: "High-level metrics"
    charts:
      - id: "total_sales"
        type: "bar"
        x: "country"
        y: "sales"
        agg: "sum"

  - id: "details"
    title: "📈 Details"
    description: "Detailed breakdown"
    charts:
      - id: "sales_trend"
        type: "line"
        x: "date"
        y: "sales"
        agg: "sum"
```

## Supported Chart Types

DashML supports **8 chart types** fully implemented across all backends:

| Chart Type | Description | Example Use Case | Required Fields |
|------------|-------------|------------------|-----------------|
| `bar` | Vertical bar chart | Compare categories | x, y, agg |
| `line` | Line chart with points | Show trends over time | x, y, agg |
| `scatter` | Scatter plot | Show correlations | x, y |
| `pie` | Pie chart | Show proportions | x, y, agg |
| `area` | Filled area chart | Show cumulative trends | x, y, agg |
| `histogram` | Distribution histogram | Show data distribution | x |
| `stacked_bar` | Stacked bar chart | Compare subcategories | x, y, group, agg |
| `grouped_bar` | Grouped/clustered bars | Compare side-by-side | x, y, group, agg |

### Chart Data Requirements

**Charts need aggregation:**
- `bar`, `line`, `area`, `pie`, `stacked_bar`, `grouped_bar`
- Must specify `agg` field: `sum`, `mean`, or `count`

**Charts use raw data:**
- `scatter`, `histogram`
- Data is plotted without aggregation

**Charts need grouping:**
- `stacked_bar`, `grouped_bar`
- Must specify `group` field to define stacking/grouping dimension

### Chart Field Reference

```yaml
- id: "chart_identifier"        # Required: Unique ID
  type: "bar"                    # Required: Chart type (see table above)
  title: "Chart Title"           # Optional: Display title
  x: "column_name"               # Required: X-axis field
  y: "column_name"               # Required: Y-axis field (except histogram)
  agg: "sum"                     # Optional: sum|mean|count (required for aggregating charts)
  group: "category_column"       # Optional: Grouping field (required for stacked/grouped bars)
  x_type: "date"                 # Optional: Explicit type for x-axis (date|number|string)
```

### Axis Type Detection & Sorting

DashML automatically detects column types from database schema and sorts data appropriately:

#### Auto-Detection (SQL/BigQuery)
For SQL and BigQuery data sources, DashML queries `INFORMATION_SCHEMA.COLUMNS` to detect column types:

| Database Type | Mapped To | Sorting |
|---------------|-----------|---------|
| DATE, DATETIME, TIMESTAMP, TIME | `date` | Chronological |
| INT, FLOAT, NUMERIC, DECIMAL, etc. | `number` | Numerical |
| VARCHAR, TEXT, CHAR, etc. | `string` | No sort |

#### Auto-Detection (CSV)
For CSV files, pandas dtype inference is used, with fallback to string parsing for date detection.

#### Explicit `x_type` Override
You can explicitly specify the axis type to override auto-detection:

```yaml
charts:
  - id: "sales_trend"
    type: "line"
    x: "order_date"
    x_type: "date"    # Force chronological sorting
    y: "amount"
    agg: "sum"
```

**Priority Order**: Explicit `x_type` > Schema-detected > No sorting

## Theme System

DashML uses `.dmls` (DashML Style) files for theming. Six built-in themes are included:

### Available Themes

- `dracula.dmls` - Dark purple theme
- `nord.dmls` - Cool blue-gray theme
- `gruvbox.dmls` - Warm retro theme
- `monokai.dmls` - Classic dark theme
- `onedark.dmls` - Atom-inspired dark theme
- `solarized_light.dmls` - Light beige theme

### Theme Structure

```yaml
version: 0.1
colors:
  background: "#282a36"    # Dashboard background
  card: "#313343"          # Chart card background
  primary: "#bd93f9"       # Primary chart color
  text: "#f8f8f2"          # Text color
  buttons: "#44475a"       # Button/UI element color
  secondary:               # Multi-series chart colors
    - "#ff79c6"
    - "#8be9fd"
    - "#50fa7b"
    - "#ffb86c"
    - "#ff5555"
```

## Architecture

```
dashml_new/
├── core/
│   ├── engine.py          # Orchestrates parsing, validation, transformation
│   ├── parser.py          # YAML → Python dict parser
│   ├── validator.py       # Semantic validation of specs
│   ├── types.py           # TypedDict definitions for type hints
│   └── __init__.py
│
├── transformers/
│   ├── base.py            # Abstract Transformer interface
│   ├── streamlit.py       # Generates Streamlit Python code
│   ├── plotly.py          # Generates Plotly HTML/JavaScript
│   ├── observable.py      # Generates Observable Plot HTML
│   └── __init__.py
│
├── cli.py                 # Command-line interface
└── __init__.py
```

### Key Design Principles

1. **Hexagonal Architecture**: Core engine isolated from transformers via clean interfaces
2. **No Intermediate Representation**: Spec is a plain Python dict from parsed YAML
3. **No Data Materialization**: Engine validates structure only, never touches actual data
4. **Code Generation**: Transformers generate standalone code that loads its own data
5. **Zero Overhead Types**: TypedDict provides type hints without runtime cost
6. **Schema Auto-Detection**: For SQL/BigQuery, column types are detected from `INFORMATION_SCHEMA`

### Output Structure

**CSV Data Source**: Single file output (HTML or Python)

**SQL/BigQuery Data Source**: Multi-file output directory:
```
output_dir/
├── app.py       # Flask backend (connects to database, serves /api/data and /api/schema)
└── index.html   # Frontend (fetches from Flask API, renders charts)
```

### How It Works

#### 1. Build Time: DashML Compiles Spec

```python
# User runs CLI
python -m dashml_new.cli dashboard.dashml --backend streamlit --output app.py

# Engine loads and validates spec
spec = yaml.safe_load(open("dashboard.dashml"))
validator.validate(spec)  # Only validates structure, never loads data!

# Transformer generates standalone code
code = StreamlitTransformer().build(spec)
```

#### 2. Run Time: Generated Code Executes

```python
# app.py (generated code)
import pandas as pd
import streamlit as st

# Generated code loads its own data
df = pd.read_csv("data/sales.csv")

# Generated code renders charts
st.title("My Dashboard")
chart_data = df.groupby("country")["sales"].sum().reset_index()
st.bar_chart(chart_data, x="country", y="sales")
```

**Key Point**: DashML never materializes data - it only generates code that will load data at runtime.

## Design Guidelines

### Naming Conventions

When naming components and concepts, DashML follows this hierarchy:

1. **Primary: Vega/Vega-Lite Nomenclature**
   - Mark types: `bar`, `line`, `point`, `area`
   - Encodings: `x`, `y`, `color`, `size`
   - Aggregations: `sum`, `mean`, `count`

2. **Fallback: Material Design 3**
   - UI containers: `card` (for chart containers)
   - Components: Use Material Design naming when Vega has no equivalent

**Rationale**: Vega is the industry standard for declarative visualization grammars. Material Design provides consistent UI terminology.

## Backend Transformers

### Streamlit Transformer

**Output**: Python code using Streamlit + Altair
**Best for**: Internal data apps, rapid prototyping
**Features**:
- Interactive widgets
- Multi-page navigation
- Automatic caching
- Live code execution

**Limitations**:
- Card backgrounds don't match other backends (Streamlit platform limitation)

### Plotly Transformer

**Output**: Standalone HTML with embedded JavaScript
**Best for**: Shareable dashboards, presentations, embedding
**Features**:
- Full theme support including card colors
- Interactive hover tooltips
- Responsive layouts
- No server required

### Observable Plot Transformer

**Output**: Standalone HTML with Observable Plot + D3
**Best for**: Modern web-based visualizations, notebooks
**Features**:
- Elegant minimalist design
- Lightweight and fast
- Full theme support
- Custom D3 pie charts (Observable Plot doesn't have native pie support)

### Superset Transformer

**Output**: None - creates dashboard directly in Superset!
**Best for**: Enterprise BI dashboards, SQL-based analytics, team collaboration
**Features**:
- **Direct dashboard creation** - no code generation, no intermediate steps
- Automatic CSV upload to Superset
- Dashboard deduplication (updates existing dashboards)
- Automatic cleanup of old charts
- Full support for all 8 DashML chart types using modern ECharts visualizations

**Requirements**:
- Running Superset instance (e.g., http://localhost:8088)
- Superset credentials (username/password)
- CSV file accessible at the path specified in the DashML spec
- `requests` library: `pip install requests`

**Usage**:
```bash
# Single command - creates dashboard immediately!
python -m dashml_new.cli build dashboard.dashml \
  --target superset \
  --superset-user admin \
  --superset-password admin
```

**What happens:**
1. ✓ Authenticates with Superset
2. ✓ Uploads CSV automatically (or finds existing dataset)
3. ✓ Creates all charts with correct ECharts viz types
4. ✓ Creates/updates dashboard with proper layout
5. ✓ Associates charts with dashboard
6. 🎉 Prints dashboard URL - open in browser!

**Chart Type Mappings**:
- `bar` → `echarts_timeseries` (bar)
- `line` → `echarts_timeseries` (line)
- `area` → `echarts_area`
- `histogram` → `histogram_v2`
- `scatter` → `scatter`
- `pie` → `pie`
- `stacked_bar` → `echarts_timeseries` (stacked)
- `grouped_bar` → `echarts_timeseries` (grouped)

**Key Benefits**:
- ⚡ Immediate execution - no intermediate Python scripts
- ✅ Automatic CSV upload
- ✅ Dashboard deduplication (updates instead of creating duplicates)
- ✅ Perfect for CI/CD pipelines
- ✅ Idempotent - run multiple times safely
- ✅ Modern ECharts visualizations for better performance

## Command-Line Interface

```bash
# Basic usage
python -m dashml_new.cli <input.dashml> --backend <backend> --output <output_file>

# Examples
python -m dashml_new.cli build dashboard.dashml --target streamlit --output app.py
python -m dashml_new.cli build dashboard.dashml --target plotly --output index.html
python -m dashml_new.cli build dashboard.dashml --target observable --output dashboard.html

# Superset - no output file needed, creates dashboard directly!
python -m dashml_new.cli build dashboard.dashml --target superset \
  --superset-user admin --superset-password admin

# With run flag (Streamlit only)
python -m dashml_new.cli build dashboard.dashml --target streamlit --output app.py --run
```

### Arguments

- `input_file`: Path to `.dashml` specification file
- `--target`, `-t`: Target platform (`streamlit`, `plotly`, `observable`, or `superset`)
- `--output`, `-o`: Output file/directory path (not needed for `superset`)
- `--run`, `-r`: Automatically run the generated dashboard after build

**SQL Database Options:**
- `--db-type`: Database type (`postgresql`, `mysql`, `sqlite`)
- `--db-host`: Database host (default: `localhost`)
- `--db-port`: Database port (default: `5432`)
- `--db-name`: Database name
- `--db-user`: Database username
- `--db-password`: Database password

**BigQuery Options:**
- `--bq-project`: Google Cloud project ID (required for BigQuery)
- `--bq-credentials`: Path to service account JSON file (optional, uses default credentials if not provided)

**Superset Options:**
- `--superset-url`: Superset instance URL (default: `http://localhost:8088`)
- `--superset-user`: Superset username (required for `superset` target)
- `--superset-password`: Superset password (required for `superset` target)

## Creating Custom Transformers

```python
from dashml_new.transformers.base import Transformer, TransformerError
from typing import Dict, Any

class MyCustomTransformer(Transformer):
    @property
    def name(self) -> str:
        return "my-platform"

    @property
    def description(self) -> str:
        return "Generates code for My Custom Platform"

    def build(self, spec: Dict[str, Any]) -> str:
        """Generate code from validated spec"""
        title = spec.get("title", "Dashboard")
        charts = spec.get("charts", [])

        # Generate platform-specific code
        code_parts = []
        code_parts.append(f"# {title}")

        for chart in charts:
            chart_code = self._generate_chart(chart)
            code_parts.append(chart_code)

        return "\n\n".join(code_parts)

    def _generate_chart(self, chart: Dict[str, Any]) -> str:
        # Your chart generation logic
        pass

    def get_run_command(self, output_path: str) -> str:
        return f"my-platform run {output_path}"
```

### Transformer Plugin System

Transformers use a simple name-based lookup (no complex registry):

```python
from dashml_new.core import DashMLEngine

engine = DashMLEngine()

# Load spec
spec = engine.load("dashboard.dashml")

# Get transformer by name
if backend == "streamlit":
    from dashml_new.transformers.streamlit import StreamlitTransformer
    transformer = StreamlitTransformer()
elif backend == "plotly":
    from dashml_new.transformers.plotly import PlotlyTransformer
    transformer = PlotlyTransformer()
# etc.

# Build
code = transformer.build(spec)
```

## Warning System

Transformers can emit warnings for unsupported features:

```python
class MyTransformer(Transformer):
    def build(self, spec: Dict[str, Any]) -> str:
        for chart in spec.get("charts", []):
            if chart["type"] == "unsupported_type":
                self.warn(f"Chart type '{chart['type']}' not supported")

        # ... continue building
        return code

# CLI displays warnings after build
transformer = MyTransformer()
code = transformer.build(spec)

warnings = transformer.get_warnings()
if warnings:
    print("⚠ Transformer warnings:")
    for warning in warnings:
        print(f"  - {warning}")
```

## Validation

DashML validates specs at build time:

```python
from dashml_new.core import DashMLValidator, ValidationError

validator = DashMLValidator()

try:
    validator.validate(spec)
except ValidationError as e:
    print(f"Invalid spec: {e}")
```

### Validation Rules

**Required Top-Level Fields:**
- `version`: String or number (e.g., `0.1` or `"1.0"`)
- `data`: Data source specification

**Must Have Either:**
- `charts`: Array of chart specs (legacy single-page format)
- `pages`: Array of page specs (multi-page format)

**Chart Validation:**
- Required fields: `id`, `type`, `x`, `y`
- Chart type must be one of 8 supported types
- Aggregation (`agg`) must be: `sum`, `mean`, or `count`
- Stacked/grouped bars must have `group` field

**Data Source Validation:**
- Supported data types: `csv`, `sql`, `bigquery`
- Must have `type` and `path` fields
- SQL path format: `schema.table`
- BigQuery path format: `dataset.table`

**Axis Type Validation:**
- Optional `x_type` field: `date`, `number`, or `string`

## Examples

### Simple Bar Chart

```yaml
version: 0.1
title: "Sales Dashboard"
style: "styles/dracula.dmls"

data:
  type: csv
  path: "data/sales.csv"

charts:
  - id: "sales_by_country"
    type: "bar"
    title: "Total Sales by Country"
    x: "country"
    y: "sales"
    agg: "sum"
```

### Stacked Bar Chart

```yaml
version: 0.1
title: "Product Sales"
style: "styles/nord.dmls"

data:
  type: csv
  path: "data/sales.csv"

charts:
  - id: "stacked_sales"
    type: "stacked_bar"
    title: "Sales by Country and Product"
    x: "country"
    y: "sales"
    group: "product"
    agg: "sum"
```

### Multi-Chart Dashboard

```yaml
version: 0.1
title: "Analytics Dashboard"
style: "styles/gruvbox.dmls"

data:
  type: csv
  path: "data/sales.csv"

charts:
  - id: "total_sales"
    type: "bar"
    title: "Total Sales"
    x: "country"
    y: "sales"
    agg: "sum"

  - id: "sales_trend"
    type: "line"
    title: "Sales Trend"
    x: "date"
    y: "sales"
    agg: "sum"

  - id: "sales_distribution"
    type: "histogram"
    title: "Sales Distribution"
    x: "sales"

  - id: "sales_breakdown"
    type: "pie"
    title: "Sales by Country"
    x: "country"
    y: "sales"
    agg: "sum"
```

### BigQuery Dashboard

```yaml
version: 0.1
title: "BigQuery Analytics"
style: "styles/nord.dmls"

data:
  type: bigquery
  path: "analytics.orders"

charts:
  - id: "sales_over_time"
    type: "line"
    title: "Sales Over Time"
    x: "order_date"
    y: "total_amount"
    agg: "sum"
    # x_type auto-detected from BigQuery INFORMATION_SCHEMA

  - id: "sales_by_region"
    type: "bar"
    title: "Sales by Region"
    x: "region"
    y: "total_amount"
    agg: "sum"
```

Build and run:
```bash
python -m dashml_new.cli build bigquery.dashml --target plotly \
  --output ./bq_dashboard --bq-project my-project --run
```

### SQL Database Dashboard

```yaml
version: 0.1
title: "PostgreSQL Analytics"
style: "styles/dracula.dmls"

data:
  type: sql
  path: "public.orders"

charts:
  - id: "orders_trend"
    type: "line"
    title: "Order Trend"
    x: "created_at"
    x_type: "date"  # Explicit type override
    y: "quantity"
    agg: "sum"
```

Build and run:
```bash
python -m dashml_new.cli build sql.dashml --target plotly --output ./sql_dashboard \
  --db-type postgresql --db-host localhost --db-port 5432 \
  --db-name mydb --db-user admin --db-password secret --run
```

## Roadmap

### Completed ✅
- ✅ All 8 Priority 1 chart types
- ✅ Multi-page dashboards
- ✅ Theme system with 6 built-in themes
- ✅ Four backend transformers (Streamlit, Plotly, Observable, Superset)
- ✅ Stacked and grouped bar charts
- ✅ Warning system for unsupported features
- ✅ SQL data sources (PostgreSQL, MySQL, SQLite)
- ✅ BigQuery data source
- ✅ Schema auto-detection from INFORMATION_SCHEMA
- ✅ Explicit `x_type` for axis type control

### Planned 🚧
- Box plots (Streamlit + Plotly only)
- Geographic visualizations (choropleth maps)
- Additional data sources (JSON, Parquet)
- Plotly-exclusive charts (treemap, sunburst, 3D)

## Contributing

When adding new features:

1. **Update types**: Add TypedDict definitions to `core/types.py`
2. **Update validator**: Add validation rules to `core/validator.py`
3. **Update transformers**: Implement in all three transformers (Streamlit, Plotly, Observable)
4. **Add tests**: Create test dashboard in `dashml_example.dashml`
5. **Document**: Update this README

## License

MIT
