# The .dashml File Format

## 📄 Overview

`.dashml` is the official file format for DashML specifications. While it uses YAML syntax under the hood, it is a distinct format with its own semantics and purpose.

---

## 🎯 Why .dashml instead of .yaml?

### 1. **Semantic Clarity**
- `.dashml` files are not just any YAML - they are dashboard specifications
- The extension immediately communicates intent
- Enables proper tooling integration (syntax highlighting, validators, etc.)

### 2. **Language Identity**
- Establishes DashML as a proper Domain-Specific Language (DSL)
- Similar to how `.tf` (Terraform) uses HCL syntax but has its own extension
- Reinforces DashML as a standard, not just a convention

### 3. **Tooling & Editor Support**
- IDEs can provide specific support for `.dashml` files
- Version control systems can handle them specifically
- Future: DashML-specific linters, formatters, and validators

### 4. **Professional Presentation**
- More professional for thesis and production use
- "We created a new language" vs "We wrote some YAML"
- Easier to market and explain

---

## 📝 File Structure

### Basic Syntax

DashML files use YAML syntax with specific semantic blocks:

```yaml
version: 0.000000001
title: "Dashboard Title"

data:
  type: csv
  path: "data/example.csv"

charts:
  - id: "chart_1"
    type: "bar"
    title: "Chart Title"
    x: "column_x"
    y: "column_y"
    agg: "sum"
```

### Top-Level Blocks

| Block | Required | Description |
|-------|----------|-------------|
| `version` | ✅ Yes | DashML spec version |
| `title` | ❌ No | Dashboard title |
| `data` | ✅ Yes | Data source specification |
| `charts` | ✅ Yes | Array of chart definitions |

---

## 🔧 Technical Details

### MIME Type (Future)
- Proposed: `application/x-dashml`
- Alternative: `text/x-dashml`

### File Extension
- Primary: `.dashml`
- Legacy: `.yaml` (deprecated, but still works)

### Character Encoding
- UTF-8 required
- Line endings: LF (Unix) or CRLF (Windows) both supported

### YAML Version
- Uses YAML 1.2 specification
- Parsed by standard YAML libraries

---

## 🎨 Syntax Highlighting

### VS Code / Cursor

Create `.vscode/extensions.json`:

```json
{
  "recommendations": ["redhat.vscode-yaml"]
}
```

Add to `settings.json`:

```json
{
  "files.associations": {
    "*.dashml": "yaml"
  },
  "yaml.schemas": {
    "./dashml-schema.json": "*.dashml"
  }
}
```

### GitHub

GitHub automatically treats `.dashml` as text and can use YAML syntax highlighting.

Add `.gitattributes`:

```
*.dashml linguist-language=YAML
```

---

## ✅ Validation

### Schema (Future)

JSON Schema for `.dashml` files:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["version", "data", "charts"],
  "properties": {
    "version": { "type": "string" },
    "title": { "type": "string" },
    "data": {
      "type": "object",
      "required": ["type", "path"],
      "properties": {
        "type": { "enum": ["csv", "json", "sql"] },
        "path": { "type": "string" }
      }
    },
    "charts": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "type", "x", "y"],
        "properties": {
          "id": { "type": "string" },
          "type": { "enum": ["bar", "line", "scatter", "pie"] },
          "title": { "type": "string" },
          "x": { "type": "string" },
          "y": { "type": "string" },
          "agg": { "enum": ["sum", "mean", "count"] }
        }
      }
    }
  }
}
```

---

## 📚 Best Practices

### 1. Naming Convention

```
✅ Good:
- sales_dashboard.dashml
- customer_analytics.dashml
- product_metrics.dashml

❌ Avoid:
- dashboard.yaml (use .dashml)
- DashML-file.txt (wrong extension)
- myDashBoard.dashml (inconsistent casing)
```

### 2. File Organization

```
project/
├── dashboards/
│   ├── sales.dashml
│   ├── marketing.dashml
│   └── operations.dashml
├── data/
│   ├── sales.csv
│   └── customers.csv
└── app.py
```

### 3. Version Control

Always commit `.dashml` files:

```bash
git add dashboards/*.dashml
git commit -m "Add sales dashboard specification"
```

### 4. Documentation

Include a comment header:

```yaml
# DashML Specification
# Dashboard: Sales Analytics
# Author: Dawid Olejniczak
# Last Updated: 2025-11-29
# Description: Weekly sales metrics by region and product

version: 0.000000001
title: "Sales Analytics Dashboard"
# ... rest of spec
```

---

## 🚀 Migration from .yaml

If you have existing `.yaml` files:

```bash
# Rename all YAML files to .dashml
for file in *.yaml; do
  mv "$file" "${file%.yaml}.dashml"
done
```

Or use Python:

```python
import os
for file in os.listdir('.'):
    if file.endswith('.yaml'):
        os.rename(file, file.replace('.yaml', '.dashml'))
```

---

## 🎓 For Your Thesis

### Academic Arguments for .dashml Format

1. **Separation of Concerns**
   - Distinct file format for distinct purpose
   - Not just configuration, but a language

2. **Domain-Specific Language**
   - Formal DSL with defined syntax and semantics
   - Own file extension reinforces this

3. **Tooling Ecosystem**
   - Foundation for future tools (linters, validators, generators)
   - Enables IDE plugins specific to DashML

4. **Industry Precedent**
   - Similar to: `.tf` (Terraform), `.prisma` (Prisma), `.proto` (Protocol Buffers)
   - All use familiar syntaxes but own extensions

5. **Language Evolution**
   - Extension allows future syntax changes
   - Can move beyond YAML if needed
   - Maintains backward compatibility

---

## 🔮 Future Extensions

### Possible Future Features

1. **Variables**
```yaml
variables:
  primary_color: "#667eea"
  date_range: "2025-01-01:2025-12-31"

charts:
  - color: $primary_color
    filter: "date BETWEEN $date_range"
```

2. **Imports**
```yaml
import:
  - common_filters.dashml
  - color_scheme.dashml
```

3. **Templates**
```yaml
templates:
  sales_chart:
    type: bar
    agg: sum
    
charts:
  - template: sales_chart
    id: sales_by_region
    x: region
    y: amount
```

---

## ✨ Summary

**`.dashml` is:**
- ✅ A proper file format for a proper language
- ✅ YAML-based for simplicity and familiarity
- ✅ Semantically distinct from generic YAML
- ✅ Professional and thesis-appropriate
- ✅ Foundation for future tooling

**It signals that DashML is not just a convention, but a real Domain-Specific Language!**

