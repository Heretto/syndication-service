"""Tests for ITargetConnector ABC and NoopConnector (TDD step 3)."""
import pytest

from syndication.ir.types import IRPage
from syndication.connector.interface import (
    ITargetConnector,
    UpsertResult,
    ValidationError,
)
from syndication.connector.noop.connector import NoopConnector


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ir_page(**overrides) -> IRPage:
    base = dict(
        uuid="page-uuid-001",
        href="some/topic",
        title="Topic Title",
        short_description="Short.",
        html_body="<p>Body</p>",
        content_type="Concept",
        last_modified_ms=0,
        last_modified_iso="1970-01-01T00:00:00.000Z",
        source_adapter_id="deploy",
        source_organization_id="org",
        source_deployment_id="dep",
    )
    base.update(overrides)
    return IRPage(**base)


# ── ValidationError / UpsertResult ────────────────────────────────────────────

class TestValueTypes:
    def test_validation_error_fields(self):
        ve = ValidationError(field="title", message="must not be empty")
        assert ve.field == "title"
        assert ve.message == "must not be empty"

    def test_upsert_result_fields(self):
        ur = UpsertResult(target_article_id="art-001", created=True)
        assert ur.target_article_id == "art-001"
        assert ur.created is True
        assert ur.url is None

    def test_upsert_result_with_url(self):
        ur = UpsertResult(target_article_id="art-002", created=False, url="https://example.com/art-002")
        assert ur.url == "https://example.com/art-002"


# ── ITargetConnector ABC contract ─────────────────────────────────────────────

class TestITargetConnectorABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            ITargetConnector()  # type: ignore[abstract]

    def test_missing_method_raises(self):
        class Partial(ITargetConnector):
            connector_id = "partial"
            async def validate_mapping(self, mapping): return []
            async def sanitize_html(self, html): return html
            async def upload_binary(self, uuid, content, mime_type, filename): return ""
            async def rewrite_links(self, html, link_map): return html
            async def upsert_article(self, ir, mapping): ...
            async def publish_article(self, target_article_id): ...
            # archive_article and deferred_link_fixup omitted

        with pytest.raises(TypeError):
            Partial()

    def test_noop_is_instance(self):
        assert isinstance(NoopConnector(), ITargetConnector)


# ── NoopConnector behaviour ───────────────────────────────────────────────────

class TestNoopConnector:
    @pytest.fixture
    def conn(self) -> NoopConnector:
        return NoopConnector()

    def test_connector_id(self, conn: NoopConnector):
        assert conn.connector_id == "noop"

    async def test_validate_mapping_always_valid(self, conn: NoopConnector):
        errors = await conn.validate_mapping({"any": "mapping"})
        assert errors == []

    async def test_sanitize_html_returns_unchanged(self, conn: NoopConnector):
        html = "<p>Hello <b>world</b></p>"
        result = await conn.sanitize_html(html)
        assert result == html

    async def test_upload_binary_returns_stable_url(self, conn: NoopConnector):
        url = await conn.upload_binary(
            uuid="img-uuid-001",
            content=b"\x89PNG",
            mime_type="image/png",
            filename="diagram.png",
        )
        assert isinstance(url, str)
        assert "img-uuid-001" in url

    async def test_upload_binary_same_uuid_same_url(self, conn: NoopConnector):
        url1 = await conn.upload_binary("u1", b"a", "image/png", "a.png")
        url2 = await conn.upload_binary("u1", b"b", "image/jpeg", "b.jpg")
        assert url1 == url2  # uuid is the stable key

    async def test_rewrite_links_returns_unchanged(self, conn: NoopConnector):
        html = '<a href="/old">link</a>'
        result = await conn.rewrite_links(html, link_map={"/old": "/new"})
        assert result == html  # noop does not rewrite

    async def test_upsert_article_returns_result(self, conn: NoopConnector):
        page = _make_ir_page()
        result = await conn.upsert_article(page, mapping={})
        assert isinstance(result, UpsertResult)
        assert result.target_article_id == page.uuid  # noop uses uuid as target id

    async def test_upsert_article_first_call_is_create(self, conn: NoopConnector):
        page = _make_ir_page(uuid="fresh-uuid")
        result = await conn.upsert_article(page, mapping={})
        assert result.created is True

    async def test_upsert_article_second_call_is_update(self, conn: NoopConnector):
        page = _make_ir_page(uuid="existing-uuid")
        await conn.upsert_article(page, mapping={})   # first → create
        result = await conn.upsert_article(page, mapping={})  # second → update
        assert result.created is False

    async def test_publish_article_records_call(self, conn: NoopConnector):
        await conn.publish_article("art-001")
        assert "art-001" in conn.published_ids

    async def test_archive_article_records_call(self, conn: NoopConnector):
        await conn.archive_article("art-002")
        assert "art-002" in conn.archived_ids

    async def test_deferred_link_fixup_returns_zero(self, conn: NoopConnector):
        n = await conn.deferred_link_fixup(run_id="run-1", link_map={"a": "b"})
        assert n == 0

    async def test_records_are_per_instance(self):
        c1, c2 = NoopConnector(), NoopConnector()
        await c1.publish_article("x")
        assert "x" not in c2.published_ids
