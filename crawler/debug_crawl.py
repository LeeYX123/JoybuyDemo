#!/usr/bin/env python
"""Joybuy 爬虫任务独立调试脚本（与正式存储完全隔离）。

用途
----
把管理端「爬虫任务」的抓取链路单独拿出来跑，方便逐行调试：

    列表页 → 商品卡 → 详情页 → 解析 → 记录级质量规则 → 落盘

复用正式链路的解析器（``parse_uk_listing`` / ``parse_uk_product_detail``）、
记录级质量规则（``quality.apply_product_rules``）和最高清图片解析
（``image_variants.resolve_highest_resolution``），但**完全不碰正式存储**：

* 不 import Django、不连数据库，不写 staging / SPU / Offer / 运行事件；
* 不写 ``var/``（``var/crawl_exports``、``var/media``、``var/cache``、
  ``var/browser_profiles`` 全部不会被访问）；
* 所有产物只写进本文件顶部 ``OUTPUT_DIR``（或 ``--output-dir``）。

每次运行在输出目录下建一个独立的 run 目录：

    <OUTPUT_DIR>/<run-name>/
      logs/crawl-debug.log                 # 与控制台同内容的完整日志
      raw_html/listings/…                  # 列表页原始 HTML（解析失败时对照用）
      raw_html/products/…                  # 详情页原始 HTML
      dataset/<一级类目>/<二级类目>/<商品ID>/
        product.json                       # 完整 payload（质量规则清洗后）
        meta.json                          # 指纹 / 抓取次数 / 是否变化
        images/main/01.jpg                 # 最高清主图
        images/detail/02.jpg …             # 画廊图 + 详情图
      dataset/<一级类目>/dataset_index.jsonl
      summary.json                         # 本次运行统计

运行示例
--------
    # 登录态：把 cURL(bash) 解析出的 headers / cookies dict 粘到同目录
    # debug_session.py（该文件已被 .gitignore 忽略，含真实 Cookie 不会入库）
    .venv/Scripts/python.exe crawler/debug_crawl.py --limit 3
    .venv/Scripts/python.exe crawler/debug_crawl.py ^
        --listing-url "https://www.joybuy.co.uk/s?k=electronics" ^
        --output-dir "E:/crawler_debug" --limit 5 --headed
    # 直接分析一个商品详情页（不需要 --limit，也不会解析列表页）
    .venv/Scripts/python.exe crawler/debug_crawl.py ^
        --listing-url "https://www.joybuy.co.uk/dp/<slug>/<id>"
    .venv/Scripts/python.exe crawler/debug_crawl.py ^
        --headers-file "E:/crawler_headers.py" --no-images --limit 1

两种输入可以混着传：``/s?k=...`` 按列表页流程抓 N 个商品，
``/dp/...`` 只分析该商品；同一个商品 ID 不会重复抓。日志会打印输入类型。

日志约定：每一次请求、每一张卡片、每一个字段、每一张图片、每一次落盘
都会打印一行，并且同时写入 run 目录下的 ``logs/crawl-debug.log``。
Cookie / Authorization 等敏感头的值一律不打印（只显示 [REDACTED]）。
"""

import argparse
import ast
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request
from urllib.parse import quote, urlsplit, urlunsplit

from parsel import Selector

# 让脚本在任何工作目录下都能 import 同目录的 joybuy_crawler 包。
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from joybuy_crawler.image_variants import resolve_highest_resolution
from joybuy_crawler.parsers.joybuy_uk import (
    UK_PRODUCT_URL_PATTERN,
    _flight_text,
    extract_variant_price,
    parse_uk_listing,
    parse_uk_product_detail,
    variant_page_url,
)
from joybuy_crawler.quality import apply_product_rules, check_listing_entry
from joybuy_crawler.render import classify_page

# ============================== 调试配置 ==============================
# 唯一的存储根目录：脚本只会往这里写，绝不碰 var/ 和数据库。
# 可以用环境变量 CRAWL_DEBUG_OUTPUT_DIR 或命令行 --output-dir 覆盖。
OUTPUT_DIR = Path(
    os.getenv(
        "CRAWL_DEBUG_OUTPUT_DIR",
        str(Path(__file__).resolve().parents[1] / "crawler_debug_output"),
    )
)

# 要抓的输入 URL，可以写多个、也可以混着写：
#   * 搜索/列表页：https://www.joybuy.co.uk/s?k=electronics → 解析卡片后抓 N 个商品
#   * 商品详情页：https://www.joybuy.co.uk/dp/<slug>/<id> → 只分析这一个商品
LISTING_URLS = [
    # "https://www.joybuy.co.uk/s?k=electronics",
    "https://www.joybuy.co.uk/dp/ochama-%E5%B0%8F%E7%BB%BF%E9%94%85-18l-%E7%94%B5%E5%8E%8B%E5%8A%9B%E9%94%85-13-%E4%BA%BA/100006995081936?requestIdentity=searchCategory",
    # "https://www.joybuy.co.uk/dp/plys-%E5%AE%B6%E7%94%A8%E4%B8%89%E4%BB%B6%E5%A5%97%E5%8E%A8%E5%88%80-%E6%B0%B4%E6%9E%9C%E5%88%80-%E5%8E%A8%E5%B8%88%E5%88%80-%E5%88%87%E7%89%87%E5%88%80/10505240?requestIdentity=searchCategory",
    # "https://www.joybuy.co.uk/dp/ochama-%E4%B8%AD%E5%BC%8F%E8%9C%82%E7%AA%9D%E4%B8%8D%E7%B2%98%E5%B0%91%E6%B2%B9%E7%83%9F%E7%82%92%E9%94%85-%E9%80%82%E7%94%A8%E4%BA%8E%E7%87%83%E6%B0%94-%E7%94%B5%E7%A3%81%E7%82%89-%E7%94%B5%E9%99%B6%E7%82%89-30cm/10003152?requestIdentity=searchCategory",
    # "https://www.joybuy.co.uk/dp/pure-cook-304%E4%B8%8D%E9%94%88%E9%92%A2%E5%8F%8C%E5%B1%82%E8%92%B8%E9%94%85%E5%A5%97%E8%A3%85-%E5%B8%A6%E7%8E%BB%E7%92%83%E7%9B%96-%E8%92%B8%E6%9E%B6%E5%92%8C2%E6%8A%8A%E6%B1%A4%E5%8B%BA-30/100828902?requestIdentity=searchCategory",
    # "https://www.joybuy.co.uk/dp/apple-iphone-17-pro-256-gb/10404455?requestIdentity=searchCategory",
]


# 每个列表页最多抓多少个商品详情。
PRODUCT_LIMIT = 1

# 请求间隔（秒）。正式链路是 2s 再乘 0.5~1.5 倍随机抖动，这里保持一致。
DOWNLOAD_DELAY = 2.0

# 登录态：cURL(bash) 解析出来的 headers / cookies 都是 dict。
# 默认从同目录 debug_session.py 读取（该文件已被 .gitignore 忽略，真实 Cookie 不进版本库）；
# 也可以用 --headers-file 指定别的 dict 文件，或 --cookie 直接追加。
# 键名大小写不限；headers 里的 cookie 可以是一整段字符串，也可以是 dict。
try:
    from debug_session import cookies as _session_cookies
    from debug_session import headers as _session_headers
except ImportError:  # 没有 debug_session.py 时按匿名抓取
    _session_cookies, _session_headers = {}, {}

# 需要临时覆盖/追加时改这两个 dict（会覆盖 debug_session.py 里的同名项）。
HEADERS: dict[str, str] = {}
COOKIES: dict[str, str] = {}

# 是否下载图片。只调试解析时可以关掉，速度快很多。
DOWNLOAD_IMAGES = True

# 是否下载商品视频（画廊里的视频，保存到商品目录 videos/）。
DOWNLOAD_VIDEOS = True

# 是否额外抓移动端详情页（m.joybuy.co.uk/dg/<sku>）。
# PC 端的规格参数/图文详情是客户端渲染（SSR 里是 BAILOUT 占位），
# 只有移动端 SSR 同时带规格参数和 structuredFloors 图文详情。
FETCH_MOBILE_SPECS = True

# 是否为非主变体逐个补抓价格页（每变体 1 次 /dp/<sku> 请求，WP-45 阶段 1）。
FETCH_VARIANT_PRICES = True
# 单个商品最多补抓多少个变体价格页。
VARIANT_PRICE_LIMIT = 10

# 命中风控页 / 登录墙时，是否改用真实 Chrome 重新取页面（需要本机装 Chrome）。
USE_BROWSER_FALLBACK = True

# 浏览器是否无头。调试浏览器渲染时改成 False（或命令行加 --headed）。
HEADLESS = True
# ======================================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
# Joybuy 商品图 CDN；flight JSON 里只给路径，需要自己拼主机和尺寸。
IMAGE_HOST = "images4.joy-sourcing.com"
IMAGE_SIZE_GALLERY = 1248  # 商品大图（mainMedia_bigImg__）
IMAGE_SIZE_SPEC = 96  # 规格处的小图（s96x96）
# 请求头兜底值；HEADERS / debug_session.py / --headers-file 里的同名项会覆盖它。
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.8",
    "Referer": "https://www.joybuy.co.uk/",
}
# 这些名字的请求头值永远不打印（项目纪律：Cookie/令牌不得进日志）。
SENSITIVE_HEADER_HINTS = (
    "cookie",
    "authorization",
    "auth",
    "token",
    "secret",
    "session",
)
# 刻意避开正式链路的 9333（抓取）/ 9334（登录），防止连到正式链路自己的浏览器。
BROWSER_DEBUG_PORT = 9335
BROWSER_PROFILE_DIRNAME = "browser_profile"
LOG = logging.getLogger("debug_crawl")

