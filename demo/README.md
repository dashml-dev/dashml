# DashML demo stack

A reproducible reference environment for evaluating DashML's six backends against a single SQL data source. **Not production guidance** — for the chapter, defense, and local exploration.

## What's in the box

- **Postgres** on `:5432` — seeded with `startup_funding` (300 rows). Used by every DashML target as the data source.
- **Apache Superset** on http://localhost:8088 (admin/admin) — the destination for `dashml build --target superset`.
- **Grafana** on http://localhost:3000 (admin/admin) — auto-imports any JSON dropped into `demo/grafana-dashboards/`. A Postgres datasource is pre-provisioned.

## Spin it up

```bash
cd demo
docker compose up -d

# First boot only: wait ~60-90s for Superset to initialize.
# Watch progress with:
docker compose logs -f superset      # press Ctrl-C once you see "Listening on 0.0.0.0:8088"
```

## Push the same dashboard to all six backends

The companion spec [`examples/startup_funding_sql.dashml`](../examples/startup_funding_sql.dashml) is the SQL-mode twin of [`startup_funding.dashml`](../examples/startup_funding.dashml) — same charts, same theme, but `data:` points at the Postgres table.

```bash
# Install DashML with all runtime extras (the demo exercises every target)
pip install 'dashml-lang[all]'

# Streamlit (generates a Python app that queries Postgres at runtime)
dashml build examples/startup_funding_sql.dashml \
  --target streamlit --output build/streamlit
cd build/streamlit && cp .env.example .env && streamlit run app.py
# .env defaults already match the demo Postgres (dashml/dashml on localhost:5432)

# Plotly (Flask + HTML)
dashml build examples/startup_funding_sql.dashml \
  --target plotly --output build/plotly

# Observable Plot (Flask + HTML + D3)
dashml build examples/startup_funding_sql.dashml \
  --target observable --output build/observable

# Vega-Lite JSON
dashml build examples/startup_funding_sql.dashml \
  --target vegalite --output build/vegalite

# Superset (pushes via REST API)
dashml build examples/startup_funding_sql.dashml \
  --target superset \
  --superset-url http://localhost:8088 \
  --superset-user admin --superset-password admin

# Grafana (drops JSON into the provisioning dir; Grafana auto-imports within ~10s)
dashml build examples/startup_funding_sql.dashml \
  --target grafana --output demo/grafana-dashboards/startup_funding
```

Open the two browser tabs (Superset at :8088, Grafana at :3000) — the dashboards appear there. The Streamlit / Plotly / Observable apps run locally and read from the same Postgres.

## Tear down

```bash
docker compose down       # stops + removes containers; volumes (no named volumes here) evaporate
```

State is intentionally ephemeral — `down && up` gives you a fresh demo every time.

## Files

```
demo/
├── docker-compose.yml          # the three services
├── seed/
│   └── 01_init.sql             # CREATE TABLE + COPY FROM CSV
├── grafana-provisioning/
│   ├── datasources/
│   │   └── postgres.yaml       # wires Grafana → demo Postgres
│   └── dashboards/
│       └── dashboards.yaml     # tells Grafana to auto-import from /var/lib/grafana/dashboards
└── grafana-dashboards/         # dashml build --target grafana drops JSON here
```
