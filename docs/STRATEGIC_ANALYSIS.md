# DashML Strategic Analysis: What to Change Beyond Adding Charts

## Context

DashML aims to be an **open standard for BI-as-code** — a declarative YAML DSL that compiles to multiple dashboard backends. The architecture (hexagonal/microkernel) is locked in. The question: what needs to change *structurally* to reach that goal, beyond adding new chart types?

After a full codebase review (~7,300 lines across core + transformers), here's the honest assessment.

---

## What Works Well

**1. The compilation model is the right bet.** Compiling a YAML spec into standalone generated code (rather than interpreting at runtime) is the correct choice for BI-as-code. The generated `.py` or `.html` runs without DashML installed — you can read it, debug it, modify it, check it into git. Tools like Metabase or Looker produce opaque runtime artifacts. DashML produces code. That's a genuine differentiator. Similarly, "core never touches data" is the right boundary — a spec compiler has no business opening database connections.

**2. Generated code quality is high.** The Streamlit/BigQuery output is genuinely production-quality — proper caching, type inference, Altair encoding. Someone could read the generated code and understand it.

**3. The DSL is LLM-friendly.** YAML is easy for both humans and AI to read/write. The spec format is flat and predictable. An LLM could generate a `.dashml` file from a natural language request with high reliability.

**4. TypedDict over dataclasses** was the right call — zero runtime overhead, IDE support, and dict passthrough means the core stays simple.

**5. Multi-backend from day one.** Four working backends (Streamlit, Plotly, Observable, Superset) prove the multi-target abstraction is viable.

---

## What Needs to Change (Beyond New Charts)

### 1. The Pipeline is Too Thin — Transformers Do All the Work

The CLAUDE.md describes the architecture as "hexagonal / microkernel." In practice, it's a thin linear pipeline where the core barely does anything:

- `parser.py` — 44 lines, literally just `yaml.safe_load`
- `validator.py` — 337 lines of structural checks
- `engine.py` — 54 lines that calls parser then validator

All the real work — path parsing, type inference, legacy field resolution, aggregation logic, data source handling — happens inside each transformer independently. This is why `plotly.py` is 2,400 lines: it's not just generating Plotly code, it's also resolving SQL paths, detecting date types, building Flask backends, and handling BigQuery auth. Every transformer repeats this.

The consequence: adding a new data source means changing all 4 transformers. Adding a new chart type means changing all 4 transformers. This is the root cause of the ~300+ lines of duplication across backends, and it will get worse with every new feature.

**What's missing is a normalizer/IR layer between validation and code generation:**

```
.dashml YAML
  -> Parser (YAML -> raw dict)                    # exists, fine
  -> Validator (structural checks)                # exists, fine
  -> Normalizer (NEW: resolve legacy fields,      # MISSING
                 parse paths, infer types,
                 resolve chart requirements
                 -> normalized IR)
  -> Backend (receives clean IR, only does        # currently overloaded
             platform-specific output)
```

The normalizer would resolve legacy `schema`+`table_name` -> `path` once, parse SQL paths once, normalize chart requirements (bubble needs size, stacked needs group) into explicit fields once, and hand backends a fully-resolved spec. Backends would shrink dramatically and only contain platform-specific code generation.

This also means data source adapters (CSV, SQL, BigQuery) and rendering adapters (Streamlit, Plotly, Observable) become **separate concerns** instead of being multiplied together inside each transformer.

### 2. The DSL is Chart-Only — Real Dashboards Need More Primitives

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

### 3. The Transformer Contract is Broken by Superset

The `build()` method's contract is: take a spec, return generated code as a string. Three transformers follow this. Superset breaks it — it makes live API calls during `build()`, creating databases, datasets, and charts directly.

This means:
- Superset `build()` has **side effects** — it's not a pure transformation
- It can't be dry-run, tested, or previewed
- Partial failures leave Superset in an inconsistent state
- It violates the "core never touches data" principle at the transformer level

