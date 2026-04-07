from dashml_new.core.engine import DashMLEngine
e = DashMLEngine()
spec = e.load('dashml_new/sql_definitive.dashml', db_config={'type':'postgresql','host':'x','port':5432,'database':'x','user':'x','password':'x'})
charts = [c for p in spec.get('pages',[]) for c in p.get('charts',[])]
for c in charts:
    cid = c['id']
    if 'pie' in cid or 'grouped' in cid or 'stacked' in cid or 'bar_sales' in cid:
        print(f"{cid}: x={c.get('x')}, y={c.get('y')}, group={c.get('group')}, agg={c.get('agg')}")
