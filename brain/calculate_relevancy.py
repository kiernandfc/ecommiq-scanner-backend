import os
import json
import logging
import time # Import time for potential retries/delays
import random # Import random for jitter
import argparse # Import argparse for command-line arguments
import shutil # For directory operations
from collections import defaultdict # Import defaultdict
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError, BadRequestError # Import specific errors
import psycopg2 # Assuming PostgreSQL - replace if needed
from psycopg2 import sql
from psycopg2.extras import DictCursor, execute_values # Import execute_values
import sys
from tqdm import tqdm  # For progress bar

# --- Configuration ---
load_dotenv() # Load environment variables from .env file

# Configure logging
logger = logging.getLogger("relevancy_calculator")

def configure_logging(use_progress_bar=False):
    """Configure logging based on whether progress bar mode is enabled.
    
    Args:
        use_progress_bar (bool): If True, minimal logging will be used with a progress bar.
                               If False, detailed logging will be enabled.
    """
    global logger
    # Reset logger configuration
    if logger.handlers:
        logger.handlers.clear()
    
    if use_progress_bar:
        # In progress bar mode, only log warnings and errors to file
        logger.setLevel(logging.WARNING)
        try:
            file_handler = logging.FileHandler("relevancy_scoring.log")
            file_handler.setLevel(logging.WARNING)
            file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_format)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file: {e}")
    else:
        # Full detailed logging
        logger.setLevel(logging.INFO)
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)
        
        # Create file handler for persistent logs
        try:
            file_handler = logging.FileHandler("relevancy_scoring.log")
            file_handler.setLevel(logging.INFO)
            file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_format)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file: {e}")

# Default to detailed logging initially
configure_logging(False)

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY environment variable not found.")
    exit(1)
OPENAI_MODEL = "gpt-4.1" # Updated model

# Database Configuration (Using existing POSTGRESQL_* variables)
DB_HOST = os.getenv("POSTGRESQL_HOST")
DB_PORT = os.getenv("POSTGRESQL_PORT")
DB_NAME = os.getenv("POSTGRESQL_DB")
DB_USER = os.getenv("POSTGRESQL_USER")
DB_PASSWORD = os.getenv("POSTGRESQL_PASSWORD")

if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
    logger.error("One or more PostgreSQL environment variables are missing.")
    exit(1)

# --- Constants ---
BATCH_SIZE = 25

# OpenAI Structured Output Schema (for single item - kept for potential reference)
# RELEVANCY_SCHEMA = { ... } # Old schema commented out or removed if not needed

# New OpenAI Structured Output Schema for Batch Processing
BATCH_RELEVANCY_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "description": "An array of relevancy scores for the competitor products.",
            "items": {
                "type": "object",
                "properties": {
                    "competitor_product_name": {
                        "type": "string",
                        "description": "The exact name of the competitor product as provided in the input."
                    },
                    "relevancy_score": {
                        "type": "integer",
                        "description": "Product relevancy score from 1 to 10."
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Brief explanation for why this score was assigned."
                    }
                },
                "required": ["competitor_product_name", "relevancy_score", "rationale"],
                "additionalProperties": False
            }
        }
    },
    "required": ["scores"],
    "additionalProperties": False
}
BATCH_RELEVANCY_SCHEMA_NAME = "batch_relevancy_score_response"

# Exponential Backoff Configuration
MAX_RETRIES = 5
INITIAL_DELAY = 1.0 # seconds
BACKOFF_FACTOR = 2.0
JITTER_FACTOR = 0.1 # Max 10% jitter

# --- OpenAI Client ---
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    exit(1)

# --- Database Connection ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        logger.info("Database connection established.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Unable to connect to the database: {e}")
        return None

