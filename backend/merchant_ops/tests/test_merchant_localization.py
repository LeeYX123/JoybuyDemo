"""商家端商品名语言跟随（购物端语言 → 商家端）的针对性测试。

覆盖点：
1. 商品池 / 本店商品：``Accept-Language`` 决定标题语言，缺失时回退中文（历史口径）；
2. 订单列表与详情、售后详情、好评通知快照、会话商品卡：同一套 locale 口径；
3. 翻译缺失时回退下单快照原文，不报错。
"""

from catalog.models import SpuTranslation
from merchant_ops.models import AfterSale, SupportConversation
from merchant_ops.tests.test_merchant_modules import MerchantModuleTestBase
from notifications.models import MerchantNotification

EN_TITLE = "Demo Product (EN)"
ZH_TITLE = "演示商品"


class LocalizedProductTitleTests(MerchantModuleTestBase):
    def _add_translation(self, spu, locale, title):
        SpuTranslation.objects.update_or_create(spu=spu, locale=locale, defaults={"title": title})

    def _make_order_with_titles(self, *, translation=True):
        order = self.make_order()
        item = order.items.first()
        spu = item.offer.sku.spu
        if translation:
            self._add_translation(spu, "en-GB", EN_TITLE)
        return order, item, spu

    def _with_lang(self, path, locale):
        return self.client.get(
            path,
            HTTP_X_MERCHANT_ID=str(self.shop.public_id),
            HTTP_ACCEPT_LANGUAGE=locale,
        )

    def test_pool_and_listings_follow_accept_language(self):
        order, _item, spu = self._make_order_with_titles()

        zh = self.get("/api/v1/merchant/catalog/products?page=1&page_size=8").json()
        en = self._with_lang("/api/v1/merchant/catalog/products?page=1&page_size=8", "en-GB").json()
        zh_names = {row["id"]: row["name"] for row in zh["items"]}
        en_names = {row["id"]: row["name"] for row in en["items"]}
        self.assertEqual(zh_names[str(spu.public_id)], ZH_TITLE)
        self.assertEqual(en_names[str(spu.public_id)], EN_TITLE)

        zh_listings = self.get("/api/v1/merchant/listings?page=1&page_size=8").json()
        en_listings = self._with_lang(
            "/api/v1/merchant/listings?page=1&page_size=8", "en-GB"
        ).json()
        self.assertEqual(zh_listings["items"][0]["name"], ZH_TITLE)
        self.assertEqual(en_listings["items"][0]["name"], EN_TITLE)

    def test_lang_query_param_wins_over_accept_language(self):
        _order, _item, spu = self._make_order_with_titles()
        payload = self.client.get(
            "/api/v1/merchant/catalog/products?page=1&page_size=8&lang=en-GB",
            HTTP_X_MERCHANT_ID=str(self.shop.public_id),
            HTTP_ACCEPT_LANGUAGE="zh-CN",
        ).json()
        names = {row["id"]: row["name"] for row in payload["items"]}
        self.assertEqual(names[str(spu.public_id)], EN_TITLE)

    def test_orders_list_and_detail_follow_locale(self):
        order, _item, _spu = self._make_order_with_titles()

        en_list = self._with_lang("/api/v1/merchant/orders?page=1&page_size=8", "en-GB").json()
        self.assertEqual(en_list["items"][0]["title"], EN_TITLE)

        en_detail = self._with_lang(f"/api/v1/merchant/orders/{order.public_id}", "en-GB").json()
        self.assertEqual(en_detail["order"]["title"], EN_TITLE)
        self.assertEqual(en_detail["order"]["items"][0]["title"], EN_TITLE)

        zh_detail = self.get(f"/api/v1/merchant/orders/{order.public_id}").json()
        self.assertEqual(zh_detail["order"]["title"], ZH_TITLE)

    def test_orders_fall_back_to_snapshot_when_translation_missing(self):
        order, _item, _spu = self._make_order_with_titles(translation=False)
        payload = self._with_lang(f"/api/v1/merchant/orders/{order.public_id}", "en-GB").json()
        # 没有 en-GB 译文时回退中文译文（原文语言），不返回空。
        self.assertEqual(payload["order"]["title"], ZH_TITLE)

    def test_after_sale_detail_product_title_follows_locale(self):
        order, _item, _spu = self._make_order_with_titles()
        record = AfterSale.objects.create(
            merchant=self.shop,
            order=order.order,
            merchant_order=order,
            kind=AfterSale.Kind.COMPLAINT,
            state=AfterSale.State.PENDING,
            issue="包装破损",
            currency="GBP",
        )
        payload = self._with_lang(
            f"/api/v1/merchant/after-sales/{record.public_id}", "en-GB"
        ).json()
        self.assertEqual(payload["after_sale"]["product"]["title"], EN_TITLE)

    def test_review_notification_snapshot_name_follows_locale(self):
        _order, _item, spu = self._make_order_with_titles()
        MerchantNotification.objects.create(
            merchant=self.shop,
            kind=MerchantNotification.Kind.REVIEW,
            title="商品好评",
            content="很好用",
            spu=spu,
            rating=5,
            product_snapshot={"id": str(spu.public_id), "name": ZH_TITLE},
        )
        payload = self._with_lang("/api/v1/merchant/notifications?page=1&page_size=8", "en-GB")
        items = payload.json()["items"]
        review = next(row for row in items if row["kind"] == "REVIEW")
        self.assertEqual(review["product"]["name"], EN_TITLE)

    def test_conversation_product_name_follows_locale(self):
        _order, _item, spu = self._make_order_with_titles()
        SupportConversation.objects.create(
            merchant=self.shop,
            kind=SupportConversation.Kind.BUYER,
            peer_name="Alex",
            spu=spu,
        )
        payload = self._with_lang("/api/v1/merchant/conversations?page=1&page_size=10", "en-GB")
        items = payload.json()["items"]
        buyer_row = next(row for row in items if row["product"])
        self.assertEqual(buyer_row["product"]["name"], EN_TITLE)
        # 价格字段与语言无关，确保没被误改。
        self.assertEqual(buyer_row["product"]["id"], str(spu.public_id))
