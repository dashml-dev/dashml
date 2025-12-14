"""
DashML Parser - Converts .dashml files to Python dicts
"""
import yaml
from pathlib import Path
from typing import Dict, Any


class DashMLParser:
    """
    Parses .dashml files (YAML syntax) into Python dictionaries.
    Does NOT validate semantics - just loads YAML.
    """

    def parse(self, dashml_path: str) -> Dict[str, Any]:
        """
        Parse a .dashml file into a dictionary.

        Args:
            dashml_path: Path to .dashml file

        Returns:
            Dict containing the parsed spec

        Raises:
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If YAML is malformed
        """
        path = Path(dashml_path)

        if not path.exists():
            raise FileNotFoundError(f"DashML file not found: {dashml_path}")

        with path.open("r", encoding="utf-8") as f:
            try:
                spec = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {dashml_path}: {e}")

        if not isinstance(spec, dict):
            raise ValueError(f"DashML file must contain a YAML object, got {type(spec)}")

        return spec
