# DashML Integration Guide

## 🎯 Philosophy

DashML is designed to be **pluggable**. The transformer and renderer are completely separate, making it easy to:
- Embed DashML dashboards into existing apps
- Render specific charts where you need them
- Switch between different rendering backends (Streamlit today, PowerBI tomorrow)

---

## 📦 Architecture

```
┌─────────────────────────────────────────┐
│         DashML Spec (YAML)              │
│  "What to visualize" - declarative      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      DashMLTransformer                  │
│  Platform-agnostic parser & data loader │
└──────────────┬──────────────────────────┘
               │
               ├─────────────┬─────────────┬──────────────┐
               ▼             ▼             ▼              ▼
       ┌──────────────┐ ┌─────────┐  ┌─────────┐  ┌──────────┐
       │  Streamlit   │ │ PowerBI │  │ Looker  │  │   HTML   │
       │   Renderer   │ │ Renderer│  │ Renderer│  │ Renderer │
       └──────────────┘ └─────────┘  └─────────┘  └──────────┘
```

---

## 🚀 Integration Examples

### Example 1: Full Dashboard (Simplest)

```python
import streamlit as st
from dashml import DashMLTransformer, StreamlitRenderer

st.title("My App")

transformer = DashMLTransformer("dashboard.dashml")
renderer = StreamlitRenderer(transformer)
renderer.render_dashboard()
```

---

### Example 2: Dashboard in a Tab

```python
import streamlit as st
from dashml import DashMLTransformer, StreamlitRenderer

tab1, tab2 = st.tabs(["My App", "Analytics"])

with tab1:
    st.write("Your existing app content...")

with tab2:
    transformer = DashMLTransformer("analytics.dashml")
    renderer = StreamlitRenderer(transformer)
    renderer.render_dashboard(show_title=False)
```

---

### Example 3: Specific Charts Only

```python
import streamlit as st
from dashml import DashMLTransformer, StreamlitRenderer

st.title("Sales Dashboard")

transformer = DashMLTransformer("sales.dashml")
transformer.load_data()  # Load once
renderer = StreamlitRenderer(transformer)

col1, col2 = st.columns(2)

with col1:
    st.subheader("By Region")
    renderer.render_chart_by_id("sales_by_region")

with col2:
    st.subheader("Over Time")
    renderer.render_chart_by_id("sales_timeline")
```

---

### Example 4: Multiple DashML Files

```python
import streamlit as st
from dashml import DashMLTransformer, StreamlitRenderer

st.sidebar.selectbox("Department", ["Sales", "Marketing", "Operations"])

if department == "Sales":
    transformer = DashMLTransformer("dashboards/sales.dashml")
elif department == "Marketing":
    transformer = DashMLTransformer("dashboards/marketing.dashml")
else:
    transformer = DashMLTransformer("dashboards/operations.dashml")

renderer = StreamlitRenderer(transformer)
renderer.render_dashboard()
```

---

### Example 5: Custom Layout with DashML Charts

```python
import streamlit as st
from dashml import DashMLTransformer, StreamlitRenderer

st.title("Executive Dashboard")

# Your custom metrics
col1, col2, col3 = st.columns(3)
col1.metric("Revenue", "$1.2M")
col2.metric("Users", "8.2K")
col3.metric("Growth", "+12%")

st.divider()

# DashML charts
transformer = DashMLTransformer("executive.dashml")
transformer.load_data()
renderer = StreamlitRenderer(transformer)

for chart_def in transformer.get_charts():
    st.subheader(chart_def["title"])
    renderer.render_chart(chart_def)
```

---

## 🔧 API Reference

### `DashMLTransformer`

**Platform-agnostic transformer**

```python
transformer = DashMLTransformer(dashml_path: str)

# Methods:
transformer.load_data() -> pd.DataFrame
transformer.get_title() -> str
transformer.get_charts() -> List[Dict]
transformer.get_chart_by_id(chart_id: str) -> Dict
transformer.aggregate_data(x: str, y: str, agg: str) -> pd.DataFrame
```

### `StreamlitRenderer`

**Streamlit-specific renderer**

```python
renderer = StreamlitRenderer(transformer: DashMLTransformer)

# Methods:
renderer.render_dashboard(
    show_title: bool = True,
    show_sidebar: bool = True,
    selected_chart_id: Optional[str] = None
)

renderer.render_chart(chart: Dict)
renderer.render_chart_by_id(chart_id: str)
```

---

## 💡 Best Practices

1. **Separate concerns**: Keep DashML specs in a `dashboards/` folder
2. **Reuse transformers**: Load data once, render multiple charts
3. **Error handling**: Wrap in try/except for production apps
4. **Caching**: Use `@st.cache_data` for expensive data loads
5. **Version control**: Track your `.yaml` specs in git

---

## 🎓 For Your Thesis

This architecture demonstrates:

✅ **Separation of concerns** (spec vs. transformer vs. renderer)  
✅ **Platform independence** (same spec, different renderers)  
✅ **Extensibility** (easy to add new chart types or renderers)  
✅ **Declarative paradigm** (describe what, not how)  
✅ **Production-ready** (can be imported as a library)

Perfect for arguing that DashML is a proper DSL with clean architecture! 🚀

