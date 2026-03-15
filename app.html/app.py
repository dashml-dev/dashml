from flask import Flask, jsonify, send_from_directory, Response
from sqlalchemy import create_engine
import pandas as pd

app = Flask(__name__)

# Database configuration
DATABASE_URL = "postgresql://neondb_owner:npg_fm0ZpyB5CQkT@ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech:5432/neondb"
SCHEMA = "public"
TABLE_NAME = "orders"

# Create database engine
engine = create_engine(DATABASE_URL)

# Per-chart SQL queries (generated at compile time)
CHART_QUERIES = {
    "bar_sales_by_country": """SELECT shipping_address_country AS x, SUM(total_amount) AS y FROM public.orders WHERE {filter_clause} GROUP BY shipping_address_country""",
    "pie_orders_by_status": """SELECT status AS x, COUNT(order_id) AS y FROM public.orders WHERE {filter_clause} GROUP BY status""",
    "grouped_bar_country_status": """SELECT shipping_address_country AS x, status AS grp, COUNT(order_id) AS y FROM public.orders WHERE {filter_clause} GROUP BY shipping_address_country, status ORDER BY y DESC""",
    "stacked_bar_payment_status": """SELECT payment_method AS x, status AS grp, COUNT(order_id) AS y FROM public.orders WHERE {filter_clause} GROUP BY payment_method, status""",
    "geo_sales_by_country": """SELECT shipping_address_country AS x, SUM(total_amount) AS y FROM public.orders WHERE {filter_clause} GROUP BY shipping_address_country""",
    "line_orders_over_time": """SELECT order_date AS x, COUNT(order_id) AS y FROM public.orders WHERE {filter_clause} GROUP BY order_date ORDER BY x ASC""",
    "area_revenue_over_time": """SELECT order_date AS x, SUM(total_amount) AS y FROM public.orders WHERE {filter_clause} GROUP BY order_date ORDER BY x ASC""",
    "scatter_amount_vs_tax": """SELECT total_amount AS x, tax_amount AS y FROM public.orders WHERE {filter_clause} AND total_amount IS NOT NULL AND tax_amount IS NOT NULL""",
    "histogram_order_amounts": """SELECT total_amount AS x FROM public.orders WHERE {filter_clause} AND total_amount IS NOT NULL""",
    "box_amount_by_status": """SELECT status AS x, total_amount AS y FROM public.orders WHERE {filter_clause} AND status IS NOT NULL AND total_amount IS NOT NULL""",
    "bubble_region_sales": """SELECT shipping_address_state AS grp, SUM(total_amount) AS x, SUM(tax_amount) AS y, SUM(total_amount) AS size FROM public.orders WHERE {filter_clause} GROUP BY shipping_address_state""",
    "heatmap_country_status": """SELECT shipping_address_country AS x, status AS heatmap_y, COUNT(order_id) AS y FROM public.orders WHERE {filter_clause} AND shipping_address_country IN (SELECT shipping_address_country FROM public.orders GROUP BY shipping_address_country ORDER BY COUNT(*) DESC LIMIT 20) AND status IN (SELECT status FROM public.orders GROUP BY status ORDER BY COUNT(*) DESC LIMIT 20) GROUP BY shipping_address_country, status""",
}

CHART_STATIC_CONDITIONS = {
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

# Cache for column types (fetched once from information_schema)
_column_types_cache = None

def get_column_types():
    """Fetch column types from information_schema and map to simple types"""
    global _column_types_cache
    if _column_types_cache is not None:
        return _column_types_cache

    try:
        query = f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = '{SCHEMA}' AND table_name = '{TABLE_NAME}'
        """
        df = pd.read_sql(query, engine)

        # Map SQL types to simple types: date, number, string
        type_mapping = {}
        for _, row in df.iterrows():
            col_name = row['column_name']
            data_type = str(row['data_type']).upper()

            # Date types (PostgreSQL, MySQL, etc.)
            if any(dt in data_type for dt in ['DATE', 'TIME', 'TIMESTAMP', 'INTERVAL']):
                type_mapping[col_name] = 'date'
            # Numeric types
            elif any(dt in data_type for dt in ['INT', 'FLOAT', 'NUMERIC', 'DECIMAL',
                                                  'REAL', 'DOUBLE', 'SERIAL', 'MONEY']):
                type_mapping[col_name] = 'number'
            # Everything else is string
            else:
                type_mapping[col_name] = 'string'

        _column_types_cache = type_mapping
        return type_mapping
    except Exception as e:
        print(f"Warning: Could not fetch column types: {e}")
        return {}

@app.route('/')
def index():
    """Serve the HTML frontend"""
    return send_from_directory('.', 'index.html')

@app.route('/api/schema')
def get_schema():
    """Return column types from information_schema"""
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
        df = pd.read_sql(query, engine)
        json_str = df.to_json(orient='records', date_format='iso')
        return Response(json_str, mimetype='application/json')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/filter/<field>')
def get_filter_options(field):
    """Return DISTINCT values for a filter field"""
    from flask import request
    if field not in ALLOWED_FILTER_FIELDS:
        return jsonify({"error": "Field not allowed"}), 403
    try:
        query = "SELECT DISTINCT " + field + " FROM public.orders WHERE " + field + " IS NOT NULL ORDER BY 1 LIMIT 500"
        df = pd.read_sql(query, engine)
        values = sorted(df.iloc[:, 0].dropna().astype(str).tolist())
        return jsonify(values)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask server...")
    print(f"Dashboard available at: http://localhost:5002")
    app.run(debug=True, port=5002)
