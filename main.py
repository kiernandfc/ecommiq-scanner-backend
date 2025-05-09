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
# Import for relevancy calculation
from brain.calculate_relevancy import get_products_to_score, get_batch_relevancy_scores, update_relevancy_scores, configure_logging

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
    parser.add_argument('--mode', choices=['scan', 'update', 'both'], default='scan',
                      help='Operation mode: scan new products (only scan is currently supported)')
    parser.add_argument('--progress', action='store_true',
                      help='Show progress bar instead of detailed logs')
    # Add threads parameter
    parser.add_argument('--threads', type=int, default=5,
                      help='Number of threads to use for parallel processing (default: 5)')
    
    # Other arguments
    parser.add_argument('--log-level', type=str, default='INFO', help='Set logging level (DEBUG, INFO, WARNING, ERROR)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set log level
    configure_logger(args.log_level)
    logger = configure_logger(__name__)

    # Check for unsupported modes
    if args.mode in ['update', 'both']:
        logger.error("Error: Only 'scan' mode is currently supported. The 'update' functionality is not available.")
        return
    
    if not args.progress:
        logger.info(f"Running in mode: {args.mode}, threads: {args.threads}, log level: {args.log_level}")
    else:
        print(f"EcommiQ Scanner - Mode: {args.mode}, Threads: {args.threads}")
    
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
    
    # Execute scan operation
    if args.progress:
        print("Starting competitor product scan...")
    else:
        logger.info("Starting competitor product scan...")
        
    try:
        # Pass progress flag and threads value to scanner
        scan_results = scanner.scan_all_competitors(show_progress=args.progress, max_workers=args.threads)
        
        # Display comprehensive scan summary
        print_scan_summary(scan_results, logger)
        
        # Calculate relevancy scores
        if args.progress:
            print("Calculating product relevancy scores...")
        else:
            logger.info("Calculating product relevancy scores...")
        
        # Get products that need relevancy scoring
        conn = db.get_connection() # Assuming you have a get_connection method in your db object
        products_to_score = get_products_to_score(conn, use_progress_bar=args.progress)
        total_to_evaluate = len(products_to_score)
        
        if total_to_evaluate > 0:
            if args.progress:
                print(f"Found {total_to_evaluate} products requiring relevancy calculation")
                # Configure progress bar mode in the relevancy calculator
                configure_logging(args.progress)
                
                # Initialize progress bars
                processed_products = 0
                relevancy_progress = tqdm(total=total_to_evaluate, desc="Calculating Relevancy", position=0)
            else:
                logger.info(f"Found {total_to_evaluate} products requiring relevancy calculation")
                
            # Process products by reference product
            reference_product_groups = {}
            for product in products_to_score:
                reference_key = (product['reference_product_name'], product['reference_brand'])
                if reference_key not in reference_product_groups:
                    reference_product_groups[reference_key] = []
                reference_product_groups[reference_key].append(product)
            
            all_scores = []
            high_relevancy_count = 0
            
            # Process each reference product group
            for (reference_name, reference_brand), products_group in reference_product_groups.items():
                reference_product_description = products_group[0]['reference_product_description']
                
                # Process in batches of 25
                for i in range(0, len(products_group), 25):
                    batch = products_group[i:i+25]
                    
                    # Prepare competitor data for the batch scoring function
                    competitor_data_for_batch = []
                    for product in batch:
                        competitor_data_for_batch.append({
                            'map_id': product['map_id'],
                            'competitor_product_name': product['competitor_product_name'],
                            'reference_product_name': reference_name,
                            'reference_product_description': reference_product_description
                        })
                    
                    # Call the batch scoring function with progress bar flag
                    batch_scores = get_batch_relevancy_scores(reference_brand, competitor_data_for_batch, args.progress)
                    
                    if batch_scores is not None:
                        all_scores.extend(batch_scores)
                        # Count high relevancy scores (>=7)
                        for score_item in batch_scores:
                            if score_item['score'] >= 7:
                                high_relevancy_count += 1
                        
                        # Update progress bar if enabled
                        if args.progress:
                            batch_size = len(batch_scores)
                            processed_products += batch_size
                            relevancy_progress.update(batch_size)
            
            # Close progress bar if enabled
            if args.progress:
                relevancy_progress.close()
            
            # Update database with all calculated scores
            if all_scores:
                update_relevancy_scores(conn, all_scores, args.progress)
                
                # Print relevancy summary
                print("\nRELEVANCY CALCULATION SUMMARY")
                print("=" * 30)
                print(f"Products evaluated:      {total_to_evaluate}")
                print(f"High relevancy (>=7):    {high_relevancy_count} ({(high_relevancy_count / total_to_evaluate * 100):.1f}% of evaluated)")
                print(f"Low relevancy (<7):      {total_to_evaluate - high_relevancy_count} ({((total_to_evaluate - high_relevancy_count) / total_to_evaluate * 100):.1f}% of evaluated)")
        else:
            if args.progress:
                print("No products require relevancy calculation.")
            else:
                logger.info("No products require relevancy calculation.")
        
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

        # Print percentage summary regardless of log level
        total_catalog_count = scan_results["total_catalog_count"]
        products_this_scan = len(scan_results["created"]) + len(scan_results["updated"])
        
        print("\nPRODUCT UPDATE SUMMARY")
        print("=" * 30)
        print(f"New Products:     {len(scan_results['created'])} ({(len(scan_results['created']) / total_catalog_count * 100):.1f}% of catalog)")
        print(f"Updated Products: {len(scan_results['updated'])} ({(len(scan_results['updated']) / total_catalog_count * 100):.1f}% of catalog)")
        print(f"Products Found:   {products_this_scan} ({(products_this_scan / total_catalog_count * 100):.1f}% of catalog)")
        print(f"Total in Catalog: {total_catalog_count}")
        if len(scan_results["errors"]) > 0:
            error_percent = (len(scan_results["errors"]) / total_catalog_count) * 100
            print(f"Failed Products:  {len(scan_results['errors'])} ({error_percent:.1f}% of catalog)")
                    
    except Exception as e:
        logger.error(f"Critical error in scan mode: {str(e)}")
    
    if not args.progress:
        logger.info("EcommiQ Scanner completed successfully")
    else:
        print("EcommiQ Scanner completed successfully")

if __name__ == "__main__":
    main()