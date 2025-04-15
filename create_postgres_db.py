"""
Create the ecommiq-scanner database in PostgreSQL
"""
import os
import sys
import logging
import psycopg2
from dotenv import load_dotenv
from utils.logger import configure_logger

# Load environment variables
load_dotenv()

def create_database():
    """Create the database if it doesn't exist"""
    logger = configure_logger("create_db", logging.INFO)
    
    # Get connection parameters
    host = os.getenv('POSTGRESQL_HOST')
    port = os.getenv('POSTGRESQL_PORT', '5432')
    target_db = os.getenv('POSTGRESQL_DB', 'ecommiq-scanner')
    user = os.getenv('POSTGRESQL_USER')
    password = os.getenv('POSTGRESQL_PASSWORD')
    
    if not all([host, port, target_db, user, password]):
        logger.error("Missing environment variables. Make sure all PostgreSQL connection details are set in .env file.")
        return False
    
    # Connect to the default 'postgres' database first
    try:
        logger.info(f"Connecting to default 'postgres' database on {host}...")
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname="postgres",
            user=user,
            password=password
        )
        conn.autocommit = True  # Required for CREATE DATABASE
        cursor = conn.cursor()
        
        # Check if database already exists
        cursor.execute("SELECT datname FROM pg_database WHERE datname = %s", (target_db,))
        if cursor.fetchone():
            logger.info(f"Database '{target_db}' already exists.")
            cursor.close()
            conn.close()
            return True
        
        # Create database
        logger.info(f"Creating database '{target_db}'...")
        cursor.execute(f'CREATE DATABASE "{target_db}"')
        logger.info(f"✓ Database '{target_db}' created successfully!")
        
        cursor.close()
        conn.close()
        
        # Test connection to the new database
        logger.info(f"Testing connection to the new database '{target_db}'...")
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=target_db,
            user=user,
            password=password
        )
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        version = cursor.fetchone()
        logger.info(f"✓ Successfully connected to new database! Server version: {version[0]}")
        cursor.close()
        conn.close()
        
        return True
    except psycopg2.OperationalError as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return False
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        return False

if __name__ == "__main__":
    success = create_database()
    sys.exit(0 if success else 1) 