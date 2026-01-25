# Minimal Streamlit: 1 bar chart, SQL source
import streamlit as st
import pandas as pd
import altair as alt
from sqlalchemy import create_engine

st.title("Simple Dashboard")

engine = create_engine("postgresql://user:pass@localhost:5432/mydb")
df = pd.read_sql("SELECT * FROM public.orders", engine)

st.subheader("Sales by Country")
chart_data = df.groupby("country")["sales"].sum().reset_index()
chart = alt.Chart(chart_data).mark_bar().encode(x="country", y="sales")
st.altair_chart(chart, use_container_width=True)

