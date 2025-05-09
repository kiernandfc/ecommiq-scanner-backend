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

Dependencies:
- reportlab (install with: pip install reportlab)
"""

import os
import pandas as pd
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError, BadRequestError
import time
import random
import json
from io import BytesIO

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.postgresql import PostgreSQLDatabase
from utils.logger import configure_logger

# Load environment variables
load_dotenv()

# --- Constants ---
# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "o3" # Using o3 model as requested
GPT_SUMMARY_MODEL = "gpt-4.1" # Using GPT-4.1 for summary as specified
MAX_RETRIES = 3
INITIAL_DELAY = 1.0
BACKOFF_FACTOR = 2.0
JITTER_FACTOR = 0.1

# Date intervals for price change analysis
CURRENT_PERIOD_DAYS = 7  # Number of days for current period (last N days)
PREVIOUS_PERIOD_DAYS = 7  # Number of days for previous period (N days before current period)
TOTAL_ANALYSIS_DAYS = CURRENT_PERIOD_DAYS + PREVIOUS_PERIOD_DAYS  # Total days to analyze

# Schema for price change rationale
PRICE_CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "rationales": {
            "type": "array",
            "description": "An array of price change rationales for the products.",
            "items": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "The exact name of the product as provided in the input."
                    },
                    "rationale": {
                        "type": "string",
                        "description": "A single sentence explanation for the possible reason behind the price change."
                    },
                    "confirmed_price": {
                        "type": ["number", "null"],
                        "description": "Current price (if different than last 7 days). Value from Google Shopping if it differs from the provided avg_price_last_7_days. Null if not different or not found."
                    }
                },
                "required": ["product_name", "rationale", "confirmed_price"],
                "additionalProperties": False
            }
        }
    },
    "required": ["rationales"],
    "additionalProperties": False
}
PRICE_CHANGE_SCHEMA_NAME = "price_change_rationale_response"

class PriceChangeReportGenerator:
    """Generates price change reports based on seven_day_change_summary view"""
    
    def __init__(self, reference_brand: str = None, debug: bool = False):
        """
        Initialize the report generator with database connection
        
        Args:
            reference_brand: Optional filter for a specific reference brand
            debug: Whether to enable debug-level logging
        """
        # Configure logger
        self.logger = logging.getLogger(f"{__name__}.PriceChangeReportGenerator")
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        
        # Print directly to confirm logger is working
        print("Price Change Report Generator initializing - Log test")
        self.logger.info("Price Change Report Generator initialized")
        
        self.db = PostgreSQLDatabase()
        self.engine = self.db.engine
        self.reference_brand = reference_brand
        self.openai_client = None
        if OPENAI_API_KEY:
            try:
                self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
                self.logger.info("OpenAI client initialized successfully.")
                print("OpenAI client initialized successfully.")
            except Exception as e:
                error_msg = f"Failed to initialize OpenAI client: {e}"
                self.logger.error(error_msg)
                print(f"ERROR: {error_msg}")
        
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
                brand_df['weight'] = brand_df['avg_review_count_last_7_days'].fillna(0).replace(0, 1)
                
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
    
    def get_price_change_rationales(self, products_list: List[Dict]) -> List[Dict]:
        """
        For a list of products, get AI-generated rationales for price changes using OpenAI API.
        Uses web search capability to analyze product URLs for better insights.
        
        Args:
            products_list: A list of product dictionaries, each containing product details
            
        Returns:
            A list of dictionaries with products enriched with 'possible_rationale' field
        """
        if not self.openai_client:
            error_msg = "OpenAI client not initialized. Cannot get price change rationales."
            self.logger.warning(error_msg)
            print(f"WARNING: {error_msg}")
            return products_list
            
        if not products_list:
            return []
        
        log_msg = f"Generating AI rationales for {len(products_list)} products with web search capability"
        self.logger.info(log_msg)
        print(log_msg)
            
        # Create a copy to avoid modifying the original
        enriched_products = products_list.copy()
            
        # Format product info for the prompt
        product_list_str = "\n\n".join([
            f"Product: {p['product_name']}\n"
            f"Category: {p.get('category', 'Unknown')}\n"
            f"Price Change: {p['price_change_percentage']:.2f}%\n"
            f"Current Price: ${p['avg_price_last_7_days']}\n"
            f"Previous Price: ${p['avg_price_prior_7_days']}\n"
            f"Review Count: {p['avg_review_count_last_7_days']}\n"
            f"URL: {p['url']}"
            for p in products_list
        ])
            
        system_prompt = """You are an AI assistant analyzing product price changes.
