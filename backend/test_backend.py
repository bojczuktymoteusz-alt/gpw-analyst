import sys
import os

# Add parent directory to path
sys.path.append(os.getcwd())

try:
    from data_fetcher import get_all_stocks
    print("Attempting to fetch stocks...")
    data = get_all_stocks()
    print(f"Success! Fetched {len(data)} stocks.")
    for s in data:
        print(f" - {s['ticker']}: {s['price']} (Div: {s['div_yield']})")
except Exception as e:
    print(f"\nCRASH DETECTED:")
    import traceback
    traceback.print_exc()
