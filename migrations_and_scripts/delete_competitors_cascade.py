""""
Script to delete specified competitors and cascade the deletion 
to associated mappings, catalog items (if orphaned), and prices.
"""
import os
import logging
import sys
from dotenv import load_dotenv
from sqlalchemy import text, select, delete, exists

# Add project root to sys.path to allow importing db and utils
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase, CompetitorBrandDB, CompetitorCatalogMapDB, CatalogProductDB, PriceHistoryDB
from utils.logger import configure_logger

# --- List of Competitor IDs to Delete --- 
COMPETITOR_IDS_TO_DELETE = [
    'comp_508320e04f714d32b4025caa35ff8eb9',
    'comp_ebbfc48c5e9a490fa723191ccde68a30',
    'comp_5171c36526d9454a933c51f7d90108ae',
    'comp_d66f3dc6268c400289ee23c8792f35fb',
    'comp_3c3398e160c04eeda4a9a7b1e59de9c9',
    'comp_1f4a04d618854e6080b571f56a760964',
    'comp_3fb524cb02ca464c9a7ac20f0ce6e91e',
    'comp_9012124a423c4515a67d6b9b44ec7d65',
    'comp_6b1802e424324d4ca5b3eaf62a50884f',
    'comp_980f279036214602bfd2398fc5929b0e',
    'comp_8748b8eaddd5499ab6b77a5878d2eee0',
    'comp_0228f6e08a7e4de1b0447cb239ecfd98',
    'comp_d9f29d8a4e3b42259cbb2de1d72f32b0',
    'comp_cfcadb7ff95440cc8e7e0b121116ce79'
]
# -----------------------------------------

def delete_competitors_cascade():
    """Deletes specified competitors and handles related data."""
    load_dotenv()
    logger = configure_logger(__name__)
    logger.info(f"Starting deletion process for {len(COMPETITOR_IDS_TO_DELETE)} competitors.")

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
            for competitor_id in COMPETITOR_IDS_TO_DELETE:
                logger.info(f"Processing competitor ID: {competitor_id}")

                # 1. Find related mappings and catalog IDs
                map_select_stmt = select(CompetitorCatalogMapDB.catalog_id).where(CompetitorCatalogMapDB.competitor_id == competitor_id)
                catalog_ids_to_check = session.execute(map_select_stmt).scalars().unique().all()
                logger.debug(f"  Found {len(catalog_ids_to_check)} associated catalog IDs to check.")

                # 2. Delete the mappings for this competitor
                map_delete_stmt = delete(CompetitorCatalogMapDB).where(CompetitorCatalogMapDB.competitor_id == competitor_id)
                map_result = session.execute(map_delete_stmt)
                deleted_mappings += map_result.rowcount
                logger.debug(f"  Deleted {map_result.rowcount} entries from competitor_catalog_map.")

                # 3. Handle potentially orphaned catalog items and prices
                for catalog_id in catalog_ids_to_check:
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

            # Commit the transaction if all deletions were successful
            if errors == 0:
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
    # Confirmation prompt before running
    print("--- WARNING: This script will permanently delete data! ---")
    print(f"Planning to delete {len(COMPETITOR_IDS_TO_DELETE)} competitors and their associated data:")
    for cid in COMPETITOR_IDS_TO_DELETE:
        print(f"  - {cid}")
    print("Associated catalog items and prices will ONLY be deleted if they become orphaned.")
    
    confirm = input("Type 'DELETE' to proceed, or anything else to cancel: ")
    if confirm == "DELETE":
        logger = configure_logger(__name__) # Configure logger early for prompt output
        logger.info("User confirmed deletion.")
        success = delete_competitors_cascade()
        sys.exit(0 if success else 1)
    else:
        print("Deletion cancelled by user.")
        sys.exit(1) 