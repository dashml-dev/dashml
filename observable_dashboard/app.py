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
