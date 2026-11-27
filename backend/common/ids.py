"""统一对外编号生成器（阶段 1 / 阶段 2：订单 / 商家 / 用户 / 售后 / 支付 / 退款 / 物流）。

2026-11-27 用户拍板的格式（全站对外展示编号，数据库主键仍是 bigint）：

========  ======  =======================  ==================
类型      前缀    格式                     示例
========  ======  =======================  ==================
平台订单  JYO     前缀 + YYYYMMDD + 6 位随机  JYO20261127K8M4P2
商家编号  JYM     前缀 + 10 位随机            JYM8K4P2X9Q
用户编号  JYU     前缀 + 10 位随机            JYU7N5K9X2P
售后编号  JYA     前缀 + YYYYMMDD + 6 位随机  JYA20261127C9R3W6
支付编号  JYPAY   前缀 + YYYYMMDD + 6 位随机  JYPAY20261127A8K2N5
退款编号  JYR     前缀 + YYYYMMDD + 6 位随机  JYR20261127P5X8M2
物流编号  JYLOG   前缀 + YYYYMMDD + 6 位随机  JYLOG20261127M4N8X2
========  ======  =======================  ==================

注意：**商品编号不在本表内**。2026-11-27 曾把 ``Spu.public_id`` 改成 ``JYP``
前缀，同日用户拍板回退——商品编号保持原来的 UUID（``UUIDField``），不参与
JY 编号体系。

约定：

* 字符集是 36 进制全字母数字 ``0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ``，**不排除**
  易混字符（用户明确选择「严格照示例、不排除字符」）。
* 日期段取项目业务时区（``settings.TIME_ZONE``，默认 Europe/London），跨零点按
  该时区算日期，用 ``django.utils.timezone.localtime``。
* 商家子单 ``MerchantOrder.public_id`` 也用 ``JYO``（同属订单体系，格式一致）。
* 不做旧号兼容：旧 UUID 一律失效，没有 legacy 字段、没有双读。

唯一性保证（两层）：

1. 数据库 ``unique=True`` 是最终防线；
2. 模型 ``save()`` 撞 ``public_id`` 唯一约束时用 :func:`save_with_public_id_retry`
   重新生成并重试（最多 8 次）。批量创建（``bulk_create`` / crawler 导入）不经过
   ``save()``，只依赖字段 ``default``；随机空间 36^10（或 36^6）足够大，冲突概率
   可忽略，唯一约束仍兜底。
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Callable, Mapping

from django.db import IntegrityError, transaction
from django.utils import timezone

ID_PREFIX: dict[str, str] = {
    "order": "JYO",
    "merchant": "JYM",
    "buyer": "JYU",
    "after_sale": "JYA",
    "payment": "JYPAY",
    "refund": "JYR",
    "shipment": "JYLOG",
}

#: 带日期段的类型：前缀 + YYYYMMDD + 6 位随机。
DATED_KINDS = frozenset({"order", "after_sale", "payment", "refund", "shipment"})
#: 不带日期段的类型：前缀 + 10 位随机。
UNDATED_KINDS = frozenset({"merchant", "buyer"})

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DATED_RANDOM_LENGTH = 6
UNDATED_RANDOM_LENGTH = 10
#: 与模型字段 ``max_length`` 保持一致（最长 3 + 8 + 6 = 17，留余量）。
PUBLIC_ID_MAX_LENGTH = 32
MAX_SAVE_ATTEMPTS = 8


def _random_suffix(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def new_public_id(kind: str, *, at: datetime | None = None) -> str:
    """按 ``kind`` 生成一个新编号。

    ``at`` 只对带日期段的类型有意义：取业务时区（``settings.TIME_ZONE``）下的
    日期段；传 naive datetime 时按当前时区补成 aware。
    """

    try:
        prefix = ID_PREFIX[kind]
    except KeyError:
        raise ValueError(f"unknown public id kind: {kind!r}") from None

    if kind in DATED_KINDS:
        moment = at or timezone.now()
        if timezone.is_naive(moment):
            moment = timezone.make_aware(moment, timezone.get_current_timezone())
        local = timezone.localtime(moment)
        return f"{prefix}{local.strftime('%Y%m%d')}{_random_suffix(DATED_RANDOM_LENGTH)}"

    return f"{prefix}{_random_suffix(UNDATED_RANDOM_LENGTH)}"


# --------------------------------------------------------------------------
# 模型字段 default：模块级无参函数（迁移里按模块路径序列化，不能用 partial）
# --------------------------------------------------------------------------


def new_order_public_id() -> str:
    return new_public_id("order")


def new_merchant_public_id() -> str:
    return new_public_id("merchant")


def new_buyer_public_id() -> str:
    return new_public_id("buyer")


def new_after_sale_public_id() -> str:
    return new_public_id("after_sale")


def new_payment_public_id() -> str:
    return new_public_id("payment")


def new_refund_public_id() -> str:
    return new_public_id("refund")


def new_shipment_public_id() -> str:
    return new_public_id("shipment")


# --------------------------------------------------------------------------
# 保存时唯一冲突重试
# --------------------------------------------------------------------------


def save_with_public_id_retry(
    instance: Any,
    *,
    kind: str,
    save_fn: Callable[..., Any],
    args: tuple = (),
    kwargs: Mapping[str, Any] | None = None,
    max_attempts: int = MAX_SAVE_ATTEMPTS,
) -> Any:
    """执行 ``save_fn(*args, **kwargs)``；``public_id`` 撞唯一约束就换号重试。

    只吞 ``public_id`` 冲突，其它唯一键（slug / email / sku 等）原样抛出。
    调用方在模型 ``save()`` 里传 ``super().save``（零参 ``super()`` 只能在方法体
    求值，不能放进 helper 内部）。
    """

    extra = dict(kwargs or {})
    if not getattr(instance, "public_id", ""):
        # 兜底：显式传空串/None 的创建路径也要拿到号（字段 default 只覆盖未传值）。
        instance.public_id = new_public_id(kind)
    for attempt in range(max_attempts):
        try:
            with transaction.atomic():
                save_fn(*args, **extra)
            return instance
        except IntegrityError as exc:
            last_attempt = attempt == max_attempts - 1
            if last_attempt or "public_id" not in str(exc):
                raise
            instance.public_id = new_public_id(kind)
