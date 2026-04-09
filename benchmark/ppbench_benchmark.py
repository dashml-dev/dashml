"""
PandasPlotBench Benchmark: DashML vs Raw Plotly Code

Runs two arms:
  A) NL → LLM → .dashml YAML → PlotlyTransformer → HTML (guaranteed valid)
  B) NL → LLM → raw Plotly Python code → subprocess exec → may fail

Usage:
    python3 benchmark/ppbench_benchmark.py --arm both --model claude-sonnet-4-20250514 --limit 5
    python3 benchmark/ppbench_benchmark.py --arm dashml --limit 10
    python3 benchmark/ppbench_benchmark.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datasets import load_dataset

from benchmark.ppbench_prompts import build_user_prompt, get_system_prompt


# ── LLM Client (self-contained, supports Anthropic) ─────────────────────────

class LLMClient:
    """Thin wrapper around LLM APIs with token tracking."""

    def __init__(self, model: str, temperature: float = 0.0):
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
            raise ValueError(f"Unknown model '{model}'. Use a Claude or GPT model name.")

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self._provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic()
        else:
            import openai
            self._client = openai.OpenAI()
        return self._client

    def generate(self, system_prompt: str, user_prompt: str) -> dict:
        """Generate response and return {text, input_tokens, output_tokens}."""
        client = self._get_client()
        if self._provider == "anthropic":
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return {
                "text": response.content[0].text,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        else:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            usage = response.usage
            return {
                "text": response.choices[0].message.content,
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
            }


# ── Caching ──────────────────────────────────────────────────────────────────

def _cache_key(system_prompt: str, user_prompt: str, model: str) -> str:
    """Generate cache key from prompt + model."""
    content = f"{model}::{system_prompt}::{user_prompt}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def load_cached_response(cache_dir: Path, key: str) -> Optional[dict]:
    """Load cached response (text + token counts)."""
    path = cache_dir / f"{key}.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            pass
    # Fallback: old text-only cache format
    txt_path = cache_dir / f"{key}.txt"
    if txt_path.exists():
        return {"text": txt_path.read_text(), "input_tokens": 0, "output_tokens": 0}
    return None


def save_cached_response(cache_dir: Path, key: str, response: dict) -> None:
    """Save response with token counts."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    with open(path, "w") as f:
        json.dump(response, f)


# ── Response Parsing ─────────────────────────────────────────────────────────

