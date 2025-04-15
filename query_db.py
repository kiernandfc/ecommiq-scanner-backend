import json
import csv
import os
from datetime import datetime
from dotenv import load_dotenv
from db.factory import get_database
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
    # Load environment variables
    load_dotenv()
    
    # Initialize database connection
    db = get_database()
    
    # Get data from database
    competitors = db.get_all_competitors()
    
    # Get all catalog products
    catalog_products = []
    for i, competitor in enumerate(competitors):
        print(f"{i+1}. {competitor.reference_brand} {competitor.reference_product} -> {competitor.competitor_brand}")

    choice = int(input("\nSelect a competitor to view products: "))
    competitor = competitors[choice - 1]
    
    print(f"\nProducts for {competitor.competitor_brand}:\n")
    
    # Get products for this competitor
    products = db.get_catalog_by_competitor(competitor.id)
    catalog_products.extend(products)
    
    # Count prices
    price_count = 0
    all_prices = []
    
    # Display summary
    print(f"\n=== Database Summary ===")
    print(f"Competitors: {len(competitors)}")
    print(f"Catalog Products: {len(catalog_products)}")
    
    # Prepare data for CSV export
    competitors_data = [c.model_dump() for c in competitors]
    products_data = [p.model_dump() for p in catalog_products]
    
    # Collect all price history
    print(f"\nCollecting price history data...")
    for i, prod in enumerate(catalog_products):
        if i % 100 == 0:
            print(f"Processing product {i+1}/{len(catalog_products)}...")
            
        # Get price history records
        price_records = db.get_price_history(prod.id)
        all_prices.extend(price_records)
        price_count += len(price_records)
    
    print(f"Total prices collected: {len(all_prices)}")
    print(f"Individual price count: {price_count}")
    
    # Debug: Check a specific product's price history
    if catalog_products:
        sample_product = catalog_products[0]
        print(f"\nChecking price history for sample product (ID: {sample_product.id})")
        price_records = db.get_price_history(sample_product.id)
        print(f"Found {len(price_records)} price records for this product")
        if price_records:
            print(f"Sample price: {price_records[0].price} {price_records[0].currency}")
    
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