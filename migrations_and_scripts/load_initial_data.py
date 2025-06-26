import os
import sys
import csv
import logging

# Add project root to Python path to allow for module imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from db.postgresql import PostgreSQLDatabase
from db.models import Site, CompetitorBrand, CatalogProduct
from utils.logger import configure_logger, setup_main_logger

# Configure a logger for this script
# Setup the main logger to stream to console
setup_main_logger('ecommiq_data_loader', level=logging.INFO)
logger = configure_logger('data_loader')

def load_data():
    """Main function to orchestrate the loading of data from CSV files into the database."""
    try:
        db = PostgreSQLDatabase()
        logger.info("Successfully connected to the database.")
    except Exception as e:
        logger.error(f"Failed to connect to the database: {e}")
        return

    # Define paths to the CSV files relative to the project root
    site_map_path = os.path.join(project_root, 'site_map.csv')
    competitor_map_path = os.path.join(project_root, 'competitor_map_new.csv')
    catalog_map_path = os.path.join(project_root, 'catalog_map.csv')

    # --- Step 1: Load Sites ---
    logger.info(f"--- Starting Step 1: Loading sites from {os.path.basename(site_map_path)} ---")
    sites_by_name = {}
    try:
        # Use 'utf-8-sig' to handle potential BOM at the start of the file
        with open(site_map_path, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                # Create a Site object from the CSV row
                site = Site(
                    name=row['name'],
                    base_url=row['base_url'],
                    oxylabs_parse_code=row['oxylabs_parse_code'],
                    active=True
                )
                # Add the site to the database
                site_id = db.add_site(site)
                sites_by_name[site.name] = site_id
                logger.info(f"Created site '{site.name}' with ID: {site_id}")
    except FileNotFoundError:
        logger.error(f"Fatal: Site map file not found at {site_map_path}. Aborting.")
        return
    except KeyError as e:
        logger.error(f"A KeyError occurred while loading sites. This likely means a column is missing or misnamed in {os.path.basename(site_map_path)}. Missing key: {e}", exc_info=True)
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading sites: {e}", exc_info=True)
        return
    logger.info(f"--- Finished loading {len(sites_by_name)} sites. ---\n")

    # --- Step 2: Load Competitors ---
    logger.info(f"--- Starting Step 2: Loading competitors from {os.path.basename(competitor_map_path)} ---")
    competitors_by_key = {}  # Using a tuple (brand, query) as the key
    try:
        with open(competitor_map_path, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                site_name = row.get('Site')
                site_id = sites_by_name.get(site_name)
                
                if not site_id:
                    logger.warning(f"Site '{site_name}' not found for competitor '{row['Competitor Brand']}'. Skipping this entry.")
                    continue

                # Create a CompetitorBrand object using the correct headers
                competitor = CompetitorBrand(
                    reference_brand=row['Reference Brand'],
                    reference_product=row['Reference Product'],
                    competitor_brand=row['Competitor Brand'],
                    search_query=row['Search Query'],
                    site_id=site_id,
                    active=True
                )
                # Add the competitor to the database
                competitor_id = db.add_reference(competitor)
                key = (competitor.competitor_brand, competitor.search_query)
                competitors_by_key[key] = competitor_id
                logger.info(f"Created competitor '{competitor.competitor_brand}' for site '{site_name}' with ID: {competitor_id}")
    except FileNotFoundError:
        logger.error(f"Fatal: Competitor map file not found at {competitor_map_path}. Aborting.")
        return
    except KeyError as e:
        logger.error(f"A KeyError occurred while loading competitors. This likely means a column is missing or misnamed in {os.path.basename(competitor_map_path)}. Missing key: {e}", exc_info=True)
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading competitors: {e}", exc_info=True)
        return
    logger.info(f"--- Finished loading {len(competitors_by_key)} competitors. ---\n")

    # --- Step 3: Load and Map Catalog Products ---
    logger.info(f"--- Starting Step 3: Loading catalog products from {os.path.basename(catalog_map_path)} ---")
    products_created = 0
    mappings_created = 0
    try:
        with open(catalog_map_path, mode='r', encoding='utf-8-sig') as infile:
            reader = csv.DictReader(infile)
            for row in reader:
                # Find the competitor ID using the brand and search query
                competitor_key = (row['competitor_brand'], row['search_query'])
                competitor_id = competitors_by_key.get(competitor_key)

                if not competitor_id:
                    logger.warning(f"Competitor for brand '{row['competitor_brand']}' and query '{row['search_query']}' not found. Skipping product '{row['name']}'.")
                    continue

                # Create a CatalogProduct object
                product = CatalogProduct(
                    name=row['name'],
                    url=row['url'],
                    source_type=row.get('source_type', 'direct_website'),
                    brand=row['competitor_brand']
                )
                
                # Add the product and create the mapping to its competitor
                product_id, is_new = db.add_or_update_catalog_product_with_status(product, competitor_ids=[competitor_id])
                
                if is_new:
                    products_created += 1
                    logger.info(f"Created catalog product '{product.name}' with ID: {product_id}")
                else:
                    logger.info(f"Found existing product for '{product.name}'. Updating its mapping.")
                mappings_created += 1

    except FileNotFoundError:
        logger.error(f"Fatal: Catalog map file not found at {catalog_map_path}. Aborting.")
    except KeyError as e:
        logger.error(f"A KeyError occurred while loading catalog products. This likely means a column is missing or misnamed in {os.path.basename(catalog_map_path)}. Missing key: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading catalog products: {e}", exc_info=True)

    logger.info(f"--- Finished loading catalog. Products created: {products_created}, Mappings created/updated: {mappings_created} ---")

if __name__ == "__main__":
    logger.info("Starting the data loading process...")
    load_data()
    logger.info("Data loading process finished.")