def clean_response(text: str) -> str:
    """Strip markdown code fences and whitespace."""
    text = text.strip()
    text = re.sub(r"^```(?:yaml|json|python|py)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def parse_dashml_prediction(raw: str) -> Optional[dict]:
    """Parse a single .dashml YAML spec from LLM response."""
    raw = clean_response(raw)
    # If multiple docs separated by ---, take only the first
    docs = re.split(r"\n---\s*\n", raw)
    for doc in docs:
        doc = doc.strip()
        if not doc:
            continue
        try:
            spec = yaml.safe_load(doc)
            if isinstance(spec, dict):
                return spec
        except yaml.YAMLError:
            continue
    return None


def parse_plotly_code(raw: str) -> Optional[str]:
    """Extract Python code from LLM response."""
    raw = clean_response(raw)
    # If it looks like Python code already, return as-is
    if raw.startswith("import ") or raw.startswith("from ") or raw.startswith("df"):
        return raw
    # Try to extract from code block
    match = re.search(r"```(?:python|py)?\s*\n(.+?)```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw


# ── DashML Compilation Pipeline ──────────────────────────────────────────────

def compile_dashml_to_plotly_html(
    spec: dict, csv_path: str, output_dir: Path
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Compile .dashml spec to Plotly HTML via PlotlyTransformer.
    Returns (success, html_path_or_none, error_or_none).
    """
    try:
        from dashml_new.core.validator import DashMLValidator
        from dashml_new.core.normalizer import DashMLNormalizer
        from dashml_new.transformers.plotly import PlotlyTransformer

        # Ensure data section points to actual CSV
        if "data" not in spec:
            spec["data"] = {}
        spec["data"]["type"] = "csv"
        spec["data"]["path"] = csv_path

        # Ensure required fields
        if "version" not in spec:
            spec["version"] = "1.0"
        if "title" not in spec:
            spec["title"] = "benchmark_chart"

        # Validate
        validator = DashMLValidator()
        validator.validate(spec)

        # Normalize
        normalizer = DashMLNormalizer()
        normalized = normalizer.normalize(spec, source_file=csv_path)

        # Generate Plotly HTML
        transformer = PlotlyTransformer()
        html = transformer.build(normalized)

        # Write to file
        output_dir.mkdir(parents=True, exist_ok=True)
        html_path = output_dir / "output.html"
        html_path.write_text(html)

        return True, str(html_path), None

    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"


# ── Plotly Code Execution ────────────────────────────────────────────────────

def execute_plotly_code(
    code: str, csv_path: str, output_dir: Path, timeout: int = 30
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Execute raw Plotly Python code in a subprocess.
    Returns (success, png_path_or_none, error_or_none).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_png = (output_dir / "output.png").resolve()
    csv_path_abs = str(Path(csv_path).resolve())

    # Build the full script
    # Prepend imports and data loading, fix output path
    script_lines = [
        "import pandas as pd",
        f'df = pd.read_csv("{csv_path_abs}")',
        "",
        code,
    ]

    # Replace any write_image call to use our output path
    script = "\n".join(script_lines)
    script = re.sub(
        r'fig\.write_image\(["\'].*?["\']\)',
        f'fig.write_image("{output_png}")',
        script,
    )
    # If no write_image call exists, add one at the end
    if "write_image" not in script:
        script += f'\nfig.write_image("{output_png}")'

    # Also replace any read_csv call with our path
    script = re.sub(
        r'pd\.read_csv\(["\'].*?["\']\)',
        f'pd.read_csv("{csv_path}")',
        script,
    )

    # Write script to temp file (use absolute path to avoid cwd issues)
    script_path = output_dir.resolve() / "script.py"
    script_path.write_text(script)

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            error = result.stderr.strip()
            # Truncate long errors
            if len(error) > 500:
                error = error[:500] + "..."
            return False, None, error

        if output_png.exists():
            return True, str(output_png), None
        else:
            return False, None, "Code ran but produced no output image"

    except subprocess.TimeoutExpired:
        return False, None, f"Execution timed out after {timeout}s"
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"


# ── Main Benchmark ───────────────────────────────────────────────────────────

def run_benchmark(
    arm: str,
    model: str,
    split: str,
    limit: Optional[int],
    output_dir: Path,
    cache_dir: Path,
    dry_run: bool = False,
    temperature: float = 0.0,
):
    """Run the benchmark for one arm."""
    print(f"\n{'='*60}")
    print(f"PandasPlotBench — {arm.upper()} arm | model={model}")
    print(f"{'='*60}\n")

    # Load dataset
    ds = load_dataset("JetBrains-Research/PandasPlotBench", split=split)
    entries = list(ds)
    if limit:
        entries = entries[:limit]
    print(f"Loaded {len(entries)} tasks")

    # Cost estimation for dry run
    if dry_run:
        system_prompt = get_system_prompt(arm)
        avg_user_tokens = 400
        avg_sys_tokens = len(system_prompt.split()) * 1.3
        avg_output_tokens = 300 if arm == "dashml" else 800
        total_input = (avg_sys_tokens + avg_user_tokens) * len(entries)
        total_output = avg_output_tokens * len(entries)
        # Claude Sonnet pricing: $3/M input, $15/M output
        est_cost = (total_input / 1e6 * 3) + (total_output / 1e6 * 15)
        print(f"\n--- DRY RUN COST ESTIMATE ({arm}) ---")
        print(f"  Tasks: {len(entries)}")
        print(f"  Est. input tokens: {total_input:,.0f}")
        print(f"  Est. output tokens: {total_output:,.0f}")
        print(f"  Est. cost (Claude Sonnet): ${est_cost:.2f}")
        return

    # Initialize LLM client
    client = LLMClient(model=model, temperature=temperature)
    system_prompt = get_system_prompt(arm)

    # Load existing results for resume
    results_path = output_dir / f"results_{arm}.jsonl"
    completed_ids = set()
    if results_path.exists():
        with open(results_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    completed_ids.add(r["task_id"])
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"Resuming: {len(completed_ids)} tasks already completed")

    # Process entries
    output_dir.mkdir(parents=True, exist_ok=True)
    results_file = open(results_path, "a")

    stats = {
        "total": 0,
        "parse_ok": 0,
        "compile_ok": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    try:
        for idx, entry in enumerate(entries):
            task_id = entry.get("id", idx)
            if task_id in completed_ids:
                continue

            stats["total"] += 1

            task_desc = entry.get("task__plot_description", "")
            style_desc = entry.get("task__plot_style", "")
            csv_data = entry.get("data_csv", "")

            # Write CSV to temp file
            task_dir = output_dir / f"task_{task_id}" / arm
            task_dir.mkdir(parents=True, exist_ok=True)
            csv_path = task_dir / "data.csv"
            csv_path.write_text(csv_data)

            # Build user prompt
            user_prompt = build_user_prompt(task_desc, style_desc, csv_data)

            # Check cache
            cache_key = _cache_key(system_prompt, user_prompt, model)
            cached = load_cached_response(cache_dir, cache_key)

            if cached:
                raw_text = cached["text"]
                input_tokens = cached.get("input_tokens", 0)
                output_tokens = cached.get("output_tokens", 0)
            else:
                try:
                    response = client.generate(system_prompt, user_prompt)
                    raw_text = response["text"]
                    input_tokens = response["input_tokens"]
                    output_tokens = response["output_tokens"]
                    save_cached_response(cache_dir, cache_key, response)
                except Exception as e:
                    print(f"  [{task_id}] API error: {e}")
                    result = {
                        "task_id": task_id,
                        "arm": arm,
                        "error": str(e),
                        "parse_ok": False,
                        "compile_ok": False,
                        "input_tokens": 0,
                        "output_tokens": 0,
                    }
                    results_file.write(json.dumps(result) + "\n")
                    results_file.flush()
                    continue

            stats["total_input_tokens"] += input_tokens
            stats["total_output_tokens"] += output_tokens

            # Process by arm
            parse_ok = False
            compile_ok = False
            output_path = None
            error_msg = None

            if arm == "dashml":
                spec = parse_dashml_prediction(raw_text)
                parse_ok = spec is not None
                if parse_ok:
                    stats["parse_ok"] += 1

                if parse_ok:
                    compile_ok, output_path, error_msg = compile_dashml_to_plotly_html(
                        spec, str(csv_path), task_dir
                    )
                    if compile_ok:
                        stats["compile_ok"] += 1

            elif arm == "plotly":
                code = parse_plotly_code(raw_text)
                parse_ok = code is not None and len(code.strip()) > 10
                if parse_ok:
                    stats["parse_ok"] += 1

                if parse_ok:
                    compile_ok, output_path, error_msg = execute_plotly_code(
                        code, str(csv_path), task_dir
                    )
                    if compile_ok:
                        stats["compile_ok"] += 1

            # Save result
            result = {
                "task_id": task_id,
                "arm": arm,
                "description": task_desc[:200],
                "parse_ok": parse_ok,
                "compile_ok": compile_ok,
                "output_path": output_path,
                "error": error_msg,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
            results_file.write(json.dumps(result) + "\n")
            results_file.flush()

            # Progress
            n = stats["total"]
            if n % 5 == 0 or n <= 3:
                parse_rate = stats["parse_ok"] / n if n else 0
                compile_rate = stats["compile_ok"] / n if n else 0
                print(
                    f"  [{task_id:>4d}] {arm:8s} | "
                    f"parse={stats['parse_ok']}/{n} ({100*parse_rate:.0f}%) "
                    f"compile={stats['compile_ok']}/{n} ({100*compile_rate:.0f}%)"
                )

    finally:
        results_file.close()

    # Final summary
    n = stats["total"]
    if n > 0:
        print(f"\n--- {arm.upper()} ARM SUMMARY ---")
        print(f"  Tasks: {n}")
        print(f"  Parse rate: {stats['parse_ok']}/{n} ({100*stats['parse_ok']/n:.1f}%)")
        print(f"  Compile/Execute rate: {stats['compile_ok']}/{n} ({100*stats['compile_ok']/n:.1f}%)")
        print(f"  Total input tokens: {stats['total_input_tokens']:,}")
        print(f"  Total output tokens: {stats['total_output_tokens']:,}")
        avg_out = stats["total_output_tokens"] / n
        print(f"  Avg output tokens/task: {avg_out:.0f}")


def main():
    parser = argparse.ArgumentParser(
        description="PandasPlotBench: DashML vs Raw Plotly"
    )
    parser.add_argument(
        "--arm", choices=["dashml", "plotly", "both"], default="both",
        help="Which arm to run (default: both)",
    )
    parser.add_argument(
        "--model", default="claude-sonnet-4-20250514",
        help="LLM model name",
    )
    parser.add_argument(
        "--split", default="test",
        help="Dataset split (default: test)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit to first N tasks",
    )
    parser.add_argument(
        "--output", default="benchmark/ppbench_results",
        help="Output directory",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.0,
        help="LLM temperature (default: 0.0)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Estimate cost without making API calls",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    cache_dir = Path("benchmark/cache")

    arms = ["dashml", "plotly"] if args.arm == "both" else [args.arm]

    for arm in arms:
        run_benchmark(
            arm=arm,
            model=args.model,
            split=args.split,
            limit=args.limit,
            output_dir=output_dir,
            cache_dir=cache_dir,
            dry_run=args.dry_run,
            temperature=args.temperature,
        )


if __name__ == "__main__":
    main()
