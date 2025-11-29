# DashML Playground

**DashML v0.000000001** - A declarative language for data visualization dashboards

## What is DashML?

DashML is a meta-language that describes data visualizations as abstractions. Like HTML for web pages, DashML provides a unified way to describe dashboards that can be transformed into different platforms (Streamlit, PowerBI, Looker, etc.).

**One spec, multiple platforms:**
- ✅ Python/Streamlit - Server-side dashboards
- ✅ JavaScript/Plotly - Client-side web dashboards
- 🚧 PowerBI, Looker - Coming soon

## Quick Start

### Option 1: Development with Auto-reload ⚡ (Recommended)

**For JavaScript/Plotly:**
```bash
# Install dependencies
pip install -r requirements.txt

# Start dev server with auto-reload
python watch.py
```

Then open:
- http://localhost:8000/index.html
- http://localhost:8000/example_integration.html

**Edit any `.dashml` file and see changes instantly!** ✨

**For Python/Streamlit:**
```bash
streamlit run app.py
```

Streamlit has auto-reload built-in! Edit `.dashml` files and see instant updates.

---

### Option 2: Simple Static Server

```bash
python -m http.server 8000
# or
npx http-server -p 8000
```

Then open: http://localhost:8000/index.html

_(No auto-reload, manual refresh needed)_

## Project Structure

```
dashml-playground/
├── dashml/                       # Python library
│   ├── __init__.py              # Package exports
│   ├── transformer.py           # Platform-agnostic DashML parser
│   └── streamlit_renderer.py    # Streamlit-specific renderer
├── js/                           # JavaScript library
│   ├── dashml.js                # Platform-agnostic DashML parser
│   └── dashml-plotly.js         # Plotly-specific renderer
├── app.py                        # Streamlit standalone demo
├── example_integration.py        # Streamlit integration example
├── index.html                    # Plotly standalone demo
├── example_integration.html      # Plotly integration example
├── dashml_example.dashml         # Example DashML spec
├── data/
│   └── example.csv               # Sample dataset
├── requirements.txt              # Python dependencies
├── USAGE.md                      # Python integration guide
└── JS_USAGE.md                   # JavaScript integration guide
```

## Usage in Your Own Streamlit App

### Simple integration (full dashboard):

```python
from dashml import DashMLTransformer, StreamlitRenderer

transformer = DashMLTransformer("my_dashboard.dashml")
renderer = StreamlitRenderer(transformer)
renderer.render_dashboard()
```

### Advanced integration (specific charts):

```python
from dashml import DashMLTransformer, StreamlitRenderer

transformer = DashMLTransformer("my_dashboard.dashml")
transformer.load_data()
renderer = StreamlitRenderer(transformer)

# Render specific chart by ID
renderer.render_chart_by_id("sales_by_country")
```

See `example_integration.py` for a complete working example.

### JavaScript Usage

```javascript
// Simple full dashboard
const transformer = await DashMLTransformer.fromYAML('dashboard.dashml');
const renderer = new DashMLPlotlyRenderer(transformer);
await renderer.renderDashboard({ containerId: 'my-div' });

// Specific charts
const transformer = await DashMLTransformer.fromYAML('dashboard.dashml');
await transformer.loadData();
const renderer = new DashMLPlotlyRenderer(transformer);
renderer.renderChartById('sales_by_country', 'chart1');
```

See `example_integration.html` for a complete working example.

## DashML Spec Example

**File: `dashboard.dashml`**

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

**Note:** `.dashml` files use YAML syntax under the hood, making them both human and machine-readable.

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
