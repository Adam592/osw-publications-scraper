import logging
import re
from dataclasses import dataclass
from datetime import date

from pydantic import ValidationError 

from osw_scraper.models import Publication

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(
    r"/publikacje/(?P<type_slug>[a-z0-9-]+)/(?P<date>\d{4}-\d{2}-\d{2})/(?P<slug>[^/?#]+)"
)
META_PATTERN = re.compile(
    r"^\s*(?P<type>[^|\n]{2,60}?)\s*\|\s*(?P<date>\d{4}-\d{2}-\d{2})\s*(?:\|\s*(?P<rest>.*))?$",
    re.MULTILINE,
)
AUTHOR_SEPARATORS = re.compile(r"\s*(?:,|;|\s+i\s+)\s*")

TYPE_LABELS = {
    "analizy": "Analizy",
    "komentarze-osw": "Komentarze OSW",
    "raport-osw": "Raport OSW",
    "punkt-widzenia": "Punkt widzenia",
}

class ParseError(ValueError):
    """Raised when a raw item cannot be turned into a publication"""

@dataclass(frozen=True)
class RawItem:
    url: str
    title: str
    context: str | None 

@dataclass(frozen=True)
class MetaLine:
    pub_type: str
    published: str
    authors: list[str]

def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in a string"""
    text = text.replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", text).strip()

def split_authors(text: str) -> list[str]:
    """Split a string of authors into a list"""
    authors = AUTHOR_SEPARATORS.split(normalize_whitespace(text))
    cleaned = [a.strip(" .") for a in authors]
    non_empty = [a for a in cleaned if a]
    return list(dict.fromkeys(non_empty))

def parse_meta_line(context: str) -> MetaLine | None:
    """Parse a meta line from the context"""
    match = META_PATTERN.search(normalize_whitespace(context))

    if not match:
        return None

    rest = match.group("rest") or ""
    authors = rest.split("|", 1)[0]

    return MetaLine(
        pub_type=match.group("type").strip(),
        published=match.group("date"),
        authors=split_authors(authors),
    )

def parse_item(raw: RawItem, regions: list[str] | None = None) -> Publication:
    """Parse a raw item into a publication"""
    url_match = URL_PATTERN.search(raw.url)
    if not url_match:
        raise ParseError(f"URL does not match expected pattern: {raw.url}")

    title = " ".join(normalize_whitespace(raw.title).split())
    if not title:
        raise ParseError("Title is empty after normalization")

    slug = url_match.group("type_slug")
    pub_type = TYPE_LABELS.get(slug, slug.replace("-", " ").capitalize())
    url_date = url_match.group("date")

    meta = parse_meta_line(raw.context) if raw.context else None

    if not meta:
        published = url_date
        authors = []
        logger.debug("Meta line not found for %s, using date from URL", raw.url)
    else:
        published = meta.published
        authors = meta.authors

        if published != url_date:
            logger.warning(
                "Published date from meta line (%s) does not match URL date (%s) for %s",
                published,
                url_date,
                raw.url,
            )

    try:
        return Publication(
            url=raw.url,
            title=title,
            pub_type=pub_type,
            published=date.fromisoformat(published),
            authors=authors,
            regions=regions or [],
        )
    except (ValidationError, ValueError) as e:
        raise ParseError(f"Failed to create Publication: {e}") from e