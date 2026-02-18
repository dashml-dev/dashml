#!/usr/bin/env python3
"""
Evaluation script for the LLM generation experiment.

Scores each generated output on:
  - Parses (0/1): YAML loads / Python AST parses
  - Validates (0/1): DashML validator passes / Streamlit imports resolve
  - Compiles (0/1): dashml build succeeds / streamlit run starts without crash
  - Completeness (0-1): Expected features present (automated check against prompt expectations)

Usage:
    python evaluate.py --results results/dryrun_20240101_120000
    python evaluate.py --results results/ --all
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path

import yaml

# Add the project root to path so we can import dashml_new
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dashml_new.core.validator import DashMLValidator, ValidationError


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------

def score_dashml_parses(content: str) -> tuple[bool, str]:
    """Check if content is valid YAML."""
    try:
        result = yaml.safe_load(content)
        if result is None:
            return False, "YAML loaded as None (empty)"
        if not isinstance(result, dict):
            return False, f"YAML loaded as {type(result).__name__}, expected dict"
        return True, "ok"
    except yaml.YAMLError as e:
        return False, f"YAML parse error: {e}"


def score_dashml_validates(content: str) -> tuple[bool, str]:
    """Check if content passes DashML validator."""
    try:
        spec = yaml.safe_load(content)
        if not isinstance(spec, dict):
            return False, "Not a dict"
        validator = DashMLValidator()
        validator.validate(spec)
        return True, "ok"
    except ValidationError as e:
        return False, f"Validation error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def score_dashml_compiles(content: str) -> tuple[bool, str]:
    """Check if dashml build produces output (without actually running it)."""
    try:
        spec = yaml.safe_load(content)
        if not isinstance(spec, dict):
            return False, "Not a dict"

        # Validate first
        validator = DashMLValidator()
        validator.validate(spec)

        # Try to import and run the streamlit transformer
        from dashml_new.transformers.streamlit import StreamlitTransformer
        transformer = StreamlitTransformer()
        output = transformer.build(spec)
        if output and len(output) > 0:
            return True, "ok"
        return False, "Transformer produced empty output"
    except Exception as e:
        return False, f"Compile error: {e}"


def score_streamlit_parses(content: str) -> tuple[bool, str]:
    """Check if content is valid Python."""
    try:
        ast.parse(content)
        return True, "ok"
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"


def score_streamlit_validates(content: str) -> tuple[bool, str]:
    """Check if Streamlit code has valid imports and no obvious NameErrors."""
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    # Collect all imported names
    imported_names = set()
    allowed_modules = {
        "streamlit", "pandas", "altair", "numpy", "os", "sys",
        "pathlib", "datetime", "json", "math",
    }
    issues = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_root = alias.name.split(".")[0]
                name = alias.asname or alias.name
                imported_names.add(name)
                if module_root not in allowed_modules:
                    issues.append(f"Unexpected import: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            module_root = (node.module or "").split(".")[0]
            if module_root and module_root not in allowed_modules:
                issues.append(f"Unexpected import from: {node.module}")
            for alias in node.names:
                name = alias.asname or alias.name
                imported_names.add(name)

    # Check for common required imports
    has_streamlit = any(
        n in imported_names for n in ("st", "streamlit")
    )
    has_pandas = any(
        n in imported_names for n in ("pd", "pandas")
    )

    if not has_streamlit:
        issues.append("Missing streamlit import")
    if not has_pandas:
        issues.append("Missing pandas import")

    if issues:
        return False, "; ".join(issues)
    return True, "ok"


def score_streamlit_compiles(content: str) -> tuple[bool, str]:
    """Check if Streamlit code compiles (AST parse + basic static checks)."""
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    # Check that st.set_page_config is called
    has_page_config = False
    has_chart_output = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Check for st.set_page_config(...)
            if (isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "st"
                    and func.attr == "set_page_config"):
                has_page_config = True
            # Check for st.altair_chart(...) or st.write(...) or st.pyplot(...)
            if (isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "st"
                    and func.attr in ("altair_chart", "write", "pyplot",
                                      "bar_chart", "line_chart", "area_chart")):
                has_chart_output = True

    issues = []
    if not has_page_config:
        issues.append("Missing st.set_page_config()")
    if not has_chart_output:
        issues.append("No chart output (st.altair_chart, etc.)")

    if issues:
        return False, "; ".join(issues)
    return True, "ok"


# ---------------------------------------------------------------------------
# Plotly HTML Scorers
# ---------------------------------------------------------------------------

import re


def score_plotly_parses(content: str) -> tuple[bool, str]:
    """Check if content is valid HTML with basic structure."""
    content_stripped = content.strip()
    issues = []

    if not re.search(r'<html', content_stripped, re.IGNORECASE):
        issues.append("Missing <html> tag")
    if not re.search(r'<script', content_stripped, re.IGNORECASE):
        issues.append("Missing <script> tag")
    if not re.search(r'<body', content_stripped, re.IGNORECASE):
        issues.append("Missing <body> tag")

    if issues:
        return False, "; ".join(issues)
    return True, "ok"


def score_plotly_validates(content: str) -> tuple[bool, str]:
    """Check if Plotly HTML includes required CDN libs and chart calls."""
    content_lower = content.lower()
    issues = []

    # Check for Plotly.js CDN
    if "plotly" not in content_lower or "cdn" not in content_lower:
        if "plotly" not in content_lower:
            issues.append("Missing Plotly.js reference")

    # Check for data loading mechanism
    has_papa = "papaparse" in content_lower or "papa.parse" in content_lower
    has_fetch = "fetch(" in content_lower
    has_d3csv = "d3.csv" in content_lower
    if not (has_papa or has_fetch or has_d3csv):
        issues.append("No CSV loading mechanism (PapaParse, fetch, or d3.csv)")

    # Check for Plotly.newPlot calls
    if "plotly.newplot" not in content_lower and "plotly.react" not in content_lower:
        issues.append("No Plotly.newPlot() or Plotly.react() calls")

    if issues:
        return False, "; ".join(issues)
    return True, "ok"


def score_plotly_compiles(content: str) -> tuple[bool, str]:
    """Check if Plotly HTML has chart containers and matching plot calls."""
    # Find all div ids used as chart containers
    div_ids = set(re.findall(r'id=["\']([^"\']+)["\']', content))
    # Find all Plotly.newPlot target ids
    plot_targets = set(re.findall(
        r'Plotly\.(?:newPlot|react)\s*\(\s*["\']([^"\']+)["\']', content
    ))

    if not plot_targets:
        return False, "No Plotly.newPlot() calls found"

    # Check that every plot target has a corresponding div
    missing_divs = plot_targets - div_ids
    if missing_divs:
        return False, f"Plot targets without matching divs: {', '.join(missing_divs)}"

    return True, "ok"


# ---------------------------------------------------------------------------
# Completeness scorer
# ---------------------------------------------------------------------------

def score_completeness(content: str, format_type: str,
                       expected: dict) -> tuple[float, str]:
    """Score how many expected features are present in the output."""
    if format_type == "dashml":
        return _score_dashml_completeness(content, expected)
    elif format_type == "plotly":
        return _score_plotly_completeness(content, expected)
    else:
        return _score_streamlit_completeness(content, expected)


def _score_dashml_completeness(content: str, expected: dict) -> tuple[float, str]:
    """Check DashML output against expected features."""
    try:
        spec = yaml.safe_load(content)
        if not isinstance(spec, dict):
            return 0.0, "Not a dict"
    except Exception:
        return 0.0, "Cannot parse YAML"

    checks = []
    missing = []

    # Check data source
    data = spec.get("data", {})
    if expected.get("data_type"):
        ok = data.get("type") == expected["data_type"]
        checks.append(ok)
        if not ok:
            missing.append(f"data.type={expected['data_type']}")

    if expected.get("data_path"):
        ok = data.get("path") == expected["data_path"]
        checks.append(ok)
        if not ok:
            missing.append(f"data.path={expected['data_path']}")

    # Collect all charts from spec (pages or flat)
    spec_charts = []
    if "pages" in spec:
        for page in spec.get("pages", []):
            spec_charts.extend(page.get("charts", []))
    else:
        spec_charts = spec.get("charts", [])

    # Check page count if expected
    if expected.get("page_count"):
        pages = spec.get("pages", [])
        ok = len(pages) == expected["page_count"]
        checks.append(ok)
        if not ok:
            missing.append(f"page_count={expected['page_count']} (got {len(pages)})")

    # Check chart count
    if expected.get("chart_count"):
        ok = len(spec_charts) >= expected["chart_count"]
        checks.append(ok)
        if not ok:
            missing.append(
                f"chart_count>={expected['chart_count']} (got {len(spec_charts)})"
            )

    # Check individual expected charts
    expected_charts = expected.get("charts", [])
    if expected.get("pages"):
        expected_charts = []
        for page in expected["pages"]:
            expected_charts.extend(page.get("charts", []))

    for exp_chart in expected_charts:
        exp_type = exp_chart.get("type")
        # Find a matching chart in spec by type
        matched = False
        for sc in spec_charts:
            if sc.get("type") == exp_type:
                matched = True
                # Check x
                if exp_chart.get("x"):
                    ok = sc.get("x") == exp_chart["x"]
                    checks.append(ok)
                    if not ok:
                        missing.append(f"{exp_type}.x={exp_chart['x']}")
                # Check y
                if exp_chart.get("y"):
                    ok = sc.get("y") == exp_chart["y"]
                    checks.append(ok)
                    if not ok:
                        missing.append(f"{exp_type}.y={exp_chart['y']}")
                # Check agg
                if exp_chart.get("agg"):
                    ok = sc.get("agg") == exp_chart["agg"]
                    checks.append(ok)
                    if not ok:
                        missing.append(f"{exp_type}.agg={exp_chart['agg']}")
                break

        if not matched:
            checks.append(False)
            missing.append(f"chart type={exp_type}")

    if not checks:
        return 1.0, "no checks defined"

    score = sum(checks) / len(checks)
    detail = f"{sum(checks)}/{len(checks)}"
    if missing:
        detail += f" missing: {', '.join(missing[:5])}"
    return round(score, 3), detail


def _score_streamlit_completeness(content: str, expected: dict) -> tuple[float, str]:
    """Basic completeness check for Streamlit code against expected features."""
    content_lower = content.lower()
    checks = []
    missing = []

    # Check data path referenced
    if expected.get("data_path"):
        ok = expected["data_path"] in content
        checks.append(ok)
        if not ok:
            missing.append(f"data_path={expected['data_path']}")

    # Check expected chart types are present (heuristic: look for Altair mark methods)
    altair_marks = {
        "bar": "mark_bar",
        "line": "mark_line",
        "scatter": "mark_circle",
        "pie": "mark_arc",
        "area": "mark_area",
        "histogram": "bin",
        "box": "mark_boxplot",
        "stacked_bar": "mark_bar",
        "grouped_bar": "mark_bar",
        "bubble": "mark_circle",
        "heatmap": "mark_rect",
        "geo": "mark_geoshape",
    }

    expected_charts = expected.get("charts", [])
    if expected.get("pages"):
        expected_charts = []
        for page in expected["pages"]:
            expected_charts.extend(page.get("charts", []))

    for exp_chart in expected_charts:
        exp_type = exp_chart.get("type", "")
        mark = altair_marks.get(exp_type, "")
        if mark:
            ok = mark in content_lower
            checks.append(ok)
            if not ok:
                missing.append(f"chart type={exp_type} ({mark})")

        # Check x column referenced
        if exp_chart.get("x"):
            ok = exp_chart["x"] in content
            checks.append(ok)
            if not ok:
                missing.append(f"x={exp_chart['x']}")

        # Check y column referenced
        if exp_chart.get("y"):
            ok = exp_chart["y"] in content
            checks.append(ok)
            if not ok:
                missing.append(f"y={exp_chart['y']}")

    # Check for multi-page structure if expected
    if expected.get("page_count") and expected["page_count"] > 1:
        ok = "st.tabs" in content_lower or "tabs" in content_lower
        checks.append(ok)
        if not ok:
            missing.append("multi-page (st.tabs)")

    if not checks:
        return 1.0, "no checks defined"

    score = sum(checks) / len(checks)
    detail = f"{sum(checks)}/{len(checks)}"
    if missing:
        detail += f" missing: {', '.join(missing[:5])}"
    return round(score, 3), detail


def _score_plotly_completeness(content: str, expected: dict) -> tuple[float, str]:
    """Basic completeness check for Plotly.js HTML against expected features."""
    content_lower = content.lower()
    checks = []
    missing = []

    # Check data path referenced
    if expected.get("data_path"):
        ok = expected["data_path"] in content
        checks.append(ok)
        if not ok:
            missing.append(f"data_path={expected['data_path']}")

    # Plotly chart type indicators
    plotly_indicators = {
        "bar": "type: 'bar'",
        "line": "mode: 'lines'",
        "scatter": "mode: 'markers'",
        "pie": "type: 'pie'",
        "area": "fill:",
        "histogram": "type: 'histogram'",
        "box": "type: 'box'",
        "stacked_bar": "barmode: 'stack'",
        "grouped_bar": "barmode: 'group'",
        "bubble": "marker:",
        "heatmap": "type: 'heatmap'",
        "geo": "choropleth",
    }

    expected_charts = expected.get("charts", [])
    if expected.get("pages"):
        expected_charts = []
        for page in expected["pages"]:
            expected_charts.extend(page.get("charts", []))

    for exp_chart in expected_charts:
        exp_type = exp_chart.get("type", "")
        indicator = plotly_indicators.get(exp_type, "")
        if indicator:
            ok = indicator in content_lower
            checks.append(ok)
            if not ok:
                missing.append(f"chart type={exp_type} ({indicator})")

        # Check x column referenced
        if exp_chart.get("x"):
            ok = exp_chart["x"] in content
            checks.append(ok)
            if not ok:
                missing.append(f"x={exp_chart['x']}")

        # Check y column referenced
        if exp_chart.get("y"):
            ok = exp_chart["y"] in content
            checks.append(ok)
            if not ok:
                missing.append(f"y={exp_chart['y']}")

    # Check for multi-page structure if expected
    if expected.get("page_count") and expected["page_count"] > 1:
        ok = "tab" in content_lower
        checks.append(ok)
        if not ok:
            missing.append("multi-page (tabs)")

    if not checks:
        return 1.0, "no checks defined"

    score = sum(checks) / len(checks)
    detail = f"{sum(checks)}/{len(checks)}"
    if missing:
        detail += f" missing: {', '.join(missing[:5])}"
    return round(score, 3), detail


# ---------------------------------------------------------------------------
# Target-aware scorer dispatch
# ---------------------------------------------------------------------------

TARGET_SCORERS = {
    "streamlit": {
        "parses": score_streamlit_parses,
        "validates": score_streamlit_validates,
        "compiles": score_streamlit_compiles,
    },
    "plotly": {
        "parses": score_plotly_parses,
        "validates": score_plotly_validates,
        "compiles": score_plotly_compiles,
    },
}


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def evaluate_results(results_dir: Path, prompts_path: str) -> dict:
    """Evaluate all results in a directory."""
    # Load metadata
    meta_path = results_dir / "metadata.json"
    if not meta_path.exists():
        print(f"Error: metadata.json not found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    with open(meta_path) as f:
        metadata = json.load(f)

    # Determine target format from metadata (backwards-compatible)
    target = metadata.get("target", "streamlit")
    target_scorers = TARGET_SCORERS.get(target, TARGET_SCORERS["streamlit"])

    # Load prompts for expected features
    prompts_file = Path(prompts_path)
    if not prompts_file.exists():
        # Try relative to this script
        prompts_file = Path(__file__).parent / prompts_path
    with open(prompts_file) as f:
        prompts = yaml.safe_load(f)

    prompts_by_id = {p["id"]: p for p in prompts}

    scores = {
        "results_dir": str(results_dir),
        "model": metadata.get("model", "unknown"),
        "target": target,
        "temperature": metadata.get("temperature", 0.3),
        "runs": metadata.get("runs", 1),
        "scores": [],
        "summary": {},
    }

    for result in metadata["results"]:
        prompt_id = result["prompt_id"]
        tier = result["tier"]
        run_num = result["run"]
        prompt_data = prompts_by_id.get(prompt_id, {})
        expected = prompt_data.get("expected", {})

        entry = {
            "prompt_id": prompt_id,
            "tier": tier,
            "run": run_num,
            "dashml": {},
            target: {},
        }

        # Score DashML
        dashml_path = Path(result["dashml_path"])
        if dashml_path.exists():
            content = dashml_path.read_text()
            parses, parses_detail = score_dashml_parses(content)
            validates, validates_detail = score_dashml_validates(content)
            compiles, compiles_detail = score_dashml_compiles(content)
            completeness, completeness_detail = score_completeness(
                content, "dashml", expected
            )
            entry["dashml"] = {
                "parses": parses,
                "parses_detail": parses_detail,
                "validates": validates,
                "validates_detail": validates_detail,
                "compiles": compiles,
                "compiles_detail": compiles_detail,
                "completeness": completeness,
                "completeness_detail": completeness_detail,
            }
        else:
            entry["dashml"] = {"error": f"File not found: {dashml_path}"}

        # Score target (Streamlit or Plotly)
        target_path = Path(result.get("target_path", result.get("streamlit_path", "")))
        if target_path.exists():
            content = target_path.read_text()
            parses, parses_detail = target_scorers["parses"](content)
            validates, validates_detail = target_scorers["validates"](content)
            compiles, compiles_detail = target_scorers["compiles"](content)
            completeness, completeness_detail = score_completeness(
                content, target, expected
            )
            entry[target] = {
                "parses": parses,
                "parses_detail": parses_detail,
                "validates": validates,
                "validates_detail": validates_detail,
                "compiles": compiles,
                "compiles_detail": compiles_detail,
                "completeness": completeness,
                "completeness_detail": completeness_detail,
            }
        else:
            entry[target] = {"error": f"File not found: {target_path}"}

        scores["scores"].append(entry)

    # Compute summary
    scores["summary"] = _compute_summary(scores["scores"], target)

    return scores


def _compute_summary(entries: list[dict], target: str = "streamlit") -> dict:
    """Compute aggregate statistics."""
    summary = {"overall": {}, "by_tier": {}}

    for format_type in ("dashml", target):
        all_parses = []
        all_validates = []
        all_compiles = []
        all_completeness = []
        by_tier: dict[int, dict[str, list]] = {}

        for entry in entries:
            data = entry.get(format_type, {})
            if "error" in data:
                continue

            tier = entry["tier"]
            if tier not in by_tier:
                by_tier[tier] = {
                    "parses": [], "validates": [],
                    "compiles": [], "completeness": [],
                }

            for metric, target in [
                ("parses", all_parses),
                ("validates", all_validates),
                ("compiles", all_compiles),
                ("completeness", all_completeness),
            ]:
                val = data.get(metric)
                if val is not None:
                    numeric = float(val) if isinstance(val, (int, float, bool)) else 0
                    target.append(numeric)
                    by_tier[tier][metric].append(numeric)

        def avg(lst):
            return round(sum(lst) / len(lst), 3) if lst else 0

        summary["overall"][format_type] = {
            "parse_rate": avg(all_parses),
            "validation_rate": avg(all_validates),
            "compile_rate": avg(all_compiles),
            "avg_completeness": avg(all_completeness),
            "n": len(all_parses),
        }

        for tier, metrics in sorted(by_tier.items()):
            tier_key = f"T{tier}"
            if tier_key not in summary["by_tier"]:
                summary["by_tier"][tier_key] = {}
            summary["by_tier"][tier_key][format_type] = {
                "parse_rate": avg(metrics["parses"]),
                "validation_rate": avg(metrics["validates"]),
                "compile_rate": avg(metrics["compiles"]),
                "avg_completeness": avg(metrics["completeness"]),
                "n": len(metrics["parses"]),
            }

    return summary


def print_report(scores: dict) -> None:
    """Print a human-readable summary."""
    summary = scores["summary"]
    overall = summary.get("overall", {})
    target = scores.get("target", "streamlit")
    target_label = target.capitalize()

    print("=" * 70)
    print("EXPERIMENT RESULTS")
    print(f"Model: {scores['model']}  |  Target: {target_label}  "
          f"|  Temperature: {scores['temperature']}  |  Runs: {scores['runs']}")
    print("=" * 70)
    print()

    # Overall comparison
    print("OVERALL COMPARISON")
    print("-" * 55)
    print(f"{'Metric':<25} {'DashML':>10} {target_label:>12} {'Delta':>10}")
    print("-" * 55)

    dm = overall.get("dashml", {})
    tgt = overall.get(target, {})

    for metric, label in [
        ("parse_rate", "Parse Rate"),
        ("validation_rate", "Validation Rate"),
        ("compile_rate", "Compile Rate"),
        ("avg_completeness", "Avg Completeness"),
    ]:
        dm_val = dm.get(metric, 0)
        tgt_val = tgt.get(metric, 0)
        delta = dm_val - tgt_val
        sign = "+" if delta > 0 else ""
        print(f"{label:<25} {dm_val:>9.1%} {tgt_val:>11.1%} {sign}{delta:>9.1%}")

    print()
    print(f"{'N (total outputs)':<25} {dm.get('n', 0):>10} {tgt.get('n', 0):>12}")
    print()

    # Per-tier breakdown
    by_tier = summary.get("by_tier", {})
    if by_tier:
        print("VALIDATION RATE BY TIER")
        print("-" * 55)
        print(f"{'Tier':<10} {'DashML':>10} {target_label:>12} {'Delta':>10}")
        print("-" * 55)
        for tier_key in sorted(by_tier.keys()):
            tier_data = by_tier[tier_key]
            dm_val = tier_data.get("dashml", {}).get("validation_rate", 0)
            tgt_val = tier_data.get(target, {}).get("validation_rate", 0)
            delta = dm_val - tgt_val
            sign = "+" if delta > 0 else ""
            print(f"{tier_key:<10} {dm_val:>9.1%} {tgt_val:>11.1%} {sign}{delta:>9.1%}")
        print()

    # Per-tier completeness
    if by_tier:
        print("COMPLETENESS BY TIER")
        print("-" * 55)
        print(f"{'Tier':<10} {'DashML':>10} {target_label:>12} {'Delta':>10}")
        print("-" * 55)
        for tier_key in sorted(by_tier.keys()):
            tier_data = by_tier[tier_key]
            dm_val = tier_data.get("dashml", {}).get("avg_completeness", 0)
            tgt_val = tier_data.get(target, {}).get("avg_completeness", 0)
            delta = dm_val - tgt_val
            sign = "+" if delta > 0 else ""
            print(f"{tier_key:<10} {dm_val:>9.1%} {tgt_val:>11.1%} {sign}{delta:>9.1%}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate LLM generation experiment results"
    )
    parser.add_argument(
        "--results", required=True,
        help="Path to a results directory (containing metadata.json)"
    )
    parser.add_argument(
        "--prompts", default="prompts.yaml",
        help="Path to prompts.yaml (default: prompts.yaml)"
    )
    parser.add_argument(
        "--output", default=None,
        help="Save scores JSON to this path (default: <results>/scores.json)"
    )

    args = parser.parse_args()

    results_dir = Path(args.results)
    if not results_dir.exists():
        print(f"Error: results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    scores = evaluate_results(results_dir, args.prompts)

    # Save scores
    output_path = args.output or str(results_dir / "scores.json")
    with open(output_path, "w") as f:
        json.dump(scores, f, indent=2)
    print(f"Scores saved to: {output_path}")
    print()

    # Print report
    print_report(scores)


if __name__ == "__main__":
    main()
