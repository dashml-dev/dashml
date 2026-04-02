import json
d = json.load(open("output_grafana/dashboard.json"))
for p in d.get("panels", []):
    if p.get("type") == "geomap":
        print(f"Title: {p['title']}")
        print(f"Type: {p['type']}")
        layer = p["options"]["layers"][0]
        print(f"Layer type: {layer['type']}")
        print(f"Location: {json.dumps(layer['location'], indent=2)}")
        print(f"Style: {json.dumps(layer['config']['style'], indent=2)}")
        print(f"Transforms: {len(p.get('transformations', []))}")
        for t in p.get("transformations", []):
            print(f"  {t['id']}: {json.dumps(t['options'])}")
        break
