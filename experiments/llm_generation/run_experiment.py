#!/usr/bin/env python3
"""
LLM Generation Experiment Runner

Calls an LLM API to generate both .dashml specs and raw Streamlit code
for each prompt, then saves the results for evaluation.

Usage:
    python run_experiment.py --prompts prompts.yaml --model claude-sonnet --runs 3
    python run_experiment.py --prompts prompts.yaml --model gpt-4o --runs 1 --dry-run
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from system_prompts import DASHML_SYSTEM_PROMPT, STREAMLIT_SYSTEM_PROMPT, PLOTLY_SYSTEM_PROMPT

TARGET_PROMPTS = {
    "streamlit": STREAMLIT_SYSTEM_PROMPT,
    "plotly": PLOTLY_SYSTEM_PROMPT,
}

TARGET_EXTENSIONS = {
    "streamlit": "py",
    "plotly": "html",
}

# ---------------------------------------------------------------------------
# LLM Client Abstraction
# ---------------------------------------------------------------------------

class LLMClient:
    """Thin wrapper around LLM APIs (Anthropic / OpenAI)."""

    def __init__(self, model: str, temperature: float = 0.3):
        self.model = model
        self.temperature = temperature
        self._client = None
        self._provider = self._detect_provider(model)

    @staticmethod
    def _detect_provider(model: str) -> str:
        if model.startswith("claude") or model.startswith("anthropic"):
            return "anthropic"
        elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
            return "openai"
        else:
            raise ValueError(
                f"Unknown model '{model}'. Use a Claude or GPT model name."
            )

    def _get_client(self):
        if self._client is not None:
            return self._client

        if self._provider == "anthropic":
            try:
                import anthropic
            except ImportError:
                print("Error: pip install anthropic", file=sys.stderr)
                sys.exit(1)
            self._client = anthropic.Anthropic()
        else:
            try:
                import openai
            except ImportError:
                print("Error: pip install openai", file=sys.stderr)
                sys.exit(1)
            self._client = openai.OpenAI()

        return self._client

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        client = self._get_client()

        if self._provider == "anthropic":
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text

        else:  # openai
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content


class DryRunClient:
    """Returns placeholder outputs without calling any API."""

    SAMPLE_DASHML = """\
version: 0.1
title: "Generated Dashboard"

data:
  type: csv
  path: "data/example.csv"

charts:
  - id: "chart_1"
    type: "bar"
    title: "Sample Chart"
    x: "category"
    y: "value"
    agg: "sum"
"""

    SAMPLE_STREAMLIT = """\
import streamlit as st
import pandas as pd
import altair as alt

st.set_page_config(page_title="Generated Dashboard", layout="wide")
st.title("Generated Dashboard")

df = pd.read_csv("data/example.csv")
agg = df.groupby("category")["value"].sum().reset_index()

chart = alt.Chart(agg).mark_bar().encode(x="category", y="value")
st.subheader("Sample Chart")
st.altair_chart(chart, use_container_width=True)
"""

    SAMPLE_PLOTLY = """\
<!DOCTYPE html>
<html>
<head>
    <title>Generated Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>
</head>
<body>
    <h1>Generated Dashboard</h1>
    <div id="chart1"></div>
    <script>
    Papa.parse("data/example.csv", {
        download: true, header: true, dynamicTyping: true,
        complete: function(results) {
            const data = results.data;
            const groups = {};
            data.forEach(r => { groups[r.category] = (groups[r.category] || 0) + r.value; });
            Plotly.newPlot('chart1',
                [{x: Object.keys(groups), y: Object.values(groups), type: 'bar'}],
                {title: 'Sample Chart'});
        }
    });
    </script>
