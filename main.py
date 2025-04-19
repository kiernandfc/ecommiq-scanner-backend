import os
from dotenv import load_dotenv
import argparse
from datetime import datetime
import logging
from tabulate import tabulate
from tqdm import tqdm

# Replace direct DynamoDB import with factory import
from db.factory import get_database
from db.models import CompetitorBrand
from scrapers.oxylabs_client import OxylabsClient
from scrapers.search_scanner import SearchScanner
from scrapers.price_updater import PriceUpdater
from utils.helpers import utc_now
from utils.logger import setup_main_logger, configure_logger

def print_scan_summary(scan_results, logger):
    """Print a detailed summary of scan results"""
    total_created = len(scan_results["created"])
    total_updated = len(scan_results["updated"])
    total_errors = len(scan_results["errors"])
    duration = scan_results["duration_seconds"]
    
    # Overall summary
    logger.info("\n" + "="*60)
    logger.info(f"SCAN SUMMARY")
    logger.info("="*60)
    logger.info(f"Total products created: {total_created}")
    logger.info(f"Total products updated: {total_updated}")
    logger.info(f"Total products processed: {total_created + total_updated}")
    logger.info(f"Total errors encountered: {total_errors}")
    logger.info(f"Total scan duration: {duration:.2f} seconds")
    
    # Reference product breakdown
    reference_table = []
    
    for ref, data in scan_results["by_reference"].items():
        reference_table.append([
            ref,
            data["created"],
            data["updated"],
            data["created"] + data["updated"],
            data.get("errors", 0)
        ])
    
    if reference_table:
        logger.info("\n" + "="*60)
        logger.info("RESULTS BY REFERENCE PRODUCT")
        logger.info("="*60)
        logger.info("\n" + tabulate(
            reference_table,
            headers=["Reference", "Created", "Updated", "Total", "Errors"],
            tablefmt="grid"
        ))
    
    # Detailed competitor breakdown
    competitor_table = []
    
    for ref, data in scan_results["by_reference"].items():
        for comp in data["competitors"]:
            if comp["created"] > 0 or comp["updated"] > 0 or comp.get("errors", 0) > 0:  # Only show competitors with results or errors
                competitor_table.append([
                    ref,
                    comp["name"],
                    comp["created"],
                    comp["updated"],
                    comp["created"] + comp["updated"],
                    comp.get("errors", 0)
                ])
    
    if competitor_table:
        logger.info("\n" + "="*60)
        logger.info("DETAILED COMPETITOR RESULTS")
        logger.info("="*60)
        logger.info("\n" + tabulate(
            competitor_table,
            headers=["Reference", "Competitor", "Created", "Updated", "Total", "Errors"],
            tablefmt="grid"
        ))
    
    # Error summary
    if total_errors > 0:
        logger.info("\n" + "="*60)
        logger.info("ERROR SUMMARY")
        logger.info("="*60)
        
        # Error count by competitor
        error_summary_table = []
        for competitor, count in scan_results["error_summary"].items():
            error_summary_table.append([competitor, count])
            
        logger.info("\n" + tabulate(
            error_summary_table,
            headers=["Competitor", "Error Count"],
            tablefmt="grid"
        ))
        
        # Detailed error listing (limited to first 10)
        if scan_results["errors"]:
            logger.info("\nDETAILED ERRORS (first 10):")
            for i, error in enumerate(scan_results["errors"][:10]):
                logger.info(f"\nError {i+1}:")
                logger.info(f"Competitor: {error['competitor']}")
                if error['product']:
                    logger.info(f"Product: {error['product']}")
                logger.info(f"Error: {error['error']}")
                # Only include first 5 lines of traceback for brevity
                if error['traceback']:
                    tb_lines = error['traceback'].split('\n')[:5]
                    logger.info(f"Traceback: \n{''.join(tb_lines)}")
            
            if len(scan_results["errors"]) > 10:
                logger.info(f"\n... and {len(scan_results['errors']) - 10} more errors (see log file for details)")
    
    logger.info("="*60)

