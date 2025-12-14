# DashML Architecture

**Date:** 29 November 2025  
**Author:** Dawid Olejniczak  
**Based on:** Architectural Memo (29 Nov 2025)

---

## 🎯 Architectural Style

**Microkernel (Plugin) Architecture** with **Compiler Pipeline**

```
┌───────────────────────────────────────────────────────────┐
│                    DashML CORE                            │
│                  (Microkernel)                            │
│                                                           │
│   .dashml → Parser → AST → IR Builder → IR               │
│                                                           │
│   Responsibilities:                                       │
│   - Parse YAML                                            │
│   - Validate structure                                    │
│   - Build IR (semantic model)                             │
│   - Version management                                    │
│                                                           │
│   NEVER:                                                  │
│   - Loads data                                            │
│   - Executes queries                                      │
│   - Materializes results                                  │
└───────────────────────────────────────────────────────────┘
                            │
                            │ IR (Intermediate Representation)
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ↓                   ↓                   ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Streamlit  │    │    Plotly    │    │    Looker    │
│   Backend    │    │   Backend    │    │   Backend    │
│   (Plugin)   │    │   (Plugin)   │    │   (Plugin)   │
└──────────────┘    └──────────────┘    └──────────────┘
        │                   │                   │
        ↓                   ↓                   ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Generated    │    │ Generated    │    │ Generated    │
│ Python code  │    │ HTML + JSON  │    │ LookML       │
│              │    │ config       │    │              │
│ + Live       │    │              │    │ + Dashboard  │
│ queries      │    │ + Browser    │    │ tiles        │
│              │    │ queries      │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
        │                   │                   │
        ↓                   ↓                   ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Streamlit   │    │   Browser    │    │   Looker     │
│  runtime     │    │   runtime    │    │   runtime    │
│              │    │              │    │              │
│  EXECUTES    │    │  EXECUTES    │    │  EXECUTES    │
│  QUERIES     │    │  QUERIES     │    │  QUERIES     │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## 🧠 Core Principle: DashML NEVER Returns Data

### What DashML Core Does:

✅ Parses `.dashml` YAML files  
✅ Validates semantic correctness  
✅ Builds IR (Intermediate Representation)  
✅ Passes IR to backends  

### What DashML Core NEVER Does:

❌ Loads data from sources  
❌ Executes SQL queries  
❌ Materializes DataFrames  
❌ Passes data rows to backends  
❌ Aggregates or transforms data  

**Why?** DashML is purely semantic. It describes WHAT to query, not the results.

---

## 📊 IR (Intermediate Representation)

The IR is the **heart of DashML** - a backend-neutral logical model.

### IR Contains:

```python
IR(
    version="0.0.1",
    title="My Dashboard",
    datasets={
        "sales": Dataset(
            id="sales",
            type="csv",
            source="data/sales.csv",
            schema={"date": "datetime", "amount": "float"}
        )
    },
    charts=[
        Chart(
            id="sales_by_region",
            type=ChartType.BAR,
            dataset_id="sales",
            x_dimension=Dimension("region", "region", "string"),
            y_measure=Measure("revenue", "amount", AggregationType.SUM),
            filters=[
                Filter("date", "gt", "2025-01-01")
            ]
        )
    ]
)
```

### IR Does NOT Contain:

❌ Actual data rows  
❌ Pandas DataFrames  
❌ SQL result sets  
❌ Materialized aggregations  
❌ Plotly figure objects  

**IR is query semantics, not query results.**

---

## 🔌 Backend Plugins

Each backend is a plugin that:

1. **Reads IR** (semantic specification)
2. **Generates code/config** for its platform
3. **Handles ALL data access** at runtime

### Backend Responsibilities:

| Responsibility | Description |
|----------------|-------------|
| **Code Generation** | Transform IR → platform-specific artifacts |
| **Data Loading** | Execute queries, fetch from sources |
| **Aggregation** | Perform GROUP BY, SUM, COUNT, etc. |
| **Filtering** | Apply WHERE clauses |
| **Rendering** | Create visualizations |

### Backends NEVER Receive:

❌ Pre-loaded data from core  
❌ Materialized DataFrames  
❌ Query results  

---

## 🏗️ Component Architecture

### Core Components

```python
dashml/
├── core/                    # Microkernel
│   ├── __init__.py
│   ├── parser.py           # YAML → AST → IR
│   ├── ir.py               # IR data structures
│   └── compiler.py         # Orchestration
│
├── backends/                # Plugins
│   ├── __init__.py
│   ├── base.py             # Backend interface
│   ├── streamlit_backend.py
│   ├── plotly_backend.py
│   └── looker_backend.py   # Future
```

### Core API

```python
from dashml.core import DashMLCompiler

# Compile .dashml to IR
compiler = DashMLCompiler()
ir = compiler.compile("dashboard.dashml")

# IR contains ONLY semantics, NO data
print(ir.charts[0].y_measure.aggregation)  # AggregationType.SUM
```

### Backend API

```python
from dashml.backends import StreamlitBackend

