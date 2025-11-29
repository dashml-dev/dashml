"""Auto-generated Streamlit dashboard from DashML"""
import streamlit as st
import pandas as pd


@st.cache_data
def load_default():
    """Load default dataset"""
    return pd.read_csv("data/example.csv")



def render_sales_by_country():
    """Render Sales by country"""
    df = load_default()
    
    # Apply filters

    # Aggregate
    grouped = df.groupby("country")["sales"].sum().reset_index()
    data = grouped.set_index("country")["sales"]
    
    # Render chart
    st.bar_chart(data)



def render_sales_over_time():
    """Render Sales over time"""
    df = load_default()
    
    # Apply filters

    # Aggregate
    grouped = df.groupby("date")["sales"].sum().reset_index()
    data = grouped.set_index("date")["sales"]
    
    # Render chart
    st.line_chart(data)



def main():
    st.title("DashML Example Dashboard")
    
    # Chart selector
    chart_options = {
        "sales_by_country": "Sales by country",
        "sales_over_time": "Sales over time",
    }
    
    selected = st.sidebar.selectbox("Select Chart", list(chart_options.keys()), format_func=lambda x: chart_options[x])
    
    st.subheader(chart_options[selected])
    
    # Render selected chart
    if selected == "sales_by_country":
        render_sales_by_country()
    elif selected == "sales_over_time":
        render_sales_over_time()


if __name__ == "__main__":
    main()
