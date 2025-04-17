import os
import requests
from typing import Dict, Any
from datetime import datetime
import logging

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
            'parse': True
        }

        self.logger.debug(f"Sending request to Oxylabs API")
        response = requests.post(
            self.base_url,
            auth=(self.username, self.password),
            json=payload
        )
        
        if response.status_code != 200:
            error_msg = f"Oxylabs API error: {response.status_code} - {response.text}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        self.logger.debug(f"Received successful response from Oxylabs API")    
        return response.json()

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
            'url': url,
            'parse': True
        }

        self.logger.debug(f"Sending request to Oxylabs API")
        response = requests.post(
            self.base_url,
            auth=(self.username, self.password),
            json=payload
        )
        
        if response.status_code != 200:
            error_msg = f"Oxylabs API error: {response.status_code} - {response.text}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
            
        self.logger.debug(f"Received successful response from Oxylabs API")
        return response.json()

    def _make_request(self, payload):
        """Make a request to Oxylabs API""" 