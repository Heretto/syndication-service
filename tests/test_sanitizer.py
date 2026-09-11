"""Tests for Salesforce Knowledge HTML sanitizer (TDD step 4).

The sanitizer must:
  - Keep the Salesforce-allowed tag whitelist
  - Strip every non-whitelisted tag but preserve its text children
  - Strip every attribute not in the per-tag allowlist
  - Remove HTML comments
  - Remove DITA-OT class attributes and xmlns:* attributes
"""
import pytest

from syndication.connector.salesforce.sanitizer import sanitize_html


# ── Tag whitelist ─────────────────────────────────────────────────────────────

class TestTagWhitelist:
    def test_paragraph_kept(self):
        assert "<p>" in sanitize_html("<p>Hello</p>")

    def test_heading_kept(self):
        for n in range(1, 7):
            result = sanitize_html(f"<h{n}>Heading</h{n}>")
            assert f"<h{n}>" in result

    def test_strong_em_kept(self):
        html = "<p><strong>bold</strong> and <em>italic</em></p>"
        result = sanitize_html(html)
        assert "<strong>" in result
        assert "<em>" in result

    def test_lists_kept(self):
        html = "<ul><li>Item A</li><li>Item B</li></ul>"
        result = sanitize_html(html)
        assert "<ul>" in result
        assert "<li>" in result

    def test_ordered_list_kept(self):
        html = "<ol><li>One</li></ol>"
        assert "<ol>" in sanitize_html(html)

    def test_anchor_kept(self):
        html = '<a href="/help/topic">Link</a>'
        result = sanitize_html(html)
        assert "<a " in result
        assert "href" in result

    def test_img_kept(self):
        html = '<img src="https://cdn.example.com/img.png" alt="diagram"/>'
        result = sanitize_html(html)
        assert "<img" in result
        assert "src=" in result

    def test_table_structure_kept(self):
        html = (
            "<table><thead><tr><th>A</th></tr></thead>"
            "<tbody><tr><td>B</td></tr></tbody></table>"
        )
        result = sanitize_html(html)
        for tag in ["table", "thead", "tbody", "tr", "th", "td"]:
            assert f"<{tag}" in result or f"<{tag}>" in result

    def test_strike_s_kept(self):
        assert "<strike>" in sanitize_html("<strike>old</strike>") or \
               "<s>" in sanitize_html("<s>old</s>")

    def test_u_kept(self):
        assert "<u>" in sanitize_html("<u>underline</u>")

    def test_q_kept(self):
        assert "<q>" in sanitize_html("<q>quote</q>")


# ── Tag stripping ─────────────────────────────────────────────────────────────

class TestTagStripping:
    def test_div_stripped_text_preserved(self):
        html = "<div>Keep this text</div>"
        result = sanitize_html(html)
        assert "<div" not in result
        assert "Keep this text" in result

    def test_span_stripped_text_preserved(self):
        html = "<p>Hello <span>world</span></p>"
        result = sanitize_html(html)
        assert "<span" not in result
        assert "world" in result

    def test_section_stripped_children_preserved(self):
        html = "<section><p>Content</p></section>"
        result = sanitize_html(html)
        assert "<section" not in result
        assert "<p>" in result
        assert "Content" in result

    def test_script_stripped_content_also_removed(self):
        html = "<p>Safe</p><script>alert('xss')</script>"
        result = sanitize_html(html)
        assert "<script" not in result
        assert "alert(" not in result

    def test_style_stripped(self):
        html = "<style>body { color: red; }</style><p>Text</p>"
        result = sanitize_html(html)
        assert "<style" not in result

    def test_dita_ot_wrappers_stripped(self):
        # DITA-OT often wraps content in <article>, <section>, <nav>, etc.
        html = "<article><p>Body</p></article>"
        result = sanitize_html(html)
        assert "<article" not in result
        assert "<p>" in result


# ── Attribute filtering ───────────────────────────────────────────────────────

class TestAttributeFiltering:
    def test_class_attribute_removed(self):
        html = '<p class="topic/concept">Text</p>'
        result = sanitize_html(html)
        assert "class=" not in result
        assert "Text" in result

    def test_dita_ot_outputclass_removed(self):
        html = '<p outputclass="note">Note text</p>'
        result = sanitize_html(html)
        assert "outputclass" not in result

    def test_id_attribute_removed_from_p(self):
        # <p> does not need an id in SF Knowledge
        html = '<p id="para-1">Text</p>'
        result = sanitize_html(html)
        assert 'id=' not in result

    def test_href_kept_on_anchor(self):
        html = '<a href="/help/topic" class="link">Link</a>'
        result = sanitize_html(html)
        assert 'href=' in result
        assert 'class=' not in result

    def test_src_alt_kept_on_img(self):
        html = '<img src="img.png" alt="desc" class="image"/>'
        result = sanitize_html(html)
        assert 'src=' in result
        assert 'alt=' in result
        assert 'class=' not in result

    def test_javascript_href_stripped(self):
        html = '<a href="javascript:alert(1)">click</a>'
        result = sanitize_html(html)
        assert "javascript:" not in result
        assert "click" in result  # text preserved

    def test_data_uri_href_stripped(self):
        html = '<a href="data:text/html,<script>x</script>">click</a>'
        result = sanitize_html(html)
        assert "data:" not in result

    def test_vbscript_href_stripped(self):
        html = '<a href="vbscript:MsgBox(1)">click</a>'
        result = sanitize_html(html)
        assert "vbscript:" not in result

    def test_http_href_kept(self):
        html = '<a href="https://help.example.com/topic">link</a>'
        result = sanitize_html(html)
        assert 'href="https://help.example.com/topic"' in result

    def test_relative_href_kept(self):
        html = '<a href="/help/topic">link</a>'
        result = sanitize_html(html)
        assert 'href="/help/topic"' in result

    def test_javascript_img_src_stripped(self):
        html = '<img src="javascript:alert(1)" alt="x"/>'
        result = sanitize_html(html)
        assert "javascript:" not in result
        assert 'alt="x"' in result

    def test_xmlns_attributes_removed(self):
        html = '<p xmlns:jcm-link-man="urn:x-jcm">Text</p>'
        result = sanitize_html(html)
        assert "xmlns" not in result

    def test_data_attributes_removed(self):
        html = '<p data-ditaval="some-val">Text</p>'
        result = sanitize_html(html)
        assert "data-" not in result


# ── HTML comments ─────────────────────────────────────────────────────────────

class TestComments:
    def test_html_comment_removed(self):
        html = "<p>Visible</p><!-- this is a comment --><p>Also visible</p>"
        result = sanitize_html(html)
        assert "<!--" not in result
        assert "this is a comment" not in result
        assert "Visible" in result


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self):
        assert sanitize_html("") == ""

    def test_plain_text_unchanged(self):
        text = "Just plain text with no tags."
        result = sanitize_html(text)
        assert text in result

    def test_nested_sanitisation(self):
        html = "<div><p><span class='x'>Hello <strong>world</strong></span></p></div>"
        result = sanitize_html(html)
        assert "<div" not in result
        assert "<span" not in result
        assert "<p>" in result
        assert "<strong>" in result
        assert "Hello" in result
        assert "world" in result
