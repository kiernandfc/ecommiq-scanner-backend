from datetime import datetime
from typing import List, Dict, Any
import logging
import traceback
from tqdm import tqdm
from decimal import Decimal
import concurrent.futures
from functools import partial
from collections import defaultdict
import time
import json
import os

from db.postgresql import PostgreSQLDatabase
from db.models import CompetitorBrand, CatalogProduct, PriceHistory
from utils.helpers import utc_now
from utils.logger import configure_logger
from .oxylabs_client import OxylabsClient

class SearchScanner:
    def __init__(self, db: PostgreSQLDatabase, oxylabs: OxylabsClient, log_level=logging.INFO):
        self.db = db
        self.oxylabs = oxylabs
        # Get logger instance, using the log level passed from main.py if provided
        self.logger = configure_logger(f"{__name__}.SearchScanner", log_level)
        # self.logger.debug("SearchScanner initialized") # This will be filtered if root is INFO
        
        # Create api_logs directory if it doesn't exist
        self.logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'api_logs')
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Tracking metrics
        self.non_usd_scrapes_count = 0
        self.out_of_bounds_prices_count = 0
        self.skipped_missing_product_id_count = 0
        self.skipped_merchant_filter_count = 0

    def _dump_raw_results(self, results: Dict[str, Any], competitor: CompetitorBrand, suffix: str = "") -> None:
        """
        Dump raw scrape results to a text file in the api_logs folder
        
        Args:
            results: The raw results from Oxylabs
            competitor: The competitor brand being scraped
            suffix: Optional suffix to add to the filename
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_scrape_{competitor.competitor_brand.replace(' ', '_')}{('_' + suffix) if suffix else ''}_{timestamp}.txt"
            filepath = os.path.join(self.logs_dir, filename)
            
            self.logger.debug(f"Dumping raw scrape results to {filepath}")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                # Write competitor info
                f.write(f"Competitor: {competitor.competitor_brand}\n")
                f.write(f"Search Query: {competitor.search_query}\n")
                f.write(f"Timestamp: {timestamp}\n")
                if suffix:
                    f.write(f"Attempt: {suffix}\n")
                f.write("="*50 + "\n\n")
                
                # Write raw results
                f.write(json.dumps(results, indent=2, ensure_ascii=False))
                
            self.logger.debug(f"Successfully saved raw scrape results to {filepath}")
        except Exception as e:
            self.logger.error(f"Error dumping raw results: {str(e)}")
            self.logger.error(traceback.format_exc())
    
    def _check_all_usd_currency(self, results: Dict[str, Any]) -> bool:
        """
        Check if all products in the results have USD currency
        
        Args:
            results: The raw results from Oxylabs
            
        Returns:
            True if all products have USD currency, False otherwise
        """
        try:
            # Process organic results
            organic_results = results['results'][0]['content']['results']['organic']
            
            # Check currency for each product
            non_usd_count = 0
            for item in organic_results:
                currency = item.get('currency', '')
                if currency != 'USD':
                    non_usd_count += 1
                    self.logger.warning(f"Found non-USD currency: {currency} for product: {item.get('title', 'Unknown')}")
            
            if non_usd_count > 0:
                self.logger.warning(f"Found {non_usd_count} out of {len(organic_results)} products with non-USD currency")
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error checking currencies: {str(e)}")
            # If we can't check, assume it's not all USD
            return False
    
    def scan_for_competitor(self, competitor: CompetitorBrand) -> Dict[str, Any]:
        """
        Scan Google Shopping for a competitor's products
        
        Args:
            competitor: The competitor brand to scan for
            
        Returns:
            Dictionary with created/updated products and error information
        """
        self.logger.debug(f"Scanning for competitor: {competitor.competitor_brand} with query: {competitor.search_query}")
        
        updated_products = []
        created_products = []
        errors = []
        skipped_merchant_filter_count_run = 0
        skipped_missing_product_id_count_run = 0
        out_of_bounds_prices_count_run = 0

        try:
            # Construct full search query by appending competitor brand
            full_search_query = f"{competitor.search_query.strip()} {competitor.competitor_brand.strip()}"
            self.logger.debug(f"Using full search query: '{full_search_query}'")
            
            # Try up to 3 times to get results with USD currency
            max_attempts = 3
            attempt = 1
            results = None
            all_usd = False
            
            while attempt <= max_attempts and not all_usd:
                self.logger.debug(f"Attempt {attempt}/{max_attempts}: Requesting Google Shopping results via Oxylabs")
                results = self.oxylabs.search_google_shopping(full_search_query)
                
                # Dump raw results to a file in api_logs folder
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self._dump_raw_results(results, competitor, f"attempt_{attempt}_{timestamp}")
                
                # Check if all products have USD currency
                all_usd = self._check_all_usd_currency(results)
                
                if all_usd:
                    self.logger.debug(f"All products have USD currency on attempt {attempt}")
                    break
                else:
                    self.logger.warning(f"Found non-USD currencies on attempt {attempt}, retrying...")
                    self.non_usd_scrapes_count += 1
                    attempt += 1
            
            # If we still don't have all USD after max attempts, log error and return
            if not all_usd:
                error_msg = f"Failed to get all USD results after {max_attempts} attempts"
                self.logger.error(error_msg)
                errors.append({
                    "competitor": competitor.competitor_brand,
                    "product": None,
                    "error": error_msg,
                    "traceback": ""
                })
                return {
                    "created": created_products, 
                    "updated": updated_products, 
                    "competitor": competitor,
                    "errors": errors
                }
            
            self.logger.debug(f"Processing search results")
            
            # Process organic results
            organic_results = results['results'][0]['content']['results']['organic']
            self.logger.debug(f"Found {len(organic_results)} organic results")
            
            for item in organic_results:
                try:
                    # Skip products from filtered merchants (ebay, poshmark)
                    merchant_name = item['merchant']['name'].lower()
                    if 'ebay' in merchant_name or 'poshmark' in merchant_name:
                        self.skipped_merchant_filter_count += 1
                        skipped_merchant_filter_count_run += 1
                        continue

                    # Skip products without product_id
                    if not item.get('product_id'):
                        self.skipped_missing_product_id_count += 1
                        skipped_missing_product_id_count_run += 1
                        self.logger.debug(f"Skipping product due to missing product_id: {item.get('title', 'Unknown')}")
                        continue
                    
                    # Check if this is from the competitor brand we're monitoring
                    brand_in_merchant = competitor.competitor_brand.lower() in merchant_name
                    brand_in_title = competitor.competitor_brand.lower() in item['title'].lower()
                    
                    if not (brand_in_merchant or brand_in_title):
                        self.logger.debug(f"Skipping product, brand not found in merchant or title: {item['merchant']['name']} - {item['title']}")
                        continue
                        
                    self.logger.debug(f"Processing product: {item['title']} from {item['merchant']['name']}")
                    self.logger.debug(f"Match type: {'Merchant' if brand_in_merchant else ''}{' & ' if brand_in_merchant and brand_in_title else ''}{'Title' if brand_in_title else ''}")
                    self.logger.debug(f"Raw item data (reviews_count, pos): reviews_count={item.get('reviews_count')}, pos={item.get('pos')}")
                    
                    # Create catalog entry
                    product_review_count = item.get('reviews_count') # Extract review_count separately for logging
                    product_position = item.get('pos') # Extract position separately for logging
                    self.logger.debug(f"Extracted reviews_count for CatalogProduct: {product_review_count}")
                    self.logger.debug(f"Extracted position for CatalogProduct: {product_position}")
                    
                    product = CatalogProduct(
                        title=item['title'],
                        link=item['url'],
                        google_shopping_id=item.get('product_id'),  # Use .get() to handle missing key
                        review_count=product_review_count,
                        position=product_position,
                        last_checked=utc_now()
                    )
                    self.logger.debug(f"Created CatalogProduct object: review_count={product.review_count}, position={product.position}")
                    
                    # Add/update in catalog
                    self.logger.debug(f"Adding/updating product in database: {product.title}")
                    product_id, is_new = self.db.add_or_update_catalog_product_with_status(product, [competitor.id])
                    product.id = product_id
                    
                    if is_new:
                        created_products.append(product)
                    else:
                        updated_products.append(product)
                    
                    # Add price history entry
                    price_review_count = item.get('reviews_count') # Extract review_count separately for logging
                    price_position = item.get('pos') # Extract position separately for logging
                    self.logger.debug(f"Extracted reviews_count for PriceHistory: {price_review_count}")
                    self.logger.debug(f"Extracted position for PriceHistory: {price_position}")

                    price = PriceHistory(
                        catalog_id=product_id,
                        merchant=item['merchant']['name'],
                        price=Decimal(str(item['price'])),
                        currency=item['currency'],
                        in_stock=True if item.get('delivery') else False,
                        review_count=price_review_count,
                        position=price_position
                    )
                    self.logger.debug(f"Created PriceHistory object: review_count={price.review_count}, position={price.position}")
                    self.logger.debug(f"Adding price history: {price.price} {price.currency}")
                    
                    # Add price history
                    try:
                        price_result = self.db.add_price(price)
                        if price_result == "OUT_OF_BOUNDS":
                            self.out_of_bounds_prices_count += 1
                            out_of_bounds_prices_count_run += 1
                            self.logger.debug(f"Price out of bounds for {product.title} - incrementing counter to {self.out_of_bounds_prices_count}")
                        elif price_result:  # It's a price ID
                            self.logger.debug(f"Added price history: {price_result}")
                    except Exception as e:
                        self.logger.warning(f"Error adding price history: {e}")
                        # Don't fail the entire scan if price addition fails:
                        raise
                    
                except Exception as e:
                    error_msg = f"Error processing product {item.get('title', 'Unknown')}: {str(e)}"
                    self.logger.error(error_msg)
                    errors.append({
                        "competitor": competitor.competitor_brand,
                        "product": item.get('title', 'Unknown'),
                        "error": str(e),
                        "traceback": traceback.format_exc()
                    })
                    continue  # Continue with next product
        
        except Exception as e:
            error_msg = f"Error scanning competitor {competitor.competitor_brand}: {str(e)}"
            self.logger.error(error_msg)
            errors.append({
                "competitor": competitor.competitor_brand,
                "product": None,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
        
        self.logger.debug(f"Scan complete. Results: {len(updated_products)} u, {len(created_products)} c, {len(errors)} e || {out_of_bounds_prices_count_run} p, {skipped_merchant_filter_count_run} m, {skipped_missing_product_id_count_run} id    for {full_search_query}")
        return {
            "created": created_products, 
            "updated": updated_products, 
            "competitor": competitor,
            "errors": errors
        }

    def scan_all_competitors(self, show_progress: bool = False, max_workers: int = 5, competitor_id: str = None) -> dict:
        """
        Scan active competitors in the database, optionally filtering by competitor_id
        
        Args:
            show_progress: If True, display a progress bar instead of detailed logs
            max_workers: Maximum number of threads to use for parallel scanning
            competitor_id: Optional specific competitor ID to scan (if None, all active competitors are scanned)
            
        Returns:
            Dictionary with scan results including products created/updated and timing info
        """
        start_time = utc_now()
        if not show_progress:
            self.logger.info(f"Starting parallel scan of all active competitors with {max_workers} workers")
        
        all_created = []
        all_updated = []
        all_errors = []
        results_by_competitor = {}
        error_summary = {}
        
        try:
            competitors = self.db.get_active_competitors()
            
            # Filter to only include Google Shopping competitors (those without a site_id)
            google_shopping_competitors = [comp for comp in competitors if comp.site_id is None]
            
            # If a specific competitor_id was provided, filter to only that competitor
            if competitor_id:
                filtered_competitors = [comp for comp in google_shopping_competitors if comp.id == competitor_id]
                if not filtered_competitors:
                    if not show_progress:
                        self.logger.warning(f"No active competitor found with ID: {competitor_id}")
                    else:
                        print(f"Warning: No active competitor found with ID: {competitor_id}")
                    # Return empty results if competitor not found
                    return {
                        "created": [],
                        "updated": [],
                        "errors": [{
                            "competitor": "UNKNOWN",
                            "product": None,
                            "error": f"No active competitor found with ID: {competitor_id}",
                            "traceback": ""
                        }],
                        "error_summary": {"UNKNOWN": 1},
                        "by_reference": {},
                        "start_time": start_time,
                        "end_time": utc_now(),
                        "duration_seconds": (utc_now() - start_time).total_seconds(),
                        "total_catalog_count": self.db.get_total_catalog_count(),
                        "non_usd_scrapes_count": 0,
                        "out_of_bounds_prices_count": 0
                    }
                google_shopping_competitors = filtered_competitors
                if not show_progress:
                    self.logger.info(f"Filtering to scan only competitor with ID: {competitor_id} ({google_shopping_competitors[0].competitor_brand})")
                else:
                    print(f"Filtering to scan only competitor with ID: {competitor_id} ({google_shopping_competitors[0].competitor_brand})")
            
            if not show_progress:
                self.logger.debug(f"Found {len(competitors)} active competitors total, {len(google_shopping_competitors)} Google Shopping competitors to scan")
            else:
                print(f"Found {len(google_shopping_competitors)} Google Shopping competitors to scan with {max_workers} threads")
            
            # Use filtered competitors for scanning
            competitors = google_shopping_competitors
            
            # Get total catalog count before scan
            total_catalog_count = self.db.get_total_catalog_count()
            
            # Helper function to process competitor results and update progress
            def process_result(result, pbar=None):
                nonlocal all_created, all_updated, all_errors, results_by_competitor, error_summary
                
                competitor = result["competitor"]
                
                all_created.extend(result["created"])
                all_updated.extend(result["updated"])
                all_errors.extend(result["errors"])
                
                # Update progress bar if available
                if pbar:
                    pbar.update(1)
                    pbar.set_postfix(created=len(result["created"]), updated=len(result["updated"]))
                
                # Update error summary
                if result["errors"]:
                    error_summary[competitor.competitor_brand] = len(result["errors"])
                
                reference_key = f"{competitor.reference_brand} - {competitor.reference_product}"
                if reference_key not in results_by_competitor:
                    results_by_competitor[reference_key] = {
                        "created": 0,
                        "updated": 0,
                        "errors": 0,
                        "competitors": []
                    }
                
                results_by_competitor[reference_key]["created"] += len(result["created"])
                results_by_competitor[reference_key]["updated"] += len(result["updated"])
                results_by_competitor[reference_key]["errors"] += len(result["errors"])
                results_by_competitor[reference_key]["competitors"].append({
                    "name": competitor.competitor_brand,
                    "created": len(result["created"]),
                    "updated": len(result["updated"]),
                    "errors": len(result["errors"])
                })
                
                return result
            
            # Create progress bar if showing progress
            pbar = None
            if show_progress:
                pbar = tqdm(total=len(competitors), desc="Scanning competitors", unit="competitor")
            
            # Run scans in parallel with ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all scanning tasks to the executor
                future_to_competitor = {
                    executor.submit(self.scan_for_competitor, competitor): competitor
                    for competitor in competitors
                }
                
                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_competitor):
                    competitor = future_to_competitor[future]
                    try:
                        result = future.result()
                        process_result(result, pbar)
                    except Exception as e:
                        error_msg = f"Error in competitor scan for {competitor.competitor_brand}: {str(e)}"
                        self.logger.error(error_msg)
                        all_errors.append({
                            "competitor": competitor.competitor_brand,
                            "product": None,
                            "error": str(e),
                            "traceback": traceback.format_exc()
                        })
                        error_summary[competitor.competitor_brand] = error_summary.get(competitor.competitor_brand, 0) + 1
                        
                        # Update progress bar if available
                        if pbar:
                            pbar.update(1)
            
            # Close progress bar
            if pbar:
                pbar.close()
        except Exception as e:
            error_msg = f"Error in main scan loop: {str(e)}"
            self.logger.error(error_msg)
            all_errors.append({
                "competitor": "GLOBAL",
                "product": None,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            error_summary["GLOBAL"] = error_summary.get("GLOBAL", 0) + 1
        
        end_time = utc_now()
        duration = (end_time - start_time).total_seconds()
        
        # Format the result
        scan_result = {
            "created": all_created,
            "updated": all_updated,
            "errors": all_errors,
            "error_summary": error_summary,
            "by_reference": results_by_competitor,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration,
            "total_catalog_count": total_catalog_count,
            "non_usd_scrapes_count": self.non_usd_scrapes_count,
            "out_of_bounds_prices_count": self.out_of_bounds_prices_count
        }
        
        if not show_progress:
            self.logger.info(f"Completed parallel scan of all competitors. Created: {len(all_created)}, Updated: {len(all_updated)}, Errors: {len(all_errors)}, Duration: {duration:.2f} seconds")
        else:
            print(f"Completed scan. Created: {len(all_created)}, Updated: {len(all_updated)}, Errors: {len(all_errors)}, Duration: {duration:.2f} seconds")
            
        return scan_result 