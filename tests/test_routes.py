"""Tests for the API routes.

Uses FastAPI TestClient with all services mocked so no DB or network required.
Auth dependency is overridden with a mock context so tests don't need a real JWT.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from syndication.routes.syncs import router as syncs_router

# Consistent org UUID used across all fixtures
ORG_UUID = uuid.UUID("00000000-0000-0000-0000-000000000abc")
ORG_ID = str(ORG_UUID)


# ── Minimal test app ──────────────────────────────────────────────────────────

def _make_mock_context() -> CurrentUserContext:
    ctx = MagicMock(spec=CurrentUserContext)
    ctx.organization_id = ORG_UUID
    return ctx


def _make_app(auth: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(syncs_router)
    if auth:
        # Override auth so tests don't need a real JWT
        app.dependency_overrides[get_current_active_user_with_org] = _make_mock_context
    return app


def _make_sync_cfg(**overrides) -> MagicMock:
    cfg = MagicMock()
    cfg.id = "sync-001"
    cfg.name = "My Sync"
    cfg.adapter_id = "deploy"
    cfg.connector_id = "salesforce"
    cfg.org_id = ORG_ID
    cfg.deployment_id = "dep-001"
    cfg.cron_expression = "0 * * * *"
    cfg.is_active = True
    cfg.high_water_mark = None
    cfg.credential_id = None
    cfg.mapping = {}
    cfg.mapping_json = "{}"
    cfg.created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_record(**overrides) -> MagicMock:
    rec = MagicMock()
    rec.id = "rec-001"
    rec.sync_id = "sync-001"
    rec.source_uuid = "uuid-aaa"
    rec.target_article_id = "sf-art-001"
    rec.status = "active"
    rec.last_synced_at = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    for k, v in overrides.items():
        setattr(rec, k, v)
    return rec


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
    store.update_sync = MagicMock(return_value=_make_sync_cfg())
    store.deactivate_sync = MagicMock()
    store.list_runs = MagicMock(return_value=[_make_run()])
    store.list_records = MagicMock(return_value=[_make_record()])
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
    app = _make_app(auth=True)
    app.state.store = mock_store
    app.state.scheduler = mock_scheduler
    app.state.executor = mock_executor
    return TestClient(app)


# ── Auth: unauthenticated requests should be rejected ─────────────────────────

class TestAuth:
    def test_unauthenticated_list_returns_401(self, mock_store, mock_scheduler, mock_executor):
        from hop_core.db import get_db

        app = _make_app(auth=False)
        # Override get_db so hop-core's dependency chain doesn't 500 before
        # the missing-token 401 is raised.
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.state.store = mock_store
        app.state.scheduler = mock_scheduler
        app.state.executor = mock_executor
        unauth_client = TestClient(app, raise_server_exceptions=False)
        resp = unauth_client.get("/syncs")
        assert resp.status_code == 401


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

    def test_list_filtered_by_org_id(self, client, mock_store):
        client.get("/syncs")
        call_kwargs = mock_store.list_active_syncs.call_args
        assert call_kwargs.kwargs.get("org_id") == ORG_ID

    def test_response_includes_mapping(self, client):
        resp = client.get("/syncs")
        item = resp.json()[0]
        assert "mapping" in item


# ── POST /syncs ───────────────────────────────────────────────────────────────

class TestCreateSync:
    def _payload(self, **overrides) -> dict:
        base = {
            "name": "New Sync",
            "adapter_id": "deploy",
            "connector_id": "salesforce",
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

    def test_create_derives_org_id_from_jwt(self, client, mock_store):
        client.post("/syncs", json=self._payload())
        kwargs = mock_store.create_sync.call_args.kwargs
        assert kwargs.get("org_id") == ORG_ID

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

    def test_wrong_org_returns_403(self, client, mock_store):
        mock_store.get_sync.return_value = _make_sync_cfg(org_id="other-org-id")
        resp = client.get("/syncs/sync-001")
        assert resp.status_code == 403


# ── PUT /syncs/{sync_id} ──────────────────────────────────────────────────────

class TestUpdateSync:
    def _payload(self, **overrides) -> dict:
        base = {"name": "Updated Name"}
        base.update(overrides)
        return base

    def test_returns_200(self, client):
        resp = client.put("/syncs/sync-001", json=self._payload())
        assert resp.status_code == 200

    def test_store_update_sync_called(self, client, mock_store):
        client.put("/syncs/sync-001", json=self._payload(name="New Name"))
        mock_store.update_sync.assert_called_once()
        call_args = mock_store.update_sync.call_args
        assert call_args.args[0] == "sync-001" or call_args.kwargs.get("sync_id") == "sync-001"

    def test_not_found_returns_404(self, client, mock_store):
        mock_store.get_sync.return_value = None
        resp = client.put("/syncs/missing", json=self._payload())
        assert resp.status_code == 404

    def test_wrong_org_returns_403(self, client, mock_store):
        mock_store.get_sync.return_value = _make_sync_cfg(org_id="other-org-id")
        resp = client.put("/syncs/sync-001", json=self._payload())
        assert resp.status_code == 403

    def test_cron_change_reschedules(self, client, mock_scheduler):
        client.put("/syncs/sync-001", json={"cron_expression": "0 0 * * *"})
        mock_scheduler.remove_schedule.assert_called_once_with("sync-001")
        mock_scheduler.add_schedule.assert_called_once()

    def test_no_cron_change_does_not_reschedule(self, client, mock_scheduler):
        client.put("/syncs/sync-001", json={"name": "New Name"})
        mock_scheduler.remove_schedule.assert_not_called()

    def test_response_includes_mapping(self, client):
        resp = client.put("/syncs/sync-001", json=self._payload())
        assert "mapping" in resp.json()


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

    def test_wrong_org_returns_403(self, client, mock_store):
        mock_store.get_sync.return_value = _make_sync_cfg(org_id="other-org-id")
        resp = client.delete("/syncs/sync-001")
        assert resp.status_code == 403


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

    def test_wrong_org_returns_403(self, client, mock_store):
        mock_store.get_sync.return_value = _make_sync_cfg(org_id="other-org-id")
        resp = client.get("/syncs/sync-001/runs")
        assert resp.status_code == 403


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

    def test_wrong_org_returns_403(self, client, mock_store):
        mock_store.get_sync.return_value = _make_sync_cfg(org_id="other-org-id")
        resp = client.post("/syncs/sync-001/trigger")
        assert resp.status_code == 403

    def test_response_contains_run_info(self, client):
        resp = client.post("/syncs/sync-001/trigger")
        body = resp.json()
        assert "sync_id" in body
        assert body["sync_id"] == "sync-001"


# ── GET /syncs/{sync_id}/records ──────────────────────────────────────────────

class TestListRecords:
    def test_returns_200(self, client):
        resp = client.get("/syncs/sync-001/records")
        assert resp.status_code == 200

    def test_returns_list_of_records(self, client):
        resp = client.get("/syncs/sync-001/records")
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_record_fields_present(self, client):
        resp = client.get("/syncs/sync-001/records")
        rec = resp.json()[0]
        assert rec["source_uuid"] == "uuid-aaa"
        assert rec["target_article_id"] == "sf-art-001"
        assert rec["status"] == "active"
        assert "last_synced_at" in rec

    def test_status_filter_passed_to_store(self, client, mock_store):
        client.get("/syncs/sync-001/records?record_status=archived")
        call_kwargs = mock_store.list_records.call_args.kwargs
        assert call_kwargs.get("status") == "archived"

    def test_no_status_filter_passes_none(self, client, mock_store):
        client.get("/syncs/sync-001/records")
        call_kwargs = mock_store.list_records.call_args.kwargs
        assert call_kwargs.get("status") is None

    def test_limit_param_passed_to_store(self, client, mock_store):
        client.get("/syncs/sync-001/records?limit=25")
        call_kwargs = mock_store.list_records.call_args.kwargs
        assert call_kwargs.get("limit") == 25

    def test_sync_not_found_returns_404(self, client, mock_store):
        mock_store.get_sync.return_value = None
        resp = client.get("/syncs/missing/records")
        assert resp.status_code == 404

    def test_wrong_org_returns_403(self, client, mock_store):
        mock_store.get_sync.return_value = _make_sync_cfg(org_id="other-org-id")
        resp = client.get("/syncs/sync-001/records")
        assert resp.status_code == 403

    def test_empty_records_returns_empty_list(self, client, mock_store):
        mock_store.list_records.return_value = []
        resp = client.get("/syncs/sync-001/records")
        assert resp.json() == []