</body>
</html>
"""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if "dashml" in system_prompt.lower() or ".dashml" in system_prompt:
            return self.SAMPLE_DASHML
        if "plotly" in system_prompt.lower():
            return self.SAMPLE_PLOTLY
        return self.SAMPLE_STREAMLIT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_prompts(path: str) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)


def clean_response(text: str, format_type: str) -> str:
    """Strip markdown fences and leading/trailing whitespace."""
    text = text.strip()
    # Remove ```yaml ... ``` or ```python ... ```
    for lang in ("yaml", "python", "py", "html", "javascript", "js", ""):
        fence_open = f"```{lang}"
        if text.startswith(fence_open):
            text = text[len(fence_open):]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            break
    return text


def save_output(results_dir: Path, prompt_id: str, format_type: str,
                run_num: int, content: str) -> Path:
    prompt_dir = results_dir / prompt_id
    prompt_dir.mkdir(parents=True, exist_ok=True)

    ext_map = {"dashml": "yaml", "streamlit": "py", "plotly": "html"}
    ext = ext_map.get(format_type, "txt")
    filename = f"{format_type}_run{run_num}.{ext}"
    path = prompt_dir / filename
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_experiment(args: argparse.Namespace) -> None:
    prompts = load_prompts(args.prompts)
    target = args.target
    target_prompt = TARGET_PROMPTS[target]
    target_label = target.capitalize()

    print(f"Loaded {len(prompts)} prompts from {args.prompts}")

    # Set up results directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_label = f"{args.model}_{target}_{timestamp}"
    if args.dry_run:
        run_label = f"dryrun_{target}_{timestamp}"
    results_dir = Path(args.output) / run_label
    results_dir.mkdir(parents=True, exist_ok=True)

    # Initialize client
    if args.dry_run:
        client = DryRunClient()
        print("DRY RUN — using placeholder outputs")
    else:
        client = LLMClient(model=args.model, temperature=args.temperature)
        print(f"Using model: {args.model}, temperature: {args.temperature}")

    print(f"Target: DashML vs {target_label}")
    print(f"Runs per prompt: {args.runs}")
    print(f"Results directory: {results_dir}")
    print(f"Total generations: {len(prompts) * args.runs * 2}")
    print()

    # Track metadata
    metadata = {
        "model": args.model if not args.dry_run else "dry-run",
        "target": target,
        "temperature": args.temperature,
        "runs": args.runs,
        "prompt_count": len(prompts),
        "total_generations": len(prompts) * args.runs * 2,
        "timestamp": timestamp,
        "results": [],
    }

    total = len(prompts) * args.runs
    completed = 0

    for prompt in prompts:
        prompt_id = prompt["id"]
        tier = prompt["tier"]
        description = prompt["description"]

        for run_num in range(1, args.runs + 1):
            completed += 1
            prefix = f"[{completed}/{total}] {prompt_id} run{run_num}"

            # Generate DashML
            print(f"{prefix} — generating .dashml ...", end=" ", flush=True)
            t0 = time.time()
            dashml_raw = client.generate(DASHML_SYSTEM_PROMPT, description)
            dashml_clean = clean_response(dashml_raw, "dashml")
            dashml_path = save_output(results_dir, prompt_id, "dashml",
                                      run_num, dashml_clean)
            dt_dashml = time.time() - t0
            print(f"done ({dt_dashml:.1f}s)")

            # Generate target (Streamlit or Plotly)
            print(f"{prefix} — generating {target_label} ...", end=" ", flush=True)
            t0 = time.time()
            target_raw = client.generate(target_prompt, description)
            target_clean = clean_response(target_raw, target)
            target_path = save_output(results_dir, prompt_id, target,
                                      run_num, target_clean)
            dt_target = time.time() - t0
            print(f"done ({dt_target:.1f}s)")

            metadata["results"].append({
                "prompt_id": prompt_id,
                "tier": tier,
                "run": run_num,
                "dashml_path": str(dashml_path),
                "target_path": str(target_path),
                "dashml_time_s": round(dt_dashml, 2),
                "target_time_s": round(dt_target, 2),
            })

    # Save metadata
    meta_path = results_dir / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print()
    print(f"Experiment complete. Results saved to: {results_dir}")
    print(f"Metadata: {meta_path}")
    print(f"Run evaluation: python evaluate.py --results {results_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Run the DashML vs raw code LLM generation experiment"
    )
    parser.add_argument(
        "--prompts", required=True,
        help="Path to prompts.yaml file"
    )
    parser.add_argument(
        "--target", choices=["streamlit", "plotly"], default="streamlit",
        help="Raw code target to compare against DashML (default: streamlit)"
    )
    parser.add_argument(
        "--model", default="claude-sonnet-4-20250514",
        help="LLM model to use (default: claude-sonnet-4-20250514)"
    )
    parser.add_argument(
        "--temperature", type=float, default=0.3,
        help="Sampling temperature (default: 0.3)"
    )
    parser.add_argument(
        "--runs", type=int, default=3,
        help="Number of runs per prompt (default: 3)"
    )
    parser.add_argument(
        "--output", default="results",
        help="Output directory for results (default: results/)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Use placeholder outputs instead of calling the LLM API"
    )

    args = parser.parse_args()

    if not os.path.exists(args.prompts):
        print(f"Error: prompts file not found: {args.prompts}", file=sys.stderr)
        sys.exit(1)

    run_experiment(args)


if __name__ == "__main__":
    main()
