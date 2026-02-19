# LLM Generation Experiment: Does .dashml Beat Raw Code?

Tests whether LLMs produce valid dashboard specs more reliably when targeting DashML's constrained YAML DSL versus generating raw Streamlit code.

## Quick Start

```bash
cd experiments/llm_generation

# Dry run (no API calls, uses placeholder outputs)
python run_experiment.py --prompts prompts.yaml --runs 1 --dry-run

# Evaluate results
python evaluate.py --results results/dryrun_*
```

## Full Experiment

```bash
# With Claude Sonnet (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
python run_experiment.py --prompts prompts.yaml --model claude-sonnet-4-20250514 --runs 3

# With GPT-4o (requires OPENAI_API_KEY)
export OPENAI_API_KEY=sk-...
python run_experiment.py --prompts prompts.yaml --model gpt-4o --runs 3

# Evaluate
python evaluate.py --results results/<model>_<timestamp>
```

## Prerequisites

```bash
pip install pyyaml anthropic  # or: pip install pyyaml openai
```

The evaluation script also needs the DashML core (already in the repo — no install needed).

## Files

| File | Purpose |
|------|---------|
| `experiment_design.md` | Full methodology, hypothesis, evaluation criteria |
| `prompts.yaml` | 30 dashboard descriptions across 6 complexity tiers |
| `system_prompts.py` | System prompts for DashML and Streamlit generation |
| `run_experiment.py` | Calls LLM API, saves outputs to `results/` |
| `evaluate.py` | Scores outputs on parse/validate/compile/completeness |

## Complexity Tiers

| Tier | Description | Count |
|------|-------------|-------|
| T1 | Single chart, CSV, no aggregation | 5 |
| T2 | Single chart with aggregation + filter | 5 |
| T3 | Multi-chart single page (3-4 charts) | 5 |
| T4 | Multi-page dashboard (2-3 pages) | 5 |
| T5 | Advanced features (sort, limit, type hints) | 5 |
| T6 | Ambiguous/underspecified descriptions | 5 |

## Output Structure

```
results/<model>_<timestamp>/
  T1_01/
    dashml_run1.yaml
    dashml_run2.yaml
    dashml_run3.yaml
    streamlit_run1.py
    streamlit_run2.py
    streamlit_run3.py
  T1_02/
    ...
  metadata.json      # Run configuration and file paths
  scores.json        # Evaluation scores (after running evaluate.py)
```

## CLI Options

### run_experiment.py

```
--prompts PATH      Path to prompts.yaml (required)
--model MODEL       LLM model name (default: claude-sonnet-4-20250514)
--temperature FLOAT Sampling temperature (default: 0.3)
--runs N            Runs per prompt (default: 3)
--output DIR        Results directory (default: results/)
--dry-run           Use placeholder outputs, no API calls
```

### evaluate.py

```
--results DIR       Path to results directory (required)
--prompts PATH      Path to prompts.yaml (default: prompts.yaml)
--output PATH       Save scores JSON (default: <results>/scores.json)
```
