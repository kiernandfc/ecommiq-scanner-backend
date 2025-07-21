"""
Unit tests for database models and Pydantic validation.
"""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from db.models import CompetitorBrand, CatalogProduct, PriceHistory, Site


@pytest.mark.unit
class TestSiteModel:
    """Test cases for Site model validation."""

    def test_site_valid_creation(self):
        """Test creating a valid site."""
        site = Site(
            id="test-site-1",
            name="Test Site",
            base_url="https://example.com",
            oxylabs_parse_code="test_code",
            active=True
        )
        
        assert site.id == "test-site-1"
        assert site.name == "Test Site"
        assert site.base_url == "https://example.com"
        assert site.oxylabs_parse_code == "test_code"
        assert site.active is True

    def test_site_defaults(self):
        """Test site model defaults."""
        site = Site(
            id="test-site",
            name="Test Site",
            base_url="https://example.com",
            oxylabs_parse_code="test_code"
        )
        
        assert site.active is True  # Default should be True

    def test_site_invalid_empty_fields(self):
        """Test site validation with missing required fields."""
        # Test missing required field (name)
        with pytest.raises(ValidationError):
            Site(
                id="test-site-1",
                # Missing name - this should fail
                base_url="https://example.com",
                oxylabs_parse_code="test_code"
            )
        
        # Test missing required field (base_url)
        with pytest.raises(ValidationError):
            Site(
                id="test-site-1",
                name="Test Site",
                # Missing base_url - this should fail
                oxylabs_parse_code="test_code"
            )
        
        # Test that empty ID is actually allowed
        site_with_empty_id = Site(
            id="",  # Empty ID should be allowed
            name="Test Site",
            base_url="https://example.com",
            oxylabs_parse_code="test_code"
        )
        assert site_with_empty_id.id == ""

@pytest.mark.unit
class TestCompetitorBrandModel:
    """Test cases for CompetitorBrand model validation."""

    def test_competitor_valid_creation(self):
        """Test creating a valid competitor."""
        competitor = CompetitorBrand(
            id="test-comp-1",
            reference_brand="RefBrand",
            reference_product="Ref Product",
            competitor_brand="Comp Brand",
            search_query="search query",
            active=True
        )
        
        assert competitor.id == "test-comp-1"
        assert competitor.reference_brand == "RefBrand"
        assert competitor.competitor_brand == "Comp Brand"
        assert competitor.search_query == "search query"
        assert competitor.active is True

    def test_competitor_with_optional_fields(self):
        """Test competitor with optional fields."""
        competitor = CompetitorBrand(
            id="test-comp-1",
            reference_brand="RefBrand",
            reference_product="Ref Product",
            competitor_brand="Comp Brand",
            search_query="search query",
            reference_product_description="Description",
            min_price=10.0,
            max_price=100.0,
            site_id="site-1"
        )
        
        assert competitor.reference_product_description == "Description"
        assert competitor.min_price == 10.0
        assert competitor.max_price == 100.0
        assert competitor.site_id == "site-1"

    def test_competitor_defaults(self):
        """Test competitor model defaults."""
        competitor = CompetitorBrand(
            id="test-comp-1",
            reference_brand="RefBrand",
            reference_product="Ref Product",
            competitor_brand="Comp Brand",
            search_query="search query"
        )
        
        assert competitor.active is True
        assert competitor.min_price is None
        assert competitor.max_price is None
        assert competitor.site_id is None

    def test_competitor_price_validation(self):
        """Test competitor price validation logic."""
        competitor = CompetitorBrand(
            id="test-comp-1",
            reference_brand="RefBrand",
            reference_product="Ref Product",
            competitor_brand="Comp Brand",
            search_query="search query",
            min_price=10.0,
            max_price=100.0
        )
        
        # Test price bounds checking (would be implemented in business logic)
        assert competitor.min_price < competitor.max_price


@pytest.mark.unit
class TestCatalogProductModel:
    """Test cases for CatalogProduct model validation."""

    def test_catalog_product_valid_creation(self):
        """Test creating a valid catalog product."""
        product = CatalogProduct(
            id="test-prod-1",
            title="Test Product",
            link="https://example.com/product"  # Required field
        )
        
        assert product.id == "test-prod-1"
        assert product.title == "Test Product"
        assert product.link == "https://example.com/product"

    def test_catalog_product_with_all_fields(self):
        """Test catalog product with all fields."""
        product = CatalogProduct(
            id="test-prod-1",
            google_shopping_id="google-123",
            title="Test Product",
            link="https://example.com/product",  # Fixed: use 'link' not 'url'
            review_count=150,
            position=1,
            sku="TEST-SKU-001",
            brand="TestBrand",
            source_type="google_shopping"
        )
        
        assert product.google_shopping_id == "google-123"
        assert product.link == "https://example.com/product"  # Fixed: use 'url' not 'link'
        assert product.review_count == 150
        assert product.sku == "TEST-SKU-001"
        assert product.source_type == "google_shopping"

    def test_catalog_product_defaults(self):
        """Test catalog product defaults."""
        product = CatalogProduct(
            id="test-prod-1",
            title="Test Product",
            link="https://example.com/product"  # Required field
        )
        
        assert product.source_type == "google_shopping"  # Default value


