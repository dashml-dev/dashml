# DashML Playground

**DashML v0.000000001** - A declarative language for data visualization dashboards

## What is DashML?

DashML is a meta-language that describes data visualizations as abstractions. Like HTML for web pages, DashML provides a unified way to describe dashboards that can be transformed into different platforms (Streamlit, PowerBI, Looker, etc.).

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the standalone demo

```bash
streamlit run app.py
```

### 3. Or see integration example

```bash
streamlit run example_integration.py
```

## Project Structure

```
dashml-playground/
├── dashml/                      # DashML core library
│   ├── __init__.py             # Package exports
│   ├── transformer.py          # Platform-agnostic DashML parser
│   └── streamlit_renderer.py   # Streamlit-specific renderer
├── app.py                       # Standalone Streamlit demo
├── example_integration.py       # Integration example
├── dashml_example.yaml          # Example DashML spec
├── data/
│   └── example.csv              # Sample dataset
└── requirements.txt             # Dependencies
```

## Usage in Your Own Streamlit App

### Simple integration (full dashboard):

```python
from dashml import DashMLTransformer, StreamlitRenderer

transformer = DashMLTransformer("my_dashboard.yaml")
renderer = StreamlitRenderer(transformer)
renderer.render_dashboard()
```

### Advanced integration (specific charts):

```python
from dashml import DashMLTransformer, StreamlitRenderer

transformer = DashMLTransformer("my_dashboard.yaml")
transformer.load_data()
renderer = StreamlitRenderer(transformer)

# Render specific chart by ID
renderer.render_chart_by_id("sales_by_country")
```

See `example_integration.py` for a complete working example.

## DashML Spec Example

```yaml
version: 0.000000001
title: "DashML Example Dashboard"

data:
  type: csv
  path: "data/example.csv"

charts:
  - id: "sales_by_country"
    type: "bar"
    title: "Sales by country"
    x: "country"
    y: "sales"
    agg: "sum"
```

## The DashML Manifesto

1. **Typeless Core** - No rigid schemas, flexible for humans & AI
2. **Non-Validating** - Validation belongs to transformers, not the language
3. **Source-Agnostic** - Works with any data source
4. **Declarative** - Define what, never how
5. **Extensible & Backend-Neutral** - Minimal core, pluggable renderers
6. **LLM & Human-Friendly** - Clean YAML, easy to write & generate
7. **Read-Only** - Visualization only, no data mutation

## Authors

- Dawid Olejniczak
- Szymon Nowaczyk
