"""
Test script to verify the search query update and search scanner behavior.
This script will:
1. Print a sample of competitor search queries before the update
2. Run the remove_brand_from_search_query script
3. Print the updated search queries
4. Test how the search scanner constructs the full query
"""
import os
import sys
import logging
from dotenv import load_dotenv

# Add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from db.postgresql import PostgreSQLDatabase
from db.models import CompetitorBrand
from scrapers.search_scanner import SearchScanner
from scrapers.oxylabs_client import OxylabsClient
from remove_brand_from_search_query import update_search_queries
from utils.logger import configure_logger

def test_search_query_update():
    """Test the search query update process and search scanner behavior"""
    # Load environment variables from .env file
    load_dotenv()
    
    # Set up console logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    # Initialize logging with explicit console output
    logger = configure_logger(__name__)
    logger.setLevel(logging.INFO)  # Explicitly set log level
    
    print("=== STARTING TEST: SEARCH QUERY UPDATE ===")
    print("This test will verify the search query update and search scanner behavior.")
    
    try:
        # Connect to PostgreSQL
        print("\n1. Connecting to PostgreSQL database...")
        db = PostgreSQLDatabase()
        session = db.Session()
        print("   Connection successful.")
        
        # Get 5 competitors as a sample
        competitors = db.get_all_competitors()[:5]
        if not competitors:
            print("ERROR: No competitors found in the database")
            return False
        
        # Print current search queries
        print("\n2. Current search queries (before update):")
        for comp in competitors:
            print(f"   ID: {comp.id}, Brand: {comp.competitor_brand}, Query: '{comp.search_query}'")
        
        # Run the update script
        print("\n3. Running the search query update script...")
        success = update_search_queries()
        if not success:
            print("ERROR: Failed to update search queries")
            return False
        
        # Get updated competitors
        updated_competitors = db.get_all_competitors()[:5]
        
        # Print updated search queries
        print("\n4. Updated search queries (after update):")
        for comp in updated_competitors:
            print(f"   ID: {comp.id}, Brand: {comp.competitor_brand}, Query: '{comp.search_query}'")
        
        # Initialize the OxylabsClient (but without making real calls)
        oxylabs = OxylabsClient()
        
        # Test the search scanner query construction
        print("\n5. Testing search scanner query construction...")
        scanner = SearchScanner(db, oxylabs)
        
        # Mock the search_google_shopping method to avoid making real API calls
        def mock_search(*args, **kwargs):
            search_query = args[0]
            print(f"   Mock search API call with query: '{search_query}'")
            return {'results': [{'content': {'results': {'organic': []}}}]}
        
        # Store the original method
        original_search = oxylabs.search_google_shopping
        
        try:
            # Replace with mock
            oxylabs.search_google_shopping = mock_search
            
            # Test with the first competitor
            if updated_competitors:
                test_competitor = updated_competitors[0]
                print(f"\n6. Testing with competitor: {test_competitor.competitor_brand}")
                print(f"   Base query: '{test_competitor.search_query}'")
                
                # This will use the mock to show the full query construction
                print("   Making test call to search scanner...")
                scanner.scan_for_competitor(test_competitor)
                print("   Test call complete.")
        finally:
            # Restore original method
            oxylabs.search_google_shopping = original_search
        
        print("\n=== TEST COMPLETED SUCCESSFULLY ===")
        return True
        
    except Exception as e:
        print(f"ERROR during test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_search_query_update()
    sys.exit(0 if success else 1) 