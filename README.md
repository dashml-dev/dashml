# DashML v0.0.1 - Microkernel Architecture

**A declarative dashboard language with proper compiler architecture**

---

## 🎯 What is DashML?

DashML is a **domain-specific language** for describing data dashboards. It uses a **compiler architecture** to transform semantic specifications into runnable code for multiple platforms.

### Key Innovation:

**DashML NEVER touches data.** It describes WHAT to query, not the results.

```
.dashml file (semantics) → IR (pure logic) → Backend (executes queries)
```

---

## 🏗️ Architecture

### Microkernel + Plugins

```
┌─────────────────────────┐
│     DashML Core         │  ← Compiles .dashml → IR
│     (Microkernel)       │  ← NO data access
└───────────┬─────────────┘
            │ IR (semantics only)
            │
    ┌───────┼───────┐
    ↓       ↓       ↓
┌────────┐ ┌────────┐ ┌────────┐
│Streamlit│ │ Plotly │ │ Looker │  ← Execute queries
│ Backend│ │Backend │ │Backend │  ← Load & visualize data
└────────┘ └────────┘ └────────┘
```

---

## ⚡ Quick Start

### 1. Run Everything

```bash
./run_all.sh
```

Opens:
- Streamlit: http://localhost:8501
- Plotly: http://localhost:8000/generated_dashboard.html

### 2. Run Streamlit Only

```bash
streamlit run app_new.py
```

### 3. Generate Plotly Dashboard

```bash
# Generate HTML
python dashml_cli.py generate dashml_example.dashml -b plotly -o dashboard.html

# Serve it
python -m http.server 8000

# Open: http://localhost:8000/dashboard.html
```

### 4. Test the Architecture

```bash
python test_new_architecture.py
```

This will:
- ✅ Compile `dashml_example.dashml` to IR
- ✅ Verify IR contains NO data
- ✅ Generate Streamlit Python code
- ✅ Generate Plotly HTML
- ✅ Prove backends handle data

See `RUNNING.md` for detailed instructions.

---

## 📖 Usage

### Basic Example

```python
from dashml.core import DashMLCompiler
from dashml.backends import StreamlitBackend

# Step 1: Compile .dashml to IR (core never loads data!)
compiler = DashMLCompiler()
ir = compiler.compile("dashboard.dashml")

# Step 2: Pass IR to backend (backend loads and visualizes data)
backend = StreamlitBackend()
backend.execute(ir)
```

### CLI

```bash
# Validate
dashml_cli.py validate dashboard.dashml

# Compile to IR (JSON)
dashml_cli.py compile dashboard.dashml

# Generate code
dashml_cli.py generate dashboard.dashml -b streamlit -o app.py

# Dev mode
dashml_cli.py dev dashboard.dashml
```

---

## 📝 DashML File Format

**File:** `sales_dashboard.dashml`

```yaml
version: 0.0.1
title: "Sales Dashboard"

data:
  type: csv
  path: "data/sales.csv"

charts:
  - id: "sales_by_region"
    type: "bar"
    title: "Sales by Region"
    x: "region"
    y: "amount"
    agg: "sum"
  
  - id: "sales_timeline"
    type: "line"
    title: "Sales Over Time"
    x: "date"
    y: "amount"
    agg: "sum"
```

**This spec describes:**
- ✅ WHERE data comes from (CSV path)
- ✅ WHAT to visualize (dimensions, measures)
- ✅ HOW to aggregate (sum, mean, count)

**It does NOT contain:**
- ❌ Actual data rows
- ❌ Query results
- ❌ Aggregated values

---

## 🧠 Core Concepts

### IR (Intermediate Representation)

Pure semantic model that describes:
- Datasets (WHERE to get data)
- Charts (WHAT to visualize)
- Aggregations (HOW to compute)

**IR never contains actual data.**

### Backends

Plugins that:
1. Read IR
2. Generate platform code
3. Execute queries
4. Load data
5. Render visualizations

**Backends handle ALL data access.**

---

## 🎓 For Your Thesis

This architecture demonstrates:

✅ **Domain-Specific Language Design**
- Formal syntax (.dashml format)
- Semantic validation
- Type system (dimensions, measures)

✅ **Compiler Theory**
- Frontend (parser)
- IR (intermediate representation)
- Backend (code generation)

✅ **Software Architecture**
- Microkernel pattern
- Plugin system
- Separation of concerns

✅ **Clean Architecture**
- Core = semantics
- Backends = execution
- No data coupling

---

## 📚 Documentation

- `ARCHITECTURE.md` - Complete architectural documentation
- `NEW_ARCHITECTURE.md` - Migration guide
- `DASHML_FORMAT.md` - File format specification
- `EDITOR_SETUP.md` - IDE configuration

---

## 🚀 Project Structure

```
dashml-playground/
├── dashml/
│   ├── core/                # Microkernel (NO data)
│   │   ├── parser.py        # YAML → IR
│   │   ├── ir.py            # Semantic model
│   │   └── compiler.py      # Orchestration
│   │
│   └── backends/            # Plugins (ALL data access)
│       ├── base.py
│       ├── streamlit_backend.py
│       └── plotly_backend.py
│
├── dashml_cli.py            # CLI tool
├── dashml_generate.py       # Code generator
├── app_new.py               # Streamlit app (new arch)
├── test_new_architecture.py # Test suite
└── dashml_example.dashml    # Example spec
```

---

## ✨ What Makes This Special?

### 1. No Data Coupling
- Core never touches data
- Works with any data source
- Backends have full control

### 2. Platform Independence
- Same spec → multiple backends
- Write once, deploy anywhere

### 3. Code Generation
- Not runtime interpretation
- Better performance
- Easier debugging

### 4. Hot Reload
- Edit .dashml → instant update
- Regenerates code on change
- Professional DX

### 5. Thesis-Ready Architecture
- Proper compiler design
- Clean patterns
- Well-documented

---

## 🎯 Comparison

| Aspect | DashML | Vega-Lite | Looker | PowerBI |
|--------|--------|-----------|--------|---------|
| **Declarative** | ✅ | ✅ | ✅ | ❌ |
| **Backend-agnostic** | ✅ | ❌ | ❌ | ❌ |
| **No data in spec** | ✅ | ❌ | ✅ | ❌ |
| **Code generation** | ✅ | ❌ | ✅ | ❌ |
| **Open source** | ✅ | ✅ | ❌ | ❌ |
| **File-based** | ✅ | ✅ | ✅ | ❌ |

---

## 🚧 Roadmap

### v0.1
- [x] Core parser & IR
- [x] Streamlit backend
- [x] Plotly backend
- [x] CLI tool
- [x] Code generation
- [ ] Schema validation
- [ ] Type inference

### v0.2
- [ ] Looker backend (LookML)
- [ ] React backend
- [ ] Multi-dataset joins
- [ ] Calculated fields
- [ ] Dashboard templates

### v1.0
- [ ] PowerBI backend
- [ ] Observable backend
- [ ] Query optimization
- [ ] Visual editor
- [ ] Plugin marketplace

---

## 📄 License

Academic project - AGH University of Krakow  
Dawid Olejniczak & Szymon Nowaczyk

---

## 🙏 Acknowledgments

- Inspired by Vega-Lite, LookML, and LLVM
- Built on microkernel architecture principles
- Guided by clean architecture patterns

---

**Built with ❤️ for academic excellence and clean code**

