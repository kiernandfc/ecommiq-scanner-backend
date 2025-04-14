import os
from dotenv import load_dotenv
import argparse
from datetime import datetime
import logging

from db.database import Database
from db.models import CompetitorBrand
from scrapers.oxylabs_client import OxylabsClient
from scrapers.search_scanner import SearchScanner
from scrapers.price_updater import PriceUpdater
from utils.helpers import utc_now
from utils.logger import configure_logger

def main():
    # Load environment variables
    load_dotenv()
    
    # Configure logging
    logger = configure_logger("ecommiq", logging.DEBUG)
    logger.debug("Starting EcommiQ Scanner")
    
    # Initialize components
    logger.debug("Initializing database connection")
    db = Database()
    
    logger.debug("Initializing Oxylabs client")
    oxylabs = OxylabsClient()
    
    logger.debug("Initializing scanners and updaters")
    scanner = SearchScanner(db, oxylabs)
    updater = PriceUpdater(db, oxylabs)
    
    # Parse arguments
    logger.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(description='EcommiQ Scanner')
    parser.add_argument('--mode', choices=['scan', 'update', 'both'], default='both',
                      help='Operation mode: scan new products, update existing prices, or both')
    parser.add_argument('--hours', type=int, default=24,
                      help='Hours threshold for considering prices as stale')
    args = parser.parse_args()
    logger.info(f"Running in mode: {args.mode}, hours threshold: {args.hours}")
    
    # Execute requested operations
    if args.mode in ['scan', 'both']:
        logger.info(f"Starting competitor product scan...")
        products = scanner.scan_all_competitors()
        logger.info(f"Found/updated {len(products)} products")
        
    if args.mode in ['update', 'both']:
        logger.info(f"Starting price updates...")
        prices = updater.update_stale_products(args.hours)
        logger.info(f"Updated prices for {len(prices)} products")
    
    logger.debug("EcommiQ Scanner completed successfully")

if __name__ == "__main__":
    main()