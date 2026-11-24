
# OSW publications scraper

A tool that builds a structured dataset of publications from the [Centre for Eastern Studies (OSW)](https://www.osw.waw.pl/pl/publikacje): title, type, publication date, authors and regions.

The dataset makes it possible to answer quantitative questions such as *how did coverage of a region change over time?* or *which publication formats are growing?*

Built with **Playwright** (browser automation), **pydantic** (validation), **SQLite** (storage) and **pytest** (tests).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate        # Windows (Git Bash): source .venv/Scripts/activate
pip install -e ".[dev]"
python -m playwright install chromium

osw-scraper scrape --max-pages 3     # first 3 listing pages (~30 publications)
osw-scraper stats                    # summary of the dataset
osw-scraper export                   # data/publications.csv
```

Other runs:

```bash
osw-scraper scrape --by-region --max-pages 10   # tag publications with regions
osw-scraper scrape --incremental                # stop at the first page with nothing new
osw-scraper scrape --max-pages 1 --headed       # watch the browser
```

## How it works

```
listing page ──► scraper.py ──► RawItem ──► parser.py ──► Publication ──► storage.py
 (Playwright)    find links,               clean, parse,   (validated)     (SQLite)
                 grab context              fall back
```

| Module          | Responsibility                                                                   |
| --------------- | -------------------------------------------------------------------------------- |
| `scraper.py`  | Browser session, retries, robots.txt, extracting raw items, region filters       |
| `parser.py`   | Pure functions: whitespace cleanup, `type \| date \| authors` parsing, fallbacks |
| `models.py`   | Validation rules (URL shape, plausible dates, no blank or duplicate authors)     |
| `storage.py`  | Schema, idempotent upserts, CSV export, aggregations                             |
| `pipeline.py` | Orchestration, run statistics, run status                                        |
| `cli.py`      | `scrape`, `export`, `stats` commands and exit codes                        |

## Design decisions

- **Started with a throwaway prototype.** Before writing the scraper I explored the page in DevTools and a one-file script. Two findings shaped the design: the metadata line is a few levels *above* the link, not inside it, and the page has **no `<main>` element**, so my first selector returned nothing.
- **Publications are found by URL shape, not CSS classes.** A publication is any link matching `/publikacje/<type>/<YYYY-MM-DD>/<slug>`. Class names change with every redesign; URLs rarely do.
- **Walk up the DOM to the smallest ancestor holding the metadata**, and stop if that ancestor contains links to *other* publications, so metadata can never leak between items. Duplicate links (image + title) are merged.
- **The parser has no browser dependency.** It is plain functions on text, so it is tested in milliseconds without network access.
- **Defensive parsing, loud logging.** Missing metadata falls back to the type and date in the URL. A date that differs between text and URL is kept and logged as a warning. Invalid items are skipped and counted; they never stop the run.
- **Validation based on the data.** Dates before 2001 are rejected because the site's own year filter starts in 2001.
- **A quality gate.** If more than 10% of items fail validation, the run is marked `partial` (exit code 2), which usually means the page layout changed.
- **Idempotent storage.** Upserts mean re-running never creates duplicates. Progress is committed after every page, so a crash keeps earlier pages.
- **Polite by default.** Respects robots.txt, waits 2 seconds between pages, sends an identifying User-Agent.

## Data model

```
publications(url PK, title, pub_type, published, first_seen, last_seen)
publication_authors(url, author, position)
publication_regions(url, region)
scrape_runs(id, started_at, finished_at, status, pages_scraped,
            items_found, items_saved, items_new, items_invalid, error)
```

Example query, publications per region per year:

```sql
SELECT r.region, substr(p.published, 1, 4) AS year, COUNT(*) AS n
FROM publications p JOIN publication_regions r USING (url)
GROUP BY r.region, year ORDER BY r.region, year;
```

## Configuration

Settings can be passed as environment variables; CLI flags override them.

| Variable              | Default         | Meaning                 |
| --------------------- | --------------- | ----------------------- |
| `OSW_DB_PATH`       | `data/osw.db` | SQLite file             |
| `OSW_MAX_PAGES`     | `5`           | Pages per listing       |
| `OSW_DELAY_SECONDS` | `2`           | Pause between pages     |
| `OSW_RETRIES`       | `3`           | Attempts per page       |
| `OSW_HEADLESS`      | `true`        | Hide the browser window |
| `LOG_LEVEL`         | `INFO`        | Logging level           |

Exit codes: `0` success, `1` failed, `2` partial.
Logs go to the console and to `logs/scraper.log` (rotated at 5 MB).

## Tests

```bash
pytest -v                                        # fast tests, no network
OSW_LIVE_TESTS=1 pytest -v tests/test_scraper.py # one test against the real site
```

- **Unit tests** for the model, parser, retry logic and storage.
- **Pipeline tests** use a fake scraper, so counting, run status, incremental mode and crash recovery are tested without a browser.
- **One live test** is skipped by default so the test suite never depends on the website being up and never puts load on it.

## Docker

```bash
docker build -t osw-scraper .
docker run --rm -v "$PWD/data:/app/data" osw-scraper                # incremental scrape
docker run --rm -v "$PWD/data:/app/data" osw-scraper stats
```

Based on the official Playwright image, runs as a non-root user.

## Limitations and next steps

- Only listing pages are scraped; detail pages (tags, abstracts) are not.
- Regions require `--by-region`, which scrapes each region filter separately.
- Possible next steps: PostgreSQL instead of SQLite, scheduled runs as a cloud container job, logs and exports in blob storage, alerts when a run ends as `failed` or `partial`, and tests against a local fake site.

## Responsible use

The scraper reads publicly available listing pages, respects robots.txt and limits its request rate. It collects publication metadata only, not the texts.
All content belongs to OSW.