**Fix:** Superset should return a deployment manifest (JSON/YAML) that a separate `deploy` CLI command executes. Same pattern as Terraform: `plan` then `apply`.

### 4. Massive Code Duplication Across Transformers (~300+ lines)

A symptom of problem #1. The Flask backend code for SQL and BigQuery is copy-pasted across Plotly and Observable (and partially in Streamlit). Each transformer independently generates Flask app boilerplate, BigQuery data loading + type inference, SQL schema introspection, and date/type serialization.

This gets solved naturally by the normalizer/IR layer — data source handling moves out of transformers entirely. In the interim, extracting shared backend code into `dashml_new/backends/` would reduce the duplication.

### 5. Data Source Model is Too Simple for Real BI

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

### 6. No Package Installation / No Entry Point

There's no `pyproject.toml` or `setup.py`. DashML can't be `pip install`-ed, can't be imported as a library, and the CLI only works when run from the project root directory. For an open standard, this is a hard blocker.

**What's needed:**
- `pyproject.toml` with metadata, entry points, and optional dependency groups (`[sql]`, `[bigquery]`, `[dev]`)
- Entry point: `dashml = dashml_new.cli:main` so users get a `dashml` command
- Optional deps: core only needs `pyyaml`; backends pull in their own deps

### 7. Test Coverage is Minimal

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

### 8. Version Strategy is Missing

`version: 0.000000001` signals "not ready" but there's no plan for what version numbers mean. An open standard needs:
- Semantic versioning for the spec format (separate from the tool version)
- A deprecation policy (how long do old spec versions remain supported?)
- A migration path (can you auto-upgrade a v1 spec to v2?)

### 9. The Registry Creates Temporary Instances

`TransformerRegistry.register()` instantiates the class just to read its `name` property, then throws the instance away. `name` should be a class attribute, not an instance property. Minor, but symptomatic of the broader pattern where the plugin system works but isn't designed for external contributors.

---

## Prioritized Recommendations

### Tier 0: Architecture (do before anything else)

#### 1. Build the normalizer/IR layer

This is the root cause of transformer bloat and duplication. Add a pipeline step between validator and backends that produces a fully-resolved intermediate representation. Transformers currently receive the raw YAML dict and each independently does the same normalization work. After this change, they receive a clean IR and only do platform-specific code generation.

**New file: `dashml_new/core/normalizer.py`**

**New pipeline:**
```
engine.load(path)
  -> parser.parse(path)       -> raw dict
  -> validator.validate(dict)  -> validated dict (unchanged)
  -> normalizer.normalize(dict, source_file) -> NormalizedSpec  <- NEW
  -> returned to CLI, passed to transformer.build(NormalizedSpec)
```

**What the normalizer does (each item is logic currently duplicated across 3-4 transformers):**

| Responsibility | Currently lives in | Move to normalizer |
|---|---|---|
| Parse SQL `schema.table` or `[schema].[table]` paths | `base.py:133-160`, called from streamlit:209, plotly:1647, observable:1210, superset:402 (superset has its own copy) | `normalizer.py` resolves once, stores `sql_schema` + `sql_table` in IR |
| Parse BigQuery `dataset.table` paths | streamlit:264, plotly:189, observable:1336, superset:247 (each does `path.split(".")`) | `normalizer.py` resolves once, stores `bq_dataset` + `bq_table` in IR |
| Resolve legacy `schema`+`table_name` -> `path` | streamlit:208-213, plotly:1646-1651, observable:1209-1214, superset:211-218 (identical 4x) | `normalizer.py` resolves once; IR always has `path` |
| Wrap single-page `charts` into `pages` | streamlit:93-96, plotly:87+109, observable:85+103, superset:270+295 (checked 6+ times) | `normalizer.py` always produces `pages[]`; backends never check |
| Load style config + merge defaults | `base.py:108-131`, plotly:325-352 has custom `_load_colors()`, each transformer defines different defaults | `normalizer.py` loads `.dmls`, resolves path relative to source file, merges with standard defaults, stores resolved `StyleColors` in IR |
| Classify chart type (needs aggregation vs raw data) | constants.py defines `CHARTS_NEED_AGGREGATION`/`CHARTS_USE_RAW_DATA`, each transformer checks at render time | `normalizer.py` annotates each chart with `needs_aggregation: bool`, `uses_raw_data: bool` |
| Store db_config | `set_db_config()` is identical in streamlit:28-33, plotly:29-35, observable:29-35, superset:123-136 | `db_config` becomes part of the IR context passed to `build()`, not stored on transformer instance |

