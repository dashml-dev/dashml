# TypedDict - Zero-Overhead Type Hints

DashML uses **TypedDict** for type hints without runtime overhead. This design decision aligns with DashML's philosophy of being a build-time compiler rather than a runtime framework.

## Current Implementation

```python
# core/types.py
from typing import TypedDict, List, Union

class StyleColors(TypedDict, total=False):
    background: str
    card: str
    primary: str
    text: str
    buttons: str
    secondary: List[str]

class DataSpec(TypedDict):
    type: str  # Currently: "csv"
    path: str

class ChartSpec(TypedDict, total=False):
    id: str           # Required: Unique identifier
    type: str         # Required: bar|line|scatter|pie|area|histogram|stacked_bar|grouped_bar
    title: str        # Optional: Display title
    x: str            # Required: X-axis column
    y: str            # Required: Y-axis column (except histogram)
    agg: str          # Optional: sum|mean|count
    group: str        # Optional: Grouping column (required for stacked/grouped bars)

class PageSpec(TypedDict, total=False):
    id: str
    title: str
    description: str
    charts: List[ChartSpec]

class DashMLSpec(TypedDict, total=False):
    version: Union[str, int, float]
    title: str
    style: str
    data: DataSpec
    charts: List[ChartSpec]   # Legacy single-page format
    pages: List[PageSpec]     # Multi-page format
```

## Benefits

### 1. IDE Autocomplete ✅

```python
def build(self, spec: DashMLSpec) -> str:
    spec["charts"]           # IDE autocompletes available keys
    spec["data"]["path"]     # Type-checked nested access
    spec["title"]            # IDE knows this field exists

    for chart in spec["charts"]:
        chart["type"]        # Autocomplete works in loops
        chart["x"]           # Type hints propagate
```

### 2. Static Type Checking ✅

```bash
$ mypy dashml_new/
# Catches typos at development time:
spec["titel"]                # ❌ Error: Key "titel" not found
spec["charts"][0]["typ"]     # ❌ Error: Key "typ" not found
chart["group"]               # ✅ OK: Optional field
```

### 3. Zero Runtime Cost ✅

```python
# TypedDict is purely a type hint - at runtime it's just a dict
spec = {"version": "1.0", "title": "Dashboard", "charts": [...]}
type(spec)  # <class 'dict'>

# No object instantiation, no conversion, no overhead
# The parsed YAML dict flows directly through the system
```

### 4. No Conversion Layer ✅

```python
# WITHOUT TypedDict (if we used dataclasses):
YAML → parse → dict → validate → convert to dataclass →
       convert back to dict → transformer

# WITH TypedDict (current approach):
YAML → parse → dict → validate → transformer
                ↑ Just annotate the type, zero overhead!
```

## Architecture Philosophy

```
┌─────────────┐
│  .dashml    │
│  YAML file  │
└──────┬──────┘
       │ Parse (yaml.safe_load)
       ▼
┌─────────────┐
│ Python dict │ ◄─── TypedDict annotates this as DashMLSpec
└──────┬──────┘      (no runtime conversion!)
       │ Validate
       ▼
┌─────────────┐
│  Valid dict │ ◄─── Still just a dict!
└──────┬──────┘
       │ Transform
       ▼
┌─────────────┐
│  Generated  │
│    Code     │
└─────────────┘
```

**Key insight:** TypedDict provides compile-time safety without runtime cost.

## Why Not Use `Literal` for Chart Types?

We intentionally use `str` instead of `Literal["bar", "line", ...]`:

```python
# ❌ BAD - Prescriptive (tight coupling)
from typing import Literal
ChartType = Literal["bar", "line", "scatter", "pie"]
type: ChartType

# Problem: Adding "histogram" requires changing types.py!

# ✅ GOOD - Descriptive (loose coupling)
type: str

# Validation happens in validator.py, not type system
# Transformers decide what they support independently
```

**Philosophy:**
- **Types document structure**, not valid values
- **Validator enforces semantics**, not the type system
- **Transformers are plugins**, they handle their own supported types

## Evolution Without Breaking Changes

TypedDict's `total=False` allows schema evolution:

```python
# Week 1: Initial implementation
class ChartSpec(TypedDict, total=False):
    id: str
    type: str
    x: str
    y: str

# Week 4: Add aggregation (backward compatible!)
class ChartSpec(TypedDict, total=False):
    id: str
    type: str
    x: str
    y: str
    agg: str  # New optional field - old code still works!

# Week 8: Add grouping (backward compatible!)
class ChartSpec(TypedDict, total=False):
    id: str
    type: str
    x: str
    y: str
    agg: str
    group: str  # Another optional field - still backward compatible!
```

Old `.dashml` files continue to work without changes!

## Practical Usage

### In Transformers

```python
from typing import Dict, Any
from core.types import DashMLSpec, ChartSpec

class StreamlitTransformer(Transformer):
    def build(self, spec: DashMLSpec) -> str:
        # IDE autocompletes and type-checks all of this
        title = spec.get("title", "Dashboard")
        charts = spec.get("charts", [])

        for chart in charts:
            chart_type = chart["type"]      # str
            x = chart["x"]                  # str
            y = chart["y"]                  # str
            group = chart.get("group")      # str | None

            # Type checker knows what fields exist
            self._generate_chart(chart)
```

### In Validators

```python
from core.types import DashMLSpec, ChartSpec

def validate(self, spec: DashMLSpec) -> None:
    # TypedDict helps catch bugs during development
    for chart in spec.get("charts", []):
        if chart["type"] in ["stacked_bar", "grouped_bar"]:
            if "group" not in chart:
                raise ValidationError(f"Chart '{chart['id']}' requires 'group' field")
```

## When to Consider Full Dataclasses

You might want full dataclass IR if:

- ❌ You need methods on spec objects (e.g., `spec.get_chart_by_id()`)
- ❌ You need deep spec transformations (e.g., macro expansion)
- ❌ You need strict runtime validation beyond semantic checks
- ❌ Team > 10 developers with many accidental dict access bugs

For DashML's current scope: **TypedDict is perfect!**

## Comparison: TypedDict vs Dataclass IR

| Feature | TypedDict | Dataclass |
|---------|-----------|-----------|
| Runtime overhead | ✅ Zero | ❌ Object creation |
| Conversion required | ✅ No | ❌ Yes (dict ↔ class) |
| IDE autocomplete | ✅ Yes | ✅ Yes |
| Type checking | ✅ Yes | ✅ Yes |
| Schema evolution | ✅ Easy | ⚠️ More complex |
| Methods on objects | ❌ No | ✅ Yes |
| Runtime validation | ⚠️ Manual | ✅ Built-in |
| Memory footprint | ✅ Minimal | ❌ Higher |

## Summary

**TypedDict provides:**
- ✅ Compile-time type safety
- ✅ IDE autocomplete and IntelliSense
- ✅ Zero runtime overhead
- ✅ No conversion layer
- ✅ Easy schema evolution
- ✅ Perfect for build-time compilation

**Aligns with DashML philosophy:**
- DashML is a **compiler**, not a runtime
- Specs are **blueprints**, not data structures
- Type hints are **documentation**, not validation
- Transformers are **plugins**, not core

**TypedDict is the right choice for DashML!** 🚀
