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

def fetch_data(url, http, headers):
    #http = urllib3.PoolManager()
    #headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept-Language': 'en-US,en;q=0.5'}
    try:
        resp = http.request('GET', url, headers=headers)
        if resp.status != 200:
            print(f'HTTP {resp.status} error from {url}')
            return None
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None
    
    html = resp.data.decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'lxml')

    ads = soup.findAll('div', attrs={'class' : 'product-item'})
    data = []

    for ad in ads:
        ad_data = {
            'Title': None,
            'Price (€)': None,
            'Square Meters': None,
            'Number of Rooms': None,
            'City': None,
            'Municipality': None,
            'Neighborhood': None,
            'Street': None,
            'Floor': None,
            'Number of Floors': None,
            'Advertiser Type': None,
            'Date Posted': None,
            'Link': None
        }
    
        title = ad.find('h3', class_ = 'product-title')
        if title:
            ad_data['Title'] = title.text.strip()
            a_tag = title.find('a')
            if a_tag and 'href' in a_tag.attrs:
                ad_data['Link'] = 'https://www.halooglasi.com' + a_tag['href']
        
        price = ad.find('div', class_ = 'central-feature')
        if price:
            clean_price = price.text.replace("\xa0€", "").replace('.', '').strip()
            if clean_price.isdigit():
                ad_data['Price (€)'] = int(clean_price)
        
        attributes = ad.findAll('div', class_ = 'value-wrapper')
        for attribute in attributes:
            text = attribute.text.strip()

            if 'Kvadratura' in text:
                match = re.search(r'\d+', text)
                if match:
                    ad_data['Square Meters'] = int(match.group())
            elif 'Broj soba' in text:
                match = re.search(r'\d+(\.\d+)?', text)
                if match:
                    ad_data['Number of Rooms'] = float(match.group())
            elif 'Spratnost' in text:
                clean_floor = text.replace('Spratnost', '').strip()
                if '/' in clean_floor:
                    floor_parts = clean_floor.split('/')
                    ad_data['Floor'] = floor_parts[0].strip()
                    ad_data['Number of Floors'] = floor_parts[1].strip()
                else:
                    ad_data['Floor'] = clean_floor
                    ad_data['Number of Floors'] = None

        location = ad.find('ul', class_ = 'subtitle-places')
        if location:
            places = location.find_all('li')
            places_text = [place.text.strip() for place in places]

            if len(places_text) > 0:
                ad_data['City'] = places_text[0]
            if len(places_text) > 1:
                ad_data['Municipality'] = places_text[1]
            if len(places_text) > 2:
                ad_data['Neighborhood'] = places_text[2]
            if len(places_text) > 3:
                ad_data['Street'] = places_text[3]

        advertiser = ad.find('span', attrs={'data-field-name': 'oglasivac_nekretnine_s'})
        if advertiser:
            advertiser_text = advertiser.get('data-field-value', '').strip().lower()

            if advertiser_text == 'vlasnik':
                ad_data['Advertiser Type'] = 'Owner'
            elif advertiser_text == 'agencija':
                ad_data['Advertiser Type'] = 'Agency'
            else:
                ad_data['Advertiser Type'] = advertiser.text.strip()
        else:
            ad_data['Advertiser Type'] = None

        
        date = ad.find('span', class_ = 'publish-date')
        if date:
            try:
                ad_data['Date Posted'] = datetime.strptime(date.text.strip(), '%d.%m.%Y.')
            except ValueError:
                pass
        
        data.append(ad_data)
    
    return data

def extract_multiple_pages(url):
    http = urllib3.PoolManager()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept-Language': 'en-US,en;q=0.5'}

    data = []
    page = 1

    while True:
        if page == 1:
            page_url = url
        else:
            separator = '&' if '?' in url else '?'
            page_url = f"{url}{separator}page={page}"

        page_data = fetch_data(page_url, http, headers)
        if page_data is None:
            print(f"Failed to fetch data from {page_url}. Stopping pagination.")
            break

        if len(page_data) == 0:
            print(f"No more data found on page {page}. Stopping pagination.")
            break

        data.extend(page_data)

        time.sleep(1) 
        page += 1

    df = pd.DataFrame(data)
    df.dropna(subset=['Title', 'Price (€)'], inplace=True)  # Ensure we have at least title and price for each entry

    if not df.empty:
        df.to_csv('rent_listings.csv', index=False)
        print(f"Data saved to rent_listings.csv with {len(df)} entries.")
    else:
        print("No data found to save.")
    
    return df

if __name__ == "__main__":
    city = 'beograd'
    url = f'https://www.halooglasi.com/nekretnine/izdavanje-stanova/{city}'

    flates = extract_multiple_pages(url)

    if not flates.empty:
        print(f"Extracted {len(flates)} flat listings from {url}")
        print(flates.head())
    else:
        print("No flat listings found.")

