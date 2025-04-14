import os
import json
from dotenv import load_dotenv
from scrapers.oxylabs_client import OxylabsClient
import logging
from utils.logger import configure_logger

def main():
    # Load environment variables
    load_dotenv()
    
    # Configure logging
    logger = configure_logger("test_oxylabs", logging.DEBUG)
    
    # Initialize Oxylabs client
    logger.info("Initializing Oxylabs client")
    oxylabs = OxylabsClient()
    
    # Test search query
    test_query = "Samsung TV"
    logger.info(f"Testing search query: {test_query}")
    
    try:
        # Execute search
        results = oxylabs.search_google_shopping(test_query)
        
        # Check if results contain expected structure
        if 'results' in results and len(results['results']) > 0:
            content = results['results'][0]['content']
            if 'results' in content and 'organic' in content['results']:
                organic = content['results']['organic']
                logger.info(f"Found {len(organic)} organic results")
                
                # Check first result for expected fields
                if len(organic) > 0:
                    first_item = organic[0]
                    logger.info("First result details:")
                    logger.info(f"Title: {first_item.get('title', 'N/A')}")
                    logger.info(f"Merchant: {first_item.get('merchant', {}).get('name', 'N/A')}")
                    logger.info(f"Price: {first_item.get('price', 'N/A')} {first_item.get('currency', 'N/A')}")
                    logger.info(f"Delivery info: {first_item.get('delivery', 'N/A')}")
                    
                    # Save full response to file for inspection
                    with open('exports/oxylabs_sample.json', 'w') as f:
                        json.dump(results, f, indent=2)
                    logger.info("Full response saved to exports/oxylabs_sample.json")
                else:
                    logger.error("No organic results found in search results")
            else:
                logger.error("Unexpected response format: missing 'results.organic' structure")
        else:
            logger.error("Unexpected response format: missing 'results' or empty results")
    
    except Exception as e:
        logger.error(f"Error testing Oxylabs API: {str(e)}")

if __name__ == "__main__":
    main() 