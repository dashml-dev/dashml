# DashML Backend x Connector Test Matrix

## Matrix

| Backend | CSV | SQL (PostgreSQL) | BigQuery |
|---------|-----|------------------|----------|
| **Streamlit** | `startup_funding.dashml` | `sql_definitive.dashml` | `bigquery_definitive.dashml` |
| **Plotly** | `startup_funding.dashml` | `sql_definitive.dashml` | `bigquery_definitive.dashml` |
| **Observable** | `startup_funding.dashml` | `sql_definitive.dashml` | `bigquery_definitive.dashml` |
| **Grafana** | `startup_funding.dashml` | `sql_definitive.dashml` | N/A (needs plugin) |
| **Vega-Lite** | `startup_funding.dashml` | N/A (no runtime) | N/A (no runtime) |
| **Superset** | N/A (has own data) | `sql_definitive.dashml` | `bigquery_definitive.dashml` |

**Total testable combinations: 15**

---

## Commands

### Streamlit

```bash
# CSV
python -m dashml_new.cli build dashml_new/startup_funding.dashml -t streamlit --output output_test_streamlit_csv
streamlit run output_test_streamlit_csv/app.py

# SQL
python -m dashml_new.cli build dashml_new/sql_definitive.dashml -t streamlit --db-type postgresql --db-host ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech --db-port 5432 --db-name neondb --db-user neondb_owner --db-password npg_fm0ZpyB5CQkT --output output_test_streamlit_sql
streamlit run output_test_streamlit_sql/app.py

# BigQuery
python -m dashml_new.cli build dashml_new/bigquery_definitive.dashml -t streamlit --output output_test_streamlit_bq
streamlit run output_test_streamlit_bq/app.py
```

### Plotly

```bash
# CSV
python -m dashml_new.cli build dashml_new/startup_funding.dashml -t plotly --output output_test_plotly_csv
# Open output_test_plotly_csv/index.html in browser

# SQL
python -m dashml_new.cli build dashml_new/sql_definitive.dashml -t plotly --db-type postgresql --db-host ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech --db-port 5432 --db-name neondb --db-user neondb_owner --db-password npg_fm0ZpyB5CQkT --output output_test_plotly_sql
python output_test_plotly_sql/app.py

# BigQuery
python -m dashml_new.cli build dashml_new/bigquery_definitive.dashml -t plotly --output output_test_plotly_bq
python output_test_plotly_bq/app.py
```

### Observable

```bash
# CSV
python -m dashml_new.cli build dashml_new/startup_funding.dashml -t observable --output output_test_observable_csv
# Open output_test_observable_csv/index.html in browser

# SQL
python -m dashml_new.cli build dashml_new/sql_definitive.dashml -t observable --db-type postgresql --db-host ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech --db-port 5432 --db-name neondb --db-user neondb_owner --db-password npg_fm0ZpyB5CQkT --output output_test_observable_sql
python output_test_observable_sql/app.py

# BigQuery
python -m dashml_new.cli build dashml_new/bigquery_definitive.dashml -t observable --output output_test_observable_bq
python output_test_observable_bq/app.py
```

### Grafana

```bash
# CSV
python -m dashml_new.cli build dashml_new/startup_funding.dashml -t grafana --grafana-serve-csv 8888 --grafana-csv-host host.docker.internal --output output_test_grafana_csv
# Import output_test_grafana_csv/dashboard.json into Grafana

# SQL
python -m dashml_new.cli build dashml_new/sql_definitive.dashml -t grafana --db-type postgresql --output output_test_grafana_sql
# Import output_test_grafana_sql/dashboard.json into Grafana (select PostgreSQL datasource)
```

### Vega-Lite

```bash
# CSV (with embedded data)
python -m dashml_new.cli build dashml_new/startup_funding.dashml -t vegalite --embed-data --output output_test_vegalite_csv
# Open output_test_vegalite_csv/dashboard.vl.json in Vega Editor: https://vega.github.io/editor/

# CSV (bare mode for nvBench)
python -m dashml_new.cli build dashml_new/startup_funding.dashml -t vegalite --bare --output output_test_vegalite_bare
```

### Superset

```bash
# SQL
python -m dashml_new.cli build dashml_new/sql_definitive.dashml -t superset --db-type postgresql --db-host ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech --db-port 5432 --db-name neondb --db-user neondb_owner --db-password npg_fm0ZpyB5CQkT --superset-url http://localhost:8088 --superset-user admin --superset-password admin

# BigQuery
python -m dashml_new.cli build dashml_new/bigquery_definitive.dashml -t superset --superset-url http://localhost:8088 --superset-user admin --superset-password admin
```

---

## Checklist

For each combination, verify:

- [ ] Build completes without errors
- [ ] All chart types render (bar, line, area, pie, scatter, histogram, stacked_bar, grouped_bar, heatmap, geo, box, bubble, metric)
- [ ] Aggregation is correct (sum, mean, count)
- [ ] Sort order matches across backends
- [ ] Filters work
- [ ] Limit (top N) works
- [ ] Colors/theme applied
- [ ] Axis labels correct

## Test Results

| Backend | Connector | Build | Render | Charts OK | Notes |
|---------|-----------|-------|--------|-----------|-------|
| Streamlit | CSV | | | | |
| Streamlit | SQL | | | | |
| Streamlit | BigQuery | | | | |
| Plotly | CSV | | | | |
| Plotly | SQL | | | | |
| Plotly | BigQuery | | | | |
| Observable | CSV | | | | |
| Observable | SQL | | | | |
| Observable | BigQuery | | | | |
| Grafana | CSV | | | | |
| Grafana | SQL | | | | |
| Vega-Lite | CSV | | | | |
| Vega-Lite | CSV (bare) | | | | |
| Superset | SQL | | | | |
| Superset | BigQuery | | | | |

## Known Limitations

| Backend | Limitation |
|---------|-----------|
| **Grafana** | Box plot: not natively supported, shown as text placeholder |
| **Grafana** | Bubble color: XY chart color field only supports numbers, not categorical strings |
| **Grafana** | Heatmap: rendered as color-coded table (Grafana's native heatmap is a 2D histogram) |
| **Grafana** | Geo: markers only, no choropleth fill |
| **Superset** | Grouped/stacked bar sort direction: `x_axis_sort_asc` is stashed (removed from form_data) on reload due to missing `disableStash: true` on the control definition in Superset's `customControls.tsx`. Falls back to `default: true` (ascending). Superset bug — DashML sets the correct value via API but Superset's control stashing mechanism discards it. |
| **Vega-Lite** | SQL/BigQuery: not supported (no runtime) |
| **Vega-Lite** | Boxplot in hconcat: crashes Vega renderer, rendered solo |
| **Superset** | CSV: not supported (Superset manages own data sources) |
