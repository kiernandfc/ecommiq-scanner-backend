import csv
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add the project root directory to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from dotenv import load_dotenv
from db.factory import get_database
from db.models import PriceHistory

def convert_date(date_str):
    """Convert date string to datetime object"""
    date_formats = [
        '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%m/%d/%Y %H:%M'  # Added new format for "4/14/2025 15:41"
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Date format not recognized: {date_str}")

def import_price_history(csv_path):
    """Import price history from CSV file into database"""
    # Load environment variables
    load_dotenv()
    
    # Initialize database connection
    db = get_database()
    
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return
    
    print(f"Importing price history from {csv_path}...")
    
    count = 0
    skipped = 0
    
    with open(csv_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row in reader:
            try:
                # Required fields
                catalog_id = row.get('catalog_id')
                merchant = row.get('merchant')
                price_str = row.get('price')
                currency = row.get('currency', 'USD')
                in_stock_str = row.get('in_stock', 'True')
                timestamp_str = row.get('timestamp')
                
                # Validate required fields
                if not catalog_id or not merchant or not price_str:
                    print(f"Skipping row: Missing required fields - {row}")
                    skipped += 1
                    continue
                
                # Convert price to Decimal
                try:
                    price = Decimal(price_str.replace('$', '').replace(',', '').strip())
                except:
                    print(f"Skipping row: Invalid price format - {price_str}")
                    skipped += 1
                    continue
                
                # Convert in_stock to boolean
                in_stock = in_stock_str.lower() in ('true', 'yes', '1', 'y')
                
                # Convert timestamp
                timestamp = datetime.now()
                if timestamp_str:
                    try:
                        timestamp = convert_date(timestamp_str)
                    except ValueError as e:
                        print(f"Warning: Using current time instead - {e}")
                
                # Create price history object
                price_history = PriceHistory(
                    catalog_id=catalog_id,
                    merchant=merchant,
                    price=price,
                    currency=currency,
                    in_stock=in_stock,
                    timestamp=timestamp
                )
                
                # Add to database - using add_price which is the correct method in both database implementations
                db.add_price(price_history)
                count += 1
                
                if count % 100 == 0:
                    print(f"Imported {count} price records...")
                
            except Exception as e:
                print(f"Error processing row: {e}")
                skipped += 1
    
    print(f"\nImport complete. Imported {count} price records. Skipped {skipped} records.")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Import price history from CSV file.')
    parser.add_argument('csv_file', help='Path to CSV file with price history data')
    args = parser.parse_args()
    
    import_price_history(args.csv_file)

if __name__ == "__main__":
    main() 