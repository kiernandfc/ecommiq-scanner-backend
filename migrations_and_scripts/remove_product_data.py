import argparse
import csv
import logging
import os
import sys

# Add the project root to the Python path to allow importing project modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase, CatalogProductDB, PriceHistoryDB, CompetitorCatalogMapDB
from utils.logger import configure_logger

# Configure logging
logger = configure_logger(__name__, level=logging.INFO)

def check_competitors_table_columns():
    """
    Check and print the actual columns in the competitors table.
    """
    logger.info("Checking columns in the competitors table...")
    try:
        db = PostgreSQLDatabase()
        engine = db.engine
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('competitors')]
        logger.info(f"Found columns in competitors table: {columns}")
        return columns
    except Exception as e:
        logger.error(f"Failed to check competitors table columns: {e}")
        return None

def remove_product_data(csv_file_path: str):
    """
    Reads catalog IDs from a CSV file and removes associated data from the database.

    Args:
        csv_file_path: Path to the CSV file containing catalog_ids.
                       The CSV must have a header row, and one column named 'catalog_id'.
    """
    logger.info(f"Starting product data removal process from CSV: {csv_file_path}")
    
    # Check the actual columns in the competitors table
    check_competitors_table_columns()

    try:
        db = PostgreSQLDatabase()
    except Exception as e:
        logger.error(f"Failed to initialize database connection: {e}")
        return

    catalog_ids_to_remove = []
    try:
        with open(csv_file_path, 'r', newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            if 'catalog_id' not in reader.fieldnames:
                logger.error(f"CSV file must contain a column named 'catalog_id'. Found headers: {reader.fieldnames}")
                return
            for row in reader:
                catalog_ids_to_remove.append(row['catalog_id'])
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_file_path}")
        return
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}")
        return

    if not catalog_ids_to_remove:
        logger.info("No catalog IDs found in the CSV file.")
        return

    logger.info(f"Found {len(catalog_ids_to_remove)} catalog IDs to process.")

    processed_count = 0
    error_count = 0

    for catalog_id in catalog_ids_to_remove:
        logger.info(f"Processing catalog_id: {catalog_id}")
        session = db.Session()
        try:
            # 1. Delete from PriceHistoryDB
            deleted_prices = session.query(PriceHistoryDB).filter(PriceHistoryDB.catalog_id == catalog_id).delete()
            logger.info(f"  Deleted {deleted_prices} entries from price_history for catalog_id: {catalog_id}")

            # 2. Delete from CompetitorCatalogMapDB
            deleted_mappings = session.query(CompetitorCatalogMapDB).filter(CompetitorCatalogMapDB.catalog_id == catalog_id).delete()
            logger.info(f"  Deleted {deleted_mappings} entries from competitor_catalog_map for catalog_id: {catalog_id}")

            # 3. Delete from CatalogProductDB using direct SQL to avoid ORM loading issues
            from sqlalchemy import text
            deleted_product = session.execute(
                text("DELETE FROM catalog WHERE id = :catalog_id RETURNING id"),
                {"catalog_id": catalog_id}
            ).fetchone()
            
            if deleted_product:
                logger.info(f"  Deleted entry from catalog_product for catalog_id: {catalog_id}")
            else:
                logger.warning(f"  CatalogProductDB entry not found for catalog_id: {catalog_id}")

            session.commit()
            logger.info(f"Successfully processed and committed changes for catalog_id: {catalog_id}")
            processed_count += 1
        except Exception as e:
            session.rollback()
            logger.error(f"Error processing catalog_id {catalog_id}: {e}", exc_info=True)
            error_count += 1
        finally:
            session.close()

    logger.info("Product data removal process completed.")
    logger.info(f"Successfully processed: {processed_count} catalog IDs.")
    logger.info(f"Encountered errors for: {error_count} catalog IDs.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove product data based on a CSV file of catalog IDs.")
    parser.add_argument("csv_file", help="Path to the CSV file containing catalog_ids. Must have a 'catalog_id' header.")
    
    args = parser.parse_args()
    
    # Ensure environment variables for DB connection are loaded (e.g., by sourcing a .env file before running)
    # Example: You might need to load dotenv if your PostgreSQLDatabase class relies on it and it's not handled elsewhere
    # from dotenv import load_dotenv
    # load_dotenv(os.path.join(project_root, '.env'))

    remove_product_data(args.csv_file)
