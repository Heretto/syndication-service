"""Core sync pipeline: Extract → Map → Load → Archive → Deferred-fixup.

The pipeline is deliberately stateless.  The executor that calls it is
responsible for persisting state (high-water-mark cursor, article mappings,
etc.) between runs.  This separation makes the pipeline easy to unit-test.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
from collections.abc import Callable
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
        adapter:      The source adapter providing content (e.g. DeployAdapter).
        connector:    The target connector receiving content (e.g. SalesforceConnector).
        mapping:      Connector-specific field-mapping configuration dict.
        auto_publish: When ``True`` (default), call ``publish_article`` after each
                      successful upsert.  Set to ``False`` to leave articles as drafts.
        concurrency:  Maximum number of articles processed concurrently per run.
                      Defaults to 1 (sequential).  Increase for large deployments.
    """

    def __init__(
        self,
        adapter: ISourceAdapter,
        connector: ITargetConnector,
        mapping: dict,
        auto_publish: bool = True,
        concurrency: int = 1,
    ) -> None:
        self._adapter = adapter
        self._connector = connector
        self._mapping = mapping
        self._auto_publish = auto_publish
        self._concurrency = max(1, concurrency)

    async def run(
        self,
        run_id: str,
        since: str | None,
        removed_target_ids: dict[str, str] | None = None,
        force_full: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
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

        structure_entries = getattr(changeset, 'entries', {})
        category_map: dict = self._mapping.get("category_map", {})
        field_map = {k: v for k, v in self._mapping.items() if k != "category_map"}
        html_body_field: str = field_map.get("html_body", "")

        total_pages = len(changeset.changed)
        counter = [0]  # mutable int — asyncio is single-threaded; plain list cell is safe

        if progress_callback and total_pages:
            progress_callback(0, total_pages)

        # ── Stages 2–4: Fetch → Sanitise → Upload → Upsert (concurrent) ──────
        sem = asyncio.Semaphore(self._concurrency)

        async def _process_one(uuid: str, href: str) -> dict | None:
            async with sem:
                # Stage 2: Fetch page
                page = await self._adapter.get_page(href)
                entry = structure_entries.get(uuid)
                if entry is not None:
                    page = dataclasses.replace(
                        page,
                        section_path=entry.section_path,
                        sort_order=entry.sort_order,
                        sibling_uuids=entry.sibling_uuids,
                    )

                # Stage 3: Sanitise HTML
                clean_html = await self._connector.sanitize_html(page.html_body)
                page = dataclasses.replace(page, html_body=clean_html)

                # Stage 3.5: Upload binary assets and rewrite <img src>
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

                # Stage 4: Upsert + category sync + publish
                article_warnings: list[str] = []
                try:
                    result = await self._connector.upsert_article(page, field_map)
                except Exception as exc:
                    if "STORAGE_LIMIT_EXCEEDED" in str(exc):
                        log.warning(
                            "Article %r (%r) skipped: Salesforce article limit exceeded.",
                            page.uuid, page.title,
                        )
                        counter[0] += 1
                        if progress_callback:
                            progress_callback(counter[0], total_pages)
                        return {"skipped": True, "title": page.title or page.uuid}
                    raise

                article_warnings.extend(result.warnings)

                try:
                    await self._connector.sync_data_categories(
                        result.target_article_id, page.taxonomy, category_map
                    )
                except Exception as exc:
                    msg = f"Category sync failed for {result.target_article_id} ({page.title!r}): {exc}"
                    log.warning(msg)
                    article_warnings.append(msg)

                if not result.update_skipped and self._auto_publish:
                    try:
                        await self._connector.publish_article(
                            result.target_article_id, was_online=result.was_online
                        )
                    except Exception as exc:
                        msg = f"Publish failed for {result.target_article_id}: {exc}"
                        log.warning(msg)
                        article_warnings.append(msg)

                counter[0] += 1
                if progress_callback:
                    progress_callback(counter[0], total_pages)

                return {"result": result, "page": page, "warnings": article_warnings}

        outcomes = await asyncio.gather(
            *[_process_one(uuid, href) for uuid, href in changeset.changed]
        )

        # Collect results from concurrent tasks
        upsert_results: list[UpsertResult] = []
        link_map: dict[str, str] = {}    # source_uuid → target_article_id
        href_map: dict[str, str] = {}    # source_href → target_article_id
        run_warnings: list[str] = []
        storage_limit_skipped: list[str] = []
        processed_pages: dict[str, IRPage] = {}  # uuid → page (for sibling pass)

        for outcome in outcomes:
            if outcome is None:
                continue
            if outcome.get("skipped"):
                storage_limit_skipped.append(outcome["title"])
                continue
            result = outcome["result"]
            page = outcome["page"]
            run_warnings.extend(outcome["warnings"])
            upsert_results.append(result)
            link_map[page.uuid] = result.target_article_id
            href_map[page.href] = result.target_article_id
            processed_pages[page.uuid] = page

        if storage_limit_skipped:
            n = len(storage_limit_skipped)
            titles = ", ".join(storage_limit_skipped)
            run_warnings.append(
                f"{n} article{'s' if n != 1 else ''} skipped — Salesforce article limit exceeded: "
                f"{titles}. "
                f"Increase your org's Knowledge article limit or archive unused articles, "
                f"then re-run the sync to create the skipped articles."
            )

        # ── Stage 4.5: Deferred sibling relationship pass (force_full only) ──
        if structure_entries:
            for page in processed_pages.values():
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
        links_fixed = await self._connector.deferred_link_fixup(
            run_id, href_map, html_body_field=html_body_field
        )

        return PipelineResult(
            changed_count=len(upsert_results),
            removed_count=archived_count,
            high_water_mark=changeset.high_water_mark,
            links_fixed=links_fixed,
            article_mappings=link_map,
            warnings=run_warnings,
        )
