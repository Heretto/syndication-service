"""Synchronous state store for syndication runs.

All methods use synchronous SQLAlchemy sessions.  In async FastAPI request
handlers call these via ``asyncio.get_event_loop().run_in_executor()`` or use
FastAPI's ``run_in_threadpool``; inside the executor service they are called
directly from synchronous helper threads spun by APScheduler.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable

_UNSET = object()  # sentinel: distinguishes "not provided" from "explicitly set to None"

from sqlalchemy.orm import Session, sessionmaker

from syndication.models import SyncConfig, SyncRecord, SyncRun


class SyncStateStore:
    """Provides all persistence operations required by the sync executor.

    Args:
        session_factory: A SQLAlchemy ``sessionmaker`` bound to the DB engine.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self._factory = session_factory

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _session(self) -> Session:
        return self._factory()

    def _with_session(self, fn: Callable[[Session], object]) -> object:
        db = self._session()
        try:
            result = fn(db)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ── SyncConfig ────────────────────────────────────────────────────────────

    def create_sync(
        self,
        name: str,
        adapter_id: str,
        connector_id: str,
        org_id: str,
        deployment_id: str,
        cron_expression: str,
        mapping: dict | None = None,
        credential_id: str | None = None,
        publish_mode: str = "auto",
        deploy_audience: str | None = None,
    ) -> SyncConfig:
        db = self._session()
        try:
            cfg = SyncConfig(
                name=name,
                adapter_id=adapter_id,
                connector_id=connector_id,
                org_id=org_id,
                deployment_id=deployment_id,
                cron_expression=cron_expression,
                publish_mode=publish_mode,
                deploy_audience=deploy_audience,
                mapping_json=json.dumps(mapping or {}),
                credential_id=credential_id,
            )
            db.add(cfg)
            db.commit()
            # refresh re-loads all attributes (clearing the post-commit expired state)
            # expunge safely detaches the object while keeping loaded values in __dict__
            db.refresh(cfg)
            db.expunge(cfg)
            return cfg
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_sync(self, sync_id: str) -> SyncConfig | None:
        db = self._session()
        try:
            cfg = db.query(SyncConfig).filter(SyncConfig.id == sync_id).first()
            if cfg is not None:
                db.expunge(cfg)
            return cfg
        finally:
            db.close()

    def list_active_syncs(self, org_id: str | None = None) -> list[SyncConfig]:
        db = self._session()
        try:
            q = db.query(SyncConfig).filter(SyncConfig.is_active.is_(True))
            if org_id is not None:
                q = q.filter(SyncConfig.org_id == org_id)
            results = q.all()
            for obj in results:
                db.expunge(obj)
            return results
        finally:
            db.close()

    def update_sync(
        self,
        sync_id: str,
        name: str | None = _UNSET,
        cron_expression: str | None = _UNSET,
        deployment_id: str | None = _UNSET,
        credential_id: str | None = _UNSET,
        mapping: dict | None = _UNSET,
        publish_mode: str | None = _UNSET,
        deploy_audience: str | None = _UNSET,
    ) -> SyncConfig:
        db = self._session()
        try:
            cfg = db.query(SyncConfig).filter(SyncConfig.id == sync_id).first()
            if cfg is None:
                raise ValueError(f"Sync {sync_id!r} not found")
            if name is not _UNSET:
                cfg.name = name
            if cron_expression is not _UNSET:
                cfg.cron_expression = cron_expression
            if deployment_id is not _UNSET:
                cfg.deployment_id = deployment_id
            if credential_id is not _UNSET:
                cfg.credential_id = credential_id
            if mapping is not _UNSET:
                cfg.mapping_json = json.dumps(mapping)
            if publish_mode is not _UNSET:
                cfg.publish_mode = publish_mode
            if deploy_audience is not _UNSET:
                cfg.deploy_audience = deploy_audience
            cfg.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(cfg)
            db.expunge(cfg)
            return cfg
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def deactivate_sync(self, sync_id: str) -> None:
        def _deactivate(db: Session) -> None:
            db.query(SyncConfig).filter(SyncConfig.id == sync_id).update(
                {"is_active": False, "updated_at": datetime.now(timezone.utc)}
            )

        self._with_session(_deactivate)

    def delete_sync(self, sync_id: str) -> None:
        """Permanently delete a SyncConfig and all its runs and records."""
        def _delete(db: Session) -> None:
            cfg = db.query(SyncConfig).filter(SyncConfig.id == sync_id).first()
            if cfg is not None:
                db.delete(cfg)

        self._with_session(_delete)

    # ── High-water mark ───────────────────────────────────────────────────────

    def get_high_water_mark(self, sync_id: str) -> str | None:
        cfg = self.get_sync(sync_id)
        return cfg.high_water_mark if cfg else None

    def set_high_water_mark(self, sync_id: str, hwm: str) -> None:
        def _set(db: Session) -> None:
            db.query(SyncConfig).filter(SyncConfig.id == sync_id).update(
                {"high_water_mark": hwm, "updated_at": datetime.now(timezone.utc)}
            )

        self._with_session(_set)

    # ── Article mappings ──────────────────────────────────────────────────────

    def save_article_mapping(
        self, sync_id: str, source_uuid: str, target_article_id: str
    ) -> None:
        def _save(db: Session) -> None:
            existing = (
                db.query(SyncRecord)
                .filter(
                    SyncRecord.sync_id == sync_id,
                    SyncRecord.source_uuid == source_uuid,
                )
                .first()
            )
            if existing:
                existing.target_article_id = target_article_id
                existing.status = "active"
                existing.last_synced_at = datetime.now(timezone.utc)
            else:
                db.add(
                    SyncRecord(
                        sync_id=sync_id,
                        source_uuid=source_uuid,
                        target_article_id=target_article_id,
                    )
                )

        self._with_session(_save)

    def get_target_id(self, sync_id: str, source_uuid: str) -> str | None:
        db = self._session()
        try:
            rec = (
                db.query(SyncRecord)
                .filter(
                    SyncRecord.sync_id == sync_id,
                    SyncRecord.source_uuid == source_uuid,
                )
                .first()
            )
            return rec.target_article_id if rec else None
        finally:
            db.close()

    def get_target_ids_for_uuids(
        self, sync_id: str, source_uuids: list[str]
    ) -> dict[str, str]:
        """Return ``{source_uuid: target_article_id}`` for all matching records."""
        if not source_uuids:
            return {}
        db = self._session()
        try:
            records = (
                db.query(SyncRecord)
                .filter(
                    SyncRecord.sync_id == sync_id,
                    SyncRecord.source_uuid.in_(source_uuids),
                )
                .all()
            )
            return {r.source_uuid: r.target_article_id for r in records}
        finally:
            db.close()

    def list_records(
        self,
        sync_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[SyncRecord]:
        """Return synced article records for *sync_id*, newest first.

        Args:
            sync_id: The sync configuration ID.
            status:  Optional filter — ``"active"`` or ``"archived"``.
            limit:   Maximum number of rows to return (default 100).
        """
        db = self._session()
        try:
            q = (
                db.query(SyncRecord)
                .filter(SyncRecord.sync_id == sync_id)
                .order_by(SyncRecord.last_synced_at.desc())
            )
            if status is not None:
                q = q.filter(SyncRecord.status == status)
            results = q.limit(limit).all()
            for obj in results:
                db.expunge(obj)
            return results
        finally:
            db.close()

    def mark_articles_archived(
        self, sync_id: str, source_uuids: list[str]
    ) -> None:
        """Mark SyncRecord rows as archived for the given source UUIDs."""
        if not source_uuids:
            return

        def _archive(db: Session) -> None:
            db.query(SyncRecord).filter(
                SyncRecord.sync_id == sync_id,
                SyncRecord.source_uuid.in_(source_uuids),
            ).update({"status": "archived"}, synchronize_session="fetch")

        self._with_session(_archive)

    # ── Sync runs ─────────────────────────────────────────────────────────────

    def create_run(self, sync_id: str, run_id: str) -> SyncRun:
        db = self._session()
        try:
            run = SyncRun(id=run_id, sync_id=sync_id, status="running")
            db.add(run)
            db.commit()
            db.refresh(run)
            db.expunge(run)
            return run
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_run(self, run_id: str) -> SyncRun | None:
        db = self._session()
        try:
            run = db.query(SyncRun).filter(SyncRun.id == run_id).first()
            if run is not None:
                db.expunge(run)
            return run
        finally:
            db.close()

    def complete_run(
        self,
        run_id: str,
        changed_count: int,
        removed_count: int,
        links_fixed: int = 0,
        warnings: list[str] | None = None,
    ) -> None:
        def _complete(db: Session) -> None:
            status = "warning" if warnings else "success"
            db.query(SyncRun).filter(SyncRun.id == run_id).update(
                {
                    "status": status,
                    "completed_at": datetime.now(timezone.utc),
                    "changed_count": changed_count,
                    "removed_count": removed_count,
                    "links_fixed": links_fixed,
                    "warning_messages": json.dumps(warnings) if warnings else None,
                }
            )

        self._with_session(_complete)

    def fail_run(self, run_id: str, error_message: str) -> None:
        def _fail(db: Session) -> None:
            db.query(SyncRun).filter(SyncRun.id == run_id).update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc),
                    "error_message": error_message,
                }
            )

        self._with_session(_fail)

    def fail_orphaned_runs(self) -> int:
        """Mark any run still in 'running' state as failed.

        Called at startup so runs orphaned by a mid-run server restart
        don't stay stuck as 'running' in the history indefinitely.
        Returns the number of rows updated.
        """
        def _fail_orphans(db: Session) -> int:
            return db.query(SyncRun).filter(SyncRun.status == "running").update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc),
                    "error_message": "Run orphaned by server restart.",
                },
                synchronize_session=False,
            )

        return self._with_session(_fail_orphans)

    def list_runs(self, sync_id: str, limit: int = 20) -> list[SyncRun]:
        db = self._session()
        try:
            results = (
                db.query(SyncRun)
                .filter(SyncRun.sync_id == sync_id)
                .order_by(SyncRun.started_at.desc())
                .limit(limit)
                .all()
            )
            for obj in results:
                db.expunge(obj)
            return results
        finally:
            db.close()
