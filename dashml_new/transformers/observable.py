"""
Observable Plot Transformer - Generates Observable Plot HTML from DashML specs
"""
from typing import TYPE_CHECKING, Dict, Any, List
from pathlib import Path
import yaml
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
)

if TYPE_CHECKING:
    from ..core.types import DashMLSpec, ChartSpec


class ObservablePlotTransformer(Transformer):
    """
    Generates standalone Observable Plot HTML dashboards from DashML specifications.
    Output: Single HTML file for CSV, multi-file with Flask backend for SQL
    """

    def __init__(self):
        super().__init__()
        self.db_config = None

    def set_db_config(self, config: Dict[str, Any]) -> None:
        """Store database configuration for SQL datasources"""
        self.db_config = config

    @property
    def name(self) -> str:
        return "observable"

    @property
    def description(self) -> str:
        return "Generates Observable Plot HTML dashboards"

    def build(self, spec: "DashMLSpec") -> str:
        """
        Generate Observable Plot HTML from DashML spec.
        For CSV: Returns single HTML file
        For SQL: Returns JSON-encoded multi-file structure with Flask backend
        For BigQuery: Returns JSON-encoded multi-file structure with Flask + BigQuery backend
        """
        try:
            self.clear_warnings()  # Clear warnings from previous builds

            # Check data type
            data_type = spec["data"].get("type", "csv")

            if data_type == "sql":
                # Generate multi-file output with Flask backend
                return self._build_sql_version(spec)
            elif data_type == "bigquery":
                # Generate multi-file output with Flask + BigQuery backend
                return self._build_bigquery_version(spec)
            else:
                # Generate single HTML file for CSV
                return self._build_csv_version(spec)

        except KeyError as e:
            raise TransformerError(f"Missing required field in spec: {e}")
        except Exception as e:
            raise TransformerError(f"Failed to generate Observable Plot HTML: {e}")

    def _build_csv_version(self, spec: "DashMLSpec") -> str:
        """Generate single HTML file for CSV datasources"""
        # Load style config
        style_config = self._load_style_config(spec.get("style"))
        colors = style_config.get("colors", {})

        # Warn about unsupported color fields
        if colors.get("buttons"):
            self.warn("'buttons' color is not currently used by Observable transformer")

        # Check for unsupported chart types
        all_charts = []
        if "pages" in spec:
            for page in spec["pages"]:
                all_charts.extend(page.get("charts", []))
        else:
            all_charts = spec.get("charts", [])

        # Warnings are now handled by validator (group field requirement)

        # Build HTML structure
        html_parts = []
        html_parts.append(self._generate_html_head(spec.get("title", "DashML Dashboard"), colors))
        html_parts.append(self._generate_body_start(spec.get("title", "DashML Dashboard"), colors))

        # Data loading
        data_spec = spec["data"]
        html_parts.append(self._generate_data_loader(data_spec))

        # Pages or Charts
        if "pages" in spec:
            html_parts.append(self._generate_pages_structure(spec["pages"], colors))
        else:
            html_parts.append(self._generate_charts_structure(spec.get("charts", []), colors))

        html_parts.append(self._generate_html_footer())

        return "\n".join(html_parts)

    def _build_bigquery_version(self, spec: "DashMLSpec") -> str:
        """Generate multi-file output with Flask + BigQuery backend"""
        if not self.db_config:
            raise TransformerError("BigQuery configuration not provided")

        # Generate Flask backend with BigQuery
        data_spec = spec["data"]
        flask_app = self._generate_flask_app_bigquery(data_spec)

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

    def _build_sql_version(self, spec: "DashMLSpec") -> str:
        """Generate multi-file output with Flask backend for SQL datasources"""

        if not self.db_config:
            raise TransformerError("Database configuration not provided for SQL datasource")

        # Generate Flask backend
        data_spec = spec["data"]
        flask_app = self._generate_flask_app(data_spec)

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

    # _load_style_config is now inherited from base class

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
                    // Check if it looks like a date (YYYY-MM-DD or similar)
                    else if (/^\\d{{4}}-\\d{{2}}-\\d{{2}}/.test(value)) {{
                        row[header] = new Date(value);
                    }}
                    // Keep as string
                    else {{
                        row[header] = value;
                    }}
                }});
                rows.push(row);
            }}
            return rows;
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
        x = chart["x"]
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

        # Determine container ID
        container_id = f"chart-{page_id}-{chart_id}" if page_id else f"chart-{chart_id}"

        # Safe variable name
        safe_var_name = chart_id.replace('-', '_')

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

        return f"""            // Chart: {chart_id}
            const data_{safe_var_name} = {data_code};
            const plot_{safe_var_name} = Plot.plot({{
                {mark_code},
                {scale_config}marginLeft: 60,
                marginBottom: 40,
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
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ]"""

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
            return f"cd {output_path} && python app.py"

        # Otherwise run simple HTTP server for single HTML file
        output_dir = output_path_obj.parent.resolve()
        return f"cd {output_dir} && python -m http.server 8000"

    # _parse_sql_path is now inherited from base class

    def _generate_flask_app(self, data_spec: Dict[str, Any]) -> str:
        """Generate Flask backend that connects to SQL database"""
        # Extract database config
        db_type = self.db_config["type"]
        host = self.db_config["host"]
        port = self.db_config["port"]
        database = self.db_config["database"]
        user = self.db_config["user"]
        password = self.db_config["password"]

        # Extract SQL spec fields (support both new path format and legacy format)
        if "path" in data_spec:
            schema, table_name = self._parse_sql_path(data_spec["path"])
        else:
            schema = data_spec["schema"]
            table_name = data_spec["table_name"]

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

    def _generate_flask_app_bigquery(self, data_spec: Dict[str, Any]) -> str:
        """Generate Flask backend that connects to BigQuery"""
        # Extract BigQuery config
        project = self.db_config["project"]
        credentials_path = self.db_config.get("credentials_path")

        # Parse dataset.table from path
        path = data_spec["path"]
        parts = path.split(".")
        if len(parts) == 2:
            dataset, table_name = parts
        else:
            raise TransformerError(f"Invalid BigQuery path format: {path}. Expected: dataset.table")

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

    def _generate_sql_frontend(self, spec: "DashMLSpec") -> str:
        """Generate HTML frontend that fetches from Flask API"""
        # Load style config
        style_config = self._load_style_config(spec.get("style"))
        colors = style_config.get("colors", {})

        # Build HTML structure
        html_parts = []
        html_parts.append(self._generate_html_head(spec.get("title", "DashML Dashboard"), colors))
        html_parts.append(self._generate_body_start(spec.get("title", "DashML Dashboard"), colors))

        # Data loading from API
        html_parts.append(self._generate_sql_data_loader())

        # Pages or Charts
        if "pages" in spec:
            html_parts.append(self._generate_pages_structure(spec["pages"], colors))
        else:
            html_parts.append(self._generate_charts_structure(spec.get("charts", []), colors))

        html_parts.append(self._generate_html_footer())

        return "\n".join(html_parts)

    def _generate_sql_data_loader(self) -> str:
        """Generate JavaScript to load data from Flask API"""
        return """
    <script>
        // Column types from INFORMATION_SCHEMA (auto-detected)
        let columnTypes = {};
        // Load data from Flask API
        let dashmlData = [];
        // World topojson for geo charts
        window.worldTopojson = null;

        // Get effective type: explicit > schema-detected > undefined
        function getEffectiveType(column, explicitType) {
            if (explicitType) return explicitType;
            return columnTypes[column] || undefined;
        }

        // Fetch schema, data, and world topojson in parallel
        Promise.all([
            fetch('/api/schema').then(r => r.json()),
            fetch('/api/data').then(r => r.json()),
            fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json').then(r => r.json())
        ])
            .then(([schema, data, worldData]) => {
                columnTypes = schema;

                // Convert topojson to geojson for Observable Plot
                window.worldTopojson = topojson.feature(worldData, worldData.objects.countries);

                // Parse ISO 8601 date strings to Date objects
                // Server already cast types, we just need to parse ISO dates
                dashmlData = data.map(row => {
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
                console.log('Parsed data (first row):', dashmlData[0]);
                renderAllCharts();
            })
            .catch(error => {
                console.error('Error loading data:', error);
                document.body.innerHTML += '<p style="color: red;">Error loading data from database</p>';
            });
    </script>"""

