"""ISourceAdapter implementation backed by the Heretto Deploy API v4."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from syndication.ir.types import ChangeSet, IRPage, IRTaxonomyValue
from syndication.source.interface import ISourceAdapter
from syndication.source.deploy.client import DeployClient


@dataclass
class StructureEntry:
    """Per-topic metadata extracted from a /structure tree walk."""

    uuid: str
    href: str
    section_path: list[str]    # titles of ancestor topichead/sitesection nodes
    sort_order: int             # 1-based position among topicref siblings
    sibling_uuids: list[str]   # UUIDs of other topicref siblings under same parent


@dataclass
class StructureChangeSet:
    """Like ChangeSet but enriched with per-topic structural metadata.

    Returned by ``get_all_from_structure()`` so the pipeline can apply
    section grouping, sort ordering, and sibling relationships during a
    force-full resync.
    """

    changed: list[tuple[str, str]]        # [(fileUuid, path), …]
    removed_uuids: list[str]
    high_water_mark: str
    entries: dict[str, StructureEntry] = field(default_factory=dict)


class DeployAdapter(ISourceAdapter):
    """Source adapter that reads from the Heretto Deploy API.

    Args:
        org_id:         Heretto organisation identifier (used in provenance).
        deployment_id:  Deploy API deployment identifier.
        api_key:        API key for ``X-Deploy-API-Auth``.
        audience:       Which audience to prefer when deduplicating changed_content
                        results (default ``"private"``).
        base_url:       Override for the Deploy API base URL; defaults to the
                        standard ``https://{org_id}.deploy.heretto.com``.
    """

    adapter_id = "deploy"

    def __init__(
        self,
        org_id: str,
        deployment_id: str,
        api_key: str,
        audience: str = "private",
        base_url: str | None = None,
    ) -> None:
        self._org_id = org_id
        self._deployment_id = deployment_id
        self._audience = audience
        resolved_base = base_url or f"https://{org_id}.deploy.heretto.com"
        self._client = DeployClient(
            base_url=resolved_base,
            deployment_id=deployment_id,
            api_key=api_key,
            audience=audience,
        )

    # ── ISourceAdapter ────────────────────────────────────────────────────────

    async def get_snapshot_token(self) -> str:
        structure = await self._client.get_structure()
        return structure.get("snapshotId", "")

    async def get_all_hrefs(self) -> list[str]:
        structure = await self._client.get_structure()
        entries: list[StructureEntry] = []
        self._collect_topics(structure, entries)
        return [e.href for e in entries]

    async def get_all_from_structure(self) -> StructureChangeSet:
        """Walk the full structure tree and return every topic as a StructureChangeSet.

        ``high_water_mark`` is left empty so the executor does not advance the
        incremental cursor — the next scheduled run will still pick up any
        changes that occurred after the previous cursor.
        """
        structure = await self._client.get_structure()
        entries: list[StructureEntry] = []
        self._collect_topics(structure, entries)
        return StructureChangeSet(
            changed=[(e.uuid, e.href) for e in entries],
            removed_uuids=[],
            high_water_mark="",
            entries={e.uuid: e for e in entries},
        )

    async def get_changed(self, since: str | None) -> ChangeSet:
        """Return a deduplicated ChangeSet from the /changed_content endpoint.

        Deduplication strategy:
          1. Group raw rows by ``fileUuid``.
          2. For each uuid prefer the row whose ``audience`` matches the
             configured audience; fall back to the first row.
          3. Rows with ``changeType == "removed"`` go into ``removed_uuids``.
          4. All other rows go into ``changed`` as ``(fileUuid, path)`` tuples.
          5. ``high_water_mark`` = lexicographic max of all
             ``contentModificationDate`` values (ISO 8601 sorts correctly as
             plain strings), or ``""`` when the response is empty.
        """
        raw: list[dict] = await self._client.get_changed_content(since=since)
        if not raw:
            return ChangeSet(changed=[], removed_uuids=[], high_water_mark="")

        # 1. Group by fileUuid
        by_uuid: dict[str, list[dict]] = {}
        for item in raw:
            by_uuid.setdefault(item["fileUuid"], []).append(item)

        # 2. Pick preferred audience row for each uuid
        selected: list[dict] = []
        for rows in by_uuid.values():
            preferred = next(
                (r for r in rows if r.get("audience") == self._audience), rows[0]
            )
            selected.append(preferred)

        # 3+4. Separate removed from changed
        changed: list[tuple[str, str]] = []
        removed_uuids: list[str] = []
        for item in selected:
            if item.get("changeType") == "removed":
                removed_uuids.append(item["fileUuid"])
            else:
                changed.append((item["fileUuid"], item["path"]))

        # 5. High-water mark across all raw items (not just selected)
        high_water_mark = max(
            (item.get("contentModificationDate", "") for item in raw),
            default="",
        )

        return ChangeSet(
            changed=changed,
            removed_uuids=removed_uuids,
            high_water_mark=high_water_mark,
        )

    async def get_page(self, href: str) -> IRPage:
        """Fetch a single page and map it to an ``IRPage``."""
        data = await self._client.get_content(path=href)
        return self._map_to_ir(data)

    async def fetch_binary(self, url: str) -> tuple[bytes, str]:
        return await self._client.fetch_binary(url)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _collect_topics(
        node: dict,
        out: list[StructureEntry],
        ancestor_path: list[str] | None = None,
        sibling_uuids: list[str] | None = None,
        sort_order: int = 1,
    ) -> None:
        """Recursively collect StructureEntry objects for every topicref with content.

        ``ancestor_path`` accumulates titles of topichead/sitesection ancestors.
        ``sibling_uuids`` lists UUIDs of other topicref children under the same parent.
        ``sort_order`` is the 1-based position of this node among its topicref siblings.
        """
        if ancestor_path is None:
            ancestor_path = []
        if sibling_uuids is None:
            sibling_uuids = []

        href = node.get("href", "/")
        if node.get("type") == "topicref" and href != "/":
            uuid = node.get("sys", {}).get("uuid", "")
            if uuid:
                out.append(StructureEntry(
                    uuid=uuid,
                    href=href,
                    section_path=ancestor_path[:],
                    sort_order=sort_order,
                    sibling_uuids=sibling_uuids[:],
                ))

        children = node.get("children", [])

        # Pre-compute sibling UUIDs for all topicref children at this level
        topicref_child_uuids = [
            c.get("sys", {}).get("uuid", "")
            for c in children
            if c.get("type") == "topicref"
            and c.get("href", "/") != "/"
            and c.get("sys", {}).get("uuid", "")
        ]

        topicref_index = 0
        for child in children:
            child_type = child.get("type")
            if child_type == "topicref":
                topicref_index += 1
                child_uuid = child.get("sys", {}).get("uuid", "")
                siblings = [u for u in topicref_child_uuids if u != child_uuid]
                DeployAdapter._collect_topics(child, out, ancestor_path, siblings, topicref_index)
            elif child_type in ("topichead", "sitesection"):
                title = child.get("title", "")
                new_path = ancestor_path + [title] if title else ancestor_path[:]
                DeployAdapter._collect_topics(child, out, new_path)

    @staticmethod
    def _parse_taxonomy(custom_metadata: dict) -> dict[str, list[IRTaxonomyValue]]:
        """Parse ``customMetadata.taxonomy`` into the IR taxonomy dict.

        Deploy shape:
            { "taxonomy": { "GroupName": { "values": [{ "value": "v", "humanReadable": "V" }] } } }
        """
        raw = custom_metadata.get("taxonomy", {})
        return {
            group: [
                IRTaxonomyValue(v["value"], v.get("humanReadable", v["value"]))
                for v in entry.get("values", [])
                if v.get("value")
            ]
            for group, entry in raw.items()
        }

    def _map_to_ir(self, data: dict) -> IRPage:
        sys_block = data.get("sys", {})
        std_meta = data.get("standardMetadata", {})

        # last modified
        last_mod_str = (
            std_meta.get("date", {})
            .get("lastModified", {})
            .get("value", "0")
        )
        last_modified_ms = int(last_mod_str or "0")
        last_modified_iso = datetime.fromtimestamp(
            last_modified_ms / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S.") + f"{last_modified_ms % 1000:03d}Z"

        content_type = (
            std_meta.get("text_single_Line", {})
            .get("contentType", {})
            .get("value", "")
        )

        return IRPage(
            uuid=sys_block.get("uuid", ""),
            href=data.get("path", ""),
            title=data.get("title", ""),
            short_description=data.get("shortDescription", ""),
            html_body=data.get("content", ""),
            content_type=content_type,
            last_modified_ms=last_modified_ms,
            last_modified_iso=last_modified_iso,
            source_adapter_id=self.adapter_id,
            source_organization_id=self._org_id,
            source_deployment_id=self._deployment_id,
            # enrichment fields — populated from nested payload sections
            breadcrumbs=[],        # TODO: parse breadcrumbs array
            taxonomy=self._parse_taxonomy(data.get("customMetadata", {})),
            versions=[],           # TODO: parse versions array
            chunked_sections=[],   # TODO: parse chunked_sections array
            keywords=[],
            othermetas=data.get("ditaMetadata", {}).get("othermetas", []),
        )
