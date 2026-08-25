"""Sync executor service.

Responsible for:
  - Concurrent-run guard (one active run per sync_id at a time)
  - Creating the adapter + connector from the sync config
  - Running the SyncPipeline
  - Persisting results (high-water mark, article mappings, run record) to the
    state store
  - Counting consecutive failures and auto-disabling after max failures
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Callable

from syndication.connector.interface import ITargetConnector
from syndication.models import SyncConfig
from syndication.pipeline.runner import SyncPipeline
from syndication.source.interface import ISourceAdapter
from syndication.state_store import SyncStateStore

log = logging.getLogger(__name__)


class SyncExecutorService:
    """Executes a single sync run end-to-end.

    Args:
        state_store:       Persistence layer for sync configs, runs, and mappings.
        settings:          Application settings (for max consecutive failures, etc.).
        adapter_factory:   Callable that builds an ISourceAdapter from a SyncConfig.
        connector_factory: Callable that builds an ITargetConnector from a SyncConfig.
    """

    def __init__(
        self,
        state_store: SyncStateStore,
        settings: object,
        adapter_factory: Callable[[SyncConfig], ISourceAdapter],
        connector_factory: Callable[[SyncConfig], ITargetConnector],
    ) -> None:
        self._store = state_store
        self._settings = settings
        self._adapter_factory = adapter_factory
        self._connector_factory = connector_factory
        self._running: set[str] = set()
        self._consecutive_failures: dict[str, int] = {}

    async def execute(self, sync_id: str, force_full: bool = False) -> None:
        """Execute a sync run for *sync_id*.

        Silently returns if:
          - The sync is already running (concurrent-run guard), or
          - The sync config does not exist or is inactive.

        On exception the run is marked as failed and the consecutive-failure
        counter increments.  After reaching ``settings.sync_max_consecutive_failures``
        the sync is automatically deactivated.

        Args:
            sync_id:    The sync configuration to run.
            force_full: When ``True``, bypass the high-water-mark cursor and
                        fetch every topic from the source structure.  The cursor
                        is not advanced after a forced resync.
        """
        # ── Concurrent-run guard ───────────────────────────────────────────────
        if sync_id in self._running:
            log.debug("Sync %s already running, skipping.", sync_id)
            return

        # ── Load and validate config ───────────────────────────────────────────
        cfg = self._store.get_sync(sync_id)
        if cfg is None or not cfg.is_active:
            log.debug("Sync %s not found or inactive, skipping.", sync_id)
            return

        self._running.add(sync_id)
        run_id = str(uuid.uuid4())
        self._store.create_run(sync_id=sync_id, run_id=run_id)

        try:
            mapping = json.loads(cfg.mapping_json or "{}")
            adapter = self._adapter_factory(cfg)
            connector = self._connector_factory(cfg)
            pipeline = SyncPipeline(adapter=adapter, connector=connector, mapping=mapping)

            if force_full:
                since = None
                removed_target_ids = {}
            else:
                since = self._store.get_high_water_mark(sync_id)
                # Peek at the changeset to resolve removed UUIDs → target article IDs
                # before the pipeline runs. The pipeline calls get_changed() again
                # internally; the duplication is intentional so both layers remain
                # independently testable.
                peek = await adapter.get_changed(since=since)
                removed_target_ids = self._store.get_target_ids_for_uuids(
                    sync_id, peek.removed_uuids
                )

            result = await pipeline.run(
                run_id=run_id,
                since=since,
                removed_target_ids=removed_target_ids,
                force_full=force_full,
            )

            # ── Persist results ────────────────────────────────────────────────
            if result.high_water_mark:
                self._store.set_high_water_mark(sync_id, result.high_water_mark)

            for source_uuid, target_id in result.article_mappings.items():
                self._store.save_article_mapping(sync_id, source_uuid, target_id)

            if not force_full and peek.removed_uuids:
                self._store.mark_articles_archived(sync_id, peek.removed_uuids)

            self._store.complete_run(
                run_id=run_id,
                changed_count=result.changed_count,
                removed_count=result.removed_count,
                links_fixed=result.links_fixed,
                warnings=result.warnings or None,
            )

            # Reset failure counter on success
            self._consecutive_failures[sync_id] = 0

        except Exception as exc:
            error_msg = str(exc)
            log.exception("Sync %s failed: %s", sync_id, error_msg)
            self._store.fail_run(run_id=run_id, error_message=error_msg)

            failures = self._consecutive_failures.get(sync_id, 0) + 1
            self._consecutive_failures[sync_id] = failures

            max_failures = getattr(self._settings, "sync_max_consecutive_failures", 5)
            if failures >= max_failures:
                log.error(
                    "Sync %s reached %d consecutive failures, deactivating.",
                    sync_id,
                    failures,
                )
                self._store.deactivate_sync(sync_id)

        finally:
            self._running.discard(sync_id)
