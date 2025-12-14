"""
DashML - Declarative Dashboard Language

A domain-specific language for building data visualization dashboards.
Write once in DashML, generate code for multiple platforms.
"""
from .core import DashMLEngine, ValidationError
from .transformers import Transformer, TransformerRegistry

__version__ = "0.000000001"
__all__ = ["DashMLEngine", "ValidationError", "Transformer", "TransformerRegistry"]
