#!/usr/bin/env python
"""
Script to update min_price and max_price columns in the competitors table
using data from competitor_map.csv
"""
import os
import sys
import csv
import logging
from decimal import Decimal
from dotenv import load_dotenv
from sqlalchemy import text

# Add parent directory to path to import from db package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

# Configure logger
logger = configure_logger("update_price_ranges")

# Add a console handler to ensure logs are displayed
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def update_price_ranges(csv_file, dry_run=False):
    """
    Update min_price and max_price columns in the competitors table
    using data from the provided CSV file
    """
    # Load environment variables
    load_dotenv()
    
    # Connect to PostgreSQL
    logger.info("Connecting to PostgreSQL database...")
    postgres_db = PostgreSQLDatabase()
    
    # Create a session
    session = postgres_db.Session()
    
    try:
        # Read CSV file
        logger.info(f"Reading data from {csv_file}")
        price_ranges = {}
        updated_count = 0
        
        # Try different encodings
        encodings = ['utf-8-sig', 'latin1', 'cp1252']
        data_read = False
        
        for encoding in encodings:
            try:
                logger.info(f"Trying to read CSV with {encoding} encoding")
                with open(csv_file, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Extract key information
                        reference_brand = row['Reference Brand']
                        reference_product = row['Reference Product']
                        competitor_brand = row['Competitor Brand']
                        min_price = row.get('Min Price', None)
                        max_price = row.get('Max Price', None)
                        
                        # Skip if price ranges are not provided
                        if not min_price or not max_price:
                            continue
                        
                        # Create a unique key for this competitor mapping
                        key = (reference_brand, reference_product, competitor_brand)
                        
                        # Store the price ranges
                        price_ranges[key] = {
                            'min_price': Decimal(min_price) if min_price else None,
                            'max_price': Decimal(max_price) if max_price else None
                        }
                # If we got here without exception, we've successfully read the data
                data_read = True
                break
            except Exception as e:
                logger.warning(f"Failed to read CSV with {encoding} encoding: {e}")
                continue
        
        if not data_read:
            raise ValueError(f"Could not read CSV file with any of the attempted encodings: {encodings}")
        
        
        logger.info(f"Found {len(price_ranges)} price ranges in CSV file")
        
        # Update the database
        if dry_run:
            logger.info("[DRY RUN] Would update price ranges in the database")
            for key, prices in price_ranges.items():
                reference_brand, reference_product, competitor_brand = key
                logger.info(f"[DRY RUN] Would set {reference_brand}/{reference_product}/{competitor_brand} "
                           f"to min_price={prices['min_price']}, max_price={prices['max_price']}")
        else:
            # Update each competitor record
            for key, prices in price_ranges.items():
                reference_brand, reference_product, competitor_brand = key
                
                # Find the competitor record
                query = text("""
                    UPDATE competitors 
                    SET min_price = :min_price, max_price = :max_price
                    WHERE reference_brand = :reference_brand
                    AND reference_product = :reference_product
                    AND competitor_brand = :competitor_brand
                    RETURNING id
                """)
                
                result = session.execute(query, {
                    'min_price': prices['min_price'],
                    'max_price': prices['max_price'],
                    'reference_brand': reference_brand,
                    'reference_product': reference_product,
                    'competitor_brand': competitor_brand
                })
                
                # Check if a row was updated
                updated_ids = [row[0] for row in result]
                if updated_ids:
                    updated_count += len(updated_ids)
                    logger.info(f"Updated price ranges for {reference_brand}/{reference_product}/{competitor_brand} "
                               f"to min_price={prices['min_price']}, max_price={prices['max_price']}")
                else:
                    logger.warning(f"No competitor found for {reference_brand}/{reference_product}/{competitor_brand}")
            
            # Commit the changes
            session.commit()
            logger.info(f"Successfully updated {updated_count} competitor records with price ranges")
        
        return True
    except Exception as e:
        logger.error(f"Error updating price ranges: {e}", exc_info=True)
        session.rollback()
        return False
    finally:
        session.close()

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Update min_price and max_price columns in competitors table")
    parser.add_argument('--csv', default='competitor_map.csv', help="Path to CSV file with price ranges")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be done without making changes")
    args = parser.parse_args()
    
    csv_file = os.path.abspath(args.csv)
    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        sys.exit(1)
    
    success = update_price_ranges(csv_file, dry_run=args.dry_run)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
