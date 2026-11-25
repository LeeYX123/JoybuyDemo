"""活动页 / 店铺页结构解析（2026-11-25）。

输入是渲染后的 HTML（真站活动页与店铺页都是客户端渲染，纯 HTTP 拿不到
商品），输出「商品链接清单」结构：

    {
      "hero": "<img url>",
      "blocks": [
        {"type": "banner", "image": "..."},
        {"type": "floor", "title": "...", "products": [
            {"source_id": "100005350090104", "url": "...", "title": "...",
             "image": "...", "price": "..."}
        ]}
      ],
      "products": [...]   # 展平去重后的商品清单（第二阶段按它逐个采详情）
    }

两套页面栈：
- 活动页 ``/campaign/active/<id>``：babel 模块（hotzone / flex_cube /
  pc_custom_code），商品锚点指向 ``m.joybuy.co.uk/dp/<id>``；
- 店铺页 ``/store/<id>``：Next.js 页面，商品锚点同上。

这里的解析只做结构抽取，不做风控判定（调用方负责）。
"""

import html as html_mod
import re

MOD_TEMPLATE_RE = re.compile(r'data-template="([^"]+)"')
DP_URL_RE = re.compile(
    r'(?:https?://(?:www|m)\.joybuy\.co\.uk)?/dp/([^"\'?#]+)', re.IGNORECASE
)
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
IMG_ALT_RE = re.compile(r'<img[^>]+alt="([^"]*)"')
PRICE_RE = re.compile(r'£\s?(\d+(?:[.,]\d{1,2})?)')


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _product_id_from_href(href: str) -> str:
    """``/dp/<slug>/<id>`` 或 ``/dp/<id>`` → 商品 source id（页面 id）。

    店铺页的卡片链接带查询串（``?requestIdentity=storeHomePage``），
    必须先去掉 query/fragment 再按路径分段，否则 ``isdigit`` 判定失败、
    整页商品会被当成 0 个。
    """

    clean = href.split("?", 1)[0].split("#", 1)[0]
    parts = [part for part in clean.split("/") if part]
    if "dp" not in parts:
        return ""
    index = parts.index("dp")
    tail = parts[index + 1 :]
    if not tail:
        return ""
    # 桌面形态 /dp/<slug>/<numeric-id>；移动形态 /dp/<numeric-id>。
    candidate = tail[-1]
    return candidate if candidate.isdigit() else ""


def _split_babel_modules(html: str):
    starts = []
    for match in re.finditer(r'class="bab-opt-mod[^"]*"', html):
        window = html[match.start() : match.start() + 500]
        template = MOD_TEMPLATE_RE.search(window)
        if template:
            starts.append((match.start(), template.group(1)))
    starts.sort()
    for index, (position, template) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(html)
        yield template, html[position:end]


def _cards_in_chunk(chunk: str) -> list[dict]:
    """从一个模块里抽出商品卡（href + alt 标题 + 图 + 价格）。"""

    cards = []
    for match in re.finditer(r'<a\b[^>]*href="([^"]*\/dp\/[^"]*)"[^>]*>(.*?)</a>', chunk, re.S):
        href = match.group(1)
        body = match.group(2)
        source_id = _product_id_from_href(href)
        if not source_id:
            continue
        alt = IMG_ALT_RE.search(body)
        image = IMG_RE.search(body)
        price = PRICE_RE.search(_clean(body))
        cards.append(
            {
                "source_id": source_id,
                "url": href if href.startswith("http") else f"https://www.joybuy.co.uk{href}",
                "title": _clean(alt.group(1)) if alt else "",
                "image": image.group(1) if image else "",
                "price": price.group(1).replace(",", ".") if price else "",
            }
        )
    # 去重（同一商品在同楼层出现两次时保留第一个）
    seen = set()
    unique = []
    for card in cards:
        if card["source_id"] in seen:
            continue
        seen.add(card["source_id"])
        unique.append(card)
    return unique


def parse_activity_page(html: str) -> dict:
    blocks: list[dict] = []
    pending_title = ""
    for template, chunk in _split_babel_modules(html):
        if template == "hotzone":
            image = IMG_RE.search(chunk)
            if image:
                blocks.append({"type": "banner", "image": image.group(1)})
        elif template == "flex_cube":
            span = re.search(r"<span[^>]*>([^<]+)</span>", chunk)
            if span:
                text = _clean(span.group(1))
            else:
                # chunk 从 class="bab-opt-mod... 开始（属性在前），先切掉开标签
                # 再取文本，否则会把 data-* 属性字符串当成标题。
                body = chunk.split(">", 1)[1] if ">" in chunk else chunk
                text = _clean(body)
            if text:
                pending_title = text
                blocks.append(
                    {"type": "floor", "title": text, "products": [], "more": False}
                )
        elif template == "pc_custom_code":
            cards = _cards_in_chunk(chunk)
            if not cards:
                # 只有「查看更多」没有商品的模块（纯按钮/优惠券区）忽略
                continue
            more = bool(re.search(r"(View more|See more|查看更多)", _clean(chunk)))
            if blocks and blocks[-1]["type"] == "floor" and not blocks[-1]["products"]:
                blocks[-1]["products"] = cards
                blocks[-1]["more"] = more
            else:
                blocks.append(
                    {
                        "type": "floor",
                        "title": pending_title,
                        "products": cards,
                        "more": more,
                    }
                )
            pending_title = ""
    hero = next((block["image"] for block in blocks if block["type"] == "banner"), "")
    return {"hero": hero, "blocks": _finalize(blocks)}


def parse_store_page(html: str) -> dict:
    title_match = re.search(r"<title>([^<]*)</title>", html)
    title = _clean(title_match.group(1)) if title_match else ""
    cards = _cards_in_chunk(html)
    # 店铺 banner 只认内容图床（``jfsintlpro-000-da``）；页面里还有 facebook
    # 像素、语言切换的 60x42 国旗小图，取「第一张 joy-sourcing 图」会拿到国旗
    # （2026-11-25：店铺页 hero 成了 60x42，页面顶部一片空白）。
    hero = ""
    for match in IMG_RE.finditer(html):
        src = match.group(1)
        if "jfsintlpro-000-da/" in src:
            hero = src
            break
    if not hero:
        for match in IMG_RE.finditer(html):
            src = match.group(1)
            if "joy-sourcing.com" in src and "s48x48_" not in src and "s96x96_" not in src:
                hero = src
                break
    blocks = [{"type": "floor", "title": "", "products": cards, "more": False}]
    return {"title": title, "hero": hero, "blocks": _finalize(blocks)}


def _finalize(blocks: list[dict]) -> list[dict]:
    cleaned = []
    for block in blocks:
        if block["type"] == "floor" and not block["products"]:
            continue
        cleaned.append(block)
    return cleaned


def parse_page_manifest(html: str, url: str) -> dict:
    """按 URL 判断页面栈并解析；返回 hero/blocks/products 展平清单。"""

    is_store = "/store/" in url
    data = parse_store_page(html) if is_store else parse_activity_page(html)
    products: list[dict] = []
    seen = set()
    for block in data["blocks"]:
        for card in block.get("products") or []:
            if card["source_id"] in seen:
                continue
            seen.add(card["source_id"])
            products.append(card)
    data["products"] = products
    data["product_count"] = len(products)
    return data
