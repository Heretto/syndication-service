"""Application entry point for the syndication-service.

Creates the FastAPI app using hop-core's ``create_hop_app()`` factory,
wraps the lifespan to start/stop APScheduler, and registers the syncs router.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from functools import lru_cache

from hop_core.app_factory import create_hop_app
from hop_core.db import Base, init_engine, get_session_factory

from syndication.settings import get_settings
from syndication.models import SyncConfig  # noqa: F401 — registers tables on Base
from syndication.models import SyncRun, SyncRecord  # noqa: F401
from syndication.state_store import SyncStateStore
from syndication.services.sync_executor import SyncExecutorService
from syndication.services.scheduler import SyncSchedulerService
from syndication.routes.syncs import router as syncs_router
from syndication.source.deploy.adapter import DeployAdapter
from syndication.connector.noop.connector import NoopConnector

log = logging.getLogger(__name__)


# ── Adapter / connector factories ─────────────────────────────────────────────

def _adapter_factory(cfg: SyncConfig):
    """Build a source adapter from a SyncConfig."""
    settings = get_settings()
    if cfg.adapter_id == "deploy":
        # API key will come from hop-core Credential model in a future iteration;
        # for now fall back to an env-var-style placeholder.
        return DeployAdapter(
            org_id=cfg.org_id,
            deployment_id=cfg.deployment_id or "",
            api_key="",  # TODO: load from hop-core Credential
            audience=settings.deploy_default_audience,
        )
    raise ValueError(f"Unknown adapter_id: {cfg.adapter_id!r}")


def _connector_factory(cfg: SyncConfig):
    """Build a target connector from a SyncConfig."""
    if cfg.connector_id == "noop":
        return NoopConnector()
    # Additional connectors (salesforce, zendesk, servicenow) registered here
    raise ValueError(f"Unknown connector_id: {cfg.connector_id!r}")


# ── Lifespan ──────────────────────────────────────────────────────────────────

def _build_lifespan(hop_lifespan):
    """Wrap hop-core's lifespan to add scheduler start/stop."""

    @asynccontextmanager
    async def _lifespan(app):
        async with hop_lifespan(app):
            # Create all syndication tables (Alembic handles schema migrations
            # in production; create_all is safe for dev/test).
            session_factory = get_session_factory()
            store = SyncStateStore(session_factory=session_factory)
            executor = SyncExecutorService(
                state_store=store,
                settings=get_settings(),
                adapter_factory=_adapter_factory,
                connector_factory=_connector_factory,
            )
            scheduler = SyncSchedulerService(state_store=store, executor=executor)

            # Expose via app.state for route handlers
            app.state.store = store
            app.state.executor = executor
            app.state.scheduler = scheduler

            scheduler.start()
            scheduler.load_all()
            log.info("Syndication scheduler started.")

            yield

            scheduler.shutdown()
            log.info("Syndication scheduler stopped.")

    return _lifespan


# ── App ───────────────────────────────────────────────────────────────────────

app = create_hop_app(
    settings_factory=get_settings,
    title="Syndication Service",
    description="DITA → knowledge-base syndication built on hop-core.",
    version="0.1.0",
)

# Register syncs routes directly (avoids FastAPI 0.138 _IncludedRouter lazy-eval issue)
app.include_router(syncs_router, prefix=get_settings().api_prefix)

# Wrap hop-core's lifespan with our scheduler lifecycle
_hop_lifespan = app.router.lifespan_context
app.router.lifespan_context = _build_lifespan(_hop_lifespan)
