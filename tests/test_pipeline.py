from osw_scraper.config import Settings
from osw_scraper.parser import RawItem
from osw_scraper.pipeline import Pipeline
from osw_scraper.storage import Repository

BASE = "https://www.osw.waw.pl/pl/publikacje/analizy"


def item(slug, title="Tytuł publikacji"):
    return RawItem(url=f"{BASE}/2025-11-05/{slug}", title=title,
                   context="Analizy | 2025-11-05 | Jan Kowalski")


PAGES = [
    [item("a"), item("b"), item("pusty", title="")], 
    [item("b"), item("c")],                           
]


class FakeScraper:
    """Pretends to be OswScraper: returns fixed pages, no browser, no network."""

    def __init__(self, settings, fail=False):
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def discover_regions(self):
        return {"12": "Rosja"}

    def iter_listing(self, region_id=None):
        for page_no, items in enumerate(PAGES):
            if self.fail and page_no == 1:
                raise RuntimeError("site down")
            yield page_no, items


def settings_for(tmp_path, **overrides):
    return Settings(db_path=tmp_path / "test.db", log_dir=None, **overrides)


def test_full_run(tmp_path):
    report = Pipeline(settings_for(tmp_path, max_invalid_ratio=0.5), FakeScraper).run()

    assert report.status == "success"
    assert report.pages_scraped == 2
    assert report.items_found == 5
    assert report.items_invalid == 1
    assert report.items_saved == 4
    assert report.items_new == 3
    with Repository(tmp_path / "test.db") as repo:
        assert repo.count() == 3
        assert repo.last_runs()[0][2] == "success"


def test_too_many_invalid_items_marks_run_partial(tmp_path):
    report = Pipeline(settings_for(tmp_path), FakeScraper).run()  
    assert report.status == "partial"


def test_incremental_run_stops_when_nothing_is_new(tmp_path):
    settings = settings_for(tmp_path, max_invalid_ratio=0.5)
    Pipeline(settings, FakeScraper).run()
    second = Pipeline(settings.with_overrides(stop_after_known_pages=1), FakeScraper).run()

    assert second.pages_scraped == 1
    assert second.items_new == 0


def test_by_region_tags_publications(tmp_path):
    Pipeline(settings_for(tmp_path, by_region=True, max_invalid_ratio=0.5), FakeScraper).run()
    with Repository(tmp_path / "test.db") as repo:
        assert repo.get(f"{BASE}/2025-11-05/a").regions == ["Rosja"]


def test_crash_is_recorded_and_earlier_pages_are_kept(tmp_path):
    report = Pipeline(settings_for(tmp_path), lambda s: FakeScraper(s, fail=True)).run()

    assert report.status == "failed"
    assert "site down" in report.error
    with Repository(tmp_path / "test.db") as repo:
        assert repo.count() == 2  
        assert repo.last_runs()[0][2] == "failed"