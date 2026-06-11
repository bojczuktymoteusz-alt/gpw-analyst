from database import get_db_connection
conn = get_db_connection()
rows = conn.execute('SELECT ticker, payout_ratio, debt_to_equity, trailing_div_yield FROM stocks LIMIT 3').fetchall()
for r in rows:
    print(dict(r))
conn.close()