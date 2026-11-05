"""Attach Chinese category names to the already-synced Joybuy source tree.

The English tree (`sync_joybuy_category_tree`) stays the structural
baseline — ids, parents and order. This command only captures the
Chinese label, matched strictly by the verbatim ``source_id``
(``minihome:UK-Mini-HP-Electronics`` / ``l2:1405``), so the two
languages stay one-to-one regardless of translation wording.

Capture: joybuy.co.uk stores the interface language in the ``_lang``
cookie; ``zh_CN`` renders the whole site (category menu included) in
Chinese while keeping the same source ids. The site now asks anonymous
visitors to sign in (2026-11-05), so a stored crawler account session is
required for the live capture path (`--account`).

Examples::

    # import a previously captured Chinese menu (no network)
    manage.py sync_joybuy_category_names_zh \
        --from-json var/joybuy_demo/data/category_menu_zh.json

    # live capture with the stored session of an account
    manage.py sync_joybuy_category_names_zh --account <account-public-id> --dump-json ...

    # only first-level channels (cheaper capture, no per-channel pages)
    manage.py sync_joybuy_category_names_zh --account <id> --no-children
"""

import json
import sys
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.models import SourceCatalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT / "crawler") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "crawler"))

from crawler_control.tree_sync import (  # noqa: E402
    MenuNode,
    apply_chinese_names,
)


