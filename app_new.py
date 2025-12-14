#!/usr/bin/env python3
"""
DashML Streamlit App (New Architecture)
Uses microkernel + backend plugin architecture
"""
import streamlit as st
from dashml.core import DashMLCompiler
from dashml.backends import StreamlitBackend


def main():
    st.set_page_config(
        page_title="DashML Demo",
        page_icon="📊",
        layout="wide"
    )
    
    # Sidebar config
    dashml_path = st.sidebar.text_input("DashML file", "dashml_example.dashml")
    
    try:
        # Step 1: Compile .dashml to IR (Core responsibility)
        compiler = DashMLCompiler()
        ir = compiler.compile(dashml_path)
        
        # Show IR in expander (for debugging)
        with st.sidebar.expander("View IR"):
            st.json(ir.to_dict())
        
        # Step 2: Pass IR to backend (Backend loads data and renders)
        backend = StreamlitBackend()
        backend.execute(ir)
        
    except FileNotFoundError:
        st.error(f"DashML file not found: {dashml_path}")
    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())


if __name__ == "__main__":
    main()

