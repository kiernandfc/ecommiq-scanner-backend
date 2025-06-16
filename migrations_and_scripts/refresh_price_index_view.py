#!/usr/bin/env python
# Script to refresh the brand_category_competitor_reindexed_price_index view with new columns

import os
import sys
import logging
from sqlalchemy import text
from dotenv import load_dotenv

# Add parent directory to path to import from db package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

# Configure logger
logger = configure_logger("refresh_price_index_view")

# Add a console handler to ensure logs are displayed
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def refresh_price_index_view():
    """Drop and recreate the brand_category_competitor_reindexed_price_index view with new columns"""
    try:
        # Load environment variables
        load_dotenv()
        
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL database...")
        postgres_db = PostgreSQLDatabase()
        
        # Create a session
        session = postgres_db.Session()
        
        # Read the SQL file content
        sql_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                    'db', 'sql', 'brand_category_competitor_reindexed_price_index.sql')
        
        with open(sql_file_path, 'r') as f:
            sql_content = f.read()
        
        try:
            # First drop the view if it exists
            logger.info("Dropping existing view...")
            session.execute(text("DROP VIEW IF EXISTS brand_category_competitor_reindexed_price_index"))
            session.commit()
            logger.info("View dropped successfully")
            
            # Then recreate it with the new definition
            logger.info("Recreating view with new columns...")
            session.execute(text(sql_content))
            session.commit()
            logger.info("View recreated successfully with new columns")
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
        
        return True
    except Exception as e:
        logger.error(f"Error refreshing view: {e}")
        return False

if __name__ == "__main__":
    if refresh_price_index_view():
        print("Successfully updated the price index view with sum_of_weights and product_count columns")
    else:
        print("Failed to update the price index view")
