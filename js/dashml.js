/**
 * DashML Core Transformer - Platform Agnostic
 * Parses DashML specs and handles data operations
 */
class DashMLTransformer {
    constructor(spec) {
        this.spec = spec;
        this.data = null;
    }

    static async fromYAML(yamlPath) {
        const response = await fetch(yamlPath);
        const yamlText = await response.text();
        const spec = jsyaml.load(yamlText);
        return new DashMLTransformer(spec);
    }

    async loadData() {
        const dataSpec = this.spec.data;
        
        if (dataSpec.type === 'csv') {
            const response = await fetch(dataSpec.path);
            const csvText = await response.text();
            this.data = this._parseCSV(csvText);
        } else {
            throw new Error(`Unsupported data type: ${dataSpec.type}`);
        }
        
        return this.data;
    }

    _parseCSV(csvText) {
        const lines = csvText.trim().split('\n');
        const headers = lines[0].split(',').map(h => h.trim());
        const rows = [];

        for (let i = 1; i < lines.length; i++) {
            const values = lines[i].split(',').map(v => v.trim());
            const row = {};
            headers.forEach((header, index) => {
                const value = values[index];
                row[header] = isNaN(value) ? value : parseFloat(value);
            });
            rows.push(row);
        }

        return rows;
    }

    getTitle() {
        return this.spec.title || 'DashML Dashboard';
    }

    getCharts() {
        return this.spec.charts || [];
    }

    getChartById(chartId) {
        return this.getCharts().find(chart => chart.id === chartId);
    }

    aggregateData(x, y, agg = 'sum') {
        if (!this.data) {
            throw new Error('Data not loaded. Call loadData() first.');
        }

        const grouped = {};
        
        this.data.forEach(row => {
            const key = row[x];
            if (!grouped[key]) {
                grouped[key] = { values: [], count: 0 };
            }
            grouped[key].values.push(row[y]);
            grouped[key].count++;
        });

        const result = [];
        Object.keys(grouped).forEach(key => {
            const values = grouped[key].values;
            let aggregated;

            switch (agg) {
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
            }

            result.push({ [x]: key, [y]: aggregated });
        });

        return result;
    }
}

