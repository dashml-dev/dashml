import streamlit as st
import pandas as pd
import altair as alt
from sqlalchemy import create_engine

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

    # Load data from SQL database
    try:
        engine = create_engine("postgresql://neondb_owner:npg_fm0ZpyB5CQkT@ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech:5432/neondb")
        df = pd.read_sql("SELECT * FROM public.orders", engine)
    except Exception as e:
        st.error(f"Error loading data from database: {e}")
        return

    tab1, tab2 = st.tabs(["📊 Overview", "📈 Trends"])

    with tab1:
        st.markdown("*High-level sales metrics and KPIs*")
        st.divider()

        # Chart: total_sales_by_country
        st.subheader("Total Sales by State")
        # Aggregate: sum(total_amount) group by shipping_address_state
        chart_data = df.groupby("shipping_address_state")["total_amount"].sum().reset_index()
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("shipping_address_state", sort=None),
            y="total_amount",
            tooltip=["shipping_address_state", "total_amount"]
        ).properties(title="Total Sales by State")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: country_sales_breakdown
        st.subheader("Market Share by State")
        # Aggregate: sum(total_amount) group by shipping_address_state
        chart_data = df.groupby("shipping_address_state")["total_amount"].sum().reset_index()
        # Use theme secondary colors for pie chart
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_arc().encode(
            theta=alt.Theta("total_amount:Q"),
            color=alt.Color("shipping_address_state:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="shipping_address_state")
            ),
            tooltip=["shipping_address_state", "total_amount"]
        ).properties(title="Market Share by State")
        st.altair_chart(c, use_container_width=True)

    with tab2:
        st.markdown("*Sales trends and patterns over time*")
        st.divider()

        # Chart: sales_over_time
        st.subheader("Sales Over Time")
        # Aggregate: sum(total_amount) group by order_date
        chart_data = df.groupby("order_date")["total_amount"].sum().reset_index()
        c = alt.Chart(chart_data).mark_line(color="#bd93f9", point=True).encode(
            x=alt.X("order_date", sort=None),
            y="total_amount",
            tooltip=["order_date", "total_amount"]
        ).properties(title="Sales Over Time")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: average_sales_trend
        st.subheader("Average Daily Sales")
        # Aggregate: mean(total_amount) group by order_date
        chart_data = df.groupby("order_date")["total_amount"].mean().reset_index()
        c = alt.Chart(chart_data).mark_line(color="#bd93f9", point=True).encode(
            x=alt.X("order_date", sort=None),
            y="total_amount",
            tooltip=["order_date", "total_amount"]
        ).properties(title="Average Daily Sales")
        st.altair_chart(c, use_container_width=True)


if __name__ == "__main__":
    main()