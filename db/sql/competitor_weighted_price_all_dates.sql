-- Drop the view if it already exists (optional, useful for development)
-- DROP MATERIALIZED VIEW IF EXISTS competitor_weighted_price_all_dates;

-- Create the materialized view for competitor weighted average prices for all dates from 2025-04-14
CREATE MATERIALIZED VIEW competitor_weighted_price_all_dates AS
WITH relevant_mappings AS (
    -- Get only product mappings with relevancy score >= 7
    SELECT
        ccm.competitor_id,
        ccm.catalog_id,
        c.reference_brand,
        c.competitor_brand,
        c.search_query
    FROM
        competitor_catalog_map ccm
    JOIN
        competitors c ON ccm.competitor_id = c.id
    WHERE
        ccm.relevancy_score >= 7  -- Only include products with high relevancy
),
latest_review_counts AS (
    -- Get the most recent review count for each product using data from 2025-04-14 onwards
    SELECT 
        catalog_id,
        -- Use the review count from the most recent date for each product
        FIRST_VALUE(max_review_count_filled) OVER (
            PARTITION BY catalog_id 
            ORDER BY report_date DESC
        ) AS latest_review_count
    FROM 
        interpolated_price_summary_all_dates -- Changed from _14day
    WHERE 
        max_review_count_filled IS NOT NULL
    GROUP BY 
        catalog_id, report_date, max_review_count_filled
),
weighted_prices AS (
    -- Join the interpolated price data (from 2025-04-14 onwards) with the mappings and calculate weights
    SELECT
        rm.competitor_id,
        rm.catalog_id,
        rm.competitor_brand,
        rm.reference_brand,
        rm.search_query,
        ips.report_date,
        ips.avg_price_interpolated,
        -- Use the most recent review count as weight for all days
        COALESCE(lrc.latest_review_count, 1) AS weight
    FROM
        relevant_mappings rm
    JOIN
        interpolated_price_summary_all_dates ips ON rm.catalog_id = ips.catalog_id -- Changed from _14day
    LEFT JOIN
        latest_review_counts lrc ON rm.catalog_id = lrc.catalog_id
    WHERE
        ips.avg_price_interpolated IS NOT NULL  -- Ensure we have a price to calculate
        -- Removed the is_available_filled filter as requested
),
total_weights AS (
    -- Calculate total weights for each competitor, reference query, and date combination
    SELECT
        competitor_id,
        competitor_brand,
        reference_brand,
        search_query,
        report_date,
        SUM(weight) AS total_weight
    FROM
        weighted_prices
    GROUP BY
        competitor_id, competitor_brand, reference_brand, search_query, report_date
)
-- Calculate the weighted average price
SELECT
    wp.competitor_id,
    wp.competitor_brand,
    wp.reference_brand,
    wp.search_query,
    wp.report_date,
    -- Calculate weighted average using the weight formula:
    -- Sum(price * weight) / Sum(weight)
    SUM(wp.avg_price_interpolated * wp.weight) / NULLIF(tw.total_weight, 0) AS weighted_avg_price,
    -- Include the sum of weights and count of products for reference
    tw.total_weight AS sum_of_weights,
    COUNT(wp.catalog_id) AS product_count
FROM
    weighted_prices wp
JOIN
    total_weights tw ON wp.competitor_id = tw.competitor_id
                    AND wp.report_date = tw.report_date
                    AND wp.search_query = tw.search_query
GROUP BY
    wp.competitor_id,
    wp.competitor_brand,
    wp.reference_brand,
    wp.search_query,
    wp.report_date,
    tw.total_weight
ORDER BY
    wp.competitor_brand,
    wp.reference_brand,
    wp.search_query,
    wp.report_date;

-- Add an index to optimize queries
CREATE INDEX IF NOT EXISTS idx_competitor_weighted_price_all_dates
ON competitor_weighted_price_all_dates (competitor_id, report_date);

-- Additional index for brand and query-based lookups
CREATE INDEX IF NOT EXISTS idx_competitor_weighted_price_all_dates_brand_query
ON competitor_weighted_price_all_dates (competitor_brand, reference_brand, search_query, report_date);

-- Note: Remember to refresh this view periodically, after refreshing the interpolated_price_summary_all_dates view
-- REFRESH MATERIALIZED VIEW competitor_weighted_price_all_dates;
