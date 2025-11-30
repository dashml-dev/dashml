# DashML - New Architecture

This is the refactored DashML implementation following hexagonal architecture principles.

## Architecture

```
dashml_new/
├── core/
│   ├── engine.py          # Main orchestrator
│   ├── parser.py          # YAML → dict parser
│   ├── validator.py       # Semantic validation
│   └── __init__.py
│
├── transformers/
│   ├── base.py           # Abstract Transformer interface
│   ├── registry.py       # Plugin system
│   ├── streamlit.py      # Streamlit code generator
│   ├── plotly.py         # Plotly HTML generator
│   └── __init__.py
│
├── cli.py                # Command-line interface
└── __init__.py
```

## Key Principles

1. **Hexagonal Architecture**: Core engine is isolated from transformers via clean interfaces
2. **No IR**: Spec is just a Python dict from YAML
3. **No Data Materialization**: Engine never fetches data, only validates structure
4. **Code Generation**: Transformers generate standalone code that fetches its own data

## Usage

### CLI

```bash
# List available transformers
python cli.py list

# Generate Streamlit app
python cli.py build ../dashml_example.dashml --target streamlit --output app.py

# Generate Plotly HTML
python cli.py build ../dashml_example.dashml --target plotly --output dashboard.html
```

### Programmatic

```python
from core import DashMLEngine
from transformers import TransformerRegistry
from transformers.streamlit import StreamlitTransformer

# Register transformer
TransformerRegistry.register(StreamlitTransformer)

# Load spec
engine = DashMLEngine()
spec = engine.load("dashboard.dashml")

# Generate code
transformer = TransformerRegistry.get("streamlit")
code = transformer.build(spec)

# Save or use code
with open("app.py", "w") as f:
    f.write(code)
```

## Creating Custom Transformers

```python
from transformers.base import Transformer

class MyTransformer(Transformer):
    @property
    def name(self) -> str:
        return "my-platform"

    @property
    def description(self) -> str:
        return "Generates code for MyPlatform"

    def build(self, spec: dict) -> str:
        # Generate code from spec
        title = spec["title"]
        charts = spec["charts"]

        # Build your platform-specific code
        code = f"# Generated code for {title}\n"
        # ... more code generation

        return code

# Register it
TransformerRegistry.register(MyTransformer)
```

## How It Works

### 1. Engine Loads Spec (Semantic Only)

```python
# engine.py
spec = yaml.safe_load(open("dashboard.dashml"))
validator.validate(spec)
# spec = {"data": {"type": "csv", "path": "data.csv"}, ...}
```

**Engine never touches the actual data file!**

### 2. Transformer Generates Code

```python
# streamlit.py
def build(self, spec: dict) -> str:
    code = f'''
import pandas as pd
import streamlit as st

df = pd.read_csv("{spec['data']['path']}")  # Generated code loads data
grouped = df.groupby("{chart['x']}")["{chart['y']}"].sum()
st.bar_chart(grouped)
'''
    return code
```

### 3. Generated Code Runs Standalone

```python
# app.py (generated)
import pandas as pd
import streamlit as st

df = pd.read_csv("data/example.csv")  # THIS loads data, not DashML!
grouped = df.groupby("country")["sales"].sum()
st.bar_chart(grouped)
```

## Testing

Run the test script:

```bash
python test_new_architecture.py
```

This will:
1. Load `dashml_example.dashml`
2. Generate Streamlit code → `generated_streamlit_app.py`
3. Generate Plotly HTML → `generated_plotly_dashboard.html`

## Differences from Old Architecture

### Old (Runtime Interpreter)

```python
# app.py imports DashMLTransformer
transformer = DashMLTransformer("spec.dashml")
transformer.load_data()  # ← DashML loads data at runtime!
renderer = StreamlitRenderer(transformer)
renderer.render_dashboard()
```

**Problem**: DashML materializes data, tight coupling, not truly declarative

### New (Build-time Code Generator)

```bash
# Build time
dashml build spec.dashml --target streamlit --output app.py

# Run time
streamlit run app.py  # Generated code loads its own data
```

**Better**: DashML is just a blueprint, generated code is independent

## Migration Path

To migrate from old to new:

1. Keep old `dashml/` package for backward compatibility
2. New projects use `dashml_new/`
3. Eventually rename `dashml_new/` → `dashml/` in v2.0

## Future Transformers

- `LookerTransformer` - Generates LookML
- `PowerBITransformer` - Generates Power BI JSON/DAX
- `TableauTransformer` - Generates Tableau workbook XML
- `GrafanaTransformer` - Generates Grafana dashboard JSON
