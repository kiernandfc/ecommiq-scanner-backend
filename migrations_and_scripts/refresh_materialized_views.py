"""
Script to refresh all materialized views in the database in the correct order.
This can be run as a standalone operation without performing a scan.
"""
import os
import sys
import logging
from dotenv import load_dotenv

# Add project root to sys.path to allow importing db and utils
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger, setup_main_logger

def refresh_materialized_views():
    """Refresh all materialized views in the database"""
    # Load environment variables
    load_dotenv()

    # Setup logging
    main_logger = setup_main_logger("refresh_materialized_views", logging.INFO)
    logger = configure_logger(__name__, logging.INFO)
    
    # Add console handler for immediate feedback
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    logger.info("Starting materialized view refresh operation")

    try:
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL database...")
        db = PostgreSQLDatabase()
        logger.info("Successfully connected to database.")

        # Refresh materialized views
        logger.info("Refreshing materialized views...")
        success = db.refresh_materialized_views()
        
        if success:
            logger.info("All materialized views refreshed successfully.")
            return True
        else:
            logger.error("Failed to refresh materialized views.")
            return False

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = refresh_materialized_views()
    sys.exit(0 if success else 1) 