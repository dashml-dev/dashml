"""
Vega-Lite Transformer

Generates Vega-Lite JSON specs viewable in:
  - Vega Editor: https://vega.github.io/editor/
  - Any Vega-Lite renderer (Observable, Jupyter, etc.)

Single-chart specs produce a bare Vega-Lite spec.
Multi-chart dashboards use vconcat/hconcat composition.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .base import Transformer
from .constants import (
    resolve_metric_format,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLORS,
    COUNTRY_DATA,
    build_alias_to_topojson,
    build_iso2_to_topojson,
    build_iso3_to_topojson,
)

if TYPE_CHECKING:
    from ..core.types import NormalizedSpec


VEGALITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v6.json"

# DashML agg → Vega-Lite aggregate
AGG_MAP = {
    "sum": "sum",
    "mean": "mean",
    "count": "count",
}

# DashML sequential scheme → Vega-Lite scheme name
SEQUENTIAL_SCHEMES = {
    "blues": "blues",
    "greens": "greens",
    "reds": "reds",
    "purples": "purples",
    "oranges": "oranges",
    "viridis": "viridis",
    "cividis": "cividis",
    "teals": "teals",
}


class VegaLiteTransformer(Transformer):
    """Generates Vega-Lite JSON specifications."""

    def __init__(self, embedded_data: list | None = None, bare: bool = False):
        super().__init__()
        self._embedded_data = embedded_data
        self._bare = bare

    @property
    def name(self) -> str:
        return "vegalite"

    @property
    def description(self) -> str:
        return "Vega-Lite JSON spec (viewable in Vega Editor or any VL renderer)"

    @property
    def output_filename(self) -> str:
        return "dashboard.vl.json"

    def get_run_command(self, output_path: str) -> str:
        return (
            f'echo "Open {output_path}/dashboard.vl.json in the Vega Editor: '
            f'https://vega.github.io/editor/"'
        )

    def build(self, spec: "NormalizedSpec") -> str:
        self.clear_warnings()

        style = spec.get("style", {})
        if style.get("buttons"):
            self.warn("'buttons' color is not supported in Vega-Lite")

        pages = spec.get("pages", [])
        all_charts = []
        for page in pages:
            all_charts.extend(page.get("charts", []))

        if self._bare:
            # Bare mode: output JSON array of stripped {mark, encoding, transform} objects
            result = [self._build_bare_spec(c, spec) for c in all_charts]
            return json.dumps(result, indent=2)

        # Single chart → bare spec, multiple → composed layout
        if len(all_charts) == 1:
            result = self._build_chart_spec(all_charts[0], spec)
        else:
            result = self._build_dashboard(spec)

        return json.dumps(result, indent=2)

    # ── Bare (nvBench-compatible) output ────────────────────────────

    # Properties to keep in encoding channels for bare output
    _BARE_CHANNEL_KEYS = {"field", "aggregate", "bin", "sort", "timeUnit"}

    # nvBench uses "pie" for arc marks — map VL mark names to nvBench equivalents
    _BARE_MARK_MAP = {
        "arc": "pie",
    }

    def _build_bare_spec(self, chart: dict, spec: "NormalizedSpec") -> dict:
        """Build a stripped {mark, encoding, transform} spec for benchmark evaluation."""
        chart_type = chart.get("type", "bar")

        builder = getattr(self, f"_build_{chart_type}", None)
        if builder:
            vl = builder(chart, spec)
        else:
            vl = self._build_bar(chart, spec)

        # For layered specs (geo), extract the data layer
        if "layer" in vl and "encoding" not in vl:
            # Use the last layer (data overlay) which has the encoding
            for layer in reversed(vl["layer"]):
                if "encoding" in layer:
                    vl = layer
                    break

        # Extract mark as plain string, mapped to nvBench names
        mark = vl.get("mark", "bar")
        if isinstance(mark, dict):
            mark = mark.get("type", "bar")
        mark = self._BARE_MARK_MAP.get(mark, mark)

        # Channels to strip per mark type (these are decorative, not in gold specs)
        # boxplot gold specs never have color; it's added by _build_box for styling only
        bare_strip_channels = {"tooltip", "shape"}
        if mark == "boxplot":
            bare_strip_channels.add("color")

        # Strip encoding channels to only benchmark-relevant properties
        encoding = {}
        for channel, props in vl.get("encoding", {}).items():
            if channel in bare_strip_channels:
                continue
            if isinstance(props, dict):
                stripped = {k: v for k, v in props.items() if k in self._BARE_CHANNEL_KEYS}
                # Normalize sort format: nvBench uses plain strings (e.g., "-y")
                if "sort" in stripped:
                    stripped["sort"] = self._normalize_bare_sort(stripped["sort"])
                if stripped:
                    encoding[channel] = stripped

        # If the chart has bin: true, add binning to x encoding
        if chart.get("bin") and "x" in encoding:
            encoding["x"]["bin"] = True

        # In bare mode, inject color from group field if present
        # (nvBench gold specs use color for grouped data; DashML uses chart type distinction)
        group = chart.get("group")
        if group and "color" not in encoding and mark not in ("boxplot",):
            encoding["color"] = {"field": group}

        # In bare mode, inject size from size field if present (for scatter/point)
        size_field = chart.get("size")
        if size_field and "size" not in encoding:
            encoding["size"] = {"field": size_field}

        result: dict = {"mark": mark, "encoding": encoding}

        # Convert DashML filters to nvBench filter format
        # Include both chart-level and dashboard-level filters
        bare_transforms = self._build_bare_filters(chart, spec)
        if bare_transforms:
            result["transform"] = bare_transforms

        return result

    @staticmethod
    def _normalize_bare_sort(sort_val) -> str:
        """Normalize sort to nvBench string format (e.g., '-y', 'ascending')."""
        if isinstance(sort_val, str):
            return sort_val
        if isinstance(sort_val, dict):
            # {"encoding": "y", "order": "descending"} → "-y"
            enc = sort_val.get("encoding", "")
            order = sort_val.get("order", "ascending")
            if enc:
                return f"-{enc}" if order == "descending" else enc
            return order
        return str(sort_val)

    def _build_bare_filters(self, chart: dict, spec: "NormalizedSpec" = None) -> list:
        """Convert chart.filters + dashboard-level filters to nvBench-style filter transforms."""
        # Collect chart-level filters
        all_filters = list(chart.get("filters", []))

        # Also collect dashboard-level filters from the page/spec
        # (LLMs sometimes put filters at the page/dashboard level instead of chart level)
        if spec:
            for page in spec.get("pages", []):
                for f in page.get("filters", []):
                    # Dashboard filters have field/type/label/values, not field/op/value
                    # Only propagate if they look like chart filters (have op)
                    if "op" in f:
                        all_filters.append(f)

        transforms = []
        for f in all_filters:
            field = f.get("field", "")
            op = f.get("op", "eq")
            value = f.get("value")
            filt = self._filter_to_nvbench(field, op, value)
            if filt:
                transforms.append({"filter": filt})
        return transforms

    @staticmethod
    def _filter_to_nvbench(field: str, op: str, value) -> dict | None:
        """Convert a DashML filter to nvBench filter object format."""
        # nvBench uses: {field, equal/lt/lte/gt/gte/range/oneOf/valid}
        nvbench_op_map = {
            "eq": "equal",
            "ne": None,  # not in nvBench
            "gt": "gt",
            "lt": "lt",
            "gte": "gte",
            "lte": "lte",
        }
        if op == "in" and isinstance(value, list):
            return {"field": field, "oneOf": value}
        if op == "range" and isinstance(value, list) and len(value) == 2:
            return {"field": field, "range": value}
        mapped = nvbench_op_map.get(op)
        if mapped:
            return {"field": field, mapped: value}
        return None

    # ── Dashboard composition ──────────────────────────────────────

    def _build_dashboard(self, spec: "NormalizedSpec") -> dict:
        """Build a composed dashboard with vconcat of hconcat rows."""
        pages = spec.get("pages", [])
        rows = []

        for page in pages:
            charts = page.get("charts", [])
            metrics = [c for c in charts if c.get("type") == "metric"]
            non_metrics = [c for c in charts if c.get("type") != "metric"]

            # Metrics row: up to 4 per hconcat
            for i in range(0, len(metrics), 4):
                batch = metrics[i:i + 4]
                row_specs = [self._build_chart_spec(c, spec, top_level=False) for c in batch]
                if len(row_specs) == 1:
                    rows.append(row_specs[0])
                else:
                    rows.append({"hconcat": row_specs})

            # Chart rows: 2 per hconcat (boxplot must be solo — crashes in hconcat with other marks)
            SOLO_TYPES = {"box"}
            i = 0
            while i < len(non_metrics):
                chart = non_metrics[i]
                if chart.get("type") in SOLO_TYPES:
                    rows.append(self._build_chart_spec(chart, spec, top_level=False))
                    i += 1
                elif i + 1 < len(non_metrics) and non_metrics[i + 1].get("type") in SOLO_TYPES:
                    # Next chart is solo, emit current one alone
                    rows.append(self._build_chart_spec(chart, spec, top_level=False))
                    i += 1
                elif i + 1 < len(non_metrics):
                    batch = non_metrics[i:i + 2]
                    row_specs = [self._build_chart_spec(c, spec, top_level=False) for c in batch]
                    rows.append({"hconcat": row_specs})
                    i += 2
                else:
                    rows.append(self._build_chart_spec(chart, spec, top_level=False))
                    i += 1

        dashboard = {
            "$schema": VEGALITE_SCHEMA,
            "title": spec.get("title", "DashML Dashboard"),
            "vconcat": rows,
            "config": self._build_config(spec),
        }

        # Add data at top level
        data_block = self._build_data(spec)
        if data_block:
            dashboard["data"] = data_block

        return dashboard

    # ── Single chart spec builder ──────────────────────────────────

    def _build_chart_spec(self, chart: dict, spec: "NormalizedSpec", top_level: bool = True) -> dict:
        """Build a complete Vega-Lite spec for one chart."""
        chart_type = chart.get("type", "bar")

        builder = getattr(self, f"_build_{chart_type}", None)
        if builder:
            vl = builder(chart, spec)
        else:
            self.warn(f"Unknown chart type '{chart_type}', falling back to bar")
            vl = self._build_bar(chart, spec)

        # Add common properties
        if top_level:
            vl.setdefault("$schema", VEGALITE_SCHEMA)
        vl.setdefault("title", chart.get("title", chart.get("id", "")))
        vl.setdefault("width", 400)
        vl.setdefault("height", 300)

        # Add data if not already set (geo sets its own); skip for child specs in compositions
        if top_level and "data" not in vl:
            data_block = self._build_data(spec)
            if data_block:
                vl["data"] = data_block

        # Add filter transforms
        transforms = vl.get("transform", [])
        filter_transforms = self._build_filter_transforms(chart)
        if filter_transforms:
            vl["transform"] = filter_transforms + transforms

        return vl

    # ── Data ───────────────────────────────────────────────────────

    def _build_data(self, spec: "NormalizedSpec") -> dict | None:
        """Build the data block."""
        # Embedded data takes priority (from --embed-data flag)
        if self._embedded_data is not None:
            return {"values": self._embedded_data}

        data = spec.get("data", {})
        data_type = data.get("type", "csv")

        if data_type == "csv":
            csv_path = data.get("csv_path", "")
            filename = Path(csv_path).name if csv_path else "data.csv"
            return {"url": filename}

        # SQL/BigQuery: no inline data, user must provide via Vega datasets
        self.warn(
            f"Data type '{data_type}' requires external data loading. "
            "The spec uses an empty values array — replace with your data source."
        )
        return {"values": []}

    # ── Filter transforms ──────────────────────────────────────────

    def _build_filter_transforms(self, chart: dict) -> list:
        """Convert chart.filters to Vega-Lite filter transforms."""
        filters = chart.get("filters", [])
        transforms = []
        for f in filters:
            field = f.get("field", "")
            op = f.get("op", "eq")
            value = f.get("value")
            expr = self._filter_to_expr(field, op, value)
            if expr:
                transforms.append({"filter": expr})
        return transforms

    @staticmethod
    def _filter_to_expr(field: str, op: str, value) -> str | None:
        """Convert a DashML filter to a Vega expression string."""
        if isinstance(value, str):
            val_repr = f"'{value}'"
        else:
            val_repr = str(value)

        op_map = {
            "eq": f"datum.{field} === {val_repr}",
            "ne": f"datum.{field} !== {val_repr}",
            "gt": f"datum.{field} > {val_repr}",
            "lt": f"datum.{field} < {val_repr}",
            "gte": f"datum.{field} >= {val_repr}",
            "lte": f"datum.{field} <= {val_repr}",
            "contains": f"indexof(datum.{field}, {val_repr}) >= 0",
        }
        if op == "in" and isinstance(value, list):
            items = ", ".join(
                f"'{v}'" if isinstance(v, str) else str(v) for v in value
            )
            return f"indexof([{items}], datum.{field}) >= 0"
        if op == "range" and isinstance(value, list) and len(value) == 2:
            lo, hi = value
            lo_repr = f"'{lo}'" if isinstance(lo, str) else str(lo)
            hi_repr = f"'{hi}'" if isinstance(hi, str) else str(hi)
            return f"datum.{field} >= {lo_repr} && datum.{field} <= {hi_repr}"
        return op_map.get(op)

    # ── Encoding helpers ───────────────────────────────────────────

    def _field_type(self, chart: dict, axis: str) -> str:
        """Resolve Vega-Lite field type from chart hints."""
        type_hint = chart.get(f"{axis}_type")
        if type_hint == "date":
            return "temporal"
        if type_hint == "number":
            return "quantitative"
        if type_hint == "string":
            return "nominal"
        # Defaults: y is quantitative, x depends on chart type
        if axis == "y":
            return "quantitative"
        return "nominal"

    def _x_encoding(self, chart: dict, with_agg: bool = False) -> dict:
        """Build x encoding channel."""
        enc = {"field": chart.get("x", "x"), "type": self._field_type(chart, "x")}
        if with_agg and chart.get("agg"):
            enc["aggregate"] = AGG_MAP.get(chart["agg"], "sum")
        sort = chart.get("sort")
        sort_order = chart.get("sort_order", "asc")
        if sort == "x":
            enc["sort"] = sort_order
        elif sort == "y":
            enc["sort"] = {"encoding": "y", "order": "descending" if sort_order == "desc" else "ascending"}
        return enc

    def _y_encoding(self, chart: dict, with_agg: bool = True) -> dict:
        """Build y encoding channel."""
        agg = chart.get("agg")
        if agg == "count":
            enc = {"aggregate": "count", "type": "quantitative"}
            enc["title"] = "count"
        else:
            enc = {"field": chart.get("y", "y"), "type": "quantitative"}
            if with_agg and agg:
                enc["aggregate"] = AGG_MAP.get(agg, "sum")
        sort = chart.get("sort")
        sort_order = chart.get("sort_order", "asc")
        if sort == "y":
            pass  # handled on x via sort by encoding
        elif sort == "x":
            enc["sort"] = sort_order
        return enc

    def _color_encoding(self, chart: dict, spec: "NormalizedSpec") -> dict:
        """Build color encoding for group field."""
        group = chart.get("group", "")
        style = spec.get("style", {})
        secondary = style.get("secondary", DEFAULT_SECONDARY_COLORS)

        enc = {"field": group, "type": "nominal"}
        if isinstance(secondary, list) and secondary:
            enc["scale"] = {"range": secondary}
        return enc

    def _apply_limit(self, vl: dict, chart: dict) -> None:
        """Add window + filter transforms for limit."""
        limit = chart.get("limit")
        if not limit:
            return
        transforms = vl.get("transform", [])
        sort_order = chart.get("sort_order", "asc")
        y_field = chart.get("y", "y")
        agg = chart.get("agg", "sum")

        # Use a window rank then filter
        transforms.extend([
            {
                "window": [{"op": "rank", "as": "_rank"}],
                "sort": [{"field": y_field, "order": "descending" if sort_order == "desc" else "ascending"}],
            },
            {"filter": f"datum._rank <= {limit}"},
        ])
        vl["transform"] = transforms

    # ── Chart type builders ────────────────────────────────────────

    def _build_bar(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        vl = {
            "mark": {"type": "bar", "color": primary},
            "encoding": {
                "x": self._x_encoding(chart),
                "y": self._y_encoding(chart),
                "tooltip": [
                    {"field": chart.get("x", "x")},
                    self._y_encoding(chart),
                ],
            },
        }
        self._apply_limit(vl, chart)
        return vl

    def _build_line(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        return {
            "mark": {"type": "line", "color": primary, "interpolate": "monotone"},
            "encoding": {
                "x": self._x_encoding(chart),
                "y": self._y_encoding(chart),
                "tooltip": [
                    {"field": chart.get("x", "x"), "type": self._field_type(chart, "x")},
                    self._y_encoding(chart),
                ],
            },
        }

    def _build_area(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        return {
            "mark": {
                "type": "area",
                "color": primary,
                "interpolate": "monotone",
                "opacity": 0.7,
            },
            "encoding": {
                "x": self._x_encoding(chart),
                "y": self._y_encoding(chart),
                "tooltip": [
                    {"field": chart.get("x", "x"), "type": self._field_type(chart, "x")},
                    self._y_encoding(chart),
                ],
            },
        }

    def _build_pie(self, chart: dict, spec: "NormalizedSpec") -> dict:
        y_enc = self._y_encoding(chart)
        color_enc = {"field": chart.get("x", "x"), "type": "nominal"}
        style = spec.get("style", {})
        secondary = style.get("secondary", DEFAULT_SECONDARY_COLORS)
        if isinstance(secondary, list) and secondary:
            color_enc["scale"] = {"range": secondary}

        return {
            "mark": "arc",
            "encoding": {
                "theta": y_enc,
                "color": color_enc,
                "tooltip": [
                    {"field": chart.get("x", "x"), "type": "nominal"},
                    y_enc,
                ],
            },
        }

    def _build_histogram(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        bins = chart.get("bins", 20)
        return {
            "mark": {"type": "bar", "color": primary},
            "encoding": {
                "x": {
                    "bin": {"maxbins": bins},
                    "field": chart.get("x", "x"),
                    "type": "quantitative",
                },
                "y": {"aggregate": "count", "type": "quantitative"},
            },
        }

    def _build_stacked_bar(self, chart: dict, spec: "NormalizedSpec") -> dict:
        return {
            "mark": "bar",
            "encoding": {
                "x": self._x_encoding(chart),
                "y": self._y_encoding(chart),
                "color": self._color_encoding(chart, spec),
                "tooltip": [
                    {"field": chart.get("x", "x")},
                    self._y_encoding(chart),
                    {"field": chart.get("group", "")},
                ],
            },
        }

    def _build_grouped_bar(self, chart: dict, spec: "NormalizedSpec") -> dict:
        return {
            "mark": "bar",
            "encoding": {
                "x": self._x_encoding(chart),
                "y": self._y_encoding(chart),
                "xOffset": {"field": chart.get("group", ""), "type": "nominal"},
                "color": self._color_encoding(chart, spec),
                "tooltip": [
                    {"field": chart.get("x", "x")},
                    self._y_encoding(chart),
                    {"field": chart.get("group", "")},
                ],
            },
        }

    def _build_scatter(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        return {
            "mark": {"type": "point", "color": primary, "filled": True},
            "encoding": {
                "x": {
                    "field": chart.get("x", "x"),
                    "type": "quantitative",
                },
                "y": {
                    "field": chart.get("y", "y"),
                    "type": "quantitative",
                },
                "tooltip": [
                    {"field": chart.get("x", "x"), "type": "quantitative"},
                    {"field": chart.get("y", "y"), "type": "quantitative"},
                ],
            },
        }

    def _build_heatmap(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        sequential = style.get("sequential", "blues")
        scheme = SEQUENTIAL_SCHEMES.get(sequential, "blues")

        agg = chart.get("agg", "sum")
        color_enc = {"type": "quantitative"}
        if agg == "count":
            color_enc["aggregate"] = "count"
            color_enc["title"] = "count"
        else:
            color_enc["field"] = chart.get("y", "y")
            color_enc["aggregate"] = AGG_MAP.get(agg, "sum")
        color_enc["scale"] = {"scheme": scheme}

        # Tooltip version without scale property
        tooltip_enc = {k: v for k, v in color_enc.items() if k != "scale"}

        return {
            "mark": "rect",
            "encoding": {
                "x": {"field": chart.get("x", "x"), "type": "nominal"},
                "y": {"field": chart.get("group", "y"), "type": "nominal"},
                "color": color_enc,
                "tooltip": [
                    {"field": chart.get("x", "x")},
                    {"field": chart.get("group", "y")},
                    tooltip_enc,
                ],
            },
        }

    def _build_geo_mapping(self, geo_encoding: str) -> list[dict]:
        """Build inline mapping table from user's country format to TopoJSON names."""
        if geo_encoding == "iso2":
            raw = build_iso2_to_topojson()
            # ISO codes are case-sensitive, no lowering needed
            return [{"_src": k, "_topo": v} for k, v in raw.items()]
        elif geo_encoding == "iso3":
            raw = build_iso3_to_topojson()
            return [{"_src": k, "_topo": v} for k, v in raw.items()]
        else:
            # "name" encoding: aliases (lowercased) + topojson names mapping to themselves
            mapping: dict[str, str] = {}
            # Add all topojson names as identity (lowercased key)
            for _iso2, (_iso3, topo_name, _plotly) in COUNTRY_DATA.items():
                mapping[topo_name.lower()] = topo_name
            # Add aliases (overwrites are fine — aliases take priority)
            alias_map = build_alias_to_topojson()
            mapping.update(alias_map)
            return [{"_src": k, "_topo": v} for k, v in mapping.items()]

    def _build_geo(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        sequential = style.get("sequential", "blues")
        scheme = SEQUENTIAL_SCHEMES.get(sequential, "blues")
        agg = chart.get("agg", "sum")
        x_field = chart.get("x", "country")
        y_field = chart.get("y", "value")
        geo_encoding = chart.get("geo_encoding", "name")

        color_enc = {"type": "quantitative"}
        if agg == "count":
            color_enc["aggregate"] = "count"
            color_enc["title"] = "count"
        else:
            color_enc["field"] = y_field
            color_enc["aggregate"] = AGG_MAP.get(agg, "sum")
        color_enc["scale"] = {"scheme": scheme}

        # User data source: embedded values or URL
        data = spec.get("data", {})
        csv_path = data.get("csv_path", "")
        csv_filename = Path(csv_path).name if csv_path else "data.csv"

        if self._embedded_data is not None:
            user_data = {"values": self._embedded_data}
        else:
            user_data = {"url": csv_filename}

        topojson_url = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"

        # Build mapping table for country name normalization
        mapping_values = self._build_geo_mapping(geo_encoding)

        # User data transforms: normalize country names → lookup geo features
        user_transforms = []

        # Step 1: Normalize key for lookup into mapping table
        if geo_encoding in ("iso2", "iso3"):
            # ISO codes: use as-is (case-sensitive)
            lookup_key = x_field
        else:
            # Names: lowercase for alias matching
            user_transforms.append({
                "calculate": f"lower(datum['{x_field}'])",
                "as": "_geo_key",
            })
            lookup_key = "_geo_key"

        # Step 2: Look up TopoJSON name from mapping table
        user_transforms.append({
            "lookup": lookup_key,
            "from": {
                "data": {"values": mapping_values},
                "key": "_src",
                "fields": ["_topo"],
            },
        })

        # Step 3: Fall back to original value if no mapping found (for name encoding)
        if geo_encoding not in ("iso2", "iso3"):
            user_transforms.append({
                "calculate": f"datum._topo || datum['{x_field}']",
                "as": "_topo",
            })

        # Step 4: Look up geo features from TopoJSON
        user_transforms.append({
            "lookup": "_topo",
            "from": {
                "data": {
                    "url": topojson_url,
                    "format": {"type": "topojson", "feature": "countries"},
                },
                "key": "properties.name",
            },
            "as": "geo",
        })

        # Step 5: Filter out unmatched countries
        user_transforms.append({"filter": "datum.geo != null"})

        # Two-layer approach: base map (gray) + colored data overlay
        tooltip_enc = {k: v for k, v in color_enc.items() if k != "scale"}

        vl = {
            "width": 600,
            "height": 400,
            "projection": {"type": "equalEarth"},
            "layer": [
                {
                    "data": {
                        "url": topojson_url,
                        "format": {"type": "topojson", "feature": "countries"},
                    },
                    "mark": {
                        "type": "geoshape",
                        "fill": "#e0e0e0",
                        "stroke": "#fff",
                        "strokeWidth": 0.5,
                    },
                },
                {
                    "data": user_data,
                    "transform": user_transforms,
                    "mark": {"type": "geoshape", "stroke": "#fff", "strokeWidth": 0.5},
                    "encoding": {
                        "shape": {"field": "geo", "type": "geojson"},
                        "color": color_enc,
                        "tooltip": [
                            {"field": x_field, "type": "nominal", "title": "Country"},
                            tooltip_enc,
                        ],
                    },
                },
            ],
        }
        return vl

    def _build_box(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        return {
            "mark": {"type": "boxplot", "extent": "min-max", "color": primary},
            "encoding": {
                "x": {"field": chart.get("x", "x"), "type": "nominal"},
                "y": {
                    "field": chart.get("y", "y"),
                    "type": "quantitative",
                    "scale": {"zero": False},
                },
                "color": {"field": chart.get("x", "x"), "type": "nominal", "legend": None},
            },
        }

    def _build_bubble(self, chart: dict, spec: "NormalizedSpec") -> dict:
        group = chart.get("group", "")
        size_field = chart.get("size", "")
        agg = chart.get("agg", "sum")

        enc = {
            "x": {
                "field": chart.get("x", "x"),
                "type": "quantitative",
                "aggregate": AGG_MAP.get(agg, "sum"),
            },
            "y": {
                "field": chart.get("y", "y"),
                "type": "quantitative",
                "aggregate": AGG_MAP.get(agg, "sum"),
            },
            "tooltip": [
                {"field": chart.get("x", "x"), "type": "quantitative"},
                {"field": chart.get("y", "y"), "type": "quantitative"},
            ],
        }

        if group:
            style = spec.get("style", {})
            secondary = style.get("secondary", DEFAULT_SECONDARY_COLORS)
            color_enc = {"field": group, "type": "nominal"}
            if isinstance(secondary, list) and secondary:
                color_enc["scale"] = {"range": secondary}
            enc["color"] = color_enc
            enc["tooltip"].append({"field": group, "type": "nominal"})

        if size_field:
            enc["size"] = {
                "field": size_field,
                "type": "quantitative",
                "aggregate": AGG_MAP.get(agg, "sum"),
            }
            enc["tooltip"].append({"field": size_field, "type": "quantitative"})

        return {
            "mark": {"type": "point", "filled": True, "opacity": 0.7},
            "encoding": enc,
        }

    def _build_metric(self, chart: dict, spec: "NormalizedSpec") -> dict:
        """Metric as a large text mark showing the aggregate value."""
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        agg = chart.get("agg", "sum")
        y_field = chart.get("y", "y")
        suffix = chart.get("suffix", "")
        fmt = chart.get("format")

        # Resolve format
        format_str = ""
        if fmt:
            format_str = resolve_metric_format(fmt)

        enc_text = {"type": "quantitative"}
        if agg == "count":
            enc_text["aggregate"] = "count"
        else:
            enc_text["field"] = y_field
            enc_text["aggregate"] = AGG_MAP.get(agg, "sum")
        if format_str:
            enc_text["format"] = format_str

        return {
            "width": 200,
            "height": 80,
            "mark": {
                "type": "text",
                "fontSize": 36,
                "fontWeight": "bold",
                "color": primary,
            },
            "encoding": {
                "text": enc_text,
            },
        }

    # ── Config (theme) ─────────────────────────────────────────────

    def _build_config(self, spec: "NormalizedSpec") -> dict:
        """Build Vega-Lite config block from style."""
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        secondary = style.get("secondary", DEFAULT_SECONDARY_COLORS)
        background = style.get("background")
        text_color = style.get("text")

        config = {}

        if isinstance(secondary, list) and secondary:
            config["range"] = {"category": secondary}

        if background:
            config["background"] = background

        if text_color:
            config["title"] = {"color": text_color}
            config["axis"] = {"labelColor": text_color, "titleColor": text_color}
            config["legend"] = {"labelColor": text_color, "titleColor": text_color}

        return config
