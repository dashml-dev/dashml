"""
Streamlit Transformer - Generates Streamlit Python code from DashML specs
"""
from typing import TYPE_CHECKING, Dict, Any, List
from pathlib import Path
import yaml
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
    from ..core.types import DashMLSpec, ChartSpec


class StreamlitTransformer(Transformer):
    """
    Generates standalone Streamlit applications from DashML specifications.
    Output: Python code that can be run with `streamlit run app.py`
    """

    def __init__(self):
        super().__init__()
        self.db_config = None

    def set_db_config(self, config: Dict[str, Any]) -> None:
        """Store database configuration for SQL datasources"""
        self.db_config = config

    @property
    def name(self) -> str:
        return "streamlit"

    @property
    def description(self) -> str:
        return "Generates Streamlit Python applications"

    def build(self, spec: "DashMLSpec") -> str:
        """
        Generate Streamlit code from DashML spec.

        TODO: [SRP] This method does too much - handles imports, config, CSS, data loading, charts.
        Consider splitting into smaller methods like _assemble_code()
        """
        try:
            self.clear_warnings()  # Clear warnings from previous builds

            # Load style config first to get colors
            style_config = self._load_style_config(spec.get("style"))
            colors = style_config.get("colors", {})
            primary_color = colors.get("primary", "#29b5e8") # Default Streamlit blue-ish

            # Warn about unsupported color fields
            if colors.get("card"):
                self.warn("'card' color is not supported - Streamlit doesn't allow custom card backgrounds")
            if colors.get("buttons"):
                self.warn("'buttons' color is not supported - Streamlit button styling is limited")

            code_parts = []

            # Get data type
            data_type = spec["data"].get("type", "csv")

            # Imports
            code_parts.append(self._generate_imports(data_type))
            code_parts.append("")

            # Main function
            code_parts.append("def main():")

            # Page config
            title = spec.get("title", "DashML Dashboard")
            code_parts.append(self._generate_page_config(title))

            # Apply CSS Styling
            if "style" in spec:
                code_parts.append(self._generate_css_injection(style_config))

            # Title
            code_parts.append(f'    st.title("{title}")')
            code_parts.append("")

            # Data loading
            code_parts.append(self._generate_data_loading(spec["data"]))
            code_parts.append("")

            # Charts or Pages
            if "pages" in spec:
                code_parts.append(self._generate_pages(spec["pages"], colors))
            else:
                charts = spec.get("charts", [])
                for i, chart in enumerate(charts):
                    code_parts.append(self._generate_chart(chart, colors))
                    if i < len(charts) - 1:
                        code_parts.append('    st.divider()')
                    code_parts.append("")

            # Entry point
            code_parts.append("")
            code_parts.append('if __name__ == "__main__":')
            code_parts.append("    main()")

            return "\n".join(code_parts)

        except KeyError as e:
            raise TransformerError(f"Missing required field in spec: {e}")
        except Exception as e:
            raise TransformerError(f"Failed to generate Streamlit code: {e}")

    # _load_style_config is now inherited from base class

    def _generate_imports(self, data_type: str = "csv") -> str:
        imports = """import streamlit as st
import pandas as pd
import altair as alt
import plotly.express as px"""

        if data_type == "sql":
            imports += "\nfrom sqlalchemy import create_engine"
        elif data_type == "bigquery":
            imports += "\nfrom google.cloud import bigquery"

        return imports

    def _generate_page_config(self, title: str) -> str:
        return f'''    st.set_page_config(
        page_title="{title}",
        page_icon="📊",
        layout="wide"
    )'''

    # _parse_sql_path is now inherited from base class

    def _generate_css_injection(self, style_config: Dict) -> str:
        """Generate CSS to override Streamlit defaults"""
        colors = style_config.get('colors', {})
        bg_color = colors.get('background', '#ffffff')
        text_color = colors.get('text', '#000000')

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
        </style>
    """, unsafe_allow_html=True)'''

    def _generate_data_loading(self, data_spec: Dict[str, Any]) -> str:
        data_type = data_spec.get("type", "csv")

        if data_type == "csv":
            path = data_spec["path"]
            return f'''    # Load data from CSV
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
    except FileNotFoundError:
        st.error("Data file not found: {path}")
        return
    except Exception as e:
        st.error(f"Error loading data: {{e}}")
        return'''

        elif data_type == "sql":
            if not self.db_config:
                return '''    st.error("Database configuration not provided")
    return'''

            # Extract database config
            db_type = self.db_config["type"]
            host = self.db_config["host"]
            port = self.db_config["port"]
            database = self.db_config["database"]
            user = self.db_config["user"]
            password = self.db_config["password"]

            # Extract SQL spec fields (support both new path format and legacy format)
            if "path" in data_spec:
                schema, table_name = self._parse_sql_path(data_spec["path"])
            else:
                schema = data_spec["schema"]
                table_name = data_spec["table_name"]

            # Build connection string based on database type
            if db_type == "postgresql":
                conn_str = f"postgresql://{user}:{password}@{host}:{port}/{database}"
            elif db_type == "mysql":
                conn_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            elif db_type == "sqlite":
                conn_str = f"sqlite:///{database}"
            else:
                return f'''    st.error("Unsupported database type: {db_type}")
    return'''

            # Generate data loading code with schema detection
            return f'''    # Load data from SQL database
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
    except Exception as e:
        st.error(f"Error loading data from database: {{e}}")
        return'''

        elif data_type == "bigquery":
            if not self.db_config:
                return '''    st.error("BigQuery configuration not provided")
    return'''

            # Extract BigQuery config
            project = self.db_config["project"]
            credentials_path = self.db_config.get("credentials_path")

            # Parse dataset.table from path
            path = data_spec["path"]
            parts = path.split(".")
            if len(parts) == 2:
                dataset, table_name = parts
            else:
                return f'''    st.error("Invalid BigQuery path format: {path}. Expected: dataset.table")
    return'''

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

            return f'''    # Load data from BigQuery
    try:{credentials_code}

        query = """
            SELECT *
            FROM `{project}.{dataset}.{table_name}`
            LIMIT 10000
        """
        df = client.query(query).to_dataframe()

        # Infer column types from pandas dtypes for auto type detection
        column_types = {{}}
        for col in df.columns:
            dtype = str(df[col].dtype)
            if 'datetime' in dtype or 'date' in dtype:
                column_types[col] = 'date'
            elif 'int' in dtype or 'float' in dtype:
                column_types[col] = 'number'
            else:
                column_types[col] = 'string'
    except Exception as e:
        st.error(f"Error loading data from BigQuery: {{e}}")
        return'''

        else:
            return f'''    st.error("Unsupported data type: {data_type}")
    return'''

    def _generate_chart(self, chart: Dict[str, Any], colors: Dict[str, Any]) -> str:
        """Generate Altair chart code with explicit colors"""
        chart_id = chart["id"]
        chart_type = chart["type"]
        title = chart.get("title", chart_id)
        x = chart["x"]
        y = chart["y"]
        agg = chart.get("agg", "sum")
        group = chart.get("group")  # Optional grouping field for stacked/grouped bars
        x_type = chart.get("x_type")  # Optional: "date", "number", "string" for sorting
        y_type = chart.get("y_type")  # Optional: "number", "string" for casting
        bins = chart.get("bins", DEFAULT_HISTOGRAM_BINS)
        filters = chart.get("filters", [])  # Optional: filter conditions
        sort_field = chart.get("sort")  # Optional: "x" or "y"
        sort_order = chart.get("sort_order", "asc")  # Optional: "asc" or "desc"
        limit = chart.get("limit")  # Optional: max rows after aggregation

        # Extract colors using constants
        primary_color = colors.get("primary", DEFAULT_PRIMARY_COLOR)
        secondary_colors = colors.get("secondary", DEFAULT_SECONDARY_COLORS)

        code_parts = []
        code_parts.append(f'    # Chart: {chart_id}')
        code_parts.append(f'    st.subheader("{title}")')

        # Create working copy of dataframe for this chart
        code_parts.append(f'    chart_df = df.copy()')

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
        if chart_type in CHARTS_NEED_AGGREGATION:
            # Use AGG_METHODS constant
            agg_method = AGG_METHODS.get(agg, "sum")

            # For stacked/grouped bars, aggregate by both x and group
            if chart_type in ["stacked_bar", "grouped_bar"] and group:
                code_parts.append(f'    # Aggregate: {agg}({y}) group by {x} and {group}')
                code_parts.append(f'    chart_data = chart_df.groupby(["{x}", "{group}"])["{y}"].{agg_method}().reset_index()')
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
        x=alt.X("{x}" + x_encoding_suffix, sort=None),
        y="{y}",
        tooltip=["{x}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "line":
            code_parts.append(f'''    c = alt.Chart(chart_data).mark_line(color="{primary_color}", point=True).encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None),
        y="{y}",
        tooltip=["{x}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "scatter":
            code_parts.append(f'''    # Scatter: aggregated data points
    c = alt.Chart(chart_data).mark_circle(color="{primary_color}", size=60).encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None),
        y="{y}",
        tooltip=["{x}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "pie":
            # Use secondary colors from theme for categorical data
            code_parts.append(f'''    # Use theme secondary colors for pie chart
    theme_colors = {secondary_colors}
    c = alt.Chart(chart_data).mark_arc().encode(
        theta=alt.Theta("{y}:Q"),
        color=alt.Color("{x}:N",
            scale=alt.Scale(range=theme_colors),
            legend=alt.Legend(title="{x}")
        ),
        tooltip=["{x}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "area":
            code_parts.append(f'''    c = alt.Chart(chart_data).mark_area(color="{primary_color}", opacity=0.7).encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None),
        y="{y}",
        tooltip=["{x}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "histogram":
            # Histogram uses binning on x axis, no aggregation needed
            code_parts.append(f'''    # Histogram: bin {x} values into {bins} bins
    c = alt.Chart(chart_df).mark_bar(color="{primary_color}").encode(
        x=alt.X("{x}:Q", bin=alt.Bin(maxbins={bins})),
        y="count()",
        tooltip=["count()"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "stacked_bar":
            # Use secondary colors from theme for stacked segments
            code_parts.append(f'''    # Stacked bar: stack {y} by {group}
    theme_colors = {secondary_colors}
    c = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None),
        y=alt.Y("{y}:Q", stack="zero"),
        color=alt.Color("{group}:N",
            scale=alt.Scale(range=theme_colors),
            legend=alt.Legend(title="{group}")
        ),
        tooltip=["{x}", "{group}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "grouped_bar":
            # Use secondary colors from theme for grouped bars
            code_parts.append(f'''    # Grouped bar: group {y} by {group}
    theme_colors = {secondary_colors}
    c = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("{x}" + x_encoding_suffix, sort=None),
        y="{y}:Q",
        color=alt.Color("{group}:N",
            scale=alt.Scale(range=theme_colors),
            legend=alt.Legend(title="{group}")
        ),
        xOffset="{group}:N",
        tooltip=["{x}", "{group}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "geo":
            # Choropleth map using Plotly
            code_parts.append(f'''    # Geo chart: choropleth map colored by {y}
    fig = px.choropleth(
        chart_data,
        locations="{x}",
        locationmode="country names",
        color="{y}",
        hover_name="{x}",
        color_continuous_scale="Blues",
        title="{title}"
    )
    fig.update_layout(
        geo=dict(
            showframe=False,
            showcoastlines=True,
            projection_type="natural earth"
        ),
        margin=dict(l=0, r=0, t=40, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)''')

        else:
            code_parts.append(f'    st.warning("Unsupported chart type: {chart_type}")')

        return "\n".join(code_parts)

    def _generate_pages(self, pages: list, colors: Dict[str, Any]) -> str:
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
            for j, chart in enumerate(page_charts):
                chart_code = self._generate_chart(chart, colors)
                indented_chart = "\n".join(f"    {line}" for line in chart_code.split("\n"))
                code_parts.append(indented_chart)

                if j < len(page_charts) - 1:
                    code_parts.append('        st.divider()')
                code_parts.append("")

        return "\n".join(code_parts)

    def get_run_command(self, output_path: str) -> str:
        return f"streamlit run {output_path}"