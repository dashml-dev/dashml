# Editor Setup for .dashml Files

This guide helps you set up proper YAML formatting, syntax highlighting, and validation for `.dashml` files in VS Code/Cursor.

---

## ✅ Quick Setup (Already Done!)

The project already includes configuration files:

```
.vscode/
├── settings.json      # Editor settings for .dashml
├── extensions.json    # Recommended extensions
dashml-schema.json     # JSON Schema for validation
```

---

## 🔧 Manual Setup (if needed)

### 1. Install YAML Extension

**Recommended**: [YAML by Red Hat](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)

Install via:
- Command Palette (Cmd/Ctrl + Shift + P)
- Type: "Extensions: Install Extensions"
- Search: "YAML"
- Install "YAML" by Red Hat

Or from terminal:
```bash
code --install-extension redhat.vscode-yaml
```

### 2. Associate .dashml with YAML

Add to your **User Settings** or **Workspace Settings**:

**Option A: Via UI**
1. Open a `.dashml` file
2. Click language indicator (bottom right)
3. Select "Configure File Association for '.dashml'"
4. Choose "YAML"

**Option B: Via settings.json**
```json
{
  "files.associations": {
    "*.dashml": "yaml"
  }
}
```

### 3. Enable YAML Formatting

Add to `settings.json`:

```json
{
  "[yaml]": {
    "editor.insertSpaces": true,
    "editor.tabSize": 2,
    "editor.autoIndent": "advanced",
    "editor.formatOnSave": true
  },
  "yaml.format.enable": true,
  "yaml.format.singleQuote": false,
  "yaml.format.bracketSpacing": true
}
```

### 4. Enable Schema Validation

```json
{
  "yaml.schemas": {
    "./dashml-schema.json": "*.dashml"
  },
  "yaml.validate": true,
  "yaml.completion": true,
  "yaml.hover": true
}
```

---

## 🎨 Features You Get

### ✅ Syntax Highlighting
- Keywords, strings, numbers properly colored
- Easy to read and navigate

### ✅ Auto-formatting
- Press **Shift + Alt + F** (Windows/Linux) or **Shift + Option + F** (Mac)
- Or enable "Format on Save" for automatic formatting

### ✅ Auto-completion
- Type `charts:` and get suggestions
- Autocomplete field names based on schema

### ✅ Validation
- Red squiggles for invalid syntax
- Warnings for missing required fields
- Hover tooltips with field descriptions

### ✅ Error Detection
- Invalid YAML syntax highlighted
- Schema violations shown inline
- Helpful error messages

---

## 📝 Example: What You'll See

When editing `dashml_example.dashml`:

```yaml
version: 0.000000001  # ✅ Validated against schema
title: "My Dashboard"

data:
  type: csv           # ✅ Autocomplete: csv, json, sql, api
  path: "data/example.csv"

charts:
  - id: "chart_1"     # ✅ Hover shows: "Unique chart identifier"
    type: bar         # ✅ Autocomplete: bar, line, scatter, pie
    x: country
    y: sales
    agg: sum          # ✅ Autocomplete: sum, mean, count, min, max
```

**Errors shown:**
- Missing required field `type` → Red squiggle + "Missing required property"
- Invalid chart type `barchart` → "Value is not accepted. Valid values: bar, line..."
- Invalid version format → "String does not match pattern"

---

## 🔍 Keyboard Shortcuts

| Action | Windows/Linux | Mac |
|--------|--------------|-----|
| Format Document | Shift + Alt + F | Shift + Option + F |
| Trigger Suggest | Ctrl + Space | Cmd + Space |
| Show Hover | Ctrl + K, Ctrl + I | Cmd + K, Cmd + I |
| Go to Definition | F12 | F12 |

---

## 🎓 Schema Benefits for Thesis

Having a JSON Schema for `.dashml` demonstrates:

1. **Formal Specification** - DashML has a well-defined structure
2. **Validation Support** - Ensures correctness before execution
3. **Documentation** - Schema serves as formal documentation
4. **IDE Integration** - Professional tooling support
5. **Type Safety** - Catches errors at edit-time, not runtime

---

## 🔧 Troubleshooting

### Issue: YAML extension not working

**Solution:**
```bash
# Reload VS Code
Cmd/Ctrl + Shift + P → "Developer: Reload Window"
```

### Issue: Schema not validating

**Solution:**
1. Check `dashml-schema.json` is in project root
2. Verify path in settings: `"./dashml-schema.json"`
3. Reload window

### Issue: Format on save not working

**Solution:**
```json
{
  "editor.formatOnSave": true,
  "[yaml]": {
    "editor.formatOnSave": true
  }
}
```

### Issue: Wrong indentation

**Solution:**
```json
{
  "[yaml]": {
    "editor.tabSize": 2,
    "editor.insertSpaces": true
  }
}
```

---

## 🚀 Advanced: Custom Snippets

Create `.vscode/dashml.code-snippets`:

```json
{
  "DashML Basic": {
    "prefix": "dashml",
    "body": [
      "version: 0.000000001",
      "title: \"${1:Dashboard Title}\"",
      "",
      "data:",
      "  type: ${2|csv,json,sql|}",
      "  path: \"${3:data/example.csv}\"",
      "",
      "charts:",
      "  - id: \"${4:chart_1}\"",
      "    type: ${5|bar,line,scatter,pie|}",
      "    title: \"${6:Chart Title}\"",
      "    x: ${7:column_x}",
      "    y: ${8:column_y}",
      "    agg: ${9|sum,mean,count|}"
    ],
    "description": "DashML basic template"
  },
  "DashML Chart": {
    "prefix": "chart",
    "body": [
      "- id: \"${1:chart_id}\"",
      "  type: ${2|bar,line,scatter,pie|}",
      "  title: \"${3:Chart Title}\"",
      "  x: ${4:column_x}",
      "  y: ${5:column_y}",
      "  agg: ${6|sum,mean,count|}"
    ],
    "description": "DashML chart definition"
  }
}
```

Then type `dashml` + Tab for instant template!

---

## ✨ Summary

Your editor now treats `.dashml` files as first-class citizens:

- ✅ Syntax highlighting
- ✅ Auto-formatting
- ✅ Schema validation
- ✅ Auto-completion
- ✅ Error detection
- ✅ Hover documentation

**This makes DashML feel like a real, professional language!** 🎉

