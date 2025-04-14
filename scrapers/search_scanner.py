from datetime import datetime
from typing import List

from db.models import CompetitorBrand, CatalogProduct, PriceHistory
from db.database import Database
from utils.helpers import utc_now
from .oxylabs_client import OxylabsClient

class SearchScanner:
    def __init__(self, db: Database, oxylabs: OxylabsClient):
        self.db = db
        self.oxylabs = oxylabs

    def scan_for_competitor(self, competitor: CompetitorBrand) -> List[CatalogProduct]:
        """
        Scan Google Shopping for a competitor's products
        
        Args:
            competitor: The competitor brand to scan for
            
        Returns:
            List of CatalogProduct objects that were found/updated
        """
        # Get search results from Oxylabs
        results = self.oxylabs.search_google_shopping(competitor.search_query)
        
        updated_products = []
        
        # Process organic results
        for item in results['results'][0]['content']['results']['organic']:
            # Check if this is from the competitor brand we're monitoring
            if competitor.competitor_brand.lower() not in item['merchant']['name'].lower():
                continue
                
            # Create catalog entry
            product = CatalogProduct(
                competitor_brand_id=competitor.id,
                brand=item['merchant']['name'],
                name=item['title'],
                url=item['url'],
                canonical_url=item['merchant']['url'],
                google_shopping_id=item['product_id'],
                last_checked=utc_now()
            )
            
            # Add/update in catalog
            product_id = self.db.add_or_update_catalog_product(product)
            product.id = product_id
            updated_products.append(product)
            
            # Add price history entry
            price = PriceHistory(
                catalog_id=product_id,
                price=float(item['price']),
                currency=item['currency'],
                in_stock=True if item.get('delivery') else False
            )
            self.db.add_price(price)
            
        return updated_products

    def scan_all_competitors(self) -> List[CatalogProduct]:
        """
        Scan all active competitors in the database
        
        Returns:
            List of all CatalogProduct objects that were found/updated
        """
        all_products = []
        for competitor in self.db.get_active_competitors():
            products = self.scan_for_competitor(competitor)
            all_products.extend(products)
        return all_products 