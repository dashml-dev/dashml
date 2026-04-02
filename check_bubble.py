import json
d = json.load(open("output_grafana/dashboard.json"))
for p in d.get("panels", []):
    if "Industries" in p.get("title", ""):
        print(f"Title: {p['title']}")
        print(f"Type: {p['type']}")
        print(f"Options: {json.dumps(p.get('options', {}), indent=2)}")
        print(f"Color: {p['fieldConfig']['defaults'].get('color', {})}")
        print(f"Custom: {json.dumps(p['fieldConfig']['defaults'].get('custom', {}), indent=2)}")
        cols = [c.get("selector") for c in p.get("targets", [{}])[0].get("columns", [])]
        print(f"Target columns: {cols}")
        print(f"Transforms: {p.get('transformations', [])}")
        break
