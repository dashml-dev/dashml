import json
d = json.load(open("output_grafana/dashboard.json"))
for p in d.get("panels", []):
    if "Heatmap" in p.get("title", ""):
        print(f"Title: {p['title']}")
        print(f"Type: {p['type']}")
        print(f"Color: {p['fieldConfig']['defaults'].get('color', {})}")
        print(f"Display mode: {p['fieldConfig']['defaults']['custom'].get('displayMode', '?')}")
        print(f"Transforms: {len(p.get('transformations', []))}")
        for t in p.get("transformations", []):
            print(f"  {t['id']}: {json.dumps(t['options'])}")
        break
