# DashML Architecture

## Overview

DashML is a build-time compiler that takes a `.dashml` YAML specification and generates standalone dashboard code for one of four target platforms. The core never loads, queries, or materializes data.

```
.dashml (YAML)
     |
     v
  Parser (yaml.safe_load)
     |
     v
  Validator (semantic checks)
     |
     v
  Validated spec (plain Python dict, annotated with TypedDict)
     |
     +---> Streamlit Transformer ---> Python code (Streamlit + Altair)
     +---> Plotly Transformer ------> HTML + JS (Plotly.js)
     +---> Observable Transformer --> HTML + JS (Observable Plot + D3)
     +---> Superset Transformer ----> REST API calls (creates dashboard directly)
```

Data loading, aggregation, filtering, and rendering all happen in the generated code at runtime, not during compilation.

---

## Project Structure

```
dashml_new/
  core/
    engine.py          # Orchestrates parse -> validate -> transform
    parser.py          # YAML loading via yaml.safe_load
    validator.py       # Semantic validation of specs
    types.py           # TypedDict definitions for type hints
    watcher.py         # File watcher for watch mode (polling-based)

  transformers/
    base.py            # Abstract Transformer interface
    registry.py        # Name-based transformer registry
    constants.py       # Shared constants (chart categories, colors, filter ops)
    streamlit.py       # Streamlit + Altair code generator
    plotly.py          # Plotly.js HTML generator
    observable.py      # Observable Plot + D3 HTML generator
    superset.py        # Superset REST API integration

  cli.py               # CLI entry point (build, list, watch commands)
```

---

## Core

### Parser (`core/parser.py`)

Loads a `.dashml` file using `yaml.safe_load` and returns a plain Python dictionary. No AST or intermediate representation classes are constructed.

### Validator (`core/validator.py`)

Validates the parsed dict for semantic correctness:

- Required top-level fields: `version`, `data`
- Must have either `charts` or `pages`
- Chart validation: required `id`, `type`, `x`, `y`; type must be one of 12 supported types
- Data source validation: `csv` requires `path`; `sql` requires `path` in `schema.table` format; `bigquery` requires `path` in `dataset.table` format
- Aggregation must be `sum`, `mean`, or `count`
- Filter operators must be one of `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `in`, `contains`
- `stacked_bar` and `grouped_bar` require a `group` field
- `bubble` requires a `size` field

The validator never checks whether data files exist or whether columns are valid. It validates structure only.

### Type System (`core/types.py`)

Uses `TypedDict` to annotate the spec dictionary. This provides IDE autocomplete and static type checking via mypy with zero runtime overhead. The parsed YAML dict flows through the entire system without conversion.

Key types:
- `DashMLSpec` - top-level spec
- `ChartSpec` - individual chart configuration
- `PageSpec` - page in multi-page dashboards
- `DataSpec` - data source configuration
- `FilterSpec` - filter condition
- `StyleColors` - theme color definitions

All TypedDicts use `total=False` for backward-compatible schema evolution.

### Engine (`core/engine.py`)

Orchestrates the pipeline: load spec, validate, pass to transformer, return generated code.

### Watcher (`core/watcher.py`)

Polls a file's modification time at a configurable interval (default: 1 second). When a change is detected, invokes a callback to trigger a rebuild.

---

## Transformers

### Base Interface (`transformers/base.py`)

Abstract base class that all transformers implement:

- `name` (property) - transformer identifier (e.g. `"streamlit"`)
- `description` (property) - human-readable description
- `build(spec)` - takes a validated spec dict, returns generated code as a string
- `get_run_command(output_path)` - returns the shell command to run the generated output
- `warn(message)` - emits a non-fatal warning
- `_load_style_config(spec)` - loads and parses a `.dmls` theme file

### Registry (`transformers/registry.py`)

A simple dict-based registry that maps transformer names to classes. Transformers are registered at CLI startup. `registry.get("streamlit")` returns a new `StreamlitTransformer` instance.

### Constants (`transformers/constants.py`)

Shared constants used across all transformers:

- `CHARTS_NEED_AGGREGATION` - chart types that require groupby + agg: `bar`, `line`, `area`, `pie`, `stacked_bar`, `grouped_bar`, `scatter`, `bubble`, `heatmap`, `geo`
- `CHARTS_USE_RAW_DATA` - chart types that skip aggregation: `histogram`, `box`
- `AGG_METHODS` - mapping of aggregation names to pandas/JS equivalents
- `SUPPORTED_FILTER_OPS` - valid filter operators
- `DEFAULT_HISTOGRAM_BINS` - 20
- `DEFAULT_PRIMARY_COLOR` - `#29b5e8`
- `DEFAULT_SECONDARY_COLORS` - 10 categorical colors
- `TEMPORAL_FIELD_NAMES` - heuristic field names used for date detection

