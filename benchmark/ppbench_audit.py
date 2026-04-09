"""
Audit PandasPlotBench tasks for DashML expressibility.

Analyzes all 175 tasks' reference matplotlib code to classify which
visualization types are needed and whether DashML can express them.

Usage:
    python3 benchmark/ppbench_audit.py
    python3 benchmark/ppbench_audit.py --limit 10   # quick test

Output:
    - Printed summary report
    - benchmark/ppbench_results/audit_results.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from datasets import load_dataset


# ── DashML chart type mapping ────────────────────────────────────────────────

# Matplotlib/Plotly patterns → DashML chart types
MATPLOTLIB_TO_DASHML = {
    # Bar charts
    "bar": "bar",
    "barh": "bar",
    "bar_label": None,  # annotation helper, not a chart type
    # Line
    "plot": "line",
    "step": "line",
    # Scatter
    "scatter": "scatter",
    # Pie
    "pie": "pie",
    # Histogram
    "hist": "histogram",
    "hist2d": "heatmap",
    # Area
    "fill_between": "area",
    "fill_betweenx": "area",
    "stackplot": "area",
    # Box
    "boxplot": "box",
    "box": "box",
    # Heatmap
    "imshow": "heatmap",
    "pcolormesh": "heatmap",
    "heatmap": "heatmap",
    "matshow": "heatmap",
    # Violin (not in DashML)
    "violinplot": None,
    "violin": None,
    # 3D (not in DashML)
    "plot_surface": None,
    "plot_wireframe": None,
    "scatter3D": None,
    "bar3d": None,
    # Contour (not in DashML)
    "contour": None,
    "contourf": None,
    # Polar (not in DashML)
    "polar": None,
    # Quiver/stream (not in DashML)
    "quiver": None,
    "streamplot": None,
    # Dendrogram (not in DashML)
    "dendrogram": None,
}

# Features that DashML cannot express
UNSUPPORTED_FEATURES = {
    "subplot",
    "subplots",
    "add_subplot",
    "twinx",
    "twiny",
    "secondary_yaxis",
    "annotate",
    "text",
    "arrow",
    "FancyArrowPatch",
    "axhline",
    "axvline",
    "axhspan",
    "axvspan",
    "errorbar",
    "stem",
    "eventplot",
    "hexbin",
    "tricontour",
    "tripcolor",
    "broken_barh",
}


def detect_chart_types(code: str) -> list[str]:
    """Detect matplotlib chart types used in reference code."""
    found = []

    # Match plt.xxx() or ax.xxx() or axes.xxx() patterns
    patterns = [
        r"(?:plt|ax|axes?|fig)\.(bar|barh|plot|scatter|pie|hist|hist2d|"
        r"fill_between|fill_betweenx|stackplot|boxplot|imshow|pcolormesh|"
        r"heatmap|matshow|violinplot|violin|plot_surface|plot_wireframe|"
        r"scatter3D|bar3d|contour|contourf|quiver|streamplot|step|errorbar|"
        r"stem|eventplot|hexbin|box)\s*\(",
        # sns.xxx() patterns
        r"sns\.(barplot|lineplot|scatterplot|boxplot|violinplot|heatmap|"
        r"histplot|kdeplot|pairplot|countplot|catplot|stripplot|swarmplot|"
        r"jointplot|displot|regplot|lmplot|clustermap)\s*\(",
    ]

    for pat in patterns:
        matches = re.findall(pat, code)
        found.extend(matches)

    return list(set(found))


def detect_unsupported_features(code: str) -> list[str]:
    """Detect features that DashML cannot express."""
    found = []

    for feature in UNSUPPORTED_FEATURES:
        if feature in code:
            found.append(feature)

    # Multi-subplot detection
    if re.search(r"fig,\s*(?:ax|axes)\s*=\s*plt\.subplots\(.+,.+\)", code):
        if "subplot" not in found:
            found.append("subplots")

    # 3D detection
    if "Axes3D" in code or "projection='3d'" in code or 'projection="3d"' in code:
        found.append("3d")

    # Log scale
    if "set_xscale" in code or "set_yscale" in code or "xscale" in code or "yscale" in code:
        if "log" in code:
            found.append("log_scale")

    # Dual axis
    if "twinx" in code or "twiny" in code:
        if "dual_axis" not in found:
            found.append("dual_axis")

    return list(set(found))


def map_to_dashml(chart_type: str) -> str | None:
    """Map a matplotlib/seaborn chart type to DashML chart type."""
    # Direct matplotlib mapping
    if chart_type in MATPLOTLIB_TO_DASHML:
        return MATPLOTLIB_TO_DASHML[chart_type]

    # Seaborn mappings
    seaborn_map = {
        "barplot": "bar",
        "countplot": "bar",
        "lineplot": "line",
        "scatterplot": "scatter",
        "regplot": "scatter",
        "lmplot": "scatter",
        "boxplot": "box",
        "histplot": "histogram",
        "displot": "histogram",
        "heatmap": "heatmap",
        "clustermap": "heatmap",
        "violinplot": None,
        "stripplot": None,
        "swarmplot": None,
        "kdeplot": None,
        "pairplot": None,
        "catplot": None,
        "jointplot": None,
    }
    return seaborn_map.get(chart_type)


def classify_task(code: str, task_description: str) -> dict:
    """Classify a single PandasPlotBench task for DashML expressibility.

    Returns dict with:
        chart_types: list of detected matplotlib chart types
        dashml_types: list of mapped DashML types (None for unsupported)
        unsupported_features: list of features DashML can't express
        expressibility: "full" | "partial" | "none"
        gaps: list of specific reasons for non-expressibility
    """
    chart_types = detect_chart_types(code)
    unsupported_features = detect_unsupported_features(code)

    dashml_types = []
    gaps = []

    for ct in chart_types:
        mapped = map_to_dashml(ct)
        dashml_types.append(mapped)
        if mapped is None:
            gaps.append(f"chart_type:{ct}")

    for feat in unsupported_features:
        gaps.append(f"feature:{feat}")

    # Determine expressibility
    if not gaps:
        expressibility = "full"
    elif any(d is not None for d in dashml_types) and not any(
        f.startswith("feature:subplot") or f.startswith("feature:3d")
        or f == "feature:dual_axis"
        for f in gaps
    ):
        expressibility = "partial"
    else:
        expressibility = "none"

    return {
        "chart_types": chart_types,
        "dashml_types": [d for d in dashml_types if d is not None],
        "unsupported_features": unsupported_features,
        "expressibility": expressibility,
        "gaps": gaps,
    }


def run_audit(limit: int | None = None):
    """Run the expressibility audit on PandasPlotBench."""
    print("Loading PandasPlotBench dataset from HuggingFace...")
    ds = load_dataset("JetBrains-Research/PandasPlotBench", split="test")
    entries = list(ds)
    if limit:
        entries = entries[:limit]
    print(f"Loaded {len(entries)} tasks")

    # Classify all tasks
    results = []
    chart_type_counter = Counter()
    dashml_type_counter = Counter()
    gap_counter = Counter()
    feature_counter = Counter()
    expressibility_counter = Counter()

    for i, entry in enumerate(entries):
        task_id = entry.get("id", i)
        code = entry.get("code_plot", "")
        description = entry.get("task__plot_description", "")

        classification = classify_task(code, description)
        classification["task_id"] = task_id
        classification["description_short"] = description[:100]
        results.append(classification)

        for ct in classification["chart_types"]:
            chart_type_counter[ct] += 1
        for dt in classification["dashml_types"]:
            dashml_type_counter[dt] += 1
        for gap in classification["gaps"]:
            gap_counter[gap] += 1
        for feat in classification["unsupported_features"]:
            feature_counter[feat] += 1
        expressibility_counter[classification["expressibility"]] += 1

    total = len(entries)

    # ── Print Report ──
    print("\n" + "=" * 70)
    print("PandasPlotBench — DashML Expressibility Audit")
    print("=" * 70)

    print(f"\nTotal tasks: {total}")
    full = expressibility_counter.get("full", 0)
    partial = expressibility_counter.get("partial", 0)
    none_ = expressibility_counter.get("none", 0)
    print(f"\n{'EXPRESSIBILITY SUMMARY':=^70}")
    print(f"  Full:    {full:>4d} / {total} ({100*full/total:.1f}%) - DashML can fully express")
    print(f"  Partial: {partial:>4d} / {total} ({100*partial/total:.1f}%) - Chart type OK, missing features")
    print(f"  None:    {none_:>4d} / {total} ({100*none_/total:.1f}%) - Chart type not supported")
    print(f"  Usable:  {full+partial:>4d} / {total} ({100*(full+partial)/total:.1f}%) - full + partial")

    print(f"\n{'MATPLOTLIB CHART TYPES DETECTED':=^70}")
    for ct, count in chart_type_counter.most_common():
        mapped = map_to_dashml(ct)
        marker = "+" if mapped else "-"
        mapped_str = f"-> {mapped}" if mapped else "-> NOT SUPPORTED"
        print(f"  {marker} {ct:20s} {count:>4d} ({100*count/total:.1f}%) {mapped_str}")

    print(f"\n{'DASHML CHART TYPES NEEDED':=^70}")
    for dt, count in dashml_type_counter.most_common():
        print(f"    {dt:20s} {count:>4d} ({100*count/total:.1f}%)")

    print(f"\n{'UNSUPPORTED FEATURES':=^70}")
    for feat, count in feature_counter.most_common():
        print(f"    {feat:25s} {count:>4d} ({100*count/total:.1f}%)")

    print(f"\n{'GAP REASONS':=^70}")
    for gap, count in gap_counter.most_common(20):
        print(f"    {gap:35s} {count:>4d} ({100*count/total:.1f}%)")

    # ── Save Results ──
    out_dir = Path(__file__).parent / "ppbench_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "total_tasks": total,
        "expressibility": {
            "full": full,
            "partial": partial,
            "none": none_,
            "usable": full + partial,
            "full_pct": round(100 * full / total, 1) if total else 0,
            "partial_pct": round(100 * partial / total, 1) if total else 0,
            "none_pct": round(100 * none_ / total, 1) if total else 0,
            "usable_pct": round(100 * (full + partial) / total, 1) if total else 0,
        },
        "chart_types_detected": dict(chart_type_counter.most_common()),
        "dashml_types_needed": dict(dashml_type_counter.most_common()),
        "unsupported_features": dict(feature_counter.most_common()),
        "gap_reasons": dict(gap_counter.most_common()),
        "per_task": results,
    }

    results_path = out_dir / "audit_results.json"
    with open(results_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nDetailed results saved to: {results_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Audit PandasPlotBench for DashML expressibility"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit to first N tasks (default: all 175)",
    )
    args = parser.parse_args()
    run_audit(limit=args.limit)
