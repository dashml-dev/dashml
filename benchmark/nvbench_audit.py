"""
Audit nvBench 2.0 gold specs to determine DashML feature coverage.

Downloads the dataset from HuggingFace, analyzes all 24,076 gold Vega-Lite
specs, and reports which features DashML can/cannot express.

Usage:
    python3 benchmark/nvbench_audit.py
    python3 benchmark/nvbench_audit.py --split test    # test split only (791 entries)

Output:
    - Printed summary report
    - benchmark/audit_results.json (detailed tallies)
    - benchmark/nvbench_metadata.json (column type mappings for evaluation)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from datasets import load_dataset


# --- DashML's current feature set (what it CAN express) ---

# nvBench uses "pie" (not standard VL "arc") for pie charts
DASHML_MARKS = {"bar", "line", "arc", "pie", "point", "rect", "boxplot"}

DASHML_AGGREGATIONS = {"count", "sum", "mean"}

# DashML filter ops that map to nvBench filter operators
DASHML_FILTER_OPS = {"equal", "gt", "lt", "gte", "lte", "oneOf", "range"}

# Encoding channels DashML can produce in bare mode
DASHML_CHANNELS = {"x", "y", "theta", "color", "size"}

# nvBench filter operator keys (from their gold spec format)
NVBENCH_FILTER_KEYS = {"equal", "lt", "lte", "gt", "gte", "range", "oneOf", "valid"}


def parse_gold_specs(entry: dict) -> list[dict]:
    """Parse gold_answer from an nvBench entry into a list of chart dicts."""
    gold = entry["gold_answer"]
    if isinstance(gold, str):
        gold = json.loads(gold)
    if isinstance(gold, dict):
        gold = [gold]
    return gold


def extract_filter_ops(transform_list: list[dict]) -> list[str]:
    """Extract filter operator names from a Vega-Lite transform array."""
    ops = []
    for t in transform_list:
        if "filter" not in t:
            continue
        f = t["filter"]
        if isinstance(f, dict):
            for key in NVBENCH_FILTER_KEYS:
                if key in f:
                    ops.append(key)
            # Check for expression-style filters (string in "filter" key within dict)
            if "expr" in f:
                ops.append("expr")
        elif isinstance(f, str):
            # Expression filter like "datum.x > 5"
            ops.append("expr_string")
    return ops


def extract_aggregates(encoding: dict) -> list[str]:
    """Extract all aggregate functions from encoding channels."""
    aggs = []
    for channel_name, channel_spec in encoding.items():
        if isinstance(channel_spec, dict) and "aggregate" in channel_spec:
            aggs.append(channel_spec["aggregate"])
    return aggs


def extract_channels(encoding: dict) -> list[str]:
    """Extract encoding channel names."""
    return list(encoding.keys())


def extract_sort_info(encoding: dict) -> list[str]:
    """Classify sort specifications in encoding channels."""
    sorts = []
    for channel_name, channel_spec in encoding.items():
        if not isinstance(channel_spec, dict):
            continue
        sort_val = channel_spec.get("sort")
        if sort_val is None:
            continue
        if isinstance(sort_val, str):
            sorts.append("string")
        elif isinstance(sort_val, dict):
            sorts.append("object")
        elif isinstance(sort_val, list):
            sorts.append("list")
        else:
            sorts.append(f"other:{type(sort_val).__name__}")
    return sorts


def has_bin(encoding: dict) -> tuple[bool, list[str]]:
    """Check if any encoding channel uses binning. Return (has_bin, channel_names)."""
    binned_channels = []
    for channel_name, channel_spec in encoding.items():
        if isinstance(channel_spec, dict) and channel_spec.get("bin"):
            binned_channels.append(channel_name)
    return bool(binned_channels), binned_channels


def has_timeunit(encoding: dict) -> tuple[bool, list[str]]:
    """Check if any encoding channel uses timeUnit."""
    tu_channels = []
    for channel_name, channel_spec in encoding.items():
        if isinstance(channel_spec, dict) and "timeUnit" in channel_spec:
            tu_channels.append(channel_name)
    return bool(tu_channels), tu_channels


def classify_expressibility(spec: dict) -> tuple[bool, list[str]]:
    """
    Determine if a gold spec is expressible in current DashML.
    Returns (is_expressible, list_of_gaps).
    """
    gaps = []
    mark = spec.get("mark", "")
    if isinstance(mark, dict):
        mark = mark.get("type", "")

    # Mark type check
    if mark not in DASHML_MARKS:
        gaps.append(f"mark:{mark}")

    # Encoding
    encoding = spec.get("encoding", {})

    # Channel check
    for ch in encoding:
        if ch not in DASHML_CHANNELS:
            gaps.append(f"channel:{ch}")

    # Aggregation check
    for agg in extract_aggregates(encoding):
        if agg not in DASHML_AGGREGATIONS:
            gaps.append(f"agg:{agg}")

    # Bin check (DashML supports bin: true on any chart type via ChartSpec.bin)
    has_bin_flag, binned_channels = has_bin(encoding)
    if has_bin_flag:
        # DashML can express bin on x for any mark type
        if binned_channels == ["x"]:
            pass  # expressible via bin: true
        else:
            # Bin on non-x channels (y, color) is not supported
            gaps.append(f"bin_on:{mark}:{','.join(binned_channels)}")

    # timeUnit check
    tu_flag, _ = has_timeunit(encoding)
    if tu_flag:
        gaps.append("timeUnit")

    # Transform check
    transforms = spec.get("transform", [])
    for t in transforms:
        if "filter" in t:
            f = t["filter"]
            if isinstance(f, dict):
                for key in f:
                    if key == "field":
                        continue
                    if key not in DASHML_FILTER_OPS:
                        gaps.append(f"filter_op:{key}")
            elif isinstance(f, str):
                gaps.append("filter_expr")
        elif "calculate" in t:
            gaps.append("transform:calculate")
        elif "window" in t:
            gaps.append("transform:window")
        elif "aggregate" in t:
            gaps.append("transform:aggregate")
        elif "bin" in t:
            gaps.append("transform:bin")
        elif "fold" in t:
            gaps.append("transform:fold")
        elif "lookup" in t:
            gaps.append("transform:lookup")
        elif "flatten" in t:
            gaps.append("transform:flatten")
        elif "density" in t:
            gaps.append("transform:density")
        elif "impute" in t:
            gaps.append("transform:impute")
        elif "stack" in t:
            gaps.append("transform:stack")
        elif "sample" in t:
            gaps.append("transform:sample")
        elif "sort" in t and "filter" not in t:
            gaps.append("transform:sort")
        else:
            # Unknown transform type
            known_keys = {"filter", "calculate", "window", "aggregate", "bin",
                         "fold", "lookup", "flatten", "density", "impute",
                         "stack", "sample", "sort", "as"}
            unknown = set(t.keys()) - known_keys
            if unknown:
                gaps.append(f"transform:unknown:{','.join(unknown)}")

    return len(gaps) == 0, gaps


def infer_column_types(table_schema: dict) -> dict[str, str]:
    """Infer quantitative vs nominal from column examples."""
    type_by_field = {}
    col_examples = table_schema.get("column_examples", {})

    for col_name, examples in col_examples.items():
        if not examples:
            type_by_field[col_name] = "nominal"
            continue

        numeric_count = 0
        for val in examples:
            if val is None:
                continue
            if isinstance(val, (int, float)):
                numeric_count += 1
            elif isinstance(val, str):
                try:
                    float(val)
                    numeric_count += 1
                except (ValueError, TypeError):
                    pass

        non_null = [v for v in examples if v is not None]
        if non_null and numeric_count / len(non_null) > 0.5:
            type_by_field[col_name] = "quantitative"
        else:
            type_by_field[col_name] = "nominal"

    return type_by_field


def run_audit(split: str | None = None):
    """Run the full audit."""
    print("Loading nvBench 2.0 dataset from HuggingFace...")
    if split:
        ds = load_dataset("TianqiLuo/nvBench2.0", split=split)
        entries = list(ds)
        print(f"Loaded {len(entries)} entries from '{split}' split")
    else:
        ds = load_dataset("TianqiLuo/nvBench2.0")
        entries = []
        for split_name in ds:
            entries.extend(list(ds[split_name]))
        print(f"Loaded {len(entries)} entries across all splits")

    # Counters
    marks = Counter()
    aggregates = Counter()
    filter_ops = Counter()
    channels = Counter()
    sort_formats = Counter()
    bin_count = 0
    bin_by_mark = Counter()
    timeunit_count = 0
    timeunit_values = Counter()
    transform_types = Counter()
    total_gold_specs = 0

    # Coverage classification
    expressible_specs = 0
    gap_reasons = Counter()  # Why specs aren't expressible
    gap_categories = Counter()  # Broad categories

    # Per-query coverage (is there at least one expressible gold answer?)
    queries_with_expressible = 0
    total_queries = len(entries)

    # Metadata for evaluation
    metadata = {}

    for i, entry in enumerate(entries):
        if i % 500 == 0:
            print(f"  Processing entry {i}/{len(entries)}...", end="\r")

        # Build column type metadata
        schema = entry.get("table_schema", {})
        if isinstance(schema, str):
            schema = json.loads(schema)
        csv_file = entry.get("csv_file", entry.get("db_id", f"entry_{i}"))
        if csv_file not in metadata:
            metadata[csv_file] = {"type_by_field": infer_column_types(schema)}

        # Analyze gold specs
        gold_specs = parse_gold_specs(entry)
        query_has_expressible = False

        for spec in gold_specs:
            total_gold_specs += 1

            # Mark
            mark = spec.get("mark", "")
            if isinstance(mark, dict):
                mark = mark.get("type", "")
            marks[mark] += 1

            # Encoding
            encoding = spec.get("encoding", {})

            # Channels
            for ch in extract_channels(encoding):
                channels[ch] += 1

            # Aggregates
            for agg in extract_aggregates(encoding):
                aggregates[agg] += 1

            # Sort
            for sort_fmt in extract_sort_info(encoding):
                sort_formats[sort_fmt] += 1

            # Bin
            b_flag, b_channels = has_bin(encoding)
            if b_flag:
                bin_count += 1
                bin_by_mark[mark] += 1

            # timeUnit
            tu_flag, tu_channels = has_timeunit(encoding)
            if tu_flag:
                timeunit_count += 1
                for ch_name in tu_channels:
                    ch_spec = encoding.get(ch_name, {})
                    if isinstance(ch_spec, dict):
                        timeunit_values[ch_spec.get("timeUnit", "unknown")] += 1

            # Transforms
            transforms = spec.get("transform", [])
            for t in transforms:
                if "filter" in t:
                    transform_types["filter"] += 1
                    for op in extract_filter_ops([t]):
                        filter_ops[op] += 1
                else:
                    for key in t:
                        if key != "as":
                            transform_types[key] += 1

            # Expressibility
            is_expr, gaps = classify_expressibility(spec)
            if is_expr:
                expressible_specs += 1
                query_has_expressible = True
            else:
                for gap in gaps:
                    gap_reasons[gap] += 1
                # Categorize
                gap_cats = set()
                for g in gaps:
                    cat = g.split(":")[0]
                    gap_cats.add(cat)
                for cat in gap_cats:
                    gap_categories[cat] += 1

        if query_has_expressible:
            queries_with_expressible += 1

    print()  # Clear progress line

    # --- Build report ---
    report = {
        "total_entries": len(entries),
        "total_gold_specs": total_gold_specs,
        "marks": dict(marks.most_common()),
        "aggregates": dict(aggregates.most_common()),
        "filter_ops": dict(filter_ops.most_common()),
        "channels": dict(channels.most_common()),
        "sort_formats": dict(sort_formats.most_common()),
        "bin_total": bin_count,
        "bin_by_mark": dict(bin_by_mark.most_common()),
        "timeunit_total": timeunit_count,
        "timeunit_values": dict(timeunit_values.most_common()),
        "transform_types": dict(transform_types.most_common()),
        "coverage": {
            "expressible_specs": expressible_specs,
            "total_specs": total_gold_specs,
            "expressible_pct": round(100 * expressible_specs / total_gold_specs, 2) if total_gold_specs else 0,
            "queries_with_expressible": queries_with_expressible,
            "total_queries": total_queries,
            "query_coverage_pct": round(100 * queries_with_expressible / total_queries, 2) if total_queries else 0,
        },
        "gap_reasons": dict(gap_reasons.most_common(30)),
        "gap_categories": dict(gap_categories.most_common()),
    }

    # --- Print report ---
    print("\n" + "=" * 70)
    print("nvBench 2.0 Feature Audit — DashML Coverage Report")
    print("=" * 70)

    print(f"\nDataset: {len(entries)} queries, {total_gold_specs} gold specs")

    print(f"\n{'HEADLINE COVERAGE':=^70}")
    print(f"  Gold specs expressible in DashML: {expressible_specs:,} / {total_gold_specs:,} ({report['coverage']['expressible_pct']}%)")
    print(f"  Queries with ≥1 expressible gold: {queries_with_expressible:,} / {total_queries:,} ({report['coverage']['query_coverage_pct']}%)")

    print(f"\n{'MARK TYPES':=^70}")
    for mark, count in marks.most_common():
        in_dashml = "✓" if mark in DASHML_MARKS else "✗"
        pct = 100 * count / total_gold_specs
        print(f"  {in_dashml} {mark:12s} {count:>6,} ({pct:5.1f}%)")

    print(f"\n{'AGGREGATION FUNCTIONS':=^70}")
    for agg, count in aggregates.most_common():
        in_dashml = "✓" if agg in DASHML_AGGREGATIONS else "✗"
        pct = 100 * count / total_gold_specs
        print(f"  {in_dashml} {agg:12s} {count:>6,} ({pct:5.1f}%)")

    print(f"\n{'FILTER OPERATORS':=^70}")
    for op, count in filter_ops.most_common():
        in_dashml = "✓" if op in DASHML_FILTER_OPS else "✗"
        pct = 100 * count / total_gold_specs
        print(f"  {in_dashml} {op:14s} {count:>6,} ({pct:5.1f}%)")

    print(f"\n{'ENCODING CHANNELS':=^70}")
    for ch, count in channels.most_common():
        in_dashml = "✓" if ch in DASHML_CHANNELS else "✗"
        pct = 100 * count / total_gold_specs
        print(f"  {in_dashml} {ch:12s} {count:>6,} ({pct:5.1f}%)")

    print(f"\n{'SORT FORMATS':=^70}")
    for fmt, count in sort_formats.most_common():
        pct = 100 * count / total_gold_specs
        print(f"    {fmt:12s} {count:>6,} ({pct:5.1f}%)")

    print(f"\n{'BINNING':=^70}")
    pct = 100 * bin_count / total_gold_specs if total_gold_specs else 0
    print(f"  Total specs with bin: {bin_count:,} ({pct:.1f}%)")
    for mark, count in bin_by_mark.most_common():
        print(f"    on {mark}: {count:,}")

    print(f"\n{'TIME UNIT':=^70}")
    pct = 100 * timeunit_count / total_gold_specs if total_gold_specs else 0
    print(f"  Total specs with timeUnit: {timeunit_count:,} ({pct:.1f}%)")
    for tu, count in timeunit_values.most_common():
        print(f"    {tu}: {count:,}")

    print(f"\n{'TRANSFORM TYPES':=^70}")
    for t_type, count in transform_types.most_common():
        pct = 100 * count / total_gold_specs
        print(f"    {t_type:14s} {count:>6,} ({pct:5.1f}%)")

    header = "TOP GAP REASONS (why specs are not expressible)"
    print(f"\n{header:=^70}")
    for reason, count in gap_reasons.most_common(15):
        pct = 100 * count / total_gold_specs
        print(f"    {reason:35s} {count:>6,} ({pct:5.1f}%)")

    print(f"\n{'GAP CATEGORIES':=^70}")
    for cat, count in gap_categories.most_common():
        pct = 100 * count / total_gold_specs
        print(f"    {cat:20s} {count:>6,} ({pct:5.1f}%)")

    # --- Save results ---
    out_dir = Path(__file__).parent
    results_path = out_dir / "audit_results.json"
    with open(results_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nDetailed results saved to: {results_path}")

    metadata_path = out_dir / "nvbench_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Column type metadata saved to: {metadata_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit nvBench 2.0 for DashML coverage")
    parser.add_argument("--split", type=str, default=None,
                        help="Specific split to audit (train/dev/test). Default: all splits.")
    args = parser.parse_args()
    run_audit(split=args.split)
