"""Tests for DashML Validator — near-100% coverage of the gatekeeper."""
import pytest
from dashml_new.core.validator import DashMLValidator, ValidationError


@pytest.fixture
def v():
    return DashMLValidator()


def _min_csv(**extra):
    """Return a minimal valid CSV spec, optionally overriding keys."""
    spec = {
        "version": "0.1",
        "data": {"type": "csv", "path": "data.csv"},
        "charts": [{"id": "c1", "type": "bar", "x": "col_a", "y": "col_b"}],
    }
    spec.update(extra)
    return spec


def _min_chart(**extra):
    """Return a minimal valid chart dict."""
    chart = {"id": "c1", "type": "bar", "x": "col_a", "y": "col_b"}
    chart.update(extra)
    return chart


# ---------------------------------------------------------------------------
# Top-level field validation
# ---------------------------------------------------------------------------

class TestTopLevel:
    def test_missing_version(self, v):
        with pytest.raises(ValidationError, match="version"):
            v.validate({"data": {"type": "csv", "path": "d.csv"}, "charts": [_min_chart()]})

    def test_missing_data(self, v):
        with pytest.raises(ValidationError, match="data"):
            v.validate({"version": "0.1", "charts": [_min_chart()]})

    def test_version_as_string(self, v):
        v.validate(_min_csv(version="1.0"))  # must not raise

    def test_version_as_int(self, v):
        v.validate(_min_csv(version=1))  # must not raise

    def test_version_as_float(self, v):
        v.validate(_min_csv(version=0.000000001))  # must not raise

    def test_version_as_list_raises(self, v):
        with pytest.raises(ValidationError, match="version"):
            v.validate(_min_csv(version=["bad"]))

    def test_version_as_dict_raises(self, v):
        with pytest.raises(ValidationError, match="version"):
            v.validate(_min_csv(version={"bad": True}))

    def test_neither_charts_nor_pages(self, v):
        spec = {"version": "0.1", "data": {"type": "csv", "path": "d.csv"}}
        with pytest.raises(ValidationError, match="'pages' or 'charts'"):
            v.validate(spec)


# ---------------------------------------------------------------------------
# Data source validation
# ---------------------------------------------------------------------------

class TestDataValidation:
    def test_data_not_dict_raises(self, v):
        spec = {"version": "0.1", "data": "not-a-dict", "charts": [_min_chart()]}
        with pytest.raises(ValidationError, match="'data' must be an object"):
            v.validate(spec)

    def test_data_missing_type(self, v):
        spec = {"version": "0.1", "data": {"path": "d.csv"}, "charts": [_min_chart()]}
        with pytest.raises(ValidationError, match="'type' field"):
            v.validate(spec)

    def test_unsupported_data_type(self, v):
        spec = {"version": "0.1", "data": {"type": "parquet"}, "charts": [_min_chart()]}
        with pytest.raises(ValidationError, match="Unsupported data type"):
            v.validate(spec)


class TestCsvValidation:
    def test_csv_missing_path(self, v):
        spec = {"version": "0.1", "data": {"type": "csv"}, "charts": [_min_chart()]}
        with pytest.raises(ValidationError, match="'path' field"):
            v.validate(spec)

    def test_csv_valid(self, v):
        v.validate(_min_csv())  # must not raise


class TestSqlValidation:
    def _sql_spec(self, data_overrides):
        data = {"type": "sql"}
        data.update(data_overrides)
        return {"version": "0.1", "data": data, "charts": [_min_chart()]}

    def test_sql_no_path_no_legacy_raises(self, v):
        with pytest.raises(ValidationError, match="'path' field"):
            v.validate(self._sql_spec({}))

    def test_sql_valid_dot_path(self, v):
        v.validate(self._sql_spec({"path": "public.orders"}))

    def test_sql_valid_bracketed_path(self, v):
        v.validate(self._sql_spec({"path": "[My Schema].[My Table]"}))

    def test_sql_invalid_path_raises(self, v):
        with pytest.raises(ValidationError, match="Invalid SQL path"):
            v.validate(self._sql_spec({"path": "notvalid"}))

    def test_sql_path_not_string_raises(self, v):
        with pytest.raises(ValidationError, match="'path' must be a string"):
            v.validate(self._sql_spec({"path": 123}))

    def test_sql_valid_legacy_fields(self, v):
        v.validate(self._sql_spec({"schema": "public", "table_name": "orders"}))

    def test_sql_legacy_schema_not_string_raises(self, v):
        with pytest.raises(ValidationError, match="'schema' must be a string"):
            v.validate(self._sql_spec({"schema": 123, "table_name": "orders"}))

    def test_sql_legacy_table_name_not_string_raises(self, v):
        with pytest.raises(ValidationError, match="'table_name' must be a string"):
            v.validate(self._sql_spec({"schema": "public", "table_name": 456}))

    def test_sql_database_id_not_int_raises(self, v):
        with pytest.raises(ValidationError, match="'database_id' must be an integer"):
            v.validate(self._sql_spec({"path": "public.orders", "database_id": "one"}))

    def test_sql_database_id_int_valid(self, v):
        v.validate(self._sql_spec({"path": "public.orders", "database_id": 1}))


