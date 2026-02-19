"""
Base Transformer Interface - Contract for all DashML transformers
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.types import NormalizedSpec


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
    def build(self, spec: "NormalizedSpec") -> str:
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

    def validate_spec(self, spec: "NormalizedSpec") -> bool:
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
