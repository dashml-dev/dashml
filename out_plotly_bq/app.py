from flask import Flask, jsonify, send_from_directory
from google.cloud import bigquery
import json
import traceback
from datetime import date, datetime
from decimal import Decimal

# BigQuery credentials and project are loaded from environment variables
# (DASHML_BQ_PROJECT, DASHML_BQ_CREDENTIALS).
# See SECRETS.md and .env.example next to this file.
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ID = os.environ.get("DASHML_BQ_PROJECT", "big-data-project-sn")

_BQ_CREDENTIALS = os.environ.get("DASHML_BQ_CREDENTIALS")
if _BQ_CREDENTIALS:
    from google.oauth2 import service_account
    _credentials = service_account.Credentials.from_service_account_file(
        _BQ_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    client = bigquery.Client(credentials=_credentials, project=PROJECT_ID)
else:
    client = bigquery.Client(project=PROJECT_ID)

app = Flask(__name__)

DATASET = "sales"
TABLE_NAME = "orders"

# Per-chart SQL queries (generated at compile time)
CHART_QUERIES = {
    "total_funding_kpi": """SELECT SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause}""",
    "total_deals_kpi": """SELECT COUNT(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause}""",
    "bar_by_industry": """SELECT industry AS x, SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY industry ORDER BY y DESC""",
    "pie_by_stage": """SELECT stage AS x, COUNT(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY stage ORDER BY x ASC""",
    "line_over_time": """SELECT funding_date AS x, SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY funding_date ORDER BY x ASC""",
    "scatter_funding_vs_valuation": """SELECT funding_amount AS x, valuation AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} AND funding_amount IS NOT NULL AND valuation IS NOT NULL""",
    "geo_by_country": """SELECT country AS x, SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY country ORDER BY x ASC""",
    "top_countries": """SELECT country AS x, SUM(funding_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY country ORDER BY y DESC LIMIT 10""",
}

CHART_STATIC_CONDITIONS = {
    "total_funding_kpi": [],
    "total_deals_kpi": [],
    "bar_by_industry": [],
    "pie_by_stage": [],
    "line_over_time": [],
    "scatter_funding_vs_valuation": [],
    "geo_by_country": [],
    "top_countries": [],
}

ALLOWED_FILTER_FIELDS = frozenset(set())

# Derived CTE for filter queries (empty string if no derived fields)
DERIVED_CTE = """"""
DERIVED_FILTER_SOURCE = "`big-data-project-sn.sales.orders`"

def build_filter_clause(chart_id, request_args):
    """Build SQL WHERE body from static per-chart conditions + runtime dashboard filters."""
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

# Cache for column types (fetched once from INFORMATION_SCHEMA)
_column_types_cache = None

def get_column_types():
    """Fetch column types from INFORMATION_SCHEMA and map to simple types"""
    global _column_types_cache
    if _column_types_cache is not None:
        return _column_types_cache

    try:
        query = f"""
            SELECT column_name, data_type
            FROM `{PROJECT_ID}.{DATASET}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{TABLE_NAME}'
        """
        query_job = client.query(query)
        results = query_job.result()

        type_mapping = {}
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
        print(f"Warning: Could not fetch column types: {e}")
        return {}

def serialize(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

@app.route('/')
def index():
    """Serve the HTML frontend"""
    return send_from_directory('.', 'index.html')

@app.route('/api/schema')
def get_schema():
    """Return column types from INFORMATION_SCHEMA"""
    try:
        column_types = get_column_types()
        return jsonify(column_types)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chart/<chart_id>')
def get_chart_data(chart_id):
    """Fetch pre-aggregated data for a specific chart"""
    from flask import request
    query_template = CHART_QUERIES.get(chart_id)
    if not query_template:
        return jsonify({"error": "Unknown chart"}), 404
    try:
        filter_clause = build_filter_clause(chart_id, request.args)
        query = query_template.format(filter_clause=filter_clause)
        print(f"[BQ] chart={chart_id} query={query[:200]}")
        query_job = client.query(query)
        results = query_job.result()
        data = [dict(row) for row in results]
        return app.response_class(
            response=json.dumps(data, default=serialize),
            mimetype='application/json'
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/filter/<field>')
def get_filter_options(field):
    """Return DISTINCT values for a filter field (used to populate dropdowns)"""
    from flask import request
    if field not in ALLOWED_FILTER_FIELDS:
        return jsonify({"error": "Field not allowed"}), 403
    try:
        query = DERIVED_CTE + " SELECT DISTINCT " + field + " FROM " + DERIVED_FILTER_SOURCE + " WHERE " + field + " IS NOT NULL ORDER BY 1 LIMIT 500"
        print(f"[BQ] filter={field} query={query[:200]}")
        query_job = client.query(query)
        results = query_job.result()
        values = [str(row[0]) for row in results if row[0] is not None]
        return jsonify(sorted(values))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask server with BigQuery backend...")
    print(f"Project: {PROJECT_ID}")
    print(f"Dataset: {DATASET}")
    print(f"Table: {TABLE_NAME}")
    print(f"Dashboard available at: http://localhost:5001")
    app.run(debug=True, port=5001)
