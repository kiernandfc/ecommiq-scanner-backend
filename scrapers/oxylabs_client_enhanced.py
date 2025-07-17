import os
import requests
from typing import Dict, Any
from datetime import datetime
import logging
import json

from utils.logger import configure_logger

class OxylabsClient:
    def __init__(self):
        # Get logger instance, level is inherited from root config set in main.py
        self.logger = configure_logger(f"{__name__}.OxylabsClient")
        
        self.username = os.getenv('OXYLABS_USERNAME')
        self.password = os.getenv('OXYLABS_PASSWORD')
        
        if not self.username or not self.password:
            self.logger.error("Oxylabs credentials not found in environment variables (OXYLABS_USERNAME, OXYLABS_PASSWORD)")
            raise ValueError("Oxylabs credentials not configured")
            
        # self.logger.debug("OxylabsClient initialized") # Filtered if root is INFO
        
        self.base_url = 'https://realtime.oxylabs.io/v1/queries'

    def search_google_shopping(self, query: str) -> Dict[str, Any]:
        """
        Execute a Google Shopping search using Oxylabs API
        
        Args:
            query: Search term to query
            
        Returns:
            Dict containing the parsed results from Oxylabs
        """
        self.logger.debug(f"Executing Google Shopping search for query: {query}")
        
        payload = {
            'source': 'google_shopping_search',
            'query': query,
            'geo_location': 'US',
            'locale': 'en-us',
            'parse': True
        }

        return self._make_request(payload)

    def get_product_details(self, url: str) -> Dict[str, Any]:
        """
        Get details for a specific product URL using Oxylabs API
        
        Args:
            url: The Google Shopping product URL to scrape
            
        Returns:
            Dict containing the parsed product details
        """
        self.logger.debug(f"Getting product details for URL: {url}")
        
        payload = {
            'source': 'google_shopping_product',
            'geo_location': 'US',
            'url': url,
            'locale': 'en-us',
            'parse': True
        }

        return self._make_request(payload)

    def _make_request(self, payload):
        """Make a request to Oxylabs API"""
        self.logger.debug(f"Sending request to Oxylabs API with payload: {payload}")
        response = requests.post(
            self.base_url,
            auth=(self.username, self.password),
            json=payload
        )
        
        if response.status_code != 200:
            # Format headers for better readability
            headers_str = '\n'.join([f"    {k}: {v}" for k, v in response.headers.items()])
            
            # Create detailed error message with status code, response text and headers
            error_msg = f"Oxylabs API error: {response.status_code} - {response.text}"
            detailed_error = f"{error_msg}\nResponse Headers:\n{headers_str}"
            
            # Log the detailed error with headers
            self.logger.error(detailed_error)
            
            # For the exception, we'll still use the shorter message to avoid overwhelming error outputs
            raise Exception(error_msg)
            
        self.logger.debug(f"Received successful response from Oxylabs API")
        return response.json()
        
    def scrape_direct_website(self, url: str, parse_code: str) -> Dict[str, Any]:
        """
        Scrape a direct website URL using Oxylabs API
        
        Args:
            url: The direct website URL to scrape
            parse_code: The parsing instructions for Oxylabs
            
        Returns:
            Dict containing the parsed website data
        """
        self.logger.debug(f"Scraping direct website URL: {url} with parse code: {parse_code}")
        
        # The parse_code is expected to be a JSON object with parsing instructions
        # We need to ensure it's a proper JSON object, not a string
        try:
            # If parse_code is already a dict, use it directly
            if isinstance(parse_code, dict):
                parsing_instructions = parse_code
            else:
                # Otherwise assume it's a JSON string and parse it
                parsing_instructions = json.loads(parse_code)
                
            payload = {
                'source': 'universal',
                'url': url,
                'geo_location': 'US',
                'render': 'html',
                'parse': True,
                'parsing_instructions': parsing_instructions
            }
        except Exception as e:
            self.logger.error(f"Error parsing parsing instructions: {e}")
            raise ValueError(f"Invalid parsing instructions: {parse_code}. Error: {e}")
        
        return self._make_request(payload)
