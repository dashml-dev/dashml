# Evaluating DashML with nvBench 2.0

## What is nvBench 2.0?

A NeurIPS 2025 benchmark for **NL2VIS** (Natural Language to Visualization). It contains 7,878 NL queries mapped to 24,076 Vega-Lite specs across 780 tables and 153 domains.

Key property: **1-to-many mapping** — each NL query has multiple valid visualizations (2-5 gold answers), because natural language is inherently ambiguous about which columns/aggregations to use.

- Paper: https://arxiv.org/html/2503.12880v2
- GitHub: https://github.com/HKUSTDial/nvBench-2.0
- Dataset: https://huggingface.co/datasets/TianqiLuo/nvBench2.0

## The Pipeline

```
NL query + table schema ──► LLM ──► .dashml YAML ──► VL transformer (--bare) ──► [{mark, encoding, transform}] ──► compare with gold
```

### What the LLM receives (input)

The model gets **table metadata only** — no actual data rows:

```
Table Columns: [stadium_id, location, name, capacity, highest, lowest, average]
Column Examples:
  stadium_id: [5, 7, 1]
  location: [Queen's Park, Ayr United, Peterhead]
  name: [Balmoor, Bayview Stadium, Hampden Park]
  capacity: [2000, 4000, 52500]
Unique Value Counts: {stadium_id: 9, location: 9, name: 9, capacity: 9, ...}

NL Query: "I want to mark a pie chart for the name while filtering it to Hampden Park and Balmoor."
```

### What the LLM must produce (DashML)

A `.dashml` spec that, when compiled with `--bare`, matches the gold answer structure:

```yaml
version: "1.0"
title: "query_result"
data:
  type: csv
  path: stadiums.csv
charts:
  - id: chart1
    type: pie
    x: name
    agg: count
    filter:
      - field: name
        op: in
        value: ["Hampden Park", "Balmoor"]
```

### What the gold answers look like

Partial Vega-Lite — only `mark`, `encoding`, and optionally `transform`:

```json
[
  {
    "mark": "pie",
    "encoding": {
      "color": {"field": "name"},
      "theta": {"aggregate": "count"}
    },
    "transform": [
      {"filter": {"field": "name", "oneOf": ["Hampden Park", "Balmoor"]}}
    ]
  },
  {
    "mark": "pie",
    "encoding": {
      "color": {"field": "name"},
      "theta": {"field": "capacity", "aggregate": "sum"}
    },
    "transform": [
      {"filter": {"field": "name", "oneOf": ["Hampden Park", "Balmoor"]}}
    ]
  }
]
```

Note: there are multiple valid answers because "pie chart for the name" is ambiguous — count? sum of capacity? sum of average?

## Evaluation Metrics

All metrics computed at K = {1, 3, 5} predictions:

| Metric | Formula | Meaning |
|--------|---------|---------|
| **Hit@K** | 1 if any of top-K predictions matches any gold | "Did we get at least one right?" |
| **Recall@K** | \|intersection\| / \|gold_answers\| | "What fraction of valid answers did we find?" |
| **Precision@K** | \|intersection\| / K | "What fraction of our predictions were correct?" |
| **F1@K** | Harmonic mean of P@K and R@K | Primary metric |

State-of-the-art (Step-NL2VIS, Qwen2.5-7B fine-tuned): **F1@3 = 81.50%**

## How Comparison Works

The evaluation is **strict structural equality** after normalization. Two specs match if and only if they are identical after:

1. **Axis normalization**: If both x and y are quantitative and x_field > y_field alphabetically, swap x/y. For bar/line/boxplot, if x is quantitative and y is not, swap them.
2. **Key ordering**: Top-level keys ordered as `mark → encoding → transform`. Encoding channels ordered as `x, y, theta, color, size`. Channel properties ordered as `field, aggregate, bin, sort`.
3. **Deep equality**: Dicts compared recursively (key-order-independent). Lists compared as unordered sets (each element must find a match).

**This means**: close-but-not-identical specs will NOT match. Using "average" instead of "mean", or different bin sizes, or extra properties → failure.

## Chart Type Mapping

nvBench 2.0 uses 6 Vega-Lite mark types:

| nvBench Mark | Visual | DashML Type | Encoding Pattern |
|-------------|--------|-------------|-----------------|
| `bar` | Bar chart | `bar` | x + y, optional color |
| `line` | Line chart | `line` | x + y, optional color |
| `arc` | Pie chart | `pie` | color + theta |
| `point` | Scatter | `scatter` | x + y, optional color/size |
| `rect` | Heatmap | `heatmap` | x + y + color |
| `boxplot` | Box plot | `box` | x + y |

