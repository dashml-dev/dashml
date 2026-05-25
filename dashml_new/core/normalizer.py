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
    )
except ImportError:
    from transformers.constants import (  # type: ignore[no-redef]
        CHARTS_NEED_AGGREGATION,
        CHARTS_USE_RAW_DATA,
        DEFAULT_HISTOGRAM_BINS,
        DEFAULT_SORT_ORDER,
        DEFAULT_PRIMARY_COLOR,
    )


class NormalizerError(Exception):
    """Raised when normalization fails (e.g., invalid SQL path format)."""
    pass


class DashMLNormalizer:
    """Transforms a validated spec dict into a NormalizedSpec."""

    # ------------------------------------------------------------------ #
    # SQL building helpers (used by _normalize_chart for sql/bigquery)    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sql_value(value) -> str:
        """Convert a Python value to a SQL literal string."""
        if isinstance(value, str):
            return "'" + value.replace("'", "''") + "'"
        if isinstance(value, (list, tuple)):
            return "(" + ", ".join(DashMLNormalizer._sql_value(v) for v in value) + ")"
        if value is None:
            return "NULL"
        return str(value)

    @staticmethod
    def _build_static_conditions(filters: list) -> list:
        """Convert chart-level DashML filters to SQL condition strings."""
        op_map = {"eq": "=", "ne": "!=", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
        parts = []
        for f in filters:
            field, op, val = f["field"], f["op"], f["value"]
            if op in op_map:
                parts.append(f"{field} {op_map[op]} {DashMLNormalizer._sql_value(val)}")
            elif op == "in":
                parts.append(f"{field} IN {DashMLNormalizer._sql_value(val)}")
            elif op == "contains":
                parts.append(f"{field} LIKE '%{val}%'")
            elif op == "range" and isinstance(val, list) and len(val) == 2:
                parts.append(
                    f"{field} BETWEEN {DashMLNormalizer._sql_value(val[0])} AND {DashMLNormalizer._sql_value(val[1])}"
                )
        return parts

    @staticmethod
    def _build_derived_cte(derived_fields: list) -> str:
        """Build the WITH __derived AS (...) CTE prefix. Empty string if no derived fields."""
        if not derived_fields:
            return ""
        T = "{table_ref}"
        exprs = []
        for f in derived_fields:
            # {col} → col  (SQL expression — strip curly braces)
            sql_expr = re.sub(r'\{(\w+)\}', r'\1', f["expression"])
            exprs.append(f"{sql_expr} AS {f['name']}")
        cols = ", ".join(exprs)
        return f"WITH __derived AS (SELECT *, {cols} FROM {T})"

    @staticmethod
    def _build_derived_pandas_code(derived_fields: list, indent: str = "        ") -> str:
        """Generate pandas assignment lines for CSV mode. Empty string if no derived fields."""
        if not derived_fields:
            return ""
        lines = []
        for f in derived_fields:
            # {col} → df["col"]  (pandas expression)
            pd_expr = re.sub(r'\{(\w+)\}', r'df["\1"]', f["expression"])
            lines.append(f'{indent}df["{f["name"]}"] = {pd_expr}')
        return "\n".join(lines)

    @staticmethod
    def _build_chart_sql(chart: dict, use_derived: bool = False) -> str:
        """Build a SQL query template with {table_ref} and {filter_clause} placeholders.

        Uses generic x/y/grp/size aliases so Plotly, Observable, and Streamlit
        can share the same SQL; Streamlit renames columns back to original names
        after run_query().

        {table_ref}   — replaced at build time by each transformer
        {filter_clause} — replaced at runtime by the generated app's build_filter_clause()
        """
        # Local vars whose VALUES are the literal placeholder strings.
        # Using them in f-strings produces those literals in the output SQL.
        # When use_derived=True the CTE alias is used; {table_ref} lives inside the CTE.
        T = "__derived" if use_derived else "{table_ref}"
        F = "{filter_clause}"

        chart_type = chart["type"]
        x = chart.get("x", "")
        y = chart.get("y", "")
        agg = chart.get("agg", "sum")
        group = chart.get("group")
        size_field = chart.get("size")
        sort_field = chart.get("sort")
        sort_order = chart.get("sort_order", "asc")
        limit = chart.get("limit")

        agg_map = {"sum": "SUM", "mean": "AVG", "count": "COUNT"}
        sql_agg = agg_map.get(agg, "SUM")
        # For count agg without y, use COUNT(*) instead of COUNT(y)
        agg_expr = f"{sql_agg}({y})" if y else "COUNT(*)"

        order = ""
        if sort_field == "y":
            order = f" ORDER BY y {'ASC' if sort_order == 'asc' else 'DESC'}"
        elif sort_field == "x":
            order = f" ORDER BY x {'ASC' if sort_order == 'asc' else 'DESC'}"
        limit_clause = f" LIMIT {limit}" if limit else ""
        if not order and chart_type in ("bar", "line", "area", "pie", "geo"):
            order = " ORDER BY x ASC"

        if chart_type in ("bar", "line", "area", "pie", "geo"):
            return f"SELECT {x} AS x, {agg_expr} AS y FROM {T} WHERE {F} GROUP BY {x}{order}{limit_clause}"
        elif chart_type in ("stacked_bar", "grouped_bar"):
            if sort_field == "y":
                # Sort x categories by aggregate total across all groups
                direction = 'ASC' if sort_order == 'asc' else 'DESC'
                return (
                    f"SELECT agg.x, agg.grp, agg.y FROM"
                    f" (SELECT {x} AS x, {group} AS grp, {agg_expr} AS y FROM {T} WHERE {F} GROUP BY {x}, {group}) agg"
                    f" JOIN (SELECT {x} AS x, {agg_expr} AS x_total FROM {T} WHERE {F} GROUP BY {x}) totals"
                    f" ON agg.x = totals.x"
                    f" ORDER BY totals.x_total {direction}, agg.x{limit_clause}"
                )
            return f"SELECT {x} AS x, {group} AS grp, {agg_expr} AS y FROM {T} WHERE {F} GROUP BY {x}, {group}{order}{limit_clause}"
        elif chart_type == "heatmap":
            hy = group if group else y
            return (
                f"SELECT {x} AS x, {hy} AS heatmap_y, {agg_expr} AS y FROM {T}"
                f" WHERE {F}"
                f" AND {x} IN (SELECT {x} FROM {T} GROUP BY {x} ORDER BY COUNT(*) DESC LIMIT 20)"
                f" AND {hy} IN (SELECT {hy} FROM {T} GROUP BY {hy} ORDER BY COUNT(*) DESC LIMIT 20)"
                f" GROUP BY {x}, {hy}{order}{limit_clause}"
            )
        elif chart_type == "scatter":
            return f"SELECT {x} AS x, {y} AS y FROM {T} WHERE {F} AND {x} IS NOT NULL AND {y} IS NOT NULL"
        elif chart_type == "bubble":
            size_ref = size_field or y
            if not group:
                return f"SELECT {x} AS x, {y} AS y, {size_ref} AS size FROM {T} WHERE {F}"
            return f"SELECT {group} AS grp, {sql_agg}({x}) AS x, {agg_expr} AS y, {sql_agg}({size_ref}) AS size FROM {T} WHERE {F} GROUP BY {group}{order}{limit_clause}"
        elif chart_type == "histogram":
            return f"SELECT {x} AS x FROM {T} WHERE {F} AND {x} IS NOT NULL"
        elif chart_type == "box":
            return f"SELECT {x} AS x, {y} AS y FROM {T} WHERE {F} AND {x} IS NOT NULL AND {y} IS NOT NULL"
        elif chart_type == "metric":
            return f"SELECT {agg_expr} AS y FROM {T} WHERE {F}"
        else:
            return f"SELECT {x} AS x, {agg_expr} AS y FROM {T} WHERE {F} GROUP BY {x}{order}{limit_clause}"

    # ------------------------------------------------------------------ #

    def normalize(
        self, spec: dict, source_file: str, db_config: Optional[Dict[str, Any]] = None
    ) -> NormalizedSpec:
        """Main entry point. Takes validated dict, returns NormalizedSpec."""
        result: NormalizedSpec = {}

        result["version"] = str(spec.get("version", ""))
        result["title"] = spec.get("title", "DashML Dashboard")
        result["data"] = self._normalize_data(spec.get("data", {}), source_file)
        result["derived_fields"] = spec.get("derived_fields", [])
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
                elif len(parts) == 3:
                    # Fully-qualified BigQuery path: project.dataset.table
                    # Self-contained spec — no need for --bq-project CLI flag.
                    result["bq_project"] = parts[0]
                    result["bq_dataset"] = parts[1]
                    result["bq_table"] = parts[2]
                else:
                    raise NormalizerError(
                        f"Invalid BigQuery path format: {path}. "
                        f"Expected: dataset.table or project.dataset.table"
                    )

        return result  # type: ignore

    def _normalize_pages(self, spec: dict) -> List[PageSpec]:
        """Ensure pages[] always exists. Wrap single-page charts if needed."""
        data_type = spec.get("data", {}).get("type", "csv")
        derived_fields = spec.get("derived_fields", [])

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
                self._normalize_chart(chart, data_type, derived_fields)
                for chart in page.get("charts", [])
            ]
            # Default filters to empty list (mirrors chart filter defaulting)
            if "filters" not in normalized_page:
                normalized_page["filters"] = []
            normalized_pages.append(normalized_page)

        return normalized_pages  # type: ignore

    def _normalize_chart(self, chart: dict, data_type: str = "csv", derived_fields: list = None) -> ChartSpec:
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

        # Semantic normalization: for aggregation charts with count, y is meaningless
        # (count counts rows, not a value column). If the user specified both x and y
        # with different columns, the second column is a grouping dimension.
        # Scoped to bar/line/heatmap where group→color is the correct interpretation.
        _COUNT_GROUP_TYPES = {"bar", "line", "heatmap"}
        if (result.get("agg") == "count"
                and result.get("y") and not result.get("group")
                and result.get("x") != result.get("y")
                and chart_type in _COUNT_GROUP_TYPES):
            result["group"] = result.pop("y")

        # Annotations
        result["needs_aggregation"] = chart_type in CHARTS_NEED_AGGREGATION
        result["uses_raw_data"] = chart_type in CHARTS_USE_RAW_DATA

        # SQL template (sql/bigquery only) — built once here, shared by all transformers.
        # {table_ref} is replaced at build time by each transformer.
        # {filter_clause} is replaced at runtime by the generated app.
        # When derived_fields exist, a CTE is prepended and the main query uses __derived.
        if data_type in ("sql", "bigquery"):
            cte = self._build_derived_cte(derived_fields or [])
            chart_sql = self._build_chart_sql(result, use_derived=bool(cte))
            result["sql"] = (cte + " " + chart_sql).strip() if cte else chart_sql
            result["static_conditions"] = self._build_static_conditions(result.get("filters", []))

        return result  # type: ignore

    def _resolve_style(
        self, style_ref: Optional[str], source_file: str
    ) -> ResolvedStyle:
        """Load .dmls theme, merge with default colors.

        Resolution rules:
        - Name (no separator, no ``.dmls`` extension): look up a bundled
          theme that ships with the package.
        - Path (contains ``/``, ``\\``, or ends with ``.dmls``): resolve
          on the filesystem, relative to the ``.dashml`` file or absolute.
        """
        defaults: ResolvedStyle = {
            "primary": DEFAULT_PRIMARY_COLOR,
            "background": "#0e1117",
            "text": "#fafafa",
            "card": "#262730",
            "sequential": "blues",
        }

        if not style_ref:
            return defaults

        style_path: Optional[Path] = None
        is_path = "/" in style_ref or "\\" in style_ref or style_ref.endswith(".dmls")

        if is_path:
            source_dir = Path(source_file).parent
            candidate = (source_dir / style_ref).resolve() if not Path(style_ref).is_absolute() else Path(style_ref)
            if candidate.exists():
                style_path = candidate
        else:
            # Bundled theme inside the package: dashml_new/styles/<name>.dmls
            bundled = Path(__file__).resolve().parent.parent / "styles" / f"{style_ref}.dmls"
            if bundled.exists():
                style_path = bundled

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
