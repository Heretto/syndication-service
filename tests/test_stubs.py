"""Tests for stub connectors — TDD step 12.

Stubs are placeholder implementations that raise NotImplementedError for
every non-trivial operation.  Tests verify the ABC contract is met and that
stub methods raise clearly rather than silently returning wrong data.

ServiceNow was promoted from stub to full implementation in step 15 and is
covered by test_servicenow_connector.py.

Zendesk was promoted from stub to full implementation in step 18 and is
covered by test_zendesk_connector.py.
"""
from __future__ import annotations

import pytest

from syndication.connector.interface import ITargetConnector
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


# No connector stubs remain — all connectors have been promoted to full
# implementations.  This file is retained as a placeholder for future stubs.
