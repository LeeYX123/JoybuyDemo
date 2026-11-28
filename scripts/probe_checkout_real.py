"""抓取真站 checkout 页（含购物车）的渲染结果：HTML + 整页截图。"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
URL = (
    "https://www.joybuy.co.uk/checkout?immediatelyBuy=false&shipmentType=66"
    "&bizExtraContext=%2BAnNktJaF20nbWcS0fCwRHdrySUEAndQXazHDxhBvdH5xkz7PZxg3tfGzs2ZrzKNEVfYgil5lla4ypSh3Xf4Vvm7lA%2BkHkVfuler5VPiuNgirzYXjV8%3D"
)


def main() -> int:
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_paths(local_port=9336, user_data_path=str(PROFILE))
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--window-size=1440,1000")
    options.set_timeouts(page_load=60, script=30)
    page = ChromiumPage(options)
    try:
        page.set.cookies({"name": "_lang", "value": "en_GB", "domain": ".joybuy.co.uk"})
    except Exception:
        pass
    page.get(URL)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        html = page.html or ""
        if len(html) > 300_000 and ("checkout" in html.lower() or "address" in html.lower()):
            break
        time.sleep(1)
    time.sleep(3)

    html = page.html or ""
    REPO.joinpath("var/checkout_real.html").write_text(html, encoding="utf-8", errors="replace")
    page.get_screenshot(path=str(REPO / "var" / "checkout_real.png"), full_page=True)
    print(f"saved: html={len(html)} chars, risk={'risk' in html.lower() and 'pic' in html.lower()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
