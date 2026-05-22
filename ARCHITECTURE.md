# DashML Architecture

## Overview

DashML is a build-time compiler that takes a `.dashml` YAML specification and generates standalone dashboard code for one of six target platforms. The core never loads, queries, or materializes data.

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
  Normalizer (NormalizedSpec — IR shared by all transformers)
     |
     +---> Streamlit Transformer ---> Python code (Streamlit + Altair)
     +---> Plotly Transformer ------> HTML + JS (Plotly.js)
     +---> Observable Transformer --> HTML + JS (Observable Plot + D3)
     +---> Superset Transformer ----> REST API calls (creates dashboard directly)
     +---> Vega-Lite Transformer ---> JSON specification
     +---> Grafana Transformer -----> Dashboard JSON (for import / provisioning)
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
    secrets.py         # Generated env-loader code; .env.example/.gitignore/SECRETS.md emission
    streamlit.py       # Streamlit + Altair code generator
    plotly.py          # Plotly.js HTML generator
    observable.py      # Observable Plot + D3 HTML generator
    superset.py        # Superset REST API integration
    vegalite.py        # Vega-Lite JSON specification generator
    grafana.py         # Grafana dashboard JSON generator

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

### Secrets (`transformers/secrets.py`)

Centralizes generation of credential-handling code shared by Streamlit, Plotly, and Observable transformers when the data source is SQL or BigQuery. Single source of truth for the env-loader pattern.

Public functions:

- `emit_sql_env_loader()` - returns a Python boilerplate string that reads `DASHML_DB_TYPE`, `DASHML_DB_HOST`, `DASHML_DB_PORT`, `DASHML_DB_NAME`, `DASHML_DB_USER`, `DASHML_DB_PASSWORD` from `os.environ`, optionally loading `.env` via `python-dotenv` (best-effort import), and constructs `DATABASE_URL` based on the runtime `DASHML_DB_TYPE`. Raises `RuntimeError` listing missing variables if any required env is unset.
- `emit_bq_env_loader(project)` - returns a Python boilerplate that initializes a `bigquery.Client`. Reads `DASHML_BQ_PROJECT` from env (falling back to the build-time `project` argument as a default; project ID is a public identifier embedded in compile-time SQL queries) and `DASHML_BQ_CREDENTIALS` (optional service account JSON path; if unset, falls back to Application Default Credentials).
- `emit_env_example(data_type, db_config)` - returns a `.env.example` template. Build-time CLI values (if provided) are inlined as visible defaults; password fields are always blank.
- `emit_gitignore()` - returns `.gitignore` content (`.env`, `__pycache__/`, `*.pyc`).
- `emit_secrets_readme(data_type)` - returns `SECRETS.md` operator instructions covering local development (`cp .env.example .env`), Docker `--env-file`, Kubernetes `Secret`, systemd `EnvironmentFile=`, CI/CD secret stores, and (for BigQuery) GCP Workload Identity.

The CLI emits the three auxiliary files (`.env.example`, `.gitignore`, `SECRETS.md`) into the output directory whenever the target is `plotly`, `observable`, or `streamlit` and the source is `sql` or `bigquery`.

---

## Data Flow by Backend

### Streamlit Transformer

Generates a single Python file that uses Streamlit for layout and Altair for charts.

- **CSV**: `pd.read_csv()` inline. Column types inferred from pandas dtypes with fallback date detection.
- **SQL**: `sqlalchemy.create_engine(DATABASE_URL)` + `pd.read_sql()`. `DATABASE_URL` constructed at module load from `DASHML_DB_*` env (see `secrets.py`). Column types detected from `information_schema.columns`.
- **BigQuery**: `google.cloud.bigquery.Client` initialized at module load from `DASHML_BQ_PROJECT` + `DASHML_BQ_CREDENTIALS` env. Column types detected from `INFORMATION_SCHEMA.COLUMNS`.

Multi-page dashboards render as `st.tabs()`.

### Plotly Transformer

Generates standalone HTML with embedded JavaScript using Plotly.js.

- **CSV**: Client-side fetch and parse (simple comma-split parser). Single HTML file.
- **SQL/BigQuery**: Flask backend (`app.py`) with `/api/data` and `/api/schema` endpoints. `app.py` reads credentials from env (see `secrets.py`); the project ID for BigQuery is also embedded in compile-time SQL queries. Frontend (`index.html`) fetches JSON and renders client-side.

Aggregation, filtering, sorting, and limiting all happen in JavaScript.

### Observable Transformer

Generates standalone HTML using Observable Plot (v0.6) and D3.js (v7).

- **CSV**: Client-side fetch and parse. Single HTML file.
- **SQL/BigQuery**: Flask backend with API endpoints, same pattern as Plotly. Same env-based credentials handling.

Pie charts use D3 directly (`d3.pie()`) since Observable Plot has no native pie support. Geo charts load world topology from a CDN.

### Superset Transformer

Does not generate files. Communicates with a Superset instance via REST API.

- **CSV**: Uploads the CSV file to Superset, creates a dataset.
- **SQL**: References an existing table. Optionally creates a database connection from CLI args.
- **BigQuery**: Creates a BigQuery database connection using service account credentials.

Charts are created with Superset's `POST /api/v1/chart/` endpoint. Dashboards are created or updated (deduplicated by title). Running the command again cleans up old charts and replaces them.

Credentials passed via CLI (`--db-password`, `--bq-credentials`) are forwarded to the Superset instance through its REST API and stored in Superset's own metadata database (`encrypted_extra` field for BigQuery). They are not written to any file on the DashML side. The env-based credentials mechanism described above does **not** apply to Superset — it is an API-driven backend, not a file-generating one.

