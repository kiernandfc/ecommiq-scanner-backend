"""
Script to add missing competitor entries from competitor_map.csv to the competitors table.
It will check for any missing reference_brand x reference_product x search_query x competitor_brand 
combinations and add them to the database if they don't already exist.
"""
import os
import sys
import csv
import logging
from dotenv import load_dotenv
import uuid

# Add project root to sys.path to allow importing db and utils
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase
from db.models import CompetitorBrand
from utils.logger import configure_logger, setup_main_logger

def configure_logging():
    """Set up logging properly for the script"""
    # First setup the main/root logger (this creates the handler)
    main_logger = setup_main_logger("add_missing_competitors", logging.INFO)
    
    # Then get a specific logger for our module that will propagate to the main logger
    logger = configure_logger(__name__, logging.INFO)
    
    # Ensure console output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

def add_missing_competitors():
    """Add missing competitors from competitor_map.csv to the database"""
    # Load environment variables from .env file
    load_dotenv()

    # Initialize logging
    logger = configure_logging()
    logger.info("Starting to add missing competitors from competitor_map.csv")

    csv_file_path = os.path.join(project_root, 'competitor_map.csv')
    if not os.path.exists(csv_file_path):
        logger.error(f"CSV file not found at: {csv_file_path}")
        return False

    try:
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL database...")
        postgres_db = PostgreSQLDatabase()
        logger.info("Successfully connected to database.")

        # Get all existing competitors from the database
        logger.info("Retrieving existing competitors from database...")
        existing_competitors = postgres_db.get_all_competitors()
        logger.info(f"Found {len(existing_competitors)} existing competitors in database")

        # Create a set of existing competitor combinations for easy lookup
        existing_combinations = set()
        for comp in existing_competitors:
            combination = (
                comp.reference_brand.strip(),
                comp.reference_product.strip(),
                comp.search_query.strip(),
                comp.competitor_brand.strip()
            )
            existing_combinations.add(combination)
        logger.info(f"existing_combinations: {existing_combinations}")
        # Process the CSV file
        # Try opening with cp1252 encoding first, fall back to utf-8
        logger.info("Reading competitor_map.csv...")
        csv_rows = []
        try:
            with open(csv_file_path, mode='r', encoding='cp1252') as file:
                reader = csv.DictReader(file)
                csv_rows = list(reader)
                logger.info(f"Successfully opened {csv_file_path} with cp1252 encoding.")
        except UnicodeDecodeError:
            logger.warning(f"Failed to decode {csv_file_path} with cp1252. Trying utf-8...")
            try:
                with open(csv_file_path, mode='r', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    csv_rows = list(reader)
                    logger.info(f"Successfully opened {csv_file_path} with utf-8 encoding.")
            except UnicodeDecodeError:
                logger.error(f"Failed to decode {csv_file_path} with both cp1252 and utf-8 encodings.")
                return False
            except Exception as e:
                logger.error(f"Error reading CSV with utf-8: {e}")
                return False
        except Exception as e:
             logger.error(f"Error reading CSV with cp1252: {e}")
             return False

        # Process rows and add missing competitors
        logger.info("Processing rows and adding missing competitors...")
        added_count = 0
        skipped_count = 0
        for i, row in enumerate(csv_rows):
            try:
                # Extract data from CSV row
                ref_brand = row.get('Reference Brand', '').strip()
                ref_product = row.get('Reference Product', '').strip()
                search_query = row.get('Search Query', '').strip()
                comp_brand = row.get('Competitor Brand', '').strip()
                ref_product_desc = row.get('Reference Product Description', '')

                # Skip if any required field is missing
                if not all([ref_brand, ref_product, search_query, comp_brand]):
                    logger.warning(f"Skipping row {i+1} due to missing key information (Brand/Product/Query/Competitor)")
                    skipped_count += 1
                    continue

                # Check if this combination already exists in the database
                combination = (ref_brand, ref_product, search_query, comp_brand)
                if combination in existing_combinations:
                    skipped_count += 1
                    continue

                # Create new competitor entry
                new_competitor = CompetitorBrand(
                    id=f"comp_{uuid.uuid4().hex[:8]}",
                    reference_brand=ref_brand,
                    reference_product=ref_product,
                    search_query=search_query,
                    competitor_brand=comp_brand,
                    reference_product_description=ref_product_desc,
                    active=True
                )

                # Add to database
                postgres_db.add_reference(new_competitor)
                added_count += 1
                existing_combinations.add(combination)  # Add to our set to avoid duplicates

                # Log progress periodically
                if (i + 1) % 50 == 0 or i == len(csv_rows) - 1:
                    logger.info(f"Processed {i+1}/{len(csv_rows)} rows, added {added_count} competitors so far")

            except Exception as e:
                logger.error(f"Error processing row {i+1}: {e}")
                skipped_count += 1
                continue

        logger.info(f"Finished processing all rows. Added {added_count} new competitors, skipped {skipped_count} entries")
        return True

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = add_missing_competitors()
    sys.exit(0 if success else 1) 