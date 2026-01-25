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
        # TODO: [DIP] Use dependency injection instead of direct instantiation
        # This makes testing harder and violates Dependency Inversion Principle
        # Fix: def __init__(self, parser=None, validator=None):
        #         self.parser = parser or DashMLParser()
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

        # Store the source file path in the spec for path resolution
        spec["_source_file"] = dashml_path

        # TODO: [Type Safety] Use cast() instead of type: ignore
        # Fix: from typing import cast
        #      return cast(DashMLSpec, spec)
        return spec  # type: ignore - Runtime dict, typed as DashMLSpec
