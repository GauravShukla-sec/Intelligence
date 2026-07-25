"""Configuration loading.

Reads configuration from environment variables (optionally seeded from a
local `.env` file). No secrets are hard-coded. A minimal `.env` parser is
included so the app runs without python-dotenv installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Project root is the directory that contains this package's parent.
ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a .env file without overwriting existing vars.

    Intentionally tiny and forgiving: supports `KEY=VALUE`, comments (#), and
    quoted values. Does not support multi-line values.
    """
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        # A missing/unreadable .env must never crash the app.
        pass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    """Resolved runtime configuration."""

    secret_key: str = "dev-insecure-key-change-me"
    host: str = "127.0.0.1"
    port: int = 8000
    env: str = "development"

    db_path: str = "gsid.sqlite3"

    # demo | live | hybrid
    data_mode: str = "demo"
    enabled_feeds: list[str] = field(default_factory=list)
    ingest_interval_minutes: int = 30
    fetch_timeout_seconds: int = 15
    ingest_every_hours: int = 0  # 0 = disabled (no in-process auto-refresh)

    ai_provider: str = "heuristic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    auth_enabled: bool = False
    access_token: str = ""

    # Public read-only deployment: anyone may view + refresh, but settings/
    # watchlist/feeds require the admin token. Per-visitor items live in the
    # browser (localStorage), so no login is needed just to use the desk.
    public_readonly: bool = False
    admin_token: str = ""
    public_allow_refresh: bool = True

    default_timezone: str = "UTC"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def db_file(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else (ROOT / p)


def load_config(env_file: str | os.PathLike | None = None) -> Config:
    """Load configuration from environment (and .env if present)."""
    _load_dotenv(Path(env_file) if env_file else (ROOT / ".env"))

    feeds_raw = os.environ.get("GSID_ENABLED_FEEDS", "").strip()
    enabled_feeds = [f.strip() for f in feeds_raw.split(",") if f.strip()]

    return Config(
        secret_key=os.environ.get("GSID_SECRET_KEY", "dev-insecure-key-change-me"),
        host=os.environ.get("GSID_HOST", "127.0.0.1"),
        port=_as_int(os.environ.get("GSID_PORT"), 8000),
        env=os.environ.get("GSID_ENV", "development"),
        db_path=os.environ.get("GSID_DB_PATH", "gsid.sqlite3"),
        data_mode=os.environ.get("GSID_DATA_MODE", "demo").strip().lower(),
        enabled_feeds=enabled_feeds,
        ingest_interval_minutes=_as_int(os.environ.get("GSID_INGEST_INTERVAL_MINUTES"), 30),
        fetch_timeout_seconds=_as_int(os.environ.get("GSID_FETCH_TIMEOUT_SECONDS"), 15),
        ingest_every_hours=_as_int(os.environ.get("GSID_INGEST_EVERY_HOURS"), 0),
        ai_provider=os.environ.get("GSID_AI_PROVIDER", "heuristic").strip().lower(),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.environ.get("GSID_ANTHROPIC_MODEL", "claude-sonnet-5"),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("GSID_OPENAI_MODEL", "gpt-4o-mini"),
        auth_enabled=_as_bool(os.environ.get("GSID_AUTH_ENABLED"), False),
        access_token=os.environ.get("GSID_ACCESS_TOKEN", ""),
        public_readonly=_as_bool(os.environ.get("GSID_PUBLIC_READONLY"), False),
        admin_token=(os.environ.get("GSID_ADMIN_TOKEN", "")
                     or os.environ.get("GSID_ACCESS_TOKEN", "")),
        public_allow_refresh=_as_bool(os.environ.get("GSID_PUBLIC_ALLOW_REFRESH"), True),
        default_timezone=os.environ.get("GSID_DEFAULT_TIMEZONE", "UTC"),
    )
