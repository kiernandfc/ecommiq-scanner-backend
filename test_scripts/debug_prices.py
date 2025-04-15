import json
from tinydb import TinyDB
import os
from pathlib import Path

def main():
    # Open the database directly
    db_path = "data/db.json"
    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}")
        return
        
    db = TinyDB(db_path)
    prices_table = db.table('prices')
    
    # Get all price records
    all_prices = prices_table.all()
    print(f"\n=== Price Table Analysis ===")
    print(f"Total price records: {len(all_prices)}")
    
    if not all_prices:
        print("No price records found in the database!")
        return
        
    # Analyze the first few records
    print(f"\nSample price records:")
    for i, price in enumerate(all_prices[:5]):
        print(f"Record {i+1}: {json.dumps(price, indent=2)}")
    
    # Check catalog_id field
    catalog_ids = set(p.get('catalog_id') for p in all_prices if 'catalog_id' in p)
    print(f"\nUnique catalog_ids: {len(catalog_ids)}")
    print(f"Sample catalog_ids: {list(catalog_ids)[:5] if catalog_ids else 'None'}")
    
    # Test query
    if catalog_ids:
        test_id = next(iter(catalog_ids))
        test_query = prices_table.search(lambda x: x.get('catalog_id') == test_id)
        print(f"\nTest query for catalog_id={test_id}: found {len(test_query)} records")
    
    # Save raw data for inspection
    os.makedirs('exports', exist_ok=True)
    with open('exports/raw_prices.json', 'w') as f:
        json.dump(all_prices, f, indent=2)
    print(f"\nRaw price data saved to exports/raw_prices.json")

if __name__ == "__main__":
    main() 