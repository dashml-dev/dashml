# DashML

A declarative language for data visualization dashboards that compiles to multiple platforms.

Write your dashboard spec once in `.dashml` format, then compile it to **Streamlit**, **Plotly**, **Observable Plot**, **Apache Superset**, **Vega-Lite**, or **Grafana**.

## Install

```bash
pip install dashml-lang
```

Or with [uv](https://docs.astral.sh/uv/) for an isolated tool install:

```bash
uv tool install dashml-lang
```

The CLI command is `dashml` (the distribution name `dashml-lang` only matters at install time).

## Quick Start

The repo includes a ready-to-build example at [`examples/startup_funding.dashml`](examples/startup_funding.dashml) — a 4-page, 20-chart dashboard against real startup funding data. Clone the repo or copy those two files to try it.

```bash
# Generate a Streamlit app
dashml build examples/startup_funding.dashml --target streamlit --output app_dir
streamlit run app_dir/app.py

# Generate a standalone Plotly HTML dashboard
dashml build examples/startup_funding.dashml --target plotly --output dashboard_dir

# Generate an Observable Plot HTML dashboard
dashml build examples/startup_funding.dashml --target observable --output dashboard_dir

# Generate a Vega-Lite JSON specification
dashml build examples/startup_funding.dashml --target vegalite --output dashboard_dir

# Generate a Grafana dashboard JSON
dashml build examples/startup_funding.dashml --target grafana --output dashboard_dir

# Create a dashboard directly in Apache Superset
dashml build examples/startup_funding.dashml --target superset \
  --superset-user admin --superset-password admin
```

For Streamlit, you'll also need the runtime extras:

```bash
pip install 'dashml-lang[streamlit]'
```

`dashml list` shows all available transformers; `dashml --help` shows full CLI options.

## Database credentials

For SQL or BigQuery data sources, the generated artifact reads connection
parameters from environment variables at runtime — never from baked-in literals.
The generator emits `.env.example`, `.gitignore`, and `SECRETS.md` next to the
generated `app.py`. Copy `.env.example` to `.env`, fill in the values, and run.
The same artifact directory is safe to commit to a public repository.

```bash
dashml build dashboard.dashml --target plotly --output app_dir
cd app_dir
cp .env.example .env       # edit .env, set DASHML_DB_PASSWORD etc.
python app.py              # reads from env (or .env via python-dotenv)
```

See `SECRETS.md` in any generated SQL/BigQuery artifact for the full list of
environment variables and recommended deployment patterns (Docker, Kubernetes,
systemd, CI/CD, GCP Workload Identity).

## Example spec

```yaml
version: "1.0"
title: "Sales Dashboard"
style: "dracula"

data:
  type: csv
  path: sales.csv

charts:
  - id: "sales_by_country"
    type: "bar"
    title: "Sales by Country"
    x: "country"
    y: "sales"
    agg: "sum"
    sort: "y"
    sort_order: "desc"
    limit: 10
```

## Documentation

- **[Architecture](ARCHITECTURE.md)** — system design, compiler pipeline, type system
- **[Testing](TESTING.md)** — running the test suite
- **[Quick start notes](QUICK_START.txt)** — extra command snippets

## Key Concepts

- **Compiler, not runtime** — DashML generates standalone code; it never loads or touches your data
- **Credentials never baked** — generated SQL/BigQuery artifacts read database credentials from environment variables at runtime; safe to version-control
- **12 chart types** — bar, line, scatter, pie, area, histogram, stacked_bar, grouped_bar, bubble, heatmap, box, geo
- **3 data sources** — CSV, SQL (PostgreSQL/MySQL/SQLite), Google BigQuery
- **6 backends** — Streamlit, Plotly, Observable Plot, Apache Superset, Vega-Lite, Grafana
- **6 built-in themes** — Dracula, Nord, Gruvbox, Monokai, One Dark, Solarized Light

## Authors

- Dawid Olejniczak
- Szymon Nowaczyk

## License

MIT
