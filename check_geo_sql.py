import json
d = json.load(open("output_grafana_sql/dashboard.json"))
for p in d.get("panels", []):
    if "Map" in p.get("title", ""):
        print(f"Title: {p['title']}")
        for t in p.get("targets", []):
            print(f"SQL: {t.get('rawSql')}")
        layers = p.get("options", {}).get("layers", [])
        if layers:
            print(f"Location: {json.dumps(layers[0].get('location', {}))}")
            print(f"Style: {json.dumps(layers[0].get('config', {}).get('style', {}))}")
        transforms = p.get("transformations", [])
        print(f"Transforms: {len(transforms)}")
        for t in transforms:
            print(f"  {t['id']}: {json.dumps(t['options'])[:200]}")
        break
