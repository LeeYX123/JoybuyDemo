"""线上同步：minihome 频道 banner 替换（2026-11-28）。

在服务器上执行（仓库根目录）：
    .venv/Scripts/python.exe scripts/sync_minihome_banners_prod.py --apply
去掉 --apply 先预演。

前置：把 var/deploy/banners_20261128/ 里的 2 个图文件随脚本一起传到
服务器任意位置，脚本内 BANNERS 指向实际路径。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from content.models import ChannelBanner  # noqa: E402

# (channel_code, sort_order, 服务器上的图文件路径)
BANNERS = [
    ("UK-Mini-HP-Electronics", 0, "banner_electronics_oppo.png"),
    ("UK-Mini-HP-Beauty", 0, "banner_beauty_month.webp"),
]
SRC_DIR = Path(__file__).resolve().parents[1] / "var" / "deploy" / "deploy_media_20261128"


def main() -> int:
    apply = "--apply" in sys.argv
    from django.core.files.storage import default_storage

    for channel_code, sort_order, filename in BANNERS:
        src = SRC_DIR / filename
        if not src.exists():
            print(f"!! missing file: {src}")
            continue
        try:
            banner = ChannelBanner.objects.get(channel_code=channel_code, sort_order=sort_order)
        except ChannelBanner.DoesNotExist:
            print(f"!! no banner row: {channel_code} #{sort_order}")
            continue
        print(f"{channel_code} #{sort_order}: {banner.image_url[:70]} -> {filename}")
        if apply:
            with open(src, "rb") as f:
                name = default_storage.save(f"cms/original/{filename}", f)
            banner.image_url = f"/media/{name}"
            banner.save(update_fields=["image_url", "updated_at"])
            print("   updated ->", banner.image_url)
    print("done" if apply else "（预演模式，加 --apply 才写库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
