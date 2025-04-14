import json
import csv
import os
from datetime import datetime
from db.database import Database
from db.models import CompetitorBrand, CatalogProduct, PriceHistory
from tinydb import TinyDB

def save_to_csv(data, filename):
    """Save data to CSV file"""
    if not data:
        print(f"No data to save to {filename}")
        return
        
    os.makedirs('exports', exist_ok=True)
    filepath = os.path.join('exports', filename)
    
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    
    print(f"Data saved to {filepath}")

def main():
    # Initialize database connection
    db = Database()
    
    # Get data from all tables using direct TinyDB access for accurate doc_ids
    db_raw = TinyDB("data/db.json")
    catalog_table = db_raw.table('catalog')
    prices_table = db_raw.table('prices')
    
    competitors = db.get_all_competitors()
    
    # Get catalog products directly and set their IDs properly
    catalog_raw = catalog_table.all()
    catalog_products = []
    for doc in catalog_raw:
        product = CatalogProduct(**doc)
        product.id = doc.doc_id  # Set the ID from the doc_id
        catalog_products.append(product)
    
    # Display summary
    print(f"\n=== Database Summary ===")
    print(f"Competitors: {len(competitors)}")
    print(f"Catalog Products: {len(catalog_products)}")
    print(f"Price History Records: {len(prices_table)}")
    
    # Prepare data for CSV export
    competitors_data = [c.model_dump() for c in competitors]
    products_data = [p.model_dump() for p in catalog_products]
    
    # Collect all price history using doc_id as catalog_id
    all_prices = []
    price_count = 0
    
    print(f"\nCollecting price history data...")
    for i, prod in enumerate(catalog_products):
        if i % 100 == 0:
            print(f"Processing product {i+1}/{len(catalog_products)}...")
            
        # Get price history records directly using lambda search
        price_records = prices_table.search(lambda x: x.get('catalog_id') == prod.id)
        
        for price_doc in price_records:
            price = PriceHistory(**price_doc)
            price.id = price_doc.doc_id
            all_prices.append(price)
        
        price_count += len(price_records)
    
    print(f"Total prices collected: {len(all_prices)}")
    print(f"Database reports {len(prices_table)} price records")
    print(f"Individual price count: {price_count}")
    
    # Debug: Check a specific product's price history
    if catalog_products:
        sample_product = catalog_products[0]
        print(f"\nChecking price history for sample product (ID: {sample_product.id})")
        price_records = prices_table.search(lambda x: x.get('catalog_id') == sample_product.id)
        print(f"Found {len(price_records)} price records for this product")
        if price_records:
            print(f"Sample price: {price_records[0].get('price')} {price_records[0].get('currency')}")
    
    prices_data = [p.model_dump() for p in all_prices]
    print(f"Price data objects created: {len(prices_data)}")
    
    # Convert datetime objects to strings for CSV
    for item in competitors_data + products_data + prices_data:
        for key, value in item.items():
            if isinstance(value, (datetime, dict)):
                item[key] = str(value)
    
    # Save to CSV
    save_to_csv(competitors_data, 'competitors.csv')
    save_to_csv(products_data, 'products.csv')
    save_to_csv(prices_data, 'prices.csv')
    
    print("\nAll data exported to CSV files in the 'exports' directory")

if __name__ == "__main__":
    main() 