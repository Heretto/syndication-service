"""Target connector interface.

Every knowledge-base target (Salesforce Knowledge, Zendesk, ServiceNow, …)
must implement ``ITargetConnector``.  The pipeline uses only this interface;
concrete connectors are selected at sync configuration time.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from syndication.ir.types import IRPage


@dataclass
class ValidationError:
    """A single field-level validation problem returned by ``validate_mapping``."""

    field: str
    message: str


@dataclass
class UpsertResult:
    """Result of a single ``upsert_article`` call."""

    target_article_id: str
    created: bool           # True = new article, False = existing article updated
    url: str | None = None  # canonical URL of the article in the target system


class ITargetConnector(ABC):
    """Abstract base class for all target connectors.

    Class attribute ``connector_id`` must be overridden with a unique string
    (e.g. ``"salesforce"``, ``"zendesk"``, ``"noop"``).
    """

    connector_id: str  # override in each concrete subclass

    @abstractmethod
    async def validate_mapping(self, mapping: dict) -> list[ValidationError]:
        """Validate a sync mapping configuration.

        Returns a list of validation errors; empty means the mapping is valid.
        Called once at sync-configuration time before any content is processed.
        """

    @abstractmethod
    async def sanitize_html(self, html: str) -> str:
        """Strip or transform HTML to the subset accepted by the target system.

        For example, Salesforce Knowledge only accepts a specific whitelist of
        tags and removes DITA-OT class attributes.
        """

    @abstractmethod
    async def upload_binary(
        self,
        uuid: str,
        content: bytes,
        mime_type: str,
        filename: str,
    ) -> str:
        """Upload a binary asset to the target system and return its stable URL.

        ``uuid`` is the source ``sys.uuid`` and is used as the stable external
        key so that re-syncs overwrite rather than duplicate the asset.
        """

    @abstractmethod
    async def rewrite_links(self, html: str, link_map: dict[str, str]) -> str:
        """Rewrite inter-article links in *html* using *link_map*.

        ``link_map`` maps source hrefs (or uuids) to target URLs.  Called as
        part of the deferred link-fixup pass after all articles are loaded.
        """

    @abstractmethod
    async def upsert_article(self, ir: IRPage, mapping: dict) -> UpsertResult:
        """Create or update a single article in the target system.

        The connector is responsible for determining whether this is a create
        or update (e.g. by checking whether the external key already exists).
        """

    @abstractmethod
    async def publish_article(self, target_article_id: str) -> None:
        """Publish a previously upserted article so it is visible to end users."""

    @abstractmethod
    async def archive_article(self, target_article_id: str) -> None:
        """Archive (unpublish) an article that was removed from the source."""

    @abstractmethod
    async def deferred_link_fixup(
        self,
        run_id: str,
        link_map: dict[str, str],
    ) -> int:
        """Post-batch pass: rewrite links in all articles loaded in *run_id*.

        Returns the number of articles updated.  Called once after all
        ``upsert_article`` calls for a sync run have completed.
        """
