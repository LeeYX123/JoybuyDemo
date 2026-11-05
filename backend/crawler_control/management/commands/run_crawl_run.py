"""Execute one crawl run to a terminal state (spawned by the start action).

This command is the detached executor process: it wires Django, then
hands over to the Scrapy-based runner in ``joybuy_crawler.runner``. The
outermost guard guarantees a RUNNING run always ends SUCCEEDED or FAILED
even when the executor itself crashes (user requirement #6).
"""

import sys
from pathlib import Path

from django.core.management.base import BaseCommand

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT / "crawler") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "crawler"))


class Command(BaseCommand):
    help = "Execute one crawl run (internal; spawned by the job start action)."

    def add_arguments(self, parser):
        parser.add_argument("--run", type=str, required=True, help="CrawlRun public_id")

    def handle(self, *args, **options):
        run_public_id = options["run"]
        try:
            from joybuy_crawler.runner import execute_run

            execute_run(run_public_id)
        except Exception as exc:  # noqa: BLE001 - the last line of defence
            from crawler_control.models import CrawlRun
            from crawler_control.services import complete_run_failed

            try:
                run = CrawlRun.objects.get(public_id=run_public_id)
                if run.status == "RUNNING":
                    complete_run_failed(run, reason=f"Executor crashed: {exc}")
            except Exception:  # noqa: BLE001 - never raise from the guard
                pass
            raise
