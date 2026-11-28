"""在真站 checkout 页用 JS 精确测量全部输入框/按钮的矩形（像素级）。"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
URL = (
    "https://www.joybuy.co.uk/checkout?immediatelyBuy=false&shipmentType=66"
    "&bizExtraContext=%2BAnNktJaF20nbWcS0fCwRHdrySUEAndQXazHDxhBvdH5xkz7PZxg3tfGzs2ZrzKNEVfYgil5lla4ypSh3Xf4Vvm7lA%2BkHkVfuler5VPiuNgirzYXjV8%3D"
)

MEASURE_JS = (
    "(() => {"
    " const out = { viewport: window.innerWidth, items: [] };"
    " const els = [...document.querySelectorAll('input, select, button')].filter(e => {"
    "  const b = e.getBoundingClientRect();"
    "  return b.width > 30 && b.height > 20 && b.top > 100 && b.top < 900;"
    " });"
    " for (const e of els) {"
    "  const b = e.getBoundingClientRect();"
    "  out.items.push({ tag: e.tagName.toLowerCase(),"
    "   ph: (e.placeholder || e.textContent || '').trim().slice(0, 24),"
    "   x: Math.round(b.left), y: Math.round(b.top),"
    "   w: Math.round(b.width), h: Math.round(b.height) });"
    " }"
    " out.items.sort((a, b) => a.y - b.y || a.x - b.x);"
    " return JSON.stringify(out);"
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
    try:
        page.set.cookies({"name": "_lang", "value": "en_GB", "domain": ".joybuy.co.uk"})
    except Exception:
        pass
    page.get(URL)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        html = page.html or ""
        if len(html) > 300_000 and "address" in html.lower():
            break
        time.sleep(1)
    time.sleep(3)
    result = page.run_js("return (" + MEASURE_JS + ")")
    print("MEASURE:", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
