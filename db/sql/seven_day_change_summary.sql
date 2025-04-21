-- Create a view that shows 7-day price and review count changes with product context
CREATE OR REPLACE VIEW seven_day_change_summary AS
WITH 
-- Get data for the last 7 days
last_seven_days AS (
    SELECT 
        catalog_id,
        AVG(avg_price) AS avg_price_last_7_days,
        AVG(max_review_count) AS avg_review_count_last_7_days,
        COUNT(DISTINCT summary_date) AS days_with_data_last_7_days
    FROM daily_price_summary
    WHERE summary_date BETWEEN CURRENT_DATE - INTERVAL '7 days' AND CURRENT_DATE
    GROUP BY catalog_id
),
-- Get data for the prior 7 days (days 8-14)
prior_seven_days AS (
    SELECT 
        catalog_id,
        AVG(avg_price) AS avg_price_prior_7_days,
        AVG(max_review_count) AS avg_review_count_prior_7_days,
        COUNT(DISTINCT summary_date) AS days_with_data_prior_7_days
    FROM daily_price_summary
    WHERE summary_date BETWEEN CURRENT_DATE - INTERVAL '14 days' AND CURRENT_DATE - INTERVAL '8 days'
    GROUP BY catalog_id
)
-- Main query combining the periods and joining with context data
SELECT 
    c.id AS catalog_id,
    c.title AS product_name,
    c.link AS url,
    l7.avg_price_last_7_days,
    p7.avg_price_prior_7_days,
    (l7.avg_price_last_7_days - p7.avg_price_prior_7_days) AS price_change,
    CASE 
        WHEN p7.avg_price_prior_7_days > 0 
        THEN (l7.avg_price_last_7_days - p7.avg_price_prior_7_days) / p7.avg_price_prior_7_days * 100 
        ELSE NULL 
    END AS price_change_percentage,
    l7.avg_review_count_last_7_days,
    p7.avg_review_count_prior_7_days,
    (l7.avg_review_count_last_7_days - p7.avg_review_count_prior_7_days) AS review_count_change,
    comp.reference_brand,
    comp.reference_product,
    comp.competitor_brand,
    ccm.relevancy_score
FROM last_seven_days l7
JOIN prior_seven_days p7 ON l7.catalog_id = p7.catalog_id
JOIN catalog c ON c.id = l7.catalog_id
JOIN competitor_catalog_map ccm ON ccm.catalog_id = c.id
JOIN competitors comp ON comp.id = ccm.competitor_id
WHERE 
    -- Only include products with at least 3 days of data in both periods
    l7.days_with_data_last_7_days >= 3
    AND p7.days_with_data_prior_7_days >= 3
ORDER BY 
    comp.reference_brand,
    comp.reference_product,
    price_change_percentage DESC NULLS LAST;

-- Create index to optimize query performance (optional)
-- CREATE INDEX IF NOT EXISTS idx_seven_day_change_summary_catalog_id ON seven_day_change_summary (catalog_id);

-- Note: Since this is a view (not materialized), it will always return current data
-- To make this a materialized view instead, replace CREATE OR REPLACE VIEW with:
-- CREATE MATERIALIZED VIEW seven_day_change_summary AS
-- And add a refresh command:
-- REFRESH MATERIALIZED VIEW seven_day_change_summary; 