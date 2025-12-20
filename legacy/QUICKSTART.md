# DashML Quick Start Guide

## 🎯 What You've Built

A complete **declarative dashboard language** with transformers for both Python and JavaScript!

```
        One DashML Spec (YAML)
                 ↓
        ┌────────┴────────┐
        ↓                 ↓
   Python/Streamlit   JavaScript/Plotly
   (Server-side)      (Client-side)
```

---

## 🚀 Test It Right Now

### Option 1: Python/Streamlit (Server-side)

```bash
# Install dependencies (first time only)
pip install -r requirements.txt

# Run standalone demo
streamlit run app.py

# Or run integration example
streamlit run example_integration.py
```

**What you'll see:**
- Interactive dashboard with chart selector
- Data loaded from CSV
- Live Streamlit components

---

### Option 2: JavaScript/Plotly (Client-side)

```bash
# Start local web server
python -m http.server 8000

# Or use Node.js
npx http-server -p 8000
```

**Then open in browser:**
- Standalone: http://localhost:8000/index.html
- Integration: http://localhost:8000/example_integration.html

**What you'll see:**
- Beautiful Plotly charts
- No backend required!
- Tab-based integration example

---

## 📝 The DashML Spec

Here's your `dashml_example.dashml`:

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

  - id: "sales_over_time"
    type: "line"
    title: "Sales over time"
    x: "date"
    y: "sales"
    agg: "sum"
```

**This single file works in BOTH Python and JavaScript!** 🎉

---

## 🔧 How to Modify

### 1. Change the data

Edit `data/example.csv`:

```csv
date,country,sales,product
2025-01-01,Poland,100,Widget
2025-01-01,Germany,50,Gadget
2025-01-02,Poland,80,Widget
```

### 2. Add a new chart

Edit `dashml_example.dashml`:

```yaml
charts:
  - id: "sales_by_product"
    type: "bar"
    title: "Sales by Product"
    x: "product"
    y: "sales"
    agg: "sum"
```

### 3. Refresh

- **Streamlit**: Auto-reloads!
- **Browser**: Reload the page (F5)

---

## 🎓 For Your Thesis Defense

### What This Demonstrates

✅ **Declarative paradigm** - Describe WHAT, not HOW  
✅ **Platform independence** - Same spec → Multiple outputs  
✅ **Modular architecture** - Clean separation (Transformer → Renderer)  
✅ **Production-ready** - Can be imported as library  
✅ **LLM-friendly** - Simple YAML, easy to generate  
✅ **Extensible** - Easy to add new chart types/platforms  

### Key Talking Points

1. **"One spec, multiple platforms"**
   - Show `dashml_example.dashml`
   - Demo in Streamlit
   - Demo in browser
   - Same data, same spec, different renderers!

2. **"Clean architecture"**
   - `DashMLTransformer` = platform-agnostic
   - `StreamlitRenderer` / `PlotlyRenderer` = platform-specific
   - Easy to add `PowerBIRenderer`, `LookerRenderer`, etc.

3. **"Easy integration"**
   - Show `example_integration.py` (tabs)
   - Show `example_integration.html` (embedded)
   - Just a few lines of code!

4. **"LLM-ready"**
   - Simple YAML structure
   - ChatGPT could generate this
   - Show: "Create a DashML spec for sales data..."

---

## 📊 Architecture Diagram

```
┌─────────────────────────────────────────────┐
│         DashML Spec (YAML)                  │
│  Declarative description of dashboard       │
└──────────────────┬──────────────────────────┘
                   │
                   ↓
┌─────────────────────────────────────────────┐
│         DashML Transformer                  │
│  - Load YAML spec                           │
│  - Load data (CSV, SQL, API, etc.)          │
│  - Aggregate data                           │
│  - Platform-agnostic operations             │
└──────────────────┬──────────────────────────┘
                   │
         ┌─────────┴─────────┐
         ↓                   ↓
┌─────────────────┐  ┌─────────────────┐
│  Streamlit      │  │  Plotly.js      │
│  Renderer       │  │  Renderer       │
│  (Python)       │  │  (JavaScript)   │
└─────────────────┘  └─────────────────┘
         │                   │
         ↓                   ↓
┌─────────────────┐  ┌─────────────────┐
│  Streamlit App  │  │  HTML/CSS/JS    │
│  (Server-side)  │  │  (Client-side)  │
└─────────────────┘  └─────────────────┘
```

---

## 🎯 Next Steps

### For Demo
1. ✅ You already have working prototypes!
2. Create more sample dashboards
3. Add more chart types (scatter, pie, etc.)
4. Test with real datasets

### For Thesis
1. Document the architecture (diagrams!)
2. Compare with Vega-Lite, Observable, etc.
3. Performance benchmarks
4. User study (which is easier?)
5. LLM integration demo

---

## 💡 Pro Tips

### Python Development
- Use `@st.cache_data` for performance
- Add error handling for production
- Support more data sources (SQL, API)

### JavaScript Development
- Add loading spinners for better UX
- Support real-time data updates
- Add export features (PDF, PNG)

### Both
- Version your DashML specs in git
- Create a schema validator
- Build a visual editor
- Add more aggregation functions

---

## 🚨 Common Issues

### CORS Errors (JavaScript)
If you get CORS errors loading .dashml/CSV files:
- Always use a local server (not `file://`)
- Run: `python -m http.server 8000`

### Module Not Found (Python)
If imports fail:
- Make sure you're in the right directory
- Check `sys.path` includes `playground/`
- Or install as package: `pip install -e .`

### Charts Not Rendering
- Check browser console (F12)
- Verify DashML syntax (YAML format)
- Check data file paths are correct

---

## 🎉 You're Ready!

You now have:
- ✅ Working Python transformer
- ✅ Working JavaScript transformer  
- ✅ Integration examples for both
- ✅ Complete documentation
- ✅ Thesis-ready architecture

**Show this to your advisor!** 🚀

Good luck with your defense! 🎓