_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")
_BAD_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass
class CrawlConfig:
    output_dir: Path
    run_name: str
    listing_urls: list[str]
    product_limit: int
    download_delay: float
    download_images: bool
    browser_fallback: bool
    headless: bool
    #: 是否抓移动端详情页拿【规格参数】和图文详情。
    fetch_mobile_specs: bool = True
    #: WP-45：是否为非主变体逐个补抓价格页（每变体 1 次 /dp/<sku> 请求）。
    fetch_variant_prices: bool = True
    #: 单商品最多补抓多少个变体价格页。
    variant_price_limit: int = 10
    #: 是否下载画廊视频。
    download_videos: bool = True
    #: cURL(bash) 解析出来的 header dict（键名大小写不限，可含 cookie）。
    headers: dict[str, str] = field(default_factory=dict)
    #: cURL(bash) 解析出来的 cookie dict（name -> value）。
    cookies: dict[str, str] = field(default_factory=dict)
    timeout: float = 60.0
    log_level: str = "DEBUG"
    #: 登录态来源，仅用于启动日志。
    session_source: str = ""

    @property
    def run_root(self) -> Path:
        return self.output_dir / self.run_name

    def request_headers(self) -> dict[str, str]:
        """默认头 + dict 头合并，并把 cookies dict 合成 Cookie 头。"""

        merged = merge_headers(DEFAULT_HEADERS, self.headers)
        pairs = parse_cookie_pairs(header_value(merged, "Cookie"))
        pairs.update({str(name): str(value) for name, value in self.cookies.items()})
        if pairs:
            merged = merge_headers(
                merged,
                {
                    "Cookie": "; ".join(
                        f"{name}={value}" for name, value in pairs.items()
                    )
                },
            )
        else:
            merged = {
                name: value
                for name, value in merged.items()
                if name.lower() != "cookie"
            }
        return merged

    def user_agent(self) -> str:
        return str(header_value(self.request_headers(), "User-Agent") or USER_AGENT)

    def cookie_header(self) -> str:
        return str(header_value(self.request_headers(), "Cookie") or "")

    def as_dict(self) -> dict:
        headers = self.request_headers()
        cookie_count = len(parse_cookie_pairs(header_value(headers, "Cookie")))
        return {
            "output_dir": str(self.output_dir),
            "run_name": self.run_name,
            "listing_urls": self.listing_urls,
            "product_limit": self.product_limit,
            "download_delay": self.download_delay,
            "headers": header_summary(headers),
            "cookie": f"{cookie_count} 条 name=value（值不打印）"
            if cookie_count
            else "未设置（匿名）",
            "session_source": self.session_source or "未使用",
            "download_images": self.download_images,
            "download_videos": self.download_videos,
            "fetch_mobile_specs": self.fetch_mobile_specs,
            "fetch_variant_prices": self.fetch_variant_prices,
            "variant_price_limit": self.variant_price_limit,
            "browser_fallback": self.browser_fallback,
            "headless": self.headless,
            "timeout": self.timeout,
            "log_level": self.log_level,
        }


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------


def _reconfigure_stdio() -> None:
    """避免 Windows GBK 控制台因中文日志报 UnicodeEncodeError。"""

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def setup_logging(log_file: Path, level: str = "DEBUG") -> None:
    """控制台 + 文件双写；同一行日志两边都能看到。"""

    log_file.parent.mkdir(parents=True, exist_ok=True)
    numeric_level = getattr(logging, str(level).upper(), logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(numeric_level)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    LOG.setLevel(numeric_level)
    LOG.debug("日志已初始化：%s（级别 %s）", log_file, level)


def log_section(title: str) -> None:
    LOG.info("──────────────── %s ────────────────", title)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", (name or "").lower()).strip("-")
    return slug[:80] or "uncategorized"


def payload_fingerprint(payload: dict) -> str:
    canonical = json.dumps(
        payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.debug("写入 JSON → %s（%d 字节）", path, path.stat().st_size)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    LOG.debug("写入文件 → %s（%d 字符）", path, len(text))


def polite_sleep(delay: float) -> None:
    if delay <= 0:
        return
    actual = delay * random.uniform(0.5, 1.5)
    LOG.debug("限速等待 %.2fs（基准 %.2fs × 随机抖动）", actual, delay)
    time.sleep(actual)


# ---------------------------------------------------------------------------
# 请求头 / Cookie（都按 cURL(bash) 解析出来的 dict 处理）
# ---------------------------------------------------------------------------


def merge_headers(base: dict | None, extra: dict | None) -> dict[str, str]:
    """大小写不敏感地合并两个 header dict；同名的后写覆盖先写。"""

    result = {str(name): str(value) for name, value in (base or {}).items()}
    for name, value in (extra or {}).items():
        lowered = str(name).lower()
        for existing in list(result):
            if existing.lower() == lowered:
                del result[existing]
        # cookie 允许是 dict，留给 parse_cookie_pairs 展开。
        result[str(name)] = value if isinstance(value, dict) else str(value)
    return result


def header_value(headers: dict | None, name: str) -> str | dict:
    """按大小写不敏感的名字取 header 值。"""

    lowered = name.lower()
    for key, value in (headers or {}).items():
        if str(key).lower() == lowered:
            return value
    return ""


def parse_cookie_pairs(value) -> dict[str, str]:
    """把 Cookie 头字符串或 cookie dict 统一成 ``{name: value}``。"""

    if isinstance(value, dict):
        return {str(name): str(item) for name, item in value.items()}
    pairs: dict[str, str] = {}
    for part in str(value or "").split(";"):
        name, sep, item = part.partition("=")
        if sep and name.strip():
            pairs[name.strip()] = item.strip()
    return pairs


def header_summary(headers: dict | None) -> str:
    """日志用的请求头摘要；敏感值一律 [REDACTED]。"""

    parts = []
    for name, value in (headers or {}).items():
        lowered = str(name).lower()
        if any(hint in lowered for hint in SENSITIVE_HEADER_HINTS):
            parts.append(f"{name}=[REDACTED]")
        else:
            parts.append(f"{name}={str(value)[:120]}")
    return "; ".join(parts)


def as_str_dict(value) -> dict[str, str]:
    """任意 dict -> ``{str: str}``；不是 dict 时返回空 dict。"""

    if not isinstance(value, dict):
        return {}
    return {str(name): str(item) for name, item in value.items()}


def normalize_url(url: str) -> str:
    """把含中文等非 ASCII 字符的 URL 编码成 urllib 能发出去的 ASCII 形式。

    Joybuy 列表页的 href 里直接带中文（如 ``/dp/佳能-pixma-ts6550i/...``），
    ``urllib`` 只接受 ASCII URL，不编码会报
    ``UnicodeEncodeError: 'ascii' codec can't encode ...``。
    """

    parts = urlsplit(str(url or ""))
    if not parts.scheme:
        return str(url or "")
    safe = "/%:@!$&'()*+,;=-._~"
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe=safe),
            quote(parts.query, safe=safe + "?"),
            parts.fragment,
        )
    )


def _assignment_dicts(text: str) -> dict:
    """解析 ``headers = {...}`` / ``cookies = {...}`` 这种粘贴形式。"""

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {"headers", "cookies"}:
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
    return found


def load_headers_file(path: Path) -> tuple[dict, dict]:
    """读取 cURL(bash) 解析出来的 dict 文件。

    支持四种写法：
      * 只有 header dict：``{"accept": "...", "cookie": "..."}``
      * 只有 cookie dict：``{"name": "value"}``
      * 同时含两者：``{"headers": {...}, "cookies": {...}}``
      * 带变量名的粘贴形式：``headers = {...}`` / ``cookies = {...}``
    也接受 JSON（小写 true/false）。返回 ``(headers, cookies)``。
    """

    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError(f"headers 文件为空：{path}")
    if re.search(r"(?m)^\s*(headers|cookies)\s*=", text):
        found = _assignment_dicts(text)
        if not found:
            raise ValueError(f"无法解析 headers 文件：{path}")
        return as_str_dict(found.get("headers")), as_str_dict(found.get("cookies"))
    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        data = json.loads(text)
    if not isinstance(data, dict):
        raise TypeError(f"headers 文件必须是 dict：{path}")
    if isinstance(data.get("headers"), dict) or isinstance(data.get("cookies"), dict):
        return as_str_dict(data.get("headers")), as_str_dict(data.get("cookies"))
    return as_str_dict(data), {}


# ---------------------------------------------------------------------------
# HTTP / 浏览器取页
# ---------------------------------------------------------------------------


class FetchError(RuntimeError):
    """所有重试都失败后抛出。"""


@dataclass
class FetchResult:
    status: int
    text: str
    #: 跟随 30x 之后的最终 URL；登录墙判定必须看它（列表页常被 307 到 /login）。
    url: str
    requested_url: str


def fetch_html(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 60.0,
    max_attempts: int = 3,
) -> FetchResult:
    """取一页 HTML；每次尝试都打印一行日志。

    ``headers`` 直接接受 cURL(bash) 解析出来的 dict（含 Cookie 也行），
    缺 User-Agent 时用默认值补齐。Cookie 值不会进日志。
    """

    request_headers = merge_headers(DEFAULT_HEADERS, headers)
    if not header_value(request_headers, "User-Agent"):
        request_headers["User-Agent"] = USER_AGENT
    cookie_count = len(parse_cookie_pairs(header_value(request_headers, "Cookie")))
    request_url = normalize_url(url)
    if request_url != url:
        LOG.debug("URL 含非 ASCII 字符，已编码：%s → %s", url, request_url)
    LOG.info(
        "HTTP 请求 → %s（请求头 %d 个，Cookie %d 条%s）",
        request_url,
        len(request_headers),
        cookie_count,
        "" if cookie_count else "，匿名",
    )
    LOG.debug("请求头明细：%s", header_summary(request_headers))

    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        req = request.Request(request_url, headers=request_headers)
        try:
            with request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                elapsed = time.monotonic() - started
                final_url = response.geturl()
                LOG.info(
                    "HTTP 响应 ← %s %s（%d 字节，%.2fs，第 %d/%d 次）",
                    response.status,
                    request_url,
                    len(raw),
                    elapsed,
                    attempt,
                    max_attempts,
                )
                if final_url and final_url != request_url:
                    LOG.warning("发生跳转：%s → %s", request_url, final_url)
                charset = response.headers.get_content_charset() or "utf-8"
                try:
                    text = raw.decode(charset, errors="replace")
                except LookupError:
                    text = raw.decode("utf-8", errors="replace")
                LOG.debug(
                    "响应体解码：charset=%s，Content-Type=%s",
                    charset,
                    response.headers.get("Content-Type", "—"),
                )
                return FetchResult(
                    status=response.status,
                    text=text,
                    url=final_url or url,
                    requested_url=request_url,
                )
        except error.HTTPError as exc:
            raw = exc.read()
            elapsed = time.monotonic() - started
            LOG.warning(
                "HTTP 错误 ← %s %s（%d 字节，%.2fs，第 %d/%d 次）",
                exc.code,
                url,
                len(raw),
                elapsed,
                attempt,
                max_attempts,
            )
            if exc.code in (429, 408, 500, 502, 503, 504) and attempt < max_attempts:
                backoff = min(30.0, 2.0**attempt)
                LOG.info("可重试状态 %s，%.1fs 后重试", exc.code, backoff)
                time.sleep(backoff)
                continue
            if exc.code in (401, 403, 404):
                # 403/401 往往就是风控页/登录墙，把页面交给调用方判定。
                return FetchResult(
                    status=exc.code,
                    text=raw.decode("utf-8", errors="replace"),
                    url=exc.geturl() or url,
                    requested_url=request_url,
                )
            raise FetchError(f"{url} 返回 HTTP {exc.code}") from exc
        except Exception as exc:
            elapsed = time.monotonic() - started
            LOG.warning(
                "网络异常 ← %s：%s: %s（%.2fs，第 %d/%d 次）",
                url,
                type(exc).__name__,
                exc,
                elapsed,
                attempt,
                max_attempts,
            )
            if attempt < max_attempts:
                backoff = min(30.0, 2.0**attempt)
                LOG.info("%.1fs 后重试", backoff)
                time.sleep(backoff)
                continue
            raise FetchError(f"{url} 重试 {max_attempts} 次仍失败：{exc}") from exc

    raise FetchError(f"{url} 重试 {max_attempts} 次仍失败")


