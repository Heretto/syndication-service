"""ServiceNow Knowledge Management connector.

Implements ITargetConnector against the ServiceNow Table API and Attachment
API.  Articles are stored in the ``kb_knowledge`` table; a custom field
(default ``u_external_id``) is used for idempotent upserts.

Upsert strategy:
  1. GET /api/now/table/kb_knowledge?sysparm_query={ext_field}={uuid} → check existence
  2. Empty result  → POST  to create (sets ext_field + kb_knowledge_base)
  3. Record found  → PATCH to update

Publish:  PATCH workflow_state → "published"
Archive:  PATCH workflow_state → "retired"
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
    "sn_instance_url",
    "sn_access_token",
    "sn_knowledge_base_sys_id",
    "field_map",
]


class ServiceNowConnector(ITargetConnector):
    """ITargetConnector for ServiceNow Knowledge Management.

    Args:
        instance_url:          ``https://{instance}.service-now.com``
        access_token:          OAuth 2.0 Bearer token.
        knowledge_base_sys_id: sys_id of the target knowledge base record.
        kb_category_sys_id:    Optional sys_id of the default KB category.
        external_id_field:     Custom field used as the external ID for upserts
                               (default ``"u_external_id"``).
    """

    connector_id = "servicenow"

    def __init__(
        self,
        instance_url: str = "",
        access_token: str = "",
        knowledge_base_sys_id: str = "",
        kb_category_sys_id: str = "",
        external_id_field: str = "u_external_id",
    ) -> None:
        self._instance_url = instance_url.rstrip("/")
        self._access_token = access_token
        self._kb_sys_id = knowledge_base_sys_id
        self._category_sys_id = kb_category_sys_id
        self._ext_field = external_id_field

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _base_url(self) -> str:
        return f"{self._instance_url}/api/now"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
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
        """Upload a binary file as a ServiceNow attachment on the knowledge base record.

        Returns the ``download_link`` URL from the ServiceNow attachment response.
        """
        url = f"{self._base_url()}/attachment/file"
        params = {
            "table_name": "kb_knowledge_base",
            "table_sys_id": self._kb_sys_id,
            "file_name": filename,
        }
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": mime_type,
            "Accept": "application/json",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, params=params, headers=headers, content=content)
            resp.raise_for_status()
        return resp.json()["result"]["download_link"]

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
        """Upsert a Knowledge article using the external ID field for idempotency.

        Queries ``kb_knowledge`` by the external ID field.  Creates a new article
        (POST) if none is found; updates the existing one (PATCH) otherwise.
        """
        base = self._base_url()
        table_url = f"{base}/table/kb_knowledge"

        # 1. Check for an existing article by external ID
        query_resp = await self._request(
            "GET",
            table_url,
            params={
                "sysparm_query": f"{self._ext_field}={ir.uuid}",
                "sysparm_fields": "sys_id",
                "sysparm_limit": "1",
            },
        )
        results = query_resp.json().get("result", [])

        # 2. Build field payload from the mapping
        payload: dict[str, Any] = {}
        for ir_field, sn_field in mapping.items():
            value = getattr(ir, ir_field, None)
            if value is not None:
                payload[sn_field] = value

        if results:
            # Update existing article
            sys_id = results[0]["sys_id"]
            await self._request("PATCH", f"{table_url}/{sys_id}", json=payload)
            return UpsertResult(target_article_id=sys_id, created=False)
        else:
            # Create new article; include external ID, knowledge base, and initial state
            payload[self._ext_field] = ir.uuid
            payload["kb_knowledge_base"] = self._kb_sys_id
            if self._category_sys_id:
                payload["kb_category"] = self._category_sys_id
            payload["workflow_state"] = "draft"

            create_resp = await self._request("POST", table_url, json=payload)
            sys_id = create_resp.json()["result"]["sys_id"]
            return UpsertResult(target_article_id=sys_id, created=True)

    async def publish_article(self, target_article_id: str) -> None:
        """Publish a Knowledge article by setting workflow_state to 'published'."""
        base = self._base_url()
        url = f"{base}/table/kb_knowledge/{target_article_id}"
        await self._request("PATCH", url, json={"workflow_state": "published"})

    async def archive_article(self, target_article_id: str) -> None:
        """Retire a Knowledge article by setting workflow_state to 'retired'."""
        base = self._base_url()
        url = f"{base}/table/kb_knowledge/{target_article_id}"
        await self._request("PATCH", url, json={"workflow_state": "retired"})

    async def deferred_link_fixup(
        self,
        run_id: str,
        link_map: dict[str, str],
    ) -> int:
        """Post-batch link rewrite pass.  Not yet implemented; returns 0."""
        # TODO: query state store for articles loaded in run_id, re-upsert each
        return 0