def print_price_update_summary(update_results, logger):
    """Print a detailed summary of price update results"""
    total_updated = len(update_results["updated_prices"])
    total_errors = len(update_results["errors"])
    duration = update_results["duration_seconds"]
    
    # Overall summary
    logger.info("\n" + "="*60)
    logger.info(f"PRICE UPDATE SUMMARY")
    logger.info("="*60)
    logger.info(f"Total prices updated: {total_updated}")
    logger.info(f"Total errors encountered: {total_errors}")
    logger.info(f"Total update duration: {duration:.2f} seconds")
    
    # Error summary
    if total_errors > 0:
        logger.info("\n" + "="*60)
        logger.info("PRICE UPDATE ERROR SUMMARY")
        logger.info("="*60)
        
        # Error count by brand
        error_summary_table = []
        for brand, count in update_results["error_summary"].items():
            error_summary_table.append([brand, count])
            
        logger.info("\n" + tabulate(
            error_summary_table,
            headers=["Brand", "Error Count"],
            tablefmt="grid"
        ))
        
        # Detailed error listing (limited to first 10)
        if update_results["errors"]:
            logger.info("\nDETAILED ERRORS (first 10):")
            for i, error in enumerate(update_results["errors"][:10]):
                logger.info(f"\nError {i+1}:")
                if error['product_id']:
                    logger.info(f"Product: {error['product_name']} (ID: {error['product_id']})")
                else:
                    logger.info(f"Product: {error['product_name']}")
                if error['competitor_brand_id']:
                    logger.info(f"Brand ID: {error['competitor_brand_id']}")
                logger.info(f"Error: {error['error']}")
                # Only include first 5 lines of traceback for brevity
                if error['traceback']:
                    tb_lines = error['traceback'].split('\n')[:5]
                    logger.info(f"Traceback: \n{''.join(tb_lines)}")
            
            if len(update_results["errors"]) > 10:
                logger.info(f"\n... and {len(update_results['errors']) - 10} more errors (see log file for details)")
    
    logger.info("="*60)

def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize Argument Parser
    parser = argparse.ArgumentParser(description='Ecommiq Scanner: Monitor competitor prices.')
    
    # Mode arguments
    parser.add_argument('--mode', choices=['scan', 'update', 'both'], default='both',
                      help='Operation mode: scan new products, update existing prices, or both')
    parser.add_argument('--hours', type=int, default=24,
                      help='Hours threshold for considering prices as stale')
    parser.add_argument('--progress', action='store_true',
                      help='Show progress bar instead of detailed logs')
    # Add threads parameter
    parser.add_argument('--threads', type=int, default=5,
                      help='Number of threads to use for parallel processing (default: 5)')
    
    # Scheduler arguments
    parser.add_argument('--run-once', action='store_true', help='Run the scan cycle once and exit.')
    parser.add_argument('--schedule', type=str, default='0 */6 * * *', help='Cron-like schedule for running scans.')
    
    # Other arguments
    parser.add_argument('--log-level', type=str, default='INFO', help='Set logging level (DEBUG, INFO, WARNING, ERROR)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set log level
    configure_logger(args.log_level)
    logger = configure_logger(__name__)
    
    if not args.progress:
        logger.info(f"Running in mode: {args.mode}, hours threshold: {args.hours}, threads: {args.threads}, log level: {args.log_level}")
    else:
        print(f"EcommiQ Scanner - Mode: {args.mode}, Hours threshold: {args.hours}, Threads: {args.threads}")
    
    # Initialize components
    if not args.progress:
        pass
    
    # Use the factory to get the appropriate database instance
    db = get_database()
    logger.info("Database connection established.")
    
    # Initialize Oxylabs Client
    oxylabs_client = OxylabsClient()
    
    if not args.progress:
        pass
    scanner = SearchScanner(db, oxylabs_client)
    updater = PriceUpdater(db, oxylabs_client)
    
    # Execute requested operations
    if args.mode in ['scan', 'both']:
        if args.progress:
            print("Starting competitor product scan...")
        else:
            logger.info("Starting competitor product scan...")
            
        try:
            # Pass progress flag and threads value to scanner
            scan_results = scanner.scan_all_competitors(show_progress=args.progress, max_workers=args.threads)
            
            # Display comprehensive scan summary
            print_scan_summary(scan_results, logger)
            
            # Refresh materialized views after scan is complete
            if args.progress:
                print("Refreshing materialized views...")
            else:
                logger.info("Refreshing materialized views...")
                
            # Call the refresh function
            refresh_result = db.refresh_materialized_views()
            
            if refresh_result:
                if args.progress:
                    print("Materialized views refreshed successfully")
                else:
                    logger.info("Materialized views refreshed successfully")
            else:
                if args.progress:
                    print("Warning: Failed to refresh materialized views")
                else:
                    logger.warning("Failed to refresh materialized views")
                    
        except Exception as e:
            logger.error(f"Critical error in scan mode: {str(e)}")
        
    if args.mode in ['update', 'both']:
        if args.progress:
            print("Starting price updates...")
        else:
            logger.info("Starting price updates...")
            
        try:
            # Pass progress flag and threads value to updater
            update_results = updater.update_stale_products(
                hours_threshold=args.hours, 
                show_progress=args.progress,
                max_workers=args.threads
            )
            
            # Display price update summary
            print_price_update_summary(update_results, logger)
        except Exception as e:
            logger.error(f"Critical error in update mode: {str(e)}")
    
    if not args.progress:
        logger.info("EcommiQ Scanner completed successfully")
    else:
        print("EcommiQ Scanner completed successfully")

if __name__ == "__main__":
    main()