Your goal is to provide a brief, single-sentence explanation for what might be driving 
the price change for each product based on the provided information and URLs.
Attempt to distinguish between temporary changes (more likely) e.g. promotions implemented or expiring or normal price volatility in the google shopping feed, or indicate if the price change is potentially a permanent one.

YOU HAVE ACCESS TO A WEB SEARCH TOOL. Use it to visit the provided URLs and gather information
about current prices, promotions, and other factors that might explain the price changes.

IMPORTANT NOTES ON GOOGLE SHOPPING LINKS:
1. The provided URLs are Google Shopping links which may redirect to merchant sites
2. When using the web search tool, focus on finding current price, regular price, and any discounts/promotions
3. Compare the current price you find online with the "Current Price" and "Previous Price" in the product details
4. Look for signs of sales events, promotions, or merchant-specific price changes; google shopping may indicate if a price is above or below the normal price.
5. IMPORTANT: If the current price you find on Google Shopping differs from the "Current Price" in the product details, 
   include this different price in the "confirmed_price" field in your response. This should be a numeric value only, 
   without currency symbols.
6. IMPORTANT: If you find a different price on Google Shopping, your rationale should explain the change between the 
   "Previous Price" and your confirmed Google Shopping price, NOT the change between "Previous Price" and "Current Price".

Output the rationales as a JSON object containing a single key 'rationales', which is an array of objects.
Each object in the array must have:
- 'product_name' (the exact product name provided in the input)
- 'rationale' (a single sentence explanation)
- 'confirmed_price' (current price (if different than last 7 days) - numeric value found on Google Shopping IF it differs 
   from the provided "Current Price", otherwise null)

Example: If product details show "Current Price: $139.0" but you find the price on Google Shopping is $129.99, 
include "confirmed_price": 129.99 in your response and base your rationale on the change between "Previous Price" and $129.99.

Be concise, analytical, and specific in your rationales, focusing on the most likely cause of the observed price change."""
            
        user_prompt = f"""Please take a look at these products and see if you can ascertain what might 
be driving the reported price change based on visiting the specified URLs.

Please keep your answer concise limited to only a single sentence per product.

