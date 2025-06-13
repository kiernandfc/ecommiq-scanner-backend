-- Drop the view if it already exists (optional, useful for development)
-- DROP VIEW IF EXISTS brand_category_reindexed_price_index;

-- Create the view for re-indexed brand category price index (base April 1st, 2025 = 1.0)
CREATE OR REPLACE VIEW brand_category_reindexed_price_index AS
WITH base_period_values AS (
    -- Get values on April 1st, 2025 for each brand/category to serve as the base (1.0)
    SELECT
        reference_brand,
        category,
        price_index AS base_original_price_index,
        avg_competitor_price AS base_avg_competitor_price,
        reference_price AS base_reference_price,
        competitor_count, -- Added competitor_count for weighting
        -- Weighted combined price: ( (ref_price*1) + (avg_comp_price*comp_count) ) / (1+comp_count)
        ((reference_price * 1) + (avg_competitor_price * competitor_count)) / (1 + competitor_count) AS base_combined_price
    FROM
        brand_category_price_index_all_dates
    WHERE
        report_date = '2025-04-01'::date
        AND price_index IS NOT NULL AND price_index <> 0
        AND avg_competitor_price IS NOT NULL AND avg_competitor_price <> 0
        AND reference_price IS NOT NULL AND reference_price <> 0
        AND competitor_count IS NOT NULL AND (1 + competitor_count) <> 0 -- Ensure divisor is not zero
)
SELECT
    bcpi.reference_brand,
    bcpi.category,
    bcpi.report_date,
    bcpi.reference_price,                   -- Original reference price
    bcpi.avg_competitor_price,              -- Original average competitor price
    bcpi.competitor_count,                  -- Number of competitors
    -- Daily weighted combined price: ( (ref_price*1) + (avg_comp_price*comp_count) ) / (1+comp_count)
    ((bcpi.reference_price * 1) + (bcpi.avg_competitor_price * bcpi.competitor_count)) / (1 + bcpi.competitor_count) AS daily_weighted_combined_price,
    bcpi.price_index AS original_price_index, -- Original price index (ref_price / avg_comp_price)

    bpv.base_reference_price,
    bpv.base_avg_competitor_price,
    bpv.base_combined_price AS base_weighted_combined_price, -- Renamed for clarity
    bpv.base_original_price_index,

    -- Re-indexed original price_index (ref_price / avg_comp_price), base April 1st = 1.0
    bcpi.price_index / bpv.base_original_price_index AS reindexed_original_price_index,

    -- Indexed average competitor price, base April 1st = 1.0
    bcpi.avg_competitor_price / bpv.base_avg_competitor_price AS indexed_avg_competitor_price,

    -- Indexed reference price, base April 1st = 1.0
    bcpi.reference_price / bpv.base_reference_price AS indexed_reference_price,

    -- Indexed weighted combined price, base April 1st = 1.0
    (((bcpi.reference_price * 1) + (bcpi.avg_competitor_price * bcpi.competitor_count)) / (1 + bcpi.competitor_count)) / bpv.base_combined_price AS indexed_weighted_combined_price
FROM
    brand_category_price_index_all_dates bcpi
JOIN
    base_period_values bpv ON bcpi.reference_brand = bpv.reference_brand
                           AND bcpi.category = bpv.category
WHERE
    bcpi.report_date >= '2025-04-01'::date -- Ensure we only consider dates from the base period onwards
    AND (1 + bcpi.competitor_count) <> 0 -- Ensure divisor is not zero for daily calculation
ORDER BY
    bcpi.reference_brand,
    bcpi.category,
    bcpi.report_date;

-- Add a comment describing the view
COMMENT ON VIEW brand_category_reindexed_price_index IS 
'Provides a re-indexed version of the brand category price index and other key prices.
All indexes are set to 1.0 on April 1st, 2025, for each reference_brand and category.
Subsequent dates show values relative to this base.
Includes:
- reindexed_original_price_index: (original price_index) / (price_index on 2025-04-01)
- indexed_avg_competitor_price: (avg_competitor_price) / (avg_competitor_price on 2025-04-01)
- indexed_reference_price: (reference_price) / (reference_price on 2025-04-01)
- indexed_weighted_combined_price: (daily_weighted_combined_price) / (base_weighted_combined_price on 2025-04-01)
  Weighted combined price = ((reference_price*1) + (avg_competitor_price*competitor_count)) / (1+competitor_count)
Sources data from brand_category_price_index_all_dates.';
