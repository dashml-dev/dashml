# DashML JavaScript/Plotly Integration Guide

## 🎯 Quick Start

### 1. Include Dependencies

```html
<!-- Plotly.js -->
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>

<!-- js-yaml for YAML parsing -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/js-yaml/4.1.0/js-yaml.min.js"></script>

<!-- DashML Core & Plotly Renderer -->
<script src="js/dashml.js"></script>
<script src="js/dashml-plotly.js"></script>
```

### 2. Basic Usage

```html
<div id="dashboard"></div>

<script>
async function loadDashboard() {
    const transformer = await DashMLTransformer.fromYAML('dashboard.yaml');
    const renderer = new DashMLPlotlyRenderer(transformer);
    
    await renderer.renderDashboard({
        containerId: 'dashboard'
    });
}

loadDashboard();
</script>
```

---

## 📖 Integration Examples

### Example 1: Full Dashboard (Simplest)

```html
<div id="my-dashboard"></div>

<script>
async function init() {
    const transformer = await DashMLTransformer.fromYAML('sales.yaml');
    const renderer = new DashMLPlotlyRenderer(transformer);
    
    await renderer.renderDashboard({
        containerId: 'my-dashboard',
        showTitle: true,
        showSelector: true
    });
}

init();
</script>
```

---

### Example 2: Embedded in Tabs

```html
<div class="tabs">
    <button onclick="showTab('home')">Home</button>
    <button onclick="showTab('analytics')">Analytics</button>
</div>

<div id="home-tab">Your existing content...</div>
<div id="analytics-tab" style="display: none;"></div>

<script>
let dashmlRenderer;

async function showTab(tab) {
    // Hide all tabs
    document.querySelectorAll('[id$="-tab"]').forEach(t => t.style.display = 'none');
    document.getElementById(`${tab}-tab`).style.display = 'block';
    
    // Load DashML when analytics tab is shown
    if (tab === 'analytics' && !dashmlRenderer) {
        const transformer = await DashMLTransformer.fromYAML('analytics.yaml');
        dashmlRenderer = new DashMLPlotlyRenderer(transformer);
        await dashmlRenderer.renderDashboard({
            containerId: 'analytics-tab'
        });
    }
}
</script>
```

---

### Example 3: Specific Charts Only

```html
<div class="dashboard-grid">
    <div>
        <h3>Sales by Region</h3>
        <div id="chart-region" style="height: 400px;"></div>
    </div>
    <div>
        <h3>Sales Timeline</h3>
        <div id="chart-timeline" style="height: 400px;"></div>
    </div>
</div>

<script>
async function loadCharts() {
    const transformer = await DashMLTransformer.fromYAML('sales.yaml');
    await transformer.loadData();
    const renderer = new DashMLPlotlyRenderer(transformer);
    
    // Render specific charts
    renderer.renderChartById('sales_by_region', 'chart-region');
    renderer.renderChartById('sales_over_time', 'chart-timeline');
}

loadCharts();
</script>
```

---

### Example 4: Dynamic Chart Selection

```html
<select id="chart-selector">
    <option value="sales_by_country">By Country</option>
    <option value="sales_over_time">Over Time</option>
</select>

<div id="dynamic-chart" style="height: 500px;"></div>

<script>
let transformer, renderer;

async function init() {
    transformer = await DashMLTransformer.fromYAML('dashboard.yaml');
    await transformer.loadData();
    renderer = new DashMLPlotlyRenderer(transformer);
    
    // Render first chart
    updateChart();
    
    // Listen for changes
    document.getElementById('chart-selector').addEventListener('change', updateChart);
}

function updateChart() {
    const chartId = document.getElementById('chart-selector').value;
    renderer.renderChartById(chartId, 'dynamic-chart');
}

init();
</script>
```

---

### Example 5: Multiple DashML Dashboards

```html
<div class="dashboard-container">
    <div class="sidebar">
        <button onclick="loadDepartment('sales')">Sales</button>
        <button onclick="loadDepartment('marketing')">Marketing</button>
        <button onclick="loadDepartment('operations')">Operations</button>
    </div>
    <div id="main-dashboard"></div>
</div>

<script>
async function loadDepartment(dept) {
    const transformer = await DashMLTransformer.fromYAML(`dashboards/${dept}.yaml`);
    const renderer = new DashMLPlotlyRenderer(transformer);
    
    await renderer.renderDashboard({
        containerId: 'main-dashboard',
        showTitle: true,
        showSelector: true
    });
}

// Load default
loadDepartment('sales');
</script>
```

---

