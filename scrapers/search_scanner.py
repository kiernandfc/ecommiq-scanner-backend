from datetime import datetime
from typing import List, Dict, Any
import logging
import traceback

from db.models import CompetitorBrand, CatalogProduct, PriceHistory
from db.database import Database
from utils.helpers import utc_now
from utils.logger import configure_logger
from .oxylabs_client import OxylabsClient

class SearchScanner:
    def __init__(self, db: Database, oxylabs: OxylabsClient):
        self.db = db
        self.oxylabs = oxylabs
        self.logger = configure_logger(f"{__name__}.SearchScanner", logging.DEBUG)
        self.logger.debug("SearchScanner initialized")

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
                    if competitor.competitor_brand.lower() not in item['merchant']['name'].lower():
                        self.logger.debug(f"Skipping product from non-target merchant: {item['merchant']['name']}")
                        continue
                        
                    self.logger.debug(f"Processing product: {item['title']} from {item['merchant']['name']}")
                    
                    # Create catalog entry
                    product = CatalogProduct(
                        competitor_brand_id=competitor.id,
                        brand=item['merchant']['name'],
                        name=item['title'],
                        url=item['url'],
                        canonical_url=item['merchant'].get('url'),
                        google_shopping_id=item['product_id'],
                        last_checked=utc_now()
                    )
                    
                    # Add/update in catalog
                    self.logger.debug(f"Adding/updating product in database: {product.name}")
                    product_id, is_new = self.db.add_or_update_catalog_product_with_status(product)
                    product.id = product_id
                    
                    if is_new:
                        created_products.append(product)
                    else:
                        updated_products.append(product)
                    
                    # Add price history entry
                    price = PriceHistory(
                        catalog_id=product_id,
                        price=float(item['price']),
                        currency=item['currency'],
                        in_stock=True if item.get('delivery') else False
                    )
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

    def scan_all_competitors(self) -> dict:
        """
        Scan all active competitors in the database
        
        Returns:
            Dictionary with scan results including products created/updated and timing info
        """
        start_time = utc_now()
        self.logger.info("Starting scan of all active competitors")
        
        all_created = []
        all_updated = []
        all_errors = []
        results_by_competitor = {}
        error_summary = {}
        
        try:
            competitors = self.db.get_active_competitors()
            self.logger.debug(f"Found {len(competitors)} active competitors to scan")
            
            for competitor in competitors:
                try:
                    self.logger.debug(f"Processing competitor: {competitor.competitor_brand}")
                    result = self.scan_for_competitor(competitor)
                    
                    all_created.extend(result["created"])
                    all_updated.extend(result["updated"])
                    all_errors.extend(result["errors"])
                    
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
                    
                except Exception as e:
                    error_msg = f"Error in competitor scan loop for {competitor.competitor_brand}: {str(e)}"
                    self.logger.error(error_msg)
                    all_errors.append({
                        "competitor": competitor.competitor_brand,
                        "product": None,
                        "error": str(e),
                        "traceback": traceback.format_exc()
                    })
                    error_summary[competitor.competitor_brand] = error_summary.get(competitor.competitor_brand, 0) + 1
                    continue  # Continue with next competitor
                    
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
        
        self.logger.info(f"Completed scan of all competitors. Created: {len(all_created)}, Updated: {len(all_updated)}, Errors: {len(all_errors)}, Duration: {duration:.2f} seconds")
        return scan_result 