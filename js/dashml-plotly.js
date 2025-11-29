/**
 * DashML Plotly Renderer
 * Renders DashML charts using Plotly.js
 */
class DashMLPlotlyRenderer {
    constructor(transformer) {
        this.transformer = transformer;
    }

    renderChart(chart, containerId) {
        const x = chart.x;
        const y = chart.y;
        const agg = chart.agg || 'sum';
        
        const aggregated = this.transformer.aggregateData(x, y, agg);
        
        const xValues = aggregated.map(row => row[x]);
        const yValues = aggregated.map(row => row[y]);

        const trace = this._createTrace(chart.type, xValues, yValues, chart.title);
        const layout = this._createLayout(chart.title, x, y);

        Plotly.newPlot(containerId, [trace], layout, {
            responsive: true,
            displayModeBar: true
        });
    }

    _createTrace(type, xValues, yValues, title) {
        const trace = {
            x: xValues,
            y: yValues,
            name: title
        };

        switch (type) {
            case 'bar':
                trace.type = 'bar';
                trace.marker = { color: '#636EFA' };
                break;
            case 'line':
                trace.type = 'scatter';
                trace.mode = 'lines+markers';
                trace.line = { color: '#EF553B', width: 2 };
                break;
            case 'scatter':
                trace.type = 'scatter';
                trace.mode = 'markers';
                trace.marker = { size: 10, color: '#00CC96' };
                break;
            default:
                trace.type = 'bar';
        }

        return trace;
    }

    _createLayout(title, xaxis, yaxis) {
        return {
            title: {
                text: title,
                font: { size: 18 }
            },
            xaxis: {
                title: xaxis,
                showgrid: false
            },
            yaxis: {
                title: yaxis,
                showgrid: true,
                gridcolor: '#eee'
            },
            plot_bgcolor: '#fff',
            paper_bgcolor: '#fff',
            margin: { t: 60, r: 40, b: 60, l: 60 }
        };
    }

    async renderDashboard(options = {}) {
        const {
            containerId = 'dashboard',
            showTitle = true,
            showSelector = true,
            selectedChartId = null
        } = options;

        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Container #${containerId} not found`);
            return;
        }

        container.innerHTML = '';

        if (showTitle) {
            const titleEl = document.createElement('h1');
            titleEl.textContent = this.transformer.getTitle();
            titleEl.style.cssText = 'margin: 0 0 20px 0; font-family: sans-serif;';
            container.appendChild(titleEl);
        }

        try {
            await this.transformer.loadData();
        } catch (error) {
            container.innerHTML += `<div style="color: red;">Error loading data: ${error.message}</div>`;
            return;
        }

        const charts = this.transformer.getCharts();
        if (charts.length === 0) {
            container.innerHTML += '<div>No charts defined in DashML spec.</div>';
            return;
        }

        if (showSelector && !selectedChartId) {
            const selector = this._createSelector(charts, containerId);
            container.appendChild(selector);
        }

        const chartContainer = document.createElement('div');
        chartContainer.id = `${containerId}-chart`;
        chartContainer.style.cssText = 'width: 100%; height: 500px; margin-top: 20px;';
        container.appendChild(chartContainer);

        const chartToRender = selectedChartId 
            ? this.transformer.getChartById(selectedChartId)
            : charts[0];

        if (chartToRender) {
            this.renderChart(chartToRender, chartContainer.id);
        }
    }

    _createSelector(charts, containerId) {
        const wrapper = document.createElement('div');
        wrapper.style.cssText = 'margin: 10px 0;';

        const label = document.createElement('label');
        label.textContent = 'Select Chart: ';
        label.style.cssText = 'font-family: sans-serif; margin-right: 10px;';

        const select = document.createElement('select');
        select.style.cssText = 'padding: 5px 10px; font-size: 14px;';

        charts.forEach(chart => {
            const option = document.createElement('option');
            option.value = chart.id;
            option.textContent = chart.title || chart.id;
            select.appendChild(option);
        });

        select.addEventListener('change', (e) => {
            const chartId = e.target.value;
            const chart = this.transformer.getChartById(chartId);
            this.renderChart(chart, `${containerId}-chart`);
        });

        wrapper.appendChild(label);
        wrapper.appendChild(select);

        return wrapper;
    }

    renderChartById(chartId, containerId) {
        const chart = this.transformer.getChartById(chartId);
        if (chart) {
            this.renderChart(chart, containerId);
        } else {
            const container = document.getElementById(containerId);
            if (container) {
                container.innerHTML = `<div style="color: red;">Chart not found: ${chartId}</div>`;
            }
        }
    }
}

