# Streamlit: Line chart with date x-axis
import streamlit as st
import pandas as pd
import altair as alt
from sqlalchemy import create_engine

st.title("Sales Trend")

engine = create_engine("postgresql://user:pass@localhost:5432/mydb")
df = pd.read_sql("SELECT * FROM public.orders", engine)

# Cast to date and sort
df["order_date"] = pd.to_datetime(df["order_date"])
chart_data = df.groupby("order_date")["total_amount"].sum().reset_index()
chart_data = chart_data.sort_values("order_date")

chart = alt.Chart(chart_data).mark_line(point=True).encode(
    x=alt.X("order_date:T"),
    y="total_amount"
)
st.altair_chart(chart, use_container_width=True)
