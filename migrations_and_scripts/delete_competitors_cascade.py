""""
Script to delete specified competitors and cascade the deletion 
to associated mappings, catalog items (if orphaned), and prices.
"""
import os
import logging
import sys
import csv
from dotenv import load_dotenv
from sqlalchemy import text, select, delete, exists

# Add project root to sys.path to allow importing db and utils
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase, CompetitorBrandDB, CompetitorCatalogMapDB, CatalogProductDB, PriceHistoryDB
from utils.logger import configure_logger

# Function to read competitor IDs from CSV file
def read_competitor_ids_from_csv(csv_path):
    """Read competitor IDs from a CSV file."""
    logger = configure_logger(__name__)
    logger.info(f"Reading competitor IDs from CSV file: {csv_path}")
    competitor_ids = []
    try:
        with open(csv_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Strip quotes and whitespace from ID to ensure clean values
                competitor_id = row['id'].strip('"').strip()
                competitor_ids.append(competitor_id)
        logger.info(f"Successfully read {len(competitor_ids)} competitor IDs from CSV")
        return competitor_ids
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}", exc_info=True)
        sys.exit(1)

# Read competitor IDs from CSV file
csv_path = os.path.join(os.path.dirname(__file__), 'competitors to delete.csv')
COMPETITOR_IDS_TO_DELETE = read_competitor_ids_from_csv(csv_path)

