"""""
Script to populate the reference_product_description column in the competitors table
based on the data in competitor_map.csv.
"""
import os
import logging
import sys
import csv
from dotenv import load_dotenv
from sqlalchemy import text, update

# Add project root to sys.path to allow importing db and utils
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase, CompetitorBrandDB
from utils.logger import configure_logger

def populate_reference_descriptions():
    """Populate reference_product_description column from competitor_map.csv"""
    # Load environment variables from .env file
    load_dotenv()

    # Initialize logging
    logger = configure_logger(__name__)
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

        # Ensure the required columns exist
        required_columns = ['Reference Brand', 'Reference Product', 'Competitor Brand', 'Reference Product Description']
        # Try opening with cp1252 encoding first, fall back to utf-8
        try:
            with open(csv_file_path, mode='r', encoding='cp1252') as file:
                reader = csv.DictReader(file)
                # Check columns again after successfully opening
                if not all(col in reader.fieldnames for col in required_columns):
                    missing = [col for col in required_columns if col not in reader.fieldnames]
                    logger.error(f"CSV file (cp1252) is missing required columns: {missing}")
                    return False
                logger.info(f"Successfully opened {csv_file_path} with cp1252 encoding.")
                process_csv_rows(session, reader, logger)
        except UnicodeDecodeError:
            logger.warning(f"Failed to decode {csv_file_path} with cp1252. Trying utf-8...")
            try:
                with open(csv_file_path, mode='r', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                     # Check columns again after successfully opening
                    if not all(col in reader.fieldnames for col in required_columns):
                        missing = [col for col in required_columns if col not in reader.fieldnames]
                        logger.error(f"CSV file (utf-8) is missing required columns: {missing}")
                        return False
                    logger.info(f"Successfully opened {csv_file_path} with utf-8 encoding.")
                    process_csv_rows(session, reader, logger)
            except UnicodeDecodeError:
                logger.error(f"Failed to decode {csv_file_path} with both cp1252 and utf-8 encodings.")
                return False
            except Exception as e:
                logger.error(f"Error reading CSV with utf-8: {e}")
                return False
        except Exception as e:
             logger.error(f"Error reading CSV with cp1252: {e}")
             return False

    except Exception as e:
        logger.error(f"Error connecting to database: {e}", exc_info=True)
        return False

def process_csv_rows(session, reader, logger):
    """Helper function to process rows from the CSV reader."""
    processed_count = 0
    updated_count = 0
    skipped_count = 0
    required_columns = ['Reference Brand', 'Reference Product', 'Competitor Brand', 'Reference Product Description']

    logger.info(f"Reading data...")
    for row in reader:
        processed_count += 1
        try:
            ref_brand = row['Reference Brand']
            ref_product = row['Reference Product']
            comp_brand = row['Competitor Brand']
            description = row['Reference Product Description']

            if not all([ref_brand, ref_product, comp_brand]):
                    logger.warning(f"Skipping row {processed_count} due to missing key information (Brand/Product/Competitor)")
                    skipped_count += 1
                    continue

            # Prepare the update statement using SQLAlchemy Core API for clarity
            stmt = (
                update(CompetitorBrandDB)
                .where(CompetitorBrandDB.reference_brand == ref_brand)
                .where(CompetitorBrandDB.reference_product == ref_product)
                .where(CompetitorBrandDB.competitor_brand == comp_brand)
                .values(reference_product_description=description)
            )

            # Execute the update
            result = session.execute(stmt)
            if result.rowcount > 0:
                updated_count += result.rowcount
                if result.rowcount > 1:
                        logger.warning(f"Updated {result.rowcount} rows for {ref_brand} - {ref_product} - {comp_brand}. Expected 1.")
            # No need to log if 0 rows were updated, as the competitor might not exist in the DB
            
            # Commit periodically to avoid holding locks for too long (e.g., every 100 rows)
            if processed_count % 100 == 0:
                session.commit()
                logger.info(f"Committed updates for {processed_count} rows processed.")
        except KeyError as e:
            logger.error(f"Skipping row {processed_count} due to missing column: {e}")
            skipped_count += 1
            continue
        except Exception as e:
            logger.error(f"Error processing row {processed_count}: {e}")
            skipped_count += 1
            session.rollback() # Rollback partial transaction for this row
            continue # Attempt to process next row

    # Final commit for any remaining changes
    session.commit()
    logger.info(f"Population complete. Processed: {processed_count}, Updated: {updated_count}, Skipped: {skipped_count}")
    return True

if __name__ == "__main__":
    success = populate_reference_descriptions()
    sys.exit(0 if success else 1) 