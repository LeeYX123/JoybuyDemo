from django.core.management.base import BaseCommand, CommandError

from catalog.localization_services import translate_sku_specification
from catalog.models import Sku
from offers.models import Locale, MarketLocale


class Command(BaseCommand):
    help = "Create locale-specific SKU specification snapshots for configured markets."

    def add_arguments(self, parser):
        parser.add_argument("--locale", action="append", dest="locales")
        parser.add_argument("--source-locale", default="en-GB")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        locale_codes = options["locales"] or list(
            MarketLocale.objects.filter(market__is_active=True, locale__is_active=True)
            .values_list("locale__code", flat=True)
            .distinct()
        )
        locales = list(Locale.objects.filter(code__in=locale_codes, is_active=True))
        missing = sorted(set(locale_codes) - {locale.code for locale in locales})
        if missing:
            raise CommandError(f"Unknown or inactive locales: {', '.join(missing)}")

        created = 0
        review = 0
        for sku in Sku.objects.filter(status=Sku.Status.ACTIVE).iterator():
            for locale in locales:
                if options["dry_run"]:
                    created += 1
                    continue
                record = translate_sku_specification(
                    sku,
                    locale,
                    source_locale=options["source_locale"],
                )
                created += 1
                review += int(record.needs_review)
        suffix = " (dry run)" if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Prepared {created} SKU-locale translations; {review} require review{suffix}."
            )
        )
