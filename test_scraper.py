"""
Tests for parsers in rent_scraper.py

Usage:
    pip install pytest
    pytest test_scraper.py -v
"""

import pytest
from bs4 import BeautifulSoup
from datetime import datetime

from rent_scraper import (
    parse_title_and_link,
    parse_price,
    parse_floor,
    parse_attributes,
    parse_location,
    parse_advertiser,
    parse_date,
    parse_single_ad,
    build_page_url,
)


# HELPER — creates a BeautifulSoup element from an HTML string

def make_ad(html: str):
    """Creates a BeautifulSoup element from an HTML string."""
    return BeautifulSoup(html, "lxml").find("div")

# parsers

class TestParseTitleAndLink:

    def test_normal_listing(self):
        ad = make_ad("""
            <div>
                <h3 class="product-title">
                    <a href="/nekretnine/stan-1">Nice apartment in the center</a>
                </h3>
            </div>
        """)
        result = parse_title_and_link(ad)
        assert result["Title"] == "Nice apartment in the center"
        assert result["Link"] == "https://www.halooglasi.com/nekretnine/stan-1"

    def test_no_title_tag(self):
        ad = make_ad("<div><p>No title here</p></div>")
        result = parse_title_and_link(ad)
        assert result["Title"] is None
        assert result["Link"] is None

    def test_title_without_link(self):
        ad = make_ad("""
            <div>
                <h3 class="product-title">Apartment without link</h3>
            </div>
        """)
        result = parse_title_and_link(ad)
        assert result["Title"] == "Apartment without link"
        assert result["Link"] is None

    def test_title_with_extra_whitespace(self):
        ad = make_ad("""
            <div>
                <h3 class="product-title">
                    <a href="/stan">   Apartment with spaces   </a>
                </h3>
            </div>
        """)
        result = parse_title_and_link(ad)
        assert result["Title"] == "Apartment with spaces"

class TestParsePrice:

    def test_normal_price(self):
        ad = make_ad('<div><div class="central-feature">500 €</div></div>')
        assert parse_price(ad) == 500

    def test_price_with_dots(self):
        ad = make_ad('<div><div class="central-feature">1.200 €</div></div>')
        assert parse_price(ad) == 1200

    def test_price_with_nbsp(self):
        ad = make_ad('<div><div class="central-feature">800\xa0€</div></div>')
        assert parse_price(ad) == 800

    def test_price_on_request(self):
        ad = make_ad('<div><div class="central-feature">By agreement</div></div>')
        assert parse_price(ad) is None

    def test_no_price(self):
        ad = make_ad('<div><p>No price</p></div>')
        assert parse_price(ad) is None

    def test_large_price(self):
        ad = make_ad('<div><div class="central-feature">2.500 €</div></div>')
        assert parse_price(ad) == 2500

class TestParseFloor:

    def test_floor_and_total(self):
        floor, total = parse_floor("Spratnost 3/5")
        assert floor == "3"
        assert total == "5"

    def test_floor_only(self):
        floor, total = parse_floor("Spratnost 2")
        assert floor == "2"
        assert total is None

    def test_ground_floor(self):
        floor, total = parse_floor("Spratnost PR/4")
        assert floor == "PR"
        assert total == "4"

    def test_high_ground_floor(self):
        floor, total = parse_floor("Spratnost VP/3")
        assert floor == "VP"
        assert total == "3"

    def test_basement(self):
        floor, total = parse_floor("Spratnost SUT/5")
        assert floor == "SUT"
        assert total == "5"

class TestParseAttributes:

    def test_all_values(self):
        ad = make_ad("""
            <div>
                <div class="value-wrapper">Kvadratura 65 m²</div>
                <div class="value-wrapper">Broj soba 2.5</div>
                <div class="value-wrapper">Spratnost 3/5</div>
            </div>
        """)
        result = parse_attributes(ad)
        assert result["Square Meters"] == 65
        assert result["Number of Rooms"] == 2.5
        assert result["Floor"] == "3"
        assert result["Number of Floors"] == "5"

    def test_no_attributes(self):
        ad = make_ad("<div><p>No attributes</p></div>")
        result = parse_attributes(ad)
        assert result["Square Meters"] is None
        assert result["Number of Rooms"] is None
        assert result["Floor"] is None
        assert result["Number of Floors"] is None

    def test_whole_number_of_rooms(self):
        ad = make_ad("""
            <div>
                <div class="value-wrapper">Broj soba 3</div>
            </div>
        """)
        result = parse_attributes(ad)
        assert result["Number of Rooms"] == 3.0

    def test_square_meters_without_rooms(self):
        ad = make_ad("""
            <div>
                <div class="value-wrapper">Kvadratura 45 m²</div>
            </div>
        """)
        result = parse_attributes(ad)
        assert result["Square Meters"] == 45
        assert result["Number of Rooms"] is None

