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
    with OswScraper(Settings(max_pages=2, delay_seconds=1)) as scraper:
        pages = list(scraper.iter_listing())

    assert [page_no for page_no, _ in pages] == [0, 1]
    assert all(5 <= len(items) <= 20 for _, items in pages)

    urls = [item.url for _, items in pages for item in items]
    assert len(urls) == len(set(urls))

    publications = [parse_item(item) for _, items in pages for item in items]
    assert all(pub.published.year >= 2001 for pub in publications)