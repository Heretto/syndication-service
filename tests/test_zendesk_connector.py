"""Tests for the Zendesk Guide connector.

Zendesk HTTP calls are mocked with respx; no real credentials required.

Design:
  - Upsert strategy: label-based search using ``heretto-{uuid}`` label.
  - Search: GET /api/v2/help_center/articles/search?label_names=heretto-{uuid}
  - Create: POST /api/v2/help_center/{locale}/sections/{section_id}/articles
  - Update: PUT  /api/v2/help_center/{locale}/articles/{id}
  - Publish: PUT  /api/v2/help_center/{locale}/articles/{id} (draft=false)
  - Archive: DELETE /api/v2/help_center/articles/{id}
  - Auth: Bearer token in Authorization header.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from syndication.connector.interface import ITargetConnector, UpsertResult, ValidationError
from syndication.connector.zendesk.connector import ZendeskConnector
from syndication.ir.types import IRPage

SUBDOMAIN = "mycompany"
ACCESS_TOKEN = "zd-bearer-token-xyz"
SECTION_ID = "12345"
LOCALE = "en-us"
BASE = f"https://{SUBDOMAIN}.zendesk.com"

FIELD_MAP = {
    "title": "title",
    "html_body": "body",
}

REQUIRED_MAPPING_KEYS = [
    "zd_subdomain",
    "zd_access_token",
    "zd_section_id",
    "field_map",
]

GOOD_MAPPING = {
    "zd_subdomain": SUBDOMAIN,
    "zd_access_token": ACCESS_TOKEN,
    "zd_section_id": SECTION_ID,
    "field_map": FIELD_MAP,
}


def _conn(**overrides) -> ZendeskConnector:
    kwargs = dict(
        subdomain=SUBDOMAIN,
        access_token=ACCESS_TOKEN,
        section_id=SECTION_ID,
        locale=LOCALE,
    )
    kwargs.update(overrides)
    return ZendeskConnector(**kwargs)


def _make_ir(**overrides) -> IRPage:
    base = dict(
        uuid="ir-uuid-001",
        href="help/intro",
        title="Getting Started",
        short_description="An introduction.",
        html_body="<p>Welcome</p>",
        content_type="Concept",
        last_modified_ms=1_700_000_000_000,
        last_modified_iso="2023-11-14T22:13:20.000Z",
        source_adapter_id="deploy",
        source_organization_id="org",
        source_deployment_id="dep",
    )
    base.update(overrides)
    return IRPage(**base)


def _search_url() -> str:
    return f"{BASE}/api/v2/help_center/articles/search"


def _create_url() -> str:
    return f"{BASE}/api/v2/help_center/{LOCALE}/sections/{SECTION_ID}/articles"


def _article_url(article_id: str | int) -> str:
    return f"{BASE}/api/v2/help_center/{LOCALE}/articles/{article_id}"


def _archive_url(article_id: str | int) -> str:
    return f"{BASE}/api/v2/help_center/articles/{article_id}"


# ── ABC membership ─────────────────────────────────────────────────────────────

class TestABCMembership:
    def test_is_instance_of_interface(self):
        assert isinstance(_conn(), ITargetConnector)

    def test_connector_id(self):
        assert ZendeskConnector.connector_id == "zendesk"


# ── validate_mapping ───────────────────────────────────────────────────────────

class TestValidateMapping:
    async def test_valid_mapping_returns_empty(self):
        errors = await _conn().validate_mapping(GOOD_MAPPING)
        assert errors == []

    async def test_missing_subdomain_returns_error(self):
        m = {**GOOD_MAPPING}
        del m["zd_subdomain"]
        errors = await _conn().validate_mapping(m)
        assert any(e.field == "zd_subdomain" for e in errors)

    async def test_missing_access_token_returns_error(self):
        m = {**GOOD_MAPPING}
        del m["zd_access_token"]
        errors = await _conn().validate_mapping(m)
        assert any(e.field == "zd_access_token" for e in errors)

    async def test_missing_section_id_returns_error(self):
        m = {**GOOD_MAPPING}
        del m["zd_section_id"]
        errors = await _conn().validate_mapping(m)
        assert any(e.field == "zd_section_id" for e in errors)

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


# ── upload_binary ─────────────────────────────────────────────────────────────

class TestUploadBinary:
    async def test_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            await _conn().upload_binary("uuid", b"data", "image/png", "img.png")


# ── rewrite_links ─────────────────────────────────────────────────────────────

class TestRewriteLinks:
    async def test_rewrites_href_in_anchor(self):
        html = '<a href="/old">link</a>'
        result = await _conn().rewrite_links(html, {"/old": f"{BASE}/hc/en-us/articles/999"})
        assert f"{BASE}/hc/en-us/articles/999" in result
        assert "/old" not in result

    async def test_unknown_href_left_unchanged(self):
        html = '<a href="/unknown">link</a>'
        result = await _conn().rewrite_links(html, {})
        assert "/unknown" in result

    async def test_empty_html_returns_empty(self):
        result = await _conn().rewrite_links("", {"a": "b"})
        assert result == ""

    async def test_empty_link_map_returns_html_unchanged(self):
        html = '<a href="/foo">bar</a>'
        result = await _conn().rewrite_links(html, {})
        assert "/foo" in result


# ── upsert_article ────────────────────────────────────────────────────────────

class TestUpsertArticle:
    """Search returns empty → POST create; search returns article → PUT update."""

    def _empty_search(self):
        return httpx.Response(200, json={"results": [], "count": 0})

    def _found_search(self, article_id: int = 98765):
        return httpx.Response(200, json={"results": [{"id": article_id}], "count": 1})

    async def test_create_new_article_returns_upsert_result(self):
        ir = _make_ir()
        with respx.mock() as mock:
            mock.get(_search_url()).mock(return_value=self._empty_search())
            mock.post(_create_url()).mock(
                return_value=httpx.Response(201, json={"article": {"id": 11111}})
            )
            result = await _conn().upsert_article(ir, FIELD_MAP)
        assert isinstance(result, UpsertResult)
        assert result.created is True
        assert result.target_article_id == "11111"

    async def test_update_existing_article_returns_upsert_result(self):
        ir = _make_ir()
        with respx.mock() as mock:
            mock.get(_search_url()).mock(return_value=self._found_search(99999))
            mock.put(_article_url(99999)).mock(
                return_value=httpx.Response(200, json={"article": {"id": 99999}})
            )
            result = await _conn().upsert_article(ir, FIELD_MAP)
        assert result.created is False
        assert result.target_article_id == "99999"

    async def test_create_sends_label_with_uuid(self):
        import json as _json
        ir = _make_ir(uuid="uuid-label-test")
        with respx.mock() as mock:
            mock.get(_search_url()).mock(return_value=self._empty_search())
            route = mock.post(_create_url()).mock(
                return_value=httpx.Response(201, json={"article": {"id": 22222}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        payload = _json.loads(route.calls.last.request.content)
        assert "heretto-uuid-label-test" in payload["article"]["label_names"]

    async def test_create_sends_draft_true(self):
        import json as _json
        ir = _make_ir()
        with respx.mock() as mock:
            mock.get(_search_url()).mock(return_value=self._empty_search())
            route = mock.post(_create_url()).mock(
                return_value=httpx.Response(201, json={"article": {"id": 33333}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        payload = _json.loads(route.calls.last.request.content)
        assert payload["article"]["draft"] is True

    async def test_create_sends_title(self):
        import json as _json
        ir = _make_ir(title="My Article")
        with respx.mock() as mock:
            mock.get(_search_url()).mock(return_value=self._empty_search())
            route = mock.post(_create_url()).mock(
                return_value=httpx.Response(201, json={"article": {"id": 44444}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        payload = _json.loads(route.calls.last.request.content)
        assert payload["article"]["title"] == "My Article"

    async def test_create_sends_html_body(self):
        import json as _json
        ir = _make_ir(html_body="<p>Content</p>")
        with respx.mock() as mock:
            mock.get(_search_url()).mock(return_value=self._empty_search())
            route = mock.post(_create_url()).mock(
                return_value=httpx.Response(201, json={"article": {"id": 55555}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        payload = _json.loads(route.calls.last.request.content)
        assert payload["article"]["body"] == "<p>Content</p>"

    async def test_search_uses_label_name_param(self):
        from urllib.parse import unquote
        ir = _make_ir(uuid="search-uuid")
        with respx.mock() as mock:
            route = mock.get(_search_url()).mock(return_value=self._empty_search())
            mock.post(_create_url()).mock(
                return_value=httpx.Response(201, json={"article": {"id": 66666}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        url_str = unquote(str(route.calls.last.request.url))
        assert "heretto-search-uuid" in url_str

    async def test_sends_bearer_auth_on_search(self):
        ir = _make_ir()
        with respx.mock() as mock:
            route = mock.get(_search_url()).mock(return_value=self._empty_search())
            mock.post(_create_url()).mock(
                return_value=httpx.Response(201, json={"article": {"id": 77777}})
            )
            await _conn().upsert_article(ir, FIELD_MAP)
        assert f"Bearer {ACCESS_TOKEN}" in route.calls.last.request.headers.get("Authorization", "")

    async def test_http_error_raises(self):
        ir = _make_ir()
        with respx.mock() as mock:
            mock.get(_search_url()).mock(return_value=httpx.Response(500))
            with pytest.raises(httpx.HTTPStatusError):
                await _conn().upsert_article(ir, FIELD_MAP)


# ── publish_article ───────────────────────────────────────────────────────────

class TestPublishArticle:
    async def test_publish_sets_draft_false(self):
        import json as _json
        with respx.mock() as mock:
            route = mock.put(_article_url("art-001")).mock(
                return_value=httpx.Response(200, json={"article": {"id": "art-001"}})
            )
            await _conn().publish_article("art-001")
        payload = _json.loads(route.calls.last.request.content)
        assert payload["article"]["draft"] is False

    async def test_publish_sends_bearer_auth(self):
        with respx.mock() as mock:
            route = mock.put(_article_url("art-001")).mock(
                return_value=httpx.Response(200, json={"article": {}})
            )
            await _conn().publish_article("art-001")
        assert f"Bearer {ACCESS_TOKEN}" in route.calls.last.request.headers.get("Authorization", "")


# ── archive_article ───────────────────────────────────────────────────────────

class TestArchiveArticle:
    async def test_archive_sends_delete_request(self):
        with respx.mock() as mock:
            route = mock.delete(_archive_url("art-002")).mock(
                return_value=httpx.Response(204)
            )
            await _conn().archive_article("art-002")
        assert route.called

    async def test_archive_sends_bearer_auth(self):
        with respx.mock() as mock:
            route = mock.delete(_archive_url("art-002")).mock(
                return_value=httpx.Response(204)
            )
            await _conn().archive_article("art-002")
        assert f"Bearer {ACCESS_TOKEN}" in route.calls.last.request.headers.get("Authorization", "")


# ── deferred_link_fixup ───────────────────────────────────────────────────────

class TestDeferredLinkFixup:
    async def test_empty_link_map_returns_zero(self):
        n = await _conn().deferred_link_fixup("run-1", {})
        assert n == 0

    async def test_returns_count_of_modified_articles(self):
        import json as _json
        link_map = {"uuid-a": "10001"}
        with respx.mock() as mock:
            mock.get(_article_url("10001")).mock(
                return_value=httpx.Response(
                    200,
                    json={"article": {"id": 10001, "body": '<a href="uuid-a">link</a>'}},
                )
            )
            mock.put(_article_url("10001")).mock(
                return_value=httpx.Response(200, json={"article": {"id": 10001}})
            )
            n = await _conn().deferred_link_fixup("run-1", link_map)
        assert n == 1

    async def test_unchanged_article_not_patched(self):
        link_map = {"uuid-b": "20002"}
        with respx.mock(assert_all_called=False) as mock:
            mock.get(_article_url("20002")).mock(
                return_value=httpx.Response(
                    200, json={"article": {"id": 20002, "body": "<p>No links here</p>"}}
                )
            )
            put_route = mock.put(_article_url("20002")).mock(
                return_value=httpx.Response(200, json={"article": {}})
            )
            n = await _conn().deferred_link_fixup("run-1", link_map)
        assert n == 0
        assert not put_route.called

    async def test_returns_non_negative_int(self):
        with respx.mock() as mock:
            mock.get(_article_url("99")).mock(
                return_value=httpx.Response(200, json={"article": {"id": 99, "body": ""}})
            )
            n = await _conn().deferred_link_fixup("run-1", {"uuid-a": "99"})
        assert isinstance(n, int)
        assert n >= 0
