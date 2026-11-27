"""抓取真站 Beauty minihome 页的 banner 图清单。"""

import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
URL = "https://www.joybuy.co.uk/minihome/UK-Mini-HP-Beauty"


def main() -> int:
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_paths(local_port=9336, user_data_path=str(PROFILE))
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--window-size=1440,900")
    options.set_timeouts(page_load=60, script=30)
    page = ChromiumPage(options)
    try:
        page.set.cookies({"name": "_lang", "value": "en_GB", "domain": ".joybuy.co.uk"})
    except Exception:
        pass
    page.get(URL)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        html = page.html or ""
        if len(html) > 200_000 and ("banner" in html or "carousel" in html.lower()):
            break
        time.sleep(1)

    html = page.html or ""
    REPO.joinpath("var/minihome_beauty_real.html").write_text(html, encoding="utf-8", errors="replace")

    # 轮播容器里的图（顶部 banner 区）：找 hero/carousel 附近的 img src
    imgs = re.findall(r'<img[^>]+src="([^"]+)"', html)
    seen = []
    for src in imgs:
        if any(k in src for k in ("jfsintlpro", "joybuyimg", "360buyimg", "joy-sourcing")) and "s14x14" not in src and "s40x40" not in src:
            if src not in seen:
                seen.append(src)
    print("candidate imgs:", len(seen))
    for s_ in seen[:15]:
        print(" -", s_[:150])
    return 0


if __name__ == "__main__":
    sys.exit(main())
