# Things We'll Branch Over Sooner Or Later

Design decisions and philosophical questions that will need resolution as DashML evolves.

---

## 1. Data Transformation Philosophy

**The Question:** What is DashML's responsibility regarding data transformation?

### Option A: Pure Visualization Tool
**"Shit in, shit out"**

- DashML works with data YOU provide - it only visualizes them
- No data transformation, cleaning, or processing
- User is responsible for providing clean, aggregated data
- DashML just renders what it receives

**Pros:**
- Clear separation of concerns
- Simple, focused tool
- Performance - no processing overhead
- Forces good data engineering practices

**Cons:**
- Users need to preprocess data (SQL views, ETL pipelines)
- Less accessible to non-technical users
- Can't handle raw transactional data elegantly

### Option B: Data Transformation Engine
**"Like Looker" - Transform anything into anything**

- DashML can transform raw data extensively
- Time binning, aggregations, calculations, filtering
- "It can transform the Eiffel Tower out of shit and shit out of the Eiffel Tower"
- Smart SQL generation for database-backed transformations

**Pros:**
- More accessible to non-technical users
- Works with raw data sources
- One tool for both viz and light transformations
- Better UX - just point at raw data

**Cons:**
- Scope creep - becomes a data processing tool
- Performance concerns for large datasets
- Complex code generation
- Blurs the line between viz and ETL

### Current Status:
🟡 **Undecided** - Currently leaning toward A with pragmatic exceptions (like `x_bin` for time series)

### Decision Needed By:
When users start complaining about raw data not looking good in charts (already happening with the "seismograph" time series issue)

---

## 2. [Future decision point - TBD]

...

## 3. [Future decision point - TBD]

...
