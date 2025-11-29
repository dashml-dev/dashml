# 🧪 DashML Manual Test Guide

**Complete step-by-step testing of the new microkernel architecture**

---

## ✅ Project is Clean!

All old architecture files moved to `legacy/` folder.  
Only the new compiler architecture remains.

---

## 📋 Prerequisites

```bash
# Make sure you're in the right directory
cd /Users/dawid.olejniczak/code/cdv/dashml/playground

# Check Python version (should be 3.8+)
python3 --version

# Install dependencies
pip install -r requirements.txt
```

---

## 🎯 Test 1: Verify Architecture (5 minutes)

### Step 1.1: Run Test Suite

```bash
python3 test_new_architecture.py
```

**What to expect:**
```
🚀 DashML New Architecture Test Suite
   Testing: Microkernel + Backend Plugins
============================================================

🧪 Testing DashML Compiler...
   ✅ IR generated successfully
   ✅ Title: DashML Example Dashboard
   ✅ Datasets: 1
   ✅ Charts: 2
   ✅ IR contains NO data (semantic only)

🧪 Testing IR Semantics...
   Chart: Sales by country
   Type: bar
   ...

🧪 Testing Core Isolation (NO DATA)...
   ✅ IR serializes to XXX chars
   ✅ Core never loaded data

🧪 Testing Streamlit Backend...
   ✅ Generated XXXX chars of Python code
   ✅ Code includes data loading functions
   📝 Saved to generated_streamlit_app.py

🧪 Testing Plotly Backend...
   ✅ Generated XXXX chars of HTML
   ✅ Browser handles data loading
   📝 Saved to generated_dashboard.html

✅ ALL TESTS PASSED!
```

**If tests pass:** ✅ Architecture is working correctly!

**If tests fail:** Check error message and verify:
- You're in the right directory
- `dashml_example.dashml` exists
- `data/example.csv` exists

---

### Step 1.2: Inspect Generated Files

```bash
# Look at generated Streamlit code
less generated_streamlit_app.py

# Look for these patterns:
# - import streamlit as st
# - import pandas as pd
# - def load_default() - data loading function
# - def render_sales_by_country() - chart rendering
# - pd.read_csv() - backend loads data!
```

Press `q` to quit `less`.

```bash
# Look at generated Plotly HTML
less generated_dashboard.html

# Look for these patterns:
# - const IR = {...} - embedded semantic spec
# - async function loadData() - browser loads data
# - function aggregateData() - browser aggregates
```

**Key insight:** Generated code handles data loading, NOT the core!

---

## 🎯 Test 2: CLI Tools (5 minutes)

### Step 2.1: Validate .dashml File

```bash
python3 dashml_cli.py validate dashml_example.dashml
```

**Expected output:**
```
✅ dashml_example.dashml is valid
```

---

### Step 2.2: Compile to IR (JSON)

```bash
python3 dashml_cli.py compile dashml_example.dashml
```

**Expected output:** JSON representation of IR

**What to look for:**
```json
{
  "version": "0.000000001",
  "title": "DashML Example Dashboard",
  "datasets": {
    "default": {
      "id": "default",
      "type": "csv",
      "source": "data/example.csv",
      ...
    }
  },
  "charts": [
    {
      "id": "sales_by_country",
      "type": "bar",
      "x_dimension": {"column": "country"},
      "y_measure": {
        "column": "sales",
        "aggregation": "sum"
      }
    }
  ]
}
```

**Key observation:** NO actual data in JSON! Only semantics.

---

### Step 2.3: Generate Streamlit Code

```bash
python3 dashml_cli.py generate dashml_example.dashml -b streamlit -o my_app.py
```

**Expected output:**
```
✅ Generated streamlit code → my_app.py
```

**Verify:**
```bash
head -20 my_app.py

# Should see:
# """Auto-generated Streamlit dashboard from DashML"""
# import streamlit as st
# import pandas as pd
# ...
```

---

### Step 2.4: Generate Plotly HTML

```bash
python3 dashml_cli.py generate dashml_example.dashml -b plotly -o my_dashboard.html
```

