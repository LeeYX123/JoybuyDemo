"""变体档案的共享规则（2026-11-27 批次 DA）。

本模块只放**纯函数**，供两处复用：

1. ``catalog/management/commands/backfill_variant_archive.py``：回填
   ``SpuVariantArchive`` 时判定 ``share_metadata``、生成轴值候选；
2. ``catalog/detail_views.py``：``GET /products/<id>?sku=`` 返回档案时挑选
   标题快照、把评分/已售快照转成既有 payload 形状。

``share_metadata`` 的口径（用户 2026-11-27 拍板 + 边界「不确定一律 true」）：

- **True（只切价格/库存/规格）**：族内轴值全是尺码/容量/数量类（服装
  XS/S/M/L、140g/300g/600g、2-Pack、76.5 x 48.5 ...）；
- **False（整套切换）**：族内出现 ≥2 种颜色词（Black/White/Grey...），或轴值
  含非尺码描述词（型号、花纹、款式，如 Flamingo/Jungle、Treat Bone/Treat Mat）；
- 其余无法确定的一律 True，原因记 ``uncertain_default``。

判据先剔除颜色词再检查尺码：全部带 ``Multicoloured`` 的包装数量族不会被
误判成颜色差异；只有族内出现多种颜色时才算「外观不同」。
"""

import re

#: 颜色 / 花纹词。命中即「外观不同」，必须整套切换。
COLOUR_WORDS = frozenset(
    """
    black white grey gray silver gold red crimson blue green yellow orange purple
    pink brown beige natural turquoise teal navy cream ivory khaki maroon violet
    indigo magenta cyan rose copper bronze multicoloured multicolor multi-coloured
    clear transparent
    """.split()
)

#: 尺码 / 数量 / 包装词（服装尺码 + 常见包装单位 + 形容词）。
SIZE_WORDS = frozenset(
    """
    xxs xs s m l xl xxl xxxl 2xl 3xl 4xl 5xl small medium med large big mini plus
    x-large xl-large size sizes pack packs count ct pair pairs piece pieces pcs pc
    roll rolls bag bags sheet sheets box boxes bottle bottles tablet tablets
    capsule capsules cap caps sachet sachets serving servings
    of the with x
    """.split()
)

#: 数量/容量类单位（``数字 + 单位`` 的整段匹配，允许 1.2l / 550ML / 40x85g / 2.5kg）。
_UNIT_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*"
    r"(?:ml|cl|l|kg|mg|g|cm|mm|m|in|inch|inches|ft|oz|lb|lbs|"
    r"pcs?|pack|packs|count|ct|pairs?|pieces?|roll|rolls|bag|bags|sheet|sheets|"
    r"box|boxes|bottle|bottles|tablet|tablets|capsule|capsules|cap|caps|"
    r"sachet|sachets|serving|servings|x)$",
    re.IGNORECASE,
)

#: 供批次 DB（未合并族）抽轴值候选用的「数字+单位」片段匹配。
_NUM_UNIT_RE = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ml|cl|l|kg|mg|g|cm|mm|m|in|inch|inches|ft|oz|lb|lbs|"
    r"pcs?|pack|packs|count|ct|pairs?|pieces?|roll|rolls|bag|bags|sheet|sheets|"
    r"box|boxes|bottle|bottles|tablet|tablets|capsule|capsules|cap|caps|"
    r"sachet|sachets|serving|servings)(?![a-z])",
    re.IGNORECASE,
)

_TOKEN_SPLIT_RE = re.compile(r"[\s,;/+()\[\]*-]+")
_SEGMENT_SPLIT_RE = re.compile(r"[-\u2013,()]")
_WORD_SPLIT_RE = re.compile(r"\s+")


def normalise_label(label: str) -> str:
    return re.sub(r"\s+", " ", str(label or "").strip())


def label_tokens(label: str) -> list[str]:
    """小写 token（去掉空格/标点分隔），供常量词剔除与颜色词判定。"""

    return [token for token in _TOKEN_SPLIT_RE.split(str(label or "").casefold()) if token]


