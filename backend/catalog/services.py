import hashlib
import json
from collections.abc import Iterable

from django.db import transaction
from django.utils import timezone

from catalog.domain import CategoryMoveInvalid, CategoryTreeInvalid, CategoryVersionConflict
from catalog.models import (
    LocalCategory,
    SourceCatalog,
    SourceCategory,
    SourceCategorySnapshot,
    SourceCategoryTreeVersion,
)


def _normalize_source_nodes(nodes: Iterable[dict]) -> tuple[dict[str, dict], list[str]]:
    normalized = {}
    for raw_node in nodes:
        source_id = str(raw_node.get("source_id", "")).strip()
        name = str(raw_node.get("name", "")).strip()
        parent_value = raw_node.get("parent_source_id")
        parent_source_id = str(parent_value).strip() if parent_value is not None else None
        if not source_id or not name:
            raise CategoryTreeInvalid("Each source category requires source_id and name.")
        if source_id in normalized:
            raise CategoryTreeInvalid(f"Duplicate source category ID: {source_id}.")
        normalized[source_id] = {
            "source_id": source_id,
            "name": name,
            # 中文名只影响展示，不参与结构哈希与版本判定。
            "name_zh": str(raw_node.get("name_zh", "")).strip(),
            "parent_source_id": parent_source_id or None,
            "source_url": str(raw_node.get("source_url", "")).strip(),
            "sort_order": int(raw_node.get("sort_order", 0)),
        }

    if not normalized:
        raise CategoryTreeInvalid("A source category version cannot be empty.")

    for node in normalized.values():
        parent_id = node["parent_source_id"]
        if parent_id is not None and parent_id not in normalized:
            raise CategoryTreeInvalid(
                f"Unknown parent {parent_id} for source category {node['source_id']}."
            )

    ordered = []
    visiting = set()
    visited = set()

    def visit(source_id: str) -> None:
        if source_id in visited:
            return
        if source_id in visiting:
            raise CategoryTreeInvalid("The source category tree contains a cycle.")
        visiting.add(source_id)
        parent_id = normalized[source_id]["parent_source_id"]
        if parent_id is not None:
            visit(parent_id)
        visiting.remove(source_id)
        visited.add(source_id)
        ordered.append(source_id)

    for source_id in normalized:
        visit(source_id)
    return normalized, ordered


