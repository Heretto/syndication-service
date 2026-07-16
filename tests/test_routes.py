"""Tests for the API routes (TDD step 9).

Uses FastAPI TestClient with all services mocked so no DB or network required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from syndication.routes.syncs import router as syncs_router


# ── Minimal test app ──────────────────────────────────────────────────────────
# We mount only the routes under test; no hop-core auth middleware required.

def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(syncs_router)
    return app


def _make_sync_cfg(**overrides) -> MagicMock:
    cfg = MagicMock()
    cfg.id = "sync-001"
    cfg.name = "My Sync"
    cfg.adapter_id = "deploy"
    cfg.connector_id = "salesforce"
    cfg.org_id = "org-abc"
    cfg.deployment_id = "dep-001"
    cfg.cron_expression = "0 * * * *"
    cfg.is_active = True
    cfg.high_water_mark = None
    cfg.mapping_json = "{}"
    cfg.created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_run(**overrides) -> MagicMock:
    run = MagicMock()
    run.id = "run-001"
    run.sync_id = "sync-001"
    run.status = "success"
    run.started_at = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    run.completed_at = datetime(2026, 7, 15, 10, 5, tzinfo=timezone.utc)
    run.changed_count = 42
    run.removed_count = 3
    run.links_fixed = 10
    run.error_message = None
    for k, v in overrides.items():
        setattr(run, k, v)
    return run


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.list_active_syncs = MagicMock(return_value=[_make_sync_cfg()])
    store.get_sync = MagicMock(return_value=_make_sync_cfg())
    store.create_sync = MagicMock(return_value=_make_sync_cfg())
    store.deactivate_sync = MagicMock()
    store.list_runs = MagicMock(return_value=[_make_run()])
    return store


@pytest.fixture
def mock_scheduler():
    sched = MagicMock()
    sched.add_schedule = MagicMock()
    sched.remove_schedule = MagicMock()
    sched.is_active = MagicMock(return_value=True)
    sched.next_run_time = MagicMock(return_value=None)
    return sched


@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.execute = AsyncMock()
    return executor


@pytest.fixture
def client(mock_store, mock_scheduler, mock_executor) -> TestClient:
    app = _make_app()
    # Inject dependencies via app.state (routes access via request.app.state)
    app.state.store = mock_store
    app.state.scheduler = mock_scheduler
    app.state.executor = mock_executor
    return TestClient(app)


# ── GET /syncs ────────────────────────────────────────────────────────────────

class TestListSyncs:
    def test_returns_200(self, client):
        resp = client.get("/syncs")
        assert resp.status_code == 200

    def test_returns_list(self, client, mock_store):
        mock_store.list_active_syncs.return_value = [_make_sync_cfg(id="s1"), _make_sync_cfg(id="s2")]
        resp = client.get("/syncs")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_each_item_has_id_and_name(self, client):
        resp = client.get("/syncs")
        item = resp.json()[0]
        assert "id" in item
        assert "name" in item


# ── POST /syncs ───────────────────────────────────────────────────────────────

class TestCreateSync:
    def _payload(self, **overrides) -> dict:
        base = {
            "name": "New Sync",
            "adapter_id": "deploy",
            "connector_id": "salesforce",
            "org_id": "org-abc",
            "deployment_id": "dep-001",
            "cron_expression": "0 * * * *",
            "mapping": {},
        }
        base.update(overrides)
        return base

    def test_returns_201(self, client):
        resp = client.post("/syncs", json=self._payload())
        assert resp.status_code == 201

    def test_store_create_sync_called(self, client, mock_store):
        client.post("/syncs", json=self._payload(name="My New Sync"))
        mock_store.create_sync.assert_called_once()
        kwargs = mock_store.create_sync.call_args.kwargs
        assert kwargs.get("name") == "My New Sync"

    def test_scheduler_add_schedule_called(self, client, mock_scheduler):
        client.post("/syncs", json=self._payload())
        mock_scheduler.add_schedule.assert_called_once()

    def test_response_has_id(self, client):
        resp = client.post("/syncs", json=self._payload())
        assert "id" in resp.json()

    def test_missing_name_returns_422(self, client):
        payload = self._payload()
        del payload["name"]
        resp = client.post("/syncs", json=payload)
        assert resp.status_code == 422


# ── GET /syncs/{sync_id} ──────────────────────────────────────────────────────

class TestGetSync:
    def test_returns_200(self, client):
        resp = client.get("/syncs/sync-001")
        assert resp.status_code == 200

    def test_returns_correct_id(self, client):
        resp = client.get("/syncs/sync-001")
        assert resp.json()["id"] == "sync-001"

    def test_not_found_returns_404(self, client, mock_store):
        mock_store.get_sync.return_value = None
        resp = client.get("/syncs/missing")
        assert resp.status_code == 404


# ── DELETE /syncs/{sync_id} ───────────────────────────────────────────────────

class TestDeactivateSync:
    def test_returns_204(self, client):
        resp = client.delete("/syncs/sync-001")
        assert resp.status_code == 204

    def test_store_deactivate_called(self, client, mock_store):
        client.delete("/syncs/sync-001")
        mock_store.deactivate_sync.assert_called_once_with("sync-001")

    def test_scheduler_remove_called(self, client, mock_scheduler):
        client.delete("/syncs/sync-001")
        mock_scheduler.remove_schedule.assert_called_once_with("sync-001")

    def test_not_found_returns_404(self, client, mock_store):
        mock_store.get_sync.return_value = None
        resp = client.delete("/syncs/missing")
        assert resp.status_code == 404


# ── GET /syncs/{sync_id}/runs ─────────────────────────────────────────────────

class TestListRuns:
    def test_returns_200(self, client):
        resp = client.get("/syncs/sync-001/runs")
        assert resp.status_code == 200

    def test_returns_list_of_runs(self, client):
        resp = client.get("/syncs/sync-001/runs")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "run-001"

    def test_sync_not_found_returns_404(self, client, mock_store):
        mock_store.get_sync.return_value = None
        resp = client.get("/syncs/missing/runs")
        assert resp.status_code == 404


# ── POST /syncs/{sync_id}/trigger ─────────────────────────────────────────────

class TestTrigger:
    def test_returns_202(self, client):
        resp = client.post("/syncs/sync-001/trigger")
        assert resp.status_code == 202

    def test_executor_execute_called(self, client, mock_executor):
        client.post("/syncs/sync-001/trigger")
        mock_executor.execute.assert_awaited_once_with("sync-001")

    def test_not_found_returns_404(self, client, mock_store):
        mock_store.get_sync.return_value = None
        resp = client.post("/syncs/missing/trigger")
        assert resp.status_code == 404

    def test_response_contains_run_info(self, client):
        resp = client.post("/syncs/sync-001/trigger")
        body = resp.json()
        assert "sync_id" in body
        assert body["sync_id"] == "sync-001"
