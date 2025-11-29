import yaml
import pandas as pd
import streamlit as st
from pathlib import Path


def load_dashml(path: str) -> dict:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_data(data_spec: dict) -> pd.DataFrame:
    if data_spec["type"] == "csv":
        return pd.read_csv(data_spec["path"])
    raise ValueError(f"Unsupported data type: {data_spec['type']}")


def aggregate(df: pd.DataFrame, x: str, y: str, agg: str) -> pd.DataFrame:
    if agg not in {"sum", "mean", "count"}:
        agg = "sum"
    if agg == "count":
        grouped = df.groupby(x)[y].count().reset_index(name=y)
    else:
        grouped = getattr(df.groupby(x)[y], agg)().reset_index()
    return grouped


def render_chart(chart: dict, df: pd.DataFrame) -> None:
    ctype = chart["type"]
    x = chart["x"]
    y = chart["y"]
    agg = chart.get("agg", "sum")
    grouped = aggregate(df, x, y, agg).set_index(x)[y]
    if ctype == "bar":
        st.bar_chart(grouped)
    elif ctype == "line":
        st.line_chart(grouped)
    else:
        st.write(f"Unsupported chart type: {ctype}")


def main() -> None:
    dashml_path = st.sidebar.text_input("DashML file", "dashml_example.yaml")
    try:
        spec = load_dashml(dashml_path)
    except FileNotFoundError:
        st.error(f"DashML file not found: {dashml_path}")
        return

    st.title(spec.get("title", "DashML Dashboard v0.000000001"))

    try:
        df = load_data(spec["data"])
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    charts = spec.get("charts", [])
    if not charts:
        st.warning("No charts defined in DashML spec.")
        return

    chart_ids = [c["id"] for c in charts]
    selected_id = st.sidebar.selectbox("Chart", chart_ids)

    for chart in charts:
        if chart["id"] == selected_id:
            st.subheader(chart.get("title", chart["id"]))
            render_chart(chart, df)
            break


if __name__ == "__main__":
    main()

