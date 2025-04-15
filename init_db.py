import csv
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from db.dynamodb import DynamoDBDatabase
from db.models import CompetitorBrand

def init_db(clear_existing=True):
    """Initialize the database with competitor brands from CSV file"""
    # Load environment variables from .env file
    load_dotenv()
    
    db = DynamoDBDatabase()
    
    # Path to the CSV file
    csv_path = 'competitor_map.csv'
    
    if not Path(csv_path).exists():
        print(f"Error: CSV file not found at {csv_path}")
        return
    
    # Clear existing competitor data if requested
    if clear_existing:
        db.clear_tables(['competitors', 'catalog', 'prices'])
        print("Cleared all tables")
    
    # Read competitor data from CSV
    with open(csv_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        count = 0
        
        for row in reader:
            competitor = CompetitorBrand(
                reference_brand=row['Reference Brand'],
                reference_product=row['Reference Product'],
                competitor_brand=row['Competitor Brand'],
                search_query=f"{row['Search Query']} {row['Competitor Brand']}"
            )
            
            db.add_reference(competitor)
            count += 1
            print(f"Added competitor tracking (ID: {competitor.id}): {competitor.reference_brand} {competitor.reference_product} -> {competitor.competitor_brand}")
        
        print(f"\nSuccessfully added {count} competitor brands to monitor")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Initialize database with competitor data')
    parser.add_argument('--keep-existing', action='store_true', 
                        help='Keep existing data instead of clearing the competitors table')
    args = parser.parse_args()
    
    init_db(clear_existing=not args.keep_existing) 