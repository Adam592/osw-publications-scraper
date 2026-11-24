import logging
import re
import time
from collections.abc import Iterator
from urllib.parse import unquote, urlencode
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from osw_scraper.config import Settings
from osw_scraper.parser import RawItem
from osw_scraper.retry import TransientError, call_with_retry

logger = logging.getLogger(__name__)

PUBLICATION_HREF_PATTERN = r"/publikacje/[a-z0-9-]+/\d{4}-\d{2}-\d{2}/[^/?#]+"
META_LINE_PATTERN = r"\|\s*\d{4}-\d{2}-\d{2}"
REGION_FACET_PATTERN = re.compile(r"obszary:(?P<id>\d+)")
FACET_COUNT_PATTERN = re.compile(r"\(\s*\d+\s*\)")

EXTRACT_PUBLICATIONS_JS = """
([hrefPattern, metaPattern]) => {
  const hrefRe = new RegExp(hrefPattern);
  const metaRe = new RegExp(metaPattern);
  const clean = (href) => href.split("#")[0];
  const scope = document.querySelector("main") || document.body;
  const isPublication = (a) => hrefRe.test(a.href);
  const links = [...scope.querySelectorAll("a[href]")].filter(isPublication);

  const results = new Map();
  for (const a of links) {
    const url = clean(a.href);
    const title = (a.innerText || a.getAttribute("title") || "").trim();

    let context = null;
    let el = a.parentElement;
    for (let depth = 0; el && depth < 8; depth++, el = el.parentElement) {
      const urls = new Set(
        [...el.querySelectorAll("a[href]")].filter(isPublication).map((x) => clean(x.href))
      );
      if (urls.size > 1) break;
      if (metaRe.test(el.innerText || "")) { context = el.innerText; break; }
    }

    const previous = results.get(url);
    if (!previous) {
      results.set(url, { url, title, context });
    } else {
      if (title.length > previous.title.length) previous.title = title;
      if (!previous.context && context) previous.context = context;
    }
  }
  return [...results.values()];
}
"""

EXTRACT_REGION_FACETS_JS = """
() => [...document.querySelectorAll("a[href]")]
  .filter((a) => decodeURIComponent(a.href).includes("obszary:"))
  .map((a) => ({ href: a.href, text: (a.innerText || "").trim() }))
"""


class ScraperError(Exception):
    """Non-recoverable scraping problem, e.g. disallowed by robots.txt or HTTP 404."""


class OswScraper:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._robots: RobotFileParser | None = None


    def __enter__(self) -> "OswScraper":
        logger.info("Starting browser (headless=%s)", self.settings.headless)
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=self.settings.headless)
            self._context = self._browser.new_context(user_agent=self.settings.user_agent, locale="pl-PL")
            self._page = self._context.new_page()
            self._page.set_default_timeout(self.settings.timeout_ms)
        except Exception:
            self.close()
            raise
        return self


    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


    def close(self) -> None:
        for resource in (self._context, self._browser):
            if resource is not None:
                try:
                    resource.close()
                except PlaywrightError as exc:
                    logger.debug("Ignoring error while closing browser: %s", exc)
        if self._playwright is not None:
            self._playwright.stop()
        self._playwright = self._browser = self._context = self._page = None


    def is_allowed(self, url: str) -> bool:
        if not self.settings.respect_robots_txt:
            return True
        if self._robots is None:
            self._robots = RobotFileParser()
            response = self._context.request.get(f"{self.settings.base_url}/robots.txt")
            lines = response.text().splitlines() if response.ok else []
            self._robots.parse(lines)
        return self._robots.can_fetch(self.settings.user_agent, url)


    def _goto(self, url: str) -> None:
        def attempt() -> None:
            try:
                response = self._page.goto(url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError as exc:
                raise TransientError(f"timeout loading {url}") from exc
            except PlaywrightError as exc:
                if "net::ERR_" in str(exc):
                    raise TransientError(f"network error loading {url}") from exc
                raise
            if response is not None and (response.status == 429 or response.status >= 500):
                raise TransientError(f"HTTP {response.status} for {url}")
            if response is not None and response.status >= 400:
                raise ScraperError(f"HTTP {response.status} for {url}")

        call_with_retry(
            attempt,
            attempts=self.settings.retries,
            retry_on=(TransientError,),
            base_delay=max(self.settings.delay_seconds, 1.0),
            description=f"GET {url}",
        )


    def listing_url(self, page_no: int, region_id: str | None = None) -> str:
        params = {}
        if region_id is not None:
            params["f[0]"] = f"obszary:{region_id}"
        if page_no > 0:
            params["page"] = page_no
        query = f"?{urlencode(params)}" if params else ""
        return f"{self.settings.base_url}{self.settings.listing_path}{query}"


    def fetch_listing(self, page_no: int, region_id: str | None = None) -> list[RawItem]:
        url = self.listing_url(page_no, region_id)
        if not self.is_allowed(url):
            raise ScraperError(f"robots.txt disallows {url}")

        started = time.perf_counter()
        self._goto(url)
        records = self._page.evaluate(EXTRACT_PUBLICATIONS_JS, [PUBLICATION_HREF_PATTERN, META_LINE_PATTERN])
        items = [RawItem(url=r["url"], title=r["title"], context=r["context"]) for r in records]

        without_meta = sum(1 for item in items if item.context is None)
        logger.info(
            "Page %d: %d items (%d without metadata) in %.1fs",
            page_no, len(items), without_meta, time.perf_counter() - started,
        )
        return items

    def iter_listing(self, region_id: str | None = None) -> Iterator[tuple[int, list[RawItem]]]:
        first = self.settings.start_page
        for page_no in range(first, first + self.settings.max_pages):
            items = self.fetch_listing(page_no, region_id)
            if not items:
                logger.info("Page %d is empty, end of listing", page_no)
                return
            yield page_no, items
            time.sleep(self.settings.delay_seconds)


    def discover_regions(self) -> dict[str, str]:
        """Return {region_id: region_name} read from the sidebar filters."""
        self._goto(self.listing_url(0))
        regions: dict[str, str] = {}
        for link in self._page.evaluate(EXTRACT_REGION_FACETS_JS):
            match = REGION_FACET_PATTERN.search(unquote(link["href"]))
            name = FACET_COUNT_PATTERN.sub("", link["text"]).strip()
            if match and name:
                regions.setdefault(match.group("id"), name)
        logger.info("Discovered %d regions: %s", len(regions), ", ".join(regions.values()))
        return regions