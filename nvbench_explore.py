"""Explore nvBench 2.0 dataset samples."""
import json
from datasets import load_dataset

ds = load_dataset("TianqiLuo/nvBench2.0", split="test")
print(f"Test set: {len(ds)} entries")
print(f"Columns: {ds.column_names}")
print()

# Show 3 samples
for i in [0, 10, 50]:
    entry = ds[i]
    print(f"=== Entry {i} ===")
    print(f"NL: {entry['nl_query']}")
    schema = json.loads(entry["table_schema"]) if isinstance(entry["table_schema"], str) else entry["table_schema"]
    print(f"Table cols: {schema.get('table_columns', [])}")
    col_examples = schema.get("column_examples", {})
    for col, vals in list(col_examples.items())[:4]:
        print(f"  {col}: {vals[:3]}")
    gold = json.loads(entry["gold_answer"]) if isinstance(entry["gold_answer"], str) else entry["gold_answer"]
    print(f"Gold answers: {len(gold)}")
    for j, g in enumerate(gold[:2]):
        print(f"  Gold[{j}]: {json.dumps(g)}")
    print()