# Backend reads IR and handles data
backend = StreamlitBackend()
code = backend.generate(ir)  # Generate Python code
backend.execute(ir)           # Run dashboard (loads data)
```

---

## 🔄 Execution Flow

### Design-Time (Development)

```
User edits dashboard.dashml
         ↓
DashML Core compiles to IR
         ↓
Backend generates code
         ↓
Code saved to file or executed
```

### Runtime (Production)

```
User opens dashboard
         ↓
Backend code executes
         ↓
Backend loads data from sources
         ↓
Backend aggregates & filters
         ↓
Backend renders charts
```

**DashML Core is NOT involved at runtime.**

---

## 🔥 Hot Reload

Development mode supports hot reload:

```bash
dashml dev dashboard.dashml
```

**How it works:**

1. Watch `.dashml` file for changes
2. On change → re-compile to IR
3. Re-generate backend code
4. Trigger backend reload (Streamlit auto-reload, browser refresh)

**Key insight:** Hot reload regenerates CODE, not DATA.

---

## 🎯 Why Microkernel?

### Advantages:

| Benefit | Description |
|---------|-------------|
| **Separation of Concerns** | Core = semantics, Backends = execution |
| **Backend Independence** | Add Looker without touching Streamlit code |
| **No Data Coupling** | Core never depends on pandas, SQL, etc. |
| **Pluggable** | New backend = new plugin |
| **Testable** | Test IR generation independently of data |
| **Scalable** | Core stays small and stable |

### Perfect For:

✅ "One language, many runtimes"  
✅ Diverse backend requirements (Streamlit, Looker, React)  
✅ Academic demonstration of clean architecture  
✅ Future extensibility  

---

## 📐 Design Decisions

### 1. No Data in Core

**Decision:** Core never loads or passes data.

**Rationale:**
- Clean separation of concerns
- Backends have full control over data access
- Works with Looker (which expects semantics, not data)
- More efficient (no unnecessary materialization)

### 2. IR as Common Format

**Decision:** All backends consume IR, not .dashml directly.

**Rationale:**
- Single source of truth
- Validation happens once
- Easy to inspect/debug
- Can serialize IR for tooling

### 3. Code Generation

**Decision:** Backends generate code, not runtime interpreters.

**Rationale:**
- Better performance (no interpretation overhead)
- Easier to debug (generated code is readable)
- Works with existing tools (Streamlit, React)
- Hot reload still works (regenerate on change)

### 4. Backend Responsibility for Data

**Decision:** Backends handle ALL data operations.

**Rationale:**
- Streamlit can use SQLAlchemy directly
- Plotly can fetch data in browser
- Looker uses its own engine
- No need for unified data layer

---

## 🚀 Future Extensions

### Planned Backends:

- **Looker** - Generate LookML
- **React** - Generate components + API
- **PowerBI** - Generate PBIX config
- **Observable** - Generate Observable notebooks

### Planned Core Features:

- Schema validation
- Type inference
- Query optimization hints
- Multi-dataset joins
- Calculated fields
- Dashboard templates

---

## 📚 For Your Thesis

### Key Points to Emphasize:

1. **Clean Architecture**
   - Microkernel pattern
   - Plugin system
   - Separation of concerns

2. **Compiler Pipeline**
   - YAML → AST → IR → Backend
   - Similar to LLVM (source → IR → machine code)

3. **Backend Neutrality**
   - IR works for any platform
   - No data coupling

4. **Declarative Paradigm**
   - Describe WHAT, not HOW
   - Backends handle execution

5. **Production Ready**
   - Hot reload
   - Code generation
   - Extensible design

---

## 🎓 Academic Contribution

DashML demonstrates:

✅ **DSL Design** - Proper domain-specific language  
✅ **Compiler Theory** - Frontend/IR/Backend separation  
✅ **Software Architecture** - Microkernel pattern  
✅ **Separation of Concerns** - Semantics vs. execution  
✅ **Pluggable Systems** - Backend plugins  

**Novel aspect:** A dashboard language that compiles to multiple platforms without touching data.

---

## 📖 References

- **Microkernel Architecture**: Tanenbaum, A. S. (1987)
- **LLVM Compiler**: Lattner & Adve (2004)
- **Vega-Lite**: Satyanarayan et al. (2017)
- **LookML**: Looker/Google documentation

---

## ✅ Summary

**DashML is:**
- A semantic declarative language
- Built on microkernel architecture
- Using compiler pipeline (YAML → IR → Backend)
- That never executes queries or materializes data
- Pushing data responsibility to runtime backends
- Supporting hot reload through code regeneration

**Backends:**
- Read IR (semantics only)
- Generate platform-specific code
- Handle ALL data access
- Execute queries at runtime

**This architecture is:**
- ✅ Scalable
- ✅ Backend-agnostic
- ✅ Efficient
- ✅ Clean
- ✅ Future-proof
- ✅ Thesis-worthy

