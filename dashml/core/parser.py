"""
DashML Parser
YAML → AST → IR
Pure semantic parsing - NEVER loads data
"""
import yaml
from pathlib import Path
from typing import Dict, Any
from .ir import (
    IR, Dataset, Chart, Filter, Dimension, Measure,
    AggregationType, ChartType
)


class DashMLParser:
    """
    Parses DashML YAML files into IR
    
    Responsibilities:
    - Load and parse YAML
    - Validate structure
    - Build semantic IR
    
    NOT responsible for:
    - Loading data
    - Executing queries
    - Materializing results
    """
    
    def __init__(self):
        self.errors = []
    
    def parse_file(self, path: str) -> IR:
        """Parse a .dashml file into IR"""
        dashml_path = Path(path)
        
        if not dashml_path.exists():
            raise FileNotFoundError(f"DashML file not found: {path}")
        
        with dashml_path.open("r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        
        return self.parse_spec(spec)
    
    def parse_spec(self, spec: Dict[str, Any]) -> IR:
        """Parse a DashML spec dict into IR"""
        self.errors = []
        
        # Validate required fields
        self._validate_spec(spec)
        
        # Parse datasets
        datasets = self._parse_datasets(spec.get("data"))
        
        # Parse charts
        charts = self._parse_charts(spec.get("charts", []), datasets)
        
        # Parse global filters
        global_filters = self._parse_filters(spec.get("filters", []))
        
        # Build IR
        ir = IR(
            version=spec.get("version", "0.0.1"),
            title=spec.get("title", "Untitled Dashboard"),
            datasets=datasets,
            charts=charts,
            global_filters=global_filters,
            metadata=spec.get("metadata", {})
        )
        
        return ir
    
    def _validate_spec(self, spec: Dict[str, Any]):
        """Validate spec structure"""
        required = ["data", "charts"]
        for field in required:
            if field not in spec:
                raise ValueError(f"Missing required field: {field}")
    
    def _parse_datasets(self, data_spec: Any) -> Dict[str, Dataset]:
        """Parse dataset definitions"""
        datasets = {}
        
        if isinstance(data_spec, dict):
            # Single dataset (backwards compatible)
            dataset = Dataset(
                id="default",
                type=data_spec.get("type", "csv"),
                source=data_spec.get("path", data_spec.get("source", "")),
                query=data_spec.get("query"),
                schema=data_spec.get("schema")
            )
            datasets["default"] = dataset
        elif isinstance(data_spec, list):
            # Multiple datasets
            for ds in data_spec:
                dataset = Dataset(
                    id=ds.get("id", "default"),
                    type=ds.get("type", "csv"),
                    source=ds.get("path", ds.get("source", "")),
                    query=ds.get("query"),
                    schema=ds.get("schema")
                )
                datasets[dataset.id] = dataset
        
        return datasets
    
    def _parse_charts(self, charts_spec: list, datasets: Dict[str, Dataset]) -> list:
        """Parse chart specifications"""
        charts = []
        
        for chart_spec in charts_spec:
            # Determine dataset
            dataset_id = chart_spec.get("dataset", "default")
            if dataset_id not in datasets:
                raise ValueError(f"Unknown dataset: {dataset_id}")
            
            # Parse dimension (x-axis)
            x_column = chart_spec.get("x")
            x_dim = Dimension(
                name=x_column,
                column=x_column,
                type=chart_spec.get("x_type", "string")
            )
            
            # Parse measure (y-axis with aggregation)
            y_column = chart_spec.get("y")
            agg_type = chart_spec.get("agg", "sum")
            
            try:
                agg = AggregationType(agg_type)
            except ValueError:
                agg = AggregationType.SUM
            
            y_measure = Measure(
                name=y_column,
                column=y_column,
                aggregation=agg
            )
            
            # Parse chart type
            try:
                chart_type = ChartType(chart_spec.get("type", "bar"))
            except ValueError:
                chart_type = ChartType.BAR
            
            # Parse filters
            filters = self._parse_filters(chart_spec.get("filters", []))
            
            # Build chart IR
            chart = Chart(
                id=chart_spec.get("id", f"chart_{len(charts)}"),
                type=chart_type,
                title=chart_spec.get("title", "Untitled Chart"),
                dataset_id=dataset_id,
                x_dimension=x_dim,
                y_measure=y_measure,
                filters=filters,
                color=chart_spec.get("color")
            )
            
            charts.append(chart)
        
        return charts
    
    def _parse_filters(self, filters_spec: list) -> list:
        """Parse filter specifications"""
        filters = []
        
        for filter_spec in filters_spec:
            filter_obj = Filter(
                column=filter_spec.get("column", ""),
                operator=filter_spec.get("operator", "eq"),
                value=filter_spec.get("value")
            )
            filters.append(filter_obj)
        
        return filters

