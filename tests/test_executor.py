"""Tests for SyncExecutorService (TDD step 7).

Uses AsyncMock / MagicMock for all I/O dependencies so the tests run
without a database or network.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from syndication.ir.types import ChangeSet
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
    store.mark_articles_archived = MagicMock()
    store.deactivate_sync = MagicMock()
    return store


def _empty_changeset() -> ChangeSet:
    return ChangeSet(changed=[], removed_uuids=[], high_water_mark="")


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
    adapter = MagicMock()
    adapter.get_changed = AsyncMock(return_value=_empty_changeset())
    return adapter


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


# ── Removed-articles flow ─────────────────────────────────────────────────────

class TestRemovedArticlesFlow:
    async def test_adapter_get_changed_called_before_pipeline(
        self, executor, mock_adapter, state_store
    ):
        """Executor must call adapter.get_changed() to peek at removed UUIDs."""
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(removed_count=0))
            await executor.execute("sync-001")

        mock_adapter.get_changed.assert_awaited_once()

    async def test_removed_uuids_looked_up_in_state_store(
        self, executor, mock_adapter, state_store
    ):
        """Removed UUIDs from the peek changeset must be passed to get_target_ids_for_uuids."""
        mock_adapter.get_changed.return_value = ChangeSet(
            changed=[], removed_uuids=["uuid-gone"], high_water_mark=""
        )
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(removed_count=1))
            await executor.execute("sync-001")

        state_store.get_target_ids_for_uuids.assert_called_once_with(
            "sync-001", ["uuid-gone"]
        )

    async def test_removed_target_ids_passed_to_pipeline(
        self, executor, mock_adapter, state_store
    ):
        """The target IDs resolved from the state store must reach pipeline.run()."""
        mock_adapter.get_changed.return_value = ChangeSet(
            changed=[], removed_uuids=["uuid-gone"], high_water_mark=""
        )
        state_store.get_target_ids_for_uuids.return_value = {"uuid-gone": "sf-art-999"}

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(removed_count=1))
            await executor.execute("sync-001")

        run_call = instance.run.call_args
        removed = run_call.kwargs.get("removed_target_ids") or (
            run_call.args[2] if len(run_call.args) > 2 else None
        )
        assert removed == {"uuid-gone": "sf-art-999"}

    async def test_removed_articles_marked_archived_in_store(
        self, executor, mock_adapter, state_store
    ):
        """After a successful run, removed UUIDs must be marked archived."""
        mock_adapter.get_changed.return_value = ChangeSet(
            changed=[], removed_uuids=["uuid-a", "uuid-b"], high_water_mark=""
        )
        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(removed_count=2))
            await executor.execute("sync-001")

        state_store.mark_articles_archived.assert_called_once_with(
            "sync-001", ["uuid-a", "uuid-b"]
        )

    async def test_no_removals_skips_mark_archived(
        self, executor, mock_adapter, state_store
    ):
        """When there are no removed UUIDs, mark_articles_archived must not be called."""
        mock_adapter.get_changed.return_value = _empty_changeset()

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(removed_count=0))
            await executor.execute("sync-001")

        state_store.mark_articles_archived.assert_not_called()

    async def test_peek_uses_same_since_as_pipeline(
        self, executor, mock_adapter, state_store
    ):
        """The peek call must use the same `since` cursor as the pipeline run."""
        state_store.get_high_water_mark.return_value = "2026-07-15T10:00:00.000Z"

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result())
            await executor.execute("sync-001")

        peek_call = mock_adapter.get_changed.call_args
        since_arg = peek_call.kwargs.get("since") or (
            peek_call.args[0] if peek_call.args else None
        )
        assert since_arg == "2026-07-15T10:00:00.000Z"


# ── Force-full removal flow ───────────────────────────────────────────────────

class TestForceFullRemovals:
    """Force-full runs must archive articles that are no longer in the source."""

    def _stale_record(self, source_uuid="uuid-stale", target_id="sf-stale-999"):
        rec = MagicMock()
        rec.source_uuid = source_uuid
        rec.target_article_id = target_id
        return rec

    async def test_stale_articles_archived_in_connector(
        self, executor, state_store, mock_connector
    ):
        stale = self._stale_record()
        state_store.list_records = MagicMock(return_value=[stale])
        mock_connector.archive_article = AsyncMock()

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(
                article_mappings={"uuid-a": "target-a", "uuid-b": "target-b"},
                removed_count=0,
            ))
            await executor.execute("sync-001", force_full=True)

        mock_connector.archive_article.assert_awaited_once_with("sf-stale-999")

    async def test_stale_articles_marked_archived_in_store(
        self, executor, state_store, mock_connector
    ):
        stale = self._stale_record()
        state_store.list_records = MagicMock(return_value=[stale])
        mock_connector.archive_article = AsyncMock()

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(
                article_mappings={"uuid-a": "target-a"},
                removed_count=0,
            ))
            await executor.execute("sync-001", force_full=True)

        state_store.mark_articles_archived.assert_called_once_with(
            "sync-001", ["uuid-stale"]
        )

    async def test_stale_count_added_to_removed_count(
        self, executor, state_store, mock_connector
    ):
        stale = self._stale_record()
        state_store.list_records = MagicMock(return_value=[stale])
        mock_connector.archive_article = AsyncMock()

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(
                article_mappings={"uuid-a": "target-a"},
                removed_count=0,
            ))
            await executor.execute("sync-001", force_full=True)

        complete_kwargs = state_store.complete_run.call_args.kwargs
        assert complete_kwargs.get("removed_count") == 1

    async def test_current_articles_not_archived(
        self, executor, state_store, mock_connector
    ):
        active = self._stale_record(source_uuid="uuid-a", target_id="target-a")
        state_store.list_records = MagicMock(return_value=[active])
        mock_connector.archive_article = AsyncMock()

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(
                article_mappings={"uuid-a": "target-a"},
                removed_count=0,
            ))
            await executor.execute("sync-001", force_full=True)

        mock_connector.archive_article.assert_not_awaited()
        state_store.mark_articles_archived.assert_not_called()

    async def test_incremental_run_does_not_query_active_records(
        self, executor, state_store
    ):
        state_store.list_records = MagicMock(return_value=[])

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result())
            await executor.execute("sync-001")  # no force_full

        state_store.list_records.assert_not_called()

    async def test_archive_failure_adds_warning_not_fails_run(
        self, executor, state_store, mock_connector
    ):
        """Archive failure on a stale article must surface as a run warning, not a run failure."""
        stale = self._stale_record()
        state_store.list_records = MagicMock(return_value=[stale])
        mock_connector.archive_article = AsyncMock(
            side_effect=RuntimeError("INSUFFICIENT_ACCESS_OR_READONLY")
        )

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(
                article_mappings={"uuid-a": "target-a"},
                removed_count=0,
            ))
            await executor.execute("sync-001", force_full=True)

        # Run must complete, not fail
        state_store.complete_run.assert_called_once()
        state_store.fail_run.assert_not_called()

        # Warning must mention the article ID and instruct manual removal
        warnings_arg = state_store.complete_run.call_args.kwargs.get("warnings")
        assert warnings_arg is not None
        assert len(warnings_arg) == 1
        assert "sf-stale-999" in warnings_arg[0]
        assert "manually" in warnings_arg[0].lower()

    async def test_pipeline_warnings_and_executor_warnings_are_merged(
        self, executor, state_store, mock_connector
    ):
        """Warnings from pipeline result and executor archive failures must both reach complete_run."""
        stale = self._stale_record()
        state_store.list_records = MagicMock(return_value=[stale])
        mock_connector.archive_article = AsyncMock(
            side_effect=RuntimeError("403 Forbidden")
        )

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(
                article_mappings={"uuid-a": "target-a"},
                removed_count=0,
                warnings=["pipeline warning 1"],
            ))
            await executor.execute("sync-001", force_full=True)

        warnings_arg = state_store.complete_run.call_args.kwargs.get("warnings")
        assert warnings_arg is not None
        assert len(warnings_arg) == 2
        assert warnings_arg[0] == "pipeline warning 1"
        assert "sf-stale-999" in warnings_arg[1]

    async def test_no_warnings_passes_none_to_complete_run(
        self, executor, state_store, mock_connector
    ):
        """When there are no warnings at all, complete_run receives warnings=None."""
        stale = self._stale_record()
        state_store.list_records = MagicMock(return_value=[stale])
        mock_connector.archive_article = AsyncMock()  # succeeds

        with patch("syndication.services.sync_executor.SyncPipeline") as MockPipeline:
            instance = MockPipeline.return_value
            instance.run = AsyncMock(return_value=_make_pipeline_result(
                article_mappings={"uuid-a": "target-a"},
                removed_count=0,
                warnings=[],
            ))
            await executor.execute("sync-001", force_full=True)

        warnings_arg = state_store.complete_run.call_args.kwargs.get("warnings")
        assert warnings_arg is None