# --- Core Logic ---
def get_products_to_score(conn, update_all=False):
    """Fetches products from competitor_catalog_map that need scoring,
    joining with competitors and catalog tables to get necessary names and context.

    Args:
        conn: Active database connection object.
        update_all: If True, fetch all products regardless of current score. If False (default),
                   only fetch products with NULL or 0 scores.

    Returns:
        A list of dictionaries, each containing 'map_id',
        'competitor_product_name', 'reference_product_name',
        'search_query', 'competitor_brand', 'reference_brand',
        and 'reference_product_description'
        for rows that match the criteria. Returns an empty list in case of error.
    """
    products = []
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            # Build the query with conditional WHERE clause
            query_parts = [
                "SELECT",
                "    ccm.id AS map_id,",
                "    cat.title AS competitor_product_name,",
                "    comp.reference_product AS reference_product_name,",
                "    comp.search_query,",
                "    comp.competitor_brand,",
                "    comp.reference_brand,",
                "    comp.reference_product_description",
                "FROM",
                "    {catalog_map_table} ccm",
                "JOIN",
                "    {competitor_table} comp ON ccm.competitor_id = comp.id",
                "JOIN",
                "    {catalog_table} cat ON ccm.catalog_id = cat.id"
            ]
            
            # Only add WHERE clause if not updating all products
            if not update_all:
                query_parts.append("WHERE")
                query_parts.append("    ccm.relevancy_score IS NULL OR ccm.relevancy_score = 0")
            
            query_sql = sql.SQL("\n".join(query_parts)).format(
                catalog_map_table=sql.Identifier('competitor_catalog_map'),
                competitor_table=sql.Identifier('competitors'),
                catalog_table=sql.Identifier('catalog')
            )
            
            cur.execute(query_sql)
            results = cur.fetchall()
            products = [dict(row) for row in results]
            
            if update_all:
                logger.info(f"Fetched {len(products)} products for scoring (including existing scores).")
            else:
                logger.info(f"Fetched {len(products)} products requiring relevancy scoring (NULL or 0 scores).")
    except psycopg2.Error as e:
        logger.error(f"Database error while fetching products: {e}")
        # Optionally re-raise or handle differently
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching products: {e}")
    return products