class TestBigQueryValidation:
    def _bq_spec(self, data_overrides):
        data = {"type": "bigquery"}
        data.update(data_overrides)
        return {"version": "0.1", "data": data, "charts": [_min_chart()]}

    def test_bq_missing_path_raises(self, v):
        with pytest.raises(ValidationError, match="'path' field"):
            v.validate(self._bq_spec({}))

    def test_bq_path_not_string_raises(self, v):
        with pytest.raises(ValidationError, match="'path' must be a string"):
            v.validate(self._bq_spec({"path": 42}))

    def test_bq_path_without_dot_raises(self, v):
        with pytest.raises(ValidationError, match="Invalid BigQuery path"):
            v.validate(self._bq_spec({"path": "nodothere"}))

    def test_bq_valid_path(self, v):
        v.validate(self._bq_spec({"path": "my_dataset.my_table"}))


# ---------------------------------------------------------------------------
# Charts array validation
# ---------------------------------------------------------------------------

class TestChartsValidation:
    def test_charts_not_list_raises(self, v):
        spec = _min_csv(charts={"bad": "not-a-list"})
        with pytest.raises(ValidationError, match="must be an array"):
            v.validate(spec)

    def test_empty_charts_raises(self, v):
        spec = _min_csv(charts=[])
        with pytest.raises(ValidationError, match="at least one chart"):
            v.validate(spec)

    def test_chart_not_dict_raises(self, v):
        spec = _min_csv(charts=["not-a-dict"])
        with pytest.raises(ValidationError, match="must be an object"):
            v.validate(spec)

    @pytest.mark.parametrize("missing_field", ["id", "type", "x", "y"])
    def test_chart_missing_required_field(self, v, missing_field):
        chart = _min_chart()
        del chart[missing_field]
        spec = _min_csv(charts=[chart])
        with pytest.raises(ValidationError, match=f"missing required field"):
            v.validate(spec)

    def test_chart_unsupported_type_raises(self, v):
        spec = _min_csv(charts=[_min_chart(type="waterfall")])
        with pytest.raises(ValidationError, match="unsupported type"):
            v.validate(spec)

    def test_chart_unsupported_aggregation_raises(self, v):
        spec = _min_csv(charts=[_min_chart(agg="median")])
        with pytest.raises(ValidationError, match="unsupported aggregation"):
            v.validate(spec)

    @pytest.mark.parametrize("chart_type", ["stacked_bar", "grouped_bar", "bubble"])
    def test_group_required_for_multi_series_charts(self, v, chart_type):
        spec = _min_csv(charts=[_min_chart(type=chart_type)])
        with pytest.raises(ValidationError, match="requires a 'group' field"):
            v.validate(spec)

    def test_bubble_requires_size(self, v):
        spec = _min_csv(charts=[_min_chart(type="bubble", group="category")])
        with pytest.raises(ValidationError, match="requires a 'size' field"):
            v.validate(spec)

    def test_unsupported_x_type_raises(self, v):
        spec = _min_csv(charts=[_min_chart(x_type="boolean")])
        with pytest.raises(ValidationError, match="unsupported x_type"):
            v.validate(spec)

    def test_unsupported_y_type_raises(self, v):
        spec = _min_csv(charts=[_min_chart(y_type="boolean")])
        with pytest.raises(ValidationError, match="unsupported y_type"):
            v.validate(spec)

    def test_unsupported_sort_raises(self, v):
        spec = _min_csv(charts=[_min_chart(sort="z")])
        with pytest.raises(ValidationError, match="unsupported sort field"):
            v.validate(spec)

    def test_unsupported_sort_order_raises(self, v):
        spec = _min_csv(charts=[_min_chart(sort_order="random")])
        with pytest.raises(ValidationError, match="unsupported sort_order"):
            v.validate(spec)

    def test_limit_not_int_raises(self, v):
        spec = _min_csv(charts=[_min_chart(limit="ten")])
        with pytest.raises(ValidationError, match="invalid limit"):
            v.validate(spec)

    def test_limit_zero_raises(self, v):
        spec = _min_csv(charts=[_min_chart(limit=0)])
        with pytest.raises(ValidationError, match="invalid limit"):
            v.validate(spec)

    def test_limit_negative_raises(self, v):
        spec = _min_csv(charts=[_min_chart(limit=-5)])
        with pytest.raises(ValidationError, match="invalid limit"):
            v.validate(spec)

    def test_limit_positive_int_valid(self, v):
        v.validate(_min_csv(charts=[_min_chart(limit=10)]))

    @pytest.mark.parametrize("chart_type", [
        "bar", "line", "scatter", "pie", "area", "histogram",
        "stacked_bar", "grouped_bar", "bubble", "heatmap", "box", "geo",
    ])
    def test_all_supported_chart_types(self, v, chart_type):
        extra = {}
        if chart_type in ("stacked_bar", "grouped_bar", "bubble"):
            extra["group"] = "category"
        if chart_type == "bubble":
            extra["size"] = "amount"
        v.validate(_min_csv(charts=[_min_chart(type=chart_type, **extra)]))

    @pytest.mark.parametrize("agg", ["sum", "mean", "count"])
    def test_all_supported_aggregations(self, v, agg):
        v.validate(_min_csv(charts=[_min_chart(agg=agg)]))

    @pytest.mark.parametrize("col_type", ["date", "number", "string"])
    def test_all_supported_column_types_x(self, v, col_type):
        v.validate(_min_csv(charts=[_min_chart(x_type=col_type)]))

    @pytest.mark.parametrize("col_type", ["date", "number", "string"])
    def test_all_supported_column_types_y(self, v, col_type):
        v.validate(_min_csv(charts=[_min_chart(y_type=col_type)]))

    @pytest.mark.parametrize("sort_field", ["x", "y"])
    def test_all_supported_sort_fields(self, v, sort_field):
        v.validate(_min_csv(charts=[_min_chart(sort=sort_field)]))

    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    def test_all_supported_sort_orders(self, v, sort_order):
        v.validate(_min_csv(charts=[_min_chart(sort_order=sort_order)]))