def download_binary(
    url: str,
    *,
    timeout: float = 120.0,
    max_attempts: int = 3,
) -> bytes:
    """下载视频等二进制文件；每次尝试都打印状态和大小。"""

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": "https://www.joybuy.co.uk/",
    }
    LOG.info("文件下载 → %s", url)
    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        try:
            req = request.Request(url, headers=headers)
            with request.urlopen(req, timeout=timeout) as response:
                data = response.read()
                LOG.info(
                    "文件响应 ← %s %s（%d 字节，%.2fs，第 %d/%d 次）",
                    response.status,
                    url,
                    len(data),
                    time.monotonic() - started,
                    attempt,
                    max_attempts,
                )
                return data
        except error.HTTPError as exc:
            LOG.warning(
                "文件 HTTP 错误 ← %s %s（第 %d/%d 次）",
                exc.code,
                url,
                attempt,
                max_attempts,
            )
            if exc.code in (429, 408, 500, 502, 503, 504) and attempt < max_attempts:
                time.sleep(min(30.0, 2.0**attempt))
                continue
            raise FetchError(f"{url} 返回 HTTP {exc.code}") from exc
        except Exception as exc:
            LOG.warning(
                "文件下载异常 ← %s：%s: %s（第 %d/%d 次）",
                url,
                type(exc).__name__,
                exc,
                attempt,
                max_attempts,
            )
            if attempt < max_attempts:
                time.sleep(min(30.0, 2.0**attempt))
                continue
            raise FetchError(f"{url} 重试 {max_attempts} 次仍失败：{exc}") from exc
    raise FetchError(f"{url} 重试 {max_attempts} 次仍失败")


def _find_chrome() -> str:
    for candidate in (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
    ):
        if candidate.exists():
            return str(candidate)
    return ""


def _cookie_dicts(cookie_header) -> list[dict]:
    """Cookie 头字符串或 cookie dict -> DrissionPage 需要的 dict 列表。"""

    return [
        {"name": name, "value": value, "domain": "joybuy.co.uk", "path": "/"}
        for name, value in parse_cookie_pairs(cookie_header).items()
    ]


def browser_fetch_html(
    url: str,
    *,
    profile_dir: Path,
    headless: bool,
    cookie: str | dict = "",
    user_agent: str = "",
    timeout: float = 60.0,
) -> str:
    """用真实 Chrome（DrissionPage）取页面；用完立即关闭。"""

    from DrissionPage import ChromiumOptions, ChromiumPage

    options = ChromiumOptions()
    options.set_address(f"127.0.0.1:{BROWSER_DEBUG_PORT}")
    options.set_user_data_path(str(profile_dir))
    chrome_path = _find_chrome()
    if chrome_path:
        options.set_paths(browser_path=chrome_path)
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--no-first-run")
    options.set_argument("--disable-gpu")
    options.set_argument("--window-size", "1440,900")
    options.set_timeouts(page_load=int(timeout), script=20)
    if headless:
        options.headless()
    # 用 cURL 里那份 UA，避免浏览器身份和 HTTP 请求不一致。
    options.set_user_agent(user_agent or USER_AGENT)

    LOG.info(
        "浏览器启动 → 端口 %d，profile=%s，headless=%s",
        BROWSER_DEBUG_PORT,
        profile_dir,
        headless,
    )
    page = ChromiumPage(options)
    try:
        cookies = _cookie_dicts(cookie)
        if cookies:
            try:
                try:
                    page.set.cookies(cookies)
                except AttributeError:
                    page.set_cookies(cookies)
                LOG.info("浏览器已注入 %d 条 Cookie（值不打印）", len(cookies))
            except Exception as exc:  # noqa: BLE001 - Cookie 注入失败不阻断
                LOG.warning("浏览器 Cookie 注入失败：%s", exc)
        LOG.info("浏览器打开 → %s", url)
        page.get(url)
        LOG.debug("页面已加载，等待 2s 让前端稳定")
        time.sleep(2.0)
        try:
            page.scroll.to_bottom()
            LOG.debug("已滚动到底部（触发懒加载）")
            time.sleep(1.0)
        except Exception as exc:  # noqa: BLE001 - 懒加载滚动是尽力而为
            LOG.debug("滚动失败（忽略）：%s", exc)
        html = page.html or ""
        LOG.info("浏览器取回 ← %s（%d 字符，最终 URL=%s）", url, len(html), page.url)
        return html
    except Exception as exc:  # noqa: BLE001 - 浏览器失败由调用方决定降级
        LOG.error("浏览器取页失败 %s：%s: %s", url, type(exc).__name__, exc)
        return ""
    finally:
        try:
            page.quit()
            LOG.info("浏览器已关闭")
        except Exception as exc:  # noqa: BLE001 - 关闭失败不阻断
            LOG.warning("浏览器关闭异常（忽略）：%s", exc)


def _check_wall(
    page_url: str, html: str, *, fetch_url: str, config: CrawlConfig
) -> str:
    """检测风控页/登录墙；需要时用浏览器重取并返回新的 HTML。

    ``page_url`` 是跟随跳转后的最终 URL（登录墙判定必须用它），
    ``fetch_url`` 是浏览器降级时要打开的原始 URL。
    """

    verdict = classify_page(page_url, html)
    LOG.info(
        "页面判定：%s（HTML %d 字符）→ 风控=%s，登录墙=%s",
        page_url,
        len(html),
        verdict.risk_control,
        verdict.login_required,
    )
    if not (verdict.risk_control or verdict.login_required):
        return html
    if not config.browser_fallback:
        LOG.warning("命中风控/登录墙，但浏览器降级已关闭，继续用当前 HTML")
        return html
    LOG.warning(
        "命中%s，改用真实 Chrome 重取：%s",
        "风控页" if verdict.risk_control else "登录墙",
        fetch_url,
    )
    rendered = browser_fetch_html(
        fetch_url,
        profile_dir=config.run_root / BROWSER_PROFILE_DIRNAME,
        headless=config.headless,
        cookie=config.cookie_header(),
        user_agent=config.user_agent(),
        timeout=config.timeout,
    )
    if not rendered:
        LOG.error("浏览器也没取到内容，继续用原始 HTML（解析大概率会失败）")
        return html
    rendered_verdict = classify_page(fetch_url, rendered)
    LOG.info(
        "浏览器版页面判定：风控=%s，登录墙=%s",
        rendered_verdict.risk_control,
        rendered_verdict.login_required,
    )
    return rendered


# ---------------------------------------------------------------------------
# 落盘（完全独立于 var/ 和数据库）
# ---------------------------------------------------------------------------


def category_folder(run_root: Path, breadcrumb_names: list[str]) -> Path:
    parts = [slugify(name) for name in (breadcrumb_names or [])[:2]] or [
        "uncategorized"
    ]
    return run_root.joinpath("dataset", *parts)


def save_product(
    run_root: Path,
    *,
    breadcrumb_names: list[str],
    payload: dict,
    config: CrawlConfig,
    summary: dict,
) -> dict:
    """写一个商品目录：product.json / meta.json / images / 索引。"""

    source_id = str(payload.get("source_id") or "unknown")
    product_dir = category_folder(run_root, breadcrumb_names) / _BAD_FILENAME_RE.sub(
        "_", source_id
    )
    LOG.info("商品目录：%s", product_dir)
    (product_dir / "images" / "main").mkdir(parents=True, exist_ok=True)
    (product_dir / "images" / "detail").mkdir(parents=True, exist_ok=True)

    meta_path = product_dir / "meta.json"
    previous = {}
    if meta_path.exists():
        try:
            previous = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
    fingerprint = payload_fingerprint(payload)
    changed = previous.get("payload_sha256") != fingerprint
    captured_at = utc_now_iso()

    write_json(product_dir / "product.json", payload)
    LOG.info(
        "商品 %s 已落盘 product.json（内容%s）",
        source_id,
        "有变化" if changed else "无变化",
    )

    image_files = {"main": [], "detail": []}
    urls = payload.get("image_urls") or []
    main_urls, detail_urls = (urls[:1], urls[1:]) if urls else ([], [])
    detail_urls += payload.get("detail_image_urls") or []
    LOG.info(
        "图片清单：主图 %d 张，详情/画廊 %d 张，下载开关=%s",
        len(main_urls),
        len(detail_urls),
        config.download_images,
    )
    if config.download_images:
        for group, group_urls in (("main", main_urls), ("detail", detail_urls)):
            for position, image_url in enumerate(group_urls, start=1):
                LOG.info(
                    "图片下载 [%s %d/%d] → %s",
                    group,
                    position,
                    len(group_urls),
                    image_url,
                )
                try:
                    resolved_url, image_bytes = resolve_highest_resolution(image_url)
                except Exception as exc:  # noqa: BLE001 - 单张失败不终止
                    LOG.error(
                        "图片下载失败 [%s %d] %s：%s",
                        group,
                        position,
                        image_url,
                        exc,
                    )
                    image_files.setdefault(f"{group}_errors", []).append(
                        {"url": image_url, "error": str(exc)}
                    )
                    summary["images"]["failed"] += 1
                    continue
                suffix = ".webp" if ".webp" in image_url else ".jpg"
                target = product_dir / "images" / group / f"{position:02d}{suffix}"
                target.write_bytes(image_bytes)
                LOG.info(
                    "图片已保存 → %s（%d 字节，实际使用 %s）",
                    target,
                    len(image_bytes),
                    resolved_url,
                )
                image_files[group].append(
                    str(target.relative_to(product_dir)).replace("\\", "/")
                )
                summary["images"]["downloaded"] += 1
    else:
        LOG.info("已按配置跳过图片下载")

    video_files = []
    videos = payload.get("videos") or []
    LOG.info(
        "视频清单：%d 个，下载开关=%s",
        len(videos),
        config.download_videos,
    )
    if config.download_videos:
        for position, video in enumerate(videos, start=1):
            video_url = str(video.get("url") or "").strip()
            if not video_url:
                continue
            LOG.info(
                "视频下载 [%d/%d] → %s",
                position,
                len(videos),
                video_url,
            )
            try:
                video_bytes = download_binary(video_url)
            except Exception as exc:  # noqa: BLE001 - 单个视频失败不终止
                LOG.error("视频下载失败 %s：%s", video_url, exc)
                summary["videos"]["failed"] += 1
                continue
            target = product_dir / "videos" / f"{position:02d}.mp4"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(video_bytes)
            LOG.info(
                "视频已保存 → %s（%d 字节）",
                target,
                len(video_bytes),
            )
            video_files.append(str(target.relative_to(product_dir)).replace("\\", "/"))
            summary["videos"]["downloaded"] += 1
    elif videos:
        LOG.info("已按配置跳过视频下载")

    write_json(
        meta_path,
        {
            "source_id": source_id,
            "payload_sha256": fingerprint,
            "first_captured_at": previous.get("first_captured_at") or captured_at,
            "last_captured_at": captured_at,
            "capture_count": int(previous.get("capture_count") or 0) + 1,
            "changed": changed,
        },
    )

    index_line = {
        "source_id": source_id,
        "product_dir": str(product_dir.relative_to(run_root)).replace("\\", "/"),
        "images": image_files,
        "videos": video_files,
        "title": payload.get("title", ""),
        "payload_sha256": fingerprint,
        "captured_at": captured_at,
        "changed": changed,
        "breadcrumbs": [
            crumb.get("name", "")
            for crumb in (payload.get("joybuy", {}).get("breadcrumbs") or [])
        ],
    }
    index_path = category_folder(run_root, breadcrumb_names) / "dataset_index.jsonl"
    if changed or not previous:
        with open(index_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(index_line, ensure_ascii=False) + "\n")
        LOG.info("索引已追加 → %s（内容有变化）", index_path)
    else:
        LOG.info("索引未追加 → %s（内容无变化）", index_path)
    index_line["index_path"] = str(index_path)
    return index_line


