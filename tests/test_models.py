from datetime import date

import pytest
from pydantic import ValidationError

from osw_scraper.models import Publication

URL = "https://www.osw.waw.pl/pl/publikacje/analizy/2025-11-05/test"

def make(**overrides):
    data = dict(url=URL, title="Tytuł testowy", pub_type="Analizy", published="2025-11-05")
    data.update(overrides)
    return Publication(**data)

def test_valid_publication():
    pub = make(title="  Tytuł testowy  ")
    assert pub.title == "Tytuł testowy"
    assert pub.published == date(2025, 11, 5)


def test_authors_are_cleaned_and_deduplicated():
    pub = make(authors=["Jan Kowalski", "", "  ", "Jan Kowalski", "Anna Nowak"])
    assert pub.authors == ["Jan Kowalski", "Anna Nowak"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"url": "https://www.osw.waw.pl/pl/o-nas"},
        {"url": "ftp://www.osw.waw.pl/pl/publikacje/x"},
        {"published": "2000-12-31"},
        {"published": "2999-01-01"},
        {"title": "ab"},
    ],
    ids=["not-publication-url", "not-http", "before-2001", "future-date", "title-too-short"],
)
def test_invalid_data_is_rejected(overrides):
    with pytest.raises(ValidationError):
        make(**overrides)