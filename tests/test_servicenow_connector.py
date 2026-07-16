"""Tests for the ServiceNow Knowledge connector — TDD step 15.

ServiceNow HTTP calls are mocked with respx; no real credentials required.

Design:
  - Credentials (instance_url, access_token, knowledge_base_sys_id, etc.)
    are stored at construction time.
  - `mapping` in upsert_article is a field-map: {ir_field: sn_field_name}.
  - Upsert strategy: GET by u_external_id, then POST (create) or PATCH (update).
  - Publish: PATCH workflow_state → "published".
  - Archive: PATCH workflow_state → "retired".
  - Binary upload: POST /api/now/attachment/file with raw body.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from syndication.connector.interface import ITargetConnector, UpsertResult, ValidationError
from syndication.connector.servicenow.connector import ServiceNowConnector
from syndication.ir.types import IRPage

SN_INSTANCE = "https://mycompany.service-now.com"
ACCESS_TOKEN = "sn-bearer-token-abc"
KB_SYS_ID = "kb-sys-id-001"
EXT_FIELD = "u_external_id"
BASE = f"{SN_INSTANCE}/api/now"

FIELD_MAP = {
    "title": "short_description",
    "html_body": "text",
}

REQUIRED_MAPPING_KEYS = [
    "sn_instance_url",
    "sn_access_token",
    "sn_knowledge_base_sys_id",
    "field_map",
]

GOOD_MAPPING = {
    "sn_instance_url": SN_INSTANCE,
    "sn_access_token": ACCESS_TOKEN,
    "sn_knowledge_base_sys_id": KB_SYS_ID,
    "field_map": FIELD_MAP,
}


def _conn(**overrides) -> ServiceNowConnector:
    kwargs = dict(
        instance_url=SN_INSTANCE,
        access_token=ACCESS_TOKEN,
        knowledge_base_sys_id=KB_SYS_ID,
        external_id_field=EXT_FIELD,
    )
    kwargs.update(overrides)
    return ServiceNowConnector(**kwargs)


def _make_ir(**overrides) -> IRPage:
    base = dict(
        uuid="ir-uuid-001",
        href="help/claims",
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


def _query_url() -> str:
    return f"{BASE}/table/kb_knowledge"


def _article_url(sys_id: str) -> str:
    return f"{BASE}/table/kb_knowledge/{sys_id}"


# ── ABC membership ─────────────────────────────────────────────────────────────

class TestABCMembership:
    def test_is_instance_of_interface(self):
        assert isinstance(_conn(), ITargetConnector)

    def test_connector_id(self):
        assert ServiceNowConnector.connector_id == "servicenow"


# ── validate_mapping ───────────────────────────────────────────────────────────

class TestValidateMapping:
    async def test_valid_mapping_returns_empty(self):
        errors = await _conn().validate_mapping(GOOD_MAPPING)
        assert errors == []

    async def test_missing_instance_url_returns_error(self):
        m = {**GOOD_MAPPING}
        del m["sn_instance_url"]
        errors = await _conn().validate_mapping(m)
        assert any(e.field == "sn_instance_url" for e in errors)

    async def test_missing_access_token_returns_error(self):
        m = {**GOOD_MAPPING}
        del m["sn_access_token"]
        errors = await _conn().validate_mapping(m)
        assert any(e.field == "sn_access_token" for e in errors)

    async def test_missing_knowledge_base_sys_id_returns_error(self):
        m = {**GOOD_MAPPING}
        del m["sn_knowledge_base_sys_id"]
        errors = await _conn().validate_mapping(m)
        assert any(e.field == "sn_knowledge_base_sys_id" for e in errors)

    async def test_missing_field_map_returns_error(self):
        m = {**GOOD_MAPPING}
        del m["field_map"]
        errors = await _conn().validate_mapping(m)
        assert any(e.field == "field_map" for e in errors)

    async def test_all_required_keys_validated(self):
        for key in REQUIRED_MAPPING_KEYS:
            m = {**GOOD_MAPPING}
            del m[key]
            errors = await _conn().validate_mapping(m)
            assert len(errors) >= 1, f"Missing key {key!r} should produce at least one error"


# ── sanitize_html ─────────────────────────────────────────────────────────────

class TestSanitizeHtml:
    async def test_strips_non_whitelisted_tags(self):
        result = await _conn().sanitize_html("<div><p>Hello</p></div>")
        assert "<div" not in result
        assert "<p>" in result

    async def test_removes_class_attributes(self):
        result = await _conn().sanitize_html('<p class="note">Text</p>')
        assert "class=" not in result

    async def test_empty_html_returns_empty(self):
        result = await _conn().sanitize_html("")
        assert result == ""


# ── upsert_article ────────────────────────────────────────────────────────────

class TestUpsertArticle:
    """GET-then-POST for new articles; GET-then-PATCH for existing ones."""

    def _empty_query(self):
        """Mock returning no existing article."""
        return httpx.Response(200, json={"result": []})

    def _found_query(self, sys_id: str = "existing-sys-id"):
        """Mock returning an existing article."""
        return httpx.Response(200, json={"result": [{"sys_id": sys_id}]})

    async def test_create_new_article_returns_upsert_result(self):
        ir = _make_ir()
        with respx.mock() as mock:
            mock.get(_query_url()).mock(return_value=self._empty_query())
            mock.post(_query_url()).mock(
                return_value=httpx.Response(201, json={"result": {"sys_id": "new-sys-001"}})
            )
            result = await _conn().upsert_article(ir, FIELD_MAP)
        assert isinstance(result, UpsertResult)
        assert result.created is True
        assert result.target_article_id == "new-sys-001"

    async def test_update_existing_article_returns_upsert_result(self):
        ir = _make_ir()
        with respx.mock() as mock:
            mock.get(_query_url()).mock(return_value=self._found_query("old-sys-001"))
            mock.patch(_article_url("old-sys-001")).mock(
                return_value=httpx.Response(200, json={"result": {"sys_id": "old-sys-001"}})
            )
            result = await _conn().upsert_article(ir, FIELD_MAP)
        assert result.created is False
        assert result.target_article_id == "old-sys-001"

    async def test_create_sets_external_id_field(self):
        ir = _make_ir(uuid="uuid-ext-001")
        with respx.mock() as mock:
            mock.get(_query_url()).mock(return_value=self._empty_query())
            route = mock.post(_query_url()).mock(
                return_value=httpx.Response(201, json={"result": {"sys_id": "new-sys"}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        import json
        payload = json.loads(route.calls.last.request.content)
        assert payload.get(EXT_FIELD) == "uuid-ext-001"

    async def test_create_sets_knowledge_base_sys_id(self):
        ir = _make_ir()
        with respx.mock() as mock:
            mock.get(_query_url()).mock(return_value=self._empty_query())
            route = mock.post(_query_url()).mock(
                return_value=httpx.Response(201, json={"result": {"sys_id": "new-sys"}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        import json
        payload = json.loads(route.calls.last.request.content)
        assert payload.get("kb_knowledge_base") == KB_SYS_ID

    async def test_create_sends_title_as_short_description(self):
        ir = _make_ir(title="My Great Article")
        with respx.mock() as mock:
            mock.get(_query_url()).mock(return_value=self._empty_query())
            route = mock.post(_query_url()).mock(
                return_value=httpx.Response(201, json={"result": {"sys_id": "new-sys"}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        import json
        payload = json.loads(route.calls.last.request.content)
        assert payload.get("short_description") == "My Great Article"

    async def test_create_sends_html_body_as_text(self):
        ir = _make_ir(html_body="<p>Body</p>")
        with respx.mock() as mock:
            mock.get(_query_url()).mock(return_value=self._empty_query())
            route = mock.post(_query_url()).mock(
                return_value=httpx.Response(201, json={"result": {"sys_id": "new-sys"}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        import json
        payload = json.loads(route.calls.last.request.content)
        assert payload.get("text") == "<p>Body</p>"

    async def test_sends_bearer_auth(self):
        ir = _make_ir()
        with respx.mock() as mock:
            route = mock.get(_query_url()).mock(return_value=self._empty_query())
            mock.post(_query_url()).mock(
                return_value=httpx.Response(201, json={"result": {"sys_id": "new-sys"}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        assert f"Bearer {ACCESS_TOKEN}" in route.calls.last.request.headers.get("Authorization", "")

    async def test_query_uses_external_id_field(self):
        from urllib.parse import unquote
        ir = _make_ir(uuid="target-uuid")
        with respx.mock() as mock:
            route = mock.get(_query_url()).mock(return_value=self._empty_query())
            mock.post(_query_url()).mock(
                return_value=httpx.Response(201, json={"result": {"sys_id": "new"}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        assert f"{EXT_FIELD}=target-uuid" in unquote(str(route.calls.last.request.url))

    async def test_http_error_raises(self):
        ir = _make_ir()
        with respx.mock() as mock:
            mock.get(_query_url()).mock(return_value=httpx.Response(500))
            with pytest.raises(httpx.HTTPStatusError):
                await _conn().upsert_article(ir, FIELD_MAP)


# ── publish_article ───────────────────────────────────────────────────────────

class TestPublishArticle:
    async def test_publish_patches_workflow_state(self):
        import json
        with respx.mock() as mock:
            route = mock.patch(_article_url("art-001")).mock(
                return_value=httpx.Response(200, json={"result": {}})
            )
            await _conn().publish_article("art-001")
        payload = json.loads(route.calls.last.request.content)
        assert payload.get("workflow_state") == "published"

    async def test_publish_sends_bearer_auth(self):
        with respx.mock() as mock:
            route = mock.patch(_article_url("art-001")).mock(
                return_value=httpx.Response(200, json={"result": {}})
            )
            await _conn().publish_article("art-001")
        assert f"Bearer {ACCESS_TOKEN}" in route.calls.last.request.headers.get("Authorization", "")


# ── archive_article ───────────────────────────────────────────────────────────

class TestArchiveArticle:
    async def test_archive_patches_workflow_state_to_retired(self):
        import json
        with respx.mock() as mock:
            route = mock.patch(_article_url("art-001")).mock(
                return_value=httpx.Response(200, json={"result": {}})
            )
            await _conn().archive_article("art-001")
        payload = json.loads(route.calls.last.request.content)
        assert payload.get("workflow_state") == "retired"


# ── upload_binary ─────────────────────────────────────────────────────────────

class TestUploadBinary:
    async def test_upload_returns_download_link(self):
        dl_link = f"{SN_INSTANCE}/api/now/attachment/att-sys-id/file"
        with respx.mock() as mock:
            mock.post(f"{BASE}/attachment/file").mock(
                return_value=httpx.Response(
                    201, json={"result": {"sys_id": "att-sys-id", "download_link": dl_link}}
                )
            )
            url = await _conn().upload_binary("bin-uuid", b"\x89PNG", "image/png", "img.png")
        assert url == dl_link

    async def test_upload_sends_raw_binary_body(self):
        with respx.mock() as mock:
            route = mock.post(f"{BASE}/attachment/file").mock(
                return_value=httpx.Response(
                    201, json={"result": {"sys_id": "att", "download_link": "http://x"}}
                )
            )
            await _conn().upload_binary("uuid", b"RAWDATA", "image/png", "f.png")
        assert route.calls.last.request.content == b"RAWDATA"

    async def test_upload_sends_bearer_auth(self):
        with respx.mock() as mock:
            route = mock.post(f"{BASE}/attachment/file").mock(
                return_value=httpx.Response(
                    201, json={"result": {"sys_id": "att", "download_link": "http://x"}}
                )
            )
            await _conn().upload_binary("uuid", b"data", "image/png", "f.png")
        assert f"Bearer {ACCESS_TOKEN}" in route.calls.last.request.headers.get("Authorization", "")


# ── rewrite_links ─────────────────────────────────────────────────────────────

class TestRewriteLinks:
    async def test_rewrites_href_in_anchor(self):
        html = '<a href="/old">link</a>'
        result = await _conn().rewrite_links(html, {"/old": "https://sn.example.com/new"})
        assert "https://sn.example.com/new" in result
        assert "/old" not in result

    async def test_unknown_href_left_unchanged(self):
        html = '<a href="/unknown">link</a>'
        result = await _conn().rewrite_links(html, {})
        assert "/unknown" in result

    async def test_empty_html_returns_empty(self):
        result = await _conn().rewrite_links("", {"a": "b"})
        assert result == ""


# ── deferred_link_fixup ───────────────────────────────────────────────────────

class TestDeferredLinkFixup:
    async def test_returns_non_negative_int(self):
        with respx.mock() as mock:
            mock.get(_article_url("target-a")).mock(
                return_value=httpx.Response(200, json={"result": {"text": ""}})
            )
            n = await _conn().deferred_link_fixup("run-1", {"uuid-a": "target-a"})
        assert isinstance(n, int)
        assert n >= 0

    async def test_modified_article_increments_count(self):
        link_map = {"uuid-a": "art-sn-001"}
        with respx.mock() as mock:
            mock.get(_article_url("art-sn-001")).mock(
                return_value=httpx.Response(200, json={"result": {"text": '<a href="uuid-a">link</a>'}})
            )
            mock.patch(_article_url("art-sn-001")).mock(
                return_value=httpx.Response(200, json={"result": {}})
            )
            n = await _conn().deferred_link_fixup("run-1", link_map)
        assert n == 1

    async def test_unchanged_article_not_patched(self):
        link_map = {"uuid-b": "art-sn-002"}
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_article_url("art-sn-002")).mock(
                return_value=httpx.Response(200, json={"result": {"text": "<p>No links</p>"}})
            )
            patch_route = mock.patch(_article_url("art-sn-002")).mock(
                return_value=httpx.Response(200, json={"result": {}})
            )
            n = await _conn().deferred_link_fixup("run-1", link_map)
        assert n == 0
        assert not patch_route.called

    async def test_empty_link_map_returns_zero(self):
        n = await _conn().deferred_link_fixup("run-1", {})
        assert n == 0
