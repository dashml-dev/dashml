import json
d = json.load(open("output_grafana_sql/dashboard.json"))
for p in d.get("panels", []):
    title = p.get("title", "")
    if any(k in title for k in ["Sales by Country (Map)", "Amount vs Tax", "Sales vs Tax"]):
        print(f"=== {title} ===")
        print(f"Type: {p['type']}")
        targets = p.get("targets", [])
        for t in targets:
            print(f"SQL: {t.get('rawSql', 'N/A')}")
        # Check what field names the panel references
        opts = p.get("options", {})
        layers = opts.get("layers", [])
        if layers:
            loc = layers[0].get("location", {})
            print(f"Lookup field: {loc.get('lookup', 'N/A')}")
            style = layers[0].get("config", {}).get("style", {})
            print(f"Size field: {style.get('size', {}).get('field', 'N/A')}")
            print(f"Color field: {style.get('color', {}).get('field', 'N/A')}")
        series = opts.get("series", [])
        if series:
            for s in series:
                for k in ("x", "y", "size", "color"):
                    m = s.get(k, {}).get("matcher", {})
                    if m:
                        print(f"  {k} matcher: {m.get('options', 'N/A')}")
        print()
