import streamlit as st
import pandas as pd
import altair as alt
from google.cloud import bigquery

def main():
    st.set_page_config(
        page_title="BigQuery Definitive - All Chart Types",
        page_icon="📊",
        layout="wide"
    )
    # Apply Custom Styling
    st.markdown("""
        <style>
        .stApp {
            background-color: #ffffff;
            color: #000000;
        }
        h1, h2, h3, p, li, .stMarkdown, .stMetricValue, .stMetricLabel {
            color: #000000 !important;
        }
        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
            color: #000000;
        }
        </style>
    """, unsafe_allow_html=True)
    st.title("BigQuery Definitive - All Chart Types")

    # Load data from BigQuery
    try:
        # Use default credentials (from gcloud auth or GOOGLE_APPLICATION_CREDENTIALS env var)
        client = bigquery.Client(project="big-data-project-sn")

        query = """
            SELECT *
            FROM `big-data-project-sn.sales.orders`
            LIMIT 10000
        """
        df = client.query(query).to_dataframe()

        # Infer column types from pandas dtypes for auto type detection
        column_types = {}
        for col in df.columns:
            dtype = str(df[col].dtype)
            if 'datetime' in dtype or 'date' in dtype:
                column_types[col] = 'date'
            elif 'int' in dtype or 'float' in dtype:
                column_types[col] = 'number'
            else:
                column_types[col] = 'string'
    except Exception as e:
        st.error(f"Error loading data from BigQuery: {e}")
        return

    tab1, tab2, tab3 = st.tabs(["Categorical Charts", "Time Series Charts", "Distribution & Relationships"])

    with tab1:
        st.markdown("*Bar charts and pie charts for categorical data*")
        st.divider()

        # Chart: bar_sales_by_country
        st.subheader("Total Sales by Country")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("shipping_address_country")
        # Aggregate: sum(total_amount) group by shipping_address_country
        chart_data = chart_df.groupby("shipping_address_country")["total_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["shipping_address_country"] = pd.to_datetime(chart_data["shipping_address_country"])
            chart_data = chart_data.sort_values("shipping_address_country")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("shipping_address_country")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("shipping_address_country")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#29b5e8").encode(
            x=alt.X("shipping_address_country" + x_encoding_suffix, sort=None),
            y="total_amount",
            tooltip=["shipping_address_country", "total_amount"]
        ).properties(title="Total Sales by Country")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: pie_orders_by_status
        st.subheader("Orders by Status")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("status")
        # Aggregate: count(order_id) group by status
        chart_data = chart_df.groupby("status")["order_id"].count().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["status"] = pd.to_datetime(chart_data["status"])
            chart_data = chart_data.sort_values("status")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("status")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("status")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Use theme secondary colors for pie chart
        theme_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        c = alt.Chart(chart_data).mark_arc().encode(
            theta=alt.Theta("order_id:Q"),
            color=alt.Color("status:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="status")
            ),
            tooltip=["status", "order_id"]
        ).properties(title="Orders by Status")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: grouped_bar_country_status
        st.subheader("Orders by Country (Grouped by Status)")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("shipping_address_country")
        # Aggregate: count(order_id) group by shipping_address_country and status
        chart_data = chart_df.groupby(["shipping_address_country", "status"])["order_id"].count().reset_index()
        # Sort by y field (desc)
        chart_data = chart_data.sort_values("order_id", ascending=False)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Grouped bar: group order_id by status
        theme_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        c = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("shipping_address_country" + x_encoding_suffix, sort=None),
            y="order_id:Q",
            color=alt.Color("status:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="status")
            ),
            xOffset="status:N",
            tooltip=["shipping_address_country", "status", "order_id"]
        ).properties(title="Orders by Country (Grouped by Status)")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: stacked_bar_payment_status
        st.subheader("Orders by Payment Method (Stacked by Status)")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("payment_method")
        # Aggregate: count(order_id) group by payment_method and status
        chart_data = chart_df.groupby(["payment_method", "status"])["order_id"].count().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["payment_method"] = pd.to_datetime(chart_data["payment_method"])
            chart_data = chart_data.sort_values("payment_method")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("payment_method")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("payment_method")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Stacked bar: stack order_id by status
        theme_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        c = alt.Chart(chart_data).mark_bar().encode(
            x=alt.X("payment_method" + x_encoding_suffix, sort=None),
            y=alt.Y("order_id:Q", stack="zero"),
            color=alt.Color("status:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="status")
            ),
            tooltip=["payment_method", "status", "order_id"]
        ).properties(title="Orders by Payment Method (Stacked by Status)")
        st.altair_chart(c, use_container_width=True)

    with tab2:
        st.markdown("*Line and area charts for temporal trends*")
        st.divider()

        # Chart: line_orders_over_time
        st.subheader("Orders Over Time")
        chart_df = df.copy()
        effective_x_type = "date" if "date" != "None" else column_types.get("order_date")
        # Aggregate: count(order_id) group by order_date
        chart_data = chart_df.groupby("order_date")["order_id"].count().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["order_date"] = pd.to_datetime(chart_data["order_date"])
            chart_data = chart_data.sort_values("order_date")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("order_date")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("order_date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_line(color="#29b5e8", point=True).encode(
            x=alt.X("order_date" + x_encoding_suffix, sort=None),
            y="order_id",
            tooltip=["order_date", "order_id"]
        ).properties(title="Orders Over Time")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: area_revenue_over_time
        st.subheader("Revenue Over Time")
        chart_df = df.copy()
        effective_x_type = "date" if "date" != "None" else column_types.get("order_date")
        # Aggregate: sum(total_amount) group by order_date
        chart_data = chart_df.groupby("order_date")["total_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["order_date"] = pd.to_datetime(chart_data["order_date"])
            chart_data = chart_data.sort_values("order_date")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("order_date")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("order_date")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_area(color="#29b5e8", opacity=0.7).encode(
            x=alt.X("order_date" + x_encoding_suffix, sort=None),
            y="total_amount",
            tooltip=["order_date", "total_amount"]
        ).properties(title="Revenue Over Time")
        st.altair_chart(c, use_container_width=True)

    with tab3:
        st.markdown("*Scatter plots and histograms*")
        st.divider()

        # Chart: scatter_amount_vs_tax
        st.subheader("Order Amount vs Tax Amount")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("total_amount")
        # Aggregate: sum(tax_amount) group by total_amount
        chart_data = chart_df.groupby("total_amount")["tax_amount"].sum().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["total_amount"] = pd.to_datetime(chart_data["total_amount"])
            chart_data = chart_data.sort_values("total_amount")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("total_amount")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("total_amount")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Scatter: aggregated data points
        c = alt.Chart(chart_data).mark_circle(color="#29b5e8", size=60).encode(
            x=alt.X("total_amount" + x_encoding_suffix, sort=None),
            y="tax_amount",
            tooltip=["total_amount", "tax_amount"]
        ).properties(title="Order Amount vs Tax Amount")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: histogram_order_amounts
        st.subheader("Distribution of Order Amounts")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("total_amount")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Histogram: bin total_amount values into 20 bins
        c = alt.Chart(chart_df).mark_bar(color="#29b5e8").encode(
            x=alt.X("total_amount:Q", bin=alt.Bin(maxbins=20)),
            y="count()",
            tooltip=["count()"]
        ).properties(title="Distribution of Order Amounts")
        st.altair_chart(c, use_container_width=True)


if __name__ == "__main__":
    main()