# ---------------------------------------------------------------------------
# 商品字段逐行日志
# ---------------------------------------------------------------------------


def log_product_fields(product, extras: dict | None = None) -> None:
    LOG.info("── 商品 %s ──", product.source_id)
    LOG.info("标题：%s", product.title)
    LOG.info("品牌：%s", product.brand or "—")
    LOG.info(
        "价格：原价 %s %s（页面展示价 %s，促销标签 %s）",
        product.current_price,
        product.currency,
        product.main_price or "—",
        product.promotion_label or "—",
    )
    LOG.info("可售状态：%s", product.availability or "—")
    crumbs = " / ".join(
        crumb.get("name", "") for crumb in product.breadcrumbs if crumb.get("name")
    )
    LOG.info("面包屑（已截断到两级）：%s", crumbs or "—")
    LOG.info("卖家：%s（%s）", product.seller_name or "—", product.seller_url or "—")
    LOG.info("SKU：共 %d 个", len(product.skus))
    for index, sku in enumerate(product.skus, start=1):
        LOG.info(
            "  SKU %d：id=%s，价格=%s，可售=%s，规格=%s",
            index,
            sku.get("source_id", "—"),
            sku.get("price", "—"),
            sku.get("availability", "—"),
            json.dumps(sku.get("specs") or {}, ensure_ascii=False),
        )
    LOG.info("画廊图：%d 张", len(product.gallery))
    for index, image_url in enumerate(product.gallery, start=1):
        LOG.info("  图 %d：%s", index, image_url)
    if extras:
        LOG.info("画廊来源：%s", extras["gallery_source"])
        options = extras["spec_options"]
        LOG.info(
            "规格（可选值）：%d 组（来源 flight.productSeriesFloor + colorSizePartList）",
            len(options),
        )
        for option in options:
            LOG.info("  %s：%d 个可选值", option["name"], len(option["values"]))
            for value in option["values"]:
                image_text = (
                    f"，图片 {value['image_url']}"
                    if value["image_url"]
                    else "，无图片（纯文字规格）"
                )
                LOG.info(
                    "    - %s%s（SKU %s）",
                    value["value"],
                    image_text,
                    "、".join(value.get("sku_ids") or []) or "—",
                )
        variants = getattr(product, "variants", None) or []
        LOG.info(
            "变体：%d 个（主变体 %s，带价 %d 个）",
            len(variants),
            next(
                (v["source_sku_id"] for v in variants if v.get("is_primary")),
                "—",
            ),
            sum(1 for v in variants if v.get("price")),
        )
        for variant in variants:
            LOG.info(
                "  变体 %s：%s，价格 %s %s（来源 %s），图 %s，stockState %s，skuStatus %s%s",
                variant.get("source_sku_id") or "—",
                json.dumps(variant.get("specification") or {}, ensure_ascii=False),
                variant.get("price") or "—",
                variant.get("currency") or "",
                variant.get("price_source") or "—",
                variant.get("image_url") or "—",
                variant.get("stock_state")
                if variant.get("stock_state") is not None
                else "—",
                variant.get("sku_status")
                if variant.get("sku_status") is not None
                else "—",
                "（主变体）" if variant.get("is_primary") else "",
            )
        tables = extras["specification_tables"]
        LOG.info(
            "规格参数：%d 条，%d 张表（来源 %s；展示必须是两列表格）",
            len(extras["specifications"]),
            len(tables),
            extras["specifications_source"],
        )
        for table in tables:
            LOG.info(
                "  表格【%s】%d 行（列：%s）",
                table["title"],
                len(table["rows"]),
                " | ".join(table["columns"]),
            )
            for row in table["rows"]:
                LOG.info("    | %s | %s |", row["name"], row["value"])
        sections = extras["content_sections"]
        LOG.info("图文详情：%d 个区块", len(sections))
        for section in sections:
            blocks = section.get("blocks") or []
            headings = [b for b in blocks if b["type"] == "heading"]
            LOG.info(
                "  【%s】%d 字，%d 图，%d 个子标题",
                section["title"],
                len(section["text"]),
                len(section["images"]),
                len(headings),
            )
            for block in blocks:
                if block["type"] == "heading":
                    LOG.info("    [子标题] %s", block["text"])
                else:
                    LOG.info("    [正文] %s", preview_text(block["text"]))
        LOG.info(
            "商品描述：%d 字，描述图 %d 张",
            len(extras["description"]),
            len(extras["description_images"]),
        )
        if extras["description"]:
            LOG.info("  描述正文（前 300 字）：%s", preview_text(extras["description"]))
        videos = extras["videos"]
        LOG.info("画廊视频：%d 个", len(videos))
        for index, video in enumerate(videos, start=1):
            LOG.info(
                "  视频 %d：%s（%s 秒，封面 %s）",
                index,
                video["url"],
                video.get("duration") if video.get("duration") is not None else "—",
                video.get("cover") or "—",
            )
    LOG.info("详情图：%d 张", len(product.detail_images))
    for index, image_url in enumerate(product.detail_images, start=1):
        LOG.info("  详情图 %d：%s", index, image_url)
    LOG.info(
        "评分：%s（%s 条，来源 %s，分布 %s）",
        product.rating_average or "—",
        product.rating_count if product.rating_count is not None else "—",
        product.rating_source or "—",
        json.dumps(product.rating_distribution or {}, ensure_ascii=False),
    )
    LOG.info(
        "AI 评价摘要：%s",
        (product.ai_summary[:200] + "…")
        if len(product.ai_summary or "") > 200
        else (product.ai_summary or "—"),
    )
    LOG.info(
        "AI 摘要标题：%s；标签：%s",
        product.ai_summary_title or "—",
        "、".join(product.ai_summary_tags or []) or "—",
    )
    LOG.info("缺失字段：%s", "、".join(product.missing_fields) or "无")


# ---------------------------------------------------------------------------
# 详情页增量解析（调试版；确认后同步回 joybuy_crawler/parsers/joybuy_uk.py）
# ---------------------------------------------------------------------------

_IMAGE_SIZE_RE = re.compile(r"/s(\d+)x(\d+)_")


def decode_server_product(html: str) -> tuple[dict, str]:
    """从 ``self.__next_f`` flight 流里解出完整的 ``serverProduct``。"""

    flight_text = _flight_text(html)
    idx = flight_text.find('"serverProduct":')
    if idx < 0:
        return {}, flight_text
    start = flight_text.find("{", idx)
    if start < 0:
        return {}, flight_text
    try:
        product, _ = json.JSONDecoder().raw_decode(flight_text[start:])
    except json.JSONDecodeError:
        return {}, flight_text
    return product, flight_text


def floors_by_id(product_data: dict) -> dict[str, dict]:
    """``serverProduct.data.floors`` -> ``{floorId: data}``（同 id 后写覆盖）。"""

    floors = {}
    for floor in (product_data.get("data") or {}).get("floors") or []:
        floor_id = str(floor.get("floorId") or "")
        if floor_id:
            floors[floor_id] = floor.get("data") or {}
    return floors


def resolve_flight_ref(text: str, ref: str):
    """解析 Next.js flight 的 ``"$7c"`` 槽位引用。"""

    slot = str(ref).lstrip("$")
    match = re.search(rf"(?m)^{re.escape(slot)}:", text)
    if not match:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[match.end() :].lstrip())
    except json.JSONDecodeError:
        return None
    if isinstance(value, str) and value.startswith("$"):
        return resolve_flight_ref(text, value)
    return value


def decode_json_after(text: str, key: str):
    """取 ``"key":`` 后面的 JSON 值；值是 ``"$ref"`` 时继续解析槽位。"""

    marker = f'"{key}":'
    idx = text.find(marker)
    if idx < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[idx + len(marker) :].lstrip())
    except json.JSONDecodeError:
        return None
    if isinstance(value, str) and value.startswith("$"):
        return resolve_flight_ref(text, value)
    return value


def product_image_url(path: str, size: int) -> str:
    """flight 里的图片路径 -> CDN 绝对地址（可指定 sNNNxNNN 尺寸）。"""

    path = str(path or "").strip().lstrip("/")
    if not path:
        return ""
    if path.startswith("http"):
        return path
    path = path.removeprefix("product/")
    path = re.sub(r"^s\d+x\d+_", "", path)
    url = f"https://{IMAGE_HOST}/product/s{size}x{size}_{path}"
    if url.endswith(".jpg"):
        url += "!q70.webp"
    return url


