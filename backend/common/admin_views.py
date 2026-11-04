"""Platform admin API (WP-31..35): catalog, reviews, crawlers, CMS, buyers, orders.

All views require staff authentication + TOTP per policy and the declared
``required_permissions``; write operations are audited via the shared audit
service.
"""

import uuid

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from accounts_staff.views import StaffCsrfAPIView
from audit.services import record_audit
from catalog.models import ProductSearchDocument, Spu
from catalog.override_services import (
    clear_local_override,
    propose_local_override,
    review_local_override,
)
from django.db.models import Q
from offers.services import adjust_offer_inventory
from rest_framework.response import Response


def _override_target_for(content_type_model, object_id):
    return content_type_model.objects.get(pk=object_id)


class AdminSearchDocumentsView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.products.manage"]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        queryset = ProductSearchDocument.objects.select_related("spu", "local_category")
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(brand_name__icontains=query))
        rows = [
            {
                "spu_public_id": str(row.spu.public_id),
                "title": row.title,
                "brand": row.brand_name,
                "is_searchable": row.is_searchable,
                "min_price": str(row.min_price) if row.min_price else None,
                "rating_count": row.rating_count,
            }
            for row in queryset[:50]
        ]
        return Response({"items": rows})


class AdminOverrideDiffView(StaffCsrfAPIView):
    """Source vs override differences for one SPU's translation."""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.products.manage"]

    def get(self, request, spu_public_id):
        spu = Spu.objects.filter(public_id=spu_public_id).first()
        if spu is None:
            raise StaffApiError(
                business_code="PRODUCT_NOT_FOUND", message="Unknown product.", status_code=404
            )
        translation = spu.translations.order_by("pk").first()
        if translation is None:
            return Response({"diffs": []})
        from catalog.override_services import list_override_diffs

        return Response({"diffs": list_override_diffs(translation)})

    def post(self, request, spu_public_id):
        spu = Spu.objects.filter(public_id=spu_public_id).first()
        if spu is None:
            raise StaffApiError(
                business_code="PRODUCT_NOT_FOUND", message="Unknown product.", status_code=404
            )
        translation = spu.translations.order_by("pk").first()
        action = str(request.data.get("action") or "")
        field_code = str(request.data.get("field") or "")
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            raise StaffApiError(
                business_code="REASON_REQUIRED", message="A reason is required.", status_code=400
            )

        kwargs = {
            "target": translation,
            "field_code": field_code,
            "reason": reason,
            "request_id": request.request_id,
        }
        if action == "propose":
            override = propose_local_override(
                value=request.data.get("value"), proposed_by=request.staff_account, **kwargs
            )
        elif action in {"approve", "reject"}:
            override = review_local_override(
                decision=request.data.get("decision")
                or ("APPROVED" if action == "approve" else "REJECTED"),
                reviewed_by=request.staff_account,
                **kwargs,
            )
        elif action == "clear":
            override = clear_local_override(cleared_by=request.staff_account, **kwargs)
        else:
            raise StaffApiError(
                business_code="ACTION_INVALID", message="Unknown action.", status_code=400
            )
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"admin.override.{action}",
            target_type="catalog.LocalFieldOverride",
            target_id=str(override.pk),
            reason=reason,
            before_state={},
            after_state={"status": override.status, "version": override.version},
        )
        return Response({"status": override.status, "version": override.version})


class AdminInventoryAdjustView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["offers.manage"]

    def post(self, request, offer_public_id):
        from offers.models import Offer

        offer = Offer.objects.filter(public_id=offer_public_id).first()
        if offer is None:
            raise StaffApiError(
                business_code="OFFER_NOT_FOUND", message="Unknown offer.", status_code=404
            )
        try:
            delta = int(request.data.get("quantity_delta"))
        except (TypeError, ValueError):
            raise StaffApiError(
                business_code="DELTA_INVALID",
                message="quantity_delta must be an integer.",
                status_code=400,
            )
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            raise StaffApiError(
                business_code="REASON_REQUIRED", message="A reason is required.", status_code=400
            )
        try:
            ledger = adjust_offer_inventory(
                offer=offer,
                quantity_delta=delta,
                reason=request.data.get("ledger_reason") or "MANUAL_ADJUSTMENT",
                idempotency_key=str(request.data.get("idempotency_key") or uuid.uuid4()),
                actor=request.staff_account,
                request_id=request.request_id,
                note=reason,
            )
        except Exception as exc:
            raise StaffApiError(
                business_code="ADJUSTMENT_INVALID", message=str(exc), status_code=400
            )
        record_audit(
            request=request,
            actor=request.staff_account,
            action="admin.inventory.adjust",
            target_type="offers.Offer",
            target_id=str(offer.public_id),
            reason=reason,
            before_state={"inventory": offer.local_inventory},
            after_state={"inventory": ledger.balance_after, "delta": delta},
        )
        return Response({"balance_after": ledger.balance_after})


