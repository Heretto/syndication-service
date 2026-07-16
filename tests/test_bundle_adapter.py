"""Tests for the Bundle source adapter stub — TDD step 13.

The Bundle adapter is a placeholder for future DITA-OT bundle (zip) support.
All non-trivial methods raise NotImplementedError so the pipeline fails loudly.
"""
from __future__ import annotations

import pytest

from syndication.source.interface import ISourceAdapter
from syndication.source.bundle.adapter import BundleAdapter


class TestBundleAdapterContract:
    def test_is_isource_adapter(self):
        assert isinstance(BundleAdapter(), ISourceAdapter)

    def test_adapter_id(self):
        assert BundleAdapter.adapter_id == "bundle"

    async def test_get_snapshot_token_raises(self):
        with pytest.raises(NotImplementedError):
            await BundleAdapter().get_snapshot_token()

    async def test_get_all_hrefs_raises(self):
        with pytest.raises(NotImplementedError):
            await BundleAdapter().get_all_hrefs()

    async def test_get_changed_raises(self):
        with pytest.raises(NotImplementedError):
            await BundleAdapter().get_changed(since=None)

    async def test_get_page_raises(self):
        with pytest.raises(NotImplementedError):
            await BundleAdapter().get_page("help/topic")

    async def test_fetch_binary_raises(self):
        with pytest.raises(NotImplementedError):
            await BundleAdapter().fetch_binary("https://example.com/img.png")
