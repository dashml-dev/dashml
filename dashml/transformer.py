import yaml
import pandas as pd
from pathlib import Path
from typing import Dict, Any


class DashMLTransformer:
    """
    Core DashML transformer - platform agnostic.
    Loads and parses DashML specs (.dashml files) and data.
    Note: .dashml files use YAML syntax.
    """
    
    def __init__(self, dashml_path: str):
        self.dashml_path = dashml_path
        self.spec = self._load_spec()
        self.df = None
    
    def _load_spec(self) -> Dict[str, Any]:
        p = Path(self.dashml_path)
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def load_data(self) -> pd.DataFrame:
        data_spec = self.spec.get("data", {})
        data_type = data_spec.get("type")
        
        if data_type == "csv":
            self.df = pd.read_csv(data_spec["path"])
        else:
            raise ValueError(f"Unsupported data type: {data_type}")
        
        return self.df
    
    def get_title(self) -> str:
        return self.spec.get("title", "DashML Dashboard")
    
    def get_charts(self) -> list:
        return self.spec.get("charts", [])
    
    def get_chart_by_id(self, chart_id: str) -> Dict[str, Any]:
        for chart in self.get_charts():
            if chart.get("id") == chart_id:
                return chart
        return None
    
    def aggregate_data(self, x: str, y: str, agg: str = "sum") -> pd.DataFrame:
        if self.df is None:
            raise ValueError("Data not loaded. Call load_data() first.")
        
        if agg not in {"sum", "mean", "count"}:
            agg = "sum"
        
        if agg == "count":
            grouped = self.df.groupby(x)[y].count().reset_index(name=y)
        else:
            grouped = getattr(self.df.groupby(x)[y], agg)().reset_index()
        
        return grouped

