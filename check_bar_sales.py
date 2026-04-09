import json
d = json.load(open("output_grafana_sql/dashboard.json"))
for p in d.get("panels", []):
    if "Total Sales by Country" in p.get("title", ""):
        for t in p.get("targets", []):
            print(f"SQL: {t.get('rawSql')}")
        print(f"Transforms: {p.get('transformations', [])}")
        break
