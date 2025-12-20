#!/usr/bin/env python3
"""
Inspect a Superset dashboard to understand its structure
"""
import sys
import os
sys.path.insert(0, os.getcwd())

from transformers.superset import SupersetTransformer
import json

def inspect_dashboard(dashboard_id):
    # Create transformer with credentials
    transformer = SupersetTransformer(
        superset_url="http://localhost:8088",
        username="admin",
        password="admin"
    )

    # Create session (normally done in build())
    import requests
    transformer.session = requests.Session()

    # Authenticate
    if not transformer._authenticate():
        print("Authentication failed")
        return

    # Get dashboard details
    url = f"http://localhost:8088/api/v1/dashboard/{dashboard_id}"
    response = transformer.session.get(url, headers=transformer._get_headers())

    if response.status_code != 200:
        print(f"Error getting dashboard: {response.status_code}")
        print(response.text[:500])
        return

    dashboard = response.json()['result']

    print("=" * 80)
    print(f"DASHBOARD {dashboard_id}: {dashboard.get('dashboard_title')}")
    print("=" * 80)
    print(f"ID: {dashboard.get('id')}")
    print(f"Published: {dashboard.get('published')}")
    print(f"Charts: {dashboard.get('charts', [])}")
    print()

    # Parse position_json
    position_json_str = dashboard.get('position_json', '{}')
    position_json = json.loads(position_json_str)

    print("=" * 80)
    print("POSITION JSON STRUCTURE")
    print("=" * 80)
    print(f"Version: {position_json.get('DASHBOARD_VERSION_KEY')}")
    print()

    # Show HEADER
    if 'HEADER_ID' in position_json:
        print("HEADER_ID:")
        print(json.dumps(position_json['HEADER_ID'], indent=2))
        print()

    # Show ROOT
    if 'ROOT_ID' in position_json:
        print("ROOT_ID:")
        print(json.dumps(position_json['ROOT_ID'], indent=2))
        print()

    # Show GRID_ID if it exists
    if 'GRID_ID' in position_json:
        print("GRID_ID:")
        print(json.dumps(position_json['GRID_ID'], indent=2))
        print()

    # Show all ROW entries
    print("ROW ENTRIES:")
    for key, value in position_json.items():
        if key.startswith('ROW-'):
            print(f"\n{key}:")
            print(json.dumps(value, indent=2))

    # Show all CHART entries
    print("\nCHART ENTRIES:")
    for key, value in position_json.items():
        if key.startswith('CHART-'):
            print(f"\n{key}:")
            print(json.dumps(value, indent=2))

    # Get details of one chart to see its configuration
    chart_ids = dashboard.get('charts', [])
    if chart_ids:
        print("\n" + "=" * 80)
        print(f"SAMPLE CHART DETAILS (Chart ID: {chart_ids[0]})")
        print("=" * 80)

        chart_url = f"http://localhost:8088/api/v1/chart/{chart_ids[0]}"
        chart_response = transformer.session.get(chart_url, headers=transformer._get_headers())

        if chart_response.status_code == 200:
            chart_data = chart_response.json()['result']

            print(f"Chart Name: {chart_data.get('slice_name')}")
            print(f"Viz Type: {chart_data.get('viz_type')}")
            print(f"Datasource ID: {chart_data.get('datasource_id')}")
            print(f"Datasource Type: {chart_data.get('datasource_type')}")

            print("\n--- PARAMS ---")
            params = json.loads(chart_data.get('params', '{}'))
            print(json.dumps(params, indent=2))

            print("\n--- QUERY CONTEXT ---")
            query_context = json.loads(chart_data.get('query_context', '{}'))
            print(json.dumps(query_context, indent=2))

if __name__ == '__main__':
    dashboard_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    inspect_dashboard(dashboard_id)
