import sqlite3
import os

db_path = os.path.join('backend', 'gpw_data.db')
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute('UPDATE stocks SET last_updated = "2000-01-01 00:00:00"')
    conn.commit()
    conn.close()
    print("Database cache cleared.")
else:
    print(f"Database not found at {db_path}")
