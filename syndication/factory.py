"""Adapter and connector factory functions.

Factories load credentials from the DB via *session_factory*, decrypt them
using hop-core's Fernet layer, and construct the correct adapter or connector.
Keeping factory logic here (rather than in main.py) makes it independently
testable without importing the full FastAPI application.
"""
from __future__ import annotations

import uuid as _uuid

from hop_core.core.security import decrypt_credentials
from hop_core.models.credential import Credential
from hop_core.models.enums import CredentialTypeRegistry

from syndication.connector.interface import ITargetConnector
from syndication.connector.noop.connector import NoopConnector
from syndication.connector.salesforce.connector import SalesforceConnector
from syndication.source.deploy.adapter import DeployAdapter
from syndication.source.interface import ISourceAdapter

# Register credential types so the hop-core UI/API surfaces them correctly.
CredentialTypeRegistry.register("deploy", label="Heretto Deploy API")
CredentialTypeRegistry.register("salesforce", label="Salesforce Knowledge")


# ── Internal helpers ──────────────────────────────────────────────────────────

def load_creds(
    credential_id: str | None,
    session_factory,
    org_id: str | None = None,
) -> dict:
    """Load and decrypt a Credential record from the DB.

    Args:
        credential_id: UUID string of the credential to load.
        session_factory: SQLAlchemy sessionmaker.
        org_id: When provided, raises PermissionError if the credential belongs
                to a different organisation (prevents cross-org credential use).

    Raises:
        ValueError:      credential_id is None or record not found.
        PermissionError: credential exists but belongs to a different org.
    """
    if not credential_id:
        raise ValueError(
            "SyncConfig has no credential_id — "
            "associate a credential before running this sync."
        )
    with session_factory() as db:
        cred = db.get(Credential, _uuid.UUID(credential_id))
        if cred is None:
            raise ValueError(
                f"Credential {credential_id!r} not found. "
                "It may have been deleted."
            )
        if org_id is not None and str(cred.organization_id) != org_id:
            raise PermissionError(
                f"Credential {credential_id!r} does not belong to this organisation."
            )
        return decrypt_credentials(cred.encrypted_data)


def check_credential_access(
    credential_id: str | None,
    session_factory,
    org_id: str,
) -> None:
    """Verify credential exists and belongs to org_id without decrypting it.

    Raises:
        ValueError:      credential not found.
        PermissionError: credential belongs to a different org.
    """
    if not credential_id:
        return
    with session_factory() as db:
        cred = db.get(Credential, _uuid.UUID(credential_id))
        if cred is None:
            raise ValueError(f"Credential {credential_id!r} not found.")
        if str(cred.organization_id) != org_id:
            raise PermissionError(
                f"Credential {credential_id!r} does not belong to this organisation."
            )


# ── Public factories ──────────────────────────────────────────────────────────

def build_adapter(cfg, session_factory) -> ISourceAdapter:
    """Construct a source adapter from *cfg*, loading credentials from the DB.

    Args:
        cfg:             A ``SyncConfig`` ORM object.
        session_factory: SQLAlchemy ``sessionmaker`` used to query credentials.

    Raises:
        ValueError: for unknown ``adapter_id`` or missing/invalid credential.
    """
    if cfg.adapter_id == "deploy":
        creds = load_creds(cfg.credential_id, session_factory, org_id=cfg.org_id)
        return DeployAdapter(
            org_id=cfg.org_id,
            deployment_id=cfg.deployment_id or "",
            api_key=creds.get("api_key", ""),
            audience=getattr(cfg, "deploy_audience", None),
            base_url=creds.get("base_url") or None,
        )

    raise ValueError(
        f"Unknown adapter_id: {cfg.adapter_id!r}. "
        f"Supported values: 'deploy'."
    )


def build_connector(cfg, session_factory) -> ITargetConnector:
    """Construct a target connector from *cfg*, loading credentials from the DB.

    Args:
        cfg:             A ``SyncConfig`` ORM object.
        session_factory: SQLAlchemy ``sessionmaker`` used to query credentials.

    Raises:
        ValueError: for unknown ``connector_id`` or missing/invalid credential.
    """
    if cfg.connector_id == "noop":
        return NoopConnector()

    if cfg.connector_id == "salesforce":
        creds = load_creds(cfg.credential_id, session_factory, org_id=cfg.org_id)
        return SalesforceConnector(
            instance_url=creds.get("instance_url", ""),
            api_version=creds.get("api_version", "65.0"),
            access_token=creds.get("access_token", ""),
            client_id=creds.get("client_id", ""),
            client_secret=creds.get("client_secret", ""),
            knowledge_type=creds.get("knowledge_type", "Knowledge__kav"),
            external_id_field=creds.get("external_id_field", "Heretto_UUID__c"),
        )

    raise ValueError(
        f"Unknown connector_id: {cfg.connector_id!r}. "
        f"Supported values: 'noop', 'salesforce'."
    )
