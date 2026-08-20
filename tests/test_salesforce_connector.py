"""Tests for the Salesforce Knowledge connector (TDD step 11).

Salesforce HTTP calls are mocked with respx; no real credentials required.

Design note: SalesforceConnector stores auth credentials (instance_url,
access_token, api_version, etc.) at construction time.  The ``mapping``
parameter in ``upsert_article`` carries only the field-map configuration
(IR field name → Salesforce field API name).  Other ITargetConnector
methods (publish_article, archive_article, etc.) use the stored credentials.
"""
from __future__ import annotations

import json
import httpx
import pytest
import respx

from syndication.connector.interface import ITargetConnector, UpsertResult, ValidationError
from syndication.connector.salesforce.connector import SalesforceConnector
from syndication.ir.types import IRPage

SF_INSTANCE = "https://myorg.my.salesforce.com"
API_VER = "60.0"
BASE = f"{SF_INSTANCE}/services/data/v{API_VER}"
ACCESS_TOKEN = "test-access-token-abc"
KAV_TYPE = "Knowledge__kav"
EXT_FIELD = "ExternalId__c"

FIELD_MAP = {
    "title": "Title",
    "short_description": "Summary__c",
    "html_body": "Answer__c",
}

REQUIRED_MAPPING_KEYS = [
    "sf_instance_url",
    "sf_api_version",
    "sf_knowledge_type",
    "sf_external_id_field",
    "sf_access_token",
    "field_map",
]

GOOD_MAPPING = {
    "sf_instance_url": SF_INSTANCE,
    "sf_api_version": API_VER,
    "sf_knowledge_type": KAV_TYPE,
    "sf_external_id_field": EXT_FIELD,
    "sf_access_token": ACCESS_TOKEN,
    "field_map": FIELD_MAP,
}


def _conn() -> SalesforceConnector:
    return SalesforceConnector(
        instance_url=SF_INSTANCE,
        api_version=API_VER,
        access_token=ACCESS_TOKEN,
        knowledge_type=KAV_TYPE,
        external_id_field=EXT_FIELD,
    )


def _make_ir_page(**overrides) -> IRPage:
    base = dict(
        uuid="9e6bc560-0ab7-11ee-b063-0242b23a931f",
        href="help/claims-handling",
        title="Claims Handling",
        short_description="How to handle claims.",
        html_body="<p>Body text</p>",
        content_type="Concept",
        last_modified_ms=1_700_000_000_000,
        last_modified_iso="2023-11-14T22:13:20.000Z",
        source_adapter_id="deploy",
        source_organization_id="org",
        source_deployment_id="dep",
    )
    base.update(overrides)
    return IRPage(**base)


# ── ABC membership ─────────────────────────────────────────────────────────────

class TestABCMembership:
    def test_is_instance_of_interface(self):
        assert isinstance(_conn(), ITargetConnector)

    def test_connector_id(self):
        assert SalesforceConnector.connector_id == "salesforce"


# ── validate_mapping (class method / static helper) ───────────────────────────

class TestValidateMapping:
    async def test_valid_mapping_returns_empty(self):
        conn = _conn()
        errors = await conn.validate_mapping(GOOD_MAPPING)
        assert errors == []

    async def test_missing_instance_url_returns_error(self):
        conn = _conn()
        mapping = {**GOOD_MAPPING}
        del mapping["sf_instance_url"]
        errors = await conn.validate_mapping(mapping)
        assert any(e.field == "sf_instance_url" for e in errors)

    async def test_missing_access_token_returns_error(self):
        conn = _conn()
        mapping = {**GOOD_MAPPING}
        del mapping["sf_access_token"]
        errors = await conn.validate_mapping(mapping)
        assert any(e.field == "sf_access_token" for e in errors)

    async def test_missing_field_map_returns_error(self):
        conn = _conn()
        mapping = {**GOOD_MAPPING}
        del mapping["field_map"]
        errors = await conn.validate_mapping(mapping)
        assert any(e.field == "field_map" for e in errors)

    async def test_all_required_keys_validated(self):
        conn = _conn()
        for key in REQUIRED_MAPPING_KEYS:
            m = {**GOOD_MAPPING}
            del m[key]
            errors = await conn.validate_mapping(m)
            assert len(errors) >= 1, f"Missing key {key!r} should produce at least one error"


# ── sanitize_html ─────────────────────────────────────────────────────────────