---

## Data Flow by Backend

### Streamlit Transformer

Generates a single Python file that uses Streamlit for layout and Altair for charts.

- **CSV**: `pd.read_csv()` inline. Column types inferred from pandas dtypes with fallback date detection.
- **SQL**: `sqlalchemy.create_engine()` + `pd.read_sql()`. Column types detected from `information_schema.columns`.
- **BigQuery**: `google.cloud.bigquery.Client` + `pd.read_sql()`. Column types detected from `INFORMATION_SCHEMA.COLUMNS`.

Multi-page dashboards render as `st.tabs()`.

### Plotly Transformer

Generates standalone HTML with embedded JavaScript using Plotly.js.

- **CSV**: Client-side fetch and parse (simple comma-split parser). Single HTML file.
- **SQL/BigQuery**: Flask backend (`app.py`) with `/api/data` and `/api/schema` endpoints. Frontend (`index.html`) fetches JSON and renders client-side.

Aggregation, filtering, sorting, and limiting all happen in JavaScript.

### Observable Transformer

Generates standalone HTML using Observable Plot (v0.6) and D3.js (v7).

- **CSV**: Client-side fetch and parse. Single HTML file.
- **SQL/BigQuery**: Flask backend with API endpoints, same pattern as Plotly.

Pie charts use D3 directly (`d3.pie()`) since Observable Plot has no native pie support. Geo charts load world topology from a CDN.

### Superset Transformer

Does not generate files. Communicates with a Superset instance via REST API.

- **CSV**: Uploads the CSV file to Superset, creates a dataset.
- **SQL**: References an existing table. Optionally creates a database connection from CLI args.
- **BigQuery**: Creates a BigQuery database connection using service account credentials.

Charts are created with Superset's `POST /api/v1/chart/` endpoint. Dashboards are created or updated (deduplicated by title). Running the command again cleans up old charts and replaces them.

---

## CLI (`cli.py`)

Three commands:

- `build` - compile a `.dashml` spec to the target platform
- `list` - show registered transformers
- `watch` - poll the spec file and rebuild on change

The CLI registers the four built-in transformers on startup, parses arguments, loads the spec through the engine, and writes the transformer output to disk (or executes the Superset API calls).

For SQL/BigQuery targets, database configuration is collected from CLI flags and passed to the transformer via `set_db_config()`.

---

## Theme System

`.dmls` files are YAML with a `colors` block. The transformer's `_load_style_config()` method reads the file and extracts color values. If no style is specified, default colors from `constants.py` are used.

Color fields: `background`, `card`, `primary`, `text`, `secondary` (array).

The `buttons` field is accepted but not used by any transformer (all emit a warning if it's present).

---

## Design Decisions

**TypedDict over dataclasses** - The spec is a plain dict throughout. TypedDict provides compile-time type checking and IDE support without any runtime conversion cost.

**No intermediate representation classes** - Unlike a traditional compiler with AST/IR objects, DashML passes the parsed YAML dict directly to transformers. Validation happens on the dict. This keeps the system simple and avoids conversion overhead.

**Code generation over runtime interpretation** - Transformers emit standalone code that runs independently of DashML. This makes debugging easier (generated code is readable), works with existing tools, and enables hot reload by regenerating.

**Core never touches data** - The validator checks structural correctness only. All data loading, aggregation, filtering, and rendering is the responsibility of the generated code or the target platform.

**Polling-based file watcher** - Uses simple mtime polling instead of OS-level file watchers (e.g. inotify/fsevents) to avoid external dependencies.
