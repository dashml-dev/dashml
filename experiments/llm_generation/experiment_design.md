# LLM Generation Experiment: Does .dashml Beat Raw Code?

## Hypothesis

LLMs produce valid, complete dashboard specifications at a higher rate when targeting `.dashml` (a constrained declarative YAML DSL) than when generating raw Streamlit code.

## Rationale

DashML's core thesis: LLMs are unreliable at generating complex framework-specific code but excel at producing simple, declarative specs within a constrained schema. If true, DashML serves as a reliable "easy target" that LLMs can hit consistently — making AI-assisted dashboard creation practical.

## Method

### Inputs
- **30 natural language dashboard descriptions**, 5 per complexity tier
- Each prompt generates **2 outputs**: a `.dashml` spec AND equivalent raw Streamlit code
- **3 runs per prompt** (to measure consistency) = **180 total generations**
- Same model, same temperature (0.3), same run

### Models (configurable)
- Claude Sonnet (default)
- GPT-4o (comparison)

### Complexity Tiers (5 prompts each)

| Tier | Description | Features Tested |
|------|-------------|-----------------|
| **T1** | Single chart, CSV, no aggregation | Basic spec structure |
| **T2** | Single chart with aggregation + filter | `agg`, `filters` |
| **T3** | Multi-chart single page (3-4 charts) | Multiple chart types, shared data |
| **T4** | Multi-page dashboard (2-3 pages) | `pages` structure, page metadata |
| **T5** | Advanced features | `sort`, `limit`, `x_type`/`y_type`, multiple filters |
| **T6** | Ambiguous/underspecified descriptions | Graceful handling, reasonable defaults |

### Controls

1. **Same LLM and temperature** for both formats in each run
2. **DashML prompt** includes the `.dashml` JSON schema and 2 examples as context
3. **Streamlit prompt** includes equivalent Streamlit/Pandas/Altair documentation and examples
4. **Both prompts** receive the identical dashboard description
5. **System prompts** are roughly equal in token count to avoid information asymmetry

## Evaluation Criteria

Each output is scored on 5 metrics:

| Metric | DashML Scoring | Streamlit Scoring | Type |
|--------|---------------|-------------------|------|
| **Parses** (0/1) | `yaml.safe_load()` succeeds | `ast.parse()` succeeds | Automated |
| **Validates** (0/1) | Passes `DashMLValidator` | No `NameError`, imports resolve, `pylint` clean | Automated + semi-auto |
| **Compiles** (0/1) | `dashml build` produces output file | `streamlit run` starts without crash (5s timeout) | Automated |
| **Completeness** (0.0–1.0) | All requested charts/types/axes/agg present | All requested charts/types/axes/agg present | Checklist per prompt |
| **Correctness** (0.0–1.0) | Chart types, axes, agg match intent | Chart types, axes, agg match intent | Checklist per prompt |

### Automated scoring

- **Parses**: Try to load the output. Binary pass/fail.
- **Validates**: For DashML, run the actual `DashMLValidator`. For Streamlit, use `ast.parse()` + check that all imports are from known packages (`streamlit`, `pandas`, `altair`).
- **Compiles**: For DashML, run `python -m dashml_new.cli build` and check exit code. For Streamlit, run `streamlit run --server.headless true` with a 5-second timeout and check for startup errors.

### Manual scoring (completeness + correctness)

Each prompt has an **expected features checklist** defined in `prompts.yaml`:
- Expected chart types
- Expected axes (x, y columns)
- Expected aggregations
- Expected filters
- Expected pages (for multi-page)

Completeness = (features present) / (features expected)
Correctness = (features correctly implemented) / (features present)

## Primary Metrics

1. **Validation Rate** = % of outputs that parse AND validate
   - Primary comparison metric between DashML and Streamlit
   - Reported per tier and overall

2. **Completeness Score** = average completeness across all prompts
   - Secondary metric: does the output capture the full intent?

3. **Consistency** = standard deviation across 3 runs per prompt
   - Measures reliability, not just accuracy

## Expected Results

If the hypothesis holds:
- DashML validation rate > 90% (constrained schema prevents most errors)
- Streamlit validation rate < 70% (import errors, API misuse, missing variables)
- Gap widens at higher complexity tiers (T4-T6)
- DashML consistency higher (lower std dev across runs)

## Output Structure

```
results/
  {model}_{timestamp}/
    T1_01/
      dashml_run1.yaml
      dashml_run2.yaml
      dashml_run3.yaml
      streamlit_run1.py
      streamlit_run2.py
      streamlit_run3.py
    T1_02/
      ...
    scores.json          # Automated scores
    report.md            # Summary report
```

## Limitations

- **No runtime data testing**: We test structure, not whether charts render correctly with real data
- **Streamlit linting is imperfect**: Some valid Streamlit patterns may be flagged as errors
- **Completeness/correctness** require manual review (or a second LLM as judge)
- **Single-model results** may not generalize across all LLMs
- **Temperature 0.3** is a single operating point; results may differ at other temperatures
