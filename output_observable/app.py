from flask import Flask, jsonify, send_from_directory, request
from google.cloud import bigquery
import json
import traceback
from datetime import date, datetime
from decimal import Decimal
import os

app = Flask(__name__)

PROJECT_ID = "big-data-project-sn"
DATASET = "sales"
TABLE_NAME = "orders"

from google.oauth2 import service_account
credentials = service_account.Credentials.from_service_account_file(
    "C:/Users/Admin/Downloads/key.json",
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
# Use the service account's own project for billing; table refs use PROJECT_ID
client = bigquery.Client(credentials=credentials)


# Per-chart SQL queries (generated at compile time)
CHART_QUERIES = {
    "total_revenue_kpi": """SELECT SUM(total_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause}""",
    "total_orders_kpi": """SELECT COUNT(order_id) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause}""",
    "avg_order_value_kpi": """SELECT AVG(total_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause}""",
    "bar_sales_by_country": """SELECT shipping_address_country AS x, SUM(total_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY shipping_address_country""",
    "pie_orders_by_status": """SELECT status AS x, COUNT(order_id) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY status""",
    "grouped_bar_country_status": """SELECT shipping_address_country AS x, status AS grp, COUNT(order_id) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY shipping_address_country, status ORDER BY y DESC""",
    "stacked_bar_payment_status": """SELECT payment_method AS x, status AS grp, COUNT(order_id) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY payment_method, status""",
    "geo_sales_by_country": """SELECT shipping_address_country AS x, SUM(total_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY shipping_address_country""",
    "line_orders_over_time": """SELECT order_date AS x, COUNT(order_id) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY order_date ORDER BY x ASC""",
    "area_revenue_over_time": """SELECT order_date AS x, SUM(total_amount) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY order_date ORDER BY x ASC""",
    "scatter_amount_vs_tax": """SELECT total_amount AS x, tax_amount AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} AND total_amount IS NOT NULL AND tax_amount IS NOT NULL""",
    "histogram_order_amounts": """SELECT total_amount AS x FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} AND total_amount IS NOT NULL""",
    "box_amount_by_status": """SELECT status AS x, total_amount AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} AND status IS NOT NULL AND total_amount IS NOT NULL""",
    "bubble_region_sales": """SELECT shipping_address_state AS grp, SUM(total_amount) AS x, SUM(tax_amount) AS y, SUM(total_amount) AS size FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} GROUP BY shipping_address_state""",
    "heatmap_country_status": """SELECT shipping_address_country AS x, status AS heatmap_y, COUNT(order_id) AS y FROM `big-data-project-sn.sales.orders` WHERE {filter_clause} AND shipping_address_country IN (SELECT shipping_address_country FROM `big-data-project-sn.sales.orders` GROUP BY shipping_address_country ORDER BY COUNT(*) DESC LIMIT 20) AND status IN (SELECT status FROM `big-data-project-sn.sales.orders` GROUP BY status ORDER BY COUNT(*) DESC LIMIT 20) GROUP BY shipping_address_country, status""",
}

CHART_STATIC_CONDITIONS = {
    "total_revenue_kpi": [],
    "total_orders_kpi": [],
    "avg_order_value_kpi": [],
    "bar_sales_by_country": [],
    "pie_orders_by_status": [],
    "grouped_bar_country_status": [],
    "stacked_bar_payment_status": [],
    "geo_sales_by_country": [],
    "line_orders_over_time": [],
    "area_revenue_over_time": [],
    "scatter_amount_vs_tax": [],
    "histogram_order_amounts": [],
    "box_amount_by_status": [],
    "bubble_region_sales": [],
    "heatmap_country_status": [],
}

ALLOWED_FILTER_FIELDS = frozenset(set())

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
    return send_from_directory('.', 'index.html')

@app.route('/api/schema')
def get_schema():
    try:
        column_types = get_column_types()
        return jsonify(column_types)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chart/<chart_id>')
def get_chart_data(chart_id):
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
    if field not in ALLOWED_FILTER_FIELDS:
        return jsonify({"error": "Field not allowed"}), 403
    try:
        query = "SELECT DISTINCT `" + field + "` FROM `big-data-project-sn.sales.orders` WHERE `" + field + "` IS NOT NULL ORDER BY 1 LIMIT 500"
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
