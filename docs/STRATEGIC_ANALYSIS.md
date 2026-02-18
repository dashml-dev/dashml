# DashML Strategic Analysis: What to Change Beyond Adding Charts

## Context

DashML aims to be an **open standard for BI-as-code** — a declarative YAML DSL that compiles to multiple dashboard backends. The architecture (hexagonal/microkernel) is locked in. The question: what needs to change *structurally* to reach that goal, beyond adding new chart types?

After a full codebase review (~7,300 lines across core + transformers), here's the honest assessment.

---

## What Works Well

**1. The core architectural bet is right.** The `YAML -> Parser -> Validator -> Transformer -> Generated Code` pipeline is clean, the separation between semantic core and code-generating transformers is properly enforced, and the "core never touches data" principle holds throughout. This is a strong foundation.

**2. Generated code quality is high.** The Streamlit/BigQuery output is genuinely production-quality — proper caching, type inference, Altair encoding. Someone could read the generated code and understand it. This is a major differentiator vs tools that produce opaque bundles.

**3. The DSL is LLM-friendly.** YAML is easy for both humans and AI to read/write. The spec format is flat and predictable. An LLM could generate a `.dashml` file from a natural language request with high reliability.

**4. TypedDict over dataclasses** was the right call — zero runtime overhead, IDE support, and dict passthrough means the core stays simple.

**5. Multi-backend from day one.** Four working backends (Streamlit, Plotly, Observable, Superset) prove the abstraction works.

---

## What Needs to Change (Beyond New Charts)

### 1. The DSL is Chart-Only — Real Dashboards Need More Primitives

**The biggest gap.** Currently the spec can only describe charts. But real BI dashboards are composed of:

- **KPI cards / scalar metrics** — "Total Revenue: $1.2M" with trend arrow
- **Text/markdown blocks** — section headers, explanations, methodology notes
- **Dashboard-level filters** — "Filter all charts by date range" (currently filters are per-chart only)
- **Calculated fields** — `profit = revenue - cost` (currently can only reference raw columns)
- **Layout hints** — 2-column vs 3-column, chart sizing

Without these, DashML can only produce chart galleries, not dashboards. This is the #1 thing keeping it from being a serious BI standard.

**Proposed DSL evolution:**
```yaml
# KPI cards as a widget type alongside charts
widgets:
  - id: "total_revenue"
    type: "metric"
    title: "Total Revenue"
    value: "revenue"
    agg: "sum"
    format: "$,.0f"

# Dashboard-level filters (apply to all charts)
filters:
  - field: "date"
    type: "date_range"
    default: "last_30_days"
  - field: "country"
    type: "select"

# Calculated fields
derived_fields:
  - name: "profit"
    expression: "{revenue} - {cost}"

# Layout hints
layout:
  columns: 3
```

### 2. The Transformer Contract is Broken by Superset

The `build()` method's contract is: take a spec, return generated code as a string. Three transformers follow this. Superset breaks it — it makes live API calls during `build()`, creating databases, datasets, and charts directly.

This means:
- Superset `build()` has **side effects** — it's not a pure transformation
- It can't be dry-run, tested, or previewed
- Partial failures leave Superset in an inconsistent state
- It violates the "core never touches data" principle at the transformer level

**Fix:** Superset should return a deployment manifest (JSON/YAML) that a separate `deploy` CLI command executes. Same pattern as Terraform: `plan` then `apply`.

### 3. Massive Code Duplication Across Transformers (~300+ lines)

The Flask backend code for SQL and BigQuery is copy-pasted across Plotly and Observable (and partially in Streamlit). Each transformer independently generates:
- Flask app boilerplate
- BigQuery data loading + type inference
- SQL schema introspection
- Date/type serialization

This isn't just tech debt — it means bug fixes need to be applied 3 times, and new data source types would need to be added in 3 places.

**Fix:** Extract shared backend code into `dashml_new/backends/`:
```
backends/
  flask_csv.py      # CSV data loading template
  flask_sql.py      # SQL + SQLAlchemy template
  flask_bigquery.py # BigQuery client template
```
Transformers import and compose these. The frontend (Plotly.js vs Observable Plot) stays in the transformer; the backend becomes shared.

