import os
import sys
import asyncio
import logging
import argparse

# Add project root to Python path to allow for module imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from scrapers.site_scanner import SiteScanner
from scrapers.oxylabs_client import OxylabsClient
from db.postgresql import PostgreSQLDatabase
from utils.logger import setup_main_logger, configure_logger

def run_scanner(competitor_brand=None):
    """Initializes and runs the site scanner.
    
    Args:
        competitor_brand (str, optional): If provided, only scan products for competitors
            with this reference_brand. If None, scan all site-associated competitors.
    """
    # Setup the main logger to stream to console with DEBUG level for more verbose output
    setup_main_logger('ecommiq_site_scanner', level=logging.DEBUG)
    logger = configure_logger('run_site_scanner', level=logging.DEBUG)

    try:
        logger.info("Initializing dependencies...")
        db = PostgreSQLDatabase()
        oxylabs = OxylabsClient()
        logger.info("Dependencies initialized.")

        logger.info("Initializing SiteScanner...")
        scanner = SiteScanner(db=db, oxylabs=oxylabs)
        
        if competitor_brand:
            logger.info(f"SiteScanner initialized. Starting scan for competitor brand: {competitor_brand}...")
        else:
            logger.info("SiteScanner initialized. Starting scan of all sites...")
        
        # Call scan_all_sites with the competitor_brand filter if provided
        result = scanner.scan_all_sites(competitor_brand=competitor_brand)
        logger.info(f"Scan completed with {len(result.get('created_prices', []))} prices created, {len(result.get('updated_products', []))} products updated, and {len(result.get('errors', []))} errors.")
        
        logger.info("Site scanning process finished.")
    except Exception as e:
        logger.error(f"An error occurred during the site scanning process: {e}", exc_info=True)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run the site scanner for direct website scraping')
    parser.add_argument('--competitor-brand', type=str, help='Filter scan to only include competitors with this reference_brand')
    args = parser.parse_args()
    
    print("Running site scanner...", flush=True)
    run_scanner(competitor_brand=args.competitor_brand)
