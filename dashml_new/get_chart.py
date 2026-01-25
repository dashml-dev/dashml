#!/usr/bin/env python3
import requests
import json

# Login
session = requests.Session()
login_response = session.post('http://localhost:8088/api/v1/security/login', json={
    'username': 'admin',
    'password': 'admin',
    'provider': 'db',
    'refresh': True
})

if login_response.status_code == 200:
    token = login_response.json()['access_token']

    # Get chart 204
    chart_response = session.get(
        'http://localhost:8088/api/v1/chart/204',
        headers={'Authorization': f'Bearer {token}'}
    )

    if chart_response.status_code == 200:
        chart_data = chart_response.json()['result']

        print("Chart ID:", chart_data.get('id'))
        print("Chart Name:", chart_data.get('slice_name'))
        print("Viz Type:", chart_data.get('viz_type'))
        print("\n=== PARAMS ===")
        params = json.loads(chart_data.get('params', '{}'))
        print(json.dumps(params, indent=2))
        print("\n=== QUERY CONTEXT ===")
        query_context = json.loads(chart_data.get('query_context', '{}'))
        print(json.dumps(query_context, indent=2))
    else:
        print(f"Error getting chart: {chart_response.status_code}")
        print(chart_response.text)
else:
    print(f"Login failed: {login_response.status_code}")
