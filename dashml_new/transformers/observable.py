"""
Observable Plot Transformer - Generates Observable Plot HTML from DashML specs
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
    TEMPORAL_FIELD_NAMES,
    DEFAULT_SORT_ORDER,
    resolve_metric_format,
)

if TYPE_CHECKING:
    from ..core.types import NormalizedSpec, ChartSpec


class ObservablePlotTransformer(Transformer):
    """
    Generates standalone Observable Plot HTML dashboards from DashML specifications.
    Output: Single HTML file for CSV, multi-file with Flask backend for SQL
    """

    @property
    def name(self) -> str:
        return "observable"

    @property
    def description(self) -> str:
        return "Generates Observable Plot HTML dashboards"

    def build(self, spec: "NormalizedSpec") -> str:
        """Generate Observable Plot HTML from NormalizedSpec."""
        try:
            self.clear_warnings()

            data_type = spec["data"].get("type", "csv")

            if data_type == "sql":
                return self._build_sql_version(spec)
            elif data_type == "bigquery":
                return self._build_bigquery_version(spec)
            else:
                return self._build_csv_version(spec)

        except KeyError as e:
            raise TransformerError(f"Missing required field in spec: {e}")
        except Exception as e:
            raise TransformerError(f"Failed to generate Observable Plot HTML: {e}")

    def _build_csv_version(self, spec: "NormalizedSpec") -> str:
        """Generate single HTML file for CSV datasources"""
        colors = spec["style"]

        if colors.get("buttons"):
            self.warn("'buttons' color is not currently used by Observable transformer")

        title = spec["title"]
        html_parts = []
        html_parts.append(self._generate_html_head(title, colors))
        html_parts.append(self._generate_body_start(title, colors))

        # Data loading
        data_spec = spec["data"]
        html_parts.append(self._generate_data_loader(data_spec))

        # Always use pages (normalizer guarantees pages[] exists)
        html_parts.append(self._generate_pages_structure(spec["pages"], colors))

        html_parts.append(self._generate_html_footer())

        return "\n".join(html_parts)

    def _build_bigquery_version(self, spec: "NormalizedSpec") -> str:
        """Generate multi-file output with Flask + BigQuery backend"""
        if not spec.get("db_config"):
            raise TransformerError("BigQuery configuration not provided")

        # Generate Flask backend with BigQuery
        data_spec = spec["data"]
        flask_app = self._generate_flask_app_bigquery(spec, data_spec)

        # Generate HTML frontend (fetches from Flask API - same as SQL version)
        html_frontend = self._generate_sql_frontend(spec)

        # Return multi-file JSON structure
        multi_file_output = {
            "type": "multi-file",
            "files": {
                "app.py": flask_app,
                "index.html": html_frontend
            }
        }

        return json.dumps(multi_file_output)

    def _sql_value(self, value) -> str:
        """Convert a Python value to a SQL literal"""
        if isinstance(value, str):
            return "'" + value.replace("'", "''") + "'"
        if isinstance(value, (list, tuple)):
            return "(" + ", ".join(self._sql_value(v) for v in value) + ")"
        if value is None:
            return "NULL"
        return str(value)

    def _build_where_clause(self, filters: list) -> str:
        """Convert DashML filter specs to a SQL WHERE clause"""
        if not filters:
            return ""
        op_map = {
            "eq": "=", "ne": "!=", "gt": ">", "lt": "<",
            "gte": ">=", "lte": "<=",
        }
        parts = []
        for f in filters:
            field = f["field"]
            op = f["op"]
            val = f["value"]
            if op in op_map:
                parts.append(f"{field} {op_map[op]} {self._sql_value(val)}")
            elif op == "in":
                parts.append(f"{field} IN {self._sql_value(val)}")
            elif op == "contains":
                parts.append(f"{field} LIKE '%{val}%'")
        return " WHERE " + " AND ".join(parts) if parts else ""

    def _build_chart_query(self, chart: Dict[str, Any], table_ref: str) -> str:
        """Build a per-chart SQL query that does server-side aggregation."""
        chart_type = chart["type"]
        x = chart.get("x", "")  # Not required for metric type
        y = chart["y"]
        agg = chart.get("agg", "sum")
        group = chart.get("group")
        size_field = chart.get("size")
        filters = chart.get("filters", [])
        sort_field = chart.get("sort")
        sort_order = chart.get("sort_order", "asc")
        limit = chart.get("limit")

        where = self._build_where_clause(filters)
        agg_map = {"sum": "SUM", "mean": "AVG", "count": "COUNT"}
        sql_agg = agg_map.get(agg, "SUM")

        order = ""
        if sort_field == "y":
            order = f" ORDER BY y {'ASC' if sort_order == 'asc' else 'DESC'}"
        elif sort_field == "x":
            order = f" ORDER BY x {'ASC' if sort_order == 'asc' else 'DESC'}"

        limit_clause = f" LIMIT {limit}" if limit else ""

        # Default ORDER BY x for charts that need sequential ordering
        if not order and chart_type in ("line", "area"):
            order = " ORDER BY x ASC"

        if chart_type in ("bar", "line", "area", "pie", "geo"):
            return f"SELECT {x} AS x, {sql_agg}({y}) AS y FROM {table_ref}{where} GROUP BY {x}{order}{limit_clause}"
        elif chart_type in ("stacked_bar", "grouped_bar"):
            return f"SELECT {x} AS x, {group} AS grp, {sql_agg}({y}) AS y FROM {table_ref}{where} GROUP BY {x}, {group}{order}{limit_clause}"
        elif chart_type == "heatmap":
            heatmap_y = group if group else y
            hm_where = where if where else " WHERE 1=1"
            hm_where += f" AND {x} IN (SELECT {x} FROM {table_ref} GROUP BY {x} ORDER BY COUNT(*) DESC LIMIT 20)"
            hm_where += f" AND {heatmap_y} IN (SELECT {heatmap_y} FROM {table_ref} GROUP BY {heatmap_y} ORDER BY COUNT(*) DESC LIMIT 20)"
            return f"SELECT {x} AS x, {heatmap_y} AS heatmap_y, {sql_agg}({y}) AS y FROM {table_ref}{hm_where} GROUP BY {x}, {heatmap_y}{order}{limit_clause}"
        elif chart_type == "scatter":
            null_filter = f"{x} IS NOT NULL AND {y} IS NOT NULL"
            sc_where = (where + " AND " + null_filter) if where else (" WHERE " + null_filter)
            return f"SELECT {x} AS x, {y} AS y FROM {table_ref}{sc_where} ORDER BY RAND() LIMIT 5000"
        elif chart_type == "bubble":
            size_ref = size_field or y
            return f"SELECT {group} AS grp, {sql_agg}({x}) AS x, {sql_agg}({y}) AS y, {sql_agg}({size_ref}) AS size FROM {table_ref}{where} GROUP BY {group}{order}{limit_clause}"
        elif chart_type == "histogram":
            null_filter = f"{x} IS NOT NULL"
            hist_where = (where + " AND " + null_filter) if where else (" WHERE " + null_filter)
            return f"SELECT {x} AS x FROM {table_ref}{hist_where} ORDER BY RAND() LIMIT 50000"
        elif chart_type == "box":
            box_where = where if where else ""
            top_n = f"{x} IN (SELECT {x} FROM {table_ref} GROUP BY {x} ORDER BY COUNT(*) DESC LIMIT 20)"
            null_filter = f"{x} IS NOT NULL AND {y} IS NOT NULL"
            box_where = (box_where + " AND " + top_n + " AND " + null_filter) if box_where else (" WHERE " + top_n + " AND " + null_filter)
            return f"SELECT {x} AS x, {y} AS y FROM {table_ref}{box_where} ORDER BY RAND() LIMIT 50000"
        elif chart_type == "metric":
            return f"SELECT {sql_agg}({y}) AS y FROM {table_ref}{where}"
        else:
            return f"SELECT {x} AS x, {sql_agg}({y}) AS y FROM {table_ref}{where} GROUP BY {x}{order}{limit_clause}"

    def _build_sql_version(self, spec: "NormalizedSpec") -> str:
        """Generate multi-file output with Flask backend for SQL datasources"""

        if not spec.get("db_config"):
            raise TransformerError("Database configuration not provided for SQL datasource")

        # Generate Flask backend
        data_spec = spec["data"]
        flask_app = self._generate_flask_app(spec, data_spec)

        # Generate HTML frontend (fetches from Flask API instead of CSV)
        html_frontend = self._generate_sql_frontend(spec)

        # Return multi-file JSON structure
        multi_file_output = {
            "type": "multi-file",
            "files": {
                "app.py": flask_app,
                "index.html": html_frontend
            }
        }

        return json.dumps(multi_file_output)

    def _generate_html_head(self, title: str, colors: Dict[str, str]) -> str:
        bg_color = colors.get("background", "#ffffff")
        card_color = colors.get("card", bg_color)
        text_color = colors.get("text", "#000000")
        primary_color = colors.get("primary", DEFAULT_PRIMARY_COLOR)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
    <script src="https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6"></script>
    <script src="https://cdn.jsdelivr.net/npm/topojson-client@3"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, sans-serif;
            background-color: {bg_color};
            color: {text_color};
            padding: 2rem;
            line-height: 1.6;
        }}

        h1 {{
            font-size: 2.5rem;
            margin-bottom: 2rem;
            font-weight: 600;
        }}

        h2 {{
            font-size: 1.5rem;
            margin-top: 2rem;
            margin-bottom: 1rem;
            font-weight: 500;
        }}

        .card {{
            margin-bottom: 3rem;
            background: {card_color};
            padding: 1.5rem;
            border-radius: 8px;
        }}

        .page-tabs {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 2rem;
            border-bottom: 2px solid rgba(128, 128, 128, 0.2);
            padding-bottom: 0;
        }}

        .tab-button {{
            background: none;
            border: none;
            color: {text_color};
            padding: 0.75rem 1.5rem;
            cursor: pointer;
            font-size: 1rem;
            border-bottom: 3px solid transparent;
            transition: all 0.2s;
            opacity: 0.6;
        }}

        .tab-button:hover {{
            opacity: 0.8;
        }}

        .tab-button.active {{
            opacity: 1;
            border-bottom-color: {primary_color};
        }}

        .page-content {{
            display: none;
        }}

        .page-content.active {{
            display: block;
        }}

        .page-description {{
            font-style: italic;
            opacity: 0.8;
            margin-bottom: 1.5rem;
        }}

        /* Observable Plot chart styling */
        svg {{
            background: transparent;
        }}

        .chart-spinner {{
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; min-height: 300px; gap: 12px;
            color: {text_color}; opacity: 0.6;
        }}
        .chart-spinner .spinner {{
            width: 40px; height: 40px;
            border: 3px solid {text_color}20;
            border-top-color: {primary_color};
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
            color: {text_color};
            opacity: 0.65;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.07em;
        }}
        .metric-value {{
            font-size: 2.6rem;
            font-weight: 700;
            color: {primary_color};
            line-height: 1.1;
        }}
    </style>
</head>"""

    def _generate_body_start(self, title: str, colors: Dict[str, str]) -> str:
        return f"""<body>
    <h1>{title}</h1>"""

    def _generate_html_footer(self) -> str:
        return """</body>
</html>"""

    def _generate_data_loader(self, data_spec: Dict[str, Any]) -> str:
        """Generate JavaScript to load CSV data"""
        data_type = data_spec["type"]
        path = data_spec["path"]

        if data_type == "csv":
            return f"""
    <script>
        // Load and parse CSV data
        let dashmlData = [];
        // World topojson for geo charts (loaded on demand)
        window.worldTopojson = null;

        // For CSV, getEffectiveType returns explicit type or detects from data
        function getEffectiveType(column, explicitType) {{
            if (explicitType) return explicitType;
            // For CSV, we don't have schema info, so return undefined
            // The sorting logic will handle runtime type detection
            return undefined;
        }}

        // Load both data and world topojson in parallel
        Promise.all([
            fetch('{path}').then(r => r.text()),
            fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json').then(r => r.json())
        ])
            .then(([csvText, worldData]) => {{
                dashmlData = parseCSV(csvText);
                // Convert topojson to geojson features for Observable Plot
                window.worldTopojson = topojson.feature(worldData, worldData.objects.countries);
                renderAllCharts();
            }})
            .catch(error => {{
                console.error('Error loading data:', error);
                document.body.innerHTML += '<p style="color: red;">Error loading data: ' + error.message + '</p>';
            }});

        function parseCSV(csvText) {{
            const lines = csvText.trim().split('\\n').filter(line => line.trim());
            const headers = lines[0].split(',').map(h => h.trim());
            const rows = [];

            for (let i = 1; i < lines.length; i++) {{
                const values = lines[i].split(',');
                if (values.length !== headers.length) continue;

                const row = {{}};
                headers.forEach((header, index) => {{
                    const value = values[index] ? values[index].trim() : '';
                    // Try to parse as number first
                    if (!isNaN(value) && value !== '') {{
                        row[header] = parseFloat(value);
                    }}
                    // Keep dates as ISO strings and other strings as-is
                    // Observable Plot handles ISO date strings natively with type: "utc"
                    else {{
                        row[header] = value;
                    }}
                }});
                rows.push(row);
            }}
            return rows;
        }}

        // Apply filter conditions to a dataset
        function applyFilters(data, filters) {{
            if (!filters || filters.length === 0) return data;
            return data.filter(row => filters.every(f => {{
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
            }}));
        }}

        // Format a metric scalar value
        function formatMetric(value, format, suffix) {{
            if (value === null || value === undefined || isNaN(value)) return 'N/A';
            const n = parseFloat(value);
            let str;
            if (format === ',.0f') str = n.toLocaleString('en-US', {{maximumFractionDigits: 0}});
            else if (format === ',.1f') str = n.toLocaleString('en-US', {{minimumFractionDigits: 1, maximumFractionDigits: 1}});
            else if (format === ',.2f') str = n.toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
            else if (format === '.0f') str = n.toFixed(0);
            else if (format === '.1f') str = n.toFixed(1);
            else if (format === '.2f') str = n.toFixed(2);
            else str = n.toLocaleString('en-US');
            return str + (suffix || '');
        }}
    </script>"""

        return f"""
    <script>
        console.error('Unsupported data type: {data_type}');
    </script>"""

    def _generate_charts_structure(self, charts: list, colors: Dict[str, str]) -> str:
        """Generate single-page charts structure"""
        chart_containers = []

        for chart in charts:
            chart_id = chart["id"]
            title = chart.get("title", chart_id)
            if chart.get("type") == "metric":
                chart_containers.append(f"""
    <div class="card metric-card">
        <div class="metric-title">{title}</div>
        <div id="chart-{chart_id}" class="metric-value">—</div>
    </div>""")
            else:
                chart_containers.append(f"""
    <div class="card">
        <h2>{title}</h2>
        <div id="chart-{chart_id}"></div>
    </div>""")

        # Generate render script
        render_functions = []
        for chart in charts:
            render_functions.append(self._generate_chart_render(chart, colors))

        script = f"""
    <script>
        function renderAllCharts() {{
{chr(10).join(render_functions)}
        }}
    </script>"""

        return "\n".join(chart_containers) + script

    def _generate_pages_structure(self, pages: list, colors: Dict[str, str]) -> str:
        """Generate multi-page structure with tabs"""
        tabs = []
        page_contents = []
        render_functions = []

        for i, page in enumerate(pages):
            page_id = page["id"]
            title = page.get("title", page_id)
            description = page.get("description", "")
            charts = page.get("charts", [])

            # Tab button
            active_class = " active" if i == 0 else ""
            tabs.append(f'        <button class="tab-button{active_class}" onclick="showPage(\'{page_id}\', this)">{title}</button>')

            # Page content
            page_html = [f'    <div id="page-{page_id}" class="page-content{active_class}">']
            if description:
                page_html.append(f'        <p class="page-description">{description}</p>')

            for chart in charts:
                chart_id = chart["id"]
                chart_title = chart.get("title", chart_id)
                if chart.get("type") == "metric":
                    page_html.append(f"""        <div class="card metric-card">
            <div class="metric-title">{chart_title}</div>
            <div id="chart-{page_id}-{chart_id}" class="metric-value">—</div>
        </div>""")
                else:
                    page_html.append(f"""        <div class="card">
            <h2>{chart_title}</h2>
            <div id="chart-{page_id}-{chart_id}"></div>
        </div>""")

                # Generate render function for this chart
                render_functions.append(self._generate_chart_render(chart, colors, page_id))

            page_html.append('    </div>')
            page_contents.append("\n".join(page_html))

        # Combine everything
        tabs_html = f"""    <div class="page-tabs">
{chr(10).join(tabs)}
    </div>"""

        script = f"""
    <script>
        function showPage(pageId, buttonElement) {{
            // Hide all pages
            document.querySelectorAll('.page-content').forEach(page => {{
                page.classList.remove('active');
            }});

            // Remove active from all buttons
            document.querySelectorAll('.tab-button').forEach(btn => {{
                btn.classList.remove('active');
            }});

            // Show selected page
            document.getElementById('page-' + pageId).classList.add('active');
            buttonElement.classList.add('active');
        }}

        function renderAllCharts() {{
{chr(10).join(render_functions)}
        }}
    </script>"""

        return tabs_html + "\n" + "\n".join(page_contents) + script

    def _generate_chart_render(self, chart: Dict[str, Any], colors: Dict[str, str], page_id: str = None) -> str:
        """Generate Observable Plot rendering code for a single chart"""
        chart_id = chart["id"]
        chart_type = chart["type"]
        x = chart.get("x", "")  # Not required for metric type
        y = chart["y"]
        agg = chart.get("agg", "sum")
        group = chart.get("group")  # Optional grouping field for stacked/grouped bars
        x_type = chart.get("x_type")  # Optional: "date", "number", "string" for sorting
        y_type = chart.get("y_type")  # Optional: "number", "string" for casting
        bins = chart.get("bins", DEFAULT_HISTOGRAM_BINS)
        filters = chart.get("filters", [])  # Optional: filter conditions
        sort_field = chart.get("sort")  # Optional: "x" or "y"
        sort_order = chart.get("sort_order", DEFAULT_SORT_ORDER)
        limit = chart.get("limit")  # Optional: max rows after aggregation
        size_field = chart.get("size")  # Optional: size field for bubble charts

        primary_color = colors.get("primary", DEFAULT_PRIMARY_COLOR)
        secondary_colors = colors.get("secondary", DEFAULT_SECONDARY_COLORS)
        format_str = resolve_metric_format(chart.get("format", "integer"))  # metric: number format
        suffix = chart.get("suffix", "")          # metric: unit text

        # Determine container ID
        container_id = f"chart-{page_id}-{chart_id}" if page_id else f"chart-{chart_id}"

        # Safe variable name
        safe_var_name = chart_id.replace('-', '_')

        # Metric type: render as KPI card with inline JS aggregation
        if chart_type == "metric":
            filters_js = json.dumps(filters)
            agg_method_js = agg  # 'sum', 'mean', 'count'
            return f"""            // Metric: {chart_id}
            {{
              const filters = {filters_js};
              let d = applyFilters(dashmlData, filters);
              const vals = d.map(r => parseFloat(r['{y}'])).filter(v => !isNaN(v));
              const value = vals.length === 0 ? null :
                '{agg_method_js}' === 'sum' ? vals.reduce((a, b) => a + b, 0) :
                '{agg_method_js}' === 'mean' ? vals.reduce((a, b) => a + b, 0) / vals.length :
                vals.length;
              document.getElementById('{container_id}').textContent = formatMetric(value, '{format_str}', '{suffix}');
            }}"""

        # Generate data code based on chart type requirements
        if chart_type in CHARTS_USE_RAW_DATA:
            # Use raw data for histogram - apply filters only
            if filters:
                filter_conditions = []
                for f in filters:
                    field = f["field"]
                    op = f["op"]
                    value = json.dumps(f["value"])
                    if op == "eq":
                        filter_conditions.append(f"d['{field}'] === {value}")
                    elif op == "ne":
                        filter_conditions.append(f"d['{field}'] !== {value}")
                    elif op == "gt":
                        filter_conditions.append(f"d['{field}'] > {value}")
                    elif op == "lt":
                        filter_conditions.append(f"d['{field}'] < {value}")
                    elif op == "gte":
                        filter_conditions.append(f"d['{field}'] >= {value}")
                    elif op == "lte":
                        filter_conditions.append(f"d['{field}'] <= {value}")
                    elif op == "in":
                        filter_conditions.append(f"{value}.includes(d['{field}'])")
                    elif op == "contains":
                        filter_conditions.append(f"String(d['{field}']).includes({value})")
                filter_code = " && ".join(filter_conditions)
                data_code = f"dashmlData.filter(d => {filter_code})"
            else:
                data_code = "dashmlData"
        elif chart_type in ["stacked_bar", "grouped_bar", "heatmap"] and group:
            # For stacked/grouped bars and heatmap, need to group by both x and group field
            data_code = self._get_aggregation_code_with_group(x, y, group, agg, x_type,
                                                               y_type, filters, sort_field, sort_order, limit)
        elif chart_type == "bubble" and group:
            # Bubble chart: 4D visualization - group by group field, aggregate x/y/size independently
            data_code = self._get_bubble_aggregation_code(group, x, y, size_field or y, agg,
                                                           filters, sort_field, sort_order, limit)
        else:
            # Aggregate data for other chart types
            data_code = self._get_aggregation_code(x, y, agg, x_type,
                                                    y_type, filters, sort_field, sort_order, limit,
                                                    size_field=size_field)

        # Pie charts use D3 directly instead of Observable Plot
        if chart_type == "pie":
            return self._generate_d3_pie_chart(safe_var_name, x, y, data_code, container_id, colors)

        # Generate Observable Plot mark based on chart type
        mark_code = self._get_plot_mark(chart_type, x, y, group, primary_color, secondary_colors, safe_var_name, bins, size_field=size_field)

        # Determine if x axis is temporal - prefer explicit x_type, fall back to field name heuristics
        # TODO: [Magic Values] Extract temporal field names to module-level constant
        # Fix: TEMPORAL_FIELD_NAMES = frozenset(['date', 'time', 'timestamp', 'datetime', 'created_at', 'updated_at'])
        temporal_fields = ['date', 'time', 'timestamp', 'datetime', 'created_at', 'updated_at']
        is_temporal_x = x_type == "date" or (x_type is None and x.lower() in temporal_fields)

        scale_config = ""
        if is_temporal_x:
            scale_config = f"""x: {{ type: "utc" }},
                """

        # Determine if chart has categorical x-axis (needs more bottom margin for rotated labels)
        categorical_types = {"bar", "grouped_bar", "stacked_bar", "heatmap"}
        margin_bottom = 100 if chart_type in categorical_types else 40

        return f"""            // Chart: {chart_id}
            const data_{safe_var_name} = {data_code};
            const plot_{safe_var_name} = Plot.plot({{
                {mark_code},
                {scale_config}marginLeft: 60,
                marginBottom: {margin_bottom},
                grid: true,
                style: {{
                    background: "transparent",
                    color: "{colors.get('text', '#000000')}"
                }}
            }});
            document.getElementById('{container_id}').appendChild(plot_{safe_var_name});"""

    def _generate_d3_pie_chart(self, var_name: str, x: str, y: str, data_code: str, container_id: str, colors: Dict[str, str]) -> str:
        """Generate D3 pie chart code"""
        text_color = colors.get('text', '#000000')
        secondary_colors = colors.get('secondary', DEFAULT_SECONDARY_COLORS)
        return f"""            // D3 Pie Chart
            const data_{var_name} = {data_code};
            const pieWidth = 400;
            const pieHeight = 400;
            const legendWidth = 150;
            const totalWidth = pieWidth + legendWidth;
            const radius = Math.min(pieWidth, pieHeight) / 2 - 10;

            const pie = d3.pie().value(d => d.{y});
            const arc = d3.arc().innerRadius(0).outerRadius(radius);

            // Use theme secondary colors for categorical data
            const themeColors = {secondary_colors};
            const color = d3.scaleOrdinal()
                .domain(data_{var_name}.map(d => d.{x}))
                .range(themeColors);

            const svg = d3.create("svg")
                .attr("width", totalWidth)
                .attr("height", pieHeight)
                .attr("viewBox", [0, 0, totalWidth, pieHeight])
                .attr("style", "max-width: 100%; height: auto;");

            // Pie chart group (centered in left portion)
            const pieGroup = svg.append("g")
                .attr("transform", `translate(${{pieWidth / 2}}, ${{pieHeight / 2}})`);

            pieGroup.selectAll("path")
                .data(pie(data_{var_name}))
                .join("path")
                .attr("fill", d => color(d.data.{x}))
                .attr("d", arc)
                .attr("stroke", "white")
                .attr("stroke-width", 2)
                .append("title")
                .text(d => `${{d.data.{x}}}: ${{d.data.{y}}}`);

            // Legend (positioned on the right)
            const legend = svg.append("g")
                .attr("transform", `translate(${{pieWidth + 10}}, 20)`);

            data_{var_name}.forEach((d, i) => {{
                const legendRow = legend.append("g")
                    .attr("transform", `translate(0, ${{i * 25}})`);

                legendRow.append("rect")
                    .attr("width", 15)
                    .attr("height", 15)
                    .attr("fill", color(d.{x}))
                    .attr("rx", 2);

                legendRow.append("text")
                    .attr("x", 22)
                    .attr("y", 12)
                    .attr("fill", "{text_color}")
                    .style("font-size", "13px")
                    .text(d.{x});
            }});

            document.getElementById('{container_id}').appendChild(svg.node());"""

    def _get_aggregation_code(self, x: str, y: str, agg: str, x_type: str = None,
                               y_type: str = None, filters: List = None,
                               sort_field: str = None, sort_order: str = "asc",
                               limit: int = None, size_field: str = None) -> str:
        """Generate JavaScript code to aggregate data with filtering, sorting, and limiting"""
        if agg == "sum":
            agg_expr = f"d3.sum(v, d => d['{y}'])"
        elif agg == "mean":
            agg_expr = f"d3.mean(v, d => d['{y}'])"
        elif agg == "count":
            agg_expr = "v.length"
        else:
            agg_expr = f"d3.sum(v, d => d['{y}'])"

        # Generate sorting based on x_type (explicit or schema-detected via getEffectiveType)
        x_type_js = f"'{x_type}'" if x_type else "undefined"

        # Generate filter conditions
        filter_conditions = []
        if filters:
            for f in filters:
                field = f["field"]
                op = f["op"]
                value = json.dumps(f["value"])
                if op == "eq":
                    filter_conditions.append(f"d['{field}'] === {value}")
                elif op == "ne":
                    filter_conditions.append(f"d['{field}'] !== {value}")
                elif op == "gt":
                    filter_conditions.append(f"d['{field}'] > {value}")
                elif op == "lt":
                    filter_conditions.append(f"d['{field}'] < {value}")
                elif op == "gte":
                    filter_conditions.append(f"d['{field}'] >= {value}")
                elif op == "lte":
                    filter_conditions.append(f"d['{field}'] <= {value}")
                elif op == "in":
                    filter_conditions.append(f"{value}.includes(d['{field}'])")
                elif op == "contains":
                    filter_conditions.append(f"String(d['{field}']).includes({value})")

        filter_code = " && ".join(filter_conditions) if filter_conditions else "true"

        # y_type casting
        y_cast = ""
        if y_type == "number":
            y_cast = f"d['{y}'] = parseFloat(d['{y}']) || 0;"
        elif y_type == "string":
            y_cast = f"d['{y}'] = String(d['{y}']);"

        # Sort logic
        sort_ascending = sort_order == "asc"
        if sort_field == "y":
            sort_code = f"result.sort((a, b) => {'1' if sort_ascending else '-1'} * (a.{y} - b.{y}));"
        elif sort_field == "x":
            sort_code = f"""
                if (effectiveXType === 'date') {{
                    result.sort((a, b) => {'1' if sort_ascending else '-1'} * (new Date(a.{x}) - new Date(b.{x})));
                }} else if (effectiveXType === 'number') {{
                    result.sort((a, b) => {'1' if sort_ascending else '-1'} * (a.{x} - b.{x}));
                }} else {{
                    result.sort((a, b) => {'1' if sort_ascending else '-1'} * String(a.{x}).localeCompare(String(b.{x})));
                }}"""
        else:
            # Default: sort by x - date/number by value, strings alphabetically
            sort_code = f"""
                if (effectiveXType === 'date') {{
                    result.sort((a, b) => new Date(a.{x}) - new Date(b.{x}));
                }} else if (effectiveXType === 'number') {{
                    result.sort((a, b) => a.{x} - b.{x});
                }} else if (result.length > 0) {{
                    const firstVal = result[0].{x};
                    if (firstVal instanceof Date) {{
                        result.sort((a, b) => a.{x} - b.{x});
                    }} else if (typeof firstVal === 'number') {{
                        result.sort((a, b) => a.{x} - b.{x});
                    }} else {{
                        // Sort strings alphabetically for consistency across transformers
                        result.sort((a, b) => String(a.{x}).localeCompare(String(b.{x})));
                    }}
                }}"""

        # Limit code
        limit_code = f"result = result.slice(0, {limit});" if limit else ""

        # Generate size aggregation for bubble charts
        if size_field and size_field != y:
            if agg == "sum":
                size_agg_expr = f"d3.sum(v, d => d['{size_field}'])"
            elif agg == "mean":
                size_agg_expr = f"d3.mean(v, d => d['{size_field}'])"
            elif agg == "count":
                size_agg_expr = "v.length"
            else:
                size_agg_expr = f"d3.sum(v, d => d['{size_field}'])"

            return f"""(() => {{
                const effectiveXType = getEffectiveType('{x}', {x_type_js});

                // Filter data
                let filteredData = dashmlData.filter(d => {filter_code});

                // Cast y values if y_type specified
                {"filteredData = filteredData.map(d => { const newD = {...d}; " + y_cast + " return newD; });" if y_cast else ""}

                let result = d3.rollups(
                    filteredData,
                    v => ({{ {y}: {agg_expr}, {size_field}: {size_agg_expr} }}),
                    d => d['{x}']
                ).map(([{x}, vals]) => ({{ {x}, {y}: vals.{y}, {size_field}: vals.{size_field} }}));

                // Sort
                {sort_code}

                // Limit
                {limit_code}

                return result;
            }})()"""

        return f"""(() => {{
                const effectiveXType = getEffectiveType('{x}', {x_type_js});

                // Filter data
                let filteredData = dashmlData.filter(d => {filter_code});

                // Cast y values if y_type specified
                {"filteredData = filteredData.map(d => { const newD = {...d}; " + y_cast + " return newD; });" if y_cast else ""}

                let result = d3.rollups(
                    filteredData,
                    v => {agg_expr},
                    d => d['{x}']
                ).map(([{x}, {y}]) => ({{ {x}, {y} }}));

                // Sort
                {sort_code}

                // Limit
                {limit_code}

                return result;
            }})()"""

    def _get_aggregation_code_with_group(self, x: str, y: str, group: str, agg: str, x_type: str = None,
                                          y_type: str = None, filters: List = None,
                                          sort_field: str = None, sort_order: str = "asc",
                                          limit: int = None) -> str:
        """Generate JavaScript code to aggregate data with grouping, filtering, sorting, and limiting"""
        if agg == "sum":
            agg_expr = f"d3.sum(v, d => d['{y}'])"
        elif agg == "mean":
            agg_expr = f"d3.mean(v, d => d['{y}'])"
        elif agg == "count":
            agg_expr = "v.length"
        else:
            agg_expr = f"d3.sum(v, d => d['{y}'])"

        # Generate sorting based on x_type (explicit or schema-detected via getEffectiveType)
        x_type_js = f"'{x_type}'" if x_type else "undefined"

        # Generate filter conditions
        filter_conditions = []
        if filters:
            for f in filters:
                field = f["field"]
                op = f["op"]
                value = json.dumps(f["value"])
                if op == "eq":
                    filter_conditions.append(f"d['{field}'] === {value}")
                elif op == "ne":
                    filter_conditions.append(f"d['{field}'] !== {value}")
                elif op == "gt":
                    filter_conditions.append(f"d['{field}'] > {value}")
                elif op == "lt":
                    filter_conditions.append(f"d['{field}'] < {value}")
                elif op == "gte":
                    filter_conditions.append(f"d['{field}'] >= {value}")
                elif op == "lte":
                    filter_conditions.append(f"d['{field}'] <= {value}")
                elif op == "in":
                    filter_conditions.append(f"{value}.includes(d['{field}'])")
                elif op == "contains":
                    filter_conditions.append(f"String(d['{field}']).includes({value})")

        filter_code = " && ".join(filter_conditions) if filter_conditions else "true"

        # y_type casting
        y_cast = ""
        if y_type == "number":
            y_cast = f"d['{y}'] = parseFloat(d['{y}']) || 0;"
        elif y_type == "string":
            y_cast = f"d['{y}'] = String(d['{y}']);"

        # Sort logic
        sort_ascending = sort_order == "asc"
        if sort_field == "y":
            sort_code = f"result.sort((a, b) => {'1' if sort_ascending else '-1'} * (a.{y} - b.{y}));"
        elif sort_field == "x":
            sort_code = f"""
                if (effectiveXType === 'date') {{
                    result.sort((a, b) => {'1' if sort_ascending else '-1'} * (new Date(a.{x}) - new Date(b.{x})));
                }} else if (effectiveXType === 'number') {{
                    result.sort((a, b) => {'1' if sort_ascending else '-1'} * (a.{x} - b.{x}));
                }} else {{
                    result.sort((a, b) => {'1' if sort_ascending else '-1'} * String(a.{x}).localeCompare(String(b.{x})));
                }}"""
        else:
            # Default: sort by x - date/number by value, strings alphabetically
            sort_code = f"""
                if (effectiveXType === 'date') {{
                    result.sort((a, b) => new Date(a.{x}) - new Date(b.{x}));
                }} else if (effectiveXType === 'number') {{
                    result.sort((a, b) => a.{x} - b.{x});
                }} else if (result.length > 0) {{
                    const firstVal = result[0].{x};
                    if (firstVal instanceof Date) {{
                        result.sort((a, b) => a.{x} - b.{x});
                    }} else if (typeof firstVal === 'number') {{
                        result.sort((a, b) => a.{x} - b.{x});
                    }} else {{
                        // Sort strings alphabetically for consistency across transformers
                        result.sort((a, b) => String(a.{x}).localeCompare(String(b.{x})));
                    }}
                }}"""

        # Limit code
        limit_code = f"result = result.slice(0, {limit});" if limit else ""

        return f"""(() => {{
                const effectiveXType = getEffectiveType('{x}', {x_type_js});

                // Filter data
                let filteredData = dashmlData.filter(d => {filter_code});

                // Cast y values if y_type specified
                {"filteredData = filteredData.map(d => { const newD = {...d}; " + y_cast + " return newD; });" if y_cast else ""}

                let result = d3.rollups(
                    filteredData,
                    v => {agg_expr},
                    d => d['{x}'],
                    d => d['{group}']
                ).flatMap(([{x}Val, groupData]) =>
                    groupData.map(([{group}Val, {y}Val]) => ({{
                        {x}: {x}Val,
                        {group}: {group}Val,
                        {y}: {y}Val
                    }}))
                );

                // Sort
                {sort_code}

                // Limit
                {limit_code}

                return result;
            }})()"""

    def _get_bubble_aggregation_code(self, group: str, x: str, y: str, size_field: str, agg: str,
                                       filters: list = None, sort_field: str = None,
                                       sort_order: str = "asc", limit: int = None) -> str:
        """Generate JavaScript code to aggregate data for bubble charts: group by group field, aggregate x/y/size independently"""
        def agg_expr(field):
            if agg == "sum":
                return f"d3.sum(v, d => d['{field}'])"
            elif agg == "mean":
                return f"d3.mean(v, d => d['{field}'])"
            elif agg == "count":
                return "v.length"
            else:
                return f"d3.sum(v, d => d['{field}'])"

        x_agg = agg_expr(x)
        y_agg = agg_expr(y)
        size_agg = agg_expr(size_field)

        # Generate filter conditions
        filter_conditions = []
        if filters:
            for f in filters:
                field = f["field"]
                op = f["op"]
                value = json.dumps(f["value"])
                if op == "eq":
                    filter_conditions.append(f"d['{field}'] === {value}")
                elif op == "ne":
                    filter_conditions.append(f"d['{field}'] !== {value}")
                elif op == "gt":
                    filter_conditions.append(f"d['{field}'] > {value}")
                elif op == "lt":
                    filter_conditions.append(f"d['{field}'] < {value}")
                elif op == "gte":
                    filter_conditions.append(f"d['{field}'] >= {value}")
                elif op == "lte":
                    filter_conditions.append(f"d['{field}'] <= {value}")
                elif op == "in":
                    filter_conditions.append(f"{value}.includes(d['{field}'])")
                elif op == "contains":
                    filter_conditions.append(f"String(d['{field}']).includes({value})")

        filter_code = " && ".join(filter_conditions) if filter_conditions else "true"

        # Sort logic
        sort_ascending = sort_order == "asc"
        if sort_field == "y":
            sort_code = f"result.sort((a, b) => {'1' if sort_ascending else '-1'} * (a.{y} - b.{y}));"
        else:
            sort_code = f"result.sort((a, b) => {'1' if sort_ascending else '-1'} * (a.{x} - b.{x}));"

        # Limit code
        limit_code = f"result = result.slice(0, {limit});" if limit else ""

        return f"""(() => {{
                // Filter data
                let filteredData = dashmlData.filter(d => {filter_code});

                let result = d3.rollups(
                    filteredData,
                    v => ({{ {x}: {x_agg}, {y}: {y_agg}, {size_field}: {size_agg} }}),
                    d => d['{group}']
                ).map(([{group}, vals]) => ({{ {group}, {x}: vals.{x}, {y}: vals.{y}, {size_field}: vals.{size_field} }}));

                // Sort
                {sort_code}

                // Limit
                {limit_code}

                return result;
            }})()"""

    def _get_plot_mark(self, chart_type: str, x: str, y: str, group: str, color: str, secondary_colors: list, data_var: str, bins: int = DEFAULT_HISTOGRAM_BINS, size_field: str = None) -> str:
        """Generate Observable Plot mark specification

        TODO: [SRP] This method is very long (~114 lines) with many if/elif branches
        Consider splitting into separate methods per chart type
        Fix: _get_bar_mark(), _get_line_mark(), _get_scatter_mark(), etc.
        """
        if chart_type == "bar":
            return f"""marks: [
                    Plot.barY(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{color}",
                        sort: null,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    domain: data_{data_var}.map(d => d.{x}),
                    tickRotate: -45
                }}"""

        elif chart_type == "line":
            return f"""marks: [
                    Plot.line(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        stroke: "{color}",
                        strokeWidth: 2,
                        sort: "{x}",
                        tip: true
                    }}),
                    Plot.dot(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{color}",
                        r: 4
                    }}),
                    Plot.ruleY([0])
                ]"""

        elif chart_type == "scatter":
            return f"""marks: [
                    Plot.dot(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{color}",
                        r: 5,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ]"""

        elif chart_type == "bubble":
            # Bubble chart: 4D visualization (group, x, y, size)
            size_ref = size_field if size_field else y
            color_scale_json = str(secondary_colors).replace("'", '"')
            if group:
                return f"""marks: [
                    Plot.dot(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{group}",
                        r: d => {{
                            const maxVal = d3.max(data_{data_var}, d => Math.abs(d["{size_ref}"]));
                            return 5 + (Math.abs(d["{size_ref}"]) / maxVal) * 25;
                        }},
                        tip: true
                    }}),
                    Plot.text(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        text: "{group}",
                        dy: -12,
                        fontSize: 10
                    }}),
                    Plot.ruleY([0])
                ],
                color: {{
                    domain: [...new Set(data_{data_var}.map(d => d.{group}))],
                    range: {color_scale_json}
                }}"""
            else:
                return f"""marks: [
                    Plot.dot(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{color}",
                        r: d => {{
                            const maxVal = d3.max(data_{data_var}, d => Math.abs(d.{size_ref}));
                            return 5 + (Math.abs(d.{size_ref}) / maxVal) * 25;
                        }},
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ]"""

        elif chart_type == "heatmap":
            # Heatmap: 2D grid with color intensity
            # Uses group field as y-axis categories if specified
            heatmap_y = group if group else y
            return f"""marks: [
                    Plot.cell(data_{data_var}, {{
                        x: "{x}",
                        y: "{heatmap_y}",
                        fill: "{y}",
                        tip: true
                    }})
                ],
                color: {{
                    type: "linear",
                    scheme: "blues",
                    legend: true,
                    label: "{y}"
                }}"""

        elif chart_type == "area":
            return f"""marks: [
                    Plot.areaY(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{color}",
                        fillOpacity: 0.7,
                        sort: "{x}",
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ]"""

        elif chart_type == "histogram":
            return f"""marks: [
                    Plot.rectY(data_{data_var}, Plot.binX({{y: "count", thresholds: {bins}}}, {{
                        x: "{x}",
                        fill: "{color}",
                        tip: true
                    }})),
                    Plot.ruleY([0])
                ]"""

        elif chart_type == "box":
            # Box plot: shows distribution (min, Q1, median, Q3, max)
            return f"""marks: [
                    Plot.boxY(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{color}",
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ]"""

        elif chart_type == "stacked_bar":
            # Observable Plot stacks by default when using fill with categorical data
            color_scale_json = str(secondary_colors).replace("'", '"')
            return f"""marks: [
                    Plot.barY(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{group}",
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                color: {{
                    domain: [...new Set(data_{data_var}.map(d => d.{group}))],
                    range: {color_scale_json}
                }}"""

        elif chart_type == "grouped_bar":
            # Observable Plot groups bars using fx channel for faceting
            # fx creates separate facets (groups), x positions bars within each facet
            color_scale_json = str(secondary_colors).replace("'", '"')
            return f"""marks: [
                    Plot.barY(data_{data_var}, {{
                        fx: "{x}",
                        x: "{group}",
                        y: "{y}",
                        fill: "{group}",
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    paddingInner: 0.1,
                    axis: null
                }},
                fx: {{
                    padding: 0.2
                }},
                color: {{
                    domain: [...new Set(data_{data_var}.map(d => d.{group}))],
                    range: {color_scale_json}
                }}"""

        elif chart_type == "geo":
            # Choropleth map using Observable Plot with world topojson
            return f"""marks: [
                    // Geo chart with country name normalization
                    Plot.geo(window.worldTopojson, {{
                        fill: d => {{
                            // Country name normalization map
                            const countryNameMap = {{
                                "USA": "United States of America",
                                "US": "United States of America",
                                "United States": "United States of America",
                                "UK": "United Kingdom",
                                "Britain": "United Kingdom",
                                "Great Britain": "United Kingdom",
                                "Russia": "Russian Federation",
                                "South Korea": "Korea, Republic of",
                                "Korea": "Korea, Republic of",
                                "North Korea": "Korea, Democratic People's Republic of",
                                "Iran": "Iran, Islamic Republic of",
                                "Syria": "Syrian Arab Republic",
                                "Venezuela": "Venezuela, Bolivarian Republic of",
                                "Bolivia": "Bolivia, Plurinational State of",
                                "Tanzania": "Tanzania, United Republic of",
                                "Vietnam": "Viet Nam",
                                "Laos": "Lao People's Democratic Republic",
                                "Czech Republic": "Czechia",
                                "Moldova": "Moldova, Republic of",
                                "Taiwan": "Taiwan, Province of China"
                            }};
                            const topoName = d.properties ? d.properties.name : null;
                            if (!topoName) return null;
                            const countryData = data_{data_var}.find(row => {{
                                if (!row.{x}) return false;
                                const normalizedName = countryNameMap[row.{x}] || row.{x};
                                return normalizedName.toLowerCase() === topoName.toLowerCase();
                            }});
                            return countryData ? countryData.{y} : null;
                        }},
                        stroke: "#ccc",
                        strokeWidth: 0.5,
                        tip: true
                    }})
                ],
                projection: "equal-earth",
                color: {{
                    type: "linear",
                    scheme: "blues",
                    unknown: "#f0f0f0",
                    legend: true,
                    label: "{y}"
                }}"""

        else:
            return f"""marks: [
                    Plot.barY(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{color}"
                    }})
                ]"""

    def get_run_command(self, output_path: str) -> str:
        """Return command to serve Observable Plot HTML or Flask app"""
        from pathlib import Path
        output_path_obj = Path(output_path)

        # If output is a directory (multi-file), run Flask
        if output_path_obj.is_dir():
            return f"cd {output_path} && python3 app.py"

        # Otherwise run simple HTTP server for single HTML file
        output_dir = output_path_obj.parent.resolve()
        return f"cd {output_dir} && python3 -m http.server 8000"

    def _generate_flask_app(self, spec: "NormalizedSpec", data_spec: Dict[str, Any]) -> str:
        """Generate Flask backend that connects to SQL database"""
        db_config = spec["db_config"]
        db_type = db_config["type"]
        host = db_config["host"]
        port = db_config["port"]
        database = db_config["database"]
        user = db_config["user"]
        password = db_config["password"]

        schema = data_spec["sql_schema"]
        table_name = data_spec["sql_table"]

        if db_type == "postgresql":
            conn_str = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        elif db_type == "mysql":
            conn_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        elif db_type == "sqlite":
            conn_str = f"sqlite:///{database}"
        else:
            conn_str = f"{db_type}://{user}:{password}@{host}:{port}/{database}"

        # Build per-chart queries
        table_ref = f"{schema}.{table_name}"
        all_charts = []
        for page in spec["pages"]:
            all_charts.extend(page.get("charts", []))

        chart_queries_dict = {}
        for chart in all_charts:
            chart_queries_dict[chart["id"]] = self._build_chart_query(chart, table_ref)

        chart_queries_code = "CHART_QUERIES = {\n"
        for cid, query in chart_queries_dict.items():
            chart_queries_code += f'    "{cid}": """{query}""",\n'
        chart_queries_code += "}"

        return f'''from flask import Flask, jsonify, send_from_directory, Response
from sqlalchemy import create_engine
import pandas as pd

app = Flask(__name__)

DATABASE_URL = "{conn_str}"
SCHEMA = "{schema}"
TABLE_NAME = "{table_name}"

engine = create_engine(DATABASE_URL)

# Per-chart SQL queries (generated at compile time)
{chart_queries_code}

_column_types_cache = None

def get_column_types():
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
        type_mapping = {{}}
        for _, row in df.iterrows():
            col_name = row['column_name']
            data_type = str(row['data_type']).upper()
            if any(dt in data_type for dt in ['DATE', 'TIME', 'TIMESTAMP', 'INTERVAL']):
                type_mapping[col_name] = 'date'
            elif any(dt in data_type for dt in ['INT', 'FLOAT', 'NUMERIC', 'DECIMAL',
                                                  'REAL', 'DOUBLE', 'SERIAL', 'MONEY']):
                type_mapping[col_name] = 'number'
            else:
                type_mapping[col_name] = 'string'
        _column_types_cache = type_mapping
        return type_mapping
    except Exception as e:
        print(f"Warning: Could not fetch column types: {{e}}")
        return {{}}

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/schema')
def get_schema():
    try:
        column_types = get_column_types()
        return jsonify(column_types)
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

@app.route('/api/chart/<chart_id>')
def get_chart_data(chart_id):
    query = CHART_QUERIES.get(chart_id)
    if not query:
        return jsonify({{"error": "Unknown chart"}}), 404
    try:
        df = pd.read_sql(query, engine)
        json_str = df.to_json(orient='records', date_format='iso')
        return Response(json_str, mimetype='application/json')
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

if __name__ == '__main__':
    print("Starting Flask server...")
    print(f"Dashboard available at: http://localhost:5001")
    app.run(debug=True, port=5001)
'''

    def _generate_flask_app_bigquery(self, spec: "NormalizedSpec", data_spec: Dict[str, Any]) -> str:
        """Generate Flask backend that connects to BigQuery"""
        db_config = spec["db_config"]
        project = db_config["project"]
        credentials_path = db_config.get("credentials_path")

        dataset = data_spec["bq_dataset"]
        table_name = data_spec["bq_table"]

        table_ref = f"`{project}.{dataset}.{table_name}`"

        all_charts = []
        for page in spec["pages"]:
            all_charts.extend(page.get("charts", []))

        chart_queries_dict = {}
        for chart in all_charts:
            chart_queries_dict[chart["id"]] = self._build_chart_query(chart, table_ref)

        chart_queries_code = "CHART_QUERIES = {\n"
        for cid, query in chart_queries_dict.items():
            chart_queries_code += f'    "{cid}": """{query}""",\n'
        chart_queries_code += "}"

        if credentials_path:
            credentials_code = f'''
from google.oauth2 import service_account
credentials = service_account.Credentials.from_service_account_file(
    "{credentials_path}",
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
'''
        else:
            credentials_code = '''
client = bigquery.Client(project=PROJECT_ID)
'''

        return f'''from flask import Flask, jsonify, send_from_directory
from google.cloud import bigquery
import json
from datetime import date, datetime
from decimal import Decimal
import os

app = Flask(__name__)

PROJECT_ID = "{project}"
DATASET = "{dataset}"
TABLE_NAME = "{table_name}"
{credentials_code}

# Per-chart SQL queries (generated at compile time)
{chart_queries_code}

_column_types_cache = None

def get_column_types():
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
    return send_from_directory('.', 'index.html')

@app.route('/api/schema')
def get_schema():
    try:
        column_types = get_column_types()
        return jsonify(column_types)
    except Exception as e:
        return jsonify({{"error": str(e)}}), 500

@app.route('/api/chart/<chart_id>')
def get_chart_data(chart_id):
    query = CHART_QUERIES.get(chart_id)
    if not query:
        return jsonify({{"error": "Unknown chart"}}), 404
    try:
        query_job = client.query(query)
        results = query_job.result()
        data = [dict(row) for row in results]
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
    print(f"Dashboard available at: http://localhost:5001")
    app.run(debug=True, port=5001)
'''

    def _generate_sql_frontend(self, spec: "NormalizedSpec") -> str:
        """Generate HTML frontend that fetches from Flask API"""
        colors = spec["style"]
        title = spec["title"]

        html_parts = []
        html_parts.append(self._generate_html_head(title, colors))
        html_parts.append(self._generate_body_start(title, colors))

        # Data loading from API
        html_parts.append(self._generate_sql_data_loader())

        # Always use pages (normalizer guarantees pages[] exists)
        html_parts.append(self._generate_sql_pages_structure(spec["pages"], colors))

        html_parts.append(self._generate_html_footer())

        return "\n".join(html_parts)

    def _generate_sql_data_loader(self) -> str:
        """Generate JavaScript to set up async per-chart loading"""
        return """
    <script>
        // World topojson for geo charts
        window.worldTopojson = null;

        // Load world topojson once
        fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json')
            .then(r => r.json())
            .then(worldData => {
                window.worldTopojson = topojson.feature(worldData, worldData.objects.countries);
            })
            .catch(err => console.warn('Could not load world topojson:', err));

        // Format a metric scalar value
        function formatMetric(value, format, suffix) {
            if (value === null || value === undefined || isNaN(value)) return 'N/A';
            const n = parseFloat(value);
            let str;
            if (format === ',.0f') str = n.toLocaleString('en-US', {maximumFractionDigits: 0});
            else if (format === ',.1f') str = n.toLocaleString('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 1});
            else if (format === ',.2f') str = n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            else if (format === '.0f') str = n.toFixed(0);
            else if (format === '.1f') str = n.toFixed(1);
            else if (format === '.2f') str = n.toFixed(2);
            else str = n.toLocaleString('en-US');
            return str + (suffix || '');
        }

        async function loadChart(containerId, chartId, renderFn) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = '<div class="chart-spinner"><div class="spinner"></div><span>Loading...</span></div>';
            try {
                const resp = await fetch('/api/chart/' + chartId);
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                container.innerHTML = '';
                renderFn(data);
            } catch (err) {
                container.innerHTML = '<div class="chart-error">Error loading chart: ' + err.message + '</div>';
                console.error('Chart ' + chartId + ' failed:', err);
            }
        }

        async function loadMetric(containerId, chartId, renderFn) {
            const el = document.getElementById(containerId);
            if (!el) return;
            el.textContent = '…';
            try {
                const resp = await fetch('/api/chart/' + chartId);
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                renderFn(data);
            } catch (err) {
                if (el) el.textContent = 'Error';
                console.error('Metric ' + chartId + ' failed:', err);
            }
        }
    </script>"""

    def _generate_sql_pages_structure(self, pages: list, colors: Dict[str, str]) -> str:
        """Generate multi-page structure with async per-chart loading for SQL/BQ mode"""
        primary_color = colors.get("primary", DEFAULT_PRIMARY_COLOR)
        secondary_colors = colors.get("secondary", DEFAULT_SECONDARY_COLORS)
        text_color = colors.get("text", "#000000")

        tabs = []
        page_contents = []
        load_calls = []

        for i, page in enumerate(pages):
            page_id = page["id"]
            title = page.get("title", page_id)
            description = page.get("description", "")
            charts = page.get("charts", [])

            active_class = " active" if i == 0 else ""
            tabs.append(f'        <button class="tab-button{active_class}" onclick="showPage(\'{page_id}\', this)">{title}</button>')

            page_html = [f'    <div id="page-{page_id}" class="page-content{active_class}">']
            if description:
                page_html.append(f'        <p class="page-description">{description}</p>')

            for chart in charts:
                chart_id = chart["id"]
                chart_title = chart.get("title", chart_id)
                container_id = f"chart-{page_id}-{chart_id}"

                if chart.get("type") == "metric":
                    page_html.append(f"""        <div class="card metric-card">
            <div class="metric-title">{chart_title}</div>
            <div id="{container_id}" class="metric-value">—</div>
        </div>""")
                    render_fn = self._generate_sql_chart_render_fn(chart, colors, container_id)
                    load_calls.append(f"        loadMetric('{container_id}', '{chart_id}', {render_fn})")
                else:
                    page_html.append(f"""        <div class="card">
            <h2>{chart_title}</h2>
            <div id="{container_id}"></div>
        </div>""")
                    render_fn = self._generate_sql_chart_render_fn(chart, colors, container_id)
                    load_calls.append(f"        loadChart('{container_id}', '{chart_id}', {render_fn})")

            page_html.append('    </div>')
            page_contents.append("\n".join(page_html))

        tabs_html = f"""    <div class="page-tabs">
{chr(10).join(tabs)}
    </div>"""

        load_calls_str = ",\n".join(load_calls)

        script = f"""
    <script>
        function showPage(pageId, buttonElement) {{
            document.querySelectorAll('.page-content').forEach(page => {{
                page.classList.remove('active');
            }});
            document.querySelectorAll('.tab-button').forEach(btn => {{
                btn.classList.remove('active');
            }});
            document.getElementById('page-' + pageId).classList.add('active');
            buttonElement.classList.add('active');
        }}

        // Load all charts independently
        Promise.allSettled([
{load_calls_str}
        ]);
    </script>"""

        return tabs_html + "\n" + "\n".join(page_contents) + script

    def _is_dark_theme(self, bg_color: str) -> bool:
        """Check if a hex background color is dark (luminance < 0.5)."""
        c = bg_color.lstrip("#")
        if len(c) == 3:
            c = c[0]*2 + c[1]*2 + c[2]*2
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5

    def _generate_sql_chart_render_fn(self, chart: Dict[str, Any], colors: Dict[str, str], container_id: str) -> str:
        """Generate a JS function(data) for rendering a chart with pre-aggregated data"""
        chart_id = chart["id"]
        chart_type = chart["type"]
        x = chart.get("x", "")  # Not required for metric type
        y = chart["y"]
        group = chart.get("group")
        size_field = chart.get("size")
        bins = chart.get("bins", DEFAULT_HISTOGRAM_BINS)
        format_str = resolve_metric_format(chart.get("format", "integer"))  # metric: number format
        suffix = chart.get("suffix", "")          # metric: unit text

        primary_color = colors.get("primary", DEFAULT_PRIMARY_COLOR)
        secondary_colors = colors.get("secondary", DEFAULT_SECONDARY_COLORS)
        text_color = colors.get("text", "#000000")

        safe_var = chart_id.replace('-', '_')

        # Determine bottom margin
        categorical_types = {"bar", "grouped_bar", "stacked_bar", "heatmap"}
        margin_bottom = 100 if chart_type in categorical_types else 40
        preprocess = ""
        margin_left = 60

        if chart_type == "metric":
            return f"""function(data) {{
            const value = (data && data[0] && data[0].y !== undefined) ? parseFloat(data[0].y) : null;
            const el = document.getElementById('{container_id}');
            if (el) el.textContent = formatMetric(value, '{format_str}', '{suffix}');
        }}"""

        if chart_type == "pie":
            color_scale_json = str(secondary_colors).replace("'", '"')
            return f"""function(data) {{
            const pieWidth = 400;
            const pieHeight = 400;
            const legendWidth = 150;
            const totalWidth = pieWidth + legendWidth;
            const radius = Math.min(pieWidth, pieHeight) / 2 - 10;
            const pie = d3.pie().value(d => d.y);
            const arc = d3.arc().innerRadius(0).outerRadius(radius);
            const themeColors = {color_scale_json};
            const color = d3.scaleOrdinal()
                .domain(data.map(d => d.x))
                .range(themeColors);
            const svg = d3.create("svg")
                .attr("width", totalWidth)
                .attr("height", pieHeight)
                .attr("viewBox", [0, 0, totalWidth, pieHeight])
                .attr("style", "max-width: 100%; height: auto;");
            const pieGroup = svg.append("g")
                .attr("transform", `translate(${{pieWidth / 2}}, ${{pieHeight / 2}})`);
            pieGroup.selectAll("path")
                .data(pie(data))
                .join("path")
                .attr("fill", d => color(d.data.x))
                .attr("d", arc)
                .attr("stroke", "white")
                .attr("stroke-width", 2)
                .append("title")
                .text(d => `${{d.data.x}}: ${{d.data.y}}`);
            const legend = svg.append("g")
                .attr("transform", `translate(${{pieWidth + 10}}, 20)`);
            data.forEach((d, i) => {{
                const legendRow = legend.append("g")
                    .attr("transform", `translate(0, ${{i * 25}})`);
                legendRow.append("rect")
                    .attr("width", 15)
                    .attr("height", 15)
                    .attr("fill", color(d.x))
                    .attr("rx", 2);
                legendRow.append("text")
                    .attr("x", 22)
                    .attr("y", 12)
                    .attr("fill", "{text_color}")
                    .style("font-size", "13px")
                    .text(d.x);
            }});
            document.getElementById('{container_id}').appendChild(svg.node());
        }}"""

        if chart_type == "geo":
            bg_color = colors.get("background", "#ffffff")
            # Determine a subtle unknown color based on theme brightness
            sphere_color = "#1a1a2e" if self._is_dark_theme(bg_color) else "#f8f8f8"
            unknown_color = "#2a2a3e" if self._is_dark_theme(bg_color) else "#e0e0e0"
            border_color = "#555570" if self._is_dark_theme(bg_color) else "#ccc"
            return f"""function(data) {{
            const plot = Plot.plot({{
                width: 928,
                marks: [
                    Plot.sphere({{fill: "{sphere_color}", stroke: "{border_color}"}}),
                    Plot.graticule({{stroke: "{border_color}40", strokeWidth: 0.5}}),
                    Plot.geo(window.worldTopojson, {{
                        fill: d => {{
                            const countryNameMap = {{
                                "USA": "United States of America",
                                "US": "United States of America",
                                "United States": "United States of America",
                                "UK": "United Kingdom",
                                "UNITED KINGDOM": "United Kingdom",
                                "Russia": "Russian Federation",
                                "South Korea": "Korea, Republic of",
                                "Iran": "Iran, Islamic Republic of",
                                "Czech Republic": "Czechia",
                                "SPAIN(CANARY IS)": "Spain",
                                "SPAIN (CANARY IS)": "Spain"
                            }};
                            const topoName = d.properties ? d.properties.name : null;
                            if (!topoName) return null;
                            const countryData = data.find(row => {{
                                if (!row.x) return false;
                                const normalizedName = countryNameMap[row.x] || row.x;
                                return normalizedName.toLowerCase() === topoName.toLowerCase();
                            }});
                            return countryData ? countryData.y : null;
                        }},
                        stroke: "{border_color}",
                        strokeWidth: 0.5,
                        tip: true
                    }})
                ],
                projection: "equal-earth",
                color: {{
                    type: "linear",
                    scheme: "YlGnBu",
                    unknown: "{unknown_color}",
                    legend: true,
                    label: "{y}"
                }},
                margin: 2,
                style: {{
                    background: "transparent",
                    color: "{text_color}"
                }}
            }});
            document.getElementById('{container_id}').appendChild(plot);
        }}"""

        # For all other chart types, build Observable Plot
        if chart_type == "bar":
            mark_code = f"""marks: [
                    Plot.barY(data, {{
                        x: "x",
                        y: "y",
                        fill: "{primary_color}",
                        sort: null,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    domain: data.map(d => d.x),
                    tickRotate: -45,
                    label: "{x}"
                }},
                y: {{ label: "{y}" }}"""
        elif chart_type == "line":
            preprocess = "data = data.filter(d => d.x != null && d.y != null); data.forEach(d => d.x = new Date(d.x));"
            margin_bottom = 100
            mark_code = f"""marks: [
                    Plot.line(data, {{
                        x: "x",
                        y: "y",
                        stroke: "{primary_color}",
                        strokeWidth: 2,
                        tip: true
                    }}),
                    Plot.dot(data, {{
                        x: "x",
                        y: "y",
                        fill: "{primary_color}",
                        r: 4
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{ type: "utc", tickRotate: -45, label: "{x}" }},
                y: {{ label: "{y}" }}"""
        elif chart_type == "scatter":
            preprocess = "data = data.filter(d => d.x != null && d.y != null);"
            mark_code = f"""marks: [
                    Plot.dot(data, {{
                        x: "x",
                        y: "y",
                        fill: "{primary_color}",
                        r: 3,
                        opacity: 0.3,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{ label: "{x}" }},
                y: {{ label: "{y}" }}"""
        elif chart_type == "area":
            preprocess = "data = data.filter(d => d.x != null && d.y != null); data.forEach(d => d.x = new Date(d.x));"
            margin_bottom = 100
            mark_code = f"""marks: [
                    Plot.areaY(data, {{
                        x: "x",
                        y: "y",
                        fill: "{primary_color}",
                        fillOpacity: 0.7,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{ type: "utc", tickRotate: -45, label: "{x}" }},
                y: {{ label: "{y}" }}"""
        elif chart_type == "histogram":
            preprocess = "data = data.filter(d => d.x != null).map(d => ({...d, x: +d.x}));"
            mark_code = f"""marks: [
                    Plot.rectY(data, Plot.binX({{y: "count", thresholds: {bins}}}, {{
                        x: "x",
                        fill: "{primary_color}",
                        tip: true
                    }})),
                    Plot.ruleY([0])
                ],
                x: {{ label: "{x}" }}"""
        elif chart_type == "box":
            preprocess = "data = data.filter(d => d.x != null && d.y != null);"
            margin_bottom = 100
            mark_code = f"""marks: [
                    Plot.boxY(data, {{
                        x: "x",
                        y: "y",
                        fill: "{primary_color}",
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{ tickRotate: -45, label: "{x}" }},
                y: {{ label: "{y}" }}"""
        elif chart_type in ("stacked_bar", "grouped_bar"):
            color_scale_json = str(secondary_colors).replace("'", '"')
            if chart_type == "stacked_bar":
                mark_code = f"""marks: [
                    Plot.barY(data, {{
                        x: "x",
                        y: "y",
                        fill: "grp",
                        sort: null,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    domain: [...new Set(data.map(d => d.x))],
                    tickRotate: -45,
                    label: "{x}"
                }},
                y: {{ label: "{y}" }},
                color: {{
                    domain: [...new Set(data.map(d => d.grp))],
                    range: {color_scale_json}
                }}"""
            else:  # grouped_bar
                mark_code = f"""marks: [
                    Plot.barY(data, {{
                        fx: "x",
                        x: "grp",
                        y: "y",
                        fill: "grp",
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    paddingInner: 0.1,
                    axis: null
                }},
                fx: {{
                    padding: 0.2,
                    tickRotate: -45,
                    label: "{x}"
                }},
                y: {{ label: "{y}" }},
                color: {{
                    domain: [...new Set(data.map(d => d.grp))],
                    range: {color_scale_json}
                }}"""
        elif chart_type == "heatmap":
            heatmap_y_label = group if group else y
            margin_left = 200
            preprocess = "data = data.filter(d => d.x != null && d.heatmap_y != null);"
            mark_code = f"""marks: [
                    Plot.cell(data, {{
                        x: "x",
                        y: "heatmap_y",
                        fill: "y",
                        tip: true
                    }})
                ],
                height: Math.max(400, [...new Set(data.map(d => d.heatmap_y))].length * 20),
                x: {{
                    tickRotate: -45,
                    label: "{x}"
                }},
                y: {{ label: "{heatmap_y_label}" }},
                color: {{
                    type: "linear",
                    scheme: "blues",
                    legend: true,
                    label: "{y}"
                }}"""
        elif chart_type == "bubble" and group:
            color_scale_json = str(secondary_colors).replace("'", '"')
            mark_code = f"""marks: [
                    Plot.dot(data, {{
                        x: "x",
                        y: "y",
                        fill: "grp",
                        r: d => {{
                            const maxVal = d3.max(data, dd => Math.abs(dd.size));
                            return 5 + (Math.abs(d.size) / maxVal) * 25;
                        }},
                        tip: true
                    }}),
                    Plot.text(data, {{
                        x: "x",
                        y: "y",
                        text: "grp",
                        dy: -12,
                        fontSize: 10
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{ label: "{x}" }},
                y: {{ label: "{y}" }},
                color: {{
                    domain: [...new Set(data.map(d => d.grp))],
                    range: {color_scale_json}
                }}"""
        else:
            # Default: bar
            mark_code = f"""marks: [
                    Plot.barY(data, {{
                        x: "x",
                        y: "y",
                        fill: "{primary_color}",
                        sort: null,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    domain: data.map(d => d.x),
                    tickRotate: -45,
                    label: "{x}"
                }},
                y: {{ label: "{y}" }}"""

        return f"""function(data) {{
            {preprocess}
            const plot = Plot.plot({{
                {mark_code},
                marginLeft: {margin_left},
                marginBottom: {margin_bottom},
                grid: true,
                style: {{
                    background: "transparent",
                    color: "{text_color}"
                }}
            }});
            document.getElementById('{container_id}').appendChild(plot);
        }}"""

