import os
from dotenv import load_dotenv
import argparse
from datetime import datetime

from db.database import Database
from db.models import CompetitorBrand
from scrapers.oxylabs_client import OxylabsClient
from scrapers.search_scanner import SearchScanner
from scrapers.price_updater import PriceUpdater
from utils.helpers import utc_now

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize components
    db = Database()
    oxylabs = OxylabsClient()
    scanner = SearchScanner(db, oxylabs)
    updater = PriceUpdater(db, oxylabs)
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='EcommiQ Scanner')
    parser.add_argument('--mode', choices=['scan', 'update', 'both'], default='both',
                      help='Operation mode: scan new products, update existing prices, or both')
    parser.add_argument('--hours', type=int, default=24,
                      help='Hours threshold for considering prices as stale')
    args = parser.parse_args()
    
    # Execute requested operations
    if args.mode in ['scan', 'both']:
        print(f"\n[{utc_now()}] Starting competitor product scan...")
        products = scanner.scan_all_competitors()
        print(f"Found/updated {len(products)} products")
        
    if args.mode in ['update', 'both']:
        print(f"\n[{utc_now()}] Starting price updates...")
        prices = updater.update_stale_products(args.hours)
        print(f"Updated prices for {len(prices)} products")

if __name__ == "__main__":
    main()