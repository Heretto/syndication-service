"""ServiceNow Knowledge Management stub connector.

Placeholder implementation — not yet built.  All non-trivial methods raise
``NotImplementedError`` so the pipeline fails loudly rather than silently
producing incorrect results.
"""
from __future__ import annotations

from syndication.connector.interface import (
    ITargetConnector,
    UpsertResult,
    ValidationError,
)
from syndication.ir.types import IRPage


class ServiceNowConnector(ITargetConnector):
    """Stub ITargetConnector for ServiceNow Knowledge.  Not yet implemented."""

    connector_id = "servicenow"

    async def validate_mapping(self, mapping: dict) -> list[ValidationError]:
        raise NotImplementedError("ServiceNowConnector.validate_mapping is not implemented yet.")

    async def sanitize_html(self, html: str) -> str:
        # Stub: return HTML unchanged until ServiceNow-specific rules are known.
        return html

    async def upload_binary(
        self, uuid: str, content: bytes, mime_type: str, filename: str
    ) -> str:
        raise NotImplementedError("ServiceNowConnector.upload_binary is not implemented yet.")

    async def rewrite_links(self, html: str, link_map: dict[str, str]) -> str:
        return html

    async def upsert_article(self, ir: IRPage, mapping: dict) -> UpsertResult:
        raise NotImplementedError("ServiceNowConnector.upsert_article is not implemented yet.")

    async def publish_article(self, target_article_id: str) -> None:
        raise NotImplementedError("ServiceNowConnector.publish_article is not implemented yet.")

    async def archive_article(self, target_article_id: str) -> None:
        raise NotImplementedError("ServiceNowConnector.archive_article is not implemented yet.")

    async def deferred_link_fixup(
        self, run_id: str, link_map: dict[str, str]
    ) -> int:
        return 0
