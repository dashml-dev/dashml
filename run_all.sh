#!/bin/bash

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🚀 DashML - Running ALL Demos (New Architecture)       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down all servers..."
    kill $STREAMLIT_PID 2>/dev/null
    kill $HTTP_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Generate Plotly HTML using new backend
echo "📊 Generating Plotly dashboard..."
python3 dashml_cli.py generate dashml_example.dashml -b plotly -o generated_dashboard.html
echo ""

# Start Streamlit (new architecture)
echo "🐍 Starting Streamlit app (new architecture)..."
streamlit run app_new.py --server.port 8501 &
STREAMLIT_PID=$!
sleep 2

# Start HTTP server for Plotly
echo "🌐 Starting HTTP server for Plotly..."
python3 -m http.server 8000 &
HTTP_PID=$!
sleep 2

echo ""
echo "✅ All servers running!"
echo ""
echo "┌─────────────────────────────────────────────────────────┐"
echo "│  🐍 Streamlit (New Architecture)                        │"
echo "│     → http://localhost:8501                             │"
echo "│                                                         │"
echo "│  📊 Plotly (Generated from new backend)                 │"
echo "│     → http://localhost:8000/generated_dashboard.html    │"
echo "│                                                         │"
echo "│  🎯 Both use the same .dashml spec!                     │"
echo "│     Edit dashml_example.dashml to see changes          │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
echo "💡 Architecture:"
echo "   .dashml → Compiler → IR → Backend → Platform"
echo ""
echo "Press Ctrl+C to stop all servers"
echo ""

# Wait for both processes
wait

