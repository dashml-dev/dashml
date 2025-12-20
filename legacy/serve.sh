#!/bin/bash

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🚀 DashML Development Server with Auto-reload          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "📦 Starting server with file watching..."
echo ""
echo "🌐 JavaScript/Plotly (with auto-reload):"
echo "   → http://localhost:8000/index.html"
echo "   → http://localhost:8000/example_integration.html"
echo ""
echo "🐍 Python/Streamlit (run in separate terminal):"
echo "   → streamlit run app.py"
echo "   → streamlit run example_integration.py"
echo ""
echo "💡 Edit any .dashml file and see instant updates!"
echo "   Press Ctrl+C to stop"
echo ""

python3 watch.py

