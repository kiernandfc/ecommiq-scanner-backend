from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from utils.helpers import utc_now

class CompetitorBrand(BaseModel):
    id: Optional[int] = None
    reference_brand: str
    reference_product: str
    competitor_brand: str
    search_query: str
    active: bool = True
    created_at: datetime = utc_now()
    updated_at: datetime = utc_now()

class CatalogProduct(BaseModel):
    id: Optional[int] = None
    competitor_brand_id: int
    brand: str
    name: str
    url: str
    canonical_url: Optional[str] = None
    google_shopping_id: str
    last_checked: datetime = utc_now()
    created_at: datetime = utc_now()
    updated_at: datetime = utc_now()

class PriceHistory(BaseModel):
    id: Optional[int] = None
    catalog_id: int
    price: float
    currency: str = "USD"
    in_stock: bool
    timestamp: datetime = utc_now()

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        } 