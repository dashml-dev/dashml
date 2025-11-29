#!/bin/bash

# DashML Development Script
# Starts both Streamlit and Plotly dev servers

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🚀 DashML Full Development Environment                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check if watchdog is installed
if ! python3 -c "import watchdog" 2>/dev/null; then
    echo "⚠️  Installing dependencies..."
    pip install -r requirements.txt
    echo ""
fi

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down all servers..."
    kill $STREAMLIT_PID 2>/dev/null
    kill $WATCH_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "🐍 Starting Streamlit server..."
streamlit run app.py --server.port 8501 &
STREAMLIT_PID=$!

sleep 2

echo "🌐 Starting Plotly dev server with auto-reload..."
python3 watch.py &
WATCH_PID=$!

sleep 2

echo ""
echo "✅ Development servers running:"
echo ""
echo "   📊 Plotly demos (auto-reload enabled):"
echo "      → http://localhost:8000/index.html"
echo "      → http://localhost:8000/example_integration.html"
echo ""
echo "   🐍 Streamlit demos (auto-reload built-in):"
echo "      → http://localhost:8501"
echo ""
echo "💡 Edit any .dashml file and see instant updates!"
echo "   Press Ctrl+C to stop all servers"
echo ""

# Wait for both processes
wait

