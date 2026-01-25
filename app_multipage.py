import streamlit as st
import pandas as pd
import altair as alt

def main():
    st.set_page_config(
        page_title="Sales Analytics Dashboard",
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
    st.title("Sales Analytics Dashboard")

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

    tab1, tab2, tab3 = st.tabs(["📊 Overview", "📈 Trends", "🔍 Detailed Analysis"])

    with tab1:
        st.markdown("*High-level sales metrics and KPIs*")
        st.divider()

        # Chart: total_sales_by_country
        st.subheader("Total Sales by Country")
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
        ).properties(title="Total Sales by Country")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: country_sales_breakdown
        st.subheader("Market Share by Country")
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
        # Use theme secondary colors for pie chart
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_arc().encode(
            theta=alt.Theta("sales:Q"),
            color=alt.Color("country:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="country")
            ),
            tooltip=["country", "sales"]
        ).properties(title="Market Share by Country")
        st.altair_chart(c, use_container_width=True)

    with tab2:
        st.markdown("*Sales trends and patterns over time*")
        st.divider()

        # Chart: sales_over_time
        st.subheader("Sales Over Time")
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
        ).properties(title="Sales Over Time")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: average_sales_trend
        st.subheader("Average Daily Sales")
        effective_x_type = "None" if "None" != "None" else column_types.get("date")
        # Aggregate: mean(sales) group by date
        chart_data = df.groupby("date")["sales"].mean().reset_index()
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
        ).properties(title="Average Daily Sales")
        st.altair_chart(c, use_container_width=True)

    with tab3:
        st.markdown("*In-depth breakdown and analysis*")
        st.divider()

        # Chart: sales_count_by_country
        st.subheader("Number of Transactions by Country")
        effective_x_type = "None" if "None" != "None" else column_types.get("country")
        # Aggregate: count(sales) group by country
        chart_data = df.groupby("country")["sales"].count().reset_index()
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
        ).properties(title="Number of Transactions by Country")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: sales_scatter
        st.subheader("Sales Distribution Over Time")
        effective_x_type = "None" if "None" != "None" else column_types.get("date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Scatter: show raw data points
        c = alt.Chart(df).mark_circle(color="#bd93f9", size=60).encode(
            x=alt.X("date"),
            y="sales",
            tooltip=["date", "sales"]
        ).properties(title="Sales Distribution Over Time")
        st.altair_chart(c, use_container_width=True)


if __name__ == "__main__":
    main()