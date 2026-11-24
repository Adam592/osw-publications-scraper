import csv
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from osw_scraper.models import Publication

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS publications (
    url         TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    pub_type    TEXT NOT NULL,
    published   TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS publication_authors (
    url       TEXT NOT NULL REFERENCES publications(url) ON DELETE CASCADE,
    author    TEXT NOT NULL,
    position  INTEGER NOT NULL,
    PRIMARY KEY (url, author)
);
CREATE TABLE IF NOT EXISTS publication_regions (
    url     TEXT NOT NULL REFERENCES publications(url) ON DELETE CASCADE,
    region  TEXT NOT NULL,
    PRIMARY KEY (url, region)
);
CREATE TABLE IF NOT EXISTS scrape_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    status         TEXT NOT NULL,
    pages_scraped  INTEGER NOT NULL DEFAULT 0,
    items_found    INTEGER NOT NULL DEFAULT 0,
    items_saved    INTEGER NOT NULL DEFAULT 0,
    items_new      INTEGER NOT NULL DEFAULT 0,
    items_invalid  INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_publications_published ON publications(published);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RunRecord:
    started_at: str
    finished_at: str | None
    status: str
    pages_scraped: int
    items_found: int
    items_saved: int
    items_new: int
    items_invalid: int
    error: str | None = None


class Repository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> "Repository":
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._conn is not None:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Repository must be used as a context manager")
        return self._conn

    def commit(self) -> None:
        self.conn.commit()

    def upsert(self, pub: Publication) -> bool:
        """Insert or update a publication. Returns True if it was new."""
        now = _now()

        row = self.conn.execute("SELECT 1 FROM publications WHERE url = ?", (pub.url,)).fetchone()
        is_new = row is None

        self.conn.execute(
            """
            INSERT INTO publications (url, title, pub_type, published, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                pub_type = excluded.pub_type,
                published = excluded.published,
                last_seen = excluded.last_seen
            """,
            (pub.url, pub.title, pub.pub_type, pub.published.isoformat(), now, now),
        )

        if pub.authors:
            self.conn.execute("DELETE FROM publication_authors WHERE url = ?", (pub.url,))
            self.conn.executemany(
                "INSERT INTO publication_authors (url, author, position) VALUES (?, ?, ?)",
                [(pub.url, author, i) for i, author in enumerate(pub.authors)]
            )

        self.conn.executemany(
            "INSERT OR IGNORE INTO publication_regions (url, region) VALUES (?, ?)",
            [(pub.url, region) for region in pub.regions]
        )

        return is_new

    def get(self, url: str) -> Publication | None:
        row = self.conn.execute(
            "SELECT url, title, pub_type, published FROM publications WHERE url = ?", (url,)
        ).fetchone()
        if row is None:
            return None
        authors = [r[0] for r in self.conn.execute(
            "SELECT author FROM publication_authors WHERE url = ? ORDER BY position", (url,))]
        regions = [r[0] for r in self.conn.execute(
            "SELECT region FROM publication_regions WHERE url = ? ORDER BY region", (url,))]
        return Publication(url=row[0], title=row[1], pub_type=row[2], published=row[3],
                           authors=authors, regions=regions)

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0]

    def record_run(self, run: RunRecord) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO scrape_runs (started_at, finished_at, status, pages_scraped,
                items_found, items_saved, items_new, items_invalid, error)
            VALUES (:started_at, :finished_at, :status, :pages_scraped,
                :items_found, :items_saved, :items_new, :items_invalid, :error)
            """,
            asdict(run),
        )
        self.conn.commit()
        return cursor.lastrowid

    def export_csv(self, path: Path) -> int:
        rows = self.conn.execute(
            """
            SELECT p.url, p.title, p.pub_type, p.published,
                   (SELECT group_concat(author, '; ') FROM
                       (SELECT author FROM publication_authors a WHERE a.url = p.url ORDER BY position)),
                   (SELECT group_concat(region, '; ') FROM
                       (SELECT region FROM publication_regions r WHERE r.url = p.url ORDER BY region))
            FROM publications p
            ORDER BY p.published DESC, p.url
            """
        ).fetchall()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["url", "title", "pub_type", "published", "authors", "regions"])
            writer.writerows(rows)
        logger.info("Exported %d publications to %s", len(rows), path)
        return len(rows)

    def counts_by_year_and_type(self) -> list[tuple[str, str, int]]:
        return self.conn.execute(
            """
            SELECT substr(published, 1, 4) AS year, pub_type, COUNT(*)
            FROM publications GROUP BY year, pub_type ORDER BY year DESC, pub_type
            """
        ).fetchall()

    def top_authors(self, limit: int = 10) -> list[tuple[str, int]]:
        return self.conn.execute(
            "SELECT author, COUNT(*) AS n FROM publication_authors "
            "GROUP BY author ORDER BY n DESC, author LIMIT ?",
            (limit,),
        ).fetchall()

    def last_runs(self, limit: int = 5) -> list[tuple]:
        return self.conn.execute(
            "SELECT id, started_at, status, pages_scraped, items_found, items_new, items_invalid "
            "FROM scrape_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()