import os
import requests
from typing import Dict, Any
from datetime import datetime

class OxylabsClient:
    def __init__(self):
        self.username = os.getenv('OXYLABS_USERNAME')
        self.password = os.getenv('OXYLABS_PASSWORD')
        self.base_url = 'https://realtime.oxylabs.io/v1/queries'

    def search_google_shopping(self, query: str) -> Dict[str, Any]:
        """
        Execute a Google Shopping search using Oxylabs API
        
        Args:
            query: Search term to query
            
        Returns:
            Dict containing the parsed results from Oxylabs
        """
        payload = {
            'source': 'google_shopping_search',
            'query': query,
            'parse': True
        }

        response = requests.post(
            self.base_url,
            auth=(self.username, self.password),
            json=payload
        )
        
        if response.status_code != 200:
            raise Exception(f"Oxylabs API error: {response.status_code} - {response.text}")
            
        return response.json()

    def get_product_details(self, url: str) -> Dict[str, Any]:
        """
        Get details for a specific product URL using Oxylabs API
        
        Args:
            url: The Google Shopping product URL to scrape
            
        Returns:
            Dict containing the parsed product details
        """
        payload = {
            'source': 'google_shopping_product',
            'url': url,
            'parse': True
        }

        response = requests.post(
            self.base_url,
            auth=(self.username, self.password),
            json=payload
        )
        
        if response.status_code != 200:
            raise Exception(f"Oxylabs API error: {response.status_code} - {response.text}")
            
        return response.json() 