# --- Batch Relevancy Scoring ---
def get_batch_relevancy_scores(reference_brand, competitor_products_batch, use_progress_bar=False):
    """Calls OpenAI API to get relevancy scores for a batch of competitor products
    using structured output with exponential backoff.

    Args:
        reference_brand: The brand of the reference product.
        competitor_products_batch: A list of dictionaries, each containing
                                    'map_id', 'competitor_product_name',
                                    and 'reference_product_description'.
        use_progress_bar: If True, use progress bar output instead of detailed logging.

    Returns:
        A list of dictionaries [{'map_id': id, 'score': score}] or None if the call fails.
    """
    if not competitor_products_batch:
        return []

    # Create a mapping from competitor name to a LIST of map_ids
    name_to_map_ids = defaultdict(list)
    for p in competitor_products_batch:
        name_to_map_ids[p['competitor_product_name']].append(p['map_id'])

    # Get reference product details from the first product in batch
    reference_name = competitor_products_batch[0].get('reference_product_name', "")
    reference_description = competitor_products_batch[0].get('reference_product_description', "")
    
    # If reference product description is not available, log a warning
    if not reference_description:
        logger.warning(f"Reference product description is missing for '{reference_name}'. Results may be less accurate.")
        reference_description = "No description available."

    system_prompt = f"""You are an AI assistant evaluating product relevancy.
Your goal is to determine how relevant a list of competitor products are to a specific reference product, based on names and descriptions.
Output the scores as a JSON object containing a single key 'scores', which is an array of objects. Each object in the array must have 'competitor_product_name' (the exact competitor product name provided in the input), 'relevancy_score' (an integer 1-10), and 'rationale' (a brief explanation for the score).

The relevancy scale is 1-10:
- 1: Not relevant at all.
- 10: Identical product.

Important scoring guidelines:
- Focus on product function, features, silhouette, and construction
- DO NOT emphasize color or pattern when scoring, as the reference product may encompass a wide range of colors/patterns not specified
- Consider the core product type, shape, materials, and intended use
- Evaluate if the products serve similar purposes and would appeal to similar customers
- Ensure every competitor product listed receives a score.
"""

    # Format competitor products for the prompt
    competitor_list_str = "\n".join([
        f"  - Name='{p['competitor_product_name']}'"
        for p in competitor_products_batch
    ])

    user_prompt = f"""
Reference Brand: "{reference_brand}"
Reference Product Name: "{reference_name}"
Reference Product Description:
{reference_description}

Competitor Products to Evaluate (Max {BATCH_SIZE}):
{competitor_list_str}

Based on the reference product description and each competitor product's name, please provide the relevancy score for *each* competitor product using the 1-10 scale. Remember to focus on product features, silhouette, and construction rather than color or pattern. Return the results in the specified JSON format (an object with a 'scores' array, where each item has 'competitor_product_name', 'relevancy_score', and 'rationale' explaining why you assigned that score).
"""

    current_delay = INITIAL_DELAY
    for attempt in range(MAX_RETRIES):
        try:
            # Use the Responses API endpoint for structured output
            response = client.responses.create(
                model=OPENAI_MODEL,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": BATCH_RELEVANCY_SCHEMA_NAME,
                        "schema": BATCH_RELEVANCY_SCHEMA,
                        "strict": True # Enforce schema strictly if possible
                    }
                },
                # Adjust max_output_tokens based on expected batch size and schema complexity
                max_output_tokens=150 * len(competitor_products_batch) # Estimate, might need tuning
            )

            # Check response status and content
            if response.status == "completed":
                if response.output and response.output[0].content and response.output[0].content[0].type == "refusal":
                    refusal_message = response.output[0].content[0].refusal
                    logger.warning(f"OpenAI refused batch request (first product name '{competitor_products_batch[0]['competitor_product_name'] if competitor_products_batch else 'N/A'}'): {refusal_message}")
                    return None # Treat refusal as failure for the whole batch

                raw_json = response.output_text
                if not raw_json:
                     logger.warning(f"Empty output_text received for batch (first product name '{competitor_products_batch[0]['competitor_product_name'] if competitor_products_batch else 'N/A'}'")
                     return None
                
                # Format the raw JSON for prettier logging
                formatted_json = raw_json
                try:
                    # Try to parse and re-serialize with proper indentation
                    parsed_json = json.loads(raw_json)
                    formatted_json = json.dumps(parsed_json, indent=2, ensure_ascii=False)
                except json.JSONDecodeError:
                    # If it's not valid JSON, keep the original format
                    logger.warning("Could not format raw JSON for logs (not valid JSON)")
                
                # Create log file with API input and output for debugging
                try:
                    import datetime
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    log_dir = "api_logs"
                    
                    # Ensure log directory exists
                    if not os.path.exists(log_dir):
                        os.makedirs(log_dir)
                    
                    log_file = f"{log_dir}/openai_api_log_{timestamp}.json"
                    
                    log_data = {
                        "timestamp": timestamp,
                        "reference_brand": reference_brand,
                        "reference_name": reference_name,
                        "input": {
                            "system_prompt": system_prompt,
                            "user_prompt": user_prompt,
                            "model": OPENAI_MODEL,
                            "schema": BATCH_RELEVANCY_SCHEMA
                        },
                        "response": {
                            "status": response.status,
                            "raw_output": formatted_json,
                            "incomplete_details": response.incomplete_details if hasattr(response, 'incomplete_details') else None
                        },
                        "scores_with_rationales": []  # Will be populated after processing
                    }
                    
                    with open(log_file, 'w', encoding='utf-8') as f:
                        json.dump(log_data, f, indent=2, ensure_ascii=False)
                    
                    if not use_progress_bar:
                        logger.info(f"API call log saved to {log_file}")
                except Exception as log_error:
                    logger.error(f"Failed to save API log: {log_error}")

                try:
                    result = json.loads(formatted_json)
                    scores_list = result.get("scores")

                    # Validate the structure and scores
                    if not isinstance(scores_list, list):
                        logger.warning(f"Invalid response structure: 'scores' is not a list. Raw JSON: {formatted_json}")
                        return None

                    validated_scores = []
                    # Keep track of names returned by the API
                    returned_names = set()

                    for item in scores_list:
                        comp_name = item.get("competitor_product_name")
                        score = item.get("relevancy_score")
                        rationale = item.get("rationale", "No rationale provided")

                        # Check if the name was in our original request and score is valid
                        if comp_name in name_to_map_ids and isinstance(score, int) and 1 <= score <= 10:
                            # Apply the score to all map_ids associated with this name in the batch
                            for map_id in name_to_map_ids[comp_name]:
                                validated_scores.append({
                                    'map_id': map_id,
                                    'score': score,
                                    'rationale': rationale,
                                    'competitor_product_name': comp_name
                                })
                            returned_names.add(comp_name)
                            logger.debug(f"Scored product '{comp_name}': {score}/10 - {rationale}")
                        elif comp_name not in name_to_map_ids:
                             logger.warning(f"API returned score for unexpected product name: '{comp_name}'. Item: {item}. Raw JSON: {formatted_json}")
                        else:
                            logger.warning(f"Invalid score or type for product '{comp_name}': {score}. Item: {item}. Raw JSON: {formatted_json} - Score must be an integer between 1 and 10.")
                            # Decide whether to skip item or fail batch - let's skip invalid items for now

                    # Check if all *unique* requested names received scores
                    if len(returned_names) != len(name_to_map_ids):
                        requested_names = set(name_to_map_ids.keys())
                        missing_names = requested_names - returned_names
                        logger.warning(f"Batch response missing scores for {len(missing_names)} product names (e.g., {list(missing_names)[:3]}). Proceeding with {len(validated_scores)} valid scores.")
                        # Decide if partial success is acceptable. Here we accept partial success.

                    # Update log data with the processed scores and rationales
                    if 'log_data' in locals():
                        for score_item in validated_scores:
                            log_data["scores_with_rationales"].append({
                                "competitor_product_name": score_item['competitor_product_name'],
                                "score": score_item['score'],
                                "rationale": score_item['rationale'],
                                "map_id": score_item['map_id']  # Keep map_id as reference
                            })
                        # Re-save the log file with the updated data
                        with open(log_file, 'w', encoding='utf-8') as f:
                            json.dump(log_data, f, indent=2, ensure_ascii=False)
                        if not use_progress_bar:
                            logger.info(f"Updated API log with processed scores and rationales in {log_file}")

                    if not use_progress_bar:
                        logger.debug(f"Successfully processed batch scoring for {len(validated_scores)} products (requested {len(competitor_products_batch)}).")
                    return validated_scores # Return the list of valid scores found

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON response for batch. Raw JSON: {formatted_json}")
                    return None # Failed to parse JSON
                except Exception as e:
                    logger.error(f"Error processing JSON response for batch. Raw JSON: {formatted_json}. Error: {e}")
                    return None # Other processing error

            elif response.status == "incomplete":
                reason = response.incomplete_details.reason if response.incomplete_details else "unknown"
                logger.warning(f"OpenAI batch response incomplete (reason: {reason})")
                # Potentially retry or handle based on reason, for now return None
                return None
            else: # Handle other statuses like 'failed', 'cancelled'
                 logger.error(f"OpenAI batch response status was '{response.status}'")
                 return None

        except RateLimitError:
            if attempt < MAX_RETRIES - 1:
                delay = current_delay * (BACKOFF_FACTOR ** attempt)
                jitter = random.uniform(0, delay * JITTER_FACTOR)
                sleep_time = delay + jitter
                if use_progress_bar:
                    print(f"Rate limit exceeded. Retrying in {sleep_time:.2f} seconds... (Attempt {attempt + 1}/{MAX_RETRIES})")
                else:
                    logger.warning(f"Rate limit exceeded on batch. Retrying in {sleep_time:.2f} seconds... (Attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(sleep_time)
            else:
                logger.error(f"Max retries ({MAX_RETRIES}) exceeded for batch rate limit error.")
                return None # Max retries hit

        except BadRequestError as e:
            logger.error(f"OpenAI BadRequestError on batch (check schema or prompt): {e}")
            return None # Bad request, likely prompt/schema issue
        except APIError as e:
            logger.error(f"OpenAI API error on batch: {e}")
            # Potentially retry API errors as well depending on the error type
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling OpenAI API for batch: {e}")
            return None # Unexpected failure

    # If loop finishes without returning, it means max retries were hit
    logger.error(f"Failed to get scores for batch after {MAX_RETRIES} attempts (first product name '{competitor_products_batch[0]['competitor_product_name'] if competitor_products_batch else 'N/A'}'): {e}")
    return None

def update_relevancy_scores(conn, scores_to_update, use_progress_bar=False):
    """Updates the relevancy_score in the database for multiple products using execute_values.

    Args:
        conn: Active database connection object.
        scores_to_update: A list of dictionaries, each with 'map_id', 'score', and potentially 'rationale'.
        use_progress_bar: If True, use progress bar output instead of logging.
    """
    if not scores_to_update:
        if use_progress_bar:
            print("No scores provided to update.")
        else:
            logger.info("No scores provided to update.")
        return

    # Prepare data as a list of tuples (score, map_id) for execute_values
    # Only include score and map_id for database update, ignoring rationale
    update_data = [(item['score'], item['map_id']) for item in scores_to_update]

    try:
        with conn.cursor() as cur:
            # Construct the UPDATE query using execute_values helper
            # Updates rows matching the id from the provided data
            update_query = sql.SQL("""
                UPDATE {table} AS t SET
                    relevancy_score = data.score
                FROM (VALUES %s) AS data (score, map_id)
                WHERE t.id = data.map_id;
            """).format(table=sql.Identifier('competitor_catalog_map'))

            execute_values(cur, update_query.as_string(cur), update_data)
            conn.commit() # Commit the transaction
            if use_progress_bar:
                print(f"Successfully updated relevancy scores for {len(update_data)} products.")
            else:
                logger.info(f"Successfully updated relevancy scores for {len(update_data)} products.")

    except psycopg2.Error as e:
        logger.error(f"Database error during bulk update: {e}")
        conn.rollback() # Roll back in case of error
    except Exception as e:
        logger.error(f"An unexpected error occurred during bulk update: {e}")
        conn.rollback()

# --- Helper Functions ---
def clear_log_directory():
    """Clears all files in the api_logs directory."""
    log_dir = "api_logs"
    if os.path.exists(log_dir):
        for filename in os.listdir(log_dir):
            file_path = os.path.join(log_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                logger.info(f"Deleted {file_path}")
            except Exception as e:
                logger.error(f"Error deleting {file_path}: {e}")
        logger.info("Log directory cleared successfully.")
    else:
        # Create the directory if it doesn't exist
        os.makedirs(log_dir)
        logger.info(f"Created new log directory: {log_dir}")

# --- Main Execution ---
if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Calculate relevancy scores for competitor products.")
    parser.add_argument("--limit", type=int, default=0, 
                      help="Limit the number of reference products to process (0 means process all, default: 0)")
    parser.add_argument("--keep-logs", action="store_true", default=False,
                      help="Keep existing log files (default: clear logs before starting)")
    parser.add_argument("--reference-product", type=str, default="",
                      help="Only process products matching this specific reference product name (default: process all)")
    parser.add_argument("--update-all", action="store_true", default=False,
                      help="Update relevancy scores for all products, not just those with NULL or 0 scores (default: only update NULL/0)")
    parser.add_argument("--progress-bar", action="store_true", default=False,
                      help="Display a progress bar instead of detailed log statements (default: show detailed logs)")
    args = parser.parse_args()
    
    # Configure logging based on progress bar preference
    configure_logging(args.progress_bar)
    
    if args.progress_bar:
        print("Starting relevancy scoring process (progress bar mode)...")
    else:
        logger.info("Starting relevancy scoring process...")
    
    # Clear log directory if specified (default behavior)
    if not args.keep_logs:
        clear_log_directory()
        if not args.progress_bar:
            logger.info("Log directory cleared before starting.")
    elif not args.progress_bar:
        logger.info("Keeping existing log files as requested.")
    
    conn = get_db_connection()

    if conn:
        try:
            # 1. Fetch products to score (all or just NULL/0 based on update-all flag)
            all_products_to_score = get_products_to_score(conn, update_all=args.update_all)
            total_products = len(all_products_to_score)
            logger.info(f"Found {total_products} products to score.")

            all_scores_calculated = []

            if all_products_to_score:
                # Group products by reference product
                reference_product_groups = {}
                for product in all_products_to_score:
                    reference_key = (product['reference_product_name'], product['reference_brand'])
                    if reference_key not in reference_product_groups:
                        reference_product_groups[reference_key] = []
                    reference_product_groups[reference_key].append(product)
                
                total_reference_products = len(reference_product_groups)
                logger.info(f"Products grouped into {total_reference_products} distinct reference products.")
                
                # Filter by reference product if specified
                if args.reference_product:
                    filtered_groups = {}
                    for key, group in reference_product_groups.items():
                        ref_name, _ = key
                        if args.reference_product.lower() in ref_name.lower():
                            filtered_groups[key] = group
                    
                    if filtered_groups:
                        reference_product_groups = filtered_groups
                        logger.info(f"Filtered to {len(reference_product_groups)} reference products matching '{args.reference_product}'.")
                    else:
                        logger.warning(f"No reference products found matching '{args.reference_product}'. Exiting.")
                        sys.exit(0)
                
                # Apply limit if specified
                if args.limit > 0 and args.limit < len(reference_product_groups):
                    logger.info(f"Limiting processing to {args.limit} reference products out of {len(reference_product_groups)}.")
                    # Convert to list to limit it
                    reference_product_items = list(reference_product_groups.items())[:args.limit]
                else:
                    reference_product_items = reference_product_groups.items()
                    if args.limit > 0:
                        logger.info(f"Requested limit ({args.limit}) exceeds available reference products ({len(reference_product_groups)}). Processing all.")
                    else:
                        logger.info(f"Processing all {len(reference_product_groups)} reference products.")

                # Process each reference product group separately
                reference_product_count = len(reference_product_items)
                if args.progress_bar:
                    # Create a progress bar for reference products
                    ref_progress = tqdm(total=reference_product_count, desc="Reference Products", position=0)
                    # Track overall products for the total progress
                    total_products_to_process = sum(len(group) for _, group in reference_product_items)
                    product_progress = tqdm(total=total_products_to_process, desc="Products Scored", position=1)
                    print(f"Processing {reference_product_count} reference products with {total_products_to_process} total products...")
                
                for i, (reference_key, products_group) in enumerate(reference_product_items, 1):
                    reference_name, reference_brand = reference_key
                    group_size = len(products_group)
                    
                    if not args.progress_bar:
                        logger.info(f"Processing group {i}/{len(reference_product_items)}: reference product '{reference_name}' ({group_size} products)")
                    
                    # Use the reference product details from the first product in this group
                    reference_product_description = products_group[0]['reference_product_description']

                    # Process products in batches within this reference product group
                    products_processed_in_group = 0
                    for j in range(0, group_size, BATCH_SIZE):
                        batch = products_group[j : j + BATCH_SIZE]
                        if not args.progress_bar:
                            logger.info(f"Processing batch {j // BATCH_SIZE + 1}/{(group_size + BATCH_SIZE - 1) // BATCH_SIZE} for reference '{reference_name}' (size {len(batch)})")

                        # Prepare competitor data for the batch scoring function
                        competitor_data_for_batch = []
                        for product in batch:
                            map_id = product['map_id']
                            comp_name = product['competitor_product_name']

                            competitor_data_for_batch.append({
                                'map_id': map_id,
                                'competitor_product_name': comp_name,
                                'reference_product_name': reference_name,
                                'reference_product_description': reference_product_description
                            })

                        # Call the batch scoring function with the correct reference brand for this group
                        batch_scores = get_batch_relevancy_scores(reference_brand, competitor_data_for_batch, args.progress_bar)

                        if batch_scores is not None:
                            all_scores_calculated.extend(batch_scores)
                            products_processed_in_group += len(batch_scores)
                            # Update progress bars if enabled
                            if args.progress_bar:
                                product_progress.update(len(batch_scores))
                        else:
                            if args.progress_bar:
                                print(f"Warning: Failed to get scores for batch of reference product '{reference_name}'. Skipping batch.")
                            else:
                                logger.warning(f"Failed to get scores for batch of reference product '{reference_name}'. Skipping batch.")
                    
                    # Update reference product progress bar
                    if args.progress_bar:
                        ref_progress.update(1)

                # Close progress bars if enabled
                if args.progress_bar:
                    ref_progress.close()
                    product_progress.close()

                # 3. Update database with all calculated scores
                if all_scores_calculated:
                    update_relevancy_scores(conn, all_scores_calculated, args.progress_bar)
                    msg = f"Attempted to update scores for {len(all_scores_calculated)} products from batches."
                    if args.progress_bar:
                        print(msg)
                    else:
                        logger.info(msg)
                else:
                    msg = "No scores were successfully calculated or updated from batches."
                    if args.progress_bar:
                        print(msg)
                    else:
                        logger.info(msg)

        except Exception as e:
            logger.error(f"A critical error occurred during the batch scoring process: {e}", exc_info=True) # Add traceback
        finally:
            conn.close()
            if args.progress_bar:
                print("Database connection closed.")
            else:
                logger.info("Database connection closed.")
    else:
        logger.error("Failed to establish database connection. Exiting.")

    if args.progress_bar:
        print("Relevancy scoring process finished.")
    else:
        logger.info("Relevancy scoring process finished.")

# --- DEPRECATED: Single Item Scoring Function ---
# def get_relevancy_score(reference_name, reference_brand, competitor_name, search_query_context):
#    ... (keep old function commented out or remove) ... 