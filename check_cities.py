import json
d = json.load(open("output_grafana/dashboard.json"))
for p in d.get("panels", []):
    if "Cities" in p.get("title", ""):
        print(f"Title: {p['title']}")
        for t in p.get("transformations", []):
            print(f"  {t['id']}: {json.dumps(t['options'])}")
        break
