Legacy Files (Old Architecture)
================================

These files represent the OLD architecture where the transformer
loaded data directly. They are kept for reference only.

Use the NEW architecture in the parent directory:
- Core (dashml/core/) - Compiler that never touches data
- Backends (dashml/backends/) - Plugins that handle data
- app_new.py - Streamlit app using new architecture
- dashml_cli.py - CLI tool

The new architecture follows proper compiler design principles
and is the version to use for the thesis.

