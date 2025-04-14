# EcommiQ Scanner Backend

A price monitoring service that tracks competitor product prices on Google Shopping using Oxylabs scraping API.

## Features

- Automated Google Shopping price monitoring
- Reference product and competitor brand mapping
- New product discovery through search term monitoring
- Price history tracking
- Stock status monitoring

## Database Schema

### Reference Table
- Reference brand
- Reference product name
- Reference search term
- Competitor brand to monitor

### Catalog Table
- Competitor SKU details (brand, name)
- URLs (product page, canonical)
- Reference table mapping
- Google Shopping ID
- Last updated timestamp

### Price History Table
- SKU reference
- Price
- Stock status
- Timestamp

## Modules

### Search Term Scanner
Scans Google Shopping search results for configured search terms to:
- Discover new competitor products
- Update catalog entries
- Record current prices

### Product Price Updater
Processes existing catalog entries to:
- Update prices for known products
- Track stock status changes
- Maintain price history

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure environment variables:
   - `OXYLABS_USERNAME`: Your Oxylabs username
   - `OXYLABS_PASSWORD`: Your Oxylabs password
4. Initialize the database: `python init_db.py`
5. Run the scanner: `python main.py`

## Development

Built with:
- Python 3.9+
- TinyDB for local NoSQL storage
- Oxylabs Scraper API for data collection
- aiohttp for async HTTP requests

## License

MIT License 