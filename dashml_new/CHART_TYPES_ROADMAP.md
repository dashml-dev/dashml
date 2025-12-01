# Chart Types Implementation Roadmap

## Current Status (4 types - Fully Implemented)

| Chart Type | Streamlit | Plotly | Observable | Status |
|------------|-----------|--------|------------|--------|
| `bar` | ✅ | ✅ | ✅ | Complete |
| `line` | ✅ | ✅ | ✅ | Complete |
| `scatter` | ✅ | ✅ | ✅ | Complete |
| `pie` | ✅ | ✅ | ✅ (D3) | Complete (Observable uses D3 workaround) |

---

## Priority 1: Universal Support (All Backends)

These chart types are natively supported by all three backends:

### To Implement

| Chart Type | Streamlit (Altair) | Plotly | Observable | Notes |
|------------|-------------------|--------|------------|-------|
| `area` | `mark_area()` | `type: 'scatter', fill: 'tozeroy'` | `Plot.areaY()` | Filled line chart |
| `histogram` | `mark_bar()` + `bin` | `type: 'histogram'` | `Plot.rectY()` + `bin` | Distribution of single variable |
| `stacked_bar` | `mark_bar()` + color channel | `type: 'bar', barmode: 'stack'` | `Plot.barY()` + fill channel | Stacked categories |
| `grouped_bar` | `mark_bar()` + `column` facet | `type: 'bar', barmode: 'group'` | `Plot.barY()` + `fx` channel | Grouped/clustered bars |

**Action:** Implement all 4 types across all transformers with full theme color support.

---

## Priority 2: Partial Support (Plotly + Streamlit)

These work in 2 out of 3 backends:

| Chart Type | Streamlit (Altair) | Plotly | Observable | Notes |
|------------|-------------------|--------|------------|-------|
| `box` | ✅ `mark_boxplot()` | ✅ `type: 'box'` | ❌ No native support | Box plots for distributions |
| `choropleth` | ✅ `mark_geoshape()` | ✅ Geographic maps | ❌ No geo support | Geographic heatmap |

**Action:** Implement with warnings for Observable transformer.

---

## Priority 3: Plotly Exclusive

These specialized charts only Plotly supports:

### Business Charts
- `treemap` - Hierarchical rectangles
- `sunburst` - Hierarchical radial
- `sankey` - Flow diagrams
- `waterfall` - Cumulative effect chart
- `funnel` - Conversion funnel
- `candlestick` - Financial OHLC

### Advanced Visualization
- `violin` - Distribution with density
- `3d_scatter` - 3D point cloud
- `3d_surface` - 3D height map
- `parallel_coordinates` - Multi-dimensional data

**Action:** Implement only in Plotly, warn in Streamlit/Observable.

---

## Backend Limitations Summary

### Observable Plot
**Cannot Support:**
- `box` - No box plot mark
- `pie` - Using D3 workaround ✅ (already implemented)
- Any geographic visualization
- Any 3D visualization

### Streamlit (Altair/Vega-Lite)
**Cannot Support:**
- 3D charts
- Specialized business charts (treemap, sunburst, etc.)

### Plotly
**Can Support:** Everything - most comprehensive library

---

## Implementation Strategy

1. ✅ **Priority 1 (Next):** Implement `area`, `histogram`, `stacked_bar`, `grouped_bar` in all transformers
2. **Priority 2:** Implement `box` and geo charts with Observable warnings
3. **Priority 3:** Implement Plotly-exclusive charts with appropriate warnings

For unsupported chart types:
- Call `self.warn(f"'{chart_type}' is not supported by {self.name} transformer")`
- Skip rendering or provide fallback

---

## Data Requirements

Some chart types require different data structures:

- **Single variable:** `histogram` (only needs one column)
- **Multi-series:** `stacked_bar`, `grouped_bar` (need grouping column)
- **Geographic:** `choropleth` (needs location identifiers)
- **Financial:** `candlestick` (needs OHLC columns)

This may require extending the DashML spec schema in the future.
