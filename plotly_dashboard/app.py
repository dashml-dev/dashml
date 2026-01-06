from flask import Flask, jsonify, send_from_directory
from sqlalchemy import create_engine
import pandas as pd

app = Flask(__name__)

# Database configuration
DATABASE_URL = "postgresql://neondb_owner:npg_fm0ZpyB5CQkT@ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech:5432/neondb"
SCHEMA = "public"
TABLE_NAME = "orders_one_week"

# Create database engine
engine = create_engine(DATABASE_URL)

@app.route('/')
def index():
    """Serve the HTML frontend"""
    return send_from_directory('.', 'index.html')

@app.route('/api/data')
def get_data():
    """Fetch data from SQL database and return as JSON"""
    try:
        query = f"SELECT * FROM {SCHEMA}.{TABLE_NAME}"
        df = pd.read_sql(query, engine)
        data = df.to_dict(orient='records')
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask server...")
    print(f"Dashboard available at: http://localhost:5000")
    app.run(debug=True, port=5000)
