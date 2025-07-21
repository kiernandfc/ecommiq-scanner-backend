"""
Unit tests for SearchScanner functionality.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json
import os

from scrapers.search_scanner import SearchScanner
from db.models import CompetitorBrand, CatalogProduct


@pytest.mark.unit
class TestSearchScanner:
    """Test cases for SearchScanner class."""

    def test_init_creates_scanner(self, mock_postgresql_db, mock_oxylabs_client):
        """Test SearchScanner initialization."""
        scanner = SearchScanner(mock_postgresql_db, mock_oxylabs_client)
        
        assert scanner.db == mock_postgresql_db
        assert scanner.oxylabs == mock_oxylabs_client
        assert scanner.logger is not None
        assert scanner.non_usd_scrapes_count == 0
        assert scanner.out_of_bounds_prices_count == 0

    def test_check_all_usd_currency_valid(self, search_scanner, sample_oxylabs_response):
        """Test currency validation with all USD products."""
        result = search_scanner._check_all_usd_currency(sample_oxylabs_response)
        assert result is True

    def test_check_all_usd_currency_invalid(self, search_scanner):
        """Test currency validation with non-USD products."""
        non_usd_response = {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": "Product 1",
                                "price": 29.99,
                                "currency": "EUR",  # Non-USD
                                "merchant": {"name": "Store"},
                                "url": "https://example.com/product1",
                                "pos": 1,
                                "product_id": "test-123"
                            }
                        ]
                    }
                }
            }]
        }
        
        result = search_scanner._check_all_usd_currency(non_usd_response)
        assert result is False

    def test_check_all_usd_currency_mixed(self, search_scanner):
        """Test currency validation with mixed currencies."""
        mixed_response = {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": "Product 1",
                                "price": 29.99,
                                "currency": "USD",
                                "merchant": {"name": "Store"},
                                "url": "https://example.com/product1",
                                "pos": 1,
                                "product_id": "test-123"
                            },
                            {
                                "title": "Product 2",
                                "price": 39.99,
                                "currency": "CAD",  # Non-USD
                                "merchant": {"name": "Store"},
                                "url": "https://example.com/product2",
                                "pos": 2,
                                "product_id": "test-456"
                            }
                        ]
                    }
                }
            }]
        }
        
        result = search_scanner._check_all_usd_currency(mixed_response)
        assert result is False

    def test_dump_raw_results(self, search_scanner, sample_competitor, temp_logs_dir):
        """Test dumping raw results to file."""
        # Mock the logs directory
        search_scanner.logs_dir = temp_logs_dir
        
        test_results = {"test": "data", "products": [{"title": "Test Product"}]}
        
        # Should not raise exception
        search_scanner._dump_raw_results(test_results, sample_competitor, "test_suffix")
        
        # Check that file was created
        files = os.listdir(temp_logs_dir)
        assert len(files) == 1
        assert "raw_scrape_" in files[0]
        assert "test_suffix" in files[0]

    @patch('scrapers.search_scanner.utc_now')
    def test_scan_for_competitor_success(self, mock_utc_now, search_scanner, sample_competitor, sample_oxylabs_response):
        """Test successful competitor scanning."""
        # Mock time
        fixed_time = datetime(2025, 7, 20, 12, 0, 0)
        mock_utc_now.return_value = fixed_time
        
        # Mock Oxylabs response
        search_scanner.oxylabs.search_google_shopping.return_value = sample_oxylabs_response
        
        # Mock database operations - these are already set up in the mock_postgresql_db fixture
        # No need to override them unless we need specific test values
        
        result = search_scanner.scan_for_competitor(sample_competitor)
        
        assert "created" in result
        assert "updated" in result
        assert "errors" in result
        assert isinstance(result["created"], list)
        assert isinstance(result["updated"], list)
        assert isinstance(result["errors"], list)

    def test_scan_for_competitor_oxylabs_error(self, search_scanner, sample_competitor):
        """Test competitor scanning with Oxylabs API error."""
        # Mock Oxylabs to raise exception
        search_scanner.oxylabs.search_google_shopping.side_effect = Exception("API Error")
        
        result = search_scanner.scan_for_competitor(sample_competitor)
        
        assert len(result["errors"]) > 0
        assert len(result["created"]) == 0
        assert len(result["updated"]) == 0

    def test_scan_for_competitor_non_usd_currency(self, search_scanner, sample_competitor):
        """Test competitor scanning with non-USD currency response."""
        non_usd_response = {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": "Product 1",
                                "price": 29.99,
                                "currency": "EUR",
                                "merchant": {"name": "Store"},
                                "url": "https://example.com/product1",
                                "pos": 1,
                                "product_id": "test-123"
                            }
                        ]
                    }
                }
            }]
        }
        
        search_scanner.oxylabs.search_google_shopping.return_value = non_usd_response
        
        result = search_scanner.scan_for_competitor(sample_competitor)
        
        # Should skip processing due to non-USD currency
        assert len(result["created"]) == 0
        assert len(result["updated"]) == 0
        assert search_scanner.non_usd_scrapes_count > 0

    def test_scan_for_competitor_price_bounds_filtering(self, search_scanner, sample_competitor, sample_oxylabs_response):
        """Test price bounds filtering during scanning."""
        # Set price bounds on competitor
        sample_competitor.min_price = 25.0
        sample_competitor.max_price = 35.0
        
        # Mock response with products outside bounds
        out_of_bounds_response = {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": "Cheap Competitor Brand Product",
                                "price": 10.0,  # Below min_price
                                "currency": "USD",
                                "merchant": {"name": "Store"},
                                "url": "https://example.com/product1",
                                "pos": 1,
                                "product_id": "test-123"
                            },
                            {
                                "title": "Expensive Competitor Brand Product",
                                "price": 50.0,  # Above max_price
                                "currency": "USD",
                                "merchant": {"name": "Store"},
                                "url": "https://example.com/product2",
                                "pos": 2,
                                "product_id": "test-456"
                            },
                            {
                                "title": "Valid Competitor Brand Product",
                                "price": 30.0,  # Within bounds
                                "currency": "USD",
                                "merchant": {"name": "Store"},
                                "url": "https://example.com/product3",
                                "pos": 3,
                                "product_id": "test-789"
                            }
                        ]
                    }
                }
            }]
        }
        
        search_scanner.oxylabs.search_google_shopping.return_value = out_of_bounds_response
        search_scanner.db.add_or_update_catalog_product_with_status.return_value = ("prod-1", True)
        # Mock add_price to return OUT_OF_BOUNDS for prices outside bounds (10.0, 50.0) and price ID for valid price (30.0)
        search_scanner.db.add_price.side_effect = ["OUT_OF_BOUNDS", "OUT_OF_BOUNDS", "price-123"]

        
        result = search_scanner.scan_for_competitor(sample_competitor)
        
        # Should only process the valid product
        assert search_scanner.out_of_bounds_prices_count == 2

    @patch('scrapers.search_scanner.concurrent.futures.ThreadPoolExecutor')
    def test_scan_all_competitors_parallel(self, mock_executor, search_scanner, sample_competitor):
        """Test parallel scanning of all competitors."""
        # Mock database to return competitors
        search_scanner.db.get_active_competitors.return_value = [sample_competitor]

        
        # Mock executor
        mock_future = Mock()
        mock_future.result.return_value = {
            "created": [],
            "updated": [],
            "errors": []
        }
        mock_executor.return_value.__enter__.return_value.submit.return_value = mock_future
        mock_executor.return_value.__enter__.return_value.as_completed.return_value = [mock_future]
        
        result = search_scanner.scan_all_competitors(show_progress=False, max_workers=2)
        
        assert "created" in result
        assert "updated" in result
        assert "errors" in result
        assert "duration_seconds" in result
        assert "by_reference" in result

    def test_scan_all_competitors_no_competitors(self, search_scanner):
        """Test scanning when no active competitors exist."""
        search_scanner.db.get_active_competitors.return_value = []

        
        result = search_scanner.scan_all_competitors()
        
        assert len(result["created"]) == 0
        assert len(result["updated"]) == 0
        assert len(result["errors"]) == 0
        assert result["duration_seconds"] >= 0

    def test_scan_all_competitors_with_filter(self, search_scanner, sample_competitor):
        """Test scanning with competitor ID filter."""
        # Create Google Shopping competitors (without site_id)
        google_competitor1 = CompetitorBrand(
            id="test-competitor-1",
            reference_brand="TestBrand",
            reference_product="Test Product",
            competitor_brand="Competitor Brand",
            search_query="test product search",
            site_id=None,  # Google Shopping competitor
            active=True
        )
        competitor2 = CompetitorBrand(
            id="test-competitor-2",
            reference_brand="TestBrand2",
            reference_product="Test Product 2",
            competitor_brand="Competitor Brand 2",
            search_query="test product search 2",
            site_id=None,  # Google Shopping competitor
            active=True
        )
        
        search_scanner.db.get_active_competitors.return_value = [google_competitor1, competitor2]

        
        # Mock scan results
        def mock_scan_for_competitor(competitor):
            return {
                "created": [],
                "updated": [],
                "errors": []
            }
        
        search_scanner.scan_for_competitor = Mock(side_effect=mock_scan_for_competitor)
        
        # Scan with filter
        result = search_scanner.scan_all_competitors(competitor_id="test-competitor-1")
        
        # Should only scan the filtered competitor
        search_scanner.scan_for_competitor.assert_called_once()
        called_competitor = search_scanner.scan_for_competitor.call_args[0][0]
        assert called_competitor.id == "test-competitor-1"

    def test_scan_all_competitors_error_handling(self, search_scanner, sample_competitor):
        """Test error handling during parallel scanning."""
        # Create a Google Shopping competitor (without site_id)
        google_competitor = CompetitorBrand(
            id="test-competitor-1",
            reference_brand="TestBrand",
            reference_product="Test Product",
            competitor_brand="Competitor Brand",
            search_query="test product search",
            site_id=None,  # Google Shopping competitor
            active=True
        )
        search_scanner.db.get_active_competitors.return_value = [google_competitor]

        
        # Mock scan_for_competitor to raise exception
        search_scanner.scan_for_competitor = Mock(side_effect=Exception("Scan error"))
        
        result = search_scanner.scan_all_competitors(show_progress=False, max_workers=1)
        
        # Should capture the error
        assert len(result["errors"]) > 0
        assert "Scan error" in str(result["errors"][0])


@pytest.mark.unit
class TestSearchScannerDataProcessing:
    """Test data processing and validation in SearchScanner."""

    def test_product_data_extraction(self, search_scanner, sample_competitor, sample_oxylabs_response):
        """Test extraction of product data from Oxylabs response."""
        # Create a Google Shopping competitor (without site_id)
        google_competitor = CompetitorBrand(
            id="test-competitor-1",
            reference_brand="TestBrand",
            reference_product="Test Product",
            competitor_brand="Sample",  # Match the product titles in sample_oxylabs_response
            search_query="test product search",
            site_id=None,  # Google Shopping competitor
            active=True
        )
        
        search_scanner.oxylabs.search_google_shopping.return_value = sample_oxylabs_response
        search_scanner.db.add_or_update_catalog_product_with_status.return_value = ("prod-1", True)
        search_scanner.db.add_price.return_value = True

        
        result = search_scanner.scan_for_competitor(google_competitor)
        
        # Verify database was called with correct product data
        search_scanner.db.add_or_update_catalog_product_with_status.assert_called()
        call_args = search_scanner.db.add_or_update_catalog_product_with_status.call_args[0][0]
        
        assert isinstance(call_args, CatalogProduct)
        # Should be one of the sample products
        assert call_args.title in ["Sample Product 1", "Sample Product 2"]
        assert call_args.price is None  # Price is stored separately in PriceHistory
        assert call_args.currency == "USD"
        assert call_args.link in ["https://example.com/product1", "https://example.com/product2"]
        
        # Verify price was added separately
        search_scanner.db.add_price.assert_called()

    def test_merchant_filtering(self, search_scanner, sample_competitor):
        """Test filtering of products by merchant."""
        # Create a Google Shopping competitor (without site_id)
        google_competitor = CompetitorBrand(
            id="test-competitor-1",
            reference_brand="TestBrand",
            reference_product="Test Product",
            competitor_brand="TestBrand",  # Match the product titles
            search_query="test product search",
            site_id=None,  # Google Shopping competitor
            active=True
        )
        
        response_with_merchants = {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": "TestBrand Product from Amazon",
                                "price": 29.99,
                                "currency": "USD",
                                "merchant": {"name": "Amazon.com"},
                                "url": "https://amazon.com/product1",
                                "pos": 1,
                                "product_id": "amazon-123"
                            },
                            {
                                "title": "TestBrand Product from eBay",
                                "price": 25.99,
                                "currency": "USD",
                                "merchant": {"name": "eBay"},
                                "url": "https://ebay.com/product2",
                                "pos": 2,
                                "product_id": "ebay-456"
                            }
                        ]
                    }
                }
            }]
        }
        
        search_scanner.oxylabs.search_google_shopping.return_value = response_with_merchants
        search_scanner.db.add_or_update_catalog_product_with_status.return_value = ("prod-1", True)
        search_scanner.db.add_price.return_value = True

        
        result = search_scanner.scan_for_competitor(google_competitor)
        
        # Should process only Amazon product (eBay should be filtered out)
        assert search_scanner.db.add_or_update_catalog_product_with_status.call_count == 1
        
        # Verify the skipped merchant count increased
        assert search_scanner.skipped_merchant_filter_count > 0

    def test_missing_product_id_handling(self, search_scanner, sample_competitor):
        """Test handling of products with missing product_id."""
        response_missing_id = {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": "Product without ID",
                                "price": 29.99,
                                "currency": "USD",
                                "merchant": {"name": "Store"},
                                "url": "https://example.com/product1",
                                "pos": 1
                                # Missing product_id
                            }
                        ]
                    }
                }
            }]
        }
        
        search_scanner.oxylabs.search_google_shopping.return_value = response_missing_id

        
        result = search_scanner.scan_for_competitor(sample_competitor)
        
        # Should skip products without product_id
        assert search_scanner.skipped_missing_product_id_count > 0
        assert search_scanner.db.add_or_update_catalog_product_with_status.call_count == 0
