# Chart Types Roadmap

## ✅ Implemented (8 types - Fully Working)

All Priority 1 chart types are now **fully implemented** across all three backends:

| Chart Type | Streamlit | Plotly | Observable | Notes |
|------------|-----------|--------|------------|-------|
| `bar` | ✅ Altair | ✅ Plotly | ✅ Plot | Vertical bar chart |
| `line` | ✅ Altair | ✅ Plotly | ✅ Plot | Line with markers |
| `scatter` | ✅ Altair | ✅ Plotly | ✅ Plot | Raw data points |
| `pie` | ✅ Altair | ✅ Plotly | ✅ D3 | Observable uses custom D3 code |
| `area` | ✅ Altair | ✅ Plotly | ✅ Plot | Filled area chart |
| `histogram` | ✅ Altair | ✅ Plotly | ✅ Plot | Bins raw data automatically |
| `stacked_bar` | ✅ Altair | ✅ Plotly | ✅ Plot | Requires `group` field |
| `grouped_bar` | ✅ Altair | ✅ Plotly | ✅ Plot | Requires `group` field |

### Implementation Details

**Data Handling:**
- **Aggregated charts** (bar, line, area, pie, stacked_bar, grouped_bar): Use `groupby` + aggregation
- **Raw data charts** (scatter, histogram): Work directly with raw data points

**Color Support:**
- Single-series charts use `primary` theme color
- Multi-series charts (pie, stacked_bar, grouped_bar) use `secondary` theme color array
- All backends properly support theme colors including `card` backgrounds (except Streamlit - platform limitation)

**Grouping Support:**
- Stacked and grouped bars require `group` field in spec
- Validator enforces this requirement
- All transformers implement multi-trace/multi-series rendering

---

## 🚧 Priority 2: Partial Backend Support

Charts that work in 2 out of 3 backends:

| Chart Type | Streamlit | Plotly | Observable | Status |
|------------|-----------|--------|------------|--------|
| `box` | ✅ `mark_boxplot()` | ✅ `type: 'box'` | ❌ Not supported | Not implemented |
| `violin` | ❌ Limited | ✅ Native | ❌ Not supported | Not implemented |

**Implementation approach:**
- Add to validator
- Implement in Streamlit + Plotly
- Observable transformer emits warning

---

## 🔮 Priority 3: Plotly-Exclusive Charts

Specialized visualizations only Plotly supports natively:

### Business/Analytics
- `treemap` - Hierarchical rectangle packing
- `sunburst` - Hierarchical radial chart
- `sankey` - Flow diagram
- `waterfall` - Cumulative effect
- `funnel` - Conversion funnel

### Scientific
- `candlestick` - Financial OHLC chart
- `3d_scatter` - 3D point cloud
- `3d_surface` - 3D height map
- `contour` - Contour/topographic plot
- `parallel_coordinates` - Multi-dimensional data

### Geographic
- `choropleth` - Geographic heatmap
- `scatter_geo` - Points on map
- `mapbox` - Custom map tiles

**Implementation approach:**
- Plotly: Full implementation
- Streamlit: Warning or fallback chart
- Observable: Warning or fallback chart

---

## 📊 Backend Capability Matrix

### Observable Plot
**Strengths:**
- Elegant, minimalist design
- Excellent for standard statistical charts
- Fast rendering

**Limitations:**
- ❌ No native pie charts (using D3 workaround ✅)
- ❌ No box plots
- ❌ No geographic visualizations
- ❌ No 3D charts
- ❌ Limited business charts

### Streamlit (Altair/Vega-Lite)
**Strengths:**
- Full statistical chart support
- Interactive widgets
- Good for data apps

**Limitations:**
- ❌ Card backgrounds don't work (platform issue)
- ❌ No 3D charts
- ❌ Limited business charts
- ⚠️ Violin plots have limited support

### Plotly
**Strengths:**
- ✅ Most comprehensive chart library
- ✅ Supports everything (statistical, business, 3D, geo)
- ✅ Full theme support
- ✅ Standalone HTML deployment

**Limitations:**
- None for basic chart types

---

## 🎯 Implementation Strategy

### Phase 1: Core Charts ✅ COMPLETE
- ✅ bar, line, scatter, pie
- ✅ area, histogram
- ✅ stacked_bar, grouped_bar

### Phase 2: Statistical Extensions 🚧
- [ ] box plots (Streamlit + Plotly)
- [ ] violin plots (Plotly only)
- [ ] Add error bars to existing charts
- [ ] Add trend lines

### Phase 3: Business Charts 🔮
- [ ] treemap, sunburst, sankey (Plotly only)
- [ ] funnel, waterfall (Plotly only)

### Phase 4: Geographic 🔮
- [ ] choropleth maps (Plotly + Streamlit)
- [ ] Requires location field support in schema
- [ ] GeoJSON data integration

### Phase 5: Advanced 🔮
- [ ] 3D visualizations (Plotly only)
- [ ] Animated charts
- [ ] Real-time data updates

---

## 📝 Schema Extensions Needed

### For Box/Violin Plots
```yaml
- type: "box"
  x: "category"  # Grouping variable
  y: "value"     # Continuous variable
  # No aggregation - shows distribution
```

### For Geographic Charts
```yaml
- type: "choropleth"
  locations: "country_code"  # ISO codes or region names
  z: "value"                 # Color intensity
  agg: "sum"
```

### For Financial Charts
```yaml
- type: "candlestick"
  x: "date"
  open: "open_price"
  high: "high_price"
  low: "low_price"
  close: "close_price"
```

---

## 🔧 Adding New Chart Types - Checklist

When implementing a new chart type:

- [ ] Add to `SUPPORTED_CHART_TYPES` in `validator.py`
- [ ] Add TypedDict documentation in `types.py`
- [ ] Update data requirement categorization:
  - [ ] Add to `CHARTS_NEED_AGGREGATION` or `CHARTS_USE_RAW_DATA`
- [ ] Implement in `streamlit.py` transformer
  - [ ] Add to `_generate_chart()` method
  - [ ] Handle aggregation correctly
  - [ ] Use theme colors
- [ ] Implement in `plotly.py` transformer
  - [ ] Add to `_generate_renderer()` (single-page)
  - [ ] Add to `_generate_javascript_pages()` (multi-page)
  - [ ] Use theme colors
- [ ] Implement in `observable.py` transformer
  - [ ] Add to `_get_plot_mark()` method
  - [ ] Handle data preparation in `_generate_chart_render()`
  - [ ] Use theme colors
- [ ] Create test case in test dashboard
- [ ] Update `README.md` chart types table
- [ ] Update this roadmap

---

## 🎨 Current Color Theme Support

All chart types support the full theme system:

- `background` - Dashboard background ✅
- `card` - Chart container (Plotly ✅, Observable ✅, Streamlit ⚠️ limited)
- `primary` - Single-series chart color ✅
- `secondary` - Multi-series colors ✅
- `text` - Labels and titles ✅
- `buttons` - UI elements ✅

Theme support is consistent across backends (except Streamlit card limitation).
