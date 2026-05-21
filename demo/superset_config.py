"""
Custom Superset config for the DashML demo stack.

Mounted at /app/pythonpath/superset_config.py — Superset reads it on startup.
Intentionally minimal: 4.1.x bundles heatmap_v2/histogram_v2 plugins by
default, so no feature flags are required. This file is kept as a hook for
future demo-specific tweaks.
"""

LOG_LEVEL = "WARNING"
