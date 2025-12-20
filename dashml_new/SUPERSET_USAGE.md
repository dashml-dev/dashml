# Apache Superset Transformer - Usage Guide

The Superset transformer **directly creates dashboards** in Apache Superset via REST API. No code generation, no intermediate steps!

## Quick Start

### Single Command

```bash
cd /mnt/c/Dev/dashml/playground/dashml_new

python3 cli.py build ../dashboard_new_charts.dashml \
  --target superset \
  --superset-user admin \
  --superset-password admin
```

That's it! Your dashboard is created immediately.

### With Custom Superset URL

```bash
python3 cli.py build dashboard.dashml \
  --target superset \
  --superset-url http://your-superset.com:8088 \
  --superset-user your_username \
  --superset-password your_password
```

## What Happens

When you run the command, you'll see:

```
==============================================================
DashML → Apache Superset Dashboard Creator
==============================================================

✓ Authenticated successfully
Dataset 'example' not found. Uploading CSV...
✓ CSV uploaded successfully
✓ Dataset created: example (ID: 1)

Creating charts...
✓ Created chart: Bar Chart (ID: 1)
✓ Created chart: Line Chart (ID: 2)
✓ Created chart: Area Chart - Sales Over Time (ID: 3)
✓ Created chart: Histogram - Sales Distribution (ID: 4)
✓ Created chart: Stacked Bar - Sales by Country and Product (ID: 5)
✓ Created chart: Grouped Bar - Sales by Country and Product (ID: 6)

Creating/updating dashboard...
✓ Created dashboard: New Chart Types Demo (ID: 1)
✓ Added 6 charts to dashboard

🎉 Dashboard created successfully!

URL: http://localhost:8088/superset/dashboard/1/
```

**Open the URL** in your browser to see your dashboard!

## Features

### 1. Automatic CSV Upload ✨

The transformer automatically uploads your CSV file to Superset. No manual upload needed.

### 2. Dashboard Deduplication ✨

Run the command multiple times - it will **update** the existing dashboard instead of creating duplicates:

**First run:**
```
✓ Created dashboard: New Chart Types Demo (ID: 1)
URL: http://localhost:8088/superset/dashboard/1/
```

**Second run (after changing the DashML file):**
```
✓ Found existing dashboard: New Chart Types Demo (ID: 1)
✓ Cleaned up 6 old charts
✓ Updated dashboard with 6 new charts
URL: http://localhost:8088/superset/dashboard/1/  ← Same URL!
```

### 3. Idempotent Operations

Running the same command multiple times is safe:
- First time: Creates everything
- Subsequent times: Updates in place
- No duplicates, no orphaned resources

### 4. Perfect for CI/CD

```bash
# In your deployment pipeline
python3 cli.py build production-dashboard.dashml \
  --target superset \
  --superset-url $SUPERSET_URL \
  --superset-user $SUPERSET_USER \
  --superset-password $SUPERSET_PASSWORD
```

Every deploy updates the dashboard automatically!

## DashML to Superset Chart Mapping

| DashML Type | Superset Viz Type | Notes |
|-------------|-------------------|-------|
| `bar` | `dist_bar` | Distribution bar chart |
| `line` | `line` | Line chart |
| `scatter` | `scatter` | Scatter plot |
| `pie` | `pie` | Pie chart |
| `area` | `area` | Area chart |
| `histogram` | `histogram` | Histogram |
| `stacked_bar` | `dist_bar` | With column grouping |
| `grouped_bar` | `dist_bar` | With column grouping |

## Comparison: Before vs After

### ❌ Old Approach (Code Generation)
```bash
# Step 1: Generate Python script
python3 cli.py build dashboard.dashml --backend superset --output create.py

# Step 2: Edit the script to add credentials
vim create.py  # Add USERNAME and PASSWORD

# Step 3: Upload CSV manually via Superset UI
# (Open browser, navigate to Data → Upload CSV, etc.)

# Step 4: Run the script
python3 create.py

# Result: Creates Dashboard ID: 1

# Problem: Run again and it creates Dashboard ID: 2 (duplicate!)
```

### ✅ New Approach (Direct Execution)
```bash
# Single command - everything happens automatically!
python3 cli.py build dashboard.dashml --target superset \
  --superset-user admin --superset-password admin

# Result: Creates Dashboard ID: 1

# Run again: Updates Dashboard ID: 1 (no duplicate!)
```

**Benefits:**
- 🚀 3x faster (no intermediate steps)
- 🎯 No manual CSV upload
- ♻️ No duplicate dashboards
- 🔒 Safe to run repeatedly

## Troubleshooting

### Authentication Failed

```
✗ Authentication failed: 401
```

**Fix:** Check username and password are correct:
```bash
python3 cli.py build dashboard.dashml --target superset \
  --superset-user admin \
  --superset-password your_correct_password
```

### CSV Upload Failed

```
✗ CSV upload failed: 500
```

**Possible causes:**
- CSV file not found at the path specified in the DashML spec
- Superset database not configured properly
- Permissions issue

**Fix:** Check the CSV path in your `.dashml` file:
```yaml
data:
  type: csv
  path: "data/example.csv"  # ← Make sure this file exists
```

### Superset Not Reachable

```
✗ Authentication failed: Connection refused
```

**Fix:** Make sure Superset is running:
```bash
# Check if Superset is running
curl http://localhost:8088

# If not running, start it
# (Depends on your Superset installation method)
```

### Missing requests Library

```
TransformerError: requests library required for Superset transformer.
Install with: pip install requests
```

**Fix:**
```bash
pip install requests
# or
pip3 install requests
```

## Environment Variables (Optional)

Instead of passing credentials via CLI arguments, you can use environment variables:

```bash
export SUPERSET_URL="http://localhost:8088"
export SUPERSET_USER="admin"
export SUPERSET_PASSWORD="admin"

# Then modify cli.py to read from env vars (future enhancement)
```

## Advanced: Multi-Page Dashboards

Multi-page DashML specs work automatically:

```yaml
pages:
  - id: "overview"
    title: "Overview"
    charts:
      - id: "sales"
        type: "bar"
        # ...

  - id: "details"
    title: "Details"
    charts:
      - id: "breakdown"
        type: "line"
        # ...
```

All charts from all pages are created in a single Superset dashboard. Chart IDs are prefixed with the page ID to avoid conflicts.

## Real-World Example

Deploy dashboard from GitHub Actions:

```yaml
# .github/workflows/deploy-dashboard.yml
name: Deploy Superset Dashboard

on:
  push:
    branches: [main]
    paths:
      - 'dashboards/*.dashml'
      - 'data/*.csv'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install pyyaml requests

      - name: Deploy to Superset
        run: |
          python3 dashml_new/cli.py build dashboards/sales.dashml \
            --target superset \
            --superset-url ${{ secrets.SUPERSET_URL }} \
            --superset-user ${{ secrets.SUPERSET_USER }} \
            --superset-password ${{ secrets.SUPERSET_PASSWORD }}
```

Every commit to `main` automatically updates your dashboard! 🎉
