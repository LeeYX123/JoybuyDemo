"""抓取真站活动页 /campaign/active/3sQw3r9uY6MZMdBUVsn57PB7sDSR 的完整快照。

用常驻 profile（登录态）打开真站页面，落盘：
- var/campaign_3sQw3r9u_20261127.html  完整渲染后的 HTML
- var/campaign_3sQw3r9u_20261127_floors.json  window._codeFloors 结构化楼层
"""

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
URL = "https://www.joybuy.co.uk/campaign/active/3sQw3r9uY6MZMdBUVsn57PB7sDSR"
OUT_HTML = REPO / "var" / "campaign_3sQw3r9u_20261127.html"
OUT_FLOORS = REPO / "var" / "campaign_3sQw3r9u_20261127_floors.json"


def main() -> int:
    from DrissionPage import ChromiumOptions, ChromiumPage

    PROFILE.mkdir(parents=True, exist_ok=True)
    options = ChromiumOptions()
    options.set_paths(local_port=9336, user_data_path=str(PROFILE))
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--window-size=1440,900")
    options.set_argument("--no-first-run")
    options.set_timeouts(page_load=60, script=30)
    page = ChromiumPage(options)
    try:
        page.set.window.max()
    except Exception:
        pass

    page.get(URL)
    html = ""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        html = page.html or ""
        if len(html) > 100_000 and ("_codeFloors" in html or "bab-opt-mod" in html):
            break
        time.sleep(1)
        try:
            page.scroll.to_bottom()
        except Exception:
            pass

    OUT_HTML.write_text(html, encoding="utf-8", errors="replace")
    print(f"html saved: {len(html)} chars, risk={'Joybuy Risk Control' in html}")

    # 楼层数据兜底：从 JS 上下文直接取
    try:
        floors = page.run_js("return window._codeFloors ? JSON.parse(JSON.stringify(window._codeFloors)) : null;")
        if floors:
            OUT_FLOORS.write_text(
                json.dumps(floors, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"floors saved: {len(floors)}")
        else:
            print("floors: window._codeFloors empty/absent")
    except Exception as exc:  # noqa: BLE001
        print(f"floors extract failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
