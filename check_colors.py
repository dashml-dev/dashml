import json
d = json.load(open("output_grafana/dashboard.json"))
for p in d.get("panels", []):
    if "Industry Funding by Stage" in p.get("title", ""):
        overrides = p.get("fieldConfig", {}).get("overrides", [])
        for o in overrides:
            print(json.dumps(o, indent=2))
        break
