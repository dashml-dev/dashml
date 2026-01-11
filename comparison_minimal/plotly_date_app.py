# Flask backend for Plotly
from flask import Flask, jsonify, send_from_directory
from sqlalchemy import create_engine
import pandas as pd

app = Flask(__name__)
engine = create_engine("postgresql://user:pass@localhost:5432/mydb")

@app.route('/')
def index():
    return send_from_directory('.', 'plotly_date.html')

@app.route('/api/data')
def get_data():
    df = pd.read_sql("SELECT * FROM public.orders", engine)
    return jsonify(df.to_dict(orient='records'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
