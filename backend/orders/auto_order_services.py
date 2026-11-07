"""一键下单任务的创建校验与到点执行（迭代02，doc02「一键下单」整节）。

- 触发时间按**电脑（服务器）时间**判定，不做时区换算；
- 下单前检查：白名单身份、规格（offer）是否仍有效、买家钱包余额是否足够；
- 下单复用 ``place_order``（余额支付真扣），买家端/商家端正常生成订单与子单；
- 任一检查失败 → 任务置 FAILED 并记录原因（管理端可见"提醒"），不再自动重试。
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from orders.models import AutoOrderTask
from orders.order_services import OrderError, place_order


class AutoOrderError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_task_offer(offer) -> str:
    """规格（offer）有效性校验：创建与触发时都要做（doc02 拍板 4）。"""

    from offers.models import Offer

    if offer is None or offer.status != Offer.Status.ACTIVE:
        return "所选规格已失效（商品或规格已下架）"
    if offer.local_inventory < 1:
        return "所选规格已无库存"
    if offer.source_availability == Offer.SourceAvailability.UNAVAILABLE:
        return "所选规格已不可售"
    return ""


def check_account_balance(account, offer, quantity: int) -> str:
    """余额检查：余额 < 商品金额则提醒（触发时不足不下单）。"""

    from checkout.checkout_views import compute_shipping

    subtotal = (offer.current_price * quantity).quantize(Decimal("0.01"))
    shipping_cost, _method = compute_shipping(subtotal, offer.currency.code)
    total = subtotal + Decimal(str(shipping_cost))
    if account.balance < total:
        return (
            f"买家钱包余额不足（需约 {total}，可用 {account.balance}），"
            "请先充值或更换买家。"
        )
    return ""


def create_auto_order_task(
    *,
    account,
    merchant,
    offer,
    quantity: int,
    trigger_at,
    created_by=None,
) -> AutoOrderTask:
    """创建任务：白名单/规格/数量/触发时间校验（余额只提醒不阻断）。"""


    if account is None or not account.purchase_whitelisted:
        raise AutoOrderError("ACCOUNT_NOT_WHITELISTED", "只能选择白名单用户的账号。")
    if quantity < 1:
        raise AutoOrderError("QUANTITY_INVALID", "数量至少为 1。")
    invalid_reason = validate_task_offer(offer)
    if invalid_reason:
        raise AutoOrderError("OFFER_INVALID", invalid_reason)
    now = timezone.now()
    if trigger_at is None:
        raise AutoOrderError("TRIGGER_TIME_REQUIRED", "请设置任务触发时间。")
    if trigger_at < now - timedelta(minutes=1):
        raise AutoOrderError("TRIGGER_TIME_INVALID", "触发时间不能早于当前时间。")
    if merchant is None or offer.merchant_id != merchant.pk:
        raise AutoOrderError("MERCHANT_MISMATCH", "所选商品不属于该商家。")

    spu = offer.sku.spu
    translation = spu.translations.order_by("pk").first()
    return AutoOrderTask.objects.create(
        account=account,
        merchant=merchant,
        offer=offer,
        product_title=translation.title if translation else "",
        specification=offer.sku.specification or {},
        quantity=quantity,
        unit_price=offer.current_price,
        trigger_at=trigger_at,
        status=AutoOrderTask.Status.PENDING,
        created_by=created_by,
    )


def _pick_address(account):
    # is_serviceable 是 Python property，不能进 SQL 过滤——默认优先，逐个判断。
    for address in account.addresses.all().order_by("-is_default", "-pk"):
        if address.is_serviceable:
            return address
    return None


def execute_due_auto_orders(*, now=None) -> dict:
    """执行到点任务（trigger_at <= 服务器当前时间，按拍板不换算时区）。"""

    now = now or timezone.now()
    executed = 0
    failed = 0
    due_ids = list(
        AutoOrderTask.objects.filter(
            status=AutoOrderTask.Status.PENDING, trigger_at__lte=now
        ).values_list("pk", flat=True)
    )
    for task_id in due_ids:
        with transaction.atomic():
            locked = AutoOrderTask.objects.select_for_update().filter(pk=task_id).first()
            if locked is None or locked.status != AutoOrderTask.Status.PENDING:
                continue
            reason = _execute_one(locked)
            if reason:
                locked.status = AutoOrderTask.Status.FAILED
                locked.failure_reason = reason[:255]
                failed += 1
            else:
                locked.status = AutoOrderTask.Status.EXECUTED
                executed += 1
            locked.executed_at = timezone.now()
            locked.save(
                update_fields=[
                    "status",
                    "failure_reason",
                    "executed_order",
                    "executed_at",
                    "updated_at",
                ]
            )
    return {"executed": executed, "failed": failed}


def _execute_one(task: AutoOrderTask) -> str:
    """执行单个任务；返回失败原因（空串=成功）。必须在外层事务内调用。"""


    account = task.account
    if not account.purchase_whitelisted:
        return "买家已不在购买白名单内，已停止下单。"
    offer = task.offer
    invalid_reason = validate_task_offer(offer)
    if invalid_reason:
        return f"规格失效：{invalid_reason}。"
    address = _pick_address(account)
    if address is None:
        return "买家没有可用收货地址，无法自动下单。"
    quantity = task.quantity
    subtotal = (offer.current_price * quantity).quantize(Decimal("0.01"))
    if account.balance < subtotal:
        return (
            f"买家钱包余额不足（需约 {subtotal}，可用 {account.balance}），已停止下单。"
        )

    cart_snapshot = {
        "items": [{"offer_public_id": str(offer.public_id), "quantity": quantity}],
        "subtotal": str(subtotal),
        "total": str(subtotal),
        "currency": offer.currency.code,
        "needs_attention": False,
    }
    try:
        order = place_order(
            account=account,
            cart_snapshot=cart_snapshot,
            address_snapshot={"public_id": str(address.public_id)},
            payment_method="BALANCE",
        )
    except OrderError as exc:
        return f"自动下单被拒绝：{exc.message}"
    task.executed_order = order
    return ""


def cancel_auto_order_task(task, *, actor=None) -> AutoOrderTask:
    if task.status != AutoOrderTask.Status.PENDING:
        raise AutoOrderError("TASK_NOT_PENDING", "只有待执行的任务可以取消。")
    task.status = AutoOrderTask.Status.CANCELED
    task.save(update_fields=["status", "updated_at"])
    return task
