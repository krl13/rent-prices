# 🏠 Halo Oglasi — Rental Apartment Scraper

A web scraper that collects rental apartment listings from [halooglasi.com](https://www.halooglasi.com).

## Data Collected

| Column | Description |
|--------|-------------|
| Title | Listing title |
| Price (€) | Price in euros |
| Square Meters | Apartment size |
| Number of Rooms | Number of rooms |
| Floor | Floor number |
| Number of Floors | Total floors in building |
| City | City |
| Municipality | Municipality |
| Neighborhood | Neighborhood |
| Street | Street |
| Advertiser Type | Owner / Agency / Investor |
| Date Posted | Date the listing was posted |
| Link | Listing URL |
| scraped_at | Timestamp of when the data was scraped |

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/your-username/halooglasi-scraper.git
cd halooglasi-scraper

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser
playwright install chromium
```

## Usage

```bash
# Basic — scrape Belgrade, all pages
python rent_scraper.py

# Specific city
python rent_scraper.py --city novisad

# Limit pages (useful for testing)
python rent_scraper.py --city beograd --max-pages 5

# All options
python rent_scraper.py --city beograd --max-pages 10 --delay-min 2 --delay-max 5 --output-file beograd.csv
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--city` | beograd | City to scrape |
| `--max-pages` | all | Maximum number of pages to scrape |
| `--delay-min` | 2 | Minimum delay between requests (seconds) |
| `--delay-max` | 5 | Maximum delay between requests (seconds) |
| `--headless` | True | Browser visibility (False = show browser) |
| `--output-file` | rent_listings.csv | Output CSV filename |

## Running Tests

```bash
pip install pytest
pytest test_scraper.py -v
```

## Project Structure

```
halooglasi-scraper/
├── rent_scraper.py       # Main scraper
├── test_scraper.py       # Parser tests
├── requirements.txt      # Python dependencies
├── .gitignore            # Ignored files
└── README.md             # This file
```

## Notes

- The scraper uses random delays between requests to avoid overloading the server
- The CSV file is automatically updated without duplicates on each run
- Logs are saved to `scraper.log`

## Disclaimer

This scraper was built for educational purposes. Use it responsibly and in accordance with the [terms of service](https://www.halooglasi.com) of the website.