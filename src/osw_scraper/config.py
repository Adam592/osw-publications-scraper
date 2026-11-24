import os
from dataclasses import dataclass, replace
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_url: str = "https://www.osw.waw.pl"
    language: str = "pl"
    db_path: Path = Path("data/osw.db")

    start_page: int = 0
    max_pages: int = 5
    by_region: bool = False
    stop_after_known_pages: int = 0

    delay_seconds: float = 2.0
    timeout_ms: int = 30_000
    retries: int = 3
    respect_robots_txt: bool = True
    user_agent: str = "osw-publications-scraper/0.1"
    headless: bool = True

    max_invalid_ratio: float = 0.1
    log_level: str = "INFO"
    log_dir: Path | None = Path("logs")

    @property
    def listing_path(self) -> str:
        return f"/{self.language}/publikacje"

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            base_url=os.getenv("OSW_BASE_URL", d.base_url).rstrip("/"),
            db_path=Path(os.getenv("OSW_DB_PATH", str(d.db_path))),
            max_pages=int(os.getenv("OSW_MAX_PAGES", d.max_pages)),
            delay_seconds=float(os.getenv("OSW_DELAY_SECONDS", d.delay_seconds)),
            retries=int(os.getenv("OSW_RETRIES", d.retries)),
            headless=_env_bool("OSW_HEADLESS", d.headless),
            log_level=os.getenv("LOG_LEVEL", d.log_level).upper(),
        )

    def with_overrides(self, **overrides) -> "Settings":
        return replace(self, **{k: v for k, v in overrides.items() if v is not None})