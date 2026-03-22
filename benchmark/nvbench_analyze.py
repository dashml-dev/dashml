"""
Analyze nvBench benchmark results.

Reads results JSONL files from both arms and computes comparison metrics.

Usage:
    python3 benchmark/nvbench_analyze.py
    python3 benchmark/nvbench_analyze.py --results benchmark/results
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List


def load_results(results_dir: Path, arm: str) -> List[dict]:
    """Load results JSONL for an arm."""
    path = results_dir / f"results_{arm}.jsonl"
    if not path.exists():
        return []
    results = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return results


def compute_summary(results: List[dict], k: int) -> dict:
    """Compute aggregate metrics from results."""
    if not results:
        return {}

    n = len(results)
    errors = sum(1 for r in results if "error" in r)
    valid = [r for r in results if "error" not in r]

    metrics = {"hit": 0.0, "recall": 0.0, "precision": 0.0, "f1": 0.0}
    for r in valid:
        m = r.get("metrics", {})
        for key in metrics:
            metrics[key] += m.get(key, 0.0)

    n_valid = len(valid) or 1
    return {
        "total": n,
        "errors": errors,
        "valid": len(valid),
        f"Hit@{k}": round(metrics["hit"] / n_valid, 4),
        f"Recall@{k}": round(metrics["recall"] / n_valid, 4),
        f"Precision@{k}": round(metrics["precision"] / n_valid, 4),
        f"F1@{k}": round(metrics["f1"] / n_valid, 4),
    }


def compute_by_mark(results: List[dict], k: int) -> dict:
    """Break down F1 by gold answer mark type."""
    by_mark = defaultdict(lambda: {"count": 0, "f1_sum": 0.0, "hit_sum": 0.0})

    for r in results:
        if "error" in r:
            continue
        marks = r.get("mark_types", [])
        m = r.get("metrics", {})
        for mark in marks:
            by_mark[mark]["count"] += 1
            by_mark[mark]["f1_sum"] += m.get("f1", 0.0)
            by_mark[mark]["hit_sum"] += m.get("hit", 0.0)

    result = {}
    for mark, data in sorted(by_mark.items(), key=lambda x: -x[1]["count"]):
        n = data["count"] or 1
        result[mark] = {
            "count": data["count"],
            f"F1@{k}": round(data["f1_sum"] / n, 4),
            f"Hit@{k}": round(data["hit_sum"] / n, 4),
        }
    return result


def compute_failure_modes(results: List[dict]) -> dict:
    """Analyze failure modes."""
    modes = Counter()
    for r in results:
        if "error" in r:
            modes["api_error"] += 1
        elif r.get("num_predictions", 0) == 0:
            modes["no_predictions"] += 1
        elif r.get("metrics", {}).get("hit", 0) == 0:
            modes["no_match"] += 1
        else:
            modes["has_match"] += 1
    return dict(modes.most_common())


def print_comparison(
    dashml_results: List[dict],
    vegalite_results: List[dict],
    k: int,
):
    """Print side-by-side comparison."""
    d_summary = compute_summary(dashml_results, k)
    v_summary = compute_summary(vegalite_results, k)

    print("\n" + "=" * 70)
    print("nvBench 2.0 Benchmark Results: DashML vs Vega-Lite")
    print("=" * 70)

    # Overall metrics
    print(f"\n{'OVERALL METRICS':=^70}")
    header = f"{'Metric':<20} {'DashML':>12} {'Vega-Lite':>12} {'Delta':>12}"
    print(header)
    print("-" * len(header))

    for metric in [f"Hit@{k}", f"Recall@{k}", f"Precision@{k}", f"F1@{k}"]:
        d_val = d_summary.get(metric, 0)
        v_val = v_summary.get(metric, 0)
        delta = d_val - v_val
        delta_str = f"{delta:+.4f}" if delta != 0 else "0.0000"
        winner = " ←" if delta > 0.005 else (" →" if delta < -0.005 else "")
        print(f"  {metric:<18} {d_val:>12.4f} {v_val:>12.4f} {delta_str:>12}{winner}")

    print(f"\n  {'Entries':<18} {d_summary.get('total', 0):>12} {v_summary.get('total', 0):>12}")
    print(f"  {'Errors':<18} {d_summary.get('errors', 0):>12} {v_summary.get('errors', 0):>12}")

    # By mark type
    d_marks = compute_by_mark(dashml_results, k)
    v_marks = compute_by_mark(vegalite_results, k)
    all_marks = sorted(set(list(d_marks.keys()) + list(v_marks.keys())))

    if all_marks:
        print(f"\n{'F1 BY MARK TYPE':=^70}")
        header = f"{'Mark':<12} {'Count':>6} {'DashML F1':>12} {'VL F1':>12} {'Delta':>12}"
        print(header)
        print("-" * len(header))
        for mark in all_marks:
            d = d_marks.get(mark, {})
            v = v_marks.get(mark, {})
            count = max(d.get("count", 0), v.get("count", 0))
            d_f1 = d.get(f"F1@{k}", 0)
            v_f1 = v.get(f"F1@{k}", 0)
            delta = d_f1 - v_f1
            delta_str = f"{delta:+.4f}" if delta != 0 else "0.0000"
            print(f"  {mark:<10} {count:>6} {d_f1:>12.4f} {v_f1:>12.4f} {delta_str:>12}")

    # Failure modes
    d_failures = compute_failure_modes(dashml_results)
    v_failures = compute_failure_modes(vegalite_results)

    print(f"\n{'FAILURE MODES':=^70}")
    header = f"{'Mode':<20} {'DashML':>12} {'Vega-Lite':>12}"
    print(header)
    print("-" * len(header))
    all_modes = sorted(set(list(d_failures.keys()) + list(v_failures.keys())))
    for mode in all_modes:
        print(f"  {mode:<18} {d_failures.get(mode, 0):>12} {v_failures.get(mode, 0):>12}")


def print_single_arm(results: List[dict], arm: str, k: int):
    """Print results for a single arm."""
    summary = compute_summary(results, k)
    marks = compute_by_mark(results, k)
    failures = compute_failure_modes(results)

    print(f"\n{'='*60}")
    print(f"{arm.upper()} ARM RESULTS")
    print(f"{'='*60}")

    print(f"\n  Entries: {summary.get('total', 0)}")
    print(f"  Errors: {summary.get('errors', 0)}")
    for metric in [f"Hit@{k}", f"Recall@{k}", f"Precision@{k}", f"F1@{k}"]:
        print(f"  {metric}: {summary.get(metric, 0):.4f}")

    if marks:
        print(f"\n  By mark type:")
        for mark, data in marks.items():
            print(f"    {mark}: F1={data.get(f'F1@{k}', 0):.4f} (n={data['count']})")

    if failures:
        print(f"\n  Failure modes:")
        for mode, count in failures.items():
            print(f"    {mode}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Analyze nvBench benchmark results")
    parser.add_argument("--results", default="benchmark/results",
                        help="Results directory")
    parser.add_argument("--k", type=int, default=3, help="K value for metrics")
    args = parser.parse_args()

    results_dir = Path(args.results)
    dashml_results = load_results(results_dir, "dashml")
    vegalite_results = load_results(results_dir, "vegalite")

    if dashml_results and vegalite_results:
        print_comparison(dashml_results, vegalite_results, args.k)
    elif dashml_results:
        print_single_arm(dashml_results, "dashml", args.k)
    elif vegalite_results:
        print_single_arm(vegalite_results, "vegalite", args.k)
    else:
        print(f"No results found in {results_dir}/")
        print("Run the benchmark first: python3 benchmark/nvbench_benchmark.py")

    # Save combined report
    report = {
        "dashml": compute_summary(dashml_results, args.k) if dashml_results else None,
        "vegalite": compute_summary(vegalite_results, args.k) if vegalite_results else None,
        "dashml_by_mark": compute_by_mark(dashml_results, args.k) if dashml_results else None,
        "vegalite_by_mark": compute_by_mark(vegalite_results, args.k) if vegalite_results else None,
    }
    report_path = results_dir / "analysis.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