## The 6 Reasoning Steps

Each nvBench entry includes a reasoning chain. These are used for training but the final answer (step 6 output) is what gets evaluated:

| Step | Name | What it does |
|------|------|-------------|
| 1 | Extract Columns & Filters | Parse NL for column references and filter conditions; flag ambiguous refs |
| 2 | Extract Transforms | Identify aggregation, binning, sorting from NL |
| 3 | Select Chart Type | Determine from explicit mention or infer (trend→bar/line, distribution→bar/arc/boxplot, etc.) |
| 4 | Channel Mapping | Map columns+transforms to x/y/color/theta/size channels |
| 5 | Add Implicit Channels | Fill obligatory channels not yet assigned; enumerate all valid combinations |
| 6 | Add Filters & Transforms | Attach filters, add binning rules (bin if >20 unique values), finalize |

Step 5 is where the 1-to-many expansion happens — ambiguous column refs get expanded into all valid assignments.

## Implementation Plan

### Phase 1: Output Adapter — DONE

The `--bare` flag on the Vega-Lite transformer handles all stripping at build time:

```bash
python -m dashml_new.cli build spec.dashml -t vegalite --bare --output out/
```

This outputs a JSON array of `{mark, encoding, transform}` objects with:
- Mark as plain string (not object) — `bar`, `line`, `arc`, `point`, `rect`, `boxplot`, `geoshape`, `text`, `area`
- Encoding channels stripped to only: `field`, `aggregate`, `bin`, `sort`, `timeUnit`
- No `type`, `scale`, `title`, `axis`, `tooltip`, `$schema`, `data`, `config`, `width`, `height`
- Filters in nvBench object format: `{"field": "x", "oneOf": [...]}`, `{"field": "x", "gte": 5}`, etc.
- Layered specs (geo) extract the data layer's encoding automatically

No separate `nvbench_adapter.py` needed — it's built into the transformer.

### Phase 2: LLM Prompt Engineering

Design a prompt that takes nvBench's table schema + NL query and produces valid `.dashml` YAML.

**A) Direct .dashml generation:**
```
Given this table schema and NL query, produce a .dashml YAML spec.
[table schema]
[NL query]
[DashML format reference]
```

**B) Multi-prediction generation:**
Since nvBench expects 1-5 predictions and scores recall, the LLM should produce multiple .dashml specs covering different interpretations of the ambiguous query. Each spec = one chart with one interpretation.

**Key prompt considerations:**
- The LLM must pick the right DashML `type` (bar/line/pie/scatter/heatmap/box)
- Must correctly map NL column references to `x`, `y`, `group` fields
- Must infer `agg` (sum/mean/count) from context or enumerate alternatives
- Must convert NL filter conditions to DashML `filter` syntax
- Should generate multiple specs when the query is ambiguous (e.g., "chart for name" — count? sum of which column?)

### Phase 3: Evaluation Harness

Script (`nvbench_eval.py`) that:
1. Loads test split from HuggingFace (791 entries)
2. For each entry: feeds `table_schema` + `nl_query` to LLM → gets 1-5 `.dashml` YAML strings
3. For each `.dashml`: parses → validates → runs `VegaLiteTransformer(bare=True).build(spec)`
4. Parses the JSON array output → list of `{mark, encoding, transform}` dicts
5. Compares against `gold_answer` using nvBench's `deep_compare_charts()` + normalization
6. Computes Hit@K, Recall@K, Precision@K, F1@K

**Dependencies:**
- `datasets` (HuggingFace) — for loading nvBench 2.0
- An LLM API (Anthropic/OpenAI/local) — for NL → .dashml generation
- nvBench evaluation code — `deep_compare_charts()` and `preprocess_charts()` from their repo
- `nvbench_metadata.json` — column type metadata needed for axis normalization

### Phase 4: Iterate

Tune the LLM prompt, experiment with step-wise reasoning, try different models.

## Baseline Scores (from the paper)

| Model | Method | F1@3 | F1@5 |
|-------|--------|------|------|
| GPT-3.5 | Direct | 28.91 | 22.35 |
| GPT-3.5 | Step-wise | 35.29 | 27.24 |
| DeepSeek-R1 | Direct | 42.90 | 33.90 |
| Qwen2.5-7B (SFT) | Step-wise | 75.08 | 59.85 |
| **Step-NL2VIS** | **Step-DPO** | **81.50** | **64.46** |

## Methodology: What Counts as Fair

