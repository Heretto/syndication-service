"""No-op connector — a test double for ITargetConnector.

Records every method call and returns safe, deterministic defaults.
Useful as a test double in pipeline and executor unit tests.
"""
from __future__ import annotations

from syndication.connector.interface import ITargetConnector, UpsertResult, ValidationError
from syndication.ir.types import IRPage


class NoopConnector(ITargetConnector):
    """ITargetConnector that does nothing and records calls for test inspection."""

    connector_id = "noop"

    def __init__(self) -> None:
        # Sets of target_article_ids that had publish/archive called on them
        self.published_ids: set[str] = set()
        self.archived_ids: set[str] = set()
        # Track which uuids have been upserted (to distinguish create vs update)
        self._upserted: set[str] = set()

    async def validate_mapping(self, mapping: dict) -> list[ValidationError]:
        return []

    async def sanitize_html(self, html: str) -> str:
        return html

    async def upload_binary(
        self,
        uuid: str,
        content: bytes,
        mime_type: str,
        filename: str,
    ) -> str:
        # Return a stable fake URL keyed on uuid so repeated calls are idempotent
        return f"noop://binaries/{uuid}"

    async def rewrite_links(self, html: str, link_map: dict[str, str]) -> str:
        # Intentionally a no-op; pipeline tests can verify links were passed
        return html

    async def upsert_article(self, ir: IRPage, mapping: dict) -> UpsertResult:
        created = ir.uuid not in self._upserted
        self._upserted.add(ir.uuid)
        return UpsertResult(target_article_id=ir.uuid, created=created)

    async def publish_article(self, target_article_id: str, was_online: bool = False) -> None:
        self.published_ids.add(target_article_id)

    async def archive_article(self, target_article_id: str) -> None:
        self.archived_ids.add(target_article_id)

    async def deferred_link_fixup(
        self,
        run_id: str,
        link_map: dict[str, str],
        html_body_field: str = "",
    ) -> int:
        return 0
