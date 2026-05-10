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
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
import time
import random
import logging
import argparse
from functools import wraps
from typing import Optional
from copy import deepcopy
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

#config
CONFIG = {
    "base_url": "https://www.halooglasi.com/nekretnine/izdavanje-stanova",
    "home_url": "https://www.halooglasi.com/",
    "city": "beograd",
    "delay_seconds": 2,
    "output_file": "rent_listings.csv",
    "max_pages": None,
    "headless": True,
    "delay_min": 2,
    "delay_max": 5,
    "viewport" : {"width": 1280, "height": 800},
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

#logging setup
def setup_logger(log_file: str = "scraper.log") -> logging.Logger:
    """
    Sets up a logger to log messages to both console and a file.
    """
    logger = logging.getLogger("halooglasi")
    logger.setLevel(logging.DEBUG)

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
 
    mapping = {"vlasnik": "Owner", "agencija": "Agency", "investitor": "Investor"}
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

#Playwright functions

def human_delay(min_seconds: int = 2, max_seconds: int = 5) -> None:
    """
    Introduces a random delay between requests to mimic human behavior.
    """
    delay = random.uniform(min_seconds, max_seconds)
    logger.debug(f"Sleeping for {delay:.2f} seconds to mimic human behavior.")
    time.sleep(delay)

def open_browser(playwright, headless: bool, user_agent: str, viewport: dict):
    """
    Opens a new browser instance with the specified settings.
    """
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-headless-mode",
        ]
    )

    context = browser.new_context(
        user_agent=user_agent,
        viewport={"width": 1280, "height": 800},
        locale="sr-RS",
        timezone_id="Europe/Belgrade",
    )

    page = context.new_page()
    Stealth().apply_stealth_sync(page)

    return browser, context, page

def warm_up_session(page: Page, home_url: str, delay_min: int, delay_max: int) -> bool:
    """
    Visits the home page to warm up the session and bypass potential Cloudflare checks.
    """
    logger.info(f"Warming up session by visiting {home_url}")
    try:
        page.goto(home_url, wait_until="domcontentloaded", timeout=30_000)
        human_delay(delay_min, delay_max)
        logger.info("Session warmed up successfully.")
        return True
    except PlaywrightTimeout:
        logger.warning(f"Timeout while warming up session at {home_url}. Continuing anyway.")
        return False

def load_page_with_retry(page: Page, url: str, max_attempts: int = 3, delay_min: float = 2, delay_max: float = 5) -> Optional[str]:
    """
    Attempts to load a page with retries and returns the page content if successful.
    """
    for attempt in range(1, max_attempts +1):
        try:
            logger.debug(f"Attempting to load {url} (Attempt {attempt}/{max_attempts})")
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            human_delay(1.5, 2.5)

            content = page.content()
        
            if "product-item" not in content:
                logger.warning(f"Page loaded but no ads found on {url}. Attempt {attempt}. Retrying...")
                human_delay(delay_min, delay_max)
                continue

            return content
        
        except PlaywrightTimeout:
            logger.warning(f"Timeout while loading {url} on attempt {attempt}. Retrying...")
            if attempt < max_attempts:
                human_delay(delay_min, delay_max)
    
    logger.error(f"Failed to load {url} after {max_attempts} attempts.")
    return None



#main scraping functions


def build_page_url(base_url: str, city: str, page: int) -> str:
    """"
    Constructs the URL for a specific page number based on the base URL.
    """
    if page == 1:
        return f"{base_url}/{city}"
    return f"{base_url}/{city}?page={page}"