# ---------------------------------------------------------------------------
# Filters validation
# ---------------------------------------------------------------------------

class TestFiltersValidation:
    def _chart_with_filters(self, filters):
        return _min_chart(filters=filters)

    def test_filters_not_list_raises(self, v):
        spec = _min_csv(charts=[self._chart_with_filters("not-a-list")])
        with pytest.raises(ValidationError, match="filters must be an array"):
            v.validate(spec)

    def test_filter_not_dict_raises(self, v):
        spec = _min_csv(charts=[self._chart_with_filters(["not-a-dict"])])
        with pytest.raises(ValidationError, match="must be an object"):
            v.validate(spec)

    def test_filter_missing_field_raises(self, v):
        spec = _min_csv(charts=[self._chart_with_filters([{"op": "eq", "value": 1}])])
        with pytest.raises(ValidationError, match="missing required 'field'"):
            v.validate(spec)

    def test_filter_missing_op_raises(self, v):
        spec = _min_csv(charts=[self._chart_with_filters([{"field": "a", "value": 1}])])
        with pytest.raises(ValidationError, match="missing required 'op'"):
            v.validate(spec)

    def test_filter_missing_value_raises(self, v):
        spec = _min_csv(charts=[self._chart_with_filters([{"field": "a", "op": "eq"}])])
        with pytest.raises(ValidationError, match="missing required 'value'"):
            v.validate(spec)

    def test_filter_unsupported_op_raises(self, v):
        spec = _min_csv(charts=[self._chart_with_filters(
            [{"field": "a", "op": "between", "value": 1}]
        )])
        with pytest.raises(ValidationError, match="unsupported op"):
            v.validate(spec)

    def test_in_op_with_non_list_value_raises(self, v):
        spec = _min_csv(charts=[self._chart_with_filters(
            [{"field": "a", "op": "in", "value": "scalar"}]
        )])
        with pytest.raises(ValidationError, match="requires value to be a list"):
            v.validate(spec)

    def test_in_op_with_list_value_valid(self, v):
        spec = _min_csv(charts=[self._chart_with_filters(
            [{"field": "a", "op": "in", "value": ["x", "y"]}]
        )])
        v.validate(spec)

    @pytest.mark.parametrize("op", ["eq", "ne", "gt", "lt", "gte", "lte", "contains"])
    def test_all_scalar_ops_valid(self, v, op):
        spec = _min_csv(charts=[self._chart_with_filters(
            [{"field": "col", "op": op, "value": 42}]
        )])
        v.validate(spec)

    def test_multiple_filters_valid(self, v):
        spec = _min_csv(charts=[self._chart_with_filters([
            {"field": "country", "op": "eq", "value": "US"},
            {"field": "amount", "op": "gt", "value": 100},
        ])])
        v.validate(spec)


