#!/usr/bin/env python
"""
Migration script to add min_price and max_price columns to the competitors table.
These columns allow for price range filtering of products.
"""

import os
import sys
import argparse
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, Column, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from alembic.migration import MigrationContext
from alembic.operations import Operations

# Add parent directory to path to import from db package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.postgresql import CompetitorBrandDB
from utils.logger import configure_logger

# Configure logger with console output
logger = logging.getLogger("add_price_range_columns")
logger.setLevel(logging.INFO)

# Remove any existing handlers to avoid duplicates
for handler in logger.handlers[:]: 
    logger.removeHandler(handler)

# Add a console handler with a clear formatter
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Make sure the logger propagates messages
logger.propagate = True

def get_db_connection():
    """Create a database connection using environment variables from .env file"""
    # Load environment variables from .env file
    load_dotenv()
    
    db_host = os.getenv('POSTGRESQL_HOST')
    db_port = os.getenv('POSTGRESQL_PORT', '5432')
    db_name = os.getenv('POSTGRESQL_DB', 'ecommiq-scanner')
    db_user = os.getenv('POSTGRESQL_USER')
    db_password = os.getenv('POSTGRESQL_PASSWORD')
    
    if not all([db_host, db_name, db_user, db_password]):
        logger.error("Database credentials not fully configured.")
        raise ValueError("Database credentials not fully configured.")
    
    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(db_url)

def add_price_range_columns(dry_run=False):
    """Add min_price and max_price columns to the competitors table"""
    engine = get_db_connection()
    logger.info("Connected to database successfully")
    
    # Check if columns already exist
    with engine.connect() as conn:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('competitors')]
        logger.info(f"Found columns in competitors table: {columns}")
        
        if 'min_price' in columns and 'max_price' in columns:
            logger.info("Price range columns already exist in the competitors table.")
            return
        
        logger.info("Adding min_price and max_price columns to competitors table...")
        
        if dry_run:
            logger.info("[DRY RUN] Would add min_price and max_price columns to competitors table")
        else:
            # Add the columns using direct SQL execution
            if 'min_price' not in columns:
                conn.execute(text("ALTER TABLE competitors ADD COLUMN min_price NUMERIC(10,2) NULL"))
                conn.commit()
                logger.info("Added min_price column")
            
            if 'max_price' not in columns:
                conn.execute(text("ALTER TABLE competitors ADD COLUMN max_price NUMERIC(10,2) NULL"))
                conn.commit()
                logger.info("Added max_price column")
            
            logger.info("Migration completed successfully.")

def main():
    parser = argparse.ArgumentParser(description="Add price range columns to competitors table")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be done without making changes")
    args = parser.parse_args()
    
    try:
        logger.info("Starting migration to add price range columns")
        add_price_range_columns(dry_run=args.dry_run)
        logger.info("Migration completed successfully")
    except Exception as e:
        logger.error(f"Error adding price range columns: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
