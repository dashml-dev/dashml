import json
d = json.load(open("output_vegalite_bare/dashboard.vl.json"))
print(f"{len(d)} charts")
for i, c in enumerate(d):
    channels = list(c.get("encoding", {}).keys())
    transforms = len(c.get("transform", []))
    t = f", transforms={transforms}" if transforms else ""
    print(f"  {i}: mark={c['mark']}, channels={channels}{t}")
