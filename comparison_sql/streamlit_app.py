import streamlit as st
import pandas as pd
import altair as alt
from sqlalchemy import create_engine

def main():
    st.set_page_config(
        page_title="Simple Dashboard",
        page_icon="📊",
        layout="wide"
    )
    st.title("Simple Dashboard")

    # Load data from SQL database
    try:
        engine = create_engine("postgresql://user:pass@localhost:5432/mydb")
        df = pd.read_sql("SELECT * FROM public.orders", engine)

        # Fetch column types from information_schema for auto type detection
        schema_query = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'orders'
        """
        schema_df = pd.read_sql(schema_query, engine)

        # Build column type mapping: date, number, string
        column_types = {}
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
        st.error(f"Error loading data from database: {e}")
        return

    # Chart: sales_chart
    st.subheader("Sales by Country")
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
    c = alt.Chart(chart_data).mark_bar(color="#29b5e8").encode(
        x=alt.X("country" + x_encoding_suffix, sort=None),
        y="sales",
        tooltip=["country", "sales"]
    ).properties(title="Sales by Country")
    st.altair_chart(c, use_container_width=True)


if __name__ == "__main__":
    main()