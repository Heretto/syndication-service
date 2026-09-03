"""Tests for SyncSchedulerService (TDD step 8).

The APScheduler instance is fully mocked so tests run without timing.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone

import pytest

from syndication.services.scheduler import SyncSchedulerService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_sync(**overrides) -> MagicMock:
    s = MagicMock()
    s.id = "sync-001"
    s.cron_expression = "0 * * * *"
    s.is_active = True
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


@pytest.fixture
def mock_apscheduler():
    sched = MagicMock()
    sched.get_job = MagicMock(return_value=None)
    sched.add_job = MagicMock()
    sched.remove_job = MagicMock()
    sched.get_jobs = MagicMock(return_value=[])
    sched.start = MagicMock()
    sched.shutdown = MagicMock()
    return sched


@pytest.fixture
def mock_state_store():
    store = MagicMock()
    store.list_active_syncs = MagicMock(return_value=[])
    return store


@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.execute = AsyncMock()
    return executor


@pytest.fixture
def scheduler(mock_state_store, mock_executor, mock_apscheduler) -> SyncSchedulerService:
    with patch(
        "syndication.services.scheduler.AsyncIOScheduler",
        return_value=mock_apscheduler,
    ):
        svc = SyncSchedulerService(
            state_store=mock_state_store,
            executor=mock_executor,
        )
    svc._scheduler = mock_apscheduler
    return svc


# ── Job ID convention ─────────────────────────────────────────────────────────

class TestJobIdConvention:
    def test_job_id_format(self):
        assert SyncSchedulerService.job_id("sync-001") == "sync:sync-001"

    def test_job_id_different_sync(self):
        assert SyncSchedulerService.job_id("abc-123") == "sync:abc-123"


# ── add_schedule ──────────────────────────────────────────────────────────────

class TestAddSchedule:
    def test_add_job_called(self, scheduler, mock_apscheduler):
        sync = _make_sync()
        scheduler.add_schedule(sync)
        mock_apscheduler.add_job.assert_called_once()

    def test_add_job_id(self, scheduler, mock_apscheduler):
        sync = _make_sync(id="sync-xyz", cron_expression="30 6 * * *")
        scheduler.add_schedule(sync)
        kwargs = mock_apscheduler.add_job.call_args.kwargs
        assert kwargs.get("id") == "sync:sync-xyz"

    def test_replace_existing_on_add(self, scheduler, mock_apscheduler):
        sync = _make_sync()
        scheduler.add_schedule(sync)
        kwargs = mock_apscheduler.add_job.call_args.kwargs
        assert kwargs.get("replace_existing") is True

    def test_cron_trigger_used(self, scheduler, mock_apscheduler):
        with patch("syndication.services.scheduler.CronTrigger") as MockCron:
            MockCron.from_crontab.return_value = MagicMock()
            sync = _make_sync(cron_expression="0 12 * * *")
            scheduler.add_schedule(sync)

        MockCron.from_crontab.assert_called_once_with("0 12 * * *")


# ── remove_schedule ───────────────────────────────────────────────────────────

class TestRemoveSchedule:
    def test_remove_job_called(self, scheduler, mock_apscheduler):
        mock_apscheduler.get_job.return_value = MagicMock()  # job exists
        scheduler.remove_schedule("sync-001")
        mock_apscheduler.remove_job.assert_called_once_with("sync:sync-001")

    def test_remove_nonexistent_job_is_noop(self, scheduler, mock_apscheduler):
        mock_apscheduler.get_job.return_value = None  # job does not exist
        scheduler.remove_schedule("sync-001")  # should not raise
        mock_apscheduler.remove_job.assert_not_called()


# ── is_active / active_count ──────────────────────────────────────────────────

class TestActiveState:
    def test_is_active_true_when_job_exists(self, scheduler, mock_apscheduler):
        mock_apscheduler.get_job.return_value = MagicMock()
        assert scheduler.is_active("sync-001") is True

    def test_is_active_false_when_no_job(self, scheduler, mock_apscheduler):
        mock_apscheduler.get_job.return_value = None
        assert scheduler.is_active("sync-001") is False

    def test_active_count_delegates_to_get_jobs(self, scheduler, mock_apscheduler):
        mock_apscheduler.get_jobs.return_value = [MagicMock(), MagicMock()]
        assert scheduler.active_count() == 2


# ── next_run_time ─────────────────────────────────────────────────────────────

class TestNextRunTime:
    def test_returns_datetime_when_job_exists(self, scheduler, mock_apscheduler):
        now = datetime.now(timezone.utc)
        job = MagicMock()
        job.next_run_time = now
        mock_apscheduler.get_job.return_value = job
        assert scheduler.next_run_time("sync-001") == now

    def test_returns_none_when_no_job(self, scheduler, mock_apscheduler):
        mock_apscheduler.get_job.return_value = None
        assert scheduler.next_run_time("sync-001") is None


# ── load_all ──────────────────────────────────────────────────────────────────

class TestLoadAll:
    def test_adds_job_for_each_active_sync(self, scheduler, mock_state_store, mock_apscheduler):
        syncs = [_make_sync(id="s1"), _make_sync(id="s2")]
        mock_state_store.list_active_syncs.return_value = syncs

        scheduler.load_all()

        assert mock_apscheduler.add_job.call_count == 2

    def test_load_all_with_no_syncs(self, scheduler, mock_state_store, mock_apscheduler):
        mock_state_store.list_active_syncs.return_value = []
        scheduler.load_all()
        mock_apscheduler.add_job.assert_not_called()

    def test_load_all_skips_invalid_cron_and_schedules_valid(
        self, scheduler, mock_state_store, mock_apscheduler
    ):
        bad = _make_sync(id="s-bad", cron_expression="not-a-cron")
        good = _make_sync(id="s-good", cron_expression="0 9 * * *")
        mock_state_store.list_active_syncs.return_value = [bad, good]

        scheduler.load_all()  # must not raise

        # Only the valid sync gets scheduled
        assert mock_apscheduler.add_job.call_count == 1
        scheduled_id = mock_apscheduler.add_job.call_args.kwargs.get("id")
        assert scheduled_id == "sync:s-good"
