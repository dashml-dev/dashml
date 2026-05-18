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

### Runtime extras

The base `pip install dashml-lang` gives you the compiler. To actually **run** a generated artifact, you also need the matching runtime libraries. Install one or more extras combining the target with the data source:

| Target | CSV | SQL | BigQuery |
|---|---|---|---|
| Streamlit | `[streamlit]` | `[streamlit,sql]` | `[streamlit,bigquery]` |
| Plotly / Observable | _(no extras — static HTML)_ | `[flask,sql]` | `[flask,bigquery]` |
| Vega-Lite | _(no extras — JSON only)_ | _(no extras)_ | _(no extras)_ |
| Grafana | _(no extras — JSON only)_ | _(no extras)_ | _(no extras)_ |
| Superset | `[superset]` | `[superset]` | `[superset]` |

For example, a Streamlit dashboard that queries Postgres:

```bash
pip install 'dashml-lang[streamlit,sql]'
```

Or the all-inclusive variant if you want to try every target and every source:

```bash
pip install 'dashml-lang[all]'
```

`dashml list` shows all available transformers; `dashml --help` shows full CLI options.

## Try all 6 backends locally

The repo ships a [`demo/`](demo/) directory with a reproducible reference stack — Postgres, Apache Superset, and Grafana orchestrated by Docker Compose — for evaluating DashML against a real SQL data source.

```bash
cd demo
docker compose up -d
# wait ~60-90s for Superset to initialize on first boot
```

That gives you Postgres on `:5432` (seeded with `startup_funding`), Superset on http://localhost:8088 (admin/admin), and Grafana on http://localhost:3000 (admin/admin). Then compile [`examples/startup_funding_sql.dashml`](examples/startup_funding_sql.dashml) — the SQL twin of the CSV example — into all six platforms against that single shared database. See [`demo/README.md`](demo/README.md) for the full walkthrough.

The demo stack is for evaluation only, not production guidance.

## Database credentials

For SQL or BigQuery data sources, the generated artifact reads connection
parameters from environment variables at runtime — never from baked-in literals.
The generator always emits `.gitignore` and `SECRETS.md` next to the generated
`app.py`. Pass `--emit-env-example` to additionally get a blank `.env.example`
template you can copy and fill in. The same artifact directory is safe to commit
to a public repository.

```bash
dashml build dashboard.dashml --target plotly --output app_dir --emit-env-example
cd app_dir
cp .env.example .env       # edit .env, set DASHML_DB_* values
python app.py              # reads from env (or .env via python-dotenv)
```

Without `--emit-env-example`, supply the same variables through your shell,
container, systemd unit, or CI secret store — see `SECRETS.md` in the artifact.

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
