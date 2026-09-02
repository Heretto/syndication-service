"""Tests for GET /fields/source and GET /fields/target routes.

SF HTTP calls are mocked with respx; credential loading is patched so no
real DB is required.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from syndication.routes.fields import router as fields_router

ORG_UUID = uuid.UUID("00000000-0000-0000-0000-000000000abc")
SF_INSTANCE = "https://testorg.my.salesforce.com"
API_VER = "65.0"
ACCESS_TOKEN = "test-token-xyz"
KAV_TYPE = "Knowledge__kav"

# Credentials dict that _load_creds would return for a Salesforce credential
GOOD_CREDS = {
    "instance_url": SF_INSTANCE,
    "api_version": API_VER,
    "access_token": ACCESS_TOKEN,
    "knowledge_type": KAV_TYPE,
}

DESCRIBE_URL = f"{SF_INSTANCE}/services/data/v{API_VER}/sobjects/{KAV_TYPE}/describe"

# Minimal describe response from Salesforce
DESCRIBE_PAYLOAD = {
    "fields": [
        {"name": "Id",          "label": "Record ID",     "type": "id",       "createable": False, "updateable": False, "autoNumber": False, "calculated": False},
        {"name": "Title",       "label": "Title",         "type": "string",   "createable": True,  "updateable": True,  "autoNumber": False, "calculated": False},
        {"name": "Answer__c",   "label": "Answer",        "type": "textarea", "createable": True,  "updateable": True,  "autoNumber": False, "calculated": False},
        {"name": "Summary__c",  "label": "Summary",       "type": "string",   "createable": True,  "updateable": True,  "autoNumber": False, "calculated": False},
        {"name": "AccountId",   "label": "Account",       "type": "reference","createable": True,  "updateable": True,  "autoNumber": False, "calculated": False},
        {"name": "AutoNum__c",  "label": "Auto Number",   "type": "string",   "createable": False, "updateable": False, "autoNumber": True,  "calculated": False},
        {"name": "Formula__c",  "label": "Computed",      "type": "string",   "createable": False, "updateable": False, "autoNumber": False, "calculated": True},
        {"name": "Section_Path__c", "label": "Section Path", "type": "string","createable": True,  "updateable": True,  "autoNumber": False, "calculated": False},
        {"name": "Sort_Order__c",   "label": "Sort Order",   "type": "double","createable": True,  "updateable": True,  "autoNumber": False, "calculated": False},
    ]
}


# ── Test app helpers ──────────────────────────────────────────────────────────

def _make_mock_context():
    ctx = MagicMock(spec=CurrentUserContext)
    ctx.organization_id = ORG_UUID
    return ctx


def _make_app(session_factory=None) -> FastAPI:
    app = FastAPI()
    app.include_router(fields_router)
    app.dependency_overrides[get_current_active_user_with_org] = _make_mock_context
    app.state.session_factory = session_factory or MagicMock()
    return app


# ── GET /fields/source ────────────────────────────────────────────────────────

class TestGetSourceFields:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(_make_app())

    def test_returns_200(self, client):
        resp = client.get("/fields/source")
        assert resp.status_code == 200

    def test_returns_list(self, client):
        resp = client.get("/fields/source")
        assert isinstance(resp.json(), list)

    def test_each_entry_has_key_and_label(self, client):
        resp = client.get("/fields/source")
        for entry in resp.json():
            assert "key" in entry
            assert "label" in entry

    def test_includes_core_fields(self, client):
        resp = client.get("/fields/source")
        keys = {f["key"] for f in resp.json()}
        assert {"title", "short_description", "html_body", "content_type", "last_modified_iso"} <= keys

    def test_includes_structure_fields(self, client):
        resp = client.get("/fields/source")
        keys = {f["key"] for f in resp.json()}
        assert "section_path" in keys
        assert "sort_order" in keys


# ── GET /fields/target ────────────────────────────────────────────────────────
#
# These tests are async so that respx can intercept the route handler's
# outgoing httpx.AsyncClient calls in the same event loop.  We use
# httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) instead of
# TestClient to avoid the thread boundary that breaks respx interception.

class TestGetTargetFields:
    def _async_client(self, app):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def test_non_salesforce_connector_returns_empty(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value={}):
            async with self._async_client(app) as client:
                resp = await client.get(
                    "/fields/target",
                    params={"credential_id": "cred-1", "connector_id": "noop"},
                )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_invalid_credential_returns_404(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", side_effect=ValueError("not found")):
            async with self._async_client(app) as client:
                resp = await client.get(
                    "/fields/target",
                    params={"credential_id": "bad", "connector_id": "salesforce"},
                )
        assert resp.status_code == 404

    async def test_sf_describe_failure_returns_502(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value=GOOD_CREDS):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(401))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        assert resp.status_code == 502

    async def test_returns_writable_fields(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value=GOOD_CREDS):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(200, json=DESCRIBE_PAYLOAD))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        assert resp.status_code == 200
        api_names = {f["api_name"] for f in resp.json()}
        assert "Title" in api_names
        assert "Answer__c" in api_names
        assert "Summary__c" in api_names
        assert "Section_Path__c" in api_names
        assert "Sort_Order__c" in api_names

    async def test_excludes_id_type_fields(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value=GOOD_CREDS):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(200, json=DESCRIBE_PAYLOAD))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        api_names = {f["api_name"] for f in resp.json()}
        assert "Id" not in api_names

    async def test_excludes_reference_fields(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value=GOOD_CREDS):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(200, json=DESCRIBE_PAYLOAD))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        api_names = {f["api_name"] for f in resp.json()}
        assert "AccountId" not in api_names

    async def test_excludes_auto_number_fields(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value=GOOD_CREDS):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(200, json=DESCRIBE_PAYLOAD))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        api_names = {f["api_name"] for f in resp.json()}
        assert "AutoNum__c" not in api_names

    async def test_excludes_calculated_fields(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value=GOOD_CREDS):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(200, json=DESCRIBE_PAYLOAD))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        api_names = {f["api_name"] for f in resp.json()}
        assert "Formula__c" not in api_names

    async def test_results_sorted_by_label(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value=GOOD_CREDS):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(200, json=DESCRIBE_PAYLOAD))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        labels = [f["label"] for f in resp.json()]
        assert labels == sorted(labels, key=str.lower)

    async def test_each_entry_has_api_name_and_label(self):
        app = _make_app()
        with patch("syndication.routes.fields._load_creds", return_value=GOOD_CREDS):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(200, json=DESCRIBE_PAYLOAD))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        for entry in resp.json():
            assert "api_name" in entry
            assert "label" in entry

    async def test_oauth_flow_acquires_token(self):
        oauth_creds = {
            "instance_url": SF_INSTANCE,
            "api_version": API_VER,
            "client_id": "consumer_key",
            "client_secret": "consumer_secret",
            "knowledge_type": KAV_TYPE,
        }
        app = _make_app()
        token_url = f"{SF_INSTANCE}/services/oauth2/token"
        with patch("syndication.routes.fields._load_creds", return_value=oauth_creds):
            async with self._async_client(app) as client:
                with respx.mock() as mock:
                    mock.post(token_url).mock(
                        return_value=httpx.Response(200, json={"access_token": "oauth-tok"})
                    )
                    mock.get(DESCRIBE_URL).mock(return_value=httpx.Response(200, json={"fields": []}))
                    resp = await client.get(
                        "/fields/target",
                        params={"credential_id": "cred-1", "connector_id": "salesforce"},
                    )
        assert resp.status_code == 200
