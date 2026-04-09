import json
d = json.load(open("output_grafana_sql/dashboard.json"))
for p in d.get("panels", []):
    if "Total Orders" in p.get("title", ""):
        print(f"Title: {p['title']}")
        print(f"Type: {p['type']}")
        for t in p.get("targets", []):
            print(f"SQL: {t.get('rawSql')}")
        print(f"Calcs: {p.get('options', {}).get('reduceOptions', {}).get('calcs')}")
        break
