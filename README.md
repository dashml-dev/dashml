# DashML

A declarative language for data visualization dashboards that compiles to multiple platforms.

Write your dashboard spec once in `.dashml` format, then compile it to **Streamlit**, **Plotly**, **Observable Plot**, **Apache Superset**, **Vega-Lite**, or **Grafana**.

## Quick Start

```bash
# Generate a Streamlit app
python -m dashml_new.cli build dashboard.dashml --target streamlit --output app_dir
streamlit run app_dir/app.py

# Generate a standalone Plotly HTML dashboard
python -m dashml_new.cli build dashboard.dashml --target plotly --output dashboard.html

# Generate an Observable Plot HTML dashboard
python -m dashml_new.cli build dashboard.dashml --target observable --output dashboard.html

# Generate a Vega-Lite JSON specification
python -m dashml_new.cli build dashboard.dashml --target vegalite --output dashboard.json

# Generate a Grafana dashboard JSON
python -m dashml_new.cli build dashboard.dashml --target grafana --output dashboard.json

# Create a dashboard directly in Apache Superset
python -m dashml_new.cli build dashboard.dashml --target superset \
  --superset-user admin --superset-password admin
```

## Database credentials

For SQL or BigQuery data sources, the generated artifact reads connection
parameters from environment variables at runtime — never from baked-in literals.
The generator emits `.env.example`, `.gitignore`, and `SECRETS.md` next to the
generated `app.py`. Copy `.env.example` to `.env`, fill in the values, and run.
The same artifact directory is safe to commit to a public repository.

```bash
python -m dashml_new.cli build dashboard.dashml --target plotly --output app_dir
cd app_dir
cp .env.example .env       # edit .env, set DASHML_DB_PASSWORD etc.
python app.py              # reads from env (or .env via python-dotenv)
```

See `SECRETS.md` in any generated SQL/BigQuery artifact for the full list of
environment variables and recommended deployment patterns (Docker, Kubernetes,
systemd, CI/CD, GCP Workload Identity).

## Example

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
    title: "Sales by Country"
    x: "country"
    y: "sales"
    agg: "sum"
    sort: "y"
    sort_order: "desc"
    limit: 10
```

## Documentation

- **[User Guide](dashml_new/README.md)** - Full specification reference, chart types, CLI, themes
- **[Architecture](ARCHITECTURE.md)** - System design, compiler pipeline, type system

## Key Concepts

- **Compiler, not runtime** - DashML generates standalone code; it never loads or touches your data
- **Credentials never baked** - generated SQL/BigQuery artifacts read database credentials from environment variables at runtime; safe to version-control
- **12 chart types** - bar, line, scatter, pie, area, histogram, stacked_bar, grouped_bar, bubble, heatmap, box, geo
- **3 data sources** - CSV, SQL (PostgreSQL/MySQL/SQLite), Google BigQuery
- **6 backends** - Streamlit, Plotly, Observable Plot, Apache Superset, Vega-Lite, Grafana
- **6 built-in themes** - Dracula, Nord, Gruvbox, Monokai, One Dark, Solarized Light

## Authors

- Dawid Olejniczak
- Szymon Nowaczyk

## License

MIT