class TestSanitizeHtml:
    async def test_strips_non_whitelisted_tags(self):
        conn = _conn()
        result = await conn.sanitize_html("<div><p>Hello</p></div>")
        assert "<div" not in result
        assert "<p>" in result

    async def test_removes_class_attributes(self):
        conn = _conn()
        result = await conn.sanitize_html('<p class="topic/concept">Text</p>')
        assert "class=" not in result

    async def test_empty_html_returns_empty(self):
        conn = _conn()
        result = await conn.sanitize_html("")
        assert result == ""


# ── upsert_article ────────────────────────────────────────────────────────────

class TestUpsertArticle:
    """upsert_article uses SOQL query-first; no External ID field required."""

    def _query_url(self) -> str:
        return f"{BASE}/query"

    def _sobject_url(self, article_id: str = "") -> str:
        base = f"{BASE}/sobjects/{KAV_TYPE}"
        return f"{base}/{article_id}" if article_id else base

    def _mock_query(self, mock, records: list) -> None:
        mock.get(self._query_url()).mock(
            return_value=httpx.Response(200, json={"records": records})
        )

    # ── create (no existing record) ───────────────────────────────────────────

    async def test_create_returns_upsert_result(self):
        conn = _conn()
        page = _make_ir_page()
        with respx.mock() as mock:
            self._mock_query(mock, [])
            mock.post(self._sobject_url()).mock(
                return_value=httpx.Response(201, json={"id": "ka01NEW", "success": True})
            )
            result = await conn.upsert_article(page, FIELD_MAP)

        assert isinstance(result, UpsertResult)
        assert result.created is True
        assert result.target_article_id == "ka01NEW"

    async def test_create_stamps_tracking_field_in_payload(self):
        conn = _conn()
        page = _make_ir_page()
        with respx.mock() as mock:
            self._mock_query(mock, [])
            post_route = mock.post(self._sobject_url()).mock(
                return_value=httpx.Response(201, json={"id": "ka01NEW", "success": True})
            )
            await conn.upsert_article(page, FIELD_MAP)

        payload = json.loads(post_route.calls.last.request.content)
        assert payload.get(EXT_FIELD) == page.uuid

    async def test_create_sends_mapped_title(self):
        conn = _conn()
        page = _make_ir_page(title="My Article Title")
        with respx.mock() as mock:
            self._mock_query(mock, [])
            post_route = mock.post(self._sobject_url()).mock(
                return_value=httpx.Response(201, json={"id": "ka01NEW", "success": True})
            )
            await conn.upsert_article(page, FIELD_MAP)

        payload = json.loads(post_route.calls.last.request.content)
        assert payload.get("Title") == "My Article Title"

    async def test_create_sends_mapped_html_body(self):
        conn = _conn()
        page = _make_ir_page(html_body="<p>Body text</p>")
        with respx.mock() as mock:
            self._mock_query(mock, [])
            post_route = mock.post(self._sobject_url()).mock(
                return_value=httpx.Response(201, json={"id": "ka01NEW", "success": True})
            )
            await conn.upsert_article(page, FIELD_MAP)

        payload = json.loads(post_route.calls.last.request.content)
        assert payload.get("Answer__c") == "<p>Body text</p>"

    # ── update — existing Draft ───────────────────────────────────────────────

    async def test_update_draft_patches_in_place(self):
        conn = _conn()
        page = _make_ir_page()
        with respx.mock() as mock:
            self._mock_query(mock, [{"Id": "ka01DRF", "PublishStatus": "Draft"}])
            patch_route = mock.patch(self._sobject_url("ka01DRF")).mock(
                return_value=httpx.Response(204)
            )
            result = await conn.upsert_article(page, FIELD_MAP)

        assert result.created is False
        assert result.target_article_id == "ka01DRF"
        assert patch_route.called

    async def test_update_draft_sends_mapped_fields(self):
        conn = _conn()
        page = _make_ir_page(title="Updated Title")
        with respx.mock() as mock:
            self._mock_query(mock, [{"Id": "ka01DRF", "PublishStatus": "Draft"}])
            patch_route = mock.patch(self._sobject_url("ka01DRF")).mock(
                return_value=httpx.Response(204)
            )
            await conn.upsert_article(page, FIELD_MAP)

        payload = json.loads(patch_route.calls.last.request.content)
        assert payload.get("Title") == "Updated Title"

    # ── update — existing Online (published) article ───────────────────────────

    async def test_update_online_creates_edit_draft_first(self):
        conn = _conn()
        page = _make_ir_page()
        edit_url = f"{BASE}/knowledgeManagement/articleVersions"
        with respx.mock() as mock:
            self._mock_query(mock, [{"Id": "ka01PUB", "PublishStatus": "Online"}])
            edit_route = mock.post(edit_url).mock(
                return_value=httpx.Response(201, json={"id": "ka01EDT", "success": True})
            )
            mock.patch(self._sobject_url("ka01EDT")).mock(
                return_value=httpx.Response(204)
            )
            result = await conn.upsert_article(page, FIELD_MAP)

        assert edit_route.called
        edit_payload = json.loads(edit_route.calls.last.request.content)
        assert edit_payload.get("masterVersionId") == "ka01PUB"
        assert result.target_article_id == "ka01EDT"
        assert result.created is False

    async def test_update_online_patches_the_edit_draft(self):
        conn = _conn()
        page = _make_ir_page(title="New Version Title")
        edit_url = f"{BASE}/knowledgeManagement/articleVersions"
        with respx.mock() as mock:
            self._mock_query(mock, [{"Id": "ka01PUB", "PublishStatus": "Online"}])
            mock.post(edit_url).mock(
                return_value=httpx.Response(201, json={"id": "ka01EDT", "success": True})
            )
            patch_route = mock.patch(self._sobject_url("ka01EDT")).mock(
                return_value=httpx.Response(204)
            )
            await conn.upsert_article(page, FIELD_MAP)

        payload = json.loads(patch_route.calls.last.request.content)
        assert payload.get("Title") == "New Version Title"

    # ── auth ─────────────────────────────────────────────────────────────────

    async def test_upsert_sends_bearer_auth(self):
        conn = _conn()
        page = _make_ir_page()
        with respx.mock() as mock:
            query_route = mock.get(self._query_url()).mock(
                return_value=httpx.Response(200, json={"records": []})
            )
            mock.post(self._sobject_url()).mock(
                return_value=httpx.Response(201, json={"id": "ka01NEW", "success": True})
            )
            await conn.upsert_article(page, FIELD_MAP)

        request = query_route.calls.last.request
        assert f"Bearer {ACCESS_TOKEN}" in request.headers.get("Authorization", "")

    # ── error handling ────────────────────────────────────────────────────────

    async def test_upsert_query_error_raises(self):
        conn = _conn()
        page = _make_ir_page()
        with respx.mock() as mock:
            mock.get(self._query_url()).mock(return_value=httpx.Response(401))
            with pytest.raises(httpx.HTTPStatusError):
                await conn.upsert_article(page, FIELD_MAP)

    async def test_upsert_create_error_raises(self):
        conn = _conn()
        page = _make_ir_page()
        with respx.mock() as mock:
            self._mock_query(mock, [])
            mock.post(self._sobject_url()).mock(
                return_value=httpx.Response(400, json=[{"message": "bad field"}])
            )
            with pytest.raises(httpx.HTTPStatusError):
                await conn.upsert_article(page, FIELD_MAP)


