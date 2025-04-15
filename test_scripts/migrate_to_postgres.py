"""
Migration script to move data from DynamoDB to PostgreSQL
"""
import argparse
import logging
import sys
from dotenv import load_dotenv
import os

from db.dynamodb import DynamoDBDatabase
from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

def migrate_data():
    """Migrate data from DynamoDB to PostgreSQL"""
    # Configure logging
    logger = configure_logger("data_migration", logging.INFO)
    logger.info("Starting migration from DynamoDB to PostgreSQL")
    
    # Load environment variables
    load_dotenv()
    
    # Check if PostgreSQL config is set
    if not os.getenv('POSTGRESQL_HOST'):
        logger.error("POSTGRESQL_HOST environment variable is not set in your .env file")
        logger.error("Please configure PostgreSQL connection details in your .env file:")
        logger.error("  POSTGRESQL_HOST=your-aurora-endpoint.rds.amazonaws.com")
        logger.error("  POSTGRESQL_PORT=5432")
        logger.error("  POSTGRESQL_DB=ecommiq-scanner")
        logger.error("  POSTGRESQL_USER=your_username")
        logger.error("  POSTGRESQL_PASSWORD=your_password")
        logger.error("Migration aborted.")
        return False
    
    try:
        # Original database (DynamoDB)
        logger.info("Connecting to source DynamoDB database...")
        source_db = DynamoDBDatabase()
        
        # Target database (PostgreSQL)
        logger.info("Connecting to target PostgreSQL database...")
        target_db = PostgreSQLDatabase()
        
        # Migrate competitor brands
        logger.info("Migrating competitor brands...")
        competitors = source_db.get_all_competitors()
        
        if not competitors:
            logger.warning("No competitor brands found in DynamoDB. Nothing to migrate.")
            return True
            
        competitor_count = 0
        # Track ID mapping from DynamoDB to PostgreSQL
        id_mapping = {}
        
        for competitor in competitors:
            # Save original ID before it might change
            original_id = competitor.id
            
            # Add to PostgreSQL (this might generate a new ID)
            new_id = target_db.add_reference(competitor)
            
            # Store the mapping
            id_mapping[original_id] = new_id
            
            competitor_count += 1
            logger.info(f"Migrated competitor {competitor_count}/{len(competitors)}: {competitor.reference_brand} - {competitor.competitor_brand}")
            logger.debug(f"ID mapping: {original_id} -> {new_id}")
        
        logger.info(f"✓ Migrated {competitor_count} competitor brands")
        
        # Migrate catalog products
        logger.info("Migrating catalog products...")
        catalog_count = 0
        
        for original_competitor_id, new_competitor_id in id_mapping.items():
            # Get catalog products for this competitor using original ID
            catalog_products = source_db.get_catalog_by_reference(original_competitor_id)
            
            logger.info(f"Found {len(catalog_products)} products for competitor ID {original_competitor_id}")
            
            for product in catalog_products:
                # Update the product to reference the new competitor ID
                product.competitor_brand_id = new_competitor_id
                
                # Add to PostgreSQL
                product_id = target_db.add_or_update_catalog_product(product)
                catalog_count += 1
                
                # Migrate price history for this product
                prices = source_db.get_price_history(product.id)
                price_count = 0
                
                for price in prices:
                    # Make sure price references the correct catalog product ID
                    price.catalog_id = product_id
                    target_db.add_price(price)
                    price_count += 1
                
                logger.info(f"Migrated product: {product.name if hasattr(product, 'name') else product.google_shopping_id} with {price_count} price records")
        
        logger.info(f"✓ Migrated {catalog_count} catalog products")
        logger.info("Migration completed successfully")
        return True
        
    except ValueError as e:
        # Configuration error
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your .env file and make sure all required connection parameters are set")
        return False
    except Exception as e:
        # Other error
        logger.error(f"Migration failed: {e}")
        logger.exception(e)  # Log the full stack trace
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Migrate data from DynamoDB to PostgreSQL')
    parser.add_argument('--check-only', action='store_true', 
                       help='Only check connection without migrating data')
    args = parser.parse_args()
    
    # Override environment variables for migration
    os.environ['DATABASE_TYPE'] = 'postgresql'
    
    # Load environment variables
    load_dotenv()
    
    logger = configure_logger("data_migration", logging.INFO)
    
    if args.check_only:
        logger.info("Checking PostgreSQL connection...")
        try:
            # Just initialize the database to check connection
            PostgreSQLDatabase()
            logger.info("✓ PostgreSQL connection successful")
            sys.exit(0)
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            sys.exit(1)
    else:
        success = migrate_data()
        sys.exit(0 if success else 1) 