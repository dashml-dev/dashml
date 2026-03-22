"""
nvBench 2.0 comparison logic.

Ports the evaluation functions from the nvBench paper:
- deep_compare_charts: recursive structural equality
- reverse_axes_if_needed: axis normalization using column types
- normalize_chart_order: canonical key ordering
- preprocess_charts: full pipeline

Reference: https://arxiv.org/html/2503.12880v2
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional


# Canonical key orderings from nvBench evaluation
_TOP_LEVEL_ORDER = ["mark", "encoding", "transform"]
_CHANNEL_ORDER = ["x", "y", "theta", "color", "size"]
_PROP_ORDER = ["field", "aggregate", "bin", "sort", "timeUnit"]
_FILTER_KEY_ORDER = ["field", "equal", "lt", "lte", "gt", "gte", "range", "oneOf", "valid"]


def deep_compare_charts(chart1: Any, chart2: Any) -> bool:
    """
    Recursive structural equality for Vega-Lite chart specs.

    - Dicts: compare key-by-key (order-independent)
    - Lists: compare as unordered sets (each element must find a match)
    - Scalars: direct equality
    """
    if type(chart1) != type(chart2):
        return False

    if isinstance(chart1, dict):
        if set(chart1.keys()) != set(chart2.keys()):
            return False
        return all(deep_compare_charts(chart1[k], chart2[k]) for k in chart1)

    if isinstance(chart1, list):
        if len(chart1) != len(chart2):
            return False
        # Unordered set matching: each element in chart1 must match one in chart2
        used = [False] * len(chart2)
        for item1 in chart1:
            found = False
            for j, item2 in enumerate(chart2):
                if not used[j] and deep_compare_charts(item1, item2):
                    used[j] = True
                    found = True
                    break
            if not found:
                return False
        return True

    return chart1 == chart2


def reverse_axes_if_needed(chart: dict, type_by_field: Dict[str, str]) -> dict:
    """
    Axis normalization: swap x/y when the assignment is ambiguous.

    Rules (from nvBench paper):
    1. If both x and y are quantitative and x_field > y_field alphabetically, swap x/y
    2. For bar/line/boxplot: if x is quantitative and y is not, swap x/y
    """
    chart = copy.deepcopy(chart)
    encoding = chart.get("encoding", {})

    x_spec = encoding.get("x", {})
    y_spec = encoding.get("y", {})

    if not x_spec or not y_spec:
        return chart

    x_field = x_spec.get("field", "")
    y_field = y_spec.get("field", "")

    # Guard against non-hashable field values (e.g., lists)
    if not isinstance(x_field, str) or not isinstance(y_field, str):
        return chart

    x_type = type_by_field.get(x_field, "nominal")
    y_type = type_by_field.get(y_field, "nominal")

    mark = chart.get("mark", "")

    # Rule 1: both quantitative, alphabetical normalization
    if x_type == "quantitative" and y_type == "quantitative":
        if x_field > y_field:
            encoding["x"], encoding["y"] = encoding["y"], encoding["x"]

    # Rule 2: bar/line/boxplot with wrong orientation
    elif mark in ("bar", "line", "boxplot"):
        if x_type == "quantitative" and y_type != "quantitative":
            encoding["x"], encoding["y"] = encoding["y"], encoding["x"]

    chart["encoding"] = encoding
    return chart


def _order_dict(d: dict, key_order: List[str]) -> dict:
    """Reorder dict keys according to a canonical order, unknown keys go last."""
    ordered = {}
    for k in key_order:
        if k in d:
            ordered[k] = d[k]
    for k in d:
        if k not in ordered:
            ordered[k] = d[k]
    return ordered


def normalize_chart_order(chart: dict) -> dict:
    """Normalize key ordering for deterministic comparison."""
    chart = copy.deepcopy(chart)

    # Normalize encoding channels
    if "encoding" in chart:
        encoding = chart["encoding"]
        for channel in encoding:
            if isinstance(encoding[channel], dict):
                encoding[channel] = _order_dict(encoding[channel], _PROP_ORDER)
        chart["encoding"] = _order_dict(encoding, _CHANNEL_ORDER)

    # Normalize transforms
    if "transform" in chart:
        for i, t in enumerate(chart["transform"]):
            if isinstance(t, dict) and "filter" in t and isinstance(t["filter"], dict):
                chart["transform"][i]["filter"] = _order_dict(t["filter"], _FILTER_KEY_ORDER)

    # Normalize top level
    chart = _order_dict(chart, _TOP_LEVEL_ORDER)
    return chart


def remove_empty_transform(charts: List[dict]) -> List[dict]:
    """Remove empty transform arrays."""
    result = []
    for c in charts:
        c = copy.deepcopy(c)
        if "transform" in c and not c["transform"]:
            del c["transform"]
        result.append(c)
    return result


def remove_duplicates(charts: List[dict]) -> List[dict]:
    """Deduplicate charts by JSON serialization."""
    seen = set()
    result = []
    for c in charts:
        key = json.dumps(c, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


def preprocess_charts(
    charts: List[dict],
    type_by_field: Optional[Dict[str, str]] = None,
) -> List[dict]:
    """
    Full preprocessing pipeline for chart comparison.

    1. Reverse axes if needed (using column type metadata)
    2. Normalize key ordering
    3. Remove empty transforms
    4. Deduplicate
    """
    if type_by_field is None:
        type_by_field = {}

    result = []
    for c in charts:
        c = reverse_axes_if_needed(c, type_by_field)
        c = normalize_chart_order(c)
        result.append(c)

    result = remove_empty_transform(result)
    result = remove_duplicates(result)
    return result


def compute_metrics(
    predictions: List[dict],
    gold_answers: List[dict],
    type_by_field: Optional[Dict[str, str]] = None,
    k: int = 3,
) -> Dict[str, float]:
    """
    Compute nvBench evaluation metrics.

    Args:
        predictions: List of predicted chart specs (up to K)
        gold_answers: List of gold chart specs (1-to-many)
        type_by_field: Column type mappings for axis normalization
        k: Number of predictions to evaluate

    Returns:
        Dict with hit, recall, precision, f1 at the given K
    """
    # Preprocess both sides
    preds = preprocess_charts(predictions[:k], type_by_field)
    golds = preprocess_charts(gold_answers, type_by_field)

    if not golds:
        return {"hit": 0.0, "recall": 0.0, "precision": 0.0, "f1": 0.0}

    # Count matches: how many predictions match a gold answer
    matches = 0
    matched_golds = set()
    for p in preds:
        for gi, g in enumerate(golds):
            if gi not in matched_golds and deep_compare_charts(p, g):
                matches += 1
                matched_golds.add(gi)
                break

    hit = 1.0 if matches > 0 else 0.0
    recall = len(matched_golds) / len(golds) if golds else 0.0
    precision = matches / k if k > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"hit": hit, "recall": recall, "precision": precision, "f1": f1}
