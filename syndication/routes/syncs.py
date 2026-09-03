"""API routes for sync configuration management.

All routes are mounted under ``/syncs`` via :data:`router`.
Services are read from ``request.app.state`` (set during lifespan in main.py).
Every route requires a valid JWT with an associated organisation.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Any

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org

router = APIRouter(prefix="/syncs", tags=["syncs"])

# Annotated alias — keeps route signatures concise
OrgCtx = Annotated[CurrentUserContext, Depends(get_current_active_user_with_org)]


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CreateSyncRequest(BaseModel):
    name: str
    adapter_id: str
    connector_id: str
    deployment_id: str
    cron_expression: str | None = None
    mapping: dict[str, Any] = {}
    credential_id: str | None = None


class UpdateSyncRequest(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    deployment_id: str | None = None
    credential_id: str | None = None
    mapping: dict[str, Any] | None = None


class SyncConfigResponse(BaseModel):
    id: str
    name: str
    adapter_id: str
    connector_id: str
    org_id: str
    deployment_id: str | None
    cron_expression: str | None
    is_active: bool
    high_water_mark: str | None
    credential_id: str | None
    mapping: dict[str, Any]
    created_at: datetime | None

    @classmethod
    def from_model(cls, cfg: Any) -> "SyncConfigResponse":
        return cls(
            id=cfg.id,
            name=cfg.name,
            adapter_id=cfg.adapter_id,
            connector_id=cfg.connector_id,
            org_id=cfg.org_id,
            deployment_id=cfg.deployment_id,
            cron_expression=cfg.cron_expression,
            is_active=cfg.is_active,
            high_water_mark=cfg.high_water_mark,
            credential_id=getattr(cfg, "credential_id", None),
            mapping=cfg.mapping if isinstance(cfg.mapping, dict) else {},
            created_at=getattr(cfg, "created_at", None),
        )


class SyncRunResponse(BaseModel):
    id: str
    sync_id: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    changed_count: int | None
    removed_count: int | None
    links_fixed: int | None
    error_message: str | None
    warning_messages: list[str] | None

    @classmethod
    def from_model(cls, run: Any) -> "SyncRunResponse":
        import json as _json
        raw = getattr(run, "warning_messages", None)
        warnings = _json.loads(raw) if raw else None
        return cls(
            id=run.id,
            sync_id=run.sync_id,
            status=run.status,
            started_at=getattr(run, "started_at", None),
            completed_at=getattr(run, "completed_at", None),
            changed_count=getattr(run, "changed_count", None),
            removed_count=getattr(run, "removed_count", None),
            links_fixed=getattr(run, "links_fixed", None),
            error_message=getattr(run, "error_message", None),
            warning_messages=warnings,
        )


class SyncRecordResponse(BaseModel):
    id: str
    sync_id: str
    source_uuid: str
    target_article_id: str
    status: str
    last_synced_at: datetime | None

    @classmethod
    def from_model(cls, rec: Any) -> "SyncRecordResponse":
        return cls(
            id=rec.id,
            sync_id=rec.sync_id,
            source_uuid=rec.source_uuid,
            target_article_id=rec.target_article_id,
            status=rec.status,
            last_synced_at=getattr(rec, "last_synced_at", None),
        )


class TriggerResponse(BaseModel):
    sync_id: str
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_cron(cron_expression: str | None) -> None:
    """Raise 422 if *cron_expression* is non-null and not a valid crontab string."""
    if cron_expression:
        try:
            CronTrigger.from_crontab(cron_expression)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid cron expression: {exc}",
            )


# ── Dependency helpers ────────────────────────────────────────────────────────

def _store(req: Request):
    return req.app.state.store


def _scheduler(req: Request):
    return req.app.state.scheduler


def _executor(req: Request):
    return req.app.state.executor


def _get_sync_or_404(req: Request, sync_id: str):
    cfg = _store(req).get_sync(sync_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Sync {sync_id!r} not found")
    return cfg


def _assert_same_org(cfg: Any, context: CurrentUserContext) -> None:
    """Raise 403 if *cfg* belongs to a different organisation than *context*."""
    if cfg.org_id != str(context.organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this sync.",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SyncConfigResponse])
def list_syncs(request: Request, context: OrgCtx):
    """List all active sync configurations for the authenticated organisation."""
    org_id = str(context.organization_id)
    syncs = _store(request).list_active_syncs(org_id=org_id)
    return [SyncConfigResponse.from_model(s) for s in syncs]


@router.post("", response_model=SyncConfigResponse, status_code=status.HTTP_201_CREATED)
def create_sync(request: Request, body: CreateSyncRequest, context: OrgCtx):
    """Create a new sync configuration and register it with the scheduler."""
    _validate_cron(body.cron_expression)
    org_id = str(context.organization_id)
    cfg = _store(request).create_sync(
        name=body.name,
        adapter_id=body.adapter_id,
        connector_id=body.connector_id,
        org_id=org_id,
        deployment_id=body.deployment_id,
        cron_expression=body.cron_expression,
        mapping=body.mapping,
        credential_id=body.credential_id,
    )
    if cfg.cron_expression:
        _scheduler(request).add_schedule(cfg)
    return SyncConfigResponse.from_model(cfg)


@router.get("/{sync_id}", response_model=SyncConfigResponse)
def get_sync(request: Request, sync_id: str, context: OrgCtx):
    """Get a single sync configuration by ID."""
    cfg = _get_sync_or_404(request, sync_id)
    _assert_same_org(cfg, context)
    return SyncConfigResponse.from_model(cfg)


@router.put("/{sync_id}", response_model=SyncConfigResponse)
def update_sync(request: Request, sync_id: str, body: UpdateSyncRequest, context: OrgCtx):
    """Update mutable fields of an existing sync configuration."""
    _validate_cron(body.cron_expression)
    cfg = _get_sync_or_404(request, sync_id)
    _assert_same_org(cfg, context)
    updates = body.model_dump(exclude_none=True)
    # Allow explicitly clearing cron_expression to None (manual-only mode)
    if "cron_expression" in body.model_fields_set and body.cron_expression is None:
        updates["cron_expression"] = None
    cfg = _store(request).update_sync(sync_id, **updates)
    # Reschedule whenever cron_expression was included in the request
    if "cron_expression" in body.model_fields_set:
        _scheduler(request).remove_schedule(sync_id)
        if cfg.cron_expression:
            _scheduler(request).add_schedule(cfg)
    return SyncConfigResponse.from_model(cfg)


@router.delete("/{sync_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sync(request: Request, sync_id: str, context: OrgCtx):
    """Permanently delete a sync and remove it from the scheduler."""
    cfg = _get_sync_or_404(request, sync_id)
    _assert_same_org(cfg, context)
    _store(request).delete_sync(sync_id)
    _scheduler(request).remove_schedule(sync_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{sync_id}/runs", response_model=list[SyncRunResponse])
def list_runs(request: Request, sync_id: str, context: OrgCtx, limit: int = 20):
    """List recent runs for a sync."""
    cfg = _get_sync_or_404(request, sync_id)
    _assert_same_org(cfg, context)
    runs = _store(request).list_runs(sync_id, limit=limit)
    return [SyncRunResponse.from_model(r) for r in runs]


@router.get("/{sync_id}/records", response_model=list[SyncRecordResponse])
def list_records(
    request: Request,
    sync_id: str,
    context: OrgCtx,
    record_status: str | None = None,
    limit: int = 100,
):
    """List synced article records for a sync.

    Use ``record_status=active`` or ``record_status=archived`` to filter.
    """
    cfg = _get_sync_or_404(request, sync_id)
    _assert_same_org(cfg, context)
    records = _store(request).list_records(sync_id, status=record_status, limit=limit)
    return [SyncRecordResponse.from_model(r) for r in records]


@router.post("/{sync_id}/trigger", response_model=TriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(request: Request, sync_id: str, context: OrgCtx, force_full: bool = False):
    """Manually trigger an immediate sync run.

    Pass ``?force_full=true`` to bypass the high-water-mark cursor and fetch
    every topic from the source structure (force full resync).
    """
    cfg = _get_sync_or_404(request, sync_id)
    _assert_same_org(cfg, context)
    executor = _executor(request)
    # Fire-and-forget: don't wait for completion
    asyncio.ensure_future(executor.execute(sync_id, force_full=force_full))
    return TriggerResponse(
        sync_id=sync_id,
        message="Full resync triggered." if force_full else "Sync triggered.",
    )
