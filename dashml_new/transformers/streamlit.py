"""
Streamlit Transformer - Generates Streamlit Python code from DashML specs
"""
from typing import TYPE_CHECKING, Dict, Any
from pathlib import Path
import yaml
from .base import Transformer, TransformerError

if TYPE_CHECKING:
    from ..core.types import DashMLSpec, ChartSpec

# Chart type categorization by data requirements
CHARTS_NEED_AGGREGATION = {"bar", "line", "area", "pie", "stacked_bar", "grouped_bar"}
CHARTS_USE_RAW_DATA = {"histogram", "scatter"}  # Charts that work with raw data points


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

    def build(self, spec: "DashMLSpec") -> str:
        """
        Generate Streamlit code from DashML spec.
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

            # Imports
            code_parts.append(self._generate_imports())
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

    def _load_style_config(self, style_path: str) -> Dict[str, Any]:
        """Read .dmls file during build"""
        if not style_path:
            return {}
        try:
            path = Path(style_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception:
            pass
        return {}

    def _generate_imports(self) -> str:
        return """import streamlit as st
import pandas as pd
import altair as alt"""

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
        data_type = data_spec["type"]
        path = data_spec["path"]

        if data_type == "csv":
            return f'''    # Load data
    try:
        df = pd.read_csv("{path}")
    except FileNotFoundError:
        st.error("Data file not found: {path}")
        return
    except Exception as e:
        st.error(f"Error loading data: {{e}}")
        return'''
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

        # Extract colors
        primary_color = colors.get("primary", "#29b5e8")
        secondary_colors = colors.get("secondary", ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'])

        code_parts = []
        code_parts.append(f'    # Chart: {chart_id}')
        code_parts.append(f'    st.subheader("{title}")')

        # Aggregation (only for chart types that need it)
        if chart_type in CHARTS_NEED_AGGREGATION:
            if agg == "sum":
                agg_method = "sum"
            elif agg == "mean":
                agg_method = "mean"
            elif agg == "count":
                agg_method = "count"
            else:
                agg_method = "sum"

            # For stacked/grouped bars, aggregate by both x and group
            if chart_type in ["stacked_bar", "grouped_bar"] and group:
                code_parts.append(f'    # Aggregate: {agg}({y}) group by {x} and {group}')
                code_parts.append(f'    chart_data = df.groupby(["{x}", "{group}"])["{y}"].{agg_method}().reset_index()')
            else:
                code_parts.append(f'    # Aggregate: {agg}({y}) group by {x}')
                code_parts.append(f'    chart_data = df.groupby("{x}")["{y}"].{agg_method}().reset_index()')

        # Altair Chart Generation
        if chart_type == "bar":
            code_parts.append(f'''    c = alt.Chart(chart_data).mark_bar(color="{primary_color}").encode(
        x=alt.X("{x}", sort=None),
        y="{y}",
        tooltip=["{x}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "line":
            code_parts.append(f'''    c = alt.Chart(chart_data).mark_line(color="{primary_color}", point=True).encode(
        x=alt.X("{x}", sort=None),
        y="{y}",
        tooltip=["{x}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "scatter":
            code_parts.append(f'''    # Scatter: show raw data points
    c = alt.Chart(df).mark_circle(color="{primary_color}", size=60).encode(
        x=alt.X("{x}"),
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
        x=alt.X("{x}", sort=None),
        y="{y}",
        tooltip=["{x}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "histogram":
            # Histogram uses binning on x axis, no aggregation needed
            code_parts.append(f'''    # Histogram: bin {x} values
    c = alt.Chart(df).mark_bar(color="{primary_color}").encode(
        x=alt.X("{x}:Q", bin=True),
        y="count()",
        tooltip=["count()"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

        elif chart_type == "stacked_bar":
            # Use secondary colors from theme for stacked segments
            code_parts.append(f'''    # Stacked bar: stack {y} by {group}
    theme_colors = {secondary_colors}
    c = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X("{x}", sort=None),
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
        x=alt.X("{x}", sort=None),
        y="{y}:Q",
        color=alt.Color("{group}:N",
            scale=alt.Scale(range=theme_colors),
            legend=alt.Legend(title="{group}")
        ),
        xOffset="{group}:N",
        tooltip=["{x}", "{group}", "{y}"]
    ).properties(title="{title}")
    st.altair_chart(c, use_container_width=True)''')

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