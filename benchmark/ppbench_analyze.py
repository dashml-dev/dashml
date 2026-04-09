"""
PandasPlotBench Results Analysis

Aggregates results from both arms across all three evaluation tiers:
- Tier 1: Validity (compilation success rate)
- Tier 2: Visual correctness (Claude Vision scores)
- Tier 3: Token efficiency

Usage:
    python3 benchmark/ppbench_analyze.py
    python3 benchmark/ppbench_analyze.py --results benchmark/ppbench_results
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional


def load_results(results_dir: Path, arm: str) -> List[dict]:
    """Load JSONL results for an arm."""
    path = results_dir / f"results_{arm}.jsonl"
    if not path.exists():
        return []
    results = []
    with open(path) as f:
        for line in f:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


def load_visual_scores(results_dir: Path) -> Dict[tuple, dict]:
    """Load visual scores keyed by (task_id, arm)."""
    path = results_dir / "visual_scores.jsonl"
    if not path.exists():
        return {}
    scores = {}
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
                scores[(r["task_id"], r["arm"])] = r
            except (json.JSONDecodeError, KeyError):
                continue
    return scores


def analyze_arm(results: List[dict], arm: str) -> dict:
    """Compute Tier 1 + Tier 3 metrics for one arm."""
    if not results:
        return {"arm": arm, "total": 0}

    total = len(results)
    parse_ok = sum(1 for r in results if r.get("parse_ok"))
    compile_ok = sum(1 for r in results if r.get("compile_ok"))
    errors = sum(1 for r in results if r.get("error") and not r.get("compile_ok"))

    # Token stats
    input_tokens = [r.get("input_tokens", 0) for r in results]
    output_tokens = [r.get("output_tokens", 0) for r in results]
    total_input = sum(input_tokens)
    total_output = sum(output_tokens)

    # Error categorization
    error_types = Counter()
    for r in results:
        err = r.get("error", "")
        if not err:
            continue
        # Categorize by first error type
        if "ModuleNotFoundError" in err or "ImportError" in err:
            error_types["import_error"] += 1
        elif "TypeError" in err:
            error_types["type_error"] += 1
        elif "ValueError" in err:
            error_types["value_error"] += 1
        elif "KeyError" in err:
            error_types["key_error"] += 1
        elif "AttributeError" in err:
            error_types["attribute_error"] += 1
        elif "FileNotFoundError" in err:
            error_types["file_not_found"] += 1
        elif "timed out" in err.lower():
            error_types["timeout"] += 1
        elif "ValidationError" in err or "DashMLValidator" in err:
            error_types["validation_error"] += 1
        elif "TransformerError" in err:
            error_types["transformer_error"] += 1
        elif "no output image" in err.lower():
            error_types["no_output"] += 1
        else:
            error_types["other"] += 1

    return {
        "arm": arm,
        "total": total,
        "parse_ok": parse_ok,
        "parse_rate": round(parse_ok / total, 4) if total else 0,
        "compile_ok": compile_ok,
        "compile_rate": round(compile_ok / total, 4) if total else 0,
        "validity_rate": round(compile_ok / total, 4) if total else 0,
        "error_count": errors,
        "error_types": dict(error_types.most_common()),
        "tokens": {
            "total_input": total_input,
            "total_output": total_output,
            "avg_input": round(total_input / total) if total else 0,
            "avg_output": round(total_output / total) if total else 0,
            "total": total_input + total_output,
        },
    }


def analyze_visual_scores(
    visual_scores: Dict[tuple, dict], arm: str
) -> Optional[dict]:
    """Compute Tier 2 metrics for one arm."""
    scores = [
        v["score"] for (tid, a), v in visual_scores.items()
        if a == arm and "score" in v
    ]
    if not scores:
        return None

    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    median = sorted_scores[n // 2] if n % 2 else (sorted_scores[n//2 - 1] + sorted_scores[n//2]) / 2

    # Distribution buckets
    buckets = {"0-29": 0, "30-49": 0, "50-69": 0, "70-89": 0, "90-100": 0}
    for s in scores:
        if s >= 90:
            buckets["90-100"] += 1
        elif s >= 70:
            buckets["70-89"] += 1
        elif s >= 50:
            buckets["50-69"] += 1
        elif s >= 30:
            buckets["30-49"] += 1
        else:
            buckets["0-29"] += 1

    good_count = sum(1 for s in scores if s >= 75)

    return {
        "arm": arm,
        "count": n,
        "mean": round(sum(scores) / n, 1),
        "median": median,
        "min": min(scores),
        "max": max(scores),
        "good_pct": round(good_count / n, 2) if n else 0,
        "good_count": good_count,
        "distribution": buckets,
    }


def load_expressible_ids(results_dir: Path) -> set:
    """Load expressible task IDs from audit results."""
    audit_path = results_dir / "audit_results.json"
    if not audit_path.exists():
        return set()
    with open(audit_path) as f:
        audit = json.load(f)
    return {
        i for i, t in enumerate(audit.get("per_task", []))
        if t.get("expressibility") in ("full", "partial")
    }


def run_analysis(results_dir: Path):
    """Run full analysis and print report."""
    # Load data
    dashml_results = load_results(results_dir, "dashml")
    plotly_results = load_results(results_dir, "plotly")
    visual_scores = load_visual_scores(results_dir)
    expressible_ids = load_expressible_ids(results_dir)

    if not dashml_results and not plotly_results:
        print("No results found. Run ppbench_benchmark.py first.")
        return

    # Tier 1: Validity
    dashml_stats = analyze_arm(dashml_results, "dashml")
    plotly_stats = analyze_arm(plotly_results, "plotly")

    # Tier 2: Visual
    dashml_visual = analyze_visual_scores(visual_scores, "dashml")
    plotly_visual = analyze_visual_scores(visual_scores, "plotly")

    # ── Print Report ──
    print("\n" + "=" * 70)
    print("PandasPlotBench — DashML vs Raw Plotly Results")
    print("=" * 70)

    # Tier 1
    print(f"\n{'TIER 1: VALIDITY (Compilation Success Rate)':=^70}")
    print(f"\n  {'Metric':<25s} {'DashML':>12s} {'Plotly':>12s} {'Delta':>10s}")
    print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*10}")

    for label, key in [
        ("Tasks", "total"),
        ("Parse rate", "parse_rate"),
        ("Compile/Exec rate", "compile_rate"),
    ]:
        d_val = dashml_stats.get(key, 0)
        p_val = plotly_stats.get(key, 0)
        if isinstance(d_val, float):
            delta = d_val - p_val
            print(f"  {label:<25s} {100*d_val:>11.1f}% {100*p_val:>11.1f}% {100*delta:>+9.1f}pp")
        else:
            print(f"  {label:<25s} {d_val:>12d} {p_val:>12d}")

    # Error breakdown
    for arm_name, stats in [("DashML", dashml_stats), ("Plotly", plotly_stats)]:
        errs = stats.get("error_types", {})
        if errs:
            print(f"\n  {arm_name} errors:")
            for err_type, count in sorted(errs.items(), key=lambda x: -x[1]):
                print(f"    {err_type:<25s} {count:>4d}")

    # Tier 2
    if dashml_visual or plotly_visual:
        print(f"\n{'TIER 2: VISUAL CORRECTNESS (Claude Vision Score 0-100)':=^70}")
        print(f"\n  {'Metric':<25s} {'DashML':>12s} {'Plotly':>12s} {'Delta':>10s}")
        print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*10}")

        for label, key in [("Count", "count"), ("Mean score", "mean"), ("Median", "median"), ("Good (>=75)", "good_pct")]:
            d_val = (dashml_visual or {}).get(key, 0)
            p_val = (plotly_visual or {}).get(key, 0)
            if isinstance(d_val, float) or (isinstance(d_val, int) and key != "count"):
                delta = d_val - p_val
                print(f"  {label:<25s} {d_val:>12.1f} {p_val:>12.1f} {delta:>+10.1f}")
            else:
                print(f"  {label:<25s} {d_val:>12d} {p_val:>12d}")

        # Distribution
        for arm_name, visual in [("DashML", dashml_visual), ("Plotly", plotly_visual)]:
            if visual:
                print(f"\n  {arm_name} score distribution:")
                for bucket, count in visual["distribution"].items():
                    bar = "#" * count
                    print(f"    {bucket:>8s}: {count:>3d} {bar}")

    # Tier 3
    print(f"\n{'TIER 3: TOKEN EFFICIENCY':=^70}")
    d_tok = dashml_stats.get("tokens", {})
    p_tok = plotly_stats.get("tokens", {})

    print(f"\n  {'Metric':<25s} {'DashML':>12s} {'Plotly':>12s} {'Ratio':>10s}")
    print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*10}")

    for label, key in [
        ("Avg output tokens", "avg_output"),
        ("Total output tokens", "total_output"),
        ("Total input tokens", "total_input"),
    ]:
        d_val = d_tok.get(key, 0)
        p_val = p_tok.get(key, 0)
        ratio = f"{p_val/d_val:.1f}x" if d_val > 0 else "N/A"
        print(f"  {label:<25s} {d_val:>12,d} {p_val:>12,d} {ratio:>10s}")

    # Cost estimate
    d_cost = (d_tok.get("total_input", 0) / 1e6 * 3) + (d_tok.get("total_output", 0) / 1e6 * 15)
    p_cost = (p_tok.get("total_input", 0) / 1e6 * 3) + (p_tok.get("total_output", 0) / 1e6 * 15)
    ratio = f"{p_cost/d_cost:.1f}x" if d_cost > 0 else "N/A"
    print(f"  {'Est. cost (Sonnet)':<25s} ${d_cost:>11.3f} ${p_cost:>11.3f} {ratio:>10s}")

    # ── Headline Summary ──
    print(f"\n{'HEADLINE SUMMARY':=^70}")
    d_validity = dashml_stats.get("validity_rate", 0)
    p_validity = plotly_stats.get("validity_rate", 0)
    delta_pp = 100 * (d_validity - p_validity)
    print(f"  DashML validity:  {100*d_validity:.1f}%")
    print(f"  Plotly validity:  {100*p_validity:.1f}%")
    print(f"  Delta:            {delta_pp:+.1f} percentage points")
    if d_tok.get("avg_output") and p_tok.get("avg_output"):
        ratio = p_tok["avg_output"] / d_tok["avg_output"]
        print(f"  Token ratio:      DashML uses {ratio:.1f}x fewer output tokens")

    # ── Expressible Subset ──
    if expressible_ids:
        print(f"\n{'EXPRESSIBLE SUBSET (' + str(len(expressible_ids)) + '/175 tasks, ' + f'{100*len(expressible_ids)/175:.1f}%' + ')':=^70}")

        d_expr = [r for r in dashml_results if r.get("task_id") in expressible_ids]
        p_expr = [r for r in plotly_results if r.get("task_id") in expressible_ids]
        d_expr_stats = analyze_arm(d_expr, "dashml")
        p_expr_stats = analyze_arm(p_expr, "plotly")

        print(f"\n  {'Metric':<25s} {'DashML':>12s} {'Plotly':>12s} {'Delta':>10s}")
        print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*10}")
        for label, key in [("Tasks", "total"), ("Compile/Exec rate", "compile_rate")]:
            d_val = d_expr_stats.get(key, 0)
            p_val = p_expr_stats.get(key, 0)
            if isinstance(d_val, float):
                delta = d_val - p_val
                print(f"  {label:<25s} {100*d_val:>11.1f}% {100*p_val:>11.1f}% {100*delta:>+9.1f}pp")
            else:
                print(f"  {label:<25s} {d_val:>12d} {p_val:>12d}")

        # Visual scores for expressible subset
        d_expr_visual = analyze_visual_scores(
            {k: v for k, v in visual_scores.items() if k[0] in expressible_ids}, "dashml"
        )
        p_expr_visual = analyze_visual_scores(
            {k: v for k, v in visual_scores.items() if k[0] in expressible_ids}, "plotly"
        )
        if d_expr_visual or p_expr_visual:
            print(f"\n  Visual scores (expressible subset):")
            print(f"  {'Metric':<25s} {'DashML':>12s} {'Plotly':>12s} {'Delta':>10s}")
            print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*10}")
            for label, key in [("Count", "count"), ("Mean task score", "mean"), ("Median", "median"), ("Good (>=75)", "good_pct")]:
                d_val = (d_expr_visual or {}).get(key, 0)
                p_val = (p_expr_visual or {}).get(key, 0)
                if isinstance(d_val, float):
                    delta = d_val - p_val
                    if key == "good_pct":
                        print(f"  {label:<25s} {100*d_val:>11.1f}% {100*p_val:>11.1f}% {100*delta:>+9.1f}pp")
                    else:
                        print(f"  {label:<25s} {d_val:>12.1f} {p_val:>12.1f} {delta:>+10.1f}")
                else:
                    print(f"  {label:<25s} {d_val:>12d} {p_val:>12d}")

    # ── Save JSON ──
    report = {
        "tier1_validity": {
            "dashml": dashml_stats,
            "plotly": plotly_stats,
            "delta_pp": round(delta_pp, 1),
        },
        "tier2_visual": {
            "dashml": dashml_visual,
            "plotly": plotly_visual,
        },
        "tier3_tokens": {
            "dashml": d_tok,
            "plotly": p_tok,
        },
    }
    analysis_path = results_dir / "analysis.json"
    with open(analysis_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to: {analysis_path}")


def main():
    parser = argparse.ArgumentParser(
        description="PandasPlotBench Results Analysis"
    )
    parser.add_argument(
        "--results", default="benchmark/ppbench_results",
        help="Results directory",
    )
    args = parser.parse_args()
    run_analysis(Path(args.results))


if __name__ == "__main__":
    main()
