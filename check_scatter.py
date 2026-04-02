import json
d = json.load(open("output_grafana/dashboard.json"))
for p in d.get("panels", []):
    if p.get("type") == "xychart":
        print(f"Title: {p['title']}")
        print(f"Type: {p['type']}")
        print(f"Options: {json.dumps(p.get('options', {}), indent=2)}")
        print(f"Transforms: {p.get('transformations', [])}")
        print()
