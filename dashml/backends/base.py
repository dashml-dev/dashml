"""
Base Backend Interface
All backends must implement this
"""
from abc import ABC, abstractmethod
from typing import Any
from dashml.core.ir import IR


class Backend(ABC):
    """
    Base class for all DashML backends
    
    Backends are responsible for:
    - Reading IR (semantic specification)
    - Generating backend-specific code/config
    - Executing queries and fetching data
    - Rendering visualizations
    
    Backends NEVER receive data from DashML core.
    """
    
    @abstractmethod
    def generate(self, ir: IR) -> Any:
        """
        Generate backend-specific artifact from IR
        
        Args:
            ir: Pure semantic IR (no data)
            
        Returns:
            Backend-specific output:
            - Streamlit: Python code string
            - Plotly: JSON config
            - Looker: LookML string
            - React: Component + API config
        """
        pass
    
    @abstractmethod
    def execute(self, ir: IR, **kwargs) -> Any:
        """
        Execute the backend (runtime)
        
        This is where data is actually loaded and visualized.
        Backend handles ALL data access.
        """
        pass

