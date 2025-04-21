-- Drop the view if it already exists (optional, useful for development)
-- DROP MATERIALIZED VIEW IF EXISTS daily_price_summary;

-- Create the materialized view for daily summaries
CREATE MATERIALIZED VIEW daily_price_summary AS
WITH most_common_merchants AS (
    -- Identify the most common merchant for each catalog_id over the last 7 days
    SELECT 
        catalog_id,
        merchant AS primary_merchant
    FROM (
        SELECT 
            catalog_id,
            merchant,
            COUNT(*) AS occurrence_count,
            ROW_NUMBER() OVER (PARTITION BY catalog_id ORDER BY COUNT(*) DESC) AS rank
        FROM prices
        WHERE 
            date_checked >= CURRENT_DATE - INTERVAL '7 days'
            AND merchant NOT ILIKE '%ebay%'
        GROUP BY catalog_id, merchant
    ) ranked_merchants
    WHERE rank = 1
)
SELECT
    p.catalog_id,
    date_trunc('day', p.date_checked)::date AS summary_date, -- Extract the date part
    AVG(p.price) AS avg_price,                     -- Average price for the day
    BOOL_OR(p.is_available) AS is_available_on_day, -- True if it was available at any point during the day
    MAX(p.review_count) AS max_review_count,       -- Maximum review count observed on that day
    AVG(p.position) AS avg_position,               -- Average position for the day
    MAX(p.date_checked) AS latest_check_timestamp, -- Latest timestamp checked on that day
    MAX(p.created_at) AS latest_creation_timestamp, -- Latest record creation timestamp for that day
    STRING_AGG(DISTINCT p.merchant, ', ' ORDER BY p.merchant) AS merchants -- List of merchants for the day (should be just one now)
FROM
    prices p
JOIN 
    most_common_merchants mcm ON p.catalog_id = mcm.catalog_id AND p.merchant = mcm.primary_merchant
WHERE
    p.merchant NOT ILIKE '%ebay%' -- Extra safety to exclude merchants containing 'ebay' (case insensitive)
GROUP BY
    p.catalog_id,
    date_trunc('day', p.date_checked) -- Group by product and day
ORDER BY
    p.catalog_id,
    summary_date;

-- Optional: Add an index for potentially faster lookups on the materialized view
CREATE INDEX IF NOT EXISTS idx_daily_price_summary_catalog_date
ON daily_price_summary (catalog_id, summary_date);

-- Note: Remember to refresh this view periodically
-- REFRESH MATERIALIZED VIEW daily_price_summary;
