import os

import pytest

from osw_scraper.config import Settings
from osw_scraper.parser import parse_item
from osw_scraper.scraper import OswScraper


def test_listing_url_first_page():
    assert OswScraper(Settings()).listing_url(0) == "https://www.osw.waw.pl/pl/publikacje"


def test_listing_url_with_page_and_region():
    assert OswScraper(Settings()).listing_url(3, "12") == (
        "https://www.osw.waw.pl/pl/publikacje?f%5B0%5D=obszary%3A12&page=3"
    )


@pytest.mark.skipif(not os.getenv("OSW_LIVE_TESTS"), reason="set OSW_LIVE_TESTS=1 to hit the real site")
def test_first_page_of_real_listing():
    with OswScraper(Settings(max_pages=1)) as scraper:
        items = scraper.fetch_listing(0)

    assert 5 <= len(items) <= 20
    publications = [parse_item(item) for item in items]
    assert all(pub.published.year >= 2001 for pub in publications)