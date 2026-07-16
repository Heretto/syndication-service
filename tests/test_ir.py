"""Tests for syndication/ir/types.py — run these first (TDD step 1)."""
import pytest

from syndication.ir.types import (
    ChangeSet,
    IRBreadcrumb,
    IRChunkedSection,
    IRPage,
    IRTaxonomyValue,
    IRVersion,
)


# ── IRBreadcrumb ──────────────────────────────────────────────────────────────

class TestIRBreadcrumb:
    def test_required_fields(self):
        bc = IRBreadcrumb(title="Root", href="/root")
        assert bc.title == "Root"
        assert bc.href == "/root"

    def test_optional_defaults(self):
        bc = IRBreadcrumb(title="A", href="/a")
        assert bc.item_type is None
        assert bc.item_id is None
        assert bc.outputclasses == []

    def test_outputclasses_is_not_shared(self):
        bc1 = IRBreadcrumb(title="A", href="/a")
        bc2 = IRBreadcrumb(title="B", href="/b")
        bc1.outputclasses.append("x")
        assert bc2.outputclasses == []

    def test_mutable(self):
        bc = IRBreadcrumb(title="A", href="/a")
        bc.title = "B"
        assert bc.title == "B"

    def test_missing_required_raises(self):
        with pytest.raises(TypeError):
            IRBreadcrumb(title="A")  # missing href


# ── IRTaxonomyValue ───────────────────────────────────────────────────────────

class TestIRTaxonomyValue:
    def test_fields(self):
        tv = IRTaxonomyValue(value="claims", human_readable="Claims Handling")
        assert tv.value == "claims"
        assert tv.human_readable == "Claims Handling"

    def test_human_readable_defaults_to_value(self):
        tv = IRTaxonomyValue(value="claims")
        assert tv.human_readable == "claims"

    def test_equality(self):
        assert IRTaxonomyValue("a", "A") == IRTaxonomyValue("a", "A")
        assert IRTaxonomyValue("a", "A") != IRTaxonomyValue("b", "B")


# ── IRVersion ─────────────────────────────────────────────────────────────────

class TestIRVersion:
    def test_fields(self):
        v = IRVersion(title="v1", href="/v1", version_id="vid1")
        assert v.title == "v1"
        assert v.href == "/v1"
        assert v.version_id == "vid1"

    def test_contained_topic_href_optional(self):
        v = IRVersion(title="v1", href="/v1", version_id="vid1")
        assert v.contained_topic_href is None


# ── IRChunkedSection ──────────────────────────────────────────────────────────

class TestIRChunkedSection:
    def test_fields(self):
        sec = IRChunkedSection(
            uuid="uuid-sec",
            title="Intro",
            topic_id="t1",
        )
        assert sec.uuid == "uuid-sec"
        assert sec.title == "Intro"
        assert sec.topic_id == "t1"

    def test_optional_defaults(self):
        sec = IRChunkedSection(uuid="u", title="T", topic_id="t")
        assert sec.dita_metadata == {}
        assert sec.children == []

    def test_children_not_shared(self):
        s1 = IRChunkedSection(uuid="u1", title="T", topic_id="t")
        s2 = IRChunkedSection(uuid="u2", title="T", topic_id="t")
        s1.children.append("x")
        assert s2.children == []


# ── IRPage ────────────────────────────────────────────────────────────────────

class TestIRPage:
    def _minimal(self, **overrides) -> IRPage:
        base = dict(
            uuid="9e6bc560-0ab7-11ee-b063-0242b23a931f",
            href="agent-portal-help/claims-handling",
            title="Claims Handling",
            short_description="How to handle claims.",
            html_body="<p>Body</p>",
            content_type="Concept",
            last_modified_ms=1_700_000_000_000,
            last_modified_iso="2023-11-14T22:13:20.000Z",
            source_adapter_id="deploy",
            source_organization_id="org123",
            source_deployment_id="dep456",
        )
        base.update(overrides)
        return IRPage(**base)

    def test_required_fields_round_trip(self):
        page = self._minimal()
        assert page.uuid == "9e6bc560-0ab7-11ee-b063-0242b23a931f"
        assert page.href == "agent-portal-help/claims-handling"
        assert page.title == "Claims Handling"
        assert page.content_type == "Concept"
        assert page.last_modified_ms == 1_700_000_000_000
        assert page.source_adapter_id == "deploy"

    def test_list_defaults_empty(self):
        page = self._minimal()
        assert page.breadcrumbs == []
        assert page.taxonomy == {}
        assert page.versions == []
        assert page.chunked_sections == []
        assert page.keywords == []
        assert page.othermetas == []
        assert page.prodinfos == []
        assert page.resource_ids == []
        assert page.binary_urls == []

    def test_list_defaults_not_shared(self):
        p1 = self._minimal()
        p2 = self._minimal()
        p1.keywords.append("foo")
        assert p2.keywords == []

    def test_mutable(self):
        page = self._minimal()
        page.html_body = "<p>Updated</p>"
        assert page.html_body == "<p>Updated</p>"

    def test_taxonomy_dict_with_values(self):
        tv = IRTaxonomyValue(value="claims", human_readable="Claims")
        page = self._minimal(taxonomy={"Department": [tv]})
        assert page.taxonomy["Department"][0].value == "claims"

    def test_breadcrumbs(self):
        bc = IRBreadcrumb(title="Root", href="/")
        page = self._minimal(breadcrumbs=[bc])
        assert len(page.breadcrumbs) == 1
        assert page.breadcrumbs[0].title == "Root"

    def test_missing_required_raises(self):
        with pytest.raises(TypeError):
            IRPage(uuid="u", title="T")  # many missing


# ── ChangeSet ─────────────────────────────────────────────────────────────────

class TestChangeSet:
    def test_fields(self):
        cs = ChangeSet(
            changed=[("uuid-1", "path/one"), ("uuid-2", "path/two")],
            removed_uuids=["uuid-old"],
            high_water_mark="2026-07-14T18:00:43.592Z",
        )
        assert len(cs.changed) == 2
        assert cs.changed[0] == ("uuid-1", "path/one")
        assert cs.removed_uuids == ["uuid-old"]
        assert cs.high_water_mark == "2026-07-14T18:00:43.592Z"

    def test_empty_change_set(self):
        cs = ChangeSet(changed=[], removed_uuids=[], high_water_mark="")
        assert cs.changed == []
        assert cs.removed_uuids == []
        assert cs.high_water_mark == ""

    def test_equality(self):
        cs1 = ChangeSet(changed=[], removed_uuids=[], high_water_mark="t")
        cs2 = ChangeSet(changed=[], removed_uuids=[], high_water_mark="t")
        assert cs1 == cs2
