"""
DashML Engine - Orchestrates parsing and validation
"""
from .parser import DashMLParser
from .validator import DashMLValidator, ValidationError
from .types import DashMLSpec


class DashMLEngine:
    """
    Main engine for DashML.
    Loads .dashml files, validates them, and prepares specs for transformers.

    The engine is purely semantic - it never fetches data or materializes datasets.
    It only ensures the .dashml specification is well-formed and valid.
    """

    def __init__(self):
        self.parser = DashMLParser()
        self.validator = DashMLValidator()

    def load(self, dashml_path: str) -> DashMLSpec:
        """
        Load and validate a .dashml file.

        Args:
            dashml_path: Path to .dashml file

        Returns:
            Validated spec as a DashMLSpec (TypedDict)

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If YAML is malformed
            ValidationError: If spec is semantically invalid
        """
        # Parse YAML to dict
        spec = self.parser.parse(dashml_path)

        # Validate semantic correctness
        self.validator.validate(spec)

        return spec  # type: ignore - Runtime dict, typed as DashMLSpec
