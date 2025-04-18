import logging
import time
import re
import argparse # For command-line arguments
import csv      # For CSV output
from datetime import datetime # For timestamping CSV file

# Import necessary functions and config from the main script
# Assuming the test script is run from the project root or the path is adjusted accordingly
from brain.calculate_relevancy import (
    get_db_connection,
    get_products_to_score,
    get_batch_relevancy_scores, # Import the new batch scoring function
    BATCH_SIZE, # Import batch size for context
    # No need to import update_relevancy_scores for testing
)

# Configure logging for the test script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - TEST - %(levelname)s - %(message)s')

# --- Argument Parsing ---
def parse_arguments():
    parser = argparse.ArgumentParser(description='Test relevancy scoring script.')
    parser.add_argument('-l', '--limit', type=int, default=10, help='Maximum number of products to test.')
    parser.add_argument('-p', '--product', type=str, default=None, help='Optional reference product name to filter products by.')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    test_limit = args.limit
    target_product = args.product

    logging.info(f"Starting relevancy scoring test for up to {test_limit} products.")
    if target_product:
        logging.info(f"Filtering for reference product name: '{target_product}'")

    start_time = time.time() # Record start time
    results_data = [] # List to store results for CSV
    products_processed = 0
    products_scored = 0

    conn = get_db_connection()
    if conn:
        try:
            # 1. Fetch products needing scores
            all_products_unfiltered = get_products_to_score(conn)
            logging.info(f"Fetched {len(all_products_unfiltered)} total products needing scores.")

            # 2. Filter products if target_product is specified
            products_to_test_unlimited = []
            if target_product:
                products_to_test_unlimited = [
                    p for p in all_products_unfiltered
                    if p.get('reference_product_name') and p['reference_product_name'].lower() == target_product.lower()
                ]
                logging.info(f"Found {len(products_to_test_unlimited)} products matching reference product '{target_product}'.")
            else:
                products_to_test_unlimited = all_products_unfiltered

            # 3. Apply limit
            products_to_test = products_to_test_unlimited[:test_limit]
            logging.info(f"Processing limit: {test_limit}. Testing {len(products_to_test)} products.")

            if not products_to_test:
                logging.info("No products found matching the criteria. Exiting test.")
            else:
                # 4. Process products in batches of BATCH_SIZE
                total_to_test = len(products_to_test)
                products_processed = total_to_test # We intend to process all limited products

                for i in range(0, total_to_test, BATCH_SIZE):
                    current_batch_products = products_to_test[i : i + BATCH_SIZE]
                    batch_num = (i // BATCH_SIZE) + 1
                    total_batches = (total_to_test + BATCH_SIZE - 1) // BATCH_SIZE
                    logging.info(f"--- Processing Test Batch {batch_num}/{total_batches} (Size: {len(current_batch_products)}) ---")

                    # Prepare data for this specific batch
                    competitor_data_for_batch = []
                    original_product_data_batch = {p['map_id']: p for p in current_batch_products}

                    for product in current_batch_products:
                        comp_name = product['competitor_product_name']
                        search_query = product['search_query']
                        competitor_brand = product['competitor_brand']

                        # Prepare context (same logic as before)
                        search_query_context = search_query
                        if competitor_brand and competitor_brand.lower() in search_query.lower():
                           try:
                               search_query_context = re.sub(re.escape(competitor_brand), '', search_query, flags=re.IGNORECASE).strip()
                               search_query_context = re.sub(' +', ' ', search_query_context)
                           except Exception as e:
                               logging.warning(f"Error stripping brand '{competitor_brand}' from query '{search_query}' for map_id={product['map_id']}: {e}")
                               search_query_context = search_query

                        competitor_data_for_batch.append({
                            'map_id': product['map_id'],
                            'competitor_product_name': comp_name,
                            'search_query_context': search_query_context
                        })

                    # Call the batch scoring function for the current batch
                    logging.info(f"Calling OpenAI batch scoring for {len(competitor_data_for_batch)} products in batch {batch_num}...")
                    # Assume all test products share the same reference brand
                    ref_brand = current_batch_products[0]['reference_brand']
                    batch_results = get_batch_relevancy_scores(ref_brand, competitor_data_for_batch)

                    # Process results for the current batch
                    if batch_results and isinstance(batch_results, list):
                        logging.info(f"Received {len(batch_results)} results for batch {batch_num}.")
                        scores_map = {item['map_id']: item['score'] for item in batch_results if isinstance(item, dict) and 'map_id' in item and 'score' in item}

                        # Merge results with original data for CSV
                        for map_id, product_data in original_product_data_batch.items():
                            score = scores_map.get(map_id)
                            data_sent = next((item for item in competitor_data_for_batch if item['map_id'] == map_id), None)
                            search_query_context_used = data_sent['search_query_context'] if data_sent else 'CONTEXT_LOOKUP_FAILED'

                            result_row = {
                                'map_id': map_id, 'reference_brand': product_data['reference_brand'],
                                'reference_product_name': product_data['reference_product_name'],
                                'competitor_product_name': product_data['competitor_product_name'],
                                'search_query': product_data['search_query'],
                                'search_query_context': search_query_context_used,
                                'competitor_brand': product_data['competitor_brand'],
                                'relevancy_score': score if score is not None else 'ERROR'
                            }
                            results_data.append(result_row)

                            if score is not None:
                                products_scored += 1
                                logging.debug(f"Score for map_id={map_id} (Batch {batch_num}): {score}")
                            else:
                                logging.warning(f"Failed to get score for map_id={map_id} in batch {batch_num}")

                    elif batch_results is None:
                        logging.error(f"Batch {batch_num} API call failed completely.")
                        for map_id, product_data in original_product_data_batch.items():
                            data_sent = next((item for item in competitor_data_for_batch if item['map_id'] == map_id), None)
                            search_query_context_used = data_sent['search_query_context'] if data_sent else 'CONTEXT_LOOKUP_FAILED'
                            result_row = {
                                'map_id': map_id, 'reference_brand': product_data['reference_brand'],
                                'reference_product_name': product_data['reference_product_name'],
                                'competitor_product_name': product_data['competitor_product_name'],
                                'search_query': product_data['search_query'],
                                'search_query_context': search_query_context_used,
                                'competitor_brand': product_data['competitor_brand'],
                                'relevancy_score': 'BATCH_ERROR'
                            }
                            results_data.append(result_row)
                    else:
                        logging.warning(f"Unexpected format received from batch {batch_num} API call: {batch_results}")

                    # Optional small delay between test batches
                    time.sleep(1.0)

        except Exception as e:
            logging.error(f"An error occurred during the test scoring process: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()
                logging.info("Database connection closed.")
    else:
        logging.error("Failed to establish database connection. Exiting test.")

    end_time = time.time() # Record end time
    total_time = end_time - start_time

    # --- Summary and CSV Output ---
    logging.info("--- Test Summary ---")
    logging.info(f"Products Processed: {products_processed}")
    logging.info(f"Products Scored Successfully: {products_scored}")
    logging.info(f"Total Execution Time: {total_time:.2f} seconds")

    if results_data:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        product_suffix = ""
        if target_product:
            sanitized_product = re.sub(r'[\/\\:\*\?"<>\|\s]+', '_', target_product)[:50]
            product_suffix = f"_{sanitized_product}"

        filename = f"relevancy_test_results_{timestamp}{product_suffix}.csv"
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = results_data[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results_data)
            logging.info(f"Results saved to: {filename}")
        except IOError as e:
            logging.error(f"Failed to write results to CSV file '{filename}': {e}")
    else:
        logging.info("No results to save to CSV.")

    logging.info("Relevancy scoring test finished.") 