class AdminReviewsView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.products.manage"]

    def get(self, request):
        from reviews.models import Review

        query = (request.query_params.get("q") or "").strip()
        queryset = Review.objects.select_related("spu", "reviewer")
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(body__icontains=query))
        review_status = request.query_params.get("status")
        if review_status in Review.Status.values:
            queryset = queryset.filter(status=review_status)
        rows = [
            {
                "public_id": str(review.public_id),
                "product": review.spu.translations.order_by("pk").first().title
                if review.spu.translations.exists()
                else "",
                "rating": review.rating,
                "title": review.title,
                "display_name": review.reviewer.display_name
                if review.reviewer
                else review.guest_display_name,
                "status": review.status,
            }
            for review in queryset[:50]
        ]
        return Response({"items": rows})

    def post(self, request):
        """Soft-delete or hide one review; history stays intact."""
        from reviews.models import Review
        from reviews.services import mark_source_review_deleted

        review = Review.objects.filter(
            public_id=str(request.data.get("review_public_id") or "")
        ).first()
        if review is None:
            raise StaffApiError(
                business_code="REVIEW_NOT_FOUND", message="Unknown review.", status_code=404
            )
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            raise StaffApiError(
                business_code="REASON_REQUIRED", message="A reason is required.", status_code=400
            )
        if review.origin == Review.Origin.SOURCE:
            mark_source_review_deleted(
                source_system=review.source_system, source_id=review.source_id
            )
        else:
            review.status = Review.Status.HIDDEN
            review.save(update_fields=["status", "updated_at"])
        record_audit(
            request=request,
            actor=request.staff_account,
            action="admin.review.remove",
            target_type="reviews.Review",
            target_id=str(review.public_id),
            reason=reason,
            before_state={"status": Review.Status.ACTIVE},
            after_state={"status": review.status},
        )
        return Response(
            {"status": "DELETED" if review.origin == Review.Origin.SOURCE else review.status}
        )


class AdminCrawlJobsView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["crawler.jobs.manage"]

    def get(self, request):
        from crawler_control.models import CrawlJob

        rows = [
            {
                "public_id": str(job.public_id),
                "name": job.name,
                "status": job.status,
                "sync_mode": job.sync_mode,
                "review_target": job.review_target,
                "created_at": job.created_at.isoformat(),
            }
            for job in CrawlJob.objects.all().order_by("-created_at")[:50]
        ]
        return Response({"items": rows})

    def post(self, request):
        from crawler_control.models import CrawlJob
        from crawler_control.services import create_crawl_job, mark_job_ready

        required = ("name", "source_category_public_id", "product_limit")
        missing = [field for field in required if not request.data.get(field)]
        if missing:
            raise StaffApiError(
                business_code="PARAMS_MISSING",
                message=f"Missing: {', '.join(missing)}.",
                status_code=400,
            )
        from catalog.models import SourceCategory
        from offers.models import Market

        category = SourceCategory.objects.filter(
            public_id=str(request.data["source_category_public_id"])
        ).first()
        if category is None:
            raise StaffApiError(
                business_code="CATEGORY_NOT_FOUND", message="Unknown category.", status_code=404
            )
        market = Market.objects.filter(code="GB", is_active=True).first()
        try:
            job = create_crawl_job(
                name=str(request.data["name"]),
                market=market,
                source_catalog=category.catalog,
                source_category=category,
                product_limit=int(request.data["product_limit"]),
                include_subcategories=request.data.get("include_subcategories"),
                listing_sort=request.data.get("listing_sort", CrawlJob.ListingSort.SOURCE_DEFAULT),
                sync_mode=request.data.get("sync_mode", CrawlJob.SyncMode.INCREMENTAL),
                review_target=request.data.get("review_target", 50),
                created_by=request.staff_account,
            )
            mark_job_ready(job)
        except Exception as exc:
            raise StaffApiError(business_code="JOB_INVALID", message=str(exc), status_code=400)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="admin.crawljob.create",
            target_type="crawler_control.CrawlJob",
            target_id=str(job.public_id),
            reason=str(request.data.get("reason") or "Created from admin"),
            before_state={},
            after_state={"status": job.status, "name": job.name},
        )
        return Response({"public_id": str(job.public_id), "status": job.status}, status=201)


