"""
Plotly Transformer - Generates Plotly HTML/JavaScript from DashML specs
"""
import re
import sys
from typing import TYPE_CHECKING, Dict, Any, List
from pathlib import Path
import json
from .base import Transformer, TransformerError
from .constants import (
    CHARTS_NEED_AGGREGATION,
    CHARTS_USE_RAW_DATA,
    DEFAULT_HISTOGRAM_BINS,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLORS,
    DEFAULT_SORT_ORDER,
    resolve_metric_format,
    resolve_plotly_colorscale,
    country_mapping_as_js,
)

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
        items = []
        for ann in annotations:
            x_val = json.dumps(ann.get("x", ""))
            y_val = json.dumps(ann.get("y", 0))
            text = json.dumps(ann.get("text", ""))
            color = json.dumps(ann.get("color", "red"))
            items.append(
                f"{{ x: {x_val}, y: {y_val}, text: {text}, showarrow: true, arrowhead: 2, font: {{ color: {color} }} }}"
            )
        return "\n      layout.annotations = [" + ", ".join(items) + "];"

    @staticmethod
    def _reference_lines_js(chart: dict) -> str:
        """Build a JS snippet that sets ``layout.shapes`` from the chart spec.

        Returns an empty string when there are no reference lines.
        """
        ref_lines = chart.get("reference_lines")
        if not ref_lines:
            return ""
        style_map = {"solid": "solid", "dashed": "dash", "dotted": "dot"}
        items = []
        for rl in ref_lines:
            axis = rl.get("axis", "y")
            value = json.dumps(rl.get("value", 0))
            label = rl.get("label", "")
            dash = style_map.get(rl.get("style", "dashed"), "dash")
            if axis == "y":
                shape = (
                    f"{{ type: 'line', yref: 'y', y0: {value}, y1: {value}, "
                    f"xref: 'paper', x0: 0, x1: 1, "
                    f"line: {{ color: 'red', width: 1.5, dash: '{dash}' }} }}"
                )
            else:
                shape = (
                    f"{{ type: 'line', xref: 'x', x0: {value}, x1: {value}, "
                    f"yref: 'paper', y0: 0, y1: 1, "
                    f"line: {{ color: 'red', width: 1.5, dash: '{dash}' }} }}"
                )
            items.append(shape)
        # If any reference line has a label, also add annotations for them
        ann_items = []
        for rl in ref_lines:
            label = rl.get("label", "")
            if not label:
                continue
            axis = rl.get("axis", "y")
            value = json.dumps(rl.get("value", 0))
            label_json = json.dumps(label)
            if axis == "y":
                ann_items.append(
                    f"{{ x: 1, xref: 'paper', y: {value}, yref: 'y', text: {label_json}, "
                    f"showarrow: false, font: {{ color: 'red', size: 11 }}, xanchor: 'left' }}"
                )
            else:
                ann_items.append(
                    f"{{ y: 1, yref: 'paper', x: {value}, xref: 'x', text: {label_json}, "
                    f"showarrow: false, font: {{ color: 'red', size: 11 }}, yanchor: 'bottom' }}"
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
        """Generate Flask backend that connects to BigQuery"""
        db_config = spec["db_config"]
        project = db_config["project"]
        credentials_path = db_config.get("credentials_path")

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

        # Build credentials loading code
        if credentials_path:
            safe_path = credentials_path.replace(chr(92), '/')
            credentials_code = f'''
# Load credentials from service account file
from google.oauth2 import service_account
credentials = service_account.Credentials.from_service_account_file(
    "{safe_path}",
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
# Use the service account\'s own project for billing; table refs use PROJECT_ID
client = bigquery.Client(credentials=credentials)
'''
        else:
            credentials_code = '''
# Use default credentials (from gcloud auth or GOOGLE_APPLICATION_CREDENTIALS env var)
client = bigquery.Client(project=PROJECT_ID)
'''

        return f'''from flask import Flask, jsonify, send_from_directory
from google.cloud import bigquery
import json
import traceback
from datetime import date, datetime
from decimal import Decimal
import os

app = Flask(__name__)

# BigQuery configuration
PROJECT_ID = "{project}"
DATASET = "{dataset}"
TABLE_NAME = "{table_name}"
{credentials_code}

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
        """Generate HTML header with dynamic CSS based on theme"""
        bg = colors["background"]
        card_bg = colors["card"]
        text = colors["text"]
        primary = colors["primary"]

        # If background is dark (simple heuristic), make shadow lighter or different
        # TODO: [Complexity] Complex conditional for dark color detection - extract to helper function
        # Fix: def is_dark_color(hex_color: str) -> bool:
        #          return hex_color.startswith("#") and len(hex_color) == 7 and int(hex_color[1:3], 16) < 100
        is_dark = bg.startswith("#") and len(bg) == 7 and int(bg[1:3], 16) < 100
        shadow = "0 2px 4px rgba(255,255,255,0.1)" if is_dark else "0 2px 4px rgba(0,0,0,0.1)"

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      margin: 0;
      padding: 20px;
      background-color: {bg};
      color: {text};
    }}
    .container {{
      max-width: 1200px;
      margin: 0 auto;
      background-color: {bg};
      padding: 0;
    }}
    .card {{
      background-color: {card_bg};
      padding: 30px;
      border-radius: 8px;
      box-shadow: {shadow};
      margin-bottom: 20px;
    }}
    h1 {{
      margin-top: 0;
      color: {text};
    }}
    #chart {{
      margin-top: 20px;
      min-height: 500px;
    }}
    .chart-selector {{
      margin: 20px 0;
    }}
    select {{
      padding: 8px 12px;
      font-size: 14px;
      border: 1px solid #ddd;
      border-radius: 4px;
      background-color: {card_bg};
      color: {text};
    }}
    label {{
      margin-right: 10px;
      font-weight: 500;
      color: {text};
    }}
    .page-tabs {{
      display: flex;
      gap: 10px;
      margin: 20px 0;
      border-bottom: 2px solid {text}40; /* 40 = 25% opacity hex */
      padding-bottom: 0;
    }}
    .tab-button {{
      padding: 10px 20px;
      background-color: transparent;
      border: none;
      border-bottom: 3px solid transparent;
      cursor: pointer;
      font-size: 16px;
      font-weight: 500;
      color: {text};
      opacity: 0.7;
      transition: all 0.2s;
    }}
    .tab-button:hover {{
      opacity: 1;
      background-color: {text}10; /* 10 = ~6% opacity */
    }}
    .tab-button.active {{
      color: {primary};
      border-bottom-color: {primary};
      opacity: 1;
    }}
    .page-container {{
      margin-top: 20px;
    }}
    .page-description {{
      color: {text};
      opacity: 0.8;
      margin-bottom: 20px;
    }}
    .chart-container {{
      margin: 20px 0;
      min-height: 400px;
    }}
    .chart-spinner {{
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; min-height: 300px; gap: 12px;
      color: {text}; opacity: 0.6;
    }}
    .chart-spinner .spinner {{
      width: 40px; height: 40px;
      border: 3px solid {text}20;
      border-top-color: {primary};
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .chart-error {{
      display: flex; align-items: center; justify-content: center;
      min-height: 300px; color: #e74c3c;
    }}
    .metric-card {{
      text-align: center;
      padding: 24px 20px;
      min-width: 160px;
      display: inline-block;
    }}
    .metric-title {{
      font-size: 13px;
      color: {text};
      opacity: 0.65;
      margin-bottom: 10px;
      text-transform: uppercase;
      letter-spacing: 0.07em;
    }}
    .metric-value {{
      font-size: 2.6rem;
      font-weight: 700;
      color: {primary};
      line-height: 1.1;
    }}
    .filter-bar {{
      display: flex;
      gap: 16px;
      align-items: flex-end;
      flex-wrap: wrap;
      padding: 14px 18px;
      background: {card_bg};
      border-radius: 10px;
      margin-bottom: 20px;
      border: 1px solid rgba(128,128,128,0.12);
      box-shadow: 0 1px 4px rgba(0,0,0,0.12);
    }}
    .filter-bar-title {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .1em;
      opacity: .4;
      align-self: center;
      padding-bottom: 2px;
      white-space: nowrap;
      margin-right: 4px;
      color: {text};
    }}
    .filter-item {{
      display: flex;
      flex-direction: column;
      gap: 5px;
    }}
    .filter-item > label {{
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .07em;
      opacity: .55;
      color: {text};
    }}
    .filter-select-wrap {{
      position: relative;
      display: inline-flex;
      align-items: center;
    }}
    .filter-select-wrap select {{
      appearance: none;
      -webkit-appearance: none;
      background: rgba(128,128,128,0.08);
      color: {text};
      border: 1px solid rgba(128,128,128,0.22);
      border-radius: 7px;
      padding: 7px 32px 7px 12px;
      font-size: 13px;
      cursor: pointer;
      min-width: 150px;
      outline: none;
      transition: border-color 0.15s, box-shadow 0.15s;
      font-family: inherit;
    }}
    .filter-select-wrap select:hover {{ border-color: rgba(128,128,128,0.45); }}
    .filter-select-wrap select:focus {{ border-color: {primary}; box-shadow: 0 0 0 2px {primary}33; }}
    .filter-select-wrap .sel-arrow {{
      position: absolute;
      right: 9px;
      pointer-events: none;
      opacity: .45;
      flex-shrink: 0;
      color: {text};
    }}
    .ms-wrap {{ position: relative; }}
    .ms-btn {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      background: rgba(128,128,128,0.08);
      color: {text};
      border: 1px solid rgba(128,128,128,0.22);
      border-radius: 7px;
      padding: 7px 10px 7px 12px;
      font-size: 13px;
      cursor: pointer;
      min-width: 150px;
      outline: none;
      transition: border-color 0.15s, box-shadow 0.15s;
      white-space: nowrap;
      font-family: inherit;
    }}
    .ms-btn:hover {{ border-color: rgba(128,128,128,0.45); }}
    .ms-btn.ms-open, .ms-btn:focus {{ border-color: {primary}; box-shadow: 0 0 0 2px {primary}33; }}
    .ms-count {{
      background: {primary};
      color: #fff;
      border-radius: 10px;
      padding: 1px 7px;
      font-size: 11px;
      font-weight: 600;
      display: none;
    }}
    .ms-count.visible {{ display: inline; }}
    .ms-arrow {{ opacity: .45; transition: transform 0.15s; flex-shrink: 0; }}
    .ms-btn.ms-open .ms-arrow {{ transform: rotate(180deg); }}
    .ms-panel {{
      position: absolute;
      top: calc(100% + 5px);
      left: 0;
      z-index: 200;
      background: {bg};
      border: 1px solid rgba(128,128,128,0.25);
      border-radius: 9px;
      padding: 6px;
      min-width: 190px;
      max-height: 230px;
      overflow-y: auto;
      box-shadow: 0 8px 28px rgba(0,0,0,0.3);
      display: none;
    }}
    .ms-panel.ms-open {{ display: block; }}
    .ms-option {{
      display: flex;
      align-items: center;
      gap: 9px;
      padding: 7px 9px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 13px;
      user-select: none;
      transition: background 0.1s;
      color: {text};
    }}
    .ms-option:hover {{ background: rgba(128,128,128,0.1); }}
    .ms-option input[type="checkbox"] {{
      accent-color: {primary};
      width: 14px;
      height: 14px;
      cursor: pointer;
      flex-shrink: 0;
    }}
    .filter-reset {{
      align-self: flex-end;
      background: none;
      border: 1px solid rgba(128,128,128,0.2);
      color: {text};
      padding: 7px 14px;
      border-radius: 7px;
      font-size: 12px;
      cursor: pointer;
      opacity: .55;
      transition: opacity 0.15s, border-color 0.15s;
      font-family: inherit;
    }}
    .filter-reset:hover {{ opacity: 1; border-color: rgba(128,128,128,0.5); }}
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
            color: theme.secondary ? bubbleData.map((_, i) => theme.secondary[i % theme.secondary.length]) : theme.primary,
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
          trace = {{ labels: xValues, values: yValues, type: 'pie', marker: {{ colors: theme.secondary }} }};
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
            display_style = '' if i == 0 else ' style="display:none"'
            description = page.get("description", "")

            container_parts = [f'    <div id="page-{page_id}" class="page-container"{display_style}>']

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
                    regular_parts.append(f'      <div class="card">')
                    regular_parts.append(f'        <div id="chart-{chart_id}"></div>')
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

      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ title: '{x}', type: '{x_scale_type}', color: theme.text, gridcolor: theme.text + '20' }},
        yaxis: {{ title: '{y}', type: '{y_scale_type}', color: theme.text, gridcolor: theme.text + '20' }},
        barmode: '{barmode}',
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};

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
          color: theme.secondary ? bubbleData.map((_, i) => theme.secondary[i % theme.secondary.length]) : theme.primary,
          sizemode: 'diameter'
        }},
        hovertemplate: bubbleData.map(d => d.group + '<br>{x}: ' + d.x + '<br>{y}: ' + d.y + '<br>{size_field or y}: ' + d.size + '<extra></extra>')
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

      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ title: '{x}', type: '{x_scale_type}', color: theme.text }},
        yaxis: {{ title: '{heatmap_y}', type: '{y_scale_type}', color: theme.text }},
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};{annotations_snippet}{ref_lines_snippet}

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
          trace = {{ x: xValues, y: yValues, type: 'scatter', mode: 'lines+markers', line: {{ color: theme.primary }} }};
          break;
        case 'scatter':
          trace = {{ x: xValues, y: yValues, type: 'scatter', mode: 'markers', marker: {{ color: theme.primary }} }};
          break;
        case 'pie':
          trace = {{ labels: xValues, values: yValues, type: 'pie', marker: {{ colors: theme.secondary }} }};
          break;
        case 'area':
          trace = {{ x: xValues, y: yValues, type: 'scatter', fill: 'tozeroy', mode: 'lines', line: {{ color: theme.primary }}, fillcolor: theme.primary + '40' }};
          break;
        case 'histogram':
          trace = {{ x: xValues, type: 'histogram', nbinsx: {bins}, marker: {{ color: theme.primary }} }};
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
              colorbar: {{ title: '{y}' }}
            }};
          }} else {{
            const normalizedX_{chart_id.replace('-', '_')} = xValues.map(v => normalizeCountryForPlotly(v, geoEnc_{chart_id.replace('-', '_')}));
            trace = {{
              type: 'choropleth',
              locations: normalizedX_{chart_id.replace('-', '_')},
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

        # Generate page show function
        page_show_function = f'''
    function showPage(pageId, clickedButton) {{
      document.querySelectorAll('.page-container').forEach(page => {{
        page.style.display = 'none';
      }});
      document.querySelectorAll('.tab-button').forEach(tab => {{
        tab.classList.remove('active');
      }});
      document.getElementById('page-' + pageId).style.display = 'block';
      if (clickedButton) {{
        clickedButton.classList.add('active');
      }}
    }}'''

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

        # Use the same full-featured aggregation functions as single-page mode
        return f'''  <script>
    const theme = {theme_json};
{geo_js_block}
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
        const headers = lines[0].split(',').map(h => h.trim());
        const data = lines.slice(1)
          .map(line => {{
            const values = line.split(',');
            if (values.length !== headers.length) return null;
            const row = {{}};
            headers.forEach((header, i) => {{
              const val = values[i] ? values[i].trim() : '';
              row[header] = (val !== '' && !isNaN(val)) ? parseFloat(val) : val;
            }});
            return row;
          }})
          .filter(row => row !== null);
{self._build_derived_js_code(derived_fields or [], var_name="data", indent="        ")}
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
        """Generate Flask backend that connects to SQL database"""
        db_config = spec["db_config"]
        db_type = db_config["type"]
        host = db_config["host"]
        port = db_config["port"]
        database = db_config["database"]
        user = db_config["user"]
        password = db_config["password"]

        # Use pre-parsed path components from normalizer
        schema = data_spec["sql_schema"]
        table_name = data_spec["sql_table"]

        # Build connection string based on database type
        if db_type == "postgresql":
            conn_str = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        elif db_type == "mysql":
            conn_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        elif db_type == "sqlite":
            conn_str = f"sqlite:///{database}"
        else:
            conn_str = f"{db_type}://{user}:{password}@{host}:{port}/{database}"

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
        return f'''from flask import Flask, jsonify, send_from_directory, Response
from sqlalchemy import create_engine
import pandas as pd

app = Flask(__name__)

# Database configuration
DATABASE_URL = "{conn_str}"
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
          color: theme.secondary ? data.map((_, i) => theme.secondary[i % theme.secondary.length]) : theme.primary,
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
          trace = {{ labels: xValues, values: yValues, type: 'pie', marker: {{ colors: theme.secondary }} }};
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