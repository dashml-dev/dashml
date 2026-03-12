# Evaluating DashML with nvBench 2.0

## What is nvBench 2.0?

A NeurIPS 2025 benchmark for **NL2VIS** (Natural Language to Visualization). It contains 7,878 NL queries mapped to 24,076 Vega-Lite specs across 780 tables and 153 domains.

Key property: **1-to-many mapping** — each NL query has multiple valid visualizations (2-5 gold answers), because natural language is inherently ambiguous about which columns/aggregations to use.

- Paper: https://arxiv.org/html/2503.12880v2
- GitHub: https://github.com/HKUSTDial/nvBench-2.0
- Dataset: https://huggingface.co/datasets/TianqiLuo/nvBench2.0

## The Pipeline

```
NL query + table schema ──► LLM ──► .dashml YAML ──► Vega-Lite transformer ──► VL JSON ──► strip to {mark, encoding, transform} ──► compare with gold
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

A `.dashml` spec that, when compiled to Vega-Lite, matches the gold answer structure:

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

### Critical differences from DashML's current Vega-Lite output

Our transformer must produce specs that exactly match this format:

| Property | nvBench format | Our current format | Gap |
|----------|---------------|-------------------|-----|
| `mark` | `"bar"` (string) | `"bar"` or `{"type": "bar", ...}` | Strip mark objects to strings |
| Encoding `type` | **absent** | `"quantitative"`, `"nominal"`, etc. | Must strip `type` from encodings |
| Encoding `title` | **absent** | Sometimes present | Must strip |
| Encoding `scale` | **absent** | Sometimes present | Must strip |
| Encoding `axis` | **absent** | Sometimes present | Must strip |
| `aggregate` | Inside encoding: `{"aggregate": "mean"}` | Inside encoding | OK |
| `bin` | `{"maxbins": 10}` | `{"maxbins": N}` | Check format |
| `sort` | Channel ref: `"y"`, `"-y"` | May differ | Check format |
| Pie encoding | `theta` + `color` | Needs verification | Ensure theta channel is used |
| Filter format | `{"filter": {"field": "x", "oneOf": [...]}}` | Vega expressions | **Major gap** — must emit nvBench filter format |
| `$schema`, `data`, `config`, `title`, `width`, `height` | **absent** | Present | Must strip in post-processing |

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

### Phase 1: Output Adapter (strip DashML VL output to nvBench format)

Write a post-processor that takes our Vega-Lite JSON and strips it to `{mark, encoding, transform}`:
- Remove: `$schema`, `data`, `config`, `title`, `width`, `height`, `description`
- From mark: if object like `{"type": "bar", "stroke": ...}`, extract just `"bar"`
- From encodings: keep only `field`, `aggregate`, `bin`, `sort`, `timeUnit`; drop `type`, `title`, `scale`, `axis`
- From transform/filter: convert DashML filter format to nvBench filter format
- Map DashML chart types to nvBench marks: `pie` → `arc`, `heatmap` → mark `rect`, `scatter` → `point`, `box` → `boxplot`

### Phase 2: LLM Prompt Engineering (colleague's part)

Design a prompt that takes nvBench's table schema + NL query and produces a valid `.dashml` YAML. Two approaches:

**A) Direct .dashml generation:**
```
Given this table schema and NL query, produce a .dashml YAML spec.
[table schema]
[NL query]
[DashML format reference]
```

**B) Multi-prediction generation:**
Since nvBench expects 1-5 predictions and scores recall, the LLM should produce multiple .dashml specs covering different interpretations of the ambiguous query.

### Phase 3: Evaluation Harness

Script that:
1. Loads test split from HuggingFace (791 entries)
2. For each entry: feeds table_schema + nl_query to LLM → gets 1-5 .dashml specs
3. Runs each through `VegaLiteTransformer.transform()`
4. Strips output to nvBench format (Phase 1 adapter)
5. Compares against gold using nvBench's `deep_compare_charts()` + normalization
6. Computes Hit@K, Recall@K, Precision@K, F1@K

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

## Key Risks and Considerations

1. **Filter format mismatch**: Our VL transformer emits standard Vega-Lite filter expressions (`"datum.x > 5"`), but nvBench expects `{"field": "x", "gt": 5}`. The adapter must convert, or we modify the transformer to emit nvBench-style filters.

2. **Multiple predictions**: Getting good Recall@K requires generating multiple .dashml specs per query. The LLM needs to reason about ambiguity and enumerate alternatives.

3. **Strict matching**: Even minor differences (extra property, different key name) cause a miss. The adapter must be precise.

4. **No data needed**: The benchmark only provides table metadata (column names, examples, cardinality). The LLM must infer the right visualization from schema alone — no CSV, no SQL, no actual data.

5. **DashML as overhead or value-add?**: Going NL → DashML → VL adds an intermediate step vs NL → VL directly. The value is that DashML enforces structure and can target multiple backends. The cost is potential information loss in the DashML → VL translation. We need to verify that every nvBench gold answer is representable as a .dashml spec.

## Quick Start

```bash
# Install deps
pip install datasets

# Download and explore
python nvbench_explore.py

# Run evaluation (once pipeline is built)
python nvbench_eval.py --model claude --predictions output/predictions/ --k 3
```

## Files to Create

| File | Purpose |
|------|---------|
| `nvbench_adapter.py` | Strip VL output to nvBench format |
| `nvbench_eval.py` | Evaluation harness (load data, run pipeline, compute metrics) |
| `nvbench_prompt.py` | LLM prompt template for NL → .dashml |
| `nvbench_explore.py` | Dataset exploration (already exists) |
