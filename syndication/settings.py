"""Application settings for syndication-service.

Extends HopCoreSettings with service-specific configuration.
All values are read from environment variables (or .env file).
"""
from __future__ import annotations

from functools import lru_cache

from hop_core.config import HopCoreSettings


class AppSettings(HopCoreSettings):
    # hop-core makes redis_url required; override to make it optional
    redis_url: str = ""

    # ── Sync executor ─────────────────────────────────────────────────────────
    sync_max_consecutive_failures: int = 5
    sync_retention_days: int = 90
    sync_timeout_seconds: int = 3600

    # ── Retry ─────────────────────────────────────────────────────────────────
    retry_max_attempts: int = 3
    retry_initial_delay_ms: int = 1000
    retry_max_delay_ms: int = 30000
    retry_backoff_multiplier: float = 2.0


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
