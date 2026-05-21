"""
Plotly Transformer - Generates Plotly HTML/JavaScript from DashML specs
"""
import re
import sys
from typing import TYPE_CHECKING, Dict, Any, List
from pathlib import Path
import json
from .base import Transformer, TransformerError, humanize_field
from .constants import (
    CHARTS_NEED_AGGREGATION,
    CHARTS_USE_RAW_DATA,
    DEFAULT_HISTOGRAM_BINS,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLORS,
    DEFAULT_SORT_ORDER,
    DESIGN_TOKENS,
    PURPLE_RAMP,
    resolve_metric_format,
    resolve_plotly_colorscale,
    country_mapping_as_js,
)

# Chart types whose x-axis is discrete categorical — axis title is redundant
# with the tick labels and should be dropped unless explicitly overridden.
_DISCRETE_X_CHART_TYPES = frozenset({"bar", "stacked_bar", "grouped_bar", "box", "pie", "heatmap"})

if TYPE_CHECKING:
    from ..core.types import NormalizedSpec


class PlotlyTransformer(Transformer):
    """
    Generates standalone HTML files with Plotly.js visualizations.
    Output: HTML file that can be opened directly in a browser
    For SQL datasources: Generates Flask backend + HTML frontend (multi-file)
    """

    @property
    def name(self) -> str:
        return "plotly"

    @property
    def description(self) -> str:
        return "Generates Plotly.js HTML dashboards"

    def build(self, spec: "NormalizedSpec") -> str:
        """
        Generate Plotly HTML from NormalizedSpec.
        For CSV: Returns single HTML file
        For SQL: Returns JSON-encoded multi-file structure with Flask backend
        """
        try:
            self.clear_warnings()

            title = spec["title"]
            data_spec = spec["data"]
            data_type = data_spec.get("type", "csv")
            colors = spec["style"]

            if data_type == "sql":
                return self._build_sql_version(spec, title, data_spec, colors)
            elif data_type == "bigquery":
                return self._build_bigquery_version(spec, title, data_spec, colors)
            else:
                return self._build_csv_version(spec, title, data_spec, colors)

        except KeyError as e:
            raise TransformerError(f"Missing required field in spec: {e}")
        except Exception as e:
            raise TransformerError(f"Failed to generate Plotly code: {e}")

    # ------------------------------------------------------------------
    # Helpers for axis scale, annotations, and reference lines
    # ------------------------------------------------------------------

    @staticmethod
    def _axis_type_js(chart: dict, axis: str) -> str:
        """Return Plotly axis type string for the given axis ('x' or 'y').

        Returns 'log' when the spec says ``x_scale: log`` / ``y_scale: log``,
        otherwise returns '-' (Plotly auto-detect, which is the default).
        """
        scale = chart.get(f"{axis}_scale", "")
        if scale == "log":
            return "log"
        return "-"

    @staticmethod
    def _annotations_js(chart: dict) -> str:
        """Build a JS snippet that sets ``layout.annotations`` from the chart spec.

        Returns an empty string when there are no annotations so nothing is
        injected into the generated code.
        """
        annotations = chart.get("annotations")
        if not annotations:
            return ""
        amber = DESIGN_TOKENS["amber"]
        items = []
        for ann in annotations:
            x_val = json.dumps(ann.get("x", ""))
            y_val = json.dumps(ann.get("y", 0))
            text = json.dumps(ann.get("text", ""))
            color = json.dumps(ann.get("color", amber))
            items.append(
                f"{{ x: {x_val}, y: {y_val}, text: {text}, showarrow: true, arrowhead: 2, font: {{ color: {color} }} }}"
            )
        return "\n      layout.annotations = [" + ", ".join(items) + "];"

    @staticmethod
    def _reference_lines_js(chart: dict) -> str:
        """Build a JS snippet that sets ``layout.shapes`` from the chart spec.

        Reference lines default to the design's amber benchmark color
        (not red — red reads as an error state). Per-line ``color`` overrides
        the default. Labels render as right-anchored chips on the chart edge
        so they don't collide with the data.

        Returns an empty string when there are no reference lines.
        """
        ref_lines = chart.get("reference_lines")
        if not ref_lines:
            return ""
        style_map = {"solid": "solid", "dashed": "dash", "dotted": "dot"}
        amber = DESIGN_TOKENS["amber"]
        line_soft = DESIGN_TOKENS["line_soft"]
        items = []
        for rl in ref_lines:
            axis = rl.get("axis", "y")
            value = json.dumps(rl.get("value", 0))
            dash = style_map.get(rl.get("style", "dashed"), "dash")
            color = json.dumps(rl.get("color", amber))
            if axis == "y":
                shape = (
                    f"{{ type: 'line', yref: 'y', y0: {value}, y1: {value}, "
                    f"xref: 'paper', x0: 0, x1: 1, layer: 'above', "
                    f"line: {{ color: {color}, width: 2.5, dash: '{dash}' }} }}"
                )
            else:
                shape = (
                    f"{{ type: 'line', xref: 'x', x0: {value}, x1: {value}, "
                    f"yref: 'paper', y0: 0, y1: 1, layer: 'above', "
                    f"line: {{ color: {color}, width: 2.5, dash: '{dash}' }} }}"
                )
            items.append(shape)
        # Reference-line labels: right-anchored chip (xref: paper, x: 1).
        ann_items = []
        line_soft_json = json.dumps(line_soft)
        for rl in ref_lines:
            label = rl.get("label", "")
            if not label:
                continue
            axis = rl.get("axis", "y")
            value = json.dumps(rl.get("value", 0))
            color = json.dumps(rl.get("color", amber))
            label_json = json.dumps(f"  {label}  ")
            if axis == "y":
                ann_items.append(
                    f"{{ xref: 'paper', x: 1, xanchor: 'right', y: {value}, yref: 'y', "
                    f"yanchor: 'bottom', text: {label_json}, showarrow: false, "
                    f"font: {{ color: {color}, size: 12, weight: 600 }}, "
                    f"bgcolor: theme.card, bordercolor: {color}, borderwidth: 1, borderpad: 3 }}"
                )
            else:
                ann_items.append(
                    f"{{ yref: 'paper', y: 1, yanchor: 'top', x: {value}, xref: 'x', "
                    f"xanchor: 'left', text: {label_json}, showarrow: false, "
                    f"font: {{ color: {color}, size: 12, weight: 600 }}, "
                    f"bgcolor: theme.card, bordercolor: {color}, borderwidth: 1, borderpad: 3 }}"
                )
        result = "\n      layout.shapes = [" + ", ".join(items) + "];"
        if ann_items:
            result += "\n      layout.annotations = (layout.annotations || []).concat([" + ", ".join(ann_items) + "]);"
        return result

    def _build_csv_version(self, spec: "NormalizedSpec", title: str, data_spec: Dict[str, Any], colors: Dict[str, str]) -> str:
        """Generate single HTML file for CSV datasources"""
        if colors.get("buttons"):
            self.warn("'buttons' color is not currently used by Plotly transformer")

        # Check for unsupported chart types
        all_charts = []
        for page in spec["pages"]:
            all_charts.extend(page.get("charts", []))

        for chart in all_charts:
            chart_type = chart.get("type")
            if chart_type in ["stacked_bar", "grouped_bar"] and not chart.get("group"):
                self.warn(f"'{chart_type}' chart '{chart.get('id')}' is missing a 'group' field")

        html_parts = []

        # HTML header (CSS injection)
        html_parts.append(self._generate_html_header(title, colors))

        # Body start
        html_parts.append("<body>")
        html_parts.append(f'  <div class="container">')
        html_parts.append(f'    <h1>{title}</h1>')

        # Always use pages (normalizer guarantees pages[] exists)
        pages = spec["pages"]
        html_parts.append(self._generate_page_tabs(pages, colors))
        html_parts.append(self._generate_page_containers(pages, colors))
        html_parts.append('  </div>')
        html_parts.append(self._generate_javascript_pages(data_spec, pages, colors, spec.get("derived_fields", [])))

        # Body end
        html_parts.append("</body>")
        html_parts.append("</html>")

        return "\n".join(html_parts)

    def _build_sql_version(self, spec: "NormalizedSpec", title: str, data_spec: Dict[str, Any], colors: Dict[str, str]) -> str:
        """Generate multi-file output with Flask backend for SQL datasources"""
        if not spec.get("db_config"):
            raise TransformerError("Database configuration not provided for SQL datasource")

        # Generate Flask backend
        flask_app = self._generate_flask_app(spec, data_spec, colors)

        # Generate HTML frontend (fetches from Flask API instead of CSV)
        html_frontend = self._generate_sql_frontend(spec, title, colors)

        # Return multi-file JSON structure
        multi_file_output = {
            "type": "multi-file",
            "files": {
                "app.py": flask_app,
                "index.html": html_frontend
            }
        }

        return json.dumps(multi_file_output)

    def _build_bigquery_version(self, spec: "NormalizedSpec", title: str, data_spec: Dict[str, Any], colors: Dict[str, str]) -> str:
        """Generate multi-file output with Flask + BigQuery backend"""
        if not spec.get("db_config"):
            raise TransformerError("BigQuery configuration not provided")

        # Generate Flask backend with BigQuery
        flask_app = self._generate_flask_app_bigquery(spec, data_spec, colors)

        # Generate HTML frontend (fetches from Flask API - same as SQL version)
        html_frontend = self._generate_sql_frontend(spec, title, colors)

        # Return multi-file JSON structure
        multi_file_output = {
            "type": "multi-file",
            "files": {
                "app.py": flask_app,
                "index.html": html_frontend
            }
        }

        return json.dumps(multi_file_output)

    def _generate_flask_app_bigquery(self, spec: "NormalizedSpec", data_spec: Dict[str, Any], colors: Dict[str, str]) -> str:
        """Generate Flask backend that connects to BigQuery.

        Project ID is required at build time (it is embedded into SQL queries
        as part of the fully-qualified table reference) and is not a secret —
        it is a public identifier. Service account credentials path is always
        read from the DASHML_BQ_CREDENTIALS environment variable at runtime;
        no credentials are baked into the generated source.
        """
        db_config = spec["db_config"]
        project = db_config["project"]

        dataset = data_spec["bq_dataset"]
        table_name = data_spec["bq_table"]

        # Build table reference for BigQuery
        table_ref = f"`{project}.{dataset}.{table_name}`"

        # Build per-chart queries
        all_charts = []
        for page in spec["pages"]:
            all_charts.extend(page.get("charts", []))

        # Build per-chart queries from normalizer-generated SQL templates
        chart_queries_code = "CHART_QUERIES = {\n"
        chart_static_code = "CHART_STATIC_CONDITIONS = {\n"
        for chart in all_charts:
            query = chart["sql"].replace("{table_ref}", table_ref)
            chart_queries_code += f'    "{chart["id"]}": """{query}""",\n'
            chart_static_code += f'    "{chart["id"]}": {repr(chart.get("static_conditions", []))},\n'
        chart_queries_code += "}"
        chart_static_code += "}"

        # Build ALLOWED_FILTER_FIELDS from page-level filters
        all_filter_fields = set()
        for page in spec["pages"]:
            for f in page.get("filters", []):
                all_filter_fields.add(f["field"])
        allowed_fields_code = f"ALLOWED_FILTER_FIELDS = frozenset({repr(all_filter_fields)})"

        # Build derived CTE for filter queries (so derived fields are available)
        from dashml_new.core.normalizer import DashMLNormalizer
        derived_fields = spec.get("derived_fields", [])
        derived_cte_template = DashMLNormalizer._build_derived_cte(derived_fields)
        if derived_cte_template:
            derived_cte_resolved = derived_cte_template.replace("{table_ref}", table_ref)
            derived_filter_source = "__derived"
        else:
            derived_cte_resolved = ""
            derived_filter_source = table_ref

        # Credentials and project are loaded from environment variables.
        from .secrets import emit_bq_env_loader
        bq_env_loader = emit_bq_env_loader(project)

        return f'''from flask import Flask, jsonify, send_from_directory
from google.cloud import bigquery
import json
import traceback
from datetime import date, datetime
from decimal import Decimal

# BigQuery credentials and project are loaded from environment variables
# (DASHML_BQ_PROJECT, DASHML_BQ_CREDENTIALS).
# See SECRETS.md and .env.example next to this file.
{bq_env_loader}
app = Flask(__name__)

DATASET = "{dataset}"
TABLE_NAME = "{table_name}"

# Per-chart SQL queries (generated at compile time)
{chart_queries_code}

{chart_static_code}

{allowed_fields_code}

# Derived CTE for filter queries (empty string if no derived fields)
DERIVED_CTE = """{derived_cte_resolved}"""
DERIVED_FILTER_SOURCE = "{derived_filter_source}"

def build_filter_clause(chart_id, request_args):
    """Build SQL WHERE body from static per-chart conditions + runtime dashboard filters."""
    conditions = ["1=1"]
    conditions.extend(CHART_STATIC_CONDITIONS.get(chart_id, []))
    for field in ALLOWED_FILTER_FIELDS:
        values = request_args.getlist(field)
        if not values:
            continue
        escaped = [str(v).replace("'", "''") for v in values]
        if len(escaped) == 1:
            conditions.append(field + " = '" + escaped[0] + "'")
        else:
            in_list = ", ".join("'" + v + "'" for v in escaped)
            conditions.append(field + " IN (" + in_list + ")")
    return " AND ".join(conditions)

# Cache for column types (fetched once from INFORMATION_SCHEMA)
_column_types_cache = None

def get_column_types():
    """Fetch column types from INFORMATION_SCHEMA and map to simple types"""
    global _column_types_cache
    if _column_types_cache is not None:
        return _column_types_cache

    try:
        query = f"""
            SELECT column_name, data_type
            FROM `{{PROJECT_ID}}.{{DATASET}}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{{TABLE_NAME}}'
        """
        query_job = client.query(query)
        results = query_job.result()

        type_mapping = {{}}
        for row in results:
            col_name = row.column_name
            data_type = row.data_type.upper()

            if data_type in ('DATE', 'DATETIME', 'TIMESTAMP', 'TIME'):
                type_mapping[col_name] = 'date'
            elif data_type in ('INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC', 'INT', 'INTEGER',
                             'SMALLINT', 'BIGINT', 'FLOAT', 'DECIMAL', 'REAL', 'DOUBLE'):
                type_mapping[col_name] = 'number'
            else:
                type_mapping[col_name] = 'string'

        _column_types_cache = type_mapping
        return type_mapping
    except Exception as e:
        print(f"Warning: Could not fetch column types: {{e}}")
        return {{}}

def serialize(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {{type(obj)}} not serializable")

@app.route('/')
def index():
    """Serve the HTML frontend"""
    return send_from_directory('.', 'index.html')

@app.route('/api/schema')
def get_schema():
    """Return column types from INFORMATION_SCHEMA"""
    try:
        column_types = get_column_types()
        return jsonify(column_types)
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

@app.route('/api/chart/<chart_id>')
def get_chart_data(chart_id):
    """Fetch pre-aggregated data for a specific chart"""
    from flask import request
    query_template = CHART_QUERIES.get(chart_id)
    if not query_template:
        return jsonify({{"error": "Unknown chart"}}), 404
    try:
        filter_clause = build_filter_clause(chart_id, request.args)
        query = query_template.format(filter_clause=filter_clause)
        print(f"[BQ] chart={{chart_id}} query={{query[:200]}}")
        query_job = client.query(query)
        results = query_job.result()
        data = [dict(row) for row in results]
        return app.response_class(
            response=json.dumps(data, default=serialize),
            mimetype='application/json'
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({{"error": str(e)}}), 500

@app.route('/api/filter/<field>')
def get_filter_options(field):
    """Return DISTINCT values for a filter field (used to populate dropdowns)"""
    from flask import request
    if field not in ALLOWED_FILTER_FIELDS:
        return jsonify({{"error": "Field not allowed"}}), 403
    try:
        query = DERIVED_CTE + " SELECT DISTINCT " + field + " FROM " + DERIVED_FILTER_SOURCE + " WHERE " + field + " IS NOT NULL ORDER BY 1 LIMIT 500"
        print(f"[BQ] filter={{field}} query={{query[:200]}}")
        query_job = client.query(query)
        results = query_job.result()
        values = [str(row[0]) for row in results if row[0] is not None]
        return jsonify(sorted(values))
    except Exception as e:
        traceback.print_exc()
        return jsonify({{"error": str(e)}}), 500

if __name__ == '__main__':
    print("Starting Flask server with BigQuery backend...")
    print(f"Project: {{PROJECT_ID}}")
    print(f"Dataset: {{DATASET}}")
    print(f"Table: {{TABLE_NAME}}")
    print(f"Dashboard available at: http://localhost:5001")
    app.run(debug=True, port=5001)
'''

    def _generate_html_header(self, title: str, colors: Dict[str, str]) -> str:
        """Generate HTML header with dynamic CSS based on theme."""
        # Theme-controlled palette (from .dmls file)
        bg = colors["background"]
        card_bg = colors["card"]
        text = colors["text"]
        primary = colors["primary"]
        # Visual design tokens (transformer-side, theme-agnostic relationships)
        card_alt = DESIGN_TOKENS["card_alt"]
        line = DESIGN_TOKENS["line"]
        line_soft = DESIGN_TOKENS["line_soft"]
        muted = DESIGN_TOKENS["muted"]
        fg_dim = DESIGN_TOKENS["fg_dim"]

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: {bg}; color: {text}; }}
    body {{
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      padding: 28px 32px 80px;
    }}
    .container {{ max-width: 1600px; margin: 0 auto; }}

    h1 {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: -0.01em;
      margin: 0 0 4px;
      color: {text};
    }}
    .sub {{ color: {muted}; font-size: 13px; margin: 0 0 20px; }}

    /* Tabs */
    .page-tabs {{
      display: flex; gap: 24px;
      border-bottom: 1px solid {line};
      margin-bottom: 18px;
    }}
    .tab-button {{
      background: none; border: 0;
      color: {fg_dim};
      font: inherit; font-weight: 500;
      padding: 10px 2px;
      cursor: pointer;
      position: relative;
      margin-bottom: -1px;
    }}
    .tab-button:hover {{ color: {text}; }}
    .tab-button.active {{ color: {primary}; }}
    .tab-button.active::after {{
      content: ""; position: absolute;
      left: 0; right: 0; bottom: -1px;
      height: 2px; background: {primary}; border-radius: 2px;
    }}
    .page-description {{
      color: {muted};
      font-size: 13px;
      font-style: italic;
      margin: 4px 0 18px;
    }}

    /* Layout grids */
    .page-container {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      align-items: start;
      margin-top: 18px;
    }}
    @media (min-width: 1100px) {{
      .page-container {{ grid-template-columns: repeat(4, 1fr); }}
    }}
    .page-container > .filter-bar,
    .page-container > .page-description {{ grid-column: 1 / -1; }}
    .page-container > .card:not(.metric-card) {{ grid-column: span 2; }}
    /* Nested layout-columns wrapper emitted by `layout.columns:` spans the row */
    .page-container > div[style*="grid-template-columns"] {{ grid-column: 1 / -1; }}
    .page-container.hidden {{ display: none; }}

    /* Card surface */
    .card {{
      background: {card_bg};
      border: 1px solid {line_soft};
      border-radius: 10px;
      padding: 20px;
      min-width: 0;
    }}

    /* KPI metric card */
    .metric-card {{
      padding: 20px;
    }}
    .metric-title {{
      color: {muted};
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .metric-value {{
      font-size: 32px;
      font-weight: 600;
      letter-spacing: -0.02em;
      color: {text};
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
    }}

    /* Chart container */
    .chart-card .chart-title {{
      font-size: 14px; font-weight: 600;
      color: {text};
      margin: 0 0 14px;
    }}
    .chart-container {{ margin: 0; min-height: 360px; }}
    .chart-spinner {{
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; min-height: 300px; gap: 12px;
      color: {fg_dim};
    }}
    .chart-spinner .spinner {{
      width: 40px; height: 40px;
      border: 3px solid {line_soft};
      border-top-color: {primary};
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .chart-error {{
      display: flex; align-items: center; justify-content: center;
      min-height: 300px; color: #ff79c6;
    }}

    /* Filter bar */
    .filter-bar {{
      display: flex; align-items: center; gap: 18px;
      background: {card_bg};
      border: 1px solid {line_soft};
      border-radius: 10px;
      padding: 12px 16px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .filter-bar-title {{
      color: {muted};
      font-size: 11px; font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      display: inline-flex; align-items: center; gap: 6px;
      margin-right: 4px;
    }}
    .filter-item {{ display: flex; flex-direction: column; gap: 4px; }}
    .filter-item > label {{
      color: {muted};
      font-size: 11px; font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .filter-select-wrap {{ position: relative; display: inline-flex; align-items: center; }}
    .filter-select-wrap select,
    .ms-btn {{
      background: {card_alt};
      color: {text};
      border: 1px solid {line};
      border-radius: 6px;
      padding: 6px 28px 6px 10px;
      font: inherit; font-size: 13px;
      min-width: 180px;
      outline: none;
      cursor: pointer;
      transition: border-color 0.15s, box-shadow 0.15s;
      appearance: none; -webkit-appearance: none;
    }}
    .filter-select-wrap select:hover, .ms-btn:hover {{ border-color: {muted}; }}
    .filter-select-wrap select:focus,
    .ms-btn.ms-open, .ms-btn:focus {{
      border-color: {primary};
      box-shadow: 0 0 0 1px {primary};
    }}
    .filter-select-wrap .sel-arrow,
    .ms-arrow {{
      position: absolute; right: 9px; pointer-events: none;
      color: {muted};
      transition: transform 0.15s;
      flex-shrink: 0;
    }}
    .ms-arrow {{ position: static; }}
    .ms-btn.ms-open .ms-arrow {{ transform: rotate(180deg); }}
    .ms-wrap {{ position: relative; min-width: 180px; }}
    .ms-btn {{
      display: flex; align-items: center; justify-content: space-between;
      gap: 10px; padding: 6px 10px;
      text-align: left; width: 100%;
    }}
    .ms-btn .ms-text {{
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      color: {text};
    }}
    .ms-btn .ms-text.placeholder {{ color: {fg_dim}; }}
    .ms-count {{
      background: {primary}; color: #fff;
      border-radius: 10px;
      padding: 1px 7px;
      font-size: 11px; font-weight: 600;
      display: none;
    }}
    .ms-count.visible {{ display: inline; }}

    .ms-panel {{
      position: absolute;
      top: calc(100% + 4px); left: 0;
      width: 100%;
      min-width: 220px;
      max-height: 280px;
      overflow-y: auto;
      overflow-x: hidden;
      background: {card_alt};
      border: 1px solid {line};
      border-radius: 8px;
      box-shadow: 0 12px 32px rgba(0,0,0,0.45);
      padding: 6px;
      z-index: 50;
      display: none;
    }}
    .ms-panel.ms-open {{ display: block; }}
    .ms-panel::-webkit-scrollbar {{ width: 10px; }}
    .ms-panel::-webkit-scrollbar-track {{ background: transparent; }}
    .ms-panel::-webkit-scrollbar-thumb {{
      background: {line}; border-radius: 6px; border: 2px solid {card_alt};
    }}
    .ms-panel::-webkit-scrollbar-thumb:hover {{ background: {muted}; }}

    .ms-option {{
      display: flex; align-items: center; gap: 10px;
      padding: 8px 10px;
      border-radius: 5px;
      cursor: pointer;
      color: {fg_dim};
      font-size: 13px;
      user-select: none;
      min-width: 0;
    }}
    .ms-option > span {{
      min-width: 0; flex: 1 1 auto;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    .ms-option:hover {{ background: rgba(189, 147, 249, 0.08); color: {text}; }}
    .ms-option input[type="checkbox"] {{
      accent-color: {primary};
      width: 14px; height: 14px; flex-shrink: 0; cursor: pointer;
    }}
    .ms-option input[type="checkbox"]:checked + span {{ color: {text}; }}

    .filter-reset {{
      background: none;
      border: 1px solid {line};
      color: {fg_dim};
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      margin-left: auto;
      font-family: inherit;
      transition: color 0.15s, border-color 0.15s;
    }}
    .filter-reset:hover {{ color: {text}; border-color: {muted}; }}
  </style>
</head>'''

    def _generate_chart_selector(self, charts: list) -> str:
        """Generate dropdown selector for charts"""
        options = []
        for chart in charts:
            chart_id = chart["id"]
            chart_title = chart.get("title", chart_id)
            options.append(f'      <option value="{chart_id}">{chart_title}</option>')

        return f'''    <div class="chart-selector">
      <label for="chartSelect">Select Chart:</label>
      <select id="chartSelect" onchange="renderSelectedChart()">
{chr(10).join(options)}
      </select>
    </div>'''

    def _generate_javascript(self, data_spec: Dict[str, Any], charts: list, colors: Dict[str, str]) -> str:
        """Generate JavaScript code for data loading and rendering"""
        data_path = data_spec["path"]

        # Resolve sequential colorscale at code-gen time
        colors = dict(colors)
        colors["sequential"] = resolve_plotly_colorscale(colors.get("sequential", "blues"))

        # Pass theme colors to JS for Plotly layout
        theme_json = json.dumps(colors)

        js_parts = []
        js_parts.append("  <script>")
        js_parts.append(f"    const theme = {theme_json};")
        js_parts.append("    // Chart definitions")
        js_parts.append(f"    const charts = {self._charts_to_json(charts)};")
        js_parts.append("")

        # Geo normalization helpers (if any chart is geo)
        if any(c.get("type") == "geo" for c in charts):
            js_parts.append(self._generate_geo_js_helpers(target="plotly"))
            js_parts.append("")

        js_parts.append(self._generate_csv_parser())
        js_parts.append(self._generate_aggregator())
        js_parts.append("")
        js_parts.append(self._generate_renderer(multi_page=False))
        js_parts.append("")
        js_parts.append(f'''    fetch('{data_path}')
      .then(response => response.text())
      .then(csvText => {{
        const data = parseCSV(csvText);
        window.dashmlData = data;
        renderChart(charts[0]);
      }})
      .catch(error => {{
        document.getElementById('chart').innerHTML =
          '<div style="color: red;">Error loading data: ' + error.message + '</div>';
      }});''')
        js_parts.append("")
        js_parts.append('''    function renderSelectedChart() {
      const select = document.getElementById('chartSelect');
      const chartId = select.value;
      const chart = charts.find(c => c.id === chartId);
      if (chart) renderChart(chart);
    }''')
        js_parts.append("  </script>")

        return "\n".join(js_parts)

    def _charts_to_json(self, charts: list) -> str:
        import json
        return json.dumps(charts, indent=6)

    def _generate_geo_js_helpers(self, target: str = "plotly") -> str:
        """Emit JS mapping tables + detectGeoEncoding + normalize function."""
        mapping_js = country_mapping_as_js(target=target)
        suffix = "Plotly" if target == "plotly" else "Topo"
        return f'''    // Geo country normalization
    {mapping_js.replace(chr(10), chr(10) + "    ")}
    function detectGeoEncoding(values) {{
      const sample = values.filter(v => v != null && v !== '').slice(0, 20);
      if (sample.every(v => /^[A-Z]{{2}}$/.test(String(v)))) return 'iso2';
      if (sample.every(v => /^[A-Z]{{3}}$/.test(String(v)))) return 'iso3';
      return 'name';
    }}
    function normalizeCountryFor{suffix}(value, encoding) {{
      const v = String(value).trim();
      if (!v) return v;
      if (encoding === 'iso2') return iso2To{suffix}[v.toUpperCase()] || v;
      if (encoding === 'iso3') return iso3To{suffix}[v.toUpperCase()] || v;
      return aliasTo{suffix}[v.toLowerCase()] || v;
    }}'''

    def _generate_csv_parser(self) -> str:
        return '''    function parseCSV(csvText) {
      const lines = csvText.trim().split('\\n').filter(line => line.trim());
      const headers = lines[0].split(',').map(h => h.trim());
      const rows = [];

      for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',');
        if (values.length !== headers.length) continue;

        const row = {};
        headers.forEach((header, index) => {
          const value = values[index] ? values[index].trim() : '';
          row[header] = isNaN(value) ? value : parseFloat(value);
        });
        rows.push(row);
      }
      return rows;
    }'''

    def _generate_aggregator(self) -> str:
        return '''    // Apply filters to data
    function applyFilters(data, filters) {
      if (!filters || filters.length === 0) return data;
      return data.filter(row => {
        return filters.every(f => {
          const val = row[f.field];
          switch (f.op) {
            case 'eq': return val === f.value;
            case 'ne': return val !== f.value;
            case 'gt': return val > f.value;
            case 'lt': return val < f.value;
            case 'gte': return val >= f.value;
            case 'lte': return val <= f.value;
            case 'in': return Array.isArray(f.value) && f.value.includes(val);
            case 'contains': return String(val).includes(f.value);
            case 'range': return Array.isArray(f.value) && f.value.length === 2 && val >= f.value[0] && val <= f.value[1];
            default: return true;
          }
        });
      });
    }

    // Cast y values based on y_type
    function castYValues(data, y, yType) {
      if (!yType) return data;
      return data.map(row => {
        const newRow = {...row};
        if (yType === 'number') {
          newRow[y] = parseFloat(row[y]) || 0;
        } else if (yType === 'string') {
          newRow[y] = String(row[y]);
        }
        return newRow;
      });
    }

    // Sort aggregated data
    function sortData(data, sortField, sortOrder, xType) {
      const result = [...data];
      const ascending = sortOrder !== 'desc';

      if (sortField === 'y') {
        result.sort((a, b) => ascending ? a.y - b.y : b.y - a.y);
      } else if (sortField === 'x') {
        if (xType === 'date') {
          result.sort((a, b) => {
            const diff = new Date(a.x) - new Date(b.x);
            return ascending ? diff : -diff;
          });
        } else if (xType === 'number') {
          result.sort((a, b) => ascending ? a.x - b.x : b.x - a.x);
        } else {
          result.sort((a, b) => {
            const cmp = String(a.x).localeCompare(String(b.x));
            return ascending ? cmp : -cmp;
          });
        }
      } else if (xType === 'date') {
        // Default: sort by date if x_type is date
        result.sort((a, b) => new Date(a.x) - new Date(b.x));
      } else if (xType === 'number') {
        result.sort((a, b) => parseFloat(a.x) - parseFloat(b.x));
      } else {
        // Default: sort strings alphabetically for consistency across transformers
        result.sort((a, b) => String(a.x).localeCompare(String(b.x)));
      }
      return result;
    }

    function aggregateData(data, x, y, agg, options) {
      options = options || {};
      const xType = options.xType;
      const yType = options.yType;
      const filters = options.filters || [];
      const sortField = options.sort;
      const sortOrder = options.sortOrder || 'asc';
      const limit = options.limit;
      const sizeField = options.sizeField;

      // Apply filters first
      let filtered = applyFilters(data, filters);

      // If x column doesn't exist in data, generate row index
      if (filtered.length > 0 && !(x in filtered[0])) {
        filtered = filtered.map((row, i) => ({...row, [x]: i}));
      }

      // Cast y values
      filtered = castYValues(filtered, y, yType);

      const grouped = {};
      filtered.forEach(row => {
        const key = row[x];
        if (!grouped[key]) grouped[key] = { values: [], count: 0, sizeValues: [] };
        grouped[key].values.push(row[y]);
        grouped[key].count++;
        if (sizeField) grouped[key].sizeValues.push(parseFloat(row[sizeField]) || 0);
      });

      let result = [];
      Object.keys(grouped).forEach(key => {
        const values = grouped[key].values;
        let aggregated;
        switch (agg) {
          case 'sum': aggregated = values.reduce((a, b) => a + b, 0); break;
          case 'mean': aggregated = values.reduce((a, b) => a + b, 0) / values.length; break;
          case 'count': aggregated = grouped[key].count; break;
          default: aggregated = values.reduce((a, b) => a + b, 0);
        }
        const entry = { x: key, y: aggregated };
        if (sizeField) {
          const sizeVals = grouped[key].sizeValues;
          switch (agg) {
            case 'sum': entry.size = sizeVals.reduce((a, b) => a + b, 0); break;
            case 'mean': entry.size = sizeVals.reduce((a, b) => a + b, 0) / sizeVals.length; break;
            case 'count': entry.size = grouped[key].count; break;
            default: entry.size = sizeVals.reduce((a, b) => a + b, 0);
          }
        }
        result.push(entry);
      });

      // Sort
      result = sortData(result, sortField, sortOrder, xType);

      // Limit
      if (limit && limit > 0) {
        result = result.slice(0, limit);
      }

      return result;
    }

    function aggregateDataWithGroup(data, x, y, groupField, agg, options) {
      options = options || {};
      const xType = options.xType;
      const yType = options.yType;
      const filters = options.filters || [];
      const sortField = options.sort;
      const sortOrder = options.sortOrder || 'asc';
      const limit = options.limit;

      // Apply filters first
      let filtered = applyFilters(data, filters);

      // Cast y values
      filtered = castYValues(filtered, y, yType);

      const grouped = {};
      filtered.forEach(row => {
        const xKey = row[x];
        const groupKey = row[groupField];
        const compositeKey = xKey + '|||' + groupKey;
        if (!grouped[compositeKey]) grouped[compositeKey] = { x: xKey, group: groupKey, values: [], count: 0 };
        grouped[compositeKey].values.push(row[y]);
        grouped[compositeKey].count++;
      });

      let result = [];
      Object.keys(grouped).forEach(key => {
        const entry = grouped[key];
        const values = entry.values;
        let aggregated;
        switch (agg) {
          case 'sum': aggregated = values.reduce((a, b) => a + b, 0); break;
          case 'mean': aggregated = values.reduce((a, b) => a + b, 0) / values.length; break;
          case 'count': aggregated = entry.count; break;
          default: aggregated = values.reduce((a, b) => a + b, 0);
        }
        result.push({ x: entry.x, group: entry.group, y: aggregated });
      });

      // Sort based on sortField or default x_type
      result = sortData(result, sortField, sortOrder, xType);

      // Limit
      if (limit && limit > 0) {
        result = result.slice(0, limit);
      }

      return result;
    }

    // Aggregate data for bubble charts: group by groupField, aggregate x, y, size independently
    function aggregateBubbleData(data, groupField, xMetric, yMetric, sizeMetric, agg, options) {
      options = options || {};
      const filters = options.filters || [];
      const sortField = options.sort;
      const sortOrder = options.sortOrder || 'asc';
      const limit = options.limit;

      // Apply filters first
      let filtered = applyFilters(data, filters);

      const grouped = {};
      filtered.forEach(row => {
        const key = row[groupField];
        if (!grouped[key]) grouped[key] = { xValues: [], yValues: [], sizeValues: [], count: 0 };
        grouped[key].xValues.push(parseFloat(row[xMetric]) || 0);
        grouped[key].yValues.push(parseFloat(row[yMetric]) || 0);
        grouped[key].sizeValues.push(parseFloat(row[sizeMetric]) || 0);
        grouped[key].count++;
      });

      function aggArray(values, count) {
        switch (agg) {
          case 'sum': return values.reduce((a, b) => a + b, 0);
          case 'mean': return values.reduce((a, b) => a + b, 0) / values.length;
          case 'count': return count;
          default: return values.reduce((a, b) => a + b, 0);
        }
      }

      let result = [];
      Object.keys(grouped).forEach(key => {
        const g = grouped[key];
        result.push({
          group: key,
          x: aggArray(g.xValues, g.count),
          y: aggArray(g.yValues, g.count),
          size: aggArray(g.sizeValues, g.count)
        });
      });

      // Sort by x by default
      if (sortField === 'y') {
        const asc = sortOrder !== 'desc';
        result.sort((a, b) => asc ? a.y - b.y : b.y - a.y);
      } else {
        const asc = sortOrder !== 'desc';
        result.sort((a, b) => asc ? a.x - b.x : b.x - a.x);
      }

      // Limit
      if (limit && limit > 0) {
        result = result.slice(0, limit);
      }

      return result;
    }'''

    def _generate_aggregator_with_schema(self) -> str:
        """Generate aggregator functions that use INFORMATION_SCHEMA for auto type detection"""
        return '''    // Get effective x_type: explicit > schema-detected > undefined
    function getEffectiveXType(xColumn, explicitXType) {
      if (explicitXType) return explicitXType;
      return columnTypes[xColumn] || undefined;
    }

    function aggregateData(data, x, y, agg, xType) {
      // Use schema-detected type if no explicit type provided
      const effectiveXType = getEffectiveXType(x, xType);

      // If x column doesn't exist in data, generate row index
      if (data.length > 0 && !(x in data[0])) {
        data = data.map((row, i) => ({...row, [x]: i}));
      }

      const grouped = {};
      data.forEach(row => {
        const key = row[x];
        if (!grouped[key]) grouped[key] = { values: [], count: 0 };
        grouped[key].values.push(row[y]);
        grouped[key].count++;
      });

      const result = [];
      Object.keys(grouped).forEach(key => {
        const values = grouped[key].values;
        let aggregated;
        switch (agg) {
          case 'sum': aggregated = values.reduce((a, b) => a + b, 0); break;
          case 'mean': aggregated = values.reduce((a, b) => a + b, 0) / values.length; break;
          case 'count': aggregated = grouped[key].count; break;
          default: aggregated = values.reduce((a, b) => a + b, 0);
        }
        result.push({ x: key, y: aggregated });
      });

      // Sort based on effective x_type (explicit or schema-detected)
      if (effectiveXType === 'date') {
        result.sort((a, b) => new Date(a.x) - new Date(b.x));
      } else if (effectiveXType === 'number') {
        result.sort((a, b) => parseFloat(a.x) - parseFloat(b.x));
      }

      return result;
    }

    function aggregateDataWithGroup(data, x, y, groupField, agg, xType) {
      // Use schema-detected type if no explicit type provided
      const effectiveXType = getEffectiveXType(x, xType);

      const grouped = {};
      data.forEach(row => {
        const xKey = row[x];
        const groupKey = row[groupField];
        const compositeKey = xKey + '|||' + groupKey;
        if (!grouped[compositeKey]) grouped[compositeKey] = { x: xKey, group: groupKey, values: [], count: 0 };
        grouped[compositeKey].values.push(row[y]);
        grouped[compositeKey].count++;
      });

      const result = [];
      Object.keys(grouped).forEach(key => {
        const entry = grouped[key];
        const values = entry.values;
        let aggregated;
        switch (agg) {
          case 'sum': aggregated = values.reduce((a, b) => a + b, 0); break;
          case 'mean': aggregated = values.reduce((a, b) => a + b, 0) / values.length; break;
          case 'count': aggregated = entry.count; break;
          default: aggregated = values.reduce((a, b) => a + b, 0);
        }
        result.push({ x: entry.x, group: entry.group, y: aggregated });
      });

      // Sort based on effective x_type (explicit or schema-detected)
      if (effectiveXType === 'date') {
        result.sort((a, b) => new Date(a.x) - new Date(b.x));
      } else if (effectiveXType === 'number') {
        result.sort((a, b) => parseFloat(a.x) - parseFloat(b.x));
      }

      return result;
    }'''

    def _generate_renderer(self, multi_page=False) -> str:
        """
        Generate chart rendering function.
        Updated to use theme colors for Plotly Layout.

        TODO: [SRP] This method is very long (~300 lines) and handles multiple chart types
        Consider splitting into separate render functions per chart type
        Fix: _render_bar_chart(), _render_line_chart(), etc.
        """
        div_id_logic = "chart.id" if not multi_page else "'chart-' + chart.id"
        if not multi_page:
            # Single page mode uses fixed div 'chart'
            plot_call = "Plotly.newPlot('chart', [trace], layout, { responsive: true });"
        else:
            # This function isn't actually used for multi-page in this implementation,
            # _generate_javascript_pages creates specific render functions.
            # But we keep it generic just in case.
            plot_call = "Plotly.newPlot('chart-' + chart.id, [trace], layout, { responsive: true });"

        return f'''    function renderChart(chart) {{
      // Chart types that need aggregation vs raw data
      const chartsNeedAggregation = new Set(['bar', 'line', 'area', 'pie', 'stacked_bar', 'grouped_bar']);
      const chartsUseRawData = new Set(['histogram', 'scatter']);

      let traces = [];
      let barmode = undefined;

      // Build options object for aggregation
      const aggOptions = {{
        xType: chart.x_type,
        yType: chart.y_type,
        filters: chart.filters || [],
        sort: chart.sort,
        sortOrder: chart.sort_order || 'asc',
        limit: chart.limit,
        sizeField: chart.size
      }};

      if (chart.type === 'bubble' && chart.group) {{
        // Bubble chart: 4D visualization (group, x, y, size)
        const bubbleData = aggregateBubbleData(window.dashmlData, chart.group, chart.x, chart.y, chart.size || chart.y, chart.agg || 'sum', aggOptions);
        const bubbleSizeVals = bubbleData.map(d => Math.abs(d.size));
        const maxSize = Math.max(...bubbleSizeVals);
        const normalizedSizes = bubbleSizeVals.map(v => 10 + (v / maxSize) * 50);
        traces.push({{
          x: bubbleData.map(d => d.x),
          y: bubbleData.map(d => d.y),
          text: bubbleData.map(d => d.group),
          type: 'scatter',
          mode: 'markers+text',
          textposition: 'top center',
          marker: {{
            size: normalizedSizes,
            color: purpleRamp(bubbleData.length),
            line: {{ color: theme.card, width: 1 }},
            sizemode: 'diameter'
          }},
          hovertemplate: bubbleData.map(d => `${{d.group}}<br>${{chart.x}}: ${{d.x}}<br>${{chart.y}}: ${{d.y}}<br>${{chart.size || chart.y}}: ${{d.size}}<extra></extra>`)
        }});
      }} else if (chart.type === 'stacked_bar' || chart.type === 'grouped_bar') {{
        // Stacked/grouped bars need multiple traces
        const aggregated = aggregateDataWithGroup(window.dashmlData, chart.x, chart.y, chart.group, chart.agg || 'sum', aggOptions);
        const groupValues = [...new Set(aggregated.map(d => d.group))];

        groupValues.forEach((groupVal, idx) => {{
          const filtered = aggregated.filter(d => d.group === groupVal);
          traces.push({{
            x: filtered.map(d => d.x),
            y: filtered.map(d => d.y),
            name: groupVal,
            type: 'bar',
            marker: {{ color: theme.secondary[idx % theme.secondary.length] }}
          }});
        }});

        // Sort x categories by aggregate y total
        if (aggOptions.sort === 'y') {{
          const catTotals = {{}};
          aggregated.forEach(d => {{ catTotals[d.x] = (catTotals[d.x] || 0) + (d.y || 0); }});
          const asc = aggOptions.sortOrder !== 'desc';
          window.__catOrder = Object.keys(catTotals).sort((a, b) => asc ? catTotals[a] - catTotals[b] : catTotals[b] - catTotals[a]);
        }}

        barmode = chart.type === 'stacked_bar' ? 'stack' : 'group';
      }} else {{
        let xValues, yValues, sizeValues;
        if (chartsUseRawData.has(chart.type)) {{
          // Use raw data for histogram - apply filters only
          let filteredData = applyFilters(window.dashmlData, aggOptions.filters);
          xValues = filteredData.map(d => d[chart.x]);
          yValues = filteredData.map(d => d[chart.y]);
        }} else {{
          // Aggregate data for other chart types
          const aggregated = aggregateData(window.dashmlData, chart.x, chart.y, chart.agg || 'sum', aggOptions);
          xValues = aggregated.map(d => d.x);
          yValues = aggregated.map(d => d.y);
          if (aggOptions.sizeField) sizeValues = aggregated.map(d => d.size);
        }}

        let trace;
        switch (chart.type) {{
        case 'bar':
          trace = {{ x: xValues, y: yValues, type: 'bar', marker: {{ color: theme.primary }} }};
          break;
        case 'line':
          trace = {{ x: xValues, y: yValues, type: 'scatter', mode: 'lines+markers', line: {{ color: theme.primary, width: 2 }} }};
          break;
        case 'scatter':
          trace = {{ x: xValues, y: yValues, type: 'scatter', mode: 'markers', marker: {{ size: 10, color: theme.primary }} }};
          break;
        case 'heatmap':
          // Heatmap: 2D grid with color intensity
          // Requires aggregated data with x, y (group), and value
          const heatmapData = aggregateDataWithGroup(window.dashmlData, chart.x, chart.y, chart.group || chart.y, chart.agg || 'sum', aggOptions);
          const heatmapX = [...new Set(heatmapData.map(d => d.x))];
          const heatmapY = [...new Set(heatmapData.map(d => d.group))];
          const heatmapZ = heatmapY.map(yVal =>
            heatmapX.map(xVal => {{
              const found = heatmapData.find(d => d.x === xVal && d.group === yVal);
              return found ? found.y : 0;
            }})
          );
          trace = {{ x: heatmapX, y: heatmapY, z: heatmapZ, type: 'heatmap', colorscale: theme.sequential || 'Blues' }};
          break;
        case 'pie':
          trace = {{ labels: xValues, values: yValues, type: 'pie',
                     marker: {{ colors: purpleRamp(xValues.length), line: {{ color: theme.card, width: 1 }} }},
                     textinfo: 'label+percent',
                     textposition: 'inside',
                     insidetextorientation: 'radial',
                     insidetextfont: {{ color: '#1a1b24', size: 11 }} }};
          break;
        case 'area':
          trace = {{ x: xValues, y: yValues, type: 'scatter', fill: 'tozeroy', mode: 'lines', line: {{ color: theme.primary }}, fillcolor: theme.primary + '40' }};
          break;
        case 'histogram':
          trace = {{ x: xValues, type: 'histogram', nbinsx: chart.bins || 20, marker: {{ color: theme.primary }} }};
          break;
        case 'box':
          // Box plot: shows distribution (min, Q1, median, Q3, max)
          // Group by x, show distribution of y values
          const boxGroups = [...new Set(window.dashmlData.map(d => d[chart.x]))];
          boxGroups.forEach(group => {{
            traces.push({{
              y: window.dashmlData.filter(d => d[chart.x] === group).map(d => d[chart.y]),
              name: group,
              type: 'box',
              marker: {{ color: theme.primary }}
            }});
          }});
          break;
        case 'geo':
          const geoEnc = chart.geo_encoding || detectGeoEncoding(xValues);
          if (geoEnc === 'iso3') {{
            trace = {{
              type: 'choropleth',
              locations: xValues,
              z: yValues,
              locationmode: 'ISO-3',
              colorscale: theme.sequential || 'Blues',
              colorbar: {{ title: chart.y }}
            }};
          }} else {{
            const normalizedX = xValues.map(v => normalizeCountryForPlotly(v, geoEnc));
            trace = {{
              type: 'choropleth',
              locations: normalizedX,
              z: yValues,
              locationmode: 'country names',
              colorscale: theme.sequential || 'Blues',
              colorbar: {{ title: chart.y }}
            }};
          }}
          break;
        default:
          trace = {{ x: xValues, y: yValues, type: 'bar', marker: {{ color: theme.primary }} }};
      }}

      if (trace) traces.push(trace);
      }}

      let layout;
      if (chart.type === 'geo') {{
        // Special layout for choropleth maps
        layout = {{
          title: {{
            text: chart.title || chart.id,
            font: {{ color: theme.text }}
          }},
          geo: {{
            showframe: false,
            showcoastlines: true,
            projection: {{ type: 'natural earth' }},
            bgcolor: 'rgba(0,0,0,0)'
          }},
          margin: {{ t: 60, r: 0, b: 0, l: 0 }},
          paper_bgcolor: 'rgba(0,0,0,0)'
        }};
      }} else {{
        layout = {{
          title: {{
              text: chart.title || chart.id,
              font: {{ color: theme.text }}
          }},
          xaxis: {{
              title: chart.x,
              type: chart.x_scale === 'log' ? 'log' : '-',
              color: theme.text,
              gridcolor: theme.text + '20' // 20 = low opacity
          }},
          yaxis: {{
              title: chart.y,
              type: chart.y_scale === 'log' ? 'log' : '-',
              color: theme.text,
              gridcolor: theme.text + '20'
          }},
          margin: {{ t: 60, r: 40, b: 60, l: 60 }},
          paper_bgcolor: 'rgba(0,0,0,0)', // Transparent to let CSS background show
          plot_bgcolor: 'rgba(0,0,0,0)'
        }};
      }}

      if (barmode) {{
        layout.barmode = barmode;
      }}

      // Apply category order for sorted grouped/stacked bars
      if (window.__catOrder) {{
        layout.xaxis.categoryorder = 'array';
        layout.xaxis.categoryarray = window.__catOrder;
        delete window.__catOrder;
      }}

      // Annotations
      if (chart.annotations && chart.annotations.length) {{
        layout.annotations = chart.annotations.map(a => ({{
          x: a.x, y: a.y, text: a.text, showarrow: true, arrowhead: 2,
          font: {{ color: a.color || 'red' }}
        }}));
      }}

      // Reference lines (shapes + labels)
      const styleMap = {{ solid: 'solid', dashed: 'dash', dotted: 'dot' }};
      if (chart.reference_lines && chart.reference_lines.length) {{
        layout.shapes = chart.reference_lines.map(rl => {{
          const dash = styleMap[rl.style] || 'dash';
          if (rl.axis === 'x') {{
            return {{ type: 'line', xref: 'x', x0: rl.value, x1: rl.value, yref: 'paper', y0: 0, y1: 1, line: {{ color: 'red', width: 1.5, dash: dash }} }};
          }}
          return {{ type: 'line', yref: 'y', y0: rl.value, y1: rl.value, xref: 'paper', x0: 0, x1: 1, line: {{ color: 'red', width: 1.5, dash: dash }} }};
        }});
        const rlAnnotations = chart.reference_lines.filter(rl => rl.label).map(rl => {{
          if (rl.axis === 'x') {{
            return {{ y: 1, yref: 'paper', x: rl.value, xref: 'x', text: rl.label, showarrow: false, font: {{ color: 'red', size: 11 }}, yanchor: 'bottom' }};
          }}
          return {{ x: 1, xref: 'paper', y: rl.value, yref: 'y', text: rl.label, showarrow: false, font: {{ color: 'red', size: 11 }}, xanchor: 'left' }};
        }});
        layout.annotations = (layout.annotations || []).concat(rlAnnotations);
      }}

      Plotly.newPlot('chart', traces, layout, {{ responsive: true }});
    }}'''

    def _generate_page_tabs(self, pages: list, colors: Dict[str, str]) -> str:
        tabs = []
        for i, page in enumerate(pages):
            page_id = page["id"]
            title = page.get("title", page_id)
            active_class = " active" if i == 0 else ""
            tabs.append(f'      <button class="tab-button{active_class}" onclick="showPage(\'{page_id}\', this)">{title}</button>')

        return f'''    <div class="page-tabs">
{chr(10).join(tabs)}
    </div>'''

    def _generate_page_containers(self, pages: list, colors: Dict[str, str]) -> str:
        containers = []
        for i, page in enumerate(pages):
            page_id = page["id"]
            page_class = "page-container" if i == 0 else "page-container hidden"
            description = page.get("description", "")

            container_parts = [f'    <div id="page-{page_id}" class="{page_class}">']

            if description:
                container_parts.append(f'      <p class="page-description"><em>{description}</em></p>')

            page_filters = page.get("filters", [])
            if page_filters:
                filter_items = []
                for f in page_filters:
                    field = f["field"]
                    label_text = f.get("label", field.replace("_", " ").title())
                    ftype = f.get("type", "select")
                    if ftype == "multiselect":
                        filter_items.append(
                            f'      <div class="filter-item">'
                            f'<label>{label_text}</label>'
                            f'<div class="ms-wrap" id="ms-{page_id}-{field}">'
                            f'<button type="button" class="ms-btn" onclick="toggleMs(this,\'{page_id}\',\'{field}\')">'
                            f'<span class="ms-text">All</span>'
                            f'<span class="ms-count" id="ms-count-{page_id}-{field}"></span>'
                            f'<svg class="ms-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>'
                            f'</button>'
                            f'<div class="ms-panel" id="ms-panel-{page_id}-{field}"></div>'
                            f'</div></div>'
                        )
                    else:
                        filter_items.append(
                            f'      <div class="filter-item">'
                            f'<label>{label_text}</label>'
                            f'<div class="filter-select-wrap">'
                            f'<select id="filter-{page_id}-{field}" onchange="applyDashboardFilter(\'{page_id}\')">'
                            f'<option value="">All</option></select>'
                            f'<svg class="sel-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>'
                            f'</div></div>'
                        )
                container_parts.append(f'      <div class="filter-bar" id="filters-{page_id}">')
                container_parts.append(
                    '      <div class="filter-bar-title">'
                    '<svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor">'
                    '<path d="M1 2h14l-5 7v4l-4-2V9z"/></svg> Filters</div>'
                )
                container_parts.extend(filter_items)
                container_parts.append(
                    f'      <button class="filter-reset" onclick="resetFilters(\'{page_id}\')">&#x2715; Reset</button>'
                )
                container_parts.append('      </div>')

            # Separate metric cards from regular chart cards
            metric_parts = []
            regular_parts = []
            for chart in page.get("charts", []):
                chart_id = chart["id"]
                if chart.get("type") == "metric":
                    chart_title = chart.get("title", chart_id)
                    metric_parts.append(f'      <div class="card metric-card">')
                    metric_parts.append(f'        <div class="metric-title">{chart_title}</div>')
                    metric_parts.append(f'        <div class="metric-value" id="metric-{chart_id}">—</div>')
                    metric_parts.append(f'      </div>')
                else:
                    chart_title = chart.get("title", chart_id)
                    regular_parts.append(f'      <div class="card chart-card">')
                    regular_parts.append(f'        <h3 class="chart-title">{chart_title}</h3>')
                    regular_parts.append(f'        <div id="chart-{chart_id}" class="chart-container"></div>')
                    regular_parts.append(f'      </div>')

            # Metric cards first (they display inline via CSS)
            container_parts.extend(metric_parts)

            # Regular chart cards — optionally wrapped in CSS Grid
            columns = page.get("layout", {}).get("columns")
            if columns and regular_parts:
                container_parts.append(f'      <div style="display: grid; grid-template-columns: repeat({columns}, 1fr); gap: 16px;">')
                container_parts.extend(regular_parts)
                container_parts.append(f'      </div>')
            else:
                container_parts.extend(regular_parts)

            container_parts.append('    </div>')
            containers.append("\n".join(container_parts))

        return "\n".join(containers)

    @staticmethod
    def _build_derived_js_code(derived_fields: list, var_name: str = "data", indent: str = "        ") -> str:
        """Build a JS forEach block that computes derived columns. Empty string if no fields."""
        if not derived_fields:
            return ""
        lines = [f"{indent}// Derived fields", f"{indent}{var_name}.forEach(row => {{"]
        for f in derived_fields:
            js_expr = re.sub(r'\{(\w+)\}', r'row["\1"]', f["expression"])
            lines.append(f'{indent}  row["{f["name"]}"] = {js_expr};')
        lines.append(f"{indent}}});")
        return "\n".join(lines)

    def _generate_javascript_pages(self, data_spec: Dict[str, Any], pages: list, colors: Dict[str, str], derived_fields: list = None) -> str:
        """Generate JavaScript for multi-page dashboard"""
        data_path = data_spec["path"]
        colors = dict(colors)
        colors["sequential"] = resolve_plotly_colorscale(colors.get("sequential", "blues"))
        theme_json = json.dumps(colors)

        # Collect all charts
        all_charts = []
        for page in pages:
            all_charts.extend(page.get("charts", []))

        # Generate chart rendering functions
        chart_functions = []
        for chart in all_charts:
            chart_id = chart["id"]
            chart_type = chart["type"]
            x = chart.get("x", "")  # Not required for metric type
            y = chart.get("y", "")
            agg = chart.get("agg", "sum")
            # When normalizer moved y→group for count agg, use "count" as the y column
            if not y and agg == "count" and chart_type != "metric":
                y = "count"
            group = chart.get("group")
            title = chart.get("title", chart_id)
            x_type = chart.get("x_type")  # Optional: "date", "number", "string"
            y_type = chart.get("y_type")  # Optional: "number", "string"
            geo_encoding = chart.get("geo_encoding")  # Optional: "iso2", "iso3", "name"
            bins = chart.get("bins", 20)  # Number of bins for histogram
            filters = chart.get("filters", [])  # Optional: filter conditions
            sort_field = chart.get("sort")  # Optional: "x" or "y"
            sort_order = chart.get("sort_order", "asc")  # Optional: "asc" or "desc"
            limit = chart.get("limit")  # Optional: max rows after aggregation
            size_field = chart.get("size")  # Optional: size field for bubble charts
            format_str = resolve_metric_format(chart.get("format", "integer"))  # metric: number format
            suffix = chart.get("suffix", "")          # metric: unit text

            # Axis scale, annotations, reference lines (compile-time helpers)
            x_scale_type = self._axis_type_js(chart, "x")
            y_scale_type = self._axis_type_js(chart, "y")
            annotations_snippet = self._annotations_js(chart)
            ref_lines_snippet = self._reference_lines_js(chart)
            # Axis titles: drop x-title for discrete categorical charts where
            # tick labels already carry the field info; otherwise humanize.
            x_title = "" if chart_type in _DISCRETE_X_CHART_TYPES else humanize_field(x)
            y_title = humanize_field(y)
            # Bar color: use ordinal purple ramp when sorted by y with no group.
            use_purple_ramp_for_bar = (
                chart_type == "bar" and sort_field == "y" and not group
            )
            bar_color_js = (
                "purpleRamp(xValues.length)" if use_purple_ramp_for_bar else "theme.primary"
            )

            # Build options object for aggregation
            options_obj = {
                "xType": x_type,
                "yType": y_type,
                "filters": filters,
                "sort": sort_field,
                "sortOrder": sort_order,
                "limit": limit
            }
            if size_field:
                options_obj["sizeField"] = size_field
            options_js = json.dumps(options_obj)

            # Metric: render as KPI card (no Plotly chart)
            if chart_type == "metric":
                filters_js = json.dumps(filters)
                chart_functions.append(f'''
    function render_{chart_id}(data) {{
      const filters = {filters_js};
      const value = computeMetric(data, '{y}', '{agg}', filters);
      document.getElementById('metric-{chart_id}').textContent = formatMetric(value, '{format_str}', '{suffix}');
    }}''')

            # Check if this is stacked/grouped bar
            elif chart_type in ["stacked_bar", "grouped_bar"]:
                barmode = 'stack' if chart_type == 'stacked_bar' else 'group'
                chart_functions.append(f'''
    function render_{chart_id}(data) {{
      // Stacked/grouped bars need multiple traces
      const options = {options_js};
      const aggregated = aggregateDataWithGroup(data, '{x}', '{y}', '{group}', '{agg}', options);
      const groupValues = [...new Set(aggregated.map(d => d.group))];

      const traces = [];
      groupValues.forEach((groupVal, idx) => {{
        const filtered = aggregated.filter(d => d.group === groupVal);
        traces.push({{
          x: filtered.map(d => d.x),
          y: filtered.map(d => d.y),
          name: groupVal,
          type: 'bar',
          marker: {{ color: theme.secondary[idx % theme.secondary.length] }}
        }});
      }});

      const layout = baseLayout({{
        xaxis: {{ title: {{ text: '{x_title}' }}, type: '{x_scale_type}' }},
        yaxis: {{ title: {{ text: '{y_title}' }}, type: '{y_scale_type}' }},
        barmode: '{barmode}',
        showlegend: true,
        legend: {{ font: {{ color: designTokens.fg_dim, size: 11 }} }},
      }});
      if ('{y_scale_type}' === 'log') applyLogPolish(layout.yaxis);
      if ('{x_scale_type}' === 'log') applyLogPolish(layout.xaxis);

      // Sort x categories by aggregate y total
      if ('{sort_field}' === 'y') {{
        const catTotals = {{}};
        aggregated.forEach(d => {{ catTotals[d.x] = (catTotals[d.x] || 0) + (d.y || 0); }});
        const asc = '{sort_order}' !== 'desc';
        layout.xaxis.categoryorder = 'array';
        layout.xaxis.categoryarray = Object.keys(catTotals).sort((a, b) => asc ? catTotals[a] - catTotals[b] : catTotals[b] - catTotals[a]);
      }}{annotations_snippet}{ref_lines_snippet}

      Plotly.newPlot('chart-{chart_id}', traces, layout, {{ responsive: true }});
    }}''')
            elif chart_type == "bubble" and group:
                chart_functions.append(f'''
    function render_{chart_id}(data) {{
      // Bubble chart: 4D visualization (group, x, y, size)
      const options = {options_js};
      const bubbleData = aggregateBubbleData(data, '{group}', '{x}', '{y}', '{size_field or y}', '{agg}', options);
      const bubbleSizeVals = bubbleData.map(d => Math.abs(d.size));
      const maxSize = Math.max(...bubbleSizeVals);
      const normalizedSizes = bubbleSizeVals.map(v => 10 + (v / maxSize) * 50);

      const trace = {{
        x: bubbleData.map(d => d.x),
        y: bubbleData.map(d => d.y),
        text: bubbleData.map(d => d.group),
        type: 'scatter',
        mode: 'markers+text',
        textposition: 'top center',
        marker: {{
          size: normalizedSizes,
          color: purpleRamp(bubbleData.length),
          line: {{ color: theme.card, width: 1 }},
          sizemode: 'diameter'
        }},
        hovertemplate: bubbleData.map(d => d.group + '<br>{x}: ' + d.x + '<br>{y}: ' + d.y + '<br>{size_field or y}: ' + d.size + '<extra></extra>')
      }};

      const layout = baseLayout({{
        xaxis: {{ title: {{ text: '{x_title}' }}, type: '{x_scale_type}' }},
        yaxis: {{ title: {{ text: '{y_title}' }}, type: '{y_scale_type}' }},
      }});
      if ('{y_scale_type}' === 'log') applyLogPolish(layout.yaxis);
      if ('{x_scale_type}' === 'log') applyLogPolish(layout.xaxis);{annotations_snippet}{ref_lines_snippet}

      Plotly.newPlot('chart-{chart_id}', [trace], layout, {{ responsive: true }});
    }}''')
            elif chart_type == "heatmap":
                heatmap_y = group if group else y
                chart_functions.append(f'''
    function render_{chart_id}(data) {{
      // Heatmap: 2D grid with color intensity
      const options = {options_js};
      const aggregated = aggregateDataWithGroup(data, '{x}', '{y}', '{heatmap_y}', '{agg}', options);
      const heatmapX = [...new Set(aggregated.map(d => d.x))];
      const heatmapY = [...new Set(aggregated.map(d => d.group))];
      const heatmapZ = heatmapY.map(yVal =>
        heatmapX.map(xVal => {{
          const found = aggregated.find(d => d.x === xVal && d.group === yVal);
          return found ? found.y : 0;
        }})
      );

      const trace = {{ x: heatmapX, y: heatmapY, z: heatmapZ, type: 'heatmap', colorscale: theme.sequential || 'Blues' }};

      const layout = baseLayout({{
        xaxis: {{ title: {{ text: '' }} }},
        yaxis: {{ title: {{ text: '' }} }},
      }});{annotations_snippet}{ref_lines_snippet}

      Plotly.newPlot('chart-{chart_id}', [trace], layout, {{ responsive: true }});
    }}''')
            else:
                # Standard single-trace charts
                if chart_type in CHARTS_USE_RAW_DATA:
                    # Raw data charts still need filter support
                    filters_js = json.dumps(filters)
                    data_prep = f'''
      // Use raw data for {chart_type} (with filters)
      const filters = {filters_js};
      const filteredData = applyFilters(data, filters);
      const xValues = filteredData.map(d => d['{x}']);
      const yValues = filteredData.map(d => d['{y}']);'''
                else:
                    size_values_code = ""
                    if size_field:
                        size_values_code = f"\n      const sizeValues = grouped.map(d => d.size);"
                    data_prep = f'''
      const options = {options_js};
      const grouped = aggregateData(data, '{x}', '{y}', '{agg}', options);
      const xValues = grouped.map(d => d.x);
      const yValues = grouped.map(d => d.y);{size_values_code}'''

                chart_functions.append(f'''
    function render_{chart_id}(data) {{{data_prep}

      let trace;
      let traces = [];
      switch ('{chart_type}') {{
        case 'line':
          trace = {{ x: xValues, y: yValues, type: 'scatter', mode: 'lines+markers',
                     line: {{ color: theme.primary, width: 2 }},
                     marker: {{ color: theme.primary, size: 4 }},
                     fill: 'tozeroy',
                     fillcolor: theme.primary + '1a' }};
          break;
        case 'scatter':
          trace = {{ x: xValues, y: yValues, type: 'scatter', mode: 'markers', marker: {{ color: theme.primary }} }};
          break;
        case 'pie':
          trace = {{ labels: xValues, values: yValues, type: 'pie',
                     marker: {{ colors: purpleRamp(xValues.length), line: {{ color: theme.card, width: 1 }} }},
                     textinfo: 'label+percent',
                     textposition: 'inside',
                     insidetextorientation: 'radial',
                     insidetextfont: {{ color: '#1a1b24', size: 11 }} }};
          break;
        case 'area':
          trace = {{ x: xValues, y: yValues, type: 'scatter', fill: 'tozeroy', mode: 'lines', line: {{ color: theme.primary }}, fillcolor: theme.primary + '40' }};
          break;
        case 'histogram':
          // Native Plotly histogram — handles log y correctly. Per-bin colors
          // aren't supported on this trace type, so we use flat primary purple.
          trace = {{ x: xValues, type: 'histogram', nbinsx: {bins},
                     marker: {{ color: theme.primary, line: {{ color: theme.card, width: 1 }} }} }};
          break;
        case 'box':
          // Box plot: shows distribution (min, Q1, median, Q3, max)
          const boxGroups_{chart_id.replace('-', '_')} = [...new Set(data.map(d => d['{x}']))];
          boxGroups_{chart_id.replace('-', '_')}.forEach(group => {{
            traces.push({{
              y: data.filter(d => d['{x}'] === group).map(d => parseFloat(d['{y}'])),
              name: group,
              type: 'box',
              marker: {{ color: theme.primary }}
            }});
          }});
          break;
        case 'geo':
          const geoEnc_{chart_id.replace('-', '_')} = '{geo_encoding}' !== 'None' ? '{geo_encoding}' : detectGeoEncoding(xValues);
          if (geoEnc_{chart_id.replace('-', '_')} === 'iso3') {{
            trace = {{
              type: 'choropleth',
              locations: xValues,
              z: yValues,
              locationmode: 'ISO-3',
              colorscale: theme.sequential || 'Blues',
              zmin: 0,
              zmax: (() => {{ const s = [...yValues].sort((a,b)=>b-a); return s[1] || s[0]; }})(),
              colorbar: {{ title: {{ text: '{y_title}' }} }}
            }};
          }} else {{
            const normalizedX_{chart_id.replace('-', '_')} = xValues.map(v => normalizeCountryForPlotly(v, geoEnc_{chart_id.replace('-', '_')}));
            trace = {{
              type: 'choropleth',
              locations: normalizedX_{chart_id.replace('-', '_')},
              z: yValues,
              locationmode: 'country names',
              colorscale: theme.sequential || 'Blues',
              zmin: 0,
              zmax: (() => {{ const s = [...yValues].sort((a,b)=>b-a); return s[1] || s[0]; }})(),
              colorbar: {{ title: {{ text: '{y_title}' }} }}
            }};
          }}
          break;
        default:
          trace = {{ x: xValues, y: yValues, type: 'bar',
                     marker: {{ color: {bar_color_js}, line: {{ width: 0 }} }} }};
      }}

      if (trace) traces.push(trace);

      let layout;
      if ('{chart_type}' === 'geo') {{
        layout = baseLayout({{
          geo: {{
            showframe: false,
            showland: true,
            showcoastlines: true,
            coastlinecolor: designTokens.geo_border,
            showcountries: true,
            countrycolor: designTokens.geo_border,
            landcolor: designTokens.geo_land,
            oceancolor: theme.card,
            showocean: true,
            projection: {{ type: 'natural earth' }},
            bgcolor: theme.card,
          }},
          margin: {{ t: 8, r: 0, b: 0, l: 0 }},
        }});
      }} else {{
        layout = baseLayout({{
          xaxis: {{ title: {{ text: '{x_title}' }}, type: '{x_scale_type}' }},
          yaxis: {{ title: {{ text: '{y_title}' }}, type: '{y_scale_type}' }},
          margin: {{ b: ('{chart_type}' === 'bar' || '{chart_type}' === 'box') ? 100 : 56 }},
        }});
        if ('{y_scale_type}' === 'log') applyLogPolish(layout.yaxis);
        if ('{x_scale_type}' === 'log') applyLogPolish(layout.xaxis);
        if ('{chart_type}' === 'bar' || '{chart_type}' === 'box') {{
          layout.xaxis.tickangle = -35;
          layout.xaxis.gridcolor = 'rgba(0,0,0,0)';
        }}
      }}{annotations_snippet}{ref_lines_snippet}

      Plotly.newPlot('chart-{chart_id}', traces, layout, {{ responsive: true }});
    }}''')

        # Generate page show function — uses .hidden class so the page-container's
        # `display: grid` survives tab switches (inline `style.display = 'block'`
        # would override the grid layout and cause cards to stack vertically).
        page_show_function = '''
    function showPage(pageId, clickedButton) {
      document.querySelectorAll('.page-container').forEach(page => {
        page.classList.add('hidden');
      });
      document.querySelectorAll('.tab-button').forEach(tab => {
        tab.classList.remove('active');
      });
      const activePage = document.getElementById('page-' + pageId);
      if (activePage) activePage.classList.remove('hidden');
      if (clickedButton) {
        clickedButton.classList.add('active');
      }
      // Plotly needs a relayout when its container becomes visible again.
      requestAnimationFrame(() => {
        if (!window.Plotly) return;
        document.querySelectorAll('#page-' + pageId + ' .chart-container').forEach(el => {
          if (el.offsetParent) Plotly.Plots.resize(el);
        });
      });
    }'''

        render_pages = []
        for page in pages:
            for chart in page.get("charts", []):
                render_pages.append(f"      render_{chart['id']}(data);")

        render_all = f'''
    function renderAllPages(data) {{
{chr(10).join(render_pages)}
    }}'''

        # Geo normalization helpers (if any chart is geo)
        geo_js_block = ""
        if any(c.get("type") == "geo" for c in all_charts):
            geo_js_block = "\n    " + self._generate_geo_js_helpers(target="plotly").replace("\n", "\n    ") + "\n"

        # Design tokens emitted as JS constants (theme-agnostic visual relationships)
        design_tokens_js = json.dumps(DESIGN_TOKENS)
        purple_ramp_js = json.dumps(PURPLE_RAMP)

        # Use the same full-featured aggregation functions as single-page mode
        return f'''  <script>
    const theme = {theme_json};
    const designTokens = {design_tokens_js};
    const PURPLE_RAMP = {purple_ramp_js};
{geo_js_block}
    // Quote-aware CSV line parser (handles airline names with commas, etc.)
    function parseCsvLine(line) {{
      const out = []; let cur = ''; let inQ = false;
      for (let i = 0; i < line.length; i++) {{
        const c = line[i];
        if (inQ) {{
          if (c === '"' && line[i + 1] === '"') {{ cur += '"'; i++; }}
          else if (c === '"') {{ inQ = false; }}
          else {{ cur += c; }}
        }} else {{
          if (c === ',') {{ out.push(cur); cur = ''; }}
          else if (c === '"') {{ inQ = true; }}
          else {{ cur += c; }}
        }}
      }}
      out.push(cur);
      return out;
    }}

    // Light → dark purple intensity ramp for ordinal bar encoding.
    // Continuous RGB interpolation between stops so any bar count produces
    // a uniformly smooth gradient (no stepped clusters at n=12, 18, etc.).
    function purpleRamp(n) {{
      const stops = PURPLE_RAMP;
      if (n <= 1) return [stops[Math.floor(stops.length / 2)]];
      const hexToRgb = h => [parseInt(h.slice(1,3),16), parseInt(h.slice(3,5),16), parseInt(h.slice(5,7),16)];
      const rgbToHex = rgb => '#' + rgb.map(v => Math.round(v).toString(16).padStart(2,'0')).join('');
      const lerpAt = t => {{
        const segments = stops.length - 1;
        const scaled = Math.max(0, Math.min(segments, t * segments));
        const idx = Math.min(segments - 1, Math.floor(scaled));
        const frac = scaled - idx;
        const a = hexToRgb(stops[idx]);
        const b = hexToRgb(stops[idx + 1]);
        return rgbToHex(a.map((v, i) => v + (b[i] - v) * frac));
      }};
      return Array.from({{length: n}}, (_, i) => lerpAt(i / (n - 1)));
    }}

    // snake_case / camelCase → Title Case for axis labels.
    function humanizeField(name) {{
      if (!name) return '';
      const parts = name.replace(/-/g, '_').split('_');
      const expanded = [];
      for (const part of parts) {{
        if (!part) continue;
        let cur = part[0];
        for (let i = 1; i < part.length; i++) {{
          const ch = part[i];
          if (ch >= 'A' && ch <= 'Z' && cur && cur[cur.length - 1] >= 'a' && cur[cur.length - 1] <= 'z') {{
            expanded.push(cur); cur = ch;
          }} else {{ cur += ch; }}
        }}
        expanded.push(cur);
      }}
      return expanded.filter(Boolean).map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
    }}

    // Build a Plotly layout dict with theme-driven paper/plot/axis/font defaults.
    // Per-chart code spreads `extra` over the result for chart-specific overrides.
    function baseLayout(extra) {{
      const base = {{
        paper_bgcolor: theme.card,
        plot_bgcolor:  theme.card,
        font: {{ family: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif', color: designTokens.fg_dim, size: 12 }},
        margin: {{ l: 56, r: 16, t: 16, b: 56 }},
        showlegend: false,
        hoverlabel: {{
          bgcolor: '#1a1b24',
          bordercolor: designTokens.line_soft,
          font: {{ color: theme.text, size: 12 }}
        }},
        xaxis: {{
          gridcolor: designTokens.line_soft,
          linecolor: designTokens.line_soft,
          zerolinecolor: designTokens.line_soft,
          tickcolor: designTokens.line_soft,
          tickfont: {{ color: designTokens.fg_dim, size: 11 }},
          title: {{ font: {{ color: designTokens.muted, size: 11 }} }},
          automargin: true,
        }},
        yaxis: {{
          gridcolor: designTokens.line_soft,
          linecolor: designTokens.line_soft,
          zerolinecolor: designTokens.line_soft,
          tickcolor: designTokens.line_soft,
          tickfont: {{ color: designTokens.fg_dim, size: 11 }},
          title: {{ font: {{ color: designTokens.muted, size: 11 }} }},
          automargin: true,
        }},
      }};
      // Deep merge xaxis/yaxis so per-chart overrides preserve theme defaults.
      const merged = Object.assign({{}}, base, extra || {{}});
      if (extra && extra.xaxis) merged.xaxis = Object.assign({{}}, base.xaxis, extra.xaxis);
      if (extra && extra.yaxis) merged.yaxis = Object.assign({{}}, base.yaxis, extra.yaxis);
      if (extra && extra.margin) merged.margin = Object.assign({{}}, base.margin, extra.margin);
      return merged;
    }}

    // Apply log-scale polish (dtick, power exponent, kill 1/2/5 minor ticks).
    function applyLogPolish(axis) {{
      return Object.assign(axis, {{
        type: 'log',
        dtick: 1,
        exponentformat: 'power',
        showexponent: 'all',
        minor: {{ ticks: '', showgrid: false }},
      }});
    }}

    // Dashboard filter UI (CSV mode — populated from loaded CSV after fetch).
    function closeAllMs() {{
      document.querySelectorAll('.ms-panel.ms-open').forEach(p => p.classList.remove('ms-open'));
      document.querySelectorAll('.ms-btn.ms-open').forEach(b => b.classList.remove('ms-open'));
    }}
    function toggleMs(btn, pageId, field) {{
      const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
      if (!panel) return;
      const opening = !panel.classList.contains('ms-open');
      closeAllMs();
      if (opening) {{ panel.classList.add('ms-open'); btn.classList.add('ms-open'); }}
    }}
    document.addEventListener('click', function(e) {{
      if (!e.target.closest('.ms-wrap')) closeAllMs();
    }});
    document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeAllMs(); }});

    function updateMsLabel(pageId, field) {{
      const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
      const textEl = document.querySelector('#ms-' + pageId + '-' + field + ' .ms-text');
      const countEl = document.getElementById('ms-count-' + pageId + '-' + field);
      if (!panel || !textEl) return;
      const checked = Array.from(panel.querySelectorAll('input[type="checkbox"]:checked'));
      const n = checked.length;
      if (n === 0) {{
        textEl.textContent = 'All';
        textEl.classList.add('placeholder');
        if (countEl) {{ countEl.textContent = ''; countEl.classList.remove('visible'); }}
      }} else if (n === 1) {{
        textEl.textContent = checked[0].value;
        textEl.classList.remove('placeholder');
        if (countEl) {{ countEl.textContent = ''; countEl.classList.remove('visible'); }}
      }} else {{
        textEl.textContent = n + ' selected';
        textEl.classList.remove('placeholder');
        if (countEl) {{ countEl.textContent = ''; countEl.classList.remove('visible'); }}
      }}
    }}

    function readPageFilters(pageId) {{
      const out = {{}};
      document.querySelectorAll('select[id^="filter-' + pageId + '-"]').forEach(sel => {{
        const m = sel.id.match(/^filter-[^-]+-(.+)$/);
        if (m && sel.value) out[m[1]] = [sel.value];
      }});
      document.querySelectorAll('.ms-panel[id^="ms-panel-' + pageId + '-"]').forEach(panel => {{
        const m = panel.id.match(/^ms-panel-[^-]+-(.+)$/);
        if (!m) return;
        const checked = Array.from(panel.querySelectorAll('input[type=checkbox]:checked')).map(cb => cb.value);
        if (checked.length) out[m[1]] = checked;
      }});
      return out;
    }}

    function applyDashboardFilter(pageId) {{
      const filters = readPageFilters(pageId);
      const data = window.__dashmlData || [];
      const filtered = data.filter(row => Object.entries(filters).every(([f, vals]) =>
        vals.map(String).includes(String(row[f]))));
      renderAllPages(filtered);
    }}

    function resetFilters(pageId) {{
      document.querySelectorAll('select[id^="filter-' + pageId + '-"]').forEach(s => {{ s.value = ''; }});
      document.querySelectorAll('.ms-panel[id^="ms-panel-' + pageId + '-"] input[type=checkbox]').forEach(cb => {{ cb.checked = false; }});
      document.querySelectorAll('.ms-panel[id^="ms-panel-' + pageId + '-"]').forEach(panel => {{
        const m = panel.id.match(/^ms-panel-([^-]+)-(.+)$/);
        if (m) updateMsLabel(m[1], m[2]);
      }});
      applyDashboardFilter(pageId);
    }}

    function populateCsvFilters(data) {{
      document.querySelectorAll('select[id^="filter-"]').forEach(sel => {{
        const m = sel.id.match(/^filter-[^-]+-(.+)$/);
        if (!m) return;
        const field = m[1];
        const values = Array.from(new Set(data.map(d => d[field]).filter(v => v !== '' && v != null))).sort();
        values.forEach(v => {{
          const opt = document.createElement('option');
          opt.value = v; opt.textContent = v;
          sel.appendChild(opt);
        }});
      }});
      document.querySelectorAll('.ms-panel').forEach(panel => {{
        const m = panel.id.match(/^ms-panel-([^-]+)-(.+)$/);
        if (!m) return;
        const pageId = m[1]; const field = m[2];
        const values = Array.from(new Set(data.map(d => d[field]).filter(v => v !== '' && v != null))).sort();
        panel.innerHTML = values.map(v => {{
          const esc = String(v).replace(/"/g, '&quot;');
          return '<label class="ms-option"><input type="checkbox" value="' + esc +
                 '" onchange="updateMsLabel(\\'' + pageId + '\\',\\'' + field +
                 '\\');applyDashboardFilter(\\'' + pageId + '\\')"> <span>' + v + '</span></label>';
        }}).join('');
      }});
    }}

    // Apply filters to data
    function applyFilters(data, filters) {{
      if (!filters || filters.length === 0) return data;
      return data.filter(row => {{
        return filters.every(f => {{
          const val = row[f.field];
          switch (f.op) {{
            case 'eq': return val === f.value;
            case 'ne': return val !== f.value;
            case 'gt': return val > f.value;
            case 'lt': return val < f.value;
            case 'gte': return val >= f.value;
            case 'lte': return val <= f.value;
            case 'in': return Array.isArray(f.value) && f.value.includes(val);
            case 'contains': return String(val).includes(f.value);
            case 'range': return Array.isArray(f.value) && f.value.length === 2 && val >= f.value[0] && val <= f.value[1];
            default: return true;
          }}
        }});
      }});
    }}

    // Cast y values based on y_type
    function castYValues(data, y, yType) {{
      if (!yType) return data;
      return data.map(row => {{
        const newRow = {{...row}};
        if (yType === 'number') {{
          newRow[y] = parseFloat(row[y]) || 0;
        }} else if (yType === 'string') {{
          newRow[y] = String(row[y]);
        }}
        return newRow;
      }});
    }}

    // Sort aggregated data
    function sortData(data, sortField, sortOrder, xType) {{
      const result = [...data];
      const ascending = sortOrder !== 'desc';

      if (sortField === 'y') {{
        result.sort((a, b) => ascending ? a.y - b.y : b.y - a.y);
      }} else if (sortField === 'x') {{
        if (xType === 'date') {{
          result.sort((a, b) => {{
            const diff = new Date(a.x) - new Date(b.x);
            return ascending ? diff : -diff;
          }});
        }} else if (xType === 'number') {{
          result.sort((a, b) => ascending ? a.x - b.x : b.x - a.x);
        }} else {{
          result.sort((a, b) => {{
            const cmp = String(a.x).localeCompare(String(b.x));
            return ascending ? cmp : -cmp;
          }});
        }}
      }} else if (xType === 'date') {{
        // Default: sort by date if x_type is date
        result.sort((a, b) => new Date(a.x) - new Date(b.x));
      }} else if (xType === 'number') {{
        result.sort((a, b) => parseFloat(a.x) - parseFloat(b.x));
      }} else {{
        // Default: sort strings alphabetically for consistency across transformers
        result.sort((a, b) => String(a.x).localeCompare(String(b.x)));
      }}
      return result;
    }}

    function aggregateData(data, x, y, agg, options) {{
      options = options || {{}};
      const xType = options.xType;
      const yType = options.yType;
      const filters = options.filters || [];
      const sortField = options.sort;
      const sortOrder = options.sortOrder || 'asc';
      const limit = options.limit;
      const sizeField = options.sizeField;

      // Apply filters first
      let filtered = applyFilters(data, filters);

      // Cast y values
      filtered = castYValues(filtered, y, yType);

      const grouped = {{}};
      filtered.forEach(row => {{
        const key = row[x];
        if (!grouped[key]) grouped[key] = {{ values: [], count: 0, sizeValues: [] }};
        grouped[key].values.push(row[y]);
        grouped[key].count++;
        if (sizeField) grouped[key].sizeValues.push(parseFloat(row[sizeField]) || 0);
      }});

      let result = [];
      Object.keys(grouped).forEach(key => {{
        const values = grouped[key].values;
        let aggregated;
        switch (agg) {{
          case 'sum': aggregated = values.reduce((a, b) => a + b, 0); break;
          case 'mean': aggregated = values.reduce((a, b) => a + b, 0) / values.length; break;
          case 'count': aggregated = grouped[key].count; break;
          default: aggregated = values.reduce((a, b) => a + b, 0);
        }}
        const entry = {{ x: key, y: aggregated }};
        if (sizeField) {{
          const sizeVals = grouped[key].sizeValues;
          switch (agg) {{
            case 'sum': entry.size = sizeVals.reduce((a, b) => a + b, 0); break;
            case 'mean': entry.size = sizeVals.reduce((a, b) => a + b, 0) / sizeVals.length; break;
            case 'count': entry.size = grouped[key].count; break;
            default: entry.size = sizeVals.reduce((a, b) => a + b, 0);
          }}
        }}
        result.push(entry);
      }});

      // Sort
      result = sortData(result, sortField, sortOrder, xType);

      // Limit
      if (limit && limit > 0) {{
        result = result.slice(0, limit);
      }}

      return result;
    }}

    function aggregateDataWithGroup(data, x, y, groupField, agg, options) {{
      options = options || {{}};
      const xType = options.xType;
      const yType = options.yType;
      const filters = options.filters || [];
      const sortField = options.sort;
      const sortOrder = options.sortOrder || 'asc';
      const limit = options.limit;

      // Apply filters first
      let filtered = applyFilters(data, filters);

      // Cast y values
      filtered = castYValues(filtered, y, yType);

      const grouped = {{}};
      filtered.forEach(row => {{
        const xKey = row[x];
        const groupKey = row[groupField];
        const compositeKey = xKey + '|||' + groupKey;
        if (!grouped[compositeKey]) grouped[compositeKey] = {{ x: xKey, group: groupKey, values: [], count: 0 }};
        grouped[compositeKey].values.push(row[y]);
        grouped[compositeKey].count++;
      }});

      let result = [];
      Object.keys(grouped).forEach(key => {{
        const entry = grouped[key];
        const values = entry.values;
        let aggregated;
        switch (agg) {{
          case 'sum': aggregated = values.reduce((a, b) => a + b, 0); break;
          case 'mean': aggregated = values.reduce((a, b) => a + b, 0) / values.length; break;
          case 'count': aggregated = entry.count; break;
          default: aggregated = values.reduce((a, b) => a + b, 0);
        }}
        result.push({{ x: entry.x, group: entry.group, y: aggregated }});
      }});

      // Sort based on sortField or default x_type
      result = sortData(result, sortField, sortOrder, xType);

      // Limit
      if (limit && limit > 0) {{
        result = result.slice(0, limit);
      }}

      return result;
    }}

    // Aggregate data for bubble charts: group by groupField, aggregate x, y, size independently
    function aggregateBubbleData(data, groupField, xMetric, yMetric, sizeMetric, agg, options) {{
      options = options || {{}};
      const filters = options.filters || [];
      const sortField = options.sort;
      const sortOrder = options.sortOrder || 'asc';
      const limit = options.limit;

      let filtered = applyFilters(data, filters);

      const grouped = {{}};
      filtered.forEach(row => {{
        const key = row[groupField];
        if (!grouped[key]) grouped[key] = {{ xValues: [], yValues: [], sizeValues: [], count: 0 }};
        grouped[key].xValues.push(parseFloat(row[xMetric]) || 0);
        grouped[key].yValues.push(parseFloat(row[yMetric]) || 0);
        grouped[key].sizeValues.push(parseFloat(row[sizeMetric]) || 0);
        grouped[key].count++;
      }});

      function aggArray(values, count) {{
        switch (agg) {{
          case 'sum': return values.reduce((a, b) => a + b, 0);
          case 'mean': return values.reduce((a, b) => a + b, 0) / values.length;
          case 'count': return count;
          default: return values.reduce((a, b) => a + b, 0);
        }}
      }}

      let result = [];
      Object.keys(grouped).forEach(key => {{
        const g = grouped[key];
        result.push({{
          group: key,
          x: aggArray(g.xValues, g.count),
          y: aggArray(g.yValues, g.count),
          size: aggArray(g.sizeValues, g.count)
        }});
      }});

      if (sortField === 'y') {{
        const asc = sortOrder !== 'desc';
        result.sort((a, b) => asc ? a.y - b.y : b.y - a.y);
      }} else {{
        const asc = sortOrder !== 'desc';
        result.sort((a, b) => asc ? a.x - b.x : b.x - a.x);
      }}

      if (limit && limit > 0) {{
        result = result.slice(0, limit);
      }}

      return result;
    }}

    // Format a metric scalar value using a format string and optional suffix
    function formatMetric(value, format, suffix) {{
      if (value === null || value === undefined || isNaN(value)) return 'N/A';
      const n = parseFloat(value);
      const m = format.match(/,?\.(\d+)f/);
      const decimals = m ? parseInt(m[1]) : 0;
      const str = n.toLocaleString('en-US', {{minimumFractionDigits: decimals, maximumFractionDigits: decimals}});
      return str + (suffix || '');
    }}

    // Aggregate a column to a scalar metric value
    function computeMetric(data, yField, agg, filters) {{
      let d = applyFilters(data, filters);
      const vals = d.map(r => parseFloat(r[yField])).filter(v => !isNaN(v));
      if (!vals.length) return null;
      if (agg === 'sum') return vals.reduce((a, b) => a + b, 0);
      if (agg === 'mean') return vals.reduce((a, b) => a + b, 0) / vals.length;
      if (agg === 'count') return vals.length;
      return null;
    }}

{''.join(chart_functions)}

{page_show_function}

{render_all}

    fetch('{data_path}')
      .then(response => response.text())
      .then(csv => {{
        const lines = csv.trim().split('\\n').filter(line => line.trim());
        const headers = parseCsvLine(lines[0]).map(h => h.trim());
        const data = lines.slice(1)
          .map(line => {{
            const values = parseCsvLine(line);
            if (values.length !== headers.length) return null;
            const row = {{}};
            headers.forEach((header, i) => {{
              const val = values[i] != null ? String(values[i]).trim() : '';
              row[header] = (val !== '' && !isNaN(val)) ? parseFloat(val) : val;
            }});
            return row;
          }})
          .filter(row => row !== null);
{self._build_derived_js_code(derived_fields or [], var_name="data", indent="        ")}
        window.__dashmlData = data;
        populateCsvFilters(data);
        renderAllPages(data);
      }})
      .catch(error => console.error('Error loading data:', error));
  </script>'''

    def get_run_command(self, output_path: str) -> str:
        """Return command to serve Plotly HTML or Flask app"""
        from pathlib import Path
        output_path_obj = Path(output_path)

        # If output is a directory with Flask app, run Flask
        if output_path_obj.is_dir() and (output_path_obj / "app.py").exists():
            return f"cd {output_path} && {sys.executable} app.py"

        # Otherwise serve directory with http.server (index.html served at /)
        serve_dir = output_path_obj if output_path_obj.is_dir() else output_path_obj.parent
        return f"cd {serve_dir} && echo Dashboard available at: http://localhost:5001 && {sys.executable} -m http.server 5001"

    def _generate_flask_app(self, spec: "NormalizedSpec", data_spec: Dict[str, Any], colors: Dict[str, str]) -> str:
        """Generate Flask backend that connects to SQL database.

        Connection string is constructed at runtime from environment variables
        (DASHML_DB_*); no credentials are baked into the generated source.
        """
        # Use pre-parsed path components from normalizer
        schema = data_spec["sql_schema"]
        table_name = data_spec["sql_table"]

        # Build table reference for SQL
        table_ref = f"{schema}.{table_name}"

        # Build per-chart queries
        all_charts = []
        for page in spec["pages"]:
            all_charts.extend(page.get("charts", []))

        # Build per-chart queries from normalizer-generated SQL templates
        chart_queries_code = "CHART_QUERIES = {\n"
        chart_static_code = "CHART_STATIC_CONDITIONS = {\n"
        for chart in all_charts:
            query = chart["sql"].replace("{table_ref}", table_ref)
            chart_queries_code += f'    "{chart["id"]}": """{query}""",\n'
            chart_static_code += f'    "{chart["id"]}": {repr(chart.get("static_conditions", []))},\n'
        chart_queries_code += "}"
        chart_static_code += "}"

        # Build ALLOWED_FILTER_FIELDS from page-level filters
        all_filter_fields = set()
        for page in spec["pages"]:
            for f in page.get("filters", []):
                all_filter_fields.add(f["field"])
        allowed_fields_code = f"ALLOWED_FILTER_FIELDS = frozenset({repr(all_filter_fields)})"

        # Build derived CTE for filter queries (so derived fields are available)
        from dashml_new.core.normalizer import DashMLNormalizer
        derived_fields = spec.get("derived_fields", [])
        derived_cte_template = DashMLNormalizer._build_derived_cte(derived_fields)
        if derived_cte_template:
            derived_cte_resolved = derived_cte_template.replace("{table_ref}", table_ref)
            derived_filter_source = "__derived"
        else:
            derived_cte_resolved = ""
            derived_filter_source = table_ref

        # Generate Flask app code
        from .secrets import emit_sql_env_loader
        sql_env_loader = emit_sql_env_loader()
        return f'''from flask import Flask, jsonify, send_from_directory, Response
from sqlalchemy import create_engine
import pandas as pd

# Database credentials are loaded from environment variables (DASHML_DB_*).
# See SECRETS.md and .env.example next to this file.
{sql_env_loader}
app = Flask(__name__)

SCHEMA = "{schema}"
TABLE_NAME = "{table_name}"

# Create database engine
engine = create_engine(DATABASE_URL)

# Per-chart SQL queries (generated at compile time)
{chart_queries_code}

{chart_static_code}

{allowed_fields_code}

# Derived CTE for filter queries (empty string if no derived fields)
DERIVED_CTE = """{derived_cte_resolved}"""
DERIVED_FILTER_SOURCE = "{derived_filter_source}"

def build_filter_clause(chart_id, request_args):
    """Build SQL WHERE body from static per-chart conditions + runtime dashboard filters."""
    conditions = ["1=1"]
    conditions.extend(CHART_STATIC_CONDITIONS.get(chart_id, []))
    for field in ALLOWED_FILTER_FIELDS:
        values = request_args.getlist(field)
        if not values:
            continue
        escaped = [str(v).replace("'", "''") for v in values]
        if len(escaped) == 1:
            conditions.append(field + " = '" + escaped[0] + "'")
        else:
            in_list = ", ".join("'" + v + "'" for v in escaped)
            conditions.append(field + " IN (" + in_list + ")")
    return " AND ".join(conditions)

# Cache for column types (fetched once from information_schema)
_column_types_cache = None

def get_column_types():
    """Fetch column types from information_schema and map to simple types"""
    global _column_types_cache
    if _column_types_cache is not None:
        return _column_types_cache

    try:
        query = f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = '{{SCHEMA}}' AND table_name = '{{TABLE_NAME}}'
        """
        df = pd.read_sql(query, engine)

        # Map SQL types to simple types: date, number, string
        type_mapping = {{}}
        for _, row in df.iterrows():
            col_name = row['column_name']
            data_type = str(row['data_type']).upper()

            # Date types (PostgreSQL, MySQL, etc.)
            if any(dt in data_type for dt in ['DATE', 'TIME', 'TIMESTAMP', 'INTERVAL']):
                type_mapping[col_name] = 'date'
            # Numeric types
            elif any(dt in data_type for dt in ['INT', 'FLOAT', 'NUMERIC', 'DECIMAL',
                                                  'REAL', 'DOUBLE', 'SERIAL', 'MONEY']):
                type_mapping[col_name] = 'number'
            # Everything else is string
            else:
                type_mapping[col_name] = 'string'

        _column_types_cache = type_mapping
        return type_mapping
    except Exception as e:
        print(f"Warning: Could not fetch column types: {{e}}")
        return {{}}

@app.route('/')
def index():
    """Serve the HTML frontend"""
    return send_from_directory('.', 'index.html')

@app.route('/api/schema')
def get_schema():
    """Return column types from information_schema"""
    try:
        column_types = get_column_types()
        return jsonify(column_types)
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

@app.route('/api/chart/<chart_id>')
def get_chart_data(chart_id):
    """Fetch pre-aggregated data for a specific chart"""
    from flask import request
    query_template = CHART_QUERIES.get(chart_id)
    if not query_template:
        return jsonify({{"error": "Unknown chart"}}), 404
    try:
        filter_clause = build_filter_clause(chart_id, request.args)
        query = query_template.format(filter_clause=filter_clause)
        df = pd.read_sql(query, engine)
        json_str = df.to_json(orient='records', date_format='iso')
        return Response(json_str, mimetype='application/json')
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

@app.route('/api/filter/<field>')
def get_filter_options(field):
    """Return DISTINCT values for a filter field"""
    from flask import request
    if field not in ALLOWED_FILTER_FIELDS:
        return jsonify({{"error": "Field not allowed"}}), 403
    try:
        query = DERIVED_CTE + " SELECT DISTINCT " + field + " FROM " + DERIVED_FILTER_SOURCE + " WHERE " + field + " IS NOT NULL ORDER BY 1 LIMIT 500"
        df = pd.read_sql(query, engine)
        values = sorted(df.iloc[:, 0].dropna().astype(str).tolist())
        return jsonify(values)
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

if __name__ == '__main__':
    print("Starting Flask server...")
    print(f"Dashboard available at: http://localhost:5001")
    app.run(debug=True, port=5001)
'''

    def _generate_sql_frontend(self, spec: "NormalizedSpec", title: str, colors: Dict[str, str]) -> str:
        """Generate HTML frontend that fetches from Flask API"""
        html_parts = []

        html_parts.append(self._generate_html_header(title, colors))

        html_parts.append("<body>")
        html_parts.append(f'  <div class="container">')
        html_parts.append(f'    <h1>{title}</h1>')

        # Always use pages (normalizer guarantees pages[] exists)
        pages = spec["pages"]
        html_parts.append(self._generate_page_tabs(pages, colors))
        html_parts.append(self._generate_page_containers(pages, colors))
        html_parts.append('  </div>')
        html_parts.append(self._generate_javascript_pages_sql(pages, colors))

        # Body end
        html_parts.append("</body>")
        html_parts.append("</html>")

        return "\n".join(html_parts)

    def _generate_javascript_sql(self, charts: list, colors: Dict[str, str]) -> str:
        """DEPRECATED: Dead code — references non-existent /api/data endpoint.
        Multi-page SQL mode uses _generate_javascript_pages instead.
        Kept for reference only; do not call."""
        colors = dict(colors)
        colors["sequential"] = resolve_plotly_colorscale(colors.get("sequential", "blues"))
        theme_json = json.dumps(colors)

        js_parts = []
        js_parts.append("  <script>")
        js_parts.append(f"    const theme = {theme_json};")
        js_parts.append("    // Chart definitions")
        js_parts.append(f"    const charts = {self._charts_to_json(charts)};")
        js_parts.append("    // Column types from INFORMATION_SCHEMA (auto-detected)")
        js_parts.append("    let columnTypes = {};")
        js_parts.append("")

        # Geo normalization helpers (if any chart is geo)
        if any(c.get("type") == "geo" for c in charts):
            js_parts.append(self._generate_geo_js_helpers(target="plotly"))
            js_parts.append("")

        js_parts.append(self._generate_aggregator_with_schema())
        js_parts.append("")
        js_parts.append(self._generate_renderer(multi_page=False))
        js_parts.append("")
        js_parts.append('''    // Fetch schema first, then data
    Promise.all([
      fetch('/api/schema').then(r => r.json()),
      fetch('/api/data').then(r => r.json())
    ])
      .then(([schema, data]) => {
        columnTypes = schema;

        // Ensure correct types: numbers as numbers, dates as ISO strings
        // Plotly.js handles ISO date strings natively on date axes
        window.dashmlData = data.map(row => {
          const parsedRow = {};
          for (const [column, value] of Object.entries(row)) {
            if (value === null) {
              parsedRow[column] = null;
            } else if (columnTypes[column] === 'number') {
              parsedRow[column] = parseFloat(value) || 0;
            } else {
              // Keep date ISO strings and other strings as-is
              parsedRow[column] = value;
            }
          }
          return parsedRow;
        });

        renderChart(charts[0]);
      })
      .catch(error => {
        document.getElementById('chart').innerHTML =
          '<div style="color: red;">Error loading data: ' + error.message + '</div>';
      });''')
        js_parts.append("")
        js_parts.append('''    function renderSelectedChart() {
      const select = document.getElementById('chartSelect');
      const chartId = select.value;
      const chart = charts.find(c => c.id === chartId);
      if (chart) renderChart(chart);
    }''')
        js_parts.append("  </script>")

        return "\n".join(js_parts)

    def _generate_javascript_pages_sql(self, pages: list, colors: Dict[str, str]) -> str:
        """Generate JavaScript for multi-page dashboard with per-chart async loading"""
        colors = dict(colors)
        colors["sequential"] = resolve_plotly_colorscale(colors.get("sequential", "blues"))
        theme_json = json.dumps(colors)

        all_charts = []
        for page in pages:
            all_charts.extend(page.get("charts", []))

        # Build PAGE_CHARTS map (compile-time mapping of page_id -> chart_id list)
        page_charts_map = {}
        for page in pages:
            page_id = page["id"]
            page_filters = page.get("filters", [])
            if page_filters:
                page_charts_map[page_id] = {
                    "charts": [c["id"] for c in page.get("charts", []) if c.get("type") != "metric"],
                    "metrics": [c["id"] for c in page.get("charts", []) if c.get("type") == "metric"],
                    "filter_fields": [f["field"] for f in page_filters]
                }
        page_charts_json = json.dumps(page_charts_map)

        chart_functions = []
        for chart in all_charts:
            chart_id = chart["id"]
            chart_type = chart["type"]
            title = chart.get("title", chart_id)
            x = chart.get("x", "")  # Not required for metric type
            y = chart.get("y", "")
            agg = chart.get("agg", "sum")
            if not y and agg == "count" and chart_type != "metric":
                y = "count"
            group = chart.get("group")
            size_field = chart.get("size")
            bins = chart.get("bins", 20)
            sort_field = chart.get("sort")
            sort_order = chart.get("sort_order", "asc")
            format_str = resolve_metric_format(chart.get("format", "integer"))  # metric: number format
            suffix = chart.get("suffix", "")          # metric: unit text

            # Axis scale, annotations, reference lines (compile-time helpers)
            x_scale_type = self._axis_type_js(chart, "x")
            y_scale_type = self._axis_type_js(chart, "y")
            annotations_snippet = self._annotations_js(chart)
            ref_lines_snippet = self._reference_lines_js(chart)

            if chart_type == "metric":
                chart_functions.append(f'''
    window.render_{chart_id} = function(data) {{
      const value = (data && data[0] && data[0].y !== undefined) ? parseFloat(data[0].y) : null;
      document.getElementById('metric-{chart_id}').textContent = formatMetric(value, '{format_str}', '{suffix}');
    }}''')
            elif chart_type in ["stacked_bar", "grouped_bar"]:
                barmode = 'stack' if chart_type == 'stacked_bar' else 'group'
                # Compute category order: sort x categories by aggregate y total
                if sort_field == "y":
                    ascending_js = "true" if sort_order == "asc" else "false"
                    category_order_js = f"""
      // Sort x categories by total y
      const catTotals = {{}};
      data.forEach(d => {{ catTotals[d.x] = (catTotals[d.x] || 0) + (parseFloat(d.y) || 0); }});
      const catOrder = Object.keys(catTotals).sort((a, b) => {ascending_js} ? catTotals[a] - catTotals[b] : catTotals[b] - catTotals[a]);"""
                    xaxis_js = f"title: '{x}', type: '{x_scale_type}', color: theme.text, gridcolor: theme.text + '20', categoryorder: 'array', categoryarray: catOrder"
                else:
                    category_order_js = ""
                    xaxis_js = f"title: '{x}', type: '{x_scale_type}', color: theme.text, gridcolor: theme.text + '20'"
                chart_functions.append(f'''
    window.render_{chart_id} = function(data) {{
      const groupValues = [...new Set(data.map(d => d.grp))];
      const traces = [];{category_order_js}
      groupValues.forEach((groupVal, idx) => {{
        const filtered = data.filter(d => d.grp === groupVal);
        traces.push({{
          x: filtered.map(d => d.x),
          y: filtered.map(d => d.y),
          name: groupVal,
          type: 'bar',
          marker: {{ color: theme.secondary[idx % theme.secondary.length] }}
        }});
      }});
      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ {xaxis_js} }},
        yaxis: {{ title: '{y}', type: '{y_scale_type}', color: theme.text, gridcolor: theme.text + '20' }},
        barmode: '{barmode}',
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};{annotations_snippet}{ref_lines_snippet}
      Plotly.newPlot('chart-{chart_id}', traces, layout, {{ responsive: true }});
    }}''')
            elif chart_type == "bubble" and group:
                chart_functions.append(f'''
    window.render_{chart_id} = function(data) {{
      const bubbleSizeVals = data.map(d => Math.abs(d.size));
      const maxSize = Math.max(...bubbleSizeVals);
      const normalizedSizes = bubbleSizeVals.map(v => 10 + (v / maxSize) * 50);
      const trace = {{
        x: data.map(d => d.x),
        y: data.map(d => d.y),
        text: data.map(d => d.grp),
        type: 'scatter',
        mode: 'markers+text',
        textposition: 'top center',
        marker: {{
          size: normalizedSizes,
          color: purpleRamp(data.length),
          line: {{ color: theme.card, width: 1 }},
          sizemode: 'diameter'
        }},
        hovertemplate: data.map(d => d.grp + '<br>{x}: ' + d.x + '<br>{y}: ' + d.y + '<br>size: ' + d.size + '<extra></extra>')
      }};
      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ title: '{x}', type: '{x_scale_type}', color: theme.text, gridcolor: theme.text + '20' }},
        yaxis: {{ title: '{y}', type: '{y_scale_type}', color: theme.text, gridcolor: theme.text + '20' }},
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};{annotations_snippet}{ref_lines_snippet}
      Plotly.newPlot('chart-{chart_id}', [trace], layout, {{ responsive: true }});
    }}''')
            elif chart_type == "heatmap":
                chart_functions.append(f'''
    window.render_{chart_id} = function(data) {{
      const heatmapX = [...new Set(data.map(d => d.x))];
      const heatmapY = [...new Set(data.map(d => d.heatmap_y))];
      const heatmapZ = heatmapY.map(yVal =>
        heatmapX.map(xVal => {{
          const found = data.find(d => d.x === xVal && d.heatmap_y === yVal);
          return found ? found.y : 0;
        }})
      );
      const trace = {{ x: heatmapX, y: heatmapY, z: heatmapZ, type: 'heatmap', colorscale: theme.sequential || 'Blues' }};
      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ title: '{x}', type: '{x_scale_type}', color: theme.text }},
        yaxis: {{ title: '{chart.get("group", y)}', type: '{y_scale_type}', color: theme.text }},
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};{annotations_snippet}{ref_lines_snippet}
      Plotly.newPlot('chart-{chart_id}', [trace], layout, {{ responsive: true }});
    }}''')
            else:
                # Standard single-trace charts - data arrives pre-aggregated with x/y columns
                geo_enc_val = chart.get("geo_encoding")
                chart_functions.append(f'''
    window.render_{chart_id} = function(data) {{
      const xValues = data.map(d => d.x);
      const yValues = data.map(d => d.y);
      let trace;
      let traces = [];
      switch ('{chart_type}') {{
        case 'line':
          trace = {{ x: xValues, y: yValues, type: 'scatter', mode: 'lines+markers', line: {{ color: theme.primary }} }};
          break;
        case 'scatter':
          trace = {{ x: xValues, y: yValues, type: 'scatter', mode: 'markers', marker: {{ color: theme.primary }} }};
          break;
        case 'pie':
          trace = {{ labels: xValues, values: yValues, type: 'pie',
                     marker: {{ colors: purpleRamp(xValues.length), line: {{ color: theme.card, width: 1 }} }},
                     textinfo: 'label+percent',
                     textposition: 'inside',
                     insidetextorientation: 'radial',
                     insidetextfont: {{ color: '#1a1b24', size: 11 }} }};
          break;
        case 'area':
          trace = {{ x: xValues, y: yValues, type: 'scatter', fill: 'tozeroy', mode: 'lines', line: {{ color: theme.primary }}, fillcolor: theme.primary + '40' }};
          break;
        case 'histogram':
          trace = {{ x: xValues, type: 'histogram', nbinsx: {bins}, marker: {{ color: theme.primary }} }};
          break;
        case 'box':
          const boxGroups = [...new Set(data.map(d => d.x))];
          boxGroups.forEach(group => {{
            traces.push({{
              y: data.filter(d => d.x === group).map(d => parseFloat(d.y)),
              name: group,
              type: 'box',
              marker: {{ color: theme.primary }}
            }});
          }});
          break;
        case 'geo':
          const geoEnc = '{geo_enc_val}' !== 'None' ? '{geo_enc_val}' : detectGeoEncoding(xValues);
          if (geoEnc === 'iso3') {{
            trace = {{
              type: 'choropleth',
              locations: xValues,
              z: yValues,
              locationmode: 'ISO-3',
              colorscale: theme.sequential || 'Blues',
              colorbar: {{ title: '{y}' }}
            }};
          }} else {{
            const normalizedX = xValues.map(v => normalizeCountryForPlotly(v, geoEnc));
            trace = {{
              type: 'choropleth',
              locations: normalizedX,
              z: yValues,
              locationmode: 'country names',
              colorscale: theme.sequential || 'Blues',
              colorbar: {{ title: '{y}' }}
            }};
          }}
          break;
        default:
          trace = {{ x: xValues, y: yValues, type: 'bar', marker: {{ color: theme.primary }} }};
      }}
      if (trace) traces.push(trace);
      let layout;
      if ('{chart_type}' === 'geo') {{
        layout = {{
          title: {{ text: '{title}', font: {{ color: theme.text }} }},
          geo: {{
            showframe: false,
            showcoastlines: true,
            projection: {{ type: 'natural earth' }},
            bgcolor: 'rgba(0,0,0,0)'
          }},
          margin: {{ t: 60, r: 0, b: 0, l: 0 }},
          paper_bgcolor: 'rgba(0,0,0,0)'
        }};
      }} else {{
        layout = {{
          title: {{ text: '{title}', font: {{ color: theme.text }} }},
          xaxis: {{ title: '{x}', type: '{x_scale_type}', color: theme.text, gridcolor: theme.text + '20' }},
          yaxis: {{ title: '{y}', type: '{y_scale_type}', color: theme.text, gridcolor: theme.text + '20' }},
          margin: {{ t: 60, r: 40, b: 60, l: 60 }},
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)'
        }};
      }}{annotations_snippet}{ref_lines_snippet}
      Plotly.newPlot('chart-{chart_id}', traces, layout, {{ responsive: true }});
    }}''')

        # Generate load calls (metrics use loadMetric; charts use loadChart)
        load_calls = []
        for chart in all_charts:
            if chart.get("type") == "metric":
                load_calls.append(f"    loadMetric('{chart['id']}', window['render_{chart['id']}'])")
            else:
                load_calls.append(f"    loadChart('{chart['id']}', window['render_{chart['id']}'])")
        load_calls_str = ",\n".join(load_calls)

        page_show_function = '''
    function showPage(pageId, clickedButton) {
      document.querySelectorAll('.page-container').forEach(page => {
        page.style.display = 'none';
      });
      document.querySelectorAll('.tab-button').forEach(tab => {
        tab.classList.remove('active');
      });
      document.getElementById('page-' + pageId).style.display = 'block';
      if (clickedButton) {
        clickedButton.classList.add('active');
      }
    }'''

        # Geo normalization helpers (if any chart is geo)
        geo_js_block_sql = ""
        if any(c.get("type") == "geo" for c in all_charts):
            geo_js_block_sql = "\n    " + self._generate_geo_js_helpers(target="plotly").replace("\n", "\n    ") + "\n"

        return f'''  <script>
    const theme = {theme_json};
{geo_js_block_sql}
    // Format a metric scalar value
    function formatMetric(value, format, suffix) {{
      if (value === null || value === undefined || isNaN(value)) return 'N/A';
      const n = parseFloat(value);
      const m = format.match(/,?\.(\d+)f/);
      const decimals = m ? parseInt(m[1]) : 0;
      const str = n.toLocaleString('en-US', {{minimumFractionDigits: decimals, maximumFractionDigits: decimals}});
      return str + (suffix || '');
    }}

    async function loadChart(chartId, renderFn, extraParams) {{
      const container = document.getElementById('chart-' + chartId);
      if (!container) return;
      container.innerHTML = '<div class="chart-spinner"><div class="spinner"></div><span>Loading...</span></div>';
      try {{
        const url = '/api/chart/' + chartId + (extraParams ? '?' + extraParams : '');
        const resp = await fetch(url);
        if (!resp.ok) {{
          const body = await resp.json().catch(() => ({{}}));
          throw new Error(body.error || 'HTTP ' + resp.status);
        }}
        const data = await resp.json();
        container.innerHTML = '';
        renderFn(data);
      }} catch (err) {{
        container.innerHTML = '<div class="chart-error">Error loading chart: ' + err.message + '</div>';
        console.error('Chart ' + chartId + ' failed:', err);
      }}
    }}

    async function loadMetric(chartId, renderFn, extraParams) {{
      const el = document.getElementById('metric-' + chartId);
      if (!el) return;
      el.textContent = '…';
      try {{
        const url = '/api/chart/' + chartId + (extraParams ? '?' + extraParams : '');
        const resp = await fetch(url);
        if (!resp.ok) {{
          const body = await resp.json().catch(() => ({{}}));
          throw new Error(body.error || 'HTTP ' + resp.status);
        }}
        const data = await resp.json();
        renderFn(data);
      }} catch (err) {{
        if (el) el.textContent = 'Error';
        console.error('Metric ' + chartId + ' failed:', err);
      }}
    }}

    const PAGE_CHARTS = {page_charts_json};

    function toggleMs(btn, pageId, field) {{
      const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
      const isOpen = panel.classList.contains('ms-open');
      closeAllMs();
      if (!isOpen) {{ panel.classList.add('ms-open'); btn.classList.add('ms-open'); }}
    }}
    function closeAllMs() {{
      document.querySelectorAll('.ms-panel.ms-open').forEach(p => p.classList.remove('ms-open'));
      document.querySelectorAll('.ms-btn.ms-open').forEach(b => b.classList.remove('ms-open'));
    }}
    document.addEventListener('click', function(e) {{
      if (!e.target.closest('.ms-wrap')) closeAllMs();
    }});
    function updateMsLabel(pageId, field) {{
      const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
      const countEl = document.getElementById('ms-count-' + pageId + '-' + field);
      const textEl = document.querySelector('#ms-' + pageId + '-' + field + ' .ms-text');
      if (!panel || !countEl || !textEl) return;
      const checked = Array.from(panel.querySelectorAll('input[type="checkbox"]:checked'));
      const n = checked.length;
      if (n === 0) {{
        textEl.textContent = 'All';
        countEl.textContent = ''; countEl.classList.remove('visible');
      }} else if (n === 1) {{
        textEl.textContent = checked[0].value;
        countEl.textContent = ''; countEl.classList.remove('visible');
      }} else {{
        textEl.textContent = checked[0].value;
        countEl.textContent = '+' + (n - 1); countEl.classList.add('visible');
      }}
    }}
    function collectFilterParams(pageId) {{
      const pageInfo = PAGE_CHARTS[pageId];
      if (!pageInfo) return '';
      const params = new URLSearchParams();
      for (const field of pageInfo.filter_fields) {{
        const sel = document.getElementById('filter-' + pageId + '-' + field);
        if (sel) {{
          if (sel.value) params.append(field, sel.value);
        }} else {{
          const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
          if (panel) panel.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => params.append(field, cb.value));
        }}
      }}
      return params.toString();
    }}
    function applyDashboardFilter(pageId) {{
      const pageInfo = PAGE_CHARTS[pageId];
      if (!pageInfo) return;
      const params = collectFilterParams(pageId);
      pageInfo.charts.forEach(chartId => {{
        loadChart(chartId, window['render_' + chartId], params);
      }});
      pageInfo.metrics.forEach(chartId => {{
        loadMetric(chartId, window['render_' + chartId], params);
      }});
    }}
    function resetFilters(pageId) {{
      const pageInfo = PAGE_CHARTS[pageId];
      if (!pageInfo) return;
      for (const field of pageInfo.filter_fields) {{
        const sel = document.getElementById('filter-' + pageId + '-' + field);
        if (sel) {{ sel.value = ''; }} else {{
          const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
          if (panel) {{ panel.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false); updateMsLabel(pageId, field); }}
        }}
      }}
      applyDashboardFilter(pageId);
    }}
    function loadFilterOptions(pageId) {{
      const pageInfo = PAGE_CHARTS[pageId];
      if (!pageInfo) return;
      for (const field of pageInfo.filter_fields) {{
        const isSel = !!document.getElementById('filter-' + pageId + '-' + field);
        fetch('/api/filter/' + field)
          .then(r => {{ if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }})
          .then(values => {{
            if (isSel) {{
              const sel = document.getElementById('filter-' + pageId + '-' + field);
              if (!sel) return;
              values.forEach(v => {{
                const opt = document.createElement('option');
                opt.value = v; opt.textContent = v; sel.appendChild(opt);
              }});
            }} else {{
              const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
              if (!panel) return;
              panel.innerHTML = values.map(v =>
                `<label class="ms-option"><input type="checkbox" value="${{v}}" onchange="updateMsLabel('${{pageId}}','${{field}}');applyDashboardFilter('${{pageId}}')"> ${{v}}</label>`
              ).join('');
            }}
          }})
          .catch(err => console.warn('Could not load filter options for ' + field + ':', err));
      }}
    }}

{''.join(chart_functions)}

{page_show_function}

    // Load all charts independently (async per-chart)
    Promise.allSettled([
{load_calls_str}
    ]);

    // Initialize filter options
    Object.keys(PAGE_CHARTS).forEach(pageId => loadFilterOptions(pageId));
  </script>'''