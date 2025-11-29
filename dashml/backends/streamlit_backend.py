"""
Streamlit Backend Plugin
Generates Streamlit Python code that executes queries
"""
import pandas as pd
import streamlit as st
from typing import Any
from dashml.core.ir import IR, Dataset, Chart, AggregationType
from .base import Backend


class StreamlitBackend(Backend):
    """
    Streamlit backend implementation
    
    Strategy:
    - Reads IR
    - Generates live query functions
    - Streamlit executes queries on each rerun
    - NO pre-materialized data
    """
    
    def generate(self, ir: IR) -> str:
        """
        Generate Streamlit Python code
        
        Returns:
            Python code string that can be written to file or exec'd
        """
        code_parts = []
        
        # Header
        code_parts.append('"""Auto-generated Streamlit dashboard from DashML"""')
        code_parts.append("import streamlit as st")
        code_parts.append("import pandas as pd")
        code_parts.append("")
        
        # Data loading functions (per dataset)
        for dataset_id, dataset in ir.datasets.items():
            code_parts.append(self._generate_data_loader(dataset_id, dataset))
            code_parts.append("")
        
        # Chart rendering functions
        for chart in ir.charts:
            code_parts.append(self._generate_chart_function(chart, ir))
            code_parts.append("")
        
        # Main app
        code_parts.append(self._generate_main(ir))
        
        return "\n".join(code_parts)
    
    def execute(self, ir: IR, **kwargs) -> None:
        """
        Execute the dashboard in Streamlit
        Backend handles all data loading
        """
        st.title(ir.title)
        
        # Sidebar chart selector
        if ir.charts:
            chart_ids = [c.id for c in ir.charts]
            chart_titles = {c.id: c.title for c in ir.charts}
            
            selected_id = st.sidebar.selectbox(
                "Select Chart",
                chart_ids,
                format_func=lambda x: chart_titles[x]
            )
            
            # Find and render selected chart
            for chart in ir.charts:
                if chart.id == selected_id:
                    st.subheader(chart.title)
                    self._render_chart(chart, ir)
                    break
    
    def _generate_data_loader(self, dataset_id: str, dataset: Dataset) -> str:
        """Generate data loading function for a dataset"""
        if dataset.type == "csv":
            return f'''
@st.cache_data
def load_{dataset_id}():
    """Load {dataset_id} dataset"""
    return pd.read_csv("{dataset.source}")
'''
        elif dataset.type == "sql":
            return f'''
@st.cache_data
def load_{dataset_id}():
    """Load {dataset_id} dataset from SQL"""
    import sqlalchemy
    engine = sqlalchemy.create_engine("{dataset.source}")
    query = """{dataset.query}"""
    return pd.read_sql(query, engine)
'''
        else:
            return f'''
def load_{dataset_id}():
    """Load {dataset_id} dataset"""
    raise NotImplementedError("Dataset type {dataset.type} not yet supported")
'''
    
    def _generate_chart_function(self, chart: Chart, ir: IR) -> str:
        """Generate chart rendering function"""
        dataset = ir.get_dataset(chart.dataset_id)
        
        func = f'''
def render_{chart.id}():
    """Render {chart.title}"""
    df = load_{chart.dataset_id}()
    
    # Apply filters
'''
        
        # Add filter logic
        for filter_obj in chart.filters:
            func += f'    df = df[df["{filter_obj.column}"] {filter_obj.operator} {repr(filter_obj.value)}]\n'
        
        # Add aggregation
        func += f'''
    # Aggregate
    grouped = df.groupby("{chart.x_dimension.column}")["{chart.y_measure.column}"].{chart.y_measure.aggregation.value}().reset_index()
    data = grouped.set_index("{chart.x_dimension.column}")["{chart.y_measure.column}"]
    
    # Render chart
'''
        
        if chart.type.value == "bar":
            func += "    st.bar_chart(data)\n"
        elif chart.type.value == "line":
            func += "    st.line_chart(data)\n"
        elif chart.type.value == "area":
            func += "    st.area_chart(data)\n"
        else:
            func += f'    st.warning("Chart type {chart.type.value} not yet supported")\n'
        
        return func
    
    def _generate_main(self, ir: IR) -> str:
        """Generate main app logic"""
        main = f'''
def main():
    st.title("{ir.title}")
    
    # Chart selector
    chart_options = {{
'''
        for chart in ir.charts:
            main += f'        "{chart.id}": "{chart.title}",\n'
        
        main += '''    }
    
    selected = st.sidebar.selectbox("Select Chart", list(chart_options.keys()), format_func=lambda x: chart_options[x])
    
    st.subheader(chart_options[selected])
    
    # Render selected chart
'''
        
        for i, chart in enumerate(ir.charts):
            if i == 0:
                main += f'    if selected == "{chart.id}":\n'
            else:
                main += f'    elif selected == "{chart.id}":\n'
            main += f'        render_{chart.id}()\n'
        
        main += '''

if __name__ == "__main__":
    main()
'''
        
        return main
    
    def _render_chart(self, chart: Chart, ir: IR):
        """Runtime chart rendering - loads and visualizes data"""
        dataset = ir.get_dataset(chart.dataset_id)
        
        # Load data (Backend responsibility!)
        df = self._load_data(dataset)
        
        # Apply filters
        for filter_obj in chart.filters:
            if filter_obj.operator == "eq":
                df = df[df[filter_obj.column] == filter_obj.value]
            elif filter_obj.operator == "gt":
                df = df[df[filter_obj.column] > filter_obj.value]
            # Add more operators as needed
        
        # Aggregate
        agg_func = chart.y_measure.aggregation.value
        grouped = df.groupby(chart.x_dimension.column)[chart.y_measure.column].agg(agg_func).reset_index()
        chart_data = grouped.set_index(chart.x_dimension.column)[chart.y_measure.column]
        
        # Render
        if chart.type.value == "bar":
            st.bar_chart(chart_data)
        elif chart.type.value == "line":
            st.line_chart(chart_data)
        elif chart.type.value == "area":
            st.area_chart(chart_data)
        else:
            st.warning(f"Chart type {chart.type.value} not yet supported")
    
    def _load_data(self, dataset: Dataset) -> pd.DataFrame:
        """Load data from dataset definition - Backend responsibility!"""
        if dataset.type == "csv":
            return pd.read_csv(dataset.source)
        elif dataset.type == "sql":
            import sqlalchemy
            engine = sqlalchemy.create_engine(dataset.source)
            return pd.read_sql(dataset.query, engine)
        else:
            raise NotImplementedError(f"Dataset type {dataset.type} not supported")

