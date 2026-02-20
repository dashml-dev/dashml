"""
DashML Normalizer — Transforms validated specs into a clean NormalizedSpec.

Replaces the current no-op pipeline step where engine.load() just labels
a raw dict as DashMLSpec. The normalizer does real work: resolving paths,
wrapping pages, filling defaults, loading styles, and annotating charts.
"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .types import NormalizedSpec, ResolvedStyle, DataSpec, PageSpec, ChartSpec

# Import shared constants — use try/except to support both
# running as a package (from ..transformers) and running from dashml_new/ (from transformers)
try:
    from ..transformers.constants import (
        CHARTS_NEED_AGGREGATION,
        CHARTS_USE_RAW_DATA,
        DEFAULT_HISTOGRAM_BINS,
        DEFAULT_SORT_ORDER,
        DEFAULT_PRIMARY_COLOR,
        DEFAULT_SECONDARY_COLORS,
    )
except ImportError:
    from transformers.constants import (  # type: ignore[no-redef]
        CHARTS_NEED_AGGREGATION,
        CHARTS_USE_RAW_DATA,
        DEFAULT_HISTOGRAM_BINS,
        DEFAULT_SORT_ORDER,
        DEFAULT_PRIMARY_COLOR,
        DEFAULT_SECONDARY_COLORS,
    )


class NormalizerError(Exception):
    """Raised when normalization fails (e.g., invalid SQL path format)."""
    pass


class DashMLNormalizer:
    """Transforms a validated spec dict into a NormalizedSpec."""

    def normalize(
        self, spec: dict, source_file: str, db_config: Optional[Dict[str, Any]] = None
    ) -> NormalizedSpec:
        """Main entry point. Takes validated dict, returns NormalizedSpec."""
        result: NormalizedSpec = {}

        result["version"] = str(spec.get("version", ""))
        result["title"] = spec.get("title", "DashML Dashboard")
        result["data"] = self._normalize_data(spec.get("data", {}), source_file)
        result["pages"] = self._normalize_pages(spec)
        result["style"] = self._resolve_style(spec.get("style"), source_file)
        result["db_config"] = db_config or {}
        result["source_file"] = str(Path(source_file).resolve())

        return result

    def _normalize_data(self, data_spec: dict, source_file: str) -> DataSpec:
        """Parse data source paths into pre-resolved components."""
        result = dict(data_spec)  # shallow copy
        data_type = result.get("type", "csv")

        if data_type == "csv":
            path = result.get("path", "")
            if path:
                source_dir = Path(source_file).parent
                result["csv_path"] = str((source_dir / path).resolve())

        elif data_type == "sql":
            # Handle legacy fields: schema + table_name (no path)
            if "path" not in result and "schema" in result and "table_name" in result:
                result["path"] = f"{result['schema']}.{result['table_name']}"

            path = result.get("path", "")
            if path:
                schema, table = self._parse_sql_path(path)
                result["sql_schema"] = schema
                result["sql_table"] = table

        elif data_type == "bigquery":
            path = result.get("path", "")
            if path:
                parts = path.split(".")
                if len(parts) == 2:
                    result["bq_dataset"] = parts[0]
                    result["bq_table"] = parts[1]
                else:
                    raise NormalizerError(
                        f"Invalid BigQuery path format: {path}. Expected: dataset.table"
                    )

        return result  # type: ignore

    def _normalize_pages(self, spec: dict) -> List[PageSpec]:
        """Ensure pages[] always exists. Wrap single-page charts if needed."""
        if "pages" in spec:
            pages = spec["pages"]
        elif "charts" in spec:
            # Wrap single-page charts into a pages array
            pages = [{
                "id": "main",
                "title": spec.get("title", ""),
                "description": "",
                "charts": spec["charts"],
            }]
        else:
            pages = []

        # Normalize each chart in every page
        normalized_pages = []
        for page in pages:
            normalized_page = dict(page)
            normalized_page["charts"] = [
                self._normalize_chart(chart)
                for chart in page.get("charts", [])
            ]
            # Default filters to empty list (mirrors chart filter defaulting)
            if "filters" not in normalized_page:
                normalized_page["filters"] = []
            normalized_pages.append(normalized_page)

        return normalized_pages  # type: ignore

    def _normalize_chart(self, chart: dict) -> ChartSpec:
        """Fill defaults and add annotations to a single chart."""
        result = dict(chart)  # shallow copy, don't mutate original
        chart_type = result.get("type", "")

        # Default title from id
        if "title" not in result:
            result["title"] = result.get("id", "")

        # Default agg for charts that need aggregation
        if "agg" not in result and chart_type in CHARTS_NEED_AGGREGATION:
            result["agg"] = "sum"

        # Default bins for histogram
        if chart_type == "histogram" and "bins" not in result:
            result["bins"] = DEFAULT_HISTOGRAM_BINS

        # Default filters
        if "filters" not in result:
            result["filters"] = []

        # Default sort_order when sort is set
        if "sort" in result and "sort_order" not in result:
            result["sort_order"] = DEFAULT_SORT_ORDER

        # Annotations
        result["needs_aggregation"] = chart_type in CHARTS_NEED_AGGREGATION
        result["uses_raw_data"] = chart_type in CHARTS_USE_RAW_DATA

        return result  # type: ignore

    def _resolve_style(
        self, style_ref: Optional[str], source_file: str
    ) -> ResolvedStyle:
        """Load .dmls file, merge with default colors."""
        defaults: ResolvedStyle = {
            "primary": DEFAULT_PRIMARY_COLOR,
            "secondary": list(DEFAULT_SECONDARY_COLORS),
            "background": "#0e1117",
            "text": "#fafafa",
            "card": "#262730",
            "buttons": DEFAULT_PRIMARY_COLOR,
        }

        if not style_ref:
            return defaults

        # Try to find the style file
        style_path = None

        # 1. Check styles/{style_ref}.dmls relative to project root
        project_root = Path(source_file).parent
        # Walk up to find styles/ directory (project root is typically dashml_new's parent)
        for parent in [project_root] + list(project_root.parents):
            candidate = parent / "styles" / f"{style_ref}.dmls"
            if candidate.exists():
                style_path = candidate
                break

        # 2. Check as relative path from source file directory
        if style_path is None:
            candidate = project_root / style_ref
            if candidate.exists():
                style_path = candidate

        # 3. Check as absolute path
        if style_path is None:
            candidate = Path(style_ref)
            if candidate.exists():
                style_path = candidate

        if style_path is None:
            return defaults

        try:
            with open(style_path, "r", encoding="utf-8") as f:
                style_config = yaml.safe_load(f) or {}
        except Exception:
            return defaults

        loaded = style_config.get("colors", {})
        if not loaded:
            return defaults

        # Merge loaded values over defaults
        result: ResolvedStyle = dict(defaults)  # type: ignore
        for key in defaults:
            if key in loaded:
                result[key] = loaded[key]  # type: ignore

        return result

    def _parse_sql_path(self, path: str) -> tuple:
        """Parse SQL schema.table path into (schema, table) tuple."""
        pattern = r'^\[?([^\]\.]+)\]?\.?\[?([^\]]+)\]?$'
        match = re.match(pattern, path)

        if match:
            return (match.group(1).strip(), match.group(2).strip())

        raise NormalizerError(f"Invalid SQL path format: {path}")