Product Details:
{product_list_str}"""
            
        current_delay = INITIAL_DELAY
        for attempt in range(MAX_RETRIES):
            try:
                # Use the Responses API endpoint for structured output
                response = self.openai_client.responses.create(
                    model=OPENAI_MODEL,
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    tools=[{"type": "web_search_preview"}],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": PRICE_CHANGE_SCHEMA_NAME,
                            "schema": PRICE_CHANGE_SCHEMA,
                            "strict": True
                        }
                    },
                    max_output_tokens=150 * len(products_list)
                )
                
                # Check response status and content
                if response.status == "completed":
                    raw_json = response.output_text
                    if not raw_json:
                        self.logger.warning("Empty output_text received from OpenAI API")
                        return enriched_products
                    
                    try:
                        result = json.loads(raw_json)
                        rationales_list = result.get("rationales", [])
                        
                        # Create mapping from product name to rationale and confirmed price
                        rationales_map = {}
                        for item in rationales_list:
                            if "product_name" in item and "rationale" in item:
                                product_name = item.get("product_name")
                                rationales_map[product_name] = {
                                    "rationale": item.get("rationale"),
                                    "confirmed_price": item.get("confirmed_price")
                                }
                        
                        # Keep track of price discrepancies
                        price_discrepancies = 0
                        
                        # Add rationales and confirmed prices to the enriched products
                        for product in enriched_products:
                            product_name = product['product_name']
                            
                            if product_name in rationales_map:
                                # Add the rationale
                                product['possible_rationale'] = rationales_map[product_name]["rationale"]
                                
                                # Check if there's a confirmed price that differs from product details
                                confirmed_price = rationales_map[product_name]["confirmed_price"]
                                if confirmed_price is not None:
                                    current_price = product.get('avg_price_last_7_days')
                                    prior_price = product.get('avg_price_prior_7_days', 0)
                                    
                                    # Add confirmed price to the product
                                    product['confirmed_price'] = confirmed_price
                                    
                                    # Calculate new price change percentage based on confirmed price
                                    if prior_price > 0:  # Avoid division by zero
                                        original_change_pct = product.get('price_change_percentage')
                                        new_change_pct = ((confirmed_price - prior_price) / prior_price) * 100
                                        product['price_change_percentage'] = new_change_pct
                                    
                                    # Log the discrepancy
                                    price_discrepancies += 1
                                    price_diff = confirmed_price - current_price
                                    self.logger.info(f"Price discrepancy found for '{product_name}': " 
                                                   f"API reports ${current_price}, Google Shopping shows ${confirmed_price} "
                                                   f"(Diff: ${price_diff:.2f})")
                                    if prior_price > 0:
                                        self.logger.info(f"  Updated price change: {new_change_pct:.2f}% (was: {original_change_pct:.2f}%)")
                            else:
                                product['possible_rationale'] = "No rationale provided by AI analysis."
                        
                        success_msg = f"Successfully added rationales for {len(rationales_map)} products with {price_discrepancies} price discrepancies"
                        self.logger.info(success_msg)
                        print(success_msg)
                        return enriched_products
                        
                    except json.JSONDecodeError:
                        self.logger.error(f"Failed to decode JSON response. Raw JSON: {raw_json}")
                    except Exception as e:
                        self.logger.error(f"Error processing JSON response: {e}")
                
                elif response.status == "incomplete":
                    reason = response.incomplete_details.reason if hasattr(response, 'incomplete_details') else "unknown"
                    self.logger.warning(f"OpenAI response incomplete (reason: {reason})")
                else:
                    self.logger.error(f"OpenAI response status was '{response.status}'")
                
                # If we got here, there was a problem with the response
                if attempt < MAX_RETRIES - 1:
                    delay = current_delay * (BACKOFF_FACTOR ** attempt)
                    jitter = random.uniform(0, delay * JITTER_FACTOR)
                    sleep_time = delay + jitter
                    self.logger.warning(f"Retrying in {sleep_time:.2f} seconds... (Attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(sleep_time)
                
            except RateLimitError:
                if attempt < MAX_RETRIES - 1:
                    delay = current_delay * (BACKOFF_FACTOR ** attempt)
                    jitter = random.uniform(0, delay * JITTER_FACTOR)
                    sleep_time = delay + jitter
                    self.logger.warning(f"Rate limit exceeded. Retrying in {sleep_time:.2f} seconds... (Attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(sleep_time)
                else:
                    self.logger.error(f"Max retries ({MAX_RETRIES}) exceeded for rate limit error.")
            except BadRequestError as e:
                self.logger.error(f"OpenAI BadRequestError (check schema or prompt): {e}")
                break
            except APIError as e:
                self.logger.error(f"OpenAI API error: {e}")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error calling OpenAI API: {e}")
                break
                
        # If we get here, we've failed after all retries
        return enriched_products
    
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
            brand_df['sort_review_count'] = brand_df['avg_review_count_last_7_days'].fillna(0).replace(0, 1)
            
            # Sort by review count descending (with nulls last)
            sorted_df = brand_df.sort_values('sort_review_count', ascending=False)
            
            # Take top 10 products by review count
            top_products = sorted_df.head(5)
            
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
            products_list = top_products[output_columns].to_dict('records')
            
            # Enrich products with AI-generated rationales if OpenAI client is available
            enriched_products = self.get_price_change_rationales(products_list)
            driving_products[key] = enriched_products
            
            self.logger.info(f"Found {len(driving_products[key])} driving products for {comp_brand} ({ref_brand})")
        
        return driving_products
    
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
        
        # Extract significant brands from highlights instead of calling identify_significant_brands
        significant_brands = []
        for ref_brand, brand_data in highlights.items():
            # Add brands from the 'top' section (price increases)
            if 'top' in brand_data:
                for brand_info in brand_data['top']:
                    significant_brands.append((brand_info['reference_brand'], brand_info['competitor_brand']))
            
            # Add brands from the 'bottom' section (price decreases)
            if 'bottom' in brand_data:
                for brand_info in brand_data['bottom']:
                    significant_brands.append((brand_info['reference_brand'], brand_info['competitor_brand']))
        
        self.logger.info(f"Identified {len(significant_brands)} brands with significant price changes (>={threshold_pct}%)")
        
        # Find driving products for significant brands
        driving_products = self.find_driving_products(df, significant_brands, threshold_pct, min_product_change_pct)
        
        # Filter highlights to only include brands that have driving products
        filtered_highlights = {}
        driving_product_keys = set(f"{rb}|{cb}" for rb, cb in driving_products.keys())
        
        for ref_brand, brand_data in highlights.items():
            # Filter top brands
            filtered_top = []
            if 'top' in brand_data:
                filtered_top = [
                    brand for brand in brand_data['top'] 
                    if f"{brand['reference_brand']}|{brand['competitor_brand']}" in driving_product_keys
                ]
            
            # Filter bottom brands
            filtered_bottom = []
            if 'bottom' in brand_data:
                filtered_bottom = [
                    brand for brand in brand_data['bottom'] 
                    if f"{brand['reference_brand']}|{brand['competitor_brand']}" in driving_product_keys
                ]
            
            # Only keep the reference brand if it has at least one entry
            if filtered_top or filtered_bottom:
                filtered_highlights[ref_brand] = {}
                if filtered_top:
                    filtered_highlights[ref_brand]['top'] = filtered_top
                if filtered_bottom:
                    filtered_highlights[ref_brand]['bottom'] = filtered_bottom
        
        # Log filtering details
        original_brand_count = sum(
            len(brand_data.get('top', [])) + len(brand_data.get('bottom', []))
            for brand_data in highlights.values()
        )
        
        filtered_brand_count = sum(
            len(brand_data.get('top', [])) + len(brand_data.get('bottom', []))
            for brand_data in filtered_highlights.values()
        )
        
        removed_count = original_brand_count - filtered_brand_count
        self.logger.info(f"Filtered out {removed_count} brands from highlights that don't have driving products")
        
        # Compile the simplified report
        report = {
            "generated_at": datetime.now().isoformat(),
            "highlights": filtered_highlights,
            "driving_products": {f"{rb}|{cb}": products 
                                for (rb, cb), products in driving_products.items()}
        }
        
        self.logger.info("Report generation complete")
        return report

def generate_html_report(json_report: Dict, output_file_path: str) -> str:
    """
    Generate a human-readable HTML report from the JSON data using OpenAI's GPT-4.1 model.
    Calls the API for each brand separately to generate HTML sections that match the template.
    
    Args:
        json_report: The JSON report data
        output_file_path: Path to the JSON output file (used to name the summary file)
        
    Returns:
        Path to the generated summary report file
    """
    logger = logging.getLogger(f"{__name__}.generate_html_report")
    logger.info("Generating HTML report using OpenAI GPT-4.1 for each brand section")
    
    if not OPENAI_API_KEY:
        logger.warning("OpenAI API key not found. Cannot generate HTML report.")
        return None
    
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized for HTML generation")
        
        # Define paths for template files
        script_dir = os.path.dirname(os.path.abspath(__file__))
        header_template_path = os.path.join(script_dir, "report_header.html")
        section_template_path = os.path.join(script_dir, "report_section.html")
        footer_template_path = os.path.join(script_dir, "report_footer.html")
        
        # Read template files
        with open(header_template_path, "r", encoding="utf-8") as f:
            header_template = f.read()
        
        with open(section_template_path, "r", encoding="utf-8") as f:
            section_template = f.read()
            
        with open(footer_template_path, "r", encoding="utf-8") as f:
            footer_template = f.read()
        
        # Get database statistics for the summary section
        try:
            db = PostgreSQLDatabase()
            total_products = db.get_total_catalog_count()
            unique_queries = db.get_unique_search_query_count()
            logger.info(f"Retrieved statistics from database: {total_products} products across {unique_queries} categories")
        except Exception as e:
            logger.warning(f"Failed to get database statistics: {e}")
            total_products = "many"
            unique_queries = "multiple"
            
        # Create the summary section with improved styling
        current_datetime = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        summary_html = f"""<div class="report-summary" style="padding: 20px; font-style: italic;">
    This report was generated on {current_datetime} based on monitoring {total_products:,} products rated at a relevancy of 7/10 or higher for reference brands across {unique_queries:,} categories of products.
</div>"""
        
        # Get all brands to process from both highlights and price index data
        all_brands = set()
        
        # Add brands from highlights
        if 'highlights' in json_report:
            all_brands.update(set(json_report['highlights'].keys()))
            
        # Add brands from price index data
        if 'brand_category_price_index' in json_report:
            all_brands.update(set(json_report['brand_category_price_index'].keys()))
            
        if not all_brands:
            logger.warning("No brands found in the report")
            return None
            
        logger.info(f"Processing {len(all_brands)} brands: {', '.join(all_brands)}")
        
        # Process each brand separately using OpenAI
        brand_sections = []
        processed_brands = set()  # Track brands we've already processed to avoid duplicates
        
        # Convert to sorted list to process brands alphabetically
        sorted_brands = sorted(list(all_brands))
        
        for brand in sorted_brands:
            # Skip if we've already processed this brand
            if brand in processed_brands:
                logger.info(f"Skipping already processed brand: {brand}")
                continue
                
            logger.info(f"Generating section for brand: {brand}")
            processed_brands.add(brand)  # Mark as processed
            
            # Extract data for this brand
            brand_data = {
                'reference_brand': brand,
                'highlights': {}, 
                'price_index': json_report.get('brand_category_price_index', {}).get(brand, None)
            }
            
            # Copy highlights for this brand if available
            has_significant_movements = False
            if brand in json_report.get('highlights', {}):
                brand_data['highlights'] = json_report['highlights'][brand]
                has_significant_movements = True
            
            # Prepare driving products data if available
            driving_products = {}
            for key, products in json_report.get('driving_products', {}).items():
                ref_brand, comp_brand = key.split('|')
                if ref_brand == brand:
                    driving_products[comp_brand] = products
                    
            brand_data['driving_products'] = driving_products
            
            # For brands without significant movements, create a simple template instead of calling OpenAI
            if not has_significant_movements and brand_data['price_index']:
                # Get price index data
                price_change_pct = brand_data['price_index'].get('avg_price_index_change_pct', 0)
                current_days = brand_data['price_index'].get('current_period_days', CURRENT_PERIOD_DAYS)
                previous_days = brand_data['price_index'].get('previous_period_days', PREVIOUS_PERIOD_DAYS)
                
                # Determine price direction for styling
                direction = "expensive" if price_change_pct > 0 else "cheaper"
                tag_class = "expensive" if price_change_pct > 0 else "cheaper"
                icon = "fa-arrow-up" if price_change_pct > 0 else "fa-arrow-down"
                
                # Create a simple section
                simple_section = f"""<section class="brand-section">
    <h2>{brand}</h2>
    <div class="summary">
        Over the last {current_days} days, {brand}'s overall price index <span class="tag {tag_class}"><i class="fa-solid {icon}"></i> became more {direction} ({price_change_pct:.1f}%)</span> compared to the previous {previous_days} days.
    </div>
    <div class="bullets">
        <ul>
            <li>No meaningful competitor price movements detected during this period.</li>
        </ul>
    </div>
    <div style="overflow-x:auto;">
    <table class="product-table">
        <thead>
            <tr>
                <th style="min-width:180px;">Product</th>
                <th style="width:60px;">Link</th>
                <th style="width:70px;">Reviews</th>
                <th style="width:95px;">Price Before</th>
                <th style="width:95px;">Price After</th>
                <th style="width:110px;">Current Price</th>
                <th style="width:50px;">Change</th>
                <th style="min-width:220px;">Rationale</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td colspan="8" style="text-align:center; padding:20px;">No significant price changes detected for competitors of {brand}.</td>
            </tr>
        </tbody>
    </table>
    </div>
</section>"""
                
                brand_sections.append(simple_section)
                logger.info(f"Generated simple section for {brand} with no significant movements")
                continue
                
            # Skip brands with no price index data and no significant movements
            if not driving_products and not brand_data['price_index']:
                logger.warning(f"No useful data for {brand}, skipping")
                continue
                
            # For brands with significant movements, continue with OpenAI generation
            # Convert brand data to string format for the API
            try:
                brand_json = json.dumps(brand_data, indent=2)
            except Exception as e:
                logger.error(f"Error converting brand data to JSON: {e}")
                continue
            
            # Prepare prompt for OpenAI API
            system_prompt = f"""You are an AI assistant that transforms JSON data about price changes into HTML sections for a report.
Your task is to create a formatted HTML section for a given brand, following the provided template structure exactly.

Here's the template structure:
```
{section_template}
```

When generating the HTML:
1. Replace {{reference_brand}} with the brand name
2. Create an appropriate summary_text about overall price changes, including appropriate tags for price direction
3. Generate meaningful bullet points for each competitor brand, extracting common themes from product rationales
4. Generate table rows for each product with all required fields

The summary text should mention both the timeframe (current period days and previous period days) and the overall price direction based on the brand_category_price_index.
If there is no brand_category_price_index data provided, please ignore this section.  For price direction tags, use:
- <span class="tag expensive"><i class="fa-solid fa-arrow-up"></i> became more expensive (+X.X%)</span>
- <span class="tag cheaper"><i class="fa-solid fa-arrow-down"></i> became cheaper (-X.X%)</span>

