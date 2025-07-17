import os
import sys
import argparse
import json
import logging
from datetime import datetime

# Add project root to Python path to allow for module imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from db.postgresql import PostgreSQLDatabase
from db.models import CatalogProduct, Site
from scrapers.site_scanner import SiteScanner
from scrapers.oxylabs_client import OxylabsClient
from utils.logger import setup_main_logger, configure_logger

class DetailedSiteScanner(SiteScanner):
    """
    Extended version of SiteScanner with enhanced debugging capabilities.
    """
    
    def scan_product_with_debugging(self, product: CatalogProduct, site: Site):
        """
        Scan a product with detailed debugging output including raw API responses.
        This is an enhanced version of the scan_product method with more detailed logging.
        """
        self.logger.info(f"DEBUG MODE: Starting site scan for product {product.id} ({product.title}) on site {site.name}")
        
        try:
            self.logger.info(f"Parsing URL: {product.url}")
            self.logger.info(f"Using site: {site.name} (ID: {site.id})")
            
            # Detailed logging of oxylabs parse code
            try:
                parse_code_str = site.oxylabs_parse_code
                parse_code = json.loads(parse_code_str)
                pretty_parse_code = json.dumps(parse_code, indent=2)
                self.logger.info(f"Using parse code:\n{pretty_parse_code}")
            except Exception as e:
                self.logger.warning(f"Could not format parse code for logging: {e}")
            
            # Call the Oxylabs API with detailed response logging
            self.logger.info("Making request to Oxylabs API...")
            try:
                # Make the API call
                scraped_data = self.oxylabs.scrape_direct_website(product.url, site.oxylabs_parse_code)
                
                # Save full response to logs directory with detailed filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"debug_site_scrape_{site.name.replace(' ', '_')}_{product.id}_{timestamp}.json"
                filepath = os.path.join(self.logs_dir, filename)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(scraped_data, f, indent=2, ensure_ascii=False)
                
                self.logger.info(f"Raw API response saved to: {filepath}")
                
                # Log response content
                self.logger.info("API Response Overview:")
                if 'results' in scraped_data and scraped_data['results']:
                    result = scraped_data['results'][0]
                    self.logger.info(f"Status: {result.get('status_code')} {result.get('status_message', '')}")
                    self.logger.info(f"Content Type: {result.get('content_type', 'unknown')}")
                    
                    # Parse and log content structure 
                    content = result.get('content', {})
                    content_keys = content.keys() if isinstance(content, dict) else []
                    self.logger.info(f"Content keys: {list(content_keys)}")
                    
                    # Log extracted values
                    if 'price' in content:
                        self.logger.info(f"Extracted price: {content['price']}")
                    if 'list_price' in content:
                        self.logger.info(f"Extracted list price: {content['list_price']}")
                    if 'SKU' in content:
                        self.logger.info(f"Extracted SKU: {content['SKU']}")
                else:
                    self.logger.warning("No results in API response")
                
                # Process the results
                self.logger.info("Processing scraped product data...")
                result = self._process_scraped_product(scraped_data, product, site)
                self.logger.info(f"Processing result: {json.dumps(result, indent=2)}")
                
                return result
                
            except Exception as e:
                self.logger.error(f"Error during site scraping: {str(e)}", exc_info=True)
                return {"created_prices": [], "updated_products": [], "errors": [{"product_id": product.id, "error": str(e)}]}
                
        except Exception as e:
            self.logger.error(f"Critical error in test_site_scanner: {str(e)}", exc_info=True)
            return {"created_prices": [], "updated_products": [], "errors": [{"product_id": product.id, "error": str(e)}]}


