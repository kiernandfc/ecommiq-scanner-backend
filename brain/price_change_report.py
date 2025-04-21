#!/usr/bin/env python
"""
Price Change Report Generator

This script generates a report of price changes by reference brand, highlighting
significant competitor movements over a recent period.

The script uses the seven_day_change_summary view for data and performs analysis
following these steps:
1. Calculate weighted average price change by brand
2. Highlight top/bottom brands by price change
3. For brands with significant changes (>2%), find driving products
"""

import os
import pandas as pd
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from sqlalchemy import create_engine, text

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

class PriceChangeReportGenerator:
    """Generates price change reports based on seven_day_change_summary view"""
    
    def __init__(self, reference_brand: str = None):
        """
        Initialize the report generator with database connection
        
        Args:
            reference_brand: Optional filter for a specific reference brand
        """
        self.logger = configure_logger(f"{__name__}.PriceChangeReportGenerator")
        self.db = PostgreSQLDatabase()
        self.engine = self.db.engine
        self.reference_brand = reference_brand
        
    def fetch_price_change_data(self) -> pd.DataFrame:
        """Fetch data from the seven_day_change_summary view"""
        self.logger.info("Fetching seven-day price change data")
        
        # The seven_day_change_summary view already includes relevancy_score, so we can filter on it directly
        query = """
            SELECT * 
            FROM seven_day_change_summary
            WHERE relevancy_score >= 7
        """
        
        # Add filter for specific reference brand if provided
        if self.reference_brand:
            query += f" AND reference_brand = '{self.reference_brand}'"
            self.logger.info(f"Filtering data for reference brand: {self.reference_brand}")
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                self.logger.info(f"Retrieved {len(df)} price change records with relevancy score >= 7")
                return df
        except Exception as e:
            self.logger.error(f"Error fetching price change data: {e}")
            raise
    
    def calculate_weighted_average_by_brand(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate the weighted average price change by brand within each reference brand
        Weights are based on the review_count for each product
        
        Returns a DataFrame with weighted average price changes
        """
        self.logger.info("Calculating weighted average price changes by brand (weighted by review count)")
        
        # Group by reference_brand and competitor_brand
        result = []
        
        # Process each reference brand separately
        for ref_brand, ref_df in df.groupby('reference_brand'):
            self.logger.info(f"Processing reference brand: {ref_brand}")
            
            # Calculate weighted average for each competitor brand
            brand_summary = []
            for comp_brand, brand_df in ref_df.groupby('competitor_brand'):
                # Use review count as weight for calculating weighted average
                # Handle null/zero review counts
                brand_df = brand_df.copy()
                brand_df['weight'] = brand_df['avg_review_count_last_7_days'].fillna(0)
                
                # Skip brands with no valid review data
                if brand_df['weight'].sum() == 0:
                    continue
                
                # Calculate weighted average of price change percentage
                weighted_pct = (
                    (brand_df['price_change_percentage'] * brand_df['weight']).sum() / 
                    brand_df['weight'].sum()
                )
                
                # Count products for this brand
                product_count = len(brand_df)
                
                # Calculate by category for this brand
                # Check if category column exists, otherwise use reference_product
                if 'category' in brand_df.columns:
                    category_field = 'category'
                else:
                    category_field = 'reference_product'
                
                category_summary = []
                for category, cat_df in brand_df.groupby(category_field):
                    if cat_df['weight'].sum() > 0:
                        cat_weighted_pct = (
                            (cat_df['price_change_percentage'] * cat_df['weight']).sum() / 
                            cat_df['weight'].sum()
                        )
                        
                        category_summary.append({
                            'category': category,
                            'weighted_price_change_pct': cat_weighted_pct,
                            'product_count': len(cat_df),
                            'total_review_count': cat_df['avg_review_count_last_7_days'].sum()
                        })
                
                # Find category with highest weighted change (if any)
                highest_change_category = None
                if category_summary:
                    cat_df = pd.DataFrame(category_summary)
                    highest_idx = cat_df['weighted_price_change_pct'].abs().idxmax()
                    highest_change_category = cat_df.iloc[highest_idx].to_dict()
                
                # Add to brand summary
                brand_summary.append({
                    'reference_brand': ref_brand,
                    'competitor_brand': comp_brand,
                    'weighted_price_change_pct': weighted_pct,
                    'product_count': product_count,
                    'total_review_count': brand_df['avg_review_count_last_7_days'].sum(),
                    'total_price_volume': brand_df['avg_price_last_7_days'].sum(),
                    'highest_change_category': highest_change_category
                })
            
            # Convert to DataFrame
            if brand_summary:
                brand_df = pd.DataFrame(brand_summary)
                result.append(brand_df)
        
        # Combine all reference brand results
        if result:
            final_df = pd.concat(result).reset_index(drop=True)
            self.logger.info(f"Calculated weighted averages for {len(final_df)} brands")
            return final_df
        else:
            self.logger.warning("No valid data to calculate weighted averages")
            return pd.DataFrame()
    
    def highlight_top_bottom_brands(self, brand_df: pd.DataFrame, top_n: int = 3) -> Dict:
        """
        For each reference brand, identify the top and bottom brands by price change
        
        Returns a dictionary with reference brands as keys and lists of top/bottom brands as values
        Only includes brands with abs(weighted_price_change_pct) >= 2%
        Ensures 'top' brands have positive changes (>0) and 'bottom' brands have negative changes (<0)
        """
        self.logger.info(f"Identifying top and bottom {top_n} brands by price change")
        
        highlights = {}
        
        for ref_brand, ref_df in brand_df.groupby('reference_brand'):
            # Filter to only include brands with significant changes (>=2%)
            significant_df = ref_df[ref_df['weighted_price_change_pct'].abs() >= 2.0]
            
            # Skip if no significant brands
            if len(significant_df) == 0:
                self.logger.info(f"No brands with >=2% change for reference brand {ref_brand}")
                continue
            
            # Filter for positive and negative price changes separately
            positive_df = significant_df[significant_df['weighted_price_change_pct'] > 0]
            negative_df = significant_df[significant_df['weighted_price_change_pct'] < 0]
            
            # Sort positive changes descending (highest first)
            positive_df = positive_df.sort_values('weighted_price_change_pct', ascending=False)
            
            # Sort negative changes ascending (most negative first)
            negative_df = negative_df.sort_values('weighted_price_change_pct', ascending=True)
            
            # Get top N from each
            top_brands = positive_df.head(top_n)
            bottom_brands = negative_df.head(top_n)
            
            # Log any empty sections
            if len(top_brands) == 0:
                self.logger.info(f"No brands with positive price changes for reference brand {ref_brand}")
            if len(bottom_brands) == 0:
                self.logger.info(f"No brands with negative price changes for reference brand {ref_brand}")
            
            # Only create entry if at least one section has brands
            if len(top_brands) > 0 or len(bottom_brands) > 0:
                highlights[ref_brand] = {
                    'top': top_brands.to_dict('records'),
                    'bottom': bottom_brands.to_dict('records')
                }
                
                self.logger.info(f"Reference brand {ref_brand}: Identified {len(top_brands)} top (+) and {len(bottom_brands)} bottom (-) brands")
        
        return highlights
    
    def find_driving_products(self, df: pd.DataFrame, significant_brands: List[Tuple[str, str]], 
                              threshold_pct: float = 2.0, min_product_change_pct: float = 1.0) -> Dict:
        """
        For brands with significant price changes (>threshold_pct), find the products driving that change
        
        Args:
            df: The original data DataFrame
            significant_brands: List of (reference_brand, competitor_brand) tuples to analyze
            threshold_pct: The minimum percentage change to be considered significant
            min_product_change_pct: The minimum percentage change for individual products to be included
            
        Returns a dictionary mapping (reference_brand, competitor_brand) to lists of driving products
        Limited to 3 products per brand, filtered to those within 50% of average brand price change
        and sorted by review count (nulls last)
        """
        self.logger.info(f"Finding products driving changes for brands with >={threshold_pct}% change")
        self.logger.info(f"Only including products with >={min_product_change_pct}% price change")
        
        driving_products = {}
        
        for ref_brand, comp_brand in significant_brands:
            # Filter data for this specific brand
            brand_df = df[(df['reference_brand'] == ref_brand) & 
                           (df['competitor_brand'] == comp_brand)].copy()
            
            # Skip if no data
            if len(brand_df) == 0:
                continue
                
            # Filter to only include products with at least min_product_change_pct change
            brand_df = brand_df[brand_df['price_change_percentage'].abs() >= min_product_change_pct]
            
            # Skip if no products meet the threshold
            if len(brand_df) == 0:
                self.logger.info(f"No products with >={min_product_change_pct}% change for {comp_brand} ({ref_brand})")
                continue
            
            # Calculate average price change for the brand
            avg_price_change = brand_df['price_change_percentage'].mean()
            
            # Calculate bounds for filtering (within 50% of average)
            lower_bound = avg_price_change - (abs(avg_price_change) * 0.5)
            upper_bound = avg_price_change + (abs(avg_price_change) * 0.5)
            
            # Filter to products within 50% of average price change
            brand_df = brand_df[(brand_df['price_change_percentage'] >= lower_bound) & 
                               (brand_df['price_change_percentage'] <= upper_bound)]
            
            # Skip if no products meet the new filter
            if len(brand_df) == 0:
                self.logger.info(f"No products within 50% of average price change for {comp_brand} ({ref_brand})")
                continue
                
            # Handle nulls for sorting by review count (replace NaN with -1 for sorting)
            brand_df['sort_review_count'] = brand_df['avg_review_count_last_7_days'].fillna(-1)
            
            # Sort by review count descending (with nulls last)
            sorted_df = brand_df.sort_values('sort_review_count', ascending=False)
            
            # Take top 3 products by review count
            top_products = sorted_df.head(3)
            
            # Determine columns to include in output
            output_columns = ['product_name', 'price_change_percentage', 
                             'avg_price_last_7_days', 'avg_price_prior_7_days',
                             'avg_review_count_last_7_days', 'merchants', 'url']
            
            # Add category if it exists
            if 'category' in top_products.columns:
                output_columns.insert(1, 'category')
            elif 'reference_product' in top_products.columns:
                output_columns.insert(1, 'reference_product')
            
            # Store results
            key = (ref_brand, comp_brand)
            driving_products[key] = top_products[output_columns].to_dict('records')
            
            self.logger.info(f"Found {len(driving_products[key])} driving products for {comp_brand} ({ref_brand})")
        
        return driving_products
    
    def identify_significant_brands(self, brand_df: pd.DataFrame, threshold_pct: float = 2.0) -> List[Tuple[str, str]]:
        """
        Identify brands with price changes exceeding the threshold percentage
        
        Returns a list of (reference_brand, competitor_brand) tuples
        """
        significant = []
        
        for _, row in brand_df.iterrows():
            if abs(row['weighted_price_change_pct']) >= threshold_pct:
                significant.append((row['reference_brand'], row['competitor_brand']))
        
        self.logger.info(f"Identified {len(significant)} brands with significant price changes (>={threshold_pct}%)")
        return significant
    
    def generate_report(self, top_n: int = 3, threshold_pct: float = 2.0, min_product_change_pct: float = 1.0) -> Dict:
        """
        Generate a simplified price change report with just highlights and driving products
        - Top and bottom brands by price change (only those with >=2% change)
        - Driving products for brands with significant changes
        
        Returns a dictionary with the report data
        """
        self.logger.info("Generating price change report")
        
        # Fetch the data
        df = self.fetch_price_change_data()
        if len(df) == 0:
            self.logger.warning("No data available for report generation")
            return {"error": "No data available"}
        
        # Calculate weighted averages
        brand_df = self.calculate_weighted_average_by_brand(df)
        if len(brand_df) == 0:
            self.logger.warning("Could not calculate weighted averages")
            return {"error": "Calculation failed"}
        
        # Identify top and bottom brands (only those with >= 2% change)
        highlights = self.highlight_top_bottom_brands(brand_df, top_n)
        
        # Identify brands with significant changes
        significant_brands = self.identify_significant_brands(brand_df, threshold_pct)
        
        # Find driving products for significant brands
        driving_products = self.find_driving_products(df, significant_brands, threshold_pct, min_product_change_pct)
        
        # Compile the simplified report
        report = {
            "generated_at": datetime.now().isoformat(),
            "highlights": highlights,
            "driving_products": {f"{rb}|{cb}": products 
                                for (rb, cb), products in driving_products.items()}
        }
        
        self.logger.info("Report generation complete")
        return report

def main():
    """Main function to generate and save the report"""
    # Setup argument parser
    parser = argparse.ArgumentParser(description='Generate price change report')
    parser.add_argument('--brand', '-b', dest='reference_brand', 
                        help='Filter report to a specific reference brand')
    parser.add_argument('--min-change', '-m', dest='min_change', type=float, default=1.0,
                        help='Minimum percentage change for products to be included (default: 1.0)')
    parser.add_argument('--threshold', '-t', dest='threshold', type=float, default=2.0,
                        help='Threshold percentage for significant brand changes (default: 2.0)')
    parser.add_argument('--top', '-n', dest='top_n', type=int, default=3,
                        help='Number of top/bottom brands to highlight (default: 3)')
    
    args = parser.parse_args()
    
    logger = configure_logger("price_change_report")
    logger.info("Starting price change report generation")
    
    if args.reference_brand:
        logger.info(f"Filtering report for reference brand: {args.reference_brand}")
    
    try:
        # Create report generator with optional reference brand filter
        generator = PriceChangeReportGenerator(reference_brand=args.reference_brand)
        
        # Generate the report with command line parameters
        report = generator.generate_report(
            top_n=args.top_n,
            threshold_pct=args.threshold,
            min_product_change_pct=args.min_change
        )
        
        # Save report to a file (future enhancement: could save to database or send via email)
        import json
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
        os.makedirs(output_dir, exist_ok=True)
        
        # Include reference brand in filename if specified
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        brand_suffix = f"_{args.reference_brand}" if args.reference_brand else ""
        output_file = os.path.join(output_dir, f"price_change_report{brand_suffix}_{timestamp}.json")
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Report saved to {output_file}")
        print(f"Report successfully generated and saved to {output_file}")
        
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        print(f"Error generating report: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 