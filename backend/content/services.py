"""CMS page services: versioned publishing and the fixture-driven home page."""

from django.db import transaction
from django.utils import timezone

from content.domain import CmsPageStateInvalid
from content.models import CmsModule, CmsPage
from content.schemas import validate_module_payload


def publish_page(*, page_key: str, title: str, modules: list[dict]) -> CmsPage:
    """Publish a new immutable version of a page from typed module dicts.

    Each module dict: ``{"module_type": ..., "payload": {...}}``. Positions
    come from list order. Previously published versions stay for rollback.
    """

    if not page_key.strip() or not title.strip():
        raise CmsPageStateInvalid("page_key and title are required.")
    if not modules:
        raise CmsPageStateInvalid("A page needs at least one module.")
    for index, module in enumerate(modules):
        validate_module_payload(str(module.get("module_type") or ""), module.get("payload") or {})
        if module["module_type"] not in CmsModule.Type.values:
            raise CmsPageStateInvalid(f"Unknown module type: {module['module_type']}.")

    with transaction.atomic():
        next_version = (
            CmsPage.objects.filter(page_key=page_key)
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
            or 0
        ) + 1
        page = CmsPage.objects.create(
            page_key=page_key,
            version=next_version,
            title=title.strip(),
            status=CmsPage.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        CmsModule.objects.bulk_create(
            [
                CmsModule(
                    page=page,
                    module_type=module["module_type"],
                    position=position + 1,
                    payload=module.get("payload") or {},
                )
                for position, module in enumerate(modules)
            ]
        )
        CmsPage.objects.filter(page_key=page_key, version__lt=next_version).exclude(
            status=CmsPage.Status.ARCHIVED
        ).update(status=CmsPage.Status.ARCHIVED)
        return page


def get_published_page(page_key: str) -> CmsPage | None:
    return (
        CmsPage.objects.filter(page_key=page_key, status=CmsPage.Status.PUBLISHED)
        .order_by("-version")
        .first()
    )


def serialize_page(page: CmsPage) -> dict:
    return {
        "page": {
            "key": page.page_key,
            "version": page.version,
            "title": page.title,
            "published_at": page.published_at.isoformat() if page.published_at else None,
        },
        "modules": [
            {
                "position": module.position,
                "type": module.module_type,
                "payload": module.payload,
            }
            for module in page.modules.all()
        ],
    }
