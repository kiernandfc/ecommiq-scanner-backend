"""
Migration script to add the sites table and update the competitors table
to support direct website scraping functionality.
"""
import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import logging

# Add parent directory to path to import from project modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import configure_logger

# Configure logger
logger = configure_logger("add_site_table")

def get_db_connection():
    """Create a connection to the PostgreSQL database"""
    # Get configuration from environment variables
    db_host = os.getenv('POSTGRESQL_HOST')
    db_port = os.getenv('POSTGRESQL_PORT', '5432')
    db_name = os.getenv('POSTGRESQL_DB', 'ecommiq-scanner')
    db_user = os.getenv('POSTGRESQL_USER')
    db_password = os.getenv('POSTGRESQL_PASSWORD')
    
    if not all([db_host, db_user, db_password]):
        logger.error("Database connection parameters not found in environment variables")
        raise ValueError("Database connection not configured")
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        raise

def run_migration():
    """Run the migration to add the sites table and update the competitors table"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        logger.info("Starting migration to add sites table")
        
        # Create sites table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            base_url VARCHAR NOT NULL,
            oxylabs_parse_code VARCHAR NOT NULL,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        logger.info("Created sites table")
        
        # Add site_id column to competitors table
        cursor.execute("""
        ALTER TABLE competitors 
        ADD COLUMN IF NOT EXISTS site_id VARCHAR,
        ADD CONSTRAINT fk_site
            FOREIGN KEY (site_id)
            REFERENCES sites (id)
            ON DELETE SET NULL;
        """)
        logger.info("Added site_id column to competitors table")
        
        # Add new columns to catalog table
        cursor.execute("""
        ALTER TABLE catalog 
        ALTER COLUMN google_shopping_id DROP NOT NULL,
        ADD COLUMN IF NOT EXISTS sku VARCHAR,
        ADD COLUMN IF NOT EXISTS brand VARCHAR,
        ADD COLUMN IF NOT EXISTS source_type VARCHAR DEFAULT 'google_shopping';
        """)
        logger.info("Updated catalog table schema")
        
        # Add new columns to prices table
        cursor.execute("""
        ALTER TABLE prices 
        ADD COLUMN IF NOT EXISTS list_price FLOAT,
        ADD COLUMN IF NOT EXISTS description TEXT;
        """)
        logger.info("Updated prices table schema")
        
        logger.info("Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
