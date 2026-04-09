from sqlalchemy import create_engine
import pandas as pd
e = create_engine('postgresql://neondb_owner:npg_fm0ZpyB5CQkT@ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech:5432/neondb')
df = pd.read_sql('SELECT DISTINCT shipping_address_country FROM public.orders', e)
print("Countries in DB:")
print(df)
