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

### The Core Question:
**Who is DashML for?**

**Target A: Data Controllers** (Data Engineers/Analysts)
- Have database access, can create views/tables
- Provide clean, pre-processed data to DashML
- DashML = pure visualization layer

**Target B: Data Consumers** (Business users without DB access)
- Get whatever data they're given
- Can't modify source data
- Need tool to handle messy data (dates as strings, etc.)
- DashML = transformation + visualization

**Looker chose B. Should DashML?**

### Dash Studio Discussion (2026-01-04):
- Team is **divided** on this
- Dawid's intuition: "Shit in, shit out" (Option A)
- Counterpoint: "Consumers work with shit" means they need transformation tools (Option B)
- **Semantic confusion:** Does "work with shit" mean "deal with bad output" or "transform bad input"?

### Current Status:
🔴 **Undecided & Divided** - No consensus yet

**We already do transformations:**
```yaml
agg: sum  # Generates GROUP BY x, SUM(y)
```
So we're already on the slope. Question: how far up do we climb?

### Pragmatic Middle Path (Option C?):
- Start with Option A (pure viz)
- Allow **SQL subqueries** in path for power users:
  ```yaml
  data:
    type: sql
    path: "(SELECT DATE(order_date) as date, SUM(revenue) FROM sales GROUP BY DATE(order_date))"
  ```
- This keeps DashML simple but lets users transform via SQL (database does the work)
- Defer "transformation DSL" decision for v2.0

### Decision Needed By:
When users start complaining about raw data not looking good in charts (already happening with the "seismograph" time series issue)

### Impact:
- **Affects:** Spec design, transformer complexity, documentation, target audience
- **Can we defer?** Yes, start with A, evolve to B later (easier than B→A)
- **Risk:** If we start with B, we're committed to maintaining transformation features forever

---

## 2. [Future decision point - TBD]

...

## 3. [Future decision point - TBD]

...
