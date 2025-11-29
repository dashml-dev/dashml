import streamlit as st
from dashml import DashMLTransformer, StreamlitRenderer


st.set_page_config(page_title="My Existing App with DashML", layout="wide")

st.title("🚀 My Existing Streamlit App")

st.markdown("""
This demonstrates how to integrate DashML into an existing Streamlit application.
""")

tab1, tab2, tab3 = st.tabs(["My App Content", "DashML Dashboard", "Specific Chart"])

with tab1:
    st.header("Original App Content")
    st.write("This is your existing app functionality...")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Revenue", "$1.2M", "+12%")
    with col2:
        st.metric("Users", "8,234", "+5%")
    
    st.info("Your existing app continues to work normally!")

with tab2:
    st.header("Embedded DashML Dashboard")
    
    try:
        transformer = DashMLTransformer("dashml_example.yaml")
        renderer = StreamlitRenderer(transformer)
        renderer.render_dashboard(show_title=False, show_sidebar=False)
    except Exception as e:
        st.error(f"Error loading DashML: {e}")

with tab3:
    st.header("Single DashML Chart Integration")
    st.write("You can embed specific charts from DashML into your app:")
    
    try:
        transformer = DashMLTransformer("dashml_example.yaml")
        transformer.load_data()
        renderer = StreamlitRenderer(transformer)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Sales by Country")
            renderer.render_chart_by_id("sales_by_country")
        
        with col2:
            st.subheader("Sales over Time")
            renderer.render_chart_by_id("sales_over_time")
            
    except Exception as e:
        st.error(f"Error: {e}")

st.divider()
st.caption("Powered by DashML v0.000000001")

