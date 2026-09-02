"""Scheduler service wrapping APScheduler.

Manages cron-based triggers for sync runs.  One APScheduler job per active
SyncConfig, with job IDs in the form ``"sync:{sync_id}"``.

Lifecycle (called from the app lifespan in main.py):
    scheduler.start()
    scheduler.load_all()   # register all active syncs
    yield                  # app serves requests
    scheduler.shutdown()
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from syndication.services.sync_executor import SyncExecutorService
    from syndication.state_store import SyncStateStore
    from syndication.models import SyncConfig

log = logging.getLogger(__name__)


class SyncSchedulerService:
    """Wraps APScheduler to manage cron-based sync schedules.

    Args:
        state_store: Used by :meth:`load_all` to enumerate active syncs.
        executor:    The executor whose :meth:`~SyncExecutorService.execute`
                     is registered as the job function.
    """

    def __init__(
        self,
        state_store: "SyncStateStore",
        executor: "SyncExecutorService",
    ) -> None:
        self._store = state_store
        self._executor = executor
        self._scheduler = AsyncIOScheduler()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the underlying APScheduler."""
        self._scheduler.start()

    def shutdown(self) -> None:
        """Shut down APScheduler, waiting for running jobs to finish."""
        self._scheduler.shutdown()

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def job_id(sync_id: str) -> str:
        """Return the APScheduler job ID for a given *sync_id*."""
        return f"sync:{sync_id}"

    # ── Schedule management ───────────────────────────────────────────────────

    def add_schedule(self, sync: "SyncConfig") -> None:
        """Register (or replace) a cron job for *sync*.

        Uses ``replace_existing=True`` so re-calling on the same sync
        safely updates the cron expression without raising a duplicate error.
        No-ops for manual-only syncs (``cron_expression`` is None or empty).
        """
        if not sync.cron_expression:
            return
        trigger = CronTrigger.from_crontab(sync.cron_expression)
        self._scheduler.add_job(
            self._executor.execute,
            trigger=trigger,
            args=[sync.id],
            id=self.job_id(sync.id),
            replace_existing=True,
            name=getattr(sync, "name", sync.id),
        )
        log.info("Scheduled sync %s with cron %r", sync.id, sync.cron_expression)

    def remove_schedule(self, sync_id: str) -> None:
        """Remove the cron job for *sync_id* if it exists."""
        job_id = self.job_id(sync_id)
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)
            log.info("Removed schedule for sync %s", sync_id)

    def load_all(self) -> None:
        """Load and schedule all active syncs from the state store.

        Called once at startup after ``start()``.
        """
        syncs = self._store.list_active_syncs()
        for sync in syncs:
            self.add_schedule(sync)
        log.info("Loaded %d active sync schedule(s).", len(syncs))

    # ── Inspection ────────────────────────────────────────────────────────────

    def is_active(self, sync_id: str) -> bool:
        """Return ``True`` if a job is currently scheduled for *sync_id*."""
        return self._scheduler.get_job(self.job_id(sync_id)) is not None

    def active_count(self) -> int:
        """Return the total number of scheduled sync jobs."""
        return len(self._scheduler.get_jobs())

    def next_run_time(self, sync_id: str) -> datetime | None:
        """Return the next scheduled run time for *sync_id*, or ``None``."""
        job = self._scheduler.get_job(self.job_id(sync_id))
        return job.next_run_time if job is not None else None
