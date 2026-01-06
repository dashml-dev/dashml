from flask import Flask, jsonify, send_from_directory
from google.cloud import bigquery
import os

app = Flask(__name__)

# BigQuery configuration
PROJECT_ID = "dashml-483511"
DATASET = "products_postresql"
TABLE_NAME = "orders_one_week"

# Use default credentials (from gcloud auth or GOOGLE_APPLICATION_CREDENTIALS env var)
client = bigquery.Client(project=PROJECT_ID)

@app.route('/')
def index():
    """Serve the HTML frontend"""
    return send_from_directory('.', 'index.html')

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
