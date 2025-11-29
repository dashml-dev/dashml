"""
DashML Intermediate Representation (IR)
Pure semantic model - NO DATA, only query logic
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class AggregationType(Enum):
    SUM = "sum"
    MEAN = "mean"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"


class ChartType(Enum):
    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"
    PIE = "pie"
    AREA = "area"
    HISTOGRAM = "histogram"


@dataclass
class Dataset:
    """Logical dataset definition - describes WHERE data comes from, not the data itself"""
    id: str
    type: str  # csv, sql, api, json
    source: str  # path, connection string, URL
    query: Optional[str] = None  # SQL query if type=sql
    schema: Optional[Dict[str, str]] = None  # column name -> type mapping
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "query": self.query,
            "schema": self.schema
        }


@dataclass
class Dimension:
    """Dimension - a grouping/categorical field"""
    name: str
    column: str
    type: str = "string"  # string, date, datetime, number
    format: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "column": self.column,
            "type": self.type,
            "format": self.format
        }


@dataclass
class Measure:
    """Measure - an aggregated numeric field"""
    name: str
    column: str
    aggregation: AggregationType
    format: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "column": self.column,
            "aggregation": self.aggregation.value,
            "format": self.format
        }


@dataclass
class Filter:
    """Logical filter - describes filtering logic, not filtered data"""
    column: str
    operator: str  # eq, ne, gt, lt, in, between, contains
    value: Any
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "column": self.column,
            "operator": self.operator,
            "value": self.value
        }


@dataclass
class Chart:
    """
    Logical chart specification
    Describes WHAT to visualize and HOW to aggregate
    NEVER contains actual data
    """
    id: str
    type: ChartType
    title: str
    dataset_id: str
    x_dimension: Dimension
    y_measure: Measure
    filters: List[Filter] = field(default_factory=list)
    color: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "dataset_id": self.dataset_id,
            "x_dimension": self.x_dimension.to_dict(),
            "y_measure": self.y_measure.to_dict(),
            "filters": [f.to_dict() for f in self.filters],
            "color": self.color
        }


@dataclass
class IR:
    """
    DashML Intermediate Representation
    
    This is the CORE semantic model.
    It contains:
    - Dataset definitions (WHERE to get data, not the data)
    - Chart specifications (WHAT to visualize, HOW to aggregate)
    - Filter logic (WHAT to filter, not filtered results)
    
    It NEVER contains:
    - Actual data rows
    - DataFrames
    - Query results
    - Materialized datasets
    
    Backends read this IR and execute the queries themselves.
    """
    version: str
    title: str
    datasets: Dict[str, Dataset]
    charts: List[Chart]
    global_filters: List[Filter] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize IR to dict for backend consumption"""
        return {
            "version": self.version,
            "title": self.title,
            "datasets": {k: v.to_dict() for k, v in self.datasets.items()},
            "charts": [c.to_dict() for c in self.charts],
            "global_filters": [f.to_dict() for f in self.global_filters],
            "metadata": self.metadata
        }
    
    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        """Get dataset definition by ID"""
        return self.datasets.get(dataset_id)
    
    def get_chart(self, chart_id: str) -> Optional[Chart]:
        """Get chart specification by ID"""
        for chart in self.charts:
            if chart.id == chart_id:
                return chart
        return None

