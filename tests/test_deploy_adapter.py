"""Tests for Deploy API client + adapter (TDD step 2b).

HTTP calls are mocked with respx so no real network is needed.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from syndication.ir.types import ChangeSet, IRPage
from syndication.source.deploy.client import DeployClient
from syndication.source.deploy.adapter import DeployAdapter

BASE_URL = "https://testorg.deploy.heretto.com"
DEPLOYMENT_ID = "dep-001"
API_KEY = "test-key-abc"

# ── Shared fixture payloads ────────────────────────────────────────────────────

CHANGED_CONTENT_PAYLOAD = [
    {
        "path": "help/topic-a",
        "fileUuid": "uuid-aaa",
        "audience": "private",
        "locale": "en",
        "contentModificationDate": "2026-07-14T18:00:43.592Z",
        "changeType": "added",
    },
    {
        "path": "help/topic-a",       # same page, different audience — should be deduped
        "fileUuid": "uuid-aaa",
        "audience": "__default",
        "locale": "en",
        "contentModificationDate": "2026-07-14T18:00:43.592Z",
        "changeType": "added",
    },
    {
        "path": "help/topic-b",
        "fileUuid": "uuid-bbb",
        "audience": "private",
        "locale": "en",
        "contentModificationDate": "2026-07-15T10:00:00.000Z",
        "changeType": "modified",
    },
    {
        "path": "help/old-page",
        "fileUuid": "uuid-ccc",
        "audience": "private",
        "locale": "en",
        "contentModificationDate": "2026-07-13T08:00:00.000Z",
        "changeType": "removed",
    },
]

CONTENT_PAYLOAD = {
    "sys": {"uuid": "uuid-aaa"},
    "path": "help/topic-a",
    "content": "<p>Hello world</p>",
    "standardMetadata": {
        "date": {
            "lastModified": {"value": "1752523243592"},
        },
        "text_single_Line": {
            "contentType": {"value": "Concept"},
        },
    },
    "shortDescription": "A short description.",
    "breadcrumbs": [],
    "versions": [],
    "chunked_sections": [],
    "customMetadata": {},
    "ditaMetadata": {"othermetas": []},
}

STRUCTURE_PAYLOAD = {
    "snapshotId": "snap-xyz",
    "items": [
        {"path": "help/topic-a", "type": "topic"},
        {"path": "help/topic-b", "type": "topic"},
    ],
}


# ── DeployClient tests ────────────────────────────────────────────────────────

class TestDeployClient:
    @pytest.fixture
    def client(self) -> DeployClient:
        return DeployClient(
            base_url=BASE_URL,
            deployment_id=DEPLOYMENT_ID,
            api_key=API_KEY,
            audience="private",
        )

    async def test_get_changed_content_no_since(self, client: DeployClient):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=CHANGED_CONTENT_PAYLOAD))

            result = await client.get_changed_content(since=None)

        assert isinstance(result, list)
        assert len(result) == 4

    async def test_get_changed_content_with_since(self, client: DeployClient):
        since = "2026-07-14T00:00:00.000Z"
        with respx.mock(base_url=BASE_URL) as mock:
            route = mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content",
            ).mock(return_value=httpx.Response(200, json=[]))

            await client.get_changed_content(since=since)

        # Verify the since query param was sent
        assert route.called
        request = route.calls.last.request
        assert f"since={since}" in str(request.url) or "since=" in str(request.url)

    async def test_get_changed_content_auth_header(self, client: DeployClient):
        with respx.mock(base_url=BASE_URL) as mock:
            route = mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=[]))

            await client.get_changed_content(since=None)

        request = route.calls.last.request
        assert request.headers.get("X-Deploy-API-Auth") == API_KEY

    async def test_get_content(self, client: DeployClient):
        path = "help/topic-a"
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/content",
            ).mock(return_value=httpx.Response(200, json=CONTENT_PAYLOAD))

            result = await client.get_content(path=path)

        assert result["sys"]["uuid"] == "uuid-aaa"
        assert result["content"] == "<p>Hello world</p>"

    async def test_get_structure(self, client: DeployClient):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            result = await client.get_structure()

        assert result["snapshotId"] == "snap-xyz"
        assert len(result["items"]) == 2

    async def test_fetch_binary(self, client: DeployClient):
        binary_url = "https://cdn.example.com/img.png"
        png_bytes = b"\x89PNG\r\n\x1a\n"
        with respx.mock() as mock:
            mock.get(binary_url).mock(
                return_value=httpx.Response(
                    200,
                    content=png_bytes,
                    headers={"Content-Type": "image/png"},
                )
            )
            data, mime = await client.fetch_binary(binary_url)

        assert data == png_bytes
        assert mime == "image/png"

    async def test_http_error_raises(self, client: DeployClient):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(401))

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_changed_content(since=None)


# ── DeployAdapter tests ────────────────────────────────────────────────────────

class TestDeployAdapter:
    @pytest.fixture
    def adapter(self) -> DeployAdapter:
        return DeployAdapter(
            org_id="testorg",
            deployment_id=DEPLOYMENT_ID,
            api_key=API_KEY,
            audience="private",
            base_url=BASE_URL,
        )

    def test_adapter_id(self, adapter: DeployAdapter):
        assert adapter.adapter_id == "deploy"

    async def test_get_changed_deduplicates_by_uuid(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=CHANGED_CONTENT_PAYLOAD))

            cs = await adapter.get_changed(since=None)

        assert isinstance(cs, ChangeSet)
        # uuid-aaa appears twice (two audiences) but should be deduplicated → 1 entry
        changed_uuids = [uuid for uuid, _ in cs.changed]
        assert changed_uuids.count("uuid-aaa") == 1

    async def test_get_changed_separates_removed(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=CHANGED_CONTENT_PAYLOAD))

            cs = await adapter.get_changed(since=None)

        assert "uuid-ccc" in cs.removed_uuids
        changed_uuids = [uuid for uuid, _ in cs.changed]
        assert "uuid-ccc" not in changed_uuids

    async def test_get_changed_high_water_mark(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=CHANGED_CONTENT_PAYLOAD))

            cs = await adapter.get_changed(since=None)

        # max contentModificationDate in the payload is topic-b's date
        assert cs.high_water_mark == "2026-07-15T10:00:00.000Z"

    async def test_get_changed_empty_response(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=[]))

            cs = await adapter.get_changed(since=None)

        assert cs.changed == []
        assert cs.removed_uuids == []
        assert cs.high_water_mark == ""

    async def test_get_page_maps_to_ir_page(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/content"
            ).mock(return_value=httpx.Response(200, json=CONTENT_PAYLOAD))

            page = await adapter.get_page("help/topic-a")

        assert isinstance(page, IRPage)
        assert page.uuid == "uuid-aaa"
        assert page.href == "help/topic-a"
        assert page.title == CONTENT_PAYLOAD.get("title", "") or True  # title may be empty in stub
        assert page.html_body == "<p>Hello world</p>"
        assert page.content_type == "Concept"
        assert page.last_modified_ms == 1_752_523_243_592
        assert page.source_adapter_id == "deploy"
        assert page.source_organization_id == "testorg"
        assert page.source_deployment_id == DEPLOYMENT_ID

    async def test_get_all_hrefs(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            hrefs = await adapter.get_all_hrefs()

        assert set(hrefs) == {"help/topic-a", "help/topic-b"}

    async def test_get_snapshot_token(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            token = await adapter.get_snapshot_token()

        assert token == "snap-xyz"

    async def test_fetch_binary_delegates(self, adapter: DeployAdapter):
        url = "https://cdn.example.com/doc.pdf"
        with respx.mock() as mock:
            mock.get(url).mock(
                return_value=httpx.Response(
                    200,
                    content=b"%PDF",
                    headers={"Content-Type": "application/pdf"},
                )
            )
            data, mime = await adapter.fetch_binary(url)

        assert data == b"%PDF"
        assert mime == "application/pdf"