### Vega-Lite Transformer

Generates a Vega-Lite JSON specification (`vega-embed` compatible).

- **CSV**: Either inline-embeds the parsed CSV (`--embed-data`) for a fully self-contained JSON, or references the CSV by relative URL.
- **SQL/BigQuery**: Not supported as a generated runtime — Vega-Lite has no native database connection mechanism. Users perform a separate ETL step to extract data into CSV/JSON before feeding it to Vega-Lite.

Use case: single-spec embedding into HTML pages, notebook outputs, and as a comparison format for empirical evaluation against DashML in the LLM-generation benchmark (see `nvbench_*` scripts).

### Grafana Transformer

Generates a Grafana dashboard JSON ready to be imported (manually, via the Grafana HTTP API, or through provisioning).

- **CSV**: Requires `--grafana-csv-url` pointing to a publicly reachable URL serving the CSV (Grafana's Infinity plugin fetches it via HTTP). Alternatively, `--grafana-serve-csv PORT` starts a local HTTP server during the build.
- **SQL**: Generates panels with embedded SQL queries against a Grafana datasource referenced by UID (`--grafana-datasource-uid`). The Grafana instance manages its own datasource credentials — DashML does not bake any credentials into the JSON.
- **BigQuery**: Same pattern, using Grafana's BigQuery plugin. Datasource credentials live in the Grafana instance.

Box plots are not natively supported in Grafana — they are rendered as a Markdown panel with a "not supported" notice. Style fields `background`, `card`, and `buttons` are ignored because Grafana's theme is configured at the instance level, not per dashboard.

---

## CLI (`cli.py`)

Three commands:

- `build` - compile a `.dashml` spec to the target platform
- `list` - show registered transformers
- `watch` - poll the spec file and rebuild on change

The CLI registers the six built-in transformers on startup, parses arguments, loads the spec through the engine, and writes the transformer output to disk (or executes the Superset API calls).

For SQL targets, all credential CLI flags (`--db-host`, `--db-port`, `--db-name`, `--db-user`, `--db-password`, `--db-type`) are **optional**. When provided, they are written into the generated `.env.example` as visible defaults — never baked into source code. For BigQuery, `--bq-project` is **required** at build time (project ID is embedded in compile-time SQL queries) but is not a secret. `--bq-credentials` is no longer used at build time; service account paths are always read from the `DASHML_BQ_CREDENTIALS` environment variable at runtime.

After writing the main artifact, the CLI emits three additional files (`.env.example`, `.gitignore`, `SECRETS.md`) into the output directory whenever the target is `plotly`, `observable`, or `streamlit` and the source is `sql` or `bigquery`. See `secrets.py` for the file contents.

---

## Theme System

`.dmls` files are YAML with a `colors` block. The normalizer's `_resolve_style()` method loads the file, merges values over defaults from `constants.py`, and exposes the resolved palette to every transformer via `spec["style"]`. If no style is specified, defaults apply.

Recognized color fields:

| Field | Purpose |
|---|---|
| `primary` | accent color: solid bar fill (no sort/group), line/scatter markers, KPI text, reference lines, active tab |
| `sequential` | name of a 6-stop categorical ramp (`blues`, `greens`, `reds`, `oranges`, `purples`, `teals`, `viridis`, `cividis`). Drives gradient coloring for sorted-bar, pie, bubble, stacked_bar, grouped_bar, and choropleth |
| `background` | page background (HTML body / Plotly paper / Observable canvas) |
| `card` | chart container and KPI card background |
| `text` | global text color |
| `buttons` | accent for filter buttons; if omitted, falls back to `primary` |

Categorical palettes for Superset, Vega-Lite, and Grafana are intentionally left to the target's native default scheme — the `.dmls` palette does not override them.

---

## Design Decisions

**TypedDict over dataclasses** - The spec is a plain dict throughout. TypedDict provides compile-time type checking and IDE support without any runtime conversion cost.

**No intermediate representation classes** - Unlike a traditional compiler with AST/IR objects, DashML passes the parsed YAML dict directly to transformers. Validation happens on the dict. This keeps the system simple and avoids conversion overhead.

**Code generation over runtime interpretation** - Transformers emit standalone code that runs independently of DashML. This makes debugging easier (generated code is readable), works with existing tools, and enables hot reload by regenerating.

**Credentials in environment, never in source** - Generated SQL/BigQuery artifacts read connection parameters from environment variables at runtime. This decouples the artifact from the machine that built it: the same `app.py` runs on any host given a populated environment. It also makes the artifact directory safe to commit to a public repository — the source code contains no secrets, only references to env variable names. The runtime supports three credential sources: shell environment, `.env` file (loaded by `python-dotenv` if installed; missing dotenv is silently OK), and platform-managed secret stores (Docker `--env-file`, Kubernetes `Secret`, systemd `EnvironmentFile=`, GCP Workload Identity for BigQuery).

**BigQuery project ID baked, credentials not** - Project ID is a public identifier (visible in any `SELECT * FROM` `project.dataset.table`). It is required at compile time because it is embedded into SQL queries as part of the fully-qualified table reference. Service account paths and other credentials remain runtime-only. This split keeps the generator simple while preserving the security guarantee.

**Core never touches data** - The validator checks structural correctness only. All data loading, aggregation, filtering, and rendering is the responsibility of the generated code or the target platform.

**Polling-based file watcher** - Uses simple mtime polling instead of OS-level file watchers (e.g. inotify/fsevents) to avoid external dependencies.
