"""
Compute metrics at multiple K values from K=5 cached responses.

Usage:
    python3 benchmark/nvbench_multik.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datasets import load_dataset

from benchmark.nvbench_compare import compute_metrics
from benchmark.nvbench_prompts import get_system_prompt, build_user_prompt
from benchmark.nvbench_benchmark import (
    parse_dashml_predictions,
    compile_dashml_to_bare,
    parse_vegalite_predictions,
    strip_vegalite_to_bare,
)

K_VALUES = [1, 2, 3, 5]


def score_at_k(arm: str, k_max: int = 5):
    """Score an arm at multiple K values using cached responses."""
    ds = load_dataset("TianqiLuo/nvBench2.0", split="test")
    metadata = json.load(open("benchmark/nvbench_metadata.json"))
    sys_prompt = get_system_prompt(arm, k_max)

    # Accumulators per K
    totals = {k: {"f1": 0, "hit": 0, "recall": 0, "precision": 0, "n": 0} for k in K_VALUES}
    by_mark = {k: defaultdict(lambda: {"n": 0, "f1": 0, "hit": 0}) for k in K_VALUES}

    for idx, entry in enumerate(ds):
        schema = json.loads(entry["table_schema"]) if isinstance(entry["table_schema"], str) else entry["table_schema"]
        gold = json.loads(entry["gold_answer"]) if isinstance(entry["gold_answer"], str) else entry["gold_answer"]
        if isinstance(gold, dict):
            gold = [gold]

        csv_file = entry.get("csv_file", entry.get("db_id", f"entry_{idx}"))
        type_by_field = metadata.get(csv_file, {}).get("type_by_field", {})

        user_prompt = build_user_prompt(entry["nl_query"], schema, k_max)
        key = hashlib.sha256(f"claude-sonnet-4-20250514::{sys_prompt}::{user_prompt}".encode()).hexdigest()[:16]
        cache = Path(f"benchmark/cache/{key}.txt")
        if not cache.exists():
            continue

        raw = cache.read_text()

        # Parse all k_max predictions
        if arm == "dashml":
            specs = parse_dashml_predictions(raw, k_max)
            all_preds = []
            for s in specs:
                bare = compile_dashml_to_bare(s)
                if bare:
                    all_preds.extend(bare)
        else:
            vl_specs = parse_vegalite_predictions(raw, k_max)
            all_preds = [strip_vegalite_to_bare(s) for s in vl_specs]

        # Get mark types from gold
        marks = set()
        for g in gold:
            m = g.get("mark", "")
            if isinstance(m, dict):
                m = m.get("type", "")
            marks.add(m)

        # Score at each K
        for k in K_VALUES:
            preds_at_k = all_preds[:k]
            m = compute_metrics(preds_at_k, gold, type_by_field, k=k)
            totals[k]["f1"] += m["f1"]
            totals[k]["hit"] += m["hit"]
            totals[k]["recall"] += m["recall"]
            totals[k]["precision"] += m["precision"]
            totals[k]["n"] += 1
            for mark in marks:
                by_mark[k][mark]["n"] += 1
                by_mark[k][mark]["f1"] += m["f1"]
                by_mark[k][mark]["hit"] += m["hit"]

    return totals, by_mark


def main():
    print("Computing multi-K scores from cached responses...\n")

    results = {}
    for arm in ["dashml", "vegalite"]:
        print(f"Scoring {arm}...")
        totals, by_mark = score_at_k(arm, k_max=5)
        results[arm] = {"totals": totals, "by_mark": by_mark}

    # Print comparison table
    print("\n" + "=" * 70)
    print("Multi-K Results: DashML vs Vega-Lite")
    print("=" * 70)

    print(f"\n{'':15s}", end="")
    for k in K_VALUES:
        print(f"  {'K='+str(k):^18s}", end="")
    print()

    print(f"{'':15s}", end="")
    for k in K_VALUES:
        print(f"  {'DashML':>8s} {'VL':>8s}", end="")
    print()

    print("-" * (15 + 18 * len(K_VALUES)))

    for metric in ["f1", "hit", "precision", "recall"]:
        label = {"f1": "F1", "hit": "Hit", "precision": "Precision", "recall": "Recall"}[metric]
        print(f"{label+'@K':15s}", end="")
        for k in K_VALUES:
            d = results["dashml"]["totals"][k]
            v = results["vegalite"]["totals"][k]
            dn = d["n"] or 1
            vn = v["n"] or 1
            print(f"  {d[metric]/dn:>8.4f} {v[metric]/vn:>8.4f}", end="")
        print()

    # Delta row
    print(f"{'F1 Delta':15s}", end="")
    for k in K_VALUES:
        d = results["dashml"]["totals"][k]
        v = results["vegalite"]["totals"][k]
        dn = d["n"] or 1
        vn = v["n"] or 1
        delta = d["f1"] / dn - v["f1"] / vn
        print(f"  {delta:>+8.4f} {'':>8s}", end="")
    print()

    # By mark type at K=3
    print(f"\n{'F1@3 by mark type':=^70}")
    print(f"{'Mark':10s} {'DashML':>8s} {'VL':>8s} {'Delta':>8s} {'Winner':>8s}")
    d3 = results["dashml"]["by_mark"][3]
    v3 = results["vegalite"]["by_mark"][3]
    all_marks = sorted(set(list(d3.keys()) + list(v3.keys())))
    for m in all_marks:
        df = d3[m]["f1"] / d3[m]["n"] if d3[m]["n"] else 0
        vf = v3[m]["f1"] / v3[m]["n"] if v3[m]["n"] else 0
        delta = df - vf
        w = "DashML" if delta > 0.005 else ("VL" if delta < -0.005 else "Tie")
        print(f"  {m:8s} {df:>8.3f} {vf:>8.3f} {delta:>+8.3f} {w:>8s}")

    # Save results
    output = {}
    for arm in ["dashml", "vegalite"]:
        output[arm] = {}
        for k in K_VALUES:
            t = results[arm]["totals"][k]
            n = t["n"] or 1
            output[arm][f"K={k}"] = {
                "f1": round(t["f1"] / n, 4),
                "hit": round(t["hit"] / n, 4),
                "precision": round(t["precision"] / n, 4),
                "recall": round(t["recall"] / n, 4),
                "n": t["n"],
            }

    with open("benchmark/results/multik_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to benchmark/results/multik_results.json")


if __name__ == "__main__":
    main()
