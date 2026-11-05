"""Close any crawler Chrome instances still running.

Crawl/login flows always close their own browser now, but a killed
process, a crashed task or a manual interruption can still leave a
crawler window behind. This command reaps only crawler browsers — those
carrying the crawler ``user-data-dir`` or listening on the crawler debug
ports (9333 crawl / 9334 login). The operator's own Chrome is never
touched.

Examples::

    manage.py close_crawler_browsers
"""

import sys
from pathlib import Path

from django.core.management.base import BaseCommand

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT / "crawler") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "crawler"))


class Command(BaseCommand):
    help = "Kill leftover crawler Chrome browsers (never the operator's own Chrome)."

    def handle(self, *args, **options):
        from joybuy_crawler.render import _kill_stale_crawler_browsers

        killed = _kill_stale_crawler_browsers()
        if killed:
            self.stdout.write(self.style.SUCCESS(f"Closed {killed} crawler browser process(es)."))
        else:
            self.stdout.write("No crawler browser was running.")
