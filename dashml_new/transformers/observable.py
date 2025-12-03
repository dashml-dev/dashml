"""
Observable Plot Transformer - Generates Observable Plot HTML from DashML specs
"""
from typing import TYPE_CHECKING, Dict, Any
from pathlib import Path
import yaml
from .base import Transformer, TransformerError

if TYPE_CHECKING:
    from ..core.types import DashMLSpec, ChartSpec

# Chart type categorization by data requirements
CHARTS_NEED_AGGREGATION = {"bar", "line", "area", "pie", "stacked_bar", "grouped_bar"}
CHARTS_USE_RAW_DATA = {"histogram", "scatter"}  # Charts that work with raw data points


class ObservablePlotTransformer(Transformer):
    """
    Generates standalone Observable Plot HTML dashboards from DashML specifications.
    Output: Single HTML file with embedded JavaScript using Observable Plot
    """

    @property
    def name(self) -> str:
        return "observable"

    @property
    def description(self) -> str:
        return "Generates Observable Plot HTML dashboards"

    def build(self, spec: "DashMLSpec") -> str:
        """
        Generate Observable Plot HTML from DashML spec.
        """
        try:
            self.clear_warnings()  # Clear warnings from previous builds

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

        except KeyError as e:
            raise TransformerError(f"Missing required field in spec: {e}")
        except Exception as e:
            raise TransformerError(f"Failed to generate Observable Plot HTML: {e}")

    def _load_style_config(self, style_path: str) -> Dict[str, Any]:
        """Read .dmls file during build"""
        if not style_path:
            return {}
        try:
            path = Path(style_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception:
            pass
        return {}

    def _generate_html_head(self, title: str, colors: Dict[str, str]) -> str:
        bg_color = colors.get("background", "#ffffff")
        card_color = colors.get("card", bg_color)
        text_color = colors.get("text", "#000000")
        primary_color = colors.get("primary", "#4269d0")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
    <script src="https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6"></script>
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

        fetch('{path}')
            .then(response => response.text())
            .then(csvText => {{
                dashmlData = parseCSV(csvText);
                renderAllCharts();
            }})
            .catch(error => {{
                console.error('Error loading data:', error);
                document.body.innerHTML += '<p style="color: red;">Error loading data file: {path}</p>';
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

        primary_color = colors.get("primary", "#4269d0")
        secondary_colors = colors.get("secondary", ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'])

        # Determine container ID
        container_id = f"chart-{page_id}-{chart_id}" if page_id else f"chart-{chart_id}"

        # Safe variable name
        safe_var_name = chart_id.replace('-', '_')

        # Generate data code based on chart type requirements
        if chart_type in CHARTS_USE_RAW_DATA:
            # Use raw data for histogram and scatter
            data_code = "dashmlData"
        elif chart_type in ["stacked_bar", "grouped_bar"] and group:
            # For stacked/grouped bars, need to group by both x and group field
            data_code = self._get_aggregation_code_with_group(x, y, group, agg)
        else:
            # Aggregate data for other chart types
            data_code = self._get_aggregation_code(x, y, agg)

        # Pie charts use D3 directly instead of Observable Plot
        if chart_type == "pie":
            return self._generate_d3_pie_chart(safe_var_name, x, y, data_code, container_id, colors)

        # Generate Observable Plot mark based on chart type
        mark_code = self._get_plot_mark(chart_type, x, y, group, primary_color, secondary_colors, safe_var_name)

        # Detect if x axis is temporal (common date field names)
        temporal_fields = ['date', 'time', 'timestamp', 'datetime', 'created_at', 'updated_at']
        is_temporal_x = x.lower() in temporal_fields

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
        secondary_colors = colors.get('secondary', ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'])
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

    def _get_aggregation_code(self, x: str, y: str, agg: str) -> str:
        """Generate JavaScript code to aggregate data"""
        if agg == "sum":
            agg_expr = f"d3.sum(v, d => d['{y}'])"
        elif agg == "mean":
            agg_expr = f"d3.mean(v, d => d['{y}'])"
        elif agg == "count":
            agg_expr = "v.length"
        else:
            agg_expr = f"d3.sum(v, d => d['{y}'])"

        return f"""d3.rollups(
                dashmlData,
                v => {agg_expr},
                d => d['{x}']
            ).map(([{x}, {y}]) => ({{ {x}, {y} }}))"""

    def _get_aggregation_code_with_group(self, x: str, y: str, group: str, agg: str) -> str:
        """Generate JavaScript code to aggregate data with grouping"""
        if agg == "sum":
            agg_expr = f"d3.sum(v, d => d['{y}'])"
        elif agg == "mean":
            agg_expr = f"d3.mean(v, d => d['{y}'])"
        elif agg == "count":
            agg_expr = "v.length"
        else:
            agg_expr = f"d3.sum(v, d => d['{y}'])"

        return f"""d3.rollups(
                dashmlData,
                v => {agg_expr},
                d => d['{x}'],
                d => d['{group}']
            ).flatMap(([{x}Val, groupData]) =>
                groupData.map(([{group}Val, {y}Val]) => ({{
                    {x}: {x}Val,
                    {group}: {group}Val,
                    {y}: {y}Val
                }}))
            )"""

    def _get_plot_mark(self, chart_type: str, x: str, y: str, group: str, color: str, secondary_colors: list, data_var: str) -> str:
        """Generate Observable Plot mark specification"""
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

        elif chart_type == "area":
            return f"""marks: [
                    Plot.areaY(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{color}",
                        fillOpacity: 0.7,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ]"""

        elif chart_type == "histogram":
            return f"""marks: [
                    Plot.rectY(data_{data_var}, Plot.binX({{y: "count"}}, {{
                        x: "{x}",
                        fill: "{color}",
                        tip: true
                    }})),
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
            # Observable Plot groups bars using fx channel
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
                x: {{
                    paddingInner: 0.2
                }},
                color: {{
                    domain: [...new Set(data_{data_var}.map(d => d.{group}))],
                    range: {color_scale_json}
                }},
                fx: {{
                    domain: [...new Set(data_{data_var}.map(d => d.{x}))]
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
        """Return command to serve Observable Plot HTML"""
        from pathlib import Path
        output_dir = Path(output_path).parent.resolve()
        return f"cd {output_dir} && python -m http.server 8000"
