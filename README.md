# DashML

A declarative language for data visualization dashboards that compiles to multiple platforms.

Write your dashboard spec once in `.dashml` format, then compile it to **Streamlit**, **Plotly**, **Observable Plot**, or **Apache Superset**.

## Quick Start

```bash
# Generate a Streamlit app
python -m dashml_new.cli build dashboard.dashml --target streamlit --output app.py
streamlit run app.py

# Generate a standalone Plotly HTML dashboard
python -m dashml_new.cli build dashboard.dashml --target plotly --output dashboard.html

# Generate an Observable Plot HTML dashboard
python -m dashml_new.cli build dashboard.dashml --target observable --output dashboard.html

# Create a dashboard directly in Apache Superset
python -m dashml_new.cli build dashboard.dashml --target superset \
  --superset-user admin --superset-password admin
```

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
- **12 chart types** - bar, line, scatter, pie, area, histogram, stacked_bar, grouped_bar, bubble, heatmap, box, geo
- **3 data sources** - CSV, SQL (PostgreSQL/MySQL/SQLite), Google BigQuery
- **4 backends** - Streamlit, Plotly, Observable Plot, Apache Superset
- **6 built-in themes** - Dracula, Nord, Gruvbox, Monokai, One Dark, Solarized Light

## Authors

- Dawid Olejniczak
- Szymon Nowaczyk

## License

MIT