# ---------------------------------------------------------------------------
# Pages validation
# ---------------------------------------------------------------------------

class TestPagesValidation:
    def _min_page(self, **extra):
        page = {"id": "p1", "title": "Page 1", "charts": [_min_chart()]}
        page.update(extra)
        return page

    def _pages_spec(self, pages):
        return {"version": "0.1", "data": {"type": "csv", "path": "d.csv"}, "pages": pages}

    def test_pages_not_list_raises(self, v):
        with pytest.raises(ValidationError, match="must be an array"):
            v.validate(self._pages_spec("not-a-list"))

    def test_empty_pages_raises(self, v):
        with pytest.raises(ValidationError, match="at least one page"):
            v.validate(self._pages_spec([]))

    def test_page_not_dict_raises(self, v):
        with pytest.raises(ValidationError, match="must be an object"):
            v.validate(self._pages_spec(["not-a-dict"]))

    @pytest.mark.parametrize("missing_field", ["id", "title", "charts"])
    def test_page_missing_required_field(self, v, missing_field):
        page = self._min_page()
        del page[missing_field]
        with pytest.raises(ValidationError, match="missing required field"):
            v.validate(self._pages_spec([page]))

    def test_page_charts_not_list_raises(self, v):
        page = self._min_page(charts="not-a-list")
        with pytest.raises(ValidationError, match="must be an array"):
            v.validate(self._pages_spec([page]))

    def test_page_empty_charts_raises(self, v):
        page = self._min_page(charts=[])
        with pytest.raises(ValidationError, match="at least one chart"):
            v.validate(self._pages_spec([page]))

    def test_page_chart_validated(self, v):
        bad_chart = {"id": "c1", "type": "invalid_type", "x": "a", "y": "b"}
        page = self._min_page(charts=[bad_chart])
        with pytest.raises(ValidationError, match="unsupported type"):
            v.validate(self._pages_spec([page]))

    def test_multiple_pages_valid(self, v):
        pages = [
            {"id": "p1", "title": "Page 1", "charts": [_min_chart(id="c1")]},
            {"id": "p2", "title": "Page 2", "charts": [_min_chart(id="c2")]},
        ]
        v.validate(self._pages_spec(pages))


# ---------------------------------------------------------------------------
# SQL path parsing (_parse_sql_path)
# ---------------------------------------------------------------------------

class TestParseSqlPath:
    def test_simple_dot_path(self, v):
        schema, table = v._parse_sql_path("public.orders")
        assert schema == "public"
        assert table == "orders"

    def test_bracketed_path(self, v):
        schema, table = v._parse_sql_path("[My Schema].[My Table]")
        assert schema == "My Schema"
        assert table == "My Table"

    def test_mixed_bracket_path(self, v):
        schema, table = v._parse_sql_path("[schema].table")
        assert schema == "schema"
        assert table == "table"

    def test_invalid_path_raises(self, v):
        with pytest.raises(ValueError):
            v._parse_sql_path("")


