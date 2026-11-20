"""Seed the per-channel product floors measured from the real Joybuy site.

Data sources (batch H, 2026-11-19):

* ``content/fixtures/channel_modules_uk_20261119.json`` — eight UK channels,
  measured from the UK minihome pages' SSR ItemList modules (``joybuy_uk``).
* ``content/fixtures/channel_modules_nl_outdoor_20261119.json`` — Outdoor &
  Sports from the **Belgian** storefront ``www.joybuy.nl/minihome/
  mini-hp-nl-sports-outdoor`` (real channel code, SSR CMS payload). The
  earlier UK-search fallback was retired once the real page became reachable
  from the dev environment (HANDOFF 0r / 0t).

The command is idempotent: modules are keyed by (channel_code, sort_order),
titles/order/flags are refreshed, and the product list is replaced in fixture
order. Products are resolved by their Joybuy source identity within the
channel's own source system (``joybuy_uk`` vs ``joybuy_nl``); missing products
are skipped and counted (a partial import must not delete floor config).

It also ensures the Belgian Outdoor channel exists locally (source catalog
``joybuy_nl`` + ``minihome:mini-hp-nl-sports-outdoor`` mapping to the
``outdoor-sports`` root) and removes the retired UK-fallback channel code
``NL-Mini-HP-Outdoor-Sports`` (wrong/legacy code, superseded 2026-11-19).
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from catalog.models import CategoryMapping, LocalCategory, SourceCatalog, SourceCategory, Spu
from content.models import ChannelModule, ChannelModuleProduct
from offers.models import Offer

FIXTURES = (
    (
        Path(__file__).resolve().parents[2] / "fixtures" / "channel_modules_uk_20261119.json",
        "joybuy_uk",
    ),
    (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "channel_modules_nl_outdoor_20261119.json",
        "joybuy_nl",
    ),
)
OUTDOOR_CODE = "mini-hp-nl-sports-outdoor"
OUTDOOR_SLUG = "outdoor-sports"
OUTDOOR_SOURCE_SYSTEM = "joybuy_nl"
#: 批次 H 的旧频道 code（比利时站真实 code 是 ``mini-hp-nl-sports-outdoor``；
#: 旧 code 的楼层配置由 UK 搜索数据拼成，2026-11-19 起作废并清理）。
LEGACY_OUTDOOR_CODES = ("NL-Mini-HP-Outdoor-Sports",)


class Command(BaseCommand):
    help = "Seed per-channel product floors from the 2026-11-19 Joybuy measurement."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--no-fill",
            action="store_true",
            help="Do not top up floors with same-category ACTIVE products.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        channels = []
        for fixture, default_system in FIXTURES:
            data = json.loads(fixture.read_text(encoding="utf-8"))
            for channel in data["channels"]:
                channel["source_system"] = channel.get("source_system", default_system)
                channels.append(channel)
        self.ensure_outdoor_channel(dry_run=dry_run)

        sellable_spu_ids = set(
            Offer.objects.filter(
                status=Offer.Status.ACTIVE, sku__spu__status=Spu.Status.ACTIVE
            ).values_list("sku__spu_id", flat=True)
        )
        gallery_spu_ids = self.gallery_spu_ids()
        usable_spu_ids = sellable_spu_ids & gallery_spu_ids
        spu_by_source: dict[tuple[str, str], int] = {}
        for source_system, source_id, spu_id in Spu.objects.filter(
            source_identities__source_system__in={channel["source_system"] for channel in channels},
            id__in=usable_spu_ids,
        ).values_list("source_identities__source_system", "source_identities__source_id", "id"):
            spu_by_source.setdefault((source_system, source_id), spu_id)
        # 楼层清单里的 id 是真站 SKU id；批次 J 补抓走搜索 SSR 时 SPU 身份就是
        # 该 sku id，但批次 H 的 PDP 导入把 SKU 身份挂在变体上（SPU 身份是父
        # 商品 id）——补一层 SKU 级身份解析，避免这些已入库商品被当缺失补位。
        from catalog.models import Sku

        sku_by_source: dict[tuple[str, str], int] = {}
        for source_system, source_id, spu_id in Sku.objects.filter(
            source_identities__source_system__in={channel["source_system"] for channel in channels},
            spu_id__in=usable_spu_ids,
        ).values_list("source_identities__source_system", "source_identities__source_id", "spu_id"):
            sku_by_source.setdefault((source_system, source_id), spu_id)

        fill = not options["no_fill"]
        created = updated = items = skipped = filled = 0
        with transaction.atomic():
            for channel in channels:
                channel_code = channel["channel_code"]
                source_system = channel["source_system"]
                used_spu_ids = set()
                candidates = (
                    self.category_pool(channel["category_slug"], sellable_spu_ids) if fill else []
                )
                for module_data in channel["modules"]:
                    sort_order = module_data["sort_order"]
                    module = ChannelModule.objects.filter(
                        channel_code=channel_code, sort_order=sort_order
                    ).first()
                    if dry_run:
                        continue
                    if module is None:
                        module = ChannelModule.objects.create(
                            channel_code=channel_code,
                            sort_order=sort_order,
                            title_en=module_data["title_en"],
                            title_zh=module_data.get("title_zh", ""),
                        )
                        created += 1
                    else:
                        module.title_en = module_data["title_en"]
                        module.title_zh = module_data.get("title_zh", "")
                        module.enabled = True
                        module.save(update_fields=["title_en", "title_zh", "enabled", "updated_at"])
                        updated += 1
                    module.items.all().delete()
                    target = len(module_data["products"])
                    resolved = []
                    for source_id in module_data["products"]:
                        spu_id = spu_by_source.get((source_system, str(source_id)))
                        if spu_id is None:
                            spu_id = sku_by_source.get((source_system, str(source_id)))
                        if spu_id is None:
                            skipped += 1
                            continue
                        resolved.append(spu_id)
                    # 两个变体 SKU id 可能解析到同一个 SPU（SKU 级身份回退），
                    # 去重保持楼层内唯一商品（唯一约束 channel_module_product_unique）。
                    deduped = []
                    seen_in_floor = set()
                    for spu_id in resolved:
                        if spu_id in seen_in_floor:
                            continue
                        seen_in_floor.add(spu_id)
                        deduped.append(spu_id)
                    resolved = deduped
                    rows = [
                        ChannelModuleProduct(module=module, spu_id=spu_id, sort_order=index)
                        for index, spu_id in enumerate(resolved)
                    ]
                    if fill:
                        # 真实商品抓取受真站风控限制时，用同品类真实可售商品补足
                        # 楼层到真站配置数量（HANDOFF 0q 记录为遗留待办）。
                        used_spu_ids.update(resolved)
                        for spu_id in candidates:
                            if len(rows) >= target:
                                break
                            if spu_id in used_spu_ids:
                                continue
                            used_spu_ids.add(spu_id)
                            rows.append(
                                ChannelModuleProduct(
                                    module=module, spu_id=spu_id, sort_order=len(rows)
                                )
                            )
                            filled += 1
                    ChannelModuleProduct.objects.bulk_create(rows)
                    items += len(rows)

        mode = "DRY RUN" if dry_run else "seeded"
        self.stdout.write(
            self.style.SUCCESS(
                f"Channel modules {mode}: modules created={created}, updated={updated}, "
                f"products linked={items}, real-site products missing={skipped}, "
                f"category top-ups={filled}."
            )
        )

    def gallery_spu_ids(self) -> set[int]:
        from django.contrib.contenttypes.models import ContentType

        from media.models import MediaUsage

        spu_type = ContentType.objects.get_for_model(Spu)
        return set(
            MediaUsage.objects.filter(content_type=spu_type, role="gallery").values_list(
                "object_id", flat=True
            )
        )

    def category_pool(self, root_slug: str, sellable_spu_ids: set[int]) -> list[int]:
        """同品类真实可售商品池（有搜索文档 + 有图），md5 稳定排序。"""

        import hashlib

        from django.contrib.contenttypes.models import ContentType

        from catalog.models import ProductSearchDocument
        from media.models import MediaUsage

        root = LocalCategory.objects.filter(slug=root_slug, depth=0).first()
        if root is None:
            return []
        subtree = [root.pk] + list(
            LocalCategory.objects.filter(parent=root).values_list("pk", flat=True)
        )
        docs = ProductSearchDocument.objects.filter(
            local_category_id__in=subtree,
            locale_code="en-GB",
            is_searchable=True,
        ).select_related("spu")
        spu_ids = {doc.spu_id for doc in docs} & sellable_spu_ids
        spu_type = ContentType.objects.get_for_model(Spu)
        with_image = set(
            MediaUsage.objects.filter(
                content_type=spu_type, object_id__in=spu_ids, role="gallery"
            ).values_list("object_id", flat=True)
        )
        public_ids = dict(Spu.objects.filter(pk__in=with_image).values_list("id", "public_id"))
        ordered = sorted(
            with_image, key=lambda pk: hashlib.md5(str(public_ids.get(pk)).encode()).hexdigest()
        )
        return ordered

    def ensure_outdoor_channel(self, *, dry_run: bool) -> None:
        if dry_run:
            return
        root = LocalCategory.objects.filter(slug=OUTDOOR_SLUG, depth=0).first()
        if root is None:
            return
        catalog, _ = SourceCatalog.objects.get_or_create(
            source_system=OUTDOOR_SOURCE_SYSTEM,
            defaults={"display_name": "Joybuy NL"},
        )
        now = timezone.now()
        source, _ = SourceCategory.objects.get_or_create(
            catalog=catalog,
            source_id=f"minihome:{OUTDOOR_CODE}",
            defaults={"first_seen_at": now, "last_seen_at": now},
        )
        CategoryMapping.objects.get_or_create(
            local_category=root,
            source_category=source,
            defaults={"is_primary": True},
        )
        self.stdout.write(
            f"Outdoor channel mapping ensured: minihome:{OUTDOOR_CODE} -> {OUTDOOR_SLUG}"
        )
        self.remove_legacy_outdoor()

    def remove_legacy_outdoor(self) -> None:
        """删除批次 H 的旧户外频道（错误 code + UK 搜索数据）。"""

        for code in LEGACY_OUTDOOR_CODES:
            modules = ChannelModule.objects.filter(channel_code=code)
            count = modules.count()
            if count:
                modules.delete()
            sources = SourceCategory.objects.filter(source_id=f"minihome:{code}").select_related(
                "catalog"
            )
            removed = 0
            for source in sources:
                CategoryMapping.objects.filter(source_category=source).delete()
                try:
                    source.delete()
                    removed += 1
                except ProtectedError:
                    # 仍被 SPU 来源身份引用时只断映射：旧频道不再被导航/楼层使用。
                    pass
            if count or removed:
                self.stdout.write(
                    f"Legacy outdoor channel removed: {code} "
                    f"(modules={count}, source categories={removed})"
                )
