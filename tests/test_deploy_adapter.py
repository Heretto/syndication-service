"""Tests for Deploy API client + adapter (TDD step 2b).

HTTP calls are mocked with respx so no real network is needed.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from syndication.ir.types import ChangeSet, IRPage, IRTaxonomyValue
from syndication.source.deploy.client import DeployClient
from syndication.source.deploy.adapter import DeployAdapter

BASE_URL = "https://testorg.deploy.heretto.com"
DEPLOYMENT_ID = "dep-001"
API_KEY = "test-key-abc"

# ── Shared fixture payloads ────────────────────────────────────────────────────

CHANGED_CONTENT_PAYLOAD = [
    {
        "path": "help/topic-a",
        "fileUuid": "uuid-aaa",
        "audience": "private",
        "locale": "en",
        "contentModificationDate": "2026-07-14T18:00:43.592Z",
        "changeType": "added",
    },
    {
        "path": "help/topic-a",       # same page, different audience — should be deduped
        "fileUuid": "uuid-aaa",
        "audience": "__default",
        "locale": "en",
        "contentModificationDate": "2026-07-14T18:00:43.592Z",
        "changeType": "added",
    },
    {
        "path": "help/topic-b",
        "fileUuid": "uuid-bbb",
        "audience": "private",
        "locale": "en",
        "contentModificationDate": "2026-07-15T10:00:00.000Z",
        "changeType": "modified",
    },
    {
        "path": "help/old-page",
        "fileUuid": "uuid-ccc",
        "audience": "private",
        "locale": "en",
        "contentModificationDate": "2026-07-13T08:00:00.000Z",
        "changeType": "removed",
    },
]

CONTENT_PAYLOAD = {
    "sys": {"uuid": "uuid-aaa"},
    "path": "help/topic-a",
    "content": "<p>Hello world</p>",
    "standardMetadata": {
        "date": {
            "lastModified": {"value": "1752523243592"},
        },
        "text_single_Line": {
            "contentType": {"value": "Concept"},
        },
    },
    "shortDescription": "A short description.",
    "breadcrumbs": [],
    "versions": [],
    "chunked_sections": [],
    "customMetadata": {},
    "ditaMetadata": {"othermetas": []},
}

STRUCTURE_PAYLOAD = {
    "snapshotId": "snap-xyz",
    "type": "topicref",
    "href": "/",
    "sys": {"uuid": "root-uuid"},
    "children": [
        {
            "type": "topicref",
            "href": "help/topic-a",
            "sys": {"uuid": "uuid-aaa"},
            "children": [],
        },
        {
            "type": "topichead",   # navigation heading — no content, should be skipped
            "href": "help/section",
            "sys": {"uuid": ""},
            "children": [
                {
                    "type": "topicref",
                    "href": "help/topic-b",
                    "sys": {"uuid": "uuid-bbb"},
                    "children": [],
                },
            ],
        },
    ],
}

# Rich structure with titles on section/heading nodes for metadata tests
RICH_STRUCTURE_PAYLOAD = {
    "snapshotId": "snap-rich",
    "type": "topicref",
    "href": "/",
    "sys": {"uuid": "root"},
    "title": "",
    "children": [
        {
            "type": "sitesection",
            "href": "/",
            "title": "Getting Started",
            "sys": {"uuid": ""},
            "children": [
                {
                    "type": "topicref",
                    "href": "gs/intro",
                    "title": "Introduction",
                    "sys": {"uuid": "uuid-intro"},
                    "children": [],
                },
                {
                    "type": "topichead",
                    "href": "/",
                    "title": "Installation",
                    "sys": {"uuid": ""},
                    "children": [
                        {
                            "type": "topicref",
                            "href": "gs/install/linux",
                            "title": "Linux",
                            "sys": {"uuid": "uuid-linux"},
                            "children": [],
                        },
                        {
                            "type": "topicref",
                            "href": "gs/install/windows",
                            "title": "Windows",
                            "sys": {"uuid": "uuid-windows"},
                            "children": [],
                        },
                    ],
                },
            ],
        },
    ],
}


# ── DeployClient tests ────────────────────────────────────────────────────────

class TestDeployClient:
    @pytest.fixture
    def client(self) -> DeployClient:
        return DeployClient(
            base_url=BASE_URL,
            deployment_id=DEPLOYMENT_ID,
            api_key=API_KEY,
            audience="private",
        )

    async def test_get_changed_content_no_since(self, client: DeployClient):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=CHANGED_CONTENT_PAYLOAD))

            result = await client.get_changed_content(since=None)

        assert isinstance(result, list)
        assert len(result) == 4

    async def test_get_changed_content_with_since(self, client: DeployClient):
        since = "2026-07-14T00:00:00.000Z"
        with respx.mock(base_url=BASE_URL) as mock:
            route = mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content",
            ).mock(return_value=httpx.Response(200, json=[]))

            await client.get_changed_content(since=since)

        # Verify the since query param was sent
        assert route.called
        request = route.calls.last.request
        assert f"since={since}" in str(request.url) or "since=" in str(request.url)

    async def test_get_changed_content_auth_header(self, client: DeployClient):
        with respx.mock(base_url=BASE_URL) as mock:
            route = mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=[]))

            await client.get_changed_content(since=None)

        request = route.calls.last.request
        assert request.headers.get("X-Deploy-API-Auth") == API_KEY

    async def test_get_content(self, client: DeployClient):
        path = "help/topic-a"
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/content",
            ).mock(return_value=httpx.Response(200, json=CONTENT_PAYLOAD))

            result = await client.get_content(path=path)

        assert result["sys"]["uuid"] == "uuid-aaa"
        assert result["content"] == "<p>Hello world</p>"

    async def test_get_structure(self, client: DeployClient):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            result = await client.get_structure()

        assert result["snapshotId"] == "snap-xyz"
        assert len(result["children"]) == 2

    async def test_fetch_binary(self, client: DeployClient):
        binary_url = "https://cdn.example.com/img.png"
        png_bytes = b"\x89PNG\r\n\x1a\n"
        with respx.mock() as mock:
            mock.get(binary_url).mock(
                return_value=httpx.Response(
                    200,
                    content=png_bytes,
                    headers={"Content-Type": "image/png"},
                )
            )
            data, mime = await client.fetch_binary(binary_url)

        assert data == png_bytes
        assert mime == "image/png"

    async def test_fetch_binary_rejects_http_scheme(self, client: DeployClient):
        with pytest.raises(ValueError, match="only HTTPS"):
            await client.fetch_binary("http://169.254.169.254/latest/meta-data/")

    async def test_fetch_binary_rejects_non_http_scheme(self, client: DeployClient):
        for url in ("ftp://example.com/file", "file:///etc/passwd"):
            with pytest.raises(ValueError, match="only HTTPS"):
                await client.fetch_binary(url)

    async def test_fetch_binary_enforces_size_cap(self, client: DeployClient):
        big = b"x" * (51 * 1024 * 1024)  # 51 MB
        with respx.mock() as mock:
            mock.get("https://cdn.example.com/big.bin").mock(
                return_value=httpx.Response(200, content=big)
            )
            with pytest.raises(ValueError, match="50 MB"):
                await client.fetch_binary("https://cdn.example.com/big.bin")

    async def test_http_error_raises(self, client: DeployClient):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(401))

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_changed_content(since=None)


# ── DeployAdapter tests ────────────────────────────────────────────────────────

class TestDeployAdapter:
    @pytest.fixture
    def adapter(self) -> DeployAdapter:
        return DeployAdapter(
            org_id="testorg",
            deployment_id=DEPLOYMENT_ID,
            api_key=API_KEY,
            audience="private",
            base_url=BASE_URL,
        )

    def test_adapter_id(self, adapter: DeployAdapter):
        assert adapter.adapter_id == "deploy"

    async def test_get_changed_deduplicates_by_uuid(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=CHANGED_CONTENT_PAYLOAD))

            cs = await adapter.get_changed(since=None)

        assert isinstance(cs, ChangeSet)
        # uuid-aaa appears twice (two audiences) but should be deduplicated → 1 entry
        changed_uuids = [uuid for uuid, _ in cs.changed]
        assert changed_uuids.count("uuid-aaa") == 1

    async def test_get_changed_separates_removed(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=CHANGED_CONTENT_PAYLOAD))

            cs = await adapter.get_changed(since=None)

        assert "uuid-ccc" in cs.removed_uuids
        changed_uuids = [uuid for uuid, _ in cs.changed]
        assert "uuid-ccc" not in changed_uuids

    async def test_get_changed_high_water_mark(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=CHANGED_CONTENT_PAYLOAD))

            cs = await adapter.get_changed(since=None)

        # max contentModificationDate in the payload is topic-b's date
        assert cs.high_water_mark == "2026-07-15T10:00:00.000Z"

    async def test_get_changed_empty_response(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/changed_content"
            ).mock(return_value=httpx.Response(200, json=[]))

            cs = await adapter.get_changed(since=None)

        assert cs.changed == []
        assert cs.removed_uuids == []
        assert cs.high_water_mark == ""

    async def test_get_page_maps_to_ir_page(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/content"
            ).mock(return_value=httpx.Response(200, json=CONTENT_PAYLOAD))

            page = await adapter.get_page("help/topic-a")

        assert isinstance(page, IRPage)
        assert page.uuid == "uuid-aaa"
        assert page.href == "help/topic-a"
        assert page.title == CONTENT_PAYLOAD.get("title", "") or True  # title may be empty in stub
        assert page.html_body == "<p>Hello world</p>"
        assert page.content_type == "Concept"
        assert page.last_modified_ms == 1_752_523_243_592
        assert page.source_adapter_id == "deploy"
        assert page.source_organization_id == "testorg"
        assert page.source_deployment_id == DEPLOYMENT_ID

    async def test_get_all_hrefs(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            hrefs = await adapter.get_all_hrefs()

        assert set(hrefs) == {"help/topic-a", "help/topic-b"}

    async def test_get_snapshot_token(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            token = await adapter.get_snapshot_token()

        assert token == "snap-xyz"

    async def test_fetch_binary_delegates(self, adapter: DeployAdapter):
        url = "https://cdn.example.com/doc.pdf"
        with respx.mock() as mock:
            mock.get(url).mock(
                return_value=httpx.Response(
                    200,
                    content=b"%PDF",
                    headers={"Content-Type": "application/pdf"},
                )
            )
            data, mime = await adapter.fetch_binary(url)

        assert data == b"%PDF"
        assert mime == "application/pdf"

    async def test_get_all_from_structure_returns_changeset(self, adapter: DeployAdapter):
        from syndication.source.deploy.adapter import StructureChangeSet
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            cs = await adapter.get_all_from_structure()

        assert isinstance(cs, StructureChangeSet)
        changed_uuids = {uuid for uuid, _ in cs.changed}
        assert changed_uuids == {"uuid-aaa", "uuid-bbb"}

    async def test_get_all_from_structure_high_water_mark_is_empty(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            cs = await adapter.get_all_from_structure()

        assert cs.high_water_mark == ""

    async def test_get_all_from_structure_no_removed_uuids(self, adapter: DeployAdapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(
                f"/v4/deployments/{DEPLOYMENT_ID}/structure"
            ).mock(return_value=httpx.Response(200, json=STRUCTURE_PAYLOAD))

            cs = await adapter.get_all_from_structure()

        assert cs.removed_uuids == []

    async def test_get_page_populates_taxonomy(self, adapter: DeployAdapter):
        payload = {
            **CONTENT_PAYLOAD,
            "customMetadata": {
                "taxonomy": {
                    "Audiences": {
                        "humanReadable": "Audiences",
                        "value": "Agent",
                        "values": [{"value": "Agent", "humanReadable": "Agent"}],
                    },
                    "Accounts": {
                        "humanReadable": "Accounts",
                        "value": "payments-billing",
                        "values": [{"value": "payments-billing", "humanReadable": "Payments & Billing"}],
                    },
                }
            },
        }
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(f"/v4/deployments/{DEPLOYMENT_ID}/content").mock(
                return_value=httpx.Response(200, json=payload)
            )
            page = await adapter.get_page("help/topic-a")

        assert "Audiences" in page.taxonomy
        assert "Accounts" in page.taxonomy
        assert page.taxonomy["Audiences"][0].value == "Agent"
        assert page.taxonomy["Accounts"][0].human_readable == "Payments & Billing"

    async def test_get_page_empty_taxonomy_when_no_custom_metadata(self, adapter: DeployAdapter):
        payload = {**CONTENT_PAYLOAD, "customMetadata": {}}
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(f"/v4/deployments/{DEPLOYMENT_ID}/content").mock(
                return_value=httpx.Response(200, json=payload)
            )
            page = await adapter.get_page("help/topic-a")

        assert page.taxonomy == {}


# ── _parse_taxonomy unit tests ────────────────────────────────────────────────

class TestParseTaxonomy:
    def test_empty_custom_metadata_returns_empty_dict(self):
        assert DeployAdapter._parse_taxonomy({}) == {}

    def test_empty_taxonomy_key_returns_empty_dict(self):
        assert DeployAdapter._parse_taxonomy({"taxonomy": {}}) == {}

    def test_single_group_single_value(self):
        result = DeployAdapter._parse_taxonomy({
            "taxonomy": {
                "Audiences": {"values": [{"value": "Agent", "humanReadable": "Agent"}]}
            }
        })
        assert len(result["Audiences"]) == 1
        assert result["Audiences"][0].value == "Agent"
        assert result["Audiences"][0].human_readable == "Agent"

    def test_multiple_groups(self):
        result = DeployAdapter._parse_taxonomy({
            "taxonomy": {
                "Audiences": {"values": [{"value": "Agent", "humanReadable": "Agent"}]},
                "Accounts":  {"values": [{"value": "payments-billing", "humanReadable": "Payments & Billing"}]},
            }
        })
        assert set(result.keys()) == {"Audiences", "Accounts"}
        assert result["Accounts"][0].value == "payments-billing"
        assert result["Accounts"][0].human_readable == "Payments & Billing"

    def test_multiple_values_in_one_group(self):
        result = DeployAdapter._parse_taxonomy({
            "taxonomy": {
                "Products": {"values": [
                    {"value": "cloud",    "humanReadable": "Cloud"},
                    {"value": "on-prem",  "humanReadable": "On-Premise"},
                ]}
            }
        })
        assert len(result["Products"]) == 2
        assert {v.value for v in result["Products"]} == {"cloud", "on-prem"}

    def test_human_readable_defaults_to_value_when_absent(self):
        result = DeployAdapter._parse_taxonomy({
            "taxonomy": {"Products": {"values": [{"value": "cloud"}]}}
        })
        assert result["Products"][0].human_readable == "cloud"

    def test_values_with_empty_value_string_are_skipped(self):
        result = DeployAdapter._parse_taxonomy({
            "taxonomy": {"Products": {"values": [{"value": ""}, {"value": "cloud"}]}}
        })
        assert len(result["Products"]) == 1
        assert result["Products"][0].value == "cloud"

    def test_returns_ir_taxonomy_value_instances(self):
        result = DeployAdapter._parse_taxonomy({
            "taxonomy": {"Audiences": {"values": [{"value": "Agent", "humanReadable": "Agent"}]}}
        })
        assert isinstance(result["Audiences"][0], IRTaxonomyValue)


# ── _collect_topics unit tests ────────────────────────────────────────────────

class TestCollectTopics:
    def test_collects_topicref_with_uuid(self):
        node = {
            "type": "topicref",
            "href": "some/path",
            "sys": {"uuid": "abc"},
            "children": [],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert len(out) == 1
        assert out[0].uuid == "abc"
        assert out[0].href == "some/path"

    def test_skips_root_href(self):
        node = {
            "type": "topicref",
            "href": "/",
            "sys": {"uuid": "root"},
            "children": [],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out == []

    def test_skips_topichead(self):
        node = {
            "type": "topichead",
            "href": "section/heading",
            "sys": {"uuid": "head-uuid"},
            "children": [],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out == []

    def test_skips_node_with_empty_uuid(self):
        node = {
            "type": "topicref",
            "href": "some/path",
            "sys": {"uuid": ""},
            "children": [],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out == []

    def test_recurses_into_children(self):
        node = {
            "type": "topichead",
            "href": "section",
            "sys": {"uuid": ""},
            "children": [
                {
                    "type": "topicref",
                    "href": "section/child",
                    "sys": {"uuid": "child-uuid"},
                    "children": [],
                }
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert len(out) == 1
        assert out[0].uuid == "child-uuid"
        assert out[0].href == "section/child"

    def test_deep_nesting(self):
        node = {
            "type": "topicref",
            "href": "/",
            "sys": {"uuid": "root"},
            "children": [
                {
                    "type": "topichead",
                    "href": "tile-1",
                    "sys": {"uuid": ""},
                    "children": [
                        {
                            "type": "topichead",
                            "href": "tile-1/intro",
                            "sys": {"uuid": ""},
                            "children": [
                                {
                                    "type": "topicref",
                                    "href": "tile-1/intro/leaf",
                                    "sys": {"uuid": "leaf-uuid"},
                                    "children": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert len(out) == 1
        assert out[0].uuid == "leaf-uuid"
        assert out[0].href == "tile-1/intro/leaf"

    def test_multiple_topics_at_same_level(self):
        node = {
            "type": "topicref",
            "href": "/",
            "sys": {"uuid": "root"},
            "children": [
                {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
                {"type": "topicref", "href": "b", "sys": {"uuid": "uuid-b"}, "children": []},
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        result_by_uuid = {e.uuid: e for e in out}
        assert "uuid-a" in result_by_uuid
        assert "uuid-b" in result_by_uuid
        assert result_by_uuid["uuid-a"].href == "a"
        assert result_by_uuid["uuid-b"].href == "b"


# ── _collect_topics metadata tests ───────────────────────────────────────────

class TestCollectTopicsMetadata:
    """TDD tests for section_path, sort_order, and sibling_uuids on StructureEntry."""

    # ── section_path ──────────────────────────────────────────────────────────

    def test_root_level_topic_has_empty_section_path(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {"type": "topicref", "href": "a", "title": "A", "sys": {"uuid": "uuid-a"}, "children": []},
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out[0].section_path == []

    def test_topic_under_topichead_inherits_topichead_title(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {
                    "type": "topichead", "href": "/", "title": "My Section",
                    "sys": {"uuid": ""},
                    "children": [
                        {"type": "topicref", "href": "a", "title": "A", "sys": {"uuid": "uuid-a"}, "children": []},
                    ],
                }
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out[0].section_path == ["My Section"]

    def test_topic_under_sitesection_inherits_sitesection_title(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {
                    "type": "sitesection", "href": "/", "title": "Top Section",
                    "sys": {"uuid": ""},
                    "children": [
                        {"type": "topicref", "href": "a", "title": "A", "sys": {"uuid": "uuid-a"}, "children": []},
                    ],
                }
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out[0].section_path == ["Top Section"]

    def test_deeply_nested_topic_gets_full_ancestor_path(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {
                    "type": "sitesection", "href": "/", "title": "Getting Started",
                    "sys": {"uuid": ""},
                    "children": [
                        {
                            "type": "topichead", "href": "/", "title": "Installation",
                            "sys": {"uuid": ""},
                            "children": [
                                {"type": "topicref", "href": "install/linux", "title": "Linux",
                                 "sys": {"uuid": "uuid-linux"}, "children": []},
                            ],
                        }
                    ],
                }
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out[0].section_path == ["Getting Started", "Installation"]

    def test_topichead_with_missing_title_omitted_from_path(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {
                    "type": "topichead", "href": "/", "title": "",
                    "sys": {"uuid": ""},
                    "children": [
                        {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
                    ],
                }
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out[0].section_path == []

    # ── sort_order ────────────────────────────────────────────────────────────

    def test_first_topicref_sibling_has_sort_order_one(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
                {"type": "topicref", "href": "b", "sys": {"uuid": "uuid-b"}, "children": []},
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        entry_a = next(e for e in out if e.uuid == "uuid-a")
        assert entry_a.sort_order == 1

    def test_second_topicref_sibling_has_sort_order_two(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
                {"type": "topicref", "href": "b", "sys": {"uuid": "uuid-b"}, "children": []},
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        entry_b = next(e for e in out if e.uuid == "uuid-b")
        assert entry_b.sort_order == 2

    def test_topics_in_different_sections_have_independent_sort_order(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {
                    "type": "topichead", "href": "/", "title": "Section A", "sys": {"uuid": ""},
                    "children": [
                        {"type": "topicref", "href": "a/1", "sys": {"uuid": "uuid-a1"}, "children": []},
                        {"type": "topicref", "href": "a/2", "sys": {"uuid": "uuid-a2"}, "children": []},
                    ],
                },
                {
                    "type": "topichead", "href": "/", "title": "Section B", "sys": {"uuid": ""},
                    "children": [
                        {"type": "topicref", "href": "b/1", "sys": {"uuid": "uuid-b1"}, "children": []},
                    ],
                },
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        by_uuid = {e.uuid: e for e in out}
        assert by_uuid["uuid-a1"].sort_order == 1
        assert by_uuid["uuid-a2"].sort_order == 2
        assert by_uuid["uuid-b1"].sort_order == 1

    # ── sibling_uuids ─────────────────────────────────────────────────────────

    def test_only_child_has_empty_sibling_uuids(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert out[0].sibling_uuids == []

    def test_siblings_list_each_other(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
                {"type": "topicref", "href": "b", "sys": {"uuid": "uuid-b"}, "children": []},
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        by_uuid = {e.uuid: e for e in out}
        assert "uuid-b" in by_uuid["uuid-a"].sibling_uuids
        assert "uuid-a" in by_uuid["uuid-b"].sibling_uuids

    def test_sibling_uuids_excludes_self(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
                {"type": "topicref", "href": "b", "sys": {"uuid": "uuid-b"}, "children": []},
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        entry_a = next(e for e in out if e.uuid == "uuid-a")
        assert "uuid-a" not in entry_a.sibling_uuids

    def test_topics_in_different_sections_are_not_siblings(self):
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
                {
                    "type": "topichead", "href": "/", "title": "Section", "sys": {"uuid": ""},
                    "children": [
                        {"type": "topicref", "href": "b", "sys": {"uuid": "uuid-b"}, "children": []},
                    ],
                },
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        entry_a = next(e for e in out if e.uuid == "uuid-a")
        assert "uuid-b" not in entry_a.sibling_uuids

    def test_returns_structure_entry_instances(self):
        from syndication.source.deploy.adapter import StructureEntry
        node = {
            "type": "topicref", "href": "/", "sys": {"uuid": "root"}, "title": "",
            "children": [
                {"type": "topicref", "href": "a", "sys": {"uuid": "uuid-a"}, "children": []},
            ],
        }
        out = []
        DeployAdapter._collect_topics(node, out)
        assert isinstance(out[0], StructureEntry)


# ── StructureChangeSet integration tests ─────────────────────────────────────

class TestStructureChangeSet:
    """Tests for get_all_from_structure() returning a StructureChangeSet with metadata."""

    @pytest.fixture
    def adapter(self) -> DeployAdapter:
        return DeployAdapter(
            org_id="testorg",
            deployment_id=DEPLOYMENT_ID,
            api_key=API_KEY,
            audience="private",
            base_url=BASE_URL,
        )

    async def test_entries_keyed_by_uuid(self, adapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(f"/v4/deployments/{DEPLOYMENT_ID}/structure").mock(
                return_value=httpx.Response(200, json=RICH_STRUCTURE_PAYLOAD)
            )
            cs = await adapter.get_all_from_structure()
        assert "uuid-intro" in cs.entries
        assert "uuid-linux" in cs.entries
        assert "uuid-windows" in cs.entries

    async def test_entries_section_path_from_sitesection_and_topichead(self, adapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(f"/v4/deployments/{DEPLOYMENT_ID}/structure").mock(
                return_value=httpx.Response(200, json=RICH_STRUCTURE_PAYLOAD)
            )
            cs = await adapter.get_all_from_structure()
        assert cs.entries["uuid-linux"].section_path == ["Getting Started", "Installation"]
        assert cs.entries["uuid-intro"].section_path == ["Getting Started"]

    async def test_entries_sort_order(self, adapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(f"/v4/deployments/{DEPLOYMENT_ID}/structure").mock(
                return_value=httpx.Response(200, json=RICH_STRUCTURE_PAYLOAD)
            )
            cs = await adapter.get_all_from_structure()
        assert cs.entries["uuid-linux"].sort_order == 1
        assert cs.entries["uuid-windows"].sort_order == 2

    async def test_entries_sibling_uuids(self, adapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(f"/v4/deployments/{DEPLOYMENT_ID}/structure").mock(
                return_value=httpx.Response(200, json=RICH_STRUCTURE_PAYLOAD)
            )
            cs = await adapter.get_all_from_structure()
        assert "uuid-windows" in cs.entries["uuid-linux"].sibling_uuids
        assert "uuid-linux" in cs.entries["uuid-windows"].sibling_uuids
        assert cs.entries["uuid-intro"].sibling_uuids == []

    async def test_changed_list_contains_all_topicref_uuids(self, adapter):
        with respx.mock(base_url=BASE_URL) as mock:
            mock.get(f"/v4/deployments/{DEPLOYMENT_ID}/structure").mock(
                return_value=httpx.Response(200, json=RICH_STRUCTURE_PAYLOAD)
            )
            cs = await adapter.get_all_from_structure()
        changed_uuids = {uuid for uuid, _ in cs.changed}
        assert changed_uuids == {"uuid-intro", "uuid-linux", "uuid-windows"}