def normalize_gallery_url(url: str) -> str:
    """把任意尺寸的商品图 URL 统一成 s1248 大图。"""

    url = str(url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    match = re.search(r"/product/s\d+x\d+_(.+)$", url)
    if match:
        return product_image_url(match.group(1), IMAGE_SIZE_GALLERY)
    match = re.search(r"/product/(.+)$", url)
    if match:
        return product_image_url(match.group(1), IMAGE_SIZE_GALLERY)
    return url


def clean_gallery(urls: list[str]) -> list[str]:
    """只保留商品大图。

    过滤规则（2026-11-08 实测）：
    * 服务/保障图标在 ``images3.joy-sourcing.com/.../jfsintlpro-000-com/``，
      尺寸是 s32x32、``.png.webp``，必须丢弃；
    * 规格小图是 s96x96，不属于商品画廊；
    * 同一张图会出现 s598/s1248/s180 多个尺寸，按去掉尺寸后的路径去重，
      统一升级成 s1248。
    """

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in urls or []:
        original = f"https:{raw}" if str(raw).startswith("//") else str(raw or "")
        if "joy-sourcing.com" not in original or "/product/" not in original:
            continue
        if "-000-com" in original:
            continue
        size_match = _IMAGE_SIZE_RE.search(original)
        if size_match and int(size_match.group(1)) < 180:
            continue
        url = normalize_gallery_url(original)
        key = _IMAGE_SIZE_RE.sub("/s_", url)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(url)
    return cleaned


def extract_flight_gallery(floors: dict) -> list[str]:
    """商品画廊：优先 ``productMainImageFloor.mediaData``（含全部 5 张大图）。"""

    data = floors.get("productMainImageFloor") or {}
    urls: list[str] = []
    for media in data.get("mediaData") or []:
        if media.get("image") is False:
            continue
        path = media.get("bigImageUrl") or media.get("imageUrl")
        if path:
            urls.append(product_image_url(path, IMAGE_SIZE_GALLERY))
    if not urls:
        for part in data.get("imagePartList") or []:
            core = part.get("C-P#image&image") or {}
            paths = [core.get("bigImageUrl") or core.get("imageUrl")]
            paths.extend(core.get("supplementaryImageList") or [])
            for path in paths:
                if path:
                    urls.append(product_image_url(path, IMAGE_SIZE_GALLERY))
    return clean_gallery(urls)


def extract_spec_options(floors: dict) -> list[dict]:
    """规格可选值：``productSeriesFloor.series`` + ``productSelectedFloor.colorSizePartList``。

    返回 ``[{name: "颜色", values: [{value, image_url, sku_ids}]}]``。
    Joybuy 有两条规格来源：
    * ``productSeriesFloor``：系列/容量等（如「系列：1TB / 512gb / 256GB」），
      每个值带 ``skus``；
    * ``colorSizePartList``：颜色/尺寸等（如「颜色：白色」），规格图 s96x96。
    两边都解析，系列在前，颜色/尺寸在后。
    """

    options = []

    series_floor = floors.get("productSeriesFloor") or {}
    series_title = str(series_floor.get("title") or "系列").strip()
    series_values = []
    for item in series_floor.get("series") or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("name") or "").strip()
        if not value:
            continue
        series_values.append(
            {
                "value": value,
                "image_url": "",
                "sku_ids": [str(sku) for sku in item.get("skus") or []],
            }
        )
    if series_title and series_values:
        options.append({"name": series_title, "values": series_values})

    selected = floors.get("productSelectedFloor") or {}
    for group in selected.get("colorSizePartList") or []:
        dimension = group.get("C-P#dimension&dimension") or {}
        name = str(dimension.get("dimTitle") or "").strip()
        values = []
        for part in group.get("buttonPartList") or []:
            button = part.get("C-P#dimensionButton&dimensionButton") or {}
            value = str(button.get("text") or "").strip()
            if not value:
                continue
            image_path = str(button.get("imgUrl") or "").strip()
            values.append(
                {
                    "value": value,
                    "image_url": product_image_url(image_path, IMAGE_SIZE_SPEC)
                    if image_path
                    else "",
                    "sku_ids": [str(item) for item in button.get("skuList") or []],
                }
            )
        if name and values:
            options.append({"name": name, "values": values})
    return options


def sku_specs_from_options(options: list[dict]) -> dict[str, list[dict]]:
    """``sku_id -> [{name, value}]``，用于补齐 SKU 的 specs。"""

    mapping: dict[str, list[dict]] = {}
    for option in options:
        for value in option.get("values") or []:
            for sku_id in value.get("sku_ids") or []:
                mapping.setdefault(str(sku_id), []).append(
                    {"name": option["name"], "value": value["value"]}
                )
    return mapping


#: 这些区块是规格参数，不进 description 正文；由移动端规格解析统一处理。
SPEC_SECTION_TITLES = {"规格参数", "材质与规格", "技术规格"}


def _dedupe(values: list) -> list:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def preview_text(text: str, limit: int = 300) -> str:
    """日志用文本预览：压平换行，最多 ``limit`` 字，超出截断并标注。"""

    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit]}…（已截断，原文 {len(clean)} 字）"


def _image_from_src(src: str) -> str:
    if not src:
        return ""
    if src.startswith("//"):
        return f"https:{src}"
    if src.startswith("http"):
        return src
    return ""


def _node_text(node) -> str:
    return " ".join(" ".join(node.css("::text").getall()).split())


def _append_dom_block(node, blocks: list[dict]) -> None:
    """把一个 DOM 段落拆成子标题 + 正文。

    Joybuy 的富文本用 ``<strong>``/``<b>`` 表示子标题（页面上加粗放大），
    例如「1.8L 小巧容量」「安全提醒：」；同一段里剩下的文字是正文。
    """

    full = _node_text(node)
    if not full:
        return
    strong = node.css("strong, b")
    if strong:
        heading = _node_text(strong[0])
        if heading:
            blocks.append({"type": "heading", "text": heading})
            remainder = full
            if remainder.startswith(heading):
                remainder = remainder[len(heading) :]
            else:
                remainder = remainder.replace(heading, "", 1)
            remainder = remainder.strip(" ：:.-")
            if remainder:
                blocks.append({"type": "paragraph", "text": remainder})
            return
    blocks.append({"type": "paragraph", "text": full})


def extract_dom_sections(selector) -> list[dict]:
    """PC 端所有折叠区块：标题 + 子标题/正文块 + 图片。

    实测（2026-11-09）不同商品的区块标题不一样：商品描述/重要信息、
    核心卖点与优势/产品详情、主要特点与优势/商品详情/设置使用与兼容性…
    规格类区块（规格参数/材质与规格/技术规格）在 PC 端是客户端渲染，DOM 为空，
    由移动端 ``structuredFloors`` 补。
    """

    sections = []
    for accordion in selector.css('[class*="MuiAccordion-root"]'):
        title = " ".join(
            accordion.css('[class*="Accordion_title"] ::text').getall()
        ).strip()
        details = accordion.css('[class*="MuiAccordionDetails"]')
        if not title or not details:
            continue
        container = details.css('[aria-label="rich text container"]')
        root = container[0] if container else details[0]
        blocks: list[dict] = []
        nodes = root.xpath(
            ".//li | .//p[not(ancestor::li)] | "
            ".//h1[not(ancestor::li)] | .//h2[not(ancestor::li)] | "
            ".//h3[not(ancestor::li)] | .//h4[not(ancestor::li)] | "
            ".//h5[not(ancestor::li)] | .//h6[not(ancestor::li)]"
        )
        for node in nodes:
            _append_dom_block(node, blocks)
        if not blocks:
            text = _node_text(root)
            if text:
                blocks.append({"type": "paragraph", "text": text})
        images = _dedupe(
            [
                _image_from_src(src)
                for src in details.css("img::attr(src), img::attr(data-src)").getall()
            ]
        )
        sections.append(
            {
                "title": title,
                "blocks": blocks,
                "text": _blocks_text(blocks),
                "images": images,
            }
        )
    return sections


def extract_flight_rating(text: str, floors: dict) -> dict:
    """评价聚合：``ratingInfo``（内联对象或 $ref）→ 平均分/条数/星级分布。"""

    info = decode_json_after(text, "ratingInfo")
    if not isinstance(info, dict):
        info = {}
    common = (floors.get("productCommonFloor") or {}).get(
        "C-M#viewCommonItem&commonCore"
    ) or {}
    count_raw = info.get("commentCount")
    if count_raw is None:
        count_raw = common.get("commentCount")
    try:
        count = int(count_raw) if count_raw is not None else None
    except (TypeError, ValueError):
        count = None

    average_raw = info.get("averageScore")
    if average_raw is None:
        average_raw = common.get("commentStar")
    average = None
    try:
        if count and average_raw not in (None, "", "0", "0.0"):
            average = f"{float(average_raw):.1f}"
    except (TypeError, ValueError):
        average = str(average_raw) if average_raw else None

    distribution = {}
    if info:
        for level in range(1, 6):
            raw = info.get(f"score{level}Count")
            if raw is not None:
                try:
                    distribution[str(level)] = int(raw)
                except (TypeError, ValueError):
                    distribution[str(level)] = 0

    if info:
        source = "flight.ratingInfo"
    elif count is not None:
        source = "flight.productCommonFloor"
    else:
        source = ""
    return {
        "average": average,
        "count": count,
        "distribution": distribution,
        "source": source,
    }


def _resolve_refs(obj, text: str, depth: int = 0):
    """递归解析 flight 的 ``$ref``。"""

    if depth > 10:
        return obj
    if isinstance(obj, str) and obj.startswith("$"):
        return _resolve_refs(resolve_flight_ref(text, obj), text, depth + 1)
    if isinstance(obj, list):
        return [_resolve_refs(item, text, depth + 1) for item in obj]
    if isinstance(obj, dict):
        return {
            key: _resolve_refs(value, text, depth + 1) for key, value in obj.items()
        }
    return obj


def _attribute_groups(node, group: str) -> list[dict]:
    """从任意嵌套结构里收集 ``C-P#Attribute&attributeBasic`` 属性。"""

    params = []

    def walk(value):
        if isinstance(value, dict):
            basic = value.get("C-P#Attribute&attributeBasic")
            if isinstance(basic, dict):
                name = str(basic.get("attributeName") or "").strip()
                attribute_value = str(basic.get("attributes") or "").strip()
                if name and attribute_value:
                    params.append(
                        {"group": group, "name": name, "value": attribute_value}
                    )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return params


def _collect_blocks(node, blocks: list[dict], images: list[str]) -> None:
    """从 structuredFloors.modules 里收集「子标题/正文」块和图片。

    Joybuy 的富文本用 ``moduleData`` 的一项表示一组内容：
    * ``title`` 非空 → 页面显示为加粗放大的子标题；
    * ``text`` → 正文段落。
    这里必须保留顺序和类型，后续展示才能按子标题加粗渲染。
    """

    if isinstance(node, dict):
        title = node.get("title")
        text = node.get("text")
        if isinstance(title, str):
            clean = title.strip()
            if clean and clean not in {"TEXT", "TEXT_AREA"}:
                blocks.append({"type": "heading", "text": clean})
        if isinstance(text, str):
            clean = text.strip()
            if clean and clean not in {"TEXT", "TEXT_AREA"}:
                blocks.append({"type": "paragraph", "text": clean})
        for key, value in node.items():
            if key in {"title", "text"}:
                continue
            if key in {"imageUrl", "coverImageUrl"} and isinstance(value, str):
                url = _image_from_src(value)
                if url:
                    images.append(url)
            elif isinstance(value, (dict, list)):
                _collect_blocks(value, blocks, images)
    elif isinstance(node, list):
        for item in node:
            _collect_blocks(item, blocks, images)


