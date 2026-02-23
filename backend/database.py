import sqlite3

DB_NAME = "gpw_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stocks
                 (ticker TEXT PRIMARY KEY, 
                  price REAL, 
                  pe REAL, 
                  pbv REAL, 
                  roe REAL, 
                  div_yield REAL,
                  last_updated TIMESTAMP)''')
    
    # Migration: Add 'name' and 'recommendation' columns if they don't exist
    c.execute("PRAGMA table_info(stocks)")
    columns = [col[1] for col in c.fetchall()]
    if 'name' not in columns:
        print("Migrating database: adding 'name' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN name TEXT")
    if 'recommendation' not in columns:
        print("Migrating database: adding 'recommendation' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN recommendation TEXT")
    if 'market_cap' not in columns:
        print("Migrating database: adding 'market_cap' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN market_cap REAL")
    if 'beta' not in columns:
        print("Migrating database: adding 'beta' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN beta REAL")
    if 'sector' not in columns:
        print("Migrating database: adding 'sector' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN sector TEXT")
    if 'operating_margin' not in columns:
        print("Migrating database: adding 'operating_margin' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN operating_margin REAL")
    if 'ebitda' not in columns:
        print("Migrating database: adding 'ebitda' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN ebitda REAL")
    if 'total_debt' not in columns:
        print("Migrating database: adding 'total_debt' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN total_debt REAL")
    if 'total_cash' not in columns:
        print("Migrating database: adding 'total_cash' column...")
        c.execute("ALTER TABLE stocks ADD COLUMN total_cash REAL")
        
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn
