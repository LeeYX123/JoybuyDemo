"""尝试抓真站 checkout 支付区的银行卡品牌 icon（购物车有货才渲染）。"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
URL = (
    "https://www.joybuy.co.uk/checkout?immediatelyBuy=false&shipmentType=66"
    "&bizExtraContext=%2BAnNktJaF20nbWcS0fCwRHdrySUEAndQXazHDxhBvdH5xkz7PZxg3tfGzs2ZrzKNEVfYgil5lla4ypSh3Xf4Vvm7lA%2BkHkVfuler5VPiuNgirzYXjV8%3D"
)

JS = (
    "(() => {"
    " const imgs = [...document.querySelectorAll('img')].filter(e => {"
    "  const b = e.getBoundingClientRect();"
    "  return b.width >= 24 && b.width <= 90 && b.height >= 14 && b.height <= 60;"
    " });"
    " return JSON.stringify(imgs.map(e => ({src: e.src.slice(0, 140), alt: e.alt, w: Math.round(e.getBoundingClientRect().width), y: Math.round(e.getBoundingClientRect().top)})).slice(0, 60));"
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
    # 滚动到底触发懒加载
    for _ in range(6):
        page.run_js("window.scrollBy(0, 900)")
        time.sleep(1)
    result = page.run_js("return (" + JS + ")")
    print("IMGS:", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