def _blocks_text(blocks: list[dict]) -> str:
    return "\n".join(block["text"] for block in blocks if block.get("text"))


def build_specification_tables(specifications: list[dict]) -> list[dict]:
    """把规格参数按 group 组成表格：``{title, columns:[属性,值], rows}``。

    Joybuy 的【规格参数】/【材质与规格】/【技术规格】都是两列表格
    （属性名 | 属性值）；后续展示必须按 group 渲染成表格，不能拼成一段文本。
    行顺序保持源站顺序（``attributeSort`` 只作参考，不重排）。
    """

    groups: list[str] = []
    for item in specifications:
        group = str(item.get("group") or "规格参数").strip()
        if group not in groups:
            groups.append(group)
    tables = []
    for group in groups:
        rows = [
            {"name": item["name"], "value": item["value"]}
            for item in specifications
            if str(item.get("group") or "规格参数").strip() == group
        ]
        tables.append({"title": group, "columns": ["属性", "值"], "rows": rows})
    return tables


def extract_mobile_detail(html: str) -> tuple[list[dict], list[dict]]:
    """移动端 SSR：``structuredFloors`` 图文区块 + 规格参数。

    返回 ``(sections, specifications)``：
    * sections: ``[{title, text, images}]``，如 核心卖点与优势/产品详情/使用说明；
    * specifications: ``[{group, name, value}]``，group 为
      规格参数/材质与规格/技术规格。
    """

    text = _flight_text(html)
    sections: list[dict] = []
    specs: list[dict] = []

    idx = text.find('"structuredFloors":')
    if idx >= 0:
        start = text.find("[", idx)
        try:
            floors, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            floors = []
        for floor in _resolve_refs(floors, text):
            if not isinstance(floor, dict):
                continue
            data = floor.get("data") or {}
            title = str(data.get("structuredName") or "").strip()
            modules = data.get("modules")
            if data.get("mode") == 8 or str(data.get("moduleType")) == "3":
                specs.extend(_attribute_groups(modules, title or "规格参数"))
                continue
            blocks, images = [], []
            _collect_blocks(modules, blocks, images)
            if title:
                sections.append(
                    {
                        "title": title,
                        "blocks": blocks,
                        "text": _blocks_text(blocks),
                        "images": _dedupe(images),
                    }
                )

    # 旧版移动端结构（商品 1）：graphDetailsModule + graphDetailListN
    gidx = text.find('"graphDetailsModule":')
    if gidx >= 0:
        start = text.find("{", gidx)
        try:
            module, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            module = {}
        module = _resolve_refs(module, text)
        specs.extend(_attribute_groups(module.get("extendPartList"), "规格参数"))
        for group in module.get("specificationPartList") or []:
            if not isinstance(group, dict):
                continue
            basic = group.get("C-P#Specification&specificationBasic") or {}
            group_name = str(basic.get("specificationGroupName") or "规格参数").strip()
            specs.extend(_attribute_groups(group.get("attributePartList"), group_name))

    if not specs:
        for match in re.finditer(r'"graphDetailList\d+"\s*:', text):
            try:
                items, _ = json.JSONDecoder().raw_decode(text[match.end() :].lstrip())
            except json.JSONDecodeError:
                continue
            if isinstance(items, list):
                specs.extend(_attribute_groups(items, "规格参数"))

    seen = set()
    clean_specs = []
    for item in specs:
        key = (item["group"], item["name"], item["value"])
        if key in seen:
            continue
        seen.add(key)
        clean_specs.append(item)

    sections = [s for s in sections if s["text"] or s["images"]]
    return sections, clean_specs


def fetch_mobile_detail(
    source_id: str,
    *,
    config: CrawlConfig,
    summary: dict,
    mobile_dir: Path,
) -> dict:
    """抓移动端详情页拿规格参数和图文详情；失败只记日志，不影响主流程。"""

    summary["mobile_specs"]["attempted"] += 1
    url = f"https://m.joybuy.co.uk/dg/{source_id}"
    LOG.info("移动端详情（规格参数 + 图文详情）→ %s", url)
    try:
        result = fetch_html(
            url, headers=config.request_headers(), timeout=config.timeout
        )
    except FetchError as exc:
        LOG.warning("移动端详情抓取失败，规格参数/图文详情留空：%s", exc)
        summary["mobile_specs"]["failed"] += 1
        return {"sections": [], "specifications": []}
    write_text(mobile_dir / f"{_BAD_FILENAME_RE.sub('_', source_id)}.html", result.text)
    sections, specs = extract_mobile_detail(result.text)
    summary["mobile_specs"]["ok"] += 1
    LOG.info(
        "移动端详情：规格参数 %d 条，图文区块 %d 个",
        len(specs),
        len(sections),
    )
    return {"sections": sections, "specifications": specs}


def fetch_variant_prices(product, *, config: CrawlConfig, summary: dict) -> None:
    """WP-45：给 ``product.variants`` 补价格（主变体继承页面价格）。

    详情页 JSON 只描述当前浏览 sku 的价格（``productPriceFloor``）；
    每个非主变体用自己的 ``/dp/<sku>`` 页面补（每变体 1 次请求，上限
    ``config.variant_price_limit``）。单变体失败只留空价格，不影响商品落盘。
    """

    variants = getattr(product, "variants", None) or []
    if not variants:
        return
    for variant in variants:
        if variant.get("is_primary") and not variant.get("price"):
            variant["price"] = product.current_price
            variant["price_source"] = "detail_page"

    fetched = 0
    failed = 0
    for variant in variants:
        if fetched >= config.variant_price_limit:
            LOG.warning(
                "变体价格补抓达到上限 %d，其余变体 price 留空",
                config.variant_price_limit,
            )
            break
        sku_id = str(variant.get("source_sku_id") or "").strip()
        if not sku_id or variant.get("price") or variant.get("is_primary"):
            continue
        url = variant_page_url(sku_id)
        LOG.info("变体价格页 → %s", url)
        try:
            result = fetch_html(
                url, headers=config.request_headers(), timeout=config.timeout
            )
        except FetchError as exc:
            LOG.warning("变体 %s 价格页抓取失败，price 留空：%s", sku_id, exc)
            failed += 1
            continue
        fetched += 1
        summary.setdefault("variant_prices", {"attempted": 0, "ok": 0, "failed": 0})
        summary["variant_prices"]["attempted"] += 1
        price = None
        try:
            price = extract_variant_price(result.text)
        except Exception as exc:  # noqa: BLE001 - 单变体失败不阻断
            LOG.warning(
                "变体 %s 价格页解析失败：%s: %s", sku_id, type(exc).__name__, exc
            )
        if price:
            variant["price"] = price
            variant["price_source"] = "variant_page"
            summary["variant_prices"]["ok"] += 1
            LOG.info("变体 %s 价格：%s %s", sku_id, price, product.currency)
        else:
            summary["variant_prices"]["failed"] += 1
            LOG.warning("变体 %s 价格页没有可解析的价格，price 留空", sku_id)

    filled = sum(1 for variant in variants if variant.get("price"))
    LOG.info(
        "变体价格：共 %d 个变体，补抓 %d 次（失败 %d），带价 %d 个",
        len(variants),
        fetched,
        failed,
        filled,
    )


def extract_ai_summary(text: str) -> dict:
    """AI 评价摘要：flight 里 ``aiSummary.summaryContent`` / ``summaryText``。"""

    marker = '"aiSummary":'
    idx = text.find('"aiSummary":{"')
    if idx < 0:
        idx = text.find(marker)
    if idx < 0:
        return {"summary": "", "title": "", "tags": []}
    try:
        value, _ = json.JSONDecoder().raw_decode(text[idx + len(marker) :].lstrip())
    except json.JSONDecodeError:
        return {"summary": "", "title": "", "tags": []}
    if isinstance(value, str) and value.startswith("$"):
        value = _resolve_refs(value, text)
    if not isinstance(value, dict):
        return {"summary": "", "title": "", "tags": []}

    summary = str(value.get("summaryContent") or value.get("summary") or "").strip()
    title = str(value.get("summaryText") or "内容由人工智能总结自用户评价").strip()
    tags = []
    tag_list = decode_json_after(text, "aiTagList")
    if isinstance(tag_list, list):
        for item in tag_list:
            if isinstance(item, dict):
                tag_name = str(item.get("tagName") or "").strip()
                if tag_name:
                    tags.append(tag_name)
    return {"summary": summary, "title": title, "tags": _dedupe(tags)}


def extract_videos(floors: dict) -> list[dict]:
    """画廊视频：``productMainImageFloor.mediaData`` 里 mediaType=2 的项。"""

    data = floors.get("productMainImageFloor") or {}
    videos = []
    for media in data.get("mediaData") or []:
        if not isinstance(media, dict):
            continue
        if not (media.get("video") or str(media.get("mediaType")) == "2"):
            continue
        url = str(media.get("videoUrl") or media.get("playUrl") or "").strip()
        if not url:
            continue
        videos.append(
            {
                "url": url,
                "duration": media.get("duration"),
                "cover": str(media.get("coverImageUrl") or ""),
                "video_id": str(media.get("videoId") or ""),
            }
        )
    return videos


def extract_detail_extras(
    html: str,
    *,
    selector,
    source_id: str,
    fallback_gallery: list[str],
    config: CrawlConfig,
    summary: dict,
    mobile_dir: Path,
) -> dict:
    """一次性补齐正式解析器漏掉/解析错的详情字段。"""

    product_data, flight_text = decode_server_product(html)
    floors = floors_by_id(product_data)
    LOG.debug(
        "flight 解码：serverProduct=%s，floors=%d 个，flight 文本 %d 字符",
        "成功" if product_data else "失败",
        len(floors),
        len(flight_text),
    )

    gallery = extract_flight_gallery(floors)
    gallery_source = "flight.productMainImageFloor.mediaData"
    if not gallery:
        gallery = clean_gallery(fallback_gallery)
        gallery_source = "dom(正式解析器 gallery 过滤)"

    options = extract_spec_options(floors)
    dom_sections = extract_dom_sections(selector)
    rating = extract_flight_rating(flight_text, floors)
    videos = extract_videos(floors)
    ai_summary = extract_ai_summary(flight_text)

    mobile_sections: list[dict] = []
    specifications: list[dict] = []
    if config.fetch_mobile_specs:
        mobile = fetch_mobile_detail(
            source_id,
            config=config,
            summary=summary,
            mobile_dir=mobile_dir,
        )
        mobile_sections = mobile["sections"]
        specifications = mobile["specifications"]
        specifications_source = (
            "mobile.structuredFloors / graphDetailsModule"
            if specifications
            else "移动端无数据"
        )
    else:
        specifications_source = "已关闭（--no-mobile-specs）"

    # 移动端 structuredFloors 优先；PC DOM 补它没有的区块（如商品 1 的「重要信息」）。
    content_sections = list(mobile_sections)
    mobile_titles = {section["title"] for section in content_sections}
    for section in dom_sections:
        if section["title"] in mobile_titles:
            continue
        if section["text"] or section["images"]:
            content_sections.append(section)

    description_parts = []
    description_images: list[str] = []
    for section in content_sections:
        if section["title"] in SPEC_SECTION_TITLES:
            continue
        block_lines = []
        for block in section.get("blocks") or []:
            if block["type"] == "heading":
                block_lines.append(f"## {block['text']}")
            else:
                block_lines.append(block["text"])
        if block_lines:
            description_parts.append(
                f"【{section['title']}】\n" + "\n".join(block_lines)
            )
        elif section["images"]:
            description_parts.append(f"【{section['title']}】")
        for image in section["images"]:
            if image not in description_images:
                description_images.append(image)

    return {
        "gallery": gallery,
        "gallery_source": gallery_source,
        "spec_options": options,
        "sku_specs": sku_specs_from_options(options),
        "description": "\n\n".join(description_parts),
        "description_images": description_images,
        "content_sections": content_sections,
        "videos": videos,
        "rating": rating,
        "ai_summary": ai_summary,
        "specifications": specifications,
        "specification_tables": build_specification_tables(specifications),
        "specifications_source": specifications_source,
    }


