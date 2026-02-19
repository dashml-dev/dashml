"""Tests for DashML Normalizer"""
import pytest
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "dashml_new"))

from dashml_new.core.normalizer import DashMLNormalizer, NormalizerError


@pytest.fixture
def normalizer():
    return DashMLNormalizer()


class TestNormalizePages:
    """Single-page specs get wrapped into pages[]."""

    def test_single_page_charts_wrapped(self, normalizer):
        spec = {
            "version": "0.1",
            "title": "Test",
            "data": {"type": "csv", "path": "data.csv"},
            "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}],
        }
        result = normalizer.normalize(spec, "/tmp/test.dashml")
        assert "pages" in result
        assert len(result["pages"]) == 1
        assert result["pages"][0]["charts"][0]["id"] == "c1"

    def test_multi_page_preserved(self, normalizer):
        spec = {
            "version": "0.1",
            "data": {"type": "csv", "path": "data.csv"},
            "pages": [
                {"id": "p1", "title": "Page 1", "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]},
            ],
        }
        result = normalizer.normalize(spec, "/tmp/test.dashml")
        assert len(result["pages"]) == 1
        assert result["pages"][0]["id"] == "p1"


class TestNormalizeData:
    """Data source path parsing."""

    def test_csv_path_resolved(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "data/sales.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/project/dashboard.dashml")
        assert result["data"]["csv_path"] == "/project/data/sales.csv"

    def test_sql_path_parsed(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "sql", "path": "public.orders"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/tmp/test.dashml")
        assert result["data"]["sql_schema"] == "public"
        assert result["data"]["sql_table"] == "orders"

    def test_sql_bracketed_path(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "sql", "path": "[My Schema].[My Table]"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/tmp/test.dashml")
        assert result["data"]["sql_schema"] == "My Schema"
        assert result["data"]["sql_table"] == "My Table"

    def test_sql_legacy_fields(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "sql", "schema": "public", "table_name": "orders"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/tmp/test.dashml")
        assert result["data"]["path"] == "public.orders"
        assert result["data"]["sql_schema"] == "public"
        assert result["data"]["sql_table"] == "orders"

    def test_bigquery_path_parsed(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "bigquery", "path": "gold.orders"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/tmp/test.dashml")
        assert result["data"]["bq_dataset"] == "gold"
        assert result["data"]["bq_table"] == "orders"


class TestNormalizeChart:
    """Chart default filling and annotations."""

    def test_needs_aggregation_bar(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        chart = normalizer.normalize(spec, "/tmp/t.dashml")["pages"][0]["charts"][0]
        assert chart["needs_aggregation"] is True
        assert chart["uses_raw_data"] is False

    def test_uses_raw_data_histogram(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "histogram", "x": "a", "y": "b"}]}
        chart = normalizer.normalize(spec, "/tmp/t.dashml")["pages"][0]["charts"][0]
        assert chart["needs_aggregation"] is False
        assert chart["uses_raw_data"] is True

    def test_default_agg(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        chart = normalizer.normalize(spec, "/tmp/t.dashml")["pages"][0]["charts"][0]
        assert chart["agg"] == "sum"

    def test_default_bins_histogram(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "histogram", "x": "a", "y": "b"}]}
        chart = normalizer.normalize(spec, "/tmp/t.dashml")["pages"][0]["charts"][0]
        assert chart["bins"] == 20

    def test_default_filters_empty(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        chart = normalizer.normalize(spec, "/tmp/t.dashml")["pages"][0]["charts"][0]
        assert chart["filters"] == []

    def test_default_title_from_id(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "my_chart", "type": "bar", "x": "a", "y": "b"}]}
        chart = normalizer.normalize(spec, "/tmp/t.dashml")["pages"][0]["charts"][0]
        assert chart["title"] == "my_chart"

    def test_explicit_values_not_overwritten(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "title": "Custom", "x": "a", "y": "b",
                            "agg": "mean", "sort_order": "desc"}]}
        chart = normalizer.normalize(spec, "/tmp/t.dashml")["pages"][0]["charts"][0]
        assert chart["title"] == "Custom"
        assert chart["agg"] == "mean"
        assert chart["sort_order"] == "desc"


class TestVersionCoercion:
    def test_float_version(self, normalizer):
        spec = {"version": 0.1, "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        assert normalizer.normalize(spec, "/tmp/t.dashml")["version"] == "0.1"

    def test_int_version(self, normalizer):
        spec = {"version": 1, "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        assert normalizer.normalize(spec, "/tmp/t.dashml")["version"] == "1"


class TestDbConfig:
    def test_db_config_attached(self, normalizer):
        db_config = {"type": "postgresql", "host": "localhost"}
        spec = {"version": "0.1", "data": {"type": "sql", "path": "public.t"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/tmp/t.dashml", db_config)
        assert result["db_config"] == db_config

    def test_no_db_config_defaults_empty(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/tmp/t.dashml")
        assert result["db_config"] == {}


class TestResolvedStyle:
    def test_no_style_returns_defaults(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/tmp/t.dashml")
        assert "style" in result
        assert result["style"]["primary"] == "#29b5e8"
        assert isinstance(result["style"]["secondary"], list)
        assert len(result["style"]["secondary"]) == 10

    def test_source_file_resolved(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        result = normalizer.normalize(spec, "/tmp/t.dashml")
        # Path.resolve() on macOS resolves /tmp -> /private/tmp
        assert result["source_file"] == str(Path("/tmp/t.dashml").resolve())


class TestNormalizerError:
    def test_invalid_sql_path(self, normalizer):
        with pytest.raises(NormalizerError, match="Invalid SQL path"):
            normalizer._parse_sql_path("")

    def test_invalid_bigquery_path(self, normalizer):
        spec = {"version": "0.1", "data": {"type": "bigquery", "path": "bad.path.format"},
                "charts": [{"id": "c1", "type": "bar", "x": "a", "y": "b"}]}
        with pytest.raises(NormalizerError, match="Invalid BigQuery path"):
            normalizer.normalize(spec, "/tmp/t.dashml")
