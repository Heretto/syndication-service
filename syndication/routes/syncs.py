"""API routes for sync configuration management.

All routes are mounted under ``/syncs`` via :data:`router`.
Services are read from ``request.app.state`` (set during lifespan in main.py).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

router = APIRouter(prefix="/syncs", tags=["syncs"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CreateSyncRequest(BaseModel):
    name: str
    adapter_id: str
    connector_id: str
    org_id: str
    deployment_id: str
    cron_expression: str
    mapping: dict[str, Any] = {}


class SyncConfigResponse(BaseModel):
    id: str
    name: str
    adapter_id: str
    connector_id: str
    org_id: str
    deployment_id: str | None
    cron_expression: str
    is_active: bool
    high_water_mark: str | None
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

    @classmethod
    def from_model(cls, run: Any) -> "SyncRunResponse":
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
        )


class TriggerResponse(BaseModel):
    sync_id: str
    message: str


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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SyncConfigResponse])
def list_syncs(request: Request):
    """List all active sync configurations."""
    syncs = _store(request).list_active_syncs()
    return [SyncConfigResponse.from_model(s) for s in syncs]


@router.post("", response_model=SyncConfigResponse, status_code=status.HTTP_201_CREATED)
def create_sync(request: Request, body: CreateSyncRequest):
    """Create a new sync configuration and register it with the scheduler."""
    cfg = _store(request).create_sync(
        name=body.name,
        adapter_id=body.adapter_id,
        connector_id=body.connector_id,
        org_id=body.org_id,
        deployment_id=body.deployment_id,
        cron_expression=body.cron_expression,
        mapping=body.mapping,
    )
    _scheduler(request).add_schedule(cfg)
    return SyncConfigResponse.from_model(cfg)


@router.get("/{sync_id}", response_model=SyncConfigResponse)
def get_sync(request: Request, sync_id: str):
    """Get a single sync configuration by ID."""
    cfg = _get_sync_or_404(request, sync_id)
    return SyncConfigResponse.from_model(cfg)


@router.delete("/{sync_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_sync(request: Request, sync_id: str):
    """Deactivate a sync and remove it from the scheduler."""
    _get_sync_or_404(request, sync_id)
    _store(request).deactivate_sync(sync_id)
    _scheduler(request).remove_schedule(sync_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{sync_id}/runs", response_model=list[SyncRunResponse])
def list_runs(request: Request, sync_id: str, limit: int = 20):
    """List recent runs for a sync."""
    _get_sync_or_404(request, sync_id)
    runs = _store(request).list_runs(sync_id, limit=limit)
    return [SyncRunResponse.from_model(r) for r in runs]


@router.post("/{sync_id}/trigger", response_model=TriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(request: Request, sync_id: str):
    """Manually trigger an immediate sync run."""
    _get_sync_or_404(request, sync_id)
    executor = _executor(request)
    # Fire-and-forget: don't wait for completion
    asyncio.ensure_future(executor.execute(sync_id))
    return TriggerResponse(sync_id=sync_id, message="Sync triggered.")
