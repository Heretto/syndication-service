"""Routes for dynamic field discovery (source IR fields + target connector fields)."""
from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from syndication.factory import load_creds

log = logging.getLogger(__name__)

router = APIRouter(prefix="/fields", tags=["fields"])

OrgCtx = Annotated[CurrentUserContext, Depends(get_current_active_user_with_org)]

_SOURCE_FIELDS = [
    {"key": "title",             "label": "Article title"},
    {"key": "short_description", "label": "Summary / subtitle"},
    {"key": "html_body",         "label": "Article body (HTML)"},
    {"key": "content_type",      "label": "DITA content type"},
    {"key": "last_modified_iso", "label": "Last modified (ISO 8601)"},
    {"key": "section_path",      "label": "Section breadcrumb (force full only)"},
    {"key": "sort_order",        "label": "Position within section (force full only)"},
]

_SKIP_TYPES = frozenset({
    "id", "reference", "calculated", "anyType",
    "encryptedstring", "masterrecord", "complexvalue",
})


@router.get("/source")
async def get_source_fields(_ctx: OrgCtx):
    """Return all mappable Deploy/IR fields."""
    return _SOURCE_FIELDS


@router.get("/target")
async def get_target_fields(
    req: Request,
    _ctx: OrgCtx,
    credential_id: str,
    connector_id: str,
):
    """Return writable fields for the target connector, fetched live from the target system."""
    if connector_id != "salesforce":
        return []

    try:
        creds = load_creds(
            credential_id,
            req.app.state.session_factory,
            org_id=str(_ctx.organization_id),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    instance_url = creds.get("instance_url", "").rstrip("/")
    api_version = creds.get("api_version", "65.0")
    kav_type = creds.get("knowledge_type", "Knowledge__kav")

    try:
        token = await _get_sf_token(creds, instance_url)
        url = f"{instance_url}/services/data/v{api_version}/sobjects/{kav_type}/describe"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.exception("Salesforce describe failed for credential %s", credential_id)
        raise HTTPException(
            status_code=502,
            detail=f"Salesforce describe failed (HTTP {exc.response.status_code}). Check server logs.",
        )
    except Exception:
        log.exception("Salesforce describe failed for credential %s", credential_id)
        raise HTTPException(status_code=502, detail="Salesforce describe failed. Check server logs.")

    fields = [
        {"api_name": f["name"], "label": f["label"]}
        for f in resp.json().get("fields", [])
        if (f.get("createable") or f.get("updateable"))
        and f.get("type") not in _SKIP_TYPES
        and not f.get("autoNumber")
        and not f.get("calculated")
    ]
    fields.sort(key=lambda f: f["label"].lower())
    return fields


@router.get("/categories/target")
async def get_target_categories(
    req: Request,
    _ctx: OrgCtx,
    credential_id: str,
    connector_id: str,
):
    """Return Salesforce Data Category Groups for the given credential."""
    if connector_id != "salesforce":
        return []

    try:
        creds = load_creds(
            credential_id,
            req.app.state.session_factory,
            org_id=str(_ctx.organization_id),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    instance_url = creds.get("instance_url", "").rstrip("/")
    api_version = creds.get("api_version", "65.0")

    try:
        token = await _get_sf_token(creds, instance_url)
        url = f"{instance_url}/services/data/v{api_version}/support/dataCategoryGroups"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"sObjectName": "KnowledgeArticleVersion"},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.exception("Salesforce category groups failed for credential %s", credential_id)
        raise HTTPException(
            status_code=502,
            detail=f"Salesforce category groups failed (HTTP {exc.response.status_code}). Check server logs.",
        )
    except Exception:
        log.exception("Salesforce category groups failed for credential %s", credential_id)
        raise HTTPException(status_code=502, detail="Salesforce category groups failed. Check server logs.")

    groups = [
        {"name": g["name"], "label": g["label"]}
        for g in resp.json().get("categoryGroups", [])
    ]
    groups.sort(key=lambda g: g["label"].lower())
    return groups


async def _get_sf_token(creds: dict, instance_url: str) -> str:
    if creds.get("access_token"):
        return creds["access_token"]
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{instance_url}/services/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": creds.get("client_id", ""),
                "client_secret": creds.get("client_secret", ""),
            },
        )
        resp.raise_for_status()
    return resp.json()["access_token"]
