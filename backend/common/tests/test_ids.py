"""统一编号生成器（common.ids）的格式 / 时区 / 唯一性 / 保存重试测试。"""

import re
from datetime import datetime
from datetime import timezone as dt_timezone

from django.db import IntegrityError, models
from django.test import TestCase
from django.utils import timezone as dj_timezone

from common.ids import (
    ALPHABET,
    DATED_KINDS,
    ID_PREFIX,
    UNDATED_KINDS,
    new_public_id,
    save_with_public_id_retry,
)
from merchants.models import Merchant

DATED_RE = {
    "order": re.compile(r"^JYO\d{8}[0-9A-Z]{6}$"),
    "after_sale": re.compile(r"^JYA\d{8}[0-9A-Z]{6}$"),
    "payment": re.compile(r"^JYPAY\d{8}[0-9A-Z]{6}$"),
    "refund": re.compile(r"^JYR\d{8}[0-9A-Z]{6}$"),
    "shipment": re.compile(r"^JYLOG\d{8}[0-9A-Z]{6}$"),
}
UNDATED_RE = {
    "merchant": re.compile(r"^JYM[0-9A-Z]{10}$"),
    "buyer": re.compile(r"^JYU[0-9A-Z]{10}$"),
}

#: 商品编号不走 JY 体系（2026-11-27 回退为 UUID），这里显式断言它不可生成。
PRODUCT_KIND_REMOVED = "spu"


class PublicIdFormatTests(TestCase):
    def test_all_kinds_have_expected_shape(self):
        for kind, pattern in {**DATED_RE, **UNDATED_RE}.items():
            with self.subTest(kind=kind):
                value = new_public_id(kind)
                self.assertRegex(value, pattern)
                expected_length = len(ID_PREFIX[kind]) + (8 + 6 if kind in DATED_KINDS else 10)
                self.assertEqual(len(value), expected_length)
                self.assertTrue(set(value[3:]) <= set(ALPHABET))

    def test_kind_sets_are_exhaustive_and_disjoint(self):
        self.assertEqual(DATED_KINDS | UNDATED_KINDS, set(ID_PREFIX))
        self.assertFalse(DATED_KINDS & UNDATED_KINDS)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            new_public_id("coupon")

    def test_date_segment_uses_business_timezone(self):
        # 2026-11-27 23:30 UTC：上海已是 11-28，伦敦仍是 11-27。
        moment = datetime(2026, 11, 27, 23, 30, tzinfo=dt_timezone.utc)
        with dj_timezone.override("Asia/Shanghai"):
            self.assertEqual(new_public_id("order", at=moment)[3:11], "20261128")
            self.assertEqual(new_public_id("after_sale", at=moment)[3:11], "20261128")
        with dj_timezone.override("Europe/London"):
            self.assertEqual(new_public_id("order", at=moment)[3:11], "20261127")

    def test_default_date_is_today_in_business_timezone(self):
        moment = dj_timezone.now()
        expected = dj_timezone.localtime(moment).strftime("%Y%m%d")
        self.assertEqual(new_public_id("order", at=moment)[3:11], expected)

    def test_undated_kinds_ignore_date(self):
        moment = datetime(2020, 1, 1, tzinfo=dt_timezone.utc)
        self.assertNotIn("2020", new_public_id("buyer", at=moment))

    def test_product_kind_is_not_part_of_jy_system(self):
        # 商品编号是 UUID（Spu.public_id = UUIDField），common.ids 不再生成 JYP。
        self.assertNotIn(PRODUCT_KIND_REMOVED, ID_PREFIX)
        with self.assertRaises(ValueError):
            new_public_id(PRODUCT_KIND_REMOVED)


class PublicIdUniquenessTests(TestCase):
    def test_ten_thousand_undated_ids_are_unique(self):
        values = {new_public_id("buyer") for _ in range(10_000)}
        self.assertEqual(len(values), 10_000)

    def test_ten_thousand_dated_ids_are_unique(self):
        values = {new_public_id("order") for _ in range(10_000)}
        self.assertEqual(len(values), 10_000)


class PublicIdSaveRetryTests(TestCase):
    def test_model_default_assigns_jym(self):
        merchant = Merchant.objects.create(slug="ids-default-mer", display_name="默认编号店")
        self.assertRegex(merchant.public_id, UNDATED_RE["merchant"])

    def test_duplicate_public_id_is_regenerated_on_save(self):
        first = Merchant.objects.create(slug="ids-dup-a", display_name="重复甲")
        second = Merchant.objects.create(
            slug="ids-dup-b", display_name="重复乙", public_id=first.public_id
        )
        self.assertNotEqual(second.public_id, first.public_id)
        self.assertRegex(second.public_id, UNDATED_RE["merchant"])
        self.assertEqual(Merchant.objects.filter(public_id=first.public_id).count(), 1)

    def test_explicit_public_id_is_kept(self):
        merchant = Merchant.objects.create(
            slug="ids-explicit", display_name="指定编号店", public_id="JYMABC1234567"
        )
        self.assertEqual(merchant.public_id, "JYMABC1234567")

    def test_retry_helper_ignores_other_unique_conflicts(self):
        Merchant.objects.create(slug="ids-other", display_name="已有店")
        merchant = Merchant(slug="ids-other", display_name="同名 slug 店")
        with self.assertRaises(IntegrityError) as ctx:
            save_with_public_id_retry(
                merchant,
                kind="merchant",
                save_fn=models.Model.save.__get__(merchant, Merchant),
            )
        # 只有 public_id 冲突才换号重试；slug 冲突原样抛出。
        self.assertIn("slug", str(ctx.exception))
