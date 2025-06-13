-- Drop the view if it already exists (optional, useful for development)
-- DROP VIEW IF EXISTS brand_category_competitor_reindexed_price_index;

-- Create the view for re-indexed price indices at the reference_brand / category / competitor_brand level
-- All indices are based to 1.0 on April 1st, 2025
CREATE OR REPLACE VIEW brand_category_competitor_reindexed_price_index AS
WITH
    competitor_prices_data AS (
        -- Get prices for specific competitor brands for each reference_brand/category/date
        SELECT
            reference_brand,
            search_query AS category, -- Using search_query as the category context
            report_date,
            competitor_brand AS specific_competitor_brand, -- The actual competitor
            weighted_avg_price AS specific_competitor_price
        FROM
            competitor_weighted_price_all_dates
        WHERE
            competitor_brand != reference_brand -- Ensuring it's a distinct competitor
    ),
    reference_prices_data AS (
        -- Get prices for the reference_brand itself for each category/date
        SELECT
            reference_brand,
            search_query AS category,
            report_date,
            weighted_avg_price AS reference_price -- Price of the reference brand
        FROM
            competitor_weighted_price_all_dates
        WHERE
            competitor_brand = reference_brand -- Data row for the reference brand itself
    ),
    daily_individual_prices AS (
        -- Join reference prices with specific competitor prices
        SELECT
            cpd.reference_brand,
            cpd.category,
            cpd.report_date,
            cpd.specific_competitor_brand,
            rpd.reference_price,
            cpd.specific_competitor_price,
            -- Calculate daily price index: reference_price / specific_competitor_price
            CASE
                WHEN cpd.specific_competitor_price IS NOT NULL AND cpd.specific_competitor_price <> 0
                THEN rpd.reference_price / cpd.specific_competitor_price
                ELSE NULL
            END AS daily_ref_vs_comp_price_index
        FROM
            competitor_prices_data cpd
        JOIN
            reference_prices_data rpd ON cpd.reference_brand = rpd.reference_brand
                                     AND cpd.category = rpd.category
                                     AND cpd.report_date = rpd.report_date
        WHERE
            rpd.reference_price IS NOT NULL
            AND cpd.specific_competitor_price IS NOT NULL
    ),
    base_period_individual_values AS (
        -- Get base period values (April 1st, 2025) for each combination
        SELECT
            reference_brand,
            category,
            specific_competitor_brand,
            reference_price AS base_reference_price,
            specific_competitor_price AS base_specific_competitor_price,
            daily_ref_vs_comp_price_index AS base_ref_vs_comp_price_index
        FROM
            daily_individual_prices
        WHERE
            report_date = '2025-04-01'::date
            AND reference_price IS NOT NULL AND reference_price <> 0
            AND specific_competitor_price IS NOT NULL AND specific_competitor_price <> 0
            AND daily_ref_vs_comp_price_index IS NOT NULL AND daily_ref_vs_comp_price_index <> 0
    )
-- Final selection and re-indexing
SELECT
    dip.reference_brand,
    dip.category,
    dip.report_date,
    dip.specific_competitor_brand,
    dip.reference_price AS original_reference_price,
    dip.specific_competitor_price AS original_specific_competitor_price,
    dip.daily_ref_vs_comp_price_index AS original_ref_vs_comp_price_index,

    bpiv.base_reference_price,
    bpiv.base_specific_competitor_price,
    bpiv.base_ref_vs_comp_price_index,

    -- Indexed reference price (relative to its own price on April 1st for this specific comparison)
    CASE
        WHEN bpiv.base_reference_price IS NOT NULL AND bpiv.base_reference_price <> 0
        THEN dip.reference_price / bpiv.base_reference_price
        ELSE NULL
    END AS indexed_reference_price,

    -- Indexed specific competitor price (relative to its own price on April 1st)
    CASE
        WHEN bpiv.base_specific_competitor_price IS NOT NULL AND bpiv.base_specific_competitor_price <> 0
        THEN dip.specific_competitor_price / bpiv.base_specific_competitor_price
        ELSE NULL
    END AS indexed_specific_competitor_price,

    -- Re-indexed reference vs specific competitor price index (base April 1st = 1.0)
    CASE
        WHEN bpiv.base_ref_vs_comp_price_index IS NOT NULL AND bpiv.base_ref_vs_comp_price_index <> 0
        THEN dip.daily_ref_vs_comp_price_index / bpiv.base_ref_vs_comp_price_index
        ELSE NULL
    END AS reindexed_ref_vs_comp_price_index
FROM
    daily_individual_prices dip
JOIN
    base_period_individual_values bpiv ON dip.reference_brand = bpiv.reference_brand
                                       AND dip.category = bpiv.category
                                       AND dip.specific_competitor_brand = bpiv.specific_competitor_brand
WHERE
    dip.report_date >= '2025-04-01'::date -- Ensure we only consider dates from the base period onwards
ORDER BY
    dip.reference_brand,
    dip.category,
    dip.specific_competitor_brand,
    dip.report_date;

-- Add a comment describing the view
COMMENT ON VIEW brand_category_competitor_reindexed_price_index IS
'Provides re-indexed price metrics at the reference_brand / category / specific_competitor_brand level.
All indices are set to 1.0 on April 1st, 2025, for each combination.
Subsequent dates show values relative to this base.
Category is derived from the search_query in competitor_weighted_price_all_dates.
Includes:
- indexed_reference_price: Reference brand''s price indexed to its own price on 2025-04-01 for that specific comparison context.
- indexed_specific_competitor_price: Specific competitor''s price indexed to its own price on 2025-04-01.
- reindexed_ref_vs_comp_price_index: (reference_price / specific_competitor_price) index, re-indexed to 1.0 on 2025-04-01.
Sources data primarily from competitor_weighted_price_all_dates.';
