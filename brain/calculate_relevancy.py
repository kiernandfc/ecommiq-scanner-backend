import os
import json
import logging
import time # Import time for potential retries/delays
import random # Import random for jitter
from collections import defaultdict # Import defaultdict
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError, BadRequestError # Import specific errors
import psycopg2 # Assuming PostgreSQL - replace if needed
from psycopg2 import sql
from psycopg2.extras import DictCursor, execute_values # Import execute_values
import sys

# --- Configuration ---
load_dotenv() # Load environment variables from .env file

# Configure logging
logger = logging.getLogger("relevancy_calculator")
logger.setLevel(logging.INFO)

# Clear any existing handlers to avoid duplicate logs
if logger.handlers:
    logger.handlers.clear()

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

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY environment variable not found.")
    exit(1)
OPENAI_MODEL = "gpt-4.1-nano" # Updated model

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
                    }
                },
                "required": ["competitor_product_name", "relevancy_score"],
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
def get_products_to_score(conn):
    """Fetches products from competitor_catalog_map that need scoring,
    joining with competitors and catalog tables to get necessary names and context.

    Args:
        conn: Active database connection object.

    Returns:
        A list of dictionaries, each containing 'map_id',
        'competitor_product_name', 'reference_product_name',
        'search_query', 'competitor_brand', 'reference_brand',
        and 'reference_product_description'
        for rows where competitor_catalog_map.relevancy_score is NULL or 0.
        Returns an empty list if no products need scoring or in case of error.
    """
    products = []
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            query = sql.SQL("""
                SELECT
                    ccm.id AS map_id,
                    cat.title AS competitor_product_name,
                    comp.reference_product AS reference_product_name,
                    comp.search_query,
                    comp.competitor_brand,
                    comp.reference_brand,
                    comp.reference_product_description
                FROM
                    {catalog_map_table} ccm
                JOIN
                    {competitor_table} comp ON ccm.competitor_id = comp.id
                JOIN
                    {catalog_table} cat ON ccm.catalog_id = cat.id
                WHERE
                    ccm.relevancy_score IS NULL OR ccm.relevancy_score = 0;
            """).format(
                catalog_map_table=sql.Identifier('competitor_catalog_map'),
                competitor_table=sql.Identifier('competitors'),
                catalog_table=sql.Identifier('catalog')
            )
            cur.execute(query)
            results = cur.fetchall()
            products = [dict(row) for row in results]
            logger.info(f"Fetched {len(products)} products requiring relevancy scoring (NULL or 0 scores).")
    except psycopg2.Error as e:
        logger.error(f"Database error while fetching products: {e}")
        # Optionally re-raise or handle differently
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching products: {e}")
    return products

