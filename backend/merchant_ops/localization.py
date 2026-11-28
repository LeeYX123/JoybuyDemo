"""商家端商品数据的语言（locale）解析与批量标题本地化。

语言链路：购物端【切换商家端】在 handoff 链接上带 ``?lang=<locale>``，
商家端 boot 落 localStorage 后，每个 API 请求带 ``Accept-Language: <locale>``
（``?lang=`` query 也接受，便于 curl / 手工验证）。这里负责：

1. ``request_locale``：从请求解析商品数据 locale（``?lang=`` 优先，其次
   ``Accept-Language``），并收敛别名（en→en-GB、zh→zh-CN …）；
2. ``pick_title`` / ``title_map_by_spu_id`` / ``title_map_by_public_id``：
   按 locale 取 ``SpuTranslation.title``，缺失回退原文语言（中文优先仍与
   历史口径一致）。

性能纪律：所有列表都必须**批量**取译文（一次 IN 查询），不允许在循环里
逐行查 ``spu.translations``——商家端列表刚做过去 DISTINCT / 轻列 / 服务端
分页优化，不能再把 N+1 加回来。
"""

from django.core.exceptions import ValidationError

from catalog.models import SpuTranslation

# 商家端默认仍按中文标题展示（历史口径），只有请求显式带 locale 时才切换。
DEFAULT_LOCALE = "zh-CN"

LOCALE_ALIASES = {
    "en": "en-GB",
    "en-gb": "en-GB",
    "en-us": "en-GB",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-CN",
    "de": "de-DE",
    "fr": "fr-FR",
    "nl": "nl-NL",
    "lb": "lb-LU",
    "ja": "ja-JP",
    "ko": "ko-KR",
}


def normalize_locale(raw) -> str:
    """把请求里的语言值收敛成 ``xx-YY``；无法识别返回空串。"""

    value = str(raw or "").strip()
    if not value:
        return ""
    # Accept-Language 可能是 "en-GB,en;q=0.9" —— 只取第一项。
    value = value.split(",")[0].split(";")[0].strip()
    if not value:
        return ""
    return (
        LOCALE_ALIASES.get(value.lower())
        or LOCALE_ALIASES.get(value.split("-")[0].lower())
        or value
    )


def request_locale(request) -> str:
    """当前请求的商品数据 locale；没带语言时回退默认（中文）。"""

    query = request.query_params.get("lang") if hasattr(request, "query_params") else None
    locale = normalize_locale(query)
    if not locale:
        locale = normalize_locale(request.headers.get("Accept-Language"))
    return locale or DEFAULT_LOCALE


def locale_priority(locale: str) -> tuple[str, ...]:
    """标题回退链：请求语言 → 对应原文语言 → 另一语言 → 兜底。"""

    primary = normalize_locale(locale) or DEFAULT_LOCALE
    if primary.startswith("zh"):
        return ("zh-CN", "zh", "en-GB", "en")
    if primary.startswith("en"):
        return ("en-GB", "en", "zh-CN", "zh")
    return (primary, "en-GB", "en", "zh-CN", "zh")


def pick_title(translations, locale: str) -> str | None:
    """从已 prefetch 的译文列表里按 locale 优先级取标题（零额外查询）。"""

    rank = {code: index for index, code in enumerate(locale_priority(locale))}
    best: tuple[int, str] | None = None
    fallback: str | None = None
    for translation in translations:
        title = translation.title
        if not title:
            continue
        if fallback is None:
            fallback = title
        index = rank.get(translation.locale)
        if index is not None and (best is None or index < best[0]):
            best = (index, title)
    if best is not None:
        return best[1]
    return fallback


def title_map_by_spu_id(spu_ids, locale: str) -> dict[int, str]:
    """spu pk → 本地化标题。最多 2 条查询（主链 + 「任何译文」兜底）。"""

    ids = sorted({int(value) for value in spu_ids if value})
    if not ids:
        return {}
    priority = locale_priority(locale)
    rank = {code: index for index, code in enumerate(priority)}
    rows = SpuTranslation.objects.filter(spu_id__in=ids, locale__in=priority).values_list(
        "spu_id", "locale", "title"
    )
    best: dict[int, tuple[int, str]] = {}
    for spu_id, code, title in rows:
        if not title:
            continue
        index = rank.get(code)
        if index is None:
            continue
        current = best.get(spu_id)
        if current is None or index < current[0]:
            best[spu_id] = (index, title)
    missing = [spu_id for spu_id in ids if spu_id not in best]
    if missing:
        for spu_id, title in (
            SpuTranslation.objects.filter(spu_id__in=missing)
            .exclude(title="")
            .order_by("pk")
            .values_list("spu_id", "title")
        ):
            best.setdefault(spu_id, (len(priority), title))
    return {spu_id: value[1] for spu_id, value in best.items()}


def title_map_by_public_id(public_ids, locale: str) -> dict[str, str]:
    """spu public_id（字符串）→ 本地化标题。最多 2 条查询，无 N+1。"""

    ids = sorted({str(value).strip() for value in public_ids if value})
    if not ids:
        return {}
    priority = locale_priority(locale)
    rank = {code: index for index, code in enumerate(priority)}
    try:
        rows = list(
            SpuTranslation.objects.filter(spu__public_id__in=ids, locale__in=priority).values_list(
                "spu__public_id", "locale", "title"
            )
        )
    except (ValueError, ValidationError):
        # 历史脏数据（spu_public_id 不是合法 UUID）时宁可回退原文，不 500。
        return {}
    best: dict[str, tuple[int, str]] = {}
    for public_id, code, title in rows:
        if not title:
            continue
        index = rank.get(code)
        if index is None:
            continue
        key = str(public_id)
        current = best.get(key)
        if current is None or index < current[0]:
            best[key] = (index, title)
    missing = [public_id for public_id in ids if public_id not in best]
    if missing:
        for public_id, title in (
            SpuTranslation.objects.filter(spu__public_id__in=missing)
            .exclude(title="")
            .order_by("pk")
            .values_list("spu__public_id", "title")
        ):
            best.setdefault(str(public_id), (len(priority), title))
    return {key: value[1] for key, value in best.items()}