class AdminCrawlJobActionsView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["crawler.jobs.manage"]

    def post(self, request, job_public_id):
        from crawler_control.models import CrawlJob, CrawlRun
        from crawler_control.services import (
            cancel_run,
            mark_job_ready,
            pause_run,
            resume_run,
            start_run,
        )

        job = CrawlJob.objects.filter(public_id=job_public_id).first()
        if job is None:
            raise StaffApiError(
                business_code="JOB_NOT_FOUND", message="Unknown job.", status_code=404
            )
        action = str(request.data.get("action") or "")
        reason = str(request.data.get("reason") or "Admin action").strip()
        try:
            if action == "start":
                run = start_run(job)
                result = {"run": str(run.public_id), "status": run.status}
            elif action == "pause" or action == "cancel":
                run = (
                    CrawlRun.objects.filter(job=job, status="RUNNING").first()
                    or CrawlRun.objects.filter(job=job, status="PAUSED").first()
                )
                if run is None:
                    raise StaffApiError(
                        business_code="RUN_NOT_FOUND",
                        message="No active run to pause.",
                        status_code=409,
                    )
                if action == "pause":
                    pause_run(run, reason="MANUAL")
                    result = {"status": "PAUSED"}
                else:
                    cancel_run(run)
                    result = {"status": "CANCELED"}
            elif action == "resume":
                run = CrawlRun.objects.filter(job=job, status="PAUSED").first()
                if run is None:
                    raise StaffApiError(
                        business_code="RUN_NOT_FOUND", message="No paused run.", status_code=409
                    )
                resumed = resume_run(run)
                result = {"status": resumed.status}
            elif action == "requeue":
                mark_job_ready(job)
                result = {"status": "READY"}
            else:
                raise StaffApiError(
                    business_code="ACTION_INVALID", message="Unknown action.", status_code=400
                )
        except StaffApiError:
            raise
        except Exception as exc:
            raise StaffApiError(business_code="ACTION_FAILED", message=str(exc), status_code=409)
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"admin.crawljob.{action}",
            target_type="crawler_control.CrawlJob",
            target_id=str(job.public_id),
            reason=reason,
            before_state={"status": job.status},
            after_state=result,
        )
        return Response(result)


class AdminContentPagesView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.products.manage"]

    def get(self, request):
        from content.models import CmsPage

        pages = [
            {
                "public_id": str(page.public_id),
                "page_key": page.page_key,
                "version": page.version,
                "status": page.status,
                "module_count": page.modules.count(),
            }
            for page in CmsPage.objects.all().order_by("page_key", "-version")[:50]
        ]
        return Response({"items": pages})

    def post(self, request):
        from content.services import publish_page

        try:
            page = publish_page(
                page_key=str(request.data.get("page_key") or "home"),
                title=str(request.data.get("title") or "Untitled"),
                modules=request.data.get("modules") or [],
            )
        except Exception as exc:
            raise StaffApiError(business_code="PAGE_INVALID", message=str(exc), status_code=400)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="admin.cms.publish",
            target_type="content.CmsPage",
            target_id=str(page.public_id),
            reason=str(request.data.get("reason") or "Published from admin"),
            before_state={},
            after_state={"version": page.version, "modules": page.modules.count()},
        )
        return Response({"public_id": str(page.public_id), "version": page.version}, status=201)


class AdminBuyersView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["staff.roles.manage"]

    def get(self, request):
        from accounts_buyers.models import BuyerAccount

        query = (request.query_params.get("q") or "").strip()
        queryset = BuyerAccount.objects.all()
        if query:
            queryset = queryset.filter(Q(email__icontains=query) | Q(phone__icontains=query))
        rows = [
            {
                "public_id": str(account.public_id),
                "email": account.email,
                "phone": account.phone,
                "status": account.status,
                "created_at": account.created_at.isoformat(),
            }
            for account in queryset[:50]
        ]
        return Response({"items": rows})

    def post(self, request):
        from accounts_buyers.models import BuyerAccount

        account = BuyerAccount.objects.filter(
            public_id=str(request.data.get("buyer_public_id") or "")
        ).first()
        if account is None:
            raise StaffApiError(
                business_code="BUYER_NOT_FOUND", message="Unknown buyer.", status_code=404
            )
        action = str(request.data.get("action") or "")
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            raise StaffApiError(
                business_code="REASON_REQUIRED", message="A reason is required.", status_code=400
            )
        if action not in {"disable", "enable"}:
            raise StaffApiError(
                business_code="ACTION_INVALID",
                message="Action must be disable or enable.",
                status_code=400,
            )
        # Buyers are never deleted (docs/01 §3.3); status only.
        before = account.status
        account.status = (
            BuyerAccount.Status.DISABLED if action == "disable" else BuyerAccount.Status.ACTIVE
        )
        account.save(update_fields=["status", "updated_at"])
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"admin.buyer.{action}",
            target_type="accounts_buyers.BuyerAccount",
            target_id=str(account.public_id),
            reason=reason,
            before_state={"status": before},
            after_state={"status": account.status},
        )
        return Response({"status": account.status})


class AdminOrdersView(StaffCsrfAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["staff.roles.manage"]

    def get(self, request):
        from orders.models import Order

        order_status = request.query_params.get("status")
        queryset = Order.objects.all().order_by("-created_at")
        if order_status in Order.Status.values:
            queryset = queryset.filter(status=order_status)
        rows = [
            {
                "public_id": str(order.public_id),
                "status": order.status,
                "total": str(order.total),
                "currency": order.currency.code,
                "created_at": order.created_at.isoformat(),
                "item_count": order.items.count(),
            }
            for order in queryset[:50]
        ]
        return Response({"items": rows})
