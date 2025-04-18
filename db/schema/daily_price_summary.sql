-- Drop the view if it already exists (optional, useful for development)
-- DROP MATERIALIZED VIEW IF EXISTS daily_price_summary;

-- Create the materialized view for daily summaries
CREATE MATERIALIZED VIEW daily_price_summary AS
SELECT
    catalog_id,
    date_trunc('day', date_checked)::date AS summary_date, -- Extract the date part
    AVG(price) AS avg_price,                     -- Average price for the day
    BOOL_OR(is_available) AS is_available_on_day, -- True if it was available at any point during the day
    MAX(review_count) AS max_review_count,       -- Maximum review count observed on that day
    AVG(position) AS avg_position,               -- Average position for the day
    MAX(date_checked) AS latest_check_timestamp, -- Latest timestamp checked on that day
    MAX(created_at) AS latest_creation_timestamp -- Latest record creation timestamp for that day
FROM
    prices  -- Assumes your table name is 'prices' based on PriceHistoryDB
GROUP BY
    catalog_id,
    date_trunc('day', date_checked) -- Group by product and day
ORDER BY
    catalog_id,
    summary_date;

-- Optional: Add an index for potentially faster lookups on the materialized view
CREATE INDEX IF NOT EXISTS idx_daily_price_summary_catalog_date
ON daily_price_summary (catalog_id, summary_date);

-- Note: Remember to refresh this view periodically
-- REFRESH MATERIALIZED VIEW daily_price_summary;
