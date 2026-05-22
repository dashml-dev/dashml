"""
Observable Plot Transformer - Generates Observable Plot HTML from DashML specs
"""
import re
import sys
from typing import TYPE_CHECKING, Dict, Any, List
from pathlib import Path
import json
from .base import Transformer, TransformerError, humanize_field
from .constants import (
    CHARTS_NEED_AGGREGATION,
    CHARTS_USE_RAW_DATA,
    DEFAULT_HISTOGRAM_BINS,
    DEFAULT_PRIMARY_COLOR,
    DESIGN_TOKENS,
    TEMPORAL_FIELD_NAMES,
    DEFAULT_SORT_ORDER,
    resolve_metric_format,
    resolve_categorical_ramp,
    country_mapping_as_js,
)

# Chart types whose x-axis is discrete categorical — axis title is redundant.
_DISCRETE_X_CHART_TYPES = frozenset({"bar", "stacked_bar", "grouped_bar", "box", "pie", "heatmap"})

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

        title = spec["title"]
        html_parts = []
        html_parts.append(self._generate_html_head(title, colors))
        html_parts.append(self._generate_body_start(title, colors))

        # Data loading
        data_spec = spec["data"]
        html_parts.append(self._generate_data_loader(data_spec, spec.get("derived_fields", []), colors))

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
        card_alt = DESIGN_TOKENS["card_alt"]
        line = DESIGN_TOKENS["line"]
        line_soft = DESIGN_TOKENS["line_soft"]
        muted = DESIGN_TOKENS["muted"]
        fg_dim = DESIGN_TOKENS["fg_dim"]

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
        * {{ box-sizing: border-box; }}
        html, body {{ margin: 0; padding: 0; background: {bg_color}; color: {text_color}; }}
        body {{
            font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            min-height: 100vh;
            padding: 28px 32px 80px;
        }}
        .container {{ max-width: 1600px; margin: 0 auto; }}

        h1 {{
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.01em;
            margin: 0 0 4px;
            color: {text_color};
        }}
        .sub {{ color: {muted}; font-size: 13px; margin: 0 0 20px; }}

        /* Tabs */
        .page-tabs {{
            display: flex; gap: 24px;
            border-bottom: 1px solid {line};
            margin-bottom: 18px;
        }}
        .tab-button {{
            background: none; border: 0;
            color: {fg_dim};
            font: inherit; font-weight: 500;
            padding: 10px 2px;
            cursor: pointer;
            position: relative;
            margin-bottom: -1px;
        }}
        .tab-button:hover {{ color: {text_color}; }}
        .tab-button.active {{ color: {primary_color}; }}
        .tab-button.active::after {{
            content: ""; position: absolute;
            left: 0; right: 0; bottom: -1px;
            height: 2px; background: {primary_color}; border-radius: 2px;
        }}
        .page-description {{
            color: {muted};
            font-size: 13px;
            font-style: italic;
            margin: 4px 0 18px;
        }}

        /* Layout grids — page becomes a 4-col grid; chart cards span 2 cols */
        .page-content {{ display: none; }}
        .page-content.active {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            align-items: start;
            margin-top: 18px;
        }}
        @media (min-width: 1100px) {{
            .page-content.active {{ grid-template-columns: repeat(4, 1fr); }}
        }}
        .page-content > .filter-bar,
        .page-content > .page-description {{ grid-column: 1 / -1; }}
        .page-content > .card:not(.metric-card) {{
            grid-column: span 2;
            height: 520px;  /* uniform card height — pie + Plot.plot fit identically */
        }}
        .page-content > .card.chart-card {{ display: flex; flex-direction: column; }}
        .page-content > .card.chart-card > div[id^="chart-"] {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }}
        .page-content > div[style*="grid-template-columns"] {{ grid-column: 1 / -1; }}

        /* Card surface */
        .card {{
            background: {card_color};
            border: 1px solid {line_soft};
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 0;
            min-width: 0;
        }}
        .chart-card .chart-title {{
            font-size: 14px; font-weight: 600;
            color: {text_color};
            margin: 0 0 14px;
        }}
        /* Override Observable's default h2 (chart title) since we use chart-title now */
        .card > h2 {{
            font-size: 14px; font-weight: 600;
            color: {text_color};
            margin: 0 0 14px;
        }}

        /* KPI metric card */
        .metric-card {{ padding: 20px; }}
        .metric-title {{
            color: {muted};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 10px;
        }}
        .metric-value {{
            font-size: 32px;
            font-weight: 600;
            letter-spacing: -0.02em;
            color: {text_color};
            font-variant-numeric: tabular-nums;
            line-height: 1.1;
        }}

        /* Observable Plot SVG */
        svg {{ background: transparent; }}
        /* Tooltip readability on dark theme */
        g[aria-label="tip"] path {{ fill: {bg_color}; stroke: {line}; }}
        g[aria-label="tip"] text {{ fill: {text_color} !important; }}

        .chart-spinner {{
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; min-height: 300px; gap: 12px;
            color: {fg_dim};
        }}
        .chart-spinner .spinner {{
            width: 40px; height: 40px;
            border: 3px solid {line_soft};
            border-top-color: {primary_color};
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .chart-error {{
            display: flex; align-items: center; justify-content: center;
            min-height: 300px; color: #ff79c6;
        }}

        /* Filter bar — single + multi-select */
        .filter-bar {{
            display: flex; align-items: center; gap: 18px;
            background: {card_color};
            border: 1px solid {line_soft};
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }}
        .filter-bar-title {{
            color: {muted};
            font-size: 11px; font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.08em;
            display: inline-flex; align-items: center; gap: 6px;
            margin-right: 4px;
        }}
        .filter-item {{ display: flex; flex-direction: column; gap: 4px; }}
        .filter-item > label {{
            color: {muted};
            font-size: 11px; font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.08em;
        }}
        .filter-select-wrap {{ position: relative; display: inline-flex; align-items: center; }}
        .filter-select-wrap select,
        .ms-btn {{
            background: {card_alt};
            color: {text_color};
            border: 1px solid {line};
            border-radius: 6px;
            padding: 6px 28px 6px 10px;
            font: inherit; font-size: 13px;
            min-width: 180px;
            outline: none;
            cursor: pointer;
            transition: border-color 0.15s, box-shadow 0.15s;
            appearance: none; -webkit-appearance: none;
        }}
        .filter-select-wrap select:hover, .ms-btn:hover {{ border-color: {muted}; }}
        .filter-select-wrap select:focus,
        .ms-btn.ms-open, .ms-btn:focus {{
            border-color: {primary_color};
            box-shadow: 0 0 0 1px {primary_color};
        }}
        .filter-select-wrap .sel-arrow {{
            position: absolute; right: 9px; pointer-events: none;
            color: {muted}; flex-shrink: 0;
        }}
        .ms-wrap {{ position: relative; min-width: 180px; }}
        .ms-btn {{
            display: flex; align-items: center; justify-content: space-between;
            gap: 10px; padding: 6px 10px;
            text-align: left; width: 100%;
        }}
        .ms-btn .ms-text {{
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            color: {text_color};
        }}
        .ms-btn .ms-text.placeholder {{ color: {fg_dim}; }}
        .ms-arrow {{ color: {muted}; transition: transform 0.15s; flex-shrink: 0; }}
        .ms-btn.ms-open .ms-arrow {{ transform: rotate(180deg); }}
        .ms-panel {{
            position: absolute;
            top: calc(100% + 4px); left: 0;
            width: 100%;
            min-width: 220px;
            max-height: 280px;
            overflow-y: auto;
            overflow-x: hidden;
            background: {card_alt};
            border: 1px solid {line};
            border-radius: 8px;
            box-shadow: 0 12px 32px rgba(0,0,0,0.45);
            padding: 6px;
            z-index: 50;
            display: none;
        }}
        .ms-panel.ms-open {{ display: block; }}
        .ms-option {{
            display: flex; align-items: center; gap: 10px;
            padding: 8px 10px;
            border-radius: 5px;
            cursor: pointer;
            color: {fg_dim};
            font-size: 13px;
            user-select: none;
            min-width: 0;
        }}
        .ms-option > span {{
            min-width: 0; flex: 1 1 auto;
            overflow-wrap: anywhere;
            word-break: break-word;
        }}
        .ms-option:hover {{ background: rgba(189, 147, 249, 0.08); color: {text_color}; }}
        .ms-option input[type="checkbox"] {{
            accent-color: {primary_color};
            width: 14px; height: 14px; flex-shrink: 0; cursor: pointer;
        }}
        .filter-reset {{
            background: none;
            border: 1px solid {line};
            color: {fg_dim};
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            margin-left: auto;
            font-family: inherit;
            transition: color 0.15s, border-color 0.15s;
        }}
        .filter-reset:hover {{ color: {text_color}; border-color: {muted}; }}
    </style>
</head>"""

    def _generate_body_start(self, title: str, colors: Dict[str, str]) -> str:
        return f"""<body>
  <div class="container">
    <h1>{title}</h1>"""

    def _generate_html_footer(self) -> str:
        return """  </div>
</body>
</html>"""

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

    def _generate_data_loader(self, data_spec: Dict[str, Any], derived_fields: list = None, colors: Dict[str, str] = None) -> str:
        """Generate JavaScript to load CSV data"""
        data_type = data_spec["type"]
        path = Path(data_spec.get("csv_path") or data_spec["path"]).name
        sequential_scheme = (colors or {}).get("sequential", "blues")
        sequential_ramp_js = json.dumps(resolve_categorical_ramp(sequential_scheme))

        if data_type == "csv":
            return f"""
    <script>
        // Load and parse CSV data
        let dashmlData = [];
        // World topojson for geo charts (loaded on demand)
        window.worldTopojson = null;

        // Shared design tokens (transformer-side visual relationships).
        // Categorical ramp matches theme.sequential — sequential_scheme={sequential_scheme!r}.
        const SEQUENTIAL_RAMP = {sequential_ramp_js};

        // Continuous ramp interpolation — used for sorted-bar / pie / bubble coloring.
        function sequentialRamp(n) {{
            const stops = SEQUENTIAL_RAMP;
            if (n <= 1) return [stops[Math.floor(stops.length / 2)]];
            const hexToRgb = h => [parseInt(h.slice(1,3),16), parseInt(h.slice(3,5),16), parseInt(h.slice(5,7),16)];
            const rgbToHex = rgb => '#' + rgb.map(v => Math.round(v).toString(16).padStart(2,'0')).join('');
            const lerpAt = t => {{
                const segments = stops.length - 1;
                const scaled = Math.max(0, Math.min(segments, t * segments));
                const idx = Math.min(segments - 1, Math.floor(scaled));
                const frac = scaled - idx;
                const a = hexToRgb(stops[idx]);
                const b = hexToRgb(stops[idx + 1]);
                return rgbToHex(a.map((v, i) => v + (b[i] - v) * frac));
            }};
            return Array.from({{length: n}}, (_, i) => lerpAt(i / (n - 1)));
        }}

        // For CSV, getEffectiveType returns explicit type or detects from data
        function getEffectiveType(column, explicitType) {{
            if (explicitType) return explicitType;
            // For CSV, we don't have schema info, so return undefined
            // The sorting logic will handle runtime type detection
            return undefined;
        }}

        // Quote-aware CSV line parser
        function parseCsvLine(line) {{
            const out = []; let cur = ''; let inQ = false;
            for (let i = 0; i < line.length; i++) {{
                const c = line[i];
                if (inQ) {{
                    if (c === '"' && line[i + 1] === '"') {{ cur += '"'; i++; }}
                    else if (c === '"') {{ inQ = false; }}
                    else {{ cur += c; }}
                }} else {{
                    if (c === ',') {{ out.push(cur); cur = ''; }}
                    else if (c === '"') {{ inQ = true; }}
                    else {{ cur += c; }}
                }}
            }}
            out.push(cur);
            return out;
        }}

        // Load both data and world topojson in parallel
        Promise.all([
            fetch('{path}').then(r => r.text()),
            fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json').then(r => r.json())
        ])
            .then(([csvText, worldData]) => {{
                dashmlData = parseCSV(csvText);
{self._build_derived_js_code(derived_fields or [], var_name="dashmlData", indent="                ")}
                // Convert topojson to geojson features for Observable Plot
                window.worldTopojson = topojson.feature(worldData, worldData.objects.countries);
                window.__dashmlData = dashmlData;
                if (typeof populateCsvFilters === 'function') populateCsvFilters(dashmlData);
                renderAllCharts();
            }})
            .catch(error => {{
                console.error('Error loading data:', error);
                document.body.innerHTML += '<p style="color: red;">Error loading data: ' + error.message + '</p>';
            }});

        function parseCSV(csvText) {{
            const lines = csvText.trim().split('\\n').filter(line => line.trim());
            const headers = parseCsvLine(lines[0]).map(h => h.trim());
            const rows = [];

            for (let i = 1; i < lines.length; i++) {{
                const values = parseCsvLine(lines[i]);
                if (values.length !== headers.length) continue;

                const row = {{}};
                headers.forEach((header, index) => {{
                    const value = values[index] != null ? String(values[index]).trim() : '';
                    // Try to parse as number first
                    if (!isNaN(value) && value !== '') {{
                        row[header] = parseFloat(value);
                    }}
                    // Keep dates as ISO strings and other strings as-is
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
            const m = format.match(/,?\.(\d+)f/);
            const decimals = m ? parseInt(m[1]) : 0;
            const str = n.toLocaleString('en-US', {{minimumFractionDigits: decimals, maximumFractionDigits: decimals}});
            return str + (suffix || '');
        }}

        // ─── Dashboard filter UI (CSV mode) ─────────────────────────────
        function closeAllMs() {{
            document.querySelectorAll('.ms-panel.ms-open').forEach(p => p.classList.remove('ms-open'));
            document.querySelectorAll('.ms-btn.ms-open').forEach(b => b.classList.remove('ms-open'));
        }}
        function toggleMs(btn, pageId, field) {{
            const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
            if (!panel) return;
            const opening = !panel.classList.contains('ms-open');
            closeAllMs();
            if (opening) {{ panel.classList.add('ms-open'); btn.classList.add('ms-open'); }}
        }}
        document.addEventListener('click', function(e) {{
            if (!e.target.closest('.ms-wrap')) closeAllMs();
        }});
        document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeAllMs(); }});

        function updateMsLabel(pageId, field) {{
            const panel = document.getElementById('ms-panel-' + pageId + '-' + field);
            const textEl = document.querySelector('#ms-' + pageId + '-' + field + ' .ms-text');
            if (!panel || !textEl) return;
            const checked = Array.from(panel.querySelectorAll('input[type="checkbox"]:checked'));
            const n = checked.length;
            if (n === 0) {{
                textEl.textContent = 'All';
                textEl.classList.add('placeholder');
            }} else if (n === 1) {{
                textEl.textContent = checked[0].value;
                textEl.classList.remove('placeholder');
            }} else {{
                textEl.textContent = n + ' selected';
                textEl.classList.remove('placeholder');
            }}
        }}

        function readPageFilters(pageId) {{
            const out = {{}};
            document.querySelectorAll('select[id^="filter-' + pageId + '-"]').forEach(sel => {{
                const m = sel.id.match(/^filter-[^-]+-(.+)$/);
                if (m && sel.value) out[m[1]] = [sel.value];
            }});
            document.querySelectorAll('.ms-panel[id^="ms-panel-' + pageId + '-"]').forEach(panel => {{
                const m = panel.id.match(/^ms-panel-[^-]+-(.+)$/);
                if (!m) return;
                const checked = Array.from(panel.querySelectorAll('input[type=checkbox]:checked')).map(cb => cb.value);
                if (checked.length) out[m[1]] = checked;
            }});
            return out;
        }}

        function applyDashboardFilter(pageId) {{
            const filters = readPageFilters(pageId);
            const allData = window.__dashmlData || [];
            const filtered = allData.filter(row => Object.entries(filters).every(([f, vals]) =>
                vals.map(String).includes(String(row[f]))));
            dashmlData = filtered;
            // Clear ALL chart containers across all pages before re-rendering —
            // renderAllCharts() rebuilds every chart, so without clearing the
            // non-active page's containers, new plots get appended on top of
            // the old ones.
            document.querySelectorAll('[id^="chart-"]').forEach(el => {{
                if (!el.classList.contains('metric-value')) el.innerHTML = '';
            }});
            renderAllCharts();
        }}

        function resetFilters(pageId) {{
            document.querySelectorAll('select[id^="filter-' + pageId + '-"]').forEach(s => {{ s.value = ''; }});
            document.querySelectorAll('.ms-panel[id^="ms-panel-' + pageId + '-"] input[type=checkbox]').forEach(cb => {{ cb.checked = false; }});
            document.querySelectorAll('.ms-panel[id^="ms-panel-' + pageId + '-"]').forEach(panel => {{
                const m = panel.id.match(/^ms-panel-([^-]+)-(.+)$/);
                if (m) updateMsLabel(m[1], m[2]);
            }});
            applyDashboardFilter(pageId);
        }}

        function populateCsvFilters(data) {{
            document.querySelectorAll('select[id^="filter-"]').forEach(sel => {{
                const m = sel.id.match(/^filter-[^-]+-(.+)$/);
                if (!m) return;
                const field = m[1];
                const values = Array.from(new Set(data.map(d => d[field]).filter(v => v !== '' && v != null))).sort();
                values.forEach(v => {{
                    const opt = document.createElement('option');
                    opt.value = v; opt.textContent = v;
                    sel.appendChild(opt);
                }});
            }});
            document.querySelectorAll('.ms-panel').forEach(panel => {{
                const m = panel.id.match(/^ms-panel-([^-]+)-(.+)$/);
                if (!m) return;
                const pageId = m[1]; const field = m[2];
                const values = Array.from(new Set(data.map(d => d[field]).filter(v => v !== '' && v != null))).sort();
                panel.innerHTML = values.map(v => {{
                    const esc = String(v).replace(/"/g, '&quot;');
                    return '<label class="ms-option"><input type="checkbox" value="' + esc +
                           '" onchange="updateMsLabel(\\'' + pageId + '\\',\\'' + field +
                           '\\');applyDashboardFilter(\\'' + pageId + '\\')"> <span>' + v + '</span></label>';
                }}).join('');
            }});
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

            # Page-level filter bar (single-select + multi-select)
            page_filters = page.get("filters", [])
            if page_filters:
                page_html.append(f'        <div class="filter-bar" id="filters-{page_id}">')
                page_html.append(
                    '          <div class="filter-bar-title">'
                    '<svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor">'
                    '<path d="M1 2h14l-5 7v4l-4-2V9z"/></svg> Filters</div>'
                )
                for f in page_filters:
                    field = f["field"]
                    label_text = f.get("label", humanize_field(field))
                    ftype = f.get("type", "select")
                    if ftype == "multiselect":
                        page_html.append(
                            f'          <div class="filter-item">'
                            f'<label>{label_text}</label>'
                            f'<div class="ms-wrap" id="ms-{page_id}-{field}">'
                            f'<button type="button" class="ms-btn" onclick="toggleMs(this,\'{page_id}\',\'{field}\')">'
                            f'<span class="ms-text placeholder">All</span>'
                            f'<svg class="ms-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>'
                            f'</button>'
                            f'<div class="ms-panel" id="ms-panel-{page_id}-{field}"></div>'
                            f'</div></div>'
                        )
                    else:
                        page_html.append(
                            f'          <div class="filter-item">'
                            f'<label>{label_text}</label>'
                            f'<div class="filter-select-wrap">'
                            f'<select id="filter-{page_id}-{field}" onchange="applyDashboardFilter(\'{page_id}\')">'
                            f'<option value="">All</option></select>'
                            f'<svg class="sel-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>'
                            f'</div></div>'
                        )
                page_html.append(
                    f'          <button class="filter-reset" onclick="resetFilters(\'{page_id}\')">&#x2715; Reset</button>'
                )
                page_html.append('        </div>')

            # Separate metric cards from regular chart cards
            metric_htmls = []
            regular_htmls = []
            for chart in charts:
                chart_id = chart["id"]
                chart_title = chart.get("title", chart_id)
                if chart.get("type") == "metric":
                    metric_htmls.append(f"""        <div class="card metric-card">
            <div class="metric-title">{chart_title}</div>
            <div id="chart-{page_id}-{chart_id}" class="metric-value">—</div>
        </div>""")
                else:
                    regular_htmls.append(f"""        <div class="card chart-card">
            <h3 class="chart-title">{chart_title}</h3>
            <div id="chart-{page_id}-{chart_id}"></div>
        </div>""")

                # Generate render function for this chart
                render_functions.append(self._generate_chart_render(chart, colors, page_id))

            # Metric cards first (they display inline via CSS)
            page_html.extend(metric_htmls)

            # Regular chart cards — optionally wrapped in CSS Grid
            columns = page.get("layout", {}).get("columns")
            if columns and regular_htmls:
                page_html.append(f'        <div style="display: grid; grid-template-columns: repeat({columns}, 1fr); gap: 16px;">')
                page_html.extend(regular_htmls)
                page_html.append(f'        </div>')
            else:
                page_html.extend(regular_htmls)

            page_html.append('    </div>')
            page_contents.append("\n".join(page_html))

        # Combine everything
        tabs_html = f"""    <div class="page-tabs">
{chr(10).join(tabs)}
    </div>"""

        # Geo normalization helpers (if any chart is geo)
        geo_helpers_js = ""
        has_geo = any(
            c.get("type") == "geo"
            for p in pages
            for c in p.get("charts", [])
        )
        if has_geo:
            geo_helpers_js = "\n        " + self._generate_geo_js_helpers_inline()

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
{geo_helpers_js}
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
        y = chart.get("y", "")
        agg = chart.get("agg", "sum")
        # When normalizer moved y→group for count agg, use "count" as the y column
        if not y and agg == "count" and chart_type != "metric":
            y = "count"
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
                    elif op == "range" and isinstance(f["value"], list) and len(f["value"]) == 2:
                        filter_conditions.append(f"d['{field}'] >= {f['value'][0]} && d['{field}'] <= {f['value'][1]}")
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

        # Pie charts use D3 directly instead of Observable Plot.
        # CSV path: bind `data_X` here from the CSV aggregation expression.
        # The pie helper itself is source-agnostic (assumes the binding exists).
        if chart_type == "pie":
            pie_body = self._generate_d3_pie_chart(safe_var_name, x, y, container_id, colors)
            return f"            const data_{safe_var_name} = {data_code};\n{pie_body}"

        body = self._emit_chart_render_body(chart, colors, container_id, safe_var_name)
        return f"            // Chart: {chart_id}\n            const data_{safe_var_name} = {data_code};\n{body}"

    def _emit_chart_render_body(self, chart: Dict[str, Any], colors: Dict[str, str], container_id: str, safe_var_name: str) -> str:
        """Source-agnostic Observable Plot rendering body.

        Assumes the caller has already bound `data_{safe_var_name}` to a
        pre-aggregated array of records. Emits the marks, axis config, scales,
        margins and the final `Plot.plot(...)` + DOM append.

        This is the canonical renderer for every non-pie chart type, called by
        both the CSV path (after computing the JS aggregation expression) and
        the SQL/BigQuery path (after the Flask backend's pre-aggregated rows
        are remapped to original field names).
        """
        chart_type = chart["type"]
        x = chart.get("x", "")
        y = chart.get("y", "")
        agg = chart.get("agg", "sum")
        if not y and agg == "count" and chart_type != "metric":
            y = "count"
        group = chart.get("group")
        x_type = chart.get("x_type")
        bins = chart.get("bins", DEFAULT_HISTOGRAM_BINS)
        sort_field = chart.get("sort")
        sort_order = chart.get("sort_order", DEFAULT_SORT_ORDER)
        size_field = chart.get("size")

        primary_color = colors.get("primary", DEFAULT_PRIMARY_COLOR)
        sequential_scheme = colors.get("sequential", "blues")

        mark_code = self._get_plot_mark(
            chart_type, x, y, group, primary_color,
            safe_var_name, bins, size_field=size_field,
            sequential=sequential_scheme, geo_encoding=chart.get("geo_encoding"),
            sort_field=sort_field, sort_order=sort_order,
            y_scale=chart.get("y_scale"),
            bg_color=colors["background"],
            card_bg=colors["card"],
        )

        # Inject annotation + reference-line marks into the marks array
        mark_code = self._inject_extra_marks(mark_code, chart, data_ref=f"data_{safe_var_name}")

        # Merge log-scale type into existing axis options inside mark_code
        mark_code = self._merge_scale_into_mark_code(mark_code, chart)

        # Determine if x axis is temporal - prefer explicit x_type, fall back to field name heuristics
        temporal_fields = ['date', 'time', 'timestamp', 'datetime', 'created_at', 'updated_at']
        is_temporal_x = x_type == "date" or (x_type is None and x.lower() in temporal_fields)

        scale_config = ""
        if is_temporal_x:
            scale_config = f"""x: {{ type: "utc" }},
                """

        # Log scale: build top-level scale overrides for axes that don't already
        # appear in mark_code (e.g. line/scatter where _get_plot_mark omits x:/y:)
        log_scale_config = self._axis_scale_options_js(chart)
        if log_scale_config:
            marks_end = mark_code.find(']')
            after_marks = mark_code[marks_end:] if marks_end != -1 else ""
            for axis in ("x", "y"):
                if chart.get(f"{axis}_scale") == "log" and f"{axis}:" not in after_marks:
                    scale_config += f"""{axis}: {{ type: "log" }},
                """

        # Determine if chart has categorical x-axis (needs more bottom margin for rotated labels)
        categorical_types = {"bar", "grouped_bar", "stacked_bar", "heatmap"}
        margin_bottom = 130 if chart_type in categorical_types else 48
        margin_right = 80 if chart_type in {"bubble", "scatter"} else 16
        margin_top = 56 if chart_type in {"bubble", "scatter"} else 24
        margin_left = 90 if chart_type in {"bubble", "scatter"} else 80

        # Consolidated x/y axis options
        x_opts: list[str] = []
        y_opts: list[str] = []
        if chart_type not in _DISCRETE_X_CHART_TYPES:
            hx = humanize_field(x)
            if hx:
                x_opts.append(f'label: {json.dumps(hx)}')
        hy = humanize_field(y)
        if hy and chart_type != "heatmap":
            y_opts.append(f'label: {json.dumps(hy)}')
        marks_end = mark_code.find(']')
        after_marks = mark_code[marks_end:] if marks_end != -1 else ""
        if chart.get("x_scale") == "log" and "x:" not in after_marks:
            x_opts.append('type: "log"')
        if chart.get("y_scale") == "log" and "y:" not in after_marks:
            y_opts.append('type: "log"')
        if is_temporal_x and "x:" not in after_marks:
            x_opts.append('type: "utc"')
        axis_config = ""
        if x_opts:
            axis_config += f'x: {{ {", ".join(x_opts)} }},\n                '
        if y_opts:
            axis_config += f'y: {{ {", ".join(y_opts)} }},\n                '

        fg_dim = DESIGN_TOKENS["fg_dim"]

        return f"""            const plot_{safe_var_name} = Plot.plot({{
                {mark_code},
                {axis_config}marginLeft: {margin_left},
                marginBottom: {margin_bottom},
                marginTop: {margin_top},
                marginRight: {margin_right},
                height: 380,
                grid: true,
                style: {{
                    background: "transparent",
                    color: "{fg_dim}",
                    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
                    fontSize: 11
                }},
                width: undefined
            }});
            document.getElementById('{container_id}').appendChild(plot_{safe_var_name});"""

    def _generate_d3_pie_chart(self, var_name: str, x: str, y: str, container_id: str, colors: Dict[str, str]) -> str:
        """Generate D3 pie chart code with light→dark sequential ramp + on-slice labels.

        Uses the global `SEQUENTIAL_RAMP` constant emitted by the data loader so
        the colors stay in sync with the bar-chart ramp and respect theme.sequential.

        The caller is responsible for binding `data_{var_name}` to a pre-aggregated
        array of `{{x_field, y_field}}` rows — this helper is source-agnostic and
        does not load or aggregate data itself.
        """
        card_bg = colors.get('card', '#2e3040')
        return f"""            // D3 Pie Chart
            // Fixed render size — keeps text sized predictably regardless of card width
            const pieSize_{var_name} = 360;
            const radius_{var_name} = pieSize_{var_name} / 2 - 10;

            const pie_{var_name} = d3.pie().value(d => d.{y}).sort(null);
            const arc_{var_name} = d3.arc().innerRadius(0).outerRadius(radius_{var_name});
            const labelArc_{var_name} = d3.arc()
                .innerRadius(radius_{var_name} * 0.6)
                .outerRadius(radius_{var_name} * 0.6);

            // Reuse the dashboard's SEQUENTIAL_RAMP (emitted in data loader) so
            // pie colors stay consistent with the bar ramp and theme.sequential.
            function rampAt_{var_name}(t) {{
                const stops = SEQUENTIAL_RAMP;
                const segments = stops.length - 1;
                const scaled = Math.max(0, Math.min(segments, t * segments));
                const idx = Math.min(segments - 1, Math.floor(scaled));
                const frac = scaled - idx;
                const a = d3.color(stops[idx]);
                const b = d3.color(stops[idx + 1]);
                return d3.interpolateRgb(a, b)(frac);
            }}
            const sliceColors_{var_name} = data_{var_name}.map((_, i) =>
                rampAt_{var_name}(i / Math.max(1, data_{var_name}.length - 1)));

            const totalY_{var_name} = d3.sum(data_{var_name}, d => d.{y});

            const svg_{var_name} = d3.create("svg")
                .attr("width", pieSize_{var_name})
                .attr("height", pieSize_{var_name})
                .attr("viewBox", [-pieSize_{var_name} / 2, -pieSize_{var_name} / 2, pieSize_{var_name}, pieSize_{var_name}])
                .attr("style", "display: block; margin: 0 auto;");

            const slices_{var_name} = svg_{var_name}.selectAll("path")
                .data(pie_{var_name}(data_{var_name}))
                .join("path")
                .attr("fill", (d, i) => sliceColors_{var_name}[i])
                .attr("d", arc_{var_name})
                .attr("stroke", "{card_bg}")
                .attr("stroke-width", 1);
            slices_{var_name}.append("title")
                .text(d => `${{d.data.{x}}}: ${{d.data.{y}}}`);

            // Radial labels: rotate each label along the slice's centroid angle
            // so small slices get tilted text instead of overlapping with neighbors
            // (matches Plotly's `insidetextorientation: "radial"`).
            const labelGroups_{var_name} = svg_{var_name}.selectAll("g.label")
                .data(pie_{var_name}(data_{var_name}))
                .join("g")
                .attr("class", "label")
                .attr("transform", d => {{
                    const [cx, cy] = labelArc_{var_name}.centroid(d);
                    const angleRad = (d.startAngle + d.endAngle) / 2;
                    let rotDeg = (angleRad * 180 / Math.PI) - 90;
                    // Flip so text never appears upside down
                    if (rotDeg > 90) rotDeg -= 180;
                    if (rotDeg < -90) rotDeg += 180;
                    return `translate(${{cx}}, ${{cy}}) rotate(${{rotDeg}})`;
                }})
                .style("display", d => (d.endAngle - d.startAngle) < 0.18 ? "none" : null);

            labelGroups_{var_name}.append("text")
                .attr("text-anchor", "middle")
                .attr("dy", "-0.25em")
                .style("font-size", "11px")
                .style("font-weight", "600")
                .style("fill", "#1a1b24")
                .text(d => d.data.{x});

            labelGroups_{var_name}.append("text")
                .attr("text-anchor", "middle")
                .attr("dy", "0.9em")
                .style("font-size", "11px")
                .style("fill", "#1a1b24")
                .text(d => {{
                    const pct = (d.data.{y} / totalY_{var_name}) * 100;
                    return pct.toFixed(1) + "%";
                }});

            document.getElementById('{container_id}').appendChild(svg_{var_name}.node());"""

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
                elif op == "range" and isinstance(f["value"], list) and len(f["value"]) == 2:
                    filter_conditions.append(f"d['{field}'] >= {f['value'][0]} && d['{field}'] <= {f['value'][1]}")

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
                elif op == "range" and isinstance(f["value"], list) and len(f["value"]) == 2:
                    filter_conditions.append(f"d['{field}'] >= {f['value'][0]} && d['{field}'] <= {f['value'][1]}")

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
                elif op == "range" and isinstance(f["value"], list) and len(f["value"]) == 2:
                    filter_conditions.append(f"d['{field}'] >= {f['value'][0]} && d['{field}'] <= {f['value'][1]}")

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

    def _get_plot_mark(self, chart_type: str, x: str, y: str, group: str, color: str, data_var: str, bins: int = DEFAULT_HISTOGRAM_BINS, size_field: str = None, sequential: str = "blues", geo_encoding: str = None, sort_field: str = None, sort_order: str = "asc", y_scale: str = None, *, bg_color: str, card_bg: str) -> str:
        """Generate Observable Plot mark specification

        TODO: [SRP] This method is very long (~114 lines) with many if/elif branches
        Consider splitting into separate methods per chart type
        Fix: _get_bar_mark(), _get_line_mark(), _get_scatter_mark(), etc.
        """
        if chart_type == "bar":
            # When sorted by y with no group, color bars with a continuous
            # sequential ramp so rank reads as a free second visual channel.
            # Note: use `.at(i)` not `[i]` — `]` inside the marks array would
            # confuse _inject_extra_marks which looks for the first `]` to
            # insert reference-line marks.
            use_ramp = sort_field == "y"
            if use_ramp:
                fill_expr = f"(d, i) => sequentialRamp(data_{data_var}.length).at(i)"
            else:
                fill_expr = f'"{color}"'
            return f"""marks: [
                    Plot.barY(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: {fill_expr},
                        sort: null,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    domain: data_{data_var}.map(d => d.{x}),
                    tickRotate: -35
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
            if group:
                return f"""marks: [
                    Plot.dot(data_{data_var}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{group}",
                        r: "{size_ref}",
                        tip: true
                    }}),
                    Plot.text(
                        (() => {{
                            const m_{data_var} = d3.max(data_{data_var}, dd => Math.abs(dd["{size_ref}"]));
                            return data_{data_var}.filter(d => Math.sqrt(Math.abs(d["{size_ref}"]) / m_{data_var}) > 0.6);
                        }})(),
                        {{ x: "{x}", y: "{y}", text: "{group}", dy: -36, fontSize: 11 }}
                    ),
                    Plot.text(
                        (() => {{
                            const m_{data_var} = d3.max(data_{data_var}, dd => Math.abs(dd["{size_ref}"]));
                            return data_{data_var}.filter(d => {{
                                const r = Math.sqrt(Math.abs(d["{size_ref}"]) / m_{data_var});
                                return r > 0.3 && r <= 0.6;
                            }});
                        }})(),
                        {{ x: "{x}", y: "{y}", text: "{group}", dy: -24, fontSize: 11 }}
                    ),
                    Plot.text(
                        (() => {{
                            const m_{data_var} = d3.max(data_{data_var}, dd => Math.abs(dd["{size_ref}"]));
                            return data_{data_var}.filter(d => Math.sqrt(Math.abs(d["{size_ref}"]) / m_{data_var}) <= 0.3);
                        }})(),
                        {{ x: "{x}", y: "{y}", text: "{group}", dy: -14, fontSize: 11 }}
                    )
                ],
                r: {{ range: [6, 28] }},
                color: {{
                    domain: data_{data_var}.map(d => d.{group}),
                    range: sequentialRamp(data_{data_var}.length)
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
                    scheme: "{sequential}",
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
            # On log y, rect baseline (y1=0) is undefined; use y1=1 and drop the
            # y=0 rule so the y-domain doesn't get extended to -∞.
            if y_scale == "log":
                return f"""marks: [
                    Plot.rectY(data_{data_var}, Plot.binX({{y2: "count", thresholds: {bins}}}, {{
                        x: "{x}",
                        y1: () => 1,
                        fill: "{color}",
                        tip: true
                    }}))
                ]"""
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
            # Observable Plot stacks by default when using fill with categorical data.
            # Group fill uses the sequential ramp so stacked layers read as
            # tonal shades of theme.primary — same visual language as the
            # sorted-bar / pie / bubble ramps. A 1px stroke in the card color
            # carves visible borders between adjacent shaded segments so the
            # layer boundaries don't disappear when shades sit close together.
            if sort_field == "y":
                sign = "" if sort_order == "asc" else "-"
                x_domain = f"d3.groupSort(data_{data_var}, g => {sign}d3.sum(g, d => d.{y}), d => d.{x})"
            else:
                x_domain = f"[...new Set(data_{data_var}.map(d => d.{x}))]"
            # Stable stack order: rows sorted by group field alphabetically.
            # Without this, stacks build in the source data's encounter order,
            # which can shuffle within each x bin and mangle the sequential
            # ramp (adjacent shades land next to each other instead of
            # progressing through the ramp).
            sorted_data = f"[...data_{data_var}].sort((a, b) => String(a.{group}).localeCompare(String(b.{group})))"
            group_domain = f"[...new Set({sorted_data}.map(d => d.{group}))]"
            return f"""marks: [
                    Plot.barY({sorted_data}, {{
                        x: "{x}",
                        y: "{y}",
                        fill: "{group}",
                        stroke: "{card_bg}",
                        strokeWidth: 1,
                        tip: true
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    domain: {x_domain}
                }},
                color: {{
                    domain: {group_domain},
                    range: sequentialRamp({group_domain}.length)
                }}"""

        elif chart_type == "grouped_bar":
            # Observable Plot groups bars using fx channel for faceting.
            # Same tonal-ramp treatment as stacked_bar (see comment above) —
            # plus the same alphabetical sort by group so bars within each
            # facet land in a consistent order across facets.
            if sort_field == "y":
                sign = "" if sort_order == "asc" else "-"
                fx_domain = f"d3.groupSort(data_{data_var}, g => {sign}d3.sum(g, d => d.{y}), d => d.{x})"
            else:
                fx_domain = f"[...new Set(data_{data_var}.map(d => d.{x}))]"
            sort_mark = f', sort: {{x: "-y"}}' if sort_field == "y" and sort_order == "desc" else (f', sort: {{x: "y"}}' if sort_field == "y" else "")
            sorted_data = f"[...data_{data_var}].sort((a, b) => String(a.{group}).localeCompare(String(b.{group})))"
            group_domain = f"[...new Set({sorted_data}.map(d => d.{group}))]"
            return f"""marks: [
                    Plot.barY({sorted_data}, {{
                        fx: "{x}",
                        x: "{group}",
                        y: "{y}",
                        fill: "{group}",
                        tip: true{sort_mark}
                    }}),
                    Plot.ruleY([0])
                ],
                x: {{
                    paddingInner: 0.1,
                    axis: null
                }},
                fx: {{
                    domain: {fx_domain},
                    padding: 0.2
                }},
                color: {{
                    domain: {group_domain},
                    range: sequentialRamp({group_domain}.length)
                }}"""

        elif chart_type == "geo":
            # Choropleth map using Observable Plot with world topojson.
            # Sphere / graticule / border / unknown colors must adapt to the
            # background so countries without data stay visible but recede on
            # dark themes instead of glowing white.
            geo_enc_js = f'"{geo_encoding}"' if geo_encoding else "null"
            # Note: dark/light decisions are baked at compile time using the
            # theme's background lightness — same logic the SQL path used.
            is_dark = self._is_dark_theme(bg_color)
            sphere_color = "#1a1a2e" if is_dark else "#f8f8f8"
            unknown_color = "#2a2a3e" if is_dark else "#e0e0e0"
            border_color = "#555570" if is_dark else "#ccc"
            return f"""marks: (() => {{
                    const enc = {geo_enc_js} || detectGeoEncoding(data_{data_var}.map(d => d.{x}));
                    const geoLookup = new Map(data_{data_var}.map(d => [normalizeCountryToTopo(d.{x}, enc).toLowerCase(), d.{y}]));
                    return [
                        Plot.sphere({{fill: "{sphere_color}", stroke: "{border_color}"}}),
                        Plot.graticule({{stroke: "{border_color}40", strokeWidth: 0.5}}),
                        Plot.geo(window.worldTopojson, {{
                            fill: d => {{
                                const topoName = d.properties ? d.properties.name : null;
                                if (!topoName) return null;
                                return geoLookup.get(topoName.toLowerCase()) ?? null;
                            }},
                            stroke: "{border_color}",
                            strokeWidth: 0.5,
                            tip: true
                        }})
                    ];
                }})(),
                projection: "equal-earth",
                color: {{
                    type: "linear",
                    scheme: "{sequential}",
                    unknown: "{unknown_color}",
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

        # If output is a directory with Flask app, run Flask
        if output_path_obj.is_dir() and (output_path_obj / "app.py").exists():
            return f"cd {output_path} && {sys.executable} app.py"

        # Otherwise serve directory with http.server (index.html served at /)
        serve_dir = output_path_obj if output_path_obj.is_dir() else output_path_obj.parent
        return f"cd {serve_dir} && echo Dashboard available at: http://localhost:5001 && {sys.executable} -m http.server 5001"

    def _generate_geo_js_helpers_inline(self) -> str:
        """Emit JS mapping tables + detectGeoEncoding + normalizeCountryToTopo for inline script blocks."""
        mapping_js = country_mapping_as_js(target="topojson")
        return f"""// Geo country normalization
        {mapping_js.replace(chr(10), chr(10) + "        ")}
        function detectGeoEncoding(values) {{
            const sample = values.filter(v => v != null && v !== '').slice(0, 20);
            if (sample.every(v => /^[A-Z]{{2}}$/.test(String(v)))) return 'iso2';
            if (sample.every(v => /^[A-Z]{{3}}$/.test(String(v)))) return 'iso3';
            return 'name';
        }}
        function normalizeCountryToTopo(value, encoding) {{
            const v = String(value).trim();
            if (!v) return v;
            if (encoding === 'iso2') return iso2ToTopo[v.toUpperCase()] || v;
            if (encoding === 'iso3') return iso3ToTopo[v.toUpperCase()] || v;
            return aliasToTopo[v.toLowerCase()] || v;
        }}"""

    def _generate_flask_app(self, spec: "NormalizedSpec", data_spec: Dict[str, Any]) -> str:
        """Generate Flask backend that connects to SQL database"""
        # Connection string is constructed at runtime from environment variables
        # (DASHML_DB_*); no credentials are baked into the generated source.

        schema = data_spec["sql_schema"]
        table_name = data_spec["sql_table"]

        # Build per-chart queries
        table_ref = f"{schema}.{table_name}"
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

        # Build derived CTE for filter queries
        from dashml_new.core.normalizer import DashMLNormalizer
        derived_fields = spec.get("derived_fields", [])
        derived_cte_template = DashMLNormalizer._build_derived_cte(derived_fields)
        if derived_cte_template:
            derived_cte_resolved = derived_cte_template.replace("{table_ref}", table_ref)
            derived_filter_source = "__derived"
        else:
            derived_cte_resolved = ""
            derived_filter_source = table_ref

        from .secrets import emit_sql_env_loader
        sql_env_loader = emit_sql_env_loader()

        return f'''from flask import Flask, jsonify, send_from_directory, Response, request
from sqlalchemy import create_engine
import pandas as pd

# Database credentials are loaded from environment variables (DASHML_DB_*).
# See SECRETS.md next to this file for configuration patterns.
{sql_env_loader}
app = Flask(__name__)

SCHEMA = "{schema}"
TABLE_NAME = "{table_name}"

engine = create_engine(
    DATABASE_URL,
    connect_args={{"options": "-c lc_messages=C"}} if _DB_TYPE == "postgresql" else {{}},
)

# Per-chart SQL queries (generated at compile time)
{chart_queries_code}

{chart_static_code}

{allowed_fields_code}

# Derived CTE for filter queries (empty string if no derived fields)
DERIVED_CTE = """{derived_cte_resolved}"""
DERIVED_FILTER_SOURCE = "{derived_filter_source}"

def build_filter_clause(chart_id, request_args):
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

    def _generate_flask_app_bigquery(self, spec: "NormalizedSpec", data_spec: Dict[str, Any]) -> str:
        """Generate Flask backend that connects to BigQuery.

        Project ID is required at build time (it is embedded into SQL queries
        as part of the fully-qualified table reference) and is not a secret.
        Service account credentials path is read from the DASHML_BQ_CREDENTIALS
        environment variable at runtime.
        """
        db_config = spec["db_config"]
        project = db_config["project"]

        dataset = data_spec["bq_dataset"]
        table_name = data_spec["bq_table"]

        table_ref = f"`{project}.{dataset}.{table_name}`"

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

        # Build derived CTE for filter queries
        from dashml_new.core.normalizer import DashMLNormalizer
        derived_fields = spec.get("derived_fields", [])
        derived_cte_template = DashMLNormalizer._build_derived_cte(derived_fields)
        if derived_cte_template:
            derived_cte_resolved = derived_cte_template.replace("{table_ref}", table_ref)
            derived_filter_source = "__derived"
        else:
            derived_cte_resolved = ""
            derived_filter_source = table_ref

        from .secrets import emit_bq_env_loader
        bq_env_loader = emit_bq_env_loader(project)

        return f'''from flask import Flask, jsonify, send_from_directory, request
from google.cloud import bigquery
import json
import traceback
from datetime import date, datetime
from decimal import Decimal

# BigQuery credentials and project are loaded from environment variables
# (DASHML_BQ_PROJECT, DASHML_BQ_CREDENTIALS).
# See SECRETS.md next to this file for configuration patterns.
{bq_env_loader}
app = Flask(__name__)

DATASET = "{dataset}"
TABLE_NAME = "{table_name}"

# Per-chart SQL queries (generated at compile time)
{chart_queries_code}

{chart_static_code}

{allowed_fields_code}

# Derived CTE for filter queries (empty string if no derived fields)
DERIVED_CTE = """{derived_cte_resolved}"""
DERIVED_FILTER_SOURCE = "{derived_filter_source}"

def build_filter_clause(chart_id, request_args):
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

    def _generate_sql_frontend(self, spec: "NormalizedSpec") -> str:
        """Generate HTML frontend that fetches from Flask API"""
        colors = spec["style"]
        title = spec["title"]

        html_parts = []
        html_parts.append(self._generate_html_head(title, colors))
        html_parts.append(self._generate_body_start(title, colors))

        # Data loading from API
        html_parts.append(self._generate_sql_data_loader(colors))

        # Always use pages (normalizer guarantees pages[] exists)
        html_parts.append(self._generate_sql_pages_structure(spec["pages"], colors))

        html_parts.append(self._generate_html_footer())

        return "\n".join(html_parts)

    def _generate_sql_data_loader(self, colors: Dict[str, str]) -> str:
        """Generate JavaScript to set up async per-chart loading.

        Emits the same `SEQUENTIAL_RAMP` / `sequentialRamp()` helpers the CSV
        loader exposes — chart-rendering code is source-agnostic and references
        these as globals.
        """
        block = self._sql_loader_template()
        visual_helpers = self._emit_visual_helpers_js(colors)
        return block.replace("__SQL_VISUAL_HELPERS__", visual_helpers)

    def _emit_visual_helpers_js(self, colors: Dict[str, str]) -> str:
        """Theme-derived JS constants shared by every chart renderer.

        Both the CSV loader (`_generate_data_loader`) and the SQL/BigQuery
        loader emit this so renderers can reference `SEQUENTIAL_RAMP` and
        `sequentialRamp()` without caring about the data source.
        """
        sequential_scheme = colors.get("sequential", "blues")
        sequential_ramp_js = json.dumps(resolve_categorical_ramp(sequential_scheme))
        return f"""        // Shared design tokens (transformer-side visual relationships).
        // Categorical ramp matches theme.sequential — sequential_scheme={sequential_scheme!r}.
        const SEQUENTIAL_RAMP = {sequential_ramp_js};

        // Continuous ramp interpolation — used for sorted-bar / pie / bubble coloring.
        function sequentialRamp(n) {{
            const stops = SEQUENTIAL_RAMP;
            if (n <= 1) return [stops[Math.floor(stops.length / 2)]];
            const hexToRgb = h => [parseInt(h.slice(1,3),16), parseInt(h.slice(3,5),16), parseInt(h.slice(5,7),16)];
            const rgbToHex = rgb => '#' + rgb.map(v => Math.round(v).toString(16).padStart(2,'0')).join('');
            const lerpAt = t => {{
                const segments = stops.length - 1;
                const scaled = Math.max(0, Math.min(segments, t * segments));
                const idx = Math.min(segments - 1, Math.floor(scaled));
                const frac = scaled - idx;
                const a = hexToRgb(stops[idx]);
                const b = hexToRgb(stops[idx + 1]);
                return rgbToHex(a.map((v, i) => v + (b[i] - v) * frac));
            }};
            return Array.from({{length: n}}, (_, i) => lerpAt(i / (n - 1)));
        }}
"""

    def _sql_loader_template(self) -> str:
        return """
    <style>
        .filter-bar {
            display: flex;
            gap: 16px;
            align-items: flex-end;
            flex-wrap: wrap;
            padding: 14px 18px;
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid rgba(128,128,128,0.12);
            box-shadow: 0 1px 4px rgba(0,0,0,0.12);
        }
        .filter-bar-title {
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
        }
        .filter-item {
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .filter-item > label {
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: .07em;
            opacity: .55;
        }
        .filter-select-wrap {
            position: relative;
            display: inline-flex;
            align-items: center;
        }
        .filter-select-wrap select {
            appearance: none;
            -webkit-appearance: none;
            background: rgba(128,128,128,0.08);
            color: inherit;
            border: 1px solid rgba(128,128,128,0.22);
            border-radius: 7px;
            padding: 7px 32px 7px 12px;
            font-size: 13px;
            cursor: pointer;
            min-width: 150px;
            outline: none;
            transition: border-color 0.15s, box-shadow 0.15s;
            font-family: inherit;
        }
        .filter-select-wrap select:hover { border-color: rgba(128,128,128,0.45); }
        .filter-select-wrap select:focus { border-color: #6c63ff; box-shadow: 0 0 0 2px #6c63ff33; }
        .filter-select-wrap .sel-arrow {
            position: absolute;
            right: 9px;
            pointer-events: none;
            opacity: .45;
            flex-shrink: 0;
        }
        .ms-wrap { position: relative; }
        .ms-btn {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            background: rgba(128,128,128,0.08);
            color: inherit;
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
        }
        .ms-btn:hover { border-color: rgba(128,128,128,0.45); }
        .ms-btn.ms-open, .ms-btn:focus { border-color: #6c63ff; box-shadow: 0 0 0 2px #6c63ff33; }
        .ms-count {
            background: #6c63ff;
            color: #fff;
            border-radius: 10px;
            padding: 1px 7px;
            font-size: 11px;
            font-weight: 600;
            display: none;
        }
        .ms-count.visible { display: inline; }
        .ms-arrow { opacity: .45; transition: transform 0.15s; flex-shrink: 0; }
        .ms-btn.ms-open .ms-arrow { transform: rotate(180deg); }
        .ms-panel {
            position: absolute;
            top: calc(100% + 5px);
            left: 0;
            z-index: 200;
            background: #1e1e2e;
            border: 1px solid rgba(128,128,128,0.25);
            border-radius: 9px;
            padding: 6px;
            min-width: 190px;
            max-height: 230px;
            overflow-y: auto;
            box-shadow: 0 8px 28px rgba(0,0,0,0.3);
            display: none;
        }
        .ms-panel.ms-open { display: block; }
        .ms-option {
            display: flex;
            align-items: center;
            gap: 9px;
            padding: 7px 9px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            user-select: none;
            transition: background 0.1s;
        }
        .ms-option:hover { background: rgba(128,128,128,0.1); }
        .ms-option input[type="checkbox"] {
            accent-color: #6c63ff;
            width: 14px;
            height: 14px;
            cursor: pointer;
            flex-shrink: 0;
        }
        .filter-reset {
            align-self: flex-end;
            background: none;
            border: 1px solid rgba(128,128,128,0.2);
            color: inherit;
            padding: 7px 14px;
            border-radius: 7px;
            font-size: 12px;
            cursor: pointer;
            opacity: .55;
            transition: opacity 0.15s, border-color 0.15s;
            font-family: inherit;
        }
        .filter-reset:hover { opacity: 1; border-color: rgba(128,128,128,0.5); }
    </style>
    <script>
__SQL_VISUAL_HELPERS__
        // World topojson for geo charts
        window.worldTopojson = null;

        // Load world topojson once; expose a promise that any geo chart awaits
        // before rendering, eliminating the data-vs-topojson race condition.
        window.worldTopojsonReady = fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json')
            .then(r => r.json())
            .then(worldData => {
                window.worldTopojson = topojson.feature(worldData, worldData.objects.countries);
            })
            .catch(err => console.warn('Could not load world topojson:', err));

        // Format a metric scalar value
        function formatMetric(value, format, suffix) {
            if (value === null || value === undefined || isNaN(value)) return 'N/A';
            const n = parseFloat(value);
            const m = format.match(/,?\.(\d+)f/);
            const decimals = m ? parseInt(m[1]) : 0;
            const str = n.toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
            return str + (suffix || '');
        }

        async function loadChart(containerId, chartId, renderFn, extraParams) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = '<div class="chart-spinner"><div class="spinner"></div><span>Loading...</span></div>';
            try {
                const url = '/api/chart/' + chartId + (extraParams ? '?' + extraParams : '');
                const [resp] = await Promise.all([fetch(url), window.worldTopojsonReady]);
                if (!resp.ok) {
                    const body = await resp.json().catch(() => ({}));
                    throw new Error(body.error || 'HTTP ' + resp.status);
                }
                const data = await resp.json();
                container.innerHTML = '';
                renderFn(data);
            } catch (err) {
                container.innerHTML = '<div class="chart-error">Error loading chart: ' + err.message + '</div>';
                console.error('Chart ' + chartId + ' failed:', err);
            }
        }

        async function loadMetric(containerId, chartId, renderFn, extraParams) {
            const el = document.getElementById(containerId);
            if (!el) return;
            el.textContent = '…';
            try {
                const url = '/api/chart/' + chartId + (extraParams ? '?' + extraParams : '');
                const resp = await fetch(url);
                if (!resp.ok) {
                    const body = await resp.json().catch(() => ({}));
                    throw new Error(body.error || 'HTTP ' + resp.status);
                }
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
        text_color = colors.get("text", "#000000")

        tabs = []
        page_contents = []
        load_calls = []
        render_fn_assignments = []

        for i, page in enumerate(pages):
            page_id = page["id"]
            title = page.get("title", page_id)
            description = page.get("description", "")
            charts = page.get("charts", [])
            page_filters = page.get("filters", [])

            active_class = " active" if i == 0 else ""
            tabs.append(f'        <button class="tab-button{active_class}" onclick="showPage(\'{page_id}\', this)">{title}</button>')

            page_html = [f'    <div id="page-{page_id}" class="page-content{active_class}">']
            if description:
                page_html.append(f'        <p class="page-description">{description}</p>')

            # Filter bar HTML for pages that have filters
            if page_filters:
                page_html.append('        <div class="filter-bar">')
                page_html.append(
                    '            <div class="filter-bar-title">'
                    '<svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor">'
                    '<path d="M1 2h14l-5 7v4l-4-2V9z"/></svg> Filters</div>'
                )
                for f in page_filters:
                    field = f["field"]
                    label_text = f.get("label", field.replace("_", " ").title())
                    ftype = f.get("type", "select")
                    if ftype == "multiselect":
                        page_html.append(
                            f'            <div class="filter-item">'
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
                        page_html.append(
                            f'            <div class="filter-item">'
                            f'<label>{label_text}</label>'
                            f'<div class="filter-select-wrap">'
                            f'<select id="filter-{page_id}-{field}" onchange="applyDashboardFilter(\'{page_id}\')">'
                            f'<option value="">All</option></select>'
                            f'<svg class="sel-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>'
                            f'</div></div>'
                        )
                page_html.append(
                    f'            <button class="filter-reset" onclick="resetFilters(\'{page_id}\')">&#x2715; Reset</button>'
                )
                page_html.append('        </div>')

            # Separate metric cards from regular chart cards
            metric_htmls = []
            regular_htmls = []
            for chart in charts:
                chart_id = chart["id"]
                chart_title = chart.get("title", chart_id)
                container_id = f"chart-{page_id}-{chart_id}"

                if chart.get("type") == "metric":
                    metric_htmls.append(f"""        <div class="card metric-card">
            <div class="metric-title">{chart_title}</div>
            <div id="{container_id}" class="metric-value">—</div>
        </div>""")
                    render_fn = self._generate_sql_chart_render_fn(chart, colors, container_id)
                    render_fn_assignments.append(f"        window['renderFn_{chart_id}'] = {render_fn};")
                    load_calls.append(f"        loadMetric('{container_id}', '{chart_id}', window['renderFn_{chart_id}'])")
                else:
                    regular_htmls.append(f"""        <div class="card">
            <h2>{chart_title}</h2>
            <div id="{container_id}"></div>
        </div>""")
                    render_fn = self._generate_sql_chart_render_fn(chart, colors, container_id)
                    render_fn_assignments.append(f"        window['renderFn_{chart_id}'] = {render_fn};")
                    load_calls.append(f"        loadChart('{container_id}', '{chart_id}', window['renderFn_{chart_id}'])")

            # Metric cards first (they display inline via CSS)
            page_html.extend(metric_htmls)

            # Regular chart cards — optionally wrapped in CSS Grid
            columns = page.get("layout", {}).get("columns")
            if columns and regular_htmls:
                page_html.append(f'        <div style="display: grid; grid-template-columns: repeat({columns}, 1fr); gap: 16px;">')
                page_html.extend(regular_htmls)
                page_html.append(f'        </div>')
            else:
                page_html.extend(regular_htmls)

            page_html.append('    </div>')
            page_contents.append("\n".join(page_html))

        # Build PAGE_CHARTS map for dashboard filter JS
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

        tabs_html = f"""    <div class="page-tabs">
{chr(10).join(tabs)}
    </div>"""

        render_fn_assignments_str = "\n".join(render_fn_assignments)
        load_calls_str = ",\n".join(load_calls)

        # Geo normalization helpers (if any chart is geo)
        geo_helpers_sql_js = ""
        has_geo = any(
            c.get("type") == "geo"
            for p in pages
            for c in p.get("charts", [])
        )
        if has_geo:
            geo_helpers_sql_js = "\n        " + self._generate_geo_js_helpers_inline()

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
{geo_helpers_sql_js}
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
                const containerId = 'chart-' + pageId + '-' + chartId;
                if (window['renderFn_' + chartId]) {{
                    loadChart(containerId, chartId, window['renderFn_' + chartId], params);
                }}
            }});
            pageInfo.metrics.forEach(chartId => {{
                const containerId = 'chart-' + pageId + '-' + chartId;
                if (window['renderFn_' + chartId]) {{
                    loadMetric(containerId, chartId, window['renderFn_' + chartId], params);
                }}
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
                    .catch(err => console.warn('Could not load options for ' + field + ':', err));
            }}
        }}

        // Store render functions on window so applyDashboardFilter can re-invoke them
{render_fn_assignments_str}

        // Initialize filter dropdowns
        Object.keys(PAGE_CHARTS).forEach(pageId => loadFilterOptions(pageId));

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

    # ------------------------------------------------------------------
    # Helpers: annotations, reference lines, log scale
    # ------------------------------------------------------------------

    def _annotation_marks_js(self, chart: Dict[str, Any], data_ref: str = "data") -> str:
        """Return JS snippet(s) for Plot.text() annotation marks.

        Each annotation is: {text, x, y, color (optional)}.
        *data_ref* is the JS variable holding the chart data array — used
        only for field-name references; annotations carry literal x/y values.
        """
        annotations = chart.get("annotations")
        if not annotations:
            return ""
        parts = []
        for ann in annotations:
            text_val = json.dumps(ann.get("text", ""))
            x_val = json.dumps(ann.get("x"))
            y_val = ann.get("y")
            # y can be numeric or string
            y_js = json.dumps(y_val) if isinstance(y_val, str) else str(y_val)
            color = ann.get("color", "currentColor")
            parts.append(
                f'Plot.text([{{x: {x_val}, y: {y_js}}}], '
                f'{{x: "x", y: "y", text: d => {text_val}, '
                f'fontSize: 12, fill: "{color}", dy: -8}})'
            )
        return ",\n                    ".join(parts)

    def _reference_lines_marks_js(self, chart: Dict[str, Any]) -> str:
        """Return JS snippet(s) for Plot.ruleY() / Plot.ruleX() reference-line marks.

        Each ref line is: {axis, value, label (optional), color (optional), style (optional)}.
        Defaults to the design-token amber so benchmark lines don't read as errors.
        style mapping: solid → (none), dashed → "4,4", dotted → "1,3".
        """
        ref_lines = chart.get("reference_lines")
        if not ref_lines:
            return ""
        _dash_map = {"solid": "", "dashed": "4,4", "dotted": "1,3"}
        amber = DESIGN_TOKENS["amber"]
        parts = []
        for rl in ref_lines:
            axis = rl.get("axis", "y")
            value = rl["value"]
            color = rl.get("color", amber)
            style = rl.get("style", "dashed")
            dash = _dash_map.get(style, "4,4")
            rule_fn = "Plot.ruleY" if axis == "y" else "Plot.ruleX"
            opts = f'stroke: "{color}", strokeWidth: 2'
            if dash:
                opts += f', strokeDasharray: "{dash}"'
            parts.append(f'{rule_fn}([{json.dumps(value)}], {{{opts}}})')
            # Optional label — right-anchored on the chart edge with a stroke
            # halo (using the card surface color) so it reads against any data
            # behind it.
            card_bg = DESIGN_TOKENS["card_alt"]
            label = rl.get("label")
            if label:
                label_js = json.dumps(f"  {label}  ")
                if axis == "y":
                    parts.append(
                        f'Plot.text([{{y: {json.dumps(value)}}}], '
                        f'{{y: "y", text: d => {label_js}, '
                        f'fontSize: 12, fill: "{color}", fontWeight: 700, '
                        f'stroke: "{card_bg}", strokeWidth: 4, paintOrder: "stroke", '
                        f'frameAnchor: "right", dx: -4, dy: -6}})'
                    )
                else:
                    parts.append(
                        f'Plot.text([{{x: {json.dumps(value)}}}], '
                        f'{{x: "x", text: d => {label_js}, '
                        f'fontSize: 12, fill: "{color}", fontWeight: 700, '
                        f'stroke: "{card_bg}", strokeWidth: 4, paintOrder: "stroke", '
                        f'frameAnchor: "top", dx: 4, dy: 10}})'
                    )
        return ",\n                    ".join(parts)

    def _inject_extra_marks(self, mark_code: str, chart: Dict[str, Any], data_ref: str = "data") -> str:
        """Append annotation + reference-line marks into an existing mark_code string.

        *mark_code* has the form ``marks: [...], x: {...}, ...``. We need the
        ``]`` that closes the marks **array**, not the first one in the string
        (inner mark calls like ``Plot.ruleY([0])`` or array subscripts like
        ``data.at(0)`` would otherwise split the injected snippet). Bracket-
        match from the marks array's opening ``[``.
        """
        extras = []
        ann = self._annotation_marks_js(chart, data_ref)
        if ann:
            extras.append(ann)
        ref = self._reference_lines_marks_js(chart)
        if ref:
            extras.append(ref)
        if not extras:
            return mark_code
        extra_str = ",\n                    ".join(extras)
        start = mark_code.find('[')
        if start == -1:
            return mark_code
        depth = 0
        end = -1
        in_str = None
        for i in range(start, len(mark_code)):
            ch = mark_code[i]
            if in_str:
                if ch == in_str and mark_code[i - 1] != '\\':
                    in_str = None
            elif ch in ('"', "'"):
                in_str = ch
            elif ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            return mark_code
        return mark_code[:end] + ",\n                    " + extra_str + "\n                " + mark_code[end:]

    def _axis_scale_options_js(self, chart: Dict[str, Any]) -> str:
        """Return JS options for log-scale axes to merge into Plot.plot() options.

        Returns a string like ``x: { type: "log" }, y: { type: "log" },``
        or empty string if no log scales are configured.
        """
        parts = []
        if chart.get("x_scale") == "log":
            parts.append('x: { type: "log" }')
        if chart.get("y_scale") == "log":
            parts.append('y: { type: "log" }')
        if not parts:
            return ""
        return ", ".join(parts) + ","

    def _merge_scale_into_mark_code(self, mark_code: str, chart: Dict[str, Any]) -> str:
        """Merge log-scale type into existing axis options inside mark_code.

        mark_code may already contain ``x: { ... }`` or ``y: { ... }`` axis
        option objects.  If x_scale or y_scale is "log", we inject
        ``type: "log"`` into the existing object (if present) or leave
        the top-level scale_config to handle it.
        """
        for axis in ("x", "y"):
            scale = chart.get(f"{axis}_scale")
            if scale != "log":
                continue
            # Try to find `x: {` or `y: {` (as a top-level option, not inside marks)
            # We look for the pattern after the marks array closes
            marks_end = mark_code.find(']')
            if marks_end == -1:
                continue
            after_marks = mark_code[marks_end:]
            # Pattern: `x: {` or `y: {` — we want to inject `type: "log",` right after the `{`
            import re as _re
            # Match axis option like:  x: {  or  y: {
            # Be careful to match the axis letter as a standalone token
            pattern = _re.compile(r'(\b' + axis + r'\s*:\s*\{)')
            m = pattern.search(after_marks)
            if m:
                insert_pos = marks_end + m.end()
                mark_code = mark_code[:insert_pos] + f' type: "log",' + mark_code[insert_pos:]
        return mark_code

    def _generate_sql_chart_render_fn(self, chart: Dict[str, Any], colors: Dict[str, str], container_id: str) -> str:
        """Wrap the source-agnostic chart body in a `function(data)` shell.

        The Flask backend delivers pre-aggregated rows with canonical column
        aliases (``x``, ``y``, ``grp``, ``size``, ``heatmap_y``). We remap them
        back to the chart's original field names so the canonical body can use
        the same field references as the CSV path — eliminating every per-chart
        SQL-vs-CSV branch.
        """
        chart_id = chart["id"]
        chart_type = chart["type"]
        safe_var = chart_id.replace('-', '_')

        # Metric stays a one-liner — no Plot.plot, no D3 — so it bypasses the
        # canonical body and reads the single pre-aggregated value directly.
        if chart_type == "metric":
            format_str = resolve_metric_format(chart.get("format", "integer"))
            suffix = chart.get("suffix", "")
            return f"""function(data) {{
            const value = (data && data[0] && data[0].y !== undefined) ? parseFloat(data[0].y) : null;
            const el = document.getElementById('{container_id}');
            if (el) el.textContent = formatMetric(value, '{format_str}', '{suffix}');
        }}"""

        remap_js = self._sql_remap_to_original_names(chart)
        bind_data = f"const data_{safe_var} = data.map(d => ({remap_js}));"

        if chart_type == "pie":
            x = chart.get("x", "")
            y = chart.get("y", "") or ("count" if chart.get("agg") == "count" else "")
            pie_body = self._generate_d3_pie_chart(safe_var, x, y, container_id, colors)
            return f"function(data) {{\n            {bind_data}\n{pie_body}\n        }}"

        body = self._emit_chart_render_body(chart, colors, container_id, safe_var)
        return f"function(data) {{\n            {bind_data}\n{body}\n        }}"

    def _sql_remap_to_original_names(self, chart: Dict[str, Any]) -> str:
        """JS object literal mapping SQL canonical aliases back to the chart's
        original field names.

        Returns a fragment usable inside ``data.map(d => ( ... ))`` — e.g.
        ``{ "industry": d.x, "funding_amount": d.y, "stage": d.grp }``.
        Lets every non-metric chart go through the same render body whether
        the data came from CSV, SQL or BigQuery.
        """
        chart_type = chart["type"]
        x = chart.get("x")
        y = chart.get("y")
        agg = chart.get("agg", "sum")
        if not y and agg == "count" and chart_type != "metric":
            y = "count"
        group = chart.get("group")
        size_field = chart.get("size")

        # pandas serializes NUMERIC/DECIMAL columns as JSON strings. Plot's
        # numeric marks (binX, dot, line, area) silently render nothing when
        # fed strings — so cast any field that's used as a quantitative
        # channel. Categorical x (bar / pie / heatmap / grouped / stacked /
        # box) and date x (line / area) stay as-is so Plot's own type
        # detection runs.
        numeric_x_charts = {"scatter", "histogram", "bubble"}
        cast_x = chart_type in numeric_x_charts

        # Histogram is single-axis — the spec carries a y field for schema
        # consistency but the SQL projection only emits x, and Plot.binX
        # derives its own y from bin counts. Skip y in the remap to avoid
        # collapsing into a duplicate-keyed object literal when y == x.
        skip_y = chart_type == "histogram"

        parts = []
        if x:
            parts.append(f'"{x}": +d.x' if cast_x else f'"{x}": d.x')
        if y and not skip_y:
            # y is always quantitative for charts that emit one (sum/mean/count
            # outputs, raw numeric scatter/box values).
            parts.append(f'"{y}": +d.y')
        if group:
            # heatmap aliases group→heatmap_y in the SQL projection; everything
            # else aliases it to grp. group is a categorical channel so no cast.
            src = "heatmap_y" if chart_type == "heatmap" else "grp"
            parts.append(f'"{group}": d.{src}')
        if size_field:
            parts.append(f'"{size_field}": +d.size')
        return "{ " + ", ".join(parts) + " }"

