"""Bundle source adapter stub.

Placeholder for future DITA-OT bundle (zip file) support.  All non-trivial
methods raise ``NotImplementedError`` so the pipeline fails loudly rather than
silently producing incorrect results.
"""
from __future__ import annotations

from syndication.ir.types import ChangeSet, IRPage
from syndication.source.interface import ISourceAdapter


class BundleAdapter(ISourceAdapter):
    """Stub ISourceAdapter for DITA-OT bundle sources.  Not yet implemented."""

    adapter_id = "bundle"

    async def get_snapshot_token(self) -> str:
        raise NotImplementedError("BundleAdapter.get_snapshot_token is not implemented yet.")

    async def get_all_hrefs(self) -> list[str]:
        raise NotImplementedError("BundleAdapter.get_all_hrefs is not implemented yet.")

    async def get_changed(self, since: str | None) -> ChangeSet:
        raise NotImplementedError("BundleAdapter.get_changed is not implemented yet.")

    async def get_page(self, href: str) -> IRPage:
        raise NotImplementedError("BundleAdapter.get_page is not implemented yet.")

    async def fetch_binary(self, url: str) -> tuple[bytes, str]:
        raise NotImplementedError("BundleAdapter.fetch_binary is not implemented yet.")
