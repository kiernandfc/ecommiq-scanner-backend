-- Script to refresh all materialized views in the correct order
-- This ensures data consistency and dependency management

-- Step 1: Refresh the daily price summary view first
-- This contains the daily aggregated data from the raw prices table
REFRESH MATERIALIZED VIEW daily_price_summary;

-- Step 2: Refresh the interpolated price data for 14-day window
-- This relies on daily_price_summary, so must be refreshed after
REFRESH MATERIALIZED VIEW interpolated_price_summary_14day;

-- Step 3: Refresh the competitor weighted price view
-- This depends on interpolated data, so must be refreshed last
REFRESH MATERIALIZED VIEW competitor_weighted_price_14day;

-- Log the refresh operation
DO $$
BEGIN
    RAISE NOTICE 'All materialized views refreshed successfully at %', NOW();
END $$; 