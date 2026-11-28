"""提取真站 /profile 页的支付品牌内联 SVG，保存为本地 .svg 文件。"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
URL = "https://www.joybuy.co.uk/profile"
OUT = REPO / "storefront" / "public" / "images" / "pdp-services"

# aria-label -> 本地文件名
TARGETS = {
    "Visa": "payment-visa.svg",
    "Mastercard": "payment-mastercard.svg",
    "American Express": "payment-american-express.svg",
    "UnionPay": "payment-unionpay.svg",
    "PayPal": "payment-paypal.svg",
    "WeChat Pay": "payment-wechat-pay.svg",
    "Google Pay": "payment-google-pay.svg",
    "Apple Pay": "payment-apple-pay.svg",
    "Klarna": "payment-klarna.svg",
}

JS = (
    "(() => {"
    " const found = {};"
    " for (const e of document.querySelectorAll('svg[role=\"img\"]')) {"
    "  const label = e.getAttribute('aria-label') || '';"
    "  if (label) found[label] = e.outerHTML;"
    " }"
    " return JSON.stringify(found);"
    "})()"
)


def main() -> int:
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_paths(local_port=9336, user_data_path=str(PROFILE))
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--window-size=1440,1000")
    options.set_timeouts(page_load=60, script=30)
    page = ChromiumPage(options)
    page.get(URL)
    time.sleep(8)
    for _ in range(8):
        page.run_js("window.scrollBy(0, 800)")
        time.sleep(0.8)
    result = page.run_js("return (" + JS + ")")
    import json

    found = json.loads(result)
    print("labels found:", list(found.keys()))
    saved = 0
    for label, filename in TARGETS.items():
        if label in found:
            (OUT / filename).write_text(found[label], encoding="utf-8", newline="")
            print(f"saved {label} -> {filename} ({len(found[label])} chars)")
            saved += 1
        else:
            print(f"!! missing {label}")
    print(f"total saved: {saved}/{len(TARGETS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
