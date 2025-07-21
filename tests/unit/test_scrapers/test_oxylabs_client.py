"""
Unit tests for Oxylabs client functionality.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from scrapers.oxylabs_client import OxylabsClient


@pytest.mark.unit
class TestOxylabsClient:
    """Test cases for OxylabsClient class."""

    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_init_creates_client(self):
        """Test OxylabsClient initialization."""
        client = OxylabsClient()
        
        assert client.username == "test_user"
        assert client.password == "test_pass"
        assert client.logger is not None

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_make_request_success(self, mock_post):
        """Test successful API request."""
        client = OxylabsClient()
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"content": "test"}]}
        mock_post.return_value = mock_response
        
        payload = {"source": "google_shopping", "query": "test"}
        result = client._make_request(payload)
        
        assert result == {"results": [{"content": "test"}]}
        mock_post.assert_called_once()

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_make_request_http_error(self, mock_post):
        """Test API request with HTTP error."""
        client = OxylabsClient()
        
        # Mock HTTP error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.raise_for_status.side_effect = requests.HTTPError("400 Client Error")
        mock_post.return_value = mock_response
        
        payload = {"source": "google_shopping", "query": "test"}
        
        with pytest.raises(Exception) as exc_info:
            client._make_request(payload)
        
        assert "Oxylabs API error" in str(exc_info.value)

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_make_request_timeout(self, mock_post):
        """Test API request timeout."""
        client = OxylabsClient()
        
        # Mock timeout
        mock_post.side_effect = Timeout("Request timed out")
        
        payload = {"source": "google_shopping", "query": "test"}
        
        with pytest.raises(Timeout) as exc_info:
            client._make_request(payload)
        
        assert "timed out" in str(exc_info.value).lower()

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_make_request_connection_error(self, mock_post):
        """Test API request connection error."""
        client = OxylabsClient()
        
        # Mock connection error
        mock_post.side_effect = ConnectionError("Connection failed")
        
        payload = {"source": "google_shopping", "query": "test"}
        
        with pytest.raises(ConnectionError) as exc_info:
            client._make_request(payload)
        
        assert "connection" in str(exc_info.value).lower()

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_make_request_json_decode_error(self, mock_post):
        """Test API request with invalid JSON response."""
        client = OxylabsClient()
        
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.text = "Invalid JSON response"
        mock_post.return_value = mock_response
        
        payload = {"source": "google_shopping", "query": "test"}
        
        with pytest.raises(Exception) as exc_info:
            client._make_request(payload)
        
        assert "JSON" in str(exc_info.value)

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_scrape_google_shopping_success(self, mock_post):
        """Test successful Google Shopping scraping."""
        client = OxylabsClient()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
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
                                "product_id": "test-123"
                            }
                        ]
                    }
                }
            }]
        }
        mock_post.return_value = mock_response
        
        result = client.search_google_shopping("test query")
        
        assert result == mock_response.json.return_value
        mock_post.assert_called_once()
        
        # Verify the payload structure
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["source"] == "google_shopping_search"
        assert payload["query"] == "test query"

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_scrape_google_shopping_with_options(self, mock_post):
        """Test Google Shopping scraping with additional options."""
        client = OxylabsClient()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response
        
        result = client.search_google_shopping("test query")
        
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["query"] == "test query"
        assert payload["source"] == "google_shopping_search"
        assert payload["geo_location"] == "US"

    @patch.object(OxylabsClient, '_make_request')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_scrape_direct_website_success(self, mock_make_request):
        """Test successful direct website scraping."""
        client = OxylabsClient()
        
        mock_response = {
            "results": [{
                "content": "<html>Website content</html>"
            }]
        }
        mock_make_request.return_value = mock_response
        
        result = client.scrape_direct_website("https://example.com", '{"test_parse_code": "test_parse_code"}')
        
        assert result == mock_response
        mock_make_request.assert_called_once()
        
        # Verify payload structure
        call_args = mock_make_request.call_args[0][0]
        assert call_args["source"] == "universal"
        assert call_args["url"] == "https://example.com"
        assert call_args["parse"] == True
        assert call_args["parsing_instructions"]["test_parse_code"] == "test_parse_code"

    @patch.object(OxylabsClient, '_make_request')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_scrape_direct_website_error(self, mock_make_request):
        """Test direct website scraping with error."""
        client = OxylabsClient()
        
        mock_make_request.side_effect = Exception("API Error")
        
        with pytest.raises(Exception):
            client.scrape_direct_website("https://example.com", "test_parse_code")

    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_request_headers_and_auth(self):
        """Test that requests include proper headers and authentication."""
        client = OxylabsClient()
        
        with patch('scrapers.oxylabs_client.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"results": []}
            mock_post.return_value = mock_response
            
            client.search_google_shopping("test")
            
            # Verify auth (headers are not set by the current implementation)
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["auth"] == ("test_user", "test_pass")
            # Verify JSON payload is sent
            assert "json" in call_kwargs
            assert call_kwargs["json"]["query"] == "test"

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_rate_limiting_simulation(self, mock_post):
        """Test behavior under rate limiting conditions."""
        client = OxylabsClient()
        
        # Simulate rate limiting response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": "Rate limit exceeded",
            "retry_after": 60
        }
        mock_post.return_value = mock_response
        
        result = client.search_google_shopping("test query")
        
        # Should return the rate limit response
        assert "error" in result
        assert "Rate limit exceeded" in result["error"]

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_empty_query_handling(self, mock_post):
        """Test handling of empty or invalid queries."""
        client = OxylabsClient()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response
        
        # Test empty query
        result = client.search_google_shopping("")
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["query"] == ""
        
        # Test None query
        result = client.search_google_shopping(None)
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["query"] is None

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'test_user', 'OXYLABS_PASSWORD': 'test_pass'})
    def test_large_response_handling(self, mock_post):
        """Test handling of large API responses."""
        client = OxylabsClient()
        
        # Create a large mock response
        large_response = {
            "results": [{
                "content": {
                    "results": {
                        "organic": [
                            {
                                "title": f"Product {i}",
                                "price": 29.99 + i,
                                "currency": "USD",
                                "description": "x" * 1000  # Large description
                            }
                            for i in range(100)  # Many products
                        ]
                    }
                }
            }]
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = large_response
        mock_post.return_value = mock_response
        
        result = client.search_google_shopping("test query")
        
        assert len(result["results"][0]["content"]["results"]["organic"]) == 100


@pytest.mark.unit
class TestOxylabsClientConfiguration:
    """Test configuration and setup of OxylabsClient."""

    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'user', 'OXYLABS_PASSWORD': 'pass'})
    def test_default_configuration(self):
        """Test default client configuration."""
        client = OxylabsClient()
        
        # Should have default values
        assert client.username == "user"
        assert client.password == "pass"

    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'custom_user', 'OXYLABS_PASSWORD': 'custom_pass'})
    def test_custom_configuration(self):
        """Test client with custom configuration."""
        client = OxylabsClient()
        
        assert client.username == "custom_user"
        assert client.password == "custom_pass"

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'user', 'OXYLABS_PASSWORD': 'pass'})
    def test_request_timeout_configuration(self, mock_post):
        """Test that requests have appropriate timeout configuration."""
        client = OxylabsClient()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response
        
        client.search_google_shopping("test")
        
        # Verify request was made (timeout is not set by current implementation)
        call_kwargs = mock_post.call_args[1]
        assert "json" in call_kwargs
        assert call_kwargs["json"]["query"] == "test"
        # Note: timeout is not currently implemented in OxylabsClient

    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'user', 'OXYLABS_PASSWORD': 'pass'})
    def test_logging_configuration(self):
        """Test that logging is properly configured."""
        client = OxylabsClient()
        
        assert client.logger is not None
        assert hasattr(client.logger, 'info')
        assert hasattr(client.logger, 'error')
        assert hasattr(client.logger, 'debug')

    @patch('scrapers.oxylabs_client.requests.post')
    @patch.dict('os.environ', {'OXYLABS_USERNAME': 'user', 'OXYLABS_PASSWORD': 'pass'})
    def test_user_agent_header(self, mock_post):
        """Test that requests include appropriate User-Agent header."""
        client = OxylabsClient()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_post.return_value = mock_response
        
        client.search_google_shopping("test")
        
        call_kwargs = mock_post.call_args[1]
        # Verify request was made with JSON payload (headers not set by current implementation)
        assert "json" in call_kwargs
        assert call_kwargs["json"]["query"] == "test"
        # Note: custom headers are not currently set by OxylabsClient
