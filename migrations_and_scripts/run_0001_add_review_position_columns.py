import os
import sys
import logging
from sqlalchemy import text

# Add project root to Python path to allow importing db module
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

try:
    from db.postgresql import PostgreSQLDatabase
    from utils.logger import configure_logger
except ImportError as e:
    print(f"Error importing modules. Make sure the script is run from the project root or the path is set correctly: {e}")
    sys.exit(1)

# Configure logging
logger = configure_logger(__name__, logging.INFO)

# --- Migration SQL ---
SQL_ADD_COLUMNS_CATALOG = """
ALTER TABLE catalog
ADD COLUMN IF NOT EXISTS review_count INTEGER,
ADD COLUMN IF NOT EXISTS position INTEGER;
"""

SQL_ADD_COLUMNS_PRICES = """
ALTER TABLE prices
ADD COLUMN IF NOT EXISTS review_count INTEGER,
ADD COLUMN IF NOT EXISTS position INTEGER;
"""

def apply_migration():
    """Connects to the database and applies the migration SQL."""
    db = None
    try:
        logger.info("Attempting to connect to the database...")
        db = PostgreSQLDatabase()
        logger.info("Database connection established.")

        logger.info("Applying migration: Adding review_count and position to 'catalog' table...")
        with db.engine.connect() as connection:
            with connection.begin(): # Start transaction
                connection.execute(text(SQL_ADD_COLUMNS_CATALOG))
        logger.info("Successfully added columns to 'catalog' table.")

        logger.info("Applying migration: Adding review_count and position to 'prices' table...")
        with db.engine.connect() as connection:
            with connection.begin(): # Start transaction
                connection.execute(text(SQL_ADD_COLUMNS_PRICES))
        logger.info("Successfully added columns to 'prices' table.")

        logger.info("Migration 0001_add_review_position_columns applied successfully.")

    except Exception as e:
        logger.error(f"Error applying migration: {e}", exc_info=True)
        # Optionally re-raise the exception if you want the script to exit with an error code
        # raise

    finally:
        # SQLAlchemy engine handles connection closing, no explicit close needed here
        logger.info("Migration script finished.")

if __name__ == "__main__":
    logger.info("Starting migration script: 0001_add_review_position_columns")
    apply_migration() 