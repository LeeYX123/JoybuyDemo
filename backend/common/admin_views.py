"""Platform admin API (WP-31..35): catalog, reviews, crawlers, CMS, buyers, orders.

All views require staff authentication + TOTP per policy and the declared
``required_permissions``; write operations are audited via the shared audit
service.
"""

import uuid

from django.db.models import Count, Q
from rest_framework.response import Response

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
from offers.services import adjust_offer_inventory


def _override_target_for(content_type_model, object_id):
    return content_type_model.objects.get(pk=object_id)


def _spawn_run_executor(run) -> None:
    """Launch the crawl executor for a run in a detached subprocess.

    The executor is a separate process so a crash (or the web server
    restarting) never silently leaves a run stuck in RUNNING: the runner
    wrapper always writes a terminal status back (requirement: failures
    must update task state).
    """

    import os
    import subprocess
    import sys
    from pathlib import Path

    from django.conf import settings

    log_dir = Path(settings.BASE_DIR).parent / "var" / "logs" / "crawl_runs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run.public_id}.log"
    python = Path(sys.executable)
    manage_py = Path(settings.BASE_DIR) / "manage.py"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        with open(log_path, "ab") as log_file:
            subprocess.Popen(
                [
                    str(python),
                    str(manage_py),
                    "run_crawl_run",
                    "--run",
                    str(run.public_id),
                ],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=str(manage_py.parent),
                env=env,
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
                if os.name == "nt"
                else 0,
            )
    except Exception as exc:  # noqa: BLE001 - spawn failure must not fail the API
        from crawler_control.models import CrawlRunEvent
        from crawler_control.services import record_run_event

        record_run_event(
            run,
            level=CrawlRunEvent.Level.ERROR,
            code="RUNNER_SPAWN_FAILED",
            message=f"Failed to launch the crawl executor: {exc}",
        )


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


class AdminCrawlerAccountsView(StaffCsrfAPIView):
    """Crawler account management (docs/05 §7.1): no passwords, ever."""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["crawler.accounts.manage"]

    def get(self, request):
        from crawler_control.models import CrawlerAccount

        rows = [
            {
                "public_id": str(account.public_id),
                "label": account.label,
                "account_group": account.account_group,
                "status": account.status,
                "session_status": account.session_status,
                "session_updated_at": account.session_updated_at.isoformat()
                if account.session_updated_at
                else None,
                "last_verified_at": account.last_verified_at.isoformat()
                if account.last_verified_at
                else None,
                "risk_flagged_at": account.risk_flagged_at.isoformat()
                if account.risk_flagged_at
                else None,
                "risk_reason": account.risk_reason,
                "note": account.note,
                "updated_at": account.updated_at.isoformat(),
            }
            for account in CrawlerAccount.objects.filter(deleted_at__isnull=True).order_by(
                "-created_at"
            )[:50]
        ]
        return Response({"items": rows})

    def post(self, request):
        from crawler_control.services import create_crawler_account

        label = str(request.data.get("label") or "").strip()
        if not label:
            raise StaffApiError(
                business_code="PARAMS_MISSING", message="账号名称必填。", status_code=400
            )
        try:
            account = create_crawler_account(
                label=label,
                account_group=str(request.data.get("account_group") or "default").strip()
                or "default",
                note=str(request.data.get("note") or "").strip(),
            )
        except Exception as exc:
            raise StaffApiError(business_code="ACCOUNT_INVALID", message=str(exc), status_code=400)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="admin.crawleraccount.create",
            target_type="crawler_control.CrawlerAccount",
            target_id=str(account.public_id),
            reason=str(request.data.get("reason") or "Created from admin"),
            before_state={},
            after_state={"label": account.label, "account_group": account.account_group},
        )
        return Response({"public_id": str(account.public_id)}, status=201)


