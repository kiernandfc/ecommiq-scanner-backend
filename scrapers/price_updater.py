from datetime import datetime
from typing import List

from db.models import CatalogProduct, PriceHistory
from db.database import Database
from utils.helpers import utc_now
from .oxylabs_client import OxylabsClient

class PriceUpdater:
    def __init__(self, db: Database, oxylabs: OxylabsClient):
        self.db = db
        self.oxylabs = oxylabs

    def update_product_price(self, product: CatalogProduct) -> PriceHistory:
        """
        Update price for a single catalog product
        
        Args:
            product: The catalog product to update
            
        Returns:
            The new PriceHistory entry
        """
        # Get product details from Oxylabs
        result = self.oxylabs.get_product_details(product.url)
        
        # Extract price data
        item = result['results'][0]['content']
        
        # Create price history entry
        price = PriceHistory(
            catalog_id=product.id,
            price=float(item['price']),
            currency=item['currency'],
            in_stock=True if item.get('availability') == 'in_stock' else False
        )
        
        # Add to database
        price_id = self.db.add_price(price)
        price.id = price_id
        
        # Update last checked timestamp
        product.last_checked = utc_now()
        self.db.add_or_update_catalog_product(product)
        
        return price

    def update_stale_products(self, hours_threshold: int = 24) -> List[PriceHistory]:
        """
        Update prices for all products that haven't been checked recently
        
        Args:
            hours_threshold: Number of hours to consider a price check as stale
            
        Returns:
            List of new PriceHistory entries
        """
        products = self.db.get_products_to_update(hours_threshold)
        
        new_prices = []
        for product in products:
            try:
                price = self.update_product_price(product)
                new_prices.append(price)
            except Exception as e:
                print(f"Error updating price for product {product.id}: {str(e)}")
                continue
                
        return new_prices 