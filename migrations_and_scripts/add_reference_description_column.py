"""
Script to add the reference_product_description column to the competitors table
"""
import os
import logging
import sys
from dotenv import load_dotenv
from sqlalchemy import text

# Add project root to sys.path to allow importing db and utils
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

def add_reference_description_column():
    """Add reference_product_description column to competitors table"""
    # Load environment variables from .env file
    load_dotenv()

    # Initialize logging
    logger = configure_logger(__name__)
    logger.info("Adding reference_product_description column to competitors table")

    try:
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL database...")
        postgres_db = PostgreSQLDatabase()

        # Create a session
        session = postgres_db.Session()

        try:
            # Check if column already exists
            check_sql = text("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='competitors' AND column_name='reference_product_description')")
            result = session.execute(check_sql).scalar()

            if result:
                logger.info("reference_product_description column already exists in competitors table")
                return True

            # Add the column
            alter_sql = text("ALTER TABLE competitors ADD COLUMN reference_product_description TEXT")
            session.execute(alter_sql)
            session.commit()

            logger.info("✓ Successfully added reference_product_description column to competitors table")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add reference_product_description column: {e}")
            return False
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        return False

if __name__ == "__main__":
    success = add_reference_description_column()
    sys.exit(0 if success else 1) 