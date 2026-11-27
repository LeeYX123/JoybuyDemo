"""活动页 / 店铺页采集 spider（2026-11-25，job_kind=PAGE_SET）。

两段式（用户 2026-11-25 口径）：
1. **清单段**：逐页渲染真站活动页/店铺页（DrissionPage 真 Chrome；活动页
   是客户端渲染，纯 HTTP 拿不到商品），抽出 banner / 楼层标题 / 商品链接，
   冻结成 ``CrawlPageManifest``。此段只存链接，不采内容——真站中途换商品
   不影响采集目标。
2. **商品段**：按清单逐个抓 ``/dp/-/<source_id>`` 商品详情，复用父类的
   ``parse_detail``（PC 解析 + 移动端详情 + 变体价格链）与 StagingPipeline，
   入库口径与品类任务完全一致。

不改动 ``joybuy_run.py``：只继承并复用它的解析/落盘路径，重写入口。
"""

import json
import os
import re
import subprocess
import time
import urllib.request

import scrapy

from joybuy_crawler.parsers.joybuy_pages import parse_page_manifest
from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36"
)
PAGE_DEBUG_PORT = 9357


class PageRunSpider(JoybuyRunSpider):
    """一个 CrawlRun 采一组页面：先冻结商品链接清单，再逐商品采详情。"""

    name = "joybuy_pages"

    def __init__(self, run_public_id: str, *args, **kwargs):
        # 不调用父类 __init__：它按品类选择构建 targets，而页面任务没有类目。
        scrapy.Spider.__init__(self, *args, **kwargs)
        from crawler_control.models import CrawlRun

        self.crawl_run_public_id = run_public_id
        self.run = CrawlRun.objects.select_related("job", "job__source_catalog").get(
            public_id=run_public_id
        )
        self.job = self.run.job
        snapshot = self.run.params_snapshot or {}
        self.product_limit = int(snapshot.get("product_limit") or self.job.product_limit or 0)
        self.enqueue_cap = max(self.product_limit, 1)
        self.target_imported = None
        self.targets = []
        self.seen_product_ids = set()
        self.fatal_error = ""
        self.skip_imported_products = bool(snapshot.get("skip_imported_products", False))
        self.allow_pagination = False
        self.listing_fetch_errors = 0
        from collections import Counter

        self.listing_error_types = Counter()
        self.listing_successes = 0
        self.last_listing_error = ""

    # -- 清单段 --------------------------------------------------------------

    def _render_page(self, page, url: str, *, wait: float = 8.0) -> str:
        """用真 Chrome（DrissionPage）渲染一页并返回 HTML。"""

        from crawler_control.services import load_account_session

        account = self.run.account
        cookies = []
        if account is not None:
            try:
                session = load_account_session(account)
                cookies = [
                    {
                        "name": item.get("name"),
                        "value": str(item.get("value")),
                        "domain": item.get("domain") or ".joybuy.co.uk",
                        "path": item.get("path") or "/",
                    }
                    for item in (session.get("cookies") or [])
                    if item.get("name") and item.get("value") is not None
                ]
            except Exception as exc:  # noqa: BLE001 - 无会话仍可匿名渲染
                self.logger.warning("会话读取失败（继续匿名渲染）：%s", exc)
        page.get(url)
        time.sleep(wait)
        clicked = 0
        # 每一层的【View more】各点一次（用户口径：每层只点一次，不反复追加载）。
        # 之前只点页面上的第一个按钮，导致第 2 层之后仍停留在默认 5 个商品
        # （2026-11-26 jnSk 的 Flash sale / Coupon zone 就是这个问题）。
        #
        # 2026-11-26（第二轮修正）：不能再按「全页按钮列表 + 索引」点。展开后
        # 该层按钮会从 DOM 消失，列表整体前移，按索引遍历会跳层（89Hg 的
        # Home & other appliances / 无标题层就是这样被跳过的）。改为按模块
        # （.bab-opt-mod）定位：只点「卡片数 ≤ 5」的楼层自己的按钮，用 JS 点击
        # 绕开浮层遮挡；已展开的楼层（>5 张）直接跳过，不会重复展开。
        #
        # 2026-11-26（第三轮修正）：楼层是滚动懒挂载的，进入页面 8 秒时后面
        # 两三层还没进 DOM（89Hg 一直只展开前 3 层就是这个原因）。先滚到底把
        # 全部楼层挂出来，再点。
        for _ in range(8):
            page.scroll.to_bottom()
            time.sleep(0.6)
        page.scroll.to_top()
        time.sleep(1.5)
        click_js = r"""
        (() => {
          let clicked = 0;
          document.querySelectorAll('.bab-opt-mod').forEach((mod) => {
            const cards = mod.querySelectorAll('a[href*="/dp/"]').length;
            if (!cards || cards > 5) return;
            const btn = [...mod.querySelectorAll('button')].find((b) =>
              /^(view|visit|see)\s+more$/i.test((b.textContent || '').trim())
              || /^查看更多$/.test((b.textContent || '').trim())
            );
            if (!btn) return;
            btn.scrollIntoView({block: 'center'});
            btn.click();
            clicked += 1;
          });
          return clicked;
        })()
        """

        def _click_floors() -> int:
            try:
                result = page.run_cdp(
                    "Runtime.evaluate", expression=click_js, returnByValue=True
                )
                return int(((result or {}).get("result") or {}).get("value") or 0)
            except Exception as exc:  # noqa: BLE001 - JS 失败时退回文本点击
                self.logger.warning("楼层按钮 JS 点击失败（改用文本点击）：%s", exc)
                return -1

        for _pass in range(3):
            count = _click_floors()
            if count <= 0:
                break
            clicked += count
            time.sleep(3.0)
            page.scroll.to_bottom()
            time.sleep(1.0)

        if clicked == 0:
            # 兜底：页面没有 .bab-opt-mod 结构（如店铺页）时，仍按文案点击。
            labels = ("View more", "See more", "Visit more", "查看更多")
            for text in labels:
                for element in (page.eles(f"text={text}") or [])[:8]:
                    try:
                        element.scroll.to_see()
                        time.sleep(0.5)
                        element.click()
                        time.sleep(2.2)
                        clicked += 1
                    except Exception:  # noqa: BLE001
                        continue
        if clicked:
            self.logger.info("已点击 %d 个 View more：%s", clicked, url)
        if "/store/" in url:
            self._deep_scroll_store(page, url)
        for _ in range(8):
            page.scroll.to_bottom()
            time.sleep(0.6)
        html = page.html or ""
        # 2026-11-27：风控页的可靠判据是标题（实测匿名访问店铺页 = "Joybuy Risk Control"，正文只有 659 字）。
        # 命中就记 RISK_CONTROL_FALLBACK，让 watch_rotate.py 按风控规则切节点，下一轮换 IP 再来；
        # 否则会把「被风控」误判成「真站没有商品」。
        try:
            title = page.title or ""
        except Exception:  # noqa: BLE001
            title = ""
        if "risk control" in title.lower():
            from crawler_control.services import record_run_event

            self.logger.warning("浏览器渲染命中风控页（title=%r）：%s", title, url)
            record_run_event(
                self.run,
                level="WARNING",
                code="RISK_CONTROL_FALLBACK",
                message=(
                    f"浏览器渲染命中风控页（title={title!r}，正文仅 {len(html)} 字节）：{url}。"
                    "已按风控上报，watch_rotate.py 会切节点，下一轮重试。"
                ),
                source_url=url,
            )
        return html

    def _deep_scroll_store(
        self, page, url: str, *, target: int = 40, max_rounds: int = 12
    ) -> int:
        """店铺页深挖（2026-11-27，建任务方要求）：滚动 + 点 Load more，直到商品卡不再增长。

        背景：店铺页是 Next 栈 + 懒加载，首屏只有 10~15 个商品。只 `to_bottom()` 几次
        拿不到后续商品，清单会一直停在 7~15 件。这里按轮次：逐步滚动触发
        IntersectionObserver → 到底 → 点「Load more / 查看更多」→ 数卡片；
        连续两轮不再增长就停，或达到 target 件提前停。
        返回最终卡片数（用于日志与事件，便于判断「真站就只有这么少」）。
        """

        def _count() -> int:
            # 按「唯一 SKU」计数：一个商品卡通常有图片 + 标题两个 /dp/ 链接，
            # 直接数 <a> 会翻倍（2026-11-27 Dyson 店铺页实测 10 个链接 = 7 个商品）。
            count_js = r"""
            (() => {
              const ids = new Set();
              document.querySelectorAll('a[href*="/dp/"]').forEach((a) => {
                const href = (a.getAttribute('href') || '').split('?')[0].replace(/\/$/, '');
                const sku = href.split('/').pop();
                if (sku) ids.add(sku);
              });
              return ids.size;
            })()
            """
            try:
                result = page.run_cdp(
                    "Runtime.evaluate", expression=count_js, returnByValue=True
                )
                return int(((result or {}).get("result") or {}).get("value") or 0)
            except Exception:  # noqa: BLE001
                return -1

        click_js = r"""
        (() => {
          let n = 0;
          const re = /^(load|show|view|see)\s*more$/i;
          document
            .querySelectorAll('button, a, div[role="button"], span[role="button"]')
            .forEach((el) => {
              const t = (el.textContent || '').trim();
              if (!t || t.length > 24) return;
              if (!(re.test(t) || /^查看更多$/.test(t) || /^加载更多$/.test(t))) return;
              if (el.dataset.__jbDeepClicked) return;
              el.dataset.__jbDeepClicked = '1';
              el.scrollIntoView({block: 'center'});
              el.click();
              n += 1;
            });
          return n;
        })()
        """

        def _click_more() -> int:
            try:
                result = page.run_cdp(
                    "Runtime.evaluate", expression=click_js, returnByValue=True
                )
                return int(((result or {}).get("result") or {}).get("value") or 0)
            except Exception:  # noqa: BLE001
                return 0

        best = _count()
        stable = 0
        for round_no in range(1, max_rounds + 1):
            try:
                height = int(page.run_js("return document.body.scrollHeight") or 0)
            except Exception:  # noqa: BLE001
                height = 0
            if height:
                for step in range(1, 5):
                    try:
                        page.run_js(f"window.scrollTo(0, {int(height * step / 5)})")
                    except Exception:  # noqa: BLE001, S110 - 单步滚动失败继续
                        pass
                    time.sleep(0.4)
            page.scroll.to_bottom()
            time.sleep(1.5)
            clicked = _click_more()
            if clicked:
                self.logger.info("店铺页 Load more 点击 %d 个：%s", clicked, url)
                time.sleep(2.5)
            now = _count()
            self.logger.info(
                "店铺页深挖 第%d轮：卡片 %s（best %s，点击 %s）：%s",
                round_no, now, best, clicked, url,
            )
            if now > best:
                best = now
                stable = 0
            else:
                stable += 1
                if stable >= 2:
                    break
            if best >= target:
                break
        try:
            from crawler_control.services import record_run_event

            record_run_event(
                self.run,
                level="INFO",
                code="PAGE_STORE_DEEP_SCROLL",
                message=(
                    f"店铺页深挖结束 {url}：商品卡 {max(best, 0)} 个"
                    f"（逐步滚动 + Load more，最多 {max_rounds} 轮）。"
                ),
                source_url=url,
            )
        except Exception as exc:  # noqa: BLE001 - 事件失败不影响采集
            self.logger.warning("深挖事件记录失败：%s", exc)
        return best

    def _pick_debug_port(self) -> int:
        """给本次 run 挑一个空闲的 devtools 端口。

        页面采集允许并行（主批次 + 店铺页补采）：固定 9357 会互相抢占，
        以 run.pk 为偏移在 9357..9416 之间取第一个能 bind 的端口。
        """

        import socket

        base = PAGE_DEBUG_PORT + (self.run.pk % 40)
        for offset in range(60):
            port = base + offset
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError:
                    continue
                return port
        return base

    def _manifest_phase(self) -> list[dict]:
        """渲染全部页面并冻结清单；返回展平后的商品链接列表。"""

        from crawler_control.models import CrawlPageManifest
        from crawler_control.services import record_run_event
        from DrissionPage import ChromiumOptions, ChromiumPage

        pages = list((self.run.params_snapshot or {}).get("page_urls") or [])
        if not pages:
            self.fatal_error = "页面任务缺少 page_urls 参数。"
            return []

        # 断点续采（用户 2026-11-25 口径）：同一任务此前跑过且清单已冻结时，
        # 直接复用清单不再重渲染——真站随后换商品也不影响本次采集目标。
        from crawler_control.models import CrawlPageManifest as _Manifest

        frozen = {}
        for row in _Manifest.objects.filter(run__job=self.job).order_by("pk"):
            if row.product_count:
                frozen[row.page_url] = row

        from pathlib import Path as _Path

        # profile 按 run 隔离：两个采集 run 并行时共用同一 user-data-dir，
        # 第二个 Chrome 会因 profile 被占用而启动失败（2026-11-25 补采店铺页踩到）。
        raw_profile = (self.run.params_snapshot or {}).get("browser_profile") or str(
            _Path(__file__).resolve().parents[3]
            / "var"
            / "browser_profiles"
            / f"page_capture_{self.run.pk}"
        )
        profile = str(_Path(raw_profile).resolve())
        _Path(profile).mkdir(parents=True, exist_ok=True)
        ua = DEFAULT_UA
        browser_proxy = (os.getenv("CRAWL_HTTPS_PROXY") or os.getenv("CRAWL_HTTP_PROXY") or "").strip()
        debug_port = self._pick_debug_port()
        proc = subprocess.Popen(
            [
                CHROME,
                "--headless=new",
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                # 2026-11-27：浏览器渲染也必须走出站代理。之前 Chrome 是裸启动，
                # 页面与 XHR 全部用本机固定 IP 直连，既违背「不直连」口径，
                # 也让「列表为空」无法判断是真站缺失还是被风控。
                *([f"--proxy-server={browser_proxy}"] if browser_proxy else []),
                f"--user-agent={ua}",
                "--window-size=1896,960",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        products: list[dict] = []
        try:
            devtools_ok = False
            for _ in range(60):
                if proc.poll() is not None:
                    break
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{debug_port}/json/version", timeout=2
                    )
                    devtools_ok = True
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.5)
            if not devtools_ok:
                self.fatal_error = (
                    "Chrome 未能启动（devtools 端口未就绪）；请检查本机 Chrome 路径与残留进程。"
                )
                record_run_event(
                    self.run,
                    level="ERROR",
                    code="PAGE_BROWSER_LAUNCH_FAILED",
                    message=self.fatal_error,
                )
                return []
            options = ChromiumOptions()
            options.set_address(f"127.0.0.1:{debug_port}")
            options.set_user_data_path(profile)
            options.set_browser_path(CHROME)
            browser = ChromiumPage(options)
            # 账号 cookie（与品类任务同口径：每请求带账号会话）
            account = self.run.account
            if account is not None:
                try:
                    from crawler_control.services import load_account_session

                    session = load_account_session(account)
                    for item in session.get("cookies") or []:
                        if not item.get("name") or item.get("value") is None:
                            continue
                        try:
                            browser.set.cookies(
                                {
                                    "name": item["name"],
                                    "value": str(item["value"]),
                                    "domain": item.get("domain") or ".joybuy.co.uk",
                                    "path": item.get("path") or "/",
                                }
                            )
                        except Exception:  # noqa: BLE001
                            pass
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning("账号 cookie 注入失败（匿名继续）：%s", exc)

            for entry in pages:
                url = str((entry or {}).get("url") or "").strip()
                if not url:
                    continue
                existing = frozen.get(url)
                if existing is not None:
                    manifest = existing.data
                    record_run_event(
                        self.run,
                        level="INFO",
                        code="PAGE_MANIFEST_REUSED",
                        message=(
                            f"复用已冻结的商品清单 {url}（{existing.product_count} 个商品，"
                            f"来源 run {existing.run_id}），不再重渲染。"
                        ),
                        source_url=url,
                    )
                else:
                    try:
                        # 店铺页（Next 栈）首屏更重，等待更长；仍无商品再重试一次。
                        wait = 14.0 if "/store/" in url else 8.0
                        html = self._render_page(browser, url, wait=wait)
                        manifest = parse_page_manifest(html, url)
                        if not manifest.get("products") and "/store/" in url:
                            html = self._render_page(browser, url, wait=20.0)
                            manifest = parse_page_manifest(html, url)
                    except Exception as exc:  # noqa: BLE001
                        record_run_event(
                            self.run,
                            level="ERROR",
                            code="PAGE_RENDER_FAILED",
                            message=f"页面渲染失败 {url}：{exc}",
                            source_url=url,
                        )
                        continue
                kind = str((entry or {}).get("kind") or ("store" if "/store/" in url else "active"))
                external_id = str((entry or {}).get("external_id") or "") or _external_id(url)
                CrawlPageManifest.objects.update_or_create(
                    run=self.run,
                    page_url=url,
                    defaults={
                        "page_kind": kind,
                        "external_id": external_id,
                        "title": (manifest.get("title") or "")[:200],
                        "product_count": manifest.get("product_count", 0),
                        "data": manifest,
                    },
                )
                for card in manifest.get("products") or []:
                    products.append({**card, "page_url": url, "page_kind": kind})
                record_run_event(
                    self.run,
                    level="INFO",
                    code="PAGE_MANIFEST_FROZEN",
                    message=(
                        f"页面清单已冻结 {url}：商品 {manifest.get('product_count', 0)} 个，"
                        f"楼层 {sum(1 for b in manifest.get('blocks') or [] if b['type'] == 'floor')} 个。"
                    ),
                    source_url=url,
                )
                self.logger.info(
                    "PAGE_MANIFEST %s products=%s", url, manifest.get("product_count", 0)
                )
            browser.quit()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                proc.kill()
        return products

    # -- Scrapy 入口 ---------------------------------------------------------

    def start_requests(self):
        from crawler_control.services import record_run_event

        products = self._manifest_phase()
        if self.fatal_error:
            record_run_event(
                self.run, level="ERROR", code="PAGE_SET_INVALID", message=self.fatal_error
            )
            return
        payload = json.dumps(
            [
                {"source_id": item["source_id"], "page_url": item["page_url"]}
                for item in products
            ],
            ensure_ascii=False,
        )
        record_run_event(
            self.run,
            level="INFO",
            code="PAGE_PRODUCTS_FROZEN",
            message=f"商品链接清单：{len(products)} 个（第二阶段按清单逐个采详情）。",
        )
        self.logger.info("PAGE_PRODUCTS total=%d payload=%s", len(products), payload[:400])

        # 「跳过已入库」：断点续采时不再重复请求已入库商品的详情页。
        if self.skip_imported_products:
            from catalog.models import SpuSourceIdentity

            known = set(
                SpuSourceIdentity.objects.filter(
                    source_system__iexact="joybuy_uk",
                    source_id__in=[entry["source_id"] for entry in products],
                ).values_list("source_id", flat=True)
            )
            if known:
                products = [entry for entry in products if entry["source_id"] not in known]
                record_run_event(
                    self.run,
                    level="INFO",
                    code="PAGE_SKIP_IMPORTED",
                    message=f"跳过已入库商品 {len(known)} 个，本轮待采 {len(products)} 个。",
                )

        limit = int(self.enqueue_cap or len(products) or 1)
        for item in products[:limit]:
            source_id = item["source_id"]
            if source_id in self.seen_product_ids:
                continue
            self.seen_product_ids.add(source_id)
            target = {
                "source_category_id": "",
                "category_name": item.get("title") or item["page_kind"],
                "source_url": item["page_url"],
                "pagination_base": "",
                "limit": limit,
                "collected": 0,
                "target_imported": None,
            }
            yield scrapy.Request(
                f"https://www.joybuy.co.uk/dp/-/{source_id}",
                callback=self.parse_detail,
                errback=self.listing_failed,
                meta={
                    "target": target,
                    "listing_entry": {
                        "title": item.get("title") or "",
                        "original_price": item.get("price") or "",
                        "image_url": item.get("image") or "",
                    },
                    "page_url": item["page_url"],
                },
                dont_filter=True,
            )


def _external_id(url: str) -> str:
    match = re.search(r"/(?:active|store)/([0-9A-Za-z]+)", url)
    return match.group(1) if match else ""
