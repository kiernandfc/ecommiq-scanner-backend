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

from db.postgresql import PostgreSQLDatabase
from db.models import CompetitorBrand, CatalogProduct, PriceHistory
from utils.helpers import utc_now
from utils.logger import configure_logger
from .oxylabs_client import OxylabsClient

class SearchScanner:
    def __init__(self, db: PostgreSQLDatabase, oxylabs: OxylabsClient):
        self.db = db
        self.oxylabs = oxylabs
        # Get logger instance, level is inherited from root config set in main.py
        self.logger = configure_logger(f"{__name__}.SearchScanner")
        # self.logger.debug("SearchScanner initialized") # This will be filtered if root is INFO

    def scan_for_competitor(self, competitor: CompetitorBrand) -> Dict[str, Any]:
        """
        Scan Google Shopping for a competitor's products
        
        Args:
            competitor: The competitor brand to scan for
            
        Returns:
            Dictionary with created/updated products and error information
        """
        self.logger.info(f"Scanning for competitor: {competitor.competitor_brand} with query: {competitor.search_query}")
        
        updated_products = []
        created_products = []
        errors = []
        
        try:
            # Get search results from Oxylabs
            self.logger.debug(f"Requesting Google Shopping results via Oxylabs")
            results = self.oxylabs.search_google_shopping(competitor.search_query)
            
            self.logger.debug(f"Processing search results")
            
            # Process organic results
            organic_results = results['results'][0]['content']['results']['organic']
            self.logger.debug(f"Found {len(organic_results)} organic results")
            
            for item in organic_results:
                try:
                    # Check if this is from the competitor brand we're monitoring
                    brand_in_merchant = competitor.competitor_brand.lower() in item['merchant']['name'].lower()
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
                        name=item['title'],
                        url=item['url'],
                        canonical_url=item['merchant'].get('url'),
                        google_shopping_id=item['product_id'],
                        primary_merchant=item['merchant']['name'],
                        review_count=product_review_count,
                        position=product_position,
                        last_checked=utc_now()
                    )
                    self.logger.debug(f"Created CatalogProduct object: review_count={product.review_count}, position={product.position}")
                    
                    # Add/update in catalog
                    self.logger.debug(f"Adding/updating product in database: {product.name}")
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
                    self.db.add_price(price)
                    
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
        
        self.logger.info(f"Scan complete for {competitor.competitor_brand}. Created: {len(created_products)}, Updated: {len(updated_products)}, Errors: {len(errors)}")
        return {
            "created": created_products, 
            "updated": updated_products, 
            "competitor": competitor,
            "errors": errors
        }

    def scan_all_competitors(self, show_progress: bool = False, max_workers: int = 5) -> dict:
        """
        Scan all active competitors in the database
        
        Args:
            show_progress: If True, display a progress bar instead of detailed logs
            max_workers: Maximum number of threads to use for parallel scanning
            
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
            if not show_progress:
                self.logger.debug(f"Found {len(competitors)} active competitors to scan")
            else:
                print(f"Found {len(competitors)} competitors to scan with {max_workers} threads")
            
            # Function to process competitor results and update progress
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
            "duration_seconds": duration
        }
        
        if not show_progress:
            self.logger.info(f"Completed parallel scan of all competitors. Created: {len(all_created)}, Updated: {len(all_updated)}, Errors: {len(all_errors)}, Duration: {duration:.2f} seconds")
        else:
            print(f"Completed scan. Created: {len(all_created)}, Updated: {len(all_updated)}, Errors: {len(all_errors)}, Duration: {duration:.2f} seconds")
            
        return scan_result 