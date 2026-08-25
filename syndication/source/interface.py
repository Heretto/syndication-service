"""Source adapter interface.

Every source of DITA content (Heretto Deploy API, DITA-OT bundle, etc.)
must implement ISourceAdapter.  The pipeline uses only this interface;
concrete adapters are selected at sync configuration time.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from syndication.ir.types import ChangeSet, IRPage


class ISourceAdapter(ABC):
    """Abstract base class for all source adapters.

    Class attribute ``adapter_id`` must be overridden with a unique string
    that identifies the adapter (e.g. ``"deploy"``, ``"bundle"``).
    """

    adapter_id: str  # override in each concrete subclass

    @abstractmethod
    async def get_snapshot_token(self) -> str:
        """Return an opaque token that identifies the current content snapshot.

        Used for logging / idempotency checks; exact semantics depend on the
        source system.
        """

    @abstractmethod
    async def get_all_hrefs(self) -> list[str]:
        """Return every content path available in the source.

        Used for first-run reconciliation; subsequent runs prefer
        ``get_changed()``.
        """

    @abstractmethod
    async def get_changed(self, since: str | None) -> ChangeSet:
        """Return pages that changed since *since* (ISO 8601) or all pages.

        When *since* is ``None`` the adapter must return the full content set
        (first-run behaviour).  The returned ``ChangeSet.high_water_mark``
        becomes the cursor stored for the next incremental run.
        """

    @abstractmethod
    async def get_page(self, href: str) -> IRPage:
        """Fetch and return a single page as a fully-populated ``IRPage``.

        Must be called within the same executor run as any ``fetch_binary()``
        calls because binary URLs may carry short-lived JWT tokens.
        """

    @abstractmethod
    async def fetch_binary(self, url: str) -> tuple[bytes, str]:
        """Download a binary asset and return ``(content, mime_type)``.

        The caller is responsible for persisting the asset; the adapter only
        performs the network download.
        """

    async def get_all_from_structure(self) -> ChangeSet:
        """Return every available topic as a ChangeSet for a force full resync.

        The default raises ``NotImplementedError``; adapters that support a
        structure/catalogue endpoint should override this.  The returned
        ``ChangeSet.high_water_mark`` should be ``""`` so the executor does not
        advance the incremental cursor after a forced resync.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support structure-based full resync."
        )
