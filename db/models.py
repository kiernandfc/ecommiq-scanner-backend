from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from utils.helpers import utc_now
from decimal import Decimal

class CompetitorBrand(BaseModel):
    id: Optional[str] = None
    reference_brand: str
    reference_product: str
    competitor_brand: str
    search_query: str
    active: bool = True
    created_at: datetime = utc_now()
    updated_at: datetime = utc_now()

class CatalogProduct(BaseModel):
    id: Optional[str] = None
    competitor_brand_id: str
    primary_merchant: str
    name: str
    url: str
    canonical_url: Optional[str] = None
    google_shopping_id: str
    last_checked: datetime = utc_now()
    created_at: datetime = utc_now()
    updated_at: datetime = utc_now()

class PriceHistory(BaseModel):
    id: Optional[str] = None
    catalog_id: str
    merchant: str
    price: Decimal
    currency: str = "USD"
    in_stock: bool
    timestamp: datetime = utc_now()

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v)
        } 