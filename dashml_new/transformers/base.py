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

    @property
    def output_filename(self) -> str:
        """Default output filename when writing single-file output into a directory."""
        return "index.html"

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


def humanize_field(name: str) -> str:
    """Convert a column/field name to a human-readable label.

    Splits on underscores and camelCase boundaries, then title-cases each
    word. Used as a fallback when a chart spec doesn't provide an explicit
    axis title.

    Examples:
        "airline_name"          -> "Airline Name"
        "average_delay_mins"    -> "Average Delay Mins"
        "pct_delayed_15plus"    -> "Pct Delayed 15plus"
        "reportingMonth"        -> "Reporting Month"
    """
    if not name:
        return ""
    # snake_case → spaces
    parts = name.replace("-", "_").split("_")
    # camelCase → split at lowercase→uppercase boundary inside each part
    expanded: list[str] = []
    for part in parts:
        if not part:
            continue
        chunks: list[str] = []
        cur = part[0]
        for ch in part[1:]:
            if ch.isupper() and cur and cur[-1].islower():
                chunks.append(cur)
                cur = ch
            else:
                cur += ch
        chunks.append(cur)
        expanded.extend(chunks)
    return " ".join(w[:1].upper() + w[1:] for w in expanded if w)
