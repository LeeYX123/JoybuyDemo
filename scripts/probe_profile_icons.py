"""抓真站 /profile 页底部的支付方式 svg（img src 或 inline svg）。"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
URL = "https://www.joybuy.co.uk/profile"

JS = (
    "(() => {"
    " const out = { imgs: [], svgs: [] };"
    " const imgs = [...document.querySelectorAll('img')].filter(e => {"
    "  const b = e.getBoundingClientRect();"
    "  return b.top > window.innerHeight * 0.5 && b.width >= 20 && b.width <= 120 && b.height >= 12 && b.height <= 60;"
    " });"
    " for (const e of imgs) out.imgs.push({ src: e.src, alt: e.alt, w: Math.round(e.getBoundingClientRect().width), h: Math.round(e.getBoundingClientRect().height) });"
    " const svgs = [...document.querySelectorAll('svg')].filter(e => {"
    "  const b = e.getBoundingClientRect();"
    "  return b.top > window.innerHeight * 0.5 && b.width >= 20 && b.width <= 120 && b.height >= 12 && b.height <= 60;"
    " });"
    " for (const e of svgs.slice(0, 30)) out.svgs.push({ cls: e.getAttribute('class') || '', html: e.outerHTML.slice(0, 300), w: Math.round(e.getBoundingClientRect().width), h: Math.round(e.getBoundingClientRect().height) });"
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
    page.get(URL)
    time.sleep(8)
    for _ in range(8):
        page.run_js("window.scrollBy(0, 800)")
        time.sleep(0.8)
    page.run_js("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)
    result = page.run_js("return (" + JS + ")")
    print("RESULT:", result[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
