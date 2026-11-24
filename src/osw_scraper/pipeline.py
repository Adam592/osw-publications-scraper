import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from osw_scraper.config import Settings
from osw_scraper.parser import ParseError, parse_item
from osw_scraper.scraper import OswScraper
from osw_scraper.storage import Repository, RunRecord

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RunReport:
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    status: str = "running"
    pages_scraped: int = 0
    items_found: int = 0
    items_saved: int = 0
    items_new: int = 0
    items_invalid: int = 0
    error: str | None = None

    @property
    def invalid_ratio(self) -> float:
        return self.items_invalid / self.items_found if self.items_found else 0.0

    def to_record(self) -> RunRecord:
        return RunRecord(
            started_at=self.started_at, finished_at=self.finished_at, status=self.status,
            pages_scraped=self.pages_scraped, items_found=self.items_found,
            items_saved=self.items_saved, items_new=self.items_new,
            items_invalid=self.items_invalid, error=self.error,
        )


class Pipeline:
    def __init__(self, settings: Settings, scraper_factory: Callable[[Settings], OswScraper] = OswScraper) -> None:
        self.settings = settings
        self._scraper_factory = scraper_factory

    def run(self) -> RunReport:
        report = RunReport()
        logger.info("Run started: %s", self.settings)

        with Repository(self.settings.db_path) as repo:
            try:
                with self._scraper_factory(self.settings) as scraper:
                    self._scrape(scraper, repo, report)
            except Exception as exc:
                report.status = "failed"
                report.error = f"{type(exc).__name__}: {exc}"
                logger.exception("Run failed")
            else:
                if report.invalid_ratio > self.settings.max_invalid_ratio:
                    report.status = "partial"
                    logger.warning(
                        "%.0f%% of items failed validation - the page layout may have changed",
                        report.invalid_ratio * 100,
                    )
                else:
                    report.status = "success"
            finally:
                report.finished_at = _now()
                repo.record_run(report.to_record())

        logger.info(
            "Run finished: status=%s pages=%d found=%d saved=%d new=%d invalid=%d",
            report.status, report.pages_scraped, report.items_found,
            report.items_saved, report.items_new, report.items_invalid,
        )
        return report

    def _scrape(self, scraper, repo: Repository, report: RunReport) -> None:
        if self.settings.by_region:
            targets = list(scraper.discover_regions().items())
            if not targets:
                raise RuntimeError("no regions found in the filter sidebar")
        else:
            targets = [(None, None)]

        for region_id, region_name in targets:
            self._scrape_listing(scraper, repo, report, region_id, region_name)

    def _scrape_listing(self, scraper, repo, report, region_id, region_name) -> None:
        regions = [region_name] if region_name else []
        known_pages_in_a_row = 0

        for page_no, raw_items in scraper.iter_listing(region_id):
            report.pages_scraped += 1
            report.items_found += len(raw_items)
            new_on_page = 0

            for raw in raw_items:
                try:
                    publication = parse_item(raw, regions=regions)
                except ParseError as exc:
                    report.items_invalid += 1
                    logger.warning("Skipping invalid item on page %d: %s", page_no, exc)
                    continue
                if repo.upsert(publication):
                    new_on_page += 1
                report.items_saved += 1

            repo.commit()
            report.items_new += new_on_page

            limit = self.settings.stop_after_known_pages
            known_pages_in_a_row = known_pages_in_a_row + 1 if new_on_page == 0 else 0
            if limit and known_pages_in_a_row >= limit:
                logger.info("No new publications on the last %d page(s), stopping early", limit)
                return