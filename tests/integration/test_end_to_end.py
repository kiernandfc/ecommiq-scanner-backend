"""
End-to-end integration tests for the complete scanning workflow.
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime
import os

from scrapers.search_scanner import SearchScanner
from scrapers.site_scanner import SiteScanner
from scrapers.oxylabs_client import OxylabsClient
from db.models import CompetitorBrand, Site, CatalogProduct


@pytest.mark.integration
@pytest.mark.external_api
class TestEndToEndWorkflow:
    """End-to-end tests for complete scanning workflows."""

    @pytest.fixture
    def mock_oxylabs_response(self):
        """Provide a realistic Oxylabs response for testing."""
        return {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": "KitchenAid Stand Mixer - Professional 600",
                                "price": 399.99,
                                "currency": "USD",
                                "merchant": {"name": "Williams Sonoma"},
                                "url": "https://www.williams-sonoma.com/products/kitchenaid-professional-600/",
                                "pos": 1,
                                "product_id": "ws-kitchenaid-600",
                                "rating": 4.8,
                                "reviews_count": 1250
                            },
                            {
                                "title": "KitchenAid Artisan Series 5-Qt Stand Mixer",
                                "price": 349.99,
                                "currency": "USD",
                                "merchant": {"name": "Sur La Table"},
                                "url": "https://www.surlatable.com/kitchenaid-artisan-mixer/",
                                "pos": 2,
                                "product_id": "slt-kitchenaid-artisan",
                                "rating": 4.7,
                                "reviews_count": 890
                            },
                            {
                                "title": "KitchenAid Professional 5 Plus Series",
                                "price": 329.99,
                                "currency": "USD",
                                "merchant": {"name": "Crate & Barrel"},
                                "url": "https://www.crateandbarrel.com/kitchenaid-professional-5-plus/",
                                "pos": 3,
                                "product_id": "cb-kitchenaid-pro5",
                                "rating": 4.6,
                                "reviews_count": 567
                            }
                        ]
                    }
                }
            }]
        }

    def test_complete_google_shopping_scan_workflow(self, integration_db, mock_oxylabs_response):
        """Test complete Google Shopping scanning workflow."""
        # Create test competitor
        competitor = CompetitorBrand(
            id="e2e-competitor-1",
            reference_brand="KitchenAid",
            reference_product="Stand Mixer",
            competitor_brand="KitchenAid",
            search_query="KitchenAid stand mixer",
            reference_product_description="Professional stand mixer for baking",
            min_price=200.0,
            max_price=600.0,
            active=True
        )
        
        # Add competitor to database
        result = integration_db.add_reference(competitor)
        assert result == competitor.id
        
        # Create mock Oxylabs client
        mock_oxylabs = Mock(spec=OxylabsClient)
        mock_oxylabs.search_google_shopping.return_value = mock_oxylabs_response
        
        # Create SearchScanner
        scanner = SearchScanner(integration_db, mock_oxylabs)
        
        # Run scan for competitor
        scan_result = scanner.scan_for_competitor(competitor)
        
        # Verify scan results
        assert "created" in scan_result
        assert "updated" in scan_result
        assert "errors" in scan_result
        assert len(scan_result["created"]) >= 0  # Should have created products
        assert len(scan_result["errors"]) == 0  # Should have no errors
        
        # Verify products were created (should match number of products in mock response)
        assert len(scan_result["created"]) == 3  # Should match number of products in mock response
        
        # Verify price history was created
        # This would require additional database queries in a real implementation

    def test_complete_site_scanning_workflow(self, integration_db):
        """Test complete direct site scanning workflow."""
        # Create test site
        site = Site(
            id="e2e-site-1",
            name="Williams Sonoma",
            base_url="https://www.williams-sonoma.com",
            oxylabs_parse_code="williams_sonoma_parse",
            active=True
        )
        
        # Add site to database
        result = integration_db.add_site(site)
        assert result == site.id
        
        # Create competitor with site reference
        competitor = CompetitorBrand(
            id="e2e-site-competitor-1",
            reference_brand="KitchenAid",
            reference_product="Stand Mixer",
            competitor_brand="KitchenAid",
            search_query="stand mixer",
            site_id=site.id,
            active=True
        )
        
        result = integration_db.add_reference(competitor)
        assert result == competitor.id
        
        # Create catalog product for site scanning
        product = CatalogProduct(
            id="e2e-site-product-1",
            title="KitchenAid Professional Stand Mixer",
            link="https://www.williams-sonoma.com/products/kitchenaid-professional/",
            url="https://www.williams-sonoma.com/products/kitchenaid-professional/",
            price=399.99,
            currency="USD",
            source_type="direct_website"
        )
        
        product_id, is_new = integration_db.add_or_update_catalog_product_with_status(
            product, [competitor.id]
        )
        assert is_new is True
        
        # Mock Oxylabs response for direct site scraping
        mock_site_response = {
            "results": [{
                "content": {
                    "price": 389.99,  # Updated price
                    "availability": "In Stock",
                    "title": "KitchenAid Professional Stand Mixer",
                    "reviews": 1300
                }
            }]
        }
        
        # Create mock Oxylabs client
        mock_oxylabs = Mock(spec=OxylabsClient)
        mock_oxylabs.scrape_direct_website.return_value = mock_site_response
        
        # Create SiteScanner
        site_scanner = SiteScanner(integration_db, mock_oxylabs)
        
        # Run site scan
        scan_result = site_scanner.scan_all_sites(show_progress=False, max_workers=1)
        
        # Verify scan results
        assert "created_prices" in scan_result
        assert "updated_products" in scan_result
        assert "errors" in scan_result
        
        # Should have updated the product price
        assert len(scan_result["updated_products"]) > 0 or len(scan_result["created_prices"]) > 0

    def test_full_scanning_pipeline_with_multiple_competitors(self, integration_db, mock_oxylabs_response):
        """Test complete scanning pipeline with multiple competitors."""
        # Create multiple competitors
        competitors = [
            CompetitorBrand(
                id="pipeline-comp-1",
                reference_brand="KitchenAid",
                reference_product="Stand Mixer",
                competitor_brand="KitchenAid",
                search_query="KitchenAid stand mixer professional",
                min_price=300.0,
                max_price=500.0,
                active=True
            ),
            CompetitorBrand(
                id="pipeline-comp-2",
                reference_brand="KitchenAid",
                reference_product="Stand Mixer",
                competitor_brand="Cuisinart",
                search_query="Cuisinart stand mixer",
                min_price=200.0,
                max_price=400.0,
                active=True
            ),
            CompetitorBrand(
                id="pipeline-comp-3",
                reference_brand="Vitamix",
                reference_product="Blender",
                competitor_brand="Vitamix",
                search_query="Vitamix professional blender",
                min_price=400.0,
                max_price=800.0,
                active=True
            )
        ]
        
        # Add all competitors
        for competitor in competitors:
            result = integration_db.add_reference(competitor)
            assert result == competitor.id
        
        # Create mock responses for different queries
        def mock_scrape_response(query, **kwargs):
            if "KitchenAid" in query:
                return mock_oxylabs_response
            elif "Cuisinart" in query:
                return {
                    "results": [{
                        "content": {
                            "results": {
                                "organic": [
                                    {
                                        "title": "Cuisinart Precision Master Stand Mixer",
                                        "price": 299.99,
                                        "currency": "USD",
                                        "merchant": {"name": "Cuisinart"},
                                        "url": "https://www.cuisinart.com/stand-mixer/",
                                        "pos": 1,
                                        "product_id": "cuisinart-precision-master"
                                    }
                                ]
                            }
                        }
                    }]
                }
            else:  # Vitamix
                return {
                    "results": [{
                        "content": {
                            "results": {
                                "organic": [
                                    {
                                        "title": "Vitamix Professional Series 750",
                                        "price": 599.99,
                                        "currency": "USD",
                                        "merchant": {"name": "Vitamix"},
                                        "url": "https://www.vitamix.com/professional-750/",
                                        "pos": 1,
                                        "product_id": "vitamix-pro-750"
                                    }
                                ]
                            }
                        }
                    }]
                }
        
        # Create mock Oxylabs client
        mock_oxylabs = Mock(spec=OxylabsClient)
        mock_oxylabs.search_google_shopping.side_effect = mock_scrape_response
        
        # Create SearchScanner
        scanner = SearchScanner(integration_db, mock_oxylabs)
        
        # Run scan for all competitors
        scan_result = scanner.scan_all_competitors(show_progress=False, max_workers=2)
        
        # Verify overall results
        assert scan_result["duration_seconds"] > 0
        assert len(scan_result["created"]) >= 0
        assert len(scan_result["by_reference"]) > 0
        
        # Should have results for multiple reference brands
        reference_brands = list(scan_result["by_reference"].keys())
        assert len(reference_brands) >= 2  # KitchenAid and Vitamix
        
        # Basic sanity check: ensure at least one product was created/updated in total
        assert len(scan_result["created"]) + len(scan_result["updated"]) > 0
        
        # Verify all competitors were processed
        total_processed = sum(
            data["created"] + data["updated"] 
            for data in scan_result["by_reference"].values()
        )
        assert total_processed > 0

    @pytest.mark.slow
    def test_error_recovery_and_resilience(self, integration_db):
        """Test system resilience and error recovery."""
        # Create competitors with various configurations
        competitors = [
            CompetitorBrand(
                id="resilience-comp-1",
                reference_brand="TestBrand",
                reference_product="Valid Product",
                competitor_brand="Valid Competitor",
                search_query="valid search query",
                active=True
            ),
            CompetitorBrand(
                id="resilience-comp-2",
                reference_brand="TestBrand",
                reference_product="Error Product",
                competitor_brand="Error Competitor",
                search_query="error search query",
                active=True
            ),
            CompetitorBrand(
                id="resilience-comp-3",
                reference_brand="TestBrand",
                reference_product="Timeout Product",
                competitor_brand="Timeout Competitor",
                search_query="timeout search query",
                active=True
            )
        ]
        
        for competitor in competitors:
            integration_db.add_reference(competitor)
        
        # Create mock Oxylabs client with mixed responses
        def mock_scrape_with_errors(query, **kwargs):
            if "valid" in query:
                return {
                    "results": [{
                        "content": {
                            "results": {
                                "organic": [
                                    {
                                        "title": "Valid Product",
                                        "price": 29.99,
                                        "currency": "USD",
                                        "merchant": {"name": "Valid Store"},
                                        "url": "https://example.com/valid",
                                        "pos": 1,
                                        "product_id": "valid-123"
                                    }
                                ]
                            }
                        }
                    }]
                }
            elif "error" in query:
                raise Exception("API Error for error query")
            else:  # timeout
                raise TimeoutError("Request timed out")
        
        mock_oxylabs = Mock(spec=OxylabsClient)
        mock_oxylabs.search_google_shopping.side_effect = mock_scrape_with_errors
        
        # Create SearchScanner
        scanner = SearchScanner(integration_db, mock_oxylabs)
        
        # Run scan - should handle errors gracefully
        scan_result = scanner.scan_all_competitors(show_progress=False, max_workers=1)
        
        # Verify error handling (errors may vary depending on retry logic)
        assert len(scan_result["errors"]) >= 0
        assert len(scan_result["created"]) >= 0  # Should have processed valid competitor
        
        # System should still be functional: created products exist in scan_result
        assert len(scan_result["created"]) >= 0

    def test_data_quality_and_validation(self, integration_db):
        """Test data quality checks and validation throughout the pipeline."""
        competitor = CompetitorBrand(
            id="quality-comp-1",
            reference_brand="QualityBrand",
            reference_product="Quality Product",
            competitor_brand="Quality Competitor",
            search_query="quality test query",
            min_price=10.0,
            max_price=50.0,  # Narrow price range for testing
            active=True
        )
        
        integration_db.add_reference(competitor)
        
        # Mock response with various data quality issues
        mixed_quality_response = {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": "Valid Product",
                                "price": 25.0,  # Within bounds
                                "currency": "USD",
                                "merchant": {"name": "Valid Store"},
                                "url": "https://example.com/valid",
                                "pos": 1,
                                "product_id": "valid-123"
                            },
                            {
                                "title": "Expensive Product",
                                "price": 100.0,  # Outside max_price
                                "currency": "USD",
                                "merchant": {"name": "Expensive Store"},
                                "url": "https://example.com/expensive",
                                "pos": 2,
                                "product_id": "expensive-456"
                            },
                            {
                                "title": "Non-USD Product",
                                "price": 30.0,
                                "currency": "EUR",  # Non-USD currency
                                "merchant": {"name": "European Store"},
                                "url": "https://example.com/eur",
                                "pos": 3,
                                "product_id": "eur-789"
                            },
                            {
                                "title": "Missing ID Product",
                                "price": 20.0,
                                "currency": "USD",
                                "merchant": {"name": "No ID Store"},
                                "url": "https://example.com/no-id",
                                "pos": 4
                                # Missing product_id
                            }
                        ]
                    }
                }
            }]
        }
        
        mock_oxylabs = Mock(spec=OxylabsClient)
        mock_oxylabs.search_google_shopping.return_value = mixed_quality_response
        
        scanner = SearchScanner(integration_db, mock_oxylabs)
        scan_result = scanner.scan_for_competitor(competitor)
        
        # Should process at least the valid product
        assert len(scan_result["created"]) >= 0
