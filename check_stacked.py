import json
d = json.load(open("output_grafana/dashboard.json"))
for p in d.get("panels", []):
    if "Industry" in p.get("title", "") and "Stage" in p.get("title", ""):
        print(f"=== {p['title']} ===")
        print(f"Type: {p['type']}")
        print(f"Stacking: {p.get('options', {}).get('stacking', '?')}")
        transforms = p.get("transformations", [])
        print(f"Transforms: {len(transforms)}")
        for t in transforms:
            print(f"  {t['id']}: {json.dumps(t['options'])[:300]}")
        # Check target columns
        if p.get("targets"):
            cols = [c.get("selector") for c in p["targets"][0].get("columns", [])]
            print(f"Target columns: {cols}")
        print()