class AdminCrawlerAccountDetailView(StaffCsrfAPIView):
    """Edit or delete one account (2026-11-05).

    Deleting is a soft delete: the row leaves the management screens and its
    stored session is destroyed, but historical runs keep the label.
    """

    permission_classes = [StaffRbacPermission]
    required_permissions = ["crawler.accounts.manage"]

    def _account(self, account_public_id):
        from crawler_control.models import CrawlerAccount

        account = CrawlerAccount.objects.filter(
            public_id=account_public_id, deleted_at__isnull=True
        ).first()
        if account is None:
            raise StaffApiError(
                business_code="ACCOUNT_NOT_FOUND", message="Unknown account.", status_code=404
            )
        return account

    def put(self, request, account_public_id):
        return self._update(request, account_public_id)

    def patch(self, request, account_public_id):
        return self._update(request, account_public_id)

    def _update(self, request, account_public_id):
        from crawler_control.services import update_crawler_account

        account = self._account(account_public_id)
        before = {
            "label": account.label,
            "account_group": account.account_group,
            "note": account.note,
        }
        try:
            update_crawler_account(
                account,
                label=request.data.get("label"),
                account_group=request.data.get("account_group"),
                note=request.data.get("note"),
            )
        except Exception as exc:
            raise StaffApiError(business_code="ACCOUNT_INVALID", message=str(exc), status_code=400)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="admin.crawleraccount.update",
            target_type="crawler_control.CrawlerAccount",
            target_id=str(account.public_id),
            reason=str(request.data.get("reason") or "Edited from admin"),
            before_state=before,
            after_state={
                "label": account.label,
                "account_group": account.account_group,
                "note": account.note,
            },
        )
        return Response(
            {
                "public_id": str(account.public_id),
                "label": account.label,
                "account_group": account.account_group,
                "note": account.note,
            }
        )

    def delete(self, request, account_public_id):
        from crawler_control.services import delete_crawler_account

        account = self._account(account_public_id)
        before = {
            "label": account.label,
            "account_group": account.account_group,
            "status": account.status,
        }
        try:
            delete_crawler_account(account, reason=str(request.data.get("reason") or "").strip())
        except Exception as exc:
            raise StaffApiError(
                business_code="ACCOUNT_NOT_DELETABLE", message=str(exc), status_code=409
            )
        record_audit(
            request=request,
            actor=request.staff_account,
            action="admin.crawleraccount.delete",
            target_type="crawler_control.CrawlerAccount",
            target_id=str(account.public_id),
            reason=str(request.data.get("reason") or "Deleted from admin"),
            before_state=before,
            after_state={"deleted": True, "session_cleared": True},
        )
        return Response({"public_id": str(account.public_id), "deleted": True})


class AdminCrawlerAccountGroupsView(StaffCsrfAPIView):
    """List and create account groups (2026-11-05)."""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["crawler.accounts.manage"]

    def get(self, request):
        from crawler_control.models import CrawlerAccount
        from crawler_control.services import list_account_groups

        counts = {
            row["account_group"]: row["total"]
            for row in CrawlerAccount.objects.filter(deleted_at__isnull=True)
            .values("account_group")
            .annotate(total=Count("id"))
        }
        return Response(
            {
                "items": [
                    {
                        "name": group.name,
                        "note": group.note,
                        "account_count": counts.get(group.name, 0),
                    }
                    for group in list_account_groups()
                ]
            }
        )

    def post(self, request):
        from crawler_control.services import create_account_group

        name = str(request.data.get("name") or "").strip()
        if not name:
            raise StaffApiError(
                business_code="PARAMS_MISSING", message="账号组名称必填。", status_code=400
            )
        try:
            group = create_account_group(name=name, note=str(request.data.get("note") or ""))
        except Exception as exc:
            raise StaffApiError(business_code="GROUP_INVALID", message=str(exc), status_code=400)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="admin.crawleraccountgroup.create",
            target_type="crawler_control.CrawlerAccountGroup",
            target_id=str(group.pk),
            reason=str(request.data.get("reason") or "Created from admin"),
            before_state={},
            after_state={"name": group.name},
        )
        return Response({"name": group.name, "note": group.note}, status=201)


