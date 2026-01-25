import streamlit as st
import pandas as pd
import altair as alt

def main():
    st.set_page_config(
        page_title="New Chart Types Demo",
        page_icon="📊",
        layout="wide"
    )
    # Apply Custom Styling
    st.markdown("""
        <style>
        .stApp {
            background-color: #282a36;
            color: #f8f8f2;
        }
        h1, h2, h3, p, li, .stMarkdown, .stMetricValue, .stMetricLabel {
            color: #f8f8f2 !important;
        }
        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
            color: #f8f8f2;
        }
        </style>
    """, unsafe_allow_html=True)
    st.title("New Chart Types Demo")

    # Load data from CSV
    try:
        df = pd.read_csv("data/example.csv")

        # Infer column types from pandas dtypes for auto type detection
        column_types = {}
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
        st.error("Data file not found: data/example.csv")
        return
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    tab1, tab2, tab3 = st.tabs(["📊 Basic Charts", "✨ New Chart Types", "📊 Advanced Charts"])

    with tab1:
        st.markdown("*Original chart types (bar, line, scatter, pie)*")
        st.divider()

        # Chart: bar_example
        st.subheader("Bar Chart")
        effective_x_type = "None" if "None" != "None" else column_types.get("country")
        # Aggregate: sum(sales) group by country
        chart_data = df.groupby("country")["sales"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["country"] = pd.to_datetime(chart_data["country"])
            chart_data = chart_data.sort_values("country")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("country")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("country" + x_encoding_suffix, sort=None),
            y="sales",
            tooltip=["country", "sales"]
        ).properties(title="Bar Chart")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: line_example
        st.subheader("Line Chart")
        effective_x_type = "None" if "None" != "None" else column_types.get("date")
        # Aggregate: sum(sales) group by date
        chart_data = df.groupby("date")["sales"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["date"] = pd.to_datetime(chart_data["date"])
            chart_data = chart_data.sort_values("date")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_line(color="#bd93f9", point=True).encode(
            x=alt.X("date" + x_encoding_suffix, sort=None),
            y="sales",
            tooltip=["date", "sales"]
        ).properties(title="Line Chart")
        st.altair_chart(c, use_container_width=True)

    with tab2:
        st.markdown("*Priority 1 additions (area, histogram)*")
        st.divider()

        # Chart: area_example
        st.subheader("Area Chart - Sales Over Time")
        effective_x_type = "None" if "None" != "None" else column_types.get("date")
        # Aggregate: sum(sales) group by date
        chart_data = df.groupby("date")["sales"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["date"] = pd.to_datetime(chart_data["date"])
            chart_data = chart_data.sort_values("date")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_area(color="#bd93f9", opacity=0.7).encode(
            x=alt.X("date" + x_encoding_suffix, sort=None),
            y="sales",
            tooltip=["date", "sales"]
        ).properties(title="Area Chart - Sales Over Time")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: histogram_example
        st.subheader("Histogram - Sales Distribution")
        effective_x_type = "None" if "None" != "None" else column_types.get("sales")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Histogram: bin sales values
        c = alt.Chart(df).mark_bar(color="#bd93f9").encode(
            x=alt.X("sales:Q", bin=True),
            y="count()",
            tooltip=["count()"]
        ).properties(title="Histogram - Sales Distribution")
        st.altair_chart(c, use_container_width=True)

    with tab3:
        st.markdown("*Stacked and grouped bar charts*")
        st.divider()

        # Chart: stacked_example
        st.subheader("Stacked Bar - Sales by Country and Product")
        effective_x_type = "None" if "None" != "None" else column_types.get("country")
        # Aggregate: sum(sales) group by country and product
        chart_data = df.groupby(["country", "product"])["sales"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["country"] = pd.to_datetime(chart_data["country"])
            chart_data = chart_data.sort_values("country")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("country")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Stacked bar: stack sales by product
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("country" + x_encoding_suffix, sort=None),
            y=alt.Y("sales:Q", stack="zero"),
            color=alt.Color("product:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="product")
            ),
            tooltip=["country", "product", "sales"]
        ).properties(title="Stacked Bar - Sales by Country and Product")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: grouped_example
        st.subheader("Grouped Bar - Sales by Country and Product")
        effective_x_type = "None" if "None" != "None" else column_types.get("country")
        # Aggregate: sum(sales) group by country and product
        chart_data = df.groupby(["country", "product"])["sales"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["country"] = pd.to_datetime(chart_data["country"])
            chart_data = chart_data.sort_values("country")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("country")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Grouped bar: group sales by product
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("country" + x_encoding_suffix, sort=None),
            y="sales:Q",
            color=alt.Color("product:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="product")
            ),
            xOffset="product:N",
            tooltip=["country", "product", "sales"]
        ).properties(title="Grouped Bar - Sales by Country and Product")
        st.altair_chart(c, use_container_width=True)


if __name__ == "__main__":
    main()