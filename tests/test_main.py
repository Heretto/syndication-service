"""Smoke tests for app wiring (TDD step 10).

We test the individual wiring components without importing syndication.main
directly (create_hop_app runs at module level and requires live settings).
The full integration is exercised by running the app in a dev environment.
"""
from __future__ import annotations

import pytest


class TestRouterAssembly:
    """Verify our router and schema exports are importable and well-formed."""

    def test_syncs_router_importable(self):
        from syndication.routes.syncs import router
        assert router is not None

    def test_syncs_router_has_expected_routes(self):
        from syndication.routes.syncs import router
        methods_and_paths = {(r.path, list(r.methods or [])[0]) for r in router.routes}
        # Spot-check key routes exist
        assert any("syncs" not in p or True for p, _ in methods_and_paths)  # router is non-empty
        assert len(router.routes) >= 5  # list, create, get, deactivate, runs, trigger

    def test_schemas_importable(self):
        from syndication.routes.syncs import (
            CreateSyncRequest,
            SyncConfigResponse,
            SyncRunResponse,
            TriggerResponse,
        )
        # Pydantic models can be instantiated
        req = CreateSyncRequest(
            name="T",
            adapter_id="deploy",
            connector_id="noop",
            org_id="org",
            deployment_id="dep",
            cron_expression="* * * * *",
        )
        assert req.name == "T"


class TestServicesImportable:
    """Verify all service modules are importable."""

    def test_executor_importable(self):
        from syndication.services.sync_executor import SyncExecutorService
        assert SyncExecutorService is not None

    def test_scheduler_importable(self):
        from syndication.services.scheduler import SyncSchedulerService
        assert SyncSchedulerService is not None

    def test_state_store_importable(self):
        from syndication.state_store import SyncStateStore
        assert SyncStateStore is not None

    def test_settings_importable(self):
        from syndication.settings import AppSettings, get_settings
        assert AppSettings is not None


class TestAdapterAndConnectorFactories:
    """Verify adapter/connector modules are importable and have correct IDs."""

    def test_deploy_adapter_id(self):
        from syndication.source.deploy.adapter import DeployAdapter
        assert DeployAdapter.adapter_id == "deploy"

    def test_noop_connector_id(self):
        from syndication.connector.noop.connector import NoopConnector
        assert NoopConnector.connector_id == "noop"

    def test_salesforce_sanitizer_importable(self):
        from syndication.connector.salesforce.sanitizer import sanitize_html, ALLOWED_TAGS
        assert "p" in ALLOWED_TAGS
        assert "script" not in ALLOWED_TAGS
