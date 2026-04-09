from sqlalchemy import create_engine
import pandas as pd

e = create_engine('postgresql://neondb_owner:npg_fm0ZpyB5CQkT@ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech:5432/neondb')
df = pd.read_sql('SELECT * FROM public.orders LIMIT 3', e)
print("=== dtypes ===")
print(df.dtypes)
print()
print("=== sample ===")
print(df.head())
print()
print("=== total_amount type ===")
print(type(df['total_amount'].iloc[0]))
print(repr(df['total_amount'].iloc[0]))
