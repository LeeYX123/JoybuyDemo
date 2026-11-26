"""批次 CB2 同款合并：``Sku.specification_merge_managed`` 的导入兼容口径。

合并工具把标题差异派生为 SKU 规格（Size/Colour/...），源站该变体页本身没有
规格解析结果；重爬时 ``get_or_create_sku_from_source`` 会因签名不同抛身份
冲突，``_adopt_enriched_specification`` 必须保留本地派生规格，而不是每合并
一组就制造 N 条 ``ImportSourceConflict``。未打标记的 SKU 口径不变。
"""

from django.test import TestCase

from catalog.models import Sku, Spu
from catalog.product_services import (
    canonicalize_source_specification,
    get_or_create_sku_from_source,
)
from crawler_control.import_services import _adopt_enriched_specification


class MergeManagedSpecificationAdoptionTests(TestCase):
    def setUp(self):
        from catalog.product_services import get_or_create_spu_from_source

        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="merge-spu", title="Collagen Powder"
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)

    def _sku(self, source_id, specification):
        sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id=source_id,
            specification=specification,
            skip_attribute_validation=True,
        )
        return sku

    def _mark_merged(self, sku, specification):
        normalized, signature = canonicalize_source_specification(specification)
        sku.specification = normalized
        sku.specification_signature = signature
        sku.specification_merge_managed = True
        sku.save()
        return sku

    def test_marked_sku_keeps_derived_spec_when_source_has_none(self):
        sku = self._mark_merged(self._sku("var-140", {}), {"Size": "140g"})

        adopted = _adopt_enriched_specification(
            spu=self.spu, source_system="joybuy", source_id="var-140", specification={}
        )

        self.assertIsNotNone(adopted)
        self.assertEqual(adopted.pk, sku.pk)
        adopted.refresh_from_db()
        self.assertEqual(adopted.specification, {"Size": "140g"})
        self.assertTrue(adopted.specification_merge_managed)

    def test_marked_sku_keeps_derived_spec_when_source_reports_something_else(self):
        sku = self._mark_merged(self._sku("var-300", {}), {"Size": "300g"})

        adopted = _adopt_enriched_specification(
            spu=self.spu,
            source_system="joybuy",
            source_id="var-300",
            specification={"Colour": "Red"},
        )

        self.assertEqual(adopted.pk, sku.pk)
        adopted.refresh_from_db()
        self.assertEqual(adopted.specification, {"Size": "300g"})

    def test_unmarked_sku_with_existing_spec_still_conflicts(self):
        sku = self._sku("var-plain", {"Colour": "Blue"})

        adopted = _adopt_enriched_specification(
            spu=self.spu, source_system="joybuy", source_id="var-plain", specification={}
        )

        self.assertIsNone(adopted)
        sku.refresh_from_db()
        self.assertEqual(sku.specification, {"Colour": "Blue"})

    def test_unmarked_empty_spec_sku_still_adopts_enrichment(self):
        sku = self._sku("var-empty", {})

        adopted = _adopt_enriched_specification(
            spu=self.spu,
            source_system="joybuy",
            source_id="var-empty",
            specification={"Colour": "Green"},
        )

        self.assertEqual(adopted.pk, sku.pk)
        sku.refresh_from_db()
        self.assertEqual(sku.specification, {"Colour": "Green"})
        self.assertFalse(sku.specification_merge_managed)

    def test_identity_of_another_spu_is_not_adopted(self):
        from catalog.product_services import get_or_create_spu_from_source

        other, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="other-spu", title="Other"
        )
        sku = self._mark_merged(self._sku("var-x", {}), {"Size": "1kg"})
        self.assertNotEqual(other.pk, self.spu.pk)

        adopted = _adopt_enriched_specification(
            spu=other, source_system="joybuy", source_id="var-x", specification={}
        )

        self.assertIsNone(adopted)
        self.assertTrue(Sku.objects.filter(pk=sku.pk, spu=self.spu).exists())
