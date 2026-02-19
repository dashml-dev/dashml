"""
Plotly Transformer - Generates Plotly HTML/JavaScript from DashML specs
"""
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
            if chart_type in ["stacked_bar", "grouped_bar"]:
                self.warn(f"'{chart_type}' requires a grouping column - not yet fully supported")

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
        html_parts.append(self._generate_javascript_pages(data_spec, pages, colors))

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

        # Use pre-parsed path components from normalizer
        dataset = data_spec["bq_dataset"]
        table_name = data_spec["bq_table"]

        # Build credentials loading code
        if credentials_path:
            credentials_code = f'''
# Load credentials from service account file
from google.oauth2 import service_account
credentials = service_account.Credentials.from_service_account_file(
    "{credentials_path}",
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
'''
        else:
            credentials_code = '''
# Use default credentials (from gcloud auth or GOOGLE_APPLICATION_CREDENTIALS env var)
client = bigquery.Client(project=PROJECT_ID)
'''

        # Generate Flask app code
        return f'''from flask import Flask, jsonify, send_from_directory
from google.cloud import bigquery
import os

app = Flask(__name__)

# BigQuery configuration
PROJECT_ID = "{project}"
DATASET = "{dataset}"
TABLE_NAME = "{table_name}"
{credentials_code}

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

        # Map BigQuery types to simple types: date, number, string
        type_mapping = {{}}
        for row in results:
            col_name = row.column_name
            data_type = row.data_type.upper()

            # Date types
            if data_type in ('DATE', 'DATETIME', 'TIMESTAMP', 'TIME'):
                type_mapping[col_name] = 'date'
            # Numeric types
            elif data_type in ('INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC', 'INT', 'INTEGER',
                             'SMALLINT', 'BIGINT', 'FLOAT', 'DECIMAL', 'REAL', 'DOUBLE'):
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
    """Return column types from INFORMATION_SCHEMA"""
    try:
        column_types = get_column_types()
        return jsonify(column_types)
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

@app.route('/api/data')
def get_data():
    """Fetch data from BigQuery and return as JSON"""
    try:
        query = f"""
            SELECT *
            FROM `{{PROJECT_ID}}.{{DATASET}}.{{TABLE_NAME}}`
            LIMIT 10000
        """
        query_job = client.query(query)
        results = query_job.result()

        # Convert to list of dicts
        data = [dict(row) for row in results]

        # Handle date/datetime/Decimal serialization
        import json
        from datetime import date, datetime
        from decimal import Decimal

        def serialize(obj):
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f"Type {{type(obj)}} not serializable")

        return app.response_class(
            response=json.dumps(data, default=serialize),
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

if __name__ == '__main__':
    print("Starting Flask server with BigQuery backend...")
    print(f"Project: {{PROJECT_ID}}")
    print(f"Dataset: {{DATASET}}")
    print(f"Table: {{TABLE_NAME}}")
    print(f"Dashboard available at: http://localhost:5000")
    app.run(debug=True, port=5000)
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

        # Pass theme colors to JS for Plotly layout
        theme_json = json.dumps(colors)

        js_parts = []
        js_parts.append("  <script>")
        js_parts.append(f"    const theme = {theme_json};")
        js_parts.append("    // Chart definitions")
        js_parts.append(f"    const charts = {self._charts_to_json(charts)};")
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
      const chartsNeedAggregation = new Set(['bar', 'line', 'area', 'pie', 'stacked_bar', 'grouped_bar', 'scatter']);
      const chartsUseRawData = new Set(['histogram']);

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
            color: theme.secondary ? theme.secondary.slice(0, bubbleData.length) : theme.primary,
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
          trace = {{ x: heatmapX, y: heatmapY, z: heatmapZ, type: 'heatmap', colorscale: 'Blues' }};
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
          trace = {{
            type: 'choropleth',
            locations: xValues,
            z: yValues,
            locationmode: 'country names',
            colorscale: 'Blues',
            colorbar: {{ title: chart.y }}
          }};
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
              color: theme.text,
              gridcolor: theme.text + '20' // 20 = low opacity
          }},
          yaxis: {{
              title: chart.y,
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

            for chart in page.get("charts", []):
                chart_id = chart["id"]
                container_parts.append(f'      <div class="card">')
                container_parts.append(f'        <div id="chart-{chart_id}"></div>')
                container_parts.append(f'      </div>')

            container_parts.append('    </div>')
            containers.append("\n".join(container_parts))

        return "\n".join(containers)

    def _generate_javascript_pages(self, data_spec: Dict[str, Any], pages: list, colors: Dict[str, str]) -> str:
        """Generate JavaScript for multi-page dashboard"""
        data_path = data_spec["path"]
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
            x = chart["x"]
            y = chart["y"]
            agg = chart.get("agg", "sum")
            group = chart.get("group")
            title = chart.get("title", chart_id)
            x_type = chart.get("x_type")  # Optional: "date", "number", "string"
            y_type = chart.get("y_type")  # Optional: "number", "string"
            bins = chart.get("bins", 20)  # Number of bins for histogram
            filters = chart.get("filters", [])  # Optional: filter conditions
            sort_field = chart.get("sort")  # Optional: "x" or "y"
            sort_order = chart.get("sort_order", "asc")  # Optional: "asc" or "desc"
            limit = chart.get("limit")  # Optional: max rows after aggregation
            size_field = chart.get("size")  # Optional: size field for bubble charts

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

            # Check if this is stacked/grouped bar
            if chart_type in ["stacked_bar", "grouped_bar"]:
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
        xaxis: {{ title: '{x}', color: theme.text, gridcolor: theme.text + '20' }},
        yaxis: {{ title: '{y}', color: theme.text, gridcolor: theme.text + '20' }},
        barmode: '{barmode}',
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};

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
          color: theme.secondary ? theme.secondary.slice(0, bubbleData.length) : theme.primary,
          sizemode: 'diameter'
        }},
        hovertemplate: bubbleData.map(d => d.group + '<br>{x}: ' + d.x + '<br>{y}: ' + d.y + '<br>{size_field or y}: ' + d.size + '<extra></extra>')
      }};

      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ title: '{x}', color: theme.text, gridcolor: theme.text + '20' }},
        yaxis: {{ title: '{y}', color: theme.text, gridcolor: theme.text + '20' }},
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};

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

      const trace = {{ x: heatmapX, y: heatmapY, z: heatmapZ, type: 'heatmap', colorscale: 'Blues' }};

      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ title: '{x}', color: theme.text }},
        yaxis: {{ title: '{heatmap_y}', color: theme.text }},
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};

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
          trace = {{
            type: 'choropleth',
            locations: xValues,
            z: yValues,
            locationmode: 'country names',
            colorscale: 'Blues',
            colorbar: {{ title: '{y}' }}
          }};
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
          xaxis: {{ title: '{x}', color: theme.text, gridcolor: theme.text + '20' }},
          yaxis: {{ title: '{y}', color: theme.text, gridcolor: theme.text + '20' }},
          margin: {{ t: 60, r: 40, b: 60, l: 60 }},
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)'
        }};
      }}

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

        # Use the same full-featured aggregation functions as single-page mode
        return f'''  <script>
    const theme = {theme_json};

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
              row[header] = values[i] ? values[i].trim() : '';
            }});
            return row;
          }})
          .filter(row => row !== null);

        renderAllPages(data);
      }})
      .catch(error => console.error('Error loading data:', error));
  </script>'''

    def get_run_command(self, output_path: str) -> str:
        """Return command to serve Plotly HTML or Flask app"""
        from pathlib import Path
        output_path_obj = Path(output_path)

        # If output is a directory (multi-file), run Flask
        if output_path_obj.is_dir():
            return f"cd {output_path} && python app.py"

        # Otherwise run simple HTTP server for single HTML file
        output_dir = output_path_obj.parent.resolve()
        return f"cd {output_dir} && python -m http.server 8000"

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

        # Generate Flask app code
        return f'''from flask import Flask, jsonify, send_from_directory