# ---------------------------------------------------------------------------
# Full happy-path integration
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_full_csv_spec_with_all_options(self, v):
        spec = {
            "version": "1.0",
            "title": "Full Dashboard",
            "data": {"type": "csv", "path": "sales.csv"},
            "charts": [
                {
                    "id": "revenue_chart",
                    "type": "bar",
                    "title": "Revenue by Country",
                    "x": "country",
                    "y": "revenue",
                    "agg": "sum",
                    "sort": "y",
                    "sort_order": "desc",
                    "limit": 10,
                    "x_type": "string",
                    "y_type": "number",
                    "filters": [
                        {"field": "year", "op": "eq", "value": 2024},
                        {"field": "region", "op": "in", "value": ["EMEA", "APAC"]},
                    ],
                },
                {
                    "id": "trend",
                    "type": "line",
                    "x": "date",
                    "y": "revenue",
                    "x_type": "date",
                },
            ],
        }
        v.validate(spec)

    def test_full_sql_spec(self, v):
        spec = {
            "version": "0.1",
            "data": {"type": "sql", "path": "analytics.orders", "database_id": 1},
            "charts": [_min_chart()],
        }
        v.validate(spec)

    def test_full_bigquery_spec(self, v):
        spec = {
            "version": "0.1",
            "data": {"type": "bigquery", "path": "gold.orders"},
            "charts": [_min_chart()],
        }
        v.validate(spec)

    def test_multipage_spec(self, v):
        spec = {
            "version": "0.1",
            "data": {"type": "csv", "path": "data.csv"},
            "pages": [
                {
                    "id": "overview",
                    "title": "Overview",
                    "charts": [
                        _min_chart(id="c1"),
                        _min_chart(id="c2", type="line"),
                    ],
                },
                {
                    "id": "details",
                    "title": "Details",
                    "charts": [_min_chart(id="c3", type="scatter")],
                },
            ],
        }
        v.validate(spec)

    def test_bubble_chart_with_all_required_fields(self, v):
        spec = _min_csv(charts=[
            _min_chart(type="bubble", group="category", size="amount")
        ])
        v.validate(spec)

    def test_stacked_bar_with_group(self, v):
        spec = _min_csv(charts=[_min_chart(type="stacked_bar", group="region")])
        v.validate(spec)

    def test_grouped_bar_with_group(self, v):
        spec = _min_csv(charts=[_min_chart(type="grouped_bar", group="segment")])
        v.validate(spec)


# ---------------------------------------------------------------------------
# Dashboard-level (page) filters validation
# ---------------------------------------------------------------------------

def _pages_spec_with_filters(filters):
    """Return a multi-page spec with the given filters on page 1."""
    return {
        "version": "0.1",
        "data": {"type": "csv", "path": "data.csv"},
        "pages": [
            {
                "id": "p1",
                "title": "Page 1",
                "charts": [_min_chart()],
                "filters": filters,
            }
        ],
    }


class TestDashboardFiltersValidation:
    def test_select_filter_valid(self, v):
        v.validate(_pages_spec_with_filters([{"field": "country", "type": "select"}]))

    def test_multiselect_filter_valid(self, v):
        v.validate(_pages_spec_with_filters([{"field": "region", "type": "multiselect"}]))

    def test_select_with_label_valid(self, v):
        v.validate(_pages_spec_with_filters([{"field": "status", "type": "select", "label": "Status"}]))

    def test_multiselect_with_static_values_valid(self, v):
        v.validate(_pages_spec_with_filters([
            {"field": "country", "type": "multiselect", "values": ["UK", "US", "DE"]}
        ]))

    def test_multiple_filters_on_one_page_valid(self, v):
        v.validate(_pages_spec_with_filters([
            {"field": "region", "type": "select"},
            {"field": "country", "type": "multiselect"},
        ]))

    def test_empty_filters_list_valid(self, v):
        v.validate(_pages_spec_with_filters([]))

    def test_filters_not_list_raises(self, v):
        with pytest.raises(ValidationError, match="filters"):
            v.validate(_pages_spec_with_filters("not-a-list"))

    def test_filter_not_dict_raises(self, v):
        with pytest.raises(ValidationError, match="filter"):
            v.validate(_pages_spec_with_filters(["not-a-dict"]))

    def test_filter_missing_field_raises(self, v):
        with pytest.raises(ValidationError, match="field"):
            v.validate(_pages_spec_with_filters([{"type": "select"}]))

    def test_filter_missing_type_raises(self, v):
        with pytest.raises(ValidationError, match="type"):
            v.validate(_pages_spec_with_filters([{"field": "country"}]))

    def test_filter_unknown_type_raises(self, v):
        with pytest.raises(ValidationError, match="type"):
            v.validate(_pages_spec_with_filters([{"field": "country", "type": "date_range"}]))

    def test_filter_values_not_list_raises(self, v):
        with pytest.raises(ValidationError, match="values"):
            v.validate(_pages_spec_with_filters([
                {"field": "country", "type": "select", "values": "UK"}
            ]))

    @pytest.mark.parametrize("ftype", ["select", "multiselect"])
    def test_all_supported_dashboard_filter_types(self, v, ftype):
        v.validate(_pages_spec_with_filters([{"field": "col", "type": ftype}]))

    def test_page_without_filters_key_valid(self, v):
        """Pages are not required to have a filters key."""
        spec = {
            "version": "0.1",
            "data": {"type": "csv", "path": "data.csv"},
            "pages": [{"id": "p1", "title": "P1", "charts": [_min_chart()]}],
        }
        v.validate(spec)

    def test_dashboard_filter_alongside_chart_filters(self, v):
        """Page-level dashboard filters coexist with per-chart static filters."""
        spec = {
            "version": "0.1",
            "data": {"type": "bigquery", "path": "dataset.table"},
            "pages": [
                {
                    "id": "overview",
                    "title": "Overview",
                    "filters": [
                        {"field": "country", "type": "multiselect"},
                        {"field": "status", "type": "select"},
                    ],
                    "charts": [
                        {
                            "id": "c1",
                            "type": "bar",
                            "x": "category",
                            "y": "revenue",
                            "filters": [{"field": "year", "op": "eq", "value": 2024}],
                        }
                    ],
                }
            ],
        }
        v.validate(spec)


