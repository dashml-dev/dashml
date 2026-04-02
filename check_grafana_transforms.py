import json
d = json.load(open("output_grafana/dashboard.json"))
for p in d.get("panels", []):
    title = p.get("title", "?")
    ptype = p.get("type", "?")
    transforms = p.get("transformations", [])
    if transforms:
        print(f"{title} ({ptype}): {len(transforms)} transform(s)")
        for t in transforms:
            print(f"  {t['id']}: {json.dumps(t['options'], indent=4)[:300]}")
    else:
        print(f"{title} ({ptype}): no transforms")
