"""Core sync pipeline: Extract → Map → Load → Archive → Deferred-fixup.

The pipeline is deliberately stateless.  The executor that calls it is
responsible for persisting state (high-water-mark cursor, article mappings,
etc.) between runs.  This separation makes the pipeline easy to unit-test.
"""
from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass

from lxml import html as lhtml

log = logging.getLogger(__name__)


def _extract_img_srcs(html: str) -> list[str]:
    """Return all unique <img src> URLs found in *html*."""
    if not html:
        return []
    doc = lhtml.fromstring(f"<div>{html}</div>")
    seen: list[str] = []
    for img in doc.iter("img"):
        src = img.get("src", "")
        if src and src not in seen:
            seen.append(src)
    return seen


def _rewrite_img_srcs(html: str, url_map: dict[str, str]) -> str:
    """Replace <img src> values according to *url_map*."""
    if not html or not url_map:
        return html
    doc = lhtml.fromstring(f"<div>{html}</div>")
    for img in doc.iter("img"):
        src = img.get("src", "")
        if src in url_map:
            img.set("src", url_map[src])
    return (doc.text or "") + "".join(
        lhtml.tostring(child, encoding="unicode") for child in doc
    )


def _object_uuid_from_url(url: str) -> str:
    """Extract the object UUID from a Deploy API object URL."""
    m = re.search(r"/object/([^/?]+)", url)
    return m.group(1) if m else url.split("/")[-1].split("?")[0]


_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}

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
    warnings: list[str] = dataclasses.field(default_factory=list)
    # non-fatal errors collected during the run (e.g. category sync failures)


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
        auto_publish: bool = True,
    ) -> None:
        self._adapter = adapter
        self._connector = connector
        self._mapping = mapping
        self._auto_publish = auto_publish

    async def run(
        self,
        run_id: str,
        since: str | None,
        removed_target_ids: dict[str, str] | None = None,
        force_full: bool = False,
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
            force_full:         When ``True`` bypasses ``changed_content`` and
                                fetches every topic from the source structure,
                                ignoring the high-water-mark cursor.

        Returns:
            :class:`PipelineResult` summarising the run.
        """
        removed_target_ids = removed_target_ids or {}

        # ── Stage 1: Extract ──────────────────────────────────────────────────
        if force_full:
            log.info("Force full resync requested for run %s — walking structure.", run_id)
            changeset = await self._adapter.get_all_from_structure()
        else:
            changeset = await self._adapter.get_changed(since=since)

        # ── Stage 2: Fetch pages ──────────────────────────────────────────────
        structure_entries = getattr(changeset, 'entries', {})
        pages: list[IRPage] = []
        for uuid, href in changeset.changed:
            page = await self._adapter.get_page(href)
            entry = structure_entries.get(uuid)
            if entry is not None:
                page = dataclasses.replace(
                    page,
                    section_path=entry.section_path,
                    sort_order=entry.sort_order,
                    sibling_uuids=entry.sibling_uuids,
                )
            pages.append(page)

        # ── Stage 3: Map (sanitise HTML) ──────────────────────────────────────
        sanitised_pages: list[IRPage] = []
        for page in pages:
            clean_html = await self._connector.sanitize_html(page.html_body)
            sanitised_pages.append(dataclasses.replace(page, html_body=clean_html))

        # ── Stage 3.5: Upload binary assets and rewrite <img src> ────────────
        ready_pages: list[IRPage] = []
        for page in sanitised_pages:
            img_srcs = _extract_img_srcs(page.html_body)
            url_map: dict[str, str] = {}
            for src in img_srcs:
                obj_uuid = _object_uuid_from_url(src)
                try:
                    content, mime_type = await self._adapter.fetch_binary(src)
                    ext = _MIME_TO_EXT.get(mime_type, ".bin")
                    sf_url = await self._connector.upload_binary(
                        obj_uuid, content, mime_type, f"{obj_uuid}{ext}"
                    )
                    url_map[src] = sf_url
                    log.info("Uploaded binary %s → %s", obj_uuid, sf_url)
                except Exception as exc:
                    log.warning("Failed to upload binary %s: %s", src[:80], exc)
            if url_map:
                page = dataclasses.replace(
                    page, html_body=_rewrite_img_srcs(page.html_body, url_map)
                )
            ready_pages.append(page)

        # ── Stage 4: Load (upsert + publish) ─────────────────────────────────
        upsert_results: list[UpsertResult] = []
        link_map: dict[str, str] = {}  # source_uuid → target_article_id
        run_warnings: list[str] = []

        category_map: dict = self._mapping.get("category_map", {})
        field_map = {k: v for k, v in self._mapping.items() if k != "category_map"}

        for page in ready_pages:
            result = await self._connector.upsert_article(page, field_map)
            # Always sync categories — they are independent of the draft/publish
            # cycle and can be applied to Published articles directly.
            try:
                await self._connector.sync_data_categories(
                    result.target_article_id, page.taxonomy, category_map
                )
            except Exception as exc:
                msg = f"Category sync failed for {result.target_article_id}: {exc}"
                log.warning(msg)
                run_warnings.append(msg)
            if not result.update_skipped and self._auto_publish:
                try:
                    await self._connector.publish_article(result.target_article_id, was_online=result.was_online)
                except Exception as exc:
                    msg = f"Publish failed for {result.target_article_id}: {exc}"
                    log.warning(msg)
                    run_warnings.append(msg)
            upsert_results.append(result)
            link_map[page.uuid] = result.target_article_id

        # ── Stage 4.5: Deferred sibling relationship pass (force_full only) ──
        if structure_entries:
            for page in ready_pages:
                if not page.sibling_uuids:
                    continue
                resolved = [link_map[u] for u in page.sibling_uuids if u in link_map]
                if not resolved:
                    continue
                article_id = link_map.get(page.uuid)
                if not article_id:
                    continue
                try:
                    await self._connector.sync_sibling_relationships(article_id, resolved)
                except Exception as exc:
                    log.warning("Sibling relationship sync failed for %s: %s", article_id, exc)

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
            warnings=run_warnings,
        )
