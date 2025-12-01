# Test Observable Plot transformer
python dashml_new\cli.py build dashboard_multipage.dashml -t observable -o app_observable.html
Write-Host "`n✓ Generated: app_observable.html"
Write-Host "`nTo view the dashboard, run:"
Write-Host "  python -m http.server 8000"
Write-Host "Then open: http://localhost:8000/app_observable.html"
