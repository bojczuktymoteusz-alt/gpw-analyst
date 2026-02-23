import sys
import os
import sqlite3

# Add parent directory to path
sys.path.append(os.getcwd())

from database import DB_NAME, get_db_connection, init_db
from data_fetcher import get_all_stocks

print("Initializing DB...")
init_db()

print("--- Database Content ---")
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT ticker, name, recommendation FROM stocks")
rows = cursor.fetchall()
for row in rows:
    print(f"Ticker: {row['ticker']}, Name: {row['name']}, Rec: {row['recommendation']}")
conn.close()

print("\n--- API Response (first stock) ---")
stocks = get_all_stocks()
if stocks:
    s = stocks[0]
    print(f"Ticker: {s['ticker']}")
    print(f"Name: {s['name']}")
    print(f"Recommendation: {s.get('recommendation')}")
else:
    print("No stocks returned")
