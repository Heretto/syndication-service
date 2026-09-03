"""Low-level HTTP client for the Heretto Deploy API v4.

Each instance is bound to a single deployment.  Authentication is done via the
``X-Deploy-API-Auth`` header.  All methods raise ``httpx.HTTPStatusError`` on
non-2xx responses.
"""
from __future__ import annotations

import httpx


class DeployClient:
    """Thin async wrapper around the Heretto Deploy API v4.

    Args:
        base_url:       ``https://{orgId}.deploy.heretto.com``
        deployment_id:  The deployment identifier.
        api_key:        API key sent in ``X-Deploy-API-Auth``.
        audience:       Audience filter appended to the ``changed_content`` query.
                        ``None`` (default) omits the parameter entirely.
    """

    def __init__(
        self,
        base_url: str,
        deployment_id: str,
        api_key: str,
        audience: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._deployment_id = deployment_id
        self._audience = audience
        self._headers = {"X-Deploy-API-Auth": api_key, "Accept": "application/json"}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _dep_url(self, path: str) -> str:
        return f"{self._base_url}/v4/deployments/{self._deployment_id}/{path.lstrip('/')}"

    async def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        async with httpx.AsyncClient(headers=self._headers) as http:
            resp = await http.get(url, params=params)
            resp.raise_for_status()
            return resp

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_changed_content(self, since: str | None = None) -> list[dict]:
        """Call ``GET /v4/deployments/{id}/changed_content``.

        Args:
            since: ISO 8601 cursor; when ``None`` all changes are returned.

        Returns:
            Raw list of change-entry dicts from the API.
        """
        params: dict = {}
        if since:
            params["since"] = since
        if self._audience:
            params["audience"] = self._audience
        resp = await self._get(self._dep_url("changed_content"), params=params or None)
        return resp.json()

    async def get_content(self, path: str) -> dict:
        """Call ``GET /v4/deployments/{id}/content?for-path={path}``."""
        resp = await self._get(self._dep_url("content"), params={"for-path": path})
        return resp.json()

    async def get_structure(self) -> dict:
        """Call ``GET /v4/deployments/{id}/structure``."""
        resp = await self._get(self._dep_url("structure"))
        return resp.json()

    async def fetch_binary(self, url: str) -> tuple[bytes, str]:
        """Download an arbitrary URL and return ``(content_bytes, mime_type)``.

        The URL is not required to be under the Deploy API base; binary assets
        often live on a CDN domain with short-lived JWT tokens.
        """
        async with httpx.AsyncClient(headers=self._headers) as http:
            resp = await http.get(url)
            resp.raise_for_status()
        mime = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
        return resp.content, mime
