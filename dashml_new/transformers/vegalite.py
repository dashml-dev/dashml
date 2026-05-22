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

from .base import Transformer, humanize_field
from .constants import (
    resolve_metric_format,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLORS,
    DESIGN_TOKENS,
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

        spec_json = json.dumps(result, indent=2)

        # Emit both the bare spec and a renderer index.html so the dashboard
        # can be viewed locally with vega-embed (no need for the Vega Editor,
        # which chokes on long gzipped URLs).
        title = spec.get("title", "Dashboard")
        bg = style.get("background", "#21222c")
        text = style.get("text", "#f8f8f2")
        renderer_html = self._build_renderer_html(title, bg, text)
        return json.dumps({
            "type": "multi-file",
            "files": {
                "dashboard.vl.json": spec_json,
                "index.html": renderer_html,
            },
        }, indent=2)

    def _build_renderer_html(self, title: str, bg: str, text: str) -> str:
        """Standalone HTML page that fetches dashboard.vl.json and renders via vega-embed."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <script src="https://cdn.jsdelivr.net/npm/vega@6"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-lite@6"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-embed@7"></script>
  <style>
    html, body {{
      margin: 0; padding: 0;
      background: {bg}; color: {text};
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Helvetica, Arial, sans-serif;
    }}
    .container {{ max-width: 1600px; margin: 0 auto; padding: 28px 32px 80px; }}
    #vis {{ width: 100%; }}
    .vega-actions a {{ color: {text} !important; }}
  </style>
</head>
<body>
  <div class="container">
    <div id="vis"></div>
  </div>
  <script>
    fetch('dashboard.vl.json')
      .then(r => r.json())
      .then(spec => vegaEmbed('#vis', spec, {{ actions: false, renderer: 'svg' }}))
      .catch(err => {{
        document.getElementById('vis').innerHTML = '<p style="color:#ff79c6">Error loading spec: ' + err.message + '</p>';
      }});
  </script>
</body>
</html>"""

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
        muted = DESIGN_TOKENS["muted"]

        for p_idx, page in enumerate(pages):
            charts = page.get("charts", [])
            layout = page.get("layout", {})
            charts_per_row = layout.get("columns", 2)
            metrics = [c for c in charts if c.get("type") == "metric"]
            non_metrics = [c for c in charts if c.get("type") != "metric"]

            # Page-section header: render the page title as a text mark so
            # multi-page dashboards have visible section boundaries when
            # concat'd into a single vega-lite spec. Skip when there's a
            # single page whose title matches the dashboard's — otherwise
            # the title would appear twice (dashboard.title + page header).
            page_title = page.get("title", page.get("id", ""))
            single_page_dup = (
                len(pages) == 1 and page_title == spec.get("title")
            )
            if page_title and not single_page_dup:
                rows.append({
                    "mark": {
                        "type": "text",
                        "text": page_title,
                        "align": "left",
                        "baseline": "top",
                        "fontSize": 16,
                        "fontWeight": 600,
                        "color": "#f8f8f2",
                        "dx": 0, "dy": 0,
                    },
                    "view": {"stroke": None},
                    "height": 24,
                    "width": 800,
                })

            # Metrics row: up to 4 per hconcat (unaffected by layout.columns)
            for i in range(0, len(metrics), 4):
                batch = metrics[i:i + 4]
                row_specs = [self._build_chart_spec(c, spec, top_level=False) for c in batch]
                if len(row_specs) == 1:
                    rows.append(row_specs[0])
                else:
                    rows.append({
                        "hconcat": row_specs,
                        # Independent scales per chart so a bar's [1..1.6M]
                        # domain doesn't flatten a geo choropleth into one shade.
                        "resolve": {"scale": {"color": "independent", "size": "independent"}},
                    })

            # Chart rows: N per hconcat (boxplot must be solo — crashes in hconcat with other marks)
            SOLO_TYPES = {"box"}
            i = 0
            while i < len(non_metrics):
                chart = non_metrics[i]
                if chart.get("type") in SOLO_TYPES:
                    rows.append(self._build_chart_spec(chart, spec, top_level=False))
                    i += 1
                else:
                    # Collect up to charts_per_row non-solo charts for this row
                    batch = []
                    while len(batch) < charts_per_row and i < len(non_metrics):
                        if non_metrics[i].get("type") in SOLO_TYPES:
                            break
                        batch.append(non_metrics[i])
                        i += 1
                    if len(batch) == 1:
                        rows.append(self._build_chart_spec(batch[0], spec, top_level=False))
                    else:
                        row_specs = [self._build_chart_spec(c, spec, top_level=False) for c in batch]
                        rows.append({
                        "hconcat": row_specs,
                        # Independent scales per chart so a bar's [1..1.6M]
                        # domain doesn't flatten a geo choropleth into one shade.
                        "resolve": {"scale": {"color": "independent", "size": "independent"}},
                    })

        dashboard = {
            "$schema": VEGALITE_SCHEMA,
            "title": spec.get("title", "DashML Dashboard"),
            "vconcat": rows,
            "config": self._build_config(spec),
            # Per-chart scales — without this, vconcat / hconcat siblings share
            # color/size domains. Concrete fallout: a geo choropleth in the
            # same hconcat row as a bar chart inherits the bar's [1, 1.6M]
            # domain and every country lands on the lightest shade.
            "resolve": {"scale": {"color": "independent", "size": "independent"}},
        }

        # Data is attached to each child chart, not at the dashboard level.
        # Top-level data in a vconcat + layered composition can shadow per-layer
        # data sources — geo choropleths in particular render gray when the
        # outer data block "wins" against the layer's CSV+lookup pipeline.
        # Each chart builder calls `_build_data` for itself.

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

        # Wrap in layer spec if reference lines or annotations are present
        vl = self._wrap_with_overlays(vl, chart)

        # Add common properties
        if top_level:
            vl.setdefault("$schema", VEGALITE_SCHEMA)
        vl.setdefault("title", chart.get("title", chart.get("id", "")))
        vl.setdefault("width", 400)
        vl.setdefault("height", 300)

        # Attach data per-chart (geo already sets its own at the layer level).
        # We do this unconditionally — even for child specs in a vconcat — so
        # the dashboard composition does not rely on top-level data inheritance
        # which Vega-Lite handles inconsistently for layered geo charts.
        if "data" not in vl:
            data_block = self._build_data(spec)
            if data_block:
                vl["data"] = data_block

        # Add filter transforms
        transforms = vl.get("transform", [])
        filter_transforms = self._build_filter_transforms(chart)
        if filter_transforms:
            transforms = filter_transforms + transforms

        # Add derived_field transforms — convert templated expressions like
        # "100 - {pct_delayed_15plus}" into Vega-Lite calculate transforms
        # "100 - datum.pct_delayed_15plus" so charts can reference the
        # computed columns (e.g. `on_time_rate`) without NaN.
        derived = spec.get("derived_fields", [])
        if derived:
            import re as _re
            calc_transforms = []
            for f in derived:
                expr = _re.sub(r'\{(\w+)\}', r'datum.\1', f["expression"])
                calc_transforms.append({"calculate": expr, "as": f["name"]})
            transforms = calc_transforms + transforms

        if transforms:
            vl["transform"] = transforms

        return vl

    def _wrap_with_overlays(self, vl: dict, chart: dict) -> dict:
        """Wrap chart in a layer spec if reference lines or annotations exist."""
        ref_lines = chart.get("reference_lines", [])
        annotations = chart.get("annotations", [])

        if not ref_lines and not annotations:
            return vl

        layers = [vl]

        # Reference lines as rule marks — default color is the design's amber
        # benchmark token (not red, which reads as an error).
        amber = DESIGN_TOKENS["amber"]
        for rl in ref_lines:
            axis = rl.get("axis", "y")
            color = rl.get("color", amber)
            rule: dict = {"mark": {"type": "rule", "color": color, "strokeWidth": 2}, "encoding": {}}
            if axis == "y":
                rule["encoding"]["y"] = {"datum": rl["value"]}
            else:
                rule["encoding"]["x"] = {"datum": rl["value"]}
            if rl.get("style") == "dashed":
                rule["mark"]["strokeDash"] = [6, 4]
            elif rl.get("style") == "dotted":
                rule["mark"]["strokeDash"] = [1, 3]
            layers.append(rule)

            # Add label as text layer if present
            if rl.get("label"):
                label_layer: dict = {
                    "mark": {
                        "type": "text", "align": "right", "baseline": "bottom",
                        "dx": -4, "dy": -4, "fontSize": 11, "fontWeight": 600,
                        "color": color,
                    },
                    "encoding": {"text": {"value": rl["label"]}},
                }
                if axis == "y":
                    label_layer["encoding"]["y"] = {"datum": rl["value"]}
                else:
                    label_layer["encoding"]["x"] = {"datum": rl["value"]}
                layers.append(label_layer)

        # Annotations as text marks — default color = amber for consistency
        for ann in annotations:
            text_layer: dict = {
                "mark": {
                    "type": "text", "fontSize": 12, "dy": -8,
                    "color": ann.get("color", amber),
                },
                "encoding": {},
            }
            if ann.get("x") is not None:
                text_layer["encoding"]["x"] = {"datum": ann["x"]}
            if ann.get("y") is not None:
                text_layer["encoding"]["y"] = {"datum": ann["y"]}
            text_layer["encoding"]["text"] = {"value": ann["text"]}
            layers.append(text_layer)

        return {"layer": layers}

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
        if chart.get("x_scale") == "log":
            enc["scale"] = {"type": "log"}
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
        if chart.get("y_scale") == "log":
            enc["scale"] = {"type": "log"}
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
        """Add aggregate + window rank + filter transforms for limit.

        Aggregates first so rank operates on totals, not individual rows.
        """
        limit = chart.get("limit")
        if not limit:
            return
        transforms = vl.get("transform", [])
        sort_order = chart.get("sort_order", "asc")
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "y")
        agg = chart.get("agg", "sum")
        agg_map = {"sum": "sum", "mean": "mean", "count": "count"}
        vl_agg = agg_map.get(agg, "sum")

        # Step 1: Aggregate so rank is on totals, not individual rows
        if agg == "count":
            transforms.append({
                "aggregate": [{"op": "count", "as": y_field}],
                "groupby": [x_field],
            })
        else:
            transforms.append({
                "aggregate": [{"op": vl_agg, "field": y_field, "as": y_field}],
                "groupby": [x_field],
            })

        # Step 2: Rank by aggregated value
        transforms.append({
            "window": [{"op": "rank", "as": "_rank"}],
            "sort": [{"field": y_field, "order": "descending" if sort_order == "desc" else "ascending"}],
        })

        # Step 3: Filter to top N
        transforms.append({"filter": f"datum._rank <= {limit}"})

        vl["transform"] = transforms

        # Remove aggregate from encoding since we did it in transforms,
        # and ensure field is set (count encoding has no field by default)
        enc = vl.get("encoding", {})
        y_enc = enc.get("y", {})
        if "aggregate" in y_enc:
            del y_enc["aggregate"]
        if "field" not in y_enc:
            y_enc["field"] = y_field

    # ── Chart type builders ────────────────────────────────────────

    def _build_bar(self, chart: dict, spec: "NormalizedSpec") -> dict:
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        # When sorted by y with no group, color bars with a light→dark purple
        # ramp keyed by rank — matches Plotly/Observable/Streamlit behavior.
        use_ramp = chart.get("sort") == "y" and not chart.get("group")
        y_field = chart.get("y", "y")
        encoding = {
            "x": self._x_encoding(chart),
            "y": self._y_encoding(chart),
            "tooltip": [
                {"field": chart.get("x", "x")},
                self._y_encoding(chart),
            ],
        }
        if use_ramp:
            encoding["color"] = {
                "field": y_field,
                "type": "quantitative",
                "aggregate": chart.get("agg", "sum"),
                "scale": {"scheme": "purples"},
                "legend": None,
            }
            mark = {"type": "bar"}
        else:
            mark = {"type": "bar", "color": primary}
        vl = {"mark": mark, "encoding": encoding}
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
        # Tonal shades from theme.sequential — same ramp the sorted-bar / bubble
        # use. Color is keyed by the categorical x field; the sequential scheme
        # maps category index to a light→dark progression (data is sorted by y
        # desc, so largest slice gets the darkest shade).
        #
        # Labels are baked INTO each slice as a text layer (category name + %),
        # rotated radially so they fan out from the centre — same affordance
        # the Plotly / Observable transformers give. The shared color legend
        # is therefore suppressed: identity already shows on the slice itself.
        style = spec.get("style", {})
        sequential = style.get("sequential", "blues")
        scheme = SEQUENTIAL_SCHEMES.get(sequential, "blues")
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "y")
        agg = chart.get("agg", "sum")
        y_enc = self._y_encoding(chart)

        color_enc = {
            "field": x_field,
            "type": "nominal",
            "scale": {"scheme": scheme},
            "legend": None,
        }

        outer_r = 150
        label_r = 105

        # Compute pct via a window transform so the text layer can show
        # "<name>  NN.N%" right inside each slice.
        pct_transform = [
            {
                "joinaggregate": [{"op": agg, "field": y_field, "as": "_total"}],
            },
            {
                "calculate": f"datum['{y_field}'] / datum._total * 100",
                "as": "_pct",
            },
            {
                "calculate": f"datum['{x_field}'] + ' ' + format(datum._pct, '.1f') + '%'",
                "as": "_label",
            },
        ]

        arc_layer = {
            "mark": {
                "type": "arc",
                "stroke": style.get("card", "#2e3040"),
                "strokeWidth": 1,
                "outerRadius": outer_r,
            },
            "encoding": {
                "theta": {**y_enc, "stack": True},
                "color": color_enc,
                "order": {"field": y_field, "aggregate": agg, "type": "quantitative", "sort": "descending"},
                "tooltip": [
                    {"field": x_field, "type": "nominal"},
                    y_enc,
                ],
            },
        }
        label_layer = {
            "mark": {
                "type": "text",
                "radius": label_r,
                "fontSize": 11,
                "fontWeight": 600,
                "color": "#1a1b24",
            },
            "encoding": {
                "theta": {**y_enc, "stack": True},
                "order": {"field": y_field, "aggregate": agg, "type": "quantitative", "sort": "descending"},
                "text": {"field": "_label", "type": "nominal"},
            },
        }

        # Apply limit FIRST (its aggregate transform drops unrelated columns,
        # so the pct/label calcs need to run on the post-limit row set).
        vl = {"layer": [arc_layer, label_layer]}
        self._apply_limit(vl, chart)
        vl.setdefault("transform", []).extend(pct_transform)
        return vl

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

        # User data source: embedded values or URL
        data = spec.get("data", {})
        csv_path = data.get("csv_path", "")
        csv_filename = Path(csv_path).name if csv_path else "data.csv"

        if self._embedded_data is not None:
            user_data = {"values": self._embedded_data}
        else:
            # Explicit CSV format hint — without it, vega-embed sometimes
            # treats the URL as JSON when the layer-level data block doesn't
            # match the top-level format.
            user_data = {"url": csv_filename, "format": {"type": "csv"}}

        topojson_url = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"

        # Build mapping table for country name normalization
        mapping_values = self._build_geo_mapping(geo_encoding)

        # User data transforms: aggregate → normalize → lookup → filter.
        # Pre-aggregating before the topojson lookup is essential: Vega-Lite's
        # encoding-level `aggregate: count` doesn't group on a geojson-typed
        # channel, so without this the choropleth renders one geoshape per
        # input row (and the colour scale collapses).
        user_transforms = []

        # Step 0: aggregate per country into a single metric column.
        metric_field = "_metric"
        if agg == "count":
            user_transforms.append({
                "aggregate": [{"op": "count", "as": metric_field}],
                "groupby": [x_field],
            })
        else:
            user_transforms.append({
                "aggregate": [{"op": AGG_MAP.get(agg, "sum"), "field": y_field, "as": metric_field}],
                "groupby": [x_field],
            })

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

        # Color encoding now points at the pre-aggregated _metric column.
        color_enc = {
            "field": metric_field,
            "type": "quantitative",
            "title": "count" if agg == "count" else y_field,
            "scale": {"scheme": scheme},
        }

        # Two-layer approach: base map (gray) + colored data overlay.
        # The user CSV is bound at the CHART level so the per-chart hoist in
        # _build_chart_spec sees `data` already set and won't add a duplicate
        # (un-formatted) block on top. Layer[0] overrides with the topojson
        # source; layer[1] inherits the CSV.
        vl = {
            "data": user_data,
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
                    "transform": user_transforms,
                    "mark": {"type": "geoshape", "stroke": "#fff", "strokeWidth": 0.5},
                    "encoding": {
                        "shape": {"field": "geo", "type": "geojson", "legend": None},
                        "color": color_enc,
                        "tooltip": [
                            {"field": x_field, "type": "nominal", "title": "Country"},
                            {"field": metric_field, "type": "quantitative", "title": color_enc["title"]},
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
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "y")
        size_field = chart.get("size", "")
        agg = chart.get("agg", "sum")
        vl_agg = AGG_MAP.get(agg, "sum")
        limit = chart.get("limit")
        sort_field = chart.get("sort")
        sort_order = chart.get("sort_order", "asc")

        # Aggregate in transforms so we get one point per group
        transforms = []
        if group:
            agg_fields = [
                {"op": vl_agg, "field": x_field, "as": x_field},
                {"op": vl_agg, "field": y_field, "as": y_field},
            ]
            if size_field:
                agg_fields.append({"op": vl_agg, "field": size_field, "as": size_field})
            transforms.append({
                "aggregate": agg_fields,
                "groupby": [group],
            })
            if limit:
                # Rank by the sort field (default y) then keep the top N — same
                # window/filter pattern _apply_limit uses for bar charts.
                rank_field = sort_field if sort_field in ("x", "y") else "y"
                rank_target = x_field if rank_field == "x" else y_field
                order = "descending" if sort_order == "desc" else "ascending"
                transforms.append({
                    "window": [{"op": "rank", "as": "_rank"}],
                    "sort": [{"field": rank_target, "order": order}],
                })
                transforms.append({"filter": f"datum._rank <= {limit}"})

        enc = {
            "x": {
                "field": x_field,
                "type": "quantitative",
                "title": humanize_field(x_field),
                "axis": {"format": "~s", "grid": False},
            },
            "y": {
                "field": y_field,
                "type": "quantitative",
                "title": humanize_field(y_field),
                "axis": {"grid": False},
            },
            "tooltip": [
                {"field": x_field, "type": "quantitative", "title": humanize_field(x_field)},
                {"field": y_field, "type": "quantitative", "title": humanize_field(y_field)},
            ],
        }

        if group:
            # Tonal shades from theme.sequential — too many groups for a useful
            # categorical legend, so hide the legend and let bubble position +
            # size carry the encoding (label-on-bubble would need a text mark
            # which Vega-Lite layered with point requires extra layers).
            style = spec.get("style", {})
            sequential = style.get("sequential", "blues")
            scheme = SEQUENTIAL_SCHEMES.get(sequential, "blues")
            enc["color"] = {
                "field": group,
                "type": "nominal",
                "scale": {"scheme": scheme},
                "legend": None,
            }
            enc["tooltip"].append({"field": group, "type": "nominal"})

        if size_field:
            # Widen the size range so volume differences read; suppress the
            # categorical size legend — the labelled bubbles already carry
            # the identity, and mean-of-fraction values (e.g. 0.001) make
            # the legend swatch noisy without adding information.
            enc["size"] = {
                "field": size_field,
                "type": "quantitative",
                "scale": {"range": [100, 1200]},
                "legend": None,
            }
            enc["tooltip"].append({"field": size_field, "type": "quantitative"})

        # Layered output: bubbles + text labels above each bubble so the chart
        # is self-describing without a giant categorical legend. dy=-12 lifts
        # the label above the bubble; small bubbles still get a label nearby.
        point_layer = {
            "mark": {"type": "point", "filled": True, "opacity": 0.7},
            "encoding": enc,
        }
        result: dict = {
            "width": 560,
            "height": 360,
            "layer": [point_layer],
        }
        if group:
            text_enc = {
                "x": enc["x"],
                "y": enc["y"],
                "text": {"field": group, "type": "nominal"},
            }
            result["layer"].append({
                "mark": {"type": "text", "dy": -14, "fontSize": 10, "color": "#c8cadf"},
                "encoding": text_enc,
            })
        if transforms:
            result["transform"] = transforms
        return result

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
        """Build Vega-Lite config block from style + design tokens."""
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        secondary = style.get("secondary", DEFAULT_SECONDARY_COLORS)
        background = style.get("background")
        text_color = style.get("text")
        card_bg = style.get("card", background)
        line_soft = DESIGN_TOKENS["line_soft"]
        muted = DESIGN_TOKENS["muted"]
        fg_dim = DESIGN_TOKENS["fg_dim"]

        config: dict = {}

        if isinstance(secondary, list) and secondary:
            config["range"] = {"category": secondary}

        if background:
            config["background"] = background
        if card_bg:
            # Per-chart "card": fill is the card surface, stroke is a clear
            # 1px line in the soft-border token so each chart reads as its
            # own bordered card against the page bg.
            config["view"] = {"fill": card_bg, "stroke": line_soft, "strokeWidth": 1}
            config["padding"] = {"top": 12, "bottom": 12, "left": 12, "right": 12}
            config["concat"] = {"spacing": 16}

        # Axis / grid styling driven by design tokens — gives a three-tier hierarchy
        # (grid faint, ticks dim, axis title muted) instead of a flat single-color.
        config["axis"] = {
            "gridColor": line_soft,
            "domainColor": line_soft,
            "tickColor": line_soft,
            "labelColor": fg_dim,
            "titleColor": muted,
            "labelFontSize": 11,
            "titleFontSize": 11,
            "titleFontWeight": "normal",
        }
        config["legend"] = {
            "labelColor": fg_dim,
            "titleColor": muted,
            "labelFontSize": 11,
            "titleFontSize": 11,
        }
        if text_color:
            config["title"] = {
                "color": text_color,
                "fontSize": 14,
                "fontWeight": 600,
                "anchor": "start",
            }

        return config