# ── publish_article ───────────────────────────────────────────────────────────

class TestPublishArticle:
    def _pub_url(self, art_id: str) -> str:
        return f"{BASE}/knowledgeManagement/articleVersions/masterVersions/{art_id}"

    async def test_publish_makes_post_request(self):
        conn = _conn()
        art_id = "ka01000000001AAA"
        with respx.mock() as mock:
            route = mock.post(self._pub_url(art_id)).mock(
                return_value=httpx.Response(200)
            )
            await conn.publish_article(art_id)

        assert route.called

    async def test_publish_sends_bearer_auth(self):
        conn = _conn()
        art_id = "ka01AAA"
        with respx.mock() as mock:
            route = mock.post(self._pub_url(art_id)).mock(
                return_value=httpx.Response(200)
            )
            await conn.publish_article(art_id)

        request = route.calls.last.request
        assert f"Bearer {ACCESS_TOKEN}" in request.headers.get("Authorization", "")


# ── archive_article ───────────────────────────────────────────────────────────

class TestArchiveArticle:
    async def test_archive_makes_delete_request(self):
        conn = _conn()
        art_id = "ka01AAA"
        with respx.mock() as mock:
            route = mock.delete(
                f"{BASE}/sobjects/{KAV_TYPE}/{art_id}"
            ).mock(return_value=httpx.Response(204))
            await conn.archive_article(art_id)

        assert route.called


