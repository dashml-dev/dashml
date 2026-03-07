from flask import Flask, jsonify, send_from_directory
from google.cloud import bigquery
import os

app = Flask(__name__)

# BigQuery configuration
PROJECT_ID = "flight-delays"
DATASET = "gold"
TABLE_NAME = "punctuality_gold"

# Use default credentials (from gcloud auth or GOOGLE_APPLICATION_CREDENTIALS env var)
client = bigquery.Client(project=PROJECT_ID)


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

        # Map BigQuery types to simple types: date, number, string
        type_mapping = {}
        for row in results:
            col_name = row.column_name
            data_type = row.data_type.upper()

            # Date types
            if data_type in ('DATE', 'DATETIME', 'TIMESTAMP', 'TIME'):
                type_mapping[col_name] = 'date'
            # Numeric types
            elif data_type in ('INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC', 'INT', 'INTEGER',
                             'SMALLINT', 'BIGINT', 'FLOAT', 'DECIMAL', 'REAL', 'DOUBLE'):
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
    """Return column types from INFORMATION_SCHEMA"""
    try:
        column_types = get_column_types()
        return jsonify(column_types)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/data')
def get_data():
    """Fetch data from BigQuery and return as JSON"""
    try:
        query = f"""
            SELECT *
            FROM `{PROJECT_ID}.{DATASET}.{TABLE_NAME}`
            LIMIT 10000
        """
        query_job = client.query(query)
        results = query_job.result()

        # Convert to list of dicts
        data = [dict(row) for row in results]

        # Handle date/datetime/Decimal serialization
        import json
        from datetime import date, datetime
        from decimal import Decimal

        def serialize(obj):
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f"Type {type(obj)} not serializable")

        return app.response_class(
            response=json.dumps(data, default=serialize),
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask server with BigQuery backend...")
    print(f"Project: {PROJECT_ID}")
    print(f"Dataset: {DATASET}")
    print(f"Table: {TABLE_NAME}")
    print(f"Dashboard available at: http://localhost:5000")
    app.run(debug=True, port=5000)
