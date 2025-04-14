from datetime import datetime
from typing import List
import logging

from db.models import CatalogProduct, PriceHistory
from db.database import Database
from utils.helpers import utc_now
from utils.logger import configure_logger
from .oxylabs_client import OxylabsClient

class PriceUpdater:
    def __init__(self, db: Database, oxylabs: OxylabsClient):
        self.db = db
        self.oxylabs = oxylabs
        self.logger = configure_logger(f"{__name__}.PriceUpdater", logging.DEBUG)
        self.logger.debug("PriceUpdater initialized")

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
            price=float(item['price']),
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
        self.db.add_or_update_catalog_product(product)
        
        self.logger.info(f"Successfully updated price for product {product.id}: {price.price} {price.currency}")
        return price

    def update_stale_products(self, hours_threshold: int = 24) -> List[PriceHistory]:
        """
        Update prices for all products that haven't been checked recently
        
        Args:
            hours_threshold: Number of hours to consider a price check as stale
            
        Returns:
            List of new PriceHistory entries
        """
        self.logger.info(f"Starting update for stale products (threshold: {hours_threshold} hours)")
        
        products = self.db.get_products_to_update(hours_threshold)
        self.logger.debug(f"Found {len(products)} products to update")
        
        new_prices = []
        for product in products:
            try:
                self.logger.debug(f"Processing product: {product.id} - {product.name}")
                price = self.update_product_price(product)
                new_prices.append(price)
            except Exception as e:
                self.logger.error(f"Error updating price for product {product.id}: {str(e)}")
                continue
        
        self.logger.info(f"Completed price updates. Updated {len(new_prices)} products")        
        return new_prices 