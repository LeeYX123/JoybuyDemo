"""Fixture loading: publish the home page from a committed JSON fixture."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from content.services import publish_page

REPOSITORY_ROOT = Path(settings.BASE_DIR).parent
DEFAULT_FIXTURE = REPOSITORY_ROOT / "backend" / "content" / "fixtures" / "home_page_v1.json"


class Command(BaseCommand):
    help = "Publish the fixture-driven CMS home page (idempotent: creates a new version)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            default=str(DEFAULT_FIXTURE),
            help="Path to a page fixture JSON file.",
        )

    def handle(self, *args, **options):
        fixture_path = Path(options["fixture"])
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        page = publish_page(
            page_key=data["page_key"],
            title=data["title"],
            modules=data["modules"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Published {page.page_key} v{page.version} with {page.modules.count()} modules."
            )
        )
