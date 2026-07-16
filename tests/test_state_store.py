"""Tests for the sync state store (TDD step 6).

Uses real in-memory SQLite so we exercise the full persistence layer.
No HTTP or external services involved.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from syndication.models import Base
from syndication.state_store import SyncStateStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def session_factory():
    """Fresh in-memory SQLite DB for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def store(session_factory) -> SyncStateStore:
    return SyncStateStore(session_factory=session_factory)


# ── SyncConfig CRUD ───────────────────────────────────────────────────────────

class TestSyncConfig:
    def test_create_and_get(self, store: SyncStateStore):
        cfg = store.create_sync(
            name="My Sync",
            adapter_id="deploy",
            connector_id="salesforce",
            org_id="org-abc",
            deployment_id="dep-001",
            cron_expression="0 * * * *",
            mapping={"field": "value"},
        )
        assert cfg.id is not None
        assert cfg.name == "My Sync"
        assert cfg.adapter_id == "deploy"
        assert cfg.connector_id == "salesforce"
        assert cfg.cron_expression == "0 * * * *"
        assert cfg.is_active is True

        fetched = store.get_sync(cfg.id)
        assert fetched is not None
        assert fetched.name == "My Sync"

    def test_get_nonexistent_returns_none(self, store: SyncStateStore):
        assert store.get_sync("does-not-exist") is None

    def test_list_active_syncs(self, store: SyncStateStore):
        store.create_sync("S1", "deploy", "noop", "org", "dep", "0 * * * *")
        store.create_sync("S2", "deploy", "noop", "org", "dep", "0 * * * *")
        syncs = store.list_active_syncs()
        assert len(syncs) == 2

    def test_deactivated_sync_not_in_list(self, store: SyncStateStore):
        cfg = store.create_sync("S1", "deploy", "noop", "org", "dep", "0 * * * *")
        store.deactivate_sync(cfg.id)
        assert store.list_active_syncs() == []


# ── High-water mark ───────────────────────────────────────────────────────────

class TestHighWaterMark:
    def test_initial_high_water_mark_is_none(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        assert store.get_high_water_mark(cfg.id) is None

    def test_set_and_get_high_water_mark(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        hwm = "2026-07-15T10:00:00.000Z"
        store.set_high_water_mark(cfg.id, hwm)
        assert store.get_high_water_mark(cfg.id) == hwm

    def test_update_high_water_mark(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        store.set_high_water_mark(cfg.id, "2026-07-14T00:00:00.000Z")
        store.set_high_water_mark(cfg.id, "2026-07-15T10:00:00.000Z")
        assert store.get_high_water_mark(cfg.id) == "2026-07-15T10:00:00.000Z"


# ── Article mappings ──────────────────────────────────────────────────────────

class TestArticleMappings:
    def test_get_target_id_before_any_save_returns_none(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        assert store.get_target_id(cfg.id, "uuid-x") is None

    def test_save_and_get_target_id(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        store.save_article_mapping(cfg.id, "uuid-a", "target-art-001")
        assert store.get_target_id(cfg.id, "uuid-a") == "target-art-001"

    def test_overwrite_article_mapping(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        store.save_article_mapping(cfg.id, "uuid-a", "old-target")
        store.save_article_mapping(cfg.id, "uuid-a", "new-target")
        assert store.get_target_id(cfg.id, "uuid-a") == "new-target"

    def test_get_target_ids_for_removed(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        store.save_article_mapping(cfg.id, "uuid-1", "target-1")
        store.save_article_mapping(cfg.id, "uuid-2", "target-2")
        store.save_article_mapping(cfg.id, "uuid-3", "target-3")

        removed = ["uuid-1", "uuid-3", "uuid-missing"]
        result = store.get_target_ids_for_uuids(cfg.id, removed)

        assert result == {"uuid-1": "target-1", "uuid-3": "target-3"}
        assert "uuid-missing" not in result

    def test_mappings_isolated_by_sync(self, store: SyncStateStore):
        c1 = store.create_sync("S1", "deploy", "noop", "org", "dep1", "* * * * *")
        c2 = store.create_sync("S2", "deploy", "noop", "org", "dep2", "* * * * *")
        store.save_article_mapping(c1.id, "uuid-a", "target-c1")
        assert store.get_target_id(c2.id, "uuid-a") is None


# ── Sync runs ─────────────────────────────────────────────────────────────────

class TestSyncRuns:
    def test_create_run(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        run = store.create_run(sync_id=cfg.id, run_id="run-001")
        assert run.id == "run-001"
        assert run.sync_id == cfg.id
        assert run.status == "running"
        assert run.started_at is not None
        assert run.completed_at is None

    def test_complete_run(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        store.create_run(cfg.id, "run-001")
        store.complete_run("run-001", changed_count=5, removed_count=1)

        run = store.get_run("run-001")
        assert run.status == "success"
        assert run.changed_count == 5
        assert run.removed_count == 1
        assert run.completed_at is not None

    def test_fail_run(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        store.create_run(cfg.id, "run-001")
        store.fail_run("run-001", error_message="Connection timeout")

        run = store.get_run("run-001")
        assert run.status == "failed"
        assert run.error_message == "Connection timeout"
        assert run.completed_at is not None

    def test_list_recent_runs(self, store: SyncStateStore):
        cfg = store.create_sync("S", "deploy", "noop", "org", "dep", "* * * * *")
        store.create_run(cfg.id, "run-001")
        store.create_run(cfg.id, "run-002")
        store.complete_run("run-001", 3, 0)

        runs = store.list_runs(cfg.id, limit=10)
        assert len(runs) == 2
        run_ids = {r.id for r in runs}
        assert "run-001" in run_ids
        assert "run-002" in run_ids
