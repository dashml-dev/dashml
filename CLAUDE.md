# DashML

Declarative YAML-based compiler for generating data visualization dashboards. Write a `.dashml` spec once, compile it to Streamlit, Plotly, Observable Plot, Apache Superset, Vega-Lite, or Grafana.

## DashML Manifesto

- **Declarative, not Imperative** - Users describe *what* they want, not *how* to build it
- **Source-Agnostic by Design** - Same spec works across CSV, SQL, BigQuery
- **Read-Only by Principle** - DashML never modifies data; it only reads and visualizes
- **Typeless at the Core** - Core validates structure/semantics only; type inference is deferred to generated code
- **Extensible and Backend-Neutral** - New backends are added as transformer plugins without changing the core
- **Validating the Spec, Trusting the Data** - Core validates the .dashml spec structure; data correctness is the user's responsibility
- **LLM- and Human-Friendly** - YAML DSL is readable by both humans and AI; designed for AI-assisted dashboard creation

## Architecture

Hexagonal (ports & adapters) / microkernel pattern. The core is purely semantic and never loads data.

```
.dashml YAML → Parser → Validator → Transformer → Generated Code
```

- **Parser** (`core/parser.py`) - `yaml.safe_load`, returns plain dict
- **Validator** (`core/validator.py`) - Semantic checks only (required fields, valid chart types, valid agg/filter operators, data-source-specific rules)
- **Engine** (`core/engine.py`) - Orchestrates parser → validator pipeline
- **Transformers** - Pluggable backends registered via registry pattern (`transformers/registry.py`)

## Project Structure

```
dashml_new/
  core/
    types.py          # TypedDict definitions (DashMLSpec, ChartSpec, PageSpec, DataSpec, etc.)
    parser.py         # YAML parsing
    validator.py      # Semantic validation
    engine.py         # Orchestration
    watcher.py        # File watcher for hot reload
  transformers/
    base.py           # Abstract Transformer interface + style loading
    constants.py      # Shared constants (chart categories, colors, operators)
    registry.py       # Transformer discovery and registration
    secrets.py        # Generated env-loader code + .env.example/.gitignore/SECRETS.md emission
    streamlit.py      # Streamlit + Altair code generator
    plotly.py         # Plotly.js HTML generator
    observable.py     # Observable Plot + D3 HTML generator
    superset.py       # Superset REST API integration
    vegalite.py       # Vega-Lite JSON specification generator
    grafana.py        # Grafana dashboard JSON generator
  cli.py              # CLI entry point (build, watch, list)
  output/             # Generated multi-file outputs (Flask + HTML for SQL/BQ backends)

styles/               # Theme files (.dmls) - dracula, nord, gruvbox, monokai, onedark, solarized_light
dashml-schema.json    # JSON Schema for .dashml validation
*.dashml              # Example specs (simple, sql, bigquery, multipage, new_charts)
test_new_architecture.py  # Test suite
```

## DSL Format (.dashml)

YAML files with:
- `version`, `title`, `style` (optional theme reference)
- `data`: `type` (csv/sql/bigquery), `path` (file path or schema.table or dataset.table)
- `charts` (single-page) or `pages` (multi-page, each with own `charts` array)
- Each chart: `id`, `type`, `title`, `x`, `y`, optional `agg`, `group`, `size`, `filter`, `sort`, `limit`, `x_type`/`y_type`

**12 chart types:** bar, line, scatter, pie, area, histogram, stacked_bar, grouped_bar, bubble, heatmap, box, geo

**Aggregations:** sum, mean, count

**Filter operators:** eq, ne, gt, lt, gte, lte, in, contains

## Backends

| Backend | Output | Libraries |
|---------|--------|-----------|
| **Streamlit** | Python file (CSV) or Python+SQLAlchemy/BQ-client (SQL/BQ) | Streamlit, Pandas, Altair |
| **Plotly** | HTML (CSV) or Flask+HTML (SQL/BQ) | Plotly.js, Flask |
| **Observable** | HTML (CSV) or Flask+HTML (SQL/BQ) | Observable Plot, D3.js, Flask |
| **Superset** | REST API calls (no files) | requests |
| **Vega-Lite** | JSON specification (vega-embed compatible) | vega-embed (browser) |
| **Grafana** | Dashboard JSON for import / provisioning | (Grafana instance) |

## Credentials handling

Generated artifacts for SQL and BigQuery sources never bake credentials into
source code. The runtime reads connection parameters from environment variables
(`DASHML_DB_*` for SQL; `DASHML_BQ_PROJECT`, `DASHML_BQ_CREDENTIALS` for BQ),
optionally loaded from a `.env` file via `python-dotenv` (loader is best-effort
— missing dotenv is silently OK). Each generated SQL/BQ artifact includes:

- `.env.example` — template with placeholders (or build-time CLI defaults if provided)
- `.gitignore` — excludes `.env`
- `SECRETS.md` — operator-facing instructions covering local dev, Docker, K8s, systemd, CI/CD, GCP Workload Identity

CLI args `--db-host` / `--db-port` / `--db-name` / `--db-user` / `--db-password`
are **optional** for SQL builds (used only as visible defaults in `.env.example`).
`--bq-project` remains **required** for BigQuery builds because the project ID
is embedded in compile-time SQL queries (the project ID is a public identifier,
not a secret). `--bq-credentials` is no longer used at build time — credentials
path always comes from `DASHML_BQ_CREDENTIALS` at runtime.

## Commands

```bash
# Build
python -m dashml_new.cli build <spec>.dashml --target <streamlit|plotly|observable|superset> --output <path>

# Watch (hot reload)
python -m dashml_new.cli watch <spec>.dashml --target <target> --output <path> --run

# List available transformers
python -m dashml_new.cli list

# Run tests
python test_new_architecture.py
```

## Key Conventions

- **TypedDict** for type hints (not dataclasses) - zero runtime overhead
- **Code generation** over runtime interpretation - generated code is readable and debuggable
- **Core never touches data** - all data loading/aggregation lives in generated code
- **Shared constants** in `transformers/constants.py` (chart categories, default colors, operators)
- **Registry pattern** for transformer plugins - add new backends without modifying core