### Example 6: Custom Styling & Layout

```html
<div id="custom-dashboard"></div>

<script>
async function loadCustom() {
    const transformer = await DashMLTransformer.fromYAML('dashboard.yaml');
    await transformer.loadData();
    const renderer = new DashMLPlotlyRenderer(transformer);
    
    const container = document.getElementById('custom-dashboard');
    const charts = transformer.getCharts();
    
    // Create custom grid layout
    const grid = document.createElement('div');
    grid.style.display = 'grid';
    grid.style.gridTemplateColumns = 'repeat(2, 1fr)';
    grid.style.gap = '20px';
    
    charts.forEach((chart, index) => {
        const chartDiv = document.createElement('div');
        chartDiv.id = `custom-chart-${index}`;
        chartDiv.style.height = '400px';
        chartDiv.style.background = 'white';
        chartDiv.style.padding = '20px';
        chartDiv.style.borderRadius = '8px';
        chartDiv.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
        
        const title = document.createElement('h3');
        title.textContent = chart.title;
        chartDiv.appendChild(title);
        
        const plotDiv = document.createElement('div');
        plotDiv.id = `plot-${index}`;
        plotDiv.style.height = '350px';
        chartDiv.appendChild(plotDiv);
        
        grid.appendChild(chartDiv);
        
        renderer.renderChart(chart, `plot-${index}`);
    });
    
    container.appendChild(grid);
}

loadCustom();
</script>
```

---

## 🔧 API Reference

### `DashMLTransformer`

**Platform-agnostic transformer**

```javascript
// Static method - load from YAML file
const transformer = await DashMLTransformer.fromYAML('dashboard.yaml');

// Or create from spec object
const transformer = new DashMLTransformer(specObject);

// Methods:
await transformer.loadData();              // Returns: Array of row objects
transformer.getTitle();                    // Returns: String
transformer.getCharts();                   // Returns: Array of chart objects
transformer.getChartById(chartId);         // Returns: Chart object or undefined
transformer.aggregateData(x, y, agg);      // Returns: Aggregated data array
```

### `DashMLPlotlyRenderer`

**Plotly-specific renderer**

```javascript
const renderer = new DashMLPlotlyRenderer(transformer);

// Render full dashboard
await renderer.renderDashboard({
    containerId: 'dashboard',      // Required: DOM element ID
    showTitle: true,                // Optional: Show dashboard title
    showSelector: true,             // Optional: Show chart selector
    selectedChartId: null           // Optional: Pre-select specific chart
});

// Render specific chart
renderer.renderChart(chartObject, containerId);

// Render chart by ID
renderer.renderChartById('chart-id', containerId);
```

---

## 🎨 Customization

### Custom Plotly Layout

Modify `dashml-plotly.js` to customize chart appearance:

```javascript
_createLayout(title, xaxis, yaxis) {
    return {
        title: {
            text: title,
            font: { size: 20, color: '#333' }  // Customize title
        },
        xaxis: {
            title: xaxis,
            showgrid: false,
            color: '#666'  // Custom axis color
        },
        yaxis: {
            title: yaxis,
            showgrid: true,
            gridcolor: '#eee'
        },
        plot_bgcolor: '#fafafa',  // Custom background
        paper_bgcolor: '#fff',
        margin: { t: 60, r: 40, b: 60, l: 60 }
    };
}
```

---

## 🚀 Deployment

### Option 1: Serve Locally

```bash
# Using Python
python -m http.server 8000

# Using Node.js
npx http-server -p 8000
```

Then visit: `http://localhost:8000`

### Option 2: Deploy to GitHub Pages

1. Push to GitHub
2. Settings → Pages → Deploy from branch
3. Your dashboard at: `https://username.github.io/repo-name/`

### Option 3: Netlify/Vercel

Just drag & drop your folder - done! ✅

---

## 💡 Best Practices

1. **Load data once**: Call `loadData()` before rendering multiple charts
2. **Error handling**: Always wrap in try/catch
3. **Container heights**: Set explicit heights for chart containers
4. **Responsive**: Use percentage widths for mobile support
5. **Caching**: Store transformer instance to avoid re-parsing YAML

---

## 🎓 For Your Thesis

This JavaScript implementation proves:

✅ **True platform independence** - Same DashML spec works in Python AND JavaScript  
✅ **Browser-based rendering** - No backend required  
✅ **Easy integration** - 3 lines of code to embed  
✅ **Modular architecture** - Transformer + Renderer pattern  
✅ **Production-ready** - Can be deployed anywhere

Perfect for demonstrating DashML's versatility! 🚀