**New types in `core/types.py`:**

```python
class NormalizedDataSource(TypedDict):
    type: str                    # "csv" | "sql" | "bigquery"
    path: str                    # original path string
    # Pre-parsed components (always populated by normalizer):
    csv_path: str                # for CSV: resolved file path
    sql_schema: str              # for SQL: parsed schema name
    sql_table: str               # for SQL: parsed table name
    bq_dataset: str              # for BigQuery: parsed dataset
    bq_table: str                # for BigQuery: parsed table

class NormalizedChart(TypedDict, total=False):
    id: str
    type: str
    title: str
    x: str
    y: str
    agg: str
    group: str
    size: str
    x_type: str
    y_type: str
    bins: int
    filters: List[FilterSpec]
    sort: str
    sort_order: str              # default "asc" resolved
    limit: int
    # Normalizer-added fields:
    needs_aggregation: bool      # from CHARTS_NEED_AGGREGATION
    uses_raw_data: bool          # from CHARTS_USE_RAW_DATA

class NormalizedPage(TypedDict):
    id: str
    title: str
    description: str
    charts: List[NormalizedChart]

class ResolvedStyle(TypedDict):
    background: str
    card: str
    primary: str
    text: str
    buttons: str
    secondary: List[str]

class NormalizedSpec(TypedDict):
    version: str                 # always coerced to string
    title: str
    data: NormalizedDataSource
    pages: List[NormalizedPage]  # always pages, even for single-page
    style: ResolvedStyle         # loaded and merged, not a file path
    db_config: Dict[str, Any]    # database config (from CLI args)
    source_file: str             # path to the .dashml file
```

**What changes in transformers after this:**

- `base.py`: Remove `_parse_sql_path()` and `_load_style_config()` — normalizer handles both
- `base.py`: Remove `set_db_config()` — db_config is in the IR
- `base.py`: `build()` signature changes from `build(spec: DashMLSpec)` to `build(spec: NormalizedSpec)`
- Each transformer: Remove all `if "pages" in spec` / `spec.get("charts", [])` branching — IR always has `pages`
- Each transformer: Remove all legacy field resolution — IR always has `path` with pre-parsed components
- Each transformer: Remove `_load_colors()` wrappers — IR has resolved `style`
- Each transformer: Remove `db_config` instance variable and `set_db_config()` method
- Plotly/Observable: Data source branching (`_build_csv_version` vs `_build_sql_version` vs `_build_bigquery_version`) can be simplified since paths are pre-parsed, but the branching itself stays (each generates different code)

**What does NOT move to the normalizer:**

- Actual code generation (stays in transformers — platform-specific)
- Data source branching for code generation (transformers still need to generate different code for CSV vs SQL vs BigQuery, but they work with pre-parsed paths)
- Chart rendering logic (each backend has its own charting library)
- Date type inference from actual data (stays in generated code — needs runtime data)

#### 2. Add `pyproject.toml`
Make it installable, define `dashml` CLI entry point.

#### 3. Test the validator
It's the gatekeeper; untested gatekeeper = unreliable standard.

