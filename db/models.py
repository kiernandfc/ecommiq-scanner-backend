from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_serializer
from utils.helpers import utc_now
from decimal import Decimal

class Site(BaseModel):
    id: Optional[str] = None
    name: str
    base_url: str
    oxylabs_parse_code: str
    active: bool = True
    created_at: datetime = utc_now()
    updated_at: datetime = utc_now()

class CompetitorBrand(BaseModel):
    id: Optional[str] = None
    reference_brand: str
    reference_product: str
    competitor_brand: str
    search_query: str
    reference_product_description: Optional[str] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    site_id: Optional[str] = None  # Reference to Site model
    active: bool = True
    created_at: datetime = utc_now()
    updated_at: datetime = utc_now()

class CompetitorCatalogMap(BaseModel):
    id: Optional[str] = None
    competitor_id: str
    catalog_id: str
    created_at: datetime = utc_now()

class CatalogProduct(BaseModel):
    id: Optional[str] = None
    google_shopping_id: Optional[str] = None  # Made optional for direct website products
    title: str
    link: str  # Fixed: match database schema field name
    image_link: Optional[str] = None
    price: Optional[float] = None  # Fixed: match database schema type
    currency: Optional[str] = "USD"
    is_available: bool = True  # Fixed: match database schema field name
    sku: Optional[str] = None  # Added for direct website products
    brand: Optional[str] = None  # Added for direct website products
    source_type: Optional[str] = "google_shopping"  # Default to google_shopping, can be direct_website
    review_count: Optional[int] = None
    position: Optional[int] = None
    last_checked: datetime = utc_now()
    created_at: datetime = utc_now()
    updated_at: datetime = utc_now()
    description: Optional[str] = None

class PriceHistory(BaseModel):
    id: Optional[str] = None
    catalog_id: str
    merchant: str
    price: Decimal
    list_price: Optional[Decimal] = None  # Added for direct website products (original price before discounts)
    currency: str = "USD"
    in_stock: bool
    description: Optional[str] = None  # Added for direct website products
    review_count: Optional[int] = None
    position: Optional[int] = None
    timestamp: datetime = utc_now()
    
    @field_serializer('timestamp')
    def serialize_timestamp(self, value: datetime) -> str:
        """Serialize datetime to ISO format string"""
        return value.isoformat()
    
    @field_serializer('price', 'list_price')
    def serialize_decimal(self, value: Optional[Decimal]) -> Optional[str]:
        """Serialize Decimal to string"""
        return str(value) if value is not None else None 