def is_size_like(label: str) -> bool:
    """整条标签是否只由尺码/容量/数量构成（不看颜色词，颜色由调用方先剔除）。"""

    text = normalise_label(label).casefold()
    if not text:
        return True
    segments = [seg.strip() for seg in _SEGMENT_SPLIT_RE.split(text) if seg.strip()]
    for segment in segments or [text]:
        if segment in SIZE_WORDS:
            continue
        if _UNIT_RE.match(segment):
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", segment):
            continue
        if re.fullmatch(r"pack of \d+", segment):
            continue
        # 段内多词：「large 9」「small 1 small size」「40 x 85g」。
        words = [word for word in _WORD_SPLIT_RE.split(segment) if word]
        if words and all(
            word in SIZE_WORDS or re.match(r"^\d+(?:\.\d+)?", word) or _UNIT_RE.match(word)
            for word in words
        ):
            continue
        return False
    return True


def _strip_colour_words(label: str) -> str:
    return " ".join(token for token in label_tokens(label) if token not in COLOUR_WORDS)


def _colour_tokens(label: str) -> set[str]:
    return {token for token in label_tokens(label) if token in COLOUR_WORDS}


def classify_share_metadata(axis: str, labels: list[str]) -> tuple[bool, str]:
    """返回 ``(share_metadata, reason)``；True=只换价格/库存/规格（保守）。

    判据（按顺序）：

    1. 去掉颜色词后全部是尺码/数量，且族内只出现 ≤1 种颜色词 → True
       （``Multicoloured`` 这类全族统一的产品描述不算维度）；
    2. 族内出现 ≥2 种颜色词 → False（颜色/花纹不同，外观必变）；
    3. 其余但轴名是 Colour/Style → False（型号/款式差异）；
    4. 剩下的一律 True（尺寸轴出现无法解析的词等，保守不换）。
    """

    labels = [normalise_label(label) for label in labels if normalise_label(label)]
    if not labels:
        return True, "no_labels"
    colours = set().union(*(_colour_tokens(label) for label in labels))
    if all(is_size_like(_strip_colour_words(label)) for label in labels):
        if len(colours) <= 1:
            return True, "size_like"
    if len(colours) >= 2:
        return False, "colour_word"
    if str(axis or "").strip().casefold() in {"colour", "color", "style"}:
        return False, "axis_text"
    return True, "uncertain_default"


def pick_title(snapshots: dict, locale_code: str | None) -> str:
    """从 ``{locale: title}`` 里按「请求语言 → en-GB → 任意」取标题。"""

    if not isinstance(snapshots, dict) or not snapshots:
        return ""
    if locale_code and snapshots.get(locale_code):
        return str(snapshots[locale_code])
    if snapshots.get("en-GB"):
        return str(snapshots["en-GB"])
    for value in snapshots.values():
        if value:
            return str(value)
    return ""


def rating_snapshot_payload(snapshot: dict) -> dict | None:
    """把档案里的评分快照转成详情接口 ``review_summary`` 的形状。"""

    if not isinstance(snapshot, dict):
        return None
    average = snapshot.get("average")
    count = snapshot.get("count") or 0
    if average in (None, "") and not count:
        return None
    return {
        "average": str(average) if average not in (None, "") else None,
        "count": int(count or 0),
        "distribution": snapshot.get("distribution") or {},
        "source": "variant_archive",
    }


def extract_axis_signals(label: str) -> dict:
    """抽一条轴值标签里的数字+单位 / 颜色词 / 其余词（批次 DB 审计用）。

    仅做机械抽取，不做「是否正确」的判断；输出原样写进候选 CSV，便于人工复核。
    """

    text = normalise_label(label)
    numbers = []
    units = []
    for match in _NUM_UNIT_RE.finditer(text):
        numbers.append(match.group("number"))
        units.append(match.group("unit").casefold())
    tokens = label_tokens(text)
    colours = [token for token in tokens if token in COLOUR_WORDS]
    size_words = [token for token in tokens if token in SIZE_WORDS]
    other = [
        token
        for token in tokens
        if token not in COLOUR_WORDS
        and token not in SIZE_WORDS
        and not re.fullmatch(r"\d+(?:\.\d+)?", token)
        and not _UNIT_RE.match(token)
    ]
    return {
        "label": text,
        "numbers": numbers,
        "units": units,
        "colours": colours,
        "size_words": size_words,
        "other_words": other,
    }