def apply_detail_extras(product, extras: dict) -> None:
    """把增量解析结果写回 ``UkProduct``（随后 ``to_payload`` 自动带上）。"""

    if extras["gallery"]:
        product.gallery = extras["gallery"]
    if extras["description"]:
        product.description = extras["description"]
    if extras["description_images"]:
        merged = list(product.detail_images or [])
        for url in extras["description_images"]:
            if url not in merged:
                merged.append(url)
        product.detail_images = merged

    rating = extras["rating"]
    if rating["count"] is not None:
        product.rating_count = rating["count"]
    if rating["average"] is not None:
        product.rating_average = rating["average"]
    if rating["distribution"]:
        product.rating_distribution = rating["distribution"]
    if rating["source"]:
        product.rating_source = rating["source"]

    ai = extras.get("ai_summary") or {}
    if ai.get("summary"):
        product.ai_summary = ai["summary"]
        product.ai_summary_title = ai.get("title") or "内容由人工智能总结自用户评价"
        product.ai_summary_tags = list(ai.get("tags") or [])

    for sku in product.skus:
        specs = extras["sku_specs"].get(str(sku.get("source_id")))
        if specs:
            sku["specs"] = specs
    if product.skus and not any(sku.get("specs") for sku in product.skus):
        # 单规格商品：把只有一个可选值的维度直接挂到唯一 SKU 上。
        single_values = [
            {"name": option["name"], "value": option["values"][0]["value"]}
            for option in extras["spec_options"]
            if len(option.get("values") or []) == 1
        ]
        if single_values:
            product.skus[0]["specs"] = single_values


def is_product_url(url: str) -> bool:
    """输入是不是商品详情页（``/dp/<slug>/<id>``）。"""

    return bool(UK_PRODUCT_URL_PATTERN.search(str(url or "")))


def product_id_from_url(url: str) -> str:
    match = UK_PRODUCT_URL_PATTERN.search(str(url or ""))
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def process_product(
    source_url: str,
    source_id: str,
    *,
    config: CrawlConfig,
    summary: dict,
    run_root: Path,
    products_dir: Path,
    mobile_dir: Path,
    card_title: str = "",
) -> bool:
    """抓取并分析一个商品详情页；返回是否成功落盘。

    列表页流程和“手动输入商品详情 URL”流程共用这一段，
    保证两种入口产出的 `product.json` 完全一致。
    """

    summary["products"]["attempted"] += 1
    if card_title:
        LOG.info("商品 URL：%s（卡片标题：%s）", source_url, card_title)
    else:
        LOG.info("商品 URL：%s（手动输入）", source_url)

    try:
        detail_result = fetch_html(
            source_url,
            headers=config.request_headers(),
            timeout=config.timeout,
        )
    except FetchError as exc:
        LOG.error("详情页抓取失败：%s", exc)
        summary["products"]["failed"] += 1
        return False
    detail_html = detail_result.text

    detail_raw = products_dir / f"{_BAD_FILENAME_RE.sub('_', source_id)}.html"
    write_text(detail_raw, detail_html)
    LOG.info("详情页原始 HTML 已保存 → %s", detail_raw)

    detail_html = _check_wall(
        detail_result.url,
        detail_html,
        fetch_url=source_url,
        config=config,
    )
    if not detail_html.strip():
        LOG.error("详情页内容为空，跳过")
        summary["products"]["failed"] += 1
        return False

    try:
        product = parse_uk_product_detail(detail_html, source_url=source_url)
    except Exception as exc:  # noqa: BLE001 - 单页解析失败不终止
        LOG.error("详情页解析异常：%s: %s", type(exc).__name__, exc)
        LOG.debug("异常堆栈：\n%s", traceback.format_exc())
        summary["products"]["failed"] += 1
        return False

    summary["products"]["parsed"] += 1
    extras = extract_detail_extras(
        detail_html,
        selector=Selector(text=detail_html),
        source_id=source_id,
        fallback_gallery=product.gallery,
        config=config,
        summary=summary,
        mobile_dir=mobile_dir,
    )
    apply_detail_extras(product, extras)
    fetch_variant_prices(product, config=config, summary=summary)
    log_product_fields(product, extras)

    payload = product.to_payload()
    payload["spec_options"] = extras["spec_options"]
    payload["specifications"] = extras["specifications"]
    payload["specification_tables"] = extras["specification_tables"]
    payload["content_sections"] = extras["content_sections"]
    payload["videos"] = extras["videos"]
    payload["video_urls"] = [video["url"] for video in extras["videos"]]
    payload["joybuy"]["specOptions"] = extras["spec_options"]
    payload["joybuy"]["specifications"] = extras["specifications"]
    payload["joybuy"]["specificationTables"] = extras["specification_tables"]
    payload["joybuy"]["contentSections"] = extras["content_sections"]
    payload["joybuy"]["videos"] = extras["videos"]
    payload["debug_sources"] = {
        "gallery": extras["gallery_source"],
        "spec_options": "flight.productSeriesFloor + colorSizePartList",
        "variants": (
            "flight.productSeriesFloor + colorSizePartList"
            + ("（价格来自每变体 /dp/<sku> 页）" if product.variants else "")
        ),
        "specifications": extras["specifications_source"],
        "description": "mobile.structuredFloors / dom accordions",
        "ai_summary": "flight.aiSummary" if extras["ai_summary"]["summary"] else "none",
        "videos": "flight.productMainImageFloor.mediaData",
        "rating": extras["rating"]["source"] or "none",
    }
    cleaned_payload, outcome = apply_product_rules(payload, source_url=source_url)
    if outcome.violations:
        LOG.warning("质量规则命中：%s", outcome.summary())
    else:
        LOG.info("质量规则：全部通过")
    if outcome.fatal:
        summary["products"]["rejected"] += 1
        LOG.error("商品 %s 被质量规则拦截，不落盘", source_id)
        return False

    breadcrumb_names = [
        crumb.get("name", "")
        for crumb in product.breadcrumbs
        if crumb.get("name") and crumb.get("name", "").lower() not in {"home", "首页"}
    ]
    try:
        index_line = save_product(
            run_root,
            breadcrumb_names=breadcrumb_names,
            payload=cleaned_payload,
            config=config,
            summary=summary,
        )
    except Exception as exc:  # noqa: BLE001 - 落盘失败要看到完整堆栈
        LOG.error("商品 %s 落盘失败：%s: %s", source_id, type(exc).__name__, exc)
        LOG.debug("异常堆栈：\n%s", traceback.format_exc())
        summary["products"]["failed"] += 1
        return False

    summary["products"]["saved"] += 1
    summary["details"].append(
        {
            "source_id": source_id,
            "title": product.title,
            "price": product.current_price,
            "currency": product.currency,
            "skus": len(product.skus),
            "variants": len(product.variants or []),
            "images": len(product.gallery) + len(product.detail_images),
            "spec_options": len(extras["spec_options"]),
            "specifications": len(extras["specifications"]),
            "specification_tables": len(extras["specification_tables"]),
            "description_length": len(extras["description"]),
            "content_sections": len(extras["content_sections"]),
            "videos": len(extras["videos"]),
            "ai_summary": bool(extras["ai_summary"]["summary"]),
            "rating": {
                "average": product.rating_average,
                "count": product.rating_count,
            },
            "product_dir": index_line.get("product_dir", ""),
            "changed": index_line.get("changed", False),
            "quality_warnings": outcome.summary(),
        }
    )
    LOG.info(
        "商品 %s 处理完成：落盘目录 %s（内容%s）",
        source_id,
        index_line.get("product_dir", "?"),
        "有变化" if index_line.get("changed") else "无变化",
    )
    return True