# ---------------------------------------------------------------------------
# Metric chart type validation
# ---------------------------------------------------------------------------

class TestMetricChartValidation:
    def test_metric_without_x_valid(self, v):
        """Metric charts do not require an x field."""
        chart = {"id": "kpi1", "type": "metric", "y": "revenue", "agg": "sum"}
        v.validate(_min_csv(charts=[chart]))

    def test_metric_missing_y_raises(self, v):
        chart = {"id": "kpi1", "type": "metric", "x": "date"}
        with pytest.raises(ValidationError, match="missing required field"):
            v.validate(_min_csv(charts=[chart]))

    def test_metric_with_format_valid(self, v):
        chart = {"id": "kpi1", "type": "metric", "y": "revenue", "agg": "sum", "format": ",.2f", "suffix": " $"}
        v.validate(_min_csv(charts=[chart]))

    def test_metric_in_pages_valid(self, v):
        spec = {
            "version": "0.1",
            "data": {"type": "csv", "path": "data.csv"},
            "pages": [
                {
                    "id": "overview",
                    "title": "Overview",
                    "charts": [
                        {"id": "total_rev", "type": "metric", "y": "revenue", "agg": "sum"},
                        _min_chart(id="bar1"),
                    ],
                }
            ],
        }
        v.validate(spec)


# ---------------------------------------------------------------------------
# Derived fields validation
# ---------------------------------------------------------------------------

def _spec_with_derived(derived_fields, **extra):
    """Return a minimal BigQuery spec with derived_fields."""
    spec = {
        "version": "0.1",
        "data": {"type": "bigquery", "path": "dataset.table"},
        "charts": [_min_chart()],
        "derived_fields": derived_fields,
    }
    spec.update(extra)
    return spec