# --- Batch Relevancy Scoring ---
def get_batch_relevancy_scores(reference_brand, competitor_products_batch):
    """Calls OpenAI API to get relevancy scores for a batch of competitor products
    using structured output with exponential backoff.

    Args:
        reference_brand: The brand of the reference product.
        competitor_products_batch: A list of dictionaries, each containing
                                    'map_id', 'competitor_product_name', 'search_query_context',
                                    and 'reference_product_description'.

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
Your goal is to determine how relevant a list of competitor products are to a specific reference product, based on names, descriptions, and search context.
Output the scores as a JSON object containing a single key 'scores', which is an array of objects. Each object in the array must have 'competitor_product_name' (the exact competitor product name provided in the input) and 'relevancy_score' (an integer 1-10).

The relevancy scale is 1-10:
- 1: Not relevant at all.
- 10: Identical product.
Focus on product function/description, not just brand. Ensure every competitor product listed receives a score.
"""

    # Format competitor products for the prompt
    competitor_list_str = "\n".join([
        f"  - Name='{p['competitor_product_name']}', Context='{p['search_query_context']}'"
        for p in competitor_products_batch
    ])

    user_prompt = f"""
Reference Brand: "{reference_brand}"
Reference Product Name: "{reference_name}"
Reference Product Description:
{reference_description}

Competitor Products to Evaluate (Max {BATCH_SIZE}):
{competitor_list_str}

Based on the reference product description and each competitor product's details (name and context), please provide the relevancy score for *each* competitor product using the 0-10 scale. Return the results in the specified JSON format (an object with a 'scores' array, where each item has 'competitor_product_name' and 'relevancy_score').
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
                try:
                    result = json.loads(raw_json)
                    scores_list = result.get("scores")

                    # Validate the structure and scores
                    if not isinstance(scores_list, list):
                        logger.warning(f"Invalid response structure: 'scores' is not a list. Raw JSON: {raw_json}")
                        return None

                    validated_scores = []
                    # Keep track of names returned by the API
                    returned_names = set()

                    for item in scores_list:
                        comp_name = item.get("competitor_product_name")
                        score = item.get("relevancy_score")

                        # Check if the name was in our original request and score is valid
                        if comp_name in name_to_map_ids and isinstance(score, int) and 1 <= score <= 10:
                            # Apply the score to all map_ids associated with this name in the batch
                            for map_id in name_to_map_ids[comp_name]:
                                validated_scores.append({'map_id': map_id, 'score': score})
                            returned_names.add(comp_name)
                        elif comp_name not in name_to_map_ids:
                             logger.warning(f"API returned score for unexpected product name: '{comp_name}'. Item: {item}. Raw JSON: {raw_json}")
                        else:
                            logger.warning(f"Invalid score or type for product '{comp_name}': {score}. Item: {item}. Raw JSON: {raw_json} - Score must be an integer between 1 and 10.")
                            # Decide whether to skip item or fail batch - let's skip invalid items for now

                    # Check if all *unique* requested names received scores
                    if len(returned_names) != len(name_to_map_ids):
                        requested_names = set(name_to_map_ids.keys())
                        missing_names = requested_names - returned_names
                        logger.warning(f"Batch response missing scores for {len(missing_names)} product names (e.g., {list(missing_names)[:3]}). Proceeding with {len(validated_scores)} valid scores.")
                        # Decide if partial success is acceptable. Here we accept partial success.

                    logger.debug(f"Successfully processed batch scoring for {len(validated_scores)} products (requested {len(competitor_products_batch)}).")
                    return validated_scores # Return the list of valid scores found

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode JSON response for batch. Raw JSON: {raw_json}")
                    return None # Failed to parse JSON
                except Exception as e:
                    logger.error(f"Error processing JSON response for batch. Raw JSON: {raw_json}. Error: {e}")
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

def update_relevancy_scores(conn, scores_to_update):
    """Updates the relevancy_score in the database for multiple products using execute_values.

    Args:
        conn: Active database connection object.
        scores_to_update: A list of dictionaries, each with 'map_id' and 'score'.
    """
    if not scores_to_update:
        logger.info("No scores provided to update.")
        return

    # Prepare data as a list of tuples (score, map_id) for execute_values
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
            logger.info(f"Successfully updated relevancy scores for {len(update_data)} products.")

    except psycopg2.Error as e:
        logger.error(f"Database error during bulk update: {e}")
        conn.rollback() # Roll back in case of error
    except Exception as e:
        logger.error(f"An unexpected error occurred during bulk update: {e}")
        conn.rollback()

# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting relevancy scoring process...")
    conn = get_db_connection()

    if conn:
        try:
            # 1. Fetch all products needing scores
            all_products_to_score = get_products_to_score(conn)
            total_products = len(all_products_to_score)
            logger.info(f"Found {total_products} products to score.")

            all_scores_calculated = []

            if all_products_to_score:
                # Assume all products share the same reference brand for simplicity in this batch structure
                # If reference brand could vary, batching needs to group by brand too.
                reference_brand = all_products_to_score[0]['reference_brand'] if total_products > 0 else "Unknown" # Get from first product
                reference_product_description = all_products_to_score[0]['reference_product_description'] if total_products > 0 else None

                # 2. Process products in batches
                for i in range(0, total_products, BATCH_SIZE):
                    batch = all_products_to_score[i : i + BATCH_SIZE]
                    logger.info(f"Processing batch {i // BATCH_SIZE + 1}/{(total_products + BATCH_SIZE - 1) // BATCH_SIZE} (size {len(batch)})")

                    # Prepare competitor data for the batch scoring function
                    competitor_data_for_batch = []
                    for product in batch:
                        map_id = product['map_id']
                        comp_name = product['competitor_product_name']
                        search_query = product['search_query']
                        competitor_brand = product['competitor_brand']
                        reference_name = product['reference_product_name']
                        reference_desc = product['reference_product_description']

                        # Prepare context (same logic as before)
                        search_query_context = search_query
                        if competitor_brand and competitor_brand.lower() in search_query.lower():
                           import re
                           search_query_context = re.sub(re.escape(competitor_brand), '', search_query, flags=re.IGNORECASE).strip()
                           search_query_context = re.sub(' +', ' ', search_query_context)

                        competitor_data_for_batch.append({
                            'map_id': map_id,
                            'competitor_product_name': comp_name,
                            'search_query_context': search_query_context,
                            'reference_product_name': reference_name,
                            'reference_product_description': reference_desc
                        })

                    # Call the batch scoring function
                    batch_scores = get_batch_relevancy_scores(reference_brand, competitor_data_for_batch)

                    if batch_scores is not None:
                        all_scores_calculated.extend(batch_scores)
                        # Optional: Add a smaller delay between batches if needed, but backoff handles most cases
                        # time.sleep(1.0) # Example: 1 second delay between successful batches
                    else:
                        logger.warning(f"Failed to get scores for batch starting with name '{batch[0]['competitor_product_name']}'. Skipping batch.")
                        # Consider adding failed map_ids to a separate list for later retry/review


                # 3. Update database with all calculated scores
                if all_scores_calculated:
                    update_relevancy_scores(conn, all_scores_calculated)
                    logger.info(f"Attempted to update scores for {len(all_scores_calculated)} products from batches.")
                else:
                    logger.info("No scores were successfully calculated or updated from batches.")

        except Exception as e:
            logger.error(f"An critical error occurred during the batch scoring process: {e}", exc_info=True) # Add traceback
        finally:
            conn.close()
            logger.info("Database connection closed.")
    else:
        logger.error("Failed to establish database connection. Exiting.")

    logger.info("Relevancy scoring process finished.")

# --- DEPRECATED: Single Item Scoring Function ---
# def get_relevancy_score(reference_name, reference_brand, competitor_name, search_query_context):
#    ... (keep old function commented out or remove) ... 