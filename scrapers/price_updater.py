from datetime import datetime
from typing import List, Dict, Any
import logging
import traceback
from tqdm import tqdm
from decimal import Decimal
import concurrent.futures

from db.models import CatalogProduct, PriceHistory
from db.dynamodb import DynamoDBDatabase
from utils.helpers import utc_now
from utils.logger import configure_logger
from .oxylabs_client import OxylabsClient

class PriceUpdater:
    def __init__(self, db: DynamoDBDatabase, oxylabs: OxylabsClient):
        self.db = db
        self.oxylabs = oxylabs
        # Get logger instance, level is inherited from root config set in main.py
        self.logger = configure_logger(f"{__name__}.PriceUpdater")
        # self.logger.debug("PriceUpdater initialized") # Filtered if root is INFO

    def update_product_price(self, product: CatalogProduct) -> PriceHistory:
        """
        Update price for a single catalog product
        
        Args:
            product: The catalog product to update
            
        Returns:
            The new PriceHistory entry
        """
        self.logger.debug(f"Updating price for product: {product.id} - {product.name}")
        
        # Get product details from Oxylabs
        self.logger.debug(f"Requesting product details from Oxylabs for URL: {product.url}")
        result = self.oxylabs.get_product_details(product.url)
        
        # Extract price data
        self.logger.debug("Processing product details")
        item = result['results'][0]['content']
        
        # Create price history entry
        price = PriceHistory(
            catalog_id=product.id,
            merchant=item.get('merchant', {}).get('name', product.primary_merchant),
            price=Decimal(str(item['price'])),
            currency=item['currency'],
            in_stock=True if item.get('availability') == 'in_stock' else False
        )
        
        # Add to database
        self.logger.debug(f"Adding price history: {price.price} {price.currency}")
        price_id = self.db.add_price(price)
        price.id = price_id
        
        # Update last checked timestamp
        self.logger.debug(f"Updating last_checked timestamp for product {product.id}")
        product.last_checked = utc_now()
        
        # Get all competitors for this product
        competitors = self.db.get_competitors_by_catalog(product.id)
        competitor_ids = [comp.id for comp in competitors]
        
        # Update the product with existing competitor mappings
        self.db.add_or_update_catalog_product(product, competitor_ids)
        
        self.logger.info(f"Successfully updated price for product {product.id}: {price.price} {price.currency}")
        return price

    def update_stale_products(self, hours_threshold: int = 24, show_progress: bool = False, max_workers: int = 5) -> Dict[str, Any]:
        """
        Update prices for all products that haven't been checked recently
        
        Args:
            hours_threshold: Number of hours to consider a price check as stale
            show_progress: If True, display a progress bar instead of detailed logs
            max_workers: Maximum number of threads to use for parallel updates
            
        Returns:
            Dictionary with updated prices and error information
        """
        start_time = utc_now()
        if not show_progress:
            self.logger.info(f"Starting parallel update for stale products (threshold: {hours_threshold} hours, workers: {max_workers})")
        
        new_prices = []
        errors = []
        error_summary = {}
        
        try:
            products = self.db.get_products_to_update(hours_threshold)
            if not show_progress:
                self.logger.debug(f"Found {len(products)} products to update")
            else:
                print(f"Found {len(products)} products to update with {max_workers} threads")
            
            # Create progress bar if showing progress
            pbar = None
            if show_progress:
                pbar = tqdm(total=len(products), desc="Updating prices", unit="product")
            
            # Function to process product update result and update progress
            def process_price_update(product):
                try:
                    price = self.update_product_price(product)
                    
                    # Update progress bar if available
                    if pbar:
                        short_name = (product.name[:30] + '...') if len(product.name) > 30 else product.name
                        pbar.set_description(f"Updated {short_name}")
                        pbar.set_postfix(price=f"{price.price:.2f} {price.currency}")
                        pbar.update(1)
                    
                    return {
                        "success": True,
                        "price": price,
                        "error": None
                    }
                        
                except Exception as e:
                    error_msg = f"Error updating price for product {product.id} - {product.name}: {str(e)}"
                    self.logger.error(error_msg)
                    
                    # Update progress bar if available
                    if pbar:
                        pbar.update(1)
                    
                    return {
                        "success": False,
                        "price": None,
                        "error": {
                            "product_id": product.id,
                            "product_name": product.name,
                            "competitor_brand_id": product.competitor_brand_id,
                            "error": str(e),
                            "traceback": traceback.format_exc()
                        }
                    }
            
            # Run updates in parallel with ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_results = list(executor.map(process_price_update, products))
                
                # Process all results
                for result in future_results:
                    if result["success"]:
                        new_prices.append(result["price"])
                    else:
                        error_data = result["error"]
                        errors.append(error_data)
                        # Update error summary by product brand
                        brand_key = f"Brand ID: {error_data['competitor_brand_id']}"
                        error_summary[brand_key] = error_summary.get(brand_key, 0) + 1
            
            # Close progress bar
            if pbar:
                pbar.close()
        
        except Exception as e:
            error_msg = f"Error in main price update loop: {str(e)}"
            self.logger.error(error_msg)
            errors.append({
                "product_id": None,
                "product_name": "GLOBAL",
                "competitor_brand_id": None,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            error_summary["GLOBAL"] = error_summary.get("GLOBAL", 0) + 1
        
        end_time = utc_now()
        duration = (end_time - start_time).total_seconds()
        
        if not show_progress:
            self.logger.info(f"Completed parallel price updates. Updated {len(new_prices)} products, Errors: {len(errors)}, Duration: {duration:.2f} seconds")
        else:
            print(f"Completed price updates. Updated {len(new_prices)} products, Errors: {len(errors)}, Duration: {duration:.2f} seconds")
        
        return {
            "updated_prices": new_prices,
            "errors": errors,
            "error_summary": error_summary,
            "start_time": start_time,
            "end_time": end_time,
            "duration_seconds": duration
        } 