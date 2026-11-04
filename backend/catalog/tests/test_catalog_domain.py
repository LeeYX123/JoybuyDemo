from decimal import Decimal

from accounts_staff.models import PlatformRole
from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.domain import CategoryMoveInvalid, CategoryTreeInvalid, CategoryVersionConflict
from catalog.models import (
    AttributeDefinition,
    AttributeOption,
    Brand,
    CategoryAttributeDefinition,
    CategoryMapping,
    SourceCategory,
    SourceCategorySnapshot,
)
from catalog.services import (
    create_local_category,
    local_category_descendants,
    move_local_category,
    save_source_category_version,
    source_category_descendants,
)


def source_nodes_v1():
    return [
        {"source_id": "root", "name": "All", "sort_order": 0},
        {
            "source_id": "electronics",
            "name": "Electronics",
            "parent_source_id": "root",
            "sort_order": 10,
        },
        {
            "source_id": "phones",
            "name": "Phones",
            "parent_source_id": "electronics",
            "sort_order": 20,
        },
        {
            "source_id": "smartphones",
            "name": "Smartphones",
            "parent_source_id": "phones",
            "sort_order": 30,
        },
    ]


class CatalogDomainTests(TestCase):
    def test_source_category_version_supports_multi_level_tree_queries(self):
        version = save_source_category_version(
            source_system="Joybuy",
            version_key="2026-11-02-a",
            nodes=source_nodes_v1(),
            metadata={"parser": "fixture-v1"},
        )

        electronics = version.snapshots.get(category__source_id="electronics")
        descendants = list(
            source_category_descendants(electronics).values_list(
                "category__source_id",
                flat=True,
            )
        )

        self.assertEqual(version.catalog.source_system, "joybuy")
        self.assertEqual(version.catalog.current_version, version)
        self.assertEqual(version.status, version.Status.PUBLISHED)
        self.assertEqual(descendants, ["phones", "smartphones"])
        self.assertEqual(electronics.depth, 1)
        self.assertEqual(version.snapshots.get(category__source_id="smartphones").depth, 3)

    def test_new_source_version_preserves_history_and_local_navigation(self):
        first = save_source_category_version(
            source_system="joybuy",
            version_key="v1",
            nodes=source_nodes_v1(),
        )
        local_root = create_local_category(name="Technology", slug="technology")
        local_phones = create_local_category(
            name="Mobile Phones",
            slug="mobile-phones",
            parent=local_root,
        )
        stable_smartphones = SourceCategory.objects.get(
            catalog=first.catalog,
            source_id="smartphones",
        )
        CategoryMapping.objects.create(
            local_category=local_phones,
            source_category=stable_smartphones,
            is_primary=True,
            confidence=Decimal("0.9900"),
        )
        original_local_path = local_phones.path

        second = save_source_category_version(
            source_system="joybuy",
            version_key="v2",
            nodes=[
                {"source_id": "root", "name": "All"},
                {
                    "source_id": "electronics",
                    "name": "Tech & Electronics",
                    "parent_source_id": "root",
                },
                {
                    "source_id": "smartphones",
                    "name": "Smart Phones",
                    "parent_source_id": "electronics",
                },
            ],
        )

        local_phones.refresh_from_db()
        stable_smartphones.refresh_from_db()
        self.assertEqual(first.snapshots.count(), 4)
        self.assertEqual(second.snapshots.count(), 3)
        self.assertEqual(
            first.snapshots.get(category__source_id="smartphones").parent.category.source_id,
            "phones",
        )
        self.assertEqual(
            second.snapshots.get(category__source_id="smartphones").parent.category.source_id,
            "electronics",
        )
        self.assertEqual(local_phones.parent, local_root)
        self.assertEqual(local_phones.path, original_local_path)
        self.assertEqual(local_phones.source_mappings.get().source_category, stable_smartphones)
        self.assertTrue(stable_smartphones.is_active)
        self.assertFalse(
            SourceCategory.objects.get(catalog=first.catalog, source_id="phones").is_active
        )

    def test_version_key_is_idempotent_but_rejects_changed_structure(self):
        first = save_source_category_version(
            source_system="joybuy",
            version_key="stable-v1",
            nodes=source_nodes_v1(),
        )
        same = save_source_category_version(
            source_system="JOYBUY",
            version_key="stable-v1",
            nodes=source_nodes_v1(),
        )

        self.assertEqual(first, same)
        with self.assertRaises(CategoryVersionConflict):
            changed = source_nodes_v1()
            changed[-1]["name"] = "Changed"
            save_source_category_version(
                source_system="joybuy",
                version_key="stable-v1",
                nodes=changed,
            )

    def test_invalid_source_tree_rejects_missing_parent_and_cycles(self):
        with self.assertRaises(CategoryTreeInvalid):
            save_source_category_version(
                source_system="joybuy",
                version_key="missing-parent",
                nodes=[
                    {
                        "source_id": "child",
                        "name": "Child",
                        "parent_source_id": "missing",
                    }
                ],
            )

        with self.assertRaises(CategoryTreeInvalid):
            save_source_category_version(
                source_system="joybuy",
                version_key="cycle",
                nodes=[
                    {"source_id": "a", "name": "A", "parent_source_id": "b"},
                    {"source_id": "b", "name": "B", "parent_source_id": "a"},
                ],
            )

    def test_moving_local_category_updates_entire_subtree(self):
        root_a = create_local_category(name="Root A", slug="root-a")
        root_b = create_local_category(name="Root B", slug="root-b")
        child = create_local_category(name="Child", slug="child", parent=root_a)
        grandchild = create_local_category(
            name="Grandchild",
            slug="grandchild",
            parent=child,
        )

        moved = move_local_category(child, new_parent=root_b)
        grandchild.refresh_from_db()

        self.assertEqual(moved.parent, root_b)
        self.assertEqual(moved.depth, 1)
        self.assertEqual(grandchild.depth, 2)
        self.assertTrue(grandchild.path.startswith(moved.path))
        self.assertEqual(
            list(
                local_category_descendants(root_b).values_list(
                    "slug",
                    flat=True,
                )
            ),
            ["child", "grandchild"],
        )

        with self.assertRaises(CategoryMoveInvalid):
            move_local_category(root_b, new_parent=grandchild)

    def test_category_mapping_is_many_to_many_but_pair_is_unique(self):
        version = save_source_category_version(
            source_system="joybuy",
            version_key="mapping-v1",
            nodes=source_nodes_v1(),
        )
        local = create_local_category(name="Phones", slug="phones")
        phones = SourceCategory.objects.get(catalog=version.catalog, source_id="phones")
        smartphones = SourceCategory.objects.get(
            catalog=version.catalog,
            source_id="smartphones",
        )
        CategoryMapping.objects.create(local_category=local, source_category=phones)
        CategoryMapping.objects.create(local_category=local, source_category=smartphones)

        self.assertEqual(local.source_mappings.count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CategoryMapping.objects.create(local_category=local, source_category=phones)

    def test_brand_normalization_prevents_case_and_spacing_duplicates(self):
        brand = Brand.objects.create(name="  Example   Brand ", slug="example-brand")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Brand.objects.create(name="example brand", slug="example-brand-copy")

        brand.name = "Renamed Brand"
        brand.save(update_fields=["name"])
        brand.refresh_from_db()
        self.assertEqual(brand.normalized_name, "renamed brand")

    def test_attributes_options_and_category_assignment_are_constrained(self):
        category = create_local_category(name="Clothing", slug="clothing")
        colour = AttributeDefinition.objects.create(
            code="colour",
            name="Colour",
            data_type=AttributeDefinition.DataType.CHOICE,
            scope=AttributeDefinition.Scope.BOTH,
            is_filterable=True,
            is_variant_axis=True,
        )
        AttributeOption.objects.create(attribute=colour, value="red", label="Red")
        CategoryAttributeDefinition.objects.create(
            category=category,
            attribute=colour,
            is_required=True,
        )

        self.assertEqual(colour.options.get().label, "Red")
        self.assertTrue(category.attribute_assignments.get().is_required)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttributeOption.objects.create(attribute=colour, value="red", label="Duplicate")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CategoryAttributeDefinition.objects.create(category=category, attribute=colour)

    def test_platform_admin_receives_taxonomy_management_permission(self):
        permission_codes = set(
            PlatformRole.objects.get(code="platform_admin").permissions.values_list(
                "code",
                flat=True,
            )
        )
        self.assertIn("catalog.taxonomy.manage", permission_codes)

    def test_source_descendant_query_never_crosses_versions(self):
        first = save_source_category_version(
            source_system="joybuy",
            version_key="descendants-v1",
            nodes=source_nodes_v1(),
        )
        save_source_category_version(
            source_system="joybuy",
            version_key="descendants-v2",
            nodes=source_nodes_v1(),
        )
        root = SourceCategorySnapshot.objects.get(
            tree_version=first,
            category__source_id="root",
        )

        self.assertEqual(source_category_descendants(root).count(), 3)
