"""回填历史商家的推荐码与入驻审核结论。

历史数据是在「商家管理」模块之前导入的（多为爬虫来源虚拟商家），
没有推荐码也无法通过入驻审核接口。这里只补最小必要字段：
- 推荐码：全局唯一的短码，后续推荐关系靠它绑定；
- 入驻审核：已经是 ACTIVE 的商家视为审核通过，避免升级后被挡在上架校验外。
"""

import uuid

from django.db import migrations


def _unique_code(Merchant, index):
    while True:
        code = f"M{uuid.uuid4().hex[:7].upper()}"
        if not Merchant.objects.filter(referral_code=code).exists():
            return code


def backfill(apps, schema_editor):
    Merchant = apps.get_model("merchants", "Merchant")
    for index, merchant in enumerate(Merchant.objects.order_by("pk")):
        changed = []
        if not merchant.referral_code:
            merchant.referral_code = _unique_code(Merchant, index)
            changed.append("referral_code")
        if merchant.onboarding_status == "ACTIVE" and not merchant.admission_approved:
            merchant.admission_approved = True
            changed.append("admission_approved")
        if merchant.onboarding_status == "ACTIVE" and not merchant.deposit_initial_paid:
            merchant.deposit_initial_paid = True
            changed.append("deposit_initial_paid")
        if changed:
            merchant.save(update_fields=changed)


def unbackfill(apps, schema_editor):
    # 回填是幂等的补数据动作，回滚时不销毁业务值。
    pass


class Migration(migrations.Migration):
    dependencies = [("merchants", "0003_merchant_admission_approved_and_more")]

    operations = [migrations.RunPython(backfill, unbackfill)]