def delete_competitors_cascade():
    """Deletes specified competitors and handles related data."""
    load_dotenv()
    logger = configure_logger(__name__)
    logger.info(f"Starting deletion process for {len(COMPETITOR_IDS_TO_DELETE)} competitors.")
    logger.info(f"First few competitor IDs: {COMPETITOR_IDS_TO_DELETE[:5] if COMPETITOR_IDS_TO_DELETE else 'None'}")

    if not COMPETITOR_IDS_TO_DELETE:
        logger.warning("No competitor IDs specified for deletion. Exiting.")
        return True

    try:
        logger.info("Connecting to PostgreSQL database...")
        postgres_db = PostgreSQLDatabase()
        session = postgres_db.Session()
        logger.info("Successfully connected to database.")

        deleted_competitors = 0
        deleted_mappings = 0
        deleted_prices = 0
        deleted_catalogs = 0
        errors = 0

        try:
            for idx, competitor_id in enumerate(COMPETITOR_IDS_TO_DELETE):
                logger.info(f"[{idx+1}/{len(COMPETITOR_IDS_TO_DELETE)}] Processing competitor ID: {competitor_id}")

                # 1. Find related mappings and catalog IDs
                logger.debug(f"  Finding related mappings for competitor {competitor_id}...")
                map_select_stmt = select(CompetitorCatalogMapDB.catalog_id).where(CompetitorCatalogMapDB.competitor_id == competitor_id)
                catalog_ids_to_check = session.execute(map_select_stmt).scalars().unique().all()
                logger.debug(f"  Found {len(catalog_ids_to_check)} associated catalog IDs to check.")

                # 2. Delete the mappings for this competitor
                logger.debug(f"  Deleting mappings for competitor {competitor_id}...")
                map_delete_stmt = delete(CompetitorCatalogMapDB).where(CompetitorCatalogMapDB.competitor_id == competitor_id)
                map_result = session.execute(map_delete_stmt)
                deleted_mappings += map_result.rowcount
                logger.debug(f"  Deleted {map_result.rowcount} entries from competitor_catalog_map.")

                # 3. Handle potentially orphaned catalog items and prices
                logger.debug(f"  Checking for orphaned catalog items...")
                for cat_idx, catalog_id in enumerate(catalog_ids_to_check):
                    if cat_idx % 10 == 0 and cat_idx > 0:
                        logger.debug(f"    Processed {cat_idx}/{len(catalog_ids_to_check)} catalog IDs...")
                        
                    # Check if this catalog_id is still referenced by OTHER competitors
                    check_stmt = select(exists().where(CompetitorCatalogMapDB.catalog_id == catalog_id))
                    is_referenced = session.execute(check_stmt).scalar()
                    
                    if not is_referenced:
                        logger.info(f"  Catalog ID {catalog_id} is orphaned. Deleting associated prices and catalog entry.")
                        # Delete associated prices
                        price_delete_stmt = delete(PriceHistoryDB).where(PriceHistoryDB.catalog_id == catalog_id)
                        price_result = session.execute(price_delete_stmt)
                        deleted_prices += price_result.rowcount
                        logger.debug(f"    Deleted {price_result.rowcount} entries from prices.")
                        
                        # Delete the catalog item
                        catalog_delete_stmt = delete(CatalogProductDB).where(CatalogProductDB.id == catalog_id)
                        catalog_result = session.execute(catalog_delete_stmt)
                        deleted_catalogs += catalog_result.rowcount
                        logger.debug(f"    Deleted {catalog_result.rowcount} entry from catalog.")
                    else:
                        logger.debug(f"  Catalog ID {catalog_id} is still referenced by other competitors. Skipping deletion.")

                # 4. Delete the competitor itself
                logger.debug(f"  Deleting competitor {competitor_id}...")
                comp_delete_stmt = delete(CompetitorBrandDB).where(CompetitorBrandDB.id == competitor_id)
                comp_result = session.execute(comp_delete_stmt)
                if comp_result.rowcount == 1:
                    deleted_competitors += 1
                    logger.info(f"  Successfully deleted competitor {competitor_id}.")
                elif comp_result.rowcount == 0:
                     logger.warning(f"  Competitor {competitor_id} not found for deletion.")
                else:
                     logger.error(f"  Unexpectedly deleted {comp_result.rowcount} rows for competitor {competitor_id}.")
                     errors += 1
                
                # Progress report every 5 competitors
                if (idx + 1) % 5 == 0:
                    logger.info(f"Progress: {idx+1}/{len(COMPETITOR_IDS_TO_DELETE)} competitors processed. " 
                                f"Deleted so far: Competitors={deleted_competitors}, Mappings={deleted_mappings}, "
                                f"Prices={deleted_prices}, Catalogs={deleted_catalogs}")

            # Commit the transaction if all deletions were successful
            if errors == 0:
                logger.info("All deletions completed. Committing transaction...")
                session.commit()
                logger.info("All deletions committed successfully.")
                logger.info(f"Summary: Competitors={deleted_competitors}, Mappings={deleted_mappings}, Prices={deleted_prices}, Catalogs={deleted_catalogs}")
                return True
            else:
                logger.error(f"Encountered {errors} errors during deletion. Rolling back transaction.")
                session.rollback()
                return False

        except Exception as e:
            session.rollback()
            logger.error(f"Error during deletion process: {e}", exc_info=True)
            return False
        finally:
            session.close()
            logger.info("Database session closed.")

    except Exception as e:
        logger.error(f"Error connecting to database: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    # Configure logger early for prompt output
    logger = configure_logger(__name__)
    logger.info("Script started")
    
    # Confirmation prompt before running
    print("--- WARNING: This script will permanently delete data! ---")
    print(f"Planning to delete {len(COMPETITOR_IDS_TO_DELETE)} competitors and their associated data.")
    print("Associated catalog items and prices will ONLY be deleted if they become orphaned.")
    
    confirm = input("Type 'DELETE' to proceed, or anything else to cancel: ")
    if confirm == "DELETE":
        logger.info("User confirmed deletion. Starting process...")
        success = delete_competitors_cascade()
        logger.info(f"Script completed with status: {'Success' if success else 'Failed'}")
        sys.exit(0 if success else 1)
    else:
        logger.info("Deletion cancelled by user.")
        print("Deletion cancelled by user.")
        sys.exit(1) 