# ── upload_binary ─────────────────────────────────────────────────────────────

class TestUploadBinary:
    async def test_upload_returns_string_url(self):
        conn = _conn()
        with respx.mock() as mock:
            mock.post(f"{BASE}/sobjects/ContentVersion").mock(
                return_value=httpx.Response(
                    201, json={"id": "068aaa", "success": True}
                )
            )
            mock.get(f"{BASE}/query").mock(
                return_value=httpx.Response(
                    200, json={"records": [{"ContentDocumentId": "069bbb"}]}
                )
            )
            url = await conn.upload_binary(
                uuid="img-uuid-001",
                content=b"\x89PNG",
                mime_type="image/png",
                filename="diagram.png",
            )

        assert isinstance(url, str)
        assert len(url) > 0

    async def test_upload_sends_bearer_auth(self):
        conn = _conn()
        with respx.mock() as mock:
            route = mock.post(f"{BASE}/sobjects/ContentVersion").mock(
                return_value=httpx.Response(
                    201, json={"id": "068aaa", "success": True}
                )
            )
            mock.get(f"{BASE}/query").mock(
                return_value=httpx.Response(
                    200, json={"records": [{"ContentDocumentId": "069bbb"}]}
                )
            )
            await conn.upload_binary("uuid", b"data", "image/png", "f.png")

        request = route.calls.last.request
        assert f"Bearer {ACCESS_TOKEN}" in request.headers.get("Authorization", "")


# ── rewrite_links ─────────────────────────────────────────────────────────────

class TestRewriteLinks:
    async def test_rewrites_href_in_anchor(self):
        conn = _conn()
        html = '<p>See <a href="/old-path">this</a></p>'
        link_map = {"/old-path": "https://sf.example.com/articles/new-article"}
        result = await conn.rewrite_links(html, link_map)
        assert "https://sf.example.com/articles/new-article" in result
        assert "/old-path" not in result

    async def test_unknown_href_left_unchanged(self):
        conn = _conn()
        html = '<a href="/unknown">link</a>'
        result = await conn.rewrite_links(html, link_map={})
        assert "/unknown" in result

    async def test_empty_html_returns_empty(self):
        conn = _conn()
        result = await conn.rewrite_links("", link_map={"a": "b"})
        assert result == ""


# ── deferred_link_fixup ───────────────────────────────────────────────────────

class TestDeferredLinkFixup:
    def _article_url(self, article_id: str) -> str:
        return f"{BASE}/sobjects/{KAV_TYPE}/{article_id}"

    async def test_returns_zero_with_empty_link_map(self):
        conn = _conn()
        n = await conn.deferred_link_fixup("run-1", {})
        assert n == 0

    async def test_returns_non_negative_int(self):
        conn = _conn()
        link_map = {"uuid-a": "art-001"}
        with respx.mock() as mock:
            mock.get(self._article_url("art-001")).mock(
                return_value=httpx.Response(200, json={"Body": ""})
            )
            n = await conn.deferred_link_fixup("run-1", link_map)
        assert isinstance(n, int)
        assert n >= 0

    async def test_modified_article_increments_count(self):
        conn = _conn()
        link_map = {"uuid-a": "art-002"}
        with respx.mock() as mock:
            mock.get(self._article_url("art-002")).mock(
                return_value=httpx.Response(200, json={"Body": '<a href="uuid-a">link</a>'})
            )
            mock.patch(self._article_url("art-002")).mock(
                return_value=httpx.Response(204)
            )
            n = await conn.deferred_link_fixup("run-1", link_map)
        assert n == 1

    async def test_unchanged_article_not_patched(self):
        conn = _conn()
        link_map = {"uuid-b": "art-003"}
        with respx.mock(assert_all_called=False) as mock:
            mock.get(self._article_url("art-003")).mock(
                return_value=httpx.Response(200, json={"Body": "<p>No links</p>"})
            )
            patch_route = mock.patch(self._article_url("art-003")).mock(
                return_value=httpx.Response(204)
            )
            n = await conn.deferred_link_fixup("run-1", link_map)
        assert n == 0
        assert not patch_route.called
        assert n >= 0
