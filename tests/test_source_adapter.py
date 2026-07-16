"""Tests for syndication/source/interface.py (TDD step 2a)."""
import pytest

from syndication.ir.types import ChangeSet, IRPage
from syndication.source.interface import ISourceAdapter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ir_page() -> IRPage:
    return IRPage(
        uuid="test-uuid",
        href="some/path",
        title="T",
        short_description="S",
        html_body="<p>B</p>",
        content_type="Concept",
        last_modified_ms=0,
        last_modified_iso="1970-01-01T00:00:00.000Z",
        source_adapter_id="test",
        source_organization_id="org",
        source_deployment_id="dep",
    )


class ConcreteAdapter(ISourceAdapter):
    """Minimal concrete adapter used only in tests."""

    adapter_id = "test-adapter"

    async def get_snapshot_token(self) -> str:
        return "tok"

    async def get_all_hrefs(self) -> list[str]:
        return ["path/a", "path/b"]

    async def get_changed(self, since: str | None) -> ChangeSet:
        return ChangeSet(changed=[], removed_uuids=[], high_water_mark="")

    async def get_page(self, href: str) -> IRPage:
        return _make_ir_page()

    async def fetch_binary(self, url: str) -> tuple[bytes, str]:
        return b"\x89PNG", "image/png"


# ── ABC contract ──────────────────────────────────────────────────────────────

class TestISourceAdapterABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            ISourceAdapter()  # type: ignore[abstract]

    def test_missing_one_method_raises(self):
        class Bad(ISourceAdapter):
            adapter_id = "bad"
            async def get_snapshot_token(self): return ""
            async def get_all_hrefs(self): return []
            async def get_changed(self, since): return ChangeSet([], [], "")
            async def get_page(self, href): return _make_ir_page()
            # fetch_binary intentionally omitted

        with pytest.raises(TypeError):
            Bad()

    def test_concrete_adapter_is_instance(self):
        adapter = ConcreteAdapter()
        assert isinstance(adapter, ISourceAdapter)

    def test_adapter_id_class_attribute(self):
        assert ConcreteAdapter.adapter_id == "test-adapter"
        assert ConcreteAdapter().adapter_id == "test-adapter"


# ── Abstract method signatures ────────────────────────────────────────────────

class TestISourceAdapterMethods:
    @pytest.fixture
    def adapter(self) -> ConcreteAdapter:
        return ConcreteAdapter()

    async def test_get_snapshot_token_returns_str(self, adapter):
        token = await adapter.get_snapshot_token()
        assert isinstance(token, str)

    async def test_get_all_hrefs_returns_list(self, adapter):
        hrefs = await adapter.get_all_hrefs()
        assert isinstance(hrefs, list)
        assert all(isinstance(h, str) for h in hrefs)

    async def test_get_changed_no_since(self, adapter):
        cs = await adapter.get_changed(since=None)
        assert isinstance(cs, ChangeSet)

    async def test_get_changed_with_since(self, adapter):
        cs = await adapter.get_changed(since="2026-07-01T00:00:00.000Z")
        assert isinstance(cs, ChangeSet)

    async def test_get_page_returns_ir_page(self, adapter):
        page = await adapter.get_page("some/path")
        assert isinstance(page, IRPage)

    async def test_fetch_binary_returns_bytes_and_mime(self, adapter):
        data, mime = await adapter.fetch_binary("https://example.com/img.png")
        assert isinstance(data, bytes)
        assert isinstance(mime, str)
        assert "/" in mime  # minimal mime-type sanity check