Each bullet point should provide a concise summary of why prices changed for that competitor brand.
For the table, ensure all columns are properly filled:
- Product name
- Link (formatted as <a> tag)
- Reviews (number only)
- Price Before (formatted as $X.XX)
- Price After (formatted as $X.XX)
- Current Price (if different from Price After)
- Change direction (using proper icon and class)
- Rationale (short explanation)

Format your response as valid HTML only, with no additional explanation."""

            user_prompt = f"""Generate the HTML section for this brand's price change report using the provided data.

Brand Data:
{brand_json}

Make sure to:
1. Format price change percentages with 1 decimal place (e.g., +0.6%)
2. Use the appropriate tag classes for price changes (expensive for increases, cheaper for decreases)
3. Generate meaningful bullet points summarizing price change patterns for each competitor brand
4. Format all prices as dollars with 2 decimal places (e.g., $499.99)
5. Include all products in the table with their rationales
6. Follow the exact HTML structure from the template"""

            # Attempt to call the OpenAI API with retries
            max_retries = MAX_RETRIES
            current_delay = INITIAL_DELAY
            
            for attempt in range(max_retries):
                try:
                    response = client.chat.completions.create(
                        model=GPT_SUMMARY_MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.5,
                        max_tokens=20000
                    )
                    
                    # Extract the HTML content from the response
                    section_html = response.choices[0].message.content.strip()
                    
                    # Validate that the response is proper HTML
                    if "<section" in section_html and "</section>" in section_html:
                        brand_sections.append(section_html)
                        logger.info(f"Successfully generated HTML section for {brand}")
                        break
                    else:
                        logger.warning(f"Invalid HTML structure received for {brand}, retrying...")
                        if attempt == max_retries - 1:
                            logger.error(f"Failed to generate valid HTML for {brand} after {max_retries} attempts")
                
                except RateLimitError:
                    if attempt < max_retries - 1:
                        delay = current_delay * (BACKOFF_FACTOR ** attempt)
                        jitter = random.uniform(0, delay * JITTER_FACTOR)
                        sleep_time = delay + jitter
                        logger.warning(f"Rate limit exceeded. Retrying in {sleep_time:.2f} seconds... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"Max retries ({max_retries}) exceeded for rate limit error.")
                except Exception as e:
                    logger.error(f"Error calling OpenAI API for {brand}: {e}")
                    break
        
        # Check if we successfully generated any brand sections
        if not brand_sections:
            logger.error("No brand sections were successfully generated")
            return None
            
        # Create output filename for HTML
        base_filename = os.path.splitext(os.path.basename(output_file_path))[0]
        output_dir = os.path.dirname(output_file_path)
        html_file_path = os.path.join(output_dir, f"{base_filename}_summary.html")
        
        # Assemble the complete HTML report
        complete_html = header_template + summary_html
        
        for section in brand_sections:
            complete_html += section
            
        complete_html += footer_template
        
        # Write the HTML to a file
        with open(html_file_path, "w", encoding="utf-8") as f:
            f.write(complete_html)
            
        logger.info(f"HTML report saved to {html_file_path}")
        print(f"SUCCESS: HTML report saved to {html_file_path}")
        
        return html_file_path
        
    except Exception as e:
        error_msg = f"Error generating HTML report: {e}"
        logger.error(error_msg)
        print(f"ERROR: {error_msg}")
        return None

def fetch_brand_category_price_index(reference_brand: str = None) -> Dict:
    """
    Query the brand_category_price_index view to get the price index data
    for the specified reference brand across its categories.
    
    Args:
        reference_brand: The reference brand to filter on (optional)
        
    Returns:
        Dictionary with brand level average price index change percentage
    """
    logger = logging.getLogger(f"{__name__}.fetch_brand_category_price_index")
    logger.info(f"Fetching brand category price index data for {reference_brand if reference_brand else 'all brands'}")
    
    try:
        # Create PostgreSQL connection
        db = PostgreSQLDatabase()
        engine = db.engine
        
        # Construct query using actual columns from the view and configurable date intervals
        query = f"""
        WITH last_{CURRENT_PERIOD_DAYS}_days AS (
            SELECT 
                reference_brand,
                category,
                AVG(price_index) AS avg_price_index,
                AVG(reference_price) AS avg_reference_price,
                AVG(avg_competitor_price) AS avg_competitor_price,
                COUNT(DISTINCT report_date) AS day_count
            FROM 
                brand_category_price_index
            WHERE 
                report_date > CURRENT_DATE - INTERVAL '{CURRENT_PERIOD_DAYS} days'
        """
        
        # Add reference brand filter if specified
        if reference_brand:
            query += f" AND reference_brand = '{reference_brand}'"
            
        query += f"""
            GROUP BY 
                reference_brand, category
        ),
        prior_{PREVIOUS_PERIOD_DAYS}_days AS (
            SELECT 
                reference_brand,
                category,
                AVG(price_index) AS avg_price_index,
                AVG(reference_price) AS avg_reference_price,
                AVG(avg_competitor_price) AS avg_competitor_price,
                COUNT(DISTINCT report_date) AS day_count
            FROM 
                brand_category_price_index
            WHERE 
                report_date <= CURRENT_DATE - INTERVAL '{CURRENT_PERIOD_DAYS} days'
                AND report_date > CURRENT_DATE - INTERVAL '{TOTAL_ANALYSIS_DAYS} days'
        """
        
        # Add reference brand filter if specified
        if reference_brand:
            query += f" AND reference_brand = '{reference_brand}'"
            
        query += """
            GROUP BY 
                reference_brand, category
        )
        SELECT 
            l.reference_brand,
            l.category,
            l.avg_price_index AS price_index_current_period,
            p.avg_price_index AS price_index_prior_period,
            l.avg_reference_price AS reference_price_current_period,
            p.avg_reference_price AS reference_price_prior_period,
            l.avg_competitor_price AS competitor_price_current_period,
            p.avg_competitor_price AS competitor_price_prior_period
        FROM 
            last_"""+ str(CURRENT_PERIOD_DAYS) + """_days l
        JOIN 
            prior_"""+ str(PREVIOUS_PERIOD_DAYS) + """_days p ON l.reference_brand = p.reference_brand AND l.category = p.category
        ORDER BY 
            l.reference_brand, l.category
        """
        
        # Execute the query
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        
        # Return empty dictionary if no data
        if len(df) == 0:
            logger.warning("No brand category price index data found")
            return {}
            
        # Calculate price change percentage for the price index
        df['price_index_change_pct'] = ((df['price_index_current_period'] - df['price_index_prior_period']) / 
                                        df['price_index_prior_period']) * 100
        
        # Group by reference_brand and calculate average price_index_change_pct
        brand_avg_df = df.groupby('reference_brand')['price_index_change_pct'].mean().reset_index()
        brand_avg_df.rename(columns={'price_index_change_pct': 'avg_price_index_change_pct'}, inplace=True)
        
        # Format the results as a simple dictionary with brand as key and average change as value
        result = {}
        for _, row in brand_avg_df.iterrows():
            brand = row['reference_brand']
            result[brand] = {
                'avg_price_index_change_pct': row['avg_price_index_change_pct'],
                'current_period_days': CURRENT_PERIOD_DAYS,
                'previous_period_days': PREVIOUS_PERIOD_DAYS
            }
            
        logger.info(f"Calculated average price index change for {len(result)} brands")
        return result
        
    except Exception as e:
        error_msg = f"Error fetching brand category price index: {e}"
        logger.error(error_msg)
        print(f"ERROR: {error_msg}")
        return {}

def main():
    """Main function to generate and save the report"""
    # Declare global variables at the beginning of the function
    global CURRENT_PERIOD_DAYS, PREVIOUS_PERIOD_DAYS, TOTAL_ANALYSIS_DAYS
    
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
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('--current-days', type=int, default=CURRENT_PERIOD_DAYS,
                        help=f'Number of days for current period analysis (default: {CURRENT_PERIOD_DAYS})')
    parser.add_argument('--previous-days', type=int, default=PREVIOUS_PERIOD_DAYS,
                        help=f'Number of days for previous period analysis (default: {PREVIOUS_PERIOD_DAYS})')
    
    args = parser.parse_args()
    
    # Update global period variables if specified in command line
    if args.current_days != CURRENT_PERIOD_DAYS:
        CURRENT_PERIOD_DAYS = args.current_days
        print(f"Current period set to {CURRENT_PERIOD_DAYS} days")
    
    if args.previous_days != PREVIOUS_PERIOD_DAYS:
        PREVIOUS_PERIOD_DAYS = args.previous_days
        print(f"Previous period set to {PREVIOUS_PERIOD_DAYS} days")
    
    # Update total days
    TOTAL_ANALYSIS_DAYS = CURRENT_PERIOD_DAYS + PREVIOUS_PERIOD_DAYS
    
    # Configure logging
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=logging_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("price_change_report.log")
        ]
    )
    
    logger = logging.getLogger("price_change_report")
    logger.info("Starting price change report generation")
    logger.info(f"Analysis periods: Current={CURRENT_PERIOD_DAYS} days, Previous={PREVIOUS_PERIOD_DAYS} days")
    
    if args.reference_brand:
        print(f"Filtering report for reference brand: {args.reference_brand}")
        logger.info(f"Filtering report for reference brand: {args.reference_brand}")
    
    try:
        # Create report generator with optional reference brand filter
        print("Initializing report generator...")
        generator = PriceChangeReportGenerator(reference_brand=args.reference_brand, debug=args.debug)
        
        # Generate the report with command line parameters
        print("Generating report...")
        report = generator.generate_report(
            top_n=args.top_n,
            threshold_pct=args.threshold,
            min_product_change_pct=args.min_change
        )
        
        # Fetch brand category price index data
        print("Fetching brand category price index data...")
        brand_category_data = fetch_brand_category_price_index(args.reference_brand)
        
        # Add brand category price index data to the report
        if brand_category_data:
            report["brand_category_price_index"] = brand_category_data
            print(f"Added price index data for {len(brand_category_data)} brands")
        
        # Save report to a file
        print("Saving report to file...")
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
        os.makedirs(output_dir, exist_ok=True)
        
        # Include reference brand in filename if specified
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        brand_suffix = f"_{args.reference_brand}" if args.reference_brand else ""
        output_file = os.path.join(output_dir, f"price_change_report{brand_suffix}_{timestamp}.json")
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        success_msg = f"Report saved to {output_file}"
        logger.info(success_msg)
        print(f"SUCCESS: {success_msg}")
        
        # Generate human-readable summary report using the new function
        print("Generating human-readable HTML summary report...")
        summary_file = generate_html_report(report, output_file)
        if summary_file:
            logger.info(f"Human-readable HTML report saved to {summary_file}")
        
    except Exception as e:
        error_msg = f"Error generating report: {e}"
        logger.error(error_msg, exc_info=True)
        print(f"ERROR: {error_msg}")
        sys.exit(1)

if __name__ == "__main__":
    main() 