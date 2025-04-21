"""
Script to populate the reference_product_description column in the competitors table
based on the data in competitor_map.csv.
"""
import os
import logging
import sys
import csv
from dotenv import load_dotenv
from sqlalchemy import func

# Add project root to sys.path to allow importing db and utils
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase, CompetitorBrandDB
from db.models import CompetitorBrand
from utils.logger import configure_logger, setup_main_logger

# Set up basic direct logging to stdout
logging.basicConfig(level=logging.INFO, 
                   format='[%(levelname)s] %(message)s',
                   handlers=[logging.StreamHandler(sys.stdout)])

# Use this logger throughout the script
logger = logging.getLogger(__name__)

def populate_reference_descriptions():
    """Populate reference_product_description column from competitor_map.csv"""
    # Load environment variables from .env file
    load_dotenv()
    
    logger.info("Starting population of reference_product_description column")
    
    csv_file_path = os.path.join(project_root, 'competitor_map.csv')
    if not os.path.exists(csv_file_path):
        logger.error(f"CSV file not found at: {csv_file_path}")
        return False

    try:
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL database...")
        postgres_db = PostgreSQLDatabase()
        session = postgres_db.Session()
        logger.info("Successfully connected to database.")

        # Get initial count of descriptions
        initial_count = session.query(CompetitorBrandDB).filter(
            CompetitorBrandDB.reference_product_description.isnot(None)
        ).count()
        logger.info(f"Initial count of products with descriptions: {initial_count}")

        # Process the CSV file
        try:
            with open(csv_file_path, mode='r', encoding='cp1252') as file:
                process_csv_file(file, postgres_db, session, logger)
        except UnicodeDecodeError:
            logger.warning(f"Failed to decode {csv_file_path} with cp1252. Trying utf-8...")
            try:
                with open(csv_file_path, mode='r', encoding='utf-8') as file:
                    process_csv_file(file, postgres_db, session, logger)
            except Exception as e:
                logger.error(f"Error reading CSV with utf-8: {e}")
                return False
        
        # Get final count of descriptions
        final_count = session.query(CompetitorBrandDB).filter(
            CompetitorBrandDB.reference_product_description.isnot(None)
        ).count()
        logger.info(f"Final count of products with descriptions: {final_count}")
        logger.info(f"Added {final_count - initial_count} new descriptions")
        
        return True

    except Exception as e:
        logger.error(f"Error in populate_reference_descriptions: {e}", exc_info=True)
        return False
    finally:
        # Always close the session
        if 'session' in locals():
            session.close()

def process_csv_file(file, postgres_db, session, logger):
    """Process the CSV file and update the database."""
    reader = csv.DictReader(file)
    
    # Check required columns
    required_columns = ['Reference Brand', 'Reference Product', 'Competitor Brand', 'Reference Product Description']
    if not all(col in reader.fieldnames for col in required_columns):
        missing = [col for col in required_columns if col not in reader.fieldnames]
        logger.error(f"CSV file is missing required columns: {missing}")
        return False
    
    # Process each row
    processed_count = 0
    updated_count = 0
    skipped_count = 0
    
    for row in reader:
        processed_count += 1
        try:
            ref_brand = row['Reference Brand'].strip()
            ref_product = row['Reference Product'].strip()
            comp_brand = row['Competitor Brand'].strip()
            description = row['Reference Product Description'].strip()
            
            if not all([ref_brand, ref_product, comp_brand, description]):
                logger.warning(f"Row {processed_count}: Missing required data, skipping")
                skipped_count += 1
                continue
                
            # Find the matching record with case insensitive comparison
            matches = session.query(CompetitorBrandDB).filter(
                func.lower(CompetitorBrandDB.reference_brand) == func.lower(ref_brand),
                func.lower(CompetitorBrandDB.reference_product) == func.lower(ref_product),
                func.lower(CompetitorBrandDB.competitor_brand) == func.lower(comp_brand)
            ).all()
            
            if not matches:
                logger.warning(f"Row {processed_count}: No match found for {ref_brand} - {ref_product} - {comp_brand}")
                skipped_count += 1
                continue
                
            # Update each matching record directly
            for record in matches:
                record.reference_product_description = description
                updated_count += 1
                
            # Log progress periodically
            if processed_count % 50 == 0:
                session.commit()
                logger.info(f"Processed {processed_count} rows, updated {updated_count} records so far")
                
        except Exception as e:
            logger.error(f"Error processing row {processed_count}: {e}")
            skipped_count += 1
            continue
    
    # Commit any remaining changes
    session.commit()
    logger.info(f"Processing complete. Processed {processed_count} rows, updated {updated_count} records, skipped {skipped_count} rows")
    return True

if __name__ == "__main__":
    success = populate_reference_descriptions()
    sys.exit(0 if success else 1) 