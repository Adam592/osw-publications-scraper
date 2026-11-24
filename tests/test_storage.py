import csv
from datetime import date

import pytest

from osw_scraper.models import Publication
from osw_scraper.storage import Repository, RunRecord

URL = "https://www.osw.waw.pl/pl/publikacje/analizy/2025-11-05/a"


def pub(**overrides) -> Publication:
    data = dict(
        url=URL,
        title="Tytuł analizy",
        pub_type="Analizy",
        published=date(2025, 11, 5),
        authors=["Jan Kowalski", "Anna Nowak"],
        regions=["Rosja"],
    )
    data.update(overrides)
    return Publication(**data)


@pytest.fixture
def repo(tmp_path):
    with Repository(tmp_path / "test.db") as r:
        yield r


def test_upsert_reports_new_and_existing(repo):
    assert repo.upsert(pub()) is True
    assert repo.upsert(pub(title="Poprawiony tytuł")) is False
    assert repo.count() == 1
    assert repo.get(URL).title == "Poprawiony tytuł"


def test_regions_accumulate(repo):
    repo.upsert(pub(regions=["Rosja"]))
    repo.upsert(pub(regions=["Ukraina"]))
    assert repo.get(URL).regions == ["Rosja", "Ukraina"]


def test_author_order_is_preserved(repo):
    repo.upsert(pub(authors=["Zofia Z", "Adam A"]))
    assert repo.get(URL).authors == ["Zofia Z", "Adam A"]


def test_export_csv(repo, tmp_path):
    repo.upsert(pub())
    repo.upsert(pub(url=URL + "-2", published=date(2024, 1, 2), authors=[], regions=[]))
    out = tmp_path / "out.csv"

    assert repo.export_csv(out) == 2
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows[0]["authors"] == "Jan Kowalski; Anna Nowak"
    assert rows[1]["authors"] == ""


def test_record_run(repo):
    run_id = repo.record_run(RunRecord("2025-01-01T00:00", "2025-01-01T00:01", "success", 2, 10, 9, 9, 1))
    assert run_id == 1
    assert repo.last_runs()[0][2] == "success"


def test_rollback_on_exception(tmp_path):
    path = tmp_path / "test.db"
    with pytest.raises(RuntimeError):
        with Repository(path) as r:
            r.upsert(pub())
            raise RuntimeError("crash before commit")
    with Repository(path) as r:
        assert r.count() == 0