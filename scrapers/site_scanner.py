from datetime import datetime
from typing import List, Dict, Any
import logging
import traceback
from tqdm import tqdm
from decimal import Decimal
import concurrent.futures
import os
import json

from db.postgresql import PostgreSQLDatabase
from db.models import CompetitorBrand, CatalogProduct, PriceHistory, Site
from utils.helpers import utc_now
from utils.logger import configure_logger
from .oxylabs_client import OxylabsClient

class SiteScanner:
    """
    Scanner for competitors associated with specific sites (direct website scraping).
    """
    def __init__(self, db: PostgreSQLDatabase, oxylabs: OxylabsClient):
        """
        Initialize the SiteScanner.

        Args:
            db: An instance of PostgreSQLDatabase.
            oxylabs: An instance of OxylabsClient.
        """
        self.db = db
        self.oxylabs = oxylabs
        self.logger = configure_logger(f"{__name__}.SiteScanner")
        self.logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'api_logs')
        os.makedirs(self.logs_dir, exist_ok=True)

    def _dump_raw_results(self, results: Dict[str, Any], product: CatalogProduct, site: Site) -> None:
        """
        Dump raw scrape results to a text file in the api_logs folder.
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_site_scrape_{site.name.replace(' ', '_')}_{product.id}_{timestamp}.txt"
            filepath = os.path.join(self.logs_dir, filename)
            
            self.logger.info(f"Dumping raw site scrape results to {filepath}")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Site: {site.name} ({site.id})\n")
                f.write(f"Product: {product.name} ({product.id})\n")
                f.write(f"URL: {product.url}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write("="*50 + "\n\n")
                f.write(json.dumps(results, indent=2, ensure_ascii=False))
                
            self.logger.info(f"Successfully saved raw scrape results to {filepath}")
        except Exception as e:
            self.logger.error(f"Error dumping raw results for site scrape: {str(e)}")

    def _process_scraped_product(self, scraped_data: Dict[str, Any], product: CatalogProduct, site: Site) -> Dict[str, Any]:
        """
        Process the scraped data for a single product, update the database, and return results.
        """
        created_prices = []
        updated_products = []
        errors = []

        try:
            # The actual parsing logic depends heavily on the structure of the returned data from Oxylabs, 
            # which is defined by the `oxylabs_parse_code` for the site.
            # This is a generic placeholder and will likely need to be customized.
            
            results = scraped_data.get('results', [])
            if not results:
                raise ValueError("Scraped data is empty or has no 'results' key.")

            content = results[0].get('content')
            if not content:
                raise ValueError("Scraped data 'results' has no 'content'.")

            # Example: extracting a single price from a parsed structure.
            # You will need to adapt this to your actual parsing instructions.
            parsed_price = content.get('price')
            list_price = content.get('list_price')
            description = content.get('description')
            in_stock = content.get('in_stock', False)
            sku = content.get('sku')
            brand = content.get('brand')

            if parsed_price is None:
                raise ValueError("Could not find 'price' in parsed content.")

            # Update CatalogProduct
            product_updated = False
            if sku and product.sku != sku:
                product.sku = sku
                product_updated = True
            if brand and product.brand != brand:
                product.brand = brand
                product_updated = True
            
            if product_updated:
                self.db.add_or_update_catalog_product(product)
                updated_products.append(product.id)

            # Create a new PriceHistory entry
            price_entry = PriceHistory(
                catalog_id=product.id,
                merchant=site.name, # Use site name as the merchant
                price=Decimal(str(parsed_price)),
                list_price=Decimal(str(list_price)) if list_price is not None else None,
                currency="USD", # Assuming USD, might need to parse this too
                in_stock=bool(in_stock),
                description=description
            )
            price_id = self.db.add_price_history(price_entry)
            created_prices.append(price_id)

        except Exception as e:
            self.logger.error(f"Error processing scraped data for product {product.id}: {e}")
            errors.append({"product_id": product.id, "error": str(e)})
            self._dump_raw_results(scraped_data, product, site)

        return {"created_prices": created_prices, "updated_products": updated_products, "errors": errors}

    def scan_product(self, product: CatalogProduct, site: Site) -> Dict[str, Any]:
        """
        Scrape and process a single product from a direct website.
        """
        self.logger.debug(f"Scanning product '{product.name}' from URL: {product.url}")
        try:
            scraped_data = self.oxylabs.scrape_direct_website(
                url=product.url,
                parse_code=site.oxylabs_parse_code
            )
            
            if not scraped_data or not scraped_data.get('results'):
                raise ValueError("Received empty or invalid data from Oxylabs.")

            return self._process_scraped_product(scraped_data, product, site)

        except Exception as e:
            self.logger.error(f"Error in scan_product for {product.id} ({product.url}): {e}")
            return {"created_prices": [], "updated_products": [], "errors": [{"product_id": product.id, "error": str(e)}]}

    def scan_all_sites(self, show_progress: bool = False, max_workers: int = 5) -> Dict[str, Any]:
        """
        Scan all active competitors associated with a site.
        """
        start_time = utc_now()
        self.logger.info(f"Starting site scan with {max_workers} workers.")

        all_competitors = self.db.get_active_competitors()
        site_competitors = [c for c in all_competitors if c.site_id]

        if not site_competitors:
            self.logger.info("No active site-associated competitors found to scan.")
            return {"status": "no_competitors", "duration_seconds": 0}

        # Fetch all sites and create a lookup dictionary
        all_sites = self.db.get_all_sites()
        sites_by_id = {s.id: s for s in all_sites}

        # Prepare a list of all products to be scanned
        products_to_scan = []
        for competitor in site_competitors:
            site = sites_by_id.get(competitor.site_id)
            if not site or not site.active:
                continue # Skip if site not found or is inactive

            # This is a placeholder for a method we need to create
            # For now, we assume a method that gets products by competitor
            # In the next step, we will create `get_catalog_products_by_competitor`
            catalog_products = self.db.get_catalog_products_by_competitor(competitor.id)
            for product in catalog_products:
                products_to_scan.append((product, site))

        if not products_to_scan:
            self.logger.info("No catalog products found for any active site-competitors.")
            return {"status": "no_products", "duration_seconds": 0}

        self.logger.info(f"Found {len(products_to_scan)} products to scan across {len(sites_by_id)} sites.")

        # Run scans in parallel
        all_created_prices = []
        all_updated_products = []
        all_errors = []

        pbar = tqdm(total=len(products_to_scan), desc="Scanning Site Products", unit="product") if show_progress else None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_scan = {executor.submit(self.scan_product, product, site): (product, site) for product, site in products_to_scan}

            for future in concurrent.futures.as_completed(future_to_scan):
                product, site = future_to_scan[future]
                try:
                    result = future.result()
                    all_created_prices.extend(result.get('created_prices', []))
                    all_updated_products.extend(result.get('updated_products', []))
                    all_errors.extend(result.get('errors', []))
                except Exception as e:
                    self.logger.error(f"Critical error in future for product {product.id}: {e}")
                    all_errors.append({"product_id": product.id, "error": traceback.format_exc()})
                
                if pbar:
                    pbar.update(1)

        if pbar:
            pbar.close()

        end_time = utc_now()
        duration = (end_time - start_time).total_seconds()
        self.logger.info(f"Site scan finished in {duration:.2f}s. Prices Created: {len(all_created_prices)}, Products Updated: {len(all_updated_products)}, Errors: {len(all_errors)}.")

        return {
            "created_prices": all_created_prices,
            "updated_products": list(set(all_updated_products)),
            "errors": all_errors,
            "duration_seconds": duration
        }
