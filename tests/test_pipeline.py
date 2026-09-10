"""Tests for the sync pipeline (TDD step 5).

The pipeline orchestrates: Extract → Map → Load → Deferred-fixup.
All I/O is mocked so tests exercise the control-flow only.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syndication.ir.types import ChangeSet, IRPage
from syndication.connector.interface import UpsertResult
from syndication.pipeline.runner import SyncPipeline, PipelineResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_ir_page(uuid: str = "page-uuid", href: str = "some/topic") -> IRPage:
    return IRPage(
        uuid=uuid,
        href=href,
        title="Title",
        short_description="Desc",
        html_body="<div><p>Body</p></div>",
        content_type="Concept",
        last_modified_ms=0,
        last_modified_iso="1970-01-01T00:00:00.000Z",
        source_adapter_id="deploy",
        source_organization_id="org",
        source_deployment_id="dep",
    )


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.adapter_id = "deploy"
    adapter.get_changed = AsyncMock(
        return_value=ChangeSet(
            changed=[("uuid-a", "path/a"), ("uuid-b", "path/b")],
            removed_uuids=["uuid-old"],
            high_water_mark="2026-07-15T10:00:00.000Z",
        )
    )
    adapter.get_page = AsyncMock(side_effect=lambda href: _make_ir_page(
        uuid=f"uuid-{href.split('/')[-1]}",
        href=href,
    ))
    adapter.fetch_binary = AsyncMock(return_value=(b"data", "image/png"))
    return adapter


@pytest.fixture
def mock_connector():
    connector = MagicMock()
    connector.connector_id = "noop"
    connector.sanitize_html = AsyncMock(side_effect=lambda html: html)
    connector.upsert_article = AsyncMock(
        side_effect=lambda ir, mapping: UpsertResult(
            target_article_id=f"target-{ir.uuid}", created=True
        )
    )
    connector.publish_article = AsyncMock()
    connector.archive_article = AsyncMock()
    connector.deferred_link_fixup = AsyncMock(return_value=2)
    connector.sync_data_categories = AsyncMock()
    connector.sync_sibling_relationships = AsyncMock()
    return connector


@pytest.fixture
def pipeline(mock_adapter, mock_connector) -> SyncPipeline:
    return SyncPipeline(
        adapter=mock_adapter,
        connector=mock_connector,
        mapping={"field": "value"},
    )


# ── PipelineResult ────────────────────────────────────────────────────────────

class TestPipelineResult:
    def test_fields(self):
        pr = PipelineResult(
            changed_count=3,
            removed_count=1,
            high_water_mark="2026-07-15T10:00:00.000Z",
            links_fixed=2,
        )
        assert pr.changed_count == 3
        assert pr.removed_count == 1
        assert pr.links_fixed == 2


# ── Extract stage ─────────────────────────────────────────────────────────────

class TestExtract:
    async def test_calls_get_changed_with_since_none(self, pipeline, mock_adapter):
        await pipeline.run(run_id="r1", since=None)
        mock_adapter.get_changed.assert_awaited_once_with(since=None)

    async def test_calls_get_changed_with_since_cursor(self, pipeline, mock_adapter):
        since = "2026-07-14T00:00:00.000Z"
        await pipeline.run(run_id="r1", since=since)
        mock_adapter.get_changed.assert_awaited_once_with(since=since)

    async def test_get_page_called_for_each_changed_item(self, pipeline, mock_adapter):
        await pipeline.run(run_id="r1", since=None)
        # changeset has two changed items: path/a and path/b
        assert mock_adapter.get_page.await_count == 2
        called_hrefs = {call.args[0] for call in mock_adapter.get_page.await_args_list}
        assert called_hrefs == {"path/a", "path/b"}


# ── Map stage ─────────────────────────────────────────────────────────────────

class TestMap:
    async def test_sanitize_html_called_for_each_page(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None)
        assert mock_connector.sanitize_html.await_count == 2

    async def test_sanitize_html_called_with_page_body(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None)
        called_htmls = {call.args[0] for call in mock_connector.sanitize_html.await_args_list}
        # All pages share the same html_body in our fixture
        assert "<div><p>Body</p></div>" in called_htmls


# ── Load stage ────────────────────────────────────────────────────────────────

class TestLoad:
    async def test_upsert_article_called_for_each_page(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None)
        assert mock_connector.upsert_article.await_count == 2

    async def test_upsert_receives_field_map_without_category_map(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None)
        for call in mock_connector.upsert_article.await_args_list:
            _, mapping = call.args
            assert mapping == {"field": "value"}
            assert "category_map" not in mapping

    async def test_publish_called_for_each_upserted_article(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None)
        assert mock_connector.publish_article.await_count == 2

    async def test_publish_called_with_target_id(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None)
        published = {call.args[0] for call in mock_connector.publish_article.await_args_list}
        # target IDs come from upsert_article side_effect: "target-{uuid}"
        assert "target-uuid-a" in published
        assert "target-uuid-b" in published


# ── Archive stage ─────────────────────────────────────────────────────────────

class TestArchive:
    async def test_archive_called_for_removed_uuids(self, pipeline, mock_connector):
        # The changeset has removed_uuids=["uuid-old"]
        await pipeline.run(run_id="r1", since=None, removed_target_ids={"uuid-old": "target-old"})
        mock_connector.archive_article.assert_awaited_once_with("target-old")

    async def test_archive_not_called_when_no_removed(self, pipeline, mock_adapter, mock_connector):
        mock_adapter.get_changed.return_value = ChangeSet(
            changed=[], removed_uuids=[], high_water_mark=""
        )
        await pipeline.run(run_id="r1", since=None)
        mock_connector.archive_article.assert_not_awaited()


# ── Deferred link fixup ───────────────────────────────────────────────────────

class TestDeferredLinkFixup:
    async def test_deferred_fixup_called_once(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None)
        mock_connector.deferred_link_fixup.assert_awaited_once()

    async def test_deferred_fixup_receives_run_id(self, pipeline, mock_connector):
        await pipeline.run(run_id="my-run", since=None)
        call_kwargs = mock_connector.deferred_link_fixup.await_args
        assert call_kwargs.args[0] == "my-run" or call_kwargs.kwargs.get("run_id") == "my-run"

    async def test_deferred_fixup_receives_link_map(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None)
        call_kwargs = mock_connector.deferred_link_fixup.await_args
        link_map = call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("link_map", {})
        # link_map is now keyed by source href (not uuid) for link rewriting
        assert "path/a" in link_map
        assert "path/b" in link_map


# ── PipelineResult values ─────────────────────────────────────────────────────

class TestPipelineResultValues:
    async def test_changed_count(self, pipeline):
        result = await pipeline.run(run_id="r1", since=None)
        assert isinstance(result, PipelineResult)
        assert result.changed_count == 2

    async def test_removed_count(self, pipeline):
        result = await pipeline.run(run_id="r1", since=None, removed_target_ids={"uuid-old": "t-old"})
        assert result.removed_count == 1

    async def test_high_water_mark_from_changeset(self, pipeline):
        result = await pipeline.run(run_id="r1", since=None)
        assert result.high_water_mark == "2026-07-15T10:00:00.000Z"

    async def test_links_fixed_from_connector(self, pipeline):
        result = await pipeline.run(run_id="r1", since=None)
        assert result.links_fixed == 2

    async def test_empty_changeset_returns_zero_counts(self, pipeline, mock_adapter):
        mock_adapter.get_changed.return_value = ChangeSet(
            changed=[], removed_uuids=[], high_water_mark=""
        )
        result = await pipeline.run(run_id="r1", since=None)
        assert result.changed_count == 0
        assert result.removed_count == 0
        assert result.high_water_mark == ""

    async def test_article_mappings_in_result(self, pipeline):
        result = await pipeline.run(run_id="r1", since=None)
        # changeset has uuid-a → path/a and uuid-b → path/b
        # upsert side_effect: target_article_id = f"target-{ir.uuid}"
        # page uuid is f"uuid-{href.split('/')[-1]}" → uuid-a, uuid-b
        assert "uuid-a" in result.article_mappings
        assert "uuid-b" in result.article_mappings
        assert result.article_mappings["uuid-a"] == "target-uuid-a"
        assert result.article_mappings["uuid-b"] == "target-uuid-b"


# ── Data category sync ────────────────────────────────────────────────────────

class TestDataCategorySync:
    async def test_category_map_not_passed_to_upsert_article(self, mock_adapter, mock_connector):
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"title": "Title", "category_map": {"Audiences": "Audiences"}},
        )
        await pipeline.run(run_id="r1", since=None)

        for call in mock_connector.upsert_article.await_args_list:
            _, field_map = call.args
            assert "category_map" not in field_map
            assert "title" in field_map

    async def test_sync_data_categories_called_once_per_page(self, mock_adapter, mock_connector):
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"title": "Title", "category_map": {"Audiences": "Audiences"}},
        )
        await pipeline.run(run_id="r1", since=None)

        assert mock_connector.sync_data_categories.await_count == 2

    async def test_sync_data_categories_receives_category_map(self, mock_adapter, mock_connector):
        category_map = {"Audiences": "Audiences", "Accounts": "Products"}
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"title": "Title", "category_map": category_map},
        )
        await pipeline.run(run_id="r1", since=None)

        for call in mock_connector.sync_data_categories.await_args_list:
            passed_map = call.args[2] if len(call.args) > 2 else call.kwargs.get("category_map")
            assert passed_map == category_map

    async def test_sync_data_categories_receives_empty_map_when_not_configured(
        self, mock_adapter, mock_connector
    ):
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"title": "Title"},
        )
        await pipeline.run(run_id="r1", since=None)

        for call in mock_connector.sync_data_categories.await_args_list:
            passed_map = call.args[2] if len(call.args) > 2 else call.kwargs.get("category_map", {})
            assert passed_map == {}

    async def test_sync_data_categories_failure_does_not_block_publish(
        self, mock_adapter, mock_connector
    ):
        mock_connector.sync_data_categories = AsyncMock(side_effect=Exception("SF category error"))
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"title": "Title", "category_map": {"Audiences": "Audiences"}},
        )
        await pipeline.run(run_id="r1", since=None)

        assert mock_connector.publish_article.await_count == 2

    async def test_sync_data_categories_called_even_when_update_skipped(
        self, mock_adapter, mock_connector
    ):
        # Categories are independent of the draft/publish cycle — they must be
        # applied even when the article content update was skipped (e.g. the
        # article is already Published and the SF API cannot create a draft).
        mock_connector.upsert_article = AsyncMock(
            return_value=UpsertResult(
                target_article_id="target-skipped", created=False, update_skipped=True
            )
        )
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"title": "Title", "category_map": {"Audiences": "Audiences"}},
        )
        await pipeline.run(run_id="r1", since=None)

        assert mock_connector.sync_data_categories.await_count == 2


# ── Force full resync ─────────────────────────────────────────────────────────

def _make_structure_cs(changed, *, removed_uuids=None, high_water_mark="", entries=None):
    """Helper: build a StructureChangeSet for force_full mocks."""
    from syndication.source.deploy.adapter import StructureChangeSet, StructureEntry
    if entries is None:
        entries = {
            uuid: StructureEntry(uuid=uuid, href=href, section_path=[], sort_order=i + 1, sibling_uuids=[])
            for i, (uuid, href) in enumerate(changed)
        }
    return StructureChangeSet(
        changed=changed,
        removed_uuids=removed_uuids or [],
        high_water_mark=high_water_mark,
        entries=entries,
    )


class TestForceFullResync:
    async def test_force_full_calls_get_all_from_structure(self, mock_adapter, mock_connector):
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=_make_structure_cs([("uuid-a", "path/a")])
        )
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"field": "value"},
        )
        await pipeline.run(run_id="r1", since=None, force_full=True)

        mock_adapter.get_all_from_structure.assert_awaited_once()
        mock_adapter.get_changed.assert_not_awaited()

    async def test_force_full_does_not_call_get_changed(self, mock_adapter, mock_connector):
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=_make_structure_cs([])
        )
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"field": "value"},
        )
        await pipeline.run(run_id="r1", since="2026-01-01T00:00:00.000Z", force_full=True)

        mock_adapter.get_changed.assert_not_awaited()

    async def test_force_full_high_water_mark_is_empty(self, mock_adapter, mock_connector):
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=_make_structure_cs([])
        )
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"field": "value"},
        )
        result = await pipeline.run(run_id="r1", since=None, force_full=True)

        assert result.high_water_mark == ""

    async def test_force_full_false_uses_get_changed(self, pipeline, mock_adapter):
        await pipeline.run(run_id="r1", since=None, force_full=False)

        mock_adapter.get_changed.assert_awaited_once_with(since=None)

    async def test_force_full_upserts_all_structure_pages(self, mock_adapter, mock_connector):
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=_make_structure_cs([("uuid-x", "path/x"), ("uuid-y", "path/y")])
        )
        pipeline = SyncPipeline(
            adapter=mock_adapter,
            connector=mock_connector,
            mapping={"field": "value"},
        )
        result = await pipeline.run(run_id="r1", since=None, force_full=True)

        assert result.changed_count == 2
        assert mock_connector.upsert_article.await_count == 2


# ── Structure enrichment fields ───────────────────────────────────────────────

class TestStructureEnrichmentFields:
    """During force_full runs, IRPages are enriched with section_path and sort_order
    from the StructureChangeSet entries before being passed to upsert_article."""

    async def test_upsert_receives_page_with_section_path(self, mock_adapter, mock_connector):
        from syndication.source.deploy.adapter import StructureChangeSet, StructureEntry
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=StructureChangeSet(
                changed=[("uuid-a", "path/a")],
                removed_uuids=[],
                high_water_mark="",
                entries={
                    "uuid-a": StructureEntry(
                        uuid="uuid-a", href="path/a",
                        section_path=["Getting Started", "Installation"],
                        sort_order=1,
                        sibling_uuids=[],
                    )
                },
            )
        )
        pipeline = SyncPipeline(adapter=mock_adapter, connector=mock_connector, mapping={"field": "value"})
        await pipeline.run(run_id="r1", since=None, force_full=True)

        page_arg = mock_connector.upsert_article.await_args_list[0].args[0]
        assert page_arg.section_path == ["Getting Started", "Installation"]

    async def test_upsert_receives_page_with_sort_order(self, mock_adapter, mock_connector):
        from syndication.source.deploy.adapter import StructureChangeSet, StructureEntry
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=StructureChangeSet(
                changed=[("uuid-a", "path/a"), ("uuid-b", "path/b")],
                removed_uuids=[],
                high_water_mark="",
                entries={
                    "uuid-a": StructureEntry(uuid="uuid-a", href="path/a", section_path=[], sort_order=1, sibling_uuids=[]),
                    "uuid-b": StructureEntry(uuid="uuid-b", href="path/b", section_path=[], sort_order=2, sibling_uuids=[]),
                },
            )
        )
        pipeline = SyncPipeline(adapter=mock_adapter, connector=mock_connector, mapping={"field": "value"})
        await pipeline.run(run_id="r1", since=None, force_full=True)

        pages_by_uuid = {call.args[0].uuid: call.args[0] for call in mock_connector.upsert_article.await_args_list}
        assert pages_by_uuid["uuid-a"].sort_order == 1
        assert pages_by_uuid["uuid-b"].sort_order == 2

    async def test_incremental_sync_pages_have_empty_section_path(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None, force_full=False)
        for call in mock_connector.upsert_article.await_args_list:
            assert call.args[0].section_path == []

    async def test_incremental_sync_pages_have_zero_sort_order(self, pipeline, mock_connector):
        await pipeline.run(run_id="r1", since=None, force_full=False)
        for call in mock_connector.upsert_article.await_args_list:
            assert call.args[0].sort_order == 0


# ── Sibling relationship deferred pass ────────────────────────────────────────

class TestSiblingRelationshipPass:
    """After all articles are upserted during force_full, sibling UUIDs are resolved
    to target article IDs and written via connector.sync_sibling_relationships()."""

    async def test_sync_sibling_relationships_called_for_pages_with_siblings(
        self, mock_adapter, mock_connector
    ):
        from syndication.source.deploy.adapter import StructureChangeSet, StructureEntry
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=StructureChangeSet(
                changed=[("uuid-a", "path/a"), ("uuid-b", "path/b")],
                removed_uuids=[],
                high_water_mark="",
                entries={
                    "uuid-a": StructureEntry(uuid="uuid-a", href="path/a", section_path=[], sort_order=1, sibling_uuids=["uuid-b"]),
                    "uuid-b": StructureEntry(uuid="uuid-b", href="path/b", section_path=[], sort_order=2, sibling_uuids=["uuid-a"]),
                },
            )
        )
        pipeline = SyncPipeline(adapter=mock_adapter, connector=mock_connector, mapping={"field": "value"})
        await pipeline.run(run_id="r1", since=None, force_full=True)

        assert mock_connector.sync_sibling_relationships.await_count == 2

    async def test_sync_sibling_relationships_receives_resolved_target_ids(
        self, mock_adapter, mock_connector
    ):
        from syndication.source.deploy.adapter import StructureChangeSet, StructureEntry
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=StructureChangeSet(
                changed=[("uuid-a", "path/a"), ("uuid-b", "path/b")],
                removed_uuids=[],
                high_water_mark="",
                entries={
                    "uuid-a": StructureEntry(uuid="uuid-a", href="path/a", section_path=[], sort_order=1, sibling_uuids=["uuid-b"]),
                    "uuid-b": StructureEntry(uuid="uuid-b", href="path/b", section_path=[], sort_order=2, sibling_uuids=["uuid-a"]),
                },
            )
        )
        pipeline = SyncPipeline(adapter=mock_adapter, connector=mock_connector, mapping={"field": "value"})
        await pipeline.run(run_id="r1", since=None, force_full=True)

        # upsert side_effect: target_article_id = f"target-{ir.uuid}"
        # page uuid from get_page mock: f"uuid-{href.split('/')[-1]}" → uuid-a, uuid-b
        calls_by_article = {
            call.args[0]: call.args[1]
            for call in mock_connector.sync_sibling_relationships.await_args_list
        }
        assert "target-uuid-b" in calls_by_article["target-uuid-a"]
        assert "target-uuid-a" in calls_by_article["target-uuid-b"]

    async def test_sync_sibling_relationships_not_called_when_no_siblings(
        self, mock_adapter, mock_connector
    ):
        from syndication.source.deploy.adapter import StructureChangeSet, StructureEntry
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=StructureChangeSet(
                changed=[("uuid-a", "path/a")],
                removed_uuids=[],
                high_water_mark="",
                entries={
                    "uuid-a": StructureEntry(uuid="uuid-a", href="path/a", section_path=[], sort_order=1, sibling_uuids=[]),
                },
            )
        )
        pipeline = SyncPipeline(adapter=mock_adapter, connector=mock_connector, mapping={"field": "value"})
        await pipeline.run(run_id="r1", since=None, force_full=True)

        mock_connector.sync_sibling_relationships.assert_not_awaited()

    async def test_sync_sibling_relationships_not_called_on_incremental_run(
        self, pipeline, mock_connector
    ):
        await pipeline.run(run_id="r1", since=None, force_full=False)
        mock_connector.sync_sibling_relationships.assert_not_awaited()

    async def test_sync_sibling_relationships_failure_does_not_block_pipeline(
        self, mock_adapter, mock_connector
    ):
        from syndication.source.deploy.adapter import StructureChangeSet, StructureEntry
        mock_connector.sync_sibling_relationships = AsyncMock(side_effect=Exception("SF error"))
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=StructureChangeSet(
                changed=[("uuid-a", "path/a"), ("uuid-b", "path/b")],
                removed_uuids=[],
                high_water_mark="",
                entries={
                    "uuid-a": StructureEntry(uuid="uuid-a", href="path/a", section_path=[], sort_order=1, sibling_uuids=["uuid-b"]),
                    "uuid-b": StructureEntry(uuid="uuid-b", href="path/b", section_path=[], sort_order=2, sibling_uuids=["uuid-a"]),
                },
            )
        )
        pipeline = SyncPipeline(adapter=mock_adapter, connector=mock_connector, mapping={"field": "value"})
        result = await pipeline.run(run_id="r1", since=None, force_full=True)

        assert result.changed_count == 2
        assert mock_connector.publish_article.await_count == 2

    async def test_sibling_uuids_not_in_link_map_are_skipped(
        self, mock_adapter, mock_connector
    ):
        from syndication.source.deploy.adapter import StructureChangeSet, StructureEntry
        mock_adapter.get_all_from_structure = AsyncMock(
            return_value=StructureChangeSet(
                changed=[("uuid-a", "path/a")],
                removed_uuids=[],
                high_water_mark="",
                entries={
                    "uuid-a": StructureEntry(
                        uuid="uuid-a", href="path/a",
                        section_path=[], sort_order=1,
                        sibling_uuids=["uuid-x"],  # uuid-x not in changeset
                    ),
                },
            )
        )
        pipeline = SyncPipeline(adapter=mock_adapter, connector=mock_connector, mapping={"field": "value"})
        await pipeline.run(run_id="r1", since=None, force_full=True)

        mock_connector.sync_sibling_relationships.assert_not_awaited()