def _structure_hash(nodes: dict[str, dict]) -> str:
    canonical = json.dumps(
        [nodes[source_id] for source_id in sorted(nodes)],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def save_source_category_version(
    *,
    source_system: str,
    version_key: str,
    nodes: Iterable[dict],
    captured_at=None,
    metadata: dict | None = None,
) -> SourceCategoryTreeVersion:
    normalized_system = source_system.strip().casefold()
    normalized_version_key = version_key.strip()
    if not normalized_system or not normalized_version_key:
        raise CategoryTreeInvalid("source_system and version_key are required.")
    normalized_nodes, ordered_ids = _normalize_source_nodes(nodes)
    structure_hash = _structure_hash(normalized_nodes)
    captured_at = captured_at or timezone.now()

    catalog, _ = SourceCatalog.objects.get_or_create(
        source_system=normalized_system,
        defaults={"display_name": normalized_system},
    )
    with transaction.atomic():
        catalog = SourceCatalog.objects.select_for_update().get(pk=catalog.pk)
        existing = SourceCategoryTreeVersion.objects.filter(
            catalog=catalog,
            version_key=normalized_version_key,
        ).first()
        if existing:
            if existing.structure_hash != structure_hash:
                raise CategoryVersionConflict(
                    "The version key already exists with a different category structure."
                )
            return existing

        version = SourceCategoryTreeVersion.objects.create(
            catalog=catalog,
            version_key=normalized_version_key,
            structure_hash=structure_hash,
            captured_at=captured_at,
            metadata=metadata or {},
        )
        identities = {}
        for source_id in ordered_ids:
            identity, created = SourceCategory.objects.get_or_create(
                catalog=catalog,
                source_id=source_id,
                defaults={
                    "is_active": True,
                    "first_seen_at": captured_at,
                    "last_seen_at": captured_at,
                },
            )
            if not created:
                identity.is_active = True
                identity.last_seen_at = captured_at
                if node_zh := normalized_nodes[source_id]["name_zh"]:
                    identity.name_zh = node_zh
                    identity.save(
                        update_fields=["is_active", "last_seen_at", "name_zh", "updated_at"]
                    )
                else:
                    identity.save(update_fields=["is_active", "last_seen_at", "updated_at"])
            identities[source_id] = identity

        SourceCategory.objects.filter(catalog=catalog).exclude(
            source_id__in=normalized_nodes
        ).update(is_active=False, updated_at=timezone.now())

        snapshots = {}
        for source_id in ordered_ids:
            node = normalized_nodes[source_id]
            parent = snapshots.get(node["parent_source_id"])
            identity = identities[source_id]
            path = f"{parent.path}{identity.pk}/" if parent else f"/{identity.pk}/"
            snapshot = SourceCategorySnapshot.objects.create(
                tree_version=version,
                category=identity,
                parent=parent,
                name=node["name"],
                name_zh=node["name_zh"] or identity.name_zh,
                source_url=node["source_url"],
                sort_order=node["sort_order"],
                depth=parent.depth + 1 if parent else 0,
                path=path,
            )
            snapshots[source_id] = snapshot

        published_at = timezone.now()
        version.status = SourceCategoryTreeVersion.Status.PUBLISHED
        version.published_at = published_at
        version.save(update_fields=["status", "published_at"])
        catalog.current_version = version
        catalog.save(update_fields=["current_version", "updated_at"])
        return version


def source_category_descendants(snapshot: SourceCategorySnapshot, *, include_self: bool = False):
    queryset = SourceCategorySnapshot.objects.filter(
        tree_version=snapshot.tree_version,
        path__startswith=snapshot.path,
    )
    if not include_self:
        queryset = queryset.exclude(pk=snapshot.pk)
    return queryset.order_by("path", "sort_order", "pk")


def create_local_category(
    *,
    name: str,
    slug: str,
    parent: LocalCategory | None = None,
    sort_order: int = 0,
    status: str = LocalCategory.Status.ACTIVE,
) -> LocalCategory:
    with transaction.atomic():
        if parent is not None:
            parent = LocalCategory.objects.select_for_update().get(pk=parent.pk)
        category = LocalCategory.objects.create(
            name=name.strip(),
            slug=slug.strip(),
            parent=parent,
            sort_order=sort_order,
            status=status,
            depth=parent.depth + 1 if parent else 0,
            path="",
        )
        category.path = f"{parent.path}{category.pk}/" if parent else f"/{category.pk}/"
        category.save(update_fields=["path", "updated_at"])
        return category


def move_local_category(
    category: LocalCategory,
    *,
    new_parent: LocalCategory | None,
) -> LocalCategory:
    with transaction.atomic():
        category = LocalCategory.objects.select_for_update().get(pk=category.pk)
        if new_parent is not None:
            new_parent = LocalCategory.objects.select_for_update().get(pk=new_parent.pk)
            if new_parent.pk == category.pk or new_parent.path.startswith(category.path):
                raise CategoryMoveInvalid(
                    "A category cannot be moved below itself or a descendant."
                )

        old_path = category.path
        new_path = f"{new_parent.path}{category.pk}/" if new_parent else f"/{category.pk}/"
        new_depth = new_parent.depth + 1 if new_parent else 0
        depth_delta = new_depth - category.depth
        descendants = list(
            LocalCategory.objects.select_for_update()
            .filter(path__startswith=old_path)
            .exclude(pk=category.pk)
        )

        category.parent = new_parent
        category.path = new_path
        category.depth = new_depth
        category.save(update_fields=["parent", "path", "depth", "updated_at"])

        now = timezone.now()
        for descendant in descendants:
            descendant.path = f"{new_path}{descendant.path[len(old_path) :]}"
            descendant.depth += depth_delta
            descendant.updated_at = now
        LocalCategory.objects.bulk_update(descendants, ["path", "depth", "updated_at"])
        return category


def local_category_descendants(category: LocalCategory, *, include_self: bool = False):
    queryset = LocalCategory.objects.filter(path__startswith=category.path)
    if not include_self:
        queryset = queryset.exclude(pk=category.pk)
    return queryset.order_by("path", "sort_order", "pk")
