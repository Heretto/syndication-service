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
from hop_core.models.organization import Organization, OrganizationMember
from hop_core.models.user import User
from hop_core.models.enums import OrganizationRole
from hop_core.core.security import get_password_hash

log = logging.getLogger(__name__)


# ── First-user-as-admin middleware ────────────────────────────────────────────

class _FirstUserAdminMiddleware:
    """Promote the first registered user to superuser + org admin.

    Runs after every POST /auth/register that returns 200. If exactly one user
    exists at that point (meaning this was the first registration) and they are
    not already a superuser, they are promoted. All other requests pass through
    untouched.
    """

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        is_register = (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path", "").endswith("/auth/register")
        )
        if not is_register:
            await self._app(scope, receive, send)
            return

        status: list[int] = []

        async def _capture(message):
            if message["type"] == "http.response.start":
                status.append(message["status"])
            await send(message)

        await self._app(scope, receive, _capture)

        if status and status[0] == 200:
            self._maybe_promote()

    @staticmethod
    def _maybe_promote():
        from hop_core.db import get_session_factory
        from hop_core.models.user import User
        from hop_core.models.organization import OrganizationMember
        from hop_core.models.enums import OrganizationRole

        db = get_session_factory()()
        try:
            # If any superuser already exists, nothing to do.
            if db.query(User).filter(User.is_superuser.is_(True)).first():
                return
            # Promote the earliest-registered user (guards against the race where
            # two registrations happen before either middleware check runs — under
            # that scenario neither would see count==1, so we'd promote nobody).
            user = db.query(User).order_by(User.created_at).first()
            if user and not user.is_superuser:
                user.is_superuser = True
                member = db.query(OrganizationMember).filter_by(user_id=user.id).first()
                if member:
                    member.role = OrganizationRole.ADMIN
                db.commit()
                log.info("Auto-promoted first registered user <%s> to superuser.", user.email)
        except Exception:
            log.exception("Failed to auto-promote first registered user.")
            db.rollback()
        finally:
            db.close()


# ── First-run seed ────────────────────────────────────────────────────────────

def _seed(session_factory):
    """Seed the default org and (optionally) the first admin account.

    Idempotent — skipped entirely if org and superuser already exist.
    Admin creation only runs when ADMIN_EMAIL + ADMIN_PASSWORD are set.
    Any failure is logged and swallowed so startup is never blocked.
    """
    settings = get_settings()
    db = session_factory()
    try:
        # ── Org ───────────────────────────────────────────────────────────────
        org = None
        if settings.single_org_mode and settings.single_org_slug:
            org = db.query(Organization).filter_by(slug=settings.single_org_slug).first()
            if not org:
                import uuid as _uuid
                org = Organization(
                    id=_uuid.uuid4(),
                    name=settings.single_org_slug.capitalize(),
                    slug=settings.single_org_slug,
                )
                db.add(org)
                db.commit()
                db.refresh(org)
                log.info("Created default organization '%s'.", settings.single_org_slug)

        # ── Admin user ────────────────────────────────────────────────────────
        if not settings.admin_email or not settings.admin_password:
            log.info(
                "ADMIN_EMAIL / ADMIN_PASSWORD not set — skipping auto-seed. "
                "Run 'python scripts/seed.py' to create the first admin account."
            )
            return

        if db.query(User).filter(User.is_superuser.is_(True)).first():
            return  # already seeded

        if org is None and settings.single_org_slug:
            org = db.query(Organization).filter_by(slug=settings.single_org_slug).first()

        import uuid as _uuid
        admin = User(
            id=_uuid.uuid4(),
            email=settings.admin_email,
            password_hash=get_password_hash(settings.admin_password),
            is_active=True,
            is_superuser=True,
            current_organization_id=org.id if org else None,
        )
        db.add(admin)
        db.flush()
        if org:
            db.add(OrganizationMember(
                user_id=admin.id,
                organization_id=org.id,
                role=OrganizationRole.ADMIN,
            ))
        db.commit()
        log.info("Auto-seed: created admin account <%s>.", settings.admin_email)
    except Exception:
        log.exception("Auto-seed failed — continuing startup.")
        db.rollback()
    finally:
        db.close()


# ── Lifespan ──────────────────────────────────────────────────────────────────

def _build_lifespan(hop_lifespan):
    """Wrap hop-core's lifespan to add scheduler start/stop."""

    @asynccontextmanager
    async def _lifespan(app):
        async with hop_lifespan(app):
            # Create all syndication tables (Alembic handles schema migrations
            # in production; create_all is safe for dev/test).
            session_factory = get_session_factory()

            _seed(session_factory)

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

            orphans = store.fail_orphaned_runs()
            if orphans:
                log.warning("Marked %d orphaned run(s) as failed on startup.", orphans)

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

app.add_middleware(_FirstUserAdminMiddleware)

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
