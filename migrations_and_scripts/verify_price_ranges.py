#!/usr/bin/env python
"""
Script to verify that min_price and max_price columns were successfully updated
in the competitors table
"""
import os
import sys
import logging
from dotenv import load_dotenv
from sqlalchemy import text

# Add parent directory to path to import from db package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

# Configure logger
logger = configure_logger("verify_price_ranges")

# Add a console handler to ensure logs are displayed
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def verify_price_ranges():
    """
    Check if min_price and max_price columns have been populated in the competitors table
    """
    # Load environment variables
    load_dotenv()
    
    # Connect to PostgreSQL
    print("Connecting to PostgreSQL database...")
    postgres_db = PostgreSQLDatabase()
    
    # Create a session
    session = postgres_db.Session()
    
    try:
        # Count total competitors
        total_query = text("SELECT COUNT(*) FROM competitors")
        total_count = session.execute(total_query).scalar()
        print(f"Total competitors in database: {total_count}")
        
        # Count competitors with price ranges
        price_query = text("""
            SELECT COUNT(*) FROM competitors 
            WHERE min_price IS NOT NULL AND max_price IS NOT NULL
        """)
        price_count = session.execute(price_query).scalar()
        print(f"Competitors with price ranges: {price_count}")
        
        # Show percentage
        if total_count > 0:
            percentage = (price_count / total_count) * 100
            print(f"Percentage of competitors with price ranges: {percentage:.2f}%")
        
        # Show some examples
        examples_query = text("""
            SELECT reference_brand, reference_product, competitor_brand, min_price, max_price
            FROM competitors
            WHERE min_price IS NOT NULL AND max_price IS NOT NULL
            LIMIT 5
        """)
        examples = session.execute(examples_query).fetchall()
        
        if examples:
            print("\nExample competitors with price ranges:")
            for example in examples:
                print(f"  {example[0]}/{example[1]}/{example[2]}: min_price={example[3]}, max_price={example[4]}")
        else:
            print("\nNo competitors found with price ranges")
        
        return True
    except Exception as e:
        print(f"Error verifying price ranges: {e}")
        return False
    finally:
        session.close()

if __name__ == "__main__":
    verify_price_ranges()
