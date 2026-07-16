"""Shared pytest fixtures for syndication-service tests."""
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_settings() -> MagicMock:
    """Return a MagicMock that satisfies all AppSettings attribute accesses."""
    s = MagicMock()
    # hop-core required
    s.app_secret_key = "test-secret-key-32-chars-minimum!"
    s.jwt_secret_key = "test-jwt-key-32-chars-minimum!!!!"
    s.encryption_key = "test-16charkey!!"
    s.database_url = "sqlite+aiosqlite:///:memory:"
    s.redis_url = ""
    # hop-core optional
    s.app_env = "test"
    s.app_debug = False
    s.cors_origins = "http://localhost:4200"
    s.cookie_secure = False
    s.single_org_mode = True
    s.single_org_slug = "syndication"
    s.frontend_base_url = "http://localhost:4200"
    # Deploy API
    s.deploy_default_audience = "private"
    # Sync executor
    s.sync_max_consecutive_failures = 5
    s.sync_retention_days = 90
    s.sync_timeout_seconds = 3600
    # Retry
    s.retry_max_attempts = 3
    s.retry_initial_delay_ms = 1000
    s.retry_max_delay_ms = 30000
    s.retry_backoff_multiplier = 2.0
    return s


@pytest.fixture(autouse=True)
def mock_settings():
    """Patch every get_settings import site so no real env vars are needed.

    Additional patch targets are added here as their modules are created.
    """
    s = _make_mock_settings()
    # Keep this list in sync with every module that does:
    #   from syndication.settings import get_settings
    patch_targets = [
        "syndication.settings.get_settings",
        # added when syndication/source/deploy/client.py is created:
        # "syndication.source.deploy.client.get_settings",
        # "syndication.source.deploy.adapter.get_settings",
        # added when syndication/services/* are created:
        # "syndication.services.sync_executor.get_settings",
        # "syndication.services.scheduler.get_settings",
    ]
    patches = [patch(t, return_value=s) for t in patch_targets]
    for p in patches:
        p.start()
    yield s
    for p in patches:
        p.stop()