class Command(BaseCommand):
    help = "Capture Joybuy category names in Chinese and map them onto the existing tree."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-json",
            type=str,
            default="",
            help="Import a previously captured Chinese menu JSON (no network)",
        )
        parser.add_argument(
            "--dump-json",
            type=str,
            default="",
            help="Save the captured Chinese menu tree to this JSON file",
        )
        parser.add_argument(
            "--account",
            type=str,
            default="",
            help="Crawler account public id whose stored session is used for the capture",
        )
        parser.add_argument(
            "--headed",
            action="store_true",
            help="Show the browser window (useful to watch the capture)",
        )
        parser.add_argument(
            "--no-children",
            action="store_true",
            help="Only capture first-level channels (skip per-channel facet pages)",
        )
        parser.add_argument(
            "--pause",
            type=float,
            default=6.0,
            help="Seconds between channel page renders (rate-limit courtesy)",
        )
        parser.add_argument(
            "--no-reset-profile",
            action="store_true",
            help="Reuse the existing crawler browser profile instead of wiping it first",
        )
        parser.add_argument(
            "--profile",
            type=str,
            default="",
            help=(
                "Browser profile to reuse, e.g. account-9b189970 (a logged-in account "
                "profile is far less likely to hit the risk-control page)"
            ),
        )
        parser.add_argument(
            "--channel",
            action="append",
            default=[],
            help=(
                "Only capture these channels (source id or minihome code); "
                "repeatable. Use with --merge-json for a resumable chunked capture."
            ),
        )
        parser.add_argument(
            "--merge-json",
            action="store_true",
            help="Merge the capture into the existing --dump-json file instead of replacing it",
        )

    def handle(self, *args, **options):
        catalog = SourceCatalog.objects.filter(source_system="joybuy_uk").first()
        if catalog is None:
            raise CommandError(
                "No joybuy_uk source catalog yet; run sync_joybuy_category_tree first."
            )

        nodes = self._capture_nodes(options)
        if options["dump_json"]:
            dump_path = Path(options["dump_json"])
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            if options["merge_json"] and dump_path.exists():
                nodes = self._merge_nodes(
                    self._json_to_nodes(json.loads(dump_path.read_text(encoding="utf-8"))),
                    nodes,
                )
            dump_path.write_text(
                json.dumps(self._nodes_to_json(nodes), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stdout.write(self.style.SUCCESS(f"Chinese menu captured -> {dump_path}"))

        result = apply_chinese_names(catalog, nodes)
        self.stdout.write(
            self.style.SUCCESS(
                f"tree={result.tree_version_key} "
                f"matched={len(result.matched_source_ids)} "
                f"categories_updated={result.updated_categories} "
                f"snapshots_updated={result.updated_snapshots} "
                f"unknown={len(result.unknown_source_ids)} "
                f"still_missing={len(result.missing_source_ids)}"
            )
        )
        if result.unknown_source_ids:
            self.stdout.write(
                self.style.WARNING(
                    "Captured ids that are not in the tree (ignored): "
                    + ", ".join(result.unknown_source_ids[:20])
                )
            )
        if result.missing_source_ids:
            self.stdout.write(
                self.style.WARNING(
                    "Tree ids without a captured Chinese name: "
                    + ", ".join(result.missing_source_ids[:20])
                )
            )

    # -- capture -----------------------------------------------------------

    def _capture_nodes(self, options) -> list[MenuNode]:
        if options["from_json"]:
            payload = json.loads(Path(options["from_json"]).read_text(encoding="utf-8"))
            return self._json_to_nodes(payload)

        from joybuy_crawler.category_menu import CHINESE_LOCALE, capture_category_tree
        from joybuy_crawler.render import reset_browser_profile

        cookies = self._account_cookies(options["account"])
        if not options["no_reset_profile"] and not options["profile"]:
            reset_browser_profile()

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                captured = capture_category_tree(
                    headless=not options["headed"],
                    fetch_children=not options["no_children"],
                    pause_seconds=options["pause"],
                    locale=CHINESE_LOCALE,
                    cookies=cookies,
                    profile_dir=self._profile_dir(options["profile"]),
                    only_channels=options["channel"] or None,
                )
                return [self._to_tree_node(node) for node in captured]
            except RuntimeError as exc:
                last_error = exc
                message = str(exc)
                if "risk-control" not in message and "Failed to render" not in message:
                    raise
                self.stdout.write(
                    self.style.WARNING(
                        f"Attempt {attempt}/3 failed ({message[:80]}); "
                        "cooling down 60s (docs/05 §7.3)..."
                    )
                )
                time.sleep(60)
        raise last_error

    def _profile_dir(self, profile: str) -> str | None:
        """Resolve ``--profile`` to a user-data-dir under var/browser_profiles."""

        if not profile:
            return None
        candidate = Path(profile)
        if candidate.is_absolute() or candidate.parent != Path("."):
            return str(candidate)
        from django.conf import settings

        root = Path(settings.BASE_DIR).parent / "var" / "browser_profiles"
        return str(root / profile)

    def _merge_nodes(self, existing: list[MenuNode], captured: list[MenuNode]) -> list[MenuNode]:
        """Union a chunked capture into the previously dumped tree.

        Chunked runs only render the requested channels, so untouched
        channels come back without children; the merged tree keeps their
        previous children instead of wiping them.
        """

        by_id = {node.source_id: node for node in existing}
        merged: list[MenuNode] = []
        for node in captured:
            previous = by_id.pop(node.source_id, None)
            children = {child.source_id: child for child in (previous.children if previous else [])}
            for child in node.children:
                children[child.source_id] = child
            merged.append(
                MenuNode(
                    name=node.name,
                    source_id=node.source_id,
                    source_url=node.source_url or (previous.source_url if previous else ""),
                    name_zh=node.name_zh or (previous.name_zh if previous else ""),
                    children=list(children.values()),
                )
            )
        merged.extend(by_id.values())
        return merged

    def _to_tree_node(self, node) -> MenuNode:
        """Crawler menu node -> tree_sync node.

        The Chinese capture renders Chinese labels in ``name``; they become
        the node's ``name_zh`` so the English baseline stays untouched.
        """

        return MenuNode(
            name=node.name,
            source_id=node.source_id,
            source_url=getattr(node, "source_url", ""),
            name_zh=node.name,
            children=[self._to_tree_node(child) for child in node.children],
        )

    def _account_cookies(self, account_public_id: str) -> list[dict]:
        if not account_public_id:
            return []
        from crawler_control.models import CrawlerAccount
        from crawler_control.services import load_account_session

        account = CrawlerAccount.objects.filter(public_id=account_public_id).first()
        if account is None:
            raise CommandError(f"Unknown crawler account: {account_public_id}")
        session = load_account_session(account)
        cookies = session.get("cookies") or []
        if not cookies:
            raise CommandError(
                f"Account {account_public_id} has no stored cookies; log in from the admin first."
            )
        self.stdout.write(
            f"Using stored session of account {account.label} ({len(cookies)} cookies)."
        )
        return cookies

    # -- json --------------------------------------------------------------

    def _nodes_to_json(self, nodes) -> list[dict]:
        return [
            {
                "name": node.name,
                "name_zh": node.name_zh,
                "source_id": node.source_id,
                "source_url": node.source_url,
                "children": [
                    {
                        "name": child.name,
                        "name_zh": child.name_zh,
                        "source_id": child.source_id,
                        "source_url": child.source_url,
                    }
                    for child in node.children
                ],
            }
            for node in nodes
        ]

    def _json_to_nodes(self, payload) -> list[MenuNode]:
        """Build nodes from a Chinese menu dump.

        A Chinese capture stores the Chinese label in ``name`` (that is what
        the rendered page shows); an explicit ``name_zh`` wins when present.
        Entries whose text has no CJK characters are dropped as labels so an
        English dump can never be imported as Chinese by mistake.
        """

        return [
            MenuNode(
                name=entry.get("name", ""),
                source_id=entry["source_id"],
                source_url=entry.get("source_url", ""),
                name_zh=_chinese_label(entry.get("name_zh") or entry.get("name", "")),
                children=[
                    MenuNode(
                        name=child.get("name", ""),
                        source_id=child["source_id"],
                        source_url=child.get("source_url", ""),
                        name_zh=_chinese_label(child.get("name_zh") or child.get("name", "")),
                    )
                    for child in entry.get("children", [])
                ],
            )
            for entry in payload
        ]


def _chinese_label(text: str) -> str:
    """Return the label only when it actually contains Chinese characters."""

    value = (text or "").strip()
    return value if any("\u4e00" <= char <= "\u9fff" for char in value) else ""