### 4. Data Source Model is Too Simple for Real BI

Currently: one `data` block -> one table. Real dashboards need:
- **Multiple data sources** — sales table + customer table
- **Joins** — at minimum, reference relationships between tables
- **Per-chart data overrides** — most charts use the same source, but some need a different one

This doesn't mean DashML should become a query engine. But the spec needs to express *which data goes where*, even if the generated code handles the actual loading.

**Proposed evolution:**
```yaml
data:
  sources:
    - id: "orders"
      type: bigquery
      path: gold.orders
    - id: "customers"
      type: bigquery
      path: gold.customers

charts:
  - id: "revenue_by_region"
    source: "orders"      # explicit binding
    type: bar
    x: region
    y: revenue
    agg: sum
```

### 5. No Package Installation / No Entry Point

There's no `pyproject.toml` or `setup.py`. DashML can't be `pip install`-ed, can't be imported as a library, and the CLI only works when run from the project root directory. For an open standard, this is a hard blocker.

**What's needed:**
- `pyproject.toml` with metadata, entry points, and optional dependency groups (`[sql]`, `[bigquery]`, `[dev]`)
- Entry point: `dashml = dashml_new.cli:main` so users get a `dashml` command
- Optional deps: core only needs `pyyaml`; backends pull in their own deps

### 6. Test Coverage is Minimal

`test_new_architecture.py` (215 lines, 5 test functions) only tests:
- Basic IR generation
- Streamlit output structure
- Plotly output structure
- Core isolation principle

**Not tested at all:**
- Validator (337 lines, zero tests) — the most critical component
- CLI argument parsing and error paths
- Filter/sort/limit in generated code
- Multi-page dashboard generation
- SQL and BigQuery code generation
- Style/theme loading
- Edge cases (empty data, missing columns, special characters)

For an open standard, the validator needs near-100% coverage. Users need to trust that a valid spec will always produce correct output.

### 7. Version Strategy is Missing

`version: 0.000000001` signals "not ready" but there's no plan for what version numbers mean. An open standard needs:
- Semantic versioning for the spec format (separate from the tool version)
- A deprecation policy (how long do old spec versions remain supported?)
- A migration path (can you auto-upgrade a v1 spec to v2?)

### 8. The Registry Creates Temporary Instances

`TransformerRegistry.register()` instantiates the class just to read its `name` property, then throws the instance away. `name` should be a class attribute, not an instance property. Minor, but symptomatic of the broader pattern where the plugin system works but isn't designed for external contributors.

---

## Prioritized Recommendations

### Tier 0: Foundational (do before anything else)
1. **Add `pyproject.toml`** — make it installable, define `dashml` CLI entry point
2. **Test the validator** — it's the gatekeeper; untested gatekeeper = unreliable standard
3. **Extract shared Flask backends** — stop the duplication before it gets worse

### Tier 1: DSL Evolution (the real differentiators)
4. **Add `metric` widget type** — KPI cards are the single most-requested BI element
5. **Add dashboard-level `filters`** — cross-chart filtering is table-stakes
6. **Add `derived_fields`** — calculated columns unlock 80% of real analytics
7. **Add `text`/`markdown` widget type** — dashboards need narrative

### Tier 2: Architecture Hardening
8. **Fix Superset transformer** — separate `plan` from `apply`
9. **Support multiple data sources** — `data.sources[]` with per-chart binding
10. **Spec versioning strategy** — define what version numbers mean, add migration tooling

### Tier 3: Open Standard Readiness
11. **Contributor docs** — how to build a transformer, how to extend the DSL
12. **JSON Schema kept in sync** — currently it doesn't enforce conditional requirements (bubble needs size, etc.)
13. **CI/CD pipeline** — tests, linting, type checking on every PR

---

## What I Would NOT Change

- **The hexagonal architecture** — it's working. Keep it.
- **TypedDict approach** — right tradeoff for a compiler
- **YAML as the DSL format** — LLM-friendly, human-readable, right choice
- **Code generation over runtime** — the "readable generated code" philosophy is a genuine differentiator
- **The 4-backend strategy** — proves universality, keep them all
