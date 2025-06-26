#!/usr/bin/env python3
"""
Script for adding products to existing competitors from a catalog CSV file
"""

import os
import sys
import pandas as pd
import logging
import codecs

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.postgresql import PostgreSQLDatabase
from db.models import CatalogProduct
from utils.logger import configure_logger

# Configure logger
logger = configure_logger("add_products_to_competitors")

def load_csv_with_bom_handling(file_path):
    """Load a CSV file with proper BOM handling"""
    try:
        # First attempt - assume UTF-8 with BOM
        df = pd.read_csv(file_path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        try:
            # Second attempt - try UTF-8 without BOM
            df = pd.read_csv(file_path, encoding='utf-8')
        except UnicodeDecodeError:
            # Third attempt - try latin1 as a fallback
            df = pd.read_csv(file_path, encoding='latin1')
    
    # Convert column names to lowercase for consistency
    df.columns = [col.lower() for col in df.columns]
    return df

def lookup_competitor_by_brand_and_query(db, competitor_brand, search_query):
    """
    Look up a competitor by brand name and search query
    
    Args:
        db: Database instance
        competitor_brand: Brand name
        search_query: Search query
        
    Returns:
        Competitor ID if found, None otherwise
    """
    all_competitors = db.get_all_competitors()
    for competitor in all_competitors:
        if (competitor.competitor_brand.lower() == competitor_brand.lower() and 
            competitor.search_query.lower() == search_query.lower()):
            return competitor.id
    return None

def add_products_from_csv(catalog_map_path=None):
    """
    Add products from a catalog map CSV to existing competitors
    
    Args:
        catalog_map_path: Path to the catalog map CSV file
    """
    if catalog_map_path is None:
        catalog_map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "catalog_map_new.csv")
    
    db = PostgreSQLDatabase()
    
    products_created = 0
    products_skipped = 0
    mappings_created = 0
    
    try:
        # Load the catalog map
        logger.info(f"Loading catalog products from {os.path.basename(catalog_map_path)}...")
        catalog_df = load_csv_with_bom_handling(catalog_map_path)
        
        # Ensure required columns exist
        required_columns = ['competitor_brand', 'search_query', 'name', 'url']
        for column in required_columns:
            if column not in catalog_df.columns:
                logger.error(f"Required column '{column}' not found in catalog map. Found columns: {catalog_df.columns.tolist()}")
                return
        
        # Process each row to add products to existing competitors
        for _, row in catalog_df.iterrows():
            competitor_brand = row['competitor_brand']
            search_query = row['search_query']
            
            competitor_id = lookup_competitor_by_brand_and_query(db, competitor_brand, search_query)
            
            if not competitor_id:
                products_skipped += 1
                logger.warning(f"Competitor for brand '{row['competitor_brand']}' and query '{row['search_query']}' not found. Skipping product '{row.get('name', 'N/A')}'...")
                continue

            # Create a CatalogProduct object
            product = CatalogProduct(
                title=row['name'],
                url=row['url'],
                source_type=row.get('source_type', 'direct_website'),
                brand=row['competitor_brand']
            )
            
            # Add the product and create the mapping to its competitor
            product_id, is_new = db.add_or_update_catalog_product_with_status(product, competitor_ids=[competitor_id])
            
            if is_new:
                products_created += 1
                logger.info(f"Created catalog product '{product.title}' with ID: {product_id}")
            else:
                logger.info(f"Found existing product for '{product.title}'. Updating its mapping.")
            mappings_created += 1

    except FileNotFoundError:
        logger.error(f"Fatal: Catalog map file not found at {catalog_map_path}. Aborting.")
        return
    except KeyError as e:
        logger.error(f"A KeyError occurred while loading catalog products. This likely means a column is missing or misnamed in {os.path.basename(catalog_map_path)}. Missing key: {e}", exc_info=True)
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading catalog products: {e}", exc_info=True)
        return

    logger.info(f"--- Finished adding products to competitors. Products created: {products_created}, Products skipped: {products_skipped}, Mappings created/updated: {mappings_created} ---")

if __name__ == "__main__":
    logger.info("Starting the process to add products to existing competitors...")
    
    # Check if a custom file path is provided
    csv_path = None
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        logger.info(f"Using custom catalog map file: {csv_path}")
    
    add_products_from_csv(csv_path)
    logger.info("Process finished.")