from sqlalchemy import create_engine
import pandas as pd

app = Flask(__name__)

# Database configuration
DATABASE_URL = "{conn_str}"
SCHEMA = "{schema}"
TABLE_NAME = "{table_name}"

# Create database engine
engine = create_engine(DATABASE_URL)

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

@app.route('/api/data')
def get_data():
    """Fetch data from SQL database and return as JSON with proper type casting"""
    try:
        # Fetch data
        query = f"SELECT * FROM {{SCHEMA}}.{{TABLE_NAME}}"
        df = pd.read_sql(query, engine)

        # Get column types and cast accordingly
        column_types = get_column_types()
        for col_name, col_type in column_types.items():
            if col_name in df.columns:
                if col_type == 'date':
                    # Cast to datetime - pandas handles various date formats
                    df[col_name] = pd.to_datetime(df[col_name])
                elif col_type == 'number':
                    # Cast to numeric
                    df[col_name] = pd.to_numeric(df[col_name], errors='coerce')

        # Convert to JSON with ISO 8601 date format
        json_str = df.to_json(orient='records', date_format='iso')

        # Return pre-serialized JSON
        from flask import Response
        return Response(json_str, mimetype='application/json')
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

if __name__ == '__main__':
    print("Starting Flask server...")
    print(f"Dashboard available at: http://localhost:5000")
    app.run(debug=True, port=5000)
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
        """Generate JavaScript that fetches from Flask API instead of CSV"""
        theme_json = json.dumps(colors)

        js_parts = []
        js_parts.append("  <script>")
        js_parts.append(f"    const theme = {theme_json};")
        js_parts.append("    // Chart definitions")
        js_parts.append(f"    const charts = {self._charts_to_json(charts)};")
        js_parts.append("    // Column types from INFORMATION_SCHEMA (auto-detected)")
        js_parts.append("    let columnTypes = {};")
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

        // Parse ISO 8601 date strings to Date objects
        // Server already cast types, we just need to parse ISO dates
        window.dashmlData = data.map(row => {
          const parsedRow = {};
          for (const [column, value] of Object.entries(row)) {
            if (columnTypes[column] === 'date' && value !== null) {
              // Parse ISO 8601 date string (e.g., "2023-01-05T00:00:00.000Z")
              parsedRow[column] = new Date(value);
            } else {
              // Numbers are already parsed by JSON, strings stay as strings
              parsedRow[column] = value;
            }
          }
          return parsedRow;
        });

        console.log('Column types from INFORMATION_SCHEMA:', columnTypes);
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
        """Generate JavaScript for multi-page dashboard (SQL version)"""
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
            x = chart["x"]
            y = chart["y"]
            agg = chart.get("agg", "sum")
            group = chart.get("group")
            title = chart.get("title", chart_id)
            x_type = chart.get("x_type")  # Optional: "date", "number", "string"
            y_type = chart.get("y_type")  # Optional: "number", "string"
            bins = chart.get("bins", 20)  # Number of bins for histogram
            filters = chart.get("filters", [])  # Optional: filter conditions
            sort_field = chart.get("sort")  # Optional: "x" or "y"
            sort_order = chart.get("sort_order", "asc")  # Optional: "asc" or "desc"
            limit = chart.get("limit")  # Optional: max rows after aggregation
            size_field = chart.get("size")  # Optional: size field for bubble charts

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

            # Check if this is stacked/grouped bar
            if chart_type in ["stacked_bar", "grouped_bar"]:
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
        xaxis: {{ title: '{x}', color: theme.text, gridcolor: theme.text + '20' }},
        yaxis: {{ title: '{y}', color: theme.text, gridcolor: theme.text + '20' }},
        barmode: '{barmode}',
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};

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
          color: theme.secondary ? theme.secondary.slice(0, bubbleData.length) : theme.primary,
          sizemode: 'diameter'
        }},
        hovertemplate: bubbleData.map(d => d.group + '<br>{x}: ' + d.x + '<br>{y}: ' + d.y + '<br>{size_field or y}: ' + d.size + '<extra></extra>')
      }};

      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ title: '{x}', color: theme.text, gridcolor: theme.text + '20' }},
        yaxis: {{ title: '{y}', color: theme.text, gridcolor: theme.text + '20' }},
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};

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

      const trace = {{ x: heatmapX, y: heatmapY, z: heatmapZ, type: 'heatmap', colorscale: 'Blues' }};

      const layout = {{
        title: {{ text: '{title}', font: {{ color: theme.text }} }},
        xaxis: {{ title: '{x}', color: theme.text }},
        yaxis: {{ title: '{heatmap_y}', color: theme.text }},
        margin: {{ t: 60, r: 40, b: 60, l: 60 }},
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)'
      }};

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
      const xValues = filteredData.map(d => d['{x}'] || d.{x});
      const yValues = filteredData.map(d => d['{y}'] || d.{y});'''
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
          trace = {{
            type: 'choropleth',
            locations: xValues,
            z: yValues,
            locationmode: 'country names',
            colorscale: 'Blues',
            colorbar: {{ title: '{y}' }}
          }};
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
          xaxis: {{ title: '{x}', color: theme.text, gridcolor: theme.text + '20' }},
          yaxis: {{ title: '{y}', color: theme.text, gridcolor: theme.text + '20' }},
          margin: {{ t: 60, r: 40, b: 60, l: 60 }},
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)'
        }};
      }}

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

        # Use the same full-featured aggregation functions with schema support
        return f'''  <script>
    const theme = {theme_json};
    // Column types from INFORMATION_SCHEMA (auto-detected)
    let columnTypes = {{}};

    // Get effective x_type: explicit > schema-detected > undefined
    function getEffectiveXType(xColumn, explicitXType) {{
      if (explicitXType) return explicitXType;
      return columnTypes[xColumn] || undefined;
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
      const xType = options.xType || getEffectiveXType(x, options.xType);
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
      const xType = options.xType || getEffectiveXType(x, options.xType);
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

{''.join(chart_functions)}

{page_show_function}

{render_all}

    // Fetch schema first, then data
    Promise.all([
      fetch('/api/schema').then(r => r.json()),
      fetch('/api/data').then(r => r.json())
    ])
      .then(([schema, data]) => {{
        columnTypes = schema;

        // Parse ISO 8601 date strings to Date objects
        // Server already cast types, we just need to parse ISO dates
        const parsedData = data.map(row => {{
          const parsedRow = {{}};
          for (const [column, value] of Object.entries(row)) {{
            if (columnTypes[column] === 'date' && value !== null) {{
              // Parse ISO 8601 date string (e.g., "2023-01-05T00:00:00.000Z")
              parsedRow[column] = new Date(value);
            }} else {{
              // Numbers are already parsed by JSON, strings stay as strings
              parsedRow[column] = value;
            }}
          }}
          return parsedRow;
        }});

        console.log('Column types from INFORMATION_SCHEMA:', columnTypes);
        renderAllPages(parsedData);
      }})
      .catch(error => console.error('Error loading data:', error));
  </script>'''