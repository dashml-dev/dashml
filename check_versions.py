import streamlit as st
import altair as alt
print(f"Streamlit: {st.__version__}")
print(f"Altair: {alt.__version__}")
try:
    import vl_convert
    print(f"vl-convert: {vl_convert.__version__}")
except:
    pass
