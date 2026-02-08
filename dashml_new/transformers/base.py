"""
Base Transformer Interface - Contract for all DashML transformers
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Any, Tuple
from pathlib import Path
import re

if TYPE_CHECKING:
    from ..core.types import DashMLSpec


class Transformer(ABC):
    """
    Abstract base class for all DashML transformers.

    Transformers are code generators that convert DashML specs
    into platform-specific code or configuration files.

    They MUST NOT fetch data or materialize datasets.
    They only generate code that will fetch data when executed.
    """

    def __init__(self):
        """Initialize transformer with empty warnings list"""
        self._warnings: list[str] = []

    def warn(self, message: str) -> None:
        """
        Record a warning about unsupported features or limitations.

        Args:
            message: Warning message describing what is not supported

        Example:
            self.warn("'card' color is not supported by Streamlit transformer")
        """
        self._warnings.append(message)

    def get_warnings(self) -> list[str]:
        """
        Get all warnings recorded during build.

        Returns:
            List of warning messages
        """
        return self._warnings.copy()

    def clear_warnings(self) -> None:
        """Clear all recorded warnings"""
        self._warnings.clear()

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for this transformer (e.g., 'streamlit', 'plotly').

        Returns:
            Transformer name in lowercase
        """
        # TODO: [Pythonic] Use '...' (Ellipsis) instead of 'pass' for abstract methods
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable description of what this transformer generates.

        Returns:
            Description string
        """
        pass

    @abstractmethod
    def build(self, spec: "DashMLSpec") -> str:
        """
        Generate platform-specific code from a DashML spec.

        Args:
            spec: Validated DashML specification (TypedDict)

        Returns:
            Generated code as a string

        Raises:
            TransformerError: If generation fails
        """
        pass

    def validate_spec(self, spec: "DashMLSpec") -> bool:
        """
        Optional: Check if this spec is compatible with this transformer.

        Args:
            spec: DashML specification

        Returns:
            True if compatible, False otherwise

        Note:
            Default implementation accepts all specs.
            Override if your transformer has specific requirements.
        """
        return True

    def _load_style_config(self, style_path: str) -> Dict[str, Any]:
        """
        Load style configuration from .dmls file.

        Args:
            style_path: Path to the .dmls style file

        Returns:
            Parsed style config dict, or empty dict if not found/invalid

        Note:
            This method is shared across all transformers to avoid duplication.
        """
        if not style_path:
            return {}
        try:
            import yaml
            path = Path(style_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            self.warn(f"Could not load style {style_path}: {e}")
        return {}

    def _parse_sql_path(self, path: str) -> Tuple[str, str]:
        """
        Parse SQL path into (schema, table_name) tuple.

        Supports formats:
        - "schema.table" -> ("schema", "table")
        - "[schema].[table]" -> ("schema", "table")
        - "[My Schema].[My Table]" -> ("My Schema", "My Table")

        Args:
            path: SQL path string in schema.table format

        Returns:
            Tuple of (schema, table_name)

        Raises:
            TransformerError: If path format is invalid
        """
        # Pattern: [optional brackets]identifier[optional brackets].identifier
        pattern = r'^\[?([^\]\.]+)\]?\.?\[?([^\]]+)\]?$'
        match = re.match(pattern, path)

        if match:
            schema = match.group(1)
            table = match.group(2)
            return (schema.strip(), table.strip())

        raise TransformerError(f"Invalid SQL path format: {path}")

    @abstractmethod
    def get_run_command(self, output_path: str) -> str:
        """
        Get the command to run the generated output.

        Args:
            output_path: Path to the generated output file

        Returns:
            Shell command to execute the generated dashboard

        Example:
            "streamlit run app.py"
            "python -m http.server 8000"
        """
        pass


class TransformerError(Exception):
    """Raised when transformer fails to generate code"""
    pass