class TestDerivedFieldsValidation:
    # --- Valid cases ---

    def test_single_field_valid(self, v):
        v.validate(_spec_with_derived([
            {"name": "on_time_rate", "expression": "100 - {pct_delayed}"}
        ]))

    def test_multiple_fields_valid(self, v):
        v.validate(_spec_with_derived([
            {"name": "on_time_rate", "expression": "100 - {pct_delayed}"},
            {"name": "delay_index", "expression": "({avg_delay} + {pct_delayed}) / 2"},
        ]))

    def test_expression_with_two_refs_valid(self, v):
        v.validate(_spec_with_derived([
            {"name": "combined", "expression": "{col_a} + {col_b}"}
        ]))

    def test_expression_with_parens_valid(self, v):
        v.validate(_spec_with_derived([
            {"name": "weighted", "expression": "({a} * {b}) / ({c} + 1)"}
        ]))

    def test_empty_derived_fields_list_valid(self, v):
        v.validate(_spec_with_derived([]))

    def test_derived_fields_absent_valid(self, v):
        """Spec without derived_fields key is valid."""
        v.validate(_min_csv())

    def test_derived_field_with_underscore_name_valid(self, v):
        v.validate(_spec_with_derived([
            {"name": "_my_field", "expression": "{a} - {b}"}
        ]))

    def test_derived_fields_alongside_pages(self, v):
        spec = {
            "version": "0.1",
            "data": {"type": "bigquery", "path": "dataset.table"},
            "derived_fields": [{"name": "rate", "expression": "100 - {pct}"}],
            "pages": [{"id": "p1", "title": "Page 1", "charts": [_min_chart()]}],
        }
        v.validate(spec)

    # --- Invalid: structure errors ---

    def test_derived_fields_not_list_raises(self, v):
        spec = _spec_with_derived("not-a-list")
        with pytest.raises(ValidationError, match="derived_fields.*must be a list"):
            v.validate(spec)

    def test_derived_fields_entry_not_dict_raises(self, v):
        spec = _spec_with_derived(["not-a-dict"])
        with pytest.raises(ValidationError, match="must be an object"):
            v.validate(spec)

    def test_derived_fields_missing_name_raises(self, v):
        spec = _spec_with_derived([{"expression": "100 - {x}"}])
        with pytest.raises(ValidationError, match="missing required 'name'"):
            v.validate(spec)

    def test_derived_fields_missing_expression_raises(self, v):
        spec = _spec_with_derived([{"name": "rate"}])
        with pytest.raises(ValidationError, match="missing required 'expression'"):
            v.validate(spec)

    def test_derived_fields_empty_expression_raises(self, v):
        spec = _spec_with_derived([{"name": "rate", "expression": "   "}])
        with pytest.raises(ValidationError, match="non-empty string"):
            v.validate(spec)

    def test_derived_fields_expression_not_string_raises(self, v):
        spec = _spec_with_derived([{"name": "rate", "expression": 42}])
        with pytest.raises(ValidationError, match="non-empty string"):
            v.validate(spec)

    # --- Invalid: expression must contain {ref} ---

    def test_expression_without_ref_raises(self, v):
        spec = _spec_with_derived([{"name": "constant", "expression": "100"}])
        with pytest.raises(ValidationError, match=r"\{col_name\}"):
            v.validate(spec)

    def test_expression_plain_arithmetic_no_ref_raises(self, v):
        spec = _spec_with_derived([{"name": "val", "expression": "1 + 2"}])
        with pytest.raises(ValidationError, match=r"\{col_name\}"):
            v.validate(spec)

    # --- Invalid: name must be a valid identifier ---

    def test_name_starts_with_digit_raises(self, v):
        spec = _spec_with_derived([{"name": "1bad", "expression": "{x}"}])
        with pytest.raises(ValidationError, match="valid identifier"):
            v.validate(spec)

    def test_name_with_hyphen_raises(self, v):
        spec = _spec_with_derived([{"name": "bad-name", "expression": "{x}"}])
        with pytest.raises(ValidationError, match="valid identifier"):
            v.validate(spec)

    def test_name_with_space_raises(self, v):
        spec = _spec_with_derived([{"name": "bad name", "expression": "{x}"}])
        with pytest.raises(ValidationError, match="valid identifier"):
            v.validate(spec)

    def test_name_not_string_raises(self, v):
        spec = _spec_with_derived([{"name": 123, "expression": "{x}"}])
        with pytest.raises(ValidationError, match="'name' must be a string"):
            v.validate(spec)

    # --- Invalid: duplicate names ---

    def test_duplicate_names_raises(self, v):
        spec = _spec_with_derived([
            {"name": "rate", "expression": "100 - {pct}"},
            {"name": "rate", "expression": "{a} / {b}"},
        ])
        with pytest.raises(ValidationError, match="duplicate name"):
            v.validate(spec)

    # --- Coexistence with other features ---

    def test_derived_fields_with_page_level_filters(self, v):
        spec = {
            "version": "0.1",
            "data": {"type": "bigquery", "path": "dataset.table"},
            "derived_fields": [{"name": "rate", "expression": "100 - {pct}"}],
            "pages": [
                {
                    "id": "overview",
                    "title": "Overview",
                    "filters": [{"field": "country", "type": "select"}],
                    "charts": [_min_chart()],
                }
            ],
        }
        v.validate(spec)

    def test_derived_fields_with_chart_filters(self, v):
        spec = _spec_with_derived(
            [{"name": "rate", "expression": "100 - {pct}"}],
            charts=[_min_chart(filters=[{"field": "region", "op": "eq", "value": "EU"}])],
        )
        v.validate(spec)
