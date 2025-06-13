#!/usr/bin/env python
"""
Script to check if min_price and max_price columns exist in the competitors table
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import text

# Add parent directory to path to import from db package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

# Configure logger
logger = configure_logger("check_columns")
import logging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

def check_columns():
    """Check if min_price and max_price columns exist in the competitors table"""
    # Load environment variables from .env file
    load_dotenv()
    
    try:
        # Connect to PostgreSQL
        print("Connecting to PostgreSQL database...")
        logger.info("Connecting to PostgreSQL database...")
        postgres_db = PostgreSQLDatabase()
        
        # Create a session
        session = postgres_db.Session()
        
        try:
            # Check if columns exist
            check_sql = text("SELECT column_name FROM information_schema.columns WHERE table_name='competitors' ORDER BY ordinal_position")
            result = session.execute(check_sql).fetchall()
            
            columns = [row[0] for row in result]
            print(f"Columns in competitors table: {columns}")
            logger.info(f"Columns in competitors table: {columns}")
            
            if 'min_price' in columns and 'max_price' in columns:
                print("✓ min_price and max_price columns exist in the competitors table")
                logger.info("✓ min_price and max_price columns exist in the competitors table")
            else:
                print("❌ min_price and/or max_price columns DO NOT exist in the competitors table")
                logger.warning("❌ min_price and/or max_price columns DO NOT exist in the competitors table")
                if 'min_price' not in columns:
                    print("  - min_price column is missing")
                    logger.warning("  - min_price column is missing")
                if 'max_price' not in columns:
                    print("  - max_price column is missing")
                    logger.warning("  - max_price column is missing")
            
            return True
        except Exception as e:
            logger.error(f"Error checking columns: {e}")
            return False
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        return False

if __name__ == "__main__":
    check_columns()
