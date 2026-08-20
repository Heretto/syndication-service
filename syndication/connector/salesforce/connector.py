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
        """Upsert a Knowledge article using a SOQL query for idempotency.

        Lightning Knowledge does not support External ID on custom fields, so
        we query by ``self._ext_field`` value instead of using the native
        External ID upsert endpoint.

        Lifecycle handling:
          - No match    → POST a new draft; stamp ``self._ext_field = ir.uuid``.
          - Draft match → PATCH the draft in place.
          - Online match → POST to ``knowledgeManagement/articleVersions`` to
            create an edit draft, then PATCH it; ``publish_article`` will
            promote it back to Online.
        """
        base = self._base_url()

        # Build field payload from mapping
        payload: dict[str, Any] = {}
        for ir_field, sf_field in mapping.items():
            value = getattr(ir, ir_field, None)
            if value is not None:
                payload[sf_field] = value

        # 1. Query for any existing version by our tracking field
        soql = (
            f"SELECT Id, PublishStatus FROM {self._kav_type} "
            f"WHERE {self._ext_field} = '{ir.uuid}' "
            f"ORDER BY LastModifiedDate DESC LIMIT 1"
        )
        q_resp = await self._request("GET", f"{base}/query", params={"q": soql})
        records = q_resp.json().get("records", [])

        if records:
            rec = records[0]
            article_id = rec["Id"]

            if rec.get("PublishStatus") == "Online":
                # Create an edit draft from the published version before patching
                edit_resp = await self._request(
                    "POST",
                    f"{base}/knowledgeManagement/articleVersions",
                    json={"masterVersionId": article_id},
                )
                article_id = edit_resp.json()["id"]

            await self._request(
                "PATCH",
                f"{base}/sobjects/{self._kav_type}/{article_id}",
                json=payload,
            )
            return UpsertResult(target_article_id=article_id, created=False)
        else:
            # New article: stamp our tracking field and create a draft
            payload[self._ext_field] = ir.uuid
            create_resp = await self._request(
                "POST",
                f"{base}/sobjects/{self._kav_type}",
                json=payload,
            )
            article_id = create_resp.json()["id"]
            return UpsertResult(target_article_id=article_id, created=True)

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

        For each source_uuid → article_id pair in *link_map*:
        1. Fetch the current article HTML body from Salesforce.
        2. Rewrite any inter-article links using the full URL map.
        3. PATCH the article if the HTML changed.

        Returns the number of articles actually modified.
        """
        if not link_map:
            return 0

        base = self._base_url()

        # Build url_map: source_uuid → full Salesforce article URL
        url_map = {
            source_uuid: f"{self._instance_url}/articles/{article_id}"
            for source_uuid, article_id in link_map.items()
        }

        count = 0
        for source_uuid, article_id in link_map.items():
            resp = await self._request(
                "GET",
                f"{base}/sobjects/{self._kav_type}/{article_id}",
            )
            body = resp.json()
            current = body.get("Body", "") or ""
            rewritten = await self.rewrite_links(current, url_map)
            if rewritten != current:
                await self._request(
                    "PATCH",
                    f"{base}/sobjects/{self._kav_type}/{article_id}",
                    json={"Body": rewritten},
                )
                count += 1

        return count