The benchmark comparison (NL → DashML → VL vs NL → VL directly) is valid only if the transformer is not tuned against specific test cases. The rule:

### Data Split

Use a held-out evaluation setup to keep development and testing cleanly separated:

| Split | Source | Size | Purpose |
|-------|--------|------|---------|
| **Dev set** | Random 10% of nvBench test split | ~80 entries | Find expressiveness gaps, tune format alignment, debug the pipeline |
| **Eval set** | Remaining 90% of nvBench test split | ~711 entries | Final scores — never seen during development |

> "We randomly sampled 10% of the test split (80 entries) as a development set to identify expressiveness gaps in the DashML schema and validate transformer output format alignment. The remaining 711 entries were held out for final evaluation. No changes to the DSL or transformer were made after development concluded."

### Development vs Evaluation

| Phase | What you do | Example |
|-------|------------|---------|
| **Development** | Build the transformer, fix bugs, align output format using **dev set only** | `pie` → `arc`, filters → nvBench object format, `--bare` stripping |
| **Freeze** | Stop changing `vegalite.py` and the DashML schema | Draw the line here |
| **Evaluation** | Run both experiments on **eval set only**, report scores as-is | No going back to patch |

### What's legitimate to fix (before freeze)

**General expressiveness gaps** — if DashML can't express a class of visualizations (e.g., intra-group sort order, binning with specific step sizes), adding that capability to the DSL is a language improvement, not overfitting. The test: would the fix help with ANY query that uses that feature, or only the specific failing test case?

Examples:
- "DashML has no `group_sort` field, so grouped bar charts with custom sort always fail" → **Add `group_sort` to the schema.** This is an expressiveness contribution.
- "The `--bare` output includes `type: quantitative` but nvBench expects it absent" → **Fix the stripping logic.** This is format alignment, required for any benchmark participation.
- "DashML doesn't support `timeUnit` in encodings" → **Add `time_unit` field.** General capability gap.

### What's NOT legitimate

- "The LLM keeps swapping x/y, let me auto-correct in the transformer" → Compensating for LLM errors.
- "Test case #347 expects descending sort, let me special-case it" → Overfitting to a specific test.
- Iterating between evaluation results and transformer changes — if tests fail after freeze, report the failure.

### Documenting the process

Expressiveness gaps discovered during development are a **thesis contribution**:

> "During pre-evaluation testing against nvBench 2.0 gold answers, we identified N expressiveness gaps in the DashML schema (e.g., no support for intra-group sorting, no `timeUnit` encoding). We extended the schema with fields X, Y, Z to address these gaps. All schema changes were completed before running the final evaluation."

## Key Risks and Considerations

1. **Multiple predictions**: Getting good Recall@K requires generating multiple .dashml specs per query. The LLM needs to reason about ambiguity and enumerate alternatives.

2. **Strict matching**: Even minor differences (extra property, different key name) cause a miss. The `--bare` adapter must be precise.

3. **No data needed**: The benchmark only provides table metadata (column names, examples, cardinality). The LLM must infer the right visualization from schema alone — no CSV, no SQL, no actual data.

4. **DashML as overhead or value-add?**: Going NL → DashML → VL adds an intermediate step vs NL → VL directly. The value is that DashML enforces structure and can target multiple backends. The cost is potential information loss in the DashML → VL translation. We need to verify that every nvBench gold answer is representable as a .dashml spec.

5. **Sort format gap**: nvBench uses sort as channel references (`"y"`, `"-y"`) while DashML's `--bare` output uses `{"encoding": "y", "order": "ascending"}`. May need alignment.

## Quick Start

```bash
# Install deps
pip install datasets

# Download and explore
python nvbench_explore.py

# Build a .dashml in bare mode (test the adapter)
python -m dashml_new.cli build my_spec.dashml -t vegalite --bare --output out/

# Run evaluation (once Phase 2-3 are built)
python nvbench_eval.py --model claude --k 3
```

## Files

| File | Status | Purpose |
|------|--------|---------|
| `dashml_new/transformers/vegalite.py` | DONE | `--bare` mode: `_build_bare_spec()`, `_build_bare_filters()`, `_filter_to_nvbench()` |
| `dashml_new/cli.py` | DONE | `--bare` CLI flag wired to `VegaLiteTransformer(bare=True)` |
| `nvbench_explore.py` | DONE | Dataset exploration |
| `nvbench_eval.py` | TODO | Evaluation harness (load data, run pipeline, compute metrics) |
| `nvbench_prompt.py` | TODO | LLM prompt template for NL → .dashml |
| `NVBENCH_EVAL.md` | DONE | This document |
