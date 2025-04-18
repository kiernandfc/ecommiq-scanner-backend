import os
import logging
from dotenv import load_dotenv
from datetime import datetime
import sys

# Add the parent directory (workspace root) to the Python path
# This allows the script to find modules in db, scrapers, utils, etc.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables
load_dotenv()

from db.models import CompetitorBrand
from db.postgresql import PostgreSQLDatabase  # Assuming PostgreSQL
from scrapers.oxylabs_client import OxylabsClient
from scrapers.search_scanner import SearchScanner
from utils.logger import setup_main_logger

# --- Configuration ---
# Option 1: Define a competitor directly
# COMPETITOR_TO_TEST = CompetitorBrand(
#     id="comp_test_123", # Optional: Provide an ID or let the DB generate one
#     reference_brand="Test Brand",
#     reference_product="Test Product",
#     competitor_brand="Competitor XYZ", # Change this to a real competitor
#     search_query="Competitor XYZ Product ABC", # Change this to a relevant query
#     active=True
# )
# Option 2: Fetch a competitor by ID from the database (replace with a valid ID)
COMPETITOR_ID_TO_FETCH = "comp_180ed0a9c8814521bd36138eb97fe086" # <--- CHANGE THIS

# --- Setup ---
# logger = configure_logger("test_single_scan", logging.DEBUG)
# Use setup_main_logger when running as a script to set the root level
logger = setup_main_logger("test_single_scan", logging.DEBUG)

def run_single_scan():
    logger.info("--- Starting Single Scan Test ---")

    # Check environment variables
    required_vars = ['POSTGRESQL_HOST', 'POSTGRESQL_USER', 'POSTGRESQL_PASSWORD', 'POSTGRESQL_DB', 'OXYLABS_USERNAME', 'OXYLABS_PASSWORD']
    # Add 'USE_IAM_AUTH' check if you use it
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please ensure your .env file is correctly configured.")
        return

    try:
        # Initialize Database
        logger.info("Initializing Database...")
        db = PostgreSQLDatabase()
        logger.info("Database initialized.")

        # Initialize Oxylabs Client
        logger.info("Initializing Oxylabs Client...")
        oxylabs = OxylabsClient()
        logger.info("Oxylabs Client initialized.")

        # Initialize Search Scanner
        logger.info("Initializing Search Scanner...")
        scanner = SearchScanner(db, oxylabs)
        logger.info("Search Scanner initialized.")

        # --- Get Competitor ---
        competitor_to_scan = None
        if 'COMPETITOR_TO_TEST' in locals():
             competitor_to_scan = COMPETITOR_TO_TEST
             # Optional: Add the test competitor to the DB if it doesn't exist
             # try:
             #     db.add_reference(competitor_to_scan)
             #     logger.info(f"Added/Ensured test competitor '{competitor_to_scan.competitor_brand}' exists in DB.")
             # except Exception as e:
             #     logger.warning(f"Could not add test competitor to DB (might already exist): {e}")
        elif COMPETITOR_ID_TO_FETCH != "your_competitor_id_here":
            logger.info(f"Fetching competitor with ID: {COMPETITOR_ID_TO_FETCH}")
            # Need a method to get a single competitor by ID in PostgreSQLDatabase
            # For now, let's get all and filter. Add a get_competitor_by_id method later if needed.
            all_competitors = db.get_all_competitors()
            competitor_to_scan = next((c for c in all_competitors if c.id == COMPETITOR_ID_TO_FETCH), None)
            if not competitor_to_scan:
                 logger.error(f"Competitor with ID {COMPETITOR_ID_TO_FETCH} not found in the database.")
                 return
            logger.info(f"Found competitor: {competitor_to_scan.competitor_brand}")
        else:
             logger.error("No competitor specified. Please configure COMPETITOR_TO_TEST or COMPETITOR_ID_TO_FETCH.")
             return

        # --- Run Scan ---
        logger.info(f"Starting scan for competitor: {competitor_to_scan.competitor_brand} (Query: '{competitor_to_scan.search_query}')...")
        scan_result = scanner.scan_for_competitor(competitor_to_scan)
        logger.info("Scan finished.")

        # --- Print Results ---
        logger.info("\n--- Scan Results ---")
        logger.info(f"Competitor: {scan_result['competitor'].competitor_brand}")
        logger.info(f"Created Products: {len(scan_result['created'])}")
        for i, product in enumerate(scan_result['created']):
            logger.info(f"  [Created {i+1}] Name: {product.name}")
            logger.info(f"              ID: {product.id}")
            logger.info(f"              Review Count: {product.review_count}")
            logger.info(f"              Position: {product.position}")
            # Fetch associated price history for this item to check its review count
            price_hist = db.get_price_history(product.id)
            if price_hist:
                logger.info(f"              Latest Price History Review Count: {price_hist[0].review_count}")
                logger.info(f"              Latest Price History Position: {price_hist[0].position}")
            else:
                 logger.info("              No price history found for this new product yet.")


        logger.info(f"Updated Products: {len(scan_result['updated'])}")
        for i, product in enumerate(scan_result['updated']):
            logger.info(f"  [Updated {i+1}] Name: {product.name}")
            logger.info(f"              ID: {product.id}")
            logger.info(f"              Review Count: {product.review_count}")
            logger.info(f"              Position: {product.position}")
            # Fetch associated price history for this item to check its review count
            price_hist = db.get_price_history(product.id)
            if price_hist:
                logger.info(f"              Latest Price History Review Count: {price_hist[0].review_count}")
                logger.info(f"              Latest Price History Position: {price_hist[0].position}")
            else:
                logger.info("              No price history found for this updated product.")


        logger.info(f"Errors: {len(scan_result['errors'])}")
        for i, error in enumerate(scan_result['errors']):
            logger.error(f"  [Error {i+1}] Competitor: {error.get('competitor', 'N/A')}, Product: {error.get('product', 'N/A')}, Error: {error.get('error', 'N/A')}")
            logger.debug(f"             Traceback: {error.get('traceback', 'N/A')}")

    except Exception as e:
        logger.error(f"An unexpected error occurred during the test: {str(e)}", exc_info=True)

    logger.info("--- Single Scan Test Finished ---")

if __name__ == "__main__":
    run_single_scan() 