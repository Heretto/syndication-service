"""Target-neutral Intermediate Representation (IR) types.

Every field maps directly to data available from the Heretto Deploy API
/content response.  ``sys.uuid`` is the stable primary key used everywhere
(href / path is secondary and can change on content reorganisation).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IRBreadcrumb:
    """One breadcrumb entry as returned by the Deploy API."""

    title: str
    href: str
    item_type: str | None = None
    item_id: str | None = None
    outputclasses: list[str] = field(default_factory=list)


@dataclass
class IRTaxonomyValue:
    """A single taxonomy facet value."""

    value: str
    human_readable: str = ""

    def __post_init__(self) -> None:
        if not self.human_readable:
            self.human_readable = self.value


@dataclass
class IRVersion:
    """One version entry from the Deploy API ``versions`` array."""

    title: str
    href: str
    version_id: str
    contained_topic_href: str | None = None


@dataclass
class IRChunkedSection:
    """One chunked section from the Deploy API ``chunked_sections`` array."""

    uuid: str
    title: str
    topic_id: str
    dita_metadata: dict = field(default_factory=dict)
    children: list = field(default_factory=list)


@dataclass
class IRPage:
    """A fully-resolved, target-neutral page ready for connector ingestion.

    Required positional semantics (no defaults) are listed first so that
    callers get a clear TypeError when a mandatory field is omitted.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    uuid: str                          # sys.uuid — immutable primary key
    href: str                          # path — secondary, changes on reorg
    title: str
    short_description: str
    html_body: str                     # raw HTML5 from Deploy API (pre-sanitisation)
    content_type: str                  # standardMetadata contentType value
    last_modified_ms: int              # epoch ms (standardMetadata date)
    last_modified_iso: str             # ISO 8601 string of the same instant

    # ── Provenance ────────────────────────────────────────────────────────────
    source_adapter_id: str
    source_organization_id: str
    source_deployment_id: str

    # ── Enrichment (all optional with empty-collection defaults) ──────────────
    breadcrumbs: list[IRBreadcrumb] = field(default_factory=list)
    taxonomy: dict[str, list[IRTaxonomyValue]] = field(default_factory=dict)
    versions: list[IRVersion] = field(default_factory=list)
    chunked_sections: list[IRChunkedSection] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    othermetas: list[dict[str, str]] = field(default_factory=list)
    prodinfos: list[dict] = field(default_factory=list)
    resource_ids: list[str] = field(default_factory=list)

    # ── Structure metadata (force_full only) ──────────────────────────────────
    # Populated from the /structure tree walk; empty on incremental runs.
    section_path: list[str] = field(default_factory=list)
    sort_order: int = 0                # 1-based position among topicref siblings
    sibling_uuids: list[str] = field(default_factory=list)

    # ── Binary assets ─────────────────────────────────────────────────────────
    # Expiring JWT URLs extracted from html_body; must be fetched within the
    # same executor run that called get_page().
    binary_urls: list[str] = field(default_factory=list)


@dataclass
class ChangeSet:
    """Result of ISourceAdapter.get_changed().

    ``changed`` is a list of (fileUuid, path) tuples — deduplication by
    fileUuid (one entry per page regardless of audience count) is done
    inside the Deploy adapter before returning this object.

    ``high_water_mark`` is the ISO 8601 maximum ``contentModificationDate``
    from the ``/changed_content`` response and should be persisted as the
    ``since`` cursor for the next incremental sync.
    """

    changed: list[tuple[str, str]]    # [(fileUuid, path), ...]
    removed_uuids: list[str]
    high_water_mark: str              # ISO 8601 or "" for first run
