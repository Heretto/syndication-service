"""Tests for stub connectors (Zendesk) — TDD step 12.

Stubs are placeholder implementations that raise NotImplementedError for
every non-trivial operation.  Tests verify the ABC contract is met and that
stub methods raise clearly rather than silently returning wrong data.

ServiceNow was promoted from stub to full implementation in step 15 and is
covered by test_servicenow_connector.py.
"""
from __future__ import annotations

import pytest

from syndication.connector.interface import ITargetConnector
from syndication.connector.zendesk.connector import ZendeskConnector
from syndication.ir.types import IRPage


def _make_ir_page() -> IRPage:
    return IRPage(
        uuid="stub-uuid",
        href="help/topic",
        title="T",
        short_description="S",
        html_body="<p>B</p>",
        content_type="Concept",
        last_modified_ms=0,
        last_modified_iso="1970-01-01T00:00:00.000Z",
        source_adapter_id="deploy",
        source_organization_id="org",
        source_deployment_id="dep",
    )


@pytest.mark.parametrize("ConnectorClass,expected_id", [
    (ZendeskConnector, "zendesk"),
])
class TestStubConnectors:
    def test_is_itarget_connector(self, ConnectorClass, expected_id):
        conn = ConnectorClass()
        assert isinstance(conn, ITargetConnector)

    def test_connector_id(self, ConnectorClass, expected_id):
        assert ConnectorClass.connector_id == expected_id

    async def test_validate_mapping_returns_not_implemented_error(self, ConnectorClass, expected_id):
        conn = ConnectorClass()
        with pytest.raises(NotImplementedError):
            await conn.validate_mapping({})

    async def test_upsert_article_raises_not_implemented(self, ConnectorClass, expected_id):
        conn = ConnectorClass()
        with pytest.raises(NotImplementedError):
            await conn.upsert_article(_make_ir_page(), {})

    async def test_publish_article_raises_not_implemented(self, ConnectorClass, expected_id):
        conn = ConnectorClass()
        with pytest.raises(NotImplementedError):
            await conn.publish_article("art-id")

    async def test_archive_article_raises_not_implemented(self, ConnectorClass, expected_id):
        conn = ConnectorClass()
        with pytest.raises(NotImplementedError):
            await conn.archive_article("art-id")

    async def test_sanitize_html_returns_unchanged(self, ConnectorClass, expected_id):
        """Sanitise is a safe no-op in stubs (no target-specific rules yet)."""
        conn = ConnectorClass()
        html = "<p>Hello</p>"
        result = await conn.sanitize_html(html)
        assert result == html

    async def test_upload_binary_raises_not_implemented(self, ConnectorClass, expected_id):
        conn = ConnectorClass()
        with pytest.raises(NotImplementedError):
            await conn.upload_binary("uuid", b"data", "image/png", "f.png")

    async def test_deferred_link_fixup_returns_zero(self, ConnectorClass, expected_id):
        """Stubs return 0 for deferred fixup (nothing to do)."""
        conn = ConnectorClass()
        n = await conn.deferred_link_fixup("run", {})
        assert n == 0
