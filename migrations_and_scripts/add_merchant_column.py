"""
Script to add the merchant column to the prices table
"""
import os
import logging
import sys
from dotenv import load_dotenv
from sqlalchemy import text

from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

def add_merchant_column():
    """Add merchant column to prices table"""
    # Load environment variables from .env file
    load_dotenv()

    # Initialize logging
    logger = configure_logger(__name__)
    logger.info("Adding merchant column to prices table")
    
    try:
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL database...")
        postgres_db = PostgreSQLDatabase()
        
        # Create a session
        session = postgres_db.Session()
        
        try:
            # Check if column already exists
            check_sql = text("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='prices' AND column_name='merchant')")
            result = session.execute(check_sql).scalar()
            
            if result:
                logger.info("Merchant column already exists in prices table")
                return True
            
            # Add the column
            alter_sql = text("ALTER TABLE prices ADD COLUMN merchant VARCHAR")
            session.execute(alter_sql)
            session.commit()
            
            logger.info("✓ Successfully added merchant column to prices table")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add merchant column: {e}")
            return False
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        return False

if __name__ == "__main__":
    success = add_merchant_column()
    sys.exit(0 if success else 1) 