**Expected output:**
```
✅ Generated plotly code → my_dashboard.html
```

**Verify:**
```bash
grep -c "plotly" my_dashboard.html
# Should return a number > 0
```

---

## 🎯 Test 3: Run Streamlit App (5 minutes)

### Step 3.1: Start Streamlit

```bash
streamlit run app_new.py
```

**Expected:**
- Terminal shows: `You can now view your Streamlit app in your browser.`
- Browser opens automatically at http://localhost:8501

**If browser doesn't open:**
- Manually go to http://localhost:8501

---

### Step 3.2: Interact with App

In the browser:

1. **Check title:** Should say "DashML Example Dashboard"

2. **Sidebar:**
   - Should show "DashML file" input (default: `dashml_example.dashml`)
   - Should show "View IR" expander
   - Should show "Select Chart" dropdown

3. **Click "View IR" in sidebar:**
   - Should show JSON representation
   - Verify NO actual data arrays (only semantic spec)

4. **Select different charts:**
   - Try "sales_by_country"
   - Try "sales_over_time"
   - Charts should render instantly

5. **Observe chart:**
   - Bar chart should show country names on x-axis
   - Values should be aggregated sums
   - Line chart should show dates on x-axis

---

### Step 3.3: Test Hot Reload

**In terminal (keep Streamlit running):**

```bash
# Open another terminal window
# Edit the .dashml file
nano dashml_example.dashml

# Change line 13 from:
    title: "Sales by country"
# To:
    title: "Sales by Country [MODIFIED]"

# Save: Ctrl+O, Enter, Ctrl+X
```

**In browser:**
- Streamlit should show "Source file changed" in top-right
- Click "Rerun"
- Chart title should update to "[MODIFIED]"

**✅ Hot reload works!**

**Stop Streamlit:** Press Ctrl+C in terminal

---

## 🎯 Test 4: Run Plotly Dashboard (5 minutes)

### Step 4.1: Generate HTML

```bash
python3 dashml_cli.py generate dashml_example.dashml -b plotly -o dashboard.html
```

---

### Step 4.2: Start HTTP Server

```bash
python3 -m http.server 8000
```

**Expected output:**
```
Serving HTTP on 0.0.0.0 port 8000 (http://0.0.0.0:8000/) ...
```

---

### Step 4.3: Open in Browser

Open: http://localhost:8000/dashboard.html

**Expected:**
1. **Title:** "DashML Example Dashboard"
2. **Dropdown:** Chart selector
3. **Chart:** Renders below dropdown

---

### Step 4.4: Test Charts

1. **Select "Sales by country"**
   - Bar chart appears
   - Shows aggregated sums by country

2. **Select "Sales over time"**
   - Line chart appears
   - Shows timeline

3. **Open browser console (F12)**
   - No errors
   - Should see: "IR from DashML compiler"

---

### Step 4.5: Verify Data Loading

**In browser console (F12 → Console tab), type:**

```javascript
IR
```

Press Enter.

**You should see:**
- The IR object
- Contains `datasets`, `charts`
- NO actual data rows!

**Then type:**

```javascript
dataCache
```

**You should see:**
- Initially empty: `{}`
- After selecting a chart: `{default: Array(4)}`
- This proves browser loaded data, not core!

**Stop server:** Press Ctrl+C in terminal

---

## 🎯 Test 5: Run Both Together (5 minutes)

### Step 5.1: Run All Script

```bash
./run_all.sh
```

**Expected output:**
```
╔══════════════════════════════════════════════════════════╗
║  🚀 DashML - Running ALL Demos (New Architecture)       ║
╚══════════════════════════════════════════════════════════╝

📊 Generating Plotly dashboard...
✅ Generated plotly code → generated_dashboard.html

🐍 Starting Streamlit app (new architecture)...
🌐 Starting HTTP server for Plotly...

✅ All servers running!

┌─────────────────────────────────────────────────────────┐
│  🐍 Streamlit (New Architecture)                        │
│     → http://localhost:8501                             │
│                                                         │
│  📊 Plotly (Generated from new backend)                 │
│     → http://localhost:8000/generated_dashboard.html    │
│                                                         │
│  🎯 Both use the same .dashml spec!                     │
└─────────────────────────────────────────────────────────┘
```

