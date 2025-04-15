import csv
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from db.factory import get_database
from db.models import CompetitorBrand

def init_db(clear_existing=True):
    """Initialize the database with competitor brands from CSV file"""
    # Load environment variables from .env file
    load_dotenv()
    
    # Get the configured database
    db = get_database()
    
    # Path to the CSV file
    csv_path = 'competitor_map.csv'
    
    if not Path(csv_path).exists():
        print(f"Error: CSV file not found at {csv_path}")
        return
    
    # Clear existing competitor data if requested
    if clear_existing:
        # Clear tables in the correct order to avoid foreign key constraint errors
        # First clear the mapping table if it exists (for many-to-many schema)
        try:
            db.clear_tables(['mapping'])
            print("Cleared mapping table")
        except Exception as e:
            print(f"Warning: Could not clear mapping table: {e}")
        
        # Then clear prices and catalog tables before competitors
        try:
            db.clear_tables(['prices'])
            print("Cleared prices table")
        except Exception as e:
            print(f"Warning: Could not clear prices table: {e}")
            
        try:
            db.clear_tables(['catalog'])
            print("Cleared catalog table")
        except Exception as e:
            print(f"Warning: Could not clear catalog table: {e}")
            
        # Finally clear competitors table
        try:
            db.clear_tables(['competitors'])
            print("Cleared competitors table")
        except Exception as e:
            print(f"Warning: Could not clear competitors table: {e}")
    
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