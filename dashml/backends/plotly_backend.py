"""
Plotly Backend Plugin
Generates JSON config that browser uses to fetch and visualize data
"""
import json
from typing import Any, Dict
from dashml.core.ir import IR, Dataset, Chart
from .base import Backend


class PlotlyBackend(Backend):
    """
    Plotly.js backend implementation
    
    Strategy:
    - Reads IR
    - Generates JSON configuration
    - Browser JavaScript loads data and renders
    - NO server-side data processing
    """
    
    def generate(self, ir: IR) -> str:
        """
        Generate Plotly-compatible JSON config
        
        Returns:
            JSON string describing dashboard structure
            Browser will use this to fetch data and render charts
        """
        config = {
            "version": ir.version,
            "title": ir.title,
            "datasets": {},
            "charts": [],
            "filters": [f.to_dict() for f in ir.global_filters]
        }
        
        # Dataset configs (tells browser WHERE to fetch)
        for dataset_id, dataset in ir.datasets.items():
            config["datasets"][dataset_id] = {
                "id": dataset_id,
                "type": dataset.type,
                "source": dataset.source,
                "query": dataset.query
            }
        
        # Chart configs (tells browser WHAT to visualize)
        for chart in ir.charts:
            config["charts"].append({
                "id": chart.id,
                "type": chart.type.value,
                "title": chart.title,
                "datasetId": chart.dataset_id,
                "x": {
                    "column": chart.x_dimension.column,
                    "type": chart.x_dimension.type
                },
                "y": {
                    "column": chart.y_measure.column,
                    "aggregation": chart.y_measure.aggregation.value
                },
                "filters": [f.to_dict() for f in chart.filters],
                "color": chart.color
            })
        
        return json.dumps(config, indent=2)
    
    def execute(self, ir: IR, **kwargs) -> Dict[str, Any]:
        """
        Generate runtime config for browser
        
        Returns dict that gets serialized to JSON for browser consumption
        """
        return json.loads(self.generate(ir))
    
    def generate_html(self, ir: IR) -> str:
        """
        Generate standalone HTML page with embedded config
        
        This HTML:
        - Contains the IR as JSON
        - Includes Plotly.js
        - Has JavaScript that reads IR and renders charts
        - Fetches data itself (backend responsibility in browser)
        """
        config_json = self.generate(ir)
        
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ir.title}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f7fa;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            margin-top: 0;
            color: #2c3e50;
        }}
        .chart-container {{
            margin: 30px 0;
            height: 500px;
        }}
        select {{
            padding: 8px 16px;
            font-size: 14px;
            border: 2px solid #ddd;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{ir.title}</h1>
        <select id="chartSelector"></select>
        <div id="chart" class="chart-container"></div>
    </div>
    
    <script>
        // IR from DashML compiler
        const IR = {config_json};
        
        // Data cache (browser fetches and caches)
        const dataCache = {{}};
        
        // Load data (browser responsibility!)
        async function loadData(datasetId) {{
            if (dataCache[datasetId]) return dataCache[datasetId];
            
            const dataset = IR.datasets[datasetId];
            
            if (dataset.type === 'csv') {{
                const response = await fetch(dataset.source);
                const csvText = await response.text();
                const data = parseCSV(csvText);
                dataCache[datasetId] = data;
                return data;
            }} else {{
                throw new Error(`Dataset type ${{dataset.type}} not yet supported in browser`);
            }}
        }}
        
        // Simple CSV parser
        function parseCSV(csvText) {{
            const lines = csvText.trim().split('\\n');
            const headers = lines[0].split(',').map(h => h.trim());
            const rows = [];
            
            for (let i = 1; i < lines.length; i++) {{
                const values = lines[i].split(',').map(v => v.trim());
                const row = {{}};
                headers.forEach((header, index) => {{
                    const value = values[index];
                    row[header] = isNaN(value) ? value : parseFloat(value);
                }});
                rows.push(row);
            }}
            
            return rows;
        }}
        
        // Aggregate data (browser responsibility!)
        function aggregateData(data, xCol, yCol, aggFunc) {{
            const grouped = {{}};
            
            data.forEach(row => {{
                const key = row[xCol];
                if (!grouped[key]) {{
                    grouped[key] = {{ values: [], count: 0 }};
                }}
                grouped[key].values.push(row[yCol]);
                grouped[key].count++;
            }});
            
            const result = [];
            Object.keys(grouped).forEach(key => {{
                const values = grouped[key].values;
                let aggregated;
                
                switch(aggFunc) {{
                    case 'sum':
                        aggregated = values.reduce((a, b) => a + b, 0);
                        break;
                    case 'mean':
                        aggregated = values.reduce((a, b) => a + b, 0) / values.length;
                        break;
                    case 'count':
                        aggregated = grouped[key].count;
                        break;
                    default:
                        aggregated = values.reduce((a, b) => a + b, 0);
                }}
                
                result.push({{ [xCol]: key, [yCol]: aggregated }});
            }});
            
            return result;
        }}
        
        // Render chart
        async function renderChart(chartId) {{
            const chart = IR.charts.find(c => c.id === chartId);
            if (!chart) return;
            
            // Load data (browser fetches!)
            const rawData = await loadData(chart.datasetId);
            
            // Apply filters
            let filteredData = rawData;
            chart.filters.forEach(filter => {{
                filteredData = filteredData.filter(row => {{
                    // Simple filter implementation
                    return row[filter.column] === filter.value;
                }});
            }});
            
            // Aggregate data (browser computes!)
            const aggregated = aggregateData(
                filteredData,
                chart.x.column,
                chart.y.column,
                chart.y.aggregation
            );
            
            // Prepare Plotly data
            const xValues = aggregated.map(row => row[chart.x.column]);
            const yValues = aggregated.map(row => row[chart.y.column]);
            
            const trace = {{
                x: xValues,
                y: yValues,
                type: chart.type === 'line' ? 'scatter' : chart.type,
                mode: chart.type === 'line' ? 'lines+markers' : undefined
            }};
            
            const layout = {{
                title: chart.title,
                xaxis: {{ title: chart.x.column }},
                yaxis: {{ title: chart.y.column }}
            }};
            
            Plotly.newPlot('chart', [trace], layout);
        }}
        
        // Initialize
        window.addEventListener('DOMContentLoaded', () => {{
            const selector = document.getElementById('chartSelector');
            
            // Populate chart selector
            IR.charts.forEach(chart => {{
                const option = document.createElement('option');
                option.value = chart.id;
                option.textContent = chart.title;
                selector.appendChild(option);
            }});
            
            // Render first chart
            if (IR.charts.length > 0) {{
                renderChart(IR.charts[0].id);
            }}
            
            // Handle selection change
            selector.addEventListener('change', (e) => {{
                renderChart(e.target.value);
            }});
        }});
    </script>
</body>
</html>'''
        
        return html

