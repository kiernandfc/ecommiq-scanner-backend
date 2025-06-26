-- SQL script to update source_type to 'direct_website' for all catalog products 
-- that are mapped to competitors with reference_brand = 'RTA Cabinet Store'

-- First, get all the catalog product IDs mapped to RTA Cabinet Store competitors
-- Then update the source_type for those products

UPDATE catalog
SET source_type = 'direct_website'
WHERE id IN (
    SELECT ccm.catalog_id
    FROM competitor_catalog_map ccm
    JOIN competitors c ON ccm.competitor_id = c.id
    WHERE c.reference_brand = 'RTA Cabinet Store'
);

-- To verify the update was successful, you can run this query:
-- SELECT COUNT(*) FROM catalog WHERE source_type = 'direct_website';
