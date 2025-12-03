"""
DashML Validator - Validates semantic correctness of DashML specs
"""
from typing import Dict, Any, List


class ValidationError(Exception):
    """Raised when DashML spec is semantically invalid"""
    pass


class DashMLValidator:
    """
    Validates the semantic correctness of DashML specifications.
    Ensures required fields exist and values are reasonable.
    Does NOT validate data sources or check if files exist.
    """

    REQUIRED_TOP_LEVEL = ["version", "data"]
    SUPPORTED_CHART_TYPES = ["bar", "line", "scatter", "pie", "area", "histogram", "stacked_bar", "grouped_bar"]
    SUPPORTED_DATA_TYPES = ["csv"]  # Only CSV is actually implemented (json/sql removed until implemented)
    SUPPORTED_AGGREGATIONS = ["sum", "mean", "count"]

    def validate(self, spec: Dict[str, Any]) -> None:
        """
        Validate a DashML spec dictionary.

        Args:
            spec: Parsed DashML specification

        Raises:
            ValidationError: If spec is invalid
        """
        self._validate_top_level(spec)
        self._validate_data(spec["data"])

        # Validate either pages or charts (not both)
        if "pages" in spec:
            self._validate_pages(spec["pages"])
        elif "charts" in spec:
            self._validate_charts(spec["charts"])
        else:
            raise ValidationError("Must have either 'pages' or 'charts'")

    def _validate_top_level(self, spec: Dict[str, Any]) -> None:
        """Validate top-level required fields"""
        for field in self.REQUIRED_TOP_LEVEL:
            if field not in spec:
                raise ValidationError(f"Missing required field: '{field}'")

        # Version can be string or number (YAML parses 0.000000001 as float)
        if not isinstance(spec["version"], (str, int, float)):
            raise ValidationError(f"'version' must be a string or number, got {type(spec['version'])}")

    def _validate_data(self, data: Any) -> None:
        """Validate data source specification"""
        if not isinstance(data, dict):
            raise ValidationError(f"'data' must be an object, got {type(data)}")

        if "type" not in data:
            raise ValidationError("'data' must have a 'type' field")

        if "path" not in data:
            raise ValidationError("'data' must have a 'path' field")

        if data["type"] not in self.SUPPORTED_DATA_TYPES:
            raise ValidationError(
                f"Unsupported data type: '{data['type']}'. "
                f"Supported: {', '.join(self.SUPPORTED_DATA_TYPES)}"
            )

    def _validate_charts(self, charts: Any) -> None:
        """Validate charts array"""
        if not isinstance(charts, list):
            raise ValidationError(f"'charts' must be an array, got {type(charts)}")

        if len(charts) == 0:
            raise ValidationError("'charts' must contain at least one chart")

        for i, chart in enumerate(charts):
            self._validate_chart(chart, i)

    def _validate_chart(self, chart: Any, index: int) -> None:
        """Validate a single chart specification"""
        if not isinstance(chart, dict):
            raise ValidationError(f"Chart at index {index} must be an object, got {type(chart)}")

        # Required fields
        required = ["id", "type", "x", "y"]
        for field in required:
            if field not in chart:
                raise ValidationError(f"Chart '{chart.get('id', index)}' missing required field: '{field}'")

        # Chart type validation
        if chart["type"] not in self.SUPPORTED_CHART_TYPES:
            raise ValidationError(
                f"Chart '{chart['id']}' has unsupported type: '{chart['type']}'. "
                f"Supported: {', '.join(self.SUPPORTED_CHART_TYPES)}"
            )

        # Aggregation validation (if present)
        if "agg" in chart and chart["agg"] not in self.SUPPORTED_AGGREGATIONS:
            raise ValidationError(
                f"Chart '{chart['id']}' has unsupported aggregation: '{chart['agg']}'. "
                f"Supported: {', '.join(self.SUPPORTED_AGGREGATIONS)}"
            )

        # Group field validation for stacked/grouped charts
        if chart["type"] in ["stacked_bar", "grouped_bar"]:
            if "group" not in chart:
                raise ValidationError(
                    f"Chart '{chart['id']}' is type '{chart['type']}' and requires a 'group' field"
                )

        # ID uniqueness (check against other charts)
        # This is simplified - full implementation would track seen IDs

    def _validate_pages(self, pages: Any) -> None:
        """Validate pages array"""
        if not isinstance(pages, list):
            raise ValidationError(f"'pages' must be an array, got {type(pages)}")

        if len(pages) == 0:
            raise ValidationError("'pages' must contain at least one page")

        for i, page in enumerate(pages):
            self._validate_page(page, i)

    def _validate_page(self, page: Any, index: int) -> None:
        """Validate a single page specification"""
        if not isinstance(page, dict):
            raise ValidationError(f"Page at index {index} must be an object, got {type(page)}")

        # Required fields
        required = ["id", "title", "charts"]
        for field in required:
            if field not in page:
                raise ValidationError(f"Page '{page.get('id', index)}' missing required field: '{field}'")

        # Validate page charts
        if not isinstance(page["charts"], list):
            raise ValidationError(f"Page '{page['id']}' charts must be an array")

        if len(page["charts"]) == 0:
            raise ValidationError(f"Page '{page['id']}' must contain at least one chart")

        # Validate each chart in the page
        for i, chart in enumerate(page["charts"]):
            self._validate_chart(chart, i)
