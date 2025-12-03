"""
Plotly Transformer - Generates Plotly HTML/JavaScript from DashML specs
"""
from typing import TYPE_CHECKING, Dict, Any
from pathlib import Path
import yaml
import json
from .base import Transformer, TransformerError

if TYPE_CHECKING:
    from ..core.types import DashMLSpec

# Chart type categorization by data requirements
CHARTS_NEED_AGGREGATION = {"bar", "line", "area", "pie", "stacked_bar", "grouped_bar"}
CHARTS_USE_RAW_DATA = {"histogram", "scatter"}  # Charts that work with raw data points


class PlotlyTransformer(Transformer):
    """
    Generates standalone HTML files with Plotly.js visualizations.
    Output: HTML file that can be opened directly in a browser
    """

    @property
    def name(self) -> str:
        return "plotly"

    @property
    def description(self) -> str:
        return "Generates Plotly.js HTML dashboards"

    def build(self, spec: "DashMLSpec") -> str:
        """
        Generate Plotly HTML from DashML spec.
        """
        try:
            self.clear_warnings()  # Clear warnings from previous builds

            title = spec.get("title", "DashML Dashboard")
            data_spec = spec["data"]

            # --- NEW: Load Styles ---
            colors = self._load_colors(spec.get("style"))
            # ------------------------

            # Warn about unsupported color fields
            if colors.get("buttons"):
                self.warn("'buttons' color is not currently used by Plotly transformer")

            # Check for unsupported chart types
            all_charts = []
            if "pages" in spec:
                for page in spec["pages"]:
                    all_charts.extend(page.get("charts", []))
            else:
                all_charts = spec.get("charts", [])

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

            # Check if using pages or legacy charts
            if "pages" in spec:
                # Multi-page dashboard with tabs
                pages = spec["pages"]
                html_parts.append(self._generate_page_tabs(pages, colors))
                html_parts.append(self._generate_page_containers(pages, colors))
                html_parts.append('  </div>')
                html_parts.append(self._generate_javascript_pages(data_spec, pages, colors))
            else:
                # Legacy: single page with chart selector
                charts = spec.get("charts", [])
                html_parts.append('    <div class="card">')

                # Chart selector
                if len(charts) > 1:
                    html_parts.append(self._generate_chart_selector(charts))

                # Chart container
                html_parts.append('      <div id="chart"></div>')
                html_parts.append('    </div>')
                html_parts.append('  </div>')

                # JavaScript
                html_parts.append(self._generate_javascript(data_spec, charts, colors))

            # Body end
            html_parts.append("</body>")
            html_parts.append("</html>")

            return "\n".join(html_parts)

        except KeyError as e:
            raise TransformerError(f"Missing required field in spec: {e}")
        except Exception as e:
            raise TransformerError(f"Failed to generate Plotly code: {e}")

    def _load_colors(self, style_path: str) -> Dict[str, str]:
        """Load colors from style file or return defaults"""
        defaults = {
            "background": "#f5f5f5",  # Page background
            "card": "#ffffff",        # Card background
            "text": "#333333",        # Main text
            "primary": "#1f77b4",     # Primary color (active tabs)
            "secondary": []
        }

        if not style_path:
            return defaults

        try:
            path = Path(style_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    loaded = data.get("colors", {})

                    # Merge with defaults
                    return {
                        "background": loaded.get("background", defaults["background"]),
                        "card": loaded.get("card", loaded.get("background", defaults["card"])),
                        "text": loaded.get("text", defaults["text"]),
                        "primary": loaded.get("primary", defaults["primary"]),
                        "secondary": loaded.get("secondary", [])
                    }
        except Exception as e:
            print(f"Warning: Failed to load style {style_path}: {e}")

        return defaults

    def _generate_html_header(self, title: str, colors: Dict[str, str]) -> str:
        """Generate HTML header with dynamic CSS based on theme"""
        bg = colors["background"]
        card_bg = colors["card"]
        text = colors["text"]
        primary = colors["primary"]

        # If background is dark (simple heuristic), make shadow lighter or different
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
        return '''    function aggregateData(data, x, y, agg) {
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
      return result;
    }

    function aggregateDataWithGroup(data, x, y, groupField, agg) {
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
      return result;
    }'''

    def _generate_renderer(self, multi_page=False) -> str:
        """
        Generate chart rendering function.
        Updated to use theme colors for Plotly Layout.
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

      if (chart.type === 'stacked_bar' || chart.type === 'grouped_bar') {{
        // Stacked/grouped bars need multiple traces
        const aggregated = aggregateDataWithGroup(window.dashmlData, chart.x, chart.y, chart.group, chart.agg || 'sum');
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
        let xValues, yValues;
        if (chartsUseRawData.has(chart.type)) {{
          // Use raw data for histogram and scatter
          xValues = window.dashmlData.map(d => d[chart.x]);
          yValues = window.dashmlData.map(d => d[chart.y]);
        }} else {{
          // Aggregate data for other chart types
          const aggregated = aggregateData(window.dashmlData, chart.x, chart.y, chart.agg || 'sum');
          xValues = aggregated.map(d => d.x);
          yValues = aggregated.map(d => d.y);
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
        case 'pie':
          trace = {{ labels: xValues, values: yValues, type: 'pie', marker: {{ colors: theme.secondary }} }};
          break;
        case 'area':
          trace = {{ x: xValues, y: yValues, type: 'scatter', fill: 'tozeroy', mode: 'lines', line: {{ color: theme.primary }}, fillcolor: theme.primary + '40' }};
          break;
        case 'histogram':
          trace = {{ x: xValues, type: 'histogram', marker: {{ color: theme.primary }} }};
          break;
        default:
          trace = {{ x: xValues, y: yValues, type: 'bar', marker: {{ color: theme.primary }} }};
      }}

      traces.push(trace);
      }}

      const layout = {{
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

            # Check if this is stacked/grouped bar
            if chart_type in ["stacked_bar", "grouped_bar"]:
                barmode = 'stack' if chart_type == 'stacked_bar' else 'group'
                chart_functions.append(f'''
    function render_{chart_id}(data) {{
      // Stacked/grouped bars need multiple traces
      const aggregated = aggregateDataWithGroup(data, '{x}', '{y}', '{group}', '{agg}');
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
            else:
                # Standard single-trace charts
                if chart_type in CHARTS_USE_RAW_DATA:
                    data_prep = f'''
      // Use raw data for {chart_type}
      const xValues = data.map(d => d['{x}']);
      const yValues = data.map(d => d['{y}']);'''
                else:
                    data_prep = f'''
      const grouped = aggregateData(data, '{x}', '{y}', '{agg}');
      const xValues = grouped.map(d => d.{x});
      const yValues = grouped.map(d => d.{y});'''

                chart_functions.append(f'''
    function render_{chart_id}(data) {{{data_prep}

      let trace;
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
          trace = {{ x: xValues, type: 'histogram', marker: {{ color: theme.primary }} }};
          break;
        default:
          trace = {{ x: xValues, y: yValues, type: 'bar', marker: {{ color: theme.primary }} }};
      }}

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

        return f'''  <script>
    const theme = {theme_json};

    function aggregateData(data, xCol, yCol, aggFunc) {{
      const groups = {{}};
      data.forEach(row => {{
        const key = row[xCol];
        if (!groups[key]) groups[key] = [];
        groups[key].push(parseFloat(row[yCol]) || 0);
      }});

      return Object.entries(groups).map(([key, values]) => {{
        let aggValue;
        switch (aggFunc) {{
          case 'mean': aggValue = values.reduce((a, b) => a + b, 0) / values.length; break;
          case 'count': aggValue = values.length; break;
          default: aggValue = values.reduce((a, b) => a + b, 0);
        }}
        return {{ [xCol]: key, [yCol]: aggValue }};
      }});
    }}

    function aggregateDataWithGroup(data, x, y, groupField, agg) {{
      const grouped = {{}};
      data.forEach(row => {{
        const xKey = row[x];
        const groupKey = row[groupField];
        const compositeKey = xKey + '|||' + groupKey;
        if (!grouped[compositeKey]) grouped[compositeKey] = {{ x: xKey, group: groupKey, values: [], count: 0 }};
        grouped[compositeKey].values.push(parseFloat(row[y]) || 0);
        grouped[compositeKey].count++;
      }});

      const result = [];
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
        """Return command to serve Plotly HTML"""
        from pathlib import Path
        output_dir = Path(output_path).parent.resolve()
        return f"cd {output_dir} && python -m http.server 8000"