"""
Web scraper for rental apartment listings on Halo Oglasi.

Author: Vuk Krstić
Description: This script scrapes rental apartment listings from the Halo Oglasi website for a specified city. 
It extracts details such as title, price, square meters, number of rooms, location, advertiser type, and date posted. 
The data is saved to a CSV file. 
Usage: Run the script and it will scrape listings for Belgrade by default.
"""

#import necessary libraries
import os
import urllib3
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
import time
import logging
import argparse
from functools import wraps
from typing import Optional

#config
CONFIG = {
    "base_url": "https://www.halooglasi.com/nekretnine/izdavanje-stanova",
    "city": "beograd",
    "delay_seconds": 1.5,
    "output_file": "rent_listings.csv",
    "max_pages": None,
    "max_retries": 3,
    "retry_dealy_seconds": 2,
    "headers": {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept-Language': 'en-US,en;q=0.5'}
}

#logging setup
def setup_logger(log_file: str = "scraper.log") -> logging.Logger:
    """
    Sets up a logger to log messages to both console and a file.
    """
    logger = logging.getLogger("halooglasi")
    logger.setLever(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s - [%(levelname)-8s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()

def retry(max_attepts: int = 3, delay_seconds: int = 2):
    """
    Decorator to retry a function if it raises an exception.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attepts + 1):
                try:
                    result = func(*args, **kwargs)
                    if result is not None:
                        return result
                except Exception as e:
                    logger.warning(f"Attempt {attempt} failed with error: {e}")
                
                if attempt < max_attepts:
                    wait = delay_seconds * attempt
                    logger.warning(f"[{func.__name__}] Attempt {attempt} failed. Retrying in {wait} seconds...")
                    time.sleep(wait)
                
                logger.error(f"[{func.__name__}] All {max_attepts} attempts failed.")
                return None
        return wrapper
    return decorator

#parse functions

def parse_title_and_link(ad) -> dict:
    """
    Extracts the title and link from an ad element.
    """
    result = {"Title": None, "Link": None}
    title_tag = ad.find('h3', class_='product-title')
    if not title_tag:
        return result
    
    result["Title"] = title_tag.text.strip()
    a_tag = title_tag.find("a")
    if a_tag and "href" in a_tag.attrs:
        result["Link"] = "https://www.halooglasi.com" + a_tag["href"]

    return result

def parse_price(ad) -> Optional[int]:
    """
    Extracts the price from an ad element and returns it as an integer.
    """
    price_div = ad.find("div", class_="central-feature")
    if not price_div:
        return None
 
    digits = re.sub(r"[^\d]", "", price_div.text)
    return int(digits) if digits else None

def parse_floor(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parses the floor information from a text string and returns the floor and total floors.
    """
    clean = text.replace("Spratnost", "").strip()
    if "/" in clean:
        parts = clean.split("/", 1)
        return parts[0].strip(), parts[1].strip()
    return clean or None, None

def parse_attributes(ad) -> dict:
    """
    Extracts attributes such as square meters, number of rooms, and floor information from an ad element.
    """
    result = {
        "Square Meters"  : None,
        "Number of Rooms": None,
        "Floor"          : None,
        "Number of Floors": None,
    }
 
    for wrapper in ad.findAll("div", class_="value-wrapper"):
        text = wrapper.text.strip()
 
        if "Kvadratura" in text:
            match = re.search(r"\d+", text)
            if match:
                result["Square Meters"] = int(match.group())
 
        elif "Broj soba" in text:
            match = re.search(r"\d+(\.\d+)?", text)
            if match:
                result["Number of Rooms"] = float(match.group())
 
        elif "Spratnost" in text:
            result["Floor"], result["Number of Floors"] = parse_floor(text)
 
    return result

def parse_location(ad) -> dict:
    """
    Extracts location information such as city, municipality, neighborhood, and street from an ad element.
    """
    keys = ["City", "Municipality", "Neighborhood", "Street"]
    result = dict.fromkeys(keys)
 
    location_ul = ad.find("ul", class_="subtitle-places")
    if not location_ul:
        return result
 
    places = [li.text.strip() for li in location_ul.find_all("li")]
    for i, key in enumerate(keys):
        result[key] = places[i] if i < len(places) else None
 
    return result

def parse_advertiser(ad) -> Optional[str]:
    """
    Extracts the advertiser type from an ad element and returns it as a standardized string.
    """
    span = ad.find("span", attrs={"data-field-name": "oglasivac_nekretnine_s"})
    if not span:
        return None
 
    mapping = {"vlasnik": "Owner", "agencija": "Agency", "Investitor": "Investor"}
    raw = span.get("data-field-value", span.text).strip().lower()
    return mapping.get(raw, raw.title())

def parse_date(ad) -> Optional[datetime]:
    """
    Extracts the date posted from an ad element and returns it as a datetime object.
    """
    date_span = ad.find("span", class_="publish-date")
    if not date_span:
        return None
    try:
        return datetime.strptime(date_span.text.strip(), "%d.%m.%Y.")
    except ValueError:
        logger.debug(f"Could not parse date: '{date_span.text.strip()}'")
        return None
    
def parse_single_ad(ad) -> dict:
    """
    Composes all parsing functions to extract all relevant information from a single ad element and returns it as a dictionary.
    """
    record = {}
    record.update(parse_title_and_link(ad))
    record["Price (€)"] = parse_price(ad)
    record.update(parse_attributes(ad))
    record.update(parse_location(ad))
    record["Advertiser Type"] = parse_advertiser(ad)
    record["Date Posted"]     = parse_date(ad)
    return record

#html fetching function
@retry(max_attepts=CONFIG["max_retries"], delay_seconds=CONFIG["retry_dealy_seconds"])
def fetch_html(url: str, http: urllib3.PoolManager, headers: dict) -> Optional[str]:
    """
    Fetches the HTML content of a given URL using the provided HTTP manager and headers.
    """
    resp = http.request("GET", url, headers=headers)
    if resp.status != 200:
        logger.error(f"HTTP {resp.status} error from {url}")
        return None
    
    logger.debug(f"Successfully fetched HTML from {url}")
    return resp.data.decode("utf-8", errors="ignore")

#main scraping functions

def scrape_page(url:str, http: urllib3.PoolManager, headers: dict) -> Optional[list[dict]]:
    """"
    Scrapes a single page of listings from the given URL and returns a list of dictionaries containing the extracted data.
    """
    html = fetch_html(url, http, headers)
    if not html:
        return None
    
    soup = BeautifulSoup(html, "lxml")
    ads = soup.findAll("div", class_="product-item")
    logger.debug(f"Found {len(ads)} ads on {url}")
    
    return [parse_single_ad(ad) for ad in ads]

def build_page_url(base_url: str, page: int) -> str:
    """"
    Constructs the URL for a specific page number based on the base URL.
    """
    if page == 1:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}page={page}"

def scrape_all_pages(base_url: str, cfg: dict) -> pd.DataFrame:
    """
    Scrapes all pages of listings from the given base URL and returns a pandas DataFrame containing the extracted data.
    """
    http    = urllib3.PoolManager()
    headers = cfg["headers"]
    delay   = cfg["delay_seconds"]
    max_pg  = cfg["max_pages"]

    all_records: list[dict] = []
    page = 1

    while True:
        if max_pg and page > max_pg:
            logger.info(f"Reached maximum page limit of {max_pg}. Stopping pagination.")
            break

        url = build_page_url(base_url, page)
        page_data = scrape_page(url, http, headers)

        if page_data is None:
            logger.error(f"Failed to scrape data from {url}. Stopping pagination.")
            break

        if len(page_data) == 0:
            logger.info(f"No more data found on page {page}. Stopping pagination.")
            break

        logger.info(f"Scraped {page:>3}: {len(page_data)} records from page {page}. | Total so far: {len(all_records) + len(page_data)}")
        all_records.extend(page_data)

        time.sleep(delay)
        page += 1

    df = pd.DataFrame(all_records)

    if not df.empty:
        before = len(df)
        df.dropna(subset=["Title", "Price (€)"], inplace=True)
        dropped = before - len(df)
        if dropped:
            logger.warning(f"Dropped {dropped} records due to missing Title or Price.")
    
    return df

#saving the data

def save_data(df: pd.DataFrame, output_file: str) -> None:
    """
    Saves the DataFrame to a CSV file.
    """
    if df.empty:
        logger.warning("No data to save. DataFrame is empty.")
        return
    
    df = df.copy()
    df["scraped_at"] = datetime.now().isoformat(timespec="seconds")
    
    if os.path.exists(output_file):
        existing = pd.read_csv(output_file, parse_dates=["Date Posted"])
        combined = pd.concat([existing, df], ignore_index=True)
        combined.drop_duplicates(subset=["Link"], keep="last", inplace=True)
        combined.to_csv(output_file, index=False)
        logger.info(f"Appended {len(df)} new records to {output_file}. Total records now: {len(combined)}")
    else:
        df.to_csv(output_file, index=False)
        logger.info(f"Saved {len(df)} records to new file {output_file}.")


#CLI Args parsing

def parse_cli_args():
    """
    Parses command-line arguments for the scraper.
    Without changing the code, you can run the script with optional arguments to specify the city, maximum pages to scrape, delay between requests, and output file name. For example:
    python rent_scraper.py --city novi-sad --max-pages 5 --delay 2 --output-file novi_sad_rentals.csv
    """
    parser = argparse.ArgumentParser(description="Scrape rental apartment listings from Halo Oglasi.")
    parser.add_argument("--city", type=str, default=CONFIG["city"], help="City to scrape (default: beograd)")
    parser.add_argument("--max-pages", type=int, default=CONFIG["max_pages"], help="Maximum number of pages to scrape (default: all)")
    parser.add_argument("--delay", type=float, default=CONFIG["delay_seconds"], help="Delay between page requests in seconds (default: 1.5)")
    parser.add_argument("--output-file", type=str, default=CONFIG["output_file"], help="Output CSV file name (default: rent_listings.csv)")
    return parser.parse_args()


if __name__ == "__main__":
    city = 'beograd'
    url = f'https://www.halooglasi.com/nekretnine/izdavanje-stanova/{city}'

    flates = extract_multiple_pages(url)

    if not flates.empty:
        print(f"Extracted {len(flates)} flat listings from {url}")
        print(flates.head())
    else:
        print("No flat listings found.")

