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
    "heatmap": "table",
    "geo": "geomap",
    "box": "text",
    "bubble": "xychart",
}

# Grafana datasource type strings for db_config types
DB_TYPE_TO_GRAFANA_DS = {
    "postgresql": "grafana-postgresql-datasource",
    "mysql": "grafana-mysql-datasource",
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

    # Human-readable names for Grafana datasource plugins
    _DS_DISPLAY_NAMES = {
        "grafana-postgresql-datasource": "PostgreSQL",
        "grafana-mysql-datasource": "MySQL",
        "grafana-sqlite-datasource": "SQLite",
        "grafana-bigquery-datasource": "BigQuery",
        "yesoreyeram-infinity-datasource": "Infinity",
    }

    def _build_dashboard_envelope(self, spec: "NormalizedSpec", panels: list) -> dict:
        """Build top-level Grafana dashboard JSON with __inputs and __requires."""
        ds_type = self._resolve_datasource_type(spec)
        ds_name = self._DS_DISPLAY_NAMES.get(ds_type, ds_type)

        dashboard = {
            "__inputs": [
                {
                    "name": "DS_DATASOURCE",
                    "label": "Datasource",
                    "description": "Select your datasource",
                    "type": "datasource",
                    "pluginId": ds_type,
                    "pluginName": ds_name,
                }
            ],
            "__requires": [
                {"type": "grafana", "id": "grafana", "name": "Grafana", "version": "10.0.0"},
                {"type": "datasource", "id": ds_type, "name": ds_name, "version": "1.0.0"},
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
            return DB_TYPE_TO_GRAFANA_DS.get(db_type, "grafana-postgresql-datasource")
        if data_type == "bigquery":
            return "grafana-bigquery-datasource"
        return "grafana-postgresql-datasource"

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
            "pluginVersion": "12.4.0",
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

        # For SQL mode, the query aliases columns to x/y/grp/size.
        # Panel configurators must use these aliased names instead of original field names.
        if sql:
            chart = dict(chart)  # shallow copy to avoid mutating original
            chart["x"] = "x"
            if chart.get("y"):
                chart["y"] = "y"
            if chart.get("group"):
                # Heatmap SQL aliases group as "heatmap_y", others as "grp"
                chart["group"] = "heatmap_y" if chart_type == "heatmap" else "grp"
            if chart.get("size"):
                chart["size"] = "size"

        # Configure panel type-specific options
        configurator = getattr(self, f"_configure_{chart_type}_panel", None)
        if configurator:
            configurator(panel, chart, spec)

        # Add data transformations
        if data_type == "csv" and self._csv_url:
            # CSV: full pipeline (filters, groupBy, sort, limit, pivot)
            transforms = self._build_transformations(chart)
            if transforms:
                # Prepend to any transforms added by the configurator (e.g. groupingToMatrix)
                existing = panel.get("transformations", [])
                panel["transformations"] = transforms + existing
        elif sql:
            # SQL: data comes pre-aggregated, but pivot is still needed
            # for stacked/grouped bars and heatmap
            pivot = self._build_pivot_transform(chart)
            if pivot:
                existing = panel.get("transformations", [])
                panel["transformations"] = existing + pivot

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
            if chart.get("x_type") == "date":
                col_type = "timestamp"
            elif chart_type in ("scatter", "bubble", "histogram"):
                col_type = "number"
            else:
                col_type = "string"
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

    # ── Panel transformations ─────────────────────────────────────

    # DashML agg → Grafana groupBy aggregation name
    _AGG_TO_GRAFANA = {
        "sum": "sum",
        "mean": "mean",
        "count": "count",
    }

    # Chart types that don't need groupBy (they handle data differently)
    _NO_GROUPBY_TYPES = {"metric", "histogram", "scatter", "box"}

    # DashML filter op → Grafana filterByValue condition type
    _FILTER_OP_TO_GRAFANA = {
        "eq": "equal",
        "ne": "notEqual",
        "gt": "greater",
        "lt": "lower",
        "gte": "greaterOrEqual",
        "lte": "lowerOrEqual",
        "contains": "regex",
    }

    def _build_transformations(self, chart: dict) -> list:
        """Build Grafana panel transformations for CSV data."""
        transforms = []

        # 1. Filters (applied first, before aggregation)
        filters = chart.get("filters", [])
        if filters:
            transforms.extend(self._build_filter_transforms(filters))

        # 2. GroupBy aggregation
        chart_type = chart.get("type", "bar")
        agg = chart.get("agg")
        if chart_type not in self._NO_GROUPBY_TYPES and agg:
            transforms.extend(self._build_groupby_transform(chart))

        # 3. Sort and limit (skip for pivoted charts — pivot handles sort internally)
        has_pivot = chart_type in ("stacked_bar", "grouped_bar") and chart.get("group")
        sort_field = chart.get("sort")
        limit = chart.get("limit")

        if not has_pivot:
            if sort_field:
                transforms.extend(self._build_sort_transform(chart))
            if limit:
                transforms.append({"id": "limit", "options": {"maxRows": limit}})

        # 4. Pivot to wide format (stacked/grouped bar — includes sort by row total)
        transforms.extend(self._build_pivot_transform(chart))

        return transforms

    def _build_filter_transforms(self, filters: list) -> list:
        """Convert DashML filters to Grafana filterByValue transformations."""
        conditions = []
        for f in filters:
            field = f.get("field", "")
            op = f.get("op", "eq")
            value = f.get("value")

            if op == "in" and isinstance(value, list):
                # "in" → multiple OR conditions with "equal"
                for v in value:
                    conditions.append({
                        "config": {"id": "equal", "options": {"value": str(v)}},
                        "fieldName": field,
                    })
            elif op == "contains" and isinstance(value, str):
                conditions.append({
                    "config": {"id": "regex", "options": {"value": value}},
                    "fieldName": field,
                })
            else:
                grafana_op = self._FILTER_OP_TO_GRAFANA.get(op)
                if grafana_op:
                    conditions.append({
                        "config": {"id": grafana_op, "options": {"value": str(value)}},
                        "fieldName": field,
                    })

        if not conditions:
            return []

        return [{
            "id": "filterByValue",
            "options": {
                "filters": conditions,
                "type": "include",
                "match": "any" if any(f.get("op") == "in" for f in filters) else "all",
            },
        }]

    def _build_groupby_transform(self, chart: dict) -> list:
        """Build groupBy transformation for aggregation."""
        chart_type = chart.get("type", "bar")
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "y")
        group_field = chart.get("group")
        size_field = chart.get("size", "")
        agg = chart.get("agg", "sum")
        grafana_agg = self._AGG_TO_GRAFANA.get(agg, "sum")

        fields = {}
        rename_map = {}

        if chart_type == "bubble" and group_field:
            # Bubble: group by the group field, aggregate x, y, and size
            fields[group_field] = {"aggregations": [], "operation": "groupby"}
            fields[x_field] = {"aggregations": [grafana_agg], "operation": "aggregate"}
            fields[y_field] = {"aggregations": [grafana_agg], "operation": "aggregate"}
            rename_map[f"{x_field} ({grafana_agg})"] = x_field
            rename_map[f"{y_field} ({grafana_agg})"] = y_field
            if size_field:
                fields[size_field] = {"aggregations": [grafana_agg], "operation": "aggregate"}
                rename_map[f"{size_field} ({grafana_agg})"] = size_field
        elif agg == "count":
            fields[x_field] = {"aggregations": ["count"], "operation": "groupby"}
            if group_field and chart_type in ("stacked_bar", "grouped_bar", "heatmap"):
                fields[group_field] = {"aggregations": [], "operation": "groupby"}
        else:
            fields[x_field] = {"aggregations": [], "operation": "groupby"}
            if group_field and chart_type in ("stacked_bar", "grouped_bar", "heatmap"):
                fields[group_field] = {"aggregations": [], "operation": "groupby"}
            fields[y_field] = {"aggregations": [grafana_agg], "operation": "aggregate"}
            rename_map[f"{y_field} ({grafana_agg})"] = y_field

        transforms = [{"id": "groupBy", "options": {"fields": fields}}]

        # Rename aggregated columns back to clean names
        if rename_map:
            transforms.append({
                "id": "organize",
                "options": {"renameByName": rename_map},
            })

        return transforms

    def _build_pivot_transform(self, chart: dict) -> list:
        """Build groupingToMatrix pivot for multi-series charts (stacked/grouped bar)."""
        chart_type = chart.get("type", "bar")
        group_field = chart.get("group")
        if not group_field or chart_type not in ("stacked_bar", "grouped_bar"):
            return []

        x_field = chart.get("x", "x")
        y_field = chart.get("y", "")
        agg = chart.get("agg", "sum")

        if y_field:
            # SQL mode (y="y") or CSV non-count (y=original field name after rename)
            value_field = y_field
        elif agg == "count":
            # CSV count mode: groupBy produces "x_field (count)" column
            value_field = f"{x_field} (count)"
        else:
            value_field = x_field

        transforms = [{
            "id": "groupingToMatrix",
            "options": {
                "columnField": group_field,
                "rowField": x_field,
                "valueField": value_field,
            },
        }]

        # After pivot, sort by row total: calculate sum → sort → hide total column
        sort_field = chart.get("sort")
        sort_order = chart.get("sort_order", "asc")
        if sort_field:
            transforms.append({
                "id": "calculateField",
                "options": {
                    "mode": "reduceRow",
                    "reduce": {"reducer": "sum", "include": []},
                    "alias": "_total",
                    "replaceFields": False,
                },
            })
            transforms.append({
                "id": "sortBy",
                "options": {
                    "fields": {},
                    "sort": [{"field": "_total", "desc": sort_order == "desc"}],
                },
            })
            transforms.append({
                "id": "organize",
                "options": {
                    "excludeByName": {"_total": True},
                },
            })

        return transforms

    def _build_sort_transform(self, chart: dict) -> list:
        """Build sortBy transformation."""
        sort = chart.get("sort")
        sort_order = chart.get("sort_order", "asc")
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "")
        agg = chart.get("agg")

        if sort == "x":
            sort_field = x_field
        elif sort == "y":
            if y_field:
                sort_field = y_field
            elif agg == "count":
                # After groupBy count, the column is "x_field (count)"
                sort_field = f"{x_field} (count)"
            else:
                sort_field = x_field
        else:
            sort_field = sort  # direct field name

        return [{
            "id": "sortBy",
            "options": {
                "fields": {},
                "sort": [{"field": sort_field, "desc": sort_order == "desc"}],
            },
        }]

    # ── Panel type configurators ───────────────────────────────────

    def _configure_metric_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure stat panel for metric charts."""
        # For SQL mode, the query already aggregates — just display the value.
        # For CSV mode, the stat panel needs to reduce the raw data.
        data_type = spec.get("data", {}).get("type", "csv")
        if data_type in ("sql", "bigquery"):
            calc = "lastNotNull"
        else:
            calc = self._agg_to_grafana_calc(chart.get("agg", "sum"))
        panel["options"] = {
            "reduceOptions": {
                "values": False,
                "calcs": [calc],
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
        """Configure XY panel for scatter plots."""
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "y")
        panel["options"] = {
            "mapping": "manual",
            "series": [
                {
                    "frame": {"matcher": {"id": "byIndex", "options": 0}},
                    "x": {"matcher": {"id": "byName", "options": x_field}},
                    "y": {"matcher": {"id": "byName", "options": y_field}},
                }
            ],
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom", "calcs": []},
        }
        panel["fieldConfig"]["defaults"]["custom"] = {
            "show": "points",
            "pointSize": {"fixed": 5},
            "fillOpacity": 50,
            "axisPlacement": "auto",
            "axisBorderShow": False,
        }

    def _configure_heatmap_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure heatmap as a color-coded table.

        Grafana's native heatmap panel is a 2D histogram for numeric/time-series data.
        DashML's heatmap is a categorical grid (category × category, colored by value),
        which is the standard definition used by Seaborn, Plotly, Vega-Lite, and Tableau.
        We render it as a table with colored cell backgrounds to match the intended semantics.
        """
        self.warn(
            "Heatmap rendered as color-coded table. Grafana's native heatmap panel is a 2D histogram "
            "for numeric data, while DashML's heatmap is a categorical grid — the standard definition "
            "used by most visualization tools."
        )
        style = spec.get("style", {})
        sequential = style.get("sequential", "blues")

        # Map DashML sequential scheme to Grafana continuous color mode
        SEQUENTIAL_TO_CONTINUOUS = {
            "blues": "continuous-blues",
            "greens": "continuous-greens",
            "reds": "continuous-reds",
            "purples": "continuous-purples",
            "oranges": "continuous-YlOrRd",
            "viridis": "continuous-GrYlRd",
            "cividis": "continuous-GrYlRd",
            "teals": "continuous-greens",
        }
        color_mode = SEQUENTIAL_TO_CONTINUOUS.get(sequential, "continuous-blues")

        # Switch panel type from heatmap to table
        panel["type"] = "table"
        panel["options"] = {
            "showHeader": True,
            "cellHeight": "sm",
            "footer": {"show": False},
        }
        panel["fieldConfig"] = {
            "defaults": {
                "custom": {
                    "cellOptions": {"type": "color-background", "mode": "gradient"},
                    "inspect": False,
                    "align": "center",
                },
                "color": {"mode": color_mode},
                "thresholds": {
                    "mode": "percentage",
                    "steps": [
                        {"color": "transparent", "value": None},
                        {"color": color_mode.replace("continuous-", ""), "value": 0},
                    ],
                },
            },
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": chart.get("x", "x")},
                    "properties": [
                        {"id": "custom.cellOptions", "value": {"type": "auto"}},
                        {"id": "custom.width", "value": 150},
                    ],
                },
            ],
        }

        # Add groupingToMatrix transform to pivot the data
        x_field = chart.get("x", "x")
        group_field = chart.get("group", "y")
        y_field = chart.get("y", "value")
        agg = chart.get("agg", "sum")
        grafana_agg = self._AGG_TO_GRAFANA.get(agg, "sum")

        # The aggregated field name: SQL mode always uses "y",
        # CSV count mode produces "x_field (count)" after groupBy
        if y_field:
            value_field = y_field
        elif agg == "count":
            value_field = f"{x_field} (count)"
        else:
            value_field = x_field

        panel.setdefault("transformations", [])
        panel["transformations"].append({
            "id": "groupingToMatrix",
            "options": {
                "columnField": x_field,
                "rowField": group_field,
                "valueField": value_field,
            },
        })

    def _configure_geo_panel(self, panel: dict, chart: dict, spec: "NormalizedSpec") -> None:
        """Configure geomap panel with country lookup from built-in gazetteer."""
        x_field = chart.get("x", "country")
        y_field = chart.get("y", "value")
        agg = chart.get("agg", "sum")
        geo_encoding = chart.get("geo_encoding", "name")

        style = spec.get("style", {})
        sequential = style.get("sequential", "blues")
        SEQUENTIAL_TO_CONTINUOUS = {
            "blues": "continuous-blues",
            "greens": "continuous-greens",
            "reds": "continuous-reds",
            "purples": "continuous-purples",
            "oranges": "continuous-YlOrRd",
            "viridis": "continuous-GrYlRd",
        }
        color_mode = SEQUENTIAL_TO_CONTINUOUS.get(sequential, "continuous-blues")

        if geo_encoding == "name":
            self.warn(
                "Geo chart: country names may not fully match Grafana's built-in gazetteer. "
                "For best results, use geo_encoding: iso2 or iso3."
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
                    "name": "Data",
                    "config": {
                        "showLegend": True,
                        "style": {
                            "size": {"field": y_field, "min": 3, "max": 20},
                            "color": {"field": y_field},
                            "opacity": 0.7,
                            "symbol": {"fixed": "img/icons/marker/circle.svg", "mode": "fixed"},
                        },
                    },
                    "location": {
                        "mode": "lookup",
                        "lookup": x_field,
                        "gazetteer": "public/gazetteer/countries.json",
                    },
                }
            ],
            "controls": {"showZoom": True, "mouseWheelZoom": True, "showAttribution": True},
            "tooltip": {"mode": "details"},
        }

        # Color field by value using continuous scheme
        panel["fieldConfig"]["defaults"]["color"] = {"mode": color_mode}
        panel["fieldConfig"]["defaults"]["thresholds"] = {
            "mode": "percentage",
            "steps": [
                {"color": "transparent", "value": None},
                {"color": color_mode.replace("continuous-", ""), "value": 0},
            ],
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
        """Bubble chart using XY chart with size and color encoding.

        Uses partitionByValues transform to split data by group field,
        creating one series per category with automatic color assignment.
        """
        x_field = chart.get("x", "x")
        y_field = chart.get("y", "y")
        size_field = chart.get("size", "")
        group_field = chart.get("group", "")

        if group_field:
            self.warn(
                f"Chart '{chart.get('id')}': Grafana XY chart color field only supports numbers, "
                f"not categorical strings. Color by '{group_field}' is not applied."
            )

        series_config = {
            "frame": {"matcher": {"id": "byIndex", "options": 0}},
            "x": {"matcher": {"id": "byName", "options": x_field}},
            "y": {"matcher": {"id": "byName", "options": y_field}},
        }
        if size_field:
            series_config["size"] = {"matcher": {"id": "byName", "options": size_field}}

        panel["options"] = {
            "mapping": "manual",
            "series": [series_config],
            "tooltip": {"mode": "single", "sort": "none"},
            "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom", "calcs": []},
        }
        panel["fieldConfig"]["defaults"]["custom"] = {
            "show": "points",
            "pointSize": {"min": 3, "max": 30},
            "fillOpacity": 50,
            "axisPlacement": "auto",
            "axisBorderShow": False,
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

        # Multi-series charts: use palette-classic (Grafana assigns colors automatically)
        # Heatmap excluded — it uses continuous color set in _configure_heatmap_panel
        if chart_type in ("stacked_bar", "grouped_bar", "pie"):
            defaults["color"] = {
                "mode": "palette-classic",
            }
        elif chart_type not in ("heatmap", "geo", "bubble"):
            # Single-series: use fixed primary color
            # Heatmap/geo/bubble excluded — they set their own color mode
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
