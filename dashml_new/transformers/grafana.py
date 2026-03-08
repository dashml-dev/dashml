"""
Grafana Dashboard JSON Transformer

Generates a Grafana dashboard JSON file that can be imported via:
  - Grafana UI: Dashboards > Import > Upload JSON
  - File provisioning: Copy to /var/lib/grafana/dashboards/

Uses __inputs variable placeholders so Grafana's import wizard
prompts the user to select their datasource.
"""
import json
from typing import TYPE_CHECKING

from .base import Transformer
from .constants import resolve_metric_format, DEFAULT_PRIMARY_COLOR, DEFAULT_SECONDARY_COLORS

if TYPE_CHECKING:
    from ..core.types import NormalizedSpec


# Grafana panel type mapping
CHART_TYPE_TO_PANEL = {
    "metric": "stat",
    "bar": "barchart",
    "line": "timeseries",
    "area": "timeseries",
    "pie": "piechart",
    "histogram": "histogram",
    "stacked_bar": "barchart",
    "grouped_bar": "barchart",
    "scatter": "xychart",
    "heatmap": "heatmap",
    "geo": "geomap",
    "box": "text",
    "bubble": "xychart",
}

# Grafana datasource type strings for db_config types
DB_TYPE_TO_GRAFANA_DS = {
    "postgresql": "postgres",
    "mysql": "mysql",
    "sqlite": "grafana-sqlite-datasource",
    "bigquery": "grafana-bigquery-datasource",
}

# Heatmap color scheme mapping from DashML sequential names
SEQUENTIAL_TO_HEATMAP_SCHEME = {
    "blues": "interpolateBlues",
    "greens": "interpolateGreens",
    "reds": "interpolateReds",
    "purples": "interpolatePurples",
    "oranges": "interpolateOranges",
    "viridis": "interpolateViridis",
    "cividis": "interpolateCividis",
    "teals": "interpolateGreens",  # close approximation
}

# Grid constants
GRID_COLS = 24
METRIC_WIDTH = 6
METRIC_HEIGHT = 4
CHART_WIDTH = 12
CHART_HEIGHT = 8
ROW_HEIGHT = 1


