import os
import sys
import json
import argparse
import logging

# Add project root to Python path to allow for module imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from db.postgresql import PostgreSQLDatabase
from db.models import Site
from utils.logger import setup_main_logger, configure_logger

def update_site_parse_code(site_name: str, json_file_path: str, dry_run: bool = False) -> bool:
    """
    Update the oxylabs_parse_code for a site with the contents of a JSON file.
    
    Args:
        site_name: The name of the site to update
        json_file_path: Path to the JSON file containing the parse code
        dry_run: If True, show what would be updated without making changes
        
    Returns:
        True if successful, False otherwise
    """
    logger = configure_logger('update_site_parse_code')
    
    try:
        # Read the JSON file
        logger.info(f"Reading parse code from {json_file_path}")
        with open(json_file_path, 'r', encoding='utf-8') as f:
            parse_code = f.read()
            
        # Validate it's valid JSON
        try:
            json_obj = json.loads(parse_code)
            logger.info("Parse code is valid JSON")
        except json.JSONDecodeError as e:
            logger.error(f"The file does not contain valid JSON: {e}")
            return False
            
        # Initialize database connection
        logger.info("Connecting to the database")
        db = PostgreSQLDatabase()
        
        # Get all sites and find the one with the matching name
        all_sites = db.get_all_sites()
        matching_site = next((site for site in all_sites if site.name.lower() == site_name.lower()), None)
        
        if not matching_site:
            logger.error(f"No site found with name: {site_name}")
            logger.info(f"Available sites: {', '.join(site.name for site in all_sites)}")
            return False
            
        logger.info(f"Found site: {matching_site.name} (ID: {matching_site.id})")
        
        if dry_run:
            logger.info("DRY RUN - No changes will be made")
            logger.info(f"Would update site {matching_site.name} with new parse code")
            logger.info(f"Current parse code: {matching_site.oxylabs_parse_code}")
            logger.info(f"New parse code: {parse_code}")
            return True
            
        # Update the site's parse code
        matching_site.oxylabs_parse_code = parse_code
        success = db.update_site(matching_site)
        
        if success:
            logger.info(f"Successfully updated parse code for site: {matching_site.name}")
            return True
        else:
            logger.error(f"Failed to update parse code for site: {matching_site.name}")
            return False
            
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    # Setup logging
    setup_main_logger('ecommiq_update_site', level=logging.INFO)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Update Oxylabs parse code for a site')
    parser.add_argument('site_name', type=str, help='Name of the site to update')
    parser.add_argument('json_file', type=str, help='Path to the JSON file containing the parse code')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    args = parser.parse_args()
    
    # Run the update function
    success = update_site_parse_code(args.site_name, args.json_file, args.dry_run)
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)
