import json
d = json.load(open("output_grafana_sql/dashboard.json"))
for p in d.get("panels", []):
    title = p.get("title", "")
    if "Order Count" in title or "heatmap" in title.lower():
        print(f"Title: {title}")
        print(f"Type: {p['type']}")
        for t in p.get("targets", []):
            print(f"SQL: {t.get('rawSql')}")
        transforms = p.get("transformations", [])
        print(f"Transforms: {len(transforms)}")
        for t in transforms:
            print(f"  {t['id']}: {json.dumps(t['options'])[:200]}")
        break
