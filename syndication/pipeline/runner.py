"""Core sync pipeline: Extract → Map → Load → Archive → Deferred-fixup.

The pipeline is deliberately stateless.  The executor that calls it is
responsible for persisting state (high-water-mark cursor, article mappings,
etc.) between runs.  This separation makes the pipeline easy to unit-test.
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

from syndication.connector.interface import ITargetConnector, UpsertResult
from syndication.ir.types import IRPage
from syndication.source.interface import ISourceAdapter


@dataclass
class PipelineResult:
    """Summary returned by :meth:`SyncPipeline.run` after a sync run."""

    changed_count: int                    # articles upserted (created or updated)
    removed_count: int                    # articles archived
    high_water_mark: str                  # cursor to persist for the next incremental run
    links_fixed: int                      # articles updated by deferred link-fixup pass
    article_mappings: dict[str, str] = dataclasses.field(default_factory=dict)
    # source_uuid → target_article_id; the executor persists these to the state store


class SyncPipeline:
    """Orchestrates a single sync run between one source adapter and one connector.

    Args:
        adapter:   The source adapter providing content (e.g. DeployAdapter).
        connector: The target connector receiving content (e.g. SalesforceConnector).
        mapping:   Connector-specific field-mapping configuration dict.
    """

    def __init__(
        self,
        adapter: ISourceAdapter,
        connector: ITargetConnector,
        mapping: dict,
    ) -> None:
        self._adapter = adapter
        self._connector = connector
        self._mapping = mapping

    async def run(
        self,
        run_id: str,
        since: str | None,
        removed_target_ids: dict[str, str] | None = None,
    ) -> PipelineResult:
        """Execute a complete sync run.

        Args:
            run_id:             Unique identifier for this run (used for logging
                                and deferred link-fixup).
            since:              ISO 8601 cursor for incremental sync; ``None``
                                triggers a full (first-run) sync.
            removed_target_ids: Mapping of ``source_uuid → target_article_id``
                                for articles that the executor knows have been
                                previously synced and must now be archived.
                                Items in the changeset's ``removed_uuids`` that
                                do not appear in this dict are silently skipped.

        Returns:
            :class:`PipelineResult` summarising the run.
        """
        removed_target_ids = removed_target_ids or {}

        # ── Stage 1: Extract ──────────────────────────────────────────────────
        changeset = await self._adapter.get_changed(since=since)

        # ── Stage 2: Fetch pages ──────────────────────────────────────────────
        pages: list[IRPage] = []
        for _uuid, href in changeset.changed:
            page = await self._adapter.get_page(href)
            pages.append(page)

        # ── Stage 3: Map (sanitise HTML) ──────────────────────────────────────
        sanitised_pages: list[IRPage] = []
        for page in pages:
            clean_html = await self._connector.sanitize_html(page.html_body)
            sanitised_pages.append(dataclasses.replace(page, html_body=clean_html))

        # ── Stage 4: Load (upsert + publish) ─────────────────────────────────
        upsert_results: list[UpsertResult] = []
        link_map: dict[str, str] = {}  # source_uuid → target_article_id

        for page in sanitised_pages:
            result = await self._connector.upsert_article(page, self._mapping)
            if not result.update_skipped:
                try:
                    await self._connector.publish_article(result.target_article_id, was_online=result.was_online)
                except Exception as exc:
                    log.warning("publish_article failed for %s: %s", result.target_article_id, exc)
            upsert_results.append(result)
            link_map[page.uuid] = result.target_article_id

        # ── Stage 5: Archive removed articles ────────────────────────────────
        archived_count = 0
        for source_uuid in changeset.removed_uuids:
            target_id = removed_target_ids.get(source_uuid)
            if target_id:
                await self._connector.archive_article(target_id)
                archived_count += 1

        # ── Stage 6: Deferred link fixup ─────────────────────────────────────
        links_fixed = await self._connector.deferred_link_fixup(run_id, link_map)

        return PipelineResult(
            changed_count=len(upsert_results),
            removed_count=archived_count,
            high_water_mark=changeset.high_water_mark,
            links_fixed=links_fixed,
            article_mappings=link_map,
        )
