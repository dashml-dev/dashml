"""
DashML Engine - Orchestrates parsing, validation, and normalization
"""
from .parser import DashMLParser
from .validator import DashMLValidator, ValidationError
from .normalizer import DashMLNormalizer
from .types import NormalizedSpec
from typing import Any, Dict, Optional


class DashMLEngine:
    """
    Main engine for DashML.
    Loads .dashml files, validates them, and normalizes specs for transformers.

    The engine is purely semantic - it never fetches data or materializes datasets.
    It only ensures the .dashml specification is well-formed, valid, and normalized.
    """

    def __init__(self):
        self.parser = DashMLParser()
        self.validator = DashMLValidator()
        self.normalizer = DashMLNormalizer()

    def parse_and_validate(self, dashml_path: str) -> dict:
        """Parse and validate a .dashml file. Returns raw validated dict."""
        spec = self.parser.parse(dashml_path)
        self.validator.validate(spec)
        return spec

    def normalize(
        self, spec: dict, dashml_path: str, db_config: Optional[Dict[str, Any]] = None
    ) -> NormalizedSpec:
        """Normalize a validated spec into a NormalizedSpec."""
        return self.normalizer.normalize(spec, dashml_path, db_config)

    def load(
        self, dashml_path: str, db_config: Optional[Dict[str, Any]] = None
    ) -> NormalizedSpec:
        """Convenience: parse + validate + normalize in one call."""
        spec = self.parse_and_validate(dashml_path)
        return self.normalize(spec, dashml_path, db_config)
