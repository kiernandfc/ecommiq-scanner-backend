-- Drop the view first to avoid column change errors
DROP VIEW IF EXISTS brand_category_price_index;

-- Create the brand category price index view
CREATE OR REPLACE VIEW brand_category_price_index AS
WITH search_categories AS (
    -- Extract category from search query by removing competitor brand
    SELECT
        competitor_id,
        reference_brand,
        competitor_brand,
        search_query,
        report_date,
        weighted_avg_price,
        -- Extract category by removing competitor brand from search query
        TRIM(REGEXP_REPLACE(
            LOWER(search_query), 
            LOWER(competitor_brand),
            '', 
            'g'
        )) AS category,
        -- Flag to identify if this is a reference brand (matching its own products)
        (reference_brand = competitor_brand) AS is_reference_brand
    FROM
        competitor_weighted_price_14day
    WHERE 
        weighted_avg_price IS NOT NULL
),
brand_category_summary AS (
    -- Group all data by reference brand, category and date
    SELECT
        reference_brand,
        category,
        report_date,
        -- Get reference brand's price (when it's equal to competitor brand)
        MAX(CASE WHEN is_reference_brand THEN weighted_avg_price ELSE NULL END) AS reference_price,
        -- Calculate average price of competitors (when it's not the reference brand)
        AVG(CASE WHEN NOT is_reference_brand THEN weighted_avg_price ELSE NULL END) AS avg_competitor_price
    FROM
        search_categories
    GROUP BY
        reference_brand, category, report_date
    -- Only include entries that have both reference and competitor data
    HAVING 
        MAX(CASE WHEN is_reference_brand THEN 1 ELSE NULL END) = 1
        AND COUNT(CASE WHEN NOT is_reference_brand THEN 1 ELSE NULL END) > 0
)
-- Final calculation of price index
SELECT
    reference_brand,
    category,
    report_date,
    reference_price,
    avg_competitor_price,
    -- Calculate price index: reference price / competitor avg price
    reference_price / avg_competitor_price AS price_index
FROM
    brand_category_summary
WHERE
    avg_competitor_price > 0  -- Ensure we don't divide by zero
ORDER BY
    reference_brand,
    category,
    report_date;

-- Add a comment describing the view
COMMENT ON VIEW brand_category_price_index IS 
'Provides a price index comparing reference brand prices to average competitor prices within each category.
Category is derived by stripping the competitor brand name from the search query.
Price index = reference brand price / average competitor price, where values < 1 indicate the reference brand is less expensive.'; 