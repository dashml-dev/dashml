# TypedDict IR - The Best of Both Worlds

DashML now uses **TypedDict** for type hints without runtime overhead.

## What We Have

```python
# core/types.py
class DashMLSpec(TypedDict):
    version: Union[str, int, float]
    title: str
    data: DataSpec
    charts: List[ChartSpec]

class ChartSpec(TypedDict, total=False):
    id: str
    type: str
    x: str
    y: str
    agg: str
    title: str
```

## Benefits

### 1. IDE Autocomplete ✅

```python
def build(self, spec: DashMLSpec) -> str:
    spec["charts"]  # ← IDE autocompletes!
    spec["data"]["path"]  # ← Type-checked!
    spec["title"]  # ← Knows this exists!
```

### 2. Type Checking (mypy/pyright) ✅

```bash
$ mypy dashml_new/
# Catches typos:
spec["titel"]  # ❌ Error: Key "titel" not found
spec["charts"][0]["typ"]  # ❌ Error: Key "typ" not found
```

### 3. Zero Runtime Cost ✅

```python
# At runtime, it's just a dict!
spec = {"version": "1.0", "title": "Dashboard", ...}
type(spec)  # <class 'dict'>

# No conversion, no overhead
# TypedDict is purely for type checkers
```

### 4. Easy Schema Evolution ✅

```python
# Week 1: Simple
class ChartSpec(TypedDict):
    id: str
    type: str

# Week 2: Add fields (no breaking changes!)
class ChartSpec(TypedDict, total=False):  # total=False makes all optional
    id: str
    type: str
    color: str  # New field!

# Week 3: Refine
class ChartSpec(TypedDict):
    id: str  # Required
    type: str  # Required
    color: NotRequired[str]  # Optional (Python 3.11+)
```

### 5. No Dataclass Conversion ✅

```python
# WITHOUT TypedDict (dataclass IR):
yaml_dict → validate → convert to dataclass → convert back to dict → transformer

# WITH TypedDict:
yaml_dict → validate → transformer
#           ↑ Just cast the type hint, no conversion!
```

## Why Not `Literal` for Enums?

We intentionally use `str` instead of `Literal["bar", "line", ...]` for values:

```python
# ❌ BAD - Prescriptive (limits extensibility)
ChartType = Literal["bar", "line", "scatter", "pie"]
type: ChartType  # Can't add "histogram" without changing types!

# ✅ GOOD - Descriptive (validator handles it)
type: str  # Any string, validator checks if reasonable
```

**Why?**
- DashML is **non-validating** - validation happens in the validator, not types
- DashML is **extensible** - new chart types shouldn't require core changes
- **Transformers** decide what they support, not the type system

## Architecture

```
YAML v1 ──┐
YAML v2 ──┤──→ Parser ──→ DashMLSpec (TypedDict) ──→ Transformers
YAML v3 ──┘     Normalizes    ↑ Just a type hint!
                             (still a dict at runtime)
```

**Key insight:** TypedDict is "IR as documentation" not "IR as data structure"

## When to Upgrade to Dataclass IR

Consider full dataclass IR when:
- ❌ Team > 5 developers
- ❌ Frequent bugs from dict typos
- ❌ Need methods on spec objects (e.g., `spec.get_chart_by_id()`)
- ❌ Complex transformations on the spec itself

For DashML MVP/thesis: **TypedDict is perfect!**

## Usage Example

```python
# Engine returns typed spec
from core import DashMLEngine
from core.types import DashMLSpec

engine = DashMLEngine()
spec: DashMLSpec = engine.load("dashboard.dashml")

# IDE knows the structure!
for chart in spec["charts"]:  # ← Autocompletes
    print(chart["id"])  # ← Type-checked
    print(chart["type"])  # ← IDE suggests valid keys
```

## Migration to Dataclass IR (Future)

If you later decide you need full dataclass IR:

```python
# Add conversion layer
@dataclass
class DashMLSpecIR:
    version: str
    title: str
    data: DataSpec
    charts: List[Chart]

    @classmethod
    def from_dict(cls, d: DashMLSpec) -> "DashMLSpecIR":
        return cls(
            version=str(d["version"]),
            title=d["title"],
            data=DataSpec(**d["data"]),
            charts=[Chart(**c) for c in d["charts"]]
        )

# Engine
def load(self, path: str) -> DashMLSpecIR:
    dict_spec = self.parser.parse(path)
    return DashMLSpecIR.from_dict(dict_spec)
```

But you probably won't need it! 🎉

## Summary

**TypedDict gives you:**
- ✅ Type safety (compile-time errors)
- ✅ IDE autocomplete
- ✅ Zero runtime cost
- ✅ Easy to evolve
- ✅ No conversion overhead

**Without:**
- ❌ Runtime object creation
- ❌ Dict ↔ Dataclass conversion
- ❌ Memory overhead
- ❌ Breaking changes when schema evolves

**Perfect for DashML!** 🚀
