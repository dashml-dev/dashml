"""
DashML Backend Plugins

Each backend:
- Reads IR (semantic spec)
- Generates backend-specific code/config
- Handles ALL data access
- Never receives data from core
"""
from .base import Backend
from .streamlit_backend import StreamlitBackend
from .plotly_backend import PlotlyBackend

__all__ = ["Backend", "StreamlitBackend", "PlotlyBackend"]

