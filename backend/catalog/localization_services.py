from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from catalog.models import (
    Sku,
    SkuSpecificationTranslation,
    SpuMarketContent,
    SpuTranslation,
)
from offers.market_services import offer_market_chain
from offers.models import Locale, Market

SPEC_TRANSLATIONS = {
    "de": {
        "color": "Farbe",
        "colour": "Farbe",
        "size": "Größe",
        "capacity": "Kapazität",
        "material": "Material",
        "style": "Stil",
        "model": "Modell",
        "quantity": "Menge",
        "pack size": "Packungsgröße",
        "flavour": "Geschmack",
        "flavor": "Geschmack",
        "black": "Schwarz",
        "white": "Weiß",
        "red": "Rot",
        "blue": "Blau",
        "green": "Grün",
        "yellow": "Gelb",
        "grey": "Grau",
        "gray": "Grau",
        "small": "Klein",
        "medium": "Mittel",
        "large": "Groß",
        "extra large": "Extra groß",
        "yes": "Ja",
        "no": "Nein",
    },
    "fr": {
        "color": "Couleur",
        "colour": "Couleur",
        "size": "Taille",
        "capacity": "Capacité",
        "material": "Matériau",
        "style": "Style",
        "model": "Modèle",
        "quantity": "Quantité",
        "pack size": "Taille du lot",
        "flavour": "Saveur",
        "flavor": "Saveur",
        "black": "Noir",
        "white": "Blanc",
        "red": "Rouge",
        "blue": "Bleu",
        "green": "Vert",
        "yellow": "Jaune",
        "grey": "Gris",
        "gray": "Gris",
        "small": "Petit",
        "medium": "Moyen",
        "large": "Grand",
        "extra large": "Très grand",
        "yes": "Oui",
        "no": "Non",
    },
    "nl": {
        "color": "Kleur",
        "colour": "Kleur",
        "size": "Maat",
        "capacity": "Capaciteit",
        "material": "Materiaal",
        "style": "Stijl",
        "model": "Model",
        "quantity": "Aantal",
        "pack size": "Verpakkingsgrootte",
        "flavour": "Smaak",
        "flavor": "Smaak",
        "black": "Zwart",
        "white": "Wit",
        "red": "Rood",
        "blue": "Blauw",
        "green": "Groen",
        "yellow": "Geel",
        "grey": "Grijs",
        "gray": "Grijs",
        "small": "Klein",
        "medium": "Middel",
        "large": "Groot",
        "extra large": "Extra groot",
        "yes": "Ja",
        "no": "Nee",
    },
    "lb": {
        "color": "Faarf",
        "colour": "Faarf",
        "size": "Gréisst",
        "capacity": "Kapazitéit",
        "material": "Material",
        "style": "Stil",
        "model": "Modell",
        "quantity": "Quantitéit",
        "pack size": "Pakgréisst",
        "flavour": "Goût",
        "flavor": "Goût",
        "black": "Schwaarz",
        "white": "Wäiss",
        "red": "Rout",
        "blue": "Blo",
        "green": "Gréng",
        "yellow": "Giel",
        "grey": "Gro",
        "gray": "Gro",
        "small": "Kleng",
        "medium": "Mëttel",
        "large": "Grouss",
        "extra large": "Extra grouss",
        "yes": "Jo",
        "no": "Nee",
    },
}


@dataclass(frozen=True)
class ResolvedProductContent:
    title: str
    subtitle: str
    description: str
    requested_locale: str
    content_locale: str
    content_market: str | None
    origin: str


def _translate_term(value, *, language_code: str, untranslated: list[str]):
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    translated = SPEC_TRANSLATIONS.get(language_code, {}).get(cleaned.casefold())
    if translated:
        return translated
    if cleaned and not any(character.isdigit() for character in cleaned):
        untranslated.append(cleaned)
    return value


def direct_translate_specification(specification: dict, locale: Locale) -> tuple[dict, list[str]]:
    """Translate common display terms without mutating canonical SKU identity data.

    Unknown free text is retained and explicitly marked for review. Numeric
    values, model codes and units are intentionally preserved.
    """

    untranslated: list[str] = []
    translated = {}
    for key, value in specification.items():
        translated_key = _translate_term(
            str(key), language_code=locale.language_code, untranslated=untranslated
        )
        if isinstance(value, list):
            translated_value = [
                _translate_term(
                    item,
                    language_code=locale.language_code,
                    untranslated=untranslated,
                )
                for item in value
            ]
        else:
            translated_value = _translate_term(
                value,
                language_code=locale.language_code,
                untranslated=untranslated,
            )
        translated[str(translated_key)] = translated_value
    return translated, sorted(set(untranslated), key=str.casefold)


@transaction.atomic
def translate_sku_specification(
    sku: Sku,
    locale: Locale,
    *,
    source_locale: str = "en-GB",
) -> SkuSpecificationTranslation:
    translated, untranslated = direct_translate_specification(sku.specification, locale)
    record, _ = SkuSpecificationTranslation.objects.update_or_create(
        sku=sku,
        locale=locale,
        defaults={
            "specification": translated,
            "source_locale": source_locale,
            "method": SkuSpecificationTranslation.Method.DIRECT,
            "untranslated_terms": untranslated,
            "needs_review": bool(untranslated),
        },
    )
    return record


