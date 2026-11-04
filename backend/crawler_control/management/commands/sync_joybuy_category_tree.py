"""Sync the live Joybuy (joybuy.co.uk) category tree into source snapshots.

Renders the site through DrissionPage (plain HTTP hits the risk-control
page, docs/11), extracts the L1/L2 category menu with verbatim public ids
(``l1:1409`` / ``cid2:13159``) and writes one new
``SourceCategoryTreeVersion`` so crawl jobs can list and freeze real
Joybuy categories.

Examples::

    # full sync with children, publish immediately
    manage.py sync_joybuy_category_tree --publish

    # capture the rendered menu to a file and stop (replayable)
    manage.py sync_joybuy_category_tree --dump-json var/joybuy_demo/data/category_menu.json

    # rebuild a version from a previously captured menu file (no network)
    manage.py sync_joybuy_category_tree --from-json var/joybuy_demo/data/category_menu.json
"""

import json
import sys
from pathlib import Path

from catalog.models import SourceCatalog
from django.core.management.base import BaseCommand

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT / "crawler") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "crawler"))

from crawler_control.tree_sync import (  # noqa: E402
    MenuNode,
    latest_published_tree,
    sync_category_tree,
)


class Command(BaseCommand):
    help = "Sync the live Joybuy category tree into versioned source snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--publish", action="store_true", help="Publish the new version")
        parser.add_argument(
            "--no-children",
            action="store_true",
            help="Only capture first-level categories (skip per-category facet pages)",
        )
        parser.add_argument(
            "--headed",
            action="store_true",
            help="Show the browser window (useful to watch the capture)",
        )
        parser.add_argument(
            "--dump-json",
            type=str,
            default="",
            help="Save the captured menu tree to this JSON file",
        )
        parser.add_argument(
            "--from-json",
            type=str,
            default="",
            help="Build the version from a previously captured menu JSON (no network)",
        )

    def handle(self, *args, **options):
        catalog, _created = SourceCatalog.objects.get_or_create(
            source_system="joybuy_uk",
            defaults={"display_name": "Joybuy UK (joybuy.co.uk)"},
        )
        nodes = self._capture_nodes(options)
        if options["dump_json"]:
            dump_path = Path(options["dump_json"])
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            dump_path.write_text(
                json.dumps(self._nodes_to_json(nodes), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stdout.write(self.style.SUCCESS(f"Menu captured -> {dump_path}"))

        result = sync_category_tree(catalog, nodes, publish=options["publish"])
        previous = latest_published_tree(catalog)
        self.stdout.write(
            self.style.SUCCESS(
                f"Version {result.tree_version.version_key} "
                f"status={result.tree_version.status} "
                f"l1={len(nodes)} snapshots={result.created_snapshots} "
                f"new_ids={len(result.new_source_ids)} "
                f"removed_vs_previous={len(result.missing_source_ids)}"
            )
        )
        if previous and previous.pk != result.tree_version.pk:
            self.stdout.write(f"Previous published version: {previous.version_key}")
        if result.missing_source_ids:
            self.stdout.write(
                self.style.WARNING(
                    "IDs no longer present on the live site: "
                    + ", ".join(result.missing_source_ids[:20])
                )
            )

    def _capture_nodes(self, options) -> list[MenuNode]:
        if options["from_json"]:
            payload = json.loads(Path(options["from_json"]).read_text(encoding="utf-8"))
            return self._json_to_nodes(payload)
        from joybuy_crawler.category_menu import capture_category_tree

        return capture_category_tree(
            headless=not options["headed"],
            fetch_children=not options["no_children"],
        )

    def _nodes_to_json(self, nodes) -> list[dict]:
        return [
            {
                "name": node.name,
                "source_id": node.source_id,
                "source_url": node.source_url,
                "children": [
                    {
                        "name": child.name,
                        "source_id": child.source_id,
                        "source_url": child.source_url,
                    }
                    for child in node.children
                ],
            }
            for node in nodes
        ]

    def _json_to_nodes(self, payload) -> list[MenuNode]:
        return [
            MenuNode(
                name=entry["name"],
                source_id=entry["source_id"],
                source_url=entry.get("source_url", ""),
                children=[
                    MenuNode(
                        name=child["name"],
                        source_id=child["source_id"],
                        source_url=child.get("source_url", ""),
                    )
                    for child in entry.get("children", [])
                ],
            )
            for entry in payload
        ]
