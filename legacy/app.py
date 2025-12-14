import streamlit as st
from dashml import DashMLTransformer, StreamlitRenderer


def main() -> None:
    st.set_page_config(
        page_title="DashML Demo",
        page_icon="📊",
        layout="wide"
    )
    
    dashml_path = st.sidebar.text_input("DashML file", "dashml_example.dashml")
    
    try:
        transformer = DashMLTransformer(dashml_path)
        renderer = StreamlitRenderer(transformer)
        renderer.render_dashboard(show_title=True, show_sidebar=True)
    except FileNotFoundError:
        st.error(f"DashML file not found: {dashml_path}")
    except Exception as e:
        st.error(f"Error: {e}")


if __name__ == "__main__":
    main()