def get_product_and_site(db: PostgreSQLDatabase, product_id: str, site_id: str = None):
    """
    Get a product and site based on their IDs.
    
    Args:
        db: Database connection
        product_id: ID of the catalog product
        site_id: Optional ID of the site to use. If not provided, the script will
                attempt to find a site linked to the product (less reliable).
    
    Returns:
        Tuple of (product, site) or (None, None) if not found
    """
    logger = configure_logger('test_site_scanner')
    
    # Get the product
    session = db.Session()
    try:
        # First, get catalog product DB entry
        from db.postgresql import CatalogProductDB, SiteDB
        product_db = session.query(CatalogProductDB).filter(CatalogProductDB.id == product_id).first()
        
        if not product_db:
            logger.error(f"Product with ID {product_id} not found in database")
            return None, None
            
        # Convert to Pydantic model
        product = CatalogProduct(
            id=product_db.id,
            title=product_db.title,
            url=product_db.link,
            sku=product_db.sku,
            brand=product_db.brand,
            source_type=product_db.source_type,
            review_count=product_db.review_count,
            position=product_db.position,
            last_checked=product_db.last_checked,
            created_at=product_db.created_at,
            updated_at=product_db.updated_at
        )
        
        # If site_id is provided, use it directly
        if site_id:
            site_db = session.query(SiteDB).filter(SiteDB.id == site_id).first()
            
            if not site_db:
                logger.error(f"Site with ID {site_id} not found in database")
                return product, None
                
            # Convert to Pydantic model
            site = Site(
                id=site_db.id,
                name=site_db.name,
                base_url=site_db.base_url,
                oxylabs_parse_code=site_db.oxylabs_parse_code,
                active=site_db.active,
                created_at=site_db.created_at,
                updated_at=site_db.updated_at
            )
            
            return product, site
        
        # If no site_id provided, try to get site from first active site in database
        # This is a fallback and less reliable than providing a specific site_id
        logger.warning("No site_id provided, using first active site from database")
        site_db = session.query(SiteDB).filter(SiteDB.active == True).first()
        
        if not site_db:
            logger.error("No active sites found in database")
            return product, None
            
        # Convert to Pydantic model
        site = Site(
            id=site_db.id,
            name=site_db.name,
            base_url=site_db.base_url,
            oxylabs_parse_code=site_db.oxylabs_parse_code,
            active=site_db.active,
            created_at=site_db.created_at,
            updated_at=site_db.updated_at
        )
        
        logger.info(f"Using site {site.name} (ID: {site.id}) as fallback")
        return product, site
        
    except Exception as e:
        logger.error(f"Error getting product and site: {e}", exc_info=True)
        return None, None
    finally:
        session.close()


def run_test_scan(catalog_id: str, site_id: str = None):
    """
    Run a test scan on a specific catalog product.
    """
    # Setup detailed logging
    setup_main_logger('ecommiq_test_scanner', level=logging.DEBUG)
    logger = configure_logger('test_site_scanner')
    
    logger.info(f"Starting test scan for catalog ID: {catalog_id}")
    
    try:
        # Initialize database and Oxylabs client
        db = PostgreSQLDatabase()
        oxylabs = OxylabsClient()
        
        # Get the product and associated site
        product, site = get_product_and_site(db, catalog_id, site_id)
        
        if not product:
            logger.error(f"Could not find product with ID: {catalog_id}")
            return False
            
        if not site:
            logger.error(f"Could not find a site associated with product ID: {catalog_id}")
            logger.info("Please make sure this product is associated with a competitor that has a site_id")
            return False
            
        logger.info(f"Found product: {product.title}")
        logger.info(f"Found site: {site.name} (URL: {site.base_url})")
        
        # Initialize enhanced scanner with debugging capabilities
        scanner = DetailedSiteScanner(db, oxylabs)
        
        # Run the scan with detailed logging
        result = scanner.scan_product_with_debugging(product, site)
        
        # Log the result summary
        created_prices = len(result.get('created_prices', []))
        updated_products = len(result.get('updated_products', []))
        errors = result.get('errors', [])
        
        logger.info("=" * 50)
        logger.info(f"Test scan completed for {product.title}")
        logger.info(f"Created prices: {created_prices}")
        logger.info(f"Updated products: {updated_products}")
        
        if errors:
            logger.warning(f"Errors encountered: {len(errors)}")
            for error in errors:
                logger.warning(f"Error for product {error.get('product_id')}: {error.get('error')}")
        else:
            logger.info("No errors encountered")
            
        logger.info("=" * 50)
        
        return True
        
    except Exception as e:
        logger.error(f"Error in test scan: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test site scanner on a specific catalog product')
    parser.add_argument('catalog_id', type=str, help='ID of the catalog product to scan')
    parser.add_argument('--site-id', type=str, help='ID of the site to use for parsing the product')
    args = parser.parse_args()
    
    # Run the test
    success = run_test_scan(args.catalog_id, args.site_id)
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)
