import requests

session = requests.Session()
r = session.post("http://localhost:8088/api/v1/security/login", json={
    "username": "admin", "password": "admin", "provider": "db"
})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Try various version endpoints
for endpoint in ["/api/v1/version/", "/version", "/api/v1/me/"]:
    r = session.get(f"http://localhost:8088{endpoint}", headers=headers)
    print(f"{endpoint}: {r.text[:200] if r.ok else r.status_code}")
