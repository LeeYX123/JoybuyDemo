"""Joybuy category menu extraction (docs/09 §2 口径).

Turns rendered joybuy.co.uk HTML into :class:`MenuNode` trees. Joybuy
encodes its category identity in listing URLs, e.g. ``/s?k=...&l1=1409``
for a first-level channel and ``cid1=/cid2=...`` style facet params for
deeper nodes (docs/09 §2.1: level-3 entries are sometimes cross-catalog
filters). Source ids are stored VERBATIM with their prefix
(``l1:1409``, ``cid2:13159``) — never normalized away.

The extraction is deliberately tolerant: it collects every category-
shaped link and dedupes by source id, keeping the first visible name.
When the live DOM changes, the fixture test fails loudly instead of
silently yielding an empty tree.
"""

import re
from dataclasses import dataclass, field

from parsel import Selector

BASE_URL = "https://www.joybuy.co.uk"

_L1_PATTERN = re.compile(r"[?&]l1=(\d+)")
_FACET_PATTERN = re.compile(r"[?&](cid[1-4]|firstcid)=(\d+)")


@dataclass
class MenuNode:
    name: str
    source_id: str
    source_url: str = ""
    children: list["MenuNode"] = field(default_factory=list)


class MenuStructureChanged(RuntimeError):
    """No category-shaped links were found in the rendered page."""


def _absolute(href: str) -> str:
    href = (href or "").strip()
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"{BASE_URL}{href}"
    return href


def _facet_ids(url: str) -> list[tuple[str, str]]:
    return [(prefix, value) for prefix, value in _FACET_PATTERN.findall(url or "")]


def extract_l1_categories(html: str) -> list[MenuNode]:
    """Collect first-level categories (``l1=`` links) from rendered HTML."""

    selector = Selector(text=html)
    nodes: dict[str, MenuNode] = {}
    order: list[str] = []
    for anchor in selector.css("a[href]"):
        href = anchor.attrib.get("href") or ""
        match = _L1_PATTERN.search(href)
        if not match:
            continue
        source_id = f"l1:{match.group(1)}"
        name = " ".join(anchor.css("::text").getall()).strip() or source_id
        if source_id not in nodes:
            nodes[source_id] = MenuNode(
                name=name, source_id=source_id, source_url=_absolute(href)
            )
            order.append(source_id)
        elif not nodes[source_id].source_url:
            nodes[source_id].source_url = _absolute(href)
    if not nodes:
        raise MenuStructureChanged(
            "No l1= category links found; the Joybuy menu structure may have changed."
        )
    return [nodes[source_id] for source_id in order]


def extract_child_categories(html: str, *, parent: MenuNode) -> list[MenuNode]:
    """Collect facet children (``cid1..cid4`` links) from one L1 page."""

    selector = Selector(text=html)
    nodes: dict[str, MenuNode] = {}
    for anchor in selector.css("a[href]"):
        href = anchor.attrib.get("href") or ""
        if parent.source_url and href.split("#")[0] == parent.source_url.split("#")[0]:
            continue
        facets = _facet_ids(href)
        if not facets:
            continue
        prefix, value = facets[-1]  # deepest prefix wins (cid4 > cid3 > …)
        source_id = f"{prefix}:{value}"
        name = " ".join(anchor.css("::text").getall()).strip()
        if not name or source_id in nodes:
            continue
        nodes[source_id] = MenuNode(
            name=name, source_id=source_id, source_url=_absolute(href)
        )
    return list(nodes.values())


def capture_category_tree(
    *,
    headless: bool = True,
    fetch_children: bool = True,
    render_page=None,
) -> list[MenuNode]:
    """Render the live site and build the L1(+L2) menu tree.

    ``render_page`` is injectable for tests; production passes
    :func:`joybuy_crawler.render.render_page`.
    """

    if render_page is None:
        from joybuy_crawler.render import render_page

    home = render_page(BASE_URL, headless=headless, scroll_for_lazy_load=True)
    if home.error:
        raise RuntimeError(f"Failed to render {BASE_URL}: {home.error}")
    if home.risk_control:
        raise RuntimeError("Joybuy served a risk-control page to the tree sync; stop, no retry.")
    l1_nodes = extract_l1_categories(home.html)
    if not fetch_children:
        return l1_nodes
    for node in l1_nodes:
        child_page = render_page(
            node.source_url, headless=headless, scroll_for_lazy_load=True
        )
        if child_page.error or child_page.risk_control:
            continue  # keep the L1 even when its facet page misbehaves
        node.children = extract_child_categories(child_page.html, parent=node)
    return l1_nodes
