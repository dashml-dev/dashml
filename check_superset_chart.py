import requests

session = requests.Session()
# Login
r = session.post("http://localhost:8088/api/v1/security/login", json={
    "username": "admin", "password": "admin", "provider": "db"
})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get the grouped bar chart (most recent)
r = session.get("http://localhost:8088/api/v1/chart/?q=(filters:!((col:slice_name,opr:eq,value:'Orders by Country (Grouped by Status)')))", headers=headers)
charts = r.json().get("result", [])
if charts:
    chart = charts[0]
    chart_id = chart["id"]
    # Get full chart details
    r = session.get(f"http://localhost:8088/api/v1/chart/{chart_id}", headers=headers)
    detail = r.json()["result"]
    import json
    params = json.loads(detail.get("params", "{}"))
    print("=== params ===")
    for k in ["x_axis_sort", "x_axis_sort_asc", "order_desc", "orderby", "groupby"]:
        print(f"  {k}: {params.get(k, 'NOT SET')}")

    qc = json.loads(detail.get("query_context", "{}"))
    fd = qc.get("form_data", {})
    print("\n=== query_context.form_data ===")
    for k in ["x_axis_sort", "x_axis_sort_asc", "order_desc", "orderby", "groupby"]:
        print(f"  {k}: {fd.get(k, 'NOT SET')}")
