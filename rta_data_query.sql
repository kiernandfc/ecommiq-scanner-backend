Select p.*, c.*, com.*
from prices as p
	left join competitor_catalog_map as ccm on p.catalog_id = ccm.catalog_id
	left join competitors as com on ccm.competitor_id = com.id
	left join catalog as c on p.catalog_id = c.id
where com.site_id is not null
