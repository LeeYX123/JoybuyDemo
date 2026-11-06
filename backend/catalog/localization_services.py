from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from catalog.models import (
    Sku,
    SkuSpecificationTranslation,
    SpuMarketContent,
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

    legacy = list(spu.translations.all())
    accepted_codes = [locale.code, locale.language_code]
    for code in accepted_codes:
        translation = next((item for item in legacy if item.locale == code), None)
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
