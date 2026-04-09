import json
d = json.load(open("output_test_vegalite_csv/dashboard.vl.json"))

def find_transforms(obj, path="root"):
    if isinstance(obj, dict):
        if "transform" in obj:
            for i, t in enumerate(obj["transform"]):
                if "aggregate" in t:
                    print(f"{path}.transform[{i}]: {json.dumps(t)}")
        if "title" in obj and "Top 10" in str(obj.get("title", "")):
            print(f"\n=== {obj['title']} ===")
            print(f"Transform: {json.dumps(obj.get('transform', []), indent=2)}")
            print(f"Encoding y: {json.dumps(obj.get('encoding', {}).get('y', {}))}")
        for k, v in obj.items():
            find_transforms(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_transforms(v, f"{path}[{i}]")

find_transforms(d)
