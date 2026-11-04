from accounts_buyers import activity_views
from accounts_buyers.urls import urlpatterns as buyer_urlpatterns
from accounts_staff.urls import urlpatterns as staff_urlpatterns
from cart import cart_views
from catalog import detail_views, search_views
from checkout import checkout_views
from common import admin_views, views
from content import views as content_views
from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from media.views import serve_media_file
from orders import order_views
from reviews import review_views

handler400 = "common.errors.bad_request"
handler404 = "common.errors.not_found"
handler500 = "common.errors.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", views.api_root, name="api-root"),
    path("api/v1/health", views.HealthView.as_view(), name="health"),
    path("api/v1/storefront/home", content_views.storefront_home, name="storefront-home"),
    path("api/v1/categories", search_views.category_tree, name="category-tree"),
    path("api/v1/search", search_views.storefront_search, name="storefront-search"),
    path(
        "api/v1/products/<uuid:public_id>",
        detail_views.product_detail,
        name="product-detail",
    ),
    path("api/v1/cart", cart_views.cart_detail, name="cart-detail"),
    path("api/v1/cart/items", cart_views.cart_items, name="cart-items"),
    path(
        "api/v1/cart/items/<uuid:item_public_id>",
        cart_views.cart_item_detail,
        name="cart-item-detail",
    ),
    path("api/v1/cart/merge", cart_views.cart_merge, name="cart-merge"),
    path("api/v1/addresses", checkout_views.address_list, name="address-list"),
    path("api/v1/checkout/quote", checkout_views.checkout_quote, name="checkout-quote"),
    path(
        "api/v1/admin/search-documents",
        admin_views.AdminSearchDocumentsView.as_view(),
        name="admin-search-documents",
    ),
    path(
        "api/v1/admin/catalog/spus/<uuid:spu_public_id>/overrides",
        admin_views.AdminOverrideDiffView.as_view(),
        name="admin-override-diff",
    ),
    path(
        "api/v1/admin/offers/<uuid:offer_public_id>/inventory",
        admin_views.AdminInventoryAdjustView.as_view(),
        name="admin-inventory-adjust",
    ),
    path("api/v1/admin/reviews", admin_views.AdminReviewsView.as_view(), name="admin-reviews"),
    path(
        "api/v1/admin/crawlers/jobs",
        admin_views.AdminCrawlJobsView.as_view(),
        name="admin-crawl-jobs",
    ),
    path(
        "api/v1/admin/crawlers/jobs/<uuid:job_public_id>/actions",
        admin_views.AdminCrawlJobActionsView.as_view(),
        name="admin-crawl-job-actions",
    ),
    path(
        "api/v1/admin/content/pages",
        admin_views.AdminContentPagesView.as_view(),
        name="admin-content-pages",
    ),
    path("api/v1/admin/buyers", admin_views.AdminBuyersView.as_view(), name="admin-buyers"),
    path("api/v1/admin/orders", admin_views.AdminOrdersView.as_view(), name="admin-orders"),
    path("api/v1/orders", order_views.order_list_create, name="orders"),
    path("api/v1/orders/<uuid:public_id>", order_views.order_detail, name="order-detail"),
    path(
        "api/v1/orders/<uuid:public_id>/payment-attempt",
        order_views.payment_attempt,
        name="payment-attempt",
    ),
    path("api/v1/buyer/favourites", activity_views.favourites, name="buyer-favourites"),
    path(
        "api/v1/buyer/recently-viewed",
        activity_views.recently_viewed,
        name="buyer-recently-viewed",
    ),
    path(
        "api/v1/products/<uuid:public_id>/reviews",
        review_views.product_reviews,
        name="product-reviews",
    ),
    *buyer_urlpatterns,
    *staff_urlpatterns,
    path("api/v1/<path:unmatched>", views.api_not_found, name="api-not-found"),
]

if settings.DEBUG:
    # Development convenience only; production Nginx serves /media/ directly.
    urlpatterns.append(re_path(r"^media/(?P<path>.*)$", serve_media_file))
