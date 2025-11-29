#!/bin/bash

echo "🚀 Starting DashML Demo Server..."
echo ""
echo "Python/Streamlit demos:"
echo "  → streamlit run app.py"
echo "  → streamlit run example_integration.py"
echo ""
echo "JavaScript/Plotly demos:"
echo "  → http://localhost:8000/index.html"
echo "  → http://localhost:8000/example_integration.html"
echo ""
echo "Starting HTTP server on port 8000..."
echo "Press Ctrl+C to stop"
echo ""

python3 -m http.server 8000

