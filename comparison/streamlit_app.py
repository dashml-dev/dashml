import streamlit as st
import pandas as pd
import altair as alt

def main():
    st.set_page_config(
        page_title="Simple Dashboard",
        page_icon="📊",
        layout="wide"
    )
    st.title("Simple Dashboard")

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