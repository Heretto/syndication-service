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
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

import httpx
from lxml import html as lhtml

from syndication.connector.interface import (
    ITargetConnector,
    UpsertResult,
    ValidationError,
)
from syndication.connector.salesforce.sanitizer import sanitize_html as _sanitize
from syndication.ir.types import IRPage

def _slugify(text: str) -> str:
    """Convert *text* to a URL-safe Salesforce UrlName (max 255 chars)."""
    text = re.sub(r"[^\w\s-]", "", text.lower().strip())
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:255] or "article"


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

    Supports two auth modes:
    - Static token: pass ``access_token`` directly (backward-compat, no refresh).
    - OAuth 2.0 client credentials flow: pass ``client_id`` and ``client_secret``
      from a Salesforce External Client App with Client Credentials Flow enabled.
      The connector acquires and caches the token on first use and retries
      once on 401.
    """

    connector_id = "salesforce"

    def __init__(
        self,
        instance_url: str = "",
        api_version: str = "65.0",
        access_token: str = "",
        client_id: str = "",
        client_secret: str = "",
        knowledge_type: str = "Knowledge__kav",
        external_id_field: str = "Heretto_UUID__c",
    ) -> None:
        self._instance_url = instance_url.rstrip("/")
        self._api_version = api_version
        self._static_token = access_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._kav_type = knowledge_type
        self._ext_field = external_id_field
        self._cached_token: str | None = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _base_url(self) -> str:
        return f"{self._instance_url}/services/data/v{self._api_version}"

    async def _ensure_token(self) -> str:
        if self._static_token:
            return self._static_token
        if self._cached_token:
            return self._cached_token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._instance_url}/services/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            resp.raise_for_status()
        self._cached_token = resp.json()["access_token"]
        return self._cached_token

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        token = await self._ensure_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        log.info("SF %s %s", method, url)
        async with httpx.AsyncClient() as client:
            resp = await client.request(method, url, headers=headers, **kwargs)

        if resp.status_code == 401 and not self._static_token:
            # Cached OAuth token expired — clear and retry once
            self._cached_token = None
            token = await self._ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            async with httpx.AsyncClient() as client:
                resp = await client.request(method, url, headers=headers, **kwargs)

        if not resp.is_success:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise httpx.HTTPStatusError(
                f"{resp.status_code} {resp.reason_phrase} — {body}",
                request=resp.request,
                response=resp,
            )
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
                # Salesforce Rich Text Area fields cap at 32768 chars
                if isinstance(value, str) and len(value) > 32000:
                    value = value[:32000]
                payload[sf_field] = value

        # 1. Query for any existing version by our tracking field
        soql = (
            f"SELECT Id, PublishStatus FROM {self._kav_type} "
            f"WHERE {self._ext_field} = '{ir.uuid}' "
            f"AND PublishStatus IN ('Draft', 'Online') "
            f"ORDER BY LastModifiedDate DESC LIMIT 1"
        )
        q_resp = await self._request("GET", f"{base}/query", params={"q": soql})
        records = q_resp.json().get("records", [])

        if records:
            rec = records[0]
            article_id = rec["Id"]
            publish_status = rec.get("PublishStatus", "")
            log.info("SF existing article %s PublishStatus=%r", article_id, publish_status)

            if publish_status in ("Online", "Archived"):
                # Create an edit draft so we can update and re-publish.
                # POST /knowledgeManagement/articleVersions may return 405 in some
                # Lightning Knowledge orgs (dev org API limitation); if so, skip the
                # content update and leave the article untouched.
                try:
                    edit_resp = await self._request(
                        "POST",
                        f"{base}/knowledgeManagement/articleVersions",
                        json={"masterVersionId": article_id},
                    )
                    article_id = edit_resp.json()["id"]
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 405:
                        log.warning(
                            "Cannot create edit draft for %s article %s "
                            "(API limitation — article not updated this run)",
                            publish_status,
                            article_id,
                        )
                        return UpsertResult(
                            target_article_id=article_id,
                            created=False,
                            was_online=publish_status == "Online",
                            update_skipped=True,
                        )
                    raise

            await self._request(
                "PATCH",
                f"{base}/sobjects/{self._kav_type}/{article_id}",
                json=payload,
            )
            return UpsertResult(
                target_article_id=article_id,
                created=False,
                was_online=publish_status == "Online",
            )
        else:
            # New article: use the Lightning Experience UI API.
            # sObject POST and Knowledge Management POST endpoints all return 405
            # for Knowledge in Lightning Knowledge orgs. The UI API is the correct
            # programmatic surface for creating new articles.
            base_slug = _slugify(ir.title)
            slug = f"{base_slug}-{ir.uuid[:8]}" if base_slug else ir.uuid.replace("-", "")
            ui_api_url = f"{self._instance_url}/services/data/v{self._api_version}/ui-api/records"
            create_resp = await self._request(
                "POST",
                ui_api_url,
                json={
                    "apiName": self._kav_type,
                    "fields": {
                        "Title": ir.title,
                        "UrlName": slug,
                        "Language": "en_US",
                    },
                },
            )
            kav_id = create_resp.json()["id"]

            # Stamp content and tracking field onto the new draft KAV
            payload[self._ext_field] = ir.uuid
            payload.setdefault("UrlName", slug)
            await self._request(
                "PATCH",
                f"{base}/sobjects/{self._kav_type}/{kav_id}",
                json=payload,
            )
            return UpsertResult(target_article_id=kav_id, created=True)

    async def publish_article(self, target_article_id: str, was_online: bool = False) -> None:
        """Publish a Knowledge article via the Lightning Knowledge standard action.

        articleVersionIdList takes the KAV version Id (ka0... prefix).
        was_online=True uses PUBLISH_ARTICLE_NEW_VERSION for re-publishing an
        article that was already Online when we patched it.
        """
        pub_action = "PUBLISH_ARTICLE_NEW_VERSION" if was_online else "PUBLISH_ARTICLE"
        url = f"{self._instance_url}/services/data/v{self._api_version}/actions/standard/publishKnowledgeArticles"
        resp = await self._request(
            "POST",
            url,
            json={"inputs": [{"articleVersionIdList": [target_article_id], "pubAction": pub_action}]},
        )
        result = resp.json()
        if result and not result[0].get("isSuccess"):
            raise httpx.HTTPStatusError(
                f"publishKnowledgeArticles failed: {result[0].get('outputValues')}",
                request=resp.request,
                response=resp,
            )

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