def localized_specification(sku: Sku, locale: Locale) -> tuple[dict, bool]:
    record = next(
        (item for item in sku.specification_translations.all() if item.locale_id == locale.pk),
        None,
    )
    if record is None:
        return sku.specification, False
    return record.specification, True


def _pick_legacy(legacy, codes) -> SpuTranslation | None:
    for code in codes:
        for item in legacy:
            if item.locale == code:
                return item
    return None


def localized_titles_for_spus(spu_ids, market: Market, locale: Locale) -> dict[int, str]:
    """批量取多个 SPU 在 ``locale`` 下的标题（列表卡片用，读取时本地化）。

    与 :func:`resolve_product_content` 同优先级：``SpuMarketContent``
    (市场链 + ``locale`` + ``status=CURRENT``) 优先，其次 ``SpuTranslation``
    （精确 locale 码 → 语言码）。都没有译文就不返回该 SPU —— 调用方保留英文
    原值，**不回退其它语言**（避免 zh-CN 列表出现德语标题）。

    固定 2 条查询（页大小无关），供搜索/推荐接口序列化时一次性本地化，
    搜索索引本身（``ProductSearchDocument.title``）保持英文快照不变。
    """

    ids = {int(pk) for pk in spu_ids}
    if not ids or locale is None:
        return {}
    titles: dict[int, str] = {}
    market_ids = [item.pk for item in offer_market_chain(market)]
    if market_ids:
        rank = {market_id: index for index, market_id in enumerate(market_ids)}
        best: dict[int, tuple[int, str]] = {}
        rows = SpuMarketContent.objects.filter(
            spu_id__in=ids,
            market_id__in=market_ids,
            locale_id=locale.pk,
            status=SpuMarketContent.Status.CURRENT,
        ).values_list("spu_id", "market_id", "title")
        for spu_id, market_id, title in rows:
            if not title:
                continue
            precedence = rank[market_id]
            current = best.get(spu_id)
            if current is None or precedence < current[0]:
                best[spu_id] = (precedence, title)
        titles = {spu_id: title for spu_id, (_, title) in best.items()}

    missing = ids - set(titles)
    if missing:
        # 精确码（zh-CN）优先于语言码（zh）；同码多行按 pk 取第一条保证确定性。
        priority = {locale.code: 0}
        if locale.language_code != locale.code:
            priority[locale.language_code] = 1
        legacy: dict[int, tuple[int, str]] = {}
        rows = (
            SpuTranslation.objects.filter(spu_id__in=missing, locale__in=list(priority))
            .order_by("spu_id", "pk")
            .values_list("spu_id", "locale", "title")
        )
        for spu_id, code, title in rows:
            if not title:
                continue
            precedence = priority[code]
            current = legacy.get(spu_id)
            if current is None or precedence < current[0]:
                legacy[spu_id] = (precedence, title)
        titles.update({spu_id: title for spu_id, (_, title) in legacy.items()})
    return titles


def resolve_product_content(spu, market: Market, locale: Locale) -> ResolvedProductContent:
    market_contents = list(spu.market_contents.all())
    for candidate_market in offer_market_chain(market):
        for content in market_contents:
            if (
                content.market_id == candidate_market.pk
                and content.locale_id == locale.pk
                and content.status == SpuMarketContent.Status.CURRENT
            ):
                return ResolvedProductContent(
                    title=content.title,
                    subtitle=content.subtitle,
                    description=content.description,
                    requested_locale=locale.code,
                    content_locale=content.locale.code,
                    content_market=candidate_market.code,
                    origin=content.origin,
                )

    # 稳定排序：MySQL 对同一 key 的多行返回顺序不保证，先按 pk 固定基线，
    # 后面的「兜底取第一行」才是确定性的（2026-11-17：zh-CN 曾随机落在
    # de-BE 行显示别国语言，就是吃了这个无序返回）。
    legacy = sorted(spu.translations.all(), key=lambda item: item.pk)
    accepted_codes = [locale.code, locale.language_code]
    translation = _pick_legacy(legacy, accepted_codes)
    if translation:
        return ResolvedProductContent(
            title=translation.title,
            subtitle=translation.subtitle,
            description=translation.description,
            requested_locale=locale.code,
            content_locale=translation.locale,
            content_market=None,
            origin="LEGACY",
        )
    # 显式回退源语言：请求 locale 没有译文时优先英文源行（en-GB → en），
    # 而不是随机落到其它语言的 legacy 行；origin 用 FALLBACK_SOURCE 与
    # 最后的兜底区分，便于排查「zh-CN 显示德语」这类问题。
    translation = _pick_legacy(legacy, ["en-GB", "en"])
    if translation:
        return ResolvedProductContent(
            title=translation.title,
            subtitle=translation.subtitle,
            description=translation.description,
            requested_locale=locale.code,
            content_locale=translation.locale,
            content_market=None,
            origin="FALLBACK_SOURCE",
        )
    translation = legacy[0] if legacy else None
    return ResolvedProductContent(
        title=translation.title if translation else "",
        subtitle=translation.subtitle if translation else "",
        description=translation.description if translation else "",
        requested_locale=locale.code,
        content_locale=translation.locale if translation else "",
        content_market=None,
        origin="FALLBACK",
    )
