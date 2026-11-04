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


class AdminCrawlerSourceTreeView(StaffCsrfAPIView):
    """Published Joybuy source category tree for the job-creation picker."""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["crawler.jobs.manage"]

    def get(self, request):
        from catalog.models import SourceCatalog
        from crawler_control.tree_sync import latest_published_tree, tree_to_payload

        catalog = SourceCatalog.objects.filter(source_system="joybuy_uk").first()
        if catalog is None:
            return Response({"version": None, "categories": []})
        tree_version = latest_published_tree(catalog)
        if tree_version is None:
            return Response({"version": None, "categories": []})
        payload = tree_to_payload(tree_version)
        return Response({"version": payload["version_key"], **payload})


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
        from catalog.models import SourceCategory
        from crawler_control.models import CrawlJob
        from crawler_control.services import create_crawl_job, mark_job_ready
        from offers.models import Market

        name = request.data.get("name")
        product_limit = request.data.get("product_limit")
        category_ids = request.data.get("category_public_ids") or []
        category_entries = request.data.get("categories") or []
        legacy_category_id = request.data.get("source_category_public_id")
        if not name or not product_limit or (
            not category_ids and not category_entries and not legacy_category_id
        ):
            raise StaffApiError(
                business_code="PARAMS_MISSING",
                message="Missing: name, product_limit and at least one category.",
                status_code=400,
            )

        public_ids = [str(item) for item in category_ids]
        entries = [
            {
                "public_id": str(entry.get("public_id")),
                "include_descendants": bool(entry.get("include_descendants", True)),
            }
            for entry in category_entries
            if entry.get("public_id")
        ]
        if legacy_category_id:
            public_ids.append(str(legacy_category_id))
        if not public_ids and not entries:
            raise StaffApiError(
                business_code="PARAMS_MISSING", message="No category selected.", status_code=400
            )

        wanted_ids = {entry["public_id"] for entry in entries} | set(public_ids)
        categories = {
            str(category.public_id): category
            for category in SourceCategory.objects.filter(public_id__in=wanted_ids)
        }
        unknown = sorted(wanted_ids - set(categories))
        if unknown:
            raise StaffApiError(
                business_code="CATEGORY_NOT_FOUND",
                message=f"Unknown category ids: {', '.join(unknown[:5])}.",
                status_code=404,
            )
        include_default = request.data.get("include_subcategories")
        if include_default is None:
            include_default = True
        selections = [
            {"category": categories[pid], "include_descendants": bool(include_default)}
            for pid in public_ids
        ]
        for entry in entries:
            selections.append(
                {
                    "category": categories[entry["public_id"]],
                    "include_descendants": entry["include_descendants"],
                }
            )

        market = Market.objects.filter(code="GB", is_active=True).first()
        try:
            job = create_crawl_job(
                name=str(name),
                market=market,
                source_catalog=selections[0]["category"].catalog,
                source_categories=selections,
                product_limit=int(product_limit),
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
            after_state={
                "status": job.status,
                "name": job.name,
                "categories": [entry["category"].source_id for entry in selections],
            },
        )
        return Response({"public_id": str(job.public_id), "status": job.status}, status=201)


class AdminCrawlJobDetailView(StaffCsrfAPIView):
    """Job detail: frozen category selections, runs and recent events."""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["crawler.jobs.manage"]

    def get(self, request, job_public_id):
        from crawler_control.models import CrawlJob

        job = (
            CrawlJob.objects.filter(public_id=job_public_id)
            .select_related("source_tree_version")
            .first()
        )
        if job is None:
            raise StaffApiError(
                business_code="JOB_NOT_FOUND", message="Unknown job.", status_code=404
            )
        selections = []
        for selection in job.source_selections.select_related(
            "source_category", "source_tree_version"
        ).order_by("sort_order", "pk"):
            snapshot = selection.source_category.snapshots.filter(
                tree_version=selection.source_tree_version
            ).first()
            selections.append(
                {
                    "source_id": selection.source_category.source_id,
                    "name": snapshot.name if snapshot else selection.source_category.source_id,
                    "include_descendants": selection.include_descendants,
                }
            )
        runs = [
            {
                "public_id": str(run.public_id),
                "status": run.status,
                "pause_reason": run.pause_reason,
                "discovered_count": run.discovered_count,
                "downloaded_count": run.downloaded_count,
                "succeeded_count": run.succeeded_count,
                "failed_count": run.failed_count,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
            for run in job.runs.order_by("-created_at")[:10]
        ]
        latest_run = job.runs.order_by("-created_at").first()
        events = []
        if latest_run is not None:
            events = [
                {
                    "level": event.level,
                    "code": event.code,
                    "message": event.message,
                    "source_url": event.source_url,
                    "created_at": event.created_at.isoformat(),
                }
                for event in latest_run.events.order_by("-created_at")[:50]
            ]
        return Response(
            {
                "public_id": str(job.public_id),
                "name": job.name,
                "status": job.status,
                "product_limit": job.product_limit,
                "sync_mode": job.sync_mode,
                "review_target": job.review_target,
                "listing_sort": job.listing_sort,
                "category_mode": job.category_mode,
                "source_tree_version": job.source_tree_version.version_key
                if job.source_tree_version
                else None,
                "categories": selections,
                "runs": runs,
                "events": events,
            }
        )


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
