-- Drop the view if it already exists (optional, useful for development)
-- DROP MATERIALIZED VIEW IF EXISTS interpolated_price_summary_14day;

-- Create the materialized view for 14-day interpolated summaries
CREATE MATERIALIZED VIEW interpolated_price_summary_14day AS
WITH date_series AS (
    -- Generate dates for the last 14 days (inclusive of today)
    SELECT generate_series(
               CURRENT_DATE - INTERVAL '13 days', -- Start date (13 days ago)
               CURRENT_DATE,                     -- End date (today)
               '1 day'::interval                 -- Step interval
           )::date AS report_date
),
-- Get distinct products that have at least 3 datapoints in the daily_price_summary
distinct_products AS (
    SELECT 
        catalog_id
    FROM 
        daily_price_summary
    WHERE 
        summary_date >= CURRENT_DATE - INTERVAL '13 days'
    GROUP BY 
        catalog_id
    HAVING 
        COUNT(DISTINCT summary_date) >= 3
),
product_date_combinations AS (
    -- Create all product x date combinations for the 14-day window
    SELECT
        p.catalog_id,
        d.report_date
    FROM distinct_products p
    CROSS JOIN date_series d
),
daily_data AS (
    SELECT * FROM daily_price_summary
    WHERE 
        summary_date >= CURRENT_DATE - INTERVAL '13 days' -- Filter data from the first view
        AND catalog_id IN (SELECT catalog_id FROM distinct_products) -- Filter to only include products with 3+ datapoints
),
joined_data AS (
    -- Left join the date combinations with actual daily data
    SELECT
        pdc.catalog_id,
        pdc.report_date,
        dd.avg_price,
        dd.is_available_on_day,
        dd.max_review_count,
        dd.avg_position,
        dd.latest_check_timestamp, -- Keep original timestamp if data exists
        dd.latest_creation_timestamp, -- Keep original timestamp if data exists
        dd.merchants -- Add merchants from daily summary
    FROM product_date_combinations pdc
    LEFT JOIN daily_data dd ON pdc.catalog_id = dd.catalog_id AND pdc.report_date = dd.summary_date
),
data_with_neighbors AS (
    -- Use window functions to find the DATE of the nearest previous and next days WITH data
    SELECT
        *,
        -- Find the DATE of the previous row with data for this product
        MAX(CASE WHEN avg_price IS NOT NULL THEN report_date END)
            OVER (PARTITION BY catalog_id ORDER BY report_date ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_date_with_data,
        -- Find the DATE of the next row with data for this product
        MIN(CASE WHEN avg_price IS NOT NULL THEN report_date END)
            OVER (PARTITION BY catalog_id ORDER BY report_date ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) AS next_date_with_data
    FROM joined_data
),
-- Fetch the actual values from the neighbor dates
data_with_neighbor_values AS (
    SELECT
        dn.*,
        -- Previous values
        prev_data.avg_price AS prev_avg_price,
        prev_data.avg_position AS prev_avg_position,
        prev_data.is_available_on_day AS prev_is_available,
        prev_data.max_review_count AS prev_max_review_count,
        -- Next values
        next_data.avg_price AS next_avg_price,
        next_data.avg_position AS next_avg_position
        -- Note: We don't need next_is_available or next_max_review_count for the final calculation logic
    FROM data_with_neighbors dn
    -- Join to get previous values (using daily_data as it's already aggregated per date)
    LEFT JOIN daily_data prev_data ON dn.catalog_id = prev_data.catalog_id AND dn.prev_date_with_data = prev_data.summary_date
    -- Join to get next values
    LEFT JOIN daily_data next_data ON dn.catalog_id = next_data.catalog_id AND dn.next_date_with_data = next_data.summary_date
)
-- Final calculation with interpolation
SELECT
    catalog_id,
    report_date,
    -- Interpolated Average Price
    CASE
        WHEN avg_price IS NOT NULL THEN avg_price -- Use actual value if available
        WHEN prev_date_with_data IS NULL AND next_date_with_data IS NULL THEN NULL -- No data points to interpolate from
        WHEN prev_date_with_data IS NULL THEN next_avg_price -- Only future data exists, use it (extrapolate backward)
        WHEN next_date_with_data IS NULL THEN prev_avg_price -- Only past data exists, use it (extrapolate forward)
        -- Avoid division by zero if dates somehow align (shouldn't happen here with distinct dates)
        WHEN next_date_with_data = prev_date_with_data THEN prev_avg_price
        ELSE
            -- Linear interpolation formula (using day difference)
            prev_avg_price + (next_avg_price - prev_avg_price) *
            ( (report_date - prev_date_with_data)::double precision / NULLIF( (next_date_with_data - prev_date_with_data)::double precision, 0) )
    END AS avg_price_interpolated,

    -- Interpolated Average Position
    CASE
        WHEN avg_position IS NOT NULL THEN avg_position
        WHEN prev_date_with_data IS NULL AND next_date_with_data IS NULL THEN NULL
        WHEN prev_date_with_data IS NULL THEN next_avg_position
        WHEN next_date_with_data IS NULL THEN prev_avg_position
        WHEN next_date_with_data = prev_date_with_data THEN prev_avg_position
        ELSE
            -- Linear interpolation formula (using day difference)
            prev_avg_position + (next_avg_position - prev_avg_position) *
            ( (report_date - prev_date_with_data)::double precision / NULLIF( (next_date_with_data - prev_date_with_data)::double precision, 0) )
    END AS avg_position_interpolated,

    -- Availability & Review Count: Carry forward the last known value if current is missing
    -- Need the previous value from the new CTE
    COALESCE(is_available_on_day, prev_is_available) AS is_available_filled,
    COALESCE(max_review_count, prev_max_review_count) AS max_review_count_filled,

    -- Merchant list: Only show for days with actual data (not interpolated)
    merchants,

    -- Timestamps: Show only if data actually exists for this specific day
    latest_check_timestamp,
    latest_creation_timestamp
FROM data_with_neighbor_values -- Use the CTE that has the neighbor values joined in
ORDER BY
    catalog_id,
    report_date;

-- Optional: Add an index for potentially faster lookups
CREATE INDEX IF NOT EXISTS idx_interpolated_price_summary_14day_cat_date
ON interpolated_price_summary_14day (catalog_id, report_date);

-- Note: Remember to refresh this view periodically, potentially after refreshing the daily view
-- REFRESH MATERIALIZED VIEW interpolated_price_summary_14day;