### Tier 1: DSL Evolution (the real differentiators)
4. **Add `metric` widget type** — KPI cards are the single most-requested BI element
5. **Add dashboard-level `filters`** — cross-chart filtering is table-stakes
6. **Add `derived_fields`** — calculated columns unlock 80% of real analytics
7. **Add `text`/`markdown` widget type** — dashboards need narrative

### Tier 2: Contract & Data Model
8. **Fix Superset transformer** — separate `plan` from `apply`
9. **Support multiple data sources** — `data.sources[]` with per-chart binding
10. **Spec versioning strategy** — define what version numbers mean, add migration tooling

### Tier 3: Open Standard Readiness
11. **Contributor docs** — how to build a transformer, how to extend the DSL
12. **JSON Schema kept in sync** — currently it doesn't enforce conditional requirements (bubble needs size, etc.)
13. **CI/CD pipeline** — tests, linting, type checking on every PR

---

## Manifesto Assessment

The CLAUDE.md defines 7 principles. Here's how the codebase tracks against each, and whether the principles themselves hold up.

### Principles That Are Sound and Followed

**"Declarative, not Imperative"** — The `.dashml` spec describes *what* (bar chart, x=country, y=sales, agg=sum) and the compiler figures out *how*. Well-executed throughout.

**"Source-Agnostic by Design"** — The spec is source-agnostic: the same chart definition works regardless of whether data comes from CSV, SQL, or BigQuery. The *transformers* aren't cleanly separated by source (each handles all three), but the principle at the spec level is correct.

**"Read-Only by Principle"** — Followed everywhere except Superset, whose `build()` makes write API calls. The principle is correct; the violation is an implementation bug, not a philosophy problem.

**"LLM- and Human-Friendly"** — Genuinely true and a competitive advantage. YAML is flat, predictable, no deep nesting. An LLM can generate valid `.dashml` specs with high reliability. This is the kind of principle that ages well.

### Principles That Need Rethinking

**"Typeless at the Core"** — This principle says the core validates structure only; type inference is deferred to generated code. The codebase follows this literally. But it's protecting a design limitation, not expressing an architectural insight. Because the core doesn't normalize types, every transformer independently does type inference, date detection, and column type mapping. "Typeless at the core" sounds principled, but in practice it means "every backend reinvents type handling."

**Suggested revision:** "**Normalize Once, Generate Many**" — the core normalizes the spec into a clean IR (resolving paths, legacy fields, chart requirements); backends only handle platform-specific output. Type *inference from actual data* still belongs in generated code, but spec-level normalization belongs in the core.

**"Extensible and Backend-Neutral"** — Aspirational, not true today. Adding a new backend means writing 1,500-2,400 lines that handle all 12 chart types, all 3 data sources, Flask backend generation, theming, and type inference from scratch. The registry pattern exists, but the transformer interface is too broad for an external contributor to implement without studying all existing backends.

**Suggested revision:** Commit to a concrete extensibility bar: "A new backend should require only rendering logic, not data source handling or spec parsing." This becomes achievable once the normalizer/IR layer exists.

**"Validating the Spec, Trusting the Data"** — Correct in spirit: a spec compiler shouldn't need a database connection. But worth acknowledging the tradeoff — errors from bad column names or type mismatches only surface when you run the generated code, not at compile time. A future goal could be optional schema-aware validation (pass a schema file to get compile-time warnings) without violating the core principle.

### What's Missing From the Manifesto

**No principle about contributor experience.** If DashML wants to be an open standard, the manifesto should say something about making it practical for external contributors to add new backends or data sources. The current principles are all about the spec and the compiler — none address the human experience of extending the system.

---

## What I Would NOT Change

- **The compilation model** — compile YAML to standalone generated code, not runtime interpretation. The "readable generated code" philosophy is a genuine differentiator.
- **"Core never touches data" principle** — correct boundary for a spec compiler
- **TypedDict approach** — right tradeoff for a compiler
- **YAML as the DSL format** — LLM-friendly, human-readable, right choice
- **The 4-backend strategy** — proves universality, keep them all
