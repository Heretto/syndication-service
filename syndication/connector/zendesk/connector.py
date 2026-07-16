"""Zendesk Guide connector.

Implements ITargetConnector against the Zendesk Help Center API.

Upsert strategy: label-based search.  Each article receives the label
``heretto-{ir.uuid}`` on creation; a search by that label locates the
article on subsequent syncs.

Auth:  ``Authorization: Bearer {access_token}`` header.
"""
from __future__ import annotations

from typing import Any

import httpx
from lxml import html as lhtml

from syndication.connector.interface import (
    ITargetConnector,
    UpsertResult,
    ValidationError,
)
from syndication.connector.salesforce.sanitizer import sanitize_html as _sanitize
from syndication.ir.types import IRPage

_REQUIRED_MAPPING_KEYS = [
    "zd_subdomain",
    "zd_access_token",
    "zd_section_id",
    "field_map",
]


class ZendeskConnector(ITargetConnector):
    """ITargetConnector for Zendesk Guide.

    Args:
        subdomain:    The Zendesk subdomain, e.g. ``"mycompany"`` for
                      ``mycompany.zendesk.com``.
        access_token: OAuth2 Bearer token.
        section_id:   Numeric ID of the target Help Center section.
        locale:       Article locale (default ``"en-us"``).
    """

    connector_id = "zendesk"

    def __init__(
        self,
        subdomain: str = "",
        access_token: str = "",
        section_id: str = "",
        locale: str = "en-us",
    ) -> None:
        self._subdomain = subdomain.strip().rstrip("/")
        self._access_token = access_token
        self._section_id = section_id
        self._locale = locale

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _base_url(self) -> str:
        return f"https://{self._subdomain}.zendesk.com"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        async with httpx.AsyncClient(headers=self._headers()) as client:
            resp = await client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp

    # ── ITargetConnector ──────────────────────────────────────────────────────

    async def validate_mapping(self, mapping: dict) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for key in _REQUIRED_MAPPING_KEYS:
            if key not in mapping:
                errors.append(
                    ValidationError(field=key, message=f"Required mapping key {key!r} is missing.")
                )
        return errors

    async def sanitize_html(self, html: str) -> str:
        return _sanitize(html)

    async def upload_binary(
        self,
        uuid: str,
        content: bytes,
        mime_type: str,
        filename: str,
    ) -> str:
        """Zendesk article attachments require the article ID at upload time.

        Because the article ID is not available when ``upload_binary`` is
        called (before ``upsert_article``), this raises ``NotImplementedError``.
        Upload binaries after the article is created using the Zendesk
        Attachments API directly if needed.
        """
        raise NotImplementedError(
            "ZendeskConnector.upload_binary: article_id is not available at "
            "upload time.  Upload attachments after upsert_article() completes."
        )

    async def rewrite_links(self, html: str, link_map: dict[str, str]) -> str:
        """Rewrite ``href`` attributes in *html* using *link_map*."""
        if not html or not link_map:
            return html

        doc = lhtml.fromstring(f"<div>{html}</div>")
        for elem in doc.iter("a"):
            href = elem.get("href", "")
            if href in link_map:
                elem.set("href", link_map[href])

        return (doc.text or "") + "".join(
            lhtml.tostring(child, encoding="unicode") for child in doc
        )

    async def upsert_article(self, ir: IRPage, mapping: dict) -> UpsertResult:
        """Upsert a Help Center article using the label ``heretto-{uuid}`` for idempotency.

        Searches for an existing article by label; creates a new draft article
        (POST) if none found, updates the existing one (PUT) otherwise.
        """
        base = self._base_url()
        label = f"heretto-{ir.uuid}"

        # 1. Search for an existing article by label
        search_resp = await self._request(
            "GET",
            f"{base}/api/v2/help_center/articles/search",
            params={"label_names": label, "per_page": "1"},
        )
        results = search_resp.json().get("results", [])

        title = getattr(ir, "title", "") or ""
        body = getattr(ir, "html_body", "") or ""

        if results:
            # Update existing article
            article_id = results[0]["id"]
            await self._request(
                "PUT",
                f"{base}/api/v2/help_center/{self._locale}/articles/{article_id}",
                json={"article": {"title": title, "body": body}},
            )
            return UpsertResult(target_article_id=str(article_id), created=False)
        else:
            # Create new draft article in the configured section
            create_resp = await self._request(
                "POST",
                f"{base}/api/v2/help_center/{self._locale}/sections/{self._section_id}/articles",
                json={
                    "article": {
                        "title": title,
                        "body": body,
                        "label_names": [label],
                        "draft": True,
                    }
                },
            )
            article_id = create_resp.json()["article"]["id"]
            return UpsertResult(target_article_id=str(article_id), created=True)

    async def publish_article(self, target_article_id: str) -> None:
        """Publish a Help Center article by setting draft to false."""
        base = self._base_url()
        await self._request(
            "PUT",
            f"{base}/api/v2/help_center/{self._locale}/articles/{target_article_id}",
            json={"article": {"draft": False}},
        )

    async def archive_article(self, target_article_id: str) -> None:
        """Archive a Help Center article by deleting it."""
        base = self._base_url()
        await self._request(
            "DELETE",
            f"{base}/api/v2/help_center/articles/{target_article_id}",
        )

    async def deferred_link_fixup(
        self,
        run_id: str,
        link_map: dict[str, str],
    ) -> int:
        """Post-batch link rewrite pass.

        For each source_uuid → article_id pair in *link_map*:
        1. Fetch the current article body from Zendesk.
        2. Rewrite any inter-article links using the full URL map.
        3. PUT the article body back if the HTML changed.

        Returns the number of articles actually modified.
        """
        if not link_map:
            return 0

        base = self._base_url()

        # Build url_map: source_uuid → full Zendesk article URL
        url_map = {
            source_uuid: f"{base}/hc/{self._locale}/articles/{article_id}"
            for source_uuid, article_id in link_map.items()
        }

        count = 0
        for source_uuid, article_id in link_map.items():
            resp = await self._request(
                "GET",
                f"{base}/api/v2/help_center/{self._locale}/articles/{article_id}",
            )
            current = resp.json().get("article", {}).get("body", "") or ""
            rewritten = await self.rewrite_links(current, url_map)
            if rewritten != current:
                await self._request(
                    "PUT",
                    f"{base}/api/v2/help_center/{self._locale}/articles/{article_id}",
                    json={"article": {"body": rewritten}},
                )
                count += 1

        return count
