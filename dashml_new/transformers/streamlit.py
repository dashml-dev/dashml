"""
Streamlit Transformer - Generates Streamlit Python code from DashML specs
"""
from typing import TYPE_CHECKING, Dict, Any, List
from .base import Transformer, TransformerError
from .constants import (
    CHARTS_NEED_AGGREGATION,
    CHARTS_USE_RAW_DATA,
    DEFAULT_HISTOGRAM_BINS,
    AGG_METHODS,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLORS,
)

if TYPE_CHECKING:
    from ..core.types import NormalizedSpec, ChartSpec


class StreamlitTransformer(Transformer):
    """
    Generates standalone Streamlit applications from DashML specifications.
    Output: Python code that can be run with `streamlit run app.py`
    """

    @property
    def name(self) -> str:
        return "streamlit"

    @property
    def description(self) -> str:
        return "Generates Streamlit Python applications"

    def build(self, spec: "NormalizedSpec") -> str:
        """Generate Streamlit code from a NormalizedSpec."""
        try:
            self.clear_warnings()

            colors = spec["style"]

            # Warn about unsupported color fields
            if colors.get("buttons"):
                self.warn("'buttons' color is not supported - Streamlit button styling is limited")

            code_parts = []

            data_type = spec["data"].get("type", "csv")
            is_sql_mode = data_type in ("bigquery", "sql")

            # Imports
            code_parts.append(self._generate_imports(data_type))
            code_parts.append("")

            # For BigQuery mode, generate CHART_QUERIES dict before run_query
            if data_type == "bigquery" and spec.get("db_config"):
                db_config = spec.get("db_config", {})
                project = db_config["project"]
                dataset = spec["data"]["bq_dataset"]
                table_name = spec["data"]["bq_table"]
                table_ref = f"`{project}.{dataset}.{table_name}`"
                code_parts.append(self._generate_chart_queries_dict(spec["pages"], table_ref))
                code_parts.append("")

            # Cached data loading function (before main)
            code_parts.append(self._generate_data_loading(spec["data"], spec.get("db_config")))
            code_parts.append("")

            # Main function
            code_parts.append("def main():")

            title = spec["title"]
            code_parts.append(self._generate_page_config(title))

            # Apply CSS Styling (if style has non-default colors)
            style_config = {"colors": colors}
            code_parts.append(self._generate_css_injection(style_config))

            # Title
            code_parts.append(f'    st.title("{title}")')
            code_parts.append("")

            # Data loading call
            if data_type == "bigquery" and spec.get("db_config"):
                code_parts.append('    column_types = get_column_types()')
            else:
                code_parts.append('    df, column_types = load_data()')
                code_parts.append('    if df is None:')
                code_parts.append('        st.error("Failed to load data")')
                code_parts.append('        return')
            code_parts.append("")

            # Always pages (normalizer guarantees this)
            code_parts.append(self._generate_pages(spec["pages"], colors, sql_mode=(data_type == "bigquery" and bool(spec.get("db_config")))))

            # Entry point
            code_parts.append("")
            code_parts.append('if __name__ == "__main__":')
            code_parts.append("    main()")

            return "\n".join(code_parts)

        except KeyError as e:
            raise TransformerError(f"Missing required field in spec: {e}")
        except Exception as e:
            raise TransformerError(f"Failed to generate Streamlit code: {e}")

    def _generate_imports(self, data_type: str = "csv") -> str:
        imports = """import streamlit as st
import pandas as pd
import altair as alt"""

        if data_type == "sql":
            imports += "\nfrom sqlalchemy import create_engine"
        elif data_type == "bigquery":
            imports += "\nfrom google.cloud import bigquery"

        return imports

    def _humanize_column_name(self, name: str) -> str:
        """Convert snake_case column names to Title Case labels"""
        return name.replace('_', ' ').replace('-', ' ').title()

    def _sql_value(self, value) -> str:
        """Convert a Python value to a SQL literal."""
        if isinstance(value, str):
            return "'" + value.replace("'", "''") + "'"
        if isinstance(value, (list, tuple)):
            return "(" + ", ".join(self._sql_value(v) for v in value) + ")"
        if value is None:
            return "NULL"
        return str(value)

    def _build_where_clause(self, filters: list) -> str:
        """Convert DashML filter specs to a SQL WHERE clause."""
        if not filters:
            return ""
        op_map = {"eq": "=", "ne": "!=", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
        parts = []
        for f in filters:
            field, op, val = f["field"], f["op"], f["value"]
            if op in op_map:
                parts.append(f"{field} {op_map[op]} {self._sql_value(val)}")
            elif op == "in":
                parts.append(f"{field} IN {self._sql_value(val)}")
            elif op == "contains":
                parts.append(f"{field} LIKE '%{val}%'")
        return " WHERE " + " AND ".join(parts) if parts else ""

    def _build_chart_query(self, chart: dict, table_ref: str) -> str:
        """Build a per-chart SQL query using ORIGINAL column names (not aliased)."""
        chart_type = chart["type"]
        x = chart["x"]
        y = chart["y"]
        agg = chart.get("agg", "sum")
        group = chart.get("group")
        size_field = chart.get("size")
        filters = chart.get("filters", [])
        sort_field = chart.get("sort")
        sort_order = chart.get("sort_order", "asc")
        limit = chart.get("limit")

        where = self._build_where_clause(filters)
        agg_map = {"sum": "SUM", "mean": "AVG", "count": "COUNT"}
        sql_agg = agg_map.get(agg, "SUM")

        order = ""
        if sort_field == "y":
            order = f" ORDER BY {y} {'ASC' if sort_order == 'asc' else 'DESC'}"
        elif sort_field == "x":
            order = f" ORDER BY {x} {'ASC' if sort_order == 'asc' else 'DESC'}"

        limit_clause = f" LIMIT {limit}" if limit else ""

        if not order and chart_type in ("line", "area"):
            order = f" ORDER BY {x} ASC"

        if chart_type in ("bar", "line", "area", "pie", "geo"):
            return f"SELECT {x}, {sql_agg}({y}) AS {y} FROM {table_ref}{where} GROUP BY {x}{order}{limit_clause}"
        elif chart_type in ("stacked_bar", "grouped_bar"):
            return f"SELECT {x}, {group}, {sql_agg}({y}) AS {y} FROM {table_ref}{where} GROUP BY {x}, {group}{order}{limit_clause}"
        elif chart_type == "heatmap":
            heatmap_y = group if group else y
            hm_where = where if where else " WHERE 1=1"
            hm_where += f" AND {x} IN (SELECT {x} FROM {table_ref} GROUP BY {x} ORDER BY COUNT(*) DESC LIMIT 20)"
            hm_where += f" AND {heatmap_y} IN (SELECT {heatmap_y} FROM {table_ref} GROUP BY {heatmap_y} ORDER BY COUNT(*) DESC LIMIT 20)"
            return f"SELECT {x}, {heatmap_y}, {sql_agg}({y}) AS {y} FROM {table_ref}{hm_where} GROUP BY {x}, {heatmap_y}{order}{limit_clause}"
        elif chart_type == "scatter":
            null_filter = f"{x} IS NOT NULL AND {y} IS NOT NULL"
            sc_where = (where + " AND " + null_filter) if where else (" WHERE " + null_filter)
            return f"SELECT {x}, {y} FROM {table_ref}{sc_where} ORDER BY RAND() LIMIT 5000"
        elif chart_type == "bubble":
            size_ref = size_field or y
            return f"SELECT {group}, {sql_agg}({x}) AS {x}, {sql_agg}({y}) AS {y}, {sql_agg}({size_ref}) AS {size_ref} FROM {table_ref}{where} GROUP BY {group}{order}{limit_clause}"
        elif chart_type == "histogram":
            null_filter = f"{x} IS NOT NULL"
            hist_where = (where + " AND " + null_filter) if where else (" WHERE " + null_filter)
            return f"SELECT {x} FROM {table_ref}{hist_where} ORDER BY RAND() LIMIT 50000"
        elif chart_type == "box":
            box_where = where if where else ""
            top_n = f"{x} IN (SELECT {x} FROM {table_ref} GROUP BY {x} ORDER BY COUNT(*) DESC LIMIT 20)"
            null_filter = f"{x} IS NOT NULL AND {y} IS NOT NULL"
            box_where = (box_where + " AND " + top_n + " AND " + null_filter) if box_where else (" WHERE " + top_n + " AND " + null_filter)
            return f"SELECT {x}, {y} FROM {table_ref}{box_where} ORDER BY RAND() LIMIT 50000"
        else:
            return f"SELECT {x}, {sql_agg}({y}) AS {y} FROM {table_ref}{where} GROUP BY {x}{order}{limit_clause}"

    def _generate_chart_queries_dict(self, pages: list, table_ref: str) -> str:
        """Generate CHART_QUERIES dict with per-chart SQL queries."""
        queries = {}
        for page in pages:
            for chart in page["charts"]:
                query = self._build_chart_query(chart, table_ref)
                queries[chart["id"]] = query

        lines = ["CHART_QUERIES = {"]
        for chart_id, query in queries.items():
            lines.append(f'    "{chart_id}": """{query}""",')
        lines.append("}")
        return "\n".join(lines)

    def _generate_page_config(self, title: str) -> str:
        return f'''    st.set_page_config(
        page_title="{title}",
        page_icon="📊",
        layout="wide"
    )'''

    def _generate_css_injection(self, style_config: Dict) -> str:
        """Generate CSS to override Streamlit defaults"""
        colors = style_config.get('colors', {})
        bg_color = colors.get('background', '#ffffff')
        text_color = colors.get('text', '#000000')
        card_color = colors.get('card', bg_color)
        primary_color = colors.get('primary', '#29b5e8')

        return f'''    # Apply Custom Styling
    st.markdown("""
        <style>
        .stApp {{
            background-color: {bg_color};
            color: {text_color};
        }}
        h1, h2, h3, p, li, .stMarkdown, .stMetricValue, .stMetricLabel {{
            color: {text_color} !important;
        }}
        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {{
            color: {text_color};
        }}
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
            border-bottom-color: {primary_color} !important;
        }}
        .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] [data-testid="stMarkdownContainer"] p {{
            color: {primary_color} !important;
        }}
        /* Card-like chart containers */
        [data-testid="stVerticalBlock"] > div {{
            background-color: {card_color};
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 0.5rem;
        }}
        /* Divider color */
        hr {{
            border-color: {text_color}20 !important;
        }}
        </style>
    """, unsafe_allow_html=True)'''

    def _generate_data_loading(self, data_spec: Dict[str, Any], db_config: Dict[str, Any] = None) -> str:
        data_type = data_spec.get("type", "csv")
        db_config = db_config or {}

        if data_type == "csv":
            path = data_spec["path"]
            return f'''@st.cache_data
def load_data():
    try:
        df = pd.read_csv("{path}")

        # Infer column types from pandas dtypes for auto type detection
        column_types = {{}}
        for col in df.columns:
            dtype = str(df[col].dtype)
            if 'datetime' in dtype or 'date' in dtype:
                column_types[col] = 'date'
            elif 'int' in dtype or 'float' in dtype:
                column_types[col] = 'number'
            else:
                # Try to detect date strings
                if df[col].dtype == 'object':
                    try:
                        pd.to_datetime(df[col].dropna().head(10))
                        column_types[col] = 'date'
                    except:
                        column_types[col] = 'string'
                else:
                    column_types[col] = 'string'
        return df, column_types
    except Exception as e:
        return None, None'''

        elif data_type == "sql":
            if not db_config:
                return '''@st.cache_data
def load_data():
    return None, None'''

            # Extract database config
            db_type = db_config["type"]
            host = db_config["host"]
            port = db_config["port"]
            database = db_config["database"]
            user = db_config["user"]
            password = db_config["password"]

            # Use pre-parsed path components from normalizer
            schema = data_spec["sql_schema"]
            table_name = data_spec["sql_table"]

            # Build connection string based on database type
            if db_type == "postgresql":
                conn_str = f"postgresql://{user}:{password}@{host}:{port}/{database}"
            elif db_type == "mysql":
                conn_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            elif db_type == "sqlite":
                conn_str = f"sqlite:///{database}"
            else:
                return f'''@st.cache_data
def load_data():
    return None, None'''

            # Generate data loading code with schema detection
            return f'''@st.cache_data
def load_data():
    try:
        engine = create_engine("{conn_str}")
        df = pd.read_sql("SELECT * FROM {schema}.{table_name}", engine)

        # Fetch column types from information_schema for auto type detection
        schema_query = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = '{schema}' AND table_name = '{table_name}'
        """
        schema_df = pd.read_sql(schema_query, engine)

        # Build column type mapping: date, number, string
        column_types = {{}}
        for _, row in schema_df.iterrows():
            col_name = row['column_name']
            data_type = str(row['data_type']).upper()
            if any(dt in data_type for dt in ['DATE', 'TIME', 'TIMESTAMP', 'INTERVAL']):
                column_types[col_name] = 'date'
            elif any(dt in data_type for dt in ['INT', 'FLOAT', 'NUMERIC', 'DECIMAL', 'REAL', 'DOUBLE', 'SERIAL', 'MONEY']):
                column_types[col_name] = 'number'
            else:
                column_types[col_name] = 'string'
        return df, column_types
    except Exception as e:
        return None, None'''

        elif data_type == "bigquery":
            if not db_config:
                return '''@st.cache_data
def load_data():
    return None, None'''

            # Extract BigQuery config
            project = db_config["project"]
            credentials_path = db_config.get("credentials_path")

            # Use pre-parsed path components from normalizer
            dataset = data_spec["bq_dataset"]
            table_name = data_spec["bq_table"]

            # Build credentials loading code
            if credentials_path:
                credentials_code = f'''
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(
            "{credentials_path}",
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        client = bigquery.Client(project="{project}", credentials=credentials)'''
            else:
                credentials_code = f'''
        # Use default credentials (from gcloud auth or GOOGLE_APPLICATION_CREDENTIALS env var)
        client = bigquery.Client(project="{project}")'''

            return f'''@st.cache_data(ttl=300)
def run_query(query_name):
    try:{credentials_code}
        query = CHART_QUERIES[query_name]
        return client.query(query).to_dataframe()
    except Exception as e:
        st.error(f"Query failed: {{e}}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_column_types():
    try:{credentials_code}
        query = """
            SELECT column_name, data_type
            FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{table_name}'
        """
        results = client.query(query).to_dataframe()
        type_mapping = {{}}
        for _, row in results.iterrows():
            col_name = row["column_name"]
            data_type = row["data_type"].upper()
            if data_type in ("DATE", "DATETIME", "TIMESTAMP", "TIME"):
                type_mapping[col_name] = "date"
            elif data_type in ("INT64", "FLOAT64", "NUMERIC", "BIGNUMERIC", "INT", "INTEGER",
                             "SMALLINT", "BIGINT", "FLOAT", "DECIMAL", "REAL", "DOUBLE"):
                type_mapping[col_name] = "number"
            else:
                type_mapping[col_name] = "string"
        return type_mapping
    except Exception as e:
        return {{}}'''

        else:
            return f'''@st.cache_data
def load_data():
    return None, None'''

    def _generate_chart(self, chart: Dict[str, Any], colors: Dict[str, Any], sql_mode: bool = False) -> str:
        """Generate Altair chart code with explicit colors"""
        chart_id = chart["id"]
        chart_type = chart["type"]
        title = chart["title"]
        x = chart["x"]
        y = chart["y"]
        agg = chart.get("agg", "sum")
        group = chart.get("group")
        x_type = chart.get("x_type")
        y_type = chart.get("y_type")
        bins = chart.get("bins", DEFAULT_HISTOGRAM_BINS)
        filters = chart.get("filters", [])
        sort_field = chart.get("sort")
        sort_order = chart.get("sort_order", "desc" if sort_field == "y" else "asc")
        limit = chart.get("limit")

        # Extract colors using constants
        primary_color = colors.get("primary", DEFAULT_PRIMARY_COLOR)
        secondary_colors = colors.get("secondary", DEFAULT_SECONDARY_COLORS)

        # Humanize column names for axis labels
        x_label = self._humanize_column_name(x)
        y_label = self._humanize_column_name(y)

        code_parts = []
        code_parts.append(f'    # Chart: {chart_id}')
        code_parts.append(f'    st.subheader("{title}")')

        if sql_mode:
            # SQL mode: data comes from per-chart queries, already aggregated/filtered
            code_parts.append(f'    chart_data = run_query("{chart_id}")')
            code_parts.append(f'    chart_df = chart_data')
            code_parts.append(f'    effective_x_type = "{x_type}" if "{x_type}" != "None" else column_types.get("{x}")')
            code_parts.append(f'    x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")')
        else:
            # Only copy when we need to modify the DataFrame in-place (y_type casting)
            if y_type:
                code_parts.append(f'    chart_df = df.copy()')
            else:
                code_parts.append(f'    chart_df = df')

            # y_type casting (before filtering and aggregation)
            if y_type == "number":
                code_parts.append(f'    # Cast y column to numeric (y_type: number)')
                code_parts.append(f'    chart_df["{y}"] = pd.to_numeric(chart_df["{y}"], errors="coerce")')
            elif y_type == "string":
                code_parts.append(f'    # Cast y column to string (y_type: string)')
                code_parts.append(f'    chart_df["{y}"] = chart_df["{y}"].astype(str)')

            # Apply filters (before aggregation)
            if filters:
                code_parts.append(f'    # Apply filters')
                for f in filters:
                    field = f["field"]
                    op = f["op"]
                    value = f["value"]

                    if op == "eq":
                        code_parts.append(f'    chart_df = chart_df[chart_df["{field}"] == {repr(value)}]')
                    elif op == "ne":
                        code_parts.append(f'    chart_df = chart_df[chart_df["{field}"] != {repr(value)}]')
                    elif op == "gt":
                        code_parts.append(f'    chart_df = chart_df[chart_df["{field}"] > {repr(value)}]')
                    elif op == "lt":
                        code_parts.append(f'    chart_df = chart_df[chart_df["{field}"] < {repr(value)}]')
                    elif op == "gte":
                        code_parts.append(f'    chart_df = chart_df[chart_df["{field}"] >= {repr(value)}]')
                    elif op == "lte":
                        code_parts.append(f'    chart_df = chart_df[chart_df["{field}"] <= {repr(value)}]')
                    elif op == "in":
                        code_parts.append(f'    chart_df = chart_df[chart_df["{field}"].isin({repr(value)})]')
                    elif op == "contains":
                        code_parts.append(f'    chart_df = chart_df[chart_df["{field}"].str.contains({repr(value)}, na=False)]')

            # Get effective x_type: explicit > schema-detected > None (used for sorting and encoding)
            code_parts.append(f'    effective_x_type = "{x_type}" if "{x_type}" != "None" else column_types.get("{x}")')

            # Aggregation (only for chart types that need it)
            if chart.get("needs_aggregation", chart_type in CHARTS_NEED_AGGREGATION):
                # Use AGG_METHODS constant
                agg_method = AGG_METHODS.get(agg, "sum")

                # For stacked/grouped bars, aggregate by both x and group
                if chart_type in ["stacked_bar", "grouped_bar"] and group:
                    code_parts.append(f'    # Aggregate: {agg}({y}) group by {x} and {group}')
                    code_parts.append(f'    chart_data = chart_df.groupby(["{x}", "{group}"])["{y}"].{agg_method}().reset_index()')
                elif chart_type == "bubble" and group:
                    size_field = chart.get("size", y)
                    # Bubble: aggregate x, y, size independently grouped by group field
                    # Deduplicate metrics (e.g. x and size may be the same column)
                    metrics = {x: agg_method, y: agg_method, size_field: agg_method}
                    # Cast metric columns to numeric before aggregation
                    for col in metrics:
                        code_parts.append(f'    chart_df["{col}"] = pd.to_numeric(chart_df["{col}"], errors="coerce")')
                    agg_dict_str = ", ".join(f'"{k}": "{v}"' for k, v in metrics.items())
                    code_parts.append(f'    # Bubble: aggregate {x}, {y}, {size_field} group by {group}')
                    code_parts.append(f'    chart_data = chart_df.groupby("{group}").agg({{{agg_dict_str}}}).reset_index()')
                else:
                    code_parts.append(f'    # Aggregate: {agg}({y}) group by {x}')
                    code_parts.append(f'    chart_data = chart_df.groupby("{x}")["{y}"].{agg_method}().reset_index()')

                # Handle sorting: explicit sort field > x_type-based sorting
                if sort_field:
                    # Explicit sort field specified
                    actual_sort_col = x if sort_field == "x" else y
                    ascending = sort_order == "asc"
                    code_parts.append(f'    # Sort by {sort_field} field ({sort_order})')
                    code_parts.append(f'    chart_data = chart_data.sort_values("{actual_sort_col}", ascending={ascending})')
                else:
                    # Default: sort by x - date/number by value, strings alphabetically
                    code_parts.append(f'    if effective_x_type == "date":')
                    code_parts.append(f'        # Sort by date for chronological order')
                    code_parts.append(f'        chart_data["{x}"] = pd.to_datetime(chart_data["{x}"])')
                    code_parts.append(f'        chart_data = chart_data.sort_values("{x}")')
                    code_parts.append(f'    elif effective_x_type == "number":')
                    code_parts.append(f'        # Sort by number for numerical order')
                    code_parts.append(f'        chart_data = chart_data.sort_values("{x}")')
                    code_parts.append(f'    else:')
                    code_parts.append(f'        # Sort strings alphabetically for consistency across transformers')
                    code_parts.append(f'        chart_data = chart_data.sort_values("{x}")')

                # Apply limit (after aggregation and sorting)
                if limit:
                    code_parts.append(f'    # Limit to top {limit} rows')
                    code_parts.append(f'    chart_data = chart_data.head({limit})')

            # Determine X encoding type based on effective_x_type (will be computed at runtime)
            # For Altair: :T = temporal, :Q = quantitative, :N = nominal
            # We'll compute this at runtime based on effective_x_type
            code_parts.append(f'    # Determine Altair encoding type based on effective x_type')
            code_parts.append(f'    x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")')
        x_encoding_type = ""  # Will be added dynamically at runtime

        # Altair Chart Generation
        if chart_type == "bar":
            code_parts.append(f'''    c = alt.Chart(chart_data).mark_bar(color="{primary_color}").encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None, title="{x_label}"),
        y=alt.Y("{y}", title="{y_label}"),
        tooltip=["{x}", "{y}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "line":
            code_parts.append(f'''    c = alt.Chart(chart_data).mark_line(color="{primary_color}", point=True).encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None, title="{x_label}"),
        y=alt.Y("{y}", title="{y_label}"),
        tooltip=["{x}", "{y}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "scatter":
            code_parts.append(f'''    # Scatter: aggregated data points
    c = alt.Chart(chart_data).mark_circle(color="{primary_color}", size=60).encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None, title="{x_label}"),
        y=alt.Y("{y}", title="{y_label}"),
        tooltip=["{x}", "{y}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "bubble":
            size_field = chart.get("size", y)  # Default to y if size not specified
            size_label = self._humanize_column_name(size_field)
            if group:
                group_label = self._humanize_column_name(group)
                code_parts.append(f'''    # Bubble: 4D visualization (group, x, y, size)
    c = alt.Chart(chart_data).mark_circle().encode(
        x=alt.X("{x}:Q", title="{x_label}"),
        y=alt.Y("{y}:Q", title="{y_label}"),
        size=alt.Size("{size_field}:Q", scale=alt.Scale(range=[50, 500]), legend=alt.Legend(title="{size_label}")),
        color=alt.Color("{group}:N", legend=alt.Legend(title="{group_label}")),
        tooltip=["{group}", "{x}", "{y}", "{size_field}"]
    )
    st.altair_chart(c, use_container_width=True)''')
            else:
                code_parts.append(f'''    # Bubble: scatter with size encoding
    c = alt.Chart(chart_data).mark_circle(color="{primary_color}").encode(
        x=alt.X("{x}:Q", title="{x_label}"),
        y=alt.Y("{y}", title="{y_label}"),
        size=alt.Size("{size_field}:Q", scale=alt.Scale(range=[50, 500]), legend=alt.Legend(title="{size_label}")),
        tooltip=["{x}", "{y}", "{size_field}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "heatmap":
            # Heatmap needs aggregation by both x and y (like grouped bars)
            # The 'group' field serves as the y-axis categories
            heatmap_y = chart.get("group", y)  # Use group as y-axis if specified
            heatmap_y_label = self._humanize_column_name(heatmap_y)
            value_field = y  # The value to aggregate for color
            value_label = self._humanize_column_name(value_field)
            if sql_mode:
                # In SQL mode, chart_data already contains aggregated and limited data
                code_parts.append(f'''    # Heatmap: 2D grid with color intensity (data pre-aggregated by SQL query)
    heatmap_data = chart_data
    c = alt.Chart(heatmap_data).mark_rect().encode(
        x=alt.X("{x}:N", sort=None, title="{x_label}"),
        y=alt.Y("{heatmap_y}:N", title="{heatmap_y_label}"),
        color=alt.Color("{value_field}:Q",
            scale=alt.Scale(scheme="blues"),
            legend=alt.Legend(title="{value_label}")
        ),
        tooltip=["{x}", "{heatmap_y}", "{value_field}"]
    ).properties(width=600, height=400)
    st.altair_chart(c, use_container_width=True)''')
            else:
                code_parts.append(f'''    # Heatmap: 2D grid with color intensity
    # Re-aggregate for heatmap (group by both x and y)
    heatmap_data = chart_df.groupby(["{x}", "{heatmap_y}"])["{value_field}"].{agg}().reset_index()
    # Limit to top categories to prevent unreadable charts
    top_x = heatmap_data.groupby("{x}")["{value_field}"].sum().nlargest(15).index
    top_y = heatmap_data.groupby("{heatmap_y}")["{value_field}"].sum().nlargest(15).index
    heatmap_data = heatmap_data[heatmap_data["{x}"].isin(top_x) & heatmap_data["{heatmap_y}"].isin(top_y)]
    c = alt.Chart(heatmap_data).mark_rect().encode(
        x=alt.X("{x}:N", sort=None, title="{x_label}"),
        y=alt.Y("{heatmap_y}:N", title="{heatmap_y_label}"),
        color=alt.Color("{value_field}:Q",
            scale=alt.Scale(scheme="blues"),
            legend=alt.Legend(title="{value_label}")
        ),
        tooltip=["{x}", "{heatmap_y}", "{value_field}"]
    ).properties(width=600, height=400)
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "pie":
            # Use secondary colors from theme for categorical data
            code_parts.append(f'''    # Use theme secondary colors for pie chart
    theme_colors = {secondary_colors}
    c = alt.Chart(chart_data).mark_arc().encode(
        theta=alt.Theta("{y}:Q"),
        color=alt.Color("{x}:N",
            scale=alt.Scale(range=theme_colors),
            legend=alt.Legend(title="{x_label}")
        ),
        tooltip=["{x}", "{y}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "area":
            code_parts.append(f'''    c = alt.Chart(chart_data).mark_area(color="{primary_color}", opacity=0.7).encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None, title="{x_label}"),
        y=alt.Y("{y}", title="{y_label}"),
        tooltip=["{x}", "{y}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "histogram":
            # Histogram uses binning on x axis, no aggregation needed
            code_parts.append(f'''    # Histogram: bin {x} values into {bins} bins
    c = alt.Chart(chart_df).mark_bar(color="{primary_color}").encode(
        x=alt.X("{x}:Q", bin=alt.Bin(maxbins={bins}), title="{x_label}"),
        y=alt.Y("count()", title="Count"),
        tooltip=["count()"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "box":
            # Box plot: shows distribution (min, Q1, median, Q3, max)
            code_parts.append(f'''    # Box plot: distribution by {x}
    c = alt.Chart(chart_df).mark_boxplot(color="{primary_color}").encode(
        x=alt.X("{x}:N", title="{x_label}"),
        y=alt.Y("{y}:Q", title="{y_label}"),
        tooltip=["{x}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "stacked_bar":
            # Use secondary colors from theme for stacked segments
            group_label = self._humanize_column_name(group) if group else group
            code_parts.append(f'''    # Stacked bar: stack {y} by {group}
    theme_colors = {secondary_colors}
    c = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None, title="{x_label}"),
        y=alt.Y("{y}:Q", stack="zero", title="{y_label}"),
        color=alt.Color("{group}:N",
            scale=alt.Scale(range=theme_colors),
            legend=alt.Legend(title="{group_label}")
        ),
        tooltip=["{x}", "{group}", "{y}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "grouped_bar":
            # Use secondary colors from theme for grouped bars
            group_label = self._humanize_column_name(group) if group else group
            code_parts.append(f'''    # Grouped bar: group {y} by {group}
    theme_colors = {secondary_colors}
    c = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None, title="{x_label}"),
        y=alt.Y("{y}:Q", title="{y_label}"),
        color=alt.Color("{group}:N",
            scale=alt.Scale(range=theme_colors),
            legend=alt.Legend(title="{group_label}")
        ),
        xOffset="{group}:N",
        tooltip=["{x}", "{group}", "{y}"]
    )
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "geo":
            # Choropleth map using Altair with world topojson
            code_parts.append(f'''    # Geo chart: choropleth map colored by {y}
    # Normalize country names: strip whitespace and convert to title case to match topojson
    geo_data = chart_data.copy()
    geo_data["{x}"] = geo_data["{x}"].fillna("").str.strip().str.title()
    # Re-aggregate after normalization (merges any entries that differ only by case)
    geo_data = geo_data[geo_data["{x}"] != ""].groupby("{x}")["{y}"].sum().reset_index()

    # Load world countries topojson (has country names in properties.name)
    countries_url = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"
    countries = alt.topo_feature(countries_url, "countries")

    # Create choropleth map (two layers: background + data)
    background = alt.Chart(countries).mark_geoshape(
        fill="#e0e0e0",
        stroke="#aaa",
        strokeWidth=0.5
    ).project(
        type="naturalEarth1"
    ).properties(
        width=800,
        height=450
    )
    foreground = alt.Chart(countries).mark_geoshape(
        stroke="#aaa",
        strokeWidth=0.5
    ).encode(
        color=alt.Color("{y}:Q",
            scale=alt.Scale(scheme="blues"),
            legend=alt.Legend(title="{y_label}")
        ),
        tooltip=["properties.name:N", "{y}:Q"]
    ).transform_lookup(
        lookup="properties.name",
        from_=alt.LookupData(data=geo_data, key="{x}", fields=["{y}"])
    ).project(
        type="naturalEarth1"
    ).properties(
        width=800,
        height=450
    )
    c = background + foreground
    st.altair_chart(c, use_container_width=True)''')

        else:
            code_parts.append(f'    st.warning("Unsupported chart type: {chart_type}")')

        return "\n".join(code_parts)

    def _generate_pages(self, pages: list, colors: Dict[str, Any], sql_mode: bool = False) -> str:
        code_parts = []
        tab_titles = []
        for page in pages:
            title = page.get("title", page.get("id"))
            tab_titles.append(f'"{title}"')

        tab_vars = ", ".join([f"tab{i+1}" for i in range(len(pages))])
        tab_list = ", ".join(tab_titles)
        code_parts.append(f'    {tab_vars} = st.tabs([{tab_list}])')
        code_parts.append("")

        for i, page in enumerate(pages):
            tab_var = f"tab{i+1}"
            code_parts.append(f'    with {tab_var}:')

            if page.get("description"):
                desc = page["description"]
                code_parts.append(f'        st.markdown("*{desc}*")')
                code_parts.append('        st.divider()')
                code_parts.append("")

            page_charts = page.get("charts", [])
            # Layout charts in rows of 2 columns
            for j in range(0, len(page_charts), 2):
                if j + 1 < len(page_charts):
                    # Two charts side by side
                    code_parts.append(f'        col1, col2 = st.columns(2)')
                    for col_idx, chart in enumerate([page_charts[j], page_charts[j + 1]]):
                        col_var = f"col{col_idx + 1}"
                        code_parts.append(f'        with {col_var}:')
                        chart_code = self._generate_chart(chart, colors, sql_mode=sql_mode)
                        indented_chart = "\n".join(f"        {line}" for line in chart_code.split("\n"))
                        code_parts.append(indented_chart)
                else:
                    # Single remaining chart at full width
                    chart_code = self._generate_chart(page_charts[j], colors, sql_mode=sql_mode)
                    indented_chart = "\n".join(f"    {line}" for line in chart_code.split("\n"))
                    code_parts.append(indented_chart)

                if j + 2 < len(page_charts):
                    code_parts.append('        st.divider()')
                code_parts.append("")

        return "\n".join(code_parts)

    def get_run_command(self, output_path: str) -> str:
        return f"streamlit run {output_path}"