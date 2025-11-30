import streamlit as st
import pandas as pd

def main():
    st.set_page_config(
        page_title="DashML Example Dashboard",
        page_icon="📊",
        layout="wide"
    )
    st.title("DashML Example Dashboard")

    # Load data
    try:
        df = pd.read_csv("data/example.csv")
    except FileNotFoundError:
        st.error("Data file not found: data/example.csv")
        return
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    # Chart: sales_by_country
    st.subheader("Sales by country")
    # Aggregate: sum(sales) group by country
    chart_data = df.groupby("country")["sales"].sum().reset_index()
    chart_data = chart_data.set_index("country")["sales"]
    st.bar_chart(chart_data)
    st.divider()

    # Chart: sales_over_time
    st.subheader("Sales over time")
    # Aggregate: sum(sales) group by date
    chart_data = df.groupby("date")["sales"].sum().reset_index()
    chart_data = chart_data.set_index("date")["sales"]
    st.line_chart(chart_data)


if __name__ == "__main__":
    main()