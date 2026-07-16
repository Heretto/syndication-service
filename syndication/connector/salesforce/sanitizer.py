"""HTML sanitizer for Salesforce Knowledge.

Salesforce Knowledge accepts only a specific whitelist of HTML tags.
This module strips everything else while preserving the text content of
removed elements, and removes all non-whitelisted attributes.

Allowed tags (per Salesforce Knowledge documentation):
    a, col, colgroup, em, h1–h6, img, li, ol, p, q, s, strike, strong,
    table, tbody, td, tfoot, th, thead, tr, u, ul

References:
    https://help.salesforce.com/articleView?id=knowledge_html_editor.htm
"""
from __future__ import annotations

from lxml import etree, html as lhtml

# Tags to keep (their children and text are preserved)
ALLOWED_TAGS: frozenset[str] = frozenset([
    "a", "col", "colgroup", "em",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "img", "li", "ol", "p", "q", "s", "strike", "strong",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr",
    "u", "ul",
])

# Tags whose content must be destroyed entirely (not just the tag)
_KILL_TAGS: frozenset[str] = frozenset(["script", "style", "head", "meta", "link"])

# Per-tag attribute allowlist; unlisted tags get no attributes
_ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a":        frozenset(["href", "title", "name", "target"]),
    "img":      frozenset(["src", "alt", "width", "height"]),
    "col":      frozenset(["span", "width"]),
    "colgroup": frozenset(["span", "width"]),
    "td":       frozenset(["colspan", "rowspan", "headers"]),
    "th":       frozenset(["colspan", "rowspan", "headers", "scope"]),
    "table":    frozenset(["summary", "width", "border", "cellpadding", "cellspacing"]),
}


def sanitize_html(html_str: str) -> str:
    """Return a sanitised copy of *html_str* safe for Salesforce Knowledge.

    All non-whitelisted tags are unwrapped (their text content is preserved).
    Script and style elements are removed entirely, including their content.
    Non-whitelisted attributes, DITA-OT ``class`` / ``outputclass``, and any
    ``xmlns:*`` namespace declarations are stripped from every element.
    HTML comments are removed.
    """
    if not html_str or not html_str.strip():
        return html_str

    # 1. Wrap in a sentinel <div> so we always have a single root element.
    doc: lhtml.HtmlElement = lhtml.fromstring(f"<div>{html_str}</div>")

    # 2. Kill dangerous tags along with their content.
    #    with_tail=False keeps the text that follows the closing tag.
    etree.strip_elements(doc, *_KILL_TAGS, with_tail=False)

    # 3. Remove HTML comments, preserving any tail text they carry.
    for comment in doc.iter(etree.Comment):
        _merge_tail_and_remove(comment)

    # 4. Collect non-allowed tag names from remaining descendants and unwrap
    #    them (strip_tags keeps text/tail in the parent).
    to_strip: set[str] = set()
    for elem in doc.iter():
        tag = elem.tag
        if isinstance(tag, str) and tag not in ALLOWED_TAGS:
            to_strip.add(tag)

    if to_strip:
        # strip_tags never touches the root element itself (doc), only descendants.
        etree.strip_tags(doc, *to_strip)

    # 5. Clean attributes from all remaining allowed tags.
    for elem in doc.iter():
        if not isinstance(elem.tag, str):
            continue
        allowed = _ALLOWED_ATTRS.get(elem.tag, frozenset())
        for attr in list(elem.attrib):
            if attr not in allowed:
                del elem.attrib[attr]

    # 6. Serialize the inner content of the sentinel <div>.
    inner = (doc.text or "") + "".join(
        lhtml.tostring(child, encoding="unicode") for child in doc
    )
    return inner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _merge_tail_and_remove(elem: etree._Element) -> None:
    """Remove *elem* from its parent, merging its tail into the adjacent text."""
    parent = elem.getparent()
    if parent is None:
        return
    tail = elem.tail or ""
    if tail:
        prev = elem.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(elem)