class GrafanaTransformer(Transformer):
    """Generates Grafana dashboard JSON for import."""

    def __init__(self, datasource_uid: str | None = None, csv_url: str | None = None):
        super().__init__()
        self._datasource_uid = datasource_uid or "${DS_DATASOURCE}"
        self._csv_url = csv_url

    @property
    def name(self) -> str:
        return "grafana"

    @property
    def description(self) -> str:
        return "Grafana dashboard JSON (import via UI or file provisioning)"

    @property
    def output_filename(self) -> str:
        return "dashboard.json"

    def get_run_command(self, output_path: str) -> str:
        return (
            f'echo "Import {output_path}/dashboard.json into Grafana: '
            f'Dashboards > Import > Upload JSON file"'
        )

    def build(self, spec: "NormalizedSpec") -> str:
        self.clear_warnings()
        data_type = spec.get("data", {}).get("type", "csv")

        if data_type == "csv" and not self._csv_url:
            self.warn(
                "Grafana is not designed for static CSV data. "
                "Use --grafana-csv-url to point to a served CSV (Infinity plugin), "
                "or convert to SQL. Panels will be generated without queries."
            )

        # Warn about unsupported style properties
        style = spec.get("style", {})
        if style.get("background"):
            self.warn("'background' color is not supported — Grafana theme is instance-level")
        if style.get("card"):
            self.warn("'card' color is not supported — Grafana theme is instance-level")
        if style.get("buttons"):
            self.warn("'buttons' color is not supported — Grafana theme is instance-level")

        pages = spec.get("pages", [])
        panels = []
        panel_id = 1
        y_pos = 0

        for page_idx, page in enumerate(pages):
            # Add row panel for multi-page dashboards
            if len(pages) > 1:
                row_panel = self._build_row_panel(
                    panel_id, page.get("title", f"Page {page_idx + 1}"), y_pos
                )
                panels.append(row_panel)
                panel_id += 1
                y_pos += ROW_HEIGHT

            # Layout charts within this page
            charts = page.get("charts", [])
            page_panels, y_pos, panel_id = self._layout_page_charts(
                charts, panel_id, y_pos, spec
            )
            panels.extend(page_panels)

        dashboard = self._build_dashboard_envelope(spec, panels)
        return json.dumps(dashboard, indent=2)

    # ── Dashboard envelope ─────────────────────────────────────────

    def _build_dashboard_envelope(self, spec: "NormalizedSpec", panels: list) -> dict:
        """Build top-level Grafana dashboard JSON with __inputs and __requires."""
        ds_type = self._resolve_datasource_type(spec)

        dashboard = {
            "__inputs": [
                {
                    "name": "DS_DATASOURCE",
                    "label": "Datasource",
                    "description": "Select your datasource",
                    "type": "datasource",
                    "pluginId": ds_type,
                    "pluginName": ds_type.capitalize(),
                }
            ],
            "__requires": [
                {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "10.0.0"},
                {"type": "datasource", "id": ds_type, "name": ds_type.capitalize(), "version": "1.0.0"},
            ],
            "annotations": {"list": []},
            "editable": True,
            "fiscalYearStartMonth": 0,
            "graphTooltip": 1,  # shared crosshair
            "id": None,
            "links": [],
            "panels": panels,
            "schemaVersion": 39,
            "tags": ["dashml", "auto-generated"],
            "templating": {"list": []},
            "time": {"from": "now-6h", "to": "now"},
            "timepicker": {},
            "timezone": "",
            "title": spec.get("title", "DashML Dashboard"),
            "uid": None,
            "version": 0,
            "weekStart": "",
        }
        return dashboard

    def _resolve_datasource_type(self, spec: "NormalizedSpec") -> str:
        """Map db_config type to Grafana datasource plugin ID."""
        data_type = spec.get("data", {}).get("type", "csv")
        if data_type == "csv" and self._csv_url:
            return "yesoreyeram-infinity-datasource"
        db_config = spec.get("db_config")
        if db_config:
            db_type = db_config.get("type", "")
            return DB_TYPE_TO_GRAFANA_DS.get(db_type, "postgres")
        if data_type == "bigquery":
            return "grafana-bigquery-datasource"
        return "postgres"

    # ── Row panels ─────────────────────────────────────────────────

    def _build_row_panel(self, panel_id: int, title: str, y_pos: int) -> dict:
        """Build a collapsible row panel for page sections."""
        return {
            "id": panel_id,
            "type": "row",
            "title": title,
            "collapsed": False,
            "gridPos": {"h": ROW_HEIGHT, "w": GRID_COLS, "x": 0, "y": y_pos},
            "panels": [],
        }

    # ── Layout ─────────────────────────────────────────────────────

    def _layout_page_charts(
        self, charts: list, panel_id: int, y_pos: int, spec: "NormalizedSpec"
    ) -> tuple[list, int, int]:
        """Layout charts: metrics 4-per-row (w=6), charts 2-per-row (w=12)."""
        panels = []

        # Separate metrics from charts
        metrics = [c for c in charts if c.get("type") == "metric"]
        non_metrics = [c for c in charts if c.get("type") != "metric"]

        # Layout metrics: 4 per row
        for i, chart in enumerate(metrics):
            col = (i % 4) * METRIC_WIDTH
            if i % 4 == 0 and i > 0:
                y_pos += METRIC_HEIGHT
            panel = self._build_panel_for_chart(chart, panel_id, col, y_pos, METRIC_WIDTH, METRIC_HEIGHT, spec)
            panels.append(panel)
            panel_id += 1

        if metrics:
            y_pos += METRIC_HEIGHT

        # Layout non-metric charts: 2 per row
        for i, chart in enumerate(non_metrics):
            col = (i % 2) * CHART_WIDTH
            if i % 2 == 0 and i > 0:
                y_pos += CHART_HEIGHT
            panel = self._build_panel_for_chart(chart, panel_id, col, y_pos, CHART_WIDTH, CHART_HEIGHT, spec)
            panels.append(panel)
            panel_id += 1

        if non_metrics:
            y_pos += CHART_HEIGHT

        return panels, y_pos, panel_id

    # ── Panel builder ──────────────────────────────────────────────

    def _build_panel_for_chart(
        self, chart: dict, panel_id: int,
        x: int, y: int, w: int, h: int,
        spec: "NormalizedSpec"
    ) -> dict:
        """Build a complete Grafana panel for a chart."""
        chart_type = chart.get("type", "bar")
        panel_type = CHART_TYPE_TO_PANEL.get(chart_type, "barchart")

        panel = {
            "id": panel_id,
            "type": panel_type,
            "title": chart.get("title", chart.get("id", "")),
            "gridPos": {"h": h, "w": w, "x": x, "y": y},
            "datasource": {
                "type": self._resolve_datasource_type(spec),
                "uid": self._datasource_uid,
            },
            "targets": [],
            "fieldConfig": {
                "defaults": {
                    "custom": {},
                },
                "overrides": [],
            },
            "options": {},
        }

        # Add query target
        data_type = spec.get("data", {}).get("type", "csv")
        sql = chart.get("sql")
        if data_type == "csv" and self._csv_url:
            # Infinity plugin CSV target
            panel["targets"].append(self._build_infinity_target(chart, spec))
        elif sql:
            resolved_sql = self._resolve_sql(sql, spec)
            panel["targets"].append({
                "refId": "A",
                "datasource": {
                    "type": self._resolve_datasource_type(spec),
                    "uid": self._datasource_uid,
                },
                "rawSql": resolved_sql,
                "format": "table",
            })

        # Configure panel type-specific options
        configurator = getattr(self, f"_configure_{chart_type}_panel", None)
        if configurator:
            configurator(panel, chart, spec)

        # Apply theme colors
        self._apply_theme(panel, chart, spec)

        return panel

    # ── SQL resolution ─────────────────────────────────────────────

    def _resolve_sql(self, sql_template: str, spec: "NormalizedSpec") -> str:
        """Substitute {table_ref} and {filter_clause} in SQL template."""
        data = spec.get("data", {})
        schema = data.get("sql_schema", "public")
        table = data.get("sql_table", "")
        bq_dataset = data.get("bq_dataset", "")
        bq_table = data.get("bq_table", "")

        data_type = data.get("type", "csv")
        if data_type == "bigquery":
            table_ref = f"`{bq_dataset}.{bq_table}`"
        else:
            table_ref = f"{schema}.{table}" if schema else table

        resolved = sql_template.replace("{table_ref}", table_ref)
        resolved = resolved.replace("{filter_clause}", "1=1")
        return resolved

    # ── Infinity CSV target ────────────────────────────────────────

    def _build_infinity_target(self, chart: dict, spec: "NormalizedSpec") -> dict:
        """Build an Infinity datasource target that reads CSV from a URL."""
        chart_type = chart.get("type", "bar")
        x_field = chart.get("x", "")
        y_field = chart.get("y", "")
        agg = chart.get("agg", "sum")
        group = chart.get("group", "")

        # Build columns list based on chart type
        columns = []
        if x_field:
            col_type = "timestamp" if chart.get("x_type") == "date" else "string"
            columns.append({"selector": x_field, "text": x_field, "type": col_type})
        if y_field:
            columns.append({"selector": y_field, "text": y_field, "type": "number"})
        if group:
            columns.append({"selector": group, "text": group, "type": "string"})

        # Size field for bubble
        size = chart.get("size", "")
        if size and size != y_field and size != x_field:
            columns.append({"selector": size, "text": size, "type": "number"})

        return {
            "refId": "A",
            "datasource": {
                "type": "yesoreyeram-infinity-datasource",
                "uid": self._datasource_uid,
            },
            "type": "csv",
            "source": "url",
            "url": self._csv_url,
            "url_options": {
                "method": "GET",
                "params": [],
                "headers": [],
                "data": "",
                "body_type": "",
                "body_content_type": "",
                "body_form": [],
                "body_graphql_query": "",
            },
            "format": "table",
            "columns": columns,
            "computed_columns": [],
            "filters": [],
            "root_selector": "",
            "parser": "backend",
            "csv_options": {
                "delimiter": ",",
                "skip_empty_lines": True,
                "skip_lines_with_error": True,
            },
            "filterExpression": "",
            "summarizeExpression": "",
            "summarizeBy": "",
            "dataOverrides": [],
            "data": "",
            "uql": "",
            "groq": "",
            "expression": "",
            "alias": "",
            "seriesCount": 0,
            "global_query_id": "",
            "query_mode": "",
        }

    # ── Chart type configurators ───────────────────────────────────

    def _configure_metric_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure stat panel for metric charts."""
        panel["options"] = {
            "reduceOptions": {
                "values": False,
                "calcs": [self._agg_to_grafana_calc(chart.get("agg", "sum"))],
                "fields": "",
            },
            "graphMode": "none",
            "colorMode": "value",
            "justifyMode": "auto",
            "textMode": "auto",
            "wideLayout": True,
            "showPercentChange": False,
            "orientation": "auto",
        }

        # Apply format / suffix
        fmt = chart.get("format")
        suffix = chart.get("suffix", "")
        if fmt:
            resolved_fmt = resolve_metric_format(fmt)
            # Extract decimals from format like ",.2f"
            decimals = 0
            if "." in resolved_fmt:
                try:
                    decimals = int(resolved_fmt.split(".")[1].rstrip("f"))
                except (IndexError, ValueError):
                    pass
            panel["fieldConfig"]["defaults"]["decimals"] = decimals
            panel["fieldConfig"]["defaults"]["unit"] = "none"

        if suffix:
            panel["fieldConfig"]["defaults"]["unit"] = "suffix:" + suffix

    def _configure_bar_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure barchart panel for bar charts."""
        panel["options"] = {
            "orientation": "horizontal" if chart.get("sort") else "auto",
            "xTickLabelRotation": 0,
            "showValue": "auto",
            "stacking": "none",
            "groupWidth": 0.7,
            "barWidth": 0.97,
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        }
        panel["fieldConfig"]["defaults"]["custom"] = {
            "axisBorderShow": False,
            "fillOpacity": 80,
            "gradientMode": "none",
            "lineWidth": 1,
        }

    def _configure_line_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure timeseries panel for line charts."""
        panel["options"] = {
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        }
        panel["fieldConfig"]["defaults"]["custom"] = {
            "drawStyle": "line",
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "fillOpacity": 0,
            "gradientMode": "none",
            "spanNulls": False,
            "pointSize": 5,
            "showPoints": "auto",
            "axisBorderShow": False,
        }

    def _configure_area_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure timeseries panel for area charts."""
        panel["options"] = {
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        }
        panel["fieldConfig"]["defaults"]["custom"] = {
            "drawStyle": "line",
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "fillOpacity": 25,
            "gradientMode": "opacity",
            "spanNulls": False,
            "pointSize": 5,
            "showPoints": "auto",
            "axisBorderShow": False,
        }

    def _configure_pie_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure piechart panel for pie charts."""
        panel["options"] = {
            "pieType": "pie",
            "reduceOptions": {
                "values": True,
                "calcs": [],
                "fields": "",
            },
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"displayMode": "table", "placement": "right", "values": ["value", "percent"]},
            "displayLabels": [],
        }

    def _configure_histogram_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure histogram panel."""
        bins = chart.get("bins", 20)
        panel["options"] = {
            "bucketCount": bins,
            "combine": False,
            "fillOpacity": 80,
            "gradientMode": "none",
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        }

    def _configure_stacked_bar_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure barchart panel with stacking for stacked_bar charts."""
        panel["options"] = {
            "orientation": "auto",
            "xTickLabelRotation": 0,
            "showValue": "auto",
            "stacking": "normal",
            "groupWidth": 0.7,
            "barWidth": 0.97,
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        }
        panel["fieldConfig"]["defaults"]["custom"] = {
            "axisBorderShow": False,
            "fillOpacity": 80,
            "gradientMode": "none",
            "lineWidth": 1,
        }

    def _configure_grouped_bar_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure barchart panel without stacking for grouped_bar charts."""
        panel["options"] = {
            "orientation": "auto",
            "xTickLabelRotation": 0,
            "showValue": "auto",
            "stacking": "none",
            "groupWidth": 0.7,
            "barWidth": 0.97,
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        }
        panel["fieldConfig"]["defaults"]["custom"] = {
            "axisBorderShow": False,
            "fillOpacity": 80,
            "gradientMode": "none",
            "lineWidth": 1,
        }

    def _configure_scatter_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure xychart panel for scatter plots (Grafana 10+)."""
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "y")
        panel["options"] = {
            "seriesMapping": "manual",
            "dims": {
                "x": x_field,
            },
            "series": [
                {
                    "x": {"field": x_field},
                    "y": {"field": y_field},
                    "pointSize": {"fixed": 5},
                    "pointColor": {"fixed": "dark-green"},
                }
            ],
            "tooltip": {"mode": "single"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        }

    def _configure_heatmap_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure heatmap panel."""
        style = spec.get("style", {})
        sequential = style.get("sequential", "blues")
        scheme = SEQUENTIAL_TO_HEATMAP_SCHEME.get(sequential, "interpolateBlues")

        panel["options"] = {
            "calculate": True,
            "calculation": {"xBuckets": {"mode": "count"}, "yBuckets": {"mode": "count"}},
            "color": {
                "mode": "scheme",
                "scheme": scheme,
                "steps": 64,
            },
            "cellGap": 1,
            "filterValues": {"le": 1e-9},
            "tooltip": {"show": True, "yHistogram": False},
            "legend": {"show": True},
            "yAxis": {"axisPlacement": "left"},
        }

    def _configure_geo_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure geomap panel."""
        self.warn(
            "Geo chart: Grafana geomap needs lat/lon fields or a lookup plugin. "
            "Ensure your data includes geographic coordinates or use the Geomap plugin's built-in lookup."
        )
        panel["options"] = {
            "view": {
                "id": "zero",
                "lat": 0,
                "lon": 0,
                "zoom": 1,
            },
            "basemap": {"type": "default", "name": "Layer 0"},
            "layers": [
                {
                    "type": "markers",
                    "name": "Markers",
                    "config": {
                        "showLegend": True,
                        "style": {
                            "size": {"fixed": 5, "min": 2, "max": 15},
                            "color": {"fixed": "dark-green"},
                            "opacity": 0.6,
                        },
                    },
                    "location": {"mode": "auto"},
                }
            ],
            "controls": {"showZoom": True, "mouseWheelZoom": True, "showAttribution": True},
            "tooltip": {"mode": "details"},
        }

    def _configure_box_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Box plot is not natively supported in Grafana — render as markdown placeholder."""
        self.warn(
            f"Chart '{chart.get('id')}': Box plots are not natively supported in Grafana. "
            "Showing a text placeholder."
        )
        panel["type"] = "text"
        x_field = chart.get("x", "category")
        y_field = chart.get("y", "value")
        panel["options"] = {
            "mode": "markdown",
            "content": (
                f"## {chart.get('title', 'Box Plot')}\n\n"
                f"Box plots are not natively supported in Grafana.\n\n"
                f"**Fields:** `{x_field}` vs `{y_field}`\n\n"
                f"Consider using the [Plotly panel plugin](https://grafana.com/grafana/plugins/natel-plotly-panel/) "
                f"or the Business Charts (Apache ECharts) plugin for box plot support."
            ),
        }
        panel["targets"] = []

    def _configure_bubble_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Bubble chart rendered as scatter (no size encoding in Grafana XY chart)."""
        self.warn(
            f"Chart '{chart.get('id')}': Grafana XY Chart does not support size encoding. "
            "Rendered as scatter plot."
        )
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "y")
        panel["options"] = {
            "seriesMapping": "manual",
            "dims": {
                "x": x_field,
            },
            "series": [
                {
                    "x": {"field": x_field},
                    "y": {"field": y_field},
                    "pointSize": {"fixed": 5},
                    "pointColor": {"fixed": "dark-green"},
                }
            ],
            "tooltip": {"mode": "single"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        }

    # ── Theme / color application ──────────────────────────────────

    def _apply_theme(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Apply style.primary / style.secondary colors to panel fieldConfig."""
        style = spec.get("style", {})
        primary = style.get("primary", DEFAULT_PRIMARY_COLOR)
        secondary = style.get("secondary", DEFAULT_SECONDARY_COLORS)
        chart_type = chart.get("type", "")

        # Skip theme for text panels (box placeholder)
        if panel.get("type") == "text":
            return

        defaults = panel["fieldConfig"]["defaults"]

        # Multi-series charts: use palette-classic with secondary color overrides
        if chart_type in ("stacked_bar", "grouped_bar", "pie", "heatmap"):
            defaults["color"] = {
                "mode": "palette-classic",
            }
            # Add overrides for each secondary color
            if isinstance(secondary, list) and secondary:
                overrides = []
                for i, color in enumerate(secondary):
                    overrides.append({
                        "matcher": {"id": "byFrameRefID"},
                        "properties": [
                            {"id": "color", "value": {"mode": "fixed", "fixedColor": color}}
                        ],
                    })
                # Only set if not already heavily customized
                if not panel["fieldConfig"]["overrides"]:
                    panel["fieldConfig"]["overrides"] = overrides
        else:
            # Single-series: use fixed primary color
            defaults["color"] = {
                "mode": "fixed",
                "fixedColor": primary,
            }

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _agg_to_grafana_calc(agg: str) -> str:
        """Map DashML aggregation to Grafana reduce calculation."""
        return {
            "sum": "sum",
            "mean": "mean",
            "count": "count",
        }.get(agg, "sum")
