import streamlit as st
import pandas as pd
from typing import Dict, Any, Optional
from .transformer import DashMLTransformer


class StreamlitRenderer:
    """
    Streamlit-specific renderer for DashML.
    Can be plugged into any Streamlit app.
    """
    
    def __init__(self, transformer: DashMLTransformer):
        self.transformer = transformer
    
    def render_chart(self, chart: Dict[str, Any]) -> None:
        ctype = chart.get("type")
        x = chart.get("x")
        y = chart.get("y")
        agg = chart.get("agg", "sum")
        
        grouped = self.transformer.aggregate_data(x, y, agg)
        chart_data = grouped.set_index(x)[y]
        
        if ctype == "bar":
            st.bar_chart(chart_data)
        elif ctype == "line":
            st.line_chart(chart_data)
        else:
            st.warning(f"Unsupported chart type: {ctype}")
    
    def render_dashboard(
        self,
        show_title: bool = True,
        show_sidebar: bool = True,
        selected_chart_id: Optional[str] = None
    ) -> None:
        """
        Render complete dashboard.
        
        Args:
            show_title: Show dashboard title
            show_sidebar: Show chart selector in sidebar
            selected_chart_id: Pre-selected chart ID (if None, uses sidebar selector)
        """
        if show_title:
            st.title(self.transformer.get_title())
        
        try:
            self.transformer.load_data()
        except Exception as e:
            st.error(f"Error loading data: {e}")
            return
        
        charts = self.transformer.get_charts()
        if not charts:
            st.warning("No charts defined in DashML spec.")
            return
        
        if selected_chart_id is None and show_sidebar:
            chart_ids = [c["id"] for c in charts]
            selected_chart_id = st.sidebar.selectbox("Select Chart", chart_ids)
        
        if selected_chart_id:
            chart = self.transformer.get_chart_by_id(selected_chart_id)
            if chart:
                st.subheader(chart.get("title", chart["id"]))
                self.render_chart(chart)
        else:
            for chart in charts:
                st.subheader(chart.get("title", chart["id"]))
                self.render_chart(chart)
                st.divider()
    
    def render_chart_by_id(self, chart_id: str) -> None:
        """
        Render a single chart by ID.
        Useful for embedding specific charts in existing apps.
        """
        chart = self.transformer.get_chart_by_id(chart_id)
        if chart:
            self.render_chart(chart)
        else:
            st.error(f"Chart not found: {chart_id}")