---

### Step 5.2: Test Both Apps

**Open two browser tabs:**

1. **Tab 1:** http://localhost:8501 (Streamlit)
2. **Tab 2:** http://localhost:8000/generated_dashboard.html (Plotly)

**Verify:**
- ✅ Both show same data
- ✅ Both have same charts
- ✅ Both use same `.dashml` spec
- ✅ Different rendering (Streamlit vs Plotly)

**Stop all:** Press Ctrl+C in terminal

---

## 🎯 Test 6: Code Quality Check (2 minutes)

### Step 6.1: Check No Data in Core

```bash
# Search for data loading in core
grep -r "pd.read_csv" dashml/core/
grep -r "DataFrame" dashml/core/
```

**Expected:** No matches! Core never touches data.

```bash
# Search for data loading in backends
grep -r "pd.read_csv" dashml/backends/
```

**Expected:** Multiple matches! Backends handle data.

---

### Step 6.2: Verify IR Structure

```bash
# Look at IR class
grep -A 10 "class IR" dashml/core/ir.py
```

**Expected:**
```python
class IR:
    """
    DashML Intermediate Representation
    
    ...NEVER contains:
    - Actual data rows
    - DataFrames
    ...
    """
```

---

## 📊 Test Summary Checklist

After completing all tests, you should have verified:

- ✅ Test suite passes
- ✅ Core never loads data (only semantics)
- ✅ Backends handle all data access
- ✅ CLI tools work (validate, compile, generate)
- ✅ Streamlit app runs and renders correctly
- ✅ Plotly dashboard generates and displays
- ✅ Hot reload works
- ✅ Both platforms use same .dashml spec
- ✅ Generated code contains query logic
- ✅ IR contains only semantics (no data)

---

## 🎓 For Your Thesis Defense

### Demo Flow (10 minutes total):

**1. Show the spec (1 min)**
```bash
cat dashml_example.dashml
```
"This is pure semantic description - no data, just WHAT to visualize."

**2. Compile to IR (1 min)**
```bash
python3 dashml_cli.py compile dashml_example.dashml | head -30
```
"The compiler produces IR - notice no data arrays, only semantics."

**3. Run Streamlit (2 min)**
```bash
streamlit run app_new.py
```
"Backend reads IR, loads data, renders charts."

**4. Generate Plotly (2 min)**
```bash
python3 dashml_cli.py generate dashml_example.dashml -b plotly -o demo.html
python3 -m http.server 8000 &
open http://localhost:8000/demo.html
```
"Same spec, different platform - proves backend independence."

**5. Show generated code (2 min)**
```bash
grep "pd.read_csv" generated_streamlit_app.py
```
"Backends load data, not core - clean separation."

**6. Emphasize architecture (2 min)**
- Draw pipeline: `.dashml → Compiler → IR → Backend → Platform`
- Core = microkernel (semantics only)
- Backends = plugins (data + visualization)

---

## ✅ All Tests Complete!

If all tests passed, your DashML implementation is:
- ✅ Architecturally sound (microkernel + plugins)
- ✅ Functionally correct (both platforms work)
- ✅ Clean (core never touches data)
- ✅ Thesis-ready (proper CS patterns)

**Ready for your defense!** 🎓🚀

---

## 🆘 Troubleshooting

### Tests fail with "Module not found"
```bash
pip install -r requirements.txt
```

### Port already in use
```bash
lsof -ti:8501 | xargs kill -9
lsof -ti:8000 | xargs kill -9
```

### Can't find .dashml file
```bash
# Make sure you're in the right directory
pwd
# Should show: .../dashml/playground

ls *.dashml
# Should show: dashml_example.dashml
```

### Browser doesn't open automatically
Just manually go to:
- Streamlit: http://localhost:8501
- Plotly: http://localhost:8000/generated_dashboard.html

