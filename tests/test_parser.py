from datetime import date

import pytest

from osw_scraper.parser import (
    ParseError,
    RawItem,
    normalize_whitespace,
    parse_item,
    parse_meta_line,
    split_authors,
)

URL = "https://www.osw.waw.pl/pl/publikacje/analizy/2025-11-05/test"


def make(context, title="Tytuł testowy", url=URL):
    return RawItem(url=url, title=title, context=context)


def test_normalize_whitespace():
    assert normalize_whitespace("  Komentarze\xa0OSW   |  x ") == "Komentarze OSW | x"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Jan Kowalski", ["Jan Kowalski"]),
        ("Jan Kowalski, Anna Nowak", ["Jan Kowalski", "Anna Nowak"]),
        ("Jan Kowalski i Anna Nowak", ["Jan Kowalski", "Anna Nowak"]),
        ("Jan Kowalski; Anna Nowak, Jan Kowalski", ["Jan Kowalski", "Anna Nowak"]),
        ("Kamil Kłysiński", ["Kamil Kłysiński"]),
        ("", []),
    ],
)
def test_split_authors(text, expected):
    assert split_authors(text) == expected


def test_meta_line_with_authors():
    meta = parse_meta_line("Raport OSW | 2025-09-11 | Tadeusz Iwański, Sławomir Matuszak")
    assert meta.pub_type == "Raport OSW"
    assert meta.published == "2025-09-11"
    assert meta.authors == ["Tadeusz Iwański", "Sławomir Matuszak"]


def test_meta_line_without_authors_inside_longer_text():
    meta = parse_meta_line("Okładka\nAnalizy | 2025-10-15\nKrym zagrożony")
    assert meta.pub_type == "Analizy"
    assert meta.authors == []


def test_meta_line_missing():
    assert parse_meta_line("Zwykły tekst bez daty") is None


def test_parse_item_full():
    pub = parse_item(make("Analizy | 2025-11-05 | Jan Kowalski"), regions=["Rosja"])
    assert pub.pub_type == "Analizy"
    assert pub.published == date(2025, 11, 5)
    assert pub.authors == ["Jan Kowalski"]
    assert pub.regions == ["Rosja"]


def test_parse_item_falls_back_to_url():
    url = "https://www.osw.waw.pl/pl/publikacje/komentarze-osw/2025-10-10/bez-metadanych"
    pub = parse_item(make(None, url=url))
    assert pub.pub_type == "Komentarze OSW"
    assert pub.published == date(2025, 10, 10)
    assert pub.authors == []


def test_parse_item_date_mismatch_keeps_text_date_and_warns(caplog):
    pub = parse_item(make("Analizy | 2025-11-06 | Jan Kowalski"))
    assert pub.published == date(2025, 11, 6)

    assert any(record.levelname == "WARNING" for record in caplog.records)
    assert "2025-11-06" in caplog.text
    assert "2025-11-05" in caplog.text


def test_parse_item_title_is_single_line():
    assert parse_item(make(None, title="  Nowa\n   Ostpolitik? ")).title == "Nowa Ostpolitik?"


@pytest.mark.parametrize(
    "raw",
    [
        make("Analizy | 2025-11-05", title="   "),
        make("Analizy | 2025-11-05", url="https://www.osw.waw.pl/pl/o-nas"),
        make("Analizy | 1985-01-01", url="https://www.osw.waw.pl/pl/publikacje/analizy/1985-01-01/x"),
        make("Analizy | 2025-13-40"),
    ],
    ids=["empty-title", "not-publication-url", "too-old", "impossible-date"],
)
def test_parse_item_rejects_invalid(raw):
    with pytest.raises(ParseError):
        parse_item(raw)

def test_type_comes_from_url_not_from_styled_text():
    pub = parse_item(make("ANALIZY | 2025-11-05 | Jan Kowalski"))
    assert pub.pub_type == "Analizy"