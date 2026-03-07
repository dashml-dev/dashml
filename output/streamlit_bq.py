import streamlit as st
import pandas as pd
import altair as alt
from google.cloud import bigquery

def main():
    st.set_page_config(
        page_title="Flight Punctuality Dashboard",
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
    st.title("Flight Punctuality Dashboard")

    # Load data from BigQuery
    try:
        # Use default credentials (from gcloud auth or GOOGLE_APPLICATION_CREDENTIALS env var)
        client = bigquery.Client(project="flight-delays-482611")

        query = """
            SELECT *
            FROM `flight-delays-482611.gold.punctuality_gold`
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

    tab1, tab2, tab3 = st.tabs(["Overview", "Delays", "Cancellations"])

    with tab1:
        st.markdown("*High-level flight punctuality metrics*")
        st.divider()

        # Chart: flights_by_airline
        st.subheader("Top 15 Airlines by Total Flights")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("airline_name")
        # Aggregate: sum(total_flights) group by airline_name
        chart_data = chart_df.groupby("airline_name")["total_flights"].sum().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("total_flights", ascending=True)
        # Limit to top 15 rows
        chart_data = chart_data.head(15)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("airline_name" + x_encoding_suffix, sort=None),
            y="total_flights",
            tooltip=["airline_name", "total_flights"]
        ).properties(title="Top 15 Airlines by Total Flights")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: airline_share
        st.subheader("Flight Share - Top 10 Airlines")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("airline_name")
        # Aggregate: sum(total_flights) group by airline_name
        chart_data = chart_df.groupby("airline_name")["total_flights"].sum().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("total_flights", ascending=True)
        # Limit to top 10 rows
        chart_data = chart_data.head(10)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        # Use theme secondary colors for pie chart
        theme_colors = ['#50fa7b', '#ffb86c', '#ff5555', '#8be9fd', '#f1fa8c']
        c = alt.Chart(chart_data).mark_arc().encode(
            theta=alt.Theta("total_flights:Q"),
            color=alt.Color("airline_name:N",
                scale=alt.Scale(range=theme_colors),
                legend=alt.Legend(title="airline_name")
            ),
            tooltip=["airline_name", "total_flights"]
        ).properties(title="Flight Share - Top 10 Airlines")
        st.altair_chart(c, use_container_width=True)

    with tab2:
        st.markdown("*Delay patterns and trends*")
        st.divider()

        # Chart: avg_delay_by_airline
        st.subheader("Average Delay (mins) - Top 15 Airlines")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("airline_name")
        # Aggregate: mean(average_delay_mins) group by airline_name
        chart_data = chart_df.groupby("airline_name")["average_delay_mins"].mean().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("average_delay_mins", ascending=True)
        # Limit to top 15 rows
        chart_data = chart_data.head(15)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("airline_name" + x_encoding_suffix, sort=None),
            y="average_delay_mins",
            tooltip=["airline_name", "average_delay_mins"]
        ).properties(title="Average Delay (mins) - Top 15 Airlines")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: delay_over_time
        st.subheader("Average Delay Over Time")
        chart_df = df.copy()
        effective_x_type = "date" if "date" != "None" else column_types.get("reporting_month")
        # Aggregate: mean(average_delay_mins) group by reporting_month
        chart_data = chart_df.groupby("reporting_month")["average_delay_mins"].mean().reset_index()
        if effective_x_type == "date":
            # Sort by date for chronological order
            chart_data["reporting_month"] = pd.to_datetime(chart_data["reporting_month"])
            chart_data = chart_data.sort_values("reporting_month")
        elif effective_x_type == "number":
            # Sort by number for numerical order
            chart_data = chart_data.sort_values("reporting_month")
        else:
            # Sort strings alphabetically for consistency across transformers
            chart_data = chart_data.sort_values("reporting_month")
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_line(color="#bd93f9", point=True).encode(
            x=alt.X("reporting_month" + x_encoding_suffix, sort=None),
            y="average_delay_mins",
            tooltip=["reporting_month", "average_delay_mins"]
        ).properties(title="Average Delay Over Time")
        st.altair_chart(c, use_container_width=True)

    with tab3:
        st.markdown("*Cancellation rates across airlines and destinations*")
        st.divider()

        # Chart: cancellation_by_airline
        st.subheader("Cancellation Rate (%) - Top 15 Airlines by Flights")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("airline_name")
        # Aggregate: mean(flights_cancelled_percent) group by airline_name
        chart_data = chart_df.groupby("airline_name")["flights_cancelled_percent"].mean().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("flights_cancelled_percent", ascending=True)
        # Limit to top 15 rows
        chart_data = chart_data.head(15)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("airline_name" + x_encoding_suffix, sort=None),
            y="flights_cancelled_percent",
            tooltip=["airline_name", "flights_cancelled_percent"]
        ).properties(title="Cancellation Rate (%) - Top 15 Airlines by Flights")
        st.altair_chart(c, use_container_width=True)
        st.divider()

        # Chart: cancellation_by_destination
        st.subheader("Cancellation Rate (%) - Top 15 Destination Countries")
        chart_df = df.copy()
        effective_x_type = "None" if "None" != "None" else column_types.get("origin_destination_country")
        # Aggregate: mean(flights_cancelled_percent) group by origin_destination_country
        chart_data = chart_df.groupby("origin_destination_country")["flights_cancelled_percent"].mean().reset_index()
        # Sort by y field (asc)
        chart_data = chart_data.sort_values("flights_cancelled_percent", ascending=True)
        # Limit to top 15 rows
        chart_data = chart_data.head(15)
        # Determine Altair encoding type based on effective x_type
        x_encoding_suffix = ":T" if effective_x_type == "date" else (":Q" if effective_x_type == "number" else "")
        c = alt.Chart(chart_data).mark_bar(color="#bd93f9").encode(
            x=alt.X("origin_destination_country" + x_encoding_suffix, sort=None),
            y="flights_cancelled_percent",
            tooltip=["origin_destination_country", "flights_cancelled_percent"]
        ).properties(title="Cancellation Rate (%) - Top 15 Destination Countries")
        st.altair_chart(c, use_container_width=True)


if __name__ == "__main__":
    main()