class AdminCrawlerAccountActionsView(StaffCsrfAPIView):
    """Actions: login (headed manual window), logout, verify, disable, enable, reactivate."""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["crawler.accounts.manage"]

    def post(self, request, account_public_id):
        from crawler_control.models import CrawlerAccount
        from crawler_control.services import (
            mark_session_expired,
            reactivate_account,
            set_account_status,
            verify_account_session,
        )

        account = CrawlerAccount.objects.filter(
            public_id=account_public_id, deleted_at__isnull=True
        ).first()
        if account is None:
            raise StaffApiError(
                business_code="ACCOUNT_NOT_FOUND", message="Unknown account.", status_code=404
            )
        action = str(request.data.get("action") or "")
        try:
            if action == "login":
                result = self._spawn_login_window(account)
            elif action == "logout":
                mark_session_expired(account)
                result = {"status": "EXPIRED"}
            elif action == "verify":
                result = verify_account_session(account)
                result["status"] = "VALID" if result.get("verified") else "CHECK_FAILED"
            elif action == "disable":
                set_account_status(account, status=CrawlerAccount.Status.DISABLED)
                result = {"status": "DISABLED"}
            elif action == "enable":
                set_account_status(account, status=CrawlerAccount.Status.ACTIVE)
                result = {"status": "ACTIVE"}
            elif action == "reactivate":
                reactivate_account(account, note="Reactivated from admin")
                result = {"status": "ACTIVE"}
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
            action=f"admin.crawleraccount.{action}",
            target_type="crawler_control.CrawlerAccount",
            target_id=str(account.public_id),
            reason=str(request.data.get("reason") or f"Admin action: {action}"),
            before_state={"status": account.status, "session_status": account.session_status},
            after_state=result,
        )
        return Response(result)

    @staticmethod
    def _spawn_login_window(account) -> dict:
        """Launch the headed manual-login window as a detached subprocess."""

        import os
        import subprocess
        import sys
        from pathlib import Path

        from django.conf import settings

        log_dir = Path(settings.BASE_DIR).parent / "var" / "logs" / "crawl_runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"account-{str(account.public_id)[:8]}.log"
        python = Path(sys.executable)
        manage_py = Path(settings.BASE_DIR) / "manage.py"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        try:
            with open(log_path, "ab") as log_file:
                subprocess.Popen(
                    [
                        str(python),
                        str(manage_py),
                        "crawler_account_login",
                        "--account",
                        str(account.public_id),
                    ],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=str(manage_py.parent),
                    env=env,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                    )
                    if os.name == "nt"
                    else 0,
                )
        except Exception as exc:  # noqa: BLE001 - spawn failure must not fail the API
            raise StaffApiError(
                business_code="LOGIN_SPAWN_FAILED",
                message=f"无法打开登录窗口：{exc}",
                status_code=500,
            )
        return {"status": "LOGIN_PENDING"}


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

        jobs = (
            CrawlJob.objects.select_related("account")
            .prefetch_related("source_selections__source_category__snapshots")
            .order_by("-created_at")[:50]
        )
        rows = []
        for job in jobs:
            category_names = []
            for selection in job.source_selections.all():
                snapshot = (
                    selection.source_category.snapshots.filter(
                        tree_version=selection.source_tree_version
                    ).first()
                    if selection.source_tree_version_id
                    else None
                )
                category_names.append(
                    (snapshot.name_zh or snapshot.name)
                    if snapshot
                    else selection.source_category.source_id
                )
            rows.append(
                {
                    "public_id": str(job.public_id),
                    "name": job.name,
                    "status": job.status,
                    "categories": "、".join(category_names) or "—",
                    "sync_mode": job.sync_mode,
                    "review_target": job.review_target,
                    "account_group": job.account_group,
                    "account_label": job.account.label if job.account else "",
                    "created_at": job.created_at.isoformat(),
                }
            )
        return Response({"items": rows})

    def post(self, request):
        from catalog.models import SourceCategory
        from crawler_control.models import CrawlJob
        from crawler_control.services import create_crawl_job, mark_job_ready
        from offers.models import Market

        name = request.data.get("name")
        product_limit = request.data.get("product_limit")
        # 类目身份 = source_id（l2:1405 / minihome:...）；category_public_ids
        # 是旧字段名，值同样是 source_id（SourceCategory 无 public_id 列）。
        category_ids = (
            request.data.get("source_ids") or request.data.get("category_public_ids") or []
        )
        category_entries = request.data.get("categories") or []
        legacy_category_id = request.data.get("source_category_public_id")
        if (
            not name
            or not product_limit
            or (not category_ids and not category_entries and not legacy_category_id)
        ):
            raise StaffApiError(
                business_code="PARAMS_MISSING",
                message="Missing: name, product_limit and at least one category.",
                status_code=400,
            )

        public_ids = [str(item) for item in category_ids]
        entries = [
            {
                "source_id": str(entry.get("source_id") or entry.get("public_id")),
                "include_descendants": bool(entry.get("include_descendants", True)),
            }
            for entry in category_entries
            if entry.get("source_id") or entry.get("public_id")
        ]
        if legacy_category_id:
            public_ids.append(str(legacy_category_id))
        if not public_ids and not entries:
            raise StaffApiError(
                business_code="PARAMS_MISSING", message="No category selected.", status_code=400
            )

        # 类目身份是 source_id（如 l2:1405 / minihome:...），不是 UUID——
        # SourceCategory 没有 public_id 字段（2026-11-05 UI 实测发现的坏假设）。
        wanted_ids = set(public_ids) | {entry["source_id"] for entry in entries}
        categories = {
            category.source_id: category
            for category in SourceCategory.objects.filter(source_id__in=wanted_ids)
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
            if pid in categories
        ]
        for entry in entries:
            if entry["source_id"] in categories:
                selections.append(
                    {
                        "category": categories[entry["source_id"]],
                        "include_descendants": entry["include_descendants"],
                    }
                )
        if not selections:
            raise StaffApiError(
                business_code="CATEGORY_NOT_FOUND",
                message="No valid category selected.",
                status_code=404,
            )

        market = Market.objects.filter(code="GB", is_active=True).first()

        # 指定爬虫账号（2026-11-05）：不传则沿用账号组自动选号；指定账号时
        # 账号组跟着该账号走，避免"指定了 A 组账号、自动回退却跑到 B 组"。
        from crawler_control.models import CrawlerAccount

        account = None
        account_public_id = request.data.get("account_public_id")
        if account_public_id:
            account = CrawlerAccount.objects.filter(public_id=str(account_public_id)).first()
            if account is None:
                raise StaffApiError(
                    business_code="ACCOUNT_NOT_FOUND",
                    message="指定的爬虫账号不存在。",
                    status_code=404,
                )
            if account.status != CrawlerAccount.Status.ACTIVE:
                raise StaffApiError(
                    business_code="ACCOUNT_UNAVAILABLE",
                    message=f"账号「{account.label}」已停用或处于风控暂停，不能指定给任务。",
                    status_code=400,
                )
        account_group = request.data.get("account_group") or (
            account.account_group if account else "default"
        )

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
                account_group=str(account_group),
                account=account,
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
            .select_related("source_tree_version", "account")
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
                    "name_zh": snapshot.name_zh if snapshot else "",
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
                "account_label": run.account.label if run.account else "",
            }
            for run in job.runs.select_related("account").order_by("-created_at")[:10]
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
                for event in latest_run.events.order_by("-created_at")[:200]
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
                "account_group": job.account_group,
                "account": {
                    "public_id": str(job.account.public_id),
                    "label": job.account.label,
                    "status": job.account.status,
                    "session_status": job.account.session_status,
                }
                if job.account
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
                _spawn_run_executor(run)
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
            queryset = queryset.filter(Q(email__icontains=query) | Q(phone_e164__icontains=query))
        rows = [
            {
                "public_id": str(account.public_id),
                "email": account.email,
                # 模型字段是 phone_e164；此前误写成 account.phone，该接口一直 500。
                "phone": account.phone_e164,
                "status": account.status,
                "purchase_whitelisted": account.purchase_whitelisted,
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
