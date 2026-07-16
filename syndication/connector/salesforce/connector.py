"""Salesforce Knowledge ITargetConnector implementation.

Supports the standard Knowledge upsert-then-publish workflow via the
Salesforce REST API.  HTML is sanitised to the Knowledge-approved whitelist
before upload.

Auth credentials are provided at construction time (typically fetched from
hop-core's ``Credential`` model by the connector factory in ``main.py``).
The ``mapping`` parameter in ``upsert_article`` carries only the field-map:
    ``{"title": "Title", "html_body": "Answer__c", ...}``
"""
from __future__ import annotations

import base64
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
    "sf_instance_url",
    "sf_api_version",
    "sf_knowledge_type",
    "sf_external_id_field",
    "sf_access_token",
    "field_map",
]


class SalesforceConnector(ITargetConnector):
    """Target connector for Salesforce Knowledge.

    Args:
        instance_url:       ``https://{myorg}.my.salesforce.com``
        api_version:        Salesforce API version, e.g. ``"60.0"``.
        access_token:       OAuth2 / JWT Bearer access token.
        knowledge_type:     Knowledge article type object API name,
                            e.g. ``"Knowledge__kav"``.
        external_id_field:  External-ID field API name for upsert idempotency,
                            e.g. ``"ExternalId__c"``.
    """

    connector_id = "salesforce"

    def __init__(
        self,
        instance_url: str = "",
        api_version: str = "60.0",
        access_token: str = "",
        knowledge_type: str = "Knowledge__kav",
        external_id_field: str = "ExternalId__c",
    ) -> None:
        self._instance_url = instance_url.rstrip("/")
        self._api_version = api_version
        self._access_token = access_token
        self._kav_type = knowledge_type
        self._ext_field = external_id_field

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _base_url(self) -> str:
        return f"{self._instance_url}/services/data/v{self._api_version}"

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
        """Upload a binary file as a Salesforce ContentVersion.

        Returns the URL of the associated ContentDocument download endpoint.
        """
        base = self._base_url()
        # 1. Create ContentVersion
        payload = {
            "Title": filename,
            "PathOnClient": filename,
            "ContentLocation": "S",
            "VersionData": base64.b64encode(content).decode(),
        }
        resp = await self._request("POST", f"{base}/sobjects/ContentVersion", json=payload)
        version_id = resp.json()["id"]

        # 2. Retrieve ContentDocumentId for the version
        query = f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{version_id}'"
        q_resp = await self._request(
            "GET", f"{base}/query", params={"q": query}
        )
        doc_id = q_resp.json()["records"][0]["ContentDocumentId"]

        return f"{self._instance_url}/sfc/servlet.shepherd/document/download/{doc_id}"

    async def rewrite_links(self, html: str, link_map: dict[str, str]) -> str:
        """Rewrite ``href`` attributes in *html* using *link_map*.

        Links whose href is not in *link_map* are left unchanged.
        """
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
        """Upsert a Knowledge article using the external ID for idempotency.

        ``mapping`` is the field-map dict: ``{ir_field: sf_field_api_name}``.
        On HTTP 201 the article was created; on 204 it was updated.
        """
        base = self._base_url()
        url = f"{base}/sobjects/{self._kav_type}/{self._ext_field}/{ir.uuid}"

        # Build Salesforce payload from field_map
        payload: dict[str, Any] = {}
        for ir_field, sf_field in mapping.items():
            value = getattr(ir, ir_field, None)
            if value is not None:
                payload[sf_field] = value

        resp = await self._request("PATCH", url, json=payload)

        if resp.status_code == 201:
            body = resp.json()
            return UpsertResult(
                target_article_id=body["id"],
                created=True,
            )
        else:
            # 204 No Content → existing article updated; use uuid as stable ref
            return UpsertResult(
                target_article_id=ir.uuid,
                created=False,
            )

    async def publish_article(self, target_article_id: str) -> None:
        """Publish a Knowledge article via the Knowledge Management API."""
        base = self._base_url()
        url = f"{base}/knowledgeManagement/articleVersions/masterVersions/{target_article_id}"
        await self._request("POST", url, json={})

    async def archive_article(self, target_article_id: str) -> None:
        """Archive (delete draft) a Knowledge article."""
        base = self._base_url()
        url = f"{base}/sobjects/{self._kav_type}/{target_article_id}"
        await self._request("DELETE", url)

    async def deferred_link_fixup(
        self,
        run_id: str,
        link_map: dict[str, str],
    ) -> int:
        """Post-batch link rewrite pass.

        In the minimal implementation the state of which articles were loaded
        in *run_id* is not yet tracked, so 0 is returned.  A full
        implementation would query the state store for the run's articles,
        re-fetch each, rewrite links, and re-upsert.
        """
        # TODO: query state store for articles loaded in run_id, re-upsert each
        return 0
