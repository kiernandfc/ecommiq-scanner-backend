"""
Shared pytest configuration and fixtures for the ecommiqscanner2 test suite.
"""
import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

# Import project modules
from db.postgresql import PostgreSQLDatabase, Base
from db.models import CompetitorBrand, CatalogProduct, PriceHistory, Site
from scrapers.oxylabs_client import OxylabsClient
from scrapers.search_scanner import SearchScanner
from scrapers.site_scanner import SiteScanner
from utils.helpers import utc_now


@pytest.fixture(scope="session")
def test_database_url():
    """Provide test database URL. Uses in-memory SQLite for fast testing."""
    return "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_db_engine(test_database_url):
    """Create a test database engine for each test."""
    engine = create_engine(test_database_url, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """Create a test database session for each test."""
    Session = sessionmaker(bind=test_db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def mock_postgresql_db(test_db_engine):
    """Create a mock PostgreSQL database instance for testing."""
    # Create a real PostgreSQL instance but replace its engine
    with patch.dict(os.environ, {
        'POSTGRESQL_HOST': 'localhost',
        'POSTGRESQL_PORT': '5432', 
        'POSTGRESQL_DB': 'test_db',
        'POSTGRESQL_USER': 'test_user',
        'POSTGRESQL_PASSWORD': 'test_password'
    }):
        # Patch the create_engine call to return our test engine
        with patch('db.postgresql.create_engine') as mock_create_engine:
            mock_create_engine.return_value = test_db_engine
            
            db = PostgreSQLDatabase()
            # Override the engine and session after initialization
            db.engine = test_db_engine
            db.Session = sessionmaker(bind=test_db_engine)
            yield db


@pytest.fixture
def sample_competitor():
    """Provide a sample competitor for testing."""
    return CompetitorBrand(
        id="test-competitor-1",
        reference_brand="TestBrand",
        reference_product="Test Product",
        competitor_brand="Competitor Brand",
        search_query="test product search",
        reference_product_description="A test product description",
        min_price=10.0,
        max_price=100.0,
        site_id="test-site-1",
        active=True
    )


@pytest.fixture
def sample_site():
    """Provide a sample site for testing."""
    return Site(
        id="test-site-1",
        name="Test Site",
        base_url="https://testsite.com",
        oxylabs_parse_code="test_parse_code",
        active=True
    )


@pytest.fixture
def sample_catalog_product():
    """Provide a sample catalog product for testing."""
    return CatalogProduct(
        id="test-product-1",
        google_shopping_id="google-123",
        title="Test Product Title",
        link="https://example.com/product",  # Fixed: use 'link' not 'url'
        review_count=150,
        position=1,
        sku="TEST-SKU-001",
        brand="TestBrand",
        source_type="google_shopping"
    )


@pytest.fixture
def sample_price_history():
    """Provide a sample price history entry for testing."""
    from decimal import Decimal
    return PriceHistory(
        id="test-price-1",
        catalog_id="test-product-1",
        price=Decimal("29.99"),  # Fixed: use Decimal type
        list_price=Decimal("39.99"),  # Fixed: use Decimal type
        currency="USD",
        merchant="Test Merchant",  # Required field
        in_stock=True,  # Fixed: use 'in_stock' not 'is_available'
        review_count=150
    )


@pytest.fixture
def mock_oxylabs_client():
    """Create a mock Oxylabs client for testing."""
    mock_client = Mock(spec=OxylabsClient)
    
    # Mock successful Google Shopping response
    mock_client.search_google_shopping.return_value = {
        "results": [{
            "content": {
                "results": {
                    "organic": [
                        {
                            "title": "Test Product",
                            "price": 29.99,
                            "currency": "USD",
                            "merchant": {"name": "Test Store"},
                            "url": "https://example.com/product",
                            "pos": 1,
                            "product_id": "google-123"
                        }
                    ]
                }
            }
        }]
    }
    
    # Mock successful direct website response
    mock_client.scrape_direct_website.return_value = {
        "results": [{
            "content": "<html>Mock website content</html>"
        }]
    }
    
    return mock_client


@pytest.fixture
def mock_postgresql_db():
    """Create a mock PostgreSQL database for testing SearchScanner."""
    from unittest.mock import Mock
    from db.postgresql import PostgreSQLDatabase
    
    mock_db = Mock(spec=PostgreSQLDatabase)
    
    # Mock only the database operations that are actually used in SearchScanner
    mock_db.add_or_update_catalog_product_with_status.return_value = ("test-product-1", True)
    mock_db.add_price.return_value = True
    mock_db.get_active_competitors.return_value = []
    mock_db.get_total_catalog_count.return_value = 0
    mock_db.add_reference.return_value = "test-competitor-1"
    
    return mock_db


@pytest.fixture
def unit_test_db():
    """Create a properly mocked PostgreSQL database for unit testing."""
    from unittest.mock import Mock, MagicMock
    from db.postgresql import PostgreSQLDatabase
    from db.models import Site, CompetitorBrand, CatalogProduct
    import uuid
    
    # Create a mock with spec to ensure we only mock real methods
    mock_db = Mock(spec=PostgreSQLDatabase)
    
    # Mock engine and Session attributes
    mock_db.engine = Mock()
    mock_db.Session = Mock()
    
    # Storage for test data
    mock_db._sites = {}
    mock_db._competitors = {}
    mock_db._products = {}
    mock_db._catalog_products_by_competitor = {}
    
    # Mock ID generation methods
    def mock_generate_id(prefix=None):
        hex_uuid = uuid.uuid4().hex
        if prefix:
            return f"{prefix}{hex_uuid}"
        return hex_uuid
    
    mock_db._generate_id = mock_generate_id
    
    # Mock site operations
    def mock_add_site(site):
        if site.id in mock_db._sites:
            raise Exception(f"Site with ID {site.id} already exists")
        mock_db._sites[site.id] = site
        return site.id
    
    def mock_get_site(site_id):
        return mock_db._sites.get(site_id)
    
    def mock_get_all_sites():
        return list(mock_db._sites.values())

    def mock_update_site(site):
        if site.id in mock_db._sites:
            mock_db._sites[site.id] = site
            return True
        return False
    
    def mock_delete_site(site_id):
        if site_id in mock_db._sites:
            del mock_db._sites[site_id]
            return True
        return False
    
    # Mock competitor operations
    def mock_add_reference(competitor):
        if competitor.id in mock_db._competitors:
            raise Exception(f"Competitor with ID {competitor.id} already exists")
        mock_db._competitors[competitor.id] = competitor
        return competitor.id
    
    def mock_get_active_competitors():
        return [comp for comp in mock_db._competitors.values() if comp.active]
    
    def mock_update_competitor(competitor):
        if competitor.id in mock_db._competitors:
            mock_db._competitors[competitor.id] = competitor
            return True
        return False
    
    # Mock product operations
    def mock_add_or_update_catalog_product_with_status(product, competitor_ids=None):
        """Create or update a catalog product and keep competitor mapping consistent."""
        # Find existing product by unique fields (title + link)
        existing_product_id = None
        for pid, existing_product in mock_db._products.items():
            if existing_product.title == product.title and existing_product.link == product.link:
                existing_product_id = pid
                break

        if existing_product_id:
            # Update in-memory record
            product.id = existing_product_id
            mock_db._products[existing_product_id] = product
            product_id = existing_product_id
            is_new = False
        else:
            # Create new product
            # Use the provided ID if it exists, otherwise generate one
            if product.id:
                product_id = product.id
            else:
                product_id = mock_generate_id("product_")
                product.id = product_id
            mock_db._products[product_id] = product
            is_new = True

        # Maintain mapping of product -> competitor(s)
        if competitor_ids:
            for cid in competitor_ids:
                mock_db._catalog_products_by_competitor.setdefault(cid, [])
                if product_id not in mock_db._catalog_products_by_competitor[cid]:
                    mock_db._catalog_products_by_competitor[cid].append(product_id)

        return product_id, is_new
    
    def mock_add_price(price):
        # Generate a price ID and return it
        price_id = mock_generate_id("price_")
        return price_id
    
    # Mock table operations
    def mock_clear_tables(table_names):
        if 'sites' in table_names:
            mock_db._sites.clear()
        if 'competitors' in table_names:
            mock_db._competitors.clear()
        if 'catalog_products' in table_names:
            mock_db._products.clear()
    
    def mock_refresh_materialized_views():
        return True
    
    def mock_get_active_competitors():
        return [c for c in mock_db._competitors.values() if c.active]

    def mock_get_catalog_products_by_competitor(competitor_id):
        product_ids = mock_db._catalog_products_by_competitor.get(competitor_id, [])
        return [mock_db._products[pid] for pid in product_ids]

    # Assign mock methods
    mock_db.add_site = mock_add_site
    mock_db.get_site = mock_get_site
    mock_db.get_all_sites = mock_get_all_sites
    mock_db.update_site = mock_update_site
    mock_db.get_active_competitors = mock_get_active_competitors
    mock_db.get_catalog_products_by_competitor = mock_get_catalog_products_by_competitor
    mock_db.delete_site = mock_delete_site
    mock_db.add_reference = mock_add_reference
    mock_db.update_competitor = mock_update_competitor
    mock_db.add_or_update_catalog_product_with_status = mock_add_or_update_catalog_product_with_status
    mock_db.add_price = mock_add_price
    mock_db.clear_tables = mock_clear_tables
    mock_db.refresh_materialized_views = mock_refresh_materialized_views
    
    return mock_db


@pytest.fixture
def search_scanner(mock_postgresql_db, mock_oxylabs_client):
    """Create a SearchScanner instance for testing."""
    return SearchScanner(mock_postgresql_db, mock_oxylabs_client)


@pytest.fixture
def site_scanner(mock_postgresql_db, mock_oxylabs_client):
    """Create a SiteScanner instance for testing."""
    return SiteScanner(mock_postgresql_db, mock_oxylabs_client)


@pytest.fixture
def temp_logs_dir():
    """Create a temporary directory for log files during testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_utc_now():
    """Mock the utc_now function to return a fixed datetime."""
    fixed_time = datetime(2025, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
    with patch('utils.helpers.utc_now', return_value=fixed_time):
        yield fixed_time


@pytest.fixture
def sample_oxylabs_response():
    """Provide a sample Oxylabs API response for testing."""
    return {
        "results": [{
            "content": {
                "results": {
                    "organic": [
                        {
                            "title": "Sample Product 1",
                            "price": 29.99,
                            "currency": "USD",
                            "merchant": {"name": "Sample Store"},
                            "url": "https://example.com/product1",
                            "pos": 1,
                            "product_id": "sample-123",
                            "rating": 4.5,
                            "reviews_count": 150
                        },
                        {
                            "title": "Sample Product 2",
                            "price": 39.99,
                            "currency": "USD",
                            "merchant": {"name": "Another Store"},
                            "url": "https://example.com/product2",
                            "pos": 2,
                            "product_id": "sample-456",
                            "rating": 4.2,
                            "reviews_count": 89
                        }
                    ]
                }
            }
        }]
    }


@pytest.fixture(scope="function")
def integration_test_db_url():
    """Provide a unique SQLite database file for integration tests to avoid file locking."""
    import uuid
    
    # Create a unique temporary database file for each test
    temp_dir = tempfile.gettempdir()
    unique_id = str(uuid.uuid4())[:8]
    db_path = os.path.join(temp_dir, f"test_integration_{unique_id}.db")
    
    yield f"sqlite:///{db_path}"
    
    # Clean up the database file after test
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except (OSError, PermissionError):
        # If we can't delete it, it's not critical for tests
        pass


@pytest.fixture(scope="function")
def integration_test_db_engine(integration_test_db_url):
    """Create a test database engine for integration tests with unique file."""
    engine = create_engine(integration_test_db_url, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    try:
        Base.metadata.drop_all(engine)
        engine.dispose()
    except Exception:
        # Ignore cleanup errors
        pass


@pytest.fixture
def integration_db(unit_test_db):
    """Create a database instance for integration tests using the working unit_test_db fixture."""
    # Use the unit_test_db fixture which we know works well with realistic mocks
    return unit_test_db


@pytest.fixture
def real_oxylabs_client():
    """Create a real OxylabsClient instance for testing (requires env vars)."""
    # Set up environment variables for OxylabsClient
    with patch.dict(os.environ, {
        'OXYLABS_USERNAME': 'test_user',
        'OXYLABS_PASSWORD': 'test_password'
    }):
        return OxylabsClient()


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Automatically set up test environment variables."""
    test_env_vars = {
        'DATABASE_TYPE': 'postgresql',
        'POSTGRESQL_HOST': 'localhost',
        'POSTGRESQL_PORT': '5432',
        'POSTGRESQL_DB': 'test_db',
        'POSTGRESQL_USER': 'test_user',
        'POSTGRESQL_PASSWORD': 'test_password',
        'OXYLABS_USERNAME': 'test_user',
        'OXYLABS_PASSWORD': 'test_password'
    }
    
    # Store original values
    original_values = {}
    for key, value in test_env_vars.items():
        original_values[key] = os.environ.get(key)
        os.environ[key] = value
    
    yield
    
    # Restore original values
    for key, original_value in original_values.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "external_api: mark test as requiring external API access"
    )
