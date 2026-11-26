"""批次 CB2 同款多规格合并：旧商品 id 别名（SpuAlias）接口与 PDP 回退。

覆盖三件事：
1. ``GET /api/v1/products/aliases/<old>`` 命中/未命中/保留商品已归档；
2. ``GET /api/v1/products/<old>`` 命中别名时返回保留商品 payload，并带
   ``canonical_public_id``；
3. 普通商品（无别名）响应里 ``canonical_public_id`` 为 None，行为不变。
"""

from django.test import TestCase
from django.urls import reverse

from catalog.models import Spu, SpuAlias
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Market
from offers.services import import_offer_from_source


class SpuAliasApiTests(TestCase):
    def setUp(self):
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.currency = Currency.objects.get(code="GBP")
        self.keep = self._make_spu("alias-keep", "Collagen Powder", "300g")
        self.old = self._make_spu("alias-old", "Collagen Powder", "140g")
        # 归档被合并 SPU（合并不物理删除），并把旧 id 写进别名表。
        Spu.objects.filter(pk=self.old.pk).update(status=Spu.Status.INACTIVE)
        self.alias = SpuAlias.objects.create(
            old_public_id=self.old.public_id,
            spu=self.keep,
            reason="CB2/A/test",
        )

    def _make_spu(self, source_id, title, label):
        spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id=source_id, title=title
        )
        Spu.objects.filter(pk=spu.pk).update(status=Spu.Status.ACTIVE)
        spu.refresh_from_db()
        sku, _ = get_or_create_sku_from_source(
            spu=spu,
            source_system="joybuy",
            source_id=f"{source_id}-sku",
            specification={"Size": label},
            skip_attribute_validation=True,
        )
        import_offer_from_source(
            sku=sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id=f"{source_id}-offer",
            current_price="14.99",
        )
        return spu

    # --- 别名查询接口（storefront 301 中间件的数据源） ---

    def test_alias_endpoint_returns_keep_public_id(self):
        response = self.client.get(
            reverse("product-alias", kwargs={"old_public_id": self.old.public_id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "old_public_id": str(self.old.public_id),
                "canonical_public_id": str(self.keep.public_id),
            },
        )
        self.assertIn("max-age=60", response["Cache-Control"])

    def test_alias_endpoint_404_for_unknown_id(self):
        response = self.client.get(
            reverse(
                "product-alias",
                kwargs={"old_public_id": "00000000-0000-0000-0000-000000000000"},
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "ALIAS_NOT_FOUND")

    def test_alias_endpoint_404_when_keep_is_archived(self):
        Spu.objects.filter(pk=self.keep.pk).update(status=Spu.Status.INACTIVE)

        response = self.client.get(
            reverse("product-alias", kwargs={"old_public_id": self.old.public_id})
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "ALIAS_NOT_FOUND")

    # --- PDP 详情回退：旧链接不能 404 ---

    def test_detail_serves_keep_payload_for_aliased_id(self):
        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.old.public_id})
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["public_id"], str(self.keep.public_id))
        self.assertEqual(data["canonical_public_id"], str(self.keep.public_id))
        self.assertEqual(len(data["skus"]), 1)
        self.assertEqual(data["skus"][0]["canonical_specification"], {"Size": "300g"})

    def test_detail_alias_falls_back_to_404_when_keep_archived(self):
        Spu.objects.filter(pk=self.keep.pk).update(status=Spu.Status.INACTIVE)

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.old.public_id})
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_NOT_AVAILABLE")

    def test_detail_of_normal_product_has_no_canonical_public_id(self):
        data = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.keep.public_id})
        ).json()

        self.assertEqual(data["public_id"], str(self.keep.public_id))
        self.assertIsNone(data["canonical_public_id"])

    def test_alias_old_id_is_unique(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            SpuAlias.objects.create(old_public_id=self.old.public_id, spu=self.keep)
