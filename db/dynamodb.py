import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import logging
import json

from .models import CompetitorBrand, CatalogProduct, PriceHistory
from utils.helpers import utc_now
from utils.logger import configure_logger

class DynamoDBDatabase:
    """Database implementation using AWS DynamoDB"""
    
    def __init__(self, region_name=None, endpoint_url=None):
        # Configure logger - level is inherited from root config set in main.py
        self.logger = configure_logger(f"{__name__}.DynamoDBDatabase")
        # self.logger.debug("Initializing DynamoDB connection") # Filtered if root is INFO
        
        # Determine region and endpoint
        self.region_name = region_name or os.getenv('AWS_REGION', 'us-east-1')
        self.endpoint_url = endpoint_url or os.getenv('DYNAMODB_ENDPOINT_URL') # For local testing
        
        # Initialize DynamoDB session
        self._init_dynamodb()
        
        # Table names
        self.competitors_table_name = os.getenv('DYNAMODB_COMPETITORS_TABLE', 'ecommiq_competitors')
        self.catalog_table_name = os.getenv('DYNAMODB_CATALOG_TABLE', 'ecommiq_catalog')
        self.prices_table_name = os.getenv('DYNAMODB_PRICES_TABLE', 'ecommiq_prices')
        self.mapping_table_name = os.getenv('DYNAMODB_MAPPING_TABLE', 'ecommiq_competitor_catalog_map')
        
        # Create tables if they don't exist
        self._ensure_tables_exist()
    
    def _init_dynamodb(self):
        """Initialize DynamoDB client and resource"""
        session_kwargs = {
            'region_name': self.region_name
        }
        
        if self.endpoint_url:
            session_kwargs['endpoint_url'] = self.endpoint_url
        
        # Initialize boto3 resources
        self.dynamodb = boto3.resource('dynamodb', **session_kwargs)
        self.client = boto3.client('dynamodb', **session_kwargs)
        self.logger.debug(f"Connected to DynamoDB in region {self.region_name}")
    
    def _ensure_tables_exist(self):
        """Create tables if they don't exist"""
        # Get existing tables
        existing_tables = self.client.list_tables()['TableNames']
        
        # Create competitors table if it doesn't exist
        if self.competitors_table_name not in existing_tables:
            self.logger.info(f"Creating competitors table: {self.competitors_table_name}")
            self.client.create_table(
                TableName=self.competitors_table_name,
                KeySchema=[
                    {'AttributeName': 'id', 'KeyType': 'HASH'},  # Partition key
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                ],
                BillingMode='PAY_PER_REQUEST'
            )
        
        # Create catalog table if it doesn't exist
        if self.catalog_table_name not in existing_tables:
            self.logger.info(f"Creating catalog table: {self.catalog_table_name}")
            self.client.create_table(
                TableName=self.catalog_table_name,
                KeySchema=[
                    {'AttributeName': 'id', 'KeyType': 'HASH'},  # Partition key
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'google_shopping_id', 'AttributeType': 'S'},
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'google_shopping_id-index',
                        'KeySchema': [
                            {'AttributeName': 'google_shopping_id', 'KeyType': 'HASH'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )

        # Create mapping table if it doesn't exist
        if self.mapping_table_name not in existing_tables:
            self.logger.info(f"Creating mapping table: {self.mapping_table_name}")
            self.client.create_table(
                TableName=self.mapping_table_name,
                KeySchema=[
                    {'AttributeName': 'id', 'KeyType': 'HASH'},  # Partition key
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'competitor_id', 'AttributeType': 'S'},
                    {'AttributeName': 'catalog_id', 'AttributeType': 'S'},
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'competitor_id-index',
                        'KeySchema': [
                            {'AttributeName': 'competitor_id', 'KeyType': 'HASH'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    },
                    {
                        'IndexName': 'catalog_id-index',
                        'KeySchema': [
                            {'AttributeName': 'catalog_id', 'KeyType': 'HASH'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )
        
        # Create prices table if it doesn't exist
        if self.prices_table_name not in existing_tables:
            self.logger.info(f"Creating prices table: {self.prices_table_name}")
            self.client.create_table(
                TableName=self.prices_table_name,
                KeySchema=[
                    {'AttributeName': 'id', 'KeyType': 'HASH'},  # Partition key
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'catalog_id', 'AttributeType': 'S'},
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'catalog_id-index',
                        'KeySchema': [
                            {'AttributeName': 'catalog_id', 'KeyType': 'HASH'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            
        # Wait for tables to be created
        self.client.get_waiter('table_exists').wait(TableName=self.competitors_table_name)
        self.client.get_waiter('table_exists').wait(TableName=self.catalog_table_name)
        self.client.get_waiter('table_exists').wait(TableName=self.mapping_table_name)
        self.client.get_waiter('table_exists').wait(TableName=self.prices_table_name)
        
        # Get table references
        self.competitors = self.dynamodb.Table(self.competitors_table_name)
        self.catalog = self.dynamodb.Table(self.catalog_table_name)
        self.mapping = self.dynamodb.Table(self.mapping_table_name)
        self.prices = self.dynamodb.Table(self.prices_table_name)
        
        self.logger.debug("All DynamoDB tables verified")
    
    def _generate_id(self, prefix=""):
        """Generate a unique ID for DynamoDB records"""
        import uuid
        return f"{prefix}{uuid.uuid4().hex}"
    
    def clear_tables(self, tables=None):
        """Clear specified tables or all tables if none specified"""
        if tables is None:
            tables = ['competitors', 'catalog', 'prices', 'mapping']
            
        for table_name in tables:
            if table_name == 'competitors':
                self._clear_table(self.competitors)
            elif table_name == 'catalog':
                self._clear_table(self.catalog)
            elif table_name == 'prices':
                self._clear_table(self.prices)
            elif table_name == 'mapping':
                self._clear_table(self.mapping)
        
        self.logger.info(f"Tables {', '.join(tables)} cleared")
    
    def _clear_table(self, table):
        """Delete all items from a table"""
        # Scan for all items
        items = table.scan()['Items']
        
        # Delete each item
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={'id': item['id']})
    
    def add_reference(self, competitor: CompetitorBrand) -> str:
        """Add a new competitor reference to the database"""
        # Convert model to dictionary
        data = competitor.model_dump()
        
        # Generate a unique ID if not provided
        competitor_id = str(data.get('id') or self._generate_id("comp_"))
        data['id'] = competitor_id
        
        # Convert datetime objects to ISO strings
        data['created_at'] = data['created_at'].isoformat()
        data['updated_at'] = data['updated_at'].isoformat()
        
        # Save to DynamoDB
        self.competitors.put_item(Item=data)
        
        # Update the model with the ID
        competitor.id = competitor_id
        return competitor_id
    
    def get_all_competitors(self) -> List[CompetitorBrand]:
        """Get all competitors from the database"""
        response = self.competitors.scan()
        competitors = []
        
        for item in response.get('Items', []):
            competitor = CompetitorBrand(**item)
            competitors.append(competitor)
            
        return competitors
    
    def get_active_competitors(self) -> List[CompetitorBrand]:
        """Get all active competitors from the database"""
        # Use a FilterExpression to get only active competitors
        response = self.competitors.scan(
            FilterExpression=Attr('active').eq(True)
        )
        
        competitors = []
        for item in response.get('Items', []):
            competitor = CompetitorBrand(**item)
            competitors.append(competitor)
            
        return competitors
    
    def update_competitor(self, competitor: CompetitorBrand) -> str:
        """Update an existing competitor reference"""
        if not competitor.id:
            raise ValueError("Competitor must have an ID to be updated")
            
        # Convert model to dictionary
        data = competitor.model_dump()
        
        # Update timestamp
        data['updated_at'] = utc_now().isoformat()
        
        # Convert any datetime objects to ISO strings
        data['created_at'] = data['created_at'].isoformat()
        
        # Save to DynamoDB
        self.competitors.put_item(Item=data)
        
        return competitor.id
    
    def add_or_update_catalog_product_with_status(self, product: CatalogProduct, competitor_ids: List[str] = None) -> tuple[str, bool]:
        """Add or update a catalog product and return status"""
        # Convert model to dictionary
        data = product.model_dump()
        
        # Convert datetime objects to ISO strings
        data['last_checked'] = data['last_checked'].isoformat()
        data['created_at'] = data['created_at'].isoformat()
        data['updated_at'] = data['updated_at'].isoformat()
        
        # Check if product already exists by google_shopping_id
        response = self.catalog.scan(
            FilterExpression=Attr('google_shopping_id').eq(product.google_shopping_id)
        )
        
        existing_items = response.get('Items', [])
        
        if existing_items:
            # Product exists, update it
            existing = existing_items[0]
            product_id = existing['id']
            data['id'] = product_id
            
            # Update timestamp
            data['updated_at'] = utc_now().isoformat()
            
            self.catalog.put_item(Item=data)
            
            # If competitor_ids is provided, update mappings
            if competitor_ids:
                self._update_competitor_mappings(product_id, competitor_ids)
                
            return product_id, False
        else:
            # New product, create it
            product_id = self._generate_id("prod_")
            data['id'] = product_id
            
            self.catalog.put_item(Item=data)
            
            # If competitor_ids is provided, create mappings
            if competitor_ids:
                self._update_competitor_mappings(product_id, competitor_ids)
                
            return product_id, True
    
    def _update_competitor_mappings(self, catalog_id: str, competitor_ids: List[str]):
        """Update the mappings between a catalog product and competitors"""
        # Get existing mappings for this catalog item
        response = self.mapping.query(
            IndexName='catalog_id-index',
            KeyConditionExpression=Key('catalog_id').eq(catalog_id)
        )
        
        # Create a set of existing competitor IDs in the mapping
        existing_competitor_ids = {item['competitor_id'] for item in response.get('Items', [])}
        
        # Add new mappings
        for competitor_id in competitor_ids:
            if competitor_id not in existing_competitor_ids:
                mapping_id = self._generate_id("map_")
                self.mapping.put_item(Item={
                    'id': mapping_id,
                    'competitor_id': competitor_id,
                    'catalog_id': catalog_id,
                    'created_at': utc_now().isoformat()
                })
    
    def add_competitor_to_catalog(self, competitor_id: str, catalog_id: str) -> str:
        """Add a competitor to a catalog product"""
        mapping_id = self._generate_id("map_")
        self.mapping.put_item(Item={
            'id': mapping_id,
            'competitor_id': competitor_id,
            'catalog_id': catalog_id,
            'created_at': utc_now().isoformat()
        })
        return mapping_id
    
    def get_catalog_by_competitor(self, competitor_id: str) -> List[CatalogProduct]:
        """Get catalog products by competitor ID"""
        # Find all mappings for this competitor
        mapping_response = self.mapping.query(
            IndexName='competitor_id-index',
            KeyConditionExpression=Key('competitor_id').eq(competitor_id)
        )
        
        catalog_ids = [item['catalog_id'] for item in mapping_response.get('Items', [])]
        
        products = []
        for catalog_id in catalog_ids:
            response = self.catalog.get_item(Key={'id': catalog_id})
            item = response.get('Item')
            if item:
                products.append(CatalogProduct(**item))
                
        return products
    
    def get_competitors_by_catalog(self, catalog_id: str) -> List[CompetitorBrand]:
        """Get competitors for a catalog product"""
        # Find all mappings for this catalog product
        mapping_response = self.mapping.query(
            IndexName='catalog_id-index',
            KeyConditionExpression=Key('catalog_id').eq(catalog_id)
        )
        
        competitor_ids = [item['competitor_id'] for item in mapping_response.get('Items', [])]
        
        competitors = []
        for competitor_id in competitor_ids:
            response = self.competitors.get_item(Key={'id': competitor_id})
            item = response.get('Item')
            if item:
                competitors.append(CompetitorBrand(**item))
                
        return competitors
    
    def add_or_update_catalog_product(self, product: CatalogProduct, competitor_ids: List[str] = None) -> str:
        """Add or update a catalog product"""
        product_id, _ = self.add_or_update_catalog_product_with_status(product, competitor_ids)
        return product_id
    
    def get_catalog_product(self, product_id: str) -> Optional[CatalogProduct]:
        """Get a catalog product by ID"""
        response = self.catalog.get_item(Key={'id': product_id})
        item = response.get('Item')
        
        if item:
            return CatalogProduct(**item)
        return None
    
    def get_catalog_by_reference(self, reference_id: str) -> List[CatalogProduct]:
        """Get catalog products by reference ID (legacy compatibility)"""
        return self.get_catalog_by_competitor(reference_id)
    
    def add_price(self, price: PriceHistory) -> str:
        """Add a price history record"""
        # Convert model to dictionary
        data = price.model_dump()
        
        # Generate a unique ID if not provided
        price_id = str(data.get('id') or self._generate_id("price_"))
        data['id'] = price_id
        
        # Convert catalog_id to string
        data['catalog_id'] = str(data['catalog_id'])
        
        # Convert datetime objects to ISO strings
        data['timestamp'] = data['timestamp'].isoformat()
        
        # Save to DynamoDB
        self.prices.put_item(Item=data)
        
        # Update the model with the ID
        price.id = price_id
        return price_id
    
    def get_price_history(self, catalog_id: str) -> List[PriceHistory]:
        """Get price history for a catalog product"""
        response = self.prices.query(
            IndexName='catalog_id-index',
            KeyConditionExpression=Key('catalog_id').eq(str(catalog_id))
        )
        
        prices = []
        for item in response.get('Items', []):
            prices.append(PriceHistory(**item))
            
        return prices
    
    def get_products_to_update(self, hours_threshold: int = 24) -> List[CatalogProduct]:
        """Get products that haven't been checked in the specified hours"""
        cutoff = (utc_now() - timedelta(hours=hours_threshold)).isoformat()
        
        response = self.catalog.scan(
            FilterExpression=Attr('last_checked').lt(cutoff)
        )
        
        products = []
        for item in response.get('Items', []):
            products.append(CatalogProduct(**item))
            
        return products
    
    def get_latest_price(self, catalog_id: str) -> Optional[PriceHistory]:
        """Get the most recent price for a catalog product"""
        response = self.prices.query(
            IndexName='catalog_id-index',
            KeyConditionExpression=Key('catalog_id').eq(str(catalog_id)),
            ScanIndexForward=False,  # Descending order (newest first)
            Limit=1
        )
        
        items = response.get('Items', [])
        if items:
            return PriceHistory(**items[0])
        return None 