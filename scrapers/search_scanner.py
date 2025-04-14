from datetime import datetime
from typing import List
import logging

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

    def scan_for_competitor(self, competitor: CompetitorBrand) -> List[CatalogProduct]:
        """
        Scan Google Shopping for a competitor's products
        
        Args:
            competitor: The competitor brand to scan for
            
        Returns:
            List of CatalogProduct objects that were found/updated
        """
        self.logger.info(f"Scanning for competitor: {competitor.competitor_brand} with query: {competitor.search_query}")
        
        # Get search results from Oxylabs
        self.logger.debug(f"Requesting Google Shopping results via Oxylabs")
        results = self.oxylabs.search_google_shopping(f"{competitor.competitor_brand} {competitor.search_query}")
        
        self.logger.debug(f"Processing search results")
        updated_products = []
        
        # Process organic results
        organic_results = results['results'][0]['content']['results']['organic']
        self.logger.debug(f"Found {len(organic_results)} organic results")
        
        for item in organic_results:
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
                canonical_url=item['merchant']['url'],
                google_shopping_id=item['product_id'],
                last_checked=utc_now()
            )
            
            # Add/update in catalog
            self.logger.debug(f"Adding/updating product in database: {product.name}")
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
            self.logger.debug(f"Adding price history: {price.price} {price.currency}")
            self.db.add_price(price)
            
        self.logger.info(f"Scan complete for {competitor.competitor_brand}. Found {len(updated_products)} products")
        return updated_products

    def scan_all_competitors(self) -> List[CatalogProduct]:
        """
        Scan all active competitors in the database
        
        Returns:
            List of all CatalogProduct objects that were found/updated
        """
        self.logger.info("Starting scan of all active competitors")
        all_products = []
        competitors = self.db.get_active_competitors()
        self.logger.debug(f"Found {len(competitors)} active competitors to scan")
        
        for competitor in competitors:
            self.logger.debug(f"Processing competitor: {competitor.competitor_brand}")
            products = self.scan_for_competitor(competitor)
            all_products.extend(products)
            
        self.logger.info(f"Completed scan of all competitors. Total products: {len(all_products)}")
        return all_products 