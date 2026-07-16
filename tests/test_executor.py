"""Tests for SyncExecutorService (TDD step 7).

Uses AsyncMock / MagicMock for all I/O dependencies so the tests run
without a database or network.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from syndication.pipeline.runner import PipelineResult
from syndication.services.sync_executor import SyncExecutorService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_sync_config(**overrides) -> MagicMock:
    cfg = MagicMock()
    cfg.id = "sync-001"
    cfg.name = "Test Sync"
    cfg.adapter_id = "deploy"
    cfg.connector_id = "noop"
    cfg.org_id = "org-abc"
    cfg.deployment_id = "dep-001"
    cfg.is_active = True
    cfg.mapping_json = '{"field": "value"}'
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_state_store(cfg=None) -> MagicMock:
    store = MagicMock()
    cfg = cfg or _make_sync_config()
    store.get_sync = MagicMock(return_value=cfg)
    store.get_high_water_mark = MagicMock(return_value=None)
    store.create_run = MagicMock(return_value=MagicMock(id="run-001"))
    store.complete_run = MagicMock()
    store.fail_run = MagicMock()
    store.set_high_water_mark = MagicMock()
    store.save_article_mapping = MagicMock()
    store.get_target_ids_for_uuids = MagicMock(return_value={})
    store.deactivate_sync = MagicMock()
    return store


def _make_pipeline_result(**overrides) -> PipelineResult:
    base = dict(
        changed_count=2,
        removed_count=0,
        high_water_mark="2026-07-15T10:00:00.000Z",
        links_fixed=1,
        article_mappings={"uuid-a": "target-a", "uuid-b": "target-b"},
    )
    base.update(overrides)
    return PipelineResult(**base)


@pytest.fixture
def mock_settings(mock_settings):
    # Inherit from conftest mock_settings; add executor-specific attrs
    mock_settings.sync_max_consecutive_failures = 3
    return mock_settings


@pytest.fixture
def state_store() -> MagicMock:
    return _make_state_store()


@pytest.fixture
def mock_adapter():
    return MagicMock()


@pytest.fixture
def mock_connector():
    return MagicMock()


@pytest.fixture
def executor(state_store, mock_adapter, mock_connector, mock_settings) -> SyncExecutorService:
    adapter_factory = MagicMock(return_value=mock_adapter)
    connector_factory = MagicMock(return_value=mock_connector)
    return SyncExecutorService(
        state_store=state_store,
        settings=mock_settings,
        adapter_factory=adapter_factory,
        connector_factory=connector_factory,
    )


# ── Successful run ────────────────────────────────────────────────────────────

class TestSuccessfulRun:
    async def test_get_sync_called(self, executor, state_store):
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result())
            await executor.execute("sync-001")

        state_store.get_sync.assert_called_once_with("sync-001")

    async def test_create_run_called(self, executor, state_store):
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result())
            await executor.execute("sync-001")

        state_store.create_run.assert_called_once()
        args = state_store.create_run.call_args
        assert args.kwargs.get("sync_id") == "sync-001" or args.args[0] == "sync-001"

    async def test_pipeline_run_called(self, executor):
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result())
            await executor.execute("sync-001")

        instance.run.assert_awaited_once()

    async def test_pipeline_run_receives_since_from_store(self, executor, state_store):
        state_store.get_high_water_mark.return_value = "2026-07-14T00:00:00.000Z"
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result())
            await executor.execute("sync-001")

        run_call = instance.run.call_args
        # `since` may be positional (args[1]) or keyword
        since = run_call.kwargs.get("since") or (
            run_call.args[1] if len(run_call.args) > 1 else None
        )
        assert since == "2026-07-14T00:00:00.000Z"

    async def test_high_water_mark_persisted(self, executor, state_store):
        result = _make_pipeline_result(high_water_mark="2026-07-15T10:00:00.000Z")
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=result)
            await executor.execute("sync-001")

        state_store.set_high_water_mark.assert_called_once_with(
            "sync-001", "2026-07-15T10:00:00.000Z"
        )

    async def test_article_mappings_persisted(self, executor, state_store):
        result = _make_pipeline_result(
            article_mappings={"uuid-a": "target-a", "uuid-b": "target-b"}
        )
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=result)
            await executor.execute("sync-001")

        assert state_store.save_article_mapping.call_count == 2
        saved = {call.args[1]: call.args[2] for call in state_store.save_article_mapping.call_args_list}
        assert saved == {"uuid-a": "target-a", "uuid-b": "target-b"}

    async def test_complete_run_called_on_success(self, executor, state_store):
        result = _make_pipeline_result(changed_count=5, removed_count=1, links_fixed=3)
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=result)
            await executor.execute("sync-001")

        state_store.complete_run.assert_called_once()
        call_kwargs = state_store.complete_run.call_args
        # check changed_count and removed_count are passed
        assert 5 in call_kwargs.args or call_kwargs.kwargs.get("changed_count") == 5

    async def test_success_resets_consecutive_failures(self, executor, state_store):
        # Simulate a previous failure
        executor._consecutive_failures["sync-001"] = 2

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result())
            await executor.execute("sync-001")

        assert executor._consecutive_failures.get("sync-001", 0) == 0


# ── Concurrent run guard ──────────────────────────────────────────────────────

class TestConcurrentRunGuard:
    async def test_skips_if_already_running(self, executor, state_store):
        executor._running.add("sync-001")
        await executor.execute("sync-001")
        # state_store should not have been touched
        state_store.get_sync.assert_not_called()

    async def test_releases_lock_after_success(self, executor):
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result())
            await executor.execute("sync-001")

        assert "sync-001" not in executor._running

    async def test_releases_lock_after_failure(self, executor, state_store):
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(side_effect=RuntimeError("boom"))
            await executor.execute("sync-001")

        assert "sync-001" not in executor._running


# ── Inactive sync ─────────────────────────────────────────────────────────────

class TestInactiveSync:
    async def test_skips_inactive_sync(self, executor, state_store):
        state_store.get_sync.return_value = _make_sync_config(is_active=False)

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            await executor.execute("sync-001")

        MockPipeline.assert_not_called()

    async def test_skips_nonexistent_sync(self, executor, state_store):
        state_store.get_sync.return_value = None

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            await executor.execute("sync-missing")

        MockPipeline.assert_not_called()


# ── Failure handling ──────────────────────────────────────────────────────────

class TestFailureHandling:
    async def test_fail_run_called_on_exception(self, executor, state_store):
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(side_effect=RuntimeError("Connection refused"))
            await executor.execute("sync-001")

        state_store.fail_run.assert_called_once()
        err_msg = state_store.fail_run.call_args.args[1] if state_store.fail_run.call_args.args else \
                  state_store.fail_run.call_args.kwargs.get("error_message", "")
        assert "Connection refused" in err_msg

    async def test_consecutive_failures_increments(self, executor, state_store):
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(side_effect=RuntimeError("err"))
            await executor.execute("sync-001")

        assert executor._consecutive_failures.get("sync-001", 0) == 1

    async def test_auto_disable_after_max_failures(self, executor, state_store, mock_settings):
        mock_settings.sync_max_consecutive_failures = 3
        executor._consecutive_failures["sync-001"] = 2  # one more will hit max

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(side_effect=RuntimeError("3rd failure"))
            await executor.execute("sync-001")

        state_store.deactivate_sync.assert_called_once_with("sync-001")

    async def test_no_auto_disable_before_max_failures(self, executor, state_store, mock_settings):
        mock_settings.sync_max_consecutive_failures = 3
        executor._consecutive_failures["sync-001"] = 1  # only 2nd failure

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(side_effect=RuntimeError("err"))
            await executor.execute("sync-001")

        state_store.deactivate_sync.assert_not_called()