class TestParseLocation:

    def test_all_four_values(self):
        ad = make_ad("""
            <div>
                <ul class="subtitle-places">
                    <li>Beograd</li>
                    <li>Savski venac</li>
                    <li>Savamala</li>
                    <li>Karađorđeva</li>
                </ul>
            </div>
        """)
        result = parse_location(ad)
        assert result["City"] == "Beograd"
        assert result["Municipality"] == "Savski venac"
        assert result["Neighborhood"] == "Savamala"
        assert result["Street"] == "Karađorđeva"

    def test_city_and_municipality_only(self):
        ad = make_ad("""
            <div>
                <ul class="subtitle-places">
                    <li>Beograd</li>
                    <li>Novi Beograd</li>
                </ul>
            </div>
        """)
        result = parse_location(ad)
        assert result["City"] == "Beograd"
        assert result["Municipality"] == "Novi Beograd"
        assert result["Neighborhood"] is None
        assert result["Street"] is None

    def test_city_only(self):
        ad = make_ad("""
            <div>
                <ul class="subtitle-places">
                    <li>Novi Sad</li>
                </ul>
            </div>
        """)
        result = parse_location(ad)
        assert result["City"] == "Novi Sad"
        assert result["Municipality"] is None

    def test_no_location(self):
        ad = make_ad("<div><p>No location</p></div>")
        result = parse_location(ad)
        assert all(v is None for v in result.values())

class TestParseAdvertiser:

    def test_owner(self):
        ad = make_ad("""
            <div>
                <span data-field-name="oglasivac_nekretnine_s" 
                      data-field-value="Vlasnik">Vlasnik</span>
            </div>
        """)
        assert parse_advertiser(ad) == "Owner"

    def test_agency(self):
        ad = make_ad("""
            <div>
                <span data-field-name="oglasivac_nekretnine_s"
                      data-field-value="Agencija">Agencija</span>
            </div>
        """)
        assert parse_advertiser(ad) == "Agency"

    def test_investor(self):
        ad = make_ad("""
            <div>
                <span data-field-name="oglasivac_nekretnine_s"
                      data-field-value="Investitor">Investitor</span>
            </div>
        """)
        assert parse_advertiser(ad) == "Investor"

    def test_unknown_type(self):
        ad = make_ad("""
            <div>
                <span data-field-name="oglasivac_nekretnine_s"
                      data-field-value="Other">Other</span>
            </div>
        """)
        assert parse_advertiser(ad) == "Other"

    def test_no_advertiser(self):
        ad = make_ad("<div><p>No advertiser</p></div>")
        assert parse_advertiser(ad) is None

class TestParseDate:

    def test_valid_date(self):
        ad = make_ad('<div><span class="publish-date">15.03.2024.</span></div>')
        result = parse_date(ad)
        assert result == datetime(2024, 3, 15)

    def test_invalid_date(self):
        ad = make_ad('<div><span class="publish-date">not a date</span></div>')
        assert parse_date(ad) is None

    def test_no_date(self):
        ad = make_ad("<div><p>No date</p></div>")
        assert parse_date(ad) is None

    def test_all_months(self):
        for month in range(1, 13):
            ad = make_ad(f'<div><span class="publish-date">01.{month:02d}.2024.</span></div>')
            result = parse_date(ad)
            assert result.month == month

class TestParseSingleAd:

    def test_complete_listing(self):
        ad = make_ad("""
            <div class="product-item">
                <h3 class="product-title">
                    <a href="/nekretnine/stan-123">Two-bedroom apartment Savski venac</a>
                </h3>
                <div class="central-feature">800 €</div>
                <div class="value-wrapper">Kvadratura 55 m²</div>
                <div class="value-wrapper">Broj soba 2</div>
                <div class="value-wrapper">Spratnost 4/8</div>
                <ul class="subtitle-places">
                    <li>Beograd</li>
                    <li>Savski venac</li>
                    <li>Savamala</li>
                </ul>
                <span data-field-name="oglasivac_nekretnine_s" 
                      data-field-value="Agencija">Agencija</span>
                <span class="publish-date">10.05.2024.</span>
            </div>
        """)
        result = parse_single_ad(ad)

        assert result["Title"] == "Two-bedroom apartment Savski venac"
        assert result["Link"] == "https://www.halooglasi.com/nekretnine/stan-123"
        assert result["Price (€)"] == 800
        assert result["Square Meters"] == 55
        assert result["Number of Rooms"] == 2.0
        assert result["Floor"] == "4"
        assert result["Number of Floors"] == "8"
        assert result["City"] == "Beograd"
        assert result["Municipality"] == "Savski venac"
        assert result["Neighborhood"] == "Savamala"
        assert result["Street"] is None
        assert result["Advertiser Type"] == "Agency"
        assert result["Date Posted"] == datetime(2024, 5, 10)

    def test_empty_listing(self):
        ad = make_ad("<div class='product-item'></div>")
        result = parse_single_ad(ad)
        assert result["Title"] is None
        assert result["Price (€)"] is None

class TestBuildPageUrl:

    BASE = "https://www.halooglasi.com/nekretnine/izdavanje-stanova"

    def test_first_page(self):
        url = build_page_url(self.BASE, "beograd", 1)
        assert url == f"{self.BASE}/beograd"

    def test_second_page(self):
        url = build_page_url(self.BASE, "beograd", 2)
        assert url == f"{self.BASE}/beograd?page=2"

    def test_tenth_page(self):
        url = build_page_url(self.BASE, "novisad", 10)
        assert url == f"{self.BASE}/novisad?page=10"

    def test_different_cities(self):
        for city in ["beograd", "novisad", "nis", "kragujevac"]:
            url = build_page_url(self.BASE, city, 1)
            assert city in url
