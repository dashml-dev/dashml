# DashML Playground

**DashML** - A declarative language for data visualization dashboards that compiles to multiple platforms.

## ⚠️ Active Development

This repository contains both the **legacy runtime architecture** and the **new compiler architecture**.

### Current Implementation: `dashml_new/` ✅

The active implementation is in the `dashml_new/` directory. This is a **build-time compiler** that generates standalone code.

**Documentation:**
- **[Main README](dashml_new/README.md)** - Complete guide to DashML
- **[Chart Types Roadmap](dashml_new/CHART_TYPES_ROADMAP.md)** - Supported chart types and future plans
- **[TypedDict Architecture](dashml_new/TYPEDDICT_IR.md)** - Type system design

**Quick Start:**
```bash
cd dashml_new

# Generate Streamlit app
python -m dashml_new.cli dashboard.dashml --backend streamlit --output app.py
streamlit run app.py

# Generate Plotly HTML
python -m dashml_new.cli dashboard.dashml --backend plotly --output dashboard.html

# Generate Observable Plot HTML
python -m dashml_new.cli dashboard.dashml --backend observable --output dashboard.html
```

### Legacy Implementation: Root Directory ⚠️ Deprecated

The files in the playground root (`dashml/`, `js/`, `app.py`, `index.html`, etc.) are from the **old runtime architecture** and are no longer actively developed.

**Old approach**: Runtime interpreter that materializes data
**New approach**: Build-time compiler that generates standalone code

## What is DashML?

DashML is a declarative language for defining analytics dashboards. Write your dashboard spec once in `.dashml` format, then compile it to:

- **Streamlit** (Python) - Interactive data apps
- **Plotly** (HTML/JS) - Standalone web dashboards
- **Observable Plot** (HTML/JS) - Modern web visualizations

### Example Spec

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
```

Compile to Streamlit:
```bash
python -m dashml_new.cli dashboard.dashml --backend streamlit --output app.py
```

## Supported Features

- ✅ **8 chart types**: bar, line, scatter, pie, area, histogram, stacked_bar, grouped_bar
- ✅ **Multi-page dashboards**: Organize charts into pages
- ✅ **Theme system**: 6 built-in themes (Dracula, Nord, Gruvbox, etc.)
- ✅ **3 backends**: Streamlit, Plotly, Observable Plot
- ✅ **CSV data sources**: Load data from CSV files
- ✅ **Aggregations**: sum, mean, count

## Documentation

All current documentation is in `dashml_new/`:

1. **[README.md](dashml_new/README.md)** - Complete user guide
2. **[CHART_TYPES_ROADMAP.md](dashml_new/CHART_TYPES_ROADMAP.md)** - Chart implementation status
3. **[TYPEDDICT_IR.md](dashml_new/TYPEDDICT_IR.md)** - Architecture details

## Architecture

DashML follows **hexagonal architecture** principles:

```
.dashml spec → Parser → Validator → Transformer → Generated Code
                                         ↓
                            ┌────────────┼────────────┐
                            ↓            ↓            ↓
                        Streamlit    Plotly    Observable
```

**Key principle**: DashML never materializes data. It only generates code that will load data at runtime.

## Authors

- Dawid Olejniczak
- Szymon Nowaczyk

## License

MIT