def crawl(config: CrawlConfig) -> dict:
    run_root = config.run_root
    listings_dir = run_root / "raw_html" / "listings"
    products_dir = run_root / "raw_html" / "products"
    mobile_dir = run_root / "raw_html" / "mobile"
    for directory in (
        run_root,
        listings_dir,
        products_dir,
        mobile_dir,
        run_root / "dataset",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    setup_logging(run_root / "logs" / "crawl-debug.log", config.log_level)

    LOG.info("=" * 78)
    LOG.info("Joybuy 爬虫独立调试开始（不连数据库、不写 var/、只写下面的目录）")
    LOG.info("本次输出目录：%s", run_root.resolve())
    for key, value in config.as_dict().items():
        LOG.info("配置 %-22s = %s", key, value)
    LOG.info("=" * 78)

    summary = {
        "run_started_at": utc_now_iso(),
        "run_finished_at": None,
        "output_dir": str(run_root.resolve()),
        "listing_urls": config.listing_urls,
        "product_limit": config.product_limit,
        "listings": {"total": 0, "ok": 0, "failed": 0, "risk_or_login": 0},
        "direct_products": {"total": 0, "saved": 0},
        "cards": {"total": 0, "rejected": 0},
        "products": {
            "attempted": 0,
            "parsed": 0,
            "saved": 0,
            "rejected": 0,
            "failed": 0,
        },
        "images": {"downloaded": 0, "failed": 0},
        "videos": {"downloaded": 0, "failed": 0},
        "mobile_specs": {"attempted": 0, "ok": 0, "failed": 0},
        "details": [],
    }

    seen_product_ids: set[str] = set()

    for listing_index, listing_url in enumerate(config.listing_urls, start=1):
        input_type = "商品详情页" if is_product_url(listing_url) else "列表页/搜索页"
        log_section(
            f"输入 {listing_index}/{len(config.listing_urls)}：{listing_url}（{input_type}）"
        )

        if is_product_url(listing_url):
            summary["direct_products"]["total"] += 1
            source_id = product_id_from_url(listing_url)
            if not source_id:
                LOG.error("商品详情 URL 里解析不出商品 ID，跳过")
                continue
            if source_id in seen_product_ids:
                LOG.info("商品 %s 已抓过，跳过重复输入", source_id)
                continue
            seen_product_ids.add(source_id)
            if listing_index > 1:
                polite_sleep(config.download_delay)
            LOG.info("输入识别：商品详情页 → 直接分析该商品，不解析列表页")
            if process_product(
                listing_url,
                source_id,
                config=config,
                summary=summary,
                run_root=run_root,
                products_dir=products_dir,
                mobile_dir=mobile_dir,
            ):
                summary["direct_products"]["saved"] += 1
            continue

        summary["listings"]["total"] += 1
        if listing_index > 1:
            polite_sleep(config.download_delay)

        try:
            listing_result = fetch_html(
                listing_url,
                headers=config.request_headers(),
                timeout=config.timeout,
            )
        except FetchError as exc:
            LOG.error("列表页抓取失败：%s", exc)
            summary["listings"]["failed"] += 1
            continue
        html = listing_result.text

        listing_raw = (
            listings_dir / f"{listing_index:02d}-{slugify(listing_url)[:60]}.html"
        )
        write_text(listing_raw, html)
        LOG.info("列表页原始 HTML 已保存 → %s", listing_raw)

        html_after_fallback = _check_wall(
            listing_result.url, html, fetch_url=listing_url, config=config
        )
        wall_verdict = classify_page(listing_result.url, html_after_fallback)
        if wall_verdict.risk_control or wall_verdict.login_required:
            summary["listings"]["risk_or_login"] += 1
            LOG.error(
                "列表页最终仍是%s，解析大概率会失败；需要登录态请用 --cookie 传入整段 Cookie",
                "风控页" if wall_verdict.risk_control else "登录墙",
            )
        if html_after_fallback is not html:
            write_text(
                listings_dir / f"{listing_index:02d}-rendered.html",
                html_after_fallback,
            )
        html = html_after_fallback

        try:
            entries = parse_uk_listing(html)
        except RuntimeError as exc:
            LOG.error("列表页解析失败（结构可能已改版）：%s", exc)
            summary["listings"]["failed"] += 1
            continue

        summary["listings"]["ok"] += 1
        LOG.info("列表页解析出 %d 张候选卡片", len(entries))

        accepted: list[tuple[int, object]] = []
        for entry_index, entry in enumerate(entries, start=1):
            verdict = check_listing_entry(
                title=entry.title, source_url=entry.source_url
            )
            LOG.info(
                "卡片 #%d：标题=%r，原价=%s，URL=%s",
                entry_index,
                entry.title,
                entry.original_price or "—",
                entry.source_url,
            )
            summary["cards"]["total"] += 1
            if verdict.fatal:
                summary["cards"]["rejected"] += 1
                LOG.warning("  丢弃卡片：%s", verdict.summary())
                continue
            if not UK_PRODUCT_URL_PATTERN.search(entry.source_url):
                LOG.warning("  丢弃卡片：URL 不是 /dp/ 商品页")
                continue
            accepted.append((entry_index, entry))

        LOG.info(
            "可用商品卡：%d 张（已丢弃 %d 张）",
            len(accepted),
            summary["cards"]["rejected"],
        )

        listing_attempted = 0
        for card_index, entry in accepted:
            match = UK_PRODUCT_URL_PATTERN.search(entry.source_url)
            source_id = match.group(1) if match else ""
            if not source_id:
                LOG.warning("卡片 #%d 解析不出商品 ID，跳过", card_index)
                continue
            if source_id in seen_product_ids:
                LOG.info("卡片 #%d 商品 %s 已抓过，跳过", card_index, source_id)
                continue
            if listing_attempted >= config.product_limit:
                LOG.info("已达到本列表页商品上限 %d，停止抓取", config.product_limit)
                break
            seen_product_ids.add(source_id)
            listing_attempted += 1

            polite_sleep(config.download_delay)
            log_section(
                f"详情页 {listing_attempted}/{config.product_limit}：商品 {source_id}"
            )
            process_product(
                entry.source_url,
                source_id,
                config=config,
                summary=summary,
                run_root=run_root,
                products_dir=products_dir,
                mobile_dir=mobile_dir,
                card_title=entry.title,
            )

    summary["run_finished_at"] = utc_now_iso()
    write_json(run_root / "summary.json", summary)

    log_section("运行结束")
    LOG.info(
        "列表页：成功 %d / 失败 %d",
        summary["listings"]["ok"],
        summary["listings"]["failed"],
    )
    LOG.info(
        "直接商品 URL：输入 %d 个，落盘 %d 个",
        summary["direct_products"]["total"],
        summary["direct_products"]["saved"],
    )
    LOG.info(
        "商品卡：解析 %d，丢弃 %d",
        summary["cards"]["total"],
        summary["cards"]["rejected"],
    )
    LOG.info(
        "详情：尝试 %d，解析 %d，落盘 %d（质量拦截 %d，抓取/解析失败 %d）",
        summary["products"]["attempted"],
        summary["products"]["parsed"],
        summary["products"]["saved"],
        summary["products"]["rejected"],
        summary["products"]["failed"],
    )
    LOG.info(
        "图片：成功 %d / 失败 %d",
        summary["images"]["downloaded"],
        summary["images"]["failed"],
    )
    LOG.info(
        "视频：成功 %d / 失败 %d",
        summary["videos"]["downloaded"],
        summary["videos"]["failed"],
    )
    LOG.info(
        "移动端规格参数：尝试 %d，成功 %d，失败 %d",
        summary["mobile_specs"]["attempted"],
        summary["mobile_specs"]["ok"],
        summary["mobile_specs"]["failed"],
    )
    LOG.info("输出目录：%s", run_root.resolve())
    LOG.info("统计文件：%s", (run_root / "summary.json").resolve())
    LOG.info("完整日志：%s", (run_root / "logs" / "crawl-debug.log").resolve())

    if summary["products"]["saved"] == 0:
        LOG.warning("本次没有成功落盘任何商品，请对照上面的日志排查")
    return summary


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Joybuy 爬虫任务独立调试：不连数据库、不写 var/，"
            "所有产物写入 --output-dir。"
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"存储根目录（默认 {OUTPUT_DIR}）",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="本次运行目录名（默认 run-年月日-时分秒）",
    )
    parser.add_argument(
        "--listing-url",
        action="append",
        default=None,
        help=(
            "输入 URL，可重复：搜索/列表页（/s?k=...）或商品详情页（/dp/...）；"
            "传入详情页时只分析该商品"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="每个搜索/列表页最多抓多少商品（商品详情页输入忽略此参数）",
    )
    parser.add_argument("--delay", type=float, default=None, help="请求间隔基准秒数")
    parser.add_argument(
        "--cookie",
        default=None,
        help="整段 Cookie 头字符串（会与 dict 里的 Cookie 合并，同名覆盖）",
    )
    parser.add_argument(
        "--headers-file",
        type=Path,
        default=None,
        help=(
            "从 cURL(bash) 解析出来的 dict 文件（JSON 或 Python dict 字面量，"
            "可含 headers/cookies 两个键）"
        ),
    )
    parser.add_argument("--timeout", type=float, default=None, help="单次请求超时秒数")
    parser.add_argument("--no-images", action="store_true", help="不下载图片")
    parser.add_argument("--no-videos", action="store_true", help="不下载画廊视频")
    parser.add_argument(
        "--no-mobile-specs",
        action="store_true",
        help="不抓移动端详情页（跳过规格参数和图文详情）",
    )
    parser.add_argument(
        "--no-variant-prices",
        action="store_true",
        help="不为非主变体补抓价格页（变体 price 留空）",
    )
    parser.add_argument(
        "--no-browser-fallback",
        action="store_true",
        help="命中风控/登录墙时不启用真实 Chrome",
    )
    parser.add_argument(
        "--headed", action="store_true", help="浏览器显示窗口（默认无头）"
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认 DEBUG，即所有行都打印）",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> CrawlConfig:
    run_name = args.run_name or datetime.now().strftime("run-%Y%m%d-%H%M%S")
    listing_urls = args.listing_url or list(LISTING_URLS)

    # 登录态优先级：debug_session.py < HEADERS/COOKIES 常量 < --headers-file < --cookie
    headers = merge_headers(as_str_dict(_session_headers), as_str_dict(HEADERS))
    cookies = as_str_dict(_session_cookies)
    cookies.update(as_str_dict(COOKIES))
    sources = []
    if _session_headers or _session_cookies:
        sources.append("debug_session.py")
    if args.headers_file:
        file_headers, file_cookies = load_headers_file(args.headers_file)
        headers = merge_headers(headers, file_headers)
        cookies.update(file_cookies)
        sources.append(str(args.headers_file))
    if args.cookie:
        cookies.update(parse_cookie_pairs(args.cookie))
        sources.append("--cookie")

    return CrawlConfig(
        output_dir=(args.output_dir or OUTPUT_DIR).expanduser(),
        run_name=run_name,
        listing_urls=[url.strip() for url in listing_urls if str(url or "").strip()],
        product_limit=args.limit if args.limit is not None else PRODUCT_LIMIT,
        download_delay=args.delay if args.delay is not None else DOWNLOAD_DELAY,
        download_images=DOWNLOAD_IMAGES and not args.no_images,
        browser_fallback=USE_BROWSER_FALLBACK and not args.no_browser_fallback,
        headless=HEADLESS and not args.headed,
        fetch_mobile_specs=FETCH_MOBILE_SPECS and not args.no_mobile_specs,
        fetch_variant_prices=FETCH_VARIANT_PRICES and not args.no_variant_prices,
        variant_price_limit=VARIANT_PRICE_LIMIT,
        download_videos=DOWNLOAD_VIDEOS and not args.no_videos,
        headers=headers,
        cookies=cookies,
        timeout=args.timeout or 60.0,
        log_level=args.log_level or "DEBUG",
        session_source=" + ".join(sources) if sources else "",
    )


def main(argv=None) -> int:
    _reconfigure_stdio()
    args = parse_args(argv)
    config = build_config(args)
    if not config.listing_urls:
        print(
            "没有输入 URL：请在文件顶部 LISTING_URLS 里填，或用 --listing-url 传入"
            "（搜索页 /s?k=... 或商品详情页 /dp/...）。"
        )
        return 2
    try:
        summary = crawl(config)
    except KeyboardInterrupt:
        print("\n已手动中断（Ctrl+C）。")
        return 130
    except Exception as exc:  # noqa: BLE001 - 调试脚本要看到完整堆栈
        LOG.error("运行崩溃：%s: %s", type(exc).__name__, exc)
        LOG.error("完整堆栈：\n%s", traceback.format_exc())
        return 1
    return 0 if summary["products"]["saved"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