def scrape_all_pages(cfg: dict) -> pd.DataFrame:
    """
    Scrapes all pages of listings from the given base URL and returns a pandas DataFrame containing the extracted data.
    """
    all_records: list = []

    with sync_playwright() as pw:
        browser, context, page = open_browser(
            pw,
            headless=cfg["headless"],
            user_agent=cfg["user_agent"],
            viewport=cfg["viewport"],
        )

        max_pages = cfg["max_pages"]

        warm_up_session(page, cfg["home_url"], cfg["delay_min"], cfg["delay_max"])

        current_page = 1
        while True:
            if max_pages and current_page > max_pages:
                logger.info(f"Reached max page limit of {max_pages}. Stopping.")
                break

            url = build_page_url(cfg["base_url"], cfg["city"], current_page)
            html = load_page_with_retry(page, url, max_attempts=3, delay_min=cfg["delay_min"], delay_max=cfg["delay_max"])

            if not html:
                logger.error(f"Failed to load page {current_page}. Stopping scraper.")
                break

            soup = BeautifulSoup(html, "lxml")
            ads = soup.findAll("div", class_="product-item")

            if not ads:
                logger.info(f"No ads found on page {current_page}. Assuming last page reached.")
                break

            page_records = [parse_single_ad(ad) for ad in ads]
            all_records.extend(page_records)

            logger.info(f"Scraped page {current_page} with {len(page_records)} records. Total records so far: {len(all_records)}")

            human_delay(cfg["delay_min"], cfg["delay_max"])

            current_page += 1

        context.close()
        browser.close()

    df = pd.DataFrame(all_records)
    if not df.empty:
        before = len(df)
        df.dropna(subset=["Title", "Link"], inplace=True)
        removed = before - len(df)
        if removed:
            logger.info(f"Removed {removed} records with missing Title or Link. Remaining records: {len(df)}")
    return df



#saving the data

def save_data(df: pd.DataFrame, output_file: str) -> None:
    """
    Saves the DataFrame to a CSV file.
    If the file already exists, appends new rows and removes duplicates by Link.
    Uses utf-8-sig encoding so Excel correctly displays special characters.
    """
    if df.empty:
        logger.warning("No data to save. DataFrame is empty.")
        return
    
    df = df.copy()
    df["Scraped at"] = datetime.now().isoformat(timespec="seconds")
    
    if os.path.exists(output_file):
        existing = pd.read_csv(output_file, parse_dates=["Date Posted"], encoding="utf-8-sig")
        combined = pd.concat([existing, df], ignore_index=True)
        combined.drop_duplicates(subset=["Link"], keep="last", inplace=True)
        combined.to_csv(output_file, index=False, encoding="utf-8-sig")
        logger.info(f"Appended {len(df)} new records to {output_file}. Total records now: {len(combined)}")
    else:
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
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
    parser.add_argument("--delay-min", type=float, default=CONFIG["delay_min"], help="Minimum delay between requests in seconds (default: 2)")
    parser.add_argument("--delay-max", type=float, default=CONFIG["delay_max"], help="Maximum delay between requests in seconds (default: 5)")
    parser.add_argument("--headless",  type=lambda x: x.lower() != "false", default=CONFIG["headless"], help="True/False (default: True)")
    parser.add_argument("--output-file", type=str, default=CONFIG["output_file"], help="Output CSV file name (default: rent_listings.csv)")
    return parser.parse_args()

def main() -> None:
    args = parse_cli_args()
    cfg = deepcopy(CONFIG)
    cfg["city"] = args.city
    cfg["max_pages"] = args.max_pages
    cfg["delay_min"] = args.delay_min
    cfg["delay_max"] = args.delay_max
    cfg["output_file"] = args.output_file
    cfg["headless"] = False

    logger.info(f"Starting scraper | City: {cfg['city']} | Max Pages: {cfg['max_pages'] or 'All'} | Delay: {cfg['delay_min']}-{cfg['delay_max']}s | Output: {cfg['output_file']}")

    df = scrape_all_pages(cfg)

    if df.empty:
        logger.warning("No data scraped. Exiting without saving.")
        return
    
    save_data(df, cfg["output_file"])

    logger.info(f"Scraping completed successfully. Number of records scraped: {len(df)}")
    logger.info(f"Columns: {list(df.columns)}")

    print("\nFirst 5 records:\n")
    print(df.head().to_string(index=False))

if __name__ == "__main__":
    main()