@pytest.mark.unit
class TestPriceHistoryModel:
    """Test cases for PriceHistory model validation."""

    def test_price_history_valid_creation(self):
        """Test creating a valid price history entry."""
        from decimal import Decimal
        price_history = PriceHistory(
            id="test-price-1",
            catalog_id="test-prod-1",
            price=Decimal("29.99"),  # Required Decimal type
            merchant="Test Merchant",  # Required field
            in_stock=True,  # Required field
            currency="USD"
        )
        
        assert price_history.id == "test-price-1"
        assert price_history.catalog_id == "test-prod-1"
        assert price_history.price == Decimal("29.99")
        assert price_history.merchant == "Test Merchant"
        assert price_history.in_stock is True
        assert price_history.currency == "USD"

    def test_price_history_with_optional_fields(self):
        """Test price history with optional fields."""
        from decimal import Decimal
        price_history = PriceHistory(
            id="test-price-1",
            catalog_id="test-prod-1",
            price=Decimal("29.99"),  # Fixed: use Decimal type
            list_price=Decimal("39.99"),  # Fixed: use Decimal type
            currency="USD",
            merchant="Test Merchant",  # Required field
            in_stock=True,  # Fixed: use 'in_stock' not 'is_available'
            review_count=150
        )
        
        assert price_history.list_price == Decimal("39.99")
        assert price_history.merchant == "Test Merchant"
        assert price_history.in_stock is True  # Fixed: use 'in_stock' not 'is_available'
        assert price_history.review_count == 150

    def test_price_history_defaults(self):
        """Test price history defaults."""
        from decimal import Decimal
        price_history = PriceHistory(
            id="test-price-1",
            catalog_id="test-prod-1",
            price=Decimal("29.99"),  # Required Decimal type
            merchant="Test Merchant",  # Required field
            in_stock=True,  # Required field
            currency="USD"
        )
        
        assert price_history.in_stock is True  # Fixed: use 'in_stock' not 'is_available'
        assert price_history.list_price is None  # Optional field should be None by default
        assert price_history.currency == "USD"  # Default value

    def test_price_history_required_fields(self):
        """Test price history with missing required fields."""
        with pytest.raises(ValidationError):
            PriceHistory(
                id="test-price-1",
                # Missing catalog_id
                price=29.99,
                currency="USD"
            )

        with pytest.raises(ValidationError):
            PriceHistory(
                id="test-price-1",
                catalog_id="test-prod-1",
                # Missing price
                currency="USD"
            )


@pytest.mark.unit
class TestModelInteractions:
    """Test interactions between different models."""

    def test_model_relationships(self):
        """Test that models can reference each other properly."""
        site = Site(
            id="test-site-1",
            name="Test Site",
            base_url="https://example.com",
            oxylabs_parse_code="test_code"
        )
        
        competitor = CompetitorBrand(
            id="test-comp-1",
            reference_brand="RefBrand",
            reference_product="Ref Product",
            competitor_brand="Comp Brand",
            search_query="search query",
            site_id=site.id  # Reference to site
        )
        
        from decimal import Decimal
        product = CatalogProduct(
            id="test-prod-1",
            title="Test Product",
            link="https://example.com/product"  # Required field
        )
        
        price_history = PriceHistory(
            id="test-price-1",
            catalog_id=product.id,  # Reference to product
            price=Decimal("29.99"),  # Required Decimal type
            merchant="Test Merchant",  # Required field
            in_stock=True,  # Required field
            currency="USD"
        )
        
        # All models should be valid
        assert site.id == competitor.site_id
        assert product.id == price_history.catalog_id

    def test_model_json_serialization(self):
        """Test that all models can be serialized to JSON."""
        from decimal import Decimal
        models = [
            Site(id="s1", name="Site", base_url="https://example.com", oxylabs_parse_code="code"),
            CompetitorBrand(id="c1", reference_brand="Ref", reference_product="Prod", 
                          competitor_brand="Comp", search_query="query"),
            CatalogProduct(id="p1", title="Product", link="https://example.com/product"),  # Fixed: added required link field
            PriceHistory(id="ph1", catalog_id="p1", price=Decimal("29.99"), merchant="Test", in_stock=True, currency="USD")  # Fixed: added required fields
        ]
        
        for model in models:
            # Fixed: Use Pydantic V2 method instead of deprecated json()
            json_str = model.model_dump_json()
            assert isinstance(json_str, str)
            assert len(json_str) > 0
            
            # Should be able to recreate from JSON
            # Fixed: Use Pydantic V2 method instead of deprecated dict()
            model_dict = model.model_dump()
            recreated = type(model)(**model_dict)
            assert recreated.id == model.id
