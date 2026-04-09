import json
d = json.load(open("output_grafana_sql/dashboard.json"))
for p in d.get("panels", []):
    if "Grouped by Status" in p.get("title", ""):
        print(f"Title: {p['title']}")
        for t in p.get("targets", []):
            print(f"SQL: {t.get('rawSql')}")
        transforms = p.get("transformations", [])
        print(f"Transforms: {len(transforms)}")
        for t in transforms:
            print(f"  {t['id']}: {json.dumps(t['options'])[:200]}")
        print(f"Stacking: {p.get('options', {}).get('stacking')}")
        break
