"""商家 public_id：JYM + 10 位随机（2026-11-27 全站编号改造阶段 1）。

旧断言（``^MER\\d{6}$``、从 MER001000 连续编号）已随格式切换作废：新号与 pk
顺序无关，只保证格式、唯一、且所有创建路径都能拿到号。
"""

import importlib

from django.test import TestCase

from merchants.models import Merchant
from merchants.services import create_merchant

JYM_RE = r"^JYM[0-9A-Z]{10}$"


class MerchantPublicIdTests(TestCase):
    def test_create_merchant_assigns_jym_id(self):
        first = create_merchant(display_name="编号店一")
        second = create_merchant(display_name="编号店二")

        for merchant in (first, second):
            self.assertRegex(merchant.public_id, JYM_RE)
        # 新号与创建顺序无关（随机号），只断言互不相同。
        self.assertNotEqual(first.public_id, second.public_id)

    def test_direct_model_create_also_gets_jym_id(self):
        merchant = Merchant.objects.create(slug="direct-mer-id", display_name="直接创建店")

        self.assertRegex(merchant.public_id, JYM_RE)
        self.assertEqual(Merchant.objects.get(pk=merchant.pk).public_id, merchant.public_id)

    def test_explicit_public_id_is_kept(self):
        merchant = Merchant.objects.create(
            slug="explicit-mer-id",
            display_name="指定编号店",
            public_id="JYMZZZZZZZZZZ",
        )

        self.assertEqual(merchant.public_id, "JYMZZZZZZZZZZ")

    def test_duplicate_public_id_is_regenerated(self):
        first = Merchant.objects.create(slug="dup-mer-a", display_name="重复编号甲")
        second = Merchant.objects.create(
            slug="dup-mer-b",
            display_name="重复编号乙",
            public_id=first.public_id,
        )

        # 撞唯一约束时 save() 换号重试（不再抛 IntegrityError）。
        self.assertNotEqual(second.public_id, first.public_id)
        self.assertRegex(second.public_id, JYM_RE)
        self.assertEqual(Merchant.objects.filter(public_id=first.public_id).count(), 1)

    def test_public_ids_are_unique_across_bulk_creation(self):
        numbers = set()
        for index in range(30):
            merchant = Merchant.objects.create(
                slug=f"bulk-mer-{index}", display_name=f"批量店 {index}"
            )
            numbers.add(merchant.public_id)
        self.assertEqual(len(numbers), 30)


class _FakeMerchantObjects:
    """模拟迁移里历史模型的 ``objects``（不落库，只验证回填算法）。"""

    def __init__(self, pks):
        self.pks = sorted(pks)
        self.updated = {}

    def order_by(self, field):
        self.assert_field(field)
        return self

    def values_list(self, field, flat=False):
        self.assert_field(field)
        assert flat is True
        return list(self.pks)

    def filter(self, pk):
        return _FakeMerchantRow(self, pk)

    @staticmethod
    def assert_field(field):
        if field != "pk":
            raise AssertionError(f"unexpected field: {field}")


class _FakeMerchantRow:
    def __init__(self, manager, pk):
        self.manager = manager
        self.pk = pk

    def update(self, **kwargs):
        self.manager.updated[self.pk] = kwargs["public_id_new"]


class _FakeMerchantModel:
    def __init__(self, pks):
        self.objects = _FakeMerchantObjects(pks)


class _FakeApps:
    def __init__(self, pks):
        self.merchant = _FakeMerchantModel(pks)

    def get_model(self, app_label, model_name):
        assert app_label == "merchants" and model_name == "Merchant"
        return self.merchant


class MerchantPublicIdBackfillTests(TestCase):
    """历史迁移 merchants/0009 的回填算法（MER+6 顺序号）保持可回归。"""

    def test_backfill_is_contiguous_unique_and_starts_from_001000(self):
        migration = importlib.import_module(
            "merchants.migrations.0009_merchant_public_id_mer_format"
        )
        fake_apps = _FakeApps([7, 3, 99, 1000])

        migration.backfill_public_ids(fake_apps, None)

        updated = fake_apps.merchant.objects.updated
        self.assertEqual(
            updated,
            {
                3: "MER001000",
                7: "MER001001",
                99: "MER001002",
                1000: "MER001003",
            },
        )
        self.assertEqual(len(set(updated.values())), len(updated))
