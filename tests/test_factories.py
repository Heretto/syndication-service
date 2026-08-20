"""Tests for the adapter/connector factory helpers — TDD step 14.

Factories load credentials from the DB (via session_factory), decrypt them,
and construct the correct adapter or connector.  The DB lookup and decryption
are mocked so no live DB or encryption key is required.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from syndication.factory import build_adapter, build_connector
from syndication.connector.noop.connector import NoopConnector
from syndication.connector.salesforce.connector import SalesforceConnector
from syndication.connector.zendesk.connector import ZendeskConnector
from syndication.source.deploy.adapter import DeployAdapter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cfg(**overrides) -> MagicMock:
    cfg = MagicMock()
    cfg.org_id = "org-001"
    cfg.deployment_id = "dep-abc"
    cfg.credential_id = "00000000-0000-0000-0000-000000000111"
    cfg.adapter_id = "deploy"
    cfg.connector_id = "salesforce"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_session_factory(decrypted_creds: dict):
    """Return a mock session_factory whose DB lookup yields *decrypted_creds*."""
    mock_cred = MagicMock()

    session = MagicMock()
    session.get = MagicMock(return_value=mock_cred)
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    session_factory = MagicMock(return_value=session)

    # Patch decrypt_credentials so we don't need a real encryption key
    with patch(
        "syndication.factory.decrypt_credentials",
        return_value=decrypted_creds,
    ) as _mock:
        pass  # just to collect the patcher; applied per-test below

    return session_factory, mock_cred


DEPLOY_CREDS = {"api_key": "deploy-key-abc", "audience": "private"}
SF_CREDS = {
    "instance_url": "https://myorg.my.salesforce.com",
    "api_version": "60.0",
    "access_token": "sf-access-token",
    "knowledge_type": "Knowledge__kav",
    "external_id_field": "ExternalId__c",
}


# ── build_adapter ─────────────────────────────────────────────────────────────

class TestBuildAdapter:
    def _call(self, cfg, creds=DEPLOY_CREDS):
        session = MagicMock()
        mock_cred = MagicMock()
        session.get = MagicMock(return_value=mock_cred)
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        sf = MagicMock(return_value=session)
        with patch("syndication.factory.decrypt_credentials", return_value=creds):
            return build_adapter(cfg, sf)

    def test_deploy_returns_deploy_adapter(self):
        cfg = _make_cfg(adapter_id="deploy")
        result = self._call(cfg)
        assert isinstance(result, DeployAdapter)

    def test_deploy_uses_api_key_from_creds(self):
        cfg = _make_cfg(adapter_id="deploy")
        adapter = self._call(cfg, creds={**DEPLOY_CREDS, "api_key": "my-key"})
        assert adapter._client._headers["X-Deploy-API-Auth"] == "my-key"

    def test_deploy_uses_deployment_id_from_cfg(self):
        cfg = _make_cfg(adapter_id="deploy", deployment_id="dep-xyz")
        adapter = self._call(cfg)
        assert adapter._client._deployment_id == "dep-xyz"

    def test_unknown_adapter_raises_value_error(self):
        cfg = _make_cfg(adapter_id="unknown")
        with pytest.raises(ValueError, match="Unknown adapter_id"):
            self._call(cfg)

    def test_missing_credential_id_raises_value_error(self):
        cfg = _make_cfg(adapter_id="deploy", credential_id=None)
        session = MagicMock()
        sf = MagicMock(return_value=session)
        with pytest.raises(ValueError, match="credential_id"):
            build_adapter(cfg, sf)

    def test_credential_not_found_raises_value_error(self):
        cfg = _make_cfg(adapter_id="deploy")
        session = MagicMock()
        session.get = MagicMock(return_value=None)
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        sf = MagicMock(return_value=session)
        with pytest.raises(ValueError, match="not found"):
            build_adapter(cfg, sf)


# ── build_connector ───────────────────────────────────────────────────────────

class TestBuildConnector:
    def _call(self, cfg, creds=SF_CREDS):
        session = MagicMock()
        mock_cred = MagicMock()
        session.get = MagicMock(return_value=mock_cred)
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        sf = MagicMock(return_value=session)
        with patch("syndication.factory.decrypt_credentials", return_value=creds):
            return build_connector(cfg, sf)

    def test_noop_returns_noop_connector(self):
        cfg = _make_cfg(connector_id="noop", credential_id=None)
        session = MagicMock()
        sf = MagicMock(return_value=session)
        result = build_connector(cfg, sf)
        assert isinstance(result, NoopConnector)

    def test_noop_does_not_require_credential(self):
        """NoopConnector has no external system so credential_id is not needed."""
        cfg = _make_cfg(connector_id="noop", credential_id=None)
        session = MagicMock()
        sf = MagicMock(return_value=session)
        build_connector(cfg, sf)  # must not raise

    def test_salesforce_returns_salesforce_connector(self):
        cfg = _make_cfg(connector_id="salesforce")
        result = self._call(cfg)
        assert isinstance(result, SalesforceConnector)

    def test_salesforce_uses_instance_url_from_creds(self):
        cfg = _make_cfg(connector_id="salesforce")
        conn = self._call(cfg, creds={**SF_CREDS, "instance_url": "https://acme.salesforce.com"})
        assert conn._instance_url == "https://acme.salesforce.com"

    def test_salesforce_uses_access_token_from_creds(self):
        cfg = _make_cfg(connector_id="salesforce")
        conn = self._call(cfg, creds={**SF_CREDS, "access_token": "tok-xyz"})
        assert conn._static_token == "tok-xyz"

    def test_salesforce_uses_api_version_from_creds(self):
        cfg = _make_cfg(connector_id="salesforce")
        conn = self._call(cfg, creds={**SF_CREDS, "api_version": "61.0"})
        assert conn._api_version == "61.0"

    def test_salesforce_uses_knowledge_type_from_creds(self):
        cfg = _make_cfg(connector_id="salesforce")
        conn = self._call(cfg, creds={**SF_CREDS, "knowledge_type": "MyKav__kav"})
        assert conn._kav_type == "MyKav__kav"

    def test_salesforce_uses_external_id_field_from_creds(self):
        cfg = _make_cfg(connector_id="salesforce")
        conn = self._call(cfg, creds={**SF_CREDS, "external_id_field": "MyId__c"})
        assert conn._ext_field == "MyId__c"

    def test_unknown_connector_raises_value_error(self):
        cfg = _make_cfg(connector_id="unknown")
        with pytest.raises(ValueError, match="Unknown connector_id"):
            self._call(cfg)

    def test_salesforce_missing_credential_id_raises_value_error(self):
        cfg = _make_cfg(connector_id="salesforce", credential_id=None)
        session = MagicMock()
        sf = MagicMock(return_value=session)
        with pytest.raises(ValueError, match="credential_id"):
            build_connector(cfg, sf)

    def test_zendesk_returns_zendesk_connector(self):
        cfg = _make_cfg(connector_id="zendesk")
        zd_creds = {
            "subdomain": "mycompany",
            "access_token": "zd-token",
            "section_id": "12345",
            "locale": "en-us",
        }
        result = self._call(cfg, creds=zd_creds)
        assert isinstance(result, ZendeskConnector)

    def test_zendesk_uses_subdomain_from_creds(self):
        cfg = _make_cfg(connector_id="zendesk")
        zd_creds = {
            "subdomain": "acme",
            "access_token": "tok",
            "section_id": "1",
            "locale": "en-us",
        }
        conn = self._call(cfg, creds=zd_creds)
        assert conn._subdomain == "acme"

    def test_zendesk_uses_access_token_from_creds(self):
        cfg = _make_cfg(connector_id="zendesk")
        zd_creds = {
            "subdomain": "x",
            "access_token": "my-zd-token",
            "section_id": "1",
            "locale": "en-us",
        }
        conn = self._call(cfg, creds=zd_creds)
        assert conn._access_token == "my-zd-token"

    def test_zendesk_uses_section_id_from_creds(self):
        cfg = _make_cfg(connector_id="zendesk")
        zd_creds = {
            "subdomain": "x",
            "access_token": "tok",
            "section_id": "99887",
            "locale": "en-us",
        }
        conn = self._call(cfg, creds=zd_creds)
        assert conn._section_id == "99887"

    def test_zendesk_defaults_locale_to_en_us(self):
        cfg = _make_cfg(connector_id="zendesk")
        zd_creds = {"subdomain": "x", "access_token": "tok", "section_id": "1"}
        conn = self._call(cfg, creds=zd_creds)
        assert conn._locale == "en-us"

    def test_zendesk_missing_credential_id_raises_value_error(self):
        cfg = _make_cfg(connector_id="zendesk", credential_id=None)
        session = MagicMock()
        sf = MagicMock(return_value=session)
        with pytest.raises(ValueError, match="credential_id"):
            build_connector(cfg, sf)
