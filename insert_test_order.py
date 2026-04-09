from sqlalchemy import create_engine, text

e = create_engine('postgresql://neondb_owner:npg_fm0ZpyB5CQkT@ep-gentle-glitter-a9duu2r4-pooler.gwc.azure.neon.tech:5432/neondb')

with e.connect() as conn:
    conn.execute(text("""
        INSERT INTO public.orders (order_id, customer_id, order_date, total_amount, status,
            shipping_address_city, shipping_address_state, shipping_address_country,
            payment_method, discount_amount, tax_amount)
        VALUES
            ('ORDTSTUK', 'CTEST', '2024-06-01', 5000.00, 'delivered', 'London', 'England', 'GB', 'paypal', 0, 500),
            ('ORDTSTDE', 'CTEST', '2024-06-01', 3000.00, 'shipped', 'Berlin', 'Berlin', 'DE', 'paypal', 0, 300),
            ('ORDTSTJP', 'CTEST', '2024-06-01', 7000.00, 'processing', 'Tokyo', 'Tokyo', 'JP', 'paypal', 0, 700)
    """))
    conn.commit()
    print("Inserted 3 test orders (GB, DE, JP)")

    # Verify
    result = conn.execute(text("SELECT DISTINCT shipping_address_country FROM public.orders"))
    print("Countries now:", [r[0] for r in result])
