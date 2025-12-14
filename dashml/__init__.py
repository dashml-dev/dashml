"""
DashML - Declarative Dashboard Language

Microkernel Architecture with Backend Plugins

Usage:
    from dashml.core import DashMLCompiler
    from dashml.backends import StreamlitBackend, PlotlyBackend
    
    compiler = DashMLCompiler()
    ir = compiler.compile("dashboard.dashml")
    backend = StreamlitBackend()
    backend.execute(ir)
"""

# New architecture
from .core import DashMLCompiler, IR
from .backends import Backend, StreamlitBackend, PlotlyBackend

__all__ = [
    "DashMLCompiler",
    "IR",
    "Backend",
    "StreamlitBackend",
    "PlotlyBackend",
]

__version__ = "0.0.1"

