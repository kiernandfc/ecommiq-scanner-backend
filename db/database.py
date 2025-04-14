from pathlib import Path
from tinydb import TinyDB, Query
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from .models import CompetitorBrand, CatalogProduct, PriceHistory
from utils.helpers import utc_now

class Database:
    def __init__(self, db_path: str = "data/db.json"):
        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.db = TinyDB(db_path)
        self.competitors = self.db.table('competitors')
        self.catalog = self.db.table('catalog')
        self.prices = self.db.table('prices')
        self.Query = Query()

    def clear_tables(self, tables=None):
        """Clear specified tables or all tables if none specified"""
        if tables is None:
            self.competitors.truncate()
            self.catalog.truncate()
            self.prices.truncate()
            print("All tables cleared")
        else:
            for table_name in tables:
                if table_name == 'competitors':
                    self.competitors.truncate()
                elif table_name == 'catalog':
                    self.catalog.truncate()
                elif table_name == 'prices':
                    self.prices.truncate()
            print(f"Tables {', '.join(tables)} cleared")

    def add_reference(self, competitor: CompetitorBrand) -> int:
        data = competitor.model_dump()
        data['created_at'] = data['created_at'].isoformat()
        data['updated_at'] = data['updated_at'].isoformat()
        doc_id = self.competitors.insert(data)
        competitor.id = doc_id  # Set the ID on the competitor object
        return doc_id

    def get_all_competitors(self) -> List[CompetitorBrand]:
        docs = self.competitors.all()
        competitors = []
        for doc in docs:
            doc_id = doc.doc_id
            competitor = CompetitorBrand(**doc)
            competitor.id = doc_id  # Explicitly set the ID
            competitors.append(competitor)
        return competitors
    
    def get_active_competitors(self) -> List[CompetitorBrand]:
        docs = self.competitors.search(self.Query.active == True)
        competitors = []
        for doc in docs:
            doc_id = doc.doc_id
            competitor = CompetitorBrand(**doc)
            competitor.id = doc_id  # Explicitly set the ID
            competitors.append(competitor)
        return competitors

    def add_or_update_catalog_product(self, product: CatalogProduct) -> int:
        data = product.model_dump()
        data['last_checked'] = data['last_checked'].isoformat()
        data['created_at'] = data['created_at'].isoformat()
        data['updated_at'] = data['updated_at'].isoformat()

        # Check if product already exists
        existing = self.catalog.get(
            (self.Query.google_shopping_id == product.google_shopping_id) &
            (self.Query.competitor_brand_id == product.competitor_brand_id)
        )
        
        if existing:
            self.catalog.update(data, doc_ids=[existing.doc_id])
            return existing.doc_id
            
        return self.catalog.insert(data)

    def get_catalog_product(self, product_id: int) -> Optional[CatalogProduct]:
        doc = self.catalog.get(doc_id=product_id)
        return CatalogProduct(**doc) if doc else None

    def get_catalog_by_reference(self, reference_id: int) -> List[CatalogProduct]:
        docs = self.catalog.search(self.Query.reference_id == reference_id)
        return [CatalogProduct(**doc) for doc in docs]

    def add_price(self, price: PriceHistory) -> int:
        data = price.model_dump()
        data['timestamp'] = data['timestamp'].isoformat()
        return self.prices.insert(data)

    def get_price_history(self, catalog_id: int) -> List[PriceHistory]:
        # Using lambda for comparison since Query may not be working properly with catalog_id
        docs = self.prices.search(lambda x: x.get('catalog_id') == catalog_id)
        return [PriceHistory(**doc) for doc in docs]

    def get_products_to_update(self, hours_threshold: int = 24) -> List[CatalogProduct]:
        """Get products that haven't been checked in the specified hours"""
        cutoff = (utc_now() - timedelta(hours=hours_threshold)).isoformat()
        docs = self.catalog.search(self.Query.last_checked < cutoff)
        return [CatalogProduct(**doc) for doc in docs]

    def get_latest_price(self, catalog_id: int) -> Optional[PriceHistory]:
        """Get the most recent price for a catalog product"""
        # Using lambda for comparison since Query may not be working properly with catalog_id
        prices = self.prices.search(lambda x: x.get('catalog_id') == catalog_id)
        if not prices:
            return None
            
        # Sort by timestamp and get the latest
        latest = sorted(prices, key=lambda x: x['timestamp'], reverse=True)[0]
        return PriceHistory(**latest)

    def add_or_update_catalog_product_with_status(self, product: CatalogProduct) -> tuple[int, bool]:
        """
        Add or update a catalog product and return status about whether it was newly created
        
        Args:
            product: The CatalogProduct to add or update
            
        Returns:
            Tuple of (product_id, is_new) where is_new is True if the product was newly created
        """
        data = product.model_dump()
        data['last_checked'] = data['last_checked'].isoformat()
        data['created_at'] = data['created_at'].isoformat()
        data['updated_at'] = data['updated_at'].isoformat()

        # Check if product already exists
        existing = self.catalog.get(
            (self.Query.google_shopping_id == product.google_shopping_id) &
            (self.Query.competitor_brand_id == product.competitor_brand_id)
        )
        
        if existing:
            self.catalog.update(data, doc_ids=[existing.doc_id])
            return existing.doc_id, False
            
        new_id = self.catalog.insert(data)
        return new_id, True 