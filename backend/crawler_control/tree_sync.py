"""Joybuy source category tree sync (docs/09 口径).

Turns a captured Joybuy category menu into a versioned
``SourceCategoryTreeVersion`` + ``SourceCategorySnapshot`` set so crawl
jobs can list real Joybuy categories and freeze the tree at creation
time. Raw public IDs are stored verbatim (``firstcid``, ``l1``,
``cid1..cid4`` prefixes are part of the identity and never normalized
away — see docs/09 §2.1).

The pure tree-building logic lives here so it can be tested offline; the
live menu capture (browser rendering) lives in the sync command.
"""

import hashlib
from dataclasses import dataclass, field

from catalog.models import SourceCategory, SourceCategorySnapshot, SourceCategoryTreeVersion
from django.db import transaction
from django.utils import timezone

from crawler_control.domain import CrawlJobParamsInvalid


@dataclass
class MenuNode:
    """One captured menu entry: name + verbatim source id + optional URL."""

    name: str
    source_id: str
    source_url: str = ""
    children: list["MenuNode"] = field(default_factory=list)


@dataclass
class TreeSyncResult:
    tree_version: SourceCategoryTreeVersion
    created_categories: int
    created_snapshots: int
    new_source_ids: list[str]
    missing_source_ids: list[str]


def compute_structure_hash(nodes: list[MenuNode]) -> str:
    digest = hashlib.sha256()
    for node in nodes:
        digest.update(f"{node.source_id}|{node.name}|{node.source_url}".encode())
        for child in node.children:
            digest.update(f"  {child.source_id}|{child.name}|{child.source_url}".encode())
    return digest.hexdigest()


def _get_catalog_category(catalog, source_id: str) -> SourceCategory:
    now = timezone.now()
    category, created = SourceCategory.objects.get_or_create(
        catalog=catalog,
        source_id=source_id,
        defaults={"first_seen_at": now, "last_seen_at": now},
    )
    if not created and not category.is_active:
        category.is_active = True
        category.save(update_fields=["is_active", "updated_at"])
    return category


@transaction.atomic
def sync_category_tree(catalog, nodes: list[MenuNode], *, publish: bool = True) -> TreeSyncResult:
    """Write one new tree version from captured menu nodes (idempotent per hash).

    Nodes already covered by the previous published version keep their
    SourceCategory rows; new ids create fresh rows. The latest previously
    published version is used only to report the diff — snapshots are
    always rebuilt for the new version.
    """

    if not nodes:
        raise CrawlJobParamsInvalid("The captured Joybuy menu is empty; refusing to sync.")
    for node in nodes:
        if not node.source_id or not node.name.strip():
            raise CrawlJobParamsInvalid(
                f"Menu node '{node.name}' has no verbatim source id; raw ids are mandatory."
            )

    now = timezone.now()
    structure_hash = compute_structure_hash(nodes)
    version_key = f"joybuy-uk-{now.strftime('%Y%m%d')}-{structure_hash[:8]}"

    previous = (
        SourceCategoryTreeVersion.objects.filter(
            catalog=catalog,
            status=SourceCategoryTreeVersion.Status.PUBLISHED,
        )
        .order_by("-captured_at", "-pk")
        .first()
    )
    previous_ids = set(
        SourceCategorySnapshot.objects.filter(tree_version=previous).values_list(
            "category__source_id", flat=True
        )
    ) if previous else set()

    tree_version = SourceCategoryTreeVersion.objects.create(
        catalog=catalog,
        version_key=version_key,
        structure_hash=structure_hash,
        captured_at=now,
        metadata={"node_count": len(nodes)},
    )

    new_source_ids = []
    created_snapshots = 0
    snapshot_by_id = {}
    for sort_order, node in enumerate(nodes):
        category = _get_catalog_category(catalog, node.source_id)
        if node.source_id not in previous_ids:
            new_source_ids.append(node.source_id)
        snapshot = SourceCategorySnapshot.objects.create(
            tree_version=tree_version,
            category=category,
            parent=None,
            name=node.name.strip(),
            source_url=node.source_url or "",
            sort_order=sort_order,
            depth=0,
            path=f"/{category.pk}/",
        )
        snapshot_by_id[node.source_id] = snapshot
        created_snapshots += 1
        for child_order, child in enumerate(node.children):
            child_category = _get_catalog_category(catalog, child.source_id)
            if child.source_id not in previous_ids:
                new_source_ids.append(child.source_id)
            child_snapshot = SourceCategorySnapshot.objects.create(
                tree_version=tree_version,
                category=child_category,
                parent=snapshot,
                name=child.name.strip(),
                source_url=child.source_url or "",
                sort_order=child_order,
                depth=1,
                path=f"{snapshot.path}{child_category.pk}/",
            )
            snapshot_by_id[child.source_id] = child_snapshot
            created_snapshots += 1

    if publish:
        tree_version.status = SourceCategoryTreeVersion.Status.PUBLISHED
        tree_version.published_at = now
        tree_version.save(update_fields=["status", "published_at", "updated_at"])
        catalog.current_version = tree_version
        catalog.save(update_fields=["current_version", "updated_at"])

    return TreeSyncResult(
        tree_version=tree_version,
        created_categories=len({node.source_id for node in nodes})
        + len({child.source_id for node in nodes for child in node.children}),
        created_snapshots=created_snapshots,
        new_source_ids=new_source_ids,
        missing_source_ids=sorted(previous_ids - {item.source_id for item in snapshot_by_id}),
    )


def latest_published_tree(catalog) -> SourceCategoryTreeVersion | None:
    return (
        SourceCategoryTreeVersion.objects.filter(
            catalog=catalog,
            status=SourceCategoryTreeVersion.Status.PUBLISHED,
        )
        .order_by("-captured_at", "-pk")
        .first()
    )


def tree_to_payload(tree_version: SourceCategoryTreeVersion) -> dict:
    """Render a published tree version as the admin API payload."""

    snapshots = list(
        SourceCategorySnapshot.objects.filter(tree_version=tree_version)
        .select_related("category")
        .order_by("path", "sort_order", "pk")
    )
    by_pk = {}
    roots = []
    for snapshot in snapshots:
        by_pk[snapshot.pk] = {
            "source_id": snapshot.category.source_id,
            "name": snapshot.name,
            "source_url": snapshot.source_url,
            "depth": snapshot.depth,
            "children": [],
        }
        if snapshot.parent_id and snapshot.parent_id in by_pk:
            by_pk[snapshot.parent_id]["children"].append(by_pk[snapshot.pk])
        else:
            roots.append(by_pk[snapshot.pk])
    return {
        "version_key": tree_version.version_key,
        "captured_at": tree_version.captured_at.isoformat(),
        "published_at": tree_version.published_at.isoformat() if tree_version.published_at else None,
        "categories": roots,
    }
