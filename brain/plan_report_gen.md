Goal is to create a summary by reference brand of major competitor movements over a recent period
We have a view in the database that will contain the raw data of period over period price changes: "db\sql\seven_day_change_summary.sql"

Now we should create a script that iterates through this data as a data analyst would with the following sequence:
For each category within a reference brand:
1. Calculate weighted average price change by brand and highlight top 3 and bottom 3
2. For brands with changes >2%, find the top products that drove that change
3. Feed that data to an LLM to summarize changes
4. Consider having the LLM visit product pages and competitor websites to add context to report