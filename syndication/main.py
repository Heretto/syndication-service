"""Application entry point for the syndication-service.

Creates the FastAPI app using hop-core's ``create_hop_app()`` factory,
wraps the lifespan to start/stop APScheduler, and registers the syncs router.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)

from hop_core.app_factory import create_hop_app
from hop_core.db import get_session_factory

from syndication.settings import get_settings
from syndication.models import SyncConfig  # noqa: F401 — registers tables on Base
from syndication.models import SyncRun, SyncRecord  # noqa: F401
from syndication.state_store import SyncStateStore
from syndication.services.sync_executor import SyncExecutorService
from syndication.services.scheduler import SyncSchedulerService
from syndication.routes.syncs import router as syncs_router
from syndication.routes.fields import router as fields_router
from syndication.factory import build_adapter, build_connector

log = logging.getLogger(__name__)


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
            app.state.session_factory = session_factory
            executor = SyncExecutorService(
                state_store=store,
                settings=get_settings(),
                adapter_factory=lambda cfg: build_adapter(cfg, session_factory),
                connector_factory=lambda cfg: build_connector(cfg, session_factory),
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

# Health check — available without auth, outside the api_prefix
@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


# Register syncs routes directly (avoids FastAPI 0.138 _IncludedRouter lazy-eval issue)
app.include_router(syncs_router, prefix=get_settings().api_prefix)
app.include_router(fields_router, prefix=get_settings().api_prefix)

# Wrap hop-core's lifespan with our scheduler lifecycle
_hop_lifespan = app.router.lifespan_context
app.router.lifespan_context = _build_lifespan(_hop_lifespan)
