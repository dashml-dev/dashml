"""
nvBench 2.0 Benchmark: DashML vs Vega-Lite LLM Accuracy

Runs two arms:
  A) NL → LLM → .dashml YAML → VegaLiteTransformer(bare) → compare with gold
  B) NL → LLM → Vega-Lite JSON → strip → compare with gold

Usage:
    python3 benchmark/nvbench_benchmark.py --arm both --model claude-sonnet-4-20250514 --k 3
    python3 benchmark/nvbench_benchmark.py --arm dashml --limit 10  # quick test
    python3 benchmark/nvbench_benchmark.py --dry-run                # estimate cost
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datasets import load_dataset

from benchmark.nvbench_compare import compute_metrics, preprocess_charts
from benchmark.nvbench_prompts import build_user_prompt, get_system_prompt


# ── LLM Client (borrowed from experiments/llm_generation/run_experiment.py) ──

class LLMClient:
    """Thin wrapper around LLM APIs (Anthropic / OpenAI)."""

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
            return response.choices[0].message.content


# ── Response Parsing ─────────────────────────────────────────────────────────

def clean_response(text: str) -> str:
    """Strip markdown code fences and whitespace."""
    text = text.strip()
    # Remove code fences
    text = re.sub(r"^```(?:yaml|json|vegalite|vl)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def parse_dashml_predictions(raw: str, k: int) -> List[dict]:
    """Parse K .dashml YAML specs from LLM response."""
    raw = clean_response(raw)
    # Split on --- separator (YAML document separator)
    docs = re.split(r"\n---\s*\n", raw)
    specs = []
    for doc in docs[:k]:
        doc = doc.strip()
        if not doc:
            continue
        try:
            spec = yaml.safe_load(doc)
            if isinstance(spec, dict):
                specs.append(spec)
        except yaml.YAMLError:
            continue
    return specs


def parse_vegalite_predictions(raw: str, k: int) -> List[dict]:
    """Parse K Vega-Lite JSON specs from LLM response."""
    raw = clean_response(raw)
    # Try splitting on --- separator first
    docs = re.split(r"\n---\s*\n", raw)
    specs = []
    for doc in docs[:k]:
        doc = doc.strip()
        if not doc:
            continue
        try:
            spec = json.loads(doc)
            if isinstance(spec, dict):
                specs.append(spec)
            elif isinstance(spec, list):
                specs.extend(s for s in spec if isinstance(s, dict))
        except json.JSONDecodeError:
            # Try extracting JSON objects from text
            for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", doc):
                try:
                    obj = json.loads(match.group())
                    if isinstance(obj, dict) and "mark" in obj:
                        specs.append(obj)
                except json.JSONDecodeError:
                    continue
    return specs[:k]


def strip_vegalite_to_bare(spec: dict) -> dict:
    """Strip a Vega-Lite spec to bare {mark, encoding, transform} format."""
    bare_channel_keys = {"field", "aggregate", "bin", "sort", "timeUnit"}

    mark = spec.get("mark", "bar")
    if isinstance(mark, dict):
        mark = mark.get("type", "bar")

    encoding = {}
    for channel, props in spec.get("encoding", {}).items():
        if channel in ("tooltip", "shape"):
            continue
        if isinstance(props, dict):
            stripped = {k: v for k, v in props.items() if k in bare_channel_keys}
            if stripped:
                encoding[channel] = stripped

    result = {"mark": mark, "encoding": encoding}
    transforms = spec.get("transform", [])
    if transforms:
        result["transform"] = transforms
    return result


# ── DashML Compilation Pipeline ──────────────────────────────────────────────

def compile_dashml_to_bare(spec: dict) -> Optional[List[dict]]:
    """
    Compile a .dashml spec to bare Vega-Lite format via the transformer.
    Returns list of {mark, encoding, transform} dicts, or None on failure.
    """
    try:
        from dashml_new.core.validator import DashMLValidator
        from dashml_new.core.normalizer import DashMLNormalizer
        from dashml_new.transformers.vegalite import VegaLiteTransformer

        # Validate
        validator = DashMLValidator()
        validator.validate(spec)

        # Normalize (needs source_file for path resolution)
        normalizer = DashMLNormalizer()
        normalized = normalizer.normalize(spec, source_file="benchmark_input.dashml")

        # Build bare VL
        transformer = VegaLiteTransformer(bare=True)
        output = transformer.build(normalized)
        charts = json.loads(output)

        if isinstance(charts, list):
            return charts
        elif isinstance(charts, dict):
            return [charts]
        return None

    except Exception:
        return None


# ── Caching ──────────────────────────────────────────────────────────────────

def _cache_key(system_prompt: str, user_prompt: str, model: str) -> str:
    """Generate cache key from prompt + model."""
    content = f"{model}::{system_prompt}::{user_prompt}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def load_cached_response(cache_dir: Path, key: str) -> Optional[str]:
    path = cache_dir / f"{key}.txt"
    if path.exists():
        return path.read_text()
    return None


def save_cached_response(cache_dir: Path, key: str, response: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.txt").write_text(response)


# ── Main Benchmark ───────────────────────────────────────────────────────────

def run_benchmark(
    arm: str,
    model: str,
    k: int,
    split: str,
    limit: Optional[int],
    output_dir: Path,
    cache_dir: Path,
    metadata_path: Path,
    dry_run: bool = False,
    temperature: float = 0.0,
):
    """Run the benchmark for one arm."""
    print(f"\n{'='*60}")
    print(f"Running {arm.upper()} arm | model={model} | k={k} | split={split}")
    print(f"{'='*60}\n")

    # Load dataset
    ds = load_dataset("TianqiLuo/nvBench2.0", split=split)
    entries = list(ds)
    if limit:
        entries = entries[:limit]
    print(f"Loaded {len(entries)} entries")

    # Load column type metadata
    type_metadata = {}
    if metadata_path.exists():
        with open(metadata_path) as f:
            type_metadata = json.load(f)

    # Load existing results for resume
    results_path = output_dir / f"results_{arm}.jsonl"
    completed_ids = set()
    if results_path.exists():
        with open(results_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    completed_ids.add(r["entry_idx"])
                except (json.JSONDecodeError, KeyError):
                    continue
        print(f"Resuming: {len(completed_ids)} entries already completed")

    # Cost estimation for dry run
    if dry_run:
        system_prompt = get_system_prompt(arm, k)
        avg_user_tokens = 300  # estimated
        avg_sys_tokens = len(system_prompt.split()) * 1.3
        avg_output_tokens = 200 * k
        total_input = (avg_sys_tokens + avg_user_tokens) * len(entries)
        total_output = avg_output_tokens * len(entries)
        # Claude Sonnet pricing (rough): $3/M input, $15/M output
        est_cost = (total_input / 1e6 * 3) + (total_output / 1e6 * 15)
        print(f"\n--- DRY RUN COST ESTIMATE ({arm}) ---")
        print(f"  Entries: {len(entries)}")
        print(f"  Est. input tokens: {total_input:,.0f}")
        print(f"  Est. output tokens: {total_output:,.0f}")
        print(f"  Est. cost (Claude Sonnet): ${est_cost:.2f}")
        return

    # Initialize LLM client
    client = LLMClient(model=model, temperature=temperature)
    system_prompt = get_system_prompt(arm, k)

    # Process entries
    output_dir.mkdir(parents=True, exist_ok=True)
    results_file = open(results_path, "a")

    stats = {
        "total": 0, "parse_ok": 0, "compile_ok": 0,
        "hit_sum": 0.0, "recall_sum": 0.0, "precision_sum": 0.0, "f1_sum": 0.0,
    }

    try:
        for idx, entry in enumerate(entries):
            if idx in completed_ids:
                continue

            stats["total"] += 1

            # Parse entry
            nl_query = entry["nl_query"]
            schema = entry.get("table_schema", {})
            if isinstance(schema, str):
                schema = json.loads(schema)
            gold_raw = entry["gold_answer"]
            if isinstance(gold_raw, str):
                gold_raw = json.loads(gold_raw)
            if isinstance(gold_raw, dict):
                gold_raw = [gold_raw]

            # Get column type metadata
            csv_file = entry.get("csv_file", entry.get("db_id", f"entry_{idx}"))
            entry_metadata = type_metadata.get(csv_file, {})
            type_by_field = entry_metadata.get("type_by_field", {})

            # Build user prompt
            user_prompt = build_user_prompt(nl_query, schema, k)

            # Check cache
            cache_key = _cache_key(system_prompt, user_prompt, model)
            cached = load_cached_response(cache_dir, cache_key)

            if cached:
                raw_response = cached
            else:
                try:
                    raw_response = client.generate(system_prompt, user_prompt)
                    save_cached_response(cache_dir, cache_key, raw_response)
                except Exception as e:
                    print(f"  [{idx}] API error: {e}")
                    result = {
                        "entry_idx": idx, "arm": arm, "error": str(e),
                        "metrics": {"hit": 0, "recall": 0, "precision": 0, "f1": 0},
                    }
                    results_file.write(json.dumps(result) + "\n")
                    results_file.flush()
                    continue

            # Parse predictions
            parse_error = None
            predictions = []
            bare_predictions = []

            if arm == "dashml":
                dashml_specs = parse_dashml_predictions(raw_response, k)
                stats["parse_ok"] += 1 if dashml_specs else 0

                for spec in dashml_specs:
                    compiled = compile_dashml_to_bare(spec)
                    if compiled:
                        bare_predictions.extend(compiled)

                stats["compile_ok"] += 1 if bare_predictions else 0

            elif arm == "vegalite":
                vl_specs = parse_vegalite_predictions(raw_response, k)
                stats["parse_ok"] += 1 if vl_specs else 0

                for spec in vl_specs:
                    bare_predictions.append(strip_vegalite_to_bare(spec))

                stats["compile_ok"] += 1 if bare_predictions else 0

            # Compute metrics
            metrics = compute_metrics(bare_predictions, gold_raw, type_by_field, k)
            stats["hit_sum"] += metrics["hit"]
            stats["recall_sum"] += metrics["recall"]
            stats["precision_sum"] += metrics["precision"]
            stats["f1_sum"] += metrics["f1"]

            # Save result
            result = {
                "entry_idx": idx,
                "arm": arm,
                "nl_query": nl_query,
                "num_predictions": len(bare_predictions),
                "num_gold": len(gold_raw),
                "metrics": metrics,
                "mark_types": list(set(g.get("mark", "") for g in gold_raw)),
            }
            results_file.write(json.dumps(result) + "\n")
            results_file.flush()

            # Progress
            n = stats["total"]
            if n % 10 == 0 or n <= 5:
                avg_f1 = stats["f1_sum"] / n if n else 0
                avg_hit = stats["hit_sum"] / n if n else 0
                print(
                    f"  [{idx:>4d}] {arm:8s} | "
                    f"parse={stats['parse_ok']}/{n} "
                    f"compile={stats['compile_ok']}/{n} | "
                    f"Hit@{k}={avg_hit:.3f} F1@{k}={avg_f1:.3f}"
                )

    finally:
        results_file.close()

    # Final summary
    n = stats["total"]
    if n > 0:
        print(f"\n--- {arm.upper()} ARM SUMMARY ---")
        print(f"  Entries: {n}")
        print(f"  Parse rate: {stats['parse_ok']}/{n} ({100*stats['parse_ok']/n:.1f}%)")
        print(f"  Compile rate: {stats['compile_ok']}/{n} ({100*stats['compile_ok']/n:.1f}%)")
        print(f"  Hit@{k}: {stats['hit_sum']/n:.4f}")
        print(f"  Recall@{k}: {stats['recall_sum']/n:.4f}")
        print(f"  Precision@{k}: {stats['precision_sum']/n:.4f}")
        print(f"  F1@{k}: {stats['f1_sum']/n:.4f}")


def main():
    parser = argparse.ArgumentParser(description="nvBench 2.0 Benchmark: DashML vs Vega-Lite")
    parser.add_argument("--arm", choices=["dashml", "vegalite", "both"], default="both",
                        help="Which arm to run (default: both)")
    parser.add_argument("--model", default="claude-sonnet-4-20250514",
                        help="LLM model name")
    parser.add_argument("--k", type=int, default=3,
                        help="Number of predictions per query (default: 3)")
    parser.add_argument("--split", default="test",
                        help="Dataset split (default: test)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to first N entries")
    parser.add_argument("--output", default="benchmark/results",
                        help="Output directory")
    parser.add_argument("--temperature", type=float, default=0.0,
                        help="LLM temperature (default: 0.0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Estimate cost without making API calls")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint (default: true)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    cache_dir = Path("benchmark/cache")
    metadata_path = Path("benchmark/nvbench_metadata.json")

    arms = ["dashml", "vegalite"] if args.arm == "both" else [args.arm]

    for arm in arms:
        run_benchmark(
            arm=arm,
            model=args.model,
            k=args.k,
            split=args.split,
            limit=args.limit,
            output_dir=output_dir,
            cache_dir=cache_dir,
            metadata_path=metadata_path,
            dry_run=args.dry_run,
            temperature=args.temperature,
        )


if __name__ == "__main__":
    main()
