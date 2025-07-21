# Testing Documentation for ecommiqscanner2

This directory contains comprehensive unit and integration tests for the ecommiqscanner2 project.

## Test Structure

```
tests/
├── conftest.py                 # Shared fixtures and configuration
├── pytest.ini                 # Pytest configuration
├── README.md                   # This file
├── unit/                       # Unit tests
│   ├── test_db/
│   │   ├── test_postgresql.py  # Database operations tests
│   │   └── test_models.py      # Pydantic model tests
│   ├── test_scrapers/
│   │   ├── test_search_scanner.py    # Google Shopping scanner tests
│   │   ├── test_site_scanner.py      # Direct website scanner tests (to be created)
│   │   └── test_oxylabs_client.py    # Oxylabs API client tests
│   ├── test_utils/             # Utility function tests (to be created)
│   └── test_brain/             # Relevancy calculation tests (to be created)
├── integration/                # Integration tests
│   ├── test_database_operations.py   # Database integration tests
│   ├── test_api_endpoints.py         # API endpoint tests (to be created)
│   ├── test_scraping_workflow.py     # Scraping workflow tests (to be created)
│   └── test_end_to_end.py            # End-to-end workflow tests
└── fixtures/                   # Test data and mock responses
    ├── sample_oxylabs_responses.json  # Mock API responses
    ├── sample_competitors.json        # Test competitor data (to be created)
    └── sample_catalog_products.json   # Test product data (to be created)
```

## Running Tests

### Prerequisites

1. Install test dependencies:
```bash
pip install pytest pytest-cov pytest-mock
```

2. Set up test environment variables:
```bash
# Copy .env.example to .env.test and configure test database
cp .env.example .env.test
```

### Running All Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run with verbose output
pytest -v
```

### Running Specific Test Categories

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run tests excluding slow tests
pytest -m "not slow"

# Run tests excluding external API tests
pytest -m "not external_api"
```

### Running Specific Test Files

```bash
# Run database tests
pytest tests/unit/test_db/

# Run scraper tests
pytest tests/unit/test_scrapers/

# Run integration tests
pytest tests/integration/
```

## Test Configuration

### Environment Variables

The following environment variables are automatically set for tests:

- `DATABASE_TYPE`: Set to 'postgresql'
- `DB_HOST`: Test database host
- `DB_PORT`: Test database port
- `DB_NAME`: Test database name
- `DB_USER`: Test database user
- `DB_PASSWORD`: Test database password
- `OXYLABS_USERNAME`: Test Oxylabs username
- `OXYLABS_PASSWORD`: Test Oxylabs password

### Test Database

Unit tests use an in-memory SQLite database for speed. Integration tests can use either:

1. **SQLite** (default): Fast, no setup required
2. **PostgreSQL**: Set `TEST_DATABASE_URL` environment variable

```bash
# For PostgreSQL integration tests
export TEST_DATABASE_URL="postgresql://test_user:test_pass@localhost:5432/test_ecommiq"
```

## Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit`: Unit tests (fast, isolated)
- `@pytest.mark.integration`: Integration tests (slower, with dependencies)
- `@pytest.mark.slow`: Slow-running tests
- `@pytest.mark.external_api`: Tests requiring external API access

## Fixtures

### Database Fixtures

- `test_database_url`: Provides test database URL
- `test_db_engine`: Creates test database engine
- `test_db_session`: Creates test database session
- `mock_postgresql_db`: Mock PostgreSQL database for unit tests
- `integration_db`: Real database instance for integration tests

### Model Fixtures

- `sample_competitor`: Sample CompetitorBrand instance
- `sample_site`: Sample Site instance
- `sample_catalog_product`: Sample CatalogProduct instance
- `sample_price_history`: Sample PriceHistory instance

### API Fixtures

- `mock_oxylabs_client`: Mock Oxylabs client
- `sample_oxylabs_response`: Sample API response data
- `search_scanner`: SearchScanner instance with mocks
- `site_scanner`: SiteScanner instance with mocks

### Utility Fixtures

- `temp_logs_dir`: Temporary directory for log files
- `mock_utc_now`: Fixed datetime for consistent testing
- `setup_test_environment`: Automatic environment setup

## Writing Tests

### Unit Test Example

```python
import pytest
from db.models import CompetitorBrand

@pytest.mark.unit
def test_competitor_creation(sample_competitor):
    """Test competitor model creation."""
    assert sample_competitor.id == "test-competitor-1"
    assert sample_competitor.active is True
```

### Integration Test Example

```python
import pytest

@pytest.mark.integration
def test_database_operations(integration_db, sample_competitor):
    """Test database operations with real database."""
    result = integration_db.add_reference(sample_competitor)
    assert result is True
    
    competitors = integration_db.get_active_competitors()
    assert len(competitors) == 1
```

### Mock Usage Example

```python
from unittest.mock import patch

@patch('scrapers.oxylabs_client.requests.post')
def test_api_call(mock_post, mock_oxylabs_client):
    """Test API call with mocked response."""
    mock_response = Mock()
    mock_response.json.return_value = {"results": []}
    mock_post.return_value = mock_response
    
    result = mock_oxylabs_client.scrape_google_shopping("test")
    assert "results" in result
```

## Best Practices

### Test Organization

1. **Group related tests** in classes
2. **Use descriptive test names** that explain what is being tested
3. **Follow AAA pattern**: Arrange, Act, Assert
4. **Keep tests independent** - each test should be able to run in isolation

### Mocking Guidelines

1. **Mock external dependencies** (APIs, file system, network)
2. **Use real objects for internal components** when possible
3. **Mock at the boundary** - mock the interface, not internal implementation
4. **Verify mock interactions** when behavior is important

### Performance Considerations

1. **Use in-memory databases** for unit tests
2. **Minimize database operations** in tests
3. **Use fixtures efficiently** - scope appropriately
4. **Mark slow tests** with `@pytest.mark.slow`

### Error Testing

1. **Test error conditions** explicitly
2. **Test edge cases** and boundary conditions
3. **Test data validation** and constraint violations
4. **Test recovery mechanisms** and error handling

## Continuous Integration

### GitHub Actions (Example)

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      - name: Run unit tests
        run: pytest tests/unit/ -v
      - name: Run integration tests
        run: pytest tests/integration/ -v --maxfail=5
```

### Coverage Goals

- **Unit tests**: Aim for >90% code coverage
- **Integration tests**: Focus on critical workflows
- **Overall**: Maintain >80% total coverage

## Troubleshooting

### Common Issues

1. **Database connection errors**: Check TEST_DATABASE_URL
2. **Import errors**: Ensure PYTHONPATH includes project root
3. **Fixture not found**: Check conftest.py imports
4. **Slow tests**: Use `-m "not slow"` to skip

### Debug Mode

```bash
# Run with debug output
pytest -s -vvv

# Run single test with debugging
pytest tests/unit/test_db/test_postgresql.py::TestPostgreSQLDatabase::test_add_site_success -s -vvv

# Drop into debugger on failure
pytest --pdb
```

## Contributing

When adding new features:

1. **Write tests first** (TDD approach)
2. **Add both unit and integration tests** for new functionality
3. **Update fixtures** if new test data is needed
4. **Document complex test scenarios**
5. **Ensure tests pass** before submitting PR

For questions about testing, refer to the pytest documentation or ask the development team.
