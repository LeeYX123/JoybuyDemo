"""补采活动页 2dawKz7 缺失的 4 件商品（2026-11-27）。

PAGE_SET run 的 DOM 抓取拿到的是真站轮换后的另一批商品，不含这 4 件。
本脚本用 DrissionPage（登录态 profile）直接抓 dp 详情页 SSR，
复用 joybuy_run 的 parse_uk_product_detail 解析 + ingest/import 管线入库。

用法：.venv/Scripts/python.exe scripts/crawl_missing_2dawKz7.py [--import-run <run_public_id>]
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "crawler"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MISSING = ["10367649", "10367637", "10372506", "10377282"]
PROFILE = ROOT / "var" / "browser_profiles" / "account-9b189970"


def fetch_html(page, url: str) -> str:
    page.get(url)
    deadline = time.monotonic() + 30
    html = ""
    while time.monotonic() < deadline:
        html = page.html or ""
        if len(html) > 100_000 and "<h1" in html:
            break
        time.sleep(1)
    return html


def main() -> int:
    from DrissionPage import ChromiumOptions, ChromiumPage
    from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

    from catalog.models import SourceCatalog
    from crawler_control.import_services import import_staging_product
    from crawler_control.models import CrawlRun
    from joybuy_crawler.ingest import ingest_product_payload
    from offers.models import Currency, Market

    run_public_id = None
    if "--import-run" in sys.argv:
        run_public_id = sys.argv[sys.argv.index("--import-run") + 1]
    run = None
    if run_public_id:
        run = CrawlRun.objects.get(public_id=run_public_id)
        if run.status == "RUNNING":
            print(f"attach RUNNING run {run_public_id}")
        else:
            print(f"run {run_public_id} status={run.status}（仍可挂载，暂存导入不要求 RUNNING）")

    options = ChromiumOptions()
    options.set_paths(local_port=9336, user_data_path=str(PROFILE))
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--window-size=1440,900")
    options.set_timeouts(page_load=60, script=30)
    page = ChromiumPage(options)
    # 站点语言 cookie：详情页 SSR 标题语言由 _lang 决定（账号会话里就是 en_GB）。
    try:
        page.set.cookies({"name": "_lang", "value": "en_GB", "domain": ".joybuy.co.uk"})
    except Exception:  # noqa: BLE001 - 已有会话时可能重复设置
        pass

    market = Market.objects.filter(code="GB", is_active=True).first()
    catalog = SourceCatalog.objects.filter(source_system="joybuy_uk").first()
    parser_version = "joybuy_uk.v2"

    for source_id in MISSING:
        url = f"https://www.joybuy.co.uk/dp/-/{source_id}"
        html = fetch_html(page, url)
        if "Joybuy Risk Control" in html or len(html) < 50_000:
            print(f"!! {source_id}: risk control / too short ({len(html)})")
            continue
        try:
            product = parse_uk_product_detail(html, source_url=url)
        except Exception as exc:  # noqa: BLE001
            print(f"!! {source_id}: parse failed: {exc}")
            continue
        payload = product.to_payload()
        payload.setdefault("source_category_id", "")
        payload["crawl_source_category_id"] = ""
        payload["crawl_source_category_name"] = "active"
        print(
            f"parsed {source_id}: {product.title[:40]!r} price={product.current_price}"
            f" skus={len(product.skus)} missing={product.missing_fields}"
        )
        if run is None:
            continue
        staging = ingest_product_payload(
            run,
            payload,
            source_system=catalog.source_system,
            source_url=url,
            parser_version=parser_version,
            structure_version=2,
        )
        currency = Currency.objects.filter(code=payload.get("currency") or "GBP").first()
        try:
            import_staging_product(
                staging,
                market=market,
                currency=currency or market.default_currency,
                locale="en-GB",
            )
            print(f"imported {source_id} OK")
        except Exception as exc:  # noqa: BLE001
            print(f"!! {source_id}: import failed: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
