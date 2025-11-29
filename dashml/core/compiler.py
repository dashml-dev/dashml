"""
DashML Compiler
Orchestrates: YAML → Parser → IR → Backend
"""
from pathlib import Path
from typing import Optional
from .parser import DashMLParser
from .ir import IR


class DashMLCompiler:
    """
    Main compiler interface
    
    Usage:
        compiler = DashMLCompiler()
        ir = compiler.compile("dashboard.dashml")
        # Pass IR to backend
    """
    
    def __init__(self):
        self.parser = DashMLParser()
    
    def compile(self, dashml_path: str) -> IR:
        """
        Compile a .dashml file to IR
        
        Returns:
            IR object containing pure semantic specification
            NO data is loaded or materialized
        """
        return self.parser.parse_file(dashml_path)
    
    def compile_spec(self, spec: dict) -> IR:
        """
        Compile a spec dict directly to IR
        """
        return self.parser.parse_spec(spec)
    
    def validate(self, dashml_path: str) -> tuple[bool, list]:
        """
        Validate a .dashml file
        
        Returns:
            (is_valid, errors)
        """
        try:
            self.compile(dashml_path)
            return True, []
        except Exception as e:
            return False, [str(e)]

