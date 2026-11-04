from django.test import TestCase

from content.domain import CmsPageStateInvalid, CmsPayloadInvalid
from content.models import CmsModule, CmsPage
from content.services import get_published_page, publish_page, serialize_page


def home_fixture_modules():
    import json
    from pathlib import Path

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "home_page_v1.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    return data["title"], data["modules"]


class CmsPageServiceTests(TestCase):
    def publish_home(self):
        title, modules = home_fixture_modules()
        return publish_page(page_key="home", title=title, modules=modules)

    def test_publish_creates_versioned_page_and_archives_previous(self):
        first = self.publish_home()
        self.assertEqual(first.version, 1)
        self.assertEqual(first.status, CmsPage.Status.PUBLISHED)
        self.assertEqual(first.modules.count(), 4)
        self.assertEqual(
            [module.position for module in first.modules.all()],
            [1, 2, 3, 4],
        )

        second = self.publish_home()
        self.assertEqual(second.version, 2)
        first.refresh_from_db()
        self.assertEqual(first.status, CmsPage.Status.ARCHIVED)
        self.assertEqual(get_published_page("home"), second)

    def test_payload_validation_rejects_unknown_types_and_missing_fields(self):
        with self.assertRaises(CmsPayloadInvalid):
            publish_page(
                page_key="home", title="x", modules=[{"module_type": "mystery", "payload": {}}]
            )
        with self.assertRaises(CmsPayloadInvalid):
            publish_page(
                page_key="home",
                title="x",
                modules=[{"module_type": "hero", "payload": {"subheading": "no heading"}}],
            )
        with self.assertRaises(CmsPayloadInvalid):
            publish_page(
                page_key="home",
                title="x",
                modules=[
                    {
                        "module_type": "product_pool",
                        "payload": {"title": "Pool", "products": [{"title": "No id"}]},
                    }
                ],
            )
        with self.assertRaises(CmsPageStateInvalid):
            publish_page(page_key="home", title="Empty", modules=[])

    def test_fixture_payload_passes_validation_end_to_end(self):
        page = self.publish_home()
        payload_types = [module.module_type for module in page.modules.all()]
        self.assertEqual(
            payload_types,
            [
                CmsModule.Type.HERO,
                CmsModule.Type.BANNER,
                CmsModule.Type.PRODUCT_POOL,
                CmsModule.Type.RICH_TEXT,
            ],
        )

    def test_serialization_shape_for_the_renderer(self):
        page = self.publish_home()
        data = serialize_page(page)
        self.assertEqual(data["page"]["key"], "home")
        self.assertEqual(data["page"]["version"], 1)
        self.assertEqual(len(data["modules"]), 4)
        pool = data["modules"][2]
        self.assertEqual(pool["type"], "product_pool")
        self.assertEqual(len(pool["payload"]["products"]), 4)
        self.assertIn("public_id", pool["payload"]["products"][0])

    def test_unpublished_page_key_returns_none(self):
        self.assertIsNone(get_published_page("never-published"))
