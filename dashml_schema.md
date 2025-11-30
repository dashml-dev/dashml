# DashML Syntax Documentation

**Version:** 0.000000001
**Format:** YAML
**File Extension:** `.dashml`

---

## Overview

DashML is a declarative language for defining data visualization dashboards. A `.dashml` file uses YAML syntax to describe:
- Data sources
- Chart specifications
- Dashboard metadata

The spec is **platform-agnostic** and can be compiled to different targets (Streamlit, Plotly, PowerBI, etc.).

---

## File Structure

### Single-Page Dashboard (Legacy)

```yaml
version: <version>
title: <dashboard-title>

data:
  <data-source-config>

charts:
  - <chart-1>
  - <chart-2>
  - ...
```

### Multi-Page Dashboard (Recommended)

```yaml
version: <version>
title: <dashboard-title>

data:
  <data-source-config>

pages:
  - id: <page-id>
    title: <page-title>              # Can include emojis: "📊 Overview"
    description: <page-description>  # Optional
    charts:
      - <chart-1>
      - <chart-2>
  - id: <page-id-2>
    title: <page-title-2>
    charts:
      - <chart-3>
```

---

## Top-Level Fields

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `version` | string/number | DashML specification version | `0.000000001` |
| `data` | object | Data source configuration | See [Data Source](#data-source) |
| `charts` OR `pages` | array | Either top-level charts (legacy) OR pages with embedded charts (recommended) | See [Charts](#charts) or [Pages](#pages) |

### Optional Fields

| Field | Type | Description | Status |
|-------|------|-------------|--------|
| `title` | string | Dashboard title | ✅ Implemented |
| `filters` | object | Global dashboard filters | 🚧 Planned |
| `theme` | object | Dashboard theme configuration | 🚧 Planned |

---

## Data Source

Defines where the dashboard data comes from.

### Structure

```yaml
data:
  type: <data-type>
  path: <data-path>
  # Optional fields based on type:
  query: <sql-query>         # For SQL sources
  connection: <connection>   # For SQL sources
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Type of data source (see below) |
| `path` | string | Path or URL to data source |

### Supported Data Types

| Type | Status | Description | Example Path |
|------|--------|-------------|--------------|
| `csv` | ✅ Implemented | CSV file | `"data/sales.csv"` |
| `json` | 🚧 Planned | JSON file | `"data/sales.json"` |
| `sql` | 🚧 Planned | SQL database | `"postgresql://..."` |
| `api` | 🚧 Planned | REST API | `"https://api.example.com/data"` |

### Example

```yaml
data:
  type: csv
  path: "data/example.csv"
```

---

## Charts

An array of chart specifications. At least **one chart is required**.

### Structure

```yaml
charts:
  - id: <unique-id>
    type: <chart-type>
    title: <chart-title>
    x: <column-name>
    y: <column-name>
    agg: <aggregation>
    # Optional fields:
    filter: <filter-expression>
    color: <color-value>
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique chart identifier (alphanumeric, `-`, `_`) |
| `type` | string | Chart type (see below) |
| `x` | string | Column name for X axis |
| `y` | string | Column name for Y axis |

### Optional Fields

| Field | Type | Default | Description | Status |
|-------|------|---------|-------------|--------|
| `title` | string | `<id>` | Display title for the chart | ✅ Implemented |
| `agg` | string | `"sum"` | Aggregation function | ✅ Implemented |
| `filter` | string | none | Filter expression | 🚧 Planned |
| `color` | string | default | Color scheme or specific color | 🚧 Planned |

### Supported Chart Types

| Type | Status | Streamlit | Plotly | Description |
|------|--------|-----------|--------|-------------|
| `bar` | ✅ Implemented | ✅ | ✅ | Bar chart |
| `line` | ✅ Implemented | ✅ | ✅ | Line chart |
| `scatter` | ✅ Implemented | ✅ | ✅ | Scatter plot |
| `pie` | ⚠️ Partial | Fallback to bar | ✅ | Pie chart |
| `area` | 🚧 Planned | - | - | Area chart |
| `histogram` | 🚧 Planned | - | - | Histogram |

### Supported Aggregations

Currently validated aggregations:

| Aggregation | Status | Description |
|-------------|--------|-------------|
| `sum` | ✅ Implemented | Sum of values |
| `mean` | ✅ Implemented | Average of values |
| `count` | ✅ Implemented | Count of records |
| `min` | 🚧 Planned | Minimum value |
| `max` | 🚧 Planned | Maximum value |
| `median` | 🚧 Planned | Median value |

### Example

```yaml
charts:
  - id: "sales_by_country"
    type: "bar"
    title: "Total Sales by Country"
    x: "country"
    y: "sales"
    agg: "sum"

  - id: "sales_trend"
    type: "line"
    title: "Sales Over Time"
    x: "date"
    y: "sales"
    agg: "sum"
```

---

## Pages

Multi-page dashboards allow you to organize charts into logical groups with tabs or navigation.

### Structure

```yaml
pages:
  - id: <page-id>
    title: <page-title>          # Can include emojis directly: "📊 Overview"
    description: <description>    # Optional
    charts:
      - <chart-spec>
      - <chart-spec>
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique page identifier |
| `title` | string | Page display title (can include emojis) |
| `charts` | array | Array of chart specifications for this page |

### Optional Fields

| Field | Type | Description | Status |
|-------|------|-------------|--------|
| `description` | string | Page description or subtitle | ✅ Implemented |

### Example

```yaml
pages:
  - id: "overview"
    title: "📊 Overview"
    description: "High-level sales metrics and KPIs"
    charts:
      - id: "total_sales"
        type: "bar"
        title: "Total Sales by Country"
        x: "country"
        y: "sales"
        agg: "sum"

  - id: "trends"
    title: "📈 Trends"
    description: "Sales trends over time"
    charts:
      - id: "daily_sales"
        type: "line"
        title: "Daily Sales"
        x: "date"
        y: "sales"
        agg: "sum"

      - id: "avg_sales"
        type: "line"
        title: "Average Sales"
        x: "date"
        y: "sales"
        agg: "mean"
```

### How Pages are Rendered

**Streamlit:**
- Each page becomes a tab using `st.tabs()`
- Users click tabs to switch between pages
- All charts in a page are displayed vertically

**Plotly:**
- Each page becomes a button in a tab bar
- JavaScript switches visibility between pages
- Charts are rendered in containers per page

### Backward Compatibility

Dashboards using top-level `charts` (without `pages`) will continue to work:
- **Streamlit**: Charts displayed vertically with dividers
- **Plotly**: Dropdown selector to switch between charts

You **cannot** use both `pages` and `charts` at the top level - choose one approach.

---

## Complete Examples

### Multi-Page Dashboard (Recommended)

```yaml
version: 0.000000001
title: "Sales Analytics Dashboard"

data:
  type: csv
  path: "data/sales.csv"

pages:
  - id: "overview"
    title: "📊 Overview"
    description: "High-level sales metrics and KPIs"
    charts:
      - id: "revenue_by_region"
        type: "bar"
        title: "Revenue by Region"
        x: "region"
        y: "revenue"
        agg: "sum"

  - id: "trends"
    title: "📈 Trends"
    description: "Sales trends and patterns"
    charts:
      - id: "revenue_trend"
        type: "line"
        title: "Revenue Trend (Monthly)"
        x: "month"
        y: "revenue"
        agg: "mean"

      - id: "customer_distribution"
        type: "scatter"
        title: "Customer Age vs. Purchase Amount"
        x: "age"
        y: "purchase_amount"
        agg: "mean"
```

### Single-Page Dashboard (Legacy)

```yaml
version: 0.000000001
title: "Sales Analytics Dashboard"

data:
  type: csv
  path: "data/sales.csv"

charts:
  - id: "revenue_by_region"
    type: "bar"
    title: "Revenue by Region"
    x: "region"
    y: "revenue"
    agg: "sum"

  - id: "revenue_trend"
    type: "line"
    title: "Revenue Trend (Monthly)"
    x: "month"
    y: "revenue"
    agg: "mean"
```

---

## Validation Rules

### Enforced by Validator

1. **Required top-level fields**: `version`, `data`, and either `charts` OR `pages`
2. **Version format**: Must be string, int, or float
3. **Data source**:
   - Must have `type` and `path`
   - Type must be: `csv`, `json`, or `sql`
4. **Charts** (legacy format):
   - Must be a non-empty array
   - Each chart must have: `id`, `type`, `x`, `y`
   - Chart type must be: `bar`, `line`, `scatter`, or `pie`
   - If `agg` is specified, must be: `sum`, `mean`, or `count`
   - Chart IDs should be unique (basic check)
5. **Pages** (multi-page format):
   - Must be a non-empty array
   - Each page must have: `id`, `title`, `charts`
   - Page `charts` must be a non-empty array
   - Charts within pages follow the same validation rules as #4
   - Cannot have both `pages` and `charts` at top level

### Not Validated

- Whether data files actually exist
- Whether column names exist in the data
- Whether aggregation makes sense for the data type
- Duplicate chart IDs (fully)
- Platform-specific capabilities

---

## Design Principles

1. **Declarative**: Describe *what*, not *how*
2. **Platform-agnostic**: Same spec works for multiple targets
3. **Minimal**: Only essential fields required
4. **Extensible**: Transformers can support additional features
5. **Non-validating**: Validation is semantic, not prescriptive
6. **Human & LLM-friendly**: Clean YAML syntax

---

## How Data Flows

```
.dashml file (YAML)
    ↓
Parser (yaml.safe_load)
    ↓
Dictionary (Python dict)
    ↓
Validator (semantic checks)
    ↓
Transformer (code generation)
    ↓
Generated code (Python/HTML/etc.)
    ↓
Generated code loads data at runtime
```

**Important**: The DashML engine **never loads the actual data**. It only validates the spec structure. Data loading happens in the **generated code**.

---

## Usage with CLI

```bash
# Generate Streamlit app
python cli.py build dashboard.dashml --target streamlit --output app.py

# Generate Plotly HTML
python cli.py build dashboard.dashml --target plotly --output dashboard.html

# Watch mode (auto-rebuild on changes)
python cli.py watch dashboard.dashml --target streamlit --output app.py

# List available transformers
python cli.py list
```

---

## Future Enhancements

### Planned Features (🚧)

- **Data Types**: `json`, `sql`, `api` data sources
- **Chart Types**: `area`, `histogram`, additional chart types
- **Aggregations**: `min`, `max`, `median`, custom aggregations
- **Filters**: Chart-level and global filters
- **Themes**: Color schemes, custom styling
- **Interactivity**: Click handlers, drill-down
- **Computed Fields**: Derived columns, calculations
- **Multi-dataset**: Multiple data sources per dashboard

### Schema Evolution

The schema is designed to evolve without breaking changes:
- New optional fields can be added
- Transformers decide which features to support
- Unknown fields are ignored (forward compatibility)

---

## Status Legend

- ✅ **Implemented**: Fully working in current version
- ⚠️ **Partial**: Partially implemented or fallback behavior
- 🚧 **Planned**: Defined in schema but not yet implemented
- ❌ **Not Supported**: Not available in current platform

---

## Notes

- Field names are case-sensitive
- Chart IDs should use `snake_case` or `kebab-case`
- Paths can be relative or absolute
- YAML syntax allows comments with `#`
- Strings with special characters should be quoted

---

**Last Updated**: 2025-11-30
**Maintained by**: Dawid Olejniczak, Szymon Nowaczyk
