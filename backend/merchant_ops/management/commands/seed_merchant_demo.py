"""为商家端（merchant-web）造一套可演示、可重复执行的数据。

只用于本地开发库：给指定店铺补上已上架商品、钱包流水、三种状态的订单、
售后、活动、通知与买家会话，让 M03–M10 的页面不是全空态。

幂等：所有写入都用固定 idempotency_key / 自然键判重，重复执行不会翻倍。
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from catalog.models import Spu
from merchant_ops.models import (
    AfterSale,
    AfterSaleEvent,
    MerchantActivity,
    MerchantActivityParticipation,
    MerchantDepositEntry,
    MerchantReferral,
    MerchantWalletEntry,
    MerchantWithdrawal,
    ReferralCommission,
    ReferralProgram,
    SupportConversation,
    SupportMessage,
)
from merchant_ops.services import record_wallet_entry
from merchants.models import Merchant
from notifications.models import MerchantNotification, MerchantNotificationReply
from offers.models import Market, Offer
from orders.models import MerchantOrder, Order, OrderItem


class Command(BaseCommand):
    help = "给指定店铺造商家端演示数据（幂等，仅本地开发库使用）"

    def add_arguments(self, parser):
        parser.add_argument("--merchant", default="CHiQ", help="店铺显示名")
        parser.add_argument("--reset", action="store_true", help="先清掉本命令造的数据再重建")
        parser.add_argument(
            "--with-deposit",
            action="store_true",
            help="给该店铺启用保证金并缴足（用于演示 M06 页面）",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["merchant"]
        merchant = Merchant.objects.filter(display_name=name).first()
        if merchant is None:
            raise CommandError(f"找不到店铺：{name}")

        if options["reset"]:
            self._reset(merchant)

        market = Market.objects.select_related("default_currency").get(code="GB")
        self._ensure_catalog_prices()
        listings = self._ensure_listings(merchant, market)
        self._ensure_wallet(merchant)
        orders = self._ensure_orders(merchant, market, listings)
        self._ensure_after_sale(merchant, orders)
        self._ensure_activities(merchant)
        self._ensure_notifications(merchant, listings)
        self._ensure_conversation(merchant, listings)
        self._ensure_referral(merchant)
        if options["with_deposit"]:
            self._ensure_deposit(merchant)

        self.stdout.write(self.style.SUCCESS(f"{name} 演示数据就绪"))

    # ------------------------------------------------------------------
    def _reset(self, merchant):
        """按依赖顺序清理本命令造的数据（PROTECT 外键必须从叶子往上删）。"""

        MerchantWalletEntry.objects.filter(
            merchant=merchant, idempotency_key__startswith="demo:"
        ).delete()
        MerchantWithdrawal.objects.filter(merchant=merchant).delete()
        MerchantDepositEntry.objects.filter(merchant=merchant, note__startswith="[demo]").delete()
        AfterSaleEvent.objects.filter(after_sale__merchant=merchant).delete()
        AfterSale.objects.filter(merchant=merchant).delete()
        MerchantNotification.objects.filter(merchant=merchant).delete()
        SupportMessage.objects.filter(conversation__merchant=merchant).delete()
        SupportConversation.objects.filter(merchant=merchant).delete()
        MerchantActivityParticipation.objects.filter(merchant=merchant).delete()
        MerchantActivity.objects.filter(title__startswith="[demo]").delete()
        ReferralCommission.objects.filter(referral__referrer=merchant).delete()
        MerchantReferral.objects.filter(referrer=merchant).delete()

        demo_orders = list(
            MerchantOrder.objects.filter(
                merchant=merchant, order__shipping_address__demo=True
            ).values_list("order_id", flat=True)
        )
        if demo_orders:
            MerchantOrder.objects.filter(order_id__in=demo_orders).delete()
            Order.objects.filter(pk__in=demo_orders).delete()

    def _ensure_catalog_prices(self):
        """给商品池补成本价/零售价。

        爬虫导入的 SPU 只有售价在 Offer 上，``spu.cost_price``/``retail_price``
        是空的，而 M03 上架要求这两个字段齐全。这里零售价取该 SPU 在售
        Offer 的价格（真实数据），成本价按零售价 62% 估算——**仅用于本地
        演示**，真实成本必须由平台运营在 A03 录入。
        """

        pending = Spu.objects.filter(
            status=Spu.Status.ACTIVE, cost_price__isnull=True
        ).prefetch_related("skus")[:200]
        updated = 0
        for spu in pending:
            if not spu.skus.exists():
                continue
            offer = Offer.objects.filter(sku__spu=spu).order_by("-current_price").first()
            retail = offer.current_price if offer else Decimal("19.99")
            if retail <= 0:
                retail = Decimal("19.99")
            spu.retail_price = retail
            spu.cost_price = (retail * Decimal("0.62")).quantize(Decimal("0.01"))
            spu.save(update_fields=["retail_price", "cost_price", "updated_at"])
            updated += 1
        if updated:
            self.stdout.write(f"补商品池价格 {updated} 个（成本价按零售价 62% 估算，仅本地演示）")

    def _ensure_listings(self, merchant, market):
        """上架 3 个成本/零售价齐全的 SPU。"""

        existing = list(
            Offer.objects.filter(merchant=merchant, status=Offer.Status.ACTIVE).select_related(
                "sku__spu"
            )[:3]
        )
        if len(existing) >= 3:
            return [offer.sku.spu for offer in existing]

        needed = 3 - len(existing)
        candidates = (
            Spu.objects.filter(
                status=Spu.Status.ACTIVE,
                cost_price__isnull=False,
                retail_price__isnull=False,
            )
            .exclude(skus__isnull=True)
            .exclude(skus__offers__merchant=merchant)
            .distinct()
            .order_by("-pk")[:needed]
        )
        spus = [offer.sku.spu for offer in existing]
        for spu in candidates:
            sku = spu.skus.filter(status="ACTIVE").order_by("pk").first()
            if sku is None:
                continue
            Offer.objects.create(
                merchant=merchant,
                sku=sku,
                market=market,
                currency=market.default_currency,
                current_price=spu.retail_price,
                list_price=spu.retail_price,
                cost_price=spu.cost_price,
                local_inventory=999,
                source_availability=Offer.SourceAvailability.IN_STOCK,
                status=Offer.Status.ACTIVE,
                listed_at=timezone.now(),
            )
            spus.append(spu)
        return spus[:3]

    def _ensure_wallet(self, merchant):
        # 幂等键必须带店铺 ID：它是全局唯一的，两家店共用同一个 key 会让
        # 第二家店直接复用第一家的流水，余额却不会增加。
        recharge_key = f"demo:recharge:{merchant.pk}"
        referral_key = f"demo:referral:{merchant.pk}"
        if MerchantWalletEntry.objects.filter(
            merchant=merchant, idempotency_key=recharge_key
        ).exists():
            return
        record_wallet_entry(
            merchant_id=merchant.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal("20000.00"),
            note="[demo] 客服充值",
            idempotency_key=recharge_key,
        )
        record_wallet_entry(
            merchant_id=merchant.pk,
            kind=MerchantWalletEntry.Kind.REFERRAL_COMMISSION,
            amount=Decimal("120.00"),
            note="[demo] 推荐返佣到账",
            idempotency_key=referral_key,
        )

    def _ensure_orders(self, merchant, market, spus):
        """三种状态各一单，走真实服务生成流水，保证数字自洽。"""

        from merchant_ops.services import ship_merchant_order

        orders = []
        buyer = BuyerAccount.objects.filter(email="demo@joybuy.test").first()
        if buyer is None:
            buyer = BuyerAccount.objects.create(email="demo@joybuy.test", status="ACTIVE")

        specs = [
            (MerchantOrder.Status.PENDING, 1, 0),
            (MerchantOrder.Status.SHIPPED, 2, 3),
            (MerchantOrder.Status.COMPLETED, 1, 7),
        ]
        for index, (status, quantity, progress) in enumerate(specs):
            marker = f"demo-order-{index}"
            if MerchantOrder.objects.filter(
                merchant=merchant, order__shipping_address__marker=marker
            ).exists():
                orders.append(
                    MerchantOrder.objects.get(
                        merchant=merchant, order__shipping_address__marker=marker
                    )
                )
                continue
            spu = spus[index % len(spus)]
            sku = spu.skus.filter(status="ACTIVE").order_by("pk").first()
            offer = Offer.objects.filter(merchant=merchant, sku=sku).first()
            if offer is None:
                continue
            unit_price = spu.retail_price
            unit_cost = spu.cost_price
            items_total = unit_price * quantity
            cost_total = unit_cost * quantity

            order = Order.objects.create(
                account=buyer,
                status=Order.Status.PENDING_PAYMENT,
                currency=market.default_currency,
                items_subtotal=items_total,
                shipping_cost=Decimal("0.00"),
                total=items_total,
                shipping_address={
                    "demo": True,
                    "marker": marker,
                    "recipient": "Demo Buyer",
                    "region": "United Kingdom",
                },
                payment_expires_at=timezone.now() + timedelta(days=1),
            )
            merchant_order = MerchantOrder.objects.create(
                order=order,
                merchant=merchant,
                currency=market.default_currency.code,
                items_total=items_total,
                cost_total=cost_total,
                payment_method=["VISA", "PAYPAL", "APPLE_PAY"][index],
                recipient_region="United Kingdom",
            )
            OrderItem.objects.create(
                order=order,
                merchant_order=merchant_order,
                offer=offer,
                spu_public_id=str(spu.public_id),
                title=self._title(spu),
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=unit_cost,
                currency=market.default_currency.code,
            )
            if status in (MerchantOrder.Status.SHIPPED, MerchantOrder.Status.COMPLETED):
                merchant_order = ship_merchant_order(merchant_order, reference=f"JB{1000 + index}")
                if progress > 0:
                    from merchant_ops.services import advance_progress

                    merchant_order = advance_progress(merchant_order, node_index=progress)
            orders.append(merchant_order)
        return orders

    def _ensure_after_sale(self, merchant, orders):
        if AfterSale.objects.filter(merchant=merchant, issue__startswith="[demo]").exists():
            return
        target = next(
            (order for order in orders if order.status != MerchantOrder.Status.PENDING), None
        )
        if target is None:
            return
        record = AfterSale.objects.create(
            merchant=merchant,
            order=target.order,
            merchant_order=target,
            kind=AfterSale.Kind.RETURN,
            state=AfterSale.State.PENDING,
            issue="[demo] 买家反馈外包装破损，申请退货。",
            progress="已联系买家核实情况",
            currency=target.currency,
        )
        AfterSaleEvent.objects.create(
            after_sale=record,
            actor=AfterSaleEvent.Actor.BUYER,
            action="提交售后",
            content=record.issue,
        )

    def _ensure_activities(self, merchant):
        today = timezone.localdate()
        permanent, _ = MerchantActivity.objects.get_or_create(
            title="[demo] 秋季家居焕新",
            defaults={
                "kind": MerchantActivity.Kind.PERMANENT,
                "state": MerchantActivity.State.ONGOING,
                "start_date": today - timedelta(days=10),
                "description": "常驻活动，参与后在商城活动页获得额外曝光。",
                "sort_order": 1,
            },
        )
        limited, _ = MerchantActivity.objects.get_or_create(
            title="[demo] 黑五限时促销",
            defaults={
                "kind": MerchantActivity.Kind.LIMITED,
                "state": MerchantActivity.State.ONGOING,
                "start_date": today,
                "end_date": today + timedelta(days=14),
                "description": "限时活动，结束时间到期后自动转为已结束。",
                "sort_order": 2,
            },
        )
        MerchantActivityParticipation.objects.get_or_create(
            activity=permanent, merchant=merchant, defaults={"exposure_added": 1200}
        )
        return [permanent, limited]

    def _ensure_notifications(self, merchant, spus):
        if MerchantNotification.objects.filter(
            merchant=merchant, title__startswith="[demo]"
        ).exists():
            return
        MerchantNotification.objects.create(
            merchant=merchant,
            kind=MerchantNotification.Kind.NORMAL,
            title="[demo] 平台结算周期调整通知",
            content="自下月起，订单回款统一在确认收货后 T+1 入账，请留意钱包明细。",
        )
        spu = spus[0]
        review = MerchantNotification.objects.create(
            merchant=merchant,
            kind=MerchantNotification.Kind.REVIEW,
            title="[demo] 商品好评",
            content="包装完好，物流很快，用起来比预期好，会回购。",
            spu=spu,
            rating=5,
            product_snapshot={
                "id": str(spu.public_id),
                "name": self._title(spu),
                "category": spu.local_category.name_zh if spu.local_category_id else "",
                "price": str(spu.retail_price) if spu.retail_price is not None else "",
                "cost": str(spu.cost_price) if spu.cost_price is not None else "",
            },
            images=[],
        )
        MerchantNotificationReply.objects.create(
            notification=review,
            role=MerchantNotificationReply.Role.PLATFORM,
            author_label="平台运营",
            content="感谢反馈，已同步给店铺。",
        )

    def _ensure_conversation(self, merchant, spus):
        if SupportConversation.objects.filter(
            merchant=merchant, kind=SupportConversation.Kind.BUYER
        ).exists():
            return
        buyer = BuyerAccount.objects.filter(email="demo@joybuy.test").first()
        spu = spus[0]
        conversation = SupportConversation.objects.create(
            merchant=merchant,
            kind=SupportConversation.Kind.BUYER,
            state=SupportConversation.State.PENDING,
            buyer=buyer,
            peer_name="演示买家",
            spu=spu,
            last_message_at=timezone.now(),
        )
        SupportMessage.objects.create(
            conversation=conversation,
            sender=SupportMessage.Sender.BUYER,
            author_label="演示买家",
            text="这个商品支持 220V 电压吗？英国能直接用吗？",
        )

    def _ensure_referral(self, merchant):
        ReferralProgram.load()
        if MerchantReferral.objects.filter(referrer=merchant).exists():
            return
        referee = (
            Merchant.objects.filter(admission_approved=True)
            .exclude(pk=merchant.pk)
            .exclude(pk__in=MerchantReferral.objects.values("referee_id"))
            .exclude(merchant_type=Merchant.Type.IMPORT_FALLBACK)
            .first()
        )
        if referee is None or not merchant.referral_code:
            return
        referral = MerchantReferral.objects.create(
            referrer=merchant, referee=referee, code_used=merchant.referral_code
        )
        last_month = (timezone.localdate().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        amount = Decimal("120.00")
        ReferralCommission.objects.create(
            referral=referral,
            period=last_month,
            shipped_amount=Decimal("12000.00"),
            rate=Decimal("1.000"),
            amount=amount,
            state=ReferralCommission.State.PENDING_PAY,
            calculated_at=timezone.now(),
        )

    def _ensure_deposit(self, merchant):
        """演示用：启用保证金并缴足，让 M06 菜单可见且内容完整。"""

        if not merchant.deposit_enabled:
            merchant.deposit_enabled = True
            merchant.deposit_required = Decimal("5000.00")
            merchant.deposit_balance = Decimal("5000.00")
            merchant.deposit_initial_paid = True
            merchant.save(
                update_fields=[
                    "deposit_enabled",
                    "deposit_required",
                    "deposit_balance",
                    "deposit_initial_paid",
                    "updated_at",
                ]
            )
        if not MerchantDepositEntry.objects.filter(
            merchant=merchant, note="[demo] 首次缴纳保证金"
        ).exists():
            MerchantDepositEntry.objects.create(
                merchant=merchant,
                kind=MerchantDepositEntry.Kind.INITIAL,
                amount=Decimal("5000.00"),
                balance_before=Decimal("0.00"),
                balance_after=Decimal("5000.00"),
                related_id="DEMO-DEPOSIT-1",
                note="[demo] 首次缴纳保证金",
                occurred_at=timezone.now(),
            )

    @staticmethod
    def _title(spu) -> str:
        for translation in spu.translations.all():
            if translation.title:
                return translation.title
        return f"SPU {str(spu.public_id)[:8]}"
