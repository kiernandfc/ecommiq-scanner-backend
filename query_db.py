import json
import csv
import os
from datetime import datetime
from db.database import Database
from db.models import CompetitorBrand, CatalogProduct, PriceHistory

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
    
    # Get data from all tables
    competitors = db.get_all_competitors()
    catalog_products = [db.get_catalog_product(i+1) for i in range(len(db.catalog))]
    catalog_products = [p for p in catalog_products if p is not None]
    
    # Display summary
    print(f"\n=== Database Summary ===")
    print(f"Competitors: {len(competitors)}")
    print(f"Catalog Products: {len(catalog_products)}")
    print(f"Price History Records: {len(db.prices)}")
    
    # Prepare data for CSV export
    competitors_data = [c.model_dump() for c in competitors]
    products_data = [p.model_dump() for p in catalog_products]
    
    # Collect all price history
    all_prices = []
    for prod in catalog_products:
        prices = db.get_price_history(prod.id)
        all_prices.extend(prices)
    prices_data = [p.model_dump() for p in all_prices]
    
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