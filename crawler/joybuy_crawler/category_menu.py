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
import time
from dataclasses import dataclass, field

from parsel import Selector

BASE_URL = "https://www.joybuy.co.uk"

# joybuy.co.uk 把界面语言存在 `_lang` Cookie 里（2026-11-05 现场核对：
# 默认 en_GB；设为 zh_CN 后类目/页面文案整体变中文，URL 与 source id 不变）。
LANG_COOKIE = "_lang"
CHINESE_LOCALE = "zh_CN"

_FACET_PATTERN = re.compile(r"[?&](l[1-4]|cid[1-4]|firstcid)=(\d+)")


def locale_cookies(locale: str) -> list[dict]:
    """Cookie that switches the rendered page to ``locale`` (empty = site default)."""

    if not locale:
        return []
    return [
        {"name": LANG_COOKIE, "value": locale, "domain": ".joybuy.co.uk", "path": "/"}
    ]


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


def extract_l1_channels(html: str) -> list[MenuNode]:
    """Collect the first-level channels (``/minihome/<pagecode>`` links).

    2026-11-05 live structure: the header category row and the Categories
    menu expose 14 channels as ``/minihome/<pagecode>`` links (docs/09's
    ``l1=<id>`` hrefs are no longer in the current UI). The pagecode is
    the verbatim public id: ``minihome:UK-Mini-HP-Electronics``.
    """

    selector = Selector(text=html)
    nodes: dict[str, MenuNode] = {}
    order: list[str] = []
    for anchor in selector.css('a[href*="/minihome/"]'):
        href = (anchor.attrib.get("href") or "").strip()
        code = href.rsplit("/", 1)[-1].split("?")[0]
        if not code:
            continue
        source_id = f"minihome:{code}"
        name = " ".join(anchor.css("::text").getall()).strip() or code
        if source_id not in nodes:
            nodes[source_id] = MenuNode(
                name=name,
                source_id=source_id,
                source_url=_absolute(f"/minihome/{code}"),
            )
            order.append(source_id)
    if not nodes:
        raise MenuStructureChanged(
            "No /minihome/ channel links found; the Joybuy menu structure may have changed."
        )
    return [nodes[source_id] for source_id in order]


def extract_child_categories(html: str, *, parent: MenuNode) -> list[MenuNode]:
    """Collect listing children (``/s?k=...`` links) from a channel page.

    Joybuy encodes deeper categories as ``l1/l2/l3/cidN`` params on
    ``/s?k=`` listing URLs; the deepest param is the verbatim id
    (``l3:1560``, ``cid2:13159``).
    """

    selector = Selector(text=html)
    nodes: dict[str, MenuNode] = {}
    for anchor in selector.css('a[href*="/s?"]'):
        href = (anchor.attrib.get("href") or "").strip()
        facets = _facet_ids(href)
        if not facets:
            continue
        prefix, value = facets[-1]  # deepest prefix wins (cid4 > cid3 > l3 > …)
        source_id = f"{prefix}:{value}"
        name = " ".join(anchor.css("::text").getall()).strip()
        if not name or source_id in nodes:
            continue
        nodes[source_id] = MenuNode(
            name=name, source_id=source_id, source_url=_absolute(href)
        )
    return list(nodes.values())


_MENU_ANCHORS_JS = (
    "return Array.from(document.querySelectorAll('a[href]')).map(a => ({"
    "href: a.getAttribute('href'), text: (a.innerText || '').trim()"
    "}));"
)


def capture_category_tree(
    *,
    headless: bool = True,
    fetch_children: bool = True,
    pause_seconds: float = 5.0,
    render_page=None,
    locale: str = "",
    cookies: list[dict] | None = None,
    profile_dir: str | None = None,
    only_channels: list[str] | None = None,
) -> list[MenuNode]:
    """Capture the live L1 channels (+ their /s?k= children).

    The category row only exists in the SSR payload, which the interactive
    page replaces after hydration; ``render_page`` captures the DOM right
    after navigation, where ``/minihome/`` channel links are present
    (2026-11-05 live evidence). Children come from each channel page.
    A polite pause between renders keeps the burst below the site's rate
    limit (rapid consecutive renders triggered 403s on 2026-11-05).

    ``locale`` sets the ``_lang`` cookie (``zh_CN`` for the Chinese
    category names); ``cookies`` carries a stored account session, which
    the site now requires for anonymous browsing (2026-11-05: channel
    pages 307 to /login without a signed-in session). ``only_channels``
    limits the per-channel renders to the given source ids / minihome
    codes (resumable chunked capture when the site rate-limits).

    The whole capture runs in ONE browser session (2026-11-05 feedback:
    a page-per-browser implementation left dozens of Chrome instances
    around). ``render_page`` is only used by tests/callers that inject a
    fake fetcher; production always goes through ``BrowserSession``.
    """

    request_cookies = list(cookies or []) + locale_cookies(locale)
    session = None
    if render_page is None:
        from joybuy_crawler.render import BrowserSession

        session = BrowserSession(
            headless=headless,
            cookies=request_cookies or None,
            profile_dir=profile_dir,
        )
        session.open()

        def fetch(
            url,
            *,
            headless=False,
            cookies=None,
            profile_dir=None,
            wait_seconds=0.0,
            **kwargs,
        ):
            return session.get(url, wait_seconds=wait_seconds, **kwargs)

    else:
        fetch = render_page

    try:
        home = fetch(
            BASE_URL,
            cookies=request_cookies or None,
            headless=headless,
            wait_seconds=0,
            scroll_for_lazy_load=False,
            profile_dir=profile_dir,
        )
        if home.error:
            raise RuntimeError(f"Failed to render {BASE_URL}: {home.error}")
        if home.risk_control:
            raise RuntimeError(
                "Joybuy served a risk-control page to the tree sync (docs/05 §7.3): "
                "stop retrying; rerun with --headed and complete any verification "
                "manually in the browser window before continuing."
            )
        l1_nodes = extract_l1_channels(home.html)
        if not fetch_children:
            return l1_nodes
        wanted = set(only_channels or [])
        for index, node in enumerate(l1_nodes):
            if (
                wanted
                and node.source_id not in wanted
                and node.source_id.split(":")[-1] not in wanted
            ):
                continue
            if pause_seconds and index:
                time.sleep(pause_seconds)
            child_page = fetch(
                node.source_url,
                cookies=request_cookies or None,
                headless=headless,
                wait_seconds=0,
                capture_ssr=True,
                profile_dir=profile_dir,
            )
            if child_page.error or child_page.risk_control:
                continue  # keep the L1 even when its facet page misbehaves
            node.children = extract_child_categories(child_page.html, parent=node)
        return l1_nodes
    finally:
        if session is not None:
            session.close()
    return l1_nodes
