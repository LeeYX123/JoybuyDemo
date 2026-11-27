"""截图真站活动页 2dawKz7 全页。"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
URL = "https://www.joybuy.co.uk/campaign/active/3sQw3r9uY6MZMdBUVsn57PB7sDSR"
OUT = REPO / "var" / "campaign_3sQw3r9u_real.png"


def main() -> int:
    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_paths(local_port=9336, user_data_path=str(PROFILE))
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--window-size=1440,900")
    options.set_timeouts(page_load=60, script=30)
    page = ChromiumPage(options)
    page.get(URL)
    time.sleep(3)
    for _ in range(6):
        try:
            page.scroll.to_bottom()
        except Exception:
            pass
        time.sleep(1)
    try:
        page.get_screenshot(path=str(OUT), full_page=True)
        print("screenshot saved:", OUT)
    except Exception as exc:  # noqa: BLE001
        print(f"full_page failed ({exc}), fallback viewport")
        page.get_screenshot(path=str(OUT))
        print("viewport screenshot saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
