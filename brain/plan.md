# Plan: Competitor Product Relevancy Scoring Module

## 1. Goal

Develop a module to calculate and maintain a "relevancy score" for each product in the `competitor_catalog_map` table relative to its corresponding reference product in the `competitor` table.

-   **Score Scale:** 0-10 (0 = Not Relevant, 5 = Potential Substitute, 7-8 = Likely Substitute, 10 = Identical)
-   **Initial Method:** Use OpenAI API to compare product names.
-   **Prioritization:** Instruct the AI model to focus on the core product name, de-emphasizing the brand name if present within the product name string.

## 2. Database Schema & Assumptions

*   **`competitor` Table:**
    *   `id` (Primary Key)
    *   `reference_product_name` (Text/VARCHAR) - The name of the product we are comparing against.
    *   *(Other relevant columns...)*
*   **`competitor_catalog_map` Table:**
    *   `id` (Primary Key)
    *   `competitor_id` (Foreign Key referencing `competitor.id`)
    *   `product_name` (Text/VARCHAR) - The name of the competitor's product.
    *   **New Column:** `relevancy_score` (Integer/Float) - To store the calculated score. *Needs to be added.*

## 3. Script (`scripts/calculate_relevancy.py`)

*   **Setup:**
    *   Import necessary libraries (`database connector`, `openai`, `os`/`dotenv`, `json`).
    *   Load configuration (DB credentials, OpenAI API key) securely (e.g., from environment variables).
    *   Establish database connection.
    *   Define the expected JSON schema for the OpenAI response (e.g., `{"type": "object", "properties": {"relevancy_score": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Product relevancy score from 0 to 10"}}, "required": ["relevancy_score"], "additionalProperties": false}`). Note: OpenAI's structured output might not support `minimum`/`maximum` keywords yet, but the description helps.
*   **Core Logic:**
    1.  **Fetch Data:**
        *   Query `competitor_catalog_map` to get rows where `relevancy_score` is NULL (or all rows if recalculating).
        *   For each row, join with the `competitor` table using `competitor_id` to retrieve the `reference_product_name`.
    2.  **Iterate and Score:**
        *   Loop through the fetched rows.
        *   For each `(competitor_product_name, reference_product_name)` pair:
            *   Construct a clear prompt for the OpenAI API (`gpt-4o-mini` model).
                *   Include the two product names.
                *   Explain the 0-10 relevancy scale and its meaning.
                *   **Crucially:** Instruct the model to evaluate similarity based primarily on the *product description/function* within the name, giving less weight to the *brand name* part of the string. Instruct it to return the score within the defined JSON schema.
            *   Call the OpenAI API using the `responses.create` endpoint (or equivalent ChatCompletion endpoint if preferred, ensuring structured output is requested):
                *   Set `model` to `gpt-4o-mini` (or the latest available snapshot like `gpt-4o-mini-2024-07-18`).
                *   Provide the prompt messages (`input`).
                *   Set `text.format` (or `response_format` for ChatCompletions) to `{"type": "json_schema", "name": "relevancy_score_response", "schema": <your_schema_object>, "strict": True}`.
            *   Parse the response:
                *   Check for API errors or refusals.
                *   If successful, parse the JSON string from `response.output_text` (or the message content).
                *   Extract the `relevancy_score` value.
                *   Implement robust error handling (API errors, JSON parsing errors, missing key, out-of-range scores if not handled by schema). Default to a specific value (e.g., NULL or -1) or log the error if parsing fails.
            *   Store the result temporarily (e.g., in a list of tuples `(map_id, score)`).
    3.  **Update Database:**
        *   After processing a batch (or all products), execute UPDATE statements to save the calculated `relevancy_score` back to the `competitor_catalog_map` table using the `id`. Use bulk updates if possible for efficiency.
*   **Error Handling & Logging:**
    *   Log progress, API calls, errors, and summary statistics (e.g., number of products processed, average score).
*   **Configuration:**
    *   Use a `.env` file for API keys and database connection strings.
    *   Specify the OpenAI model name (e.g., `gpt-4o-mini`) in configuration or constants.
    *   Potentially add configuration for batch size, API timeouts, etc.

## 4. Implementation Steps

1.  **Database Migration:** Add the `relevancy_score` column (nullable integer or float) to the `competitor_catalog_map` table.
2.  **Environment Setup:** Create a `.env` file and add `OPENAI_API_KEY` and database credentials. Ensure `.env` is in `.gitignore`.
3.  **Dependency Installation:** Add `openai` (ensure version supports structured outputs) and the appropriate database driver (e.g., `psycopg2-binary`, `mysql-connector-python`) to `requirements.txt` (or `pyproject.toml`). Run `pip install -r requirements.txt`.
4.  **Script Development:** Implement `scripts/calculate_relevancy.py` following the logic outlined above, specifically using structured outputs with `gpt-4o-mini`.
5.  **Testing:**
    *   Test with a small subset of data.
    *   Verify API prompts and responses.
    *   Check database updates.
    *   Test error handling logic.
6.  **Execution:** Run the script to populate the relevancy scores.

## 5. Future Enhancements

*   **Scraping Integration:** Fetch content from product listing pages for more context in the AI prompt.
*   **Embedding-based Comparison:** Explore using text embeddings (e.g., OpenAI embeddings) for a potentially faster/cheaper similarity calculation, possibly combined with the LLM approach.
*   **Batch Processing:** Optimize API calls and database updates using batching.
*   **UI for Review/Override:** Develop an interface for users to review and manually adjust scores.
*   **Incremental Updates:** Modify the script to only process new or updated entries in `competitor_catalog_map`.
*   **Periodic Recalculation:** Schedule the script to run periodically to refresh scores.
