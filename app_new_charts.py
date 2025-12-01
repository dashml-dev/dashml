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

    # Load data
    try:
        df = pd.read_csv("data/example.csv")
    except FileNotFoundError:
        st.error("Data file not found: data/example.csv")
        return
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    tab1, tab2, tab3 = st.tabs(["📊 Basic Charts", "✨ New Chart Types", "🚧 Coming Soon"])

    with tab1:
        st.markdown("*Original chart types (bar, line, scatter, pie)*")
        st.divider()

        # Chart: bar_example
        st.subheader("Bar Chart")
        # Aggregate: sum(sales) group by country
        chart_data = df.groupby("country")["sales"].sum().reset_index()
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("country", sort=None),
            y="sales",
            tooltip=["country", "sales"]
        ).properties(title="Bar Chart")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: line_example
        st.subheader("Line Chart")
        # Aggregate: sum(sales) group by date
        chart_data = df.groupby("date")["sales"].sum().reset_index()
        c = alt.Chart(chart_data).mark_line(color="#bd93f9", point=True).encode(
            x=alt.X("date", sort=None),
            y="sales",
            tooltip=["date", "sales"]
        ).properties(title="Line Chart")
        st.altair_chart(c, use_container_width=True)

    with tab2:
        st.markdown("*Priority 1 additions (area, histogram)*")
        st.divider()

        # Chart: area_example
        st.subheader("Area Chart - Sales Over Time")
        # Aggregate: sum(sales) group by date
        chart_data = df.groupby("date")["sales"].sum().reset_index()
        c = alt.Chart(chart_data).mark_area(color="#bd93f9", opacity=0.7).encode(
            x=alt.X("date", sort=None),
            y="sales",
            tooltip=["date", "sales"]
        ).properties(title="Area Chart - Sales Over Time")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: histogram_example
        st.subheader("Histogram - Sales Distribution")
        # Histogram: bin sales values
        c = alt.Chart(df).mark_bar(color="#bd93f9").encode(
            x=alt.X("sales:Q", bin=True),
            y="count()",
            tooltip=["count()"]
        ).properties(title="Histogram - Sales Distribution")
        st.altair_chart(c, use_container_width=True)

    with tab3:
        st.markdown("*Charts requiring schema extensions*")
        st.divider()

        # Chart: stacked_example
        st.subheader("Stacked Bar (Not Yet Supported)")
        # Aggregate: sum(sales) group by country
        chart_data = df.groupby("country")["sales"].sum().reset_index()
        st.warning("stacked_bar not yet fully implemented")
        st.divider()

        # Chart: grouped_example
        st.subheader("Grouped Bar (Not Yet Supported)")
        # Aggregate: sum(sales) group by country
        chart_data = df.groupby("country")["sales"].sum().reset_index()
        st.warning("grouped_bar not yet fully implemented")


if __name__ == "__main__":
    main()