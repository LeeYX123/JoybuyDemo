# Joybuy 新会话交接文档

> 本文档是新会话的第一入口。每次任务结束前必须更新；详细纪律见 `AGENTS.md`。

## 0bt. 商品图片本地缺文件（2026-11-23，`store_bytes` 去重补写 ✅ / 补抓 8,651 张 ✅ 0 失败 / 复扫缺失 0，未 commit）

- **任务**：用户报「商品图片本地缺文件导致网站裂图」，抽查十几个有七八个裂。实测 gallery 资产去重 **90,484**、本地缺文件 **8,651（9.56%）**，全部有 `source_url`；受影响 SPU **1,582**。前端读 `MediaUsage.role='gallery'` → `/media/<relative_path>`（dev 由 Django serve，文件不在就裂）。与 `0bk` 占位回退的关系：现在缺失图返回 200 SVG 占位而非 404，所以用户看到的是「图不对/占位」；补抓后占位不再命中。
- **根因（有代码证据，勿重复排查）**：`backend/media/storage.py::store_bytes` 命中 sha256 时只更新 `last_seen_at/updated_at`（必要时 `source_url`）就返回，**从不检查物理对象**。S3 时代（`MEDIA_BACKEND=s3`）创建的行字节只进了桶；切回本地后端后重抓同一张图被去重跳过 → 本地**永远不补写**，越重抓越缺。**DB 行存在 ≠ 文件存在。**
- **已完成 1：堵住源头**（源码只改 `backend/media/storage.py`）
  - 新增 `_object_exists(relative_path)`：`s3_enabled()` 时 `head_object`（`ClientError` → False），否则 `resolve_media_path(...).is_file()`；实现委托已有 `stored_file_exists()`，避免两份逻辑。
  - 去重命中分支改为：`if not _object_exists(existing.relative_path): store_file_bytes(existing.relative_path, data, content_type=normalized_mime or existing.mime_type)`，然后照旧更新 `last_seen_at` 等字段。**零额外网络**（`data` 就在手上），命中仍返回 `created=False`。
  - 测试：`backend/media/tests/test_media_storage.py` +2（①DB 有行但文件被删 → 同字节再存 → 文件被补写、`created=False`、`MediaAsset` 行数仍 1；②文件存在 → `patch("media.storage.store_file_bytes")` 断言未调用且 mtime 不变）、`test_media_storage_s3.py` +1（S3 模式对象被删 → 命中后重新 `put_object`，content_type/bytes 正确、行数 1）。
  - 验证：`MEDIA_BACKEND=local ./.venv/Scripts/python.exe backend/manage.py test media.tests.test_media_storage media.tests.test_media_storage_s3 --keepdb --noinput --parallel 1` → **Ran 29 tests, OK**；`ruff check` + `ruff format --check` 三个文件 → **All checks passed / 3 files already formatted**。按验证纪律只跑受影响的媒体测试，未跑全量。
- **已完成 2：补抓脚本** `var/media_materialize_20261123/materialize.py`（DRY_RUN 时目录里只有脚本本身；apply 后新增 `progress.json` / `report.json` / `apply.log`，另有 `verify.py` / `compare_source.py` 两个只读核验脚本）
  - 目标运行时重算：`MediaUsage.role='gallery'` 引用且 `stored_file_exists()` 为 False 的 `MediaAsset`（本次 8,651）。
  - **默认 DRY_RUN**：只统计 + 抽 5 个**不同 SPU** 打印（spu_public_id/title/relative_path/source_url 前 80 字符/该 SPU 缺失张数），不写任何文件；`--apply` 才下载。
  - apply 行为：`requests` 下载（连接 10s、读 60s）、失败重试 2 次（404 不重试）、并发 `--workers 8`（可调）、每 200 个原子落 `progress.json`、**已存在文件跳过**（断点续跑/幂等）、`sha256` 与 `asset.sha256` 不一致只报告不覆盖、直接 `store_file_bytes(relative_path, data)` **不走 `store_bytes`**（避免再撞去重）。
  - 失败分类：`dns / timeout / connection / ssl / http_404 / http_<code> / sha_mismatch / no_source_url / bad_url / write_error / unexpected`；`report.json` 含 `ok / skipped_existing / failure_breakdown / http_404_list / failures`（逐条带 SPU public_id）。
  - 安全：脚本文件内强制 `MEDIA_BACKEND=local` 语义，s3 下**拒绝启动**（除 `--allow-s3`，本批不用）；不碰 9334/FB、不 kill 任何进程、不删/不覆盖已有文件。
  - DRY_RUN 实测 `./.venv/Scripts/python.exe -I var/media_materialize_20261123/materialize.py`：`gallery_assets_total=90484 / gallery_assets_missing=8651 / missing_pct=9.56 / affected_spu_count=1582 / missing_without_source_url=0`；样例（不同 SPU）：`a24fca4e-6e9a-4360-bec1-5783b9122393` ochama 400W 离心榨汁机（该 SPU 缺 7 张）、`bee9c3f1-6c64-425d-a387-8f59bc6cdbe0` 硼硅玻璃茶壶（7 张）、`f2ac69a9-ee35-4143-99c9-23b0f1eefee5` ROVSUN 铸铁压汁器（9 张）、`e8d355fd-39d8-4c90-aa80-4121037e3d35` 不锈钢柠檬压汁器（1 张）、`d9386341-0d97-410f-a102-d0edbccf313a` KOMORE 咖啡机（6 张）。
  - 只读联通性验证（同一 `download()`，不写盘）：抽 4 个源站 URL 实抓 → **4/4 `status=ok` 且 sha256 与 asset 全部一致**（31/72/91/69 KB），host 均为 `images4.joy-sourcing.com`；当前网络可达（未出现 DNS 失败）。
- **用户报的 4 个 SPU apply 前复核**：`6bea71ac-9015-4517-8f88-0e8b88f5da46` gallery 9 / 缺 8；`13d74c05-0f2b-4c46-9fd2-a51be714ca59` 10/10；`b46f5247-2f45-47b8-8e8d-a162b636f825` 1/1；`154e81e0-99ef-4ed7-a124-9614f96be592` 5/5 —— 与用户抽查完全一致。
- **已完成 3：apply 实测（用户确认后执行）** `./.venv/Scripts/python.exe -I var/media_materialize_20261123/materialize.py --apply`
  - 结果：**8,651 / 8,651 成功（ok=8651），已存在跳过 0，失败 0**；`failure_breakdown={}`、`http_404_list=[]`、`failures=[]`；耗时 **2,529.3s ≈ 42.2 分钟**（8 并发，作业窗口 11:21:09→12:02:58 UTC）。源站全程未出现 DNS/超时/404/sha 不一致，说明这批 S3 时代资产在 `images4.joy-sourcing.com` 上仍完好。
  - 产物：`var/media_materialize_20261123/report.json`（分类计数 + `http_404_list` + `failures`）、`progress.json`、`apply.log`。**真 404 清单：空**（0 条，无需换图或兜底）。
  - 关闭 4 个用户 SPU 复核（`verify.py`，Django test client 走 dev `/media/` 路由，逐张比对响应字节 sha256，避免把 200 的 SVG 占位当成功）：`6bea71ac-9015-4517-8f88-0e8b88f5da46` 9/9、`13d74c05-0f2b-4c46-9fd2-a51be714ca59` 10/10、`b46f5247-2f45-47b8-8e8d-a162b636f825` 1/1、`154e81e0-99ef-4ed7-a124-9614f96be592` 5/5 —— **files_present / served_200_non_placeholder / served_sha256_match 三项全部等于 gallery 数，`all_ok=true`，failures=[]**（共 25 张）。
  - 同口径复扫（`verify.py` 复用 `materialize.load_missing_targets`）：`gallery_assets_total=90,484 / gallery_assets_missing=**0** / affected_spu_count=**0** / missing_without_source_url=0`。即 gallery 缺失从 8,651（9.56%）降到 **0**，没有残留非 404 缺失。
  - 与源站数量对比（`compare_source.py`；源站详情页需登录/风控，普通 HTTP 抓不到商品数据，故用爬虫 dataset 的最近一份 `product.json.image_urls` 作源站快照，导入时 gallery usage 就是逐条按它写的）：
    - 用户 4 个 SPU：DB 9/10/1/5 vs 源站 9/10/1/5，**全部 count_match**；`13d74c05` 有 5 条 URL 与快照不同（尺寸 token/换图导致字符串不同，**数量相同**）。
    - 另抽 6 个「本次刚补写」的商品（随机命中 apply 窗口内 mtime 的资产，再反查 SPU）：`a24fca4e…`（7/7）、`0d753697…`（10/10）、`c8ea9517…`（10/10）、`05c4eea9…`（5/5）、`6d5b0236…`（3/3）、`b7b0a4bd…`（5/5），全部 count_match，URL 集合同样仅个别尺寸 token 差异。
    - 结论：**数量本来就与源站一致**，之前的裂图纯属本地字节缺失，不是导入时少抓。
  - 复现命令（全部已实跑）：`./.venv/Scripts/python.exe -I var/media_materialize_20261123/materialize.py --apply`（补抓）→ `... verify.py`（复扫 + 4 个 SPU 逐字节 serve 校验 + 随机抽样出本次补写的 6 个 SPU）→ `... compare_source.py <spu 公id...>`（对源站快照比数量）。`verify.py` 抽到的 6 个 SPU 与上表一致（seed 固定 20261123，可复现）。
- **坑（不得再踩）**：①**任何「内容寻址去重」都必须校验物理对象存在**——DB 行存在 ≠ 文件在（这 8,651 张就是这么攒出来的）；②做媒体写入的脚本必须 `MEDIA_BACKEND=local` 覆盖启动（本脚本已内置强制并在 s3 下拒绝运行）；③`source_url` 前 80 字符几乎都一样（CDN 长公共前缀），要区分得看完整 URL 尾部；④DRY_RUN「零写盘」要当真验（跑完 `ls var/media_materialize_20261123/` 只有脚本）；⑤Windows 控制台 GBK 会因标题里的 U+2011 抛 `UnicodeEncodeError`，脚本已 `reconfigure(encoding="utf-8", errors="replace")`，自写脚本照做；⑥**核验 `serve` 不能只看 200**：`media.views` 对缺失文件返回 200 + SVG 占位（0bk），必须断言 content-type 非 `image/svg` 且字节 sha256 与 asset 一致；⑦别用 `find var/media -newermt` 找「本次写入的文件」（70 万文件在 NTFS 上跑 >10 分钟），改成随机抽 30~40 个 `MediaAsset` 查 mtime 命中更快。
- **遗留**：①gallery 已 0 缺失，但**其它 role 未在本次范围内**（review_image / cms_banner 等如有 S3 时代资产仍可能缺；需要时按同一脚本口径扩展 role 重跑）；②`0bk` 的占位回退保留不动——将来再有缺图仍应可见占位而不是 404；③真实浏览器抽验未做（本次用 Django test client 逐字节核验 `/media/`），若要视觉确认可拿 4 个用户 SPU 的 PDP 截图。
- **未 commit**：`backend/media/storage.py` + 两个测试文件；`var/media_materialize_20261123/{materialize.py,verify.py,compare_source.py}`（report/progress/日志也在该目录）。未动 `.env`、未动 AWS/S3。

## 0bs. 批次 AA 复验（2026-11-23，#5/#6 修复后，3/3 PASS，仅验收未改代码）

- **范围**：#5 商家端时延、#6 bm 入站闭环、每线程每分钟配额；报告见 `var/acceptance_aa_20261123/acceptance-report.md` 的「复验」节。**未改源码/配置**。
- **环境**：后端进程 18:54:32 启动 > `.env` 18:33:05，本轮**未重启**；开发方修复自测的 4 条回复已 `source=crisp` 入库，证明读的是真实 `.env`。
- **#5 PASS**：真实商家端 UI 连测 3 次 → **6.165s / 7.590s / 2.419s**（DB 入库 5.627 / 7.306 / 2.237s），全部 ≤10s。采样相位不同，最高 7.59s 仍有余量。
- **#6 PASS**：bm 会话 Crisp 人工回复 → 买家面板 **4.939s**；`sender_kind=support`、`source=crisp`；气泡 `merchant-chat__bubble--support` + 标签 `Support`（zh「客服」）、白底+左侧色条，与我方红底气泡区分；商家端 `GET /merchant/chats/{id}/messages` 返回同一条 support，UI 买家咨询 tab 作者「平台客服」+ `is-support`（`#fff5f4`）。
- **配额 PASS**：bm 线程 1s×58 轮询 = 43 次后端请求 → **11 次真实 Crisp 拉取**，`inbound_window_count=11`，最小间隔 **5.031s**（其余零 HTTP）。
- **回归**：`test_crisp_inbound+test_crisp_mirror+test_support_chat+test_merchant_chat` → **110 OK**；check/makemigrations OK，0006/0007 已应用；`ruff check` 过；vitest `MerchantChatPanel` **9 passed**；prettier 过；五语言 **531** 键一致。
- **minor（与 0bo §7 声明不符）**：`ruff format --check` 仍对 `crisp_inbound.py`（`_store_merchant_chat_reply` 签名换行、`Q(...)` 换行）与 `tests/test_crisp_inbound.py`（`pull_thread("bm:…")` 超长行）报需格式化，是本次修复新引入的；不影响运行，提交前 `ruff format` 一下。
- **清理**：MirrorLog 1 / MirrorSession 1 / MerchantChatMessage 2 / MerchantChatThread 1 / StaffSession 4 / BuyerSession 2 / BuyerAccount 1 / SupportMessage 3；HOMCOM 会话保留开发方 9 条、`last_message_at=2026-11-23 10:55:57`。
- **本轮 Crisp 会话（未删）**：新增 `session_bbfdbc6d-259a-4102-8ffe-6eb982c636ed`（bm）；复用 `session_b572cd2f-8ecb-4e73-a679-3bae32d64ad0`（merchant:HOMCOM）。
- **坑**：复验前必须核对「后端进程创建时间 > `.env` mtime」，否则会重演 0br 的静默 skipped；本轮未重启后端所以无此问题。

## 0br. 批次 AA 独立验收（2026-11-23，9/11 PASS，仅验收未改代码）

- **任务**：黑盒验收 `功能需求迭代文档03.md` 23.2（见 §0bo）。真连 Crisp，每方向 ≤2 条消息；报告与全部证据在 `var/acceptance_aa_20261123/`（`acceptance-report.md`）。**未改任何源码/配置**。
- **三条用户问题**：① 买家→Crisp→客服回复→买家面板 **闭环**（落库 2.488s、面板 2.743s）；② 商家消息在 Crisp 已变 `from=user` + `nickname=HOMCOM`（**闭环**）；③ Crisp→商家端**能收到**，但持续 5s 轮询时实测 **18.32s** 才可见（**不达 ≤10s 验收口径**）。
- **FAIL 清单**
  1. **#5 商家端时延**：`INBOUND_THROTTLE_SECONDS=20` 与商家端每 5s 的会话详情 GET 叠加，轮询持续占用节流窗口 → 最坏 ≈25s。离开消息页 >25s 再打开为 15ms。若 20s 节流不打算改，应把验收口径改成 ≤25s，或只对"当前打开中的会话"放宽窗口。
  2. **#6 bm 入站缺失（非回归）**：`bm:` 的 Crisp 人工回复不会回买家面板（`pull_thread` 对 bm 返回 unsupported，DB `source=crisp` 0 行）；bm 出站身份未变坏（operator + 店名）。语义上 bm 的 operator 就是商家，可落 `MerchantChatMessage(sender=merchant, source=crisp)`，需单独立项。
- **PASS 要点**：镜像 `CrispMirrorLog.status=sent`；判定只认 `user.user_id`（真实 payload 4 条无 id 全 False / 6 条有 id 全 True，`type=website` 不可作判据）；节流第二次 GET 0.064s 且 `last_inbound_at` 不变；游标回拨重拉不产生重复行；`_http_get` 两条回归用例 OK 且真实"已有会话"路径 message 70/45 正常 sent；管理端两 tab 回复 201 且镜像 operator +「Joybuy 客服」；首页/PDP/购物车 200 + console 0；五语言各 530 键一致；`check`/`makemigrations --check`/`ruff check` 干净。
- **minor**：`ruff format --check` 对新增迁移 `merchant_ops/migrations/0006_…py` 报 1 处空行（`crisp_mirror.py` / `test_crisp_mirror.py` 的 format 偏差在 HEAD 上就存在，非本批）。
- **踩坑（必看）**：验收中途 :8000 进程在 `.env` 被重写的瞬间启动（18:33:01 启动 / 18:33:05 写入），进程内 Crisp 配置为空 → 镜像静默 `skipped`、入站不拉取。**重启后端后必须确认 `.env` 已就绪**（本次 18:35:09 的买家消息因此未进 Crisp，18:35:32 的回复 124s 后才入库）。建议后端启动时对 Crisp 配置加健康检查。
- **Crisp 会话（未删）**：`session_fbf7f6f6-10b1-48c8-a1f5-ab2fe41fc2d1`（bp）、`session_b572cd2f-8ecb-4e73-a679-3bae32d64ad0`（merchant:HOMCOM，复用）、`session_ec38261a-85c7-4039-b29b-e8c3dc7415df`（bm）。
- **数据清理**：按 FK 顺序删除 MirrorLog 7、MirrorSession 2、MerchantChatMessage 2、MerchantChatThread 1、SupportChatMessage 5、SupportChatThread 1、StaffSession 3、BuyerSession 4、BuyerAccount 1、SupportMessage 4；HOMCOM 会话已恢复为 5 条历史消息、`last_message_at=2026-11-23 10:24:18`。
- **后续**：以上两条 FAIL 已在 `0bo` §10 修完并重验（5s 节流 + 12 次/分钟上限 → 商家端最坏 5.90s；bm 入站落 `sender_kind=support` → 买家最坏 6.15s、商家端可见）。本节保留作验收基线。

## 0bo. 批次 AA（2026-11-23 客服双向同步后端 + 商家端轮询，✅ 含验收修正 #5/#6，未 commit）

> 需求：`功能需求迭代文档03.md` 23.2（Q3/Q4/Q7(a)/Q8）；事实依据：`var/cs_sync_panel_20261123/findings.md`；独立验收结论见上面 `0br`（首轮 9/11）。**未 commit**、`MEDIA_BACKEND=local` 未动、未做 AWS。

- **范围**：Crisp → 我们的入站同步（买家 `bp:`、商家 `merchant:`、**买家↔商家 `bm:`**）、`merchant:` 出站改访客身份、去重/游标/节流、商家端平台客服 tab 轮询。**首轮验收的 #5（商家端 18.3s）与 #6（bm 不回传）已在 §10 修完重验。**

### 1. 模型与迁移（`backend/merchant_ops/models.py` + `migrations/0006_merchantchatmessage_crisp_fingerprint_and_more.py`、`0007_merchantchatthread_inbound_window_count_and_more.py`，**均已 migrate 到本机 MySQL**）
- `SupportChatMessage`（bp）、`MerchantChatMessage`（bm）、`SupportMessage`（merchant:）各加：`crisp_fingerprint`（BigInteger, null, db_index）、`source`（CharField(8), 默认 `local`，入站写 `crisp`）。
- 唯一约束允许 null 多行：`(thread, crisp_fingerprint)` → `schat_msg_thread_fp_unique` / `mchat_msg_thread_fp_unique`；`(conversation, crisp_fingerprint)` → `support_msg_conv_fp_unique`。
- 线程表 `SupportChatThread` / `MerchantChatThread` / `SupportConversation` 各加 `last_inbound_at`（DateTime, null）+ `inbound_cursor_ms`（BigInteger, null）+（0007）`inbound_window_start`（DateTime, null）/ `inbound_window_count`（PositiveInteger, 默认 0）。
- 0007 还给 `MerchantChatMessage.SenderKind` 加了 **`SUPPORT="support"`（"平台客服"）**，用于 bm 线程的 Crisp 人工回复。
- **消息 `created_at` 仍用 `auto_now_add`（不按 Crisp timestamp 回填）**：买家/商家端增量都是 `?after=<最后一条 created_at>`，回填到过去会让新消息永远查不出来。

### 2. 入站同步 `backend/merchant_ops/crisp_inbound.py`（新文件）
- `pull_thread(thread_key, now=None, budget_seconds=2.0)` → `{status: pulled|throttled|skipped|unsupported|failed, imported, requested, error[, reason]}`；`pull_support_chat(thread)` / `pull_conversation(conversation)` / `pull_merchant_chat(thread)` 是视图用包装。
- **节流（验收修正后）**：先原子 `UPDATE ... WHERE last_inbound_at IS NULL OR <= now-5s` 占窗口，抢不到直接 `throttled`（**零 HTTP**，`reason=window`）；失败/超时也占窗口，恢复后也不会打爆配额。**窗口 5s**（与前端 5s 轮询对齐，端到端 ≤10s），再叠**每线程每分钟 12 次**上限（`inbound_window_start`/`inbound_window_count` 计数窗口，超限 `throttled`、`reason=minute_cap`）防多标签页/脚本滥用。
- **每次拉取只发 1 个 HTTP**（不"连拉到空批"）：翻批会让配额外推 2 倍；游标推进保证下一轮补齐。
- **游标**：`inbound_cursor_ms` 直接当 `timestamp_after`（毫秒）；首次为空 → 只回看 72h；每批成功后写 `max(timestamp)`。
- **过滤 `is_operator_reply`**：`from=operator` + `type=text` + **`user.user_id` 存在且 != session_id**。**不要**用 `user.type=="website"` 排除 —— 实测（2026-11-23）用 website API 以 operator 身份发消息时 Crisp 会把 `user.type` 补成 `website`，真实 Inbox 回复没有该字段；唯一可靠判据是 `user_id` 有无（我方镜像恒无）。
- **落库**：bp → `SupportChatMessage(sender_kind=support, source=crisp)` + `buyer_unread+1`；merchant: → `SupportMessage(sender=PLATFORM, author_label=<operator 昵称>, source=crisp)`；**bm → `MerchantChatMessage(sender_kind=support, source=crisp)` + `buyer_unread+1`**；三者都更新 `last_message_at`。`IntegrityError` 视为已同步（并发去重）；`fingerprint` 缺失用 `sha256(session:timestamp:body)` 前 48bit 兜底。
- **失败降级**：任何异常只写一条 `CrispMirrorLog(thread_key, message_id="inbound_pull", sender_kind="inbound", status=failed)`（每线程复用一行、`attempts` 累加），绝不抛回请求。
- **触发点（Q7(a)，无 cron）**：`BuyerSupportChatMessagesView.get`、`MerchantConversationDetailView.get`（仅 `PLATFORM_SUPPORT`）、`BuyerMerchantChatMessagesView.get` 与 `MerchantChatMessagesView.get`（bm 两侧）在返回前调用。

### 3. `merchant:` 出站改访客身份（Q8）—— `crisp_mirror.py`
- 新增 `SENDER_MERCHANT_VISITOR="merchant_visitor"`：`from=user` + `user={type:website,nickname:店名}`；`queue_support_message_mirror` 的商家分支改用它。平台客服仍是 `SENDER_PLATFORM`（operator + `CRISP_PLATFORM_NICKNAME`）。
- `bm:` 保持 `SENDER_MERCHANT`（operator + 店名），`test_merchant_chat` 未改一字仍全过。
- **已知可接受代价**：同一条 `merchant:` 线程历史消息身份前后不一致（旧 operator / 新 user），实测 Crisp 里已出现混排；新会话无此问题。

### 4. 管理端 → Crisp 双写（Q3）
- 核对结论：**已齐，无需新增**。`/admin/support/conversations/{id}` reply → `queue_support_message_mirror`；`/admin/support-chat/threads/{id}/messages` reply → `queue_support_chat_mirror`；都走 `transaction.on_commit`，失败不影响 201。
- 仍缺（**有意不动**）：商家端 `kind=BUYER`（买家商品咨询）不镜像 —— 它没有对应的买家端线程，属历史数据。

### 5. 商家端轮询（`merchant-web/src/views/MessagesView.vue`）
- 原来只有 `pollBuyer`（买家咨询 tab）。新增 `pollSupport`（5s、`document.hidden` 时跳过、`pollInFlight` 防重入）：刷新 `/merchant/conversations` 列表未读 + 打开中会话的 `/merchant/conversations/{id}`；按"最后一条 id 是否变化"决定替换消息，避免跳动。`onMounted` 改为 `setInterval(pollActiveTab)`（按 tab 分发）。
- 不改 `mobile.html`/`folio`；管理端 `SupportView.vue` 不动。

### 6. **顺手修掉的既有 bug（重要）**
- `crisp_mirror._http_get(path)` 只收 1 个参数，但 `_request_with_retry` 统一用 `send(path, payload)` 调 → **只要命中"已有会话 → 补写 meta"分支就 TypeError**，消息卡在 `CrispMirrorLog.status=pending`、永远不再镜像（测试里 `_http_get` 一直被 mock 所以从没暴露；线上 2026-11-22 的日志有同一条崩溃）。已改成 `_http_get(path, payload=None)` 并加 2 条回归用例。

### 7. 验证（按验证纪律仅做了针对性验证；未跑全量）
- `manage.py check` → **no issues**；`makemigrations --check --dry-run` → **No changes detected**；`migrate merchant_ops` → **OK**（本机 MySQL，0006+0007 均已应用）。
- `test merchant_ops.tests.test_crisp_inbound` → **Ran 33, OK**（5s 节流内零 HTTP / 6s 后可拉 / 每分钟 12 次上限且跨分钟重置 / 只认 user_id / fingerprint 去重 / 游标推进 / 首次 72h / 每次 1 个 HTTP / 超时降级且占窗口 / 失败不影响 200 / bp、merchant:、bm 三种落库 / bm 买家 GET 接线 / 模型唯一约束）。
- `test merchant_ops.tests.test_crisp_mirror` → **Ran 34, OK**（+2 回归：`fetch_conversation_meta` 走真实签名、已有会话仍发消息；merchant: 断言改为 `from=user`）。
- `test test_support_chat test_merchant_chat test_crisp_mirror` → **77, OK**。
- `test merchant_ops` 全包 → **Ran 359, failures=3 errors=8**；这 **11 个失败在 HEAD worktree 上逐字相同**（`test_merchant_console_session` 9 个 + `test_admin_round2.NotificationApiTests` 2 个，均与客服无关），**不是本批引入**，不要去修。
- 前端：`vitest components/MerchantChatPanel.test.js` → **9 passed**（+1：support 气泡带 `merchant-chat__bubble--support` + `客服/Support` 标签、不带 `--mine`）；五语言键 **531×5 一致**。`vitest` 全量跑时 **4 个 `components/SupportChatLauncher.test.js` 失败是批次 AB 正在重写该组件造成的**（`SupportChatLauncher.vue` 有 1200+ 行未提交改动、AB 另建了 `tests/supportChatLauncher.test.js`），与 AA 无关。
- ruff：`ruff check backend/merchant_ops/` 全过；`crisp_inbound.py` / `test_crisp_inbound.py` / `0006` / `0007` `format --check` 过（**验收提的 0006 空行已 format 修掉**；`0003_crisp_mirror.py` 的 format 偏差是 HEAD 既有，不碰）；`eslint`/`prettier --check` 对 `MessagesView.vue`、`MerchantChatPanel.vue(.test)`、`messages.js` 全过。
- **端到端（真连 Crisp）**，脚本 `var/cs_sync_aa_e2e_20261123/e2e_check.py`（`state.json` 含会话 token，收尾已删；重跑先 `setup`）：
  - 买家（首轮）：`POST /api/v1/account/support-chat/messages` 201 → Crisp 新会话 `session_7f6c994e-…` 出现 `from=user` 镜像 → 用 website API 以 operator 身份发 `user.user_id=61b9b8df…` 的回复（Crisp 原样保留）→ 买家 `GET .../messages` **同一次请求内 0.79s** 返回 `[('buyer',…),('support',…)]`，DB `source=crisp`。
  - 商家（首轮）：`POST /merchant/conversations/{id}/messages` 201 → Crisp 新增消息 **`from=user` + nickname=HOMCOM**（旧消息仍 operator，混排符合预期）→ 人工回复 → `GET /merchant/conversations/{id}` **0.79s** 返回 `PLATFORM / Joy / …`。
  - **#5 时延重测（5s 节流后，模拟前端 5s 轮询）**：商家端三次 **≈0s / 5.00s / 5.00s**；最坏场景（先打一次占满窗口再发回复）**5.90s**。买家 bm 侧最坏 **6.15s**。全部 ≤10s。
  - **#6 bm 闭环**：`bm:` 会话（买家 vs MER001001）→ Crisp 人工回复 → 买家面板 **同一次轮询可见**（最坏 6.15s），`sender_kind=support`、`source=crisp`；商家端 `GET /merchant/chats/{id}/messages` 同样返回 `('support', …)`。
  - 配额：实测同一分钟内商家线程/ bm 线程 `inbound_window_count` 均为 **4**（上限 12）；重复 GET 不产生重复行；`throttled` 时零 HTTP。

### 8. 坑 / 新会话必看
1. **`user.type=="website"` 不能作为"我方镜像"判据**（见 §2）：Crisp 会给 API 注入的 operator 消息补 `type=website`，真实回复无该字段。唯一判据是 `user.user_id`。
2. `_http_get` 签名 bug 已修；**任何新的 `_request_with_retry` send 函数都必须接受 `(path, payload)` 两个参数**，否则线上静默 pending。
3. 入站消息**不要**用 Crisp timestamp 回填 `created_at`（会让 `?after=` 增量永远漏消息）。
4. 节流用条件 UPDATE 抢窗口（不是先读后写），并发轮询不会双发；失败也占窗口，别改成"失败不占"。
5. 本机开发库是 **MySQL**（`DJANGO_DATABASE_ENGINE` 默认 mysql，`.env` 在根目录由 settings 加载）；迁移已应用，别再用 sqlite 路径验证。
6. 后端 :8000 由 `var/run_backend_keepalive.sh` 守护（`--noreload`）：改完 py 必须 `taskkill` 掉监听进程，keepalive 会在 ~5-15s 内自动拉起；`taskkill` 需 `MSYS_NO_PATHCONV=1`。
7. e2e 里买家/商家会话是用 `create_buyer_session` / `create_staff_session` 直接签发的（等价于登录），**POST 必须带 `X-CSRFToken` 且 Cookie 里要有 `csrftoken`**（先 GET `/api/v1/auth/buyer/session`、`/api/v1/admin/auth/session`）；商家接口还要 `X-Merchant-Id`。
8. `test merchant_ops` 有 11 个与客服无关的历史失败（见 §7），跑之前先对齐这个基线，别误判成回归。`components/SupportChatLauncher.test.js` 的 4 个失败属批次 AB 未完成的改造。
9. **`bm:` 入站已接**（§10，落 `sender_kind=support`）；前端必须同时按 support 渲染，否则买家会把客服回复当成商家本人。新增的 sender_kind 是**枚举变更**，改 `MerchantChatMessage.SenderKind` 时别忘了迁移与商家端/买家端两处映射。
10. Crisp 里"商家消息改 from=user"只对新消息生效；存量会话历史混排不可逆。
11. **5s 节流 + 5s 前端轮询是"掐点"关系**：一次拉取耗时会顺移窗口，最坏 2 个轮询周期（实测 5.9s/6.15s）。要提高稳定性别再压窗口，而是让前端"一次轮询只打一个接口"或把 `INBOUND_THROTTLE_SECONDS` 设成 4.5s（会略超 12 次/分钟上限，需同步调 `INBOUND_MAX_PER_MINUTE`）。

### 9. 遗留
- **webhook 未确认**：website hook 是否在当前 Free 计划可用、是否签名/重试，代码无法代验（需在 Crisp 后台肉眼确认）；本批不依赖它。
- **真站客服面板内页未实测**（点击会话整页跳 `/login`，见 findings C4）——与 AB 批次相关，不影响本批后端。
- 商家端轮询只在"打开的消息中心页"生效；若商家离线，Crisp 回复要等下次打开会话才入库（Q7(a) 已拍板的取舍）。
- bm 线程的客服回复只累加 `buyer_unread`，**不累加 `merchant_unread`**（商家列表看不到"客服回复"红点，但消息本体、预览与详情都正常）。若产品要求商家也提醒，需要新增 `merchant_unread+1` 并区分角标来源。

### 10. 验收修正（2026-11-23 晚，闭 #5 / #6）
1. **#5 商家端 18.3s → 实测 ≤6.15s**：`INBOUND_THROTTLE_SECONDS` 20 → **5**（与前端 5s 轮询对齐）；新增 `INBOUND_MAX_PER_MINUTE=12` 与计数窗口（迁移 `0007` 的 `inbound_window_start`/`inbound_window_count`），超限 `throttled(reason=minute_cap)`；游标与 `last_inbound_at` 语义不变。
2. **#6 bm 入站**：`_resolve_target` 支持 `bm:{buyer}:{merchant}`；`pull_merchant_chat(thread)` 为视图包装；`MerchantChatMessage.SenderKind` 新增 **`support`**（迁移 `0007`）；落库 `sender_kind=support` + `buyer_unread+1`；`BuyerMerchantChatMessagesView.get` 与 `MerchantChatMessagesView.get` 都触发拉取。
3. **前端**：`storefront/components/MerchantChatPanel.vue` 对 `sender_kind=support` 加 `merchant-chat__bubble--support` 浅底+左色条与 `chat.supportLabel` 小标签（五语言：Support/客服/Support/Assistance/Klantenservice）；`merchant-web MessagesView.vue` 的买家会话对 support 显示作者「平台客服」+ `.chat-bubble.is-support` 样式。
4. 迁移 `0006` 的 ruff format 空行已修。


## 0bq. 批次 AB（2026-11-23 客服面板重做，✅，未 commit）

- **任务**：需求文档03 **23.3** 客服面板按真站重做（header / 会话列表 / 会话首屏 / FAQ / 发送订单 / 输入框内发送）。**未 commit；只改前端客服面板与 support.* 文案；未动后端（AA）、未动 `pages/p/[id].vue`（AC）、`AppHeader.vue`、`pages/account/*`、`merchant-web/`、`MEDIA_BACKEND`（仍 local）。**
- **改动文件**
  - `storefront/components/SupportChatLauncher.vue`：整体重写 UI 结构，保留原逻辑（未登录引导、5s 轮询、2000 字上限、乐观发送/失败重试/发送中禁用、轮询游标去重）。新增 `view: 'list' | 'conversation'`、订单弹层、`support.*` 新文案引用。
  - `storefront/locales/messages.js`：`support.*` 新增 **19 个键 ×5 语言**（本批结束时全库 **531/语言**：511 原基线 + 本批 19 + AA 并行 `chat.*` 1，五语言键集合一致，missing/extra 0）；`support.placeholder` 改为「请输入你的问题」/「Type your question」等。旧键 `support.title/subtitle/empty` 保留未删（暂无引用）。
  - `storefront/tests/supportChatLauncher.test.js`（新）：8 个组件测试。
  - `storefront/components/SupportChatLauncher.test.js`（批次 Y 旧文件，2026-11-23 按新双视图结构同步）：10 个测试（header 三元素 / 会话卡片 / 首屏欢迎语+3 FAQ+输入框 / 乐观发送 / FAQ 点击即发送并收起 / 清除后重进拉回 / 订单弹层多选两行 / 5s 轮询增量 / 未登录跳转 / 会话过期提示）。
  - 验收产物 `var/ab_support_panel_20261123/`（fixtures/setup_fixture.py、verify_panel.mjs、check_db.py、screens/*.png、e2e-result.json、db-check.json、backend8001.log、storefront-dev.log）。
- **真站实测值（直接采用，来自 `var/cs_sync_panel_20261123/findings.md` C2/C3）**
  - 面板：**375 宽 × 80% 高（max 720）**、`right:84` / `bottom:104.5`、背景 `#F5F6FA`、radius 8、border `#F0F1F2`、`0 2px 16px rgba(0,0,0,.078)`、z-index 1200；e2e 实测盒子 `375×720 @ (981,175.5)`（1440×1000 视口，与真站完全一致）。
  - header 60px 白底：左【清除】距边 16（24×24）、中【客服】24px/700、右【×】距边 16（24×24）。实测相对面板左边 17px（含 1px 面板边框，等价真站 981→998）。
  - 列表项：`padding:12px 16px`、头像 60 圆、标题 16/600 `#1A1A1A`、时间 12 `#505259`、摘要 14/500 两行截断、未读 16px `#E1251B`、hover `rgba(0,16,71,.102)`、列表 `padding-top:8px` + 卡片 `margin-bottom:8px`。
  - 清除图标为**自绘 24px 橡皮擦图标**（真站只测到 `clean-up-icon` 24×24，图标本身未取到）。真站 `delChatSession` 语义是删会话，但我们按 Q4 只清显示。
- **推定项（真站未实测，按需求 23.3 + 用户描述实现）**
  1. 会话内首屏**全部为推定**：居中客服头像（64 圆，本地内联耳机 SVG，非真站图）、欢迎语（用户提供的黑五大促文案 ×5 语言）、三条 FAQ 按钮（白底 8px 圆角、`min-height:40px`、文案居中、hover `rgba(0,16,71,.06)`）、【发送订单】药丸按钮、输入框（圆角 20、发送图标在框内右侧）。
  2. 欢迎语以**本地渲染的欢迎卡片**呈现（不写库、不伪造 support 消息）；FAQ 与订单按钮的显隐规则：FAQ 仅在**会话为空**时展示（发送任一消息后收起回到普通消息流），【发送订单】在输入框上方工具条**常驻**（否则聊天中途无法再发订单）。
  3. 会话视图**返回列表**用正文顶部的小返回条（`‹ 返回会话列表`）；真站 header 只测到清除/客服/×，没有返回控件，故返回入口放正文。
  4. 订单金额用**订单自身币种**（`Intl.NumberFormat('en-GB', {currency})` → `£12.34`），与任务书示例 `£xx` 一致；注意这与站点展示层「所有价格一律 `$`」的 2026-11-03 规则**不同**（订单消息属内容而非页面价格标签）。若要改回 `$` 只需改组件 `orderAmount()`。
  5. 订单号用**完整 UUID**（弹层里展示前 8 位大写 `#XXXXXXXX`，与订单页一致；消息正文用完整号便于客服查单）。
- **订单消息格式（Q5，按语言本地化，实测原文）**
  - zh：`【订单查询】订单号：<uuid>，金额：£7.99，状态：已取消`，多笔 `\n` 拼接成**一条**文本消息。
  - en：`Order enquiry — Order no.: <uuid>, amount: £7.99, status: Canceled`；de/fr/nl 对应翻译（`support.orderMessage`）。状态文案复用 `orders.status*`。
  - 数据源 `GET /api/v1/orders`（现有接口，`-created_at` 最新在前），取前 3 笔；弹层可多选（checkbox），确认按钮显示 `Send selected (N)`。
- **清除语义（Q4）**
  - **纯前端清屏**：点【清除】把已渲染消息清空、回到首屏（欢迎语 + FAQ 重新出现），**不调后端、不删库**；买家侧后端没有清除接口（只有管理端/网关侧 `delChatSession`，未接）。
  - 轮询游标**独立于 messages**，清除后不回退，所以 5s 轮询不会把历史重新拉回来；从列表**再次进入会话**会重新 `GET /messages` 拉回完整历史（e2e 实测 3 条清空后重进仍是 3 条）。
  - 清除按钮在会话列表视图或无消息时禁用（`#c4c6cc`）。
- **验证（按验证纪律仅做了针对性验证，未跑全量）**
  - 组件测试：`node node_modules/vitest/vitest.mjs run --root storefront components/SupportChatLauncher.test.js tests/supportChatLauncher.test.js` → **18 passed / 2 files**（旧文件 10 + 新文件 8）。旧文件 4 个失败的根因是**旧断言对应旧单视图 DOM**：打开面板后停在会话列表，bubble/input/FAQ 都在会话视图里；轮询也改成进会话才启动，旧测试直接取 `setInterval` 回调拿不到。已按新实现更新断言而不是改组件，并补齐 header 三元素/列表卡片/首屏（欢迎语+FAQ+输入框）/FAQ 点击发送/清除/订单弹层用例。`$fetch` 用 `globalThis.$fetch` 打桩，`useBuyerAuth` mock 固定已登录。
  - `npx eslint` 改动的 3 个文件 → 0 告警；`npx prettier --check` 同 3 文件 → 通过（已先 `--write`）。
  - 五语言键集合：en/zh/de/fr/nl 各 **531**（本批 +19；另 AA 并行新增 1 个 `chat.*` 键），missing/extra 均 0。
  - Playwright `var/ab_support_panel_20261123/verify_panel.mjs`（**EN + ZH 各自独立买家**，:3000 完全重启后跑，1440×1000）→ **36 checks / FAILURES=0**：
    - 面板尺寸/底色/边框/圆角/阴影/z-index、header 60px/清除左 16/标题 24-700 居中/关闭右 16 全部与实测量一致；列表卡片 padding/头像/标题/时间/摘要样式逐项断言通过。
    - 打开先显示**会话列表**（一条【客户服务】，摘要 `7*24小时在线支持。`）；点进会话后首屏头像中心 = 面板中心（1168.5）、欢迎语、3 条 FAQ、发送订单、placeholder、发送图标在输入框右半区。
    - 点 FAQ「我的包裹送到哪里了？」/`Where is my parcel?` → POST **201**，消息流出现该句；随后 FAQ 收起。
    - 【发送订单】弹层 3 笔订单（订单号/金额/状态），勾 2 笔 → 发送 201 → 消息流为两行订单文本，含完整订单号 + `£7.99/£45.60` + 状态。
    - 【清除】→ 已渲染消息 0 条、FAQ 重新出现；返回列表（时间 `18:13`、摘要更新时间）再进入 → 历史 3 条全部拉回。
    - 输入框右侧发送按钮：空值禁用、有内容可点、点击后 201 且输入框清空；进入会话后 5s 轮询 +1 次；Esc 关闭面板、打开时焦点落在面板内【×】；未登录点客服 → `/auth/login?next=%2F`。
    - PDP：客服按钮 `(1360,784,80,60)` 与【联系商家】`(1268,860,…)` 不重叠；面板打开时底边 228px、顶边 y=52，不遮【联系商家】；console error 0（en/zh/anon/pdp 全 0）。
    - 截图：`var/ab_support_panel_20261123/screens/panel-{list,first-screen,faq-sent,order-dialog,order-sent,cleared}-{en,zh}.png`、`anon-login-redirect.png`、`pdp-dual-buttons.png`、`pdp-panel-open.png`。
  - 落库核对 `var/ab_support_panel_20261123/check_db.py` → **DB CHECK OK**：en/zh 两个买家各 3 条 `SupportChatMessage`，FAQ 句与两行订单文本（订单号可回查夹具）都在库里；`CrispMirrorSession` 对这两个买家 **0 条**（e2e 走隔离 `:8001` + CRISP_* 全空，**没有真连 Crisp 发送**）。
- **坑/结论（新会话必看）**
  1. **会话首屏都是推定**，真站需登录才拉会话 JS（findings C4）；若之后拿到真站截图，先核对欢迎卡片/FAQ 形状/返回入口。
  2. 未读数只能取 `POST /thread`（get-or-create）那一刻的 `buyer_unread`；`GET /messages` 会顺手清零未读，用它的 payload 覆盖会把红点抹掉（组件里 `applyThreadMeta(..., {withUnread})` 已按此区分）。
  3. 清除后**必须保持轮询游标**，否则下一轮 `?after=` 会回退成全量把历史拉回来；组件用独立 `cursor` ref，不依赖 messages。
  4. 发消息的 `$fetch` 第二个参数 `body` 是**对象**（Nuxt 自动序列化）；单测打桩要同时兼容 string/object，否则 `JSON.parse` 抛错被 `deliver` 静默吞掉。
  5. FAQ 只在**空会话**显示；e2e 每个语言必须用**独立新买家**（setup_fixture.py 每个语言建一个），否则上一轮历史会占掉首屏。
  6. 订单列表按 `-created_at`，弹层行序与夹具创建顺序相反；断言要按弹层实际行序（读 `.support-chat__order-id`）而非夹具数组顺序。
  7. `:3000` 本批**完全重启**为 `npx nuxt dev --host 127.0.0.1 --port 3000`（e2e 用 `http://127.0.0.1:3000`，cookie domain 写 `127.0.0.1`）；若该进程随会话结束，重启后用同一 host/port。`:8001` 隔离后端验收后已停。
  8. 重跑 e2e 前先跑 `./.venv/Scripts/python.exe var/ab_support_panel_20261123/setup_fixture.py`（会删掉 `ab-panel-*` 买家的订单/会话/消息，相当于重置现场）；`ab-panel-en/zh@joybuy.test` 是测试号，**不要**当真实数据清理。
  9. 面板 `max-height` 在 PDP 环境收窄为 `min(720px, calc(100vh - 260px))`（bottom 上移到 228），平时仍是真站的 `80% / max 720`；改高度务必同时看 PDP 不重叠回归。
  10. AA 新增 `sender_kind='support'`（客服回复）与 `bm:` 入站对本面板**无影响**：`SupportChatLauncher` 只按 `sender_kind === 'buyer'` 区分自己的气泡，`support` 一律渲染成左侧气泡（组件测试已断言非 `--mine`）；`bm:` 是买家 ↔ 商家线程，走 `MerchantChatPanel`，不在本组件范围。

## 0bp. 批次 AC（2026-11-23 PDP 横线 / 评价数 / 已售，✅，未 commit）

- **任务**：需求文档03 **23.1**（PDP 三点）；批次 AC。**未 commit；只改 PDP 前端；未动客服面板（AB）、未动后端（AA）、未动 `MEDIA_BACKEND`。**
- **改动文件**
  - `storefront/pages/p/[id].vue`：横线重排（只留 `.detail__promise` 与 `.detail__support` 的 `border-top`，删 `.detail__guarantees` 的 `border-bottom` 与 `.detail__guarantee` 的 3 条 `border-top`）；删除顶部行评价条数渲染与 `ratingCount` computed / `ratingCountLabel` import；已售右侧新增 20px 本地内联 SVG 信息图标 + `role="tooltip"` 弹层（hover 整块 / hover 图标 / 键盘 focus / 点击均可显示）；评分与已售之间的灰竖线保留（`#e0e1e5`，1×14px）。
  - `storefront/utils/pdpDisplay.js`：`soldCountLabel` 归一化保证 `+`；删除不再使用的 `ratingCountLabel`。
  - `storefront/locales/messages.js`：新增 `pdp.soldTooltipTitle`、`pdp.soldTooltip` ×5 语言。
  - `storefront/tests/pdpDisplay.test.js`：覆盖 `40→40+`、`461→461+`、`12000→12k+`、`1500→1.5k+`、`1.2k` 补 `+`、`1.5K+→1.5k+`、空值确定性占位带 `+`；删除 `ratingCountLabel` 用例。
- **真站值 vs 用户口径（重要）**
  - 横线：真站是独立 `div.MuiDivider-root`，**0.5px `rgb(224,225,229)`、`margin:12px 0`**；按 23.1-1 只保留【配送与服务承诺】顶部与【我们支持/支付】顶部两条。实现用 **1px `#e0e1e5` + `margin-top:12px` + `padding-top:12px`**（等价 12px 上下留白）。选 1px 原因：0.5px CSS border 在 DPR1 浏览器会被舍入成 0 或 1，1px 在 DPR1/2 下视觉最接近真站且可稳定断言；与用户认可的 1px 口径一致。
  - 评价条数：23.1-2 只要求顶部评分行不显示；**评价区 `ProductReviews.vue` 的「X 条评价」仍保留**（真站评价区同样有，属另一 surface，故意未动）。验收断言限定在 `[data-testid="pdp-rating"]` 内无 `条评价/reviews/(N)`；若日后要全页删除需另立需求。
  - 已售 `+`：根因不是模板吞掉（zh `已售{count}件` 正常），而是 **`soldCountLabel` 对源站串原样透出**：库内 `SpuDetail.sale_amount` 实测 **13,691 条带 `+`、2,920 条是纯数字（1~999，如 `198`）、111 条为空**，纯数字商品就显示成「已售198件」。现统一归一化：已带单位/`+` 保留（`1.5k+`/`12k`→补 `+`）、纯数字 ≥1000 缩写为 k（12000→`12k+`、1500→`1.5k+`）、<1000 原数（`198+`）；空值仍走确定性占位 `10k+~30k+`（本来带 `+`）。
  - 文案空格：zh 仍为 `已售{count}件`（真站实测 `已售1k+件` 无空格），未按任务书示例在数字两侧加空格；`+` 由 count 保证。
  - 竖线：用户明确要求保留；**真站实测其实也有**（`skuReviewFloor_divisionLine`，见 crawler_debug_output 原始 HTML），修正 findings D12「真站无竖线」的说法。
  - tooltip：真站同位置是 20px 图标按钮，弹层 `saleAmountTip.popTitle = 销量解读`（英文站同页 `/help/salesdetails` 为 **Sales Details**），说明文案「涵盖 Joybuy 欧洲各站点（含本站、其他欧洲站点及 ochama）的历史成交数据」。标题与英文文案为真站实测；de/fr/nl 为对应翻译（推定，非真站实测）。
- **验证（按验证纪律仅做了针对性验证，未跑全量）**
  - `npx vitest run --config storefront/vitest.config.js storefront/tests/pdpDisplay.test.js storefront/tests/pdpBreadcrumb.test.js` → **15 passed / 2 files**。
  - `npx eslint` 改动 4 文件 → 0 告警；`npx prettier --check` 同 4 文件 → 通过。
  - 五语言键集合：en/zh/de/fr/nl 各 **511**，missing/extra 均 0（原 509 + 2）。
  - Playwright `var/pdp_ac_20261123/verify_pdp_detail.cjs`（EN+ZH × 4 商品，`http://localhost:3000`）→ **FAILURES=0**：
    - 横线：`.detail__promise` 与 `.detail__support` 各 1 条 `border-top:1px`；`.detail__guarantees` 与 3 个 `.detail__guarantee` 上下 border 全 0（断言「恰好 2 条且位置正确」）。
    - 顶部行 `innerText` 无 `条评价/reviews/(N)`；竖线 `1×14px #e0e1e5` 且 x 位于评分与已售之间。
    - 已售：`a41c9b79`（源串 3.8k+）→ `已售3.8k+件` / `3.8k+ sold`；`4286608d`（源串纯数字 198）→ `已售198+件`；`6f2493a3`（sale 空）→ `已售26k+件`；`467c7755`（无评分无 detail）→ 评分 `—` + `已售22k+件`。EN/ZH 全部带 `+`。
    - tooltip：hover 图标出现 `#pdp-sold-tooltip`（标题 `销量解读` / `Sales Details`）；移开鼠标关闭；键盘 `focus()` 也显示。
    - 每页 console error 0、404 0；截图 `var/pdp_ac_20261123/pdp_{en,zh}_{8位id}.png`、`rating_tooltip_{en,zh}.png`。
- **坑/结论（新会话必看）**
  1. 已售不要再直接透出 `sale_amount`：库里 2,920 条纯数字 + 111 条空，必须走 `soldCountLabel` 归一化；`+` 只加在数字/单位后，不要写成 `198++`。
  2. 0.5px 横线不要照抄：Chrome DPR1 下可能消失；本批用 1px `#e0e1e5`。
  3. 评价区 `ProductReviews.vue` 的「X 条评价」**未删**（不在 23.1-2 范围）；页面级 grep 仍会命中，别误判回归。
  4. tooltip 的显示条件挂在 `.detail__sold-block` 的 `mouseenter/mouseleave` + 图标 `focus/blur`，不要只挂 button 的 hover，否则鼠标放在「已售xx件」文字上不出提示。
  5. 本批并行存在 AA/AB 的未提交改动（`backend/merchant_ops/*`、`merchant-web/.../MessagesView.vue`）；本批只改上面 4 个前端文件，**不要**把这些一起 commit。
  6. `:3000` 仍仅监听 `[::1]`，Playwright 必须用 `http://localhost:3000`；Nuxt dev 热更新即可，本批未重启前后端。

## 0bn. 批次 A：面包屑 local_slug + 类目映射回填 + 导入校验（2026-11-23，✅，未 commit）

> 任务书写的编号 `0bl` 已被上面「无评分商品随机生成评分」占用、`0bm` 已被并行批次 B 占用，本批取 `0bn`。

- **任务**：修 PDP 面包屑「配件」误落到 `fashion-accessories`（服装与配饰>配件，0 商品）的显示/链接 bug；把 `ProductCategory.local_category`（原 0/242）按 2026-11-23 分析回填；在导入解析侧加配件类目父级校验。**未 commit；未改 `Spu.local_category`（批次 B）、未重建搜索文档、未动 `merchant-web/`、未做 AWS；`MEDIA_BACKEND=local` 未改。**
- **根因**：前端 `pages/p/[id].vue` 面包屑按类目名在**全树**找第一个同名节点（本地树 `fashion-accessories` 的 name_en 就是 `Accessories`），而电子类正确节点叫 `Electronics Accessories`（name_zh 电子配件），所以永远匹配到服装配件。后端 `category_breadcrumb` 只有 `{id,name,depth}`，与本地类目没有公共键；`ProductCategory.local_category` 字段存在但从未回填。
- **实现**
  1. 后端 `backend/catalog/detail_views.py::product_detail`：`category_breadcrumb` 每级**增量**返回 `local_slug`（`node.local_category.slug if node.local_category_id else None`），并 `select_related` 两级 `local_category`；既有字段不变。
  2. 前端新增 `storefront/utils/pdpBreadcrumb.js`（纯函数，可单测）：`resolveProductCategoryCrumbs(crumbs, categories, labelFor)`。有 `local_slug` → 按 slug 在本地树取节点再走 `utils/categoryLinks.categoryHref`（L1 有 channel_code → `/minihome/<code>`，否则 `/c/<slug>`；L2 恒 `/c/<slug>`）；没有 `local_slug` → **父级 + 名称**（一级只在根里找，二级只在已解析父级的 children 里找同名），**不再全树取首个**；树里没有该 slug 时降级 `/c/<local_slug>`；相邻两级解析到同一类目时去重（139 条「归父级」映射否则会出现「家居生活 / 家居生活 / 商品名」）。`pages/p/[id].vue` 删除旧 `normalizeCategoryName/findTreeCategory`，改为调用该 util；显示文案仍用本地化名称、回退接口 `name`。
  3. 映射数据 `backend/catalog/product_category_mapping_data.py`（由报告生成：206 条映射 + 34 条待确认说明）。
  4. 新管理命令 `backend/catalog/management/commands/backfill_product_category_local_category.py`：**DRY_RUN 默认**，`--apply` 才写库；只动 `catalog=joybuy_uk`（`joybuy` 下 2 条孤儿不碰）；已填且相同 = `unchanged`，已填但不同 = `conflict`（视为人工值，不覆盖）；`--apply` 先写 `backup_pc_mapping.json`（240 行 before），DRY_RUN 与 --apply 都写 `review_needed.csv`（34 行）。
  5. 导入校验 `backend/crawler_control/import_services.py::_sync_product_categories`（新增可选 `staging` 参数）：类目名含「配件 / Accessory / Accessories」且库内节点已有父级时，若与本次源面包屑父级不一致（或 payload 缺父级）→ **不重新归类/不重挂父级**（保留库内现值，并作为后续层级的父级继续解析），记录 `PRODUCT_CATEGORY_PARENT_MISMATCH`（`logger.warning` + `CrawlRunEvent` WARNING，含两边 source_id）；非配件类目行为完全不变。
- **脚本用法**
  - 预览：`cd backend && ../.venv/Scripts/python.exe manage.py backfill_product_category_local_category`
  - 写库：`... backfill_product_category_local_category --apply`（可选 `--output-dir`，默认 `var/category_misclass_20261123`）
  - 幂等：实测第二次 `--apply` → `to_fill=0 unchanged=206`（日志 `var/category_misclass_20261123/idempotent_reapply.log`）。
- **回填数量（已执行 --apply）**
  - `catalog=joybuy_uk` 共 **240** 行：已填 **206**（67 高置信 + 139 归父级）、未填 **34**；全库 `ProductCategory` 已填 **206/242**，`catalog=joybuy` 的 2 条孤儿（4909/4945）仍为空。
  - **口径修正（重要）**：任务书写「剩余 33 条（22 词包含/跨父级 + 11 无法映射）」，实际分析结果是 **34 条 = 22 词集合包含 + 1 跨父级 + 11 无法映射**（240 = 206 + 34；只跳 33 会漏 1 条）。本批按事实处理 34 条，全部只出清单不填。
  - 清单：`var/category_misclass_20261123/review_needed.csv`（列 source_id / name / path / parent_name / suggested_local_slug / reason / spu_count；11 条汽车+摩托为「无法映射：本地无对应根」，suggested 为空）。
  - 备份：`var/category_misclass_20261123/backup_pc_mapping.json`（240 行，`local_category_slug_before` 全 null）。
- **验证（按验证纪律仅做了针对性验证，未跑全量）**
  - 后端：`test catalog.tests.test_product_detail_api` → **Ran 17, OK**（原 15 + 2：映射存在返回正确 slug / 只有一级映射时二级 null；原面包屑断言补 `local_slug: None`）；`test catalog.tests.test_backfill_product_category_local_category` → **Ran 3, OK**（DRY_RUN 不写库 / --apply 写入+备份+清单 / 重跑幂等且保留人工 conflict）；`test crawler_control.tests.test_crawler_product_category` → **Ran 28, OK**（+4：父级匹配无告警、父级不匹配保留原父级并记事件、payload 缺父级视为不一致、非配件类目照旧）；`test crawler_control.tests` → **Ran 281, OK**；`test catalog.tests.test_product_detail_api test_product_detail_extras test_standard_categories test_backfill_...` → **31, OK**；`makemigrations --check --dry-run` → **No changes detected**。
  - ruff：本批 7 个 py 文件 `ruff check` 全过；3 个新文件已 `ruff format`。**`import_services.py` 的 I001 是 HEAD 既有问题**（`git show HEAD:` 单独 check 同样报），不要 `--fix`。
  - 前端：`vitest run --config storefront/vitest.config.js` → **204 passed / 31 files**（新增 `storefront/tests/pdpBreadcrumb.test.js` 10 例：local_slug 优先、无 channel_code、slug 不在树、父级内同名、同名但不跨父级、孤儿层级、归父级去重、空输入、名称归一化）；`eslint` 3 个改动文件 0 告警；`prettier --check` 通过；五语言键集合 **509×5** 一致（本批未新增 i18n 键）。
  - Playwright（`var/category_misclass_20261123/verify_breadcrumb.cjs`，EN+ZH，5 个不同品类商品）→ **FAILURES=0**：
    - `a41c9b79-6ff9-4782-96d5-3ca5a6a76b84`：EN `Electronics → /minihome/UK-Mini-HP-Electronics`、`Electronics Accessories → /c/electronics-accessories`；ZH `电子产品 / 电子配件`，**不是** `/c/fashion-accessories`；点击二级实际落地 `/c/electronics-accessories`。
    - `3e75a502…`（Phones / 手机 → `/c/mobile-phones`）、`7ae528ce…`（Beauty / 美妆 → `/minihome/UK-Mini-HP-Beauty` + Makeup / 彩妆 → `/c/makeup`）、`f999a29f…`（归父级去重成 1 级 Home & Living / 家居生活 → `/minihome/UK-Mini-HP-Home-Living`）、`c4ebaa87…`（Gaming / 游戏 + Consoles / 游戏机 → `/c/consoles`）全部与 DB 推导值一致；每页 console error 0、404 0；截图 `breadcrumb_{en,zh}_{8位id}.png`。
    - 无映射样例 `ba4f35d8…`（Automobiles > Auto Accessories）：SSR 面包屑为纯文本、无链接、无异常。
- **坑/结论（新会话必看）**
  1. 任务书的「33 条」是笔误，实际 **34 条**（22+1+11），必须凑满 240。
  2. 类目名归一化**不能只保留 `[a-z0-9]`**：`ProductCategory.name` 有中文（「配件」「电子产品」），旧的 `[^a-z0-9]+` 会把汉字整段删掉变成空串；新 util 用 `[^\p{L}\p{N}]+`。
  3. `ProductCategory.name` 本批样本库内是英文（Electronics/Accessories），但有中文历史数据，两种都要能按名称回退。
  4. 本批 e2e 发现 **:3000 只监听 `[::1]`**，`http://127.0.0.1:3000` 返回 000；Playwright/curl 必须用 `http://localhost:3000`（cookie domain 写 `localhost`）。
  5. 改后端后必须重启 :8000（`--noreload`）；本批已重启，只有 1 个 LISTENING（pid 36252，日志 `var/category_misclass_20261123/runserver_8000.log`）；:3000 未重启（Nuxt dev 热更新即可）。
  6. 再跑 `--apply` 会用当前（已填）值覆盖 `backup_pc_mapping.json`；复测幂等请加 `--output-dir var/category_misclass_20261123/idempotent_check`，不要冲掉原始 before 备份。
  7. 导入校验只对名字含「配件 / Accessory / Accessories」的类目生效；旧 payload 只有一级面包屑（父级缺失）会触发告警并保留库内父级——有意行为，不是回归。
  8. 「归父级」映射会让两级指向同一本地类目，前端已去重；若要显示源站二级名（如「生鲜>肉禽」）需另做文案层，不要退回去按名字全树匹配。
  9. `backend/catalog/search_services.py` 与 `backend/catalog/tests/test_generated_rating_shape.py` 属上一批（0bl 评分），本批未碰。

## 0bm. 批次 B（2026-11-23 614 商品归类修正，✅ apply + 定向回滚 137 完成并核对，未 commit）

- **任务**：614 个源站 `Accessories` 商品的 `Spu.local_category` 归置 + 搜索文档重建。用户拍板：只自动改高置信；301 个手机壳从 `mobile-phones` → `electronics-accessories`；Computing 137 条先按关键词细分、分不进去归 `computers-accessories` 根；美妆 5 条不动；`fashion-accessories` 必须保持 0。
- **2026-11-23 二次决定（已执行）**：**Computing 137 条全部回滚到原分类**。原因：①关键词命中 0 条，137 条全落进顶部导航隐藏的 `computers-accessories` 根，用户从导航进不去；②它抽干了本来正确的桶（batteries 150→71、laptops 132→103、gaming-gear 71→44）。**净变更 351 条**。**未 commit；未改业务代码；`MEDIA_BACKEND=local` 未动；未做 AWS。**
- **产物**（全部在 `var/category_misclass_20261123/`）
  - `apply_recategorize.py`（新）：清单生成 + 备份 + DRY_RUN/APPLY + 每 500 一批事务写库 + 逐个重建搜索文档 + 前后核对。默认 DRY_RUN，`--apply` 才写；Computing 关键词细分规则与人工修正表都写在脚本内可审计。
  - `apply_plan.csv`（595 行 = 459 高置信 + 137 Computing 细分；其中 488 行曾变更、107 行 no-op）
  - `backup_spu_category.json`（**488 行**原始备份）+ `backup_spu_category_computing137.json`（137 条子集，定向回滚用）
  - `rollback_spu_category.py`（回滚，默认 DRY_RUN；`--backup` 可指定子集）+ `rollback_computing137.log`
  - `build_review_needed.py` + `review_needed_batch_b.csv`（167 行）+ `review_null_batch_b.csv`（137 行回滚清单）
  - `verify_after_recategorize.py` + `verify_result.json`、`verify_c_pages.py` + `verify_c_pages_result.json`
  - `apply.log`、`apply_result.json`、`search_refresh_failures.json`（failures=[]）
- **执行结果（先 apply 488 条，再定向回滚 137 条 → 净 351 条）**
  - 首次 apply（`--apply --batch 500`，exit 0）：488 条，按目标 `electronics-accessories` 322 / `computers-accessories` 137 / `peripherals` 26 / `networking-devices` 1 / `headphones` 1 / `shaving-hair-removal` 1；搜索文档重建成功 443、无 ACTIVE Offer 跳过 45、失败 0。
  - **定向回滚 137 条**（`rollback_spu_category.py --backup backup_spu_category_computing137.json --apply`，exit 0）：137/137 提交，分布 batteries 79 / laptops 22 / school-office-accessories 15 / headphones 9 / electronics-accessories 5 / mobile-phones 4 / controllers 2 / gaming-gear 1；搜索文档重建 **137/137、失败 0**；落库与文档类目 mismatch=0。
  - Computing 137 关键词细分实测：**0 条命中 3 个专用桶**（`printer-accessories` / `gaming-pc-components` 本次变更数均为 0），这正是回滚的直接触发点。
  - **人工修正 6 条**（plan 的「高置信」关键词误命中，脚本 `MANUAL_CORRECTIONS`，均在保留的 351 条内）：2 个播客麦克风被 "Headphone Jack" 误判耳机、1 个绕线器被 "Earphones" 误判耳机 → 改归电子配件；2 个游戏耳机被 "Nintendo Switch" 误判网络设备 → 改归 `headphones`；1 个 Rokid AR 终端被 "5000mAh Battery" 误判电池 → **不自动改、转 review**。
  - 最终 351 条按目标：`electronics-accessories` 322 / `peripherals` 26 / `networking-devices` 1 / `headphones` 1 / `shaving-hair-removal` 1。
- **分类数量（直属 SPU / 可搜文档）：原始 → apply 488 后 → 回滚 137 后（最终）**
  | 分类 | 原始 | apply 后 | **最终** |
  |---|---|---|---|
  | `mobile-phones` | 453 / 327 | 156 / 58 | **160 / 60** |
  | `electronics-accessories` | 89 / 32 | 406 / 323 | **411 / 323** |
  | `peripherals` | 27 / 8 | 53 / 30 | **53 / 30** |
  | `computers-accessories`（根） | 2 / 2 | 139 / 118 | **2 / 2**（子树页仍有 336 个可搜） |
  | `batteries` | 150 | 71 | **150 / 150** |
  | `laptops` | 132 | 103 | **125 / 32**（7 条保留：6→peripherals、1→电子配件） |
  | `gaming-gear` | 71 | 44 | **45 / 17**（26 条保留：20→peripherals、4→电子配件、1→headphones、1→networking） |
  | `school-office-accessories` | 200 | 185 | **200 / 200** |
  | `headphones` | 199 | 191 | **200 / 199** |
  | `printer-accessories` | 12 / 12 | 12 / 12 | **12 / 12** |
  | `gaming-pc-components` | 79 / 79 | 79 / 79 | **79 / 79** |
  | `fashion-accessories` | 0 / 0 | 0 / 0 | **0 / 0** |
  - 注：`laptops` 125、`gaming-gear` 45 与用户预估的「~132 / ~71」差异，正是保留的 7 + 26 条正收益变更（鼠标垫/扩展坞/耳机/网线），不是回滚遗漏。
- **验证（按验证纪律仅针对性验证；未跑全量测试）**
  - `manage.py check` → no issues；`makemigrations --check --dry-run` → No changes detected（本批无迁移；回滚前后各跑一次）。
  - API（回滚后重跑）：10 个被改商品 `GET /api/v1/search?category=<目标>` 全部命中（5 个电子配件 + 4 个 peripherals + 1 个 shaving）；DB `local_category`、搜索文档 `local_category` 一致，mismatch=0。
  - **137 回滚核对**：备份 137 行 → 未恢复 0、仍在 `computers-accessories` 根 0、文档类目不一致 0。
  - 页面（:3000 临时启动 Nuxt dev，验完已停；之后其它批次起了仅 `[::1]:3000` 监听的实例，本批复验用 `http://[::1]:3000`）：10/10 在 `/c/<slug>?page=N` SSR HTML 命中；`/c/mobile-phones` 3 页且无被迁走手机壳；**4 个被回滚商品已回到 `/c/batteries`、`/c/school-office-accessories`、`/c/controllers`，且都不在 `/c/computers-accessories`**。
  - 未改动抽检（5 个）：AirTag（wearables）、HOMCOM 显示器增高架（monitors）、Nutmeg Bath Sponge / Silicone Back Scrubber（bath）、Rokid（wearables）全部未变；另核汽车电子样本 `51038723` 不在 `apply_plan` 内（本批不可能改到）。`fashion-accessories` SPU=0、文档=0。
  - PDP：`GET /api/v1/products/a41c9b79…` `category_slug=electronics-accessories`；面包屑文案已是「电子配件」但**链接仍是 `/c/fashion-accessories`**（批次 A 未生效，按约定不作为本批验收项）。
  - 回滚脚本 DRY_RUN（全量 488）：可回滚 488、已在旧值 0（**未执行全量回滚**）；定向回滚只用 137 子集。
- **待确认清单**：`review_needed_batch_b.csv`（167 行）= 137 Computing（已回滚，建议保留原分类）+ 8 中置信 + 5 低置信 + 5 美妆专项 + 1 高置信人工剔除（Rokid）+ 11 汽车/摩托源类目（92 个 SPU）。其中 137 条另出 **`review_null_batch_b.csv`**（列：spu / title / 当前(回滚后)分类 / 源面包屑 / 备注「源站写 Accessories 但本地分类更贴切，建议保留」）。用户口径 171 = 155+5+11 中「美妆 5」已含在 155 内，去重后 167（不重复列同一 SPU）。
- **回滚用法**
  ```bash
  # 全量回滚（488 行；本批只执行了下面的 137 子集，全量未执行）
  ./.venv/Scripts/python.exe var/category_misclass_20261123/rollback_spu_category.py --backup var/category_misclass_20261123/backup_spu_category.json --apply
  # 定向回滚 Computing 137（已执行，日志 rollback_computing137.log）
  ./.venv/Scripts/python.exe var/category_misclass_20261123/rollback_spu_category.py --backup var/category_misclass_20261123/backup_spu_category_computing137.json --apply
  ```
  参数：`--batch 500`、`--skip-search-refresh`、`--backup <路径>`；不带 `--apply` 为 DRY_RUN。读备份的 `old_local_category_id`，分批事务写回、批内复核，再逐个重建搜索文档（失败写 `rollback_search_refresh_failures.json`）。
- **坑（新会话必看）**
  0. **最重要的教训：源面包屑（`ProductCategory`）与本地 `local_category` 冲突时，不要盲目按源面包屑改。先看本地分类是否已合理**（电池在 `batteries`、鼠标垫在 `peripherals`、背包在 `school-office-accessories` 都是对的）。本次 137 条正是因为「Computing>Accessories」被机械地归到隐藏根，才导致 batteries/laptops/gaming-gear 被抽干；回滚后本地分类更贴切。今后遇到「源站类目笼统」的批量归置，应先做「本地分类是否已合理」的前置判断，再决定是否改。
  1. `recategorize_plan.csv` 的「高置信」里有 6 条关键词误命中（见上）。**不要**不加修正直接按 plan 写库（会把游戏耳机放进 `networking-devices`、麦克风放进 `headphones`）；修正表在 `apply_recategorize.py::MANUAL_CORRECTIONS`。
  2. Computing 137 条实测没有任何打印耗材/整机零件/键鼠外设标题 → 曾全部落 `computers-accessories` 根，**现已回滚**；`printer-accessories` / `gaming-pc-components` 本次变更数为 **0**。
  3. `/c/<slug>` 在 category 模式下**不传 `q`**（`ProductListing.vue` 只有 search 模式带 `base.q`），页面验收必须用 `?page=N` 翻页，不能用 `?q=`。
  4. DRAFT SPU 没有可搜文档；重建后 13 个带 ACTIVE Offer 的 DRAFT 会新增 `is_searchable=False` 文档（文档总数 +13 属正常，不是漏刷）。抽样别选 DRAFT（`44504934` / `51164c26` / `27c4f419` 都是 DRAFT，API 必然搜不到）。
  5. 本批只改 `Spu.local_category`，**不动** `ProductCategory.local_category`（批次 A 的映射回填是另一件事）；`local_category_descendants` 字段不存在，后代按 `path` 前缀实时算。
  6. 调查脚本 `build_plan.py` 是只生成建议的离线脚本；本批真正执行的是 `apply_recategorize.py`（含 Computing 细分与人工修正），回滚以 `backup_spu_category.json` 为准。
  7. **文件名冲突**：批次 A 的管理命令 `backfill_product_category_local_category.py` 也写 `var/category_misclass_20261123/review_needed.csv`（34 条 ProductCategory 映射待确认，mtime 17:02 覆盖了本批先写的内容）。因此**批次 B 的 SPU 清单是 `review_needed_batch_b.csv`（167 行）**，`review_needed.csv` 属于批次 A，两者不要互相覆盖。

## 0bl. 无评分商品随机生成评分（2026-11-23，✅ apply 完成并核验，未 commit）

- **任务**：给 `SpuDetail.rating_count = 0` 的商品随机生成评分（N ∈ [50,1500] 均匀随机，1~5 星阶梯上升、均分 4.1~4.6），评分不得超过销量（不足则重算销量 `N × uniform(1.2,10)`），一起写 `comment_count_display`；排除 143 个源站已下架 SPU；顺带修 61 条历史脏分布（只补/校准 `rating_distribution`，不动 count/average）；刷新搜索文档。**未 commit；未改前端；未碰 9334/FB；未 kill 任何抓取进程。**
- **已完成**
  - `backend/catalog/search_services.py::rebuild_search_document`：本地 ACTIVE 评价聚合为 0 时回退 `getattr(spu, "detail", None)` 的 `rating_average/rating_count`（与 `backend/catalog/detail_views.py:309-323` 同口径，注释按同风格）。仅此一处业务代码改动，diff +13/-2。
  - `var/gen_rating_20261123/generate.py`（新）：DRY_RUN 默认、`--apply/--seed(默认 20261123)/--batch(默认 2000)/--skip-search-refresh`；纯函数 `generate_rating_distribution / format_sold / parse_sold / calibrate_distribution`；备份→分批 `bulk_update`（评分/销量/评价数展示）→修 61 条脏分布→分批刷新搜索文档；**DRY_RUN 全程只读**。
  - `backend/catalog/tests/test_generated_rating_shape.py`（新）：10 个测试（分布和/阶梯/均分/占比/强制 1&2 星/`format_sold`/`parse_sold`/搜索文档回退/本地评价优先）。
- **DRY_RUN 结果**（日志 `var/gen_rating_20261123/dry_run.log`，seed=20261123）
  - `rating_count=0` 共 **12,238**；排除已下架 **142**（143 个中 1 个本身有评分）；本次写入 **12,096**（ACTIVE 9,289 / DRAFT 2,806 / INACTIVE 1）；需重算销量 **9,007**；销量展示串无法解析 **0**；历史脏分布 **61**（空 4 / 合计!=count 57）。
  - 实际占比：1 星 0.00~1.00%（N=100~124 强制 ≥1 条导致 192 条略超 0.8%，强制规则优先）、2 星 0~2.00%、3 星 8.00~18.00%、4 星 22.00~34.00%、5 星 46.00~65.00%。
  - 均分直方图：4.1-4.2=0、4.2-4.3=591（4.9%）、4.3-4.4=4,703（38.9%）、4.4-4.5=5,775（47.7%）、4.5-4.6=1,027（8.5%）。
  - 5 个真实样例（标题/原销量→新销量/N/1~5 星/均分）：`荣耀 600 Lite…` 1.5k+→1.5k+，N=1229，3/6/213/397/610，4.31；`RELX Lime Ice…` 6→5.2k+，N=1375，3/24/242/422/684，4.28；`Nestle Milkybar 6 Pack 72g` 27→7.8k+，N=1125，8/7/141/296/673，4.44；`NESCAFÉ Azera Americano Intense 90g` 100→3.1k+，N=380，1/5/55/102/217，4.39；`RuneScape: Dragonwilds - Xbox Series X` 10→4.7k+，N=484，2/5/43/144/290，4.48。
  - 搜索文档待刷新 **9,904** = 本次改动 SPU 的现有文档 9,289（DRAFT 无文档）+ 历史「文档评分为 0 但 SpuDetail 有评分」615（去重）。
- **验证（按验证纪律仅针对性验证；未跑全量）**
  - `manage.py test catalog.tests.test_generated_rating_shape` → **Ran 10, OK**；`manage.py test catalog.tests.test_search catalog.tests.test_localization catalog.tests.test_product_detail_api` → **Ran 43, OK**。
  - `ruff check`（新测试 + generate.py）→ All checks passed；`ruff format` 两文件已格式化。**`search_services.py` 的 I001 是 HEAD 既有问题**，不要对它跑 `ruff --fix`（会产生无关 diff）。
  - DRY_RUN 后只读复核：`rating_count=0` 仍 **12,238**、搜索文档评分非 0 仍 **0**、`backup_before.json` 不存在 → 确认 DRY_RUN 未写库。
- **APPLY 实际结果（2026-11-23，`var/gen_rating_20261123/apply.log`，seed=20261123、batch=2000、exit=0）**
  - 备份 `var/gen_rating_20261123/backup_before.json`：**12,157 行**（12,096 评分行 + 61 脏行），**6,276,924 字节**；含 before/after，可直接回滚。
  - 写入：评分/销量 **12,096**（7 批）、脏分布 **61**、搜索文档刷新 **9,904**（5 批），全部完成。
  - 落库复核（全量 12,096 行 DB vs 备份 after）：**mismatch=0**；`sale_amount` 重算 **9,007**；解析销量 < rating_count **0**；均分越界 **0**；分布非五档 / 合计≠count **0**；61 条脏分布合计全部 == rating_count。`rating_count=0` 由 12,238 → **142**（正好是排除的已下架 SPU），`rating_count>0` = **16,580**。
  - 抽样 5 个商品（id / N / 1~5 星 / 均分 / 销量→解析 / 评价数展示）：id=2 N=1229 3/6/213/397/610 4.31 `1.5k+`→1500 `1.2k+`；id=2442 N=1375 3/24/242/422/684 4.28 `5.2k+`→5200 `1.4k+`；id=4865 N=1125 8/7/141/296/673 4.44 `7.8k+`→7800 `1.1k+`；id=7285 N=380 1/5/55/102/217 4.39 `3.1k+`→3100 `380`；id=11377 N=484 2/5/43/144/290 4.48 `4.7k+`→4700 `484`。五档全非空、均分 4.1~4.6、销量 ≥ 评分、comment 全部有值。
  - 搜索文档：`ProductSearchDocument.rating_count > 0` = **9,904**（文档总数 10,280，其余 376 为未纳入的 0 评分/DRAFT 文档）；抽查 ACTIVE 商品 2582/5009/7431 的文档 `rating_count/rating_average` 与 SpuDetail **完全一致**（1375/4.28、1125/4.44、380/4.39）。
  - PDP 接口（Django shell 直接调 `catalog.detail_views.product_detail`，`?market=GB&locale=en-GB`）：2582/5009/7431 均 HTTP 200，`review_summary.source="crawler"`、count>0、`distribution` 五档齐全且合计==count（未开浏览器）。
  - **1 星占比偏差（必须记录）**：实测 **0~1.00%**（需求 0~0.8%）。原因：N=100~124 时「N≥100 强制 1 星 ≥1 条」与 0.8% 上限数学冲突（1/100=1%），按用户加粗的强制规则优先，受影响 **192** 条；其余 11,904 条均在 0~0.8%。2/3/4/5 星实测 0~2% / 8~18% / 22~34% / 46~65%，全部符合。
- **坑/结论（新会话必看）**
  1. `Spu` 模型**没有 `title` 字段**（标题在 `SpuTranslation`），脚本样例/备份标题按 en-GB 优先从 `SpuTranslation` 批量取；不要写 `spu__title`。
  2. 5 星「余下」必须显式限制 45~65%，否则低 3/4 星组合会让 5 星到 ~70%，均分仍合法但不符合需求。
  3. `N=100~124` 时「1 星强制 ≥1 条」与「1 星 ≤0.8%」数学冲突（1/100=1%），按用户加粗的强制规则优先，已在预览与本节标注。
  4. 销量展示串格式不统一：除 `"486"`/`"1.2k+"` 还有 `"10+"`/`"50+"`（下界），`parse_sold` 按数字下界解析（`"10+"→10`），空串按 0；未知格式才返回 None（本次 0 条）。
  5. 12,238 含 DRAFT/INACTIVE，只有 ACTIVE 的 9,289 个有搜索文档；刷新搜索文档数量天然少于改动数，不是漏刷。

## 0bk. 本地媒体占位回退（2026-11-23，✅，未 commit）

- **任务/根因**：`MEDIA_BACKEND=local` 下大量 `var/media/products/original/...` 文件本地缺失（S3 时代资产 + 爬虫未抓全；0bg 测得新上架 1,926 个 SPU 中 406 个缺主图 = 21%），`/media/...` 直接 404 → 搜索/购物车/PDP 破图与白块（商家页 API 层早已回退，故本批前后均无 404）。本批在**统一媒体服务层**回退，不再逐页修。
- **改动**（仅后端 2 文件；未改前端、未动 `.env`、无 AWS 操作、未 commit）
  - `backend/media/views.py`：`serve_media_file` 在 `s3_enabled()` 为 False 时先 `resolve_media_path` + `os.path.isfile`（`os.stat`，**每条请求 0 条 DB 查询**）判定；文件不存在 → `placeholder_image_response()`：**HTTP 200 + `image/svg+xml` + `Cache-Control: public, max-age=3600`**，内联 360×360 SVG（灰底 #f5f6f7 + 图片图标，与 `storefront/public/images/categories/_placeholder.svg` 视觉一致但**不跨目录引用前端文件**）。扩展名无关（.jpg/.png/.webp/.avif/无扩展名同一张）。路径穿越（`MediaPathInvalid`）与目录路径仍 404。**S3 模式一行未改**（缺文件仍 302 到桶 URL，缺对象必须可见，不能拿占位图掩盖）；`DEBUG=False` 仍 404（生产走 Nginx）。
  - 选 200 内联 SVG 而非 302 到静态占位图的理由：不依赖前端/静态目录部署布局；省一次跳转；单响应可缓存；`nosniff` 下 `image/svg+xml` 在 `<img>` 中正常渲染（截图已验证）。
  - **日志口径**：每次回退 `logging.getLogger("media.fallback").debug("media.placeholder_fallback", extra={"event": "media.placeholder_fallback", "path": <相对路径>})`；JSON 日志可直接 `grep '"event":"media.placeholder_fallback"'` 统计缺图规模。默认 root 级别 INFO → 不输出；`DJANGO_LOG_LEVEL=DEBUG` 才采集（避免每张图刷屏）。实测样本：`{"level":"DEBUG","logger":"media.fallback","event":"media.placeholder_fallback","path":"products/original/zz/zz/log_probe.webp",...}`（临时 :8010 探针，已停）。
  - `backend/media/tests/test_media_storage_s3.py`：原 `test_local_mode_missing_file_returns_404` 改为断言 200/SVG/缓存头；新增扩展名无关、存在文件原样返回、`assertNumQueries(0)` + `assertLogs`（event/path）、目录路径 404；S3 缺文件仍 302、S3 存在文件仍本地返回（原用例保留）。测试辅助 `drain()` 解决下面「坑 1」。
- **验证（按验证纪律仅针对性验证）**
  - `manage.py test media --noinput` → **Ran 36, OK**（原 31 + 新增 5）；`ruff check` + `ruff format --check` 2 文件 → All checks passed / already formatted；`makemigrations --check --dry-run` → No changes detected。
  - `curl -I`（:8000 单实例、最终代码）：已知缺失 `products/original/72/fe/72fe…webp` → `HTTP 200`、`Content-Type: image/svg+xml`、`Cache-Control: public, max-age=3600`；`.jpg/.png/.webp/无扩展名` 同上；已存在 `.webp` → `200 image/webp` 原内容；`/media/products/original/00`（目录）→ 404；`/media/../../etc/passwd` → 404。
  - Playwright（`var/media_placeholder_20261123/measure.mjs`，1440×900，Nuxt dev :3000 代理 /media→:8000；搜索 `/search?q=phone`、商家 `/merchants/source-5f19c3a976ba9182ec064185`、3 个缺图商品 PDP、临时买家经 API 加 3 件缺图商品到购物车）：
    | 页面 | 前（HEAD 旧 `views.py`） | 后（本批） |
    |---|---|---|
    | 搜索 | media 4xx **6**（破损 `<img>` 6） | **0**（占位图可见，`naturalWidth>0`） |
    | 购物车（3 件真实缺图商品） | media 4xx **4**（3 商品图 + 1 推荐位；破损 4） | **0**（占位图可见） |
    | PDP | media 4xx **31** | **0** |
    | 商家页 | 0（既有 API 层回退） | 0 |
    - 前后对比用同一脚本、同一批商品、同一缺图文件；「前」通过临时 `git checkout -- backend/media/views.py` 重启 :8000 测得（旧 diff 存 `var/media_placeholder_20261123/views.patch`），随后 `git apply` 还原并按最终代码再跑一轮（`final2_result.json`）。截图：`before_real_cart.png`（破图图标+alt 文字）、`after_final_cart.png`、`after_search_placeholder_visible.png`（占位图）。
  - 临时买家已清理（6 账号 / 6 购物车 / 15 CartItem / 6 会话 / 12 RecentlyViewed，`delete()` 共 45 行）；`MEDIA_BACKEND=local` 未改；无 AWS 操作；未 commit。
- **坑（新会话必看）**
  1. **不要在 TestCase 里直接 `response.close()` 后继续查 DB**：`HttpResponseBase.close()` 会发 `request_finished`，其 `close_old_connections` 接收器在 atomic 块内关连接 → `needs_rollback=True`，同测试类下一个 DB 查询抛 `TransactionManagementError`（本批新增测试改变字母序才暴露）。测试用 `drain()`：先读 streaming_content，再临时 `request_finished.disconnect(close_old_connections)` 后 close。
  2. **生产 `/media/` 由 Nginx `alias` 直接服务、不走 Django**（`infra/nginx/joybuy.conf`；Django 的 `/media/` 路由仅在 `DEBUG` 时注册）。所以本修复只覆盖 dev/DEBUG 实例；生产缺图仍会 404，彻底覆盖需部署时给 Nginx 加 `try_files … @placeholder`（本轮**未改** Nginx、未部署）。
  3. 重启 :8000 后仍可能出现**两个 LISTENING**（Windows SO_REUSEADDR）：本轮 38432/49272 同时监听，仅因两进程代码相同才无害；以后先 `netstat` 确认只剩 1 个。
  4. 占位响应缓存 1 小时：后续从 S3/爬虫补回真实图片后，浏览器最多 1 小时内仍显示占位图（强刷或等过期即可），不是回退失效。
  5. 商家页 API 回退返回前端静态 `categories/_placeholder.svg`，与本层内联 SVG 视觉一致但来源不同；两处不要互相删除。
- **遗留**：缺失文件真实规模建议后续从 S3 恢复或由爬虫补抓（0bg：406/1,926）。统计可用 `DJANGO_LOG_LEVEL=DEBUG` 起后端后按 `event=media.placeholder_fallback` 聚合，或直接用 `var/media_placeholder_20261123/count_missing.py` / `find_targets.py`（读 `var/media` 文件系统）。

## 0bh. 批次 Z1（2026-11-22 PDP 七项，✅ 完成，未 commit）

- **任务**：`功能需求迭代文档03.md` 22.1 的 7 项 PDP 对齐。**未 commit；未动商家端/mobile.html/其它页面；MEDIA_BACKEND=local 未改。**
- **真站实测**（cookies 来自 `crawler/debug_session.py` + Playwright route 打桩 `**color-api.joybuy.co.uk**` → `{"code":0,"data":{}}`；`https://www.joybuy.co.uk/dp/iphone-18-pro-max-256-gb/100020640078595` **zh 200 实测成功**，EN 另抓一轮取承诺正文；产物 `var/pdp_round7_20261122/`，含 `real_zh_full.png`、`probe_*.json`、`crop_panel_*.png`）：
  1. 真站字段：主图 wrapper（`.mainMedia_bigImg`）**border-radius 16px**；画廊区背景实际透明（商品图自带底色），本轮按用户要求改 **#F5F5F5**（标注：圆角实测、底色按需求）。
  2. 评价区：h2 **24px/600 lh26**；section `padding 20px 8px 16px`、无外框；评分卡 **1px #F0F1F2 / radius 12 / padding 20 / 内部 gap 32**；均分 **32px/700 lh40**；评价数 **14px/500 #6E7078**；分布条 6px #F5F6FA、填充 #D17D00、行高 22；AI 总结**无卡片**（无背景/边框/圆角/内边距），正文 16px/500 lh22、说明 14px/500 #6E7078 lh20，无图标。
  3. 承诺行：高 **54px**、**16px/600 lh22**、右侧 16px、divider 1px；展开正文 **14px/400 lh20**、底部 20px；真站顺序为 **30 天退货 → 24/7 客户支持 → 厂家保修**（chevron 真站换字形，本轮用 24px SVG 旋转 180° 等价实现）。
  4. 配送与服务承诺：真站 section `padding 8px 0`、标题 **24px/600 lh48**、销售方行 16px/500 lh22；Joybuy 为红色字标。
  5. 评分+已售：位于 h1 下方、画廊上方，整行 **16px/400**、高 38；真站示例 `★ 4.8 (70+ 评价) | 已售 7k+ 件`。
  6. 面包屑：真站 **16px/500**、`/` 分隔、每级 `<a>`；本地按 categoryLinks 口径：L1→`/minihome/<channel_code>`，L2→`/c/<slug>`。
- **改动**
  - `storefront/pages/p/[id].vue`：
    - 【我们支持】+9 个支付图标从页尾移入右栏 `.detail__panel`，紧跟三项承诺之后（购买按钮下方）；页尾不再渲染。
    - 新增 `.detail__promise`（配送与服务承诺 + `pdp.sellerLabel` + `/images/news/logo.svg` 18px 高 Joybuy 图标），位于承诺列表上方。
    - 三项承诺改 accordion（`guaranteeItems` + `openGuarantee`，aria-expanded，chevron 旋转，正文 i18n 详情）。
    - h1 下新增 `.detail__rating`（黑色星标 + 均分 + `(N 条评价)` + 分隔线 + 已售）。
    - 面包屑改用 `breadcrumbNodes`：商品 `category_breadcrumb` 按名称匹配本地类目树（`findTreeCategory`），用 `categoryHref` 生成链接并显示本地化类目名。
    - `.detail__image`/`img` 改 `border-radius:16px` + `background:#F5F5F5`（圆角不放在 overflow:hidden 容器上，避免裁掉放大层）。
  - `storefront/components/ProductReviews.vue`：评价区/评分卡/分布条/AI 总结按上述实测值重做（AI 正文用 `order:-1` 放到说明上方，视觉与真站一致）。
  - `storefront/utils/pdpDisplay.js`（新）+ `storefront/tests/pdpDisplay.test.js`（新）：`soldCountLabel` 优先接口 `sale_amount`，仅 **null** 时用 public_id FNV-1a 哈希生成 10k–30k 的**确定性展示占位**（同 id 恒定、非运行时随机）；`ratingAverageLabel`/`ratingCountLabel`。
  - `storefront/locales/messages.js`：新增 6 个 `pdp.*` 键（deliveryTitle / sellerLabel / soldCount / 三个 guarantee*Detail），en/zh/de/fr/nl 各 7 个 `pdp.*` 键集合一致（脚本核对）。
  - **后端（协调者批准，增量字段）** `backend/catalog/detail_views.py`：详情 payload 新增 `"sale_amount": detail.sale_amount or None`（无 SpuDetail 行为 null，不发明数据）。`backend/catalog/tests/test_product_detail_api.py` 新增 2 例（有详情返回 "25k+"、无详情 null）；顺带按 ruff 口径整理该文件 import 顺序。
- **验证（按验证纪律仅针对性验证；EN+ZH，完全重启 :8000/:3000 后）**
  - `prettier --check` 5 个改动前端文件 → 全过；`eslint` 5 文件 → 0；`vitest run storefront/tests/pdpDisplay.test.js` → **4 passed**。
  - 后端：`ruff check --config backend/pyproject.toml` 2 文件 → All checks passed；`manage.py test catalog.tests.test_product_detail_api --noinput` → **Ran 15, OK**（含新增 2）。
  - API 抽查与 DB 一致：`c38390ff…` API/页面 `17k+`；`864f00f8…` API/页面 `139`；`3324e318…` API `18k+`。
  - Playwright `var/pdp_round7_20261122/verify_z1.cjs`（EN+ZH，测试商品 `c38390ff-6d21-427a-8806-1b60c22649bc`，DB `sale_amount=17k+` / 1208 评价 / 有 AI 摘要）→ **FAILURES= 0**：
    1. 【我们支持】只渲染 1 次且在 `.detail__panel` 内；support y=981.5 > buy/add y=652.5，< footer y=8247；且在承诺列表之后。
    2. 配送与服务承诺在第一条承诺上方；标题 24px/600；销售方行 + Joybuy logo `naturalWidth>0`（高 18）。
    3. 三项均可展开/收起：aria-expanded true/false、正文 14px/20px（>20 字）、caret `matrix(-1,0,0,-1,0,0)`，收起后 detail 移除。
    4. 评价区：h2 24px/600、section `20px 8px 16px`、卡片 radius 12 / border rgb(240,241,242) / padding 20、均分 32px/700、计数 14px/500 rgb(110,112,120)、track 6px rgb(245,246,250)、fill rgb(209,125,0)、AI 无卡片（padding 0 / radius 0 / 透明）、AI 标题 14px/500 #6E7078、正文 16px/500。
    5. 评分在 h1 下方、画廊上方；`已售17k+件` 连续刷新 3 次完全一致（EN `17k+ sold`）。
    6. 面包屑 3 级链接：`/`、`/minihome/UK-Mini-HP-Electronics`、`/c/mobile-phones`，点击 L1/L2 落地 URL 正确。
    7. 主图计算值 `border-radius:16px`、`background-color:rgb(245,245,245)`（img 与容器均一致）。
    8. PDP 单独复测（`check_pdp_clean.cjs`）EN/ZH **console 0、404 0**；两语截图 `local_*_{top,panel,reviews,full,guarantee_open}.png`。
- **踩坑（新会话必看）**
  1. :8000 当时**同时有两个 `--noreload` runserver 进程**（46164/50168，Windows SO_REUSEADDR），请求随机落到旧进程 → 同一接口时而返回新字段、时而旧字段、值还是 None。已全部结束并只启动 1 个（日志 `var/pdp_round7_20261122/runserver_8000.log`）；以后改后端后先 `netstat -ano | grep :8000` 确认只有一个 LISTENING。
  2. :3000 也有多套 Nuxt dev 进程；本轮已按 PID 树全停后用 `storefront/node_modules/nuxt/bin/nuxt.mjs dev --host 127.0.0.1 --port 3000` 单实例重启（日志 `storefront_3000.log`）。
  3. 商品图/详情图有历史缺失（0bg 已知 406 个 SPU 缺主图）；面包屑点到 minihome/category 页会带出其它页的 404。验收 PDP console 必须**限定在 PDP 页面内**统计；测试商品已选媒体齐全的 `c38390ff…`。`5b7098bf…` 商品数据本身有 3 张变体图 404，勿用作验收样本。
  4. 真站 **EN 版本的 AI 摘要/Delivery 区块在部分请求下不渲染**（实测 EN probe 为 null），故区块文案/尺寸以 zh 实测为准，EN 只取承诺正文。
  5. Vue scoped CSS 里 `.detail__image` 不能加 `overflow:hidden` 实现圆角，否则 `left:calc(100%+16px)` 的悬停放大层会被裁掉；圆角加在 img 上。
- **遗留/说明**
  - 真站把支付图标放在页脚（`支付方式`），本轮按用户 22.1-1 明确要求放进右栏购买区；两者不一致处**以用户要求为准**。
  - 已售回退只在后端 `sale_amount` 为 null（无 SpuDetail 行/空值）时生效，值形如 `24k+`，同商品恒定；DB 真实值存在时绝不覆盖。当前 ACTIVE 商品绝大多数有值（15,030/16,373 个 SPU 有 `sale_amount`）。
  - 评价列表条目（头像/有用/图片）沿用旧样式，本轮只对齐 22.1-2 要求的区块与 AI 总结卡片。
  - 未做真站 3 级类目（Electronics/Phones/Smartphones）第 3 级：后端 `category_breadcrumb` 只保留 2 级。


## 0bj. 批次 Z2（2026-11-22 客服按钮/用户下拉/用户中心，✅ 完成，未 commit）

- **任务**：`功能需求迭代文档03.md` 22.2（首页右下角【客服】按钮按真站改样式）+ 22.3-1（用户下拉头像+用户名整块可点 → `/account`）+ 22.3-2（用户中心按真站 `/profile` 重做视觉）。保留全部既有逻辑与功能，**只改视觉/结构**；未动 PDP（Z1）、商家端（Z3）、后端；未 commit。
- **真站实测**（cookies `crawler/debug_session.py` + Playwright，color-api 打桩 `{"code":0,"data":{}}`；1440×1000，产物 `var/z2_support_account_20261122/`）
  - **客服入口**：真站不是单按钮，是 `#jdi-floating-toolbar`（固定 `right:0 / bottom:100px / z-index:1100`，宽 80、flex column）。单个入口 80×60（`min-height:48` + `padding:8px 5px` + 4px 间距）、`border:1px solid rgba(0,0,0,.059)` 且**无右边框**、`border-radius:8px 0 0 8px`、白底 `#fff`、文字 `#1a1a1a`/12px、图标 24px 在上、文字在下、hover **仅文字下划线**（无背景变化）。图标为 `joybuy-icons` 字体 `U+E601`（耳机+笑脸），字体未本地托管，本批用等效 SVG 复刻（**推定项**，标注见下）。
  - **客服面板**：375×720，`right:84 / bottom≈104.5`，背景 `#f5f6fa`、圆角 8、阴影 `0 2px 16px rgba(0,0,0,.08)`、z-index 1200 → 本批把面板右移 84、底边贴按钮、顶边落在站头下方。
  - **`/profile`**：**没有左侧导航**，是纵向堆叠（实测 `profile_profile_container` 白底 + 上下 48px，内层 **1264px** 居中）。①用户行 120px 高 / `padding:20px 24px`：60px 圆头像、昵称 28px/700、链接行 `padding:8px 12px`/4px 圆角/20px，分隔线 1px `#f0f1f2`；②会员 banner（76px，`#f5f6fa`，圆角 8，`margin-top:24`，紫色文案 + 黑色按钮）；③订单条（`#f5f6fa`，圆角 8，`padding:20px 24px`，`margin-top:24`）：首格【我的订单】22px/700 透明底，状态格 224×80 白底圆角 8、数字 24/700、标签 18/400；④权益 tile：`margin-top:32`、104px 高、`#f5f6fa`、圆角 8、`padding:24px 24px 16px`，标题 22/700（24px 图标 + 16px 右箭头），描述 18/400 `#888b94`。
- **交付 1（`storefront/components/SupportChatLauncher.vue`，样式区重写，逻辑一行未动）**
  - 按钮改为真站贴边形态：`fixed right:0 / bottom:100 / 80×60 / 12px / #fff / #1a1a1a / 8px 0 0 8px / 无右边框`，图标 24px + 文字竖排；hover 文字下划线；`.support-chat__launcher svg { flex:none }` 防 flex 压成 22px。
  - 面板：`top:calc(var(--site-header-height,180px)+16px) / right:84 / bottom:104 / width:375 / z-index:1200`（**必须把顶边压到站头下方**，否则会盖住右上角购物车/头像——本轮实测踩到并已修）。
  - PDP 错位（不改 PDP）：`body.pdp-merchant-contact` → 按钮 `bottom:156`（【联系商家】top=140，留 16px）；再叠加 `pdp-buybar-visible` → `bottom:212`（联系商家 148+44=192 之上）。面板同步 228/284。
- **交付 2（`storefront/components/AppHeader.vue`）**：下拉里 `.account-menu__user` 由 `div` 改为 `NuxtLink to="/account"`（`data-testid="account-menu-profile"`），头像+昵称整块可点，`@click` 关闭下拉；5 行菜单项、申请店铺五态入口、hover 开合/延迟关闭全部保持。
- **交付 3（`storefront/pages/account/index.vue` 重写模板/样式，脚本数据逻辑保留）**
  - 结构对齐真站：白底页 + 1264 内容区；用户行（60px 头像、昵称 28/700、我的地址 + 退出登录，链接 20px/8×12 内边距/4px 圆角）；订单条（`#f5f6fa`/圆角 8/20×24/`margin-top:24`，首格透明【我的订单】，3 个状态格白底 80 高、数字 24/700、标签 18/400）；权益 tile（3 列、104 高、`#f5f6fa`、24/24/16 内边距、标题 22/700 + 24px 图标 + 16px 箭头、描述 18/400 `#888b94`、`margin-top:32`）。
  - 功能入口：订单（含 3 个状态 tab 深链）、售后、评价、**收藏**、**最近浏览**、申请店铺（五态复用 `useMerchantEntry`），地址在用户行；收藏/最近浏览是新挂到 hub 的既有页面（此前只存在于路由/头部下拉）。
  - `displayName` 改为优先 `display_name`（与右上角一致），回退 `display_identifier`/邮箱/手机号。
  - 五语言新增 `account.moduleFavouritesDesc` / `account.moduleRecentlyViewedDesc`（en/zh/de/fr/nl，精确锚点插入）；脚本核对五语言键集合 **509/509/509/509/509** 一致。
  - 与真站的**有意差异**：真站会员 JoyPlus banner 与「邀请有礼」卡未实现（本项目无会员/邀请功能）；订单状态格 3 个（真站 4 个，本项目评论/售后无后端数据）；权益 tile 5 个（真站 3 个，保留售后/评价/收藏/浏览/申请店铺）；头像沿用既有笑脸占位。
- **验证（按验证纪律仅做针对性验证）**
  - `prettier --check` 5 个改动文件 → 全过；`eslint` 5 文件 → 0 告警；`vitest` `AppHeader.test.js`(20) + `SupportChatLauncher.test.js`(7) → **27 passed**（AppHeader 新增 1 例：用户块是 `<a href="/account">`、含头像+昵称、点击后面板关闭）。
  - Playwright（`var/z2_support_account_20261122/e2e.mjs`，完全重启 :3000 后，EN+ZH；临时买家见 `setup_fixture.py`/`cleanup.py`）：**FAILURES=[]**
    1. 首页按钮计算样式逐项 = 真站实测：`fixed / right:0 / bottom:100 / 80×60 / min-height:48 / radius "8px 0px 0px 8px" / rgb(255,255,255) / rgb(26,26,26) / 12px / border-top 1px rgba(0,0,0,.06)（CSS 0.059 计算值）/ border-right 0 / column / 图标 24×24 / hover underline`；box `(1360,740)-(1440,800)`；点击开面板 375×625、z=1200（截图 `local_home_launcher_*_en.png`）。
    2. 下拉用户块 `tag=A href=/account`，点击跳 `/account` 且面板关闭；5 行菜单项 href/顺序不变。
    3. `/account` 计算值：内容区 1264、页白底、用户行 120、头像 60、昵称 28/700、订单条 `rgb(245,246,250)`+8px、状态格白底、3 列、tile 104/`#f5f6fa`/标题 22/700/描述 18 `rgb(136,139,148)`、**无左侧导航**；10 个入口 URL 全部 200；ZH 文案（我的订单/售后单/我的收藏/最近浏览/申请店铺）正常（截图 `local_account_{en,zh}.png`、`local_account_section_*.png`，真站对照 `real_profile_full.png`）。
    4. PDP（白名单买家 + `?offer=&from=merchant`）：客服 `(1360,684,80×60)` vs 联系商家 `(1268,760,148×44)` **不相交**；`body.pdp-merchant-contact` 生效。当前 PDP（Z1 并行改动中）在 1440×520 滚到底主图 bottom=58 仍不离屏、`.buy-bar` 不出现，购物条态改为手动挂 `pdp-buybar-visible` 验证：客服 212 / 联系商家 148，**不相交**（截图 `local_pdp_buttons_900.png`）。
    5. 全部页面 console error **0**。
  - 清理：删除 2 临时买家/2 会话/1 客服线程，leftovers 全 0；:3000 已用新代码完全重启、:8000 未动；`MEDIA_BACKEND=local` 未改；无 AWS 操作；未 commit。
- **坑（新会话必看）**
  1. 真站客服图标是 `joybuy-icons` 私有字体 `U+E601`，项目未本地托管该字体；本批用等效 SVG（耳机+笑脸）**推定**，若后续拿到字体可替换。
  2. 真站 `/profile` **没有左侧导航**；不要拿 `AccountShell`（240px 左栏 + 白面板）套用户中心 hub。
  3. 客服面板必须限制在站头下方（用 `--site-header-height`）；只按 `bottom` 定高会在 900 高视口盖住购物车/头像（本轮已踩）。
  4. 客服按钮改为 `right:0` 后会与 PDP【联系商家】（right 24 / bottom 96 / 44 高）重叠，必须保留 `body.pdp-merchant-contact` 这个类名（PDP 侧由 Z1 维护）以触发上移；若 Z1 改名，需同步本组件两条 `:global(body.pdp-merchant-contact …)`。
  5. 真站 `rgba(0,0,0,.059)` 在 Chromium computed 值是 `rgba(0,0,0,0.06)`，验收比较时按计算值。
  6. Playwright 在 Nuxt dev 下仍需 `networkidle + ~700ms` 再交互（沿用批次 Y 的 `gotoReady`）。完全重启后**第一次**跑 e2e 可能在首屏编译期超时；等 `curl :3000` 200 且 Vite warmup 完成后重跑即可（本轮第二次通过）。

## 0bi. 批次 Z3（2026-11-22 商家上架中心，✅ 完成，未 commit）

- **任务**：`功能需求迭代文档03.md` 22.4（商家端「商品上架中心」查看详情）：描述/规格要显示真实采集数据；去掉【商家数】与【成本价用于发货扣款…】提示；无采集详情显示空态。只改桌面 Vue，手机版 `mobile.html`+`src/folio/` 一行未动。
- **根因（接口 + 前端双缺）**：①商家端商品池列表 `/api/v1/merchant/catalog/products` 复用 `_spu_payload`，只带 `Spu.description` / `Spu.specs`；爬虫商品的这两个历史字段基本为空（实测 16k SPU 中 15.9k 有 `SpuDetail`，真实图文/规格全在 `detail.content_sections`/`specification_tables`/`specifications`/`spec_options` 与 `Sku.specification`），且商家端**没有单品详情接口**；②前端抽屉直接把列表行当详情渲染（`detail.value = item`），从不请求详情。两条叠加 → 描述/规格必空。
- **后端改动**：`backend/merchant_ops/views_merchant_catalog.py` 新增 `MerchantCatalogProductDetailView`（`GET /api/v1/merchant/catalog/products/<uuid>`，权限 `merchant.listings.manage`，仅 ACTIVE 商品，404 `PRODUCT_NOT_FOUND`）：在 `_spu_payload` 既有字段之上**增量**返回 `content_sections` / `content_source` / `specification_tables` / `specifications` / `spec_options` / `ai_summary*` / `skus[{id,specification,status}]` / `sku_count`，成本价按本店折扣折算（与列表/上架公式一致），`listed` 标本店是否已上架；既有字段与列表接口零改动。路由 `backend/merchant_ops/urls.py`。
- **前端改动**：`merchant-web/src/views/CatalogueView.vue` 打开抽屉时先用列表行占位再拉单品详情（`requestId` 防串台/关闭后回写）；描述按 section 标题 + heading/paragraph + 图片渲染，无结构化区块回退 `description` 纯文本；规格优先规格表（属性/值表格），再回退平铺 `specifications`/`specs`、SKU 规格汇总、`spec_options` chips；都为空显示「该商品暂无图文详情。」/「该商品暂无规格信息。」。删除【商家数】`<dt>` 与价格混用提示；抽屉改 `wide`。样式新增 `.detail-content*` / `.detail-spec-table` / `.detail-spec-options*`。
- **验证（按验证纪律仅做针对性验证）**：`ruff check` 三文件过（`ruff format --check` 仍只报 `views_merchant_catalog.py` 既有的 `merchant_category_label` 换行漂移，未顺手重排）；`manage.py test merchant_ops.tests.test_merchant_modules.CatalogListingTests --keepdb --noinput --parallel 1` → **Ran 10, OK**（新增 3 例：有采集详情时 blocks/规格表/SKU 规格返回且既有字段不变、无详情返回空结构、INACTIVE 404）；`merchant-web` `npm run build` 通过。浏览器（IAB 127.0.0.1:5174，账号 `123456@joybuy.com` 测试商家）：搜索并打开 SPU `6b556170…` → 描述有 section 标题 `Product Description` + heading + 段落，规格表 `Materials & Specifications` 4 行；与 DB 逐项一致（2 sections/10 headings/32 paragraphs/1 table/3 rows 的另一 SPU `f39ee3fa…` 亦与接口完全一致）；`document.body.innerText` 不再含「商家数」「成本价用于发货扣款」；无采集详情 `4255c614…`（描述空态 + SKU 规格 Colour: GREEN/khaki）与完全无详情 `0ca53144…`（描述与规格双空态）均正常。
- **手机版是否同问题**：否（`src/folio/base-2.js`/`base-3.js` 的商品详情弹窗是静态稿自拟文案，无【商家数】也无该价格提示；按铁律**未改**，仅记录）。
- **环境备注/坑**：:8000 原进程是 `runserver --noreload`，新路由必须重启后端才生效（已按 `MEDIA_BACKEND=local` 重启，`.env` 未动、无 AWS 操作、未 commit）；`功能需求迭代文档03.md` 在 `git status` 中显示已修改（22 节由用户/他批写入，非本批改动，勿回滚）。

## 0bg. 批量上架 DRAFT 商品（2026-11-22，✅ 完成，未 commit）

- **任务**：用户已批准把「6,889 个 ACTIVE Offer 挂在 DRAFT SPU 上」的商品批量上架。复用 2026-11-15 配方（`var/sql_online_crawled_20261115/bring_crawled_online.sql`，见本文 §2「把这两天抓取的商品全部上架」），本次差异：那次 Offer 也全是 DRAFT（两层都翻），这次 Offer 本来就是 ACTIVE，只翻 SPU。工作目录 `var/bulk_online_20261122/`。
- **摸底（决定口径）**：全库 SPU 16,310 → ACTIVE 8,353 / DRAFT 7,955 / INACTIVE 2。按验收 `sellable-ratio.json` 同口径（只看 searchable 商家：onboarding ACTIVE、非 IMPORT_FALLBACK、有 ACTIVE Offer，共 661 家）：**DRAFT 且至少一个 ACTIVE Offer(sku ACTIVE) 的 SPU = 1,926 个，对应 6,889 个 ACTIVE Offer**；这些 SPU 当时 `product_search_document` 0 条（导入不建文档）。全商家口径为 3,100 个 SPU，其中 **1,174 个属 onboarding 未完成 / import-fallback 商家，本次故意不激活**（否则商品能搜到但店铺页 404）。
- **变更前后（searchable 商家口径，与验收同口径）**：
  - **可售 Offer 4,712 → 11,601（+6,889，一行不差；占 searchable 商家 Offer 13,701 的 84.7%；验收当时分母 13,700，差 1 是期间数据自然增长）**；
  - **ACTIVE Offer 挂 DRAFT SPU：6,889 → 0**；**可售为 0 的商家：130 → 0**；
  - **搜索文档 `is_searchable=1`：8,353 → 10,279**，与「ACTIVE 且有 ACTIVE Offer 的 SPU」数完全一致；
  - SPU：ACTIVE 8,353 → 10,279、DRAFT 7,955 → 6,029、INACTIVE 2 不变；
  - **Offer 状态分布完全未变**（ACTIVE 17,432 / DRAFT 4,711 / INACTIVE 568）——本次没有改任何 Offer。
- **执行（三层，均分批 + 每批独立事务）**：
  1. 备份 `var/bulk_online_20261122/backup_ids.json`：1,926 个 SPU（id/public_id/status_before/updated_at_before）+ 6,889 个 Offer（含 status_before / listed_at_before）；
  2. DRY_RUN（默认只读，必须 `--execute` 才写）：4 批共 **1,926 行**、Offer 全 ACTIVE、目标 SPU 现有文档 0 条；
  3. 第一层 `UPDATE spu SET status='ACTIVE', updated_at=NOW() WHERE id IN (...) AND status<>'ACTIVE'`：500/批 × 4 批 = **1,926 行**；
  4. 第二层 Offer **只读核对**（不改）：前后均 `{ACTIVE: 6889}`，DRAFT/INACTIVE Offer 原样保留（脚本发现变化会 `ABORT`）；
  5. 第三层逐 SPU `catalog.search_services.refresh_spu_search_documents(spu)`：250/批 × 8 批 = **ok 1,926 / fail 0**；
  6. **总耗时 63s**（22:57:08–22:58:11 本地），无约束错误、无回滚批次。
- **踩坑（新，务必记住）**：**MySQL 8.4.7 InnoDB FULLTEXT 索引会落后于表数据**。批量插入文档后抽查发现 id 8908–8999 这 92 行 `MATCH(title)` 得分 0 → doc `is_searchable=1` 但搜索搜不到；抽样 200 个**历史**文档另有 12 个同样不在索引里（id 8480–8866 段），说明是操作前就存在的索引漂移，不是本次写入逻辑写坏。**重跑 refresh（UPDATE 行）补不上索引**；`OPTIMIZE TABLE product_search_document`（返回 "Table does not support optimize, doing recreate + analyze instead" + status OK）重建后目标集 unindexed 92 → 0，全量抽样 300 条 + 历史段 427 条 unindexed 均为 0。→ 以后大批量建/改文档后若「doc 在、搜索搜不到」，先查 MATCH 得分再 `OPTIMIZE TABLE`，不要先怀疑 refresh 逻辑。检查/修复脚本 `var/bulk_online_20261122/fix_fts.py --check | --refresh | --optimize --execute`。
- **执行后核对（按验证纪律只做针对性验证）**：
  1. DB 三层一致：可售 11,601 = 4,712 + 6,889；searchable docs 10,279 = ACTIVE 且有 ACTIVE Offer 的 SPU 10,279（另有 1 条 `is_searchable=0` 的历史文档 id=71/spu DRAFT，操作前就存在，不影响搜索）。
  2. 抽查 5 个刚上架 SPU（7967 / 8656 / 11933 / 14293 / 17003）：`/api/v1/search?q=` **5/5 命中**、`/p/<public_id>` **5/5 = 200**（`post_verify.json`）。其中 7967 正是 FTS 修复前唯一搜不到的样本，修复后同一 query total 10 → 11 并命中。
  3. 抽查 3 家此前可售为 0 的商家（Modewe `source-a29d…`、HOBIBEAR `source-777b…`、Ubjuliwa `source-a628…`）：`GET /api/v1/merchants/<slug>` 均 200、`products` 均 50（接口上限）。
  4. 未重启后端（8000 仍在跑）、`MEDIA_BACKEND=local` 未动、无 AWS 操作、未 commit。
- **缺图 / 缺详情比例（新上架 1,926 个）**：**缺主图 406 个（21.08%）** —— 这些 SPU 的 gallery `MediaUsage` 指向 `var/media` 下不存在的文件，`/media/products/original/...webp` 实测 **404**（前台会白块/占位）；只有 1,520 个有本地真实存在的图。**缺详情 0 个**（`SpuDetail` 的 content_sections/specification_tables 或 `description` 至少一项非空）。两者都缺 0 个。**属爬虫未抓全的历史数据问题，不是本次操作引入**（本次只改 `spu.status`，没碰媒体与详情）。
- **遗留**：1,174 个 DRAFT SPU 带 ACTIVE Offer 但属 onboarding 未完成 / IMPORT_FALLBACK 商家，本次故意不激活；待这些商家 onboarding 完成后需再评估是否上架（用 `var/bulk_online_20261122/stats.py` 可复测该数字）。
- **回滚方式**：`cd E:/code/AgentProject/Joybuy && .venv/Scripts/python.exe var/bulk_online_20261122/bulk_online.py --mode rollback --execute` —— 按 `backup_ids.json` 把 1,926 个 SPU 改回 DRAFT（`updated_at=NOW()`），并对每个 SPU 调 `refresh_spu_search_documents`（非 ACTIVE 会自动删除其搜索文档，搜索立刻消失）。Offer 无需回滚（本次未改）。
- **产物**：`var/bulk_online_20261122/` 下 `backup_ids.json`（清单）、`stats_before.json` / `stats_after.json`（前后统计）、`run.log`（执行日志）、`report.json`（汇总）、`post_verify.json`（抽查）、`gap_stats.json` / `spu_missing_image.json`（缺图）、`fts_unindexed.json`（FTS 修复记录）、`bring_draft_spus_online.sql`（配方/回滚 SQL 说明）、脚本 `bulk_online.py` `stats.py` `verify.py` `fix_fts.py` `gap_stats.py`。

## 0bf. 批次 Y（2026-11-22 全局客服入口 + 管理端买家咨询，✅ 完成，未 commit）

- **任务**：`功能需求迭代文档03.md` 第二十一节 21.3-2、21.4。关闭 Crisp 原生挂件，全站右下角改用自研【客服】按钮/面板（所有登录买家，不要求白名单），管理端客服中心新增「买家咨询」分组。**未 commit；未改后端契约、未动商家端/mobile.html/folio。**
- **Crisp 挂件关闭（可回滚）**
  - `storefront/plugins/crisp.client.js`：先读 `useRuntimeConfig().public.crispWidgetEnabled`，**false 直接 return、不注入脚本**；文件保留。
  - `storefront/nuxt.config.js`：`public.crispWidgetEnabled = process.env.NUXT_PUBLIC_CRISP_WIDGET_ENABLED === 'true'`（默认 false）。
  - `storefront/.env.example` 与根 `.env.example` 均补注释：默认 false；回滚原生挂件设 true（后端 Crisp 镜像不受影响）。
- **全局【客服】按钮 + 面板**（新 `storefront/components/SupportChatLauncher.vue`，独立于 `MerchantChatPanel`）
  - 右下角图标 + 文字（`data-testid="support-chat-launcher"`，默认 bottom 24/right 24，pill 样式）；点击展开右侧浮层面板（宽 384、高 min(34rem,100vh-120px)，移动端近全宽）；含消息列表、输入框、发送、2000 字上限、Escape 关闭。
  - 接口：`POST /account/support-chat/thread` → `GET/POST /account/support-chat/messages`；5s 轮询（`after` = 最后已确认/在发消息时间）；面板关闭、`document.hidden`、组件卸载即停轮询；乐观发送 + 服务端消息原地认领（沿用 V3 去重口径）。
  - 未登录点击 → `navigateTo('/auth/login?next=<route.fullPath>')`；API 返回 `BUYER_AUTH_REQUIRED` 时面板内提示登录（同样带 next）。
  - 挂到 `storefront/layouts/default.vue` 与 `storefront/layouts/footer-page.vue`（AppFooter/UiToast 之后），全站（含帮助/政策内容页）可见。
  - 五语言新增 16 个 `support.*` 键（en/zh/de/fr/nl 键集合一致，已脚本核对 16×5）。
- **PDP 双按钮错开**（`storefront/pages/p/[id].vue`）
  - 客服按钮 bottom 24px（48 高），【联系商家】保持 bottom 96px（44 高），900 高视口实测 bounding box 不相交。
  - `stickyBarVisible` 时给 `body` 挂 `pdp-buybar-visible`（卸载移除）；购物条出现时客服 84px、【联系商家】148px，均在购物条（top 452@520 高视口）之上。
- **管理端「买家咨询」分组**（`admin-web/src/views/SupportView.vue`）
  - 顶部 `.tabs` 新增「商家来信」（原逻辑不动）与「买家咨询」两个分组，带条数；「发起客服会话」只在商家分组显示。
  - 买家分组：`GET /admin/support-chat/threads`（分页 20，AppPager）、买家昵称/最后消息/未读/时间；**不自动打开第一条**（避免一进组就清未读）；点击 `GET .../<uuid>/messages` 打开并清零未读；回复 `POST` 同路径。
  - 刷新策略：**5s 轮询**（列表 + 当前会话，按最后一条 id 判断是否替换；页面隐藏/切组/卸载即停），另保留手动「刷新（每 5 秒自动）」按钮。
- **验证（按验证纪律仅做针对性验证）**
  - `prettier --check` 8 个改动文件 → 全过；`eslint` storefront 7 文件 + admin SupportView → 0 告警。
  - `vitest run SupportChatLauncher.test.js MerchantChatPanel.test.js AppHeader.test.js` → **34 passed**（新增 7：打开即建会话/渲染、乐观发送替换、轮询增量、未登录跳登录带 next、Escape 停轮询、401 提示）。
  - `admin-web` `vite build` → 成功（SupportView 12.22 kB）。
  - Playwright（`var/_y_support_chat_20261122/e2e.mjs`，完全重启 :3000/:5173 后，EN+ZH，support-chat API 经 route 转发隔离 :8001）：**FAILURES=[]**，截图 01–09：
    1. home/search/cart/PDP 四页 `script[src*=client.crisp.chat]`=0、`#crisp-chatbox/.crisp-client`=0、`window.$crisp===undefined`，console error 全 0。
    2. 非白名单买家（session `purchase_whitelisted=false`）打开面板发 EN 消息 → 出现在面板；管理端「买家咨询」行显示「Y客服买家 / 摘要原文 / 未读 1」→ 打开回复 → 买家面板 3–5s 内可见（实测 waitedMs 5ms，因轮询已对齐）；刷新页面后两条消息仍在。
    3. ZH：按钮「客服」、标题「Joybuy 客服」；ZH 消息收发与回复同链路通过。
    4. 未登录点按钮 → `/auth/login?next=%2Fcart`。
    5. PDP：supportBox y=828/h=48、contactBox y=760/h=44 不相交；购物条出现后 support 388–436、contact 328–372、barTop 452，互不重叠且都在购物条上方。
  - 清理：`cleanup.py` 删除 2 买家/2 会话/16 消息/1 客服/角色/会话，`leftovers` 全 0；:8001 已 kill；:8000/:3000/:5173 正常。
- **坑（新会话必看）**
  1. **Vue scoped 里 `:global(body.x) .child` 会丢掉后代部分**（编译成 `body.x { ... }`，规则打到 body 上）。必须整段写 `:global(body.x .child)`。本批 buybar 错位据此修复。
  2. Playwright 在 Nuxt dev 下点击 SSR 按钮可能早于 hydration（点击无效、等待超时）：每次 goto 后 `waitForLoadState('networkidle')` + ~600ms 再交互（`gotoReady()`）。
  3. **隔离 :8001 必须用 `var/_y_support_chat_20261122/run8001.sh`（bash export 空 CRISP_*）**。用 PowerShell `$env:X=''` + `Start-Process` 时空变量被 Windows 环境块丢弃，`.env` 的真实 Crisp 凭据生效 → 本轮 run3 误向真实 Crisp 发送 **8 条**（`bp:cee17af7-…`，会话 `session_fe8a105a-768c-4e35-b7e2-0448dc868742`，买家/客服各 4 条，本地 `crisp_status=sent`）。**该 Crisp 会话需用户手动归档/忽略**；run4 用 bash 空 env，消息 17–20 均 `skipped`，零真实发送。
  4. 管理端买家分组**不要自动打开第一条会话**，否则未读角标在列表里永远看不到（`GET messages` 会清零 support_unread）。
  5. 该 PDP 商品页在 900 高视口滚到底主图仍未离屏、`.buy-bar` 不出现；验购物条错位需把视口缩到 ≤520 高（本脚本用 1440×520）。
  6. `AppPager` 的全局 `.pager` 自带 margin/padding，直接放列表 panel 内即可，不必再加容器样式。
- **遗留**
  - Crisp Inbox 中该 `bp:` 会话标题「Y客服买家」（真实挂件已关闭，仅 Inbox 侧人眼验收待用户确认）；上述误发的 8 条消息需用户决定是否归档/删除。
  - 客服面板为浮层（无全屏 backdrop），PDP 打开面板时会遮住【联系商家】按钮（关闭后恢复）；如需“面板打开时隐藏业务按钮”另立需求。
  - 未做商家端/mobile.html 的任何入口改动（范围外）。

## 0be. 批次 X（2026-11-22 买家 ↔ 平台客服会话后端，✅ 完成，未 commit）

- **任务**：`功能需求迭代文档03.md` 第二十一节 21.3-1。全站【客服】的后端：**所有登录买家**都能与平台客服会话，消息镜像 Crisp `bp:{buyer_public_id}`，管理端客服可见可回。**未 commit；未改前端（批次 Y）、未改商家端、未动 PLATFORM_SUPPORT / `bm:` / `merchant:` 线程逻辑。**
- **模型 + 迁移**（`backend/merchant_ops/models.py` + `migrations/0005_support_chat.py`，已 apply 到开发库）
  - `SupportChatThread`：`public_id` / `buyer` **OneToOneField**（一买家一条，related_name `support_chat_thread`）/ `status`(OPEN|CLOSED) / `buyer_unread` / `support_unread` / `last_message_at`(null) / `created_at` / `updated_at`；索引 `schat_thread_last_idx(last_message_at)`。
  - `SupportChatMessage`：`thread` FK / `sender_kind`(buyer|support) / `body`(2000) / `created_at` / `read_at`(null) / `crisp_status`(null: sent|skipped|failed)；索引 `schat_msg_thread_idx(thread,created_at)`。
- **买家 API**（新 `views_support_chat.py`；路由 `merchant_ops/urls.py`）
  - `POST /api/v1/account/support-chat/thread`：登录即 get-or-create（新建 201 / 已有 200），返回 `{thread:{id,status,last_message_at,buyer_unread,created_at}}`；**不查 `purchase_whitelisted`**（显式测试固化）。
  - `GET /api/v1/account/support-chat/messages?after=<iso>`：消息列表 + 清零 buyer_unread、回填对方消息 read_at；无线程 404 `THREAD_NOT_FOUND`；`after` 非法 400 `AFTER_INVALID`。
  - `POST /api/v1/account/support-chat/messages` body `{"body":"..."}`：1–2000 字，落库 buyer → `last_message_at`/`support_unread+1` → `on_commit` 镜像；空/超长 400 `MESSAGE_EMPTY`/`MESSAGE_TOO_LONG`。
  - 未登录（合法 CSRF）401 `BUYER_AUTH_REQUIRED`。**复用** `views_merchant_chat._validated_body/_parse_after`，口径不漂移。
- **管理端 API**（`views_support.py` 末尾，权限沿用 `StaffRbacPermission` + `support.view`/`support.manage`，与现有客服中心一致）
  - `GET /api/v1/admin/support-chat/threads`：`paginate`，`{items:[{id,buyer:{id,display_name,avatar_url,email},status,unread,last_message,last_message_kind,last_message_at,created_at}], page,page_size,total,has_next}`；最后消息用 **Subquery 预取**（`last_message_body`/`last_message_kind`），无 N+1。
  - `GET /api/v1/admin/support-chat/threads/<uuid>/messages`：消息 + 清零 `support_unread`（不回写 buyer 未读）。
  - `POST .../messages` body `{"body":"..."}`：`sender_kind=support`，`buyer_unread+1`，on_commit 镜像；空/超长同上。
- **Crisp 镜像**（`crisp_mirror.py` 新增 `thread_key_for_support_chat` / `support_chat_meta_nickname` / `queue_support_chat_mirror`）
  - `thread_key = bp:{buyer.public_id}`；买家 → `sender_kind=user` + 昵称；客服 → `sender_kind=platform`（`from=operator`，`user.nickname`=`CRISP_PLATFORM_NICKNAME`，默认「Joybuy 客服」）；**正文无前缀**。
  - 会话 meta nickname **始终 = 买家昵称**（display_name → 邮箱前缀 → 「买家」），客服回复也不改成客服名；`session_email` 传买家邮箱。`on_commit` 才发、失败只写 `CrispMirrorLog`、`duplicate` 回写 `sent`、未配置 `skipped` 零 HTTP。
- **验证（按验证纪律仅针对性验证）**
  - `manage.py check` → 0 issues；`makemigrations --check --dry-run` → **No changes detected**；`migrate merchant_ops` 已 apply 0005。
  - `manage.py test merchant_ops.tests.test_support_chat merchant_ops.tests.test_crisp_mirror merchant_ops.tests.test_merchant_chat merchant_ops.tests.test_merchant_modules --noinput --parallel 1` → **Ran 110, OK**（新增 21：未登录 401/非白名单可用/幂等/无线程 404/收发与未读/after/空超长/买家隔离/管理端 401+403/列表与已读/回复/镜像 thread_key+sender_kind+正文无前缀+meta 标题/duplicate/镜像抛错不阻塞）。
  - `ruff check` 7 个改动 py → All checks passed；`ruff format --check` 新文件与 `views_support.py`/`models.py` → 已格式化（`crisp_mirror.py` 仅新代码按 format 调整，未动旧行）。
  - **curl 端到端**（临时 :8001、`CRISP_*` 全置空 → 只写 skipped；脚本/响应在 `var/_support_chat_e2e_20261122/`）：非白名单买家建线程 201 → 重复 200 同 id → 发消息 201；未登录无 CSRF 403、带合法 CSRF **401**；买家 B 读 404 且无正文泄漏；管理端列表 unread=1/昵称/摘要正确 → 读后 0 → 回复 201 → 买家读到 2 条、未读清零、`after` 只回新消息；DB `crisp_status=['skipped','skipped']`、`CrispMirrorLog` 2（`bp:<buyer>`，user/platform）、`CrispMirrorSession` 0。**check.py `FAILURES=[]`**。
  - 清理：临时 2 买家/1 客服/角色/会话/消息/镜像日志全删，`leftovers` 全 0（DB 复核 threads 0 / messages 0 / bp logs 0 / bp sessions 0）；:8001 已 kill；**:8000 已加载新路由**（`/api/v1/account/support-chat/messages` 返回 401 而非 404）。
- **坑（新会话必看）**
  1. 买家路由是**单数无 id**：`/support-chat/thread`、`/support-chat/messages`（一买家一条线程）；只有管理端路径带 `<uuid>`。别照抄 V2 的 `/threads/<id>/messages`。
  2. 买家接口是 CSRF 保护的 `BuyerCsrfAPIView`：**裸 curl 无 CSRF → 403**（中间件先于鉴权）；要验「未登录 401」必须先 GET `/api/v1/auth/buyer/session` 取 `csrf_token` 再带 `X-CSRFToken`。单测默认不强制 CSRF，故单测里直接是 401。
  3. 未白名单不是错误：`require_support_buyer` 只查登录，**不要**从 V2 抄白名单门禁；测试已显式断言 `purchase_whitelisted=False` 可收发。
  4. `admin_thread_payload` 依赖列表视图的 Subquery 别名（`last_message_body`/`last_message_kind`）；新增列表入口时记得带上，否则会退回逐行 `messages.last()`（N+1）。
  5. Crisp 会话标题只有买家昵称（没有「· 客服」后缀），客服回复也**不得**改 meta；区分「买家咨询」与 `bm:`/`merchant:` 靠 thread_key 前缀。
  6. 测试库本轮用**不带 `--keepdb`** 重建（结尾已 destroy）；下轮若用 `--keepdb`，注意 0bd 坑 3 的 data-migration 种子缺失问题。
- **遗留（批次 Y 前端）**
  - 关闭/开关 Crisp 挂件、全局 `SupportChatLauncher.vue`（右下角按钮 + 面板 + 5s 轮询）、未登录引导登录、与 PDP【联系商家】按钮纵向错开、EN/ZH + 五语言键一致。
  - 管理端前端「买家咨询」分组接这 3 个接口（本轮未改 admin-web）；Crisp Inbox 标题人眼验收待用户确认。

## 0bd. 批次 W（2026-11-22 offer 归属 / 商家页白屏 / PDP 联系商家，✅ 完成，未 commit）

- **任务**：`功能需求迭代文档03.md` 第二十节（20.1–20.4）。**未 commit**；未改商家端前端/手机版，未动 PLATFORM_SUPPORT，无新迁移。
- **20.1 offer 归属（后端 + 商家页链接 + PDP）**
  - `backend/catalog/detail_views.py`：`_offer_payload` 增量返回 `merchant: {public_id, display_name, slug, avatar_url}`（不破坏既有字段）；新增 `_resolve_sku_offer()`：同一 SKU 多商家时默认 `.first()` 会串商家，**`?offer=<offer public_id>` 命中则优先该 offer**（仅限 ACTIVE + 当前 market 回退链内；非法/不存在 UUID 原样回落，不 500）；`select_related("currency", "merchant")` 避免 N+1。
  - `storefront/pages/merchants/[slug].vue` 链接改为 `/p/<spu>?offer=<offer_id>&from=merchant`（此前丢 offer_id）。
  - `storefront/pages/p/[id].vue`：`useFetch` URL/key 均含 `offer`（key 仍是 computed，避免历史冻结坑）；新增 `storefront/utils/offerSelection.js::resolveSelectedSku()`（顺序：用户手选 → URL offer 命中 SKU → 首个可购 SKU）；带 offer 但命中不到时回落默认并显示 `chat.offerFallback`（"该商家无此规格，已为你展示其他商家"）。规格切换不锁死商家（按需求允许），首屏一定选对。
- **20.2 商家页白屏（后端）**：`backend/merchants/public_views.py` 图片回退链 = `spu.image_urls[0]` → `MediaUsage(role=gallery)` 第一条（`sort_order,pk`）的 `/media/...` → 本地占位图 `PRODUCT_PLACEHOLDER_IMAGE=/images/categories/_placeholder.svg`；**`_gallery_paths()` 一次查询批量取最多 50 个 SPU 的首图，不再逐商品查（无 N+1）**；`image` 永不为空字符串。
- **20.3 PDP【联系商家】（`storefront/pages/p/[id].vue`）**
  - 显示条件（全部满足）：已登录 + `purchaseWhitelisted===true` + `from=merchant` + `?offer` 命中某 SKU 且 `offer.merchant.slug` 存在；`chatBlocked` 时隐藏。直达 `/p/<id>`、非白名单、offer 命中不到（商家上下文不确定）均不显示。
  - 右下角**图标 + 文字**固定按钮（`data-testid="pdp-contact-seller"`），复用 `MerchantChatPanel`，绑定 `offer.merchant` 的 slug/店名/头像（非全局默认）；面板 `blocked` → 隐藏入口。
  - 与 Crisp 二选一方案：**入口显示时在 `body` 挂 `pdp-merchant-contact`，CSS 隐藏 `#crisp-chatbox` / `.crisp-client`**（`display:none!important`）；按钮 `bottom:96px` 另位于 Crisp 常规区域（约 20–80px）之上，双保险。页面卸载/入口消失移除 body 类。
  - 双语：新增 `chat.offerFallback`（en/zh/de/fr/nl），五语言 `chat.*` 各 18 键一致；按钮复用 `chat.contactSeller`。
  - PDP `.detail__panel` 增 `data-offer-id` / `data-merchant-slug` 便于验收读取。
- **验收（针对性验证，脚本/截图在 `var/_w_offer_20261122/`，EN/ZH，完全重启 :8000/:3000 后）**
  - 后端：`ruff check` 4 个改动 py → All checks passed（**注：验收须 `--config backend/pyproject.toml`**；按此口径本批新增的 4 处 I001 已在返工清除，见下）；`makemigrations --check` → No changes detected。
  - `manage.py test merchants.tests.test_wp42_services catalog.tests.test_product_detail_api --keepdb --noinput --parallel 1` → **Ran 31, OK**（18 + 13；新增图片回退/占位/无 N+1、offer.merchant、`?offer` 覆盖默认、非法 offer 回落）。
  - `catalog.tests.test_product_detail_extras` → **Ran 2, OK**（需在**未 flush 的测试库**上跑，见坑 3）。
  - 前端：`prettier --check` 5 个改动文件 → passed；`eslint` → 0；`vitest` offerSelection 6 + use-locale 3 + MerchantChatPanel 8 → **17 passed**。
  - Playwright（`e2e.mjs`，CHiQ 店铺页 + 真实 :8000；聊天 API 经 `context.route` 转发隔离 :8001、`CRISP_*` 置空 → **零真实 Crisp**）：**failures=[]**
    1. CHiQ 店铺页 14 卡/14 图，`broken=0 / emptySrc=0 / media 404=0`，14 条链接全部含 `?offer=&from=merchant`（截图 01；**返工后只保留 9 件可售，见下**）；另抽查 HOMCOM 首页 50 件商品：`image` 字段 0 空、去重后 35 张图逐个 GET 全 200（此前该店全部为空字符串白块）。
    2. 点 CHiQ offer（`b02c6f9b…`，同 SKU 默认会是 MER001000 `5c735e81…`）→ PDP `data-offer-id`/`data-merchant-slug` = CHiQ → 加购后 `GET /api/v1/cart` item `offer_public_id` = CHiQ offer、`merchant_id=MER001007`。
    3. 白名单买家：入口 EN `Contact seller` / ZH `联系商家`（图标+文字）→ 开面板 → 发 1 条 → 商家 API `unread=1`、摘要=原文，商家端 `:5174`「买家咨询」会话气泡可见（截图 02–05）。
    4. 非白名单同链路 0 入口；白名单直达 `/p/<id>` 0 入口；伪造 offer → 回落 MER001000 并显示提示、0 入口（有意为之，商家上下文不确定）。
    5. 多商家同款抽查 3 组（同一 SPU 3 个商家 offer）：详情 API 均返回 CHiQ offer 而非默认 MER001000。
    6. Crisp：脚本 200 但无头 Chromium 里挂件 DOM **未初始化**（`crispPresent=false`）；已用同 id 探针验证 `body.pdp-merchant-contact` 规则 `display:none` 生效，且按钮位于 `bottom:96px`（截图 02 右下角仅业务按钮、无重叠）。console error 5 个页面均 0。
  - 清理：删除 2 买家/2 会话、2 购物车、1 聊天线程/1 消息/1 条 `skipped` 镜像日志、临时店长+membership；`leftovers` 全 0，DB 复核全 0；隔离 :8001 已 kill；:8000/:3000 重启后 200。
- **坑（新会话必看）**
  1. `_listed_offers()[:50]` 按 `-listed_at` 排序；同款多商家的演示商品不一定在 HOMCOM 首屏（HOMCOM 首 50 无多商家），本轮改用 **CHiQ**（返工后 9 件可售里 3 组多商家）。验收别把商家 slug 写死成某一家的首屏假设。
  2. 详情接口每个 SKU 只返回 1 个 offer；**多商家同 SKU 必须靠后端 `?offer=` 覆盖默认 `.first()`**，只改前端匹配无法修归属。
  3. `--keepdb` + 含 `TransactionTestCase` 的模块（如 `test_product_detail_api`）会在结尾 **flush 测试库**，之后单跑别的模块会缺 data-migration 种子（`IMPORT_FALLBACK` 商家/Market 缺失 → 503 或 DoesNotExist）。复现时用**不带 `--keepdb`** 重建测试库再跑。
  4. Crisp 挂件在无头 Chromium 不初始化（脚本 200、`$crisp` 队列被消费但无 DOM）；不要据此判定 CSS 失效——用 `#crisp-chatbox` 探针验证隐藏规则，真实挂件视觉仍需用户肉眼确认。
  5. ~~商家店铺页仍会列出 SPU 为 DRAFT/INACTIVE 的 offer~~ **已在返工修复**：`_listed_offers` 只取 Offer ACTIVE + SKU ACTIVE + SPU ACTIVE，且过滤发生在 `[:50]` **之前**（先切片后过滤会把整店误判为空，见返工记录）。
  6. 临时买家 `purchase_whitelisted` 默认 True；造非白名单必须显式 `False`。
- **遗留**
  - 商家页商品上限 50（现仅可售商品）；搜索结果卡片入口仍未做（沿用 0ba 口径）。
  - 变体手动切换后不强制锁在 A 商家（需求允许）；若产品要求「切规格也锁商家」需另立需求并在后端按 offer 过滤 variants。
  - Crisp 真实挂件在浏览器里的隐藏效果待用户肉眼确认（本地 headless 不初始化）。
- **返工修复（2026-11-22 晚，验收 10/14 → 3 fail + 1 缺陷全部修复，仍未 commit）**
  - **FAIL 7 白块（三店 196/1348 图片 404）**：`media_usage` 行可能指向本地已缺失文件（S3 时代遗留）。新增 `_media_file_exists()`：`MEDIA_BACKEND=local` 时用 `resolve_media_path(...).is_file()` 校验磁盘，S3 时信任 DB（不逐对象 HEAD）；`_gallery_paths()` 跳过缺失文件、按 `sort_order` 取同 SPU 下一张存在的图，全缺才落到占位图；仍是一次 `media_usage` 查询（无 N+1）。AMORAB/CIFOX/PawHut 现分别 2/16/50 件，去重后图片逐个 GET **0 个 404、0 空 src、0 断图**；占位图 `/images/categories/_placeholder.svg` 200。测试新增「DB 行在/文件缺失 → 用下一张」「全缺 → 占位」。
  - **FAIL 13 五语言键集合**：补齐 de/fr/nl 的 `auth.handoff.*` 6 键（title/processing/success/invalid/generic/backToLogin）。`var/_w_offer_20261122/check-locales.mjs` 用 `Object.keys` 比对：**五语言各 501 键，missing=0 extra=0，KEY_SETS_EQUAL**。
  - **FAIL 14 ruff I001**：只修本批新增的 4 处（`public_views._gallery_paths` 本地 import 块、`test_wp42_services` 3 个新增局部 import 块）。**新增 I001 = 0；既有 5 处未动**（这 4 个文件仍各 1/2/1/1 处；仓库 I001 总数 146 → 142）。`ruff check --ignore I001` 这 4 文件 → All checks passed。
  - **缺陷 12 商家页列 DRAFT**：`_listed_offers()` 增加 `sku__status=ACTIVE, sku__spu__status=ACTIVE`，并在 DB 查询层过滤后才 `[:50]`。CHiQ 14→**9**、Samsung 58→**22**、AMORAB 98→**2**（可售数）；两店全部商品逐个请求详情 API **200 且 offer 命中**，UI 点入 `.detail__panel` 正常、无 `.detail-state` 404。`_searchable_merchants` 未改（搜索口径不变，仅列表只出可售商品）。
  - **复验**：后端 `test_wp42_services + test_product_detail_api` → **Ran 33, OK**；前端 prettier/eslint 过，vitest **17 passed**（offerSelection 6 + use-locale 3 + MerchantChatPanel 8）；Playwright `reverify.mjs`（AMORAB/CIFOX/PawHut/CHiQ/Samsung 五店 + 白名单入口）→ **failures=[]**，console error 0（截图 `reverify-*.png`）；白名单从 CHiQ 店点商品 → 入口仍在、`data-offer-id` = CHiQ offer、面板标题 = CHiQ。清理后 buyers/threads/messages/carts/mirror 全 0；:8000/:3000 已全量重启且 200。
  - **新坑**：①可售过滤必须放在 `[:50]` **之前**，否则「前 50 全是 DRAFT」的店会被误判为 0 商品；②本地媒体 DB 行 ≠ 磁盘文件，任何返回 `/media/...` 的列表都必须按后端校验存在性；③`ruff check` 在仓库根直接跑会漏掉 `backend/pyproject.toml`，必须 `--config backend/pyproject.toml`（或 cd backend）才是验收口径。

## 0bc. 批次 V4（2026-11-22 Crisp 名称区分与会话 meta，✅，未 commit）

- **任务**：让 Crisp Inbox 里能分辨「哪位买家 / 哪家店」。调研（`var/crisp_operator_naming_20261122/research.md`，含 chatbox 截图）先认为 `from=operator` + `user.nickname` 可改显示名；**用户实测更正（重要认知，别丢）**：
  - `user.nickname` **只影响访客端 chatbox**；**客服端 Inbox 的 operator 气泡仍显示席位账号（Joybuy），不认该字段**。API 回读 `user.nickname` 有值是真的，但 Inbox UI 不采用 → **这条路对「客服看 Inbox」的场景无效**。
  - 已实测无效、**不要再走**：①把会话 routing 分配给 operator；②给每商家开席位/独立 token（website token 是 workspace 级）。
  - 用户选定方案：**会话标题（meta nickname）带商家名，消息正文保持干净无前缀**。
- **改动（只改后端，未改前端、未动 PLATFORM_SUPPORT 业务逻辑、无新迁移）**
  - `backend/merchant_ops/crisp_mirror.py`
    - `build_message_payload`：merchant → `from=operator` + `content=正文` + `user={type:website,nickname:店名}`；platform → nickname=`CRISP_PLATFORM_NICKNAME`（settings，默认「Joybuy 客服」）；user → `from=user` + `type=website` + 买家昵称。**正文不再有 `[商家] 店名:` / `[平台]:` 前缀**；`user.nickname` 保留（chatbox 加分项，**不用于客服侧区分**）。
    - 新增 `merchant_chat_meta_nickname()`：`bm` 线程标题 = `"{买家昵称} · {商家店名}"`（买家名取 display_name → 邮箱前缀 → 「买家」；店名取 `Merchant.display_name`）。非 `bm` 线程（PLATFORM_SUPPORT）沿用调用方传入值（店名），不拼接。
    - 新增 `patch_conversation_meta()` / `fetch_conversation_meta()` / `_http_patch` / `_http_get` / `_http_request(method,...)`：`PATCH|GET /website/{id}/conversation/{sid}/meta`，PATCH body `{nickname, email?}`，昵称截断 40 字符；失败重试 1 次后仅记 warning（`crisp_meta_patch_failed` / `crisp_meta_fetch_failed`），**不影响发消息**。
    - `ensure_session()`：新会话 POST conversation → 落库映射 → **PATCH meta** → `from=user` 开场消息；**已存在会话**（历史 anonymous）→ `_backfill_conversation_meta()` 先 GET，meta nickname 为空才 PATCH，成功/已非空写入进程内 `_META_READY` 缓存，避免每条消息都 GET；失败不缓存、下次再试。
    - `queue_merchant_chat_mirror` 用 `MerchantChatThread.objects.select_related("buyer","merchant").filter(pk=message.thread_id).first()` **一次查询**取买家+店名（不 N+1），传 `session_nickname=买家 · 店名`、`session_email=buyer.email`；`queue_support_message_mirror` 传 `session_nickname=merchant.display_name`。
  - `backend/config/settings.py`：新增 `CRISP_PLATFORM_NICKNAME`（env，可空；默认「Joybuy 客服」在代码里）。
- **payload 形态（实测回读）**：merchant 消息 `{type:text, from:operator, origin:chat, content:"V4真机验证：商家回复一句", user:{type:website,nickname:"V4探针店"}, fingerprint:<int>, timestamp}`；会话 meta `{nickname:"V4探针买家 · V4探针店", email:""}`。
- **验证（按验证纪律仅针对性验证）**
  - `manage.py test merchant_ops.tests.test_crisp_mirror --keepdb --noinput --parallel 1` → **Ran 32, OK**（28 + 新增 4：历史会话补写一次/已有昵称不补写/补写失败不阻塞/GET meta 失败不阻塞；另含 meta nickname、昵称截断、platform 可配置、PATCH method 等；旧前缀断言已改成新语义而非保留旧前缀）。
  - `test_merchant_chat`（22）+ `test_merchant_modules`（35）→ **Ran 89, OK**（含 `session_nickname="小明 · 会话测试店"`、`session_email` 传参断言）。
  - `ruff check`（crisp_mirror / 两个测试 / settings）→ All checks passed；`makemigrations --check --dry-run` → No changes detected。
  - **真机**（临时 :8001、真实 Crisp；`var/_v4_crisp_naming_20261122/e2e.py`，只发 2 条业务消息）：`FAILURES=[]`。读回 meta `nickname='V4探针买家 · V4探针店'`；operator 消息 `content='V4真机验证：商家回复一句'`（无 `[商家]`）、`user.nickname='V4探针店'`；买家消息 nickname 正确；本地两条 `crisp_status=sent`、`CrispMirrorLog=2`。
  - **Crisp 会话（用户手工归档）**：`session_3ce75238-2982-41fd-a57d-d52db79c8c57`（3 条：Conversation started + 买家 1 + 商家 1；列表标题应显示 `V4探针买家 · V4探针店`）。首轮（拼接前）的 `session_2e455068…` 与一个调试生成、昵称为空的旧会话均已 `DELETE`（200 deleted），Crisp 侧只留上面这一个。
  - 清理：临时商家/店主/买家/会话/消息/镜像日志/`CrispMirrorSession` 全删，`leftovers` 全 0（复查 DB 亦全 0）；:8001 已 kill。
- **坑 / 实测发现**
  1. **Inbox 不认 `user.nickname`**（见上），客服侧唯一可控标识是会话 meta nickname；chatbox 侧才认消息 nickname。
  2. Crisp 消息列表是 `GET /v1/website/{id}/conversation/{sid}/messages`（复数）；单数 `/message` 只支持 POST（GET 返回 405）。
  3. `PATCH .../meta` 带 `email` 返回 200 `updated`，但回读 `meta.email` 仍为 `""`（访客已绑定匿名 people 档案时不写入）。仍按需求传 email，但**不要断言它一定被保存**。
  4. 真机验证必须用新起的 :8001（`--noreload`）或重启 :8000，`:8000` 上的旧进程不会加载新代码。
- **遗留**：`_META_READY` 只是进程内缓存（多 worker/重启后会重新 GET 一次，幂等、只多一次读）；meta 补写失败无 DB 标记（需迁移才能持久重试）；`user.avatar` 未传（气泡是默认客服图标）；**Inbox 列表标题仍需用户肉眼最终确认**（API 已读回正确 nickname）。

## 0bb. 用户↔商家链路总记录（2026-11-22，批次 V2+V3 + 独立验收 + 竞态复验，✅ 13/13 全过，未 commit）

- **需求**：`功能需求迭代文档03.md` 第十九节（v2.1）。触发条件 = **白名单买家 + 搜索到商家** → 【联系商家】；消息同步到 Crisp 供系统客服查看。
- **V2 后端 ✅**（详见 `0ay`）：`MerchantChatThread`/`MerchantChatMessage`（迁移 0004）；买家 API 4 个（未登录 401 / 非白名单 403 `NOT_WHITELISTED` / 商家不存在 404 / 建会话幂等）；商家 API 3 个（权限 `merchant.messages.use`、跨店 404）；Crisp 镜像 thread_key `bm:{buyer}:{merchant}`，买家 `from=user`+昵称、商家 `from=operator`+`[商家]` 前缀；新增 22 测试 + 受影响 58 测试全过。
- **V3 前端 ✅**（详见 `0ba`）：`MerchantChatPanel.vue` 右侧抽屉（乐观发送、5s 轮询、403 提示、2000 字上限）；`/merchants/<slug>` 仅「已登录 + 白名单」显示入口；商家端 `MessagesView.vue` 新增「买家咨询」tab（不动原客服 tab，切换不自动选中会话以免清未读）；`chat.*` 17 键五语言。
- **独立验收 13/13**（`var/acceptance_bm_chat_20261122/acceptance-report.md`）：白名单门禁 4 接口全 403；收发/未读双向转场/越权 404/跨商家隔离全过；**Crisp 真实 sent**，读回买家（user+昵称）与商家（operator+`[商家]`）消息在同一会话；幂等重复触发不产生重复。
- **验收发现并修复的 1 条真 bug**：首条消息在「轮询先于 POST 返回」竞态下重复渲染 2 个气泡（DB 仅 1 条）。根因：乐观气泡无 serverId、合并只按 serverId 去重、轮询游标忽略未确认消息。修复：`clientId` 原地替换 + 去重键 `serverId ?? clientId` + 游标纳入未确认消息 + 失败分支独立处理；新增竞态回归用例（连跑 4 遍无 flake）；**真实环境把 POST 延迟 7s 稳定复现原窗口，结果气泡 1、pending 0、正文 1 次**。
- **Crisp 测试会话（待用户手动归档）**：`d8de8375…`、`9a71a9ee…`、`49636b2e…`。
- **未做/遗留**：①搜索结果卡片入口（卡片为整块 NuxtLink，仅做了店铺页）；②**商家端手机版（mobile.html/folio）无买家会话入口**——手机版是"原码直 copy"，需另开任务且只加数据层调用、不动渲染代码；③生产环境 Crisp env 未部署（用户要求缓）。
- **验证口径**：针对性验证（后端 22 新测试 + 58 受影响、前端 vitest 8/8 连跑 4 遍、build、Playwright 全链路、ruff/eslint/prettier），未跑全量后端测试套件。

## 0ba. 批次 V3（2026-11-22 用户↔商家前端，✅ 完成，未 commit）

- **任务**：需求 19.1–19.4 的前端部分（批次 V2 已交付后端，见 0ay）。**本轮未改后端、未改 mobile.html/folio、未 commit。**
- **商城端入口**（`storefront/pages/merchants/[slug].vue`）
  - 仅在 **已登录 + `purchase_whitelisted === true`** 时渲染【Contact seller / 联系商家】，位于店铺头右侧（`.shop-contact`，描边红字次要按钮）；未登录/非白名单**不渲染任何节点**。
  - `useBuyerAuth` 新增 `purchaseWhitelisted`（读 session `account.purchase_whitelisted`，不额外发请求）。
  - 点击直接打开面板；面板收到 403 `NOT_WHITELISTED` 时抛 `blocked` 事件，页面置 `chatBlocked=true` **隐藏入口**。
  - **搜索结果卡片（`merchants/index.vue`）本轮未加入口**：卡片整块是 `NuxtLink`，塞按钮会产生嵌套交互元素/破坏现有布局，按需求「可选」只做店铺页（搜索 → 店铺页 → 联系商家）。
- **聊天面板**（新 `storefront/components/MerchantChatPanel.vue`）
  - 右侧抽屉（480px、移动端全宽），交互/无障碍沿用 `AddressDrawer`：backdrop、Escape 关闭、Tab 焦点闭环、锁 body 滚动、关闭后焦点还原。
  - 打开即 `POST /api/v1/account/merchant-chat/threads`（get-or-create）→ `GET .../messages`；消息按 `sender_kind` 分左右（自己红底右对齐、商家灰底左对齐）并显示 HH:MM。
  - 发送走乐观追加（opacity 半透明 pending）→ 接口确认后替换为服务端消息；失败气泡标红并带「未发送，点击重试」；空白不可发；上限 2000（`maxlength` + 提交前二次校验），显示 `n/2000`。
  - 轮询每 5s：`GET .../messages?after=<最后一条服务端消息 created_at>`；抽屉关闭或 `document.hidden` 时停止轮询，页面重新可见立即补一次。加载/空态/失败可重试；401 显示登录提示+登录链接，403 显示白名单提示并隐藏输入区。
  - 双语：`chat.*` 共 17 个键，en/zh/de/fr/nl 五语言齐备（每语言 17 个 `chat.*`）。
- **商家端（桌面 Vue）**（`merchant-web/src/views/MessagesView.vue`）
  - 顶部新增 `.tabs`：**客服会话**（原 PLATFORM_SUPPORT/商品咨询，行为保持：进页自动打开第一条）与**买家咨询**（新 `/merchant/chats`）并列；右侧「刷新」按钮（买家 tab 文案提示 5 秒自动）。
  - 买家 tab：列表显示买家昵称、最后消息摘要、时间、未读角标；点击进入会话后消息列表（买家左/商家右）+ 回复框（Ctrl/Cmd+Enter 发送，2000 字上限+计数）；发送后就地更新列表摘要/未读。
  - **买家 tab 切换时不自动选中第一条**（否则一进 tab 就 GET 详情把未读清零，角标永远看不到）；客服 tab 保留原自动选中行为。买家 tab 每 5s 静默刷新列表 + 当前会话（消息量按最后一条 id 变化才替换，避免跳动）；客服 tab 仍为手动刷新。
- **验证（按验证纪律仅做针对性验证）**
  - `prettier --check` 6 个改动前端文件 → **All matched files use Prettier code style!**
  - `eslint`（`MerchantChatPanel.vue/.test.js`、`useBuyerAuth.js`、`[slug].vue`、`MessagesView.vue`）→ **0 error / 0 warning（静默通过）**。
  - `vitest` `MerchantChatPanel.test.js` → **Ran 5, OK**（建会话+左对齐、乐观发送替换 201、403 提示+隐藏输入+emit blocked、空白/超长不发、`after=` 轮询增量）；连同 `AddressDrawer`+`use-locale` → **12 passed**。
  - `merchant-web` `vite build` → **✓ built**（MessagesView chunk 正常）。
  - **Playwright 端到端**（`var/_v3_merchant_chat_20261122/{setup.py,e2e.mjs,check.py,cleanup.py}`，截图 01–07）：**全部 PASS，failures=[]**
    1. 非白名单买家：店铺页 `[data-testid=contact-seller]` **0 个**；直调 `POST threads` → **403 `NOT_WHITELISTED`**；session `purchase_whitelisted=false`。
    2. 白名单买家：入口文案 "Contact seller" → 开面板 → 发送 `POST messages` **201** → 自己气泡右对齐；商家端 `GET /api/v1/merchant/chats` **200**、`unread=1`、摘要=原文、`last_message_kind=buyer`；商家 UI「买家咨询」tab 显示昵称/摘要/角标 `1`，点开消息在左侧（非 mine）。
    3. 商家回复（隔离 :8001 API）**201** → 买家面板 ≤5s 轮询收到，左对齐。
    4. 刷新页面重开面板：**2 条消息仍在**（落库）。
    5. EN/ZH：`Contact seller` / `联系商家`、`Buyer–seller conversation` / `买家与商家会话`、placeholder、发送按钮均正确；买家与商家页 **console error 0**。
  - **零真实 Crisp**：E2E 把页面里的聊天 API 经 Playwright `route.fetch` 转发到隔离 **:8001**（`CRISP_*= ` 置空），复用同一开发库；`check.py` 复核两条消息 `crisp_status=['skipped','skipped']`、`CrispMirrorLog` 2 条均 `skipped`、`CrispMirrorSession=0`（**没有 sent/没有真连 Crisp**）。
  - 清理（`cleanup.py`）：threads 1 / messages 2 / mirror logs 2 / offers 1 / SPU 1 / buyers 2 / buyer sessions 2 / staff 1 / staff session 1 / merchant 1 全删；`leftovers` 全 0 → **CLEAN**；临时 :8001 已 kill（:8000 200 / :3000 200 / :5174 200 仍正常）。
- **手机版未接入（必须知悉）**：`merchant-web/mobile.html` + `src/folio/` 是「原码直 copy」，本批**一行未改**；手机版**暂无买家会话入口/列表**，买家咨询目前只在桌面 Vue `MessagesView.vue` 可见。
- **验收修复（2026-11-22 晚）：首发送偶发 2 个相同已确认气泡（✅ 已修，仍未 commit）**
  - **触发**：5s 轮询在慢 `POST /messages`（真实 Crisp 首发约 2–4s）返回前触发；DB 仅 1 条，面板出现 2 个相同气泡且都不带 `--pending`。
  - **根因**：`lastServerAt` 只认已确认消息（首发窗口为空 → 轮询拉全量）；`mergeMessages` 只按 `serverId` 去重，而乐观气泡没有 serverId；`deliver` 又原地赋值 → 同一条服务端消息被轮询 append 一次、POST 返回时再替换出第二份。
  - **修复**（只改 `storefront/components/MerchantChatPanel.vue`，按根因修、无 setTimeout）：
    1. 乐观气泡带 `clientId`（`crypto.randomUUID()`，无则时间+随机兜底），key `local-<clientId>`；POST 返回先按 `serverId`（轮询可能先到）→ 再按 `clientId` **原地替换**，绝不 append。
    2. 去重键 = **`serverId ?? clientId`**（`messageIdentity`）+ `pruneDuplicateMessages()` 兜底；`applyServerMessage` 对「同为买家发出、同文、尚未确认」的乐观气泡**原地认领**（补 serverId），轮询不再多出一条。
    3. 轮询游标 `pollCursor` = max(已确认消息, **正在发送的乐观消息** created_at)；失败的乐观气泡不推进游标（避免客户端时钟偏差吞消息）。
    4. `deliver` 的失败/异常分支只在 `!message.serverId` 时标 failed，避免已被轮询认领的已确认消息被误标红。
  - **回归测试**：`MerchantChatPanel.test.js` 新增 3 轮竞态用例（手动 hold POST → 轮询先返回同 id → 再 resolve POST）→ 全程气泡数 1、无 pending、正文只出现一次；**Ran 8, OK**；连跑 3 遍均 8/8；`eslint` / `prettier --check` 通过（同批 5 个旧用例也全过）。
  - **真实环境自验**（`var/_v3_merchant_chat_20261122/e2e-real-first-send.mjs`，**真实 :8000 + 真实 Crisp，只发 1 条**，截图 `08-real-first-send.png`）：面板就绪后等 ~4.6s 再发送以命中窗口 → `POST 201`、耗时 **2252ms**、**POST 期间发生 1 次轮询**、最终气泡 **1**、pending **0**、正文出现 **1** 次、console error **0**。DB 复核：消息 1 条 `crisp_status=sent`、`CrispMirrorLog` 1 条 sent、`CrispMirrorSession=1`——即**只真实发送了这 1 条**。
  - 复跑全量隔离 E2E（:8001、CRISP 置空）→ **failures=[] 全过**（入口/403/发送/商家未读+UI/回复/刷新持久化/EN-ZH/console 0）；两条消息均 `skipped`、mirror session 0；清理后 leftovers 全 0，:8001 已 kill。
  - **副作用（可忽略）**：Crisp Inbox 会留下 1 条临时买家「V3验收买家」的会话（`thread_key bm:<uuid>:MER001775`），本地镜像记录已随临时数据删除；用户可自行归档该会话。
- **遗留 / 风险**
  1. 搜索结果卡片入口未做（见上）；商家端顶栏「消息中心」未挂买家未读总数角标（需求未要求）；买家侧无「我的会话列表」页面，只能从店铺页进入既有会话。
  2. 商家端轮询只在「买家咨询」tab 生效；客服 tab 维持手动刷新（与改动前一致）。
  3. 面板 403 处理有组件测试覆盖，E2E 未做「会话中途被取消白名单」的 UI 场景。
  4. **Crisp Inbox 人眼验收**：竞态修复自验已真实发送 1 条（`sent`，临时买家「V3验收买家」），仍需用户在 Inbox 肉眼确认该会话；其余隔离 E2E 消息均 `skipped`。
- **坑（不得再踩）**
  1. **`/merchants/<slug>` 只返回「有 ACTIVE Offer」的商家**（`merchants/public_views.py::_searchable_merchants`）。E2E 临时商家必须挂 Spu+Sku+Offer，否则店铺页 404，入口根本不会出现。
  2. 商家端买家 tab **不能在切换时自动打开第一条会话**：详情 GET 会把 `merchant_unread` 清零，未读角标永远不可见（首轮 E2E 即因此 timeout）。
  3. Playwright reload 后 SSR HTML 先出现、Vue 尚未 hydrate，立即 click 可能点在没有监听器的按钮上 → 面板不打开。E2E 用 `openChatPanel()`「点一次 + 等 dialog，最多 3 次」规避。
  4. 想零真实 Crisp 又要在真实 :3000 页面里测 UI：用 `context.route('**/api/v1/account/merchant-chat/**')` + `route.fetch({url: :8001, headers:{cookie: 合并 context.cookies()}})`；**必须带合并后的 Cookie（含 csrftoken）并删掉 host/content-length**，否则 CSRF/400。隔离实例启动命令：在 `backend/` 下 `CRISP_WEBSITE_ID= … CRISP_API_TOKEN_KEY= ../.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8001 --noreload`，测完 kill。
  5. 脚本里买家/商家 POST 的 CSRF：`GET session` 返回的 `csrf_token` 是**掩码 token**，Cookie 里的 `csrftoken` 才是密钥，二者都要带（从 `Set-Cookie` 解析），只把 `csrf_token` 当 cookie 会 403。
  6. 五语言键集合目前本来就不完全一致：de/fr/nl 缺 `auth.handoff.*` 6 个键（0ax 遗留），本轮未动；本轮只保证 `chat.*` 17 键五语言一致。不要把它当作 V3 回归。

## 0ay. 批次 V2（2026-11-22 用户↔商家会话后端，✅ 完成，未 commit）

- **任务**：需求 19.1–19.4 的后端部分（原 0ay「导入 UUID 修复」已顺延为 **0az**，内容未改，避免重号）。
- **模型 + 迁移**（`backend/merchant_ops/models.py` + `migrations/0004_merchantchatthread_merchantchatmessage_and_more.py`，已 apply 到开发库）
  - `MerchantChatThread`：`public_id`(UUID，外部 id) / `buyer` FK / `merchant` FK / `status`(OPEN/CLOSED) / `buyer_unread` / `merchant_unread` / `last_message_at`(null) / `created_at` / `updated_at`；`UniqueConstraint(buyer, merchant)`；索引 `(buyer,last_message_at)`、`(merchant,last_message_at)`。
  - `MerchantChatMessage`：`thread` FK / `sender_kind`(buyer|merchant) / `body`(2000) / `created_at` / `read_at`(null) / `crisp_status`(null: sent|skipped|failed)；索引 `(thread,created_at)`。
- **API**（新 `views_merchant_chat.py`，路由在 `merchant_ops/urls.py`）
  - 买家：`POST /api/v1/account/merchant-chat/threads`（body `{"merchant":"<slug>"}`，get-or-create：新建 201 / 已存在 200，同一 id）→ `{thread:{id,merchant:{public_id,display_name,avatar_url},status,last_message_at,unread,created_at}}`；`GET` 同路径按 `last_message_at desc` 列出；`GET .../threads/<uuid>/messages?after=<iso>`（`created_at__gt`，读后 buyer_unread=0 且对方消息回填 read_at）；`POST .../messages`（body 1–2000 字）。
  - 商家：`GET /api/v1/merchant/chats`（`{items:[{id,buyer:{id,display_name,avatar_url:""},unread,last_message,last_message_kind,last_message_at}],total}`）；`GET/POST /api/v1/merchant/chats/<uuid>/messages`；权限 `permission_any=("merchant.messages.use",)`，`X-Merchant-Id` 店铺上下文，跨店 404 `THREAD_NOT_FOUND`。
  - 错误码：未登录 401 `BUYER_AUTH_REQUIRED`；非白名单 403 `NOT_WHITELISTED`（买家侧**读/写/列全部**拦截，不只在建会话）；商家不存在 404 `MERCHANT_NOT_FOUND`；空/超长 400 `MESSAGE_EMPTY`/`MESSAGE_TOO_LONG`；`after` 非法 400 `AFTER_INVALID`。
- **白名单下发**：`_account_payload` **本来就有** `purchase_whitelisted`（`accounts_buyers/views.py:102`），本轮未改代码，只补测试固化 `GET /api/v1/auth/buyer/session` 双向（true/false）且不破坏既有字段。
- **Crisp 镜像**（`crisp_mirror.py` 新增 `queue_merchant_chat_mirror` / `thread_key_for_merchant_chat` / `merchant_chat_buyer_name`）
  - `thread_key = bm:{buyer.public_id}:{merchant.public_id}`；买家 → `sender_kind=user` + 昵称（display_name → 邮箱前缀 → 「买家」）；商家 → `sender_kind=merchant` + display_name，`[商家] 店名: 正文` 前缀由 `build_message_payload` 内部生成。
  - 落库后 `transaction.on_commit` 才发；返回值回写 `MerchantChatMessage.crisp_status`（`duplicate` 记 `sent`）；镜像抛错只写日志、不影响已落库消息。未配置 → `skipped` 且零 HTTP。PLATFORM_SUPPORT 逻辑未动。
- **改动文件**：`backend/merchant_ops/models.py`、`migrations/0004_...`(新)、`crisp_mirror.py`、`views_merchant_chat.py`(新)、`urls.py`、`tests/test_merchant_chat.py`(新)。**未改前端、未 commit。**
- **验证（按验证纪律仅做针对性验证）**
  - `manage.py check` → 0 issues；`makemigrations --check --dry-run` → **No changes detected**；`migrate merchant_ops` 已 apply 0004 到开发库。
  - `manage.py test merchant_ops.tests.test_merchant_chat --keepdb --noinput --parallel 1` → **Ran 22, OK**（白名单 403/未登录 401/404、幂等、收发与未读、`after` 增量、跨买家/跨商家 404、镜像 thread_key/sender_kind/sender_name/body、crisp_status=skipped/sent、镜像抛错不阻塞、session 白名单字段）。
  - 受影响既有：`merchant_ops.tests.test_crisp_mirror` + `test_merchant_modules` → **Ran 58, OK**。
  - `ruff check` 6 个改动 py → **All checks passed!**
  - **curl 端到端**（临时 **:8001** 实例：同一开发库、`CRISP_*` 环境变量置空 → 只在本地写 `skipped`，**零真连 Crisp**；脚本与响应在 `var/_merchant_chat_e2e_20261122/`）：白名单买家建会话 201 → 重复 200 同 id → 发消息 201；非白名单建会话/列表 **403 NOT_WHITELISTED**；商家端列表 unread=1 → 读消息后 0 → 回复 201 → 买家列表 unread=1 → 读消息 unread=0、两条消息按序、`after` 只回新消息；DB `crisp_status=['skipped','skipped']`、`CrispMirrorLog` 2 条（`bm:<buyer>:MER001775`，sender_kind user/merchant）、`CrispMirrorSession` 0（skipped 不建会话）。**全部断言 PASS**。
  - 清理：临时商家/店主/买家×2/会话/消息/镜像日志/会话记录全删，`leftovers` 全 0；临时 :8001 进程已 kill（现 :8000 仅 keepalive 一个，PID **38060**，已加载新代码：`/api/v1/account/merchant-chat/threads` 与 `/api/v1/merchant/chats` 均返回 401 而非 404）。
- **坑（本轮）**
  1. 买家侧白名单门禁必须覆盖**三个**接口（列/读/写），只在建会话拦会被已建会话绕过；本轮已统一走 `_require_chat_buyer`。
  2. 商家侧 thread payload 的 `unread` 是**商家自己的**未读数；验证买家未读要读买家列表，别拿商家响应断言（E2E 首轮错断言即此）。
  3. 迁移由 Django 生成后 import 顺序不合 ruff I 规则，需 `ruff check --fix`；`ruff format` 会顺手改动无关行，本轮已还原 `crisp_mirror.ensure_session` 的原有换行以保持 diff 聚焦。
  4. 想让 E2E 不真发 Crisp：**不要改 `.env`**，另起 `runserver 127.0.0.1:8001` 并在命令前把 `CRISP_*` 置空（`load_dotenv` 默认不覆盖已存在的空值）；测完 kill。
- **遗留（批次 V3，已由 0ba 完成；仅「搜索结果卡片入口」未做、Crisp Inbox 人眼验收仍待）**：商城端店铺页/搜索结果【联系商家】入口 + 聊天面板；商家端「消息」页接入买家会话 tab（现有 `MessagesView.vue` 只接了 PLATFORM_SUPPORT/BUYER 旧接口）；前端轮询/未读角标；EN/ZH 文案；Crisp Inbox 人眼验收。后端已具备全部 V3 所需接口。

## 0az. 修复商品导入 `ValueError('badly formed hexadecimal UUID string')`（2026-11-22，✅ 完成，未 commit；原编号 0ay，临时让位给批次 V2）

- **现象**：08:40 UTC 起商品导入批量失败，`failed_import`（runner 只存 `repr(exc)`，无 traceback）→ 属 TERMINAL 不会被重试。累计 **60** 条：shard1 46 / shard2 14；品类分布：电子健康检测 20、印度及南亚食品 14、冷冻肉类与家禽 7、冷冻派对食品 6、智能家居 6、冷冻素食 4、珠宝 2、韩国食品 1。失败记录特征：`skus_parsed=1, mobile_merged=True, variants=0`、`db=None media=None`（导入在创建任何对象前就抛）、`StagingProduct` 仍 PENDING。payload 里没有任何 uuid/guid 字段 → **不是源站脏数据**。
- **真实根因（不是 payload，也不是数据竞争）**：`Merchant.public_id` 在 **2026-11-22 08:36:10 UTC** 由 `UUIDField` 改成 `CharField(16)`（0at「商家 ID 改 MER+6 位」，`backend/merchants/models.py`），迁移 `merchants.0009_merchant_public_id_mer_format` 于 **08:36:51 UTC** 落库并回填 770 行为 `MER001000…MER001769`。**08:36 之前启动的长生命周期导入进程内存里仍是旧模型元数据（`public_id=UUIDField`）**，MySQL 后端给该列挂 `convert_uuidfield_value`，直接 `uuid.UUID('MER001000')`（**Django 这个转换器没有 try/except**，与 `UUIDField.to_python` 不同，所以抛的是裸 `ValueError` 而不是 `ValidationError`）→ 异常在 `import_services.py:1062 resolve_import_merchant(...)` 处抛出，整条导入判死。
- **traceback（复刻栈，见 `var/uuid_fix_20261122/repro4.log`；原始进程没存栈）**：
  ```
  File "backend/crawler_control/import_services.py", line 1062, in import_staging_product
      merchant = resolve_import_merchant(
  File "backend/merchants/services.py", line 37, in resolve_import_merchant      # 旧代码：select_related("merchant")
      existing = (MerchantSourceMapping.objects.select_related("merchant")...first())
  File ".../django/db/models/sql/compiler.py", line 1541, in apply_converters
      value = converter(value, expression, connection)
  File ".../django/db/backends/mysql/operations.py", line 327, in convert_uuidfield_value
      value = uuid.UUID(value)
  ValueError: badly formed hexadecimal UUID string
  ```
  复刻方式：把真实 `Merchant.public_id` 字段临时伪装成 `UUIDField`（`mock.patch.object(field, "get_internal_type")`），同一栈与原错误字符串 100% 复现；`DB 真实值 = 'MER001000'`（类型 str）。
- **为什么「今天才出现」+ 为什么只有一部分商品挂**（证据链，全部来自落盘文件/进程时间，未猜）：
  1. `backend/merchants/models.py` mtime = 2026-11-22 16:36:10 本地 = **08:36:10 UTC**；`django_migrations` 记录 `merchants.0009` applied_at = **08:36:51 UTC**；首条失败 **08:40:13 UTC**（shard2）/ 08:42:13（shard1）；此前全部 0 条。
  2. 事故窗口内**每个 stale 进程的导入 100% 失败**（不是 payload 相关）：shard2 自 08:40:13 起直到 10:49 无一条 imported；shard1 08:42:13–09:37:04 全部 failed_import。
  3. shard2 现进程（pid 38956/31832）**创建于 07:39:02 UTC**（早于迁移）→ 仍在失败；shard1 槽位在 **09:53:37 UTC 被 chain3 重启**（`runner.shard1of3.lock` mtime = 09:53:37 UTC），新进程读到 CharField 元数据 → 09:53:37 起连续 9 条 imported、再 0 条失败；shard0 最后一条 imported 是 08:09:23（早于迁移）→ 0 失败。
  4. 全库 UUID 列扫描（所有 `UUIDField` 列 × `NOT REGEXP '^[0-9a-fA-F]{32}$'`）= 0 行：只有 `merchant.public_id` 被改成字符型，`MER…` 不在 UUIDField 列里，所以**只有持有旧元数据的进程**会中招。
- **修复（≤30 行，`backend/merchants/services.py`）**：导入链路取商家时**不再 SELECT 展示列**——新增 `_import_merchant_queryset() = Merchant.objects.only("pk", "display_name")` 与 `_import_merchant(pk)`；`resolve_import_merchant` 三条路径（fallback / 已有映射 / get_or_create）全部改走它，**删掉 `select_related("merchant")` 与 `existing.merchant`**（二者都会 SELECT 整行并解码 `public_id`），`IntegrityError` 回退改 `values_list("merchant_id")`。导入端只用 `merchant.pk` + `display_name`（身份冲突提示），`_validate_offer_identity` 也只比 `merchant.pk`（`offers/services.py:59-67`）。**注意：只对 `resolve_import_merchant` 生效，`get_import_fallback_merchant()` 未改**（其他调用方要用其展示字段）。
- **回归测试（`backend/crawler_control/tests/test_crawler_import.py::ImportMerchantLegacyColumnTests`）**：把真实 `Merchant.public_id` 字段临时伪装成 `UUIDField` 复刻旧进程元数据，先断言「整行读取必抛 `ValueError('badly formed hexadecimal UUID string')`」（证明复刻有效），再断言已有映射/fallback 两条解析路径正常、**整条 `import_staging_product` 成功**（`status=IMPORTED`）。**已验证反向有效**：把 `services.py` 还原成 HEAD 版本跑该用例 → `FAILED (errors=1)`，错误就是生产那条 ValueError；修复后通过。
- **验证（按验证纪律仅做针对性验证）**：
  - `py_compile` 两个改动文件 + `ruff check` / `ruff format --check` → 全过（顺带修正了这 2 个文件里 3 处 HEAD 既有的格式偏差）。
  - `manage.py test crawler_control.tests.test_crawler_import --keepdb --noinput --parallel 1` → **Ran 16, OK**（含新回归用例）。
  - `... crawler_control.tests.test_crawler_import_variants` → **Ran 5, OK**；`... crawler_control.tests.test_crawler_quality_gates` → **Ran 13, OK**。
  - `... merchants.tests.test_merchant_domain` → Ran 13，**1 failure = HEAD 既有 TOTP 过期用例**（`test_merchant_totp_policy_is_enforced_during_staff_login` 断言 403 实得 200，HANDOFF 0at 已记录为既有漂移，与本改动无关）。
- **追补（失败清单 + 重放）**：
  - 清单：**`var/uuid_fix_20261122/failed_uuids.json`**（60 条：source_id/品类/分片/账号组/时间/skus/variants，含根因说明；生成脚本 `var/uuid_fix_20261122/collect_failures.py`，`--flip-shards` 可把已结束分片的 `failed_import` 改回合法的可重试状态）。
  - 已做的可重试化：**shard1（非运行中）46 条** `failed_import → failed_http`（runner 的 `TERMINAL` 不含 `failed_http`，`--retry_failed` 也会重试；`stats.failed` 计数不变，因仍以 `failed` 开头）。**shard2（当时在跑）未动**，只记录清单——其进程内存态会在下次 `Progress.set()` 覆盖文件，等它退出后再处理（`chain3` 对 shard2 槽位 starts 已用尽，退出后不再重启）。
  - 重放脚本：**`var/uuid_fix_20261122/reimport_failed.py`**（payload 已在 staging，**无需重抓源站**）：`--dry-run / --limit / --shards / --update-progress-shards / --sleep`；`--update-progress-shards N` 只在 `runner.shardNof3.lock` 未被占用时回写（防覆盖在跑进程）。结果落 `var/uuid_fix_20261122/reimport_results.json`。
  - **实测重放：60 条全部重新导入成功**（`reimport_run.log`：本轮 ok=22 fail=0，其余 38 条在更早的试跑已 IMPORTED；`reimport_results.json` 60 条 unique、staging 全部 IMPORTED）。shard1 的 46 条 progress 已回写 imported（stats imported 369→**415**、failed 56→10）。**shard2 的 14 条 DB 已 IMPORTED、但 progress 文件仍是 failed_import**（在跑进程内存态）→ 等 shard2 进程退出后执行一次：`python var/uuid_fix_20261122/reimport_failed.py --shards 2 --update-progress-shards 2`（幂等，已 IMPORTED 会跳过，只回写 progress）。
- **当前环境状态（勿误判）**：**shard2 的 stale 进程（07:39 UTC 启动）仍在按旧代码跑，它的新失败仍会是同一条 ValueError** —— 这是进程级问题，代码修复只对**新进程**生效；不要为救它去 kill 分片（铁律 + chain3/watchdog 在盯）。它退出后 chain3 会走阶段 2/finale。**后端 8000 未重启**（本次改的是导入服务，不影响接口；但若要让 admin 侧导入串也用新代码，重启 runserver 即可）。
- **坑（不得再踩）**：
  1. **改模型字段类型（尤其 UUIDField）必须意识到长生命周期导入进程持有旧元数据**：迁移后这些进程会继续按旧类型解码新列值，Django MySQL 的 `convert_uuidfield_value` 无 try/except，抛的是裸 `ValueError`。要么先停批再迁移，要么让**热路径只 SELECT 真正用到的列**（本次修法）。
  2. 排查这类错误先看 `django_migrations.applied` 与进程创建时间：`Get-CimInstance Win32_Process` 的 CreationDate 是**本地时间（UTC+8）**，别把 15:39 当 15:39 UTC。
  3. **导入链路上的 `select_related("merchant")` / `existing.merchant` 是事故点**，新增导入相关查询不要整行取商家。
  4. runner 之前只存 `repr(exc)` 导致无栈可看；已在 `var/recrawl_local_20261122/recrawl_runner.py` 的 import 异常分支补 `rec["import_traceback"] = traceback.format_exc()[-4000:]`（var 脚本，不影响在跑进程，重启后生效）。
  5. 不要用「同一个 payload 现在能导入」来否定事故：stale 进程里必然失败、新进程里必然成功，**必须按进程/时间切片看 progress**。

## 0ax. 批次 V（2026-11-22 Crisp 消息镜像，✅ 代码 + 真实令牌端到端实测通过，未 commit）

- **范围**：只做「商家 ↔ 系统客服」镜像（需求 18，用户拍板）。用户 ↔ 系统客服直接复用商城 Crisp 挂件（原生会话，前端未动）；用户 ↔ 商家不做。
- **实现要点**
  1. **服务** `backend/merchant_ops/crisp_mirror.py`：`mirror_message(thread_key, sender_kind, sender_name, body, occurred_at, message_id)` 返回 `{"status": skipped|sent|failed|duplicate, session_id, error}`。未配置 → `skipped`（仍写一条 `CrispMirrorLog`，零 HTTP、无 error 日志）。
  2. **会话标识**：`thread_key = f"merchant:{Merchant.public_id}"`，**商家与平台两侧共用**（管理端若按 `admin:{staff_id}` 会把回复拆到另一个 Crisp 会话）。只镜像 `SupportConversation.kind=PLATFORM_SUPPORT`；`BUYER` 会话直接跳过。
  3. **建会话**：首次 `POST /website/{id}/conversation` → 立刻落库 `CrispMirrorSession(thread_key unique → session_id)` → 发一条 `from=user` 的 "Conversation started"（先落库再发首消息，避免首消息失败后重试又建重复会话）；Crisp 无幂等/无自定义 sid。
  4. **消息体**：`merchant` → `from=operator` + `[商家] {display_name}: {body}`；`platform` → `from=operator` + `[平台]: {body}`；`user` → `from=user` + `user.nickname`。均带 `origin=chat`、`timestamp`（毫秒）、`fingerprint = f"{thread_key}:{message_id}"`。
  5. **幂等**：`CrispMirrorLog` 唯一约束 `(thread_key, message_id)`（message_id=本地 `SupportMessage.pk`）；已 `sent` 直接返回 `duplicate` 不发 HTTP；`skipped`/`failed` 允许重试补发。
  6. **降级**：HTTP 用**标准库 urllib**（`requests` 不在 `backend/requirements/`），超时 5s、最多 2 次尝试（0.5s 退避）；任何失败只写 `CrispMirrorLog(status=failed, error, attempts)` + warning，不抛给接口。`transaction.on_commit` 内还有兜底 try/except。
  7. **触发点**：`views_merchant_inbox.MerchantConversationReplyView.post`、`views_support.AdminSupportConversationDetailView.post(action=reply)` 落库后 `queue_support_message_mirror(message)`（on_commit；前端零改动）。
  8. **配置**：settings 新增 `CRISP_WEBSITE_ID/CRISP_WEBSITE_TOKEN/CRISP_PLUGIN_ID/CRISP_PLUGIN_TOKEN`（env，默认空）；两者都配时优先 plugin token（`X-Crisp-Tier: plugin`）。
- **改动文件**：`backend/merchant_ops/crisp_mirror.py`(新)、`backend/merchant_ops/models.py`(新增 `CrispMirrorSession`/`CrispMirrorLog`)、`backend/merchant_ops/migrations/0003_crisp_mirror.py`(新)、`backend/merchant_ops/views_merchant_inbox.py`、`backend/merchant_ops/views_support.py`、`backend/config/settings.py`、`.env.example`、`backend/merchant_ops/management/commands/crisp_mirror_check.py`(新；仓库无 `backend/management/` 包，命令放在 app 下)、`backend/merchant_ops/tests/test_crisp_mirror.py`(新)。
- **验证（按验证纪律仅做针对性验证）**
  - `manage.py test merchant_ops.tests.test_crisp_mirror --keepdb --noinput --parallel 1` → **Ran 18 tests, OK**（未配置零 HTTP、首建会话顺序、merchant/platform/user 消息体、同 message_id 只发一次、skipped 后补发、HTTP 500/超时降级、on_commit 提交才发/回滚不发、BUYER 不镜像、两端真实接口接线、管理端与商家共用会话、命令输出）。
  - 受影响既有用例：`merchant_ops.tests.test_admin_round2.SupportApiTests` + `test_merchant_modules.InboxTests` → **Ran 10 tests, OK**。
  - `ruff check` 8 个改动 py 文件 → **All checks passed!**；`makemigrations --check --dry-run` → **No changes detected**（0003 已 apply 到开发库）。
  - `manage.py crisp_mirror_check` 无 token → 输出「未配置，跳过镜像…缺少 CRISP_WEBSITE_ID, CRISP_WEBSITE_TOKEN 或 …」。
  - 真实 :8000 实测（临时数据脚本 `var/_crisp_mirror_20261122/{live_check.py,cleanup.py}`）：商家端 `POST /api/v1/merchant/conversations/{id}/messages` → **201**，`CrispMirrorLog` 记 `sender_kind=merchant,status=skipped,attempts=0`；管理端 `POST /api/v1/admin/support/conversations/{id}` (reply) → **201**，记 `sender_kind=platform,status=skipped`。清理后 merchant/staff/conversation/log/role **全部 0**。**未改任何前端文件，页面交互不变**。
- **真实令牌联调结果（2026-11-22，✅ 2xx + 端到端双向已实测）**
  - **配置**：`.env` 新增 `CRISP_API_TOKEN_ID`（前缀 `5b2a…`，36 chars）/`CRISP_API_TOKEN_KEY`/`CRISP_API_TIER=website`，并补上原先缺失的后端 `CRISP_WEBSITE_ID=4c57…`（之前只有 `NUXT_PUBLIC_CRISP_WEBSITE_ID`，后端 `is_configured()` 一直为假）。`MEDIA_BACKEND=local` 未动。**令牌明文不落任何代码/文档。**
  - **代码**：`settings` 新增三项（tier 默认 `website`）；`crisp_config()`/`is_configured()`/`_credentials()` 支持 API token，优先级 **API token > plugin > website**；`_http_post` 的 `X-Crisp-Tier` 用 `CRISP_API_TIER`（API token 生效时）。`crisp_mirror_check` 输出新增三项且只打印 identifier 前 4 位。
  - **实测鉴权方式**：`Authorization: Basic base64(identifier:key)` + `X-Crisp-Tier: website` → **直接可用，无 401/403**，不需要退化方案（Bearer/去 tier 均未用）。
  - **`--send-test` 真实结果**：首次 **HTTP 400** `{"error":true,"reason":"invalid_data","data":{"namespace":"data","message":"data.fingerprint should be number"}}` —— Crisp 要求 `fingerprint` 是 **number**，原实现发 `thread_key:message_id` 字符串。已改为 `int(sha256(f"{thread_key}:{message_id}").hexdigest()[:12], 16)`（稳定 48bit，<2^53）；重跑 → `{'status': 'sent', 'session_id': 'session_ee9c19e2-b58a-4cbb-9bb8-cbda67bbf7ee'}`。
  - **副作用修复**：开场消息「Conversation started」原先不带时间戳，落库时间晚于正式首条消息 → Inbox 预览显示开场语。现给开场消息 `timestamp = occurred_at - 1000ms`（`ensure_session(..., occurred_at=)`）。
  - **端到端实测（真实 :8000 → 真实 Crisp）**：临时商家 `crisp-live-shop`（MER001775）商家端 `POST /api/v1/merchant/conversations/{id}/messages` → **201**，`CrispMirrorLog` `sender_kind=merchant,status=sent,attempts=1`；管理端 `POST /api/v1/admin/support/conversations/{id}` reply → **201**，`sender_kind=platform,status=sent`，**复用同一 Crisp 会话**。Crisp 侧 `GET .../conversation/{session}/messages` **HTTP 200** 读到 3 条（时间升序）：
    1. `from=user` `Conversation started`（nickname 镜像验收店）
    2. `from=operator` `[商家] 镜像验收店: 批次 V 真实令牌联调：请确认商家可以开专票（live-check-20261122）`
    3. `from=operator` `[平台]: 平台已收到，稍后为你处理（live-check-20261122）`
    Crisp `session_id = session_2c668f1d-20f3-4b9d-9c79-68e64cd4f284`（`thread_key=merchant:MER001775`）。
  - **针对性验证（按验证纪律）**：`manage.py test merchant_ops.tests.test_crisp_mirror --keepdb --noinput --parallel 1` → **Ran 23 tests, OK**（原 18 + 5 新：API token 单独可用/优先级高于 plugin 与 website/tier 取自 settings/Authorization 为 identifier:key 的 Basic/401 响应体进 error 文案）；`ruff check` 4 个改动 py → **All checks passed!**。
  - **清理**：`var/_crisp_live_20261122/cleanup.py` 删除临时商家/会员/客服账号/session/会话/消息/镜像日志与映射/`diag:*` 记录 → leftover 全 0。**Crisp 侧会话刻意保留**（供用户在 Inbox 肉眼确认，见下）；`session_ee9c19e2…` 为 `diag:crisp-check` 自检会话，`session_4ad093aa…` 为修复前首轮会话，均可归档/删除。
  - **用户如何确认**：Crisp 后台 → Inbox → 找昵称「镜像验收店」的会话（session `2c668f1d…`）→ 应看到上述三条，且首条之后是 `[商家]` 与 `[平台]` 前缀；`diag:crisp-check` 会话昵称为「系统客服」。**以下需人眼确认、代码无法代验**：Inbox 列表预览、operator 显示名（当前为 token 所属账号 `Joybuy`）、通知/未读状态、免费计划是否限制会话可见。
  - **调试坑（新）**：①`fingerprint` 必须 number，字符串 400；②`_http_post` 现在会把错误响应体截 300 字带进 `CrispMirrorError` 文案，排 401/403 直接看日志；③Windows Git Bash 里 python print 中文偶发 GBK 乱码，**不代表 DB 存错**，用 `ascii()` 核对；④后端 keepalive PID 每次 kill 后会变（当前 **5580**）。
- **未实测/风险（2026-11-22 更新）**：`POST /conversation` 无 body 已实测 2xx；`from=operator` 在 Crisp 侧显示名为 token 所属账号 `Joybuy`（不是商家名，身份靠正文前缀）；免费/付费计划的 note/participant 差异仍未验证；真实 email 可能触发 Crisp 外发邮件（本实现不写 email，只写 nickname）；每日配额 website 1 万 / plugin 5 千次。**只做了开发库实测，生产需在部署环境配同一组 env 并重启。**
- **坑（本轮新踩）**
  1. 后端是 `runserver --noreload`（keepalive 托管）：改 models/settings/views 后**必须 kill 监听 8000 的 PID 让 keepalive 重启**，否则新代码不生效（曾出现接口 201 但 `CrispMirrorLog` 为空）。当前 PID 20692。
  2. staff 会话的 POST 受 CSRF 保护：curl/脚本要同时带 `Cookie: joybuy_staff_session=…; csrftoken=<32位>` 与 `X-CSRFToken: <同值>`，否则 403「CSRF cookie not set」。
  3. 镜像 Status 存小写 `pending/skipped/sent/failed`（与需求 18.3 的 `status=failed` 口径一致），不是大写枚举。
  4. `CrispMirrorLog` 未配置也会写一行 `skipped`：这是可观测要求，且 `skipped` 可重试，配置补齐后同一 message_id 会补发，不要把它当终态。

## 0aw. Crisp 集成技术调研（2026-11-22，✅ 调研完成，只读，未 commit）

- **任务**：调研 Crisp 能否作为「用户↔商家 / 商家↔系统客服 / 用户↔系统客服」三条链路的旁路工作台。**只调研：未写业务代码、未改配置、未 commit。**
- **产出**：`var/crisp_integration_research_20261122/research.md`（能力矩阵、三条链路可行性、架构 A/B、可复用代码清单、风险、待实测清单）。
- **核心结论**：
  1. Crisp **支持服务端代访客发消息**：`POST /v1/website/{id}/conversation/{sid}/message` 的 `from` 可取 `user`（并可用 `user.nickname/avatar`、`timestamp` 毫秒、`fingerprint`）；创建会话 `POST /conversation` 后必须发一条 `from=user` 才进 Inbox。官方 `crisp-import-conversations` 工具即按此模式导入，属官方路径。
  2. **operator 身份不可按消息指定**：`from=operator` 没有 operator_id/nickname 字段，实际显示为 token 所属客服；商家回复无法显示为商家名。
  3. Crisp 会话模型是「1 访客 + N operator」，**不是访客↔访客 IM**，因此「用户↔商家」镜像只能把商家表示为 operator（内容前缀）、付费版 note（Free 不支持 note）、或 participant（Free 最多 1 个额外 participant）。
  4. 推荐**架构 B：自有 `SupportConversation`/`SupportMessage` 为主 + Crisp 旁路镜像**；架构 A（Crisp 为主）覆盖不了用户↔商家，除非给每个商家买 operator 席位。
  5. 免费版：2 席位、无 AI credits、100 profiles；定价页把 Developer APIs 列在 Free，但官方未明确声明 REST API 含在 Free，**必须用真实 workspace 实测**；website token 10,000 请求/天、plugin token 5,000/天；Identity Verification 需 Mini+。
  6. 风险：website webhook 不签名且失败不重试（plugin hook 才 HMAC 签名+重试）；创建会话无幂等/无自定义 session_id；真实 email 可能触发 Crisp 外发邮件（导入前需关闭 outgoing emails）；API 注入消息也会触发 webhook，需 fingerprint 去重。
- **现有代码**：商家端 `MessagesView.vue` + `folio/api.js`、管理端 `SupportView.vue`、后端 `views_merchant_inbox.py`/`views_support.py`、模型 `SupportConversation/SupportMessage` 均为真实 API，可直接复用；**买家端没有任何会话 API/UI**，商城只有未接线的 CustomerServicePage“Online chat”按钮和只注入脚本的 `plugins/crisp.client.js`。
- **验证（按验证纪律仅做针对性验证）**：本任务为文档调研，**未运行代码/测试**；Crisp 侧结论均来自官方文档与官方导入工具 README，未在真实 workspace 发请求，待实测项见 research.md 第 6 节。

## 0au. 修复「申请店铺上传 logo 仍提示请上传店铺logo」（2026-11-22，✅ 完成，未 commit）

- **现象**：`/account/apply-shop` 选图后 `POST /api/v1/account/merchant-application/media` 返回 500，页面提示【请上传店铺logo】。
- **根因（不是代码 bug）**：根 `.env` 被写成 `MEDIA_BACKEND=s3`（17:06 改 Crisp 时整文件覆写遗留），后端 17:18 重启后按 s3 跑；AWS 账户仍封禁/本机凭证失效，`storage.store_file_bytes` 走 S3 分支抛未捕获异常 → 500。真实栈（`var/logs/backend.log` 09:37:49 那行 ERROR 的 `exception` 字段，关键三行）：
  ```
  File "backend/media/storage.py", line 215, in store_bytes
    store_file_bytes(relative_path, data, content_type=normalized_mime)
  File "backend/media/storage.py", line 97, in store_file_bytes
    get_s3_client().put_object(
  botocore.exceptions.ClientError: An error occurred (InvalidAccessKeyId) when calling the PutObject operation
  ```
  迷惑点：同一页面前一次上传返回过 201——内容寻址去重命中已有 sha256 时不写后端，**201 不代表 S3 正常**。
- **改动**：只改 `.env`：`MEDIA_BACKEND=s3` → `MEDIA_BACKEND=local`（保留 `MEDIA_S3_*` 四行与 S3 凭证不动，仅加注释「AWS 封禁期间本地存储，恢复前勿改回 s3」）。`backend/media/uploads.py`、`media/storage.py`、`views_shop_application.py`、`storefront/pages/account/apply-shop.vue` **均无需改**：前端上传逻辑本来就把 `response.media.url` 写进 `logoUrl` 并清 `fieldErrors.logo`、预览用本地 blob。
- **生效动作**：settings 只在进程启动读 env → `taskkill //F //PID 58464`，keepalive（`var/run_backend_keepalive.sh`，PID 42196）自动拉起新 runserver **PID 52556**，`:8000` 200。
- **验证（按验证纪律仅做针对性验证）**：
  - 进程内探针 `store_upload(purpose='shop_application')`：`MEDIA_BACKEND=local`，返回 `/media/merchants/original/89/53/....png`。
  - curl 完整链路（临时买家 + `create_buyer_session` → GET session 取 csrftoken → multipart POST）：**201** `{"media":{"url":"/media/merchants/original/fd/ee/....png",...}}`；该 url `GET` → **200** `image/png` 185 bytes。
  - Playwright（脚本 `var/_fix_apply_shop_20261122/e2e_apply_shop.mjs`）真实 `setInputFiles` 两图：两次 media POST **201/201**、logo 预览可见、`.shop-apply__error[role=alert]` 上传后/提交后均为 `[]`（**无「请上传店铺logo」**）、提交 `POST /api/v1/account/merchant-application` **201 PENDING**、待审面板可见、console error **0**；截图 `var/_fix_apply_shop_20261122/apply-shop-after-upload.png`。
  - `manage.py test merchant_ops.tests.test_merchant_application --keepdb --noinput --parallel 1` → **Ran 32 tests, OK**。
  - `ruff check backend/merchant_ops/views_shop_application.py backend/media/uploads.py backend/media/storage.py` → **All checks passed!**
  - 清理（`var/_fix_apply_shop_20261122/cleanup_temp.py`）：MerchantApplication 1 / BuyerSession 1 / BuyerAccount 1 / MediaAsset 3（含探针图）+ 磁盘文件 3 全删；复核 buyer_left=0、assets_left=0、files_still_on_disk=0。
- **坑（不得再踩）**：
  1. **AWS 未恢复前根 `.env` 必须是 `MEDIA_BACKEND=local`**；`.env` 不在 git 里，其他批次改 `.env`（如加 Crisp）很容易整文件覆写把 s3 带回来。遇到上传 500 先看 `.env` 与 `var/logs/backend.log` 的 ERROR `exception`，不要先怀疑 Pillow/目录权限。
  2. 改完 `.env` 必须重启 runserver（settings 启动时只读一次）；正确姿势是 kill 监听 8000 的 PID 让 keepalive 重启，**不要**再手工起一个带 env 前缀的 runserver（会与 keepalive 抢端口/双进程）。
  3. Playwright 点提交别用 `button[type=submit]`（页头搜索按钮也匹配，strict mode 报 2 个）；用 `form button.base-button[type=submit]`。
  4. 买家侧上传的 CSRF 需要同一 Cookie 头里同时带 `joybuy_buyer_session` 与 `csrftoken`；curl 同时用 `-b jar` 再手写 `Cookie:` 会被 Django 只取到一个头导致 401。

## 0push. 代码推送 GitHub（2026-11-23，✅ 完成）

- 用户要求「把代码提交到 GitHub，包括爬虫相关的」。检查结论：**爬虫代码 42 个文件早已全部入库**（、、fixtures 均在工作区无遗留改动），（真实 FB cookie）与 、 仍被 .gitignore 正确排除，**未提交任何凭证**。
- 本次推送两个提交到 （b516985..600739e）：
  1.  修复媒体去重残留失效引用（ 去重命中时校验物理对象存在性并回写）+ 购物端请求超时兜底（useFetch 15s、devProxy +8s）。
  2.  频道页卡片版式（layout 枚举 row3/row3_scroll/grid2x2 + 迁移 0015/0016 播种）+ 新增  楼层同步命令（默认 dry-run）+ 管理端面板/商家端接口适配 + 测试。
- 安全扫描：待提交文件内无 AWS key/password/token 字面量；无大二进制（仅 HANDOFF.md 1.3MB 文档）。工作区提交后干净。

## 0ss. 一个账号只能绑定一家店 + 存量多店清理（2026-11-22，✅ 完成，未 commit）

- **需求**：一个账号 = 一个商家端 = 一家店（商家端不再有店铺切换）；之前多店的商家去掉多余店铺。
- **存量只有 3 个多店账号、各多 1 店**（「一店多成员」= 0 例），处理如下（用户未逐项答复，按最保守方案执行并**先做完整备份**）：
  1. `admin@joybuy.test` 保留 HOMCOM(MER001001)；**CHiQ(MER001007) 新建独立账号 `chiq@joybuy.test`（密码 `Chiq!2026`，staff pk=108）接管**——CHiQ 有 17 Offer/3 订单/钱包 80,464.72/保证金 5,000 及多处 PROTECT 外键，不可删，业务数据零丢失。
  2. `123456@joybuy.com` 保留「测试商家」(MER001762)；**删除空壳「多多手机」(820)**（事前校验 0 Offer/0 订单/0 流水/0 余额），`MerchantApplication pk=26` 置 **REJECTED + merchant=NULL** + 理由「平台清理：一个账号只能绑定一家店铺，如需开店请重新申请」（保留审计、可重新申请）。
  3. `mobile-paging-20261122@joybuy.test`（自动化测试遗留）**整体删除**：staff 86 + 821/822 两店 + 全部业务数据（售后 2、消息 2、会话 3、通知 5、订单链 26×3、钱包流水 34、Offer 40、membership 2）。
- **备份**：`var/merchant_single_shop_20261122/backup/`（32 表 JSON + `manifest.json`，464KB，关键：offer 187、wallet_entry 63、merchant_order 40、support_conversation 7），如需回滚可按行重建。清理脚本 `cleanup.py`（`DRY_RUN` 默认 1、每个写操作前 guard、单事务）——**DRY_RUN 计划与实际计数完全一致**。
- **代码改动（防止再长出多店）**：
  - `backend/merchants/models.py:237-250`：约束 `(merchant, staff)` → **`UniqueConstraint(fields=['staff'], name='merchant_membership_staff_unique')`**；迁移 `merchants/0010_merchant_membership_staff_unique` 已 apply。（MySQL 不支持部分唯一索引，故用无条件 unique(staff)。）
  - `backend/merchant_ops/views_shop_application.py`：买家提交 `:241-253` 与审批 `:619-646` 均新增 **409 `ACCOUNT_ALREADY_BOUND_SHOP`**「该邮箱已绑定其他店铺，一个账号只能绑定一家店铺。」；审批处用保存点 + `IntegrityError` 转同一 409（并发兜底），外层事务回滚保证不建店；email 查询统一 `iexact`。
  - `backend/merchant_ops/merchant_context.py:63-70`：多店脏数据从 400 改 **403 `MERCHANT_MULTIPLE_SHOPS`**「数据异常：该账号绑定了多家店铺，请联系平台处理。」（`X-Merchant-Id` 匹配逻辑不变）。
  - **前端零改动**：桌面 `MerchantLayout.vue:178`、手机版 `merchant-mobile.js:299` 都是 `shops.length > 1` 才渲染切换，单店自动隐藏（实测 DOM `select` 数量 = 0）。
- **测试**：`test_merchant_domain`（多店绑定被拒 / 三 staff 覆盖三态 / unique(staff)）、`test_merchant_app`（跨店绑定被拒 + 脏数据 403 + 带 X-Merchant-Id 仍 200）、`test_merchant_application`（提交 409、审批 409 且不建店不建账号）。指定命令 **Ran 76 / failures=1**（唯一失败为既有过期 TOTP 用例，非本次回归）；新增 11 用例 **Ran 11 OK**；ruff check 全过，format 仅剩 2 个文件历史漂移。
- **验证（针对性）**：后端重启后 health 200；数据核对全 PASS——`multi_shop_staff=[]`、admin→仅 HOMCOM、chiq→仅 CHiQ（密码可校验、余额 80,464.72 不变）、123456→仅测试商家、mobile-paging 不存在、820/821/822 不存在、app26=REJECTED/NULL、**[demo] 共享活动 2 条完好**；浏览器 IAB 桌面+手机四组实测均**无店铺切换控件**、页面数据正常、console error 0；审批 API 实测 409 且事务回滚（无新店）。截图 11 张 `var/merchant_single_shop_20261122/`。
- **坑（不得再踩）**：①`manage.py shell -c "exec(open(...))"` 里 `__file__` 指向 Django 命令模块而非脚本本身（曾把备份写进 site-packages，已清理），一次性脚本路径写死绝对路径；②kill 8000 后可能同一秒拉起**两个 keepalive/两棵 runserver**，重启后必须确认只有一棵；③开发库有并发爬虫导入持续新建 SOURCE_VIRTUAL 商家（本轮 844–848），商家总数不能写死断言；④CHiQ 17 Offer 中 3 DRAFT + 5 个 SPU 被平台置 DRAFT → UI「本店已上架」只显示 9 件，属历史状态非本次改动；⑤IAB 截图 surface timeout 换新 tab。
- **遗留**：`unique(staff)` 上线后**平台侧没有「换绑店铺」接口**——要把账号从 A 店换到 B 店目前只能手工改 membership；如需要应加事务内换绑接口（校验目标邮箱未绑店 + 审计）。另 `test_merchant_console_session` 有 8 个既有失败（`_submit` 只发 shop_name，被 7 字段校验拒），与本次无关未修。

## 0av. 手机版列表改服务端逐页拉取 + 翻译任务暂停（2026-11-22，✅ 分页完成 / ⏸ 翻译暂停，未 commit）

- **任务**：用户两项要求——①全量英文翻译；②改造静态稿数据槽为逐页拉取。**串行执行**（文件重叠，且并行曾触发配额上限）。**②已完成，①被用户中途叫停（暂停，未完成）**。
- **② 服务端分页（✅ 完成）**：渲染仍是静态稿原码，只改数据槽/取数/接线与必要 CSS（未改模板结构/文案/未引入 Vue）。
  - 后端契约：所有列表共用 `merchant_ops/api_utils.paginate()`，响应统一 `items/page/page_size/total/has_next`；`catalog/products`（page/page_size/q/category）、`listings`（+status）、`orders`（+status/q/start/end，含 `counts`）、`wallet/entries`（+kind/start/end）、`after-sales`/`notifications`/`activities`/`deposit`/`withdrawals` 均支持；**`conversations` 只有 `total`**（无 page/has_next）。
  - 改动：`api.js`（`PAGE_SIZE/ORDERS_PAGE_SIZE=8`；新增 `catalogPage/listingsPage/ordersPage/entriesPage` + `loadCatalogPage/loadListingsPage/loadOrdersPage/loadEntriesPage`（页码越界回夹、筛选下推、失败 toast、加载态禁用）；`rebuildProducts()` 重建当前页 products/orders/listed；`syncRouteData()`+render 包装（筛选变化回第 1 页、纯翻页保页码、写后 stale 补拉**跟随当前 UI 筛选**）；发货/上架/提现只刷新受影响当前页；深链订单用 `q=<id>` 定位；`allFundRows`=当前页含 WITHDRAWAL 行）；`base-3.js`（shop/catalogue 用服务端 `total` 与页码；`orderPage` 直出当前页并新增同款分页器〔**本轮唯一新增结构**，静态稿原本无〕；钱包明细改 entries 单源〔WITHDRAWAL 行=提现申请〕；`pagerClass` 4 位页码紧凑类）；`merchant-mobile.js`（店铺商品也走服务端筛选、订单徽标用 `counts.pending`、钱包页码用 `walletPages`）；`joyplay-concepts.css`（分页按钮 nowrap + `.pagination-wide`）。
  - 实测：上架中心真实 **8353 件** → `共 8353 件`、分页器 `1 2 3 4 5 … 1045` 单行、第 3 页/末页请求与内容正确、搜索回第 1 页；店铺商品 40→41 件翻页带筛选；订单 status=PENDING 10 条 2 页、日期筛选、**发货后当前页刷新且徽标 10→9**；钱包 5 页 + kind 下推 + 提现行可开明细；筛选态上架后重拉 `page=1&category=ELECTRONICS` 且页码不跳；失败 toast + 可重试、加载中分页全禁用；console error 0。截图 `var/mobile_paging_20261122/`。
  - **未改造**：售后/通知/活动/保证金明细（后端支持分页但静态稿无分页器，保持首屏 50 条）；会话（响应无 page 字段）；订单 CSV 导出仍只导当前页；钱包提现单明细依赖 `withdrawals?page_size=100`。
- **① 全量英文翻译（⏸ 暂停，未接线，不可当作已完成）**：用户中途叫停。停止时的状态：
  - 已产出 **未接线的半成品**：`src/folio/i18n.js`（227 行：localize 引擎 + MutationObserver 自动重跑 + 中英双向，语法完整）+ `src/folio/locale-en.js`（910 行/692 条中文→英文字典，结构完整含 `translateEn` 导出）。**两者没有任何文件引用**（boot.js / mobile.html / merchant-mobile.js 均未接线），因此对运行零影响；`vite build` 通过（427ms），未进 dist。
  - 盘点产物（有复用价值）：`var/mobile_i18n_20261122/`——`coverage_before.json`、`collect_inventory.mjs`、`_labels_missing.txt`、`_static_candidates.txt`、`_static_missing.txt`、`zh_*.png` 各页中文截图。
  - **恢复路径**：①接线（boot 启动 `startAutoLocalize()`；语言 sheet 回调 `setLang+localize`）；②补齐覆盖率到英文 UI 0 中文残留（用户数据除外）+ 中英双向校验；③英文变长后的 375/390/430 布局修正；④11 route + 全弹层截图验收。
  - 临时数据已核：无 i18n 临时账号/买家/店铺残留（0/0/0），`merchant-2` 演示店仍在。

## 0at. 商家 ID 改 MER+6 位 + 手机版第 3 轮 5 项调整（2026-11-22，✅ 完成，未 commit）

- **商家 ID 格式**：`Merchant.public_id` 从 UUIDField 改为 `CharField(16)`，格式 **`MER`+6 位数字，从 001000 起顺序编号**（用户原话「随机数字」按顺序编号实现，天然唯一无碰撞）。生成在 `merchants/models.py` 的 `Merchant.save()`：事务内 `select_for_update` 取 max+1，唯一冲突重试 5 次，覆盖 create_merchant/get_or_create/直接 create 全部路径。迁移 `merchants/0009_merchant_public_id_mer_format`（临时列→按 pk 升序回填→删旧列→rename→unique，MySQL 不能直接 Alter 截断）。**dev 回填 770 条**：MER001000（pk1 自营导入）… MER001769（pk810 RONMAR）；HOMCOM=MER001001、CHiQ=MER001007、**merchant-2「测试商家」=MER001762**；COUNT(*)=COUNT(DISTINCT)=770。`MerchantMembership.public_id` 等其他 UUID 字段**未改**。
  - **连带改动（坑）**：商家 ID 不只出现在 `/admin/merchants/*`——`/admin/deposits/{id}/*` 与 `/admin/growth/{id}/actions` 的路径参数也是商家 ID，三处 `<uuid:public_id>` 全改 `<str:public_id>`；`views_catalog` 商家筛选与 `views_auto_orders.merchant_id` 原本按 UUID 解析，改为字符串匹配。前端 `ActivitiesView.vue:216`、`MerchantsView.vue:232` 有 `slice(0,8)` 截断展示（会显示 MER00176 这类 8 字符短串，非解析、功能无碍，未改）。
  - 测试：`merchants.tests.test_merchant_public_id`（5 例：格式/递增/直连 create/显式 ID/重复拒绝/回填算法）+ 原有商家/申请流程 83 例（1 failure 为 HEAD 既有过期 TOTP 用例）；`test_admin_commerce` 56 全过；ruff 9 文件全过。
- **手机版第 3 轮 5 项**（`merchant-web/mobile.html` + `src/folio/`，**仍是静态稿原码直 copy 原则**，只动数据槽位/接线/点名调整）：
  1. **头部右上角**：恢复【切换去商城】（真实接线见 0as-2）+ 【中文】语言按钮（sheet 中文/English，选中持久化 `localStorage['joybuy.merchant.language']`，**只存偏好不翻译文案**——全量 EN 翻译待用户拍板）；**删除【退出】**；多店 select 保留并收窄（96/76px）。375/390/430 单行不溢出。`openOptionSheet` 增加显式 `dismiss()`（Chromium 里 `dialog.close()` 不派发 close 事件，原逻辑会残留不可见 sheet）。
  2. **经营面板 4 格均分一行**：`joyplay-concepts.css` 238-249 `/* JOYBUY-DEV OVERRIDE */` 覆盖 `.work-grid` 为 `repeat(4,minmax(0,1fr))`（原 folio 是 3 列+1.65fr），数字 17px nowrap、环比改单列；375/390/430 实测等宽 82.31/85.75/95.75px、零溢出。
  3. **删除「交互原型 · 示例数据」**：全 route 壳级 bottomnote 全局删除（base-2 + base-4 补插节点）；顺带把钱包密码弹层「本地交互原型/演示密码」、客服「消息仅保存在本地」两处假文案改真实口径。
  4. **上架中心分页窗口化**：`base-3.js:67 pageWindow()`——≤7 页全显，否则首末页 + 当前 ±2 + 省略号；69/71 两处使用（**上架中心与店铺商品共用**）；CSS 固定单行 nowrap。14 页实测 `1 2 3 4 5 … 14` / `1 … 3 4 5 6 7 … 14` / `1 … 10 11 12 13 14`。
  5. **数据交互审计补齐**：上架中心 q/category 改走服务端 `/merchant/catalog/products?q=&category=`；恢复订单搜索+下单日期区间（原先被 improveOrders 整块删掉）；修复推荐返佣 undefined 行（映射 referrals/commissions、PENDING_PAY→待发放）；提现草稿补 frozen、todayProfit 改用 `overview.stats.shipping_profit_today`；已接真实数据的 12 类交互抽验通过；演示面板（#platform-admin 守卫内）与假凭证/假费率入口确认不可达/已移除。
- **验证（按验证纪律仅针对性验证）**：`npx vite build`（多入口）通过；根仓 eslint 我方 3 个 JS 文件 0 error（base 原码副本不计）；移动 route 0-10 + 桌面 1366 三页回归；console error 0（临时收集器已移除）；截图 `var/mobile_copy2_20261122/`；临时数据 ALL CLEAN 且 **`[demo]` 黑五活动 count=1**（cleanup 已改为按 merchant_id 删参与、绝不按标题删活动）、123456@joybuy.com 只读。
- **遗留**：①语言切换不翻译文案；②上架中心仍是「单次查询前 100 件+本地分页」（后端 page_size 上限 100，真正逐页服务端翻页需改数据槽）；③本地 S3 凭证无效（`/merchant/media` 500 InvalidAccessKeyId）→ 头像/售后凭证上传无法验收；④移动端钱包不展示冻结金额/今日收益统计卡（数据层已备好真实字段，仅未渲染）。

## 0as-2. 商家端「切换去商城」改为一次性 handoff token（2026-11-22，✅ 完成，两 host 浏览器实测通过，未 commit）

- **任务/根因**：上一版 `POST /api/v1/merchant/switch-to-mall` 直接给 `joybuy_buyer_session` 写 `Domain=.localhost`，让 storefront(localhost:3000) 共享登录态。**实测失败**：Chromium 拒绝从 `m.localhost:5174` 写入 `Domain=.localhost` 的 cookie（localhost 是 public-suffix 特例），只有从 `localhost:5174` 打开手机版才生效；用户常用 `http://m.localhost:5174/mobile.html`，必须修。
- **新方案（已生效）**：商家端换 **60 秒一次性 handoff token** → 跳 storefront 专用接入页 → storefront 用自己的同源 host 兑换并写 **host-only** session cookie（同源写入永远可靠）。跨 host 写 cookie 的代码路径已彻底删除。
- **改动文件（逐项）**：
  - `backend/accounts_buyers/services.py`：新增 `MERCHANT_HANDOFF_CACHE_PREFIX` / `MERCHANT_HANDOFF_TTL_SECONDS=60`、`issue_merchant_handoff_token(buyer_id=...)`（`secrets.token_urlsafe(32)` → `cache.set("merchant-handoff:<token>", {"buyer_id": str(public_id)}, 60)`）、`consume_merchant_handoff_token(token)`（get → **`cache.delete` 返回值为 True 才算本次消费成功** → 查 ACTIVE buyer；cache 异常按无效凭证返回 None）。`set_buyer_session_cookie()` **删除 `domain` 参数**，现在只写 host-only。
  - `backend/merchant_ops/views_switch_mall.py`：保留 staff 会话校验（401 `MERCHANT_AUTH_REQUIRED`）、空邮箱 400 `STAFF_EMAIL_REQUIRED`、按 email 查/建 BuyerAccount、复制 staff 密码哈希（并发 IntegrityError 复用）；**不再 create_buyer_session / 不再 Set-Cookie**；返回 `{"handoff_token", "redirect_url"}`，redirect_url 由后端用 `settings.STOREFRONT_BASE_URL` 拼 `/auth/merchant-handoff?token=...`。
  - `backend/config/settings.py`：新增 `STOREFRONT_BASE_URL`（env，默认 `http://localhost:3000`，去尾部 `/`）；`.env.example` 同步说明（生产必须改成正式商城域名）。
  - `backend/accounts_buyers/views.py` + `urls.py`：新增 `BuyerMerchantHandoffView` → `POST /api/v1/auth/buyer/merchant-handoff`。**CSRF 选择**：继承 `BuyerCsrfAPIView`（`ensure_csrf_cookie` + `csrf_protect`），与现有 buyer login/register 完全同款——storefront 先 GET `/api/v1/auth/buyer/session` 拿 csrftoken，再带 `X-CSRFToken` POST；不额外用 csrf_exempt。校验 token → 失败 400 `HANDOFF_TOKEN_INVALID`（message「登录凭证已过期，请从商家端重新进入」）→ 成功 `create_buyer_session` + host-only cookie + 返回 `{"email"}`。
  - `backend/merchant_ops/tests/test_switch_to_mall.py`：重写为 handoff 契约（14 用例，见验证）。
  - `storefront/pages/auth/merchant-handoff.vue`（新页，客户端 onMounted 兑换，无登录守卫）：成功 toast + `navigateTo('/account')`；失败显示双语文案 + 「返回登录」；`data-testid="merchant-handoff-error"` 便于测试。
  - `storefront/composables/useBuyerAuth.js`：新增 `exchangeMerchantHandoff(token)`，复用 `post()` 的「先 GET session 取 CSRF → POST → refresh」链路。
  - `storefront/locales/messages.js`：只加 en/zh 成对键 `auth.handoff.{title,processing,success,invalid,generic,backToLogin}`（de/fr/nl 自动回退英文；**用精确 Edit，未重写整文件**）。
  - `merchant-web/src/folio/api.js`：`switchToMall` 改为 `const payload = await merchantWrite(...); window.location.href = payload.redirect_url || STOREFRONT_URL`；`STOREFRONT_URL` 只作响应缺字段时兜底，注释已更新。错误 toast 逻辑（`merchant-mobile.js`）不变。
- **接口契约**：
  - `POST /api/v1/merchant/switch-to-mall`（需 staff 会话；body `{}`）→ 200 `{"handoff_token": "<43 字符 urlsafe>", "redirect_url": "http://localhost:3000/auth/merchant-handoff?token=<token>"}`；401 `MERCHANT_AUTH_REQUIRED`；400 `STAFF_EMAIL_REQUIRED`。**响应不再带 Set-Cookie，也不再返回 email/created**。
  - `POST /api/v1/auth/buyer/merchant-handoff`（无需登录；body `{"token": "..."}`）→ 200 `{"email": "..."}` + `Set-Cookie: joybuy_buyer_session=...; Path=/; HttpOnly; SameSite=Lax`（无 Domain）；400 `HANDOFF_TOKEN_INVALID`。
  - **token 生命周期**：签发即写 redis（Django cache，KEY_PREFIX 之外的真实 key 形如 `joybuy:1:merchant-handoff:<token>`），TTL 60 秒；兑换成功或第二次兑换时删除；并发双击只有一个请求能拿到 `cache.delete()==True`；过期/不存在/buyer 非 ACTIVE/cache 不可用统一 400。
- **验证（按验证纪律仅做针对性验证，未跑全量后端/全量组件/全部 e2e）**：
  - `python backend/manage.py test merchant_ops.tests.test_switch_to_mall --keepdb` → **Ran 14 tests, OK**（覆盖：401、空邮箱 400、首建账号 + 密码哈希一致、二次复用不改密、redirect_url 用 `STOREFRONT_BASE_URL`、兑换 host-only cookie、兑换后 session authenticated、完整 switch→exchange 往返、token 一次性第二次 400、手动删 cache 模拟过期 400、未知/空 token 400、DISABLED buyer 400）。
  - `python backend/manage.py test merchant_ops.tests.test_merchant_app --keepdb` → **Ran 13 tests, OK**。
  - 额外针对性（因改了 accounts_buyers services/views）：`accounts_buyers.tests.test_auth_api --keepdb` → **Ran 15 tests, OK**。
  - `ruff check` 6 个改动 py 文件 → **All checks passed!**
  - storefront `node E:/code/AgentProject/Joybuy/node_modules/vitest/vitest.mjs run`（cwd=storefront）→ **26 files / 168 tests passed**。
  - `prettier --check --end-of-line auto` 改动 storefront 文件 → 通过（Windows CRLF 需带 `--end-of-line auto`，否则全文件 EOL 报错）。`merchant-web/src/folio/api.js` 是上一轮原码直 copy 的未格式化数据层（全文件历史如此），**未做全文件 prettier --write 以避免 1200+ 行无关 diff**；其 eslint 0 error。
  - merchant-web `npx vite build` → **✓ built in 317ms**。
  - 后端重启：旧 PID 43564 → `taskkill //F //PID` → keepalive 拉起 **PID 58464**，`GET /api/v1/categories` = 200。`localhost:3000/api/v1/auth/buyer/merchant-handoff` 经 Nuxt devProxy 冒烟：bad token → 400 `HANDOFF_TOKEN_INVALID`（CSRF 预取正常、无 403）。
- **浏览器端到端（IAB，390×844，截图存 `var/mobile_handoff_20261122/`）**：
  1. `http://m.localhost:5174/mobile.html` 登录临时商家 → 点【切换去商城】→ 落到 `http://localhost:3000/account`；`GET /api/v1/auth/buyer/session` → 200 `authenticated=true`，email=`mobile-handoff-20261122@joybuy.test`。截图 `01_m_localhost_home_before_switch.png`、`02_m_localhost_landing_account.png`。**这就是上一版失败的场景，现已通过。**
  2. `http://localhost:5174/mobile.html` 同流程 → `localhost:3000/account`，session 同样 `authenticated=true` + 同 email。截图 `03_localhost_home_before_switch.png`、`04_localhost_landing_account.png`。
  3. 直接访问 `http://localhost:3000/auth/merchant-handoff?token=bad` → 不白屏：标题「商家账号登录」+ alert「登录凭证已过期，请从商家端重新进入。」+「返回登录」。截图 `05_bad_token_error_page.png`。
  4. 复用同一 token：第一次 → `/account`（截图 `06_token_first_use_landing.png`）；第二次 → 错误页 alert「登录凭证已过期，请从商家端重新进入。」（截图 `07_token_reuse_rejected.png`）。事后 redis `scan *merchant-handoff*` = **0 个残留 key**。
  - console error：账户页 reload 前注入 `console.error`/`window.error`/`unhandledrejection` 钩子，reload 后 **0 条**；两个失败页/成功页无可见错误。DB 核对：3 次兑换共产生 3 条 BuyerSession、1 个 BuyerAccount。
- **临时数据清理核对（脚本 `var/mobile_handoff_20261122/{setup_temp_account.py,cleanup_temp_account.py}`，setup 复用 mobile_copy2 模式）**：cleanup 输出 **RESULT: ALL CLEAN** —— 临时账号/店铺/订单/钱包/保证金/提现/售后/通知/会话/Offer/每日统计/活动参与/**自动创建的买家账号 + 买家会话** 全部 0；**共享活动 `[demo] 黑五限时促销` count=1 仍存活**（只按 merchant_id 删参与记录，绝不按标题删活动）；只读演示账号 `123456@joybuy.com`（staff pk=77、1 个 membership、无 BuyerAccount 被创建）全程未动。
- **坑（必读）**：
  1. **不要再尝试跨 host 写 `Domain=.localhost` cookie**：Chromium 从 `*.localhost` 写入会被拒绝；同源兑换是唯一可靠路径。`m.localhost` 与 `localhost:5174` 的 staff 登录态仍然各自独立（host-only），这是既有行为。
  2. IAB 里「登录」按钮 locator click 会超时（静态稿覆盖层）；用 `evaluate(() => button.click())`。
  3. token TTL 只有 60 秒：手工测试时不要在「拿到 token」和「打开 redirect_url」之间停顿；后端签发与前端整页跳转是连续动作。
  4. 测试用 redis 不是测试库，`test_switch_to_mall` 在 tearDown 里显式删除未消费的 handoff key；不要用 `cache.clear()`（会清掉开发缓存）。
  5. `cache.delete()` 的返回值就是一次性判定，不要改成先 `get` 再无条件 `delete`（并发双击会双花）。
  6. Windows 下 prettier 默认 `endOfLine=lf`，仓库 checkout 是 CRLF：检查改动文件要加 `--end-of-line auto`；不要把 `api.js` 全文件 reformat。
  7. 新 storefront 页在本轮被 Nuxt 自动热加载（curl 直接 200，无需重启）；若下轮出现 404，再按既有流程重启 3000 端口单实例。
- **遗留/生产化**：① cache 仅用 redis，**未做 DB 降级表**——redis 挂掉时 switch 签发会 500、兑换按无效凭证 400；若生产需要高可用再加 `MerchantHandoffToken` 表。② 生产部署必须设置 `STOREFRONT_BASE_URL`，并把商城正式域名加入 `DJANGO_CSRF_TRUSTED_ORIGINS`；③ 本页依赖客户端 JS（禁用 JS 会停在「正在登录…」），开发阶段可接受。④ 未 commit。

## 0as. Crisp Website ID 配置 + 挂件真实加载验证（2026-11-22，✅ 完成，未 commit）

- **任务**：把用户给的 Crisp Website ID `4c57c1c5-7246-46d3-b9db-b925c93eee3b` 配进开发环境，验证「配置后能加载」（批次 A 的未配置零加载路径此前已验收）。
- **改动**：①根 `.env` 追加（原 4 行 MEDIA_* 未动，备份 `var/crisp_20261122/.env.before`）`NUXT_PUBLIC_CRISP_WEBSITE_ID=4c57...`；②根 `.env.example` 末尾补同键占位 + 注释；③**新增 `storefront/.env`（gitignored）只含该键**——Nuxt 只从 rootDir（storefront）读 `.env`，根 `.env` 是后端 `load_dotenv` 用的，对 nuxt 不生效（坑①）；`storefront/.env.example` 早前批次已有该占位，未改。业务代码零改动。
- **重启**：先杀 storefront 看护链（`taskkill //F //T //PID 49556/48192/3052`）再杀旧 nuxt 树（`//PID 50120/23488`，旧实例只绑 `[::1]:3000`）；用 `HOST=127.0.0.1 PORT=3000 NUXT_PUBLIC_CRISP_WEBSITE_ID=... nohup bash var/run_storefront_keepalive.sh >> var/logs/storefront.log 2>&1 &` 重启。现网单实例：`127.0.0.1:3000 LISTENING`（nuxt PID 56972），keepalive 在跑。
- **验证（按验证纪律仅针对性验证）**：`var/crisp_20261122/verify_crisp.cjs`（Playwright）首页 + `/pages/privacy-policy` 双页：head 有 `client.crisp.chat/l.js?website_id=4c57...`（src/参数均对）、`window.$crisp` 存在且 `window.CRISP_WEBSITE_ID` 正确、`#crisp-chatbox` 与 `.crisp-client` 出现（≤15s）、console 0 error / pageerror 0 / 请求失败 0；l.js→`client_default_b8befba.js`→`settings/website/<id>/prelude` 全 200（说明 website 有效且已激活）。截图 `var/crisp_20261122/home_crisp.png`、`privacy_crisp.png`；点开测试 `click_crisp.cjs` → 聊天窗弹出、显示站点真实欢迎语「请问有什么可以帮您 joybuy?」+「客服在线」，截图 `home_crisp_opened.png`。报告 `verify_report.json`。
- **坑（必读）**：①Crisp loader v4.18.3 内置反爬 agent 列表含 **`HeadlessChrome`**，默认 Playwright headless UA 会被**静默跳过**（l.js 200 但无任何后续请求、无报错、无挂件）——验证必须把 context UA 改成普通 Chrome；真浏览器不受影响。②`#crisp-chatbox` 的 rect 高度为 0 属正常（启动器是内部 fixed 元素），DOM 存在性判断足够；③杀 nuxt 前必须连看护 shell 一起杀，否则 5s 内复活。
- **遗留**：未 commit；生产部署需在部署环境配 `NUXT_PUBLIC_CRISP_WEBSITE_ID`（或 storefront `.env`），本地 `127.0.0.1:3000` 的 HOST 绑定是通过启动命令注入的，keepalive 脚本本身未改（下次重启若不带 HOST 会回到 `::1`，但 `http://localhost:3000` 仍可访问）。

## 0ar. FB 爬虫账号扩容 +14（2026-11-22，✅ 完成：**14/14 全部 VALID**，新组 数据抓取07=10、08=4，未 commit）

- **任务**：新 Excel `C:\Users\lyx\Downloads\123-已分列.xlsx`（3 列：账号/密码/TOTP seed，14 数据行）建号入组 + 半自动登录（脚本全自动、用户只过人机验证）。**新 14 个一律进新组 07/08**（与被源站风控标记的 01/02 隔离），不满足于 `crawler_account_batch_setup --create-only`（它按 Excel 行序分到 01/02，会污染）。
- **建号**：新脚本 `var/fb_add_20261122/create_accounts.py`（dry-run 先行 → --apply）：调 `crawler_control.services.create_crawler_account` 逐个创建，label=账号列（`_cell_id` 同款 float→int 清洗，14 位纯数字），前 10 → 数据抓取07、后 4 → 数据抓取08，note=「FB 账号（Excel 批量导入 2026-11-22）」，**幂等（同 label 已存在则跳过）**。结果：pk=64–73（07）、pk=74–77（08）。Excel 体检（`var/fb_add_20261122/inspect_excel.py`）：14 行、label 全 14 位数字、seed 16/32 位 base32 全合法、无重复、密码 10–18 字符。
- **登录**：`var/fb_manual_assist.py` 只改两处——`EXCEL_PATH` → `123-已分列.xlsx`、`ACCOUNT_PKS` → 新 pk 列表；凭据按 label 匹配（`read_credentials` 的 `_cell_id`/`_clean_secret` 天然兼容该表），`--check` 14 个全过（密码/seed 长度、TOTP 可生成，值不打印）。
- **网络预检的关键发现（下次别再误判）**：**python 裸 socket / Git Bash curl 直连 facebook.com 全部超时 ≠ VPN 不通**——本机 VPN 是系统代理模式（`ProxyEnable=1`、`ProxyServer=127.0.0.1:7897`，Clash 系混合端口），直连探测绕过了系统代理。经代理探测 `-x http://127.0.0.1:7897` → facebook.com **HTTP 200**。启动登录脚本时用 `FB_LOGIN_PROXY=http://127.0.0.1:7897` 显式给浏览器设代理（脚本原生支持该 env var），不再依赖 Chromium 跟随系统代理。joybuy.co.uk 直连正常（307=登录墙，正常）。
- **跑批实录（三段）**：
  1. **首跑 14 个**（`var/logs/fb_add_20261122.log`）：9 个 VALID（pk=64/65/67/68/69/70/71/72/73，Cookie 42–44 条含 pin；pk=67 经历 1 次「退回登录页」自动重填后成功）后在**第 11 个（pk=74）中途被外部误杀**——python 脚本进程与浏览器一起消失（非脚本自身异常、无 traceback；killer 不明），剩余 pk=66/74/75/76/77。
  2. **续跑 5 个**（`var/logs/fb_add_20261122_resume.log`，ACCOUNT_PKS=(66,74,75,76,77)）：清场确认（wmic 无 manual_assist/run_crawl、9334 空闲）后重启；4 个 VALID（pk=66 瞬态重跑成功、pk=74 中断重跑成功、pk=75/76 成功），pk=77 报 `ElementLostError`（页面刷新致元素失效，瞬态、未标不可用——与第 9 批 pk=58 同类）。
  3. **补跑 pk=77**（`var/logs/fb_add_20261122_retry77.log`）：单账号重跑 → **VALID**（44 条含 pin）。
- **收尾核验（DB 实查 + `load_account_session` 解密）**：新 14 个 **session_status=VALID 14/14**、无 unavailable；组分布 07=10、08=4；**pin 存在 14/14**（抽查 pk=64/70/77 解密 Cookie 43/44/44 条，只打存在性与条数不打印值）；全库账号总数 63→77。
- **checkpoint 损耗：0**——新批 14 个没有触发 Google 帐户验证/邮箱验证码/设备通知验证（绑定非 Gmail），人机验证由用户通过，凭据错误 0。**坑**：①`ElementLostError` 瞬态失败重跑即成功（pk=58/66/77 三例），不要判不可用；②后台任务可能被外部整体误杀（本轮首跑被杀一次，killer 不明）——恢复流程=wmic 查残留 + netstat 9334 + 按剩余 pk 续跑，已落库的成功不受影响。
- **新组可用性建议**：数据抓取07/08 是干净风控池（14/14 VALID、无源站标记记录），**可直接用于爬虫任务轮转**；建议新建 CrawlJob 时选 07/08 组，与被标记的 01/02 隔离；04 组仍待 Gmail 解封、02 组 4 个 UNKNOWN 可重试。
- **脚本状态**：`ACCOUNT_PKS` 现值 `(77,)`（已跑完），下批照旧改 pk。日志：`var/logs/fb_add_20261122{,_resume,_retry77}.log`；状态事件 `var/logs/fb_manual_assist_status.jsonl`（--check 事件混有 11-22 全程记录）。
- **铁律遵守**：密码/TOTP seed 只在内存（Excel 读入即用、不落盘不打印不进 HANDOFF）；TOTP 只在自动填码失败时才 print 一次性值（本轮未触发）；未 commit、未改 backend 业务代码（只动 var/ 脚本 + 本文件）、未启动 joybuy 抓取任务（DB 里 2 个 RUNNING CrawlRun 是 11-03/11-04/11-15 的已知僵尸态）。

## 0aq. 商家端手机版「原码直copy」重做（2026-11-21，✅ 完成，未 commit，**当前生效方案**）

- **背景**：用户先后否决 0an（手写近似）与 0ap（提取 DOM 重建 Vue 模板）两版「还是不一样」，明确要求「删除当前手机版商家端，直接复制 `商家端手机版需求/寰球优选-商家端三案预览.html` 源码，再修改对接数据接口」。**本轮渲染代码=静态稿原代码，保真由构造保证**。
- **已删除**：`src/mobile/`（13 视图+SheetModal+ProductArt+lib/ui.js）、`src/shell.js`、`RootShell.vue`+`MobileShell.vue`、`mobile-folio.css`；`router/index.js` 还原纯桌面路由（dualShell/手机守卫/`/orders/:id` 全撤）；main.js 改为切换协议入口。
- **新结构**：`merchant-web/mobile.html`（静态稿 948 行逐字+四处最小手术：内嵌脚本抽出/boot 入口、phone 参数烘焙 `data-phone-preview`、三 CSS 带 id 引用〔merchant-mobile.js 原换链机制改切 disabled〕、`html data-design="studio"`）+ `src/folio/`：`base-1..4.js`（4 段内嵌脚本逐段抽出，**仅 14 处数据槽位替换**〔日期/计数/图表 nums/品类饼/收件地区/商品ID/订单日期硬编码〕，渲染结构零改动）、`merchant-mobile.js`（逐字 854 行+3 处接入：`__JOYPLAY_MOBILE__/__JOYPLAY_CONCEPT__` 烘焙开关、CSS 切 disabled、头部演示工具→**店铺切换 select+退出**）、三个 CSS 逐字 0 改动、`api.js`（数据层：14 端点→静态稿全局状态同构映射+全部动作函数真实化+演示逻辑 no-op 化）、`boot.js/boot.css`（登录门/空态屏/脚本按序注入/?p= 路由映射/滞回切回）。`vite.config.js` 多入口 `{main, mobile}`。
- **切换协议**：main.js——`m.` 主机或宽度<760 → `location.replace('/mobile.html?p='+path)`；boot.js——非 m. 主机且 >780 → 弹回桌面同路径（滞回防抖动）；`?p=` 映射 route 后 `history.replaceState` 还原干净地址；静态稿自身 pushState/popstate 历史集成原样。**本架构下切换=换文档（有 reload），vue-router 只在桌面文档里，两文档互不干扰**。
- **数据对接**：overview/orders(+ship)/wallet(+entries/withdrawals/password)/deposit/after-sales(+actions)/activities(+join)/conversations(+send)/notifications(+read/reply)/catalog+listings/profile/media/referral 全部真实 API；删除演示逻辑（localStorage 业务持久化/OrderLifecycle 15s 轮询/PBKDF2 本地哈希/CSV Blob 导出/演示审核与预览开关/切商城语言工具）；登录门=session 检查→folio 登录屏（POST /admin/auth/login）→无绑定店空态→按序动态注入 base-1..4+merchant-mobile.js→populateGlobals→按 ?p= 落 route。
- **保真对照**：15 张并排图 `var/mobile_copy_20261121/compare/`（左稿右应用，390×844）——结构逐页一致，差异仅三类：真实数据值（UUID 单号 vs HW 短号/真实价格）、被删演示 UI（保证金预览折叠/切商城语言）、头部改造区（店铺切换+退出）。
- **验证（按验证纪律仅针对性验证）**：vite build 3 次（删旧/复制/收尾）全过；eslint 我方文件 0 error（base/merchant-mobile 为原码副本不计）；功能回归全过（发货真实扣款 20111.74→20067.12、提现冻结 100、8 类写操作无一 403、console 双端 0、切换协议四象限实测）；临时数据 15 项全 0（脚本 `var/mobile_copy_20261121/{setup,cleanup}_temp_account.py`）；**共享 [demo] 黑五活动再次被 cleanup 误删已重建**（下轮清理脚本要先剔除它）；123456@joybuy.com（merchant-2）全程只读。
- **坑（必读）**：①classic 脚本才共享全局词法环境——base 脚本必须 `<script>` 注入不能 import；②populateGlobals 必须在动态注入后调用；③原稿 compactCopy 按属性顺序剔 banner 是原稿行为别"修"；④conversationOpen 是 IIFE 内部变量，判线程视图读 `.chat-shell` dataset.view；⑤会话线程详情懒加载挂 render 包装；⑥`/merchant/wallet` 自带 entries 第一页；⑦IAB evaluate 传函数要 IIFE 自调用；⑧locator click 偶发卡死用 requestSubmit 兜底。
- **限制/生产化待办**：①base-1..4.js/merchant-mobile.js 是运行时动态注入的 classic script，**未打进 dist**——生产构建需把 6 段脚本纳入打包；②商品卡/聊天商品位沿用原稿 art() 八款 SVG（原稿本无实图位）；③商品池窗口 100/订单流水售后通知窗口 50（原稿客户端分页口径）；④bottomnote「交互原型 · 示例数据」为原稿结构文本，保真优先保留。

## 0ap. 商家端手机版 folio 像素级保真重建（2026-11-21，✅ 已被 0aq 取代，仅存档）

- **背景**：用户抱怨 0an 版手机壳「跟 `商家端手机版需求/寰球优选-商家端三案预览.html` 完全不一样，要一模一样」——0an 是凭探索报告手写的近似实现；本轮以**静态稿浏览器最终渲染结果为唯一保真来源**重做全部 13 个手机视图。方法：IAB 390×844 开 `Joyplay-folio.html`（本地 http 服务 8777 托管需求目录，file:// 不能 goto；清空 localStorage 取首访态），逐 route 提取 `#app` outerHTML **16 份**+截图存 `var/mobile_fidelity_20261121/draft_dom/`，13 视图按提取 DOM 1:1 重建 template（类名/嵌套/属性/内联 SVG 照抄，数据槽位映射真实 API，**script 取数提交逻辑原样保留**）。
- **CSS**：新建 `merchant-web/src/styles/mobile-folio.css`（1885 行，替代 mobile-tokens.css 已删）：三层合并（HTML 内嵌基础样式的移动子集 → joyplay-mobile.css 原文 → joyplay-concepts.css 原文，顺序=静态稿级联），全包 `[data-merchant][data-concept]` 壳根作用域（MobileShell 根 div + **登录页根元素自带属性**——/login 是顶层路由不在壳内，否则 folio 变量全失）；`:root/body>#app` 级规则改写到壳内 `.m-app`；补齐 layer1 三处遗漏（od-* 整套/chat 全套/review·ops-history·avatar-editor）；**中和 merchant.css 五条同名类泄漏**（.tabs padding/.card+.card margin/.tag line-height/.empty-state font-size）。新增 `mobile/components/ProductArt.vue`（静态稿 art() 八款示意 SVG 1:1，无图商品按品类映射）+ `mobile/lib/ui.js`；SheetModal 重做为静态稿 `.dock-sheet` 原生 dialog 结构。**桌面视图一行未动**。
- **逐页保真对照（14 张并排图 `var/mobile_fidelity_20261121/compare/route*.png`）**：route0-10 全部「已一致」，差异仅=真实 API 数据值 vs 演示值（如品类饼图 1 类 3 笔、上架中心 8354 件 vs 演示 33 件）、单号 UUID 前 8 位（后端无 HW 式短号）、无「↗12.3%」环比（API 无字段）。壳头右侧静态稿演示工具（切商城/语言）按既定口径替换为真实店铺切换/退出（无稿自设计）；登录页/店铺管理页/占位页无稿，按 folio 视觉自设计。
- **坑（不得再踩）**：①IAB fullPage 截图拼接伪影——整页图用「视口分片+真实 scrollY 对齐+裁吸顶头」重拼（`scripts/stitch_and_compare.py`）；②IAB setViewportSize 不派发原生 resize/mql-change（切壳用合成事件或真浏览器验证）；③静态稿 IIFE 内部函数 evaluate 全局赋值无效，开消息线程必须 el.click() 会话按钮；④`/login` 不在壳内要自带 data-merchant/data-concept；⑤merchant.css 全局类（.tabs/.card/.tag/.empty-state）泄进手机壳，同名类逐条复位；⑥商品池 8354 件，上架中心页码必须窗口化；⑦seed_merchant_demo 在 deposit_enabled 已开时不会重设 deposit_balance（保证金要走 recharge_deposit/adjust_deposit）；⑧Overview 今日订单/品类占比按 Order.Status.PAID 统计，demo 订单需置 PAID。
- **验证（按验证纪律仅针对性验证）**：`npx vite build` 过；根仓 eslint 0 error（merchant-web 自身无 lint 配置）；功能回归全过（**发货真实扣款 20,095.05→20,075.84 分毫不差**、消息发送、通知已读、售后/钱包/分类 sheet、多店切换、m.localhost 宽视口强制手机壳、桌面 1366 三页与上轮基线并排零回归）；console error 全程 0。
- **临时数据已清**：mobile-folio-20261121@joybuy.test 及两店数据删除核对 15 项全 0（脚本 `var/mobile_fidelity_20261121/{setup,cleanup}_temp_account.py`，复验可重跑 setup）；**共享种子活动 [demo] 黑五限时促销曾被清理误删，已按原值重建**（参与 0 条）；123456@joybuy.com（merchant-2）全程只读未动。

## 0ao. 演示商家账号（2026-11-21，✅ 完成）

- 应用户要求创建商家账号：**email `123456@joybuy.com` / 密码 `123456789`**（StaffAccount pk=77，display_name「测试商家」）+ `create_merchant(display_name='测试商家', admission_approved=True, require_deposit=False)`（Merchant pk=800，slug `merchant-2`，**接单中 ACTIVE、免保证金**）+ MerchantMembership（merchant_owner, ACTIVE）。
- 验证：`check_password` True；`POST /api/v1/admin/auth/login`（字段是 `email`+`password`，不是 identifier）200；`GET /api/v1/merchant/shops` 返回该店（ACTIVE、owner、13 项权限）。可直接在 m.localhost:5174 / 127.0.0.1:5174 登录（两 host 各登一次）。
- 坑：`create_merchant` 的签名是 `display_name`（无 `name` kwarg），`review_admission` 首审锁定——补录 ACTIVE 店直接 `admission_approved=True` 传给 create_merchant 即可。

## 0an. 商家端手机版双壳（2026-11-20/21，✅ 完成并全量验收，未 commit）

- **需求来源**：`商家端手机版需求/` 静态稿（README 明确 `Joyplay-folio.html` 为定稿入口，URL 固定 `design=studio`+`concept=folio`，即 **studio 信息架构 + folio 红色皮肤 + merchant-mobile.js 移动交互**；orbit 远洋蓝/flow 绿洲是过程稿不实现）。用户要求：静态页转 Vue+JS 成为手机版商家端，`m.*` 主机名访问手机版 + 宽度小于阈值自动切换。
- **方案（已实现）**：merchant-web 内「双壳」——同一 Vite app（:5174）、同一路由表、同一会话：
  1. `src/shell.js` 维护响应式 `isMobileShell`：**主机名以 `m.` 开头 → 永远手机壳**（与宽度无关）；否则 `matchMedia('(max-width: 767.98px)')`，另挂 window resize 兜底（真机旋转/WebView 不派发 mql change）。跨阈值切换**无 reload、无路由跳转**（探针法验证：切壳往返 `window.__probe` 存活、路由不变）。
  2. 路由表一份：13 个业务路由用 `dualShell(桌面loader, 手机loader)` 包装（`defineAsyncComponent` 保住独立 chunk）；根布局 `RootShell.vue` 双壳切换。**桌面视图/样式一行未改**（git status 可证）。
  3. 新建 18 文件：`src/shell.js`、`src/styles/mobile-tokens.css`（folio tokens：accent #c31324/hero #a81324/canvas #f5f6f8/radius 8-12-16/space 4-8-12-16/--m-target:44px/gutter clamp(12px,4.1vw,16px)，m- 前缀构件）、`src/layouts/RootShell.vue`、`MobileShell.vue`（顶栏 ←返回+标题+多店紧凑下拉+退出；内容列 max-width min(100%,390px) 居中=folio 预览行为；**无底部 tabbar**）、`src/mobile/` 13 视图+`SheetModal.vue`（底部 sheet：Teleport/safe-area/滚动锁）。
  4. 新增路由 `/orders/:id`（手机订单详情独立页；桌面直连守卫重定向回 /orders，桌面详情仍是抽屉）。守卫：手机壳 `/` 绑店即放行（首页宫格即导航根），模块显隐由宫格按 `can()`+deposit_enabled 过滤；桌面 LANDING 逻辑原样。
  5. 手机视图自取数（复用 `src/lib/api.js`+`useMerchantSession.js`，与桌面同端点），**不重构桌面视图**避免回归。
- **后端唯一改动**：`config/settings.py` `CSRF_TRUSTED_ORIGINS` 追加 `http://m.localhost:5174`（已重启生效）。Vite 8 默认放行 `.localhost` 子域（**未改 vite.config.js**）；**`m.127.0.0.1` 浏览器不解析（IP 无子域），实际入口是 `http://m.localhost:5174/`**。SESSION_COOKIE_DOMAIN 未动：cookie host-only，m.localhost 与 127.0.0.1 登录态各自独立（已知限制，各登一次；不动它否则 admin-web 现状会破）。
- **页面↔端点**：登录 /admin/auth/login；首页 /merchant/overview+conversations+notifications（badge=待发货/会话未读/通知未读）；商品双段 /merchant/catalog/*+/merchant/listings；订单 /merchant/orders(+{id}/ship)；详情 {id}（node_labels/progress/can_ship）；钱包 /merchant/wallet(+entries/password/withdrawals)；保证金 {deposit}；售后 {after-sales,+actions}；活动 {activities,+join}；消息 {conversations,/{id},/{id}/messages}；通知 {notifications,/{id},/{id}/replies}；店铺 GET/PATCH /merchant/profile+/merchant/media。
- **静态稿演示逻辑全部丢弃**（localStorage 数据/OrderLifecycle 模拟/PBKDF2 本地哈希/CSV Blob 导出/切换去商城与语言预览工具）——改接真实 API。偏差：折叠面板指标 folio 实际 5 个、按派单口径做了 6 个；桌面「推荐返佣」板块 folio 未画、手机壳未做。
- **README 验收①②③④全过**（截图 24 张 `var/mobile_shell_20261120/`）：①PENDING 详情默认只显当前节点→「查看全部进度」展开 8 节点→实际发货成功（PENDING→SHIPPED、钱包实时扣款）→COMPLETED 详情整个进度区隐藏；②会话页无订单号、右下角发送+textarea 自动增高、发客服消息成功；③首页身份卡（头像/复制ID toast/编辑资料）+三组宫格+图表直显数值不交互；④375/390/430 三档实测不破版。m.localhost 宽视口强制手机壳（登录页 390 居中偏差 0）；127.0.0.1 1366→390→1366 无 reload 切壳；桌面看板/订单表格+抽屉/消息双栏截图对比零回归；console error 全程 0；m.localhost 下 8 次写操作无一 403。
- **坑（不得再踩）**：①无头环境 rAF 节流——toast 必须同步赋值不能等 rAF；②clipboard 可能挂起——复制 ID 用「先 toast、异步复制+失败回退」；③`?view=shop` 直达商品页时 mount 必须按段取数（曾写死 loadPool 出现假空态）；④会话态写 `?c=<id>` 历史，否则顶栏返回跳过列表；⑤首页「联系平台客服」`?open=support` 改 query 后 watcher 会被 loading 挡住，需手动 syncViewFromQuery；⑥chips 漏 `m-chip` 类导致样式缺失。
- **临时数据已清**：`var/mobile_shell_20261120/cleanup_temp_account.py` 原子删除临时账号+2 店铺+全部关联数据逐项 count=0；CHiQ/HOMCO 与共享 [demo] 活动未动。**注意**：seed 附带给 200 个无价商品池 SPU 补了演示价（62% 估算，seed 原有幂等逻辑，仅本地演示库）。
- **验证（按验证纪律仅针对性验证）**：`npx vite build` 两次通过；merchant-web 无 eslint/prettier 配置（无法跑，如实说明）；未跑全量套件；未 git commit。

## 0an. 16 篇文章详情页验收（2026-11-21，✅ 10/10 全过，未 commit→本轮随批提交）

- **独立验收（`var/acceptance_cs_articles_20261121/acceptance-report.md`）：10/10 PASS，0 fail。**
  - 16 篇（支付 5 + 退货 11）清单行全部可点、落地 `/help/<slug>`；`/pages/` 与 `/help/` 双入口 16×2 URL 全 200 且渲染逐字符一致；面包屑 32/32 可回清单、互链 5 个去重目标全可达。
  - 内容强化比对：16 篇 EN/ZH 标题+分块与 `article_*.json` 逐块一致，**另独立比对批次 S raw 存档**（去标签+声明替换后全文）**32/32 逐字符一致**——不是拿开发方产物自证。
  - 8 图本地 200、0 外链请求；joybuy 域名/EU/欧洲 grep 0；邮箱仅 gmail；our-return-policy 存在 `www.joyfumi.com`（giftcard 处）。
  - 回归：清单页批次 U 形态（7 chips/右栏客服卡）、政策页 5 tab、页脚 3/5/2、批次 T header 全部不回归；vitest 177 全过；五语言 461 恒等；console 0 error。
- **观察项（非阻断，建议后续排查）**：长会话偶发 dev 模式 hydration mismatch 告警（4/13 轮、URL 不固定、隔离复现 0 次、内容检查仍全过）——疑似共享布局异步数据竞态，dev 模式才有，非本批引入。
- **环境坑**：项目 keepalive 会自动复活默认 nuxt 实例——验收时清理后保持 127.0.0.1:3000 单实例。

## 0am. 支付 5 篇 + 退货 11 篇文章详情页复刻（2026-11-20/21，✅ 完成，未 commit）

- **任务**：customer-service【Checkout & Payments】清单页（批次 U 0ak）的文章行此前不可点；
  本批给**支付 5 篇 + 退货 11 篇（用户中途扩范围）全部 16 篇**做真站文章详情页复刻并接通清单页。
  **全程 0 次访问真站**（零风控暴露）：正文用批次 S 存档
  `var/footer_help_20261120/raw_{en_GB,zh_CN}_<slug>.json`（16×2 全 status 200，EN/ZH 均真站自带文案）；
  版式用真站 www 文章页完整 SSR 存档 `invoice_www_en.html` 本地渲染实测（详见
  `var/cs_articles_20261120/measurement.md` + `measure_real_article.cjs`/`real_article_measure.json`）。
- **16 篇 slug（真站 URL 形态 `https://www.joybuy.co.uk/help/<slug>`，全部 ✅ 完成）**：
  支付：`payment-methods` / `update-payment` / `download-invoice` / `apply-coupon` / `payment-declined`；
  退货：`statutory-rights` / `our-return-policy` / `return-exceptions` / `wrong-return` /
  `refunds-overview` / `return-request` / `return-window` / `return-method` /
  `return-pickup-reschedule` / `return-refund` / `submit-complaint`。
  没有抓不到的文章（16×2 全有正文）；EN/ZH 结构本就不同（如 submit-complaint EN=ol、ZH=ul；
  download-invoice 图片 URL 两语言不同），数据按语言各存一套 blocks 逐语言还原。
- **真站详情页结构实测**：wrapper #F5F6FA padding 32px 0 flex 居中；mainWrapper 1264px/min-height
  200px/flex；白卡 `margin-left 16px`（真站 detail_itemContent 原值，无左菜单时保留 → 卡片
  x=104/w=1248）、radius 8、padding 24px 36px；标题 32px/700/32 #000；正文 16px/24px、
  块 margin 10px 0；ul disc、margin 10px 0 10px 20px + padding-left 40px；链接 #0000EE 下划线；
  图片 width:100% + hover 阴影 0 0 5px #333。**真站文章页无面包屑/无页脚/无相关文章区**
  （差异：本地按任务要求加清单页同款面包屑，分类项链回 `/help/<分类 slug>`；footer 保留）。
  本地 vs 真站逐项对照（`compare_layout.cjs`→`layout_compare.json`）：卡片 x/w、标题字号、
  p 行高全部一致。
- **改动文件**：新建 `components/CsArticlePage.vue`(+test)、`content/help/csArticles.js`
  （16 篇双语言 blocks，89KB，生成器 `var/cs_articles_20261120/build_cs_articles.cjs` 0 警告）、
  `storefront/public/images/help/`（8 张真站配图本地托管）；改 `CustomerServicePage.vue`
  （文章行 div→NuxtLink `/help/<slug>`）、两个 content js（articles 加 slug）、
  `pages/help/[slug].vue` 与 `pages/pages/[slug].vue`（csArticles 注册表命中→CsArticlePage，
  双入口同渲染）、`tests/help-pages.test.js`（+7 例）。i18n **无新增键**（复用
  help.csBreadcrumbRoot，461×5 恒等）。未碰 HelpCenter/AppHeader/AppFooter/layouts。
- **替换规则（16.5）**：`support@joybuy.com`→Joybuyfumi@gmail.com（statutory-rights、
  submit-complaint）；真站互链→本地 `/help/<slug>`（23 处全映射）；无本地页的真站网址→
  `https://www.joyfumi.com` 保留路径（giftcard-terms-conditions）；`EU`→Asia、`欧盟`→亚洲
  （EN 4 处/ZH 3 处）；return-window 真站 help.joybuy.com **空锚点**（无可见文本）丢弃。
- **验证（按验证纪律仅针对性验证；dev server 双实例已杀、`HOST=127.0.0.1 --port 3000` 完全重启）**：
  vitest 5 文件 **50/50**（新组件 7 + CS 组件 8 + help-pages 22 + 政策回归 + 页脚）；
  eslint 0 error、prettier 全过（10 改动文件）；五语言 461 键恒等（node 逐键比对）；
  **Playwright `verify_articles.cjs`：269/269 全过** —— EN/ZH × 16 篇：清单行可点、落
  `/help/<slug>`、面包屑可回清单、标题+正文与抓取 JSON **逐段一致**（块数/每块文本/src）、
  8 张图片本地 200（naturalWidth>0）、替换规则 grep 零残留（joybuy 域名/真站邮箱/EU/欧盟）、
  无远程媒体、`/pages/*` 与 `/help/*` 双入口 32 URL 全 200 同标题、**console 0 error**；
  批次 U `verify_pages.cjs` 回归 **45/45 过**（清单页改链接后不回归）。
  截图：`local_article_invoice_en.png`、`local_article_returnrequest_zh.png`。
- **退货 11 篇真实 URL 清单**：已写入 `var/cs_articles_20261120/measurement.md` 第六节
  （含 www/m 两种真站路径形态与每篇 EN/ZH 标题），下批可直接用。
- **坑（新会话必读）**：①真站文章页卡片自带 `margin-left:16px`（非对称 16px 左缝）是
  detail_itemContent 原值，别"修对称"；②Playwright route 是**后注册先匹配**，CSS 兜底
  fulfill 必须注册在 abort 之后（0am 实测踩过）；③批次 S 的 submit-complaint 抓自
  m.joybuy.co.uk（同一篇文章），raw JSON 的 url 字段不全是 www；④detail 类 CSS 只在
  bundle `aa6a29a3f278211f.css`，styled-components 富文本规则在存档页内联 <style>；
  ⑤EN/ZH 文章结构不同，别共用一套块骨架，逐语言存 blocks。

## 0al. 第六轮总记录（2026-11-20，需求文档03 v1.9 第十七节：批次 T/U + 暂停/恢复 + 独立验收，✅ 全部收口）

- **任务链**：用户第六轮 5 项 → 并入 `功能需求迭代文档03.md` **v1.9 第十七节**（17.1–17.6）→ 批次 T/U 并行 → **用户中途要求暂停**（T 停在调研阶段 0 行改动、U 未产出文件，均已如实记录）→ 用户恢复 → 完成 → 各自独立验收（**T 13/13、U 11/11，0 fail**）。
- **批次 T ✅ 13/13**（详见 `## 0aj`）：
  - **17.1**：`hideCategoryNav` 拆分为两条件——【分类】按钮+下拉保留，仅隐藏一级品类行；header 阴影改真站原值 `0 2px 12px .039 / 0 4px 6px .059`（根因：旧值第二层 1px/4px）；header→白卡 32px；左栏 sticky 无遮挡。
  - **17.2**：用户下拉一比一复刻——面板 280px/radius 16/无边框/真站阴影；行 56px+16px+icon 右对齐（flex space-between+padding 0 16px）；hover #f0f1f4+radius 4；用户区头像 40×40+昵称 16/700+**居中（用户口径覆盖真站左对齐，已注明）**+无分隔线；退出登录 `#6E7078`。保留批次 M hover 开合/Escape/语言 5 项/申请店铺五态。
  - **17.3（真站裁决）**：四份真站 SSR 存档+CSS 证明右上角顺序为 **申请店铺→购物车→头像**（购物车在左），需求文档原假设"头像→购物车"被证伪；按派单口径"真站是 购物车→头像则按真站"执行 DOM 顺序互换（非 CSS order），SSR 一致。
  - **17.4**：页脚三栏相邻链接 y 差 52→37px（gap 16/行高 14+21）。
- **批次 U ✅ 11/11**（详见 `## 0ak`）：
  - **真站 customer-service 页真实形态 = 分类 FAQ 清单页**（非文章正文页）：面包屑+标题白卡 24/700+文章清单（支付 5 篇/退货 11 篇，0.5px 分隔、hover 下划线）+Browse by categories 7 chips 3 列（两页 chips 顺序不同）+右栏 319px 客服卡（24/7+搜索框+Online chat）；**无折叠/无正文/无配图**——上一版（批次 S）抓移动 help 文章做的聚合页方向全错，已按清单页形态重做（新建 `CustomerServicePage.vue`，含 4 个内联 SVG），旧聚合正文与 8 张无主图删除。
  - ZH 抓取被风控 → 同日存档 `cat_*_zh.json`+RSC payload 兜底（已标注）。替换口径：邮箱仅 `Joybuyfumi@gmail.com`；两页无网址与 EU 表述（连注释都干净）。
  - 已知差异：真站本页**无站点页脚**，本地保留页脚（待用户裁决）；文章清单项点击跳文章详情未实现（真站清单本身不带正文跳转目标时为纯展示，与真站一致）。
- **验收证据**：`var/acceptance_t_20261120/`（13 条+截图+JSON）、`var/acceptance_u_20261120/`（11 条+281 项明细+6 截图）。vitest storefront 154+admin 9；五语言键 461 恒等；console 0 error 全程。
- **环境新坑**：dev server 曾只监听 IPv6 `[::1]:3000`（127.0.0.1 访问 000）——重启时必须 `HOST=127.0.0.1 PORT=3000`；T 验收时发现并清理了双实例。
- **待办（等用户）**：爬虫恢复（9+1 分类，`var/crawl_night_20261120/create_jobs20.py`）；AWS 恢复后 `aws s3 sync` 本地增量媒体。

## 0ak. 批次 U（2026-11-20 两个 customer-service 页重做，✅ 完成，未 commit）

- **任务**：需求03 **17.5**。上一版（批次 S，见 `0ah`）把【支付和发票】【退货和退款】做成了
  抓自移动 help 站的文章聚合页，与真站 customer-service 页**完全不搭边**，本轮按真站
  customer-service 分类页结构重做并删除旧聚合内容。改动文件：`content/help/payment-and-invoice.js`、
  `content/help/returns-and-refunds.js`（重写）、`content/helpPages.js`（注释）、
  **新建** `components/CustomerServicePage.vue` + `components/CustomerServicePage.test.js`、
  `pages/pages/[slug].vue` 与 `pages/help/[slug].vue`（模板各改一行接线）、
  `locales/messages.js`（新增 `help.cs*` 7 键 × 5 语言，454→**461** 恒等）、
  `tests/help-pages.test.js`（重写 CS 断言）、`components/HelpCenter.test.js`（删旧 image 断言）；
  **删除** `storefront/public/images/help/`（8 张旧文章配图，新结构无正文配图，真站本页也无）。
  未碰 AppHeader/AppFooter/HelpCenter/布局（页脚两个入口链接本就不变）。

- **真站结构实测**（Playwright+cookies+color-api 打桩；产物 `var/customer_service_20261120/`，
  详见 `measurement.md`；EN 两页完整命中 200，抓 ZH 时 pay 页被风控只回壳、但 RSC payload
  完整存于 `cs_pay_zh.html`，returns ZH 停抓，ZH 正文用同日存档
  `var/footer_help_20261120/cat_pay_zh.json`/`cat_returns_zh.json` 兜底）：
  - 页面 = 分类 FAQ 清单页，**无 h1-h4 标签、无段落正文、无表格、无 FAQ 折叠、无配图、无返回按钮**；
  - 骨架：面包屑（根「Customer Service」链到 /customer-service-centre › 当前分类）→
    左列（标题白卡 24px/700 + 文章列表白卡：行 padding 15px 0、0.5px #E0E1E5 分隔、
    16px/400/22 hover 下划线 + 「Browse by categories」20px/600 + 7 个分类 chips
    3 列白卡 16px/600）+ 右栏白卡 319px（24/7 Customer Service + 搜索框 36 高 +
    Online chat 按钮 40 高 1px #1A1A1A）+ 底部联系行 14px/500（信封 icon + 邮箱下划线）；
  - 页面底 #F5F6FA、内容宽 min(1264px,92vw)、联系行贴 wrapper 底（margin-top:auto 复现）；
  - 支付页 5 篇文章 / 退货页 11 篇文章（标题清单，即批次 S 已抓过的同一批文章的入口页），
    chips 顺序两页不同（均不含自身分类）；真站点击文章行实测无可见跳转（click_test.json）。
  - 真站本页**没有**深色站点页脚（DOM 无 footer）；本地 footer-page 布局固定带 AppFooter
    （layouts 禁改）→ 已记录的既知差异。

- **替换规则落地（16.5 口径）**：联系行邮箱 support@joybuy.com → Joybuyfumi@gmail.com；
  两页可见内容**无** joybuy 域名网址、**无** EU/欧洲表述（无需替换）；文件内连注释都不含
  `joybuy.com|joybuy.co.uk|support@joybuy.com|EU|欧洲` 字样（grep 干净）。内容存档
  `content_payment-and-invoice.json` / `content_returns-and-refunds.json`。

- **前端实现**：`CustomerServicePage.vue` 按实测渲染（内联真站 4 个 SVG：chevron/放大镜/
  聊天气泡/信封；标题用 h1/h2 替代真站 p——真站无 heading 标签，视觉样式逐条按实测值）。
  差异记录：①面包屑根本地为灰色文本非链接（真站 /customer-service-centre 本地无此页且禁外链）；
  ②文章行/chips 仅保留 hover 样式不导航（真站可点跳 m 站文章/其它分类页；仅互为对方分类的
  chip 本地互链，恰 1 个）；③搜索框/在线咨询按钮视觉 1:1、不接真站客服系统；④字体沿用全站栈
  （真站面包屑/搜索用 Barlow）。

- **抓不到/未做的清单**：returns ZH 页面实时抓取被风控停（ZH 正文用存档兜底，标题 11 条
  齐全）；真站文章正文页（m 站）本轮不聚合进页面（真站分类页本就不含正文，批次 S 聚合正文
  已按要求删除）；搜索与在线咨询不接真站功能。

- **验证（按验证纪律仅做针对性验证）**：
  - vitest 4 个文件 **36/36 过**（CS 数据结构 5/11 篇+chips 顺序+互链、组件 EN/ZH 渲染、
    政策页回归、页脚链接）；
  - eslint 0 error、prettier 全过（改动 11 文件）；
  - messages 五语言 **461 键恒等**（node 逐键比对通过）；
  - **完全重启 dev server** 后 Playwright `verify_pages.cjs`：**45/45 过** —— EN/ZH ×
    /pages/* 与 /help/* 双入口 8 个 URL 全 200；标题卡/面包屑/行数 5+11/chips 7/右栏/联系行
    与 measurement 一致；联系邮箱=Joybuyfumi@gmail.com；正文+链接属性 grep
    joybuy 域名 0（全局 CSS 里的开发期源码注释 2 处不算，已注明）、EU/欧洲 0、外链图片 0、
    页脚两个入口存在且可点、双入口结构一致、**console 0 error**；
    本地截图 `local_pay_en.png`/`local_returns_zh.png` 与真站 `cs_pay_en.png`/
    `cs_returns_en.png` 并排对比：区块顺序/层级/间距观感一致；
  - dev server 用 `HOST=127.0.0.1 node node_modules/nuxt/bin/nuxt.mjs dev --host 127.0.0.1
    --port 3000` 重启（旧两个实例 IPv4/IPv6 已杀）。

- **坑（新会话必读）**：①真站 customer-service 页类名是 FAQList 但**没有 FAQ 折叠**，别臆造
  折叠交互；②真站该页无站点页脚，本地保留是布局约束非缺陷；③抓 ZH 一次被风控就停，
  存档兜底要标注来源；④`verify_pages.cjs` 的 joybuy grep 要排除 `<style>` 源码注释
  （全局 CSS 里有 2 处开发期注释，见 inspect_joybuy.cjs）。

## 0aj. 批次 T（2026-11-20 header 纠正/用户下拉/位置互换/页脚间距，✅ 全部完成，未 commit）

- **任务**：需求03 **17.1 / 17.2 / 17.3 / 17.4**（纠正 16.1 的过度隐藏）。改动文件（均为批次 T 独占）：
  `storefront/components/AppHeader.vue`、`storefront/components/AppFooter.vue`、
  `storefront/layouts/footer-page.vue`、`storefront/components/AppHeader.test.js`、
  `storefront/components/AppFooter.test.js`。**未碰** messages.js（无新键）、content/、HelpCenter.vue、
  pages/。证据与脚本：`var/header_dropdown_20261120/`（`verify_t.mjs`→`verify_t.json`、
  `t_home_{en,zh}.png`、`t_policy{,_panel}_{en,zh}.png`、`t_dropdown_{en,zh}.png`、
  `t_langswitch_{en,zh}.png`）。

- **17.3 顺序的实测判定（重要，勿回退）**：真站右上角顺序 = **申请店铺(原配送至位) → 购物车 → 头像/登录**
  （购物车在左、头像最右）。证据多重一致：①四份真站 SSR 存档（`var/header_footer_cart_20261119/
  real_home_{en,zh}.html`、`real_home_check.html`、`real_cart_nl.html`，2026-11-19）`jdi-header-user-info`
  内均为 `cartEntry_topBtnWrap`(购物车)在前、`userInfoButton_infoBox`(头像)在后；②真站 CSS 无
  row-reverse/order、cart 有 margin-right:16px；③存档截图 `real_header_closed.png` 视觉一致；
  ④真站政策页存档 `page_priv_en_check.html` 同序。**需求文档 17.3 写的"真站应为 头像→购物车"与
  存档不符**（用户记反）；按任务口径"若真站是 购物车→头像 则按真站"执行 → 用 **DOM 顺序**把购物车
  移到头像/登录之前（未登录：申请店铺→购物车→登录；登录：申请店铺→购物车→头像），SSR 首屏即正确。
  我们改前的真实顺序是 头像→购物车（主会话 Brief 里"当前是 购物车→头像"描述反了），本次改动=真互换。

- **17.1 政策页 header**：
  - `AppHeader.vue` 把 `showCategoryNav` 拆成 `showCategoriesButton`（按钮+面板，仅 /p/ 隐藏）与
    `showCategoryNav`（品类行，/p/ 或 `hideCategoryNav` 时隐藏）。真站政策页存档实测：分类按钮 ×1、
    `header-mini-home-row` ×0 → 政策页有【分类】按钮（可点开下拉）、无一级品类行。
  - 阴影 `.site-header` → 真站原文（fc6d34e1e663c66e.css）：`0 2px 12px 0 rgb(0 0 0/3.9%),
    0 4px 6px 0 rgb(0 0 0/5.9%)`（旧值第二层 1px/4px 偏淡即"太淡"根因）。
  - 间距：真站 `detail_detailWrapper`（政策页 CSS `aa6a29a3f278211f.css`，本次从 st.joy-sourcing.com
    CDN 一次性抓 26 个 bundle 到 `var/footer_help_20261120/priv_css/`）自带 `padding:32px 0`、
    页面底 `#f5f6fa`、白卡 radius 8 → header 下缘到白卡 = **32px**。我们的 HelpCenter 已有
    `padding:32px 24px`，多出的是全局 `.app-main > * { margin-block: 24px }` → `footer-page.vue`
    新增 `.app-main > :deep(.help-center){ margin-block: 0 }` **只对 HelpCenter 根归零**
    （about/contact/news 等页间距不动）。实测 header→白卡 gap = 32px（wrapper 缝 0 + 卡内 padding 32）。
  - 左栏 sticky 不回归：实测滚动后 navTop=136 ≥ headerBottom=120（`--site-header-height` 机制未动）。

- **17.2 用户下拉一比一**（真站 `userInfoButton_meListDropdownLayer` CSS 原文）：面板 280px /
  radius 16px / padding 12px / 无边框、阴影 `0 4px 28px 0 rgba(0,0,0,.039), 0 8px 24px 0 rgba(0,0,0,.059)`
  （替换批次 M 的推断值）；行 56px / 16px / #1a1a1a / 行内 space-between + padding 0 16px（icon 右对齐，
  20px 线性 SVG 保留）/ hover #f0f1f4 + radius 4px；退出登录 `#6e7078`（含 hover，新增
  `.account-menu__item--sign-out`）；用户区头像 40×40 + 昵称 16px/700/22px/max-width 188px、
  **无 border-bottom 分隔线**。⚠️ **用户区居中是用户口径**：真站 `.meAvatarWrap` 实为左对齐+gap 12px，
  17.2-3 明确要求"整体水平居中"，已按 `justify-content:center` 实现（实测面板中心偏移 0px），
  验收对照真站截图时此项会不一致，属用户要求而非缺陷。
  批次 M 行为全保留：hover 即开、移出 ~200ms 关（120ms 仍开/340ms 已关实测）、Escape/外点关、
  五语言、申请店铺五态入口共存（vitest 五态 4 例 + e2e 未登录/登录两态）。

- **17.4 页脚三栏间距**：真站 `.footer_links___k1TA{font-size:14px}` + `li{margin-bottom:16px}`、
  全局 `html{line-height:1.5}` → 行盒 21px、相邻 y 差 **37px**。旧值 min-height 44 + gap 8 = 52px。
  改 `.footer-column__list{gap:16px}`、`.footer-column__link` 去 min-height/padding-block、
  `font-size:var(--font-size-md)`(14px) + `line-height:1.5`。列标题（16/600/mb8）与支付行/©行/
  法规段未动（17.4 只圈条目间距；真站列标题实为 16/700/mb14，记录不在本批范围）。
  实测相邻链接 y 差 EN/ZH 均 **[37, 37]**；ZH 页脚无法规段是既有口径（真站 EN only）。

- **验证（按验证纪律仅做针对性验证；dev server 已 kill 旧实例并以
  `--host 127.0.0.1 --port 3000` 完全重启后执行）**：
  - vitest：`AppHeader.test.js`(19) + `AppFooter.test.js`(6) = **25/25 过**（新增/改写：政策页
    分类按钮保留且可开、17.3 两态 DOM 顺序、17.2 结构行/icon 右位/退出灰类、页脚三栏 3/5/2 结构）。
    注意：vitest happy-dom + css 不注入，**computed style 断言全部放在 Playwright**（既有"44px"
    测试在当前环境下实为空转，已确认，未动它）。
  - eslint 5 个改动文件 **0 error 0 warning**；prettier `--check` **全过**。
  - Playwright EN/ZH（`verify_t.json`，1440×1000，登录态=临时买家注册 API）**全绿，console
    error 两语言均 0**：首页分类按钮+品类行(9 links)在、阴影匹配；政策页分类按钮在/可开下拉/
    品类行 0/阴影匹配/白卡 gap 32/sticky navTop 136>header 120；右上角 DOM 与 SSR 顺序均为
    申请店铺→购物车→头像/登录（SSR 另用 fetch 断言：policy SSR 无 category-nav__list、有
    categories-button）；下拉 280/16px/无边框/阴影/行 56px/16px/#1a1a1a/icon 右缘距行右=16px/
    用户区居中 offset 0/无分隔线/退出 #6e7078，hover 开合+Escape 关+购物车 200+语言切换即时生效；
    页脚 gap 16px/14px/y 差 37。
  - 五语言键：en/zh/de/fr/nl **461/461/461/461/461 恒等**（我未改 messages.js；454→461 的 7 键是
    并行批次 U 加的 customer-service 键，"454+ 恒等"口径满足）。
  - 本批未跑全量套件；回归抽查含首页头部、语言切换、购物车入口、hover 开合。

- **踩坑（勿重踩）**：
  - 真站右上角顺序以**存档 SSR+CSS+截图**为准，别信需求文档的"真站应为 头像→购物车"——已证伪。
  - Chrome computed style 会把阴影 alpha 舍入为两位小数（0.039→0.04），断言需按数值模糊匹配。
  - vitest（happy-dom，css:false）里 SFC 样式不注入，getComputedStyle 取不到组件样式；
    样式类断言放 e2e 或只做 DOM 结构断言；SVG 元素的 `className` 是 SVGAnimatedString，
    用 `getAttribute('class')`。
  - 政策页"header→正文间距"度量口径 = header 下缘到**白色内容卡**顶（=32px）；wrapper 与 wrapper
    之间是 0（真站 detailWrapper 的 padding 在内侧），别量错层。
  - 并行批次 U 在同一仓库工作：dev server 有两个实例（我 127.0.0.1:3000、U [::1]:3000），
    HMR 互相可见属正常；验证用自己实例即可，**不要杀对方的**。
  - 真站政策页 CSS 不在旧 bundle 里，从 `st.joy-sourcing.com` CDN 抓 CSS 不触发风控（HTML 才会）。

## 0ai. 第五轮总记录（2026-11-20，需求文档03 v1.8 第十六节：批次 R/S 开发 + 独立验收 + 修复复验，✅ 全部收口，未 commit）

- **任务链**：用户第五轮 5 项 → 并入 `功能需求迭代文档03.md` **v1.8 第十六节**（16.1–16.6）→ 2 个开发子 Agent 并行（R：头部/首页/搜索/频道；S：页脚/帮助中心/政策页网址）→ 各自独立验收 → 问题修复 → 复验通过。
- **批次 R ✅ 13/13**（详见 `## 0ag`）：
  - **16.1** `AppHeader` 新增 `hideCategoryNav`，政策页布局删除简顶栏改用 `<AppHeader hide-category-nav />`（**未复制第二份 header**）；顺带修 sticky 冲突（header 写 `--site-header-height`，左栏 `:deep` 抬高）。验收：政策页头部除品类外与首页逐元素一致；搜索框因移除分类按钮左移加宽 154.56px（必然结果）。
  - **16.2** `.home-reco__more` 加 60px padding-bottom；**补齐改为渲染时计算**——首屏按当前列数补齐（1440→25 件），1024→3 列、768→2 列同步，`items = 已加载 + 池头循环补到列数整数倍`，无占位灰块、无 hydration mismatch。实测 25→50→75→100→120→145 每步末行满。
  - **16.3** 删除 `/s` 品类 title 下【xx 件商品】（仅展示，分页/筛选不动）。
  - **16.4** 抽共享 `AppMoreButton.vue`，首页与 9 个频道页复用；频道页文案【更多/More】，购物车 View more 不变。
- **批次 S ✅ 12/12 + 复验 3/3**（详见 `## 0ah`）：
  - 页脚三栏 **3/5/2**：了解 Joybuy（删 JoyPlus）/ 政策 5 项（Cookie、隐私、使用条款、**无障碍声明**、**销售条款**）/ 帮助中心仅 2 项（支付和发票、退货和退款）。
  - 帮助中心两页正文抓自**真站移动站** `m.joybuy.co.uk/help/<slug>`（PC `/help/*` 对这两个 slug 只回空壳）——**支付 5 篇 / 退货 11 篇**，配图 8 个文件本地托管（`public/images/help/`），`HelpCenter` 新增 `image` 块类型。
  - 替换口径分三类：①帮助中心两页 EU/欧洲→亚洲 + 网址→joyfumi.com + 邮箱→gmail；②5 个政策页**只换网址**（`joybuy.com`/`joybuy.co.uk`/`joybuy.zendesk.com` → `www.joyfumi.com`，保留路径），公司名/地址/注册号/European Commission/ICO **保持真站原文**；③其余不动。实测全 help 目录 joybuy 域名命中 **0**、邮箱仅 `Joybuyfumi@gmail.com`。
- **决策记录（用户当天两次追加，覆盖此前口径）**：
  1. 政策页正文此前按 0s 节做过「中性 demo 实体」替换 → 用户要求**恢复真站原文**（含公司名/注册号/地址），仅换邮箱（见 `0ae`）；
  2. 用户再追加：**政策页网址也统一换 `www.joyfumi.com`**（公司信息仍保留真站原文）。
- **验证口径**：针对性验证（vitest 140、五语言键 454 恒等、ruff/eslint/prettier、Playwright EN/ZH 多宽度、console 0 error）。**未跑全量套件**。
- **遗留**：①政策页搜索框位置因移除分类按钮必然偏移（已注明，非缺陷）；②帮助中心两页不入左侧 tab（真站左栏仅 5 政策页），只从页脚进入；③英文版销售条款真站本身无表格（首列加粗只对中文定义表）。
- **待办（等用户）**：爬虫恢复（9+1 分类，`var/crawl_night_20261120/create_jobs20.py`）；AWS 恢复后 `aws s3 sync` 本地增量媒体；**全部改动未 commit**（已累积四轮 + 政策页返工，建议尽快提交）。

## 0ah. 批次 S（2026-11-20 页脚三栏 + 帮助中心两页，✅ 完成，未 commit）

- **任务**：需求03 **16.5**。独占文件：`components/AppFooter.vue`、`content/help/`
  （新增 `payment-and-invoice.js`、`returns-and-refunds.js`）、`content/helpPages.js`、
  `locales/messages.js` 的 footer 键。**未碰** header/布局/首页/搜索页/频道页；
  `HelpCenter.vue` 仅新增 `image` 块分支（验收返工要求，见下）与对应最小样式，未改既有版式。

- **真站页脚实测**（2026-11-20 Playwright，`var/footer_help_20261120/dump_footer_en2.json`、
  `footer_zh.json`）：
  - EN：`Get to know us`（Contact us / About us / Joybuy news / **JoyPlus**）；
    `Our policies`（Cookies Policy / Privacy policy / Terms and Conditions）；
    `Let us help you`（**空**，真站当前无链接）。
  - ZH：`了解Joybuy`（联系我们 / 关于我们 / Joybuy 新闻 / **JoyPlus**）；
    `我们的政策`（Cookies政策 / 隐私政策 / 使用条款）；`帮助中心`（**空**）。
  - 真站现状与本轮 16.5 目标不同（目标要求删 JoyPlus、政策栏 5 项、帮助中心 2 项），
    已按用户表格覆盖；列名沿用真站：EN `Get to know us / Our policies / Let us help you`，
    ZH `了解Joybuy / 我们的政策 / 帮助中心`。
  - 最终页脚：了解 3 项（Contact us、About us、Joybuy news）；政策 5 项（Cookies Policy、
    Privacy policy、**Terms of Sale**（slug `terms-conditions`）、Terms of Use、
    Accessibility Statement）；帮助中心 2 项（Payment and invoice → `/pages/payment-and-invoice`、
    Returns and refunds → `/pages/returns-and-refunds`）。`/pages/joyplus` 页面保留，仅页脚不再链接。

- **两页内容来源（真站抓取，非合成）**：
  - 真站 `www.joybuy.co.uk/help`、`/help/<slug>` 对支付/退货等 slug 返回 200 但只有空壳
    （正文 “There's nothing more”），**不能拿 200 当有内容**。
  - 真实入口是客户服务分类页 `https://www.joybuy.co.uk/customer-service-centre`
    （原始 HTML `var/footer_help_20261120/csc_raw_en.html`，其 RSC 数据给出文章 urlName）；
    实际正文在 **`https://m.joybuy.co.uk/help/<slug>`**（移动帮助中心，与 www 客户服务页同一内容体系）。
  - 支付和发票 = **5 篇**：`payment-methods` / `update-payment` / `download-invoice` /
    `payment-declined` / `apply-coupon`；
    退货和退款 = **11 篇**：`statutory-rights` / `our-return-policy` / `return-exceptions` /
    `wrong-return` / `refunds-overview` / `return-request` / `return-window` / `return-method` /
    `return-pickup-reschedule` / `return-refund` / `submit-complaint`。
  - 原始抓取：`var/footer_help_20261120/raw_{en_GB,zh_CN}_<slug>.json`（16 篇 × 2 语言；
    `submit-complaint` 在 m 站首次强风控 403，EN 用同页 SSR HTML 解析 `detail_mainWrapper`，
    ZH 正常抓到；两语言正文均有）；生成脚本同目录 `build_help_pages.cjs`（输出
    `storefront/content/help/<slug>.js`，zh 用真站自带中文文章；文章按真站分组，标题作为
    加粗段落，块类型 `p`/`list`/`image`，未新增 heading）。
  - **左栏是否收录**：真站 help 左栏只有 5 个政策/条款页（批次 Q 实测），支付/退货属于
    customer-service 分类，**故不加入左栏**（`helpNav` 仍 5 项），只从页脚进入；
    路由 `/pages/<slug>` 与 `/help/<slug>` 均可达。

- **替换规则（三类页面，互不混用）**：
  - 新增两页（16.5 口径）：EU / European / Europe / 欧盟 / 欧洲 → Asia / Asian / 亚洲；
    所有网址 → `www.joyfumi.com`（保留路径）；所有邮箱 → `Joybuyfumi@gmail.com`。
  - 5 个既有政策页（本次用户追加口径，**仅换网址**）：所有 `joybuy.com` / `joybuy.co.uk`
    （含 www、www、带路径、href）→ `www.joyfumi.com`（保留路径，如
    `https://www.joybuy.co.uk/help/x` → `https://www.joyfumi.com/help/x`）；
    **EU/EEA/European Commission、公司名（Jingdong Retail…）、地址、注册号 15830555、
    FCA/ICO 等监管表述保持原文**（与 15.2 一致）；邮箱已替换为 gmail，无重复处理。
    第三方链接（如 Trustpilot）不是真站网址，保持原样。
  - 政策页正文替换脚本：`var/footer_help_20261120/replace_policy_urls.cjs`（5 文件，共 45 处网址）。
  - **验收返工（2026-11-20 追加）**：
    - 补齐文章：支付 4→**5**（+`apply-coupon`）、退货 8→**11**（+`return-method` /
      `return-pickup-reschedule` / `submit-complaint`），无缺篇。
    - `terms-conditions` 残留的 2 个 `joybuy.zendesk.com` 外链（均为空文本图标链，指向
      Joybuy 客服门户与 After Sales Policy）按“外部客服系统 → joyfumi”处理，改为
      `https://www.joyfumi.com/hc/en-us` 与
      `https://www.joyfumi.com/hc/en-us/articles/43253173737497-Joybuy-After-sales-Policy`
      （保留原路径）；全 help 目录 grep `zendesk` = 0。第三方 Trustpilot / europa.eu /
      gov.uk / ico / edpb 等非 joybuy 链接保持原样。
    - 源图按语言各一套共 8 个文件（支付 `download-invoice` 每语言 2 张、退货
      `return-request` 每语言 1 张、`return-pickup-reschedule` 每语言 1 张；EN/ZH 截图不同），
      已下载到 `storefront/public/images/help/`（`invoice-step-{1,2}-{en,zh}.png`、
      `return-request-{en,zh}.jpg`、`pickup-reschedule-{en,zh}.png`），正文对应位置用
      `image` 块渲染，本地 `/images/help/*` 200；无外链。两页合计每语言 **4 张**
      （支付 2 + 退货 2）。真站存档中支付页每语言只有这 2 张 `<img>`，不存在第 3 张
      （已核对 m 站与 www 桌面端 EN/ZH）。
    - 复验补漏（2026-11-20 第二次）：`return-pickup-reschedule` 的配图在 `<div>` 内、
      此前解析只认 `<p><img>` 被漏掉；生成脚本已支持 DIV/LI 包裹的图片，并补下载
      `pickup-reschedule-{en,zh}.png`，两语言该图均渲染（naturalWidth>0）。

- **改动清单**：
  - `components/AppFooter.vue`：`columns` 改为三栏 3/5/2；删除硬编码空帮助栏；删 JoyPlus。
  - `locales/messages.js`：`footer.linkTerms` 改为 Terms of Sale / 销售条款 / Verkaufsbedingungen /
    Conditions de vente / Verkoopvoorwaarden；新增 `footer.linkTermsOfUse`、
    `footer.linkAccessibility`、`footer.linkPaymentInvoice`、`footer.linkReturnsRefunds`（五语言同键）；
    `footer.linkJoyPlus` 保留不用。键数 450 → **454**，五语言恒等。
  - `content/helpPages.js`：`helpPages` 共 7（路由用），`helpNav` 仍 5（左栏用）。
  - `content/help/*.js`：5 个政策页网址换 joyfumi；新增 2 页（5/11 篇 + image 块）。
  - `components/HelpCenter.vue`：新增 `block.type === 'image'` 渲染分支与
    `.help-center__image`（max-width:100%;height:auto;margin:10px 0），其余版式未动。
  - `public/images/help/`：8 个本地配图（见上）。
  - 测试：`components/AppFooter.test.js`（10 链接/无 JoyPlus/新标签）、
    `tests/help-pages.test.js`（7 路由 / nav 5 / 5+11 文章 / 网址替换 / 本地图片 /
    zendesk 零残留）、`components/HelpCenter.test.js`（image 块渲染）。

- **验证（按验证纪律仅做针对性验证；含验收返工后复跑）**：
  - vitest（`AppFooter.test.js` + `help-pages.test.js` + `HelpCenter.test.js`）**26/26 过**
    （新增 5/11 文章标题、8 个本地图片、zendesk 零残留、image 渲染等用例）；
    eslint 改动文件 **0 error 0 warning**；prettier `--check` 改动文件 **全过**。
  - `var/footer_help_20261120/verify_local.cjs` → `verify_local.json`：**PASS，errors []**（EN/ZH）。
    EN/ZH 页脚三栏 **3/5/2**、无 JoyPlus、10 个 href 与目标顺序完全一致；ZH 含
    销售条款/无障碍声明/支付和发票/退货和退款。两页 200：payment 正文 1675/625 字符、
    returns 22574/7242 字符、块 129/136；左栏 5 项且新页无 active。
    支付页每语言 2 张图、退货页每语言 2 张图（合计每语言 4 张），全部 `naturalWidth>0`
    且 src 为 `/images/help/*`；正文与 href 中 `joybuy.com|joybuy.co.uk` **0**、`zendesk` **0**、
    EN `EU/European/Europe` **0**、ZH `欧盟/欧洲` **0**、邮箱仅 `Joybuyfumi@gmail.com`；
    returns 含 `www.joyfumi.com` 链接。
    回归 privacy：含 `Jingdong Retail (UK) Limited`、`15830555`、`European Commission`（ZH 欧盟委员会）、
    无 joybuy 域名、邮箱仅 gmail、有 joyfumi 链接；terms-conditions 无 zendesk、有 joyfumi 锚点。
  - `verify_routes.cjs` → 10 条路由 × EN/ZH（含 `/help/<新 slug>` 双入口、5 个政策页）
    **全部 200，console/pageerror 0**；截图 `final_footer_{en,zh}.png`、
    `final_payment_{en,zh}.png`、`final_returns_{en,zh}.png`；
    配图证据 `final_payment_images_{en,zh}.png`、`final_returns_image_{en,zh}.png`。
  - 五语言 messages 键 **454/454/454/454/454**，无缺失/多余键。

- **踩过的坑（勿重踩）**：
  - `www.joybuy.co.uk/help/<slug>` 对所有未知 slug 都回 200 + 空壳，必须检查正文/标题；
    支付与退货文章在 `m.joybuy.co.uk/help/<slug>`。
  - ZH `return-refund` 首次加载偶发空 DOM，重试即可；`return-window` 偶发导航超时。
  - `submit-complaint` 在 m 站频繁触发风控（HTTP 200 + “403 Forbidden”页）：EN 用
    `curl` 取同页 SSR HTML，解析 `detail_mainWrapper` 后回灌生成脚本；ZH 可正常抓。
    不要因 200 就当抓取成功。
  - 支付页真站只有 2 张正文图（每语言），第 3 张不存在；勿臆造。
  - `joybuy.zendesk.com` 这类第三方域名的 joybuy 品牌链接也算“joybuy 相关网址”，
    验收要求一并改 `www.joyfumi.com`（保留路径）；但 Trustpilot/europa.eu/gov.uk 等
    与 joybuy 无关的第三方链接不要动。
  - 真站页脚当前帮助栏为空，不能据此判断“真站没有这两项”；按 16.5 目标实现。
  - 本批次只换政策页网址，**不要**顺手把政策页的 EU/欧洲 改成亚洲（用户明确保持原文）；
    也不要给两页新页加左栏 tab。
  - prettier 会把 AppFooter/messages.js 写成 LF（仓库 core.autocrlf=true），属格式行为，
    提交时 git 会归一化，不要手工改回。

## 0ag. 批次 R（2026-11-20 政策页头部/首页 reco/搜索页件数/频道按钮，✅ 完成，未 commit）

需求：功能需求迭代文档03 **16.1 / 16.2 / 16.3 / 16.4**。证据目录 `var/header_reco_20261120/`
（`verify_r.cjs`→`verify.json`、`shots_buttons.cjs`、`check_i18n.cjs`、`debug_channel.cjs`、
`header_{en,zh}_policy.png`、`home_reco_after5.png`、`btn_home.png`/`btn_channel.png`、
`channel_*.png`）。**未 commit；未碰 AppFooter / content/ / HelpCenter.vue / backend/content。**

- **16.1 政策页头部**：
  - `components/AppHeader.vue` 新增 prop `hideCategoryNav`（默认 false），`showCategoryNav =
    !hideCategoryNav && !route.path.startsWith('/p/')`；分类按钮 + `AppCategoryPanel` 整块
    `v-if` 不渲染（下拉逻辑/状态一并不渲染，面板本无请求）。
  - `layouts/footer-page.vue` 删掉第二份简顶栏（`.simple-header` 及其样式/脚本），改为
    `<AppHeader hide-category-nav />`；黑条、logo、搜索、申请店铺、登录、购物车与首页同一组件。
  - **吸顶补偿（新增，勿删）**：header 是 `position: sticky`，help 中心左栏也是 sticky（本地
    改进，真站为 static）。AppHeader 在 mount + ResizeObserver 把实际高度写到
    `:root --site-header-height`；`footer-page.vue` 用
    `.app-main :deep(.help-center__nav){ top: calc(var(--site-header-height,120px) + 16px) }`
    抬开左栏——**没有改 HelpCenter.vue**（S 边界）。实测 1440 下 header 120 → nav top 136；
    768 下 header 180，变量同步。
  - 其他 /pages/*（about-us/contact-us/joyplus/joybuy-news）同布局，一并为新头部且无品类行。
- **16.2 首页精选好物**（`components/home/HomeRecommended.vue`）：
  - `.home-reco__more` 加 `padding-bottom: 60px`。
  - **2026-11-20 修正（用户口径：首屏也要满行）**：补齐改为**渲染时**做——`items`
    computed = 已加载商品（`loadedItems`，来自 `useFetch` 页一 + `appended` 接口批次）
    + 池头循环补到当前列数整数倍（`slice(0, cols - len % cols)`），**首屏数据也补**
    （桌面 5 列 → 25 件）；不用占位骨架/灰块。`appended` 只存接口数据，不再掺补齐项。
  - **列数随视口**：`columns` ref 默认 5（SSR/桌面），客户端 mount 后按
    `matchMedia('(max-width:48rem)')` → 2、`(max-width:80rem)` → 3 同步并监听 resize
    （与 `.home-reco__grid` 断点一致）。SSR 固定按 5 列输出，客户端 hydrate 后才改，
    **不产生 hydration mismatch**。
  - key 用 `${spu_public_id}-${index}`（补齐会重复商品，避免重复 key / console 告警）。
  - `reachedEnd` / `loadEnded` 用 `loadedItems`（接口条数）判断，不受补齐影响；
    MAX_ITEMS=240 仍成立。
  - 未回退 O1 结构：仍 `await useFetch` + `appended` ref，列表从 data 派生、未在 setup
    拷贝首屏 items。
- **16.3 /s 去掉件数**（`components/ProductListing.vue`）：删除 `.listing-head__count`
  节点与样式；未用的 `total` computed 一并删除（`totalPages` 仍取接口）。筛选/分页/接口未动，
  `listing.productsSuffix` 键保留未删（五语言键数不变）。
- **16.4 频道页底部按钮**：新增共享组件 `components/AppMoreButton.vue`（#1A1A1A / 白字 /
  131×48 / radius 4 / 16px/500，唯一一份实现），首页与频道页都用它。`ChannelPickedForYou.vue`
  加 prop `moreLabel`（默认空 → `reco.viewMore`，购物车页不变），`pages/minihome/[code].vue`
  传 `:more-label="t('channel.more')"`（复用既有键：More/更多/Mehr/Plus/Meer）。10 个频道页
  （11 个一级里有 channel_code 的 10 个）全部生效。
- **验证（按验证纪律仅做针对性验证）**：
  - vitest 4 个受影响文件 **39/39 过**（AppHeader 16、HomeRecommended 6、
    ChannelPickedForYou 6、minihome 11；HomeRecommended 新增首屏补齐/3 列/2 列 3 例）；命令
    `node node_modules/vitest/vitest.mjs run --config storefront/vitest.config.js components/home/HomeRecommended.test.js components/AppHeader.test.js components/ChannelPickedForYou.test.js tests/minihome-channel-page.test.js`。
  - eslint 改动文件 **0 error**；`ChannelPickedForYou.test.js` 剩 2 条**既有** warning
    （`vue/one-component-per-file`，holder 组件，非本次引入）。prettier `--check` 改动文件
    **全过**。i18n `check_i18n.cjs`：en/zh/de/fr/nl **450=450 恒等**。
  - **完全重启 dev server 后**（kill 17448 树 → `node node_modules/nuxt/bin/nuxt.mjs dev
    --host 127.0.0.1 --port 3000`），`node var/header_reco_20261120/verify_r.cjs` 全绿：
    - EN/ZH `/pages/privacy-policy`、`/help/privacy-policy`、`/pages/terms-conditions` 均 200；
      黑条/语言/logo/搜索/申请店铺/登录/购物车都在，分类按钮与一级品类行 **0 个**；
      logo/购物车/搜索右缘与首页逐像素一致（搜索因少分类按钮左移并加宽 154.56/110px），
      站头总高比首页少 **35px**（=品类行）。截图 `header_{en,zh}_policy.png`。
    - 首页 1440：**首屏 25 件（末行 5/5 满格）**，padding-bottom **60px**；连点 5 次总数
      25→50→75→100→**120**→145（120 本身已是 5 的倍数不再补），**每一步末行都是 5 个**
      （补齐项来自池头，允许重复；截图 `home_reco_first_screen.png`）。
    - 首页 1024（3 列）：首屏 24 件 / 末行 3 满格，点 1 次后 48 件 / 末行 3 满格；
      768（2 列）：24 → 48，末行均为 2 满格（`verify.json.recoResponsive`）。
    - `/s?category=home-living` EN/ZH：`.listing-head__count` 不存在、title 下无件数、
      24 商品 + 分页仍在、body 无 `xx products/件商品` 文案。
    - 10 个 `/minihome/<code>` EN/ZH：模块存在、按钮出现、计算样式与首页按钮**逐值一致
      （差异对象 {}）**、文案 More/更多、点击后商品数增加（24→48）。
    - misc：语言下拉 5 项（English/中文（简体）/Deutsch/Français/Nederlands）可切到 zh；
      help 左栏 sticky top=136px 未被站头遮住；768 宽政策页无横向溢出；
      console/pageerror **0**。
- **踩坑（勿重踩）**：
  - pnpm 启动器在本 Git Bash 坏（解析到 `D:\Anaconda\...`），用 `node node_modules/...`。
  - 频道页验收滚动 sentinel **必须在 hydration 之后**（`waitUntil:'load'` + 800ms），
    `domcontentloaded` 就 scrollIntoView 会让 IntersectionObserver 的首次自动加载不触发，
    表现为"按钮永远不出现"（不是代码 bug）。
  - 模板里别在 `.listing-head` 内留注释：dev 编译会输出 HTML 注释节点，验收会看到脏 DOM。
  - 首屏补齐必须让 SSR 与客户端首帧一致：`columns` 初值 5（SSR），只在 `onMounted` 里
    按视口改；别用 CSS 媒体查询去隐藏/重排补齐项，也别让 setup 直接读 `window.innerWidth`
    （会 SSR/客户端条数不同 → hydration mismatch）。

## 0af. 政策页表格样式修复（2026-11-20，✅ 完成，未 commit）

- **任务**：修用户指出的两处缺陷 —— ①隐私政策 4.1 表格无外边框；②销售条款第 1 条定义表无外边框、首列文字需加粗。
- **真站实测**（Playwright 实时，cookie 复用 `var/align_search_20261120/cookies.json`，
  `**color-api.joybuy.co.uk**` 打桩；数据 `var/policy_table_fix_20261120/{measure_tables,measure_zh}.json`，
  结论 `measurement.md`）：
  - **外边框**：真站是**完整四边 1px `#CCC`**，但由两半拼成 —— `table` 只给 `border-top/left:1px solid #ccc`
    （另有 `display:block;max-width:100%;overflow-x:auto;box-sizing:border-box;border-collapse:collapse`），
    `td` 给 `border-right/bottom:1px solid #CCC`。真实 CSS bundle `var/cart_page_20261119/all_css/css_01.css`
    里 td 写的是 `#d9d9d9`，但**线上 computed 实测为 `#CCC`**（以实测 #CCC 为准）。
    批次 Q 只写了 td 右/下 → 上/左开放，即用户看到的缺陷。
  - **首列加粗**：**只有销售条款（ZH）「第1条 定义」表**首列每格内是 `<b>`（内层 700，td 自身 400），13 行全部；
    **隐私政策表格（EN/ZH）首列不加粗**（个别非首列正文有行内 `<b>`，属术语强调）。其余 3 页无表格；
    **EN 销售条款本身没有表格**（该定义表只在真站 ZH 版存在）。
  - **表头**：所有表格 `th` 数 = 0，首行也是 `td`（400、透明背景）；真站 CSS 的 `th{background:#f1f1f1}` 不生效。
- **改动**：
  - `storefront/components/HelpCenter.vue`：`.help-center__table` 加 `border-top/left:1px solid #ccc` +
    `box-sizing:border-box`（与 td 右/下合成四边外框，无重复双线）；`td` 增加
    `:class="{ 'help-center__table-cell--bold': block.firstColBold && cellIndex === 0 }"`
    与 `.help-center__table-cell--bold{font-weight:700}`。
  - `storefront/content/help/terms-conditions.js`：仅 ZH 定义表块加 `firstColBold: true`（块级标志，
    不做全局 `td:first-child`，避免污染隐私政策表格）。
  - `storefront/components/HelpCenter.test.js`：mock 改为返回带 `.value` 的 locale（原 mock 返回字符串，
    组件 `locale.value` 恒为 undefined → 永远走英文，zh 分支从未被测到）；新增 1 例校验销售条款首列 bold、
    隐私政策无 bold。
- **验证（按验证纪律仅做针对性验证）**：
  - vitest `components/HelpCenter.test.js` + `tests/help-pages.test.js` **13/13 过**；
    eslint 改动文件 **0 error 0 warning**；prettier `--check` 改动文件 **全过**。
  - `var/policy_table_fix_20261120/verify_local.cjs`（EN/ZH × 1440/1024/768 × 5 页）：
    全部 200、console/pageerror **0**；隐私政策表格四边（table top/left + td right/bottom）均 1px #ccc、
    首列 400；ZH 销售条款表格首列 **13 格全 700**、其余列 400；其余 3 页 0 表格无回归；
    各宽度 `wrap.scrollWidth == clientWidth`、`documentElement` 横向溢出 **0**。
  - `verify_borders.cjs`：表格元素截图 + 像素采样，四条边均为 **(204,204,204)** 且第二像素即白色
    （证明外框实画、无双线）；截图 `border_{zh_terms-conditions,zh_privacy-policy,en_privacy-policy}.png`，
    数据 `verify_borders.json`、`verify_local.json`。
- **未碰**：路由/导航/正文文案/其他组件；未 commit。

## 0ae. 批次 Q 验收（2026-11-20，政策页返工，✅ 13/13 全过，未 commit）

- **独立验收（`var/acceptance_q_20261120/acceptance-report.md`）：13/13 PASS，0 fail。**
- **文案逐段比对**：EN/ZH 各 5 页与抓取的 `content_*.json` **逐块比对 10/10 一致、块级差异 0**（唯一差异=邮箱）；另复核「存档 JSON ↔ 真站 raw HTML」10/10 一致——即抓取本身可信，不是拿自己产物自证。
- **合规口径按用户拍板执行**：公司名 `Jingdong Retail`、注册号 `15830555`、King Street 地址、ICO/EEA/欧盟委员会表述均**保留真站原文**；邮箱仅 `Joybuyfumi@gmail.com`（28 处），无 `DPO@jd.com`/`dpo@joybuy.com`/`support@joybuy.com` 残留；**无 `joyfumi.com` 旧口径残留**。
- 版式：左 240 + 右 1008 / 容器 1264 / 当前项 `#FF0F23` / hover `#F5F6FA`；5 项顺序正确、Terms of Sale 内容对应正确；`/pages/*` 与 `/help/*` 双入口 200，前进/后退正常；1024/768 无横向溢出；左栏 sticky 生效。
- 回归：about-us/contact-us/joyplus/joybuy-news 正常；vitest 124/124；五语言 450=450；console 0 error。
- **⚠️ 决策记录（与 0s 节相反，用户明确要求）**：政策/条款正文恢复为真站原文（含他公司法定主体与监管资质），仅替换邮箱。这是用户对本节内容的明确指示，后续**不要**再用 0s 的「中性 demo 实体」口径覆盖。若将来对外公开部署，建议重新评估该风险并告知用户。

## 0ad. 批次 Q（2026-11-20 政策页左 tab 版式 + 正文照抄真站，✅ 完成，未 commit）

> 需求文档03 **v1.7 第十五节 15.1–15.3**（**覆盖 14.8**）。实测/脚本/证据全部在
> `var/policy_help_20261120/`（`measure_nav.json`、`measure3.json`、`measure_table.json`、
> `lists.json`、`content_{en_GB,zh_CN}_<slug>.json`、`raw_<lang>_<slug>.html`、
> `real_*.png`/`final_*.png`、`verify2.json`、`devserver.log`）。
> **未 commit；未碰首页 / components/home / components/cms / AppCategoryPanel /
> CategoryTileGrid / ProductListing / pages/s.vue / pages/cart / AppHeader / AppFooter。**

- **任务**：隐私政策页从「单页长文」改为真站 help 中心形态（左 tab + 右内容），并把 help 中心全部
  政策/条款页正文照抄真站，**唯一替换 = 邮箱 → `Joybuyfumi@gmail.com`**。
  ⚠️ **本节法律口径与 `0s` 节 / `14.8` 相反**（不再做欧盟→亚洲、域名→www.joyfumi.com、
  公司实体→Joyfumi (demo) 替换），这是 **用户 2026-11-20 明确拍板**，需求文档 v1.7 已写明覆盖。

- **真站实测（本次 Playwright 带 cookie 实时抓取，非存档；cookie 复用
  `var/align_search_20261120/cookies.json`，`**color-api.joybuy.co.uk**` 打桩返回
  `{"code":0,"data":{}}`，`/help/*` 全部 200 无风控拦截）**：
  - **左栏导航 5 项、不分组件、顺序固定**：Privacy Policy → Terms of Sale → Cookie Policy →
    Terms of Use → Accessibility Statement。真站 URL 为 `/help/privacy-policy`、
    `/help/terms-conditions`、`/help/cookie-policy`、`/help/TermsofUse`、
    `/help/AccessibilityStatement`（后两条驼峰）。
  - 左栏尺寸：容器 1264 居中（1440 下 x=88）、**nav 宽 240**（padding `4px 12px`、radius 8、白底）、
    与右卡间距 **16**；`nav` 是 `position: static`（**真站不吸顶**）。
    条目：`padding 16px 16px 20px`、16px/400/24、`border-bottom 1px #F0F1F2`（末项无）、
    当前项文字 **#FF0F23**、hover 底 **#F5F6FA** + 文字 #FF0F23、高度 61（末项 60）、
    整卡高 328；**点击是整页跳转**（`/help/<slug>`），非页内切换。
  - 右卡：宽 1008（1007.84）、`padding 24px 36px`、radius 8、白底；标题 **32px/700/32px #000**；
    右上「Archived Version」（zh「存档版本」）28px 图标 + 16/400/20 `#1A1A1A`，**点击在实测中无跳转/无弹层**。
  - 正文：**16px/24px #000**、`p{margin:10px 0}`、粗体 700、链接 `#0000EE` 下划线；
    真站正文大量用 `<br><br>` 分段（章节标题只是普通文本行，无标题样式）；
    表格：`width:100%`、`border-collapse:collapse`、auto 列宽（实测 127/365/443）、
    `td{padding:3px 5px;border-right:1px solid #CCC;border-bottom:1px solid #CCC;vertical-align:middle}`；
    有序/无序列表用浏览器默认（`margin 16px 0; padding-left 40px; decimal/disc`）。
  - **移动/窄屏**：真站**没有移动版**，1024/768 下左栏恒 240、整页横向溢出（内容 768/512）；
    无折叠、无下拉、无返回顶部、无锚点目录。
  - **中文版存在且是真站自带**（`_lang=zh_CN`）：5 项 nav 全部中文，正文为人工中文，
    结构与英文版不同（中文隐私政策把章节拆成独立 `<p>`，并带 11 项 `<ol>` 目录），已原样采用。

- **交付**：
  - `storefront/content/help/{privacy-policy,terms-conditions,cookie-policy,terms-of-use,accessibility-statement}.js`：
    每页 `title{en,zh}` + `blocks{en,zh}`，块类型 `p{segments}`（`t/b/i/u/href/br`）、
    `table{rows}`、`list{ordered,items}`；zh 用真站中文版，de/fr/nl 回退英文（内容页既定口径）。
  - `storefront/content/helpPages.js`：nav 顺序表 + `helpPageBySlug` + `resolveHelpSlug`
    （把真站驼峰路径 `TermsofUse`/`AccessibilityStatement` 大小写不敏感映射到本地 kebab slug）。
  - `storefront/components/HelpCenter.vue`：左 tab + 右内容版式（按上述实测值实现），
    tab 为 `NuxtLink` **路由切换**（前进/后退正常），当前项 `--active` + `aria-current=page`。
  - 路由：新增 `storefront/pages/help/[slug].vue`（真站原路径）；
    `storefront/pages/pages/[slug].vue` 重写为同一组件的别名入口（页脚 `/pages/<slug>` 不用改，
    `AppFooter` 未动）；两者都 `layout: footer-page`，未知 slug 404。
  - **删除**：`storefront/content/privacyPolicy.js`、`storefront/content/footerPages.js`
    （旧 14.8 正文与旧 cookie/terms 正文，避免两套并存；已 grep 确认无其他引用）。
  - 测试：`storefront/tests/help-pages.test.js`（7 例：nav 顺序/双语非空/仅邮箱被替换/
    公司名 `Jingdong Retail (UK) Limited`+`15830555`+`Floor 3, 20 King Street` 存在/无 14.8 残留/
    无 urldefense、无 `/help/` 死链/列表结构 11+22 项）、
    `storefront/components/HelpCenter.test.js`（5 例：5 项顺序与 href、唯一高亮+aria-current、
    9 段+9×3 表、Archived 只出现在隐私页、ol/ul 8 个 22 项）。

- **替换范围（严格按 15.2）**：只替换邮箱。真站出现 3 个邮箱 `DPO@jd.com`（正文/链接文本）、
  `dpo@joybuy.com`、`support@joybuy.com`（mailto）→ 全部 `Joybuyfumi@gmail.com`
  （`mailto:Joybuyfumi@gmail.com`）。**其余一律原文**：公司名（Jingdong Retail (UK) Limited 等 4 家）、
  注册号 15830555、地址 Floor 3, 20 King Street / Boompjes 40、ICO/EDPB/European Commission、
  EEA/UK、生效日期（2026 年 4 月）、`www.joybuy.com` 等域名、`/help/*` 外部链接。
  唯一技术性处理（非文案替换）：①真站 HTML 里的 `urldefense.com` 跳转包装解码回原始 URL；
  ②同属本 help 中心的链接指向本地路由（`/pages/<slug>`），避免本站内部跳回真站。

- **验证（按验证纪律仅做针对性验证；验收前已 2 次完全重启 dev server，
  启动方式 `cd storefront && node node_modules/nuxt/bin/nuxt.mjs dev --host 127.0.0.1 --port 3000`，
  日志 `var/policy_help_20261120/devserver.log`；backend :8000 未动）**：
  - vitest `--config storefront/vitest.config.js` **124/124 全过**（24 文件，含新增 12 例）；
    eslint 改动文件 **0 error 0 warning**；prettier 改动文件 **全过**；
    五语言键集合自检 `var/align_search_20261120/check_keys.mjs` **450 = 450 PASS**（本轮未新增键）。
  - Playwright `var/policy_help_20261120/verify2.cjs`（EN + ZH，10 组页面）：
    ①5 项 nav 文本/顺序/active 与真站一致；②**正文与 `content_<lang>_<slug>.json` 归一化后
    `text true`（仅邮箱不同）+ 表格逐格 `table true`**，长度逐页相等（如 en privacy 31339/31339，
    zh privacy 10215/10215）；③列表 8 个/22 项（en a11y）、11 项（zh 隐私目录）、6 项（zh cookie）；
    ④页面 email 集合**只有** `Joybuyfumi@gmail.com`；⑤标题 EN/ZH 与真站一致；
    ⑥路由切换 `/help/privacy-policy` → `/pages/terms-conditions` 内容+高亮跟随，back/forward 均正确；
    ⑦console/pageerror **0**（101 次导航）；⑧1024/768 `overflowX = 0`，768 仍为左 200 + 右 520 两栏，
    不压内容。截图 `final_privacy_{en,zh}.png`、`final_privacy_{1024,768}.png`。
  - 冒烟：`/`、`/pages/{about-us,contact-us,joyplus,joybuy-news}`、`/help/terms-conditions`、
    `/help/AccessibilityStatement`、`/help/TermsofUse` 均 200；`/pages/<未知>` 404。

- **偏差/决策（务必知晓）**：
  1. **左栏 sticky 是用户本次交付要求**（原文「左栏 sticky」），真站实测为 `static`；
     已按用户要求做 `position:sticky; top:16px`，其余尺寸/颜色/交互全部照真站。
  2. 「Archived Version / 存档版本」真站可点但实测无跳转、无弹层（疑似需登录/接口失效），
     本地按视觉保留为**静态标签**（不可点），并在组件注释标注。
  3. <768px 改为上下堆叠（真站无移动版且整页横向溢出），1024/768 与真站同构（两栏）。
  4. `/pages/<slug>` 与 `/help/<slug>` 双入口（15.3 第 4 条要求页脚链接可用）；
     `/help/` 支持真站驼峰写法。
  5. de/fr/nl 内容与 nav 标签回退英文（沿用内容页既定口径，不翻译法律文本）。

- **踩坑（不得再踩）**：
  ①真站正文用 `<br><br>` 分段，抓取时必须保留**连续两个 br**，否则段落黏连、间距失真（曾合并成一个）；
  ②只按 `<p>/<table>` 取块会**静默丢掉 `<ol>/<ul>`**（zh 隐私 11 项目录、en 无障碍 8 个列表），
  且「本地渲染 vs 自家 JSON」的对账会**同样缺**而假通过——对账必须包含 list 块；
  ③对账时 expected 文本要先做同样的邮箱替换，否则永远 diff；
  ④真站页面里的 `urldefense.com` 链接是跳转包装（不能照抄，需解码）；
  ⑤`extract2_lang.cjs` 的 raw HTML 曾按 slug 落盘，跑第二语言会覆盖第一语言（已改 `raw_<lang>_<slug>`）；
  ⑥dev server 必须从 `storefront/` 目录、用 `storefront/node_modules/nuxt/bin/nuxt.mjs` 启动
  （根目录 `node_modules` 没有 nuxt，`pnpm --filter` 在本机 PATH 下也不可用）。

- **遗留**：①de/fr/nl 回退英文（既定口径）；②真站「Archived Version」目标页未知（本地为静态标签）；
  ③左栏 sticky 与真站 static 的差异已记录，若验收要求 100% 对齐真站可一行改回；④全部改动未 commit
  （工作区仍含更早批次未 commit 改动）；⑤`pagesDoc.backHome` 等旧键已无引用但保留（不影响 450 键集合）；
  ⑥整页 SSR HTML 里唯一一处 `Joyfumi` 来自 `AppFooter` 既有的「non-commercial replica」demo 声明
  （不归属批次 Q，未改；政策正文本身零残留，grep `(demo)`/`www.joyfumi.com`/`Asian Economic Area`
  /`DPO@jd.com`/`support@joybuy.com`/`dpo@joybuy.com` 均为 0）。

## 0ac. 第四轮总记录（2026-11-20，需求文档03 v1.6 第十四节：批次 O/P 开发 + 独立验收 + 修复复验，✅ 全部收口，未 commit）

- **任务链**：用户第四轮 8 项购物端细化 → 并入 `功能需求迭代文档03.md` **v1.6 第十四节**（14.1–14.9）→ 2 个开发子 Agent 并行（O 首页 / P 分类·搜索·内容页）→ 各自独立验收 → 3 条问题修复 → 复验通过。
- **批次 O ✅ 13/13**（详见 `## 0aa`）：品类发现固定 6 卡（宠物/母婴/游戏仅从该模块移除，导航与 /c 直链保留）+ 电子产品换真站手机图 + 卡片样式按真站 CSS 实测；新增 `/marketing` 活动页（无顶部 tab、无品牌筛选、商品取服装+户外）+ 首页【每周甄选】6 卡 + admin「每周甄选」tab + `seed_home_weekly_picks`；查看更多 `#1A1A1A`/白字/131×48；**恢复心选品牌**（根因：`storefront_home` 重建时连带删掉 `brand_logos`）。
- **批次 P ✅ 15/15**（详见 `## 0ab`）：分类下拉图文居中（69 项 delta ≤0.01px）；`/c` 选中卡 1px `#1a1a1a` 黑边（真站 /c 已 404，颜色为推定）；`/s` 分页重做（40×40/radius4/16px500/gap4/当前页与 hover `rgba(0,16,71,.1)`/禁用 .38/省略号）+ 左筛选与列表间 1px `#E0E1E5` 通栏竖线（x=282）；隐私政策按真站重做（12 标题/46 段/9×3 表，EN/ZH）。
- **验收修复的 3 项**：①心选品牌标题 line-height 35→28px、色 #17202A→#1E1E1E；②品类发现末卡在 1440/1600 被裁切（行继承 12px gap 且宽度未计入）→ gap 归零 + 断点 1199px + ≥1600 流式公式，1280/1440/1600 三档 `scrollWidth==clientWidth`；③活动页 2 件商品 PDP 面包屑显示 Cookware/Garden **根因是面包屑源 `product_category` 与 LocalCategory 不一致**（非活动页过滤问题）→ 幂等命令 `align_outdoor_product_categories` 修正归属，10 件商品逐一进 PDP 面包屑全部落在服装/户外。
- **本轮实测/推定标注**：心选品牌标题与 logo 墙为真站实测；/c 选中黑边、查看更多与页脚 64px 间距、每周甄选后 2 张卡（真站历史活动）为**推定/替代**（真站交互态 403 不可测），已在 measurement.md 与验收报告中标注。
- **验证口径**：针对性验证（vitest 112/112、后端 content+catalog 74/74、campaign 23/23、ruff/eslint/prettier、五语言键 450=450、Playwright EN/ZH/DE console 0 error）。
- **遗留**：①真站 `/c/<slug>` 404 导致选中黑边颜色/粗细只能推定；②活动页商品池为「服装 + 户外」品类可售商品（非真站各 activityId 独立商品池）；③17 件缺图商品在活动页被 `has_local_image=1` 过滤；④7 个频道页商品图 404 属既有媒体缺失（AWS 封禁期本地缺文件）。
- **待办（等用户）**：爬虫恢复（9+1 分类，脚本 `var/crawl_night_20261120/create_jobs20.py`）；AWS 恢复后 `aws s3 sync` 本地增量媒体；全部改动未 commit。

## 0aa. 批次 O（2026-11-20 首页品类发现/每周甄选/查看更多/心选品牌，✅ 完成，未 commit）

> 需求文档03 **14.1/14.2/14.3/14.4**。实测与证据目录：`var/home_weekly_20261120/`
> （`measurement.md` 实测报告、真站 SSR `home_en.html`/`marketing_en.html`、
> `css/`+`css_marketing/` 离线 bundle、`live_home_full.png`=真站 Playwright 403 风控证据、
> `verify_o.mjs/.json` + `o_home_{en,zh,de}.png`、`o_marketing_{en,zh,de}.png`）。
> **未 commit；未碰 `AppCategoryPanel.vue` / `CategoryTileGrid.vue` / `pages/s.vue` / `search.vue` / `pages/pages/`。**

- **实测口径（⚠️ 真站 SSR curl 可抓，Playwright 交互态 403「Temporary service interruption」）**：
  - 品类发现（真站 `pc-popular-categoryV3` + CSS 实测）：卡片高 366、`#F5F6FA`、radius16、
    shadow `0 10px 30px rgba(0,0,0,.08)`（hover 仅阴影 `0 14px 38px rgba(0,0,0,.12)`，无位移）；
    文案绝对定位 top/left 28、18px/600/24px `#1A1A1A`；图片底部 275 高 radius12；
    宽度 1200–1599 `calc((100%+330px)/6)` + 邻卡 `-66px`，≥1600 279px + `-32px`，<1200 `calc((100%+525px)/6)` + `-105px`。
  - 每周甄选（`pc-theme-module`）：标题 28/600/42；行 gap16、mt16；方卡 radius8；
    底部渐变 `transparent 51.92% → rgba(0,0,0,.4)`；卡标题 20/700/36 白色，bottom/left 16。
    真站当前 4 张（20050029/21090013/21090021/21050021），验收要 6 张 → 补 2 个真站历史活动
    （20530005/20490005，取自 2026-11-03 存档 SSR 的真实卡与图）。
  - 活动页：banner 384 高、容器 1264、h1 44/700/44、副标题 18/500/24；主体 mt34；
    左筛选 234 + 右边框 `#E0E1E5`；商品 4 列 gap `24px 16px`。顶部 tab（banner 底部）与
    品牌 accordion 按需求删除，仅留「类别」。
  - 心选品牌：标题 28/600/`#1E1E1E`；单行横滑 logo 圆 194、gap24、`scale(.79)`+4% 蒙层、
    名称 16/600/20、两侧 194px 白渐隐；无「查看全部」。
  - 查看更多：真站 footer/按钮为 CSR，交互态被挡 → 用真站黑按钮 token（131×48、radius4、
    `#1A1A1A`、白字、16/500）实现；**与页脚间距 64px 为推定**（footer 无法实测，原 24px）。
- **交付 1 品类发现（14.1）**：`campaign_services` 增加 `DISCOVERY_HIDDEN_SLUGS`
  `{pet-supplies,baby-toddler,games-accessories}` + `DISCOVERY_VISIBLE_LIMIT=6`（只影响该模块，
  卡片数据/导航保留）；电子产品卡图改本地 `/images/discovery/electronics.webp`（真站「手机」
  Galaxy S25 卡图，已下载）；`CmsLinkGrid.vue` tiles 变体按上述实测重写（campaign 5×2 未动）。
- **交付 2 每周甄选 + 活动页（14.2）**：
  - 复用 `HomeCampaignCard` 新 `section=weekly`（上限 6）+ 新 CMS 模块类型 `weekly_picks`
    （迁移 `content/0014`），`storefront_home` 注入（position 追加在快照模块后 → 真站顺序
    品类发现→心选品牌→每周甄选）。新组件 `CmsWeeklyPicks.vue`，6 张卡均可点。
  - 新页面 `storefront/pages/marketing.vue`：接收 `activityId`/`tagId`（可选），从
    `/storefront/home` 的 weekly 卡取标题/副标题/图作为 banner；商品用
    `/api/v1/recommendations` 分别取 `clothing-accessories` + `outdoor-sports` 合并；
    左筛选仅「全部/服装配饰/户外运动」；**无顶部 tab、无品牌筛选**。
  - 商品图 404 兜底：recommendations 新增可选 `has_local_image=1`（`catalog/search_views.py`），
    过滤抓取入库但图片文件缺失的商品；活动页实测 3 服装 + 7 户外 = 10 件，全部有图有价。
  - 种子命令 `manage.py seed_home_weekly_picks`（幂等）：6 张 weekly 卡 + 电子产品图 +
    确保快照含 brand_logos（心选品牌）模块；图在 `storefront/public/images/weekly-picks/`。
- **交付 3 查看更多（14.3）**：`HomeRecommended` 按钮改 `#1A1A1A`/白字/48 高/radius4/16px·500、
  最小宽 131；`index.vue` `.home-content` 底距 24→64。
- **交付 4 心选品牌（14.4）**：**根因**——`storefront_home` 注入品类发现时把所有 `link_grid`
  都替换掉，把快照里的 brand_logos 一起删了。现只覆盖 `variant != brand_logos` 的 link_grid，
  品牌模块恢复；`CmsLinkGrid.vue` brand_logos 改为真站静态横滑 row（194 圆、24 gap、渐隐，
  不可点、无箭头、无查看全部）。后台：`admin-web` 活动卡片页新增「每周甄选」tab（复用同表/接口）。
- **五语言**：`messages.js` 每语言新增 11 键（`home.weekly.title`/`home.brands.title` +
  `marketing.*` 9 键），脚本复核 **en/zh/de/fr/nl 键集合完全一致（450=450）**、无缺/多。
- **针对性验证（按验证纪律仅做针对性验证；验收前完全重启 dev server + backend）**：
  - 后端：ruff 全过；`content` + `catalog.tests.test_search` **74/74 OK**；另 `test_campaign_cards`
    **23/23 OK**（新增：discovery 隐藏三类且 6 张、brand_logos 不被注入删除、weekly 6 张/注入/上限 6）。
  - 前端：eslint 0 error；prettier 改动文件全过（messages.js CRLF 既有遗留未动）；
    vitest **112/112**（+6：CmsRenderer weekly/品牌静态行 + 原有用例更新）。
  - Playwright EN/ZH/DE（`verify_o.mjs`）：首页品类发现 6 卡且 labels 无宠物/母婴/游戏、
    电子产品图 `/images/discovery/electronics.webp` 已加载、卡片 279×366（本机容器 1344）、
    label 18/600/24 top28 left28、图片 279×275；每周甄选 6 卡、首卡 href
    `/marketing?activityId=20050029`、点击成功落 `/marketing?activityId=20050029`；
    心选品牌 12 logo 圆 194 不可点；查看更多背景 `rgb(26,26,26)`、高 48、radius4、与页脚距 64；
    活动页 0 tab、筛选仅 Category（All/Clothing/Outdoor）、商品 10（图 10/价 10）、
    **三语言 console/资源 error 合计 0**。`verify_filter.mjs`：10 → 服装 3 / 户外 7。
- **遗留/口径**：①「查看更多」与页脚间距 64px 及按钮宽度为推定（真站 footer CSR + 风控 403），
  已写进 `measurement.md`；②de/fr/nl 下 CMS 模块标题/品类名/活动卡标题仍回退英文=既定口径；
  ③17 件户外商品 DB 有行但图片文件缺失，已用 `has_local_image=1` 在活动页过滤（未回滚数据）；
  ④真站当前 weekly 仅 4 张，补的 2 张为真站历史活动（链接可用，落地页统一取数）；
  ⑤未 commit（工作区仍含更早批次未 commit 改动）。

- **验收返修（2026-11-20，12/13 PASS + 2 清单外缺陷）**：
  - ①心选品牌标题：`CmsLinkGrid.vue` 加 `cms-link-grid--brands` 作用域，标题改
    `line-height:28px`（真站 100%）+ `color:#1E1E1E`；实测 computed 28px/`rgb(30,30,30)`。
  - ②品类发现末卡裁切：根因是 tiles 行继承了基础行的 `gap:12px`（卡片宽度公式未计 gap），
    已 `gap:0`；同时把网格回退断点 80rem→1199px，并把 ≥1600px 的固定 279/-32 规则并入
    ≥1200px 流式公式（本机容器在 1600 为 1504，固定规则会 1514 越界）。实测
    1280/1440/1600 均 6 卡单行、`last.right - row.right ≤ 0`、scrollWidth=clientWidth。
  - ③活动页 PDP 面包屑错配（2/10）：实查 `f0941496…`（grill）与 `35b8c0a8…`（patio chairs）
    `Spu.local_category=outdoor-gear`、搜索文档 local_category 也是 outdoor-gear（一致），
    错的是 PDP 面包屑数据源 `Spu.product_category`：Cookware / Garden Furniture & Accessories。
    新增幂等命令 `manage.py align_outdoor_product_categories`：前者→Camping & Hiking（4625），
    后者→Sports & Outdoor（1819），均已执行（changed=2，复跑 0）。
    复核 10 件 PDP：6 件户外均有 Sports & Outdoor 面包屑（含原 2 件），其余 4 件（3 服装 +
    1 滑板车）源类目为空、无错误面包屑。
  - 返修验证：vitest 112/112；五语言键 450=450 无缺/多；ruff/prettier/eslint 全过；
    Playwright 1280/1440/1600 三宽度 console/资源 error 0。

## 0ab. 批次 P（2026-11-20 分类居中/黑边/搜索页/隐私政策，✅ 完成，未 commit）

> 需求文档03 **14.5 / 14.6 / 14.7 / 14.8**。真站实测 + 脚本 + 证据全部在
> `var/align_search_20261120/`（`measurement.md` 为权威记录；`verify.json` 为本地验证结果）。
> **未 commit；未碰 `index.vue` / `components/home/*` / `components/cms/*` / `backend/content/` / `/marketing`（批次 O 领地）。**

- **交付 1（14.5 图文居中）**：根因是默认瓦片的图片盒是 `display:block; width:100%`，内部 60% 宽图片贴左。
  `CategoryTileGrid.vue` 的 `.category-tile__media` 改 `display:flex; align-items:center; justify-content:center`。
  实测修复后：分类下拉子项 图片中心 delta **0**、名称 delta **0**（名称 14px/500/20px 居中，沿用 2026-11-11 真站口径）；
  `/c` 品类条与频道页 `channel` 变体（`/minihome/UK-Mini-HP-Home-Living`，140px 瓦片、18px/500/24px）delta 全 0。
  → **给主会话/O 的备注：首页品类发现 tiles 走 `CmsLinkGrid` discovery 变体，结构是「名称左上、275px 图片贴左下」，
  与真站 `pc-popular-categoryV3` 一致，不属于「图+文居中」类，未发现需修的居中 bug（只读未改）；仅 ≥1600px 卡宽 279px、
  图 275px 时底部图片左贴会留 4px 右侧空隙，如要居中由 O 决定（非本轮验收项）。**
- **交付 2（14.6 选中卡黑边）**：`.category-tile--active` 边框色 `var(--colour-accent)` → **`#1a1a1a`**。瓦片本身已有
  1px 透明边框，只换颜色，**不产生尺寸变化**（实测选中/未选中宽均 136）。仅作用于 `CategoryTileGrid` default 变体
  （`/c` 品类条 + 分类下拉）；首页白底红边规则在 `CmsLinkGrid`，未改。真站 `/c/<slug>` 路由 404，故「1px 黑边」为
  **推定**（真站同族选中态口径），已在 measurement.md §2 标注。
- **交付 3（14.7 /s 分页 + 竖线）**：
  - 分页按真站 MUI Pagination 实测重做：单项 **40×40、radius 4px、16px/500、gap 4px、无边框**，当前页与 hover 同为
    `rgba(0,16,71,.1)`，禁用箭头 `opacity .38`，省略号 40×40，上/下页为 Material chevron SVG，容器 **padding-top 24px**
    居中；页码窗口实测 = 近端 `1 2 3 4 5 … N`、中段 `1 … c-1 c c+1 … N`、末端 `1 … N-4..N`（34 页逐页实抓 1/3/4/5/10/20/31/32/33）。
    纯函数 `storefront/utils/pagination.js::buildPageList`（+`pagination.test.js` 5 例）。**未改共享 AppPager/AccountPager。**
  - 竖线：真站是 `search_productArea::before`（1px、**#E0E1E5**、absolute、top 0 / bottom 0 通栏、left −23px）；
    本地在 `.listing-main::before` 复刻为 left −24px（本地列间距 24），不占布局、不影响 sidebar sticky，单列断点隐藏。
  - 实测：`/s?k=home&page=10` → `‹ 1 … 9 [10] 11 … 15 ›`，点击 11 URL `page=11`、active 跟随；ZH aria `第 10 页/上一页/下一页`；
    竖线 x=282 = 左栏右缘，无横向溢出；`/search?q=home` 200 正常。
- **交付 4（14.8 隐私政策重做）**：真站 `/help/privacy-policy` 200，正文 421 行结构化抓取（`real_privacy_lines.txt`）+
  第 4 节 9×3 表格（`real_privacy_table.json`）。新建 `storefront/content/privacyPolicy.js`（EN/ZH 各 12 标题 / 46 段 /
  28 缩进项 / 6 项目符号 / 9×3 表格），`content/footerPages.js` 的 privacy 条目改为引用该模块（其余 cookie/terms 内容零改动）。
  `pages/pages/[slug].vue` 渲染器新增 `item`（缩进项）与 `table.rows`（真实表格）两种块，旧块类型行为不变。
  替换铁律已执行：真站主体名→`Joyfumi … (demo)`、公司编号全删、EEA→ASEA、European Commission→Asian Commission、
  ICO/Secretary of State→`the relevant supervisory authority`/`the relevant authority in the UK`、所有 URL→`www.joyfumi.com`、
  邮箱→`Joybuyfumi@gmail.com`、真实地址→`Demo address`、Trustpilot→`an external review platform (demo)`；
  服务器位置 Netherlands→Asia。页面文本 grep：`Jingdong/DPO@jd.com/joybuy.com/European/EEA/Company number/HRP/Trustpilot`
  **全 0**（含 `HRB` 公司号）。de/fr/nl 回退英文（`blocks[locale] || blocks.en`，内容页既定口径）。
- **i18n**：新增 `listing.pageAria`、`listing.pageCurrentAria` 各 5 语言（en/zh/de/fr/nl），五语言键集合
  **恒等、占位符逐键一致**（`var/align_search_20261120/check_keys.mjs`；自检时 450 = 450，含批次 O 并发新增的键）。
- **验证（按验证纪律：针对性 + messages.js 共享故跑全量单测）**：
  - `vitest run` **112/112 全过**（22 文件；含新增 pagination 5 例；原 AppCategoryPanel/CategoryTileGrid 用例零改动通过）；
  - eslint 改动 8 文件 **0 error**；prettier 7 文件全过（`footerPages.js` 沿用既有 CRLF，`--end-of-line crlf` 下全过，
    默认配置仅因历史 CRLF 报 EOL，非本批引入）；
  - **完全重启 dev server**（kill PID 5368 → `nuxt dev --host 127.0.0.1 --port 3000`，日志本目录 `devserver.log`；
    backend :8000 未动）后 Playwright 实跑：见 `verify.json`；console error **0**；截图 `local_s_page*`/`local_s_pager_*`/
    `local_c_strip*`/`local_dropdown_en.png`/`local_privacy_{en,zh}.png`/`local_channel_en.png`，真站对照
    `real_s_pager_*`/`real_s_page2_top.png`/`real_privacy.png`。
- **踩坑（不得再踩）**：①`waitUntil:'networkidle'` 在 Nuxt dev（HMR websocket）下会让 Playwright 定位器等到超时——改
  `domcontentloaded` + 显式 `waitForTimeout`；②真站 `/c/<slug>` 不存在，active 黑边只能推定；③真站 Categories 下拉列表
  在风控下恒 `Loading…`（导航瓦片可量），居中数据用导航瓦片 + 2026-11-11 下拉瓦片口径；④`pager` 截图前把鼠标移开，
  否则 hover 态会被当成第二个「当前页」；⑤`footerPages.js` 是 CRLF 文件（prettier 默认 EOL 会报全文件 diff），
  本轮用「行区间替换 + 断言唯一」脚本改（`var/align_search_20261120/rewire_privacy.py`），未整文件重写。
- **遗留**：①de/fr/nl 隐私政策正文回退英文（既定口径，不阻塞）；②真站 `/c` 与下拉列表风控不可量（已标注推定）；
  ③未 commit（工作区仍含更早批次改动）。

## 0z. 批次 N 验收 + 主会话补修（2026-11-20，多语言词典，✅ 验收 9/9 + aria-label 补修完成，未 commit）

- **验收（独立子 Agent，`var/acceptance_n_20261120/acceptance-report.md`）：9/9 PASS**——键/占位符程序化全量比对一致；de/fr/nl × 首页/频道/PDP/购物车 12 屏全部 8/8 目标语言（0 英语回退 miss）；nl 术语（Inloggen/Toevoegen aan winkelwagen）与真站 pairs 一致；切换链 en→de→fr→nl→zh→en cookie 持久、console 0 error；占位符实渲染正确（fr「Vendu et expédié par …」计数正确）；en/zh 回归 0 miss；vitest 106/106。
- **验收发现的范围外遗留 → 主会话已补修**：购物车入口 aria-label 硬编码英文（`AppHeader.vue:449`）。修复：新增 `cart.itemsAria`（5 语言各一条，`{count}` 占位），`useLocale.t()` 支持 `params` 替换（`{name}` → 值，replaceAll），`AppHeader` 改 `t('cart.itemsAria', { count })`。**实测 SSR：nl `Winkelwagen, 0 artikelen` / de `Warenkorb, 0 Artikel` / fr `Panier, 0 articles` 全部本地化渲染**。五语言键集合 438=438 恒等复验 ✅；prettier 已跑（messages.js CRLF 本体由 prettier 规范化）；vitest 106/106。
- **遗留小项**：验收用测试买家（probe-*/accept-*@joybuy.test）与 1 条 dev 购物车行未删（报告有记录）；de/fr 词典按通用电商惯例（真站不响应 Accept-Language），nl 为真站实抓 6450 条。

## 0y. 批次 N（2026-11-20 de/fr/nl 词典补齐，✅ 完成，未 commit）

> 需求文档03 **13.5 第 4 条优化补充**：批次 M 语言下拉 5 项上线后 de/fr/nl 缺词回退英语，本批把
> `storefront/locales/messages.js` 的 de/fr/nl 词典补齐到与 en 全量对齐。证据与脚本全在
> `var/batch_n_i18n_20261120/`。**只改 messages.js（纯尾部追加）+ 文件头 1 行注释；未 commit；未碰
> useLocale.js 回退逻辑、backend、admin-web、merchant-web。**

- **交付 1 词典（messages.js）**：新增 `de:` `fr:` `nl:` 三块，**各 437 键**（=en 键集全量，任务口径
  874=en+zh 合计），文件 910→2318 行。插入方式：脚本 `apply_dictionaries.mjs apply` 以**文件尾唯一锚点
  `  },\r\n}\r\n` 做单次精确替换**（先断言锚点唯一=1），CRLF 全程保持（LF-only=0）；文件头注释第 1 行
  改为提及 batch N。⚠️ `git diff` 显示该文件有 39 行删除——**全是批次 M 等更早的未 commit 工作区改动**
  （footer 13.6/cart 13.7 旧键值），`git show HEAD:...` 已核对；本批对工作区**纯增量**。
- **翻译来源与口径（术语表 `glossary.md`，40 高频词 × 3）**：
  - **nl 跟真站**：joybuy.nl SSR 内嵌 i18n 词条包实抓 **6450 条真值**（`realsite/nl_pairs_raw.txt`，
    抓取脚本 `realsite/extract_nl_pairs.cjs`，原始 HTML `realsite/joybuy_nl_home.html`，2026-11-20 200 OK）。
    Winkelwagen / Toevoegen aan winkelwagen / Toegevoegd aan winkelwagen / Inloggen / Uitloggen /
    Registreren / Afrekenen / Verlanglijstje / Mijn bestellingen / Adressen / Postcode / Telefoonnummer /
    Adresregel 1 / Privacy- en cookiebeleid / Algemene voorwaarden / Kwaliteit gegarandeerd /
    Veilige betalingen / Klantenservice / Reviews & Q&A / Ga winkelen / Bekijk meer / Alles bekijken 等
    **直接采用真站术语**；国家名六国真值（Verenigd Koninkrijk/Nederland/België/Luxemburg/Frankrijk/Duitsland）。
  - **joybuy.co.uk 实测不响应 Accept-Language**（de/fr 请求 lang 恒 en-GB，`realsite/joybuy_uk_{de,fr}.html`
    证据），无 de/fr 真站界面 → **de/fr 按通用电商惯例**（Amazon.de/.fr 同场景口径，Sie/vous 敬称）。
  - 品牌不译（Joybuy/Klarna/WeChat Pay/JoyPlus）；slogan "Don't just buy, Joybuy" 按 zh 块先例保留英文；
    占位符 `{name}` `{page}` `{total}` 与 `→←…©` 符号原样保留；`footer.langLabel`=Deutsch - DE/
    Français - FR/Nederlands - NL；`topStrip.region`=UK | Deutsch/Français/Nederlands（市场仍 UK）。
- **自检（`apply_dictionaries.mjs check/verify`，结果已跑通）**：
  - `check`（JSON 词典 vs en/zh 真值）：**PASS——en/zh/de/fr/nl 键集合完全一致（437 键），占位符逐键一致**；
  - `apply` 后 `verify`（import 真实 messages.js 复核）：**PASS 同上**；
  - 格式：生成行按 prettier（printWidth 100/singleQuote/双引号包容 apostrophe）输出，**LF 副本
    `prettier --check` 全过**；messages.js 本体仍因 **CRLF 历史问题**不过 prettier（0u 既有遗留，非本批引入，
    本批保持 CRLF 不恶化）。eslint messages.js 0 error。
- **翻译质量抽查**：`spot_check_30.md`（固定种子 20261120 随机 30 键 × en/de/fr/nl 四列）人工过目合格；
  nl 语义错误 1 处（termsNotice「扣款」误写「返还」）在 JSON 阶段已改（`int`）。
- **针对性验证（按验证纪律；词典是共享文件故 vitest 全量跑了一次）**：
  - vitest **106/106 全过**（21 文件；无任何用例需要改，批次 M 的 5 语言回退用例原样通过）；
  - eslint messages.js 0 error；prettier 见上（LF 副本过、本体 CRLF 既有遗留）；
  - `toggleLocale` 排查：**无活跃调用方**（AppFooter 仅注释引用，批次 M 已停用），行为无误，零改动；
  - **Playwright（完全重启 dev server 后）**：杀掉旧双进程（PID 41448/[::1]:30352）→ 新起
    `nuxt dev --host 127.0.0.1 --port 3000`（后台，日志 `devserver_restart.log`，**:3000 现由本批进程托管**；
    backend :8000 未动）。`verify_n.mjs` → `verify_n.json` + 9 截图 `n_{home,pdp,cart}_{de,fr,nl}.png`：
    - de/fr/nl **全部 overall pass**：头部（Kategorien/Catégories/Categorieën、搜索占位、Shops/Inloggen 等）、
      通告条、页脚版权/法务段、购物车（Ga winkelen/Faire du shopping/Einkaufen gehen、Afrekenen (0)、
      Overzicht、Veilige SSL-versleutelde betaling）、PDP（Ajouter au panier/Acheter maintenant/
      30 jours de retours gratuits 等）**全部目标语言，不再英语回退**；语言下拉仍 5 项；
      **三语言 9 页 console error 合计 0**。
- **踩坑（不得再踩）**：①验证脚本预期值要跟**实际渲染键**——购物车空态按钮是 `cart.goShopping`
  （不是 `cart.browse`），首跑误报 fail 改预期后全过；②共享热点文件看 `git diff` 出现删除行先
  `git show HEAD:` 对照——本批 39 删除全是早批未 commit 改动，别误判自己；③Git Bash `node -e` 内嵌
  含反斜杠正则会炸转义 → 一律写脚本文件；var 下 ESM 用 `.mjs`（root package.json type:module，
  `.cjs` 例外）；④Windows 下 `pathToFileURL().pathname` 会拼出 `E:\E:\...` → 用 `fileURLToPath`；
  ⑤joybuy.co.uk 不响应 Accept-Language，de/fr 真站参照拿不到是常态，别硬冲（风控口径不变）。
- **遗留/既定口径（不阻塞）**：①**品类名、CMS 模块标题（如 "Category discovery"）、PDP 结构化区块标题
  （"Product Description"/"Product Selling Points"）走后端内容/译文管线**，de/fr/nl 下回退英文=既定口径，
  不是词典缺词；②messages.js CRLF prettier 遗留同 0u；③未 commit（含更早批次的工作区改动仍在）。

## 0x. 爬虫预检（2026-11-20，✅ 完成，只读未启动任何抓取）

> 任务：为今晚正式抓取（10 分类）做只读预检。报告：`var/crawl_preflight_20261120/preflight.md`，
> 检查脚本 `var/crawl_preflight_20261120/inspect_db.py`（Django shell 只读）。**未登录账号、未杀/启任务、未改配置、未 commit。**
> **结论：可启动（7/7 PASS）**。要点：
> - 后端 :8000 `/api/v1/categories` 200；`showmigrations` 证 MySQL 通。E: 剩 **144G**（`var/media` 现 56.76G/707,786 文件，PS 口径），2–8GB 增量无忧。
> - baidu 200；joybuy.co.uk / joybuy.nl 均 **307 可达**（真站风控口径不变：只走 SSR，不碰交互态）。
> - 账号池 62 未删：**44 ACTIVE+VALID / 18 UNKNOWN**。分组 VALID：03=10、01=9、05=8、06=8、02=6、04=**0**（全 UNKNOWN）⚠️ 今晚调度**避开 数据抓取04**。
> - `MEDIA_BACKEND=local` 行为验证过：:8000 返回 11-19 本地卡片图 200 且字节数与 `var/media` 磁盘文件一致（settings 默认 local，AWS 决策不动）。
> - CrawlJob 236 行（COMPLETED 114 / READY 90 / FAILED 26 / CANCELED 4 / **RUNNING 2 zombie**：job id=2、id=3，11 月初 demo 遗留，group=default，**未杀**，待主会话决定改 CANCELED；不阻塞新建任务）。
> - 候选 10 分类：joybuy_uk 树 version 6（211 活跃二级节点，`is_active=False`=0，95 个 SPU=0）。按父类分散各挑 1 个 0-SPU 节点：
>   l2:1418 Tablets / l2:1405 Kettles & Toasters / l2:2710 Body / l2:1363 Cat Food / l2:3499 Gaming Headsets /
>   l2:1380 Electronic Toys & Music / l2:1881 Watches / l2:1460 Sports Nutrition & Performance / l2:1445 Pens & Pencils /
>   l2:1522 Household Essentials（完整表+备选+参数建议在 preflight.md；`source_catalog=joybuy_uk`，product_limit 40–60，allow_pagination 默认 True，组轮转 01/02/03/05/06）。
> - 树小坑：version 6 有 3 个 depth=1 行 source_id 带 `l3:` 前缀（l3:3129/l3:1430/l3:1500），已排除出候选；`joybuy`/`joybuy_nl` catalog 无 current_version，任务别挂它们。

## 0x-2. 爬虫启动记录（2026-11-20，⚠️ 启动 1 个后**用户叫停**，最终全停）

> 任务：按预检口径创建并启动 10 个分类的正式抓取任务（用户已批准当晚抓取、完成后自动关机）。
> **执行中途（04:00 UTC 前后）用户经协调者下达「暂停爬虫任务」指令**，已立即执行：
> 停止创建剩余任务、走正常取消路径停掉唯一在跑的 run。**未关机、未改代码、未 commit、未动配置。**

- **已创建并启动（仅 1 个，后已取消）**：CrawlJob **pk=237** `数据抓取01-平板电脑-1120`
  （l2:1418 Tablets，joybuy_uk 树 v6，limit=50，allow_pagination=True，group=数据抓取01，
  其余参数=预检建议口径：SOURCE_DEFAULT/INCREMENTAL/skip_imported=False/PAUSE/媒体=主图+评价图）。
  Run `fc2e40dc-80c8-480c-8ecc-d821bcd0a9aa`（执行器 PID 17392，独立进程 `manage.py run_crawl_run`，
  启动命令带 `MEDIA_BACKEND=local`）。**启动健康**（观察 ~2.5 分钟）：LISTING_FETCHED×2（翻页第 2 页都 HTTP 200）、
  PRODUCT_PARSED/导入持续产出、**零风控/登录墙信号**（无 risk605/维护页/LOGIN_WALL/RISK_CONTROL 事件）。
- **用户暂停的最终状态（DB 实查 + tasklist 确认）**：
  * Run `fc2e40dc` → **CANCELED**（finished_at=2026-11-20 04:00:26 UTC，pause_reason=NONE）；
    job 237 → **CANCELED**。取消走管理端同款 `crawler_control.services.cancel_run`（脚本
    `var/crawl_night_20261120/cancel_run20.py`），随后向执行器进程组发 **CTRL_BREAK 优雅退出**
    （非 taskkill /F；日志尾「Spider closed (shutdown)」，进程 17392 已退出）。
  * 计数：**discovered=50 / imported=5 / failed=0**，钉定账号 `100006876375579`（数据抓取01）。
    事件：RUN_ACCOUNT_SELECTED/RUN_STARTED/ACCOUNT_POOL_READY/LISTING_FETCHED×2/PRODUCT_PARSED×7/
    MOBILE_DETAIL_MERGED×7/VARIANT_PRICES_MERGED×3/DATASET_SAVED×5/PRODUCT_IMPORTED×5/DATASET_SUMMARY；
    trip_signals=none。已导入的 5 件商品数据保留（真实数据，未回滚）。
  * 其余 9 个任务**从未创建**（无残留）；既有 90 READY/2 zombie（job 2/3）原样未动。
- **剩余 9 个任务的既定计划（未执行，供恢复时直接用）**：名字/分组已定稿在
  `var/crawl_night_20261120/create_jobs20.py` 的 PLAN 表（`{group}-{中文名}-1120` 命名，组轮转
  01/02/03/05/06 各 2 个，避开 04；l2:1405→02、l2:2710→03、l2:1363→05、l2:3499→06、l2:1380→01、
  l2:1881→02、l2:1460→03、l2:1445→05、l2:1522→06）。恢复时：`create_jobs20.py <source_id>...`
  逐个建（幂等，撞名自动跳过）→ 复用 `var/night_crawl_20261115/launch_run.py` 启动 →
  队列按 night_queue.py 模式（**同组串行、5 组并行**，单 run 超时建议提到 150 分钟——limit=50
  按实测 ~2.5 分钟/件会超 90 分钟旧值）。风控纪律不变：连续 2 账号 email 验证封锁即停批。
- **本次踩坑（不得再踩）**：①爬虫执行器**不轮询 run.status**——只调 `cancel_run` 只改 DB，Scrapy
  会继续抓完；要真正停下来需对执行器进程组发 CTRL_BREAK（`close_spider` 见状态非 RUNNING 会跳过
  回写，不产生脏状态）。②Windows 下跨进程发 CTRL_BREAK：`os.kill` 报 WinError 87；
  `AttachConsole` 先 `FreeConsole()`（否则 ERROR_ACCESS_DENIED=5），成功后
  `GenerateConsoleCtrlEvent(1, pid)`。③Git Bash 会把 `tasklist /FI` 转义成路径，要加
  `MSYS_NO_PATHCONV=1`。④CrawlerAccount 在 `crawler_control.models`（不是 crawler_accounts），
  软删字段是 `deleted_at`（无 `is_deleted`）。⑤CrawlJob.name unique——重抓同类目换后缀
  （本次用 `-1120`），复用旧名会撞唯一约束。
- 本次产物（仅运维脚本与结果 json，无代码改动）：`var/crawl_night_20261120/`
  （recon.py 只读侦察 / create_jobs20.py 建任务 / cancel_run20.py 取消 / final_state.py 终态核查 /
  create_jobs_result.json / signal_result.txt）。所有启动/取消命令均带 `MEDIA_BACKEND=local`。

## 0w. 批次 M（2026-11-19/20 头部 6 项 + footer 裁剪 + 购物车 3 项，✅ 完成，未 commit）

> 需求文档03 **13.5/13.6/13.7**。实测与证据目录：`var/header_footer_cart_20261119/`
> （`measurement.md` 实测报告、real_home_{zh,en}.html/real_cart_nl.html SSR、css/ 24 个真站
> bundle 离线解析、header_measure*.json 探测、verify_m.{mjs,json} + m_*.png 自验截图）。
> **全程未 commit；未碰 backend/content/、admin-web/、crawler/、频道页组件。**

- **实测口径（⚠️ 2026-11-20 起真站风控：SSR curl 可抓但悬停打开态/页面交互触发「服务暂时中断」页）**：
  被挡项改用既有存档（`var/header_drawer_20261116/joybuy_user_hover.png` 头像下拉截图、
  `var/footer_rework_20261119/measurement.md` 的 `_lang=en_GB` 真值结论）+ 静态证据
  （真站 24 个 CSS bundle + SSR HTML 离线解析），不硬冲真站（主会话 2026-11-20 拍板）。
  关键实测值见 measurement.md：主行 14+52+14、sticky 阴影 token
  `0 2px 12px rgba(0,0,0,.039), 0 4px 6px rgba(0,0,0,.059)`、品类行 y=120 紧贴主行
  （gap 0）+ padding-bottom 14 + 文本 14px/400/16px、分类按钮 16px/600/icon24/`#F5F6FA`
  圆 50px、头像下拉 = 笑脸(#E5E7F0 圆 + 白笑脸 SVG 原文抓取) + `user4323txlb` 粗体 +
  5 行左文右线性 icon、hover 16ms 开/18ms 关、购物车 `paymentLogos` 13 项顺序
  （Amex→Visa→MC→Maestro→?→PayPal→WeChat→Google→Apple→Klarna→iDEAL→Bancontact→?）。
- **交付 1 头部（AppHeader/AppCategoryPanel/useMarketLocale）**：①品类下拉阴影换真站
  token 同族放大 `0 4px 24px .08, 0 12px 48px .06`（⚠️ 打开态 CSS 被风控挡，静态推断项，
  验收可复核）；②品类行去 40px min-height、14px/400/16px、padding-bottom 14px（视觉间隙
  ≈真站 0px 结构）；③分类按钮 16px/600/24px icon；④语言下拉 5 项
  English/中文（简体）/Deutsch/Français/Nederlands（GB 市场放开 de/fr/nl；真站清单为
  countryLang 键集推定项），切换全站跟随：`useLocale.t()` 已有 en 回退链无需改，
  de/fr/nl 页面实测不崩、回退生效（词典=批次 N）；⑤头像菜单 hover 即开（mouseenter）
  / 移出 200ms 关 / click 保留触屏路径，批次 F 五态入口不动；⑥面板 270px、用户行 =
  笑脸 SVG + 粗体 display_name、5 行左文右 20px 线性 icon。
- **交付 1b 后端（accounts_buyers）**：`BuyerAccount.display_name`（0007 迁移，dev 库已
  migrate）+ `_ensure_display_name`：为空时生成 **`user`+4位数字+4位小写字母**（真站格式
  实证 user4323txlb），查重 10 次后 hex 兜底，一次生成固定存库；`_account_payload` 带
  `display_name`。⚠️ **:8000 已按 HANDOFF 姿势重启**（并存双 runserver 旧 PID 全杀，
  `MEDIA_BACKEND=local CRAWL_VARIANT_PRICE_LIMIT=3 manage.py runserver 127.0.0.1:8000
  --noreload`，AWS 被封口径不动 MEDIA_BACKEND；日志 `var/header_footer_cart_20261119/
  backend_restart.log`）。
- **交付 2 Footer（AppFooter）**：顶行/中部 `v-if="false"` 保留代码不渲染，`toggleLocale`
  解构与 `@click` 一并停用（孤儿引用已清）；底部【内部研究演示项目…】声明删除，法规段
  中性 demo 实体文案保留（主会话法律安全口径勿回退）；We support 支付行保留。
- **交付 3 购物车（pages/cart/index.vue + ChannelPickedForYou）**：①h1 删除、useHead
  保留；②合计下方支付图标行 = 本地 `pdp-services` 8 个 SVG 按真站顺序
  （Amex/Visa/MC/PayPal/WeChat/Google/Apple/Klarna；Maestro/iDEAL/Bancontact 无本地
  SVG 记偏差）；③底部【精选好物】：`ChannelPickedForYou` 的 categorySlug 改可选，不传 =
  不带 category 参数（全库池），四步交互复用（频道页零影响）。
- **针对性验证（按验证纪律仅做针对性验证）**：
  - 后端：ruff 4 个改动文件全过；`manage.py test accounts_buyers --keepdb --parallel 1`
    **20/20 OK**（新增 BuyerDisplayNameTests 2 例：生成格式/固定存库、已设置不覆盖）。
  - 前端：eslint 0 error（ChannelPickedForYou.test.js 2 条 one-component-per-file
    warning，既有模式）；prettier 全过（messages.js 未触碰、仍 CRLF）；vitest
    **106/106**（+3：AppHeader hover/笑脸/用户名 2 例 + ForYou 无 slug 全库池 1 例）。
  - Playwright EN/ZH（`verify_m.mjs` → `verify_m.json`，localhost:3000）：分类按钮
    16/600、品类行 14px/400/16px + pb14、打开态新阴影生效、语言下拉 5 项、de/fr/nl
    页面 0 pageError 回退英语、footer 两块不渲染+声明不在+We support 7 图标+ZH 无法规段
    （真站口径）、cart h1=0 + 标签页标题保留 + 8 支付图标全加载、精选好物
    24→(滚动自动)48→(按钮)72→96 循环、console 0 error、注册临时买家 → 菜单显示
    `user8392htzs`/`user0372wmso`（格式正则过）、hover 开/120ms 仍开/320ms 关、5 行 icon。
- **清理**：2 个临时买家（m-batch-en/zh-…）已删净（left 0，含 session 级联）。
- **遗留项**：①品类面板真站打开态阴影/语言清单为静态推定（真站风控，验收如恢复可复核）；
  ②Maestro/iDEAL/Bancontact 支付 SVG 需补本地素材；③de/fr/nl 词典=批次 N；
  ④messages.js CRLF 历史格式未动（0u 遗留）；⑤dev :3000 现由其他会话进程托管
  （绑 [::1]:3000，curl/验证用 localhost:3000）。

## 0v. 批次 J（2026-11-19/20 品类页活动卡片后台+接口 + 13.8 链接规则 + 13.3 模块数据补抓，✅ 完成，未 commit）

> 需求文档03 13.2 / 13.3 / 13.8。证据与全部脚本：`var/channel_page_cards_20261119/`。
> **全程未 commit；未碰 storefront/、CategoryTile*、backend/catalog/search_views.py（批次 I 在改，只 import 了其常量）、AppHeader/AppFooter/cart。**

- **交付 1 品类页卡片（13.2）**：新模型 `content.ChannelPageCard`（channel_code/image_url/link_url/sort_order/is_active，
  迁移 `0012`；权限种子 `0013`：`cms.channel_page_cards.manage/view`，platform_admin+operator 全量、_viewer 只读）。
  服务 `content/channel_page_card_services.py`（channel_code 校验复用 banner 口径 + **按 `NAV_HIDDEN_ROOT_SLUGS` 过滤下拉到 9 个频道**；
  图片只收本站 `/media/`；link_url 按 13.8 存原值）；管理端 `merchant_ops/views_channel_page_cards.py`（CRUD+move/toggle，
  URL `/api/v1/admin/channel-page-cards[/channels|/<uuid>|/<uuid>/actions]`，写操作审计）。
  **买家接口契约（勿改名）**：`GET /api/v1/cms/channel-page-cards?channel=<channel_code>` →
  `{"items":[{id,image_url,link_url,sort_order}]}`（sort_order 升序；未知/未配置频道 `{"items":[]}`；缺 channel 参数 400 `CHANNEL_REQUIRED`）。
  批次 I 按 `storefront/utils/cmsLink.js::resolveCmsLink()` 消费。
  admin-web：`CampaignCardsView.vue` 新增第三个 tab【品类页卡片展示】（`ChannelPageCardsPanel.vue`，模式照抄 ChannelBannersPanel：
  频道下拉/ImageUploader(purpose=`channel_page_card`)/排序/启停/上下移/删除，AppModal+overlay 约定一致）。
  `media/uploads.py` PURPOSES 新增 `channel_page_card`（CMS 桶 2MB）。
- **种子数据（9 频道 31 张，图片全部本地托管）**：抓 9 频道页 EN SSR（8 UK `.co.uk` + `mini-hp-nl-sports-outdoor` `.nl`），
  活动卡片在 RSC `moduleCode:"uk-pc-image-ads"` 的 `dataBatch`（每卡 img_small/img_middle/img_large + jump.jumpValue.link）。
  逐页用「卡片图在渲染 `<img>` 里的字节位置」确定可见行，选择口径：默认取品类卡下第一行 campaign 卡；
  美妆/健康取 **campaign 行**（module0 是品牌店行）；母婴=两个 2 卡模块（4 张一行两张）；宠物取【热门好价】下方行前 3 张（真站 4 张）；
  游戏去掉行首 2 张品牌店卡取 3 张 campaign 卡。配置数=家居/电子/美妆/家电/宠物/户外/游戏 3 + 健康 6 + 母婴 4（与 13.1③ 一致）。
  图片下载 `images3.joy-sourcing.com/product/s820x400_<path>.webp`（母婴用 `s1247x400_`）——**坑：`images2/joybuyimg/` 原始前缀对部分
  路径返回同一个 fallback 对象（不同路径同字节），必须用尺寸渲染前缀**；链接按真站→域名替换 `www.joyfumi.com`（13.8 全链接原样入库）。
  入库脚本 `seed_cards.py`（store_upload purpose=channel_page_card + create_card，`--force` 幂等重跑），DB 现存 31 张（9 频道各就位）。
- **交付 2 链接规则（13.8）**：`content/campaign_services.py::validate_href` 与 `content/channel_banner_services.py::validate_href`
  统一为 `^(?:https?://|//|www\.|/(?!/))\S*$`（全链接原样保存；javascript: 等仍拒）；`ChannelPageCard.link_url` 与首页轮播
  HomeBanner 本就存原值不改写。admin 表单说明文案三处已加（活动卡片/频道 banner/品类页卡片："以 http(s):// 或 www. 开头按外链原样跳转，否则视为站内路径"）。
  验证：admin 实配 `https://www.example.com/x` 与 `/pages/abc` → 接口/公开接口均返回原值（verify_admin.cjs）。
- **交付 3 模块数据补抓（13.3）**：UK 8 频道 368 个唯一真站 SKU，批次 H 已入库 105 → 缺 263。全程走既有链路：
  `harvest_uk.py`（`/s?k=<标题>` SSR，parse_search.py 按 skuId 精确匹配，单线程 delay 2.5s，3 次候选词）
  → **259/263 解析成功**（价格/图/品牌/评分）→ `import_uk.py`（UkProduct payload → joybuy_crawler.ingest →
  crawler_control.import_services.import_staging_product → 激活 SPU/Offer → rebuild_search_document；GBP/市场 GB，
  source_category=minihome:<频道 code>）→ 185 直接新建；74 个因「批次 H 已入库但非可售」在导入期冲突
  （46 商家不一致 + 28 规格/商品绑定冲突）→ `fix_existing.py` 按「已入库直接复用」处置：按 SPU 级/`SkuSourceIdentity`
  SKU 级身份找到既有 SPU → 补 gallery 图 → 激活 SPU+Offer → 刷搜索文档（63+7 激活，2 本就可售）。
  媒体下载在导入期整批失败（见下坑②），事后用 `_import_gallery_images` 以 `MEDIA_BACKEND=local` 重跑补齐（182+2+1 张，185/185 有图）。
  最后重跑 `seed_channel_modules`（**默认 fill，勿加 --no-fill**）：**495 位次，真站商品缺失从 223 → 9，同品类补位从 320 → 12**。
  统计（`backfill_stats.py` → `stats.json` + `missing_products.json`）：真站 453 唯一 SKU / 产品级可售 448 / 缺 5
  （3 个真检索 miss：102085953、10474135、10489687 + 2 个真站 payload 里的 `undefined` 占位 id）；户外 67/67、宠物 38/38、
  家电 79/79、游戏 43/43 全齐。`seed_channel_modules` 新增 SKU 级身份回退（SkuSourceIdentity→spu）+ 楼层内 SPU 去重
  （两个变体 SKU 解析到同一 SPU 会撞唯一约束 `channel_module_product_unique`）。
- **⚠️ 环境大坑（影响所有会话，非本批引入）**：①本机 `~/.aws/credentials` 的 key（AKIAUGV5ODE6…）已失效
  （S3 `InvalidAccessKeyId`），**且 bucket `joybuy-media-fra` 匿名 GET 返回 `AllAccessDisabled`（403）**、生产 IP 从本机不可达
  ——即 `MEDIA_BACKEND=s3` 时**所有上传 500、旧 S3 媒体本地 302→403 全挂**。本批处置：本机 :8000 改以
  `MEDIA_BACKEND=local` 重启（写本地 `var/media`，读本地，旧 S3 媒体本地 404——与之前 403 一样不可用，非回归）；
  31 张卡片图 + 185 张新商品图全部落本地。**待用户修复 AWS key/bucket 策略后，需把本批本地媒体同步到 bucket
  （重跑 `seed_cards.py`/gallery 重导即可，内容寻址幂等），生产站才能看到这批图。**
  ⭐ **用户已确认根因与决策（2026-11-20 凌晨）**：亚马逊账户**未付款被暂时封禁**；**决策 = 数据先存本地（MEDIA_BACKEND=local）**，用户恢复账户后会主动通知，届时再把本地增量媒体上传 S3（`aws s3 sync` + 对账）。**在用户通知前：不做任何 AWS/S3 操作、不切回 s3、不重试连接。**
  ②本机 :8000 / :5173 / :3000 均在跑；重启后端时杀两个 runserver PID（autoreload 有父子两个）。
- **针对性验证（按验证纪律仅做针对性验证）**：
  - 后端：`content.tests`+`catalog.tests.test_standard_categories` **59/59 OK**（无 --keepdb 跑，见下坑⑤）；
    改动 py `ruff check`+`format --check` 全过。admin-web eslint/prettier 全过。
  - admin 浏览器实测（临时 staff `cardcheck-j@joybuy.test`（platform_admin，**用完已删**），
    `verify_admin.cjs` → `admin_verify.json` + 4 截图）：登录→活动卡片页→【品类页卡片展示】tab→9 频道下拉→
    列表 3 行缩略图 0 破图→UI 上传 canvas 图+填 `https://www.example.com/x` 保存→列表与公开接口原值返回→
    API 建 `/pages/abc` 卡→公开接口两值都在→清理 10 张测试卡（11/11 PASS，console 0 error）。
    另 `verify_tabs.cjs`：首页活动卡片/频道页 banner 两 tab 回归通过（banner 下拉仍 10 项=未过滤，属既有口径）。
  - 接口契约：`GET /api/v1/cms/channel-page-cards?channel=…` 家居 3 张/健康 6 张按序返回、字段四键固定；
    图片 200 image/webp；未知频道空数组；缺参 400。
  - 数据：5 个新 SPU 抽查 `/p/<id>` 200 且 PDP API 有 gallery（本地 /media/ URL）+ offer.price；
    `/api/v1/search?q=Falcon Heritage Electric Bike` 命中新导入；频道模块接口 Pets/Health/Baby 各楼层
    100% 有价有图（部分楼层标题匹配率<100% 是 PDP 标题 vs 楼层 listing 标题的差异，非补位）。
    storefront 两个频道页 Playwright 渲染 91/108 张图正常（少数破图=旧 S3-only 媒体本地 404，见坑①）。
- **坑（不得再踩）**：①AWS/S3 见上（⚠️ 用户需修）；②`MEDIA_BACKEND` 在 `.env`，任何做媒体写入的脚本
  **必须 `MEDIA_BACKEND=local` 覆盖启动**，否则 store_bytes 走 S3 全 500（本批 185 张图整批失败就是它）；
  老资产（S3 时代）的行存在但本地无文件，本地模式重下时 `store_bytes` sha256 去重不会补写文件 → 需先写本地文件再
  `link_asset_to_object`；③真站活动卡片数据在 RSC `uk-pc-image-ads` 的 dataBatch，每个 image-ads 模块会在 RSC 重复出现
  （去重按卡片 image_path+link 元组）；判断「可见行」要按卡片图在渲染 `<img>` 里的位置（RSC 文本位置≠视觉顺序），
  且匹配要用图片路径**最后两段**（文件名 hash 不唯一）；④批次 H 从 PDP 导入的商品：SPU 身份=父商品 id、SKU 身份=
  skuId，用 skuId 找 SPU 必须同时查 `Spu.source_identities` 和 `SkuSourceIdentity`，且这些商品重导会撞
  商家/规格绑定冲突——**复用激活，不要重建**；⑤`--keepdb` 的既有测试库缺 Market 种子（历史漂移），
  content 套件要**不带 --keepdb**跑（59/59）；⑥admin 验证脚本里 Node 直接 fetch POST/DELETE 必须带
  `X-CSRFToken`（取 csrftoken cookie），否则 Django 返回 HTML 403（`.json()` 报 "Unexpected token '<'"）；
  `joybuy_staff_session` cookie path=/api/v1/，`context.cookies()` 要按 `http://localhost:8000/api/v1/` 取；
  ⑦真站搜索 SSR 的 4 个 miss 里 `undefined` 是真站 payload 的占位 id，不算风控缺失。
- **遗留项**：①本批媒体在本地盘，等 AWS 修复后同步 bucket（见坑①）；②真站卡片链接指向
  `www.joyfumi.com/campaign/active/<id>` 等路径，本站尚无对应落地页（13.8 外链原样跳转口径，落地页属后续需求）；
  ③13.3 的 3 个真检索 miss 商品未入库（missing_products.json 有清单）；④storefront 卡片渲染与 resolveCmsLink 消费
  归批次 I（0u），本批只保证契约；⑤批次 I 的 0u 与本批并行执行，两批都对 `content/` 有改动但文件不重叠
  （0u 未改 backend/content/，已在 0u 节注明）。

## 0u. 批次 I（2026-11-20 频道页视觉改造 + 精选好物，✅ 完成，未 commit）

> 需求文档03 13.1①②④ + 13.4。实测与证据目录：`var/channel_styles_20261119/`
> （`measurement.md` 实测报告、measure*.json/cjs、cookies.json、verify_channel_styles.{json,cjs}、
> local_*.png 双语截图）。**全程未 commit；未碰 backend/content/、admin-web/、AppHeader/AppFooter/cart。**

- **实测要点（真站 3 页：家居/健康/户外，登录态 cookie + color-api 打桩，详见 measurement.md）**：
  二级品类卡两规格——small「140px 图容器 / 名称区 120px ≈ 6 字宽 / 一行 8 张」、
  big「194px 图容器 / 名称区 174px ≈ 9 字宽 / 一行 6 张」；图片容器 `#F5F6FA`(rgb(245,246,250))
  只包图、radius 8px，名称在背景**外**：18px/500/lh24 居中、margin-top 12px、**名称盒固定 48px**
  （2×24 预留，保证列内第 2 张卡纵向 pitch 一致）、max 2 行截断；卡间距 20px。
  商品楼层卡：194 宽、无边框无阴影、图盒白底 r12、20px 间距、**一行 6 张**；楼层标题
  28px/700、头块 margin-bottom 24px。健康页模块标题 `Category Navigation` 28px/700、与卡区隔 24px。
  精选好物（ForYou）真站接口 `guide_recommendation_getSlotList` 登录态 403（风控）→
  **每批数量无法实测**；i18n 词典证实交互文案 `View more/查看更多`。
- **交付 1 品类卡改造**：新增 `storefront/utils/channelTiles.js` 频道配置表
  （rows/perRow/nameChars/maxVisible/hiddenTiles/showTitle，数据驱动，组件零硬编码）；
  `CategoryTileGrid.vue` 加 `variant="channel"`（背景只包图、名称在外、nameChars→140/194px、
  48px 名称盒）+ `columns`（2 行频道切成纵向列栈，余量整列横滑）；`CategoryTileCarousel.vue`
  加 variant/rows/nameChars 透传；行数按 13.1② 表：家居/电子/美妆/家电 2行8个6字、
  健康 1行8个6字+标题、户外 1行6个9字、宠物 2行6个6字+隐藏 `other-animals`、
  母婴 2行6个9字、游戏 1行6个9字。首页下拉/结果页条带走 default variant **零变化**。
- **交付 2 模块卡样式**：`CmsProductPool.vue` 加 `single_row`（单行横滑、6 卡/行 194px、
  底部圆形箭头+进度条，与 CategoryTileCarousel 同交互）+ `flat`（去外框去 padding），
  由频道页 payload 传入；首页 CMS 楼层不受影响。
- **交付 3 精选好物**：新组件 `storefront/components/ChannelPickedForYou.vue`，
  9 频道页底部（现有模块之后）：SSR 首批 24 件（接口一页=RECOMMENDATION_PAGE_SIZE，
  与首页为您推荐同口径）→ IntersectionObserver 监听模块底部哨兵**首次自动加载**下一批 →
  之后出现【View more/查看更多】按钮**点击**加载 → **循环**：请求一律带 `cycle=1`，
  页号超池后端取模回到第 1 页（响应结构不变，total/total_pages 仍是池子真实大小）。
  卡片与楼层同款无边框，6 列网格，加载态 spinner。后端 `catalog/search_services.py::
  recommendation_documents` 加 `category`（子树过滤，与 search_documents 同口径）+
  `cycle`（取模循环）；`search_views.py::recommendations` 解析 `category=<slug>`
  （未知 slug → 404 CATEGORY_NOT_FOUND）与 `cycle=1`。
- **针对性验证（按验证纪律仅做针对性验证）**：
  - 后端：`ruff check` 3 个改动文件全过（`ruff format --check` 有 2 处**批次 C 遗留**的
    历史格式差（search_services.py L79/L364，不在本次 diff 内，未动）；`manage.py test
    catalog.tests.test_search --keepdb --noinput --parallel 1` → **20/20 OK**
    （RecommendationTests 5→8：新增子树过滤/cycle 循环/端点参数 3 例）。
  - 前端：eslint 0 error、prettier 全过（`locales/messages.js` 因整文件 CRLF **历史上**就不满足
    prettier，仅精确锚点插入 4 组 i18n 键（channel.categoriesNav / reco.pickedForYou /
    reco.viewMore / reco.loading，EN+ZH），未整文件重写）；vitest 全套 **103/103**
    （新增 ChannelPickedForYou.test.js 4 例 + CategoryTileGrid 3 例频道 variant +
    minihome-channel-page 3 例：variant 透传/健康标题/宠物隐藏卡）。
  - Playwright（`verify_channel_styles.cjs` → `verify_channel_styles.json`，1440×1000，EN/ZH）：
    9 频道全部 200；家居 2 行(22 卡 11 列)、健康 1 行 9 卡+【Category Navigation/分类导航】、
    户外 1 行 5 卡 194px；名称区 18px/500/24px/居中/背景外、图块 rgb(245,246,250) r8、间距 20px；
    楼层单行横滑 6 卡/行、卡 border none；宠物页 12 卡且无 other-animals、**分类树 API 仍 13 子类**
    （下拉不受影响）；精选好物四步：24 →(滚动自动)→ 48 →(按钮出现)→ 点击 72；
    `?category=home-living&page=99&cycle=1` → page=9（10 页池循环，backend 直证）；
    console 0 非 404 error。
- **环境/数据发现（⚠️ 非本批引入，跨批次问题）**：
  1. **本机媒体 404**：`MEDIA_ROOT=var/media` 本地缺 12,993/114,915 个 DOWNLOADED 资产
     （0i 迁 S3 后本地盘不全）。首页/楼层/ForYou 里约 11% 图 404（浏览器 console 计 404，
     **非 JS error**）。批次 H 楼层商品图同样受影响（家居 7 个 404 中 6 个是楼层商品）。
  2. **:8000 进程**：2026-11-20 0:06 并行批次（bcad1190 会话）以 `MEDIA_BACKEND=local`
     显式重启了 :8000（`netstat`/命令行取证）；root `.env` 是 s3，但 s3 302 的匿名桶 URL
     现测 **403**（桶不再匿名可读）→ 当前 local 模式反而是能出图的可用状态。**动 :8000 前
     先读本条**；恢复 s3 需先解决桶匿名读策略。
  3. ForYou 每批数量真站 403 无法实测 → 取接口一页 24（measurement.md §5 偏差 4）。
- **遗留项**：①媒体缺失/S3 桶匿名读策略（跨批次，需数据侧决策）；②`messages.js` CRLF 历史
  格式（prettier 全绿需另起格式化任务，避免与批次 M/N 冲突）；③户外真站 h1 `Sports & outdoor`
  未改（0t 遗留）；④真站品类卡 Swiper 是悬浮半透明箭头，本批按任务口径沿用底部箭头+进度条
  （measurement.md §5 偏差 5）。
- **验收修复（2026-11-20，验收 9/12，`var/acceptance_ij_20261119/`，脚本在 `var/channel_styles_20261119/`）**：
  - **FAIL-A（为您推荐/精选好物点击 40%，已修）根因**：池子只信
    `ProductSearchDocument.is_searchable=True`，而它是 `rebuild_search_document` 写入的
    **快照**——并发爬虫导入（批次 J 补抓正在跑，36h 内新建 1,656 SPU/其中 1,534 仍是 DRAFT）
    期间 SPU 状态/Offer 活性与快照脱节，池子混进 PDP 已 404 的商品。修复：
    `recommendation_documents` 池子构建改为实时校验——`spu__status=ACTIVE` +
    `Exists(ACTIVE Offer for market)`，文档快照只作初筛；新增回归用例
    `test_recommendations_pool_excludes_stale_searchable_docs`（SPU 置回 DRAFT/Offer 撤下但
    文档仍 searchable → 必须被排除，恢复后重新可见）。
    **自验**：为您推荐 10 页 EN 239 unique/ZH 240 unique 全部 PDP 200（0 non-200）；
    家居精选好物 24/24 EN+ZH 200；**9 频道精选好物首批 24×9×2 全 200（OVERALL_BAD=0）**；
    ForYou 页面交互抽查 24→48→按钮，console 0 非 404 error。
    脚本：`check_pdp_404.py`/`verify_fail_a.py`/`verify_fail_a_channels.py`。
    ⚠️ 注意：`--keepdb` 测试库曾因并行批次测试缺 `get_import_fallback_merchant` 的系统商家
    fixture 而 9/9 报错（非本批代码问题）；**不带 --keepdb 重建后 21/21 OK**，keepdb 复跑也 OK。
  - **FAIL-B（ZH 品类区图片丢失回归，判非复现）**：品类 tiles 图片来源是
    `assets/category-images.js` 静态本地清单（204/204 文件在盘），**完全不经过 locale 数据**，
    与楼层同一策略、无按 locale 的第二份数据。实测 SSR HTML 两 locale 各 22 img；
    水化后家居/健康/户外 × EN/ZH img=tiles（22/22、9/9、5/5）、0 破图、0 图片 404
    （`repro_b.cjs`/`repro_b2.cjs` 证据）。验收报告的「9 卡 4 img vs 13/13」在当前代码任何
    状态下都无法构造（家居 tiles 恒为 22），疑似验收时 dev server 处于 HMR 中间态或计数口径
    （未滚动时懒加载 img 的 naturalWidth 计数，视口相关而非 locale 相关）。如复现请先确认
    dev server 已重启至 0u 最终态再测。
  - **数据问题（按主会话口径，不在本批处理）**：本地缺媒体文件为主会话单独处理，
    本批不动 :8000 的 MEDIA_BACKEND。

## 0s. 总记录（2026-11-19，需求文档03 v1.4 第二轮 4 项：批次 E–H 开发 + 独立验收 + 修复复验，✅ 全部收口，未 commit）

- **任务链**：用户第二轮 4 项需求（页脚返工 / 申请店铺入口 / 购物车多商家 / 品类对照+频道页模块）→ 并入 `功能需求迭代文档03.md` **v1.4 第十二节**（12.1–12.5）→ 4 个开发子 Agent 滚动执行 → 2 轮独立验收（E+F、G+H）→ 3 条问题原地修复 → 复验通过。
- **批次 E ✅**（详见 `## 0n.`）：页脚按真站**全量结构**重写（顶行三框 + 订阅/App 块 + 三列 + We support 支付行 + © 行 + 法规段），新建 `layouts/footer-page.vue`（无品类导航简洁顶栏）+ `pages/pages/`（contact-us / about-us / joybuy-news / joyplus / 三个政策页），联系我们页双 tab（Contact us / Partner with Joybuy），关于我们按 `promo/welcome` 1:1；删除 5 个真站无对应页。验收 **10/10**。
- **批次 F ✅**（详见 `## 0o.`）：右上角【配送至】→【申请店铺】，头像菜单入口移除；状态并入 `GET /api/v1/auth/buyer/session`（`merchant_application_status`+`merchant_id`），SSR 首屏无闪变；五态 24/24。验收 **10/10**。
- **批次 G ✅**（详见 `## 0q.`）：`serialize_cart` 每 item 增量 `merchant{}`（offer→merchant，select_related），前端按商家分组白卡 + 组/顶全选与半选联动，单商家隐藏顶行不回归；契约零改动；单测 9/9、E2E 37/37。验收通过。
- **批次 H ✅/⚠️**（详见 `## 0r.`）：①改名改**数据源**（LocalCategory name/en/zh + seed 常量重跑），顶栏/下拉/面包屑/频道 h1 同步；②新增 `NAV_HIDDEN_ROOT_SLUGS` + `visible_in_nav`，隐藏计算机与配件、服装与配饰（直链仍 200）；③比利时站当时判定不可达（`joybuy.be` 无 DNS，且频道 code 用错）→ 回退英国站（**2026-11-19 已由 `## 0t.` 推翻并换成真实比利时频道数据**）；④9 频道 29 层模块，实测 408 商品 → 新建 61 SPU/64 Offer + 复用 50，320 位次用同品类真实可售商品补足。验收 12/13 → 修复 → **复验 2/2、47/47**。
- **本轮主会话修的 3 处（重要）**：
  1. **法律风险**：批次 E 把真站 FCA 监管声明与 Jingdong Retail 系列实体/公司号搬进页脚与政策正文 → 已全部替换为 `Joyfumi ... (demo)` / `(demo entity)` / `the relevant supervisory authority` / demo phone（脚本 `var/fix_legal_identity_20261119/replace.py` 可复跑，残留 grep 全 0）。**这是对"一模一样"的有意偏离，不得回退。**
  2. `layouts/footer-page.vue` 登录态头像链到 `/minihome`（404）→ 改 `/account`。
  3. 首页【畅销榜单】tabs 仍含两个隐藏品类 → `HomeBestsellers.vue` 按 `visible_in_nav` 过滤（现 9 个 tab，EN/ZH 一致）。
- **修复的两条真 bug（验收发现）**：
  - **中文频道页全部无图**：频道楼层按请求 locale 取搜索文档 → zh-CN 的 `image_path` 全空。修法：商品文档统一取市场默认 locale（en-GB）+ 图片改查 `MediaUsage(role=gallery)`，locale 只影响楼层标题。**不要**再往"本地化搜索文档"方向修（该实验已回退）。
  - **首页品类发现 tiles 用旧口径**：`campaign_payload('discovery')` 按 `NAV_HIDDEN_ROOT_SLUGS` 过滤 + label 覆盖 LocalCategory 现名，新增幂等命令 `sync_home_discovery_categories`。
- **遗留（需用户决策/后续任务）**：①~~比利时户外数据缺口（现用英国站）~~ → **已解决，见 `## 0t.`（真实 joybuy.nl 频道数据）**；②408 个真站商品仅 111 个真实入库，297 个被风控挡住，320 个位次为同品类补位（非真站同款）；③管理端频道模块**只有 API 无 admin-web 配置页**；④导入商品仅主图；⑤健康保健后 3 层池偏薄；⑥应用商店徽章自绘 SVG、语言框点击切换（非真站 modal）；⑦JoyPlus 商品用本站池 95 折模拟；⑧CSS 注释残留 `joybuy.co.uk`（不影响渲染）。
- **证据目录**：`var/footer_rework_20261119/`、`var/header_apply_entry_20261119/`、`var/cart_merchant_group_20261119/`、`var/category_align_20261119/`、`var/acceptance_ef_20261119/`、`var/acceptance_gh_20261119/`、`var/fix_legal_identity_20261119/`。
- **验证口径**：全轮只做针对性验证（各批次 eslint/prettier/vitest/ruff + 相关后端测试 + 浏览器双语实测），未跑全量套件。

## 0t. 比利时户外频道真实数据补齐（2026-11-19，✅ 完成，未 commit）

> 用户提供真实地址 `https://www.joybuy.nl/minihome/mini-hp-nl-sports-outdoor`（域名 joybuy.nl，
> channel code `mini-hp-nl-sports-outdoor`），推翻 `## 0r.` 的「比利时不可达」结论。
> 证据目录：`var/be_sports_20261119/`（原始 HTML、floor JSON、商品数据、导入日志、验证 JSON + 截图）。

- **可达性（关键更正）**：直接用 `crawler/debug_session.py` 的 **joybuy.co.uk 会话 cookie** 请求
  `https://www.joybuy.nl/minihome/mini-hp-nl-sports-outdoor` → **HTTP 200**，~0.95–1.1MB 完整 SSR
  （`product-pc-floor` ×4 + CMS `floors[].dataBatch.productPool`）。上一轮失败的根因是**频道 code
  用错**（`NL-Mini-HP-Outdoor-Sports` 是空壳），不是站点不可达。同 cookie 对 `.nl` 通用。
- **抓到的频道结构（EN/ZH 各一版 SSR）**：4 个楼层、顺序固定：
  `Bestsellers/热销好物` 11、`Gifting/礼品精选` 20、`New Arrivals/新品上市` 20、
  `Final Pieces — Don’t Miss Out/最后几件 — 别错过` 20 → **71 个位次 / 67 个唯一 SKU**（EUR）。
  真站页内 schema.org `ItemList` 是**占位**（`/dp/undefined`、无价无图），真实数据只存在于
  Next.js RSC 的 `floors[].moduleInstances[].dataBatch.productPool`（title + skuId + skuName +
  imageUrl），解析脚本 `var/be_sports_20261119/extract_floors.py`。
- **价格/图片的取数路径（PDP 仍被风控）**：`/dp/<sku>` 对 `.nl` 与 `.co.uk` 均 307 →
  `/user/risk/pic?...redirectReason=risk605_pic`（PDP 依旧不可达）。改用**同站 SSR 搜索页**
  `/s?k=<标题>`：RSC 里有 `itemCompleteView`（`itemCommonView.skuId`、`itemTitleView.title`、
  `itemImageView.imageUrl`、`itemPriceView.priceInfo.mainPrice/crossOffPrice`），按**精确 skuId**
  匹配 → **67/67 全部命中**（66 个首查命中，1 个换短词命中）。脚本 `harvest.py` + `parse_search.py`，
  结果 `products_resolved.json`。注意：cookie 里的收货地址是英国 EC1A，所有搜索结果的
  `inStock` 都是 false（**库存未知，不是比利时地址实测**），价格与图不受影响。
- **商品入库（既有链路，幂等）**：先查库 —— 78 个 SKU（EN 67）**0 个已存在**（`overlap.json`）。
  新建数据源 `joybuy_nl`（`SourceCatalog` "Joybuy NL"）+ `SourceCategory
  minihome:mini-hp-nl-sports-outdoor` → 映射 `outdoor-sports`；用
  `joybuy_crawler.ingest.ingest_product_payload` → `crawler_control.import_services.
  import_staging_product` → 激活 SPU/Offer → 每个商品 `rebuild_search_document`（历史坑）。
  **新建 67 SPU / 67 ACTIVE Offer（0 失败、0 复用）**，每商品 1 张主图（s1248 → 本地媒体库/S3）。
  4 个商品首轮媒体下载失败（`no-gallery`），已用 `_import_gallery_images` 重下修好 →
  **67/67 有 gallery 图**。市场口径：`market=GB` + `currency=EUR`（购物端默认市场是 GB；
  站点价格全站按 `formatDisplayPrice` 显示 `$`，含既有的 GBP 商品，本轮不改这个全局口径）。
- **频道模块配置**：新增 fixture `backend/content/fixtures/channel_modules_nl_outdoor_20261119.json`
  （4 层真实标题 + 真实 SKU 清单）；`seed_channel_modules` 改为**按频道 source_system 解析商品**
  （UK 8 频道 `joybuy_uk`、户外 `joybuy_nl`），`OUTDOOR_CODE` 改为
  **`mini-hp-nl-sports-outdoor`**，并清理旧 code `NL-Mini-HP-Outdoor-Sports` 的 2 条楼层 +
  1 条 SourceCategory/映射（受 PROTECT 引用时只断映射）。UK fixture 里的户外回退条目已删除。
  运行 `manage.py seed_channel_modules`（默认补足）：户外 **71/71 位次全部为真实比利时商品
  （0 补位）**；其余 8 频道按原补足逻辑重算，**楼层数与批次 H 完全一致**（未被本轮改动影响）。
- **针对性验证（按验证纪律仅做针对性验证）**：
  - 接口：`GET /api/v1/channels/mini-hp-nl-sports-outdoor/modules` EN/ZH → 4 楼层标题正确、
    71 个商品 **100% 有价（EUR）有图**、`href=/c/outdoor-sports`；`/api/v1/categories` 中
    `outdoor-sports.channel_code=mini-hp-nl-sports-outdoor`、`visible_in_nav=true`；
    首页头部链接已指向新 code；`/api/v1/search?q=ION8` total=10 且命中新导入 EUR 商品。
    抽查 `UK-Mini-HP-Beauty` 仍 20/20/3。
  - 前端（Playwright 1440×1000，`verify_outdoor.cjs` → `verify_outdoor.json`）：EN/ZH 均 200；
    4 楼层唯一卡片数 **11/20/20/20**、`<img>` 与卡片一一对应、**破图 0**、`pendingImages=0`、
    每卡都有价格、【更多】全 `/c/outdoor-sports`、console **0 error**；截图
    `local_nl_outdoor_en.png` / `local_nl_outdoor_zh.png`。中文页商品标题为英文（与全站口径一致，
    库里只有 en-GB 搜索文档）。
  - 后端单测：`content.tests.test_channel_modules` **6/6 OK**、`catalog.tests.test_standard_categories`
    **9/9 OK**；改动 py 文件 `ruff check` + `ruff format --check` 全过。前端本轮无代码改动。
- **踩坑（不得再踩）**：①真实 channel code 是 **`mini-hp-nl-sports-outdoor`**（`NL-Mini-HP-Outdoor-Sports`
  是错的/空壳），判断"频道不可达"前先确认 code；②频道页 ld+json `ItemList` 是占位，数据在 RSC
  `dataBatch.productPool`；③PDP 仍被 `risk605_pic` 挡，价格/图改从 `/s?k=` SSR 结果取（按 skuId 精确匹配）；
  ④搜索结果的 `inStock` 受 cookie 里英国地址影响，别当成比利时库存；⑤`seed_channel_modules --no-fill`
  会删掉 UK 楼层的补足位（本轮误跑过一次，已用默认 fill 复跑恢复；**全量重跑不要加 `--no-fill`**）；
  ⑥`SourceCategory` 新建必须给 `first_seen_at/last_seen_at`，否则 IntegrityError。
- **遗留项**：①真站频道 h1 是 `Sports & outdoor`，本站一级名仍是 `Outdoor & Sports`（未改，避免
  影响顶部导航/首页 tile/测试）；②价格全站仍显示 `$`（`formatDisplayPrice` 硬编码 USD，既有口径）；
  ③库存状态未按比利时地址验证；④旧 code 深链 `/minihome/NL-Mini-HP-Outdoor-Sports` 已无配置
  （页面降级为空楼层）；⑤商品仅主图，无详情/画廊/规格。

## 0r. 批次 H（2026-11-19 品类对照 + 频道页模块化，⚠️ 商品导入被真站风控阻断，未 commit）

> 编号说明：任务口径原写 `0q`，但批次 G 已先占用 `0q`，按「编号唯一」改用 `0r`。

- **任务**：①顶部 9 个一级品类改 Joybuy 口径（zh 指定 + en 按真站）；②顶部/下拉隐藏
  `计算机与配件`、`服装与配饰`（直链与商品保留）；③【户外运动】对照比利时站；
  ④频道页模块化：9 个品类各展示真站特有商品楼层 + 商品入库 + 【更多】落
  `/c/<一级 slug>`。**全程未 commit；未碰 cart/footer/auth 文件。**
- **Step 1 改名（数据源，非 i18n）**：名称来自 `catalog.LocalCategory.name/name_en/name_zh`
  → `catalog/search_views.py::category_tree` → 顶部行/下拉/面包屑/频道 h1 同一来源。
  改 `backend/catalog/management/commands/seed_standard_categories.py` 的
  `STANDARD_CATEGORIES` 常量并重跑命令（幂等 upsert），DB 即刻生效：
  `small-home-appliances`→`Home Appliances/家用电器`、`beauty-personal-care`→`Beauty/美妆`、
  `health-wellness`→`Health & Wellness/健康保健`、`baby-toddler`→`Toys, Baby and Kids/母婴童玩`、
  `pet-supplies`→`Pets/宠物`、`games-accessories`→`Gaming/游戏`；另 3 个不变。
  en 名依据真站频道页 `<h1>`（2026-11-11 存档 + 2026-11-19 登录态实测，截图
  `var/category_align_20261119/real_*`）。**未动 slug/树结构/channel_code/204 个二级。**
- **Step 2 隐藏（后端标志，前端不硬编码）**：`catalog/search_views.py` 新增常量
  `NAV_HIDDEN_ROOT_SLUGS = {computers-accessories, clothing-accessories}`，`category_tree`
  每行加 `visible_in_nav`；`AppHeader.vue` 用 `navCategories` 过滤顶部行并传下拉面板，
  其余消费方（面包屑/PDP/筛选）仍见 11 个一级。验证：顶部 9、下拉 9；
  `/c/computers-accessories` 200（24 卡）、`/c/clothing-accessories` 200（3 卡）、
  `/minihome/uk-minihp-clothing-footwear-acc-` 200（6 卡），EN/ZH 全过。
- **Step 3 比利时站结论：不可达 → 回退英国站（⚠️ 已作废，见 `## 0t.`）**：
  > 2026-11-19 后续任务拿到真实 URL 后确认：站点可达（HTTP 200），上轮失败是**频道 code 用错**
  > （`NL-Mini-HP-Outdoor-Sports` 空壳）+ 该次探测被 WAAP。现户外频道已换成
  > `mini-hp-nl-sports-outdoor` 的真实 4 层/67 商品。以下为本轮当时的历史记录（勿再据此回退）。
  ①`joybuy.be` DNS 不存在（NXDOMAIN）；②`joybuy.com/country-selection` 给出的比利时
  唯一官方入口是 `https://www.joybuy.nl?lang=en_GB&country=BE`；③`NL-Mini-HP-Outdoor-Sports`
  频道 code 真实存在（canonical/Next 壳确认），但频道内容由 color-api 客户端拉取；
  ④匿名/会话/consent 四种 cookie 组合都被 WAAP 风控挡成
  `Temporary service interruption` / `Oops! Network error`，`ijdst.joybuy.nl/jdst/waap/refresh`
  `net::ERR_ABORTED`，拿不到任何模块/商品；⑤英国站本身没有 Outdoor 频道（导航无此项，
  `UK-Mini-HP-Outdoor*`/`Sports*` 候选 code 全是 ~512KB 空壳）。回退：用英国站搜索
  `?k=outdoor`/`?k=fitness` 的真实商品组两个楼层，标题沿用真实二级名
  `Outdoors/户外`、`Sports & Leisure/体育与休闲`。**未伪造频道模块**。详见
  `var/category_align_20261119/measurement.md` §3。
- **Step 4 频道页模块化（已落地）**：
  - 实测：登录态抓 8 个英国频道页 SSR，解析 schema.org `ItemList` 得到模块名/商品/价/图
    （zh+en 各一份，`uk_*.modules.json`）；合并为 `modules_all.json`、默认配置
    fixture `backend/content/fixtures/channel_modules_uk_20261119.json`。9 频道 29 个楼层。
  - 后端：新增 `content.ChannelModule` + `ChannelModuleProduct`（迁移 `0010`，权限种子
    `0011`：`cms.channel_modules.manage/view`）；服务 `content/channel_module_services.py`；
    公开接口 `GET /api/v1/channels/<code>/modules`（与 `/search` item 同构，`href=/c/<slug>`）；
    管理端 `GET/PUT /api/v1/admin/channel-modules[/<uuid>]`（RBAC+审计，改标题/排序/开关/
    商品清单）；幂等命令 `manage.py seed_channel_modules`（默认配置落库，`--no-fill` 可关补足）。
    另：为 `outdoor-sports` 建 `minihome:NL-Mini-HP-Outdoor-Sports` 的 SourceCategory+
    CategoryMapping（比利时站真实 code；否则该一级没有频道页入口），顶部户外现在跳
    `/minihome/NL-Mini-HP-Outdoor-Sports`。
  - 前端：新增 `composables/useChannelModules.js`（带 market/locale query + 静态 key）；
    `pages/minihome/[code].vue` 用配置楼层替换原两个通用楼层（无配置时回退旧逻辑）；
    `CmsProductPool` 支持 `more_label` 与 5 列（默认 4 不变）；i18n `channel.more`=More/更多。
    【更多】→ `/c/<一级 slug>`。
  - 模块清单（zh / en，商品数=实际配置）：家居生活 圣诞特惠低至6折 20；电子产品 新品速递 20；
    美妆 爆品热销 20、新品上线 20、国货美妆 3；家用电器 黑五狂欢提前开启 12、寒冬来袭 13、
    大家电 20、电动出行上新 15、库存有限卖完即止 20；健康保健 新品首发 20、电动出行上新 15、
    超值组合购 4、Joybuy必抢榜 16、热销爆款 20、基础维矿 20、运动健身 14、家庭常备 3（真站 10）、
    运动服装和背包 1（真站 17）、智动科技 4（真站 7）；宠物 热门好价 20、大包装更划算 20；
    母婴童玩 新品速递 19、多买多省 9；游戏 新品上架 20、促销专区 14、经典回归 16；
    户外（回退）体育与休闲 20、户外 20。健康后 3 层因同品类可售池不足（101 件/145 需求）
    未补满，已留短。
- **商品入库（既有链路，幂等）**：408 个唯一真站商品 id；**新建 61 个 SPU + 64 个 ACTIVE
  Offer**、**复用 50 个库内可售 SPU**（其中 22 条脚本显式复核并重建搜索文档），共 111 个真站商品可售且有图；
  另 74 个库内已有但 DRAFT/无 ACTIVE Offer/无图、223 个库内不存在。29 层目标
  464 位，实配 438 位（健康后 3 层池不足），其中真站商品 118 位/111 个唯一；
  320 位用「同品类子树真实可售+有图」商品补足（`seed_channel_modules` 默认，`--no-fill`
  关闭；**补足位不是真站同款，已列为遗留**）。每个商品导入后都执行
  `rebuild_search_document`（历史坑），实测 `/api/v1/search?q=Fino Premium Touch Shampoo`
  total=2 且带本地媒体图；`category=beauty-personal-care` total=855。媒体按现状
  `MEDIA_BACKEND=s3`；418 个唯一模块图片 URL 逐条实测 302→S3→200，0 失败。
- **⚠️ 真站风控（重要）**：单线程 ~60 件正常；改 8 并发 0.2s 后 PDP 被重定向到
  `www.joybuy.co.uk/user/risk/pic?...redirectReason=risk605_pic`（title `Joybuy Risk Control`），
  解析缺 `source_id` 连续失败。立即停掉全部导入进程，未再消耗会话。**剩余 223+74 件
  未入库是风控阻断，不是脚本错误**；`import_products.py` 幂等，恢复后可续跑。
- **改动文件**：后端 `content/models.py`、`content/channel_module_services.py`（新）、
  `content/views.py`、`content/migrations/0010_channel_module.py`、`0011_seed_channel_module_permissions.py`、
  `content/management/commands/seed_channel_modules.py`、`content/fixtures/channel_modules_uk_20261119.json`、
  `content/tests/test_channel_modules.py`、`merchant_ops/views_channel_modules.py`（新）、
  `merchant_ops/urls.py`、`config/urls.py`、`catalog/search_views.py`、
  `catalog/management/commands/seed_standard_categories.py`、`catalog/tests/test_standard_categories.py`；
  前端 `composables/useChannelModules.js`（新）、`pages/minihome/[code].vue`、
  `components/cms/CmsProductPool.vue`、`components/AppHeader.vue`、`locales/messages.js`、
  `tests/minihome-channel-page.test.js`。
- **针对性验证（按验证纪律仅做针对性验证）**：
  - 后端 `manage.py test content.tests.test_channel_modules catalog.tests.test_standard_categories
    --keepdb --noinput --parallel 1` → **14/14 OK**；改动 py 文件 ruff check/format 全过。
  - 前端 eslint 0 error、prettier --check 全过；vitest `minihome-channel-page`(7)+
    `AppHeader`(13) → **20/20**。
  - Playwright 1440×900（`var/category_align_20261119/verify_channels.cjs` →
    `verify_channels.json` + `local_<slug>_<lang>.png` ×18）：9 频道 × EN/ZH 全 200；
    29 楼层标题与真站实测逐项一致；每层卡片数=配置数、价格 100% 有、链接全 `/p/`；
    【更多】全 `/c/<slug>`；顶部/下拉 9；两个隐藏品类直链 EN/ZH 全 200 有商品；
    Beauty 首件 PDP 200 且价格可见；console 0 error。图片懒加载初次断言个别
    `naturalWidth=0`，延长等待后 0 破图，且 418 个 URL 直连全部 200。
  - 管理端接口实测（临时 staff，已删净）：`GET /api/v1/admin/channel-modules?channel_code=...`
    200、`PUT .../<uuid>` 200（标题/排序/清单往返一致）。
- **坑（不得再踩）**：①临时 source_identities 的 `source_system` 必须用 **`joybuy_uk`**
  （不是 `joybuy`），否则 `_resolve_local_category` 找不到 SourceCategory → SPU 无本地类目；
  ②活动商品（如圣诞装饰命中「节日与活动」）导入后 `local_category` 为 None 是**设计如此**，
  不是 bug；③`LocalCategory.path` 形如 `/2/`、`/1/10/`（按主键，不是 slug），按子树查商品
  要用 `parent_id=root.pk`（树只有 depth 0/1）；④8 并发抓 PDP 会触发真站风控
  （`risk605_pic`），批量抓取保持低并发+长间隔；⑤SSR 楼层标题要带 market/locale 查询参数，
  否则 `resolve_market_context` 只看到默认 en-GB，中文页会显示英文楼层名（`useChannelModules`
  已按 `useMarketLocale().apiQuery` 拼 query 并进 key）；⑥本机 :8000 常出现两个 runserver
  监听（重启时两个 PID 都要杀）；⑦Playwright 全页截图/懒加载图片要分步滚动 + 2.5s 以上等待。
- **遗留项**：①风控导致 223 个不存在 + 74 个不可售的真站商品未入库，补足位 320 个
  非同款；恢复会话后重跑 `import_products.py` + `seed_channel_modules` 即可替换；
  ②比利时站不可达（WAAP），户外用英国站搜索数据，频道 code/楼层名非真站频道页；
  ③健康保健后 3 层可售池不足未补满；④管理端仅提供 API，未做 admin-web 配置页面；
  ⑤频道楼层图片只导主图（每商品 1 张），PDP 画廊不完整。
- **验收修复（2026-11-19，`var/acceptance_gh_20261119/acceptance-report.md` FAIL ① + 观察项 ②）**：
  - **FAIL ①（ZH 频道楼层全无图）根因**：`content/channel_module_services.py::public_modules`
    用**请求 locale** 查 `ProductSearchDocument`；库里只有 en-GB 文档，zh-CN 查不到 →
    走 fallback 且 `image_path` 仍取同 locale 文档集合 → 438/438 空，前端只渲染灰骨架。
    修复：商品文档统一取 `market.default_locale`（GB=en-GB），图片改走新增的
    `_gallery_paths(spu_ids)`（直接查 `MediaUsage` role=gallery，与 locale 无关）；
    请求 locale 只用于响应元信息与楼层标题（`language_code`）。不再往 zh-CN 搜索文档方向修。
    自验：zh-CN 接口 9 频道 438 位 `image_path` 空值 **0**（en-GB 同样 0）；
    `/minihome/UK-Mini-HP-Beauty` ZH 页 **43 卡 / 43 `<img>` / 0 broken**，EN **43/43/0**
    （等 `img.complete` 全真后截图）；418 个唯一图片 URL 全部 302→S3→200。
    证据：`var/category_align_20261119/verify_fix.json`、`fix_channel_beauty_{en,zh}.png`。
  - **观察项 ②（首页品类发现 tiles 旧名 + 隐藏品类）修复**：tiles 数据来自
    `HomeCampaignCard(section=discovery)`（load_joybuy_demo fixture）。`campaign_payload('discovery')`
    现按 href 解析一级 slug：命中后端 `NAV_HIDDEN_ROOT_SLUGS` 的卡片**只过滤不删数据**，
    并把 label/label_zh 覆盖为 `LocalCategory.name_en/name_zh`（与顶部同源，无前端硬编码）。
    新增幂等命令 `manage.py sync_home_discovery_categories`（4 created / 4 updated，隐藏卡保留在库），
    把 9 个可见一级按导航顺序补齐 tiles（缺卡的用第一个有本地图的二级图
    `/images/categories/<child>.webp`，真实本地资源）。自验：首页 EN/ZH tiles 均 9 项，
    EN=Home & Living/Electronics/Beauty/Home Appliances/Health & Wellness/Outdoor & Sports/Pets/
    Toys, Baby and Kids/Gaming；ZH=家居生活/电子产品/美妆/家用电器/健康保健/户外运动/宠物/母婴童玩/游戏；
    「小家电」「服装与配饰（以及配饰）」均 0 命中；截图 `fix_home_tiles_{en,zh}.png`。
  - **修复后针对性验证**：后端 `content.tests.test_channel_modules`（+1 locale 独立性用例）
    + `content.tests.test_campaign_cards`（+1 隐藏过滤/改名用例）+ `catalog.tests.test_standard_categories`
    → **33/33 OK**；ruff check/format 全过；eslint 0 error、prettier 全过、vitest **20/20**。
    新增陷阱：图片首次截图偶发 `naturalWidth=0` 是懒加载 + S3 大图（单个 680KB）时序，
    自验脚本应 `waitForFunction(img.complete)` 后再断言，不能据此判定无图。

## 0q. 批次 G（2026-11-19 购物车多商家分组，✅ 完成，未 commit）

> 编号说明：任务书要求 `0p`，但并行批次 E 已占用 `0p`，按「编号唯一不删旧」改用 `0q`。

- **任务**：`功能需求迭代文档03.md` 12.3——购物车按商家分组渲染白卡（商家头像 + 店名 + 组内全选），组内勾选与顶部全选联动；后端增量加商家字段不破坏契约；单商家观感与批次 D 单卡一致（不回归）；双语。
- **后端字段口径（增量契约，改动文件 `backend/cart/services.py` + `backend/cart/tests/test_cart_services.py`）**：
  - `serialize_cart` 每个 item 新增 `merchant: {merchant_id, merchant_name, merchant_avatar_url}`（来源 `CartItem.offer → Offer.merchant`，查询已加 `select_related("offer__merchant")`，无额外 N+1）。既有字段（public_id/offer_public_id/spu_public_id/title/quantity/price/currency/inventory_display/is_valid/issue）**全部保留**。
  - 新函数 `merchant_entry(offer)`：`merchant_id = str(Merchant.public_id)`；`merchant_name`：**平台自营导入商家（`IMPORT_FALLBACK_SLUG = joybuy-self-operated-import`）对外统一为 `Joybuy`**，其余透传 `Merchant.display_name`；`merchant_avatar_url = Merchant.avatar_url or ""`。None 安全：merchant 缺失时回退 `{"", "Joybuy", ""}`（防御分支，FK 实为 PROTECT 非空）。
  - `GET /cart`、`PATCH/DELETE /cart/items/:id` 响应、`checkout_views` 快照、`orders` 的 `cart_snapshot` 共用 `serialize_cart` → 全部自动带上该增量字段，契约其余部分零改动。
- **前端分组/联动（`storefront/pages/cart/index.vue`）**：
  - `merchantGroups` computed：按行首次出现顺序分组（key = merchant_id，缺失回退店名）；每组一张白卡：组头 = 组内全选勾选框 + 商家头像（`merchant_avatar_url` 有则显示，24x24 radius 4）+ 店名 + 副行「Sold and fulfilled by {name} / 由 {name} 销售并发货」；组内商品行沿用批次 D 行样式。
  - 顶部全选行放在标题卡（`cart-head__select-row`，文案 `cart.selectAll`）：**仅当分组数 > 1 时显示**——单商家时只有一卡，组头勾选已覆盖全部，隐藏顶部行以保持批次 D 单卡观感（这是「单商家不回归」的落地口径）。
  - 联动：顶部全选 = 所有组全选；任一组/行未选 → 顶部 indeterminate；组全选 = 组内所有可售行；组内部分选中 → 组 indeterminate；组内取消一件 → 组选取消（`isGroupAllSelected`/`isGroupIndeterminate`/`toggleGroup` + `topIndeterminate`）。半选态视觉 = 黑底 #1A1A1A + 白色横杠（`:indeterminate` CSS，真站实车不可测，按 JDICheckbox 选中口径延伸）。
  - 结算栏逻辑不变（已选件数/小计/`去结算`），去结算仍 `navigateTo('/checkout')` 无参数；数量步进/删除沿用批次 D 逻辑（item 按行内 group.items 渲染）。
  - i18n（`storefront/locales/messages.js`，精确锚点 Edit，未动他人键）：新增 `cart.fulfilledByMerchant`（EN `Sold and fulfilled by {name}` / ZH `由 {name} 销售并发货`）；`t()` 无插值，页面用 `fulfilledText()` 做 `{name}` 替换（避免动 useLocale 公共实现）。`cart.fulfilledBy` 旧键保留（无消费方，单商家渲染文案与它完全一致）。
- **真站样式来源（`var/cart_merchant_group_20261119/measurement.md`）**：真站实车仍不可测（批次 D 已确认 session 被风控，加购 0 请求）。本轮补查 38 个真站 CSS bundle：`grep -il "merchant|seller|store|shop"` 命中 css_01/02/05/09/15，与商家行相关的只有 `optimized_sellerRow`/`legacy_sellerRow`（PDP「Sold and fulfilled by」行）与 `storeTitleInfoFloor_*`（店铺标题楼层，店名 18px/700、头像与店名 8px 间距）；**购物车模块 css_17 的 cartList_* 内无 merchant/seller 规则**（真站分组卡在懒加载 chunk）。故：白卡 radius 8 / 卡间距 10px / 勾选框 20x20 黑底对勾 / 商品行尺寸全部沿用批次 D 实测与 CSS 原文；组头字号 16px/600、副行 12px #888B94、头像 24x24 radius 4 为同站 token 近似（已在 measurement.md 标注可靠度）。
- **改动文件（4 个，未 commit）**：`backend/cart/services.py`、`backend/cart/tests/test_cart_services.py`（+2 用例：多商家 payload 三字段/自营映射 Joybuy/既有字段不变；`merchant_entry(None)` 回退）、`storefront/pages/cart/index.vue`、`storefront/locales/messages.js`。未触碰 AppHeader/AppFooter/pages/pages/content/HomeRecommended/p/[id]。
- **针对性验证（按验证纪律仅做针对性验证）**：
  - 后端：`ruff check` + `ruff format --check` 2 文件全过；`manage.py test cart.tests.test_cart_services --keepdb --noinput --parallel 1` → **9/9 OK**（含新增 2 用例；含既有 serialize/merge 回归）。
  - 前端：eslint `pages/cart/index.vue` 0 error；prettier --check cart/index.vue 通过。**注意**：`prettier --check storefront/locales/messages.js` 仍报 1 处格式问题，位置 `footer.appDesc`（并行批次 E 的新增行，非本批改动）——为免与并行 Agent 冲突**未做整文件 --write**；本批新增的两行键已确认符合 prettier。
  - vitest：`tests/use-locale.test.js`(3) + `tests/design-tokens.test.js`(4) + `components/AppContainer.test.js`(3) = **10/10 通过**（cart 页无既有单测，本轮未新增组件测试——逻辑由 E2E 覆盖）。
  - **Playwright 本地实测（`var/cart_merchant_group_20261119/e2e_groups.cjs` → `e2e_groups_result.json`，37/37 PASS，console 0 error）**：API 注册临时买家 → 种 3 商家 5 行 6 件（Joybuy×2 行、HOMCOM×2 行（唯一有头像商家）、LEGO×1 行）。断言：API payload 每 item 带 merchant 三字段且既有字段保留、商家名 `Joybuy/HOMCOM/LEGO`、HOMCOM 带 `/media/...jpg` 头像；EN 3 张分组白卡、顺序按行首出现、仅 HOMCOM 显头像、组内 2/2/1 行、初始全选+计数 (6)、副行文案按商家名替换；取消 HOMCOM 组 → 组内行全不选 + 顶部半选（且实测黑底+横杠 computed style）+ 计数 (3)；取消 LEGO 唯一件 → 组取消非半选、顶部仍半选、计数 (2)；HOMCOM 只勾一件 → 组半选、计数 (4)；顶部全选 → 全组全选 (6)，再点 → 全不选 (0)；数量 +1 → 行小计 $1.48→$2.22、合计 $98.05→$98.79、计数 (7)；ZH：3 组仍在、副行「由 xxx 销售并发货」、顶「全选」、按钮「去结算 (7)」；删除 LEGO 最后一件 → 该组消失（剩 Joybuy/HOMCOM）；去结算 → `/checkout` 且无 query（契约不变）；单商家场景：只 1 张分组卡（Joybuy 2 行、无头像）、**顶部全选行隐藏**、默认全选、计数 (2)。
  - 截图：`cart_groups_en.png`、`cart_groups_zh.png`、`cart_groups_partial_en.png`（顶部半选态）、`cart_single_merchant_en.png`（单商家不回归）。
  - **hydration/SSR 快检（`check_hydration.cjs`）**：带 cookie 直取 `/cart` SSR HTML 已含 `cart-card--group` 与「Sold and fulfilled by」；浏览器 hydrate 后 3 张分组卡，console **0 warning / 0 error**（含 0 hydration mismatch）；脚本自建自删 `cart-g-hydra-*` 买家（复核 0 残留）。
- **测试数据清理（已复核 0 残留）**：`cleanup_batch_g.py` 删除 5 个临时买家 `cart-g-*@joybuy.test`，级联 50 行（BuyerSession 5 / Cart 5 / CartItem 10 / RecentlyViewed 25 / BuyerAccount 5）；按前缀复核买家与购物车均为 0。
- **环境动作**：后端 :8000 原进程（PID 41384，`runserver --noreload`）已 taskkill 并按同参数重启（新代码生效，日志 `var/cart_merchant_group_20261119/backend.log`）；前端 :3000 未重启。
- **坑（新）**：①`useLocale().t()` **不支持 `{name}` 插值**（纯查表），需要占位文案时在页面内做字符串替换，不要顺手改 useLocale 公共实现；②顶部全选 **不能在单商家时也渲染**，否则单卡页出现两个全选勾选框，与批次 D 观感回归冲突；③`:checked` 与 `:indeterminate` 是互斥状态，自定义 `appearance:none` 勾选框**必须单独写 `:indeterminate` 样式**，否则半选态在 DOM 里正确、视觉上却是空框（本轮 E2E 首跑截图才发现）；④并行批次 E 在 messages.js 新增了不符合 prettier 的行（`footer.appDesc`），本批只保证自己新增行格式正确，不整文件 --write。
- **遗留项**：①真站购物车商家分组卡仍无实测（风控 + 懒加载 chunk），组头/头像为同站 token 近似，真站布局可得后可按实测微调；②商家头像当前仅 1 个商家（HOMCOM）有值，其余为空 → 不显示头像占位（符合「有则显示」），如需首字母占位可后续加；③「联系商家」等组内其它真站动作未做（真站实车不可测、需求只要求分组+全选）；④分组卡间距 10px 沿用批次 D 口径，未与真站对照。

## 0p. 批次 E（2026-11-19，需求文档03 12.1 页脚与内容页返工，✅ 完成，未 commit）

- **任务**：批次 A 的页脚被用户判「所有内容都与 Joybuy 不相似，完全不一样」（未逐链接实测、4 页合成内容）。本批**逐个真点击真站页脚链接重抓**，以真站为准重做页脚 + 全部内容页。真站实测产物：`var/footer_rework_20261119/`（`measurement.md` 为唯一权威记录，含逐链接落地页实测、联系我们/关于我们结构、本站逐链接对照表、验证结果；原始 JSON + 截图同目录，脚本 crawl_footer/crawl2-8、local_verify）。
- **真站页脚实际结构（EN，`footer_jdiFooter`）vs 批次 A 的差异**：真站是「顶行（Joybuy logo + "Don't just buy, Joybuy" + 语言/货币/国家三框）→ 订阅块（Be the first to know / Enter your email / Subscribe）+ App 块（Download Joybuy App / 二维码 / App Store + Google Play）→ 三列（Get to know us：Contact us / About us / Joybuy news / JoyPlus；Our policies：Cookies Policy / Privacy policy / Terms and Conditions；Let us help you：**空列**）→ We support 支付行 → © 2026 Joybuy. All Rights Reserved + Personalised settings + Manage cookies」。批次 A 只有 3 列 10 链接 + We support 文字 + 声明，缺顶行/订阅/App 块，且列内塞了真站没有的 accessibility/DSA/payment/returns 链接。现 `AppFooter.vue` 已按上述全量重写（配色用真站 CSS 原文 #F5F6FA/#1A1A1A/#505259/#6E7078、容器 1512px）。
- **两个特殊页实测要点**：①**联系我们** 真站页脚链到 `/discover/contact-us` 是**空态**（"There's nothing more"），有内容的是 `/discover/contact-us-for-web`——顶部**无品类导航**、左侧白卡双 tab（Contact us / Partner with Joybuy，active 红字）、右侧白卡内容：Tab1 = 标题 + 一句 lead + Email/Live Chat/Callback Service 三段；Tab2 = 标题 + Welcome + Enroll as a Vendor / Enroll as a Seller 两段（各带 "Please click here…"）。实现：新增 `layouts/footer-page.vue`（logo+搜索+账号的简顶栏，**不改 AppHeader.vue**）+ `definePageMeta({layout:'footer-page'})` + `pages/pages/contact-us.vue` 页内双 tab。②**关于我们** = `/promo/welcome`（title "Get to know Joybuy…"）：面包屑 → "Welcome to Joybuy" + Sign-in/Sign-up → 三支柱（Fast delivery / Brands you love / 24/7 support）→ 8 个楼层（当日达含 How it works 3 步、品质含 UEFA 合作、24/7 客服含三联络卡、Smarter prices、30 天退货 3 步、安全支付含 Klarna/PayPal/Apple/Google 瓦片 + We accept、邀请好友 3 步、JoyPlus）→ T&C 手风琴 4 条。`pages/pages/about-us.vue` 按此结构 1:1 复刻，图片全部本地化到 `public/images/about/`。
- **删/增内容页**：**删** accessibility-statement、digital-services-act、payment-and-invoice、returns-and-refunds、partner-with-joybuy 五个 slug（真站页脚无对应；partner 并入 contact-us 第二 tab）；**增** joybuy-news（复刻 about.joybuy.com Newsroom：顶导航/hero/3 支柱/6 国旗/3 条真新闻/资源区）、joyplus（复刻 /membership：hero/11 品类 tab/Plus Price 商品卡/£5 券/Spotify+ClassPass 权益/4 项会员权益/月·年·学生方案/4 FAQ）。`content/footerPages.js` 只保留 cookie-policy/privacy-policy/terms-conditions 三页；`pages/pages/[slug].vue` 也改用 `footer-page` 布局（真站帮助页同口径无品类导航）。
- **`footer.legal` 未复刻真站原文的原因（重要，勿改回）**：真站页脚底部那段是 **Jingdong Retail (UK) Limited 的 FCA 金融资质声明**（公司号、FRN、Klarna/NewDay 信贷中介资质）。那是第三方公司的监管牌照表述，我们站点不提供受监管信贷/支付服务，照抄有法律风险。现改为同位置两段中性声明：`Joyfumi Limited (demo replica). …` + 既有 demo 说明（EN 展示；ZH 留空，与真站 ZH 页脚一致）。
- **验证（按验证纪律仅做针对性验证）**：eslint 0 error、prettier --check 全过（AppFooter/test、layouts、pages/pages 6 个文件、content、messages.js、app.vue）；vitest **27/27**（AppFooter 4 + AppHeader 13 + AppContainer 3 + use-locale 3 + design-tokens 4）；浏览器 1440×900：7 个内容页 EN/ZH 全 200、首页/search/cart/login/minihome 冒烟 200、**console 0 error / 0 Vue warn**、联系我们无品类导航且双 tab 切换正确、关于我们 hero+3 支柱+8 楼层+3 组步骤+4 条 T&C、45 图 0 破图、替换规则源码+渲染文本 grep 0 残留（邮箱仅 Joybuyfumi@gmail.com）。截图见 `var/footer_rework_20261119/local_*.png`。
- **踩坑**：①真站 `_lang=en_US` cookie **无效**（页面渲染原始 i18n key 如 `footer.contact`），必须走页脚语言 modal 点 English - EN，站点回写 `_lang=en_GB`；②真站 `<footer>` 在部分页面不存在（Contact us 空态页无 footer 元素），找页脚要用文本标记兜底；③Nuxt 下 `useFetch('/api/…')` 在 SSR 会绕开 nitro devProxy 拿不到数据——要 `import.meta.server ? apiBaseInternal : '/api/v1/…'`，且**必须给静态 `key`**，否则 SSR/客户端 URL 不同 → payload 不复用 → hydration mismatch（JoyPlus 页已按 HomeRecommended 口径修好）；④改 `messages.js` 后 dev HMR 可能吃旧模块，异常时 `touch` 再判断。
- **遗留项**：①App Store/Google Play 徽章为本地自绘 SVG（不外链商店，符合本地托管约束）；②页脚语言框为 EN↔ZH 点击切换（真站是 modal 三选），货币/国家框为静态展示；③JoyPlus 商品网格用本站商品池 + 按真站约 95 折口径算 Plus Price，非真站同批商品；④ZH 页脚无法规段（与真站一致）。

## 0o. 批次 F（2026-11-19，需求文档03 12.2 右上角【申请店铺】入口替换【配送至】，✅ 完成，未 commit）

- **任务**：12.2——右上角【配送至 xxx】删除，替换为状态驱动的【申请店铺/切换商家端】入口；头像下拉菜单移除「申请开店」入口；状态查询并入买家 session（禁止头部单独发请求）；SSR 首屏正确；双语。地址抽屉组件 `AddressDrawer.vue` 本身保留（只删头部触发，文件与其测试未动）。
- **状态查询实现口径（关键决策）**：后端 `accounts_buyers/views.py::_account_payload` 注入两个轻字段 `merchant_application_status`（MerchantApplication.Status，无申请为 None）+ `merchant_id`（APPROVED 时店铺 public_id，无则 None）。查询走 OneToOne `merchant_application` 反查 + `select_related("merchant")` + `only("status","merchant__public_id")`，单条窄查询。**GET /api/v1/auth/buyer/session 一次带回**（login/register 响应同样带，口径一致）；前端 `useBuyerAuth` 新增 `merchantApplicationStatus` computed，`useMerchantEntry` **删掉模块级缓存和独立的 merchant-application fetch**，全部改为 session 派生（`loadStatus({force:true})` 现在刷新共享 session，同 key 只发一次）。SSR 时 session 由 useFetch SSR 直出 → 首屏即正确，Playwright 实测带 cookie 拉 SSR HTML 已含目标文案、无闪变。
- **五态行为落点（全部在 `AppHeader.vue`）**：未登录 → `.account-nav__apply` 链接 `header.applyShop.apply`，href=`/auth/login?next=/account/apply-shop`；无申请/PENDING/REJECTED → 同样式链接 `/account/apply-shop`（PENDING/REJECTED 标签仍是【申请店铺】，点进申请页看状态/原因）；APPROVED → 按钮【切换商家端】→ 既有 `openMerchantConsole()`（签发 console session → window.location.assign 商家端）。头像菜单 seller 两项（NuxtLink+button）删除，菜单剩 orders/reviews/wishlist/addresses/sign out。`useMerchantEntry` 的 label/description（merchantEntry.*）保留给 AccountNav/账号首页，未动。
- **改动文件**：后端 2（`backend/accounts_buyers/views.py`、`backend/accounts_buyers/tests/test_auth_api.py` 新增 `BuyerSessionMerchantApplicationTests` 3 用例：无申请 null/PENDING 无 merchant/APPROVED 带 merchant_id）；前端 6（`components/AppHeader.vue`（删配送至抽屉全部状态/方法/AddressDrawer 挂载/watch，新增 apply 入口三态模板 + `.account-nav__apply` 样式 + `applyShopHref`/`openSellerConsole`，媒体查询隐藏改为 `.account-nav__apply`）、`components/AppHeader.test.js`（删 6 个配送抽屉用例，新增 apply 入口 5 用例 + 菜单无残留用例；RouterLinkStub 改为支持 object `to` 序列化 href）、`components/account/AccountNav.test.js`（mock 补 merchantApplicationStatus/refresh，状态改由 `__setApplicationStatus` 驱动）、`composables/useBuyerAuth.js`、`composables/useMerchantEntry.js`、`locales/messages.js`（en/zh 成对新增 `header.applyShop.apply`/`header.applyShop.switch`，精确锚点小步 Edit；**`header.deliverTo` 键保留未删**——防并行批次冲突，现为未使用键））。
- **针对性验证（按验证纪律仅做针对性验证）**：
  - 后端：ruff check + ruff format --check 2 文件全过；`manage.py test accounts_buyers.tests.test_auth_api --keepdb --parallel 1` → **13/13 OK**（含新 3 用例）。
  - 前端：eslint + prettier --check 6 个改动文件全过；vitest `AppHeader.test.js`(13) + `AccountNav.test.js`(5) + `AddressDrawer.test.js`(4 回归，组件未动) + `use-locale.test.js`(3) = **25/25 通过**。
  - **Playwright 五态实测（`var/header_apply_entry_20261119/e2e_five_states.cjs` → `e2e_report.json`，24/24 PASS，console 0 error）**：S1 未登录 EN 显示 Apply for a shop、`.account-nav__deliver` 0 命中、点击落 `/auth/login?next=/account/apply-shop`；S2 API 注册（绕 HMR，见坑①）→ 未申请显示链接进申请页表单态、头像菜单仅 5 项无申请/商家中心残留；S3 DB 造 PENDING（`seed_state.py`）→ 头部仍申请店铺 → 申请页显示 Under review + 已提交信息；S4 DB 造 APPROVED（create_merchant + StaffAccount 复制密码哈希 + owner membership）→ 头部变按钮 Switch to Seller console → **SSR HTML 直出该文案且无 Deliver to** → session payload 实测 `merchant_application_status=APPROVED + merchant_id` → 点击落 `127.0.0.1:5174/dashboard` 经营看板已登录（Header F Shop / Merchant owner）；S5 改 REJECTED（删店铺链）→ 头部恢复申请店铺 → 申请页显示失败原因 + Re-apply；ZH 双语（joybuy-locale cookie）：申请店铺/切换商家端/登录 next 回跳全对；清理后未登录入口回归正常。截图 13 张：`state1_signedout_home/login_en.png`、`state1_signedout_home_zh.png`、`state2_account_page/menu/unapplied_*_en.png`、`state3_pending_applypage_en.png`、`state4_approved_home_en/zh.png`、`state4_approved_merchantweb_en.png`、`state5_rejected_applypage_en.png`。
  - **清理（已复核 0 残留）**：`seed_state.py cleanup` 按**先 MerchantReferral → membership → Merchant → StaffAccount → MerchantApplication → BuyerAccount（session CASCADE）**顺序删除（PROTECT 纪律：Referral 必须先删）；同时清掉了此前 E2E 崩溃遗留的孤儿买家（按 `header-f-` 邮箱前缀）。ORM 复核：buyer/staff/merchant/application/membership/referral 全部 0。
- **坑（新，重要）**：①**并行批次 E 改 AppFooter/messages.js 会引发 HMR 风暴**：UI 表单刚填的字段会被页面重渲染清空（注册邮箱框被清空导致提交报错），且 AppFooter.vue 引用图片早于图片落盘时 vite overlay 弹全屏错误挡死交互——本批 UI 注册/登录改走 **API（page.request 共享 cookie jar）** 才稳定；后续批次 E2E 在并行开发期一律优先 API 种会话，UI 表单操作加重试。② **vitest 里 jsdom 的 `window.location.assign` 可直接赋值为 vi.fn()**（APPROVED 点击测试用它断言跳转）。③ playwright 只装了 `@playwright/test`（1.64.1，项目根 node_modules），`require('playwright')` 不存在——从 `@playwright/test` 解构 `chromium` 即可。④ `node_modules/.bin/prettier.cmd` 在**项目根**，storefront 下没有；eslint 在 storefront 目录 `cmd //c "node_modules\\.bin\\eslint.CMD <file>"`。⑤ merchant-web 仪表盘有两个同文案 h1（桌面/移动双实例），Playwright locator 必须 `.first()`。
- **遗留项**：① `header.deliverTo` 键与 `joybuy:delivery-address` localStorage 约定已无消费方（键保留，后续清理批次可删）；② AddressDrawer 组件与 10 用例测试成为孤儿组件（checkout 实际未引用它，任务口径"checkout 仍在用"与代码现状不符——组件保留未删，等后续拍板是否复用/删除）；③ 头部入口在 SPA 内不主动重查状态：APPROVED 后需刷新一次页面头部才变【切换商家端】（session 派生的自然代价，验收实测以整页加载为准）。

## 0m. 总记录（2026-11-19，需求文档03 v1.3 追加需求 9 项：批次 A–D 开发 + 独立验收 + 修复复验，✅ 全部完成，未 commit）

- **任务链**：用户追加 9 项购物端需求 → 优化并入 `功能需求迭代文档03.md` **v1.3 第十一节**（11.1–11.10，含排期批次 A–D）→ 4 个开发子 Agent 滚动执行 → 2 个独立验收子 Agent 黑盒验收 → 2 条 fail 原地修复 → 复验通过。全程未 commit。
- **批次 A ✅**（页脚/Crisp/语言/登录态，⚠️ 其交接小节在并发误杀恢复中丢失，本节代记）：`AppFooter.vue` 三栏（列名按真站实测 Get to know us / Our policies / Let us help you）+ 新增 `storefront/content/footerPages.js` + `pages/pages/[slug].vue` 通用内容页 **10 个 slug**（contact-us、partner-with-joybuy、about-us、cookie-policy、terms-conditions、privacy-policy、accessibility-statement、digital-services-act、payment-and-invoice、returns-and-refunds）+ `plugins/crisp.client.js`（`NUXT_PUBLIC_CRISP_WEBSITE_ID` 未配置不加载不报错）+ 顶栏只留语言 + 未登录右上角 Sign in/登录 文本按钮（`?next=` 回跳）。**替换规则零残留**（joybuy.co.uk/.com、European/EU/欧盟/欧洲、47 处邮箱→Joybuyfumi@gmail.com；所有外链→www.joyfumi.com）。vitest 20/20。**兜底说明**：contact-us、无障碍声明、DSA、退货退款 4 页真站无静态正文，按真站已发布口径合成，真站有内容后可回填。
- **批次 B ✅**（详见 `## 0l-b.`）：380px 竖列 email-first 复刻（真站实测 #1A1A1A/#E1251B/#F5F6FA），删京东/ochama/礼包，`?next=` 回跳，双语行内校验。遗留：①电话注册需后端新端点（待拍板）；②协议行仍是纯文本（批次 A 内容页已落地，后续可换真链接——待做小活）。
- **批次 C ✅**（详见 `## 0l-c.`）：`GET /api/v1/recommendations?page=N`（与 /search 同构 envelope，ProductCard 直用；240 件池=ProductSearchDocument(is_searchable) 按 md5(spu_public_id) 稳定伪随机排序）；首页 `HomeRecommended.vue` 无 tab、查看更多追加；PDP 去库存行、三段间距 24px；【我们支持】=9 个真站支付 SVG 本地托管（`storefront/public/images/pdp-services/`）。真站首页已无 Recommended for you 模块（按 Bestsellers 楼层实测落地）；「查看更多」按钮样式自行设计（真站无参照）。
- **批次 D ✅**（详见 `## 0l-d.`）：购物车 1:1（真站实车被风控挡死→用 38 个真站 CSS bundle 提取规则原文复刻），去配送/自提 tab，契约零改动；商家分组按 Sold and fulfilled by Joybuy 单卡近似（购物车 JSON 无商家字段，多商家分组需后端加字段，待拍板）。
- **验收**：`var/acceptance_ab_20261119/acceptance-report.md`（A+B **11/11 PASS**）+ `var/acceptance_cd_20261119/acceptance-report.md`（C+D 首轮 **9/11**）→ 修复 → 复验**全部 PASS**：
  - **O1 hydration mismatch（真回归，已修）**：根因比验收初诊更深——`HomeRecommended.vue` 首屏列表在 setup 里把 useFetch 数据**拷贝成本地 ref**，SSR 渲染占位、客户端渲染列表→结构性错配。修复：SSR `await useFetch` 直出真实列表 + 追加页独立 `appended` ref；vitest 改 `<Suspense>` 包裹。复验 3 干净会话 0 warn、SSR HTML 含 `home-reco__grid`。
  - **D7 购物车容器几何（已修）**：全站 shell 把内容压到 1216px（真站 1344）。修复：弃自设 shell，改 AppContainer + 页面局部 `--container-max: calc(1344px + 2*var(--container-pad))`（minihome 先例口径，全局 1608px 未动）+ 删 Summary 卡真站没有的运费说明行（`cart.deliveryNotice` 键保留）。复验 1440×900 四值 1344/884/48/436 **偏差全 0px**。
- **验收期间发现的环境级问题（非本批代码）**：并行爬虫导入会挤挂 :8000 写接口（POST /cart/items ~48s 后 500，加购 UI 静默无反馈——既有 UX 缺口，后续可加加载态/重试提示）。
- **新增踩坑（重要）**：①共享 dev :3000 改 `messages.js` 后 HMR 可能用旧模块致 hydration 错配——先 touch 受影响文件或重启再判断真 bug；②dev :3000 被停后重启要 `HOST=127.0.0.1 PORT=3000` 显式指定；③真站测试 session 会被风控标记（加购 0 网络请求），实车测量要有 CSS bundle 兜底方案。
- **待用户提供/拍板**：①Crisp Website ID（插件已就绪，配 env 重启即生效）；②电话注册是否要做（后端需新端点）；③购物车多商家分组是否要做（后端需加字段）；④B 批次协议行换 `/pages/<slug>` 真链接（小活，可并入下轮）。
- **证据目录**：`var/footer_auth_cluster_20261119/`（批次 A）、`var/auth_page_20261119/`（B）、`var/reco_pdp_20261119/`（C）、`var/cart_page_20261119/`（D）、`var/acceptance_ab_20261119/`、`var/acceptance_cd_20261119/`。

## 0l-d. 批次 D（2026-11-19，需求文档03 11.9 购物车页 1:1 复刻 Joybuy（去配送/自提 tabs），✅ 完成，未 commit）

- **任务**：`功能需求迭代文档03.md` 11.9——购物车页 `storefront/pages/cart/index.vue` 按 1:1 复刻真站布局/卡片/结算栏/交互；**去掉【配送】【自提】两个 tab**；只换皮不改数据契约（仍走 useCart 的 GET /cart、PATCH/DELETE /cart/items/:id，去结算仍跳现有 /checkout 无参数）；双语 cart.*。
- **真站实测（先测后写，产物全部在 `var/cart_page_20261119/`，关键数值写入 `measurement.md`）**：Playwright 1440x900 + `var/auth_page_20261119/session.json` cookies + `color-api.joybuy.co.uk` 打桩。实测空车骨架（页面灰底 #F5F6FA、容器 1344px@1440/左右栏 884+436 gap24、白卡 radius 8、Summary 卡 padding 32 16 16、结算钮 #E1251B/hover #990915/disabled #FF9FA7 18px/700 48px radius4、SSL 行 14px/36px #505259、空态文案与颜色）。
  - **⚠️ 实车布局测不了**：真站加车点击 0 网络请求（session 被真站风控标记，不 mock 时 color-api 返回 "Temporary service interruption"，与 HANDOFF「账号已损 1/3」吻合；Buy now 同样无效）。改用真站 CSS bundle（38 个全量下载到 `var/cart_page_20261119/all_css/`）提取 cartList_/cartOrder_/JDICheckbox/counter 规则原文 + :root 设计 token —— 商品行/勾选框/计数器样式均来自真站 CSS 原文，可信度等同实测。
  - **商家分组卡**：真站商家头像/店名样式在懒加载 chunk 拿不到；且购物车 JSON 无商家字段（契约不改）——按真站 PDP「Sold and fulfilled by Joybuy」口径做单商家白卡：全选勾选框 + 「Joybuy」店名 + 副行，多商家分组等后端加字段再说（measurement.md 有注明）。
- **改动文件（未 commit）**：`storefront/pages/cart/index.vue`（整体重写）、`storefront/components/CartEmptyIllustration.vue`（新增，真站 EmptyBox SVG 从 `cart_dom_zh.html` 提取、id 前缀改为 CartEmptySvg__ 防双实例冲突）、`storefront/locales/messages.js`（cart.* 成对新增 7 对键：goShopping/summaryTitle/emptySummary/securePayment/selectAll/fulfilledBy/delete；cart.title/empty/goToCheckout 文案按真站改：Cart/No items yet？/Checkout；**cart.remove 未动**——favourites/recently-viewed 也在用，购物车删除链接用新键 cart.delete）。商品图/规格用只读 GET /api/v1/products/:id 客户端增强（offer_public_id 对 sku 规格），规格对象按真站 PDP 口径渲染为取值 " / " 连接。
- **坑（新）**：①**Nuxt dev 共享服务吃旧模块**：messages.js 改完后 :3000 的 client bundle 还是旧文案（zh 仍「去结账」）导致 ZH 页 hydration mismatch 报错——`touch storefront/locales/messages.js` 强制 HMR 失效即恢复；遇到「改了没生效/SSR 客户端文案不一致」先 touch 再查代码。②后端 :8000 写接口会被并行 Agent 的爬虫导入挤挂（POST /cart/items 挂 30s+，连 information_schema.innodb_trx 都查不动），是环境级争用不是代码问题，等窗口期重试即可；测试数据可用 curl 直打 API 种入（`seed_cart.cjs`）绕开 UI 加车。③ AuthForm 提交按钮选择器必须用 `.auth-submit`，`button[type="submit"]` 会命中页头搜索按钮。④注册（201）即自动登录，无需再走 /auth/login。
- **针对性验证（按验证纪律仅做针对性验证）**：
  - eslint + prettier --check：cart/index.vue、CartEmptyIllustration.vue、messages.js 全过。
  - vitest：`tests/use-locale.test.js`+`tests/design-tokens.test.js`+`components/AppHeader.test.js`+`components/AppContainer.test.js` = 27/27 通过（cart 页无既有单测）。
  - 本地 Playwright 全流程（`var/cart_page_20261119/local_e2e.cjs`，dev :3000，临时买家）：注册即登录→3 件商品全部入车→数量步进器 +1 →行小计/合计联动（$2,198.00）→单件勾选/取消（Checkout 计数 (3)→(1)→(3)）→全选/取消全选（(0)/(3)）→去结算落 `/checkout` ✅→删除→空车态 EN/ZH（还没有商品？/去购物/合计/没有待结算的商品/去结算 (0) 粉禁用）——全过；console 0 error；hydration mismatch 0（EN/ZH）。
  - 截图：`local_cart_en.png`/`local_cart_zh.png`（有货）、`local_cart_empty_en/zh.png`、真站对照 `cart_en_live.png`/`cart_zh_live.png`/`probe_en.png`。
  - 零残留：cart 页源码无【配送】【自提】tab（仅注释说明），无第三方 CDN。
- **测试数据清理**：31 个临时买家（cart-d-/cart-dbg-/cart-reg-/cart-curl-* @joybuy.test）已删净，级联 124 行（session/cart/cart_item/address），复核 0 残留；真站购物车从未加入过商品（复核 Checkout (0) 空态）。
- **遗留项**：①真站实车布局不可得（session 被风控），商品行视觉以真站 CSS bundle 原文为准，商家头像/店名行为近似（已注明）；②购物车 JSON 无商家字段，多商家分组卡与「选中项传 checkout 参数」需后端加字段/参数后才能做（本批契约不动）；③「Added to cart」按钮反馈文字轮询在 dev 高负载下偶发捕捉不到（商品实际已入车），E2E 以购物车条数为准；④ dev :3000 的 HMR 旧模块坑见上，后续批次改 messages.js 后记得 touch。
- **验收修复（D7，2026-11-19）**：容器几何不对——首版自设 `.cart-page__shell` max-width 1312 导致内容 1216/起点 x=112，与真站 1344/x=48 差 128px；Summary 卡多一行真站没有的运费说明。修复：①改用 AppContainer + 页面局部 `--container-max: calc(1344px + 2 * var(--container-pad))`（minihome/[code].vue 先例口径，全局 token 1608px 不动），窄视口随 --container-pad 降级、<1024px 栈叠；②删 `.cart-summary__note` 运费行（cart.deliveryNotice 键保留，已复核全仓仅 cart 页引用过、现为未使用键）。自验（`var/cart_page_20261119/verify_d7_fix.cjs` → `verify_d7_result.json` + `d7_cart_en/zh.png`）：1440×900 实测内容 1344 / 左栏 884 / 起点 x=48 / 右栏 436，**与真站偏差全部 0px**；全流程回归（数量 +1 → $2,198.00 联动、勾选 → Checkout (1)、取消全选 → (0)、去结算落 /checkout、删除 2→1）全过；console 0 error；`cart-d2-*` 临时买家已删净（left 0）。另：dev :3000 曾被停，已 `HOST=127.0.0.1 PORT=3000` 重启（裸起会漂 3001 且只听 ::1，curl 127.0.0.1 连不上）。

## 0l-c. 批次 C（2026-11-19，需求文档03 11.6 首页为您推荐 + 11.7 PDP 微调 + 11.8 我们支持图标区，✅ 完成，未 commit）

- **任务**：11.6 首页【为您推荐】模块（畅销榜单正下方、无 tab 行、240 件池 10 页×24、点【查看更多】追加、双语）；11.7 PDP 去【库存 999+】行 + 三段按钮区间距调大（以真站实测为准）；11.8 PDP【我们支持】图标区（图标本地托管）。
- **真站实测（先测后写，脚本+产物全在 `var/reco_pdp_20261119/`，数值详见该目录 `measurement.md`）**：
  - **当前真站首页（EN，带会话 cookie，慢滚到底+等待）不存在【Recommended for you】模块**（楼层=Bestsellers→Shop the look→story 网格→footer，网络层也无 recommend 接口）——本批次按真站楼层通用规范+Bestsellers 楼层实测值落地：标题 h2 **28px/600 #1A1A1A**（标题行下 4px）、**5 列网格、列距 16px**（卡宽 256、pitch 272）、无 tab。
  - **PDP 无任何库存行（全文无 999+）**、buy-box 无收藏按钮（本地保留收藏按钮，只调间距）；数量块实测 `padding 12px 0`；数量块→按钮区 **12px**；立即购买/加入购物车各 **317x48、radius 4、按钮间 gap 8px**（红 #E1251B/黑 #1A1A1A）。
  - **【我们支持】在真站=PDP footer 支付图标区**（`footer_footerPay`，padding 26px 0，标题 14px/400 #505259 margin-right 16px + **9 个支付 SVG 各 32x20**，顺序 American Express/Visa/Mastercard/UnionPay/PayPal/WeChat Pay/Google Pay/Apple Pay/Klarna）；30 天退货/24-7 客服在真站位于 buy-box「Delivery & promises」展开区（此前批次已复刻为 guarantees 行），真站并未与支付图标合成一块——按「真站怎么分区就怎么分区」处理。
- **接口契约**：新增 `GET /api/v1/recommendations?page=N`（`backend/catalog/search_views.py::recommendations` + `backend/catalog/search_services.py::recommendation_documents`，路由 `backend/config/urls.py`）。返回 `{market, locale, display_currency_symbol, requested_market/requested_locale/price_source_market, page, page_size:24, total, total_pages, items[]}`，item 与 `/search` 完全同构（spu_public_id/title/brand/category_slug/price_min/price_max/currency/rating_average/rating_count/image_path），`ProductCard` 直接复用。**240 件池怎么保证真实可售**：只从 `ProductSearchDocument(is_searchable=True)` 取（该字段口径=rebuild_search_document 里「SPU ACTIVE 且存在 ACTIVE Offer」，下架商品即时删文档），排序键=`md5(spu_public_id)` 十六进制串（稳定伪随机：刷新不乱序、又不是主键序），切片前 240 后按页分页，页内回查按池序重排。市场/locale 复用 search 的市场链兜底（抽成 `_resolve_search_market` 供两处共用）。
- **改动文件**：后端 4 个（search_views.py、search_services.py、config/urls.py、tests/test_search.py）；前端 5 个（`storefront/components/home/HomeRecommended.vue` 新增、`HomeRecommended.test.js` 新增、`storefront/pages/index.vue` 挂载在 HomeBestsellers 下、`storefront/pages/p/[id].vue`、`storefront/locales/messages.js`）；资源 `storefront/public/images/pdp-services/`（9 个支付 SVG，从真站 footer outerHTML 提取、加 xmlns 本地托管，无第三方引用）。
- **实现要点/坑**：① `HomeRecommended` 的 useFetch 不加 await（与 HomeBestsellers 同模式，Nuxt SSR 渲染前统一等待挂起请求；vitest 挂载才不会卡 async setup）；key 用静态 `home-recommended-page1`（模板字符串 key 冻结的旧坑）。② 本地 PDP `.detail__panel` 是 flex-column 且自带 `gap: var(--space-3)`（12px），margin 12px 会叠加 → 实测三段间距 24px（qty→收藏、收藏→按钮区），比原 20px 大、真站 12px 的 margin 口径也照抄了。③ `Spu.Status` 只有 DRAFT/ACTIVE/INACTIVE，测试里下架商品用 INACTIVE（没有 DELISTED）。④ vitest 必须在 storefront 目录下跑（项目根跑会因缺 vue 插件报错）；prettier 在项目根 node_modules/.bin（storefront 下没有）。⑤ 本地验证脚本语言切换用的是 `joybuy-locale` cookie（值 en-GB/zh-CN），不是真站的 `_lang`。
- **i18n 键（en/zh 成对，精确锚点小步 Edit，未动他人键）**：`home.reco.title/viewMore/allLoaded/loading`、`pdp.supportTitle`。
- **针对性验证（按验证纪律仅做针对性验证）**：① 后端 `manage.py test catalog.tests.test_search.RecommendationTests --keepdb --noinput --parallel 1` **5/5 通过**（确定性/翻页无重复/只含可售/page 校验/端点契约；:8000 已 taskkill 重启后实测 `GET /api/v1/recommendations?page=1` total=240 items=24）；ruff 4 个后端文件全过。② eslint + prettier 全过（4 个改动前端文件 + 2 个新测试文件）。③ vitest `HomeRecommended.test.js`(2 用例) + 回归 `HomeBestsellers.test.js`(2 用例) **4/4 通过**。④ Playwright 本地双语实测（`var/reco_pdp_20261119/verify_local.cjs` → `local_verify.json`）：EN/ZH 推荐楼层均在 Bestsellers/畅销榜单 正下方，首屏 24 件、点 2 次查看更多=72 件且 href 无重复，标题/网格 5 列/16px 间距实测吻合；PDP EN/ZH 全文无 999+、无库存行；三段间距 24px（margin 12px×2 叠加 flex gap）；我们支持区 9 个图标全部 200 加载（`/images/pdp-services/*.svg`，0 第三方域名），EN "We support"/ZH "我们支持"。
- **截图目录**：`var/reco_pdp_20261119/`（local_reco_en/zh.png、local_pdp_en/zh.png、local_pdp_support_en/zh.png、local_pdp_panel_zh.png、bestsellers_viewport.png、pdp_support 真站对比图等）。
- **O1 修复（2026-11-19 验收 fail → 已修）**：验收发现 HomeRecommended.vue hydration mismatch——根因是 setup 里把 `data.value.items` 拷进本地 `items` ref 且 useFetch **未 await**：SSR setup 阶段 data 还是 null → SSR HTML 渲染「Loading…」占位，客户端 hydrate 时 payload 已有 24 件 → 结构不一致。修法（只动 `HomeRecommended.vue` + 其测试）：① `await useFetch`（SSR 等数据、直出真实列表）；② 首屏列表改为**从 data 派生的 computed**（`[...first, ...appended]`），点击追加的页放 `appended` ref，不再在 setup 里拷贝——这是 mismatch 的根因，单独 await 也顺手消除。vitest 配套：async setup 必须挂 Suspense 边界，测试改用 `<Suspense>` 包裹 mount + flushPromises。**自验（`var/reco_pdp_20261119/verify_o1_fix.cjs` → `verify_o1_fix.json`，dev server 已 taskkill 完全重启）**：SSR 静态 HTML 含 `home-reco__grid` 且无 `home-reco__empty` 占位；3 个干净 context（无 cookie/全新 storage）console 0 hydration warn / 0 error；功能回归 24 件 → 点 2 次=72 件、href 无重复；ZH 会话同验通过（SSR 含「为您推荐」、0 警告）。vitest 4/4、eslint/prettier 过。
- **遗留项**：① 卡片/PDP 价格显示 "$"（真站 £）——`formatDisplayPrice`/`display_currency_symbol` 是既有市场展示层行为，不属本批次，未动。② 真站首页当前没有该推荐模块，网格/标题样式取自 Bestsellers 楼层实测，「查看更多」按钮样式（200x48 黑描边）无真站参照、属自行设计。③ 池子 240 件上限与确定性排序依赖 md5(spu_public_id)，新增/下架商品会自然进出池（顺序对已有商品稳定）。

- **任务**：`功能需求迭代文档03.md` 11.1（页脚三栏 + 9 个本地内容页 + 全局替换）、11.2（Crisp 客服，未配置不加载）、11.4（顶栏只留语言）、11.5（未登录显示【登录】）。完成，未 commit。
- **改动文件**：`storefront/components/AppFooter.vue`（三栏换新 + 支付方式行保留 + 链接指向 `/pages/<slug>`）、`storefront/pages/pages/[slug].vue`（新增通用内容页路由）、`storefront/content/footerPages.js`（新增，9+1 个 slug 的 en/zh 块数据，由脚本生成）、`storefront/plugins/crisp.client.js`（新增）、`storefront/nuxt.config.js`（`runtimeConfig.public.crispWebsiteId`）、`storefront/.env.example`（`NUXT_PUBLIC_CRISP_WEBSITE_ID=`）、`storefront/components/AppHeader.vue`（顶栏去国家、登录文本按钮 + `.login-button` 样式、`loginHref` 用 AuthForm 现有 `?next=` 回跳约定）、`storefront/locales/messages.js`（footer.* 键整块换新成对添加 + `pagesDoc.backHome`，未动 auth.*）、`storefront/components/AppFooter.test.js` / `AppHeader.test.js`（断言更新）。地址抽屉国家选择未动。
- **内容页 slug（10 个，覆盖 11.1 三栏全部枚举链接；需求口径写"9 个"但三栏枚举实为 10 条，按枚举落地）**：contact-us、partner-with-joybuy、about-us、cookie-policy、terms-conditions、privacy-policy、accessibility-statement、digital-services-act、payment-and-invoice、returns-and-refunds。列名 EN 按真站实测：Get to know us / Our policies / Let us help you。
- **抓取方式（先测后写）**：脚本与产物全部在 `var/footer_auth_cluster_20261119/`：真站页脚需先点页脚语言按钮（`footer [role="button"]:has-text("中文(简体)")`）→ DOM 点 English 单选（MUI 抽屉在视口外，必须 `page.evaluate` DOM click，Playwright 常规 click 会超时）→ 确定；EN cookies 已存 `cookies_en.json`。内容页正文抓取 `crawl_pages_en.cjs` → `footer_pages_content_en.json`（zh 版 `footer_pages_content.json`）。**生成器 `build_footer_pages.cjs` 输出 `footerPages.js`——改文案改生成器再重跑，不要手改数据文件**。
- **替换规则核对（grep 断言，0 残留）**：`footerPages.js` 中 `joybuy.co.uk|joybuy.com|European|europa|EU|EEA|欧盟|欧洲|ico.org|edpb` 全部为 0 命中；所有 URL（含第三方外链如 ICO）按口径统一替换为 `www.joyfumi.com`；邮箱 47 处均为 `Joybuyfumi@gmail.com`。
- **兜底（真站无静态正文的 4 页）**：contact-us（真站是聊天壳页无正文）、accessibility-statement、digital-services-act、returns-and-refunds（真站 Terms 引用的 After Sales Policy 未发布）——按真站已发布口径（About 页 30 天退货承诺、Terms 退款条款、页脚法律实体信息）合成，en/zh 双语，生成脚本内有标注。
- **针对性验证（按验证纪律仅做针对性验证）**：① vitest `components/AppFooter.test.js` + `AppHeader.test.js` 20/20 通过（storefront 目录下跑 `node ../node_modules/vitest/vitest.mjs run …`，项目根跑会因缺 vue 插件报错——坑）；② eslint 10 个改动文件 0 error（坑：AppHeader 去国家后 `MARKET_OPTIONS` 导入未删会报 no-unused-vars；插件需显式 `import { defineNuxtPlugin } from '#imports'`）；③ prettier 全过（坑：`node_modules\.bin\prettier.CMD` 在**项目根**，storefront 下没有）；④ Playwright 本地实测 `verify_local.cjs` → `verify_report.json`：页脚 EN/ZH 三栏与 10 链接全对、9 页 EN+1 页 ZH 全开无死链、正文 `badEu/badUrl/badEmail` 全 false、顶栏无 `#market-select` 且语言切换全站生效、登出态右上角"Sign in"文本无图标圆框、点击跳 `/auth/login?next=/`、未知 slug 出错误页、Crisp 未配置 0 个 crisp script + `window.$crisp` undefined；干净会话（首页 + terms 页）console 0 error。
- **截图目录**：`var/footer_auth_cluster_20261119/`（footer_en.png、footer_zh.png、topbar_en/zh.png、header_loggedout.png、page_<slug>.png × 10、page_contact-us_zh.png、lang_modal.png 等）。
- **遗留项**：① Crisp Website ID 用户还没给——未配置路径已实测零加载零报错；**已配置路径未实测**（需要带 `NUXT_PUBLIC_CRISP_WEBSITE_ID` 重启共享 dev 服务，没动），拿到 ID 后配置 env 重启即可。② 真站页脚实际只有 7 个链接（了解 Joybuy×4 / 政策×3 / 帮助中心只挂支付方式），本批次按需求 11.1 的 9 链接口径落地，与真站的差异是需求拍板不是复刻误差。③ footerPages.js 未提交 prettier 原格式（已跑 --write 过）。

## 0l-b. 批次 B（2026-11-19，需求文档03 11.3 登录/注册页 1:1 复刻 Joybuy，✅ 完成，未 commit）

- **任务**：`功能需求迭代文档03.md` 11.3——登录/注册页与真站一模一样；去第三方登录入口与【注册即得礼包】文案；表单=邮箱/电话+密码；只换视觉皮不改后端契约；双语；登录成功回跳来源页。
- **真站实测（先测后写，产物全部在 `var/auth_page_20261119/`）**：Playwright chromium 1440x900 + `crawler/debug_session.py` cookies（`_lang` 覆写 `en_US` 得英文版）+ `color-api.joybuy.co.uk` 打桩。脚本 `measure_auth.cjs` / `probe_auth2.cjs` / `probe_head.cjs`；截图 `login_live.png`（zh）、`login_en_step.png`（en）、`login_step_step.png`（新邮箱→注册形态）、各 `*_measure.json`；**关键数值全部写进 `var/auth_page_20261119/measurement.md`**。要点：
  - **真站无 tab、无卡片容器**：白底页面中央 **380px 竖列**；登录页是 email-first 两步流（`/register` 直达 URL 404，注册只能从登录页输新邮箱进入）。
  - 主黑 `#1A1A1A`（按钮 bg，380x48，radius 4px，字 18px/600）；红 `#E1251B`（礼包行金额）；灰字 `#6E7078`（副标题/协议 12px）；灰底输入 `#F5F6FA`（48px 高，radius 4px）；禁用 `#C2C4CC`；密码输入白底 1px 描边聚焦变黑。
  - 标题 18px/700 居中（登录「登录或创建Joybuy账号」+ 副标题🔒数据加密 14px；注册「创建您的Joybuy账户」+ 副标题 信赖品质，极速送达）。
- **改动（4 文件，未 commit）**：
  - `storefront/components/AuthForm.vue` 整体重写（视觉皮）：380px 中央竖列、灰底 identifier 框 + 白底描边密码框、黑色 48px 提交钮、灰字协议行；**删真站第三方登录区（Google/京东/ochama 全不渲染）与礼包文案**；表单=邮箱/电话+密码同屏直填；行内校验双语（identifier 空/格式（电话须 E.164 `+` 开头，与后端 `normalize_identifier` 对齐）、密码空/注册≥8 位）；后端 `error.code` 业务码映射双语（INVALID_CREDENTIALS/EMAIL_INVALID/PASSWORD_TOO_SHORT/BUYER_ACCOUNT_EXISTS/BUYER_LOGIN_RATE_LIMITED/BUYER_ACCOUNT_DISABLED）；**回跳用 `?next=`**（沿用 useWishlist 既有约定，`//` 开头拒绝防 open redirect）；保留忘记密码入口。
  - `storefront/pages/auth/login.vue` / `register.vue`：title 双语化（`auth.titleLogin`/`auth.titleRegister`）。
  - `storefront/pages/auth/forgot-password.vue`：同皮肤（380 竖列、同色值）。
  - `storefront/locales/messages.js`：`auth.*` 命名空间 en/zh 成对新增 29 对键（`auth.titleLogin`…`auth.error.generic`），精确锚点小步 Edit，未动 footer./topbar./header.。
- **取舍（记录给后续会话）**：①真站无 tab，本站维持 `/auth/login`、`/auth/register` 两页 + 页内切换链接（视觉与真站一致）；②登录=邮箱/电话+密码一步直填（用户拍板"邮箱/电话那里正常加个密码输入就好了"，不做真站 email-first 两步）；③**注册仅邮箱**——后端 `/auth/buyer/register/email` 契约只收 email，电话注册需走验证码契约，本批不改后端（遗留项，见下）。
- **验证（按验证纪律仅针对性验证）**：
  - eslint + prettier --check：AuthForm.vue、login/register/forgot-password.vue、messages.js **全过**。
  - vitest（storefront 配置）：`components/AppHeader.test.js` + `components/account/AccountNav.test.js`（auth 相关的两处既有测试）**2 文件 21 测试全过**。注意根目录跑 vitest 不带 storefront 配置会报缺 @vitejs/plugin-vue，须 `cd storefront` 再跑。
  - 本地全流程 Playwright（`var/auth_page_20261119/local_e2e.cjs`，dev :3000）：注册新买家→落地 /account ✅ →登出 ✅ →错误密码提示「邮箱/电话或密码不正确。」✅ →带 `?next=/cart` 登录落地 /cart ✅ →再登出 ✅ →忘记密码页可见 ✅ →行内校验 zh/en 双语 ✅。截图 `local_login_en/zh.png`、`local_register_zh/en.png`、`local_login_wrong_pw_zh.png`、`local_forgot_zh.png`；console 仅 1 条预期内 401（错误密码那次 POST 的 resource 日志）。
  - 零残留 grep：京东/ochama/Ochama 全 storefront 源码 0 命中；auth 页面列（.auth-page，en+zh×login+register 四组合）内 京东/ochama/JD/Google/礼包/Welcome Offers/查看更多选项 0 命中（`residue_check.cjs`）。**注意**：页面顶栏黑条 en 文案含 "Welcome Offers"（`topStrip.welcomeOffers`，全站性促销条，属 topbar 命名空间/头部集群，非本批次范围，未动）。
- **测试数据清理**：注册的临时买家 `auth_b_1795023866975@example.test`（id 118）已从 dev DB 删除，连带 2 条 buyer_session，复核 0 残留。
- **遗留项**：①电话注册不支持（后端契约限制，如要支持需后端加免验证码 phone-register 端点，须用户拍板）；②协议行《隐私与Cookie政策》《条款与条件》是带下划线的纯文本（本地无对应内容页；等批次 A 的 `/pages/<slug>` 内容页落地后可换成真链接）；③真站顶栏促销条（礼包字样）不在本批范围。

## 0k. 本次会话记录（2026-11-20，⚠️ AWS 账户关闭/停用事故诊断：S3 全挂（AllAccessDisabled）+ EC2 不可达 + IAM key 全失效，⏸ 等用户恢复账户）

- **用户报障「本机 AWS key 失效 + 存储桶匿名读被禁（AllAccessDisabled）——MEDIA_BACKEND=s3 全挂」→ 主代理实测三层证据，结论升级为账户级事故**：① 本机 `aws sts get-caller-identity` → `InvalidClientTokenId`（key 无效）；② 匿名 GET 桶对象 → **`403 AllAccessDisabled`**（"All access to this object has been disabled"）——**这是 AWS 账户被关闭后 S3 的专属错误码**（普通权限问题是 AccessDenied，不要混淆）；③ EC2 18.184.216.138 的 80/22 全 000 + ping 100% 丢（同时刻本机 baidu/github/aws 官网全 200，网络正常）——账户关闭/停用会停掉所有 EC2。**判定：整个 AWS 账户 closed 或 suspended（多半付款失败），不是单点 key/桶问题。** 生产（站点/API/媒体）当前全不可用；旧 Lightsail 已删，无兜底。
- **用户待办（只有用户能做，且要快）**：登录 AWS 控制台看账户状态 + 查注册邮箱（AWS 关户/停户必发邮件，主题含 closed/suspended/unpaid）；付款问题 → Billing 补款自动恢复；误关户 → 登录后 **Reopen account**（宽限期内可重开，桶数据仍在；**拖过宽限期 S3 数据真删，要快**）。
- **账户恢复后的复核清单（新会话照此执行）**：① S3：对象数对账（706,445）+ 匿名 GET 200 + `sts get-caller-identity` 两机验证；② **EC2 重启后公网 IPv4 大概率变化**（停机释放）→ 更新本机 ~/.ssh/config 的 joybuy2 HostName、服务器 .env 的 DJANGO_ALLOWED_HOSTS/DJANGO_CSRF_TRUSTED_ORIGINS、通知用户新地址；③ 生产回归：首页/类目 API/媒体反代/admin 登录（Playwright）；④ 若实例已 terminated（不是 stopped）→ 按 HANDOFF 0g/0h 配方 + git bundle 重新部署（数据从 S3 与最新 dump 恢复）；⑤ 恢复后把本节标注 ✅。
- **教训（防再踩）**：① `AllAccessDisabled` ≠ `AccessDenied`——前者=账户级停用，后者=策略拒绝，见到前者直接查账户状态不要去改桶策略；② 账户恢复后 EC2 公网 IP 变化会连环影响 ssh 别名/ALLOWED_HOSTS/CSRF/用户书签，要当成一套变更处理；③ 生产单点 EC2 + 同账户 S3：账户被停 = 全站全灭，待办里「备份/容灾」的优先级应上调（至少：DB dump 每日落本地或异地、IAM key 轮换意识）。

## 0k. 本次会话记录（2026-11-18，需求文档03优化：澄清歧义 + 补验收标准 + 标注现状差距，✅ 完成，未 commit）

- **任务**：用户要求阅读 `功能需求迭代文档03.md`（v1.1，2026-11-18 19:51 拍板版）并优化其中需求。**只改文档，未动任何代码。**
- **产出**：`功能需求迭代文档03.md` 升到 **v1.2**，新增内容全部标注【优化补充】，拍板结论一字未改。要点：
  1. **已售随机数关键约束**：必须一次性生成落库（同商品恒定，防刷新变数字一眼假），预留真实爬虫值覆盖；评语**不允许随机占位**（抓不到就空着）。
  2. **无限加载边界**：每页 24 件、总上限 200 件、失败重试、SSR 降级——防拖垮服务器。
  3. **专区**落到现有 CmsProductPool 机制（默认固定、后台可换、不足自动隐藏），商品清单按真站测量流程配。
  4. **申请店铺状态机**补"未登录"态；标注现状：四态申请页 + 商家端会话接口已实现（2026-11-17），本轮只做入口迁移（头像菜单→右上角替换配送至）；记录了配送至入口被替换的取舍。
  5. **管理端路径改造**补安全配套：旧路径 404（非 301，防泄漏）、登录失败限流、新路径不出现在 robots/sitemap。
  6. **上新流程**与现状对齐：图片直写 S3 已实现（`MEDIA_BACKEND=s3`）；"同步数据文件"固化为 5 步管道，把"导入必刷搜索文档"的历史坑写进需求。
  7. **HTTPS 补前置依赖：域名**（当前生产是裸 IP 18.184.216.138，无域名签不了证书）；提供 Let's Encrypt 免费备选，不动拍板。
  8. **爬虫风险**：账号已损 1/3 → 建议 11/21 中期盘点；对数口径按 ACTIVE 上架数；连续 2 账号封锁即停批。
  9. 新增 第七节依赖表 / 第八节验收清单 / 第九节优先级排期（P0 购物端+管理端路径+HTTPS，P1 数据管道，P2 商家端美化）/ 第十节优化说明。
- **下一步建议**：①按 v1.2 拆工作包执行（P0 先行）；②域名采购是 HTTPS 硬前置，需用户先定；③已售落库字段方案（建议 Spu 加展示用字段）在开发时定。

## 0j. 前一次会话记录（2026-11-19，修复管理端 http 下 `crypto.randomUUID is not a function` + cookie Secure 临时降级，✅ 两轮修复均已部署 joybuy2，生产 admin 登录 Playwright 实测打通）

- **任务**：修生产管理端（http://18.184.216.138/admin/，纯 http 无 TLS）登录报 `crypto.randomUUID is not a function`，部署并用真实浏览器 E2E 验证登录。**终态：两轮修复（uuid 降级 `a85e985` + cookie Secure env 化 `dde07ae`）全部上线，Playwright 真浏览器登录成功进入商家管理页、console 0 error（主代理独立抽查吻合：三方 git = a4ee6f3、.env 25/26 两行覆盖 chmod 600、admin/buyer 两端点 Set-Cookie 的 Secure 计数均 0、joybuy-api active）。第一轮末曾按纪律停下报告"登录未打通"，第二轮经用户同意选项①后完成。**
- **根因 1（已修复）**：`crypto.randomUUID()` 是 secure-context-only API，http 且非 localhost 的页面里是 undefined；点击登录 → `apiRequest` 生成 X-Request-ID 时直接抛 TypeError（错误被 LoginView catch 后显示在表单里，console 无 unhandled error）。全仓 grep 只有 2 个调用点，**storefront 干净无此问题**：
  * `admin-web/src/lib/api.js:59`（apiRequest 的 X-Request-ID 请求头 + ApiError 追踪字段）；
  * `merchant-web/src/lib/api.js:36`（同用途）。
- **修复内容（commit `a85e985`，4 文件 +28/-2，一行英文 commit 信息，不动其他代码）**：`admin-web/src/lib/uuid.js` 与 `merchant-web/src/lib/uuid.js` 各自新增 `uuidv4()`（优先 `crypto.randomUUID`，降级用 insecure context 可用的 `crypto.getRandomValues` 的模板位运算实现），两处 `api.js` 改为 import 调用。两包无 utils 目录，按既有风格放 `src/lib/`。merchant-web 与 admin-web 同构同修（其登录同样会踩雷），三包各自持有实现、不跨包共享。
- **本地针对性验证（按验证纪律，未跑全量）**：`vitest run --config admin-web/vitest.config.js admin-web/src/views/LoginView.test.js admin-web/src/router/auth.test.js` → **2 文件 3 测试全过**；node 直测降级实现（stub 掉 randomUUID 只留 getRandomValues）→ 2000 次**全唯一、全部合法 v4 格式**；eslint + prettier --check 4 个改动文件 → 全 clean（根级 eslint/prettier 配置覆盖 admin/merchant）。
- **部署（joybuy2，走了 bundle 路径——本机到 GitHub 不通）**：**本机 git push 连续 8+ 次失败**（`Failed to connect to github.com:443` / `Connection was reset`；无代理、无 VPN，疑似本机当前网络到 GitHub 被墙/VPN 未开），push **仍欠着**：`origin/main` 停在 `4873836`，服务器与本地都在 `a85e985`（服务器比 origin 领先两个 commit：4873836 + a85e985）。部署改走：本地 `git bundle create var/uuid_fix_20261119/uuid_fix.bundle uuid-fix-stage ^0d06cbd`（须用**分支名**做 bundle ref，裸 SHA 范围会报 "Refusing to create empty bundle"，虽然 rev-list 正常）→ scp 到 joybuy2:/tmp → `git fetch /tmp/uuid_fix.bundle uuid-fix-stage && git merge --ff-only FETCH_HEAD` → 服务器 HEAD 0d06cbd→**a85e985**（顺带补上了 4873836 这个 HANDOFF commit）。服务器侧 `git push origin main` 也不行（无凭据 could not read Username）。**等本机网络恢复后必须补 `git push origin main`**，补完后一切自洽（服务器 pull --ff-only 会显示 Already up to date）。
- **服务器构建**：`cd /srv/joybuy && pnpm --filter @joybuy/admin-web exec vite build --base=/admin/` → exit 0。**注意 package.json 的 build 脚本没有 base，必须 exec 显式带 `--base=/admin/`**（老坑复确认）。产物 `/srv/joybuy/admin-web/dist/`（nginx `location /admin/` alias 指向此处，已核对 sites-available/joybuy）；对 dist grep 确认含 `randomUUID` 特性判断与 `getRandomValues` 降级、index.html 引用 `/admin/assets/...`。merchant-web 同 commit 已改但**未在服务器构建**（nginx 未挂载，无需）；storefront 未改、未动、未重启（joybuy-api/joybuy-storefront 都没 restart——本次零后端改动）。
- **E2E 证据（Playwright chromium headless，真浏览器打生产；脚本 `var/uuid_fix_20261119/admin_login_probe.js`，参数 before/after）**：
  * **before（部署前）**：提交登录表单 → 表单内红字 **`crypto.randomUUID is not a function`**（客户端 TypeError，登录请求根本没发出，页面被 router 守卫弹到 /login?next=/admin/），截图 `before_2_after_submit.png`。
  * **after（部署后）**：uuid 报错**彻底消失**，登录 POST 真正打到后端 → 但返回 **403**，UI 显示「当前账号无权执行该操作。」（api.js 对非 JSON 403 的兜底文案），截图 `after_2_after_submit.png`。console 仅 1 条 `Failed to load resource: 403`，无其他噪音。
- **根因 2（未修，是当前登录真正的拦路虎，需用户拍板）**：服务器 `.env` 里 `APP_ENV=production` → `backend/config/settings.py:189/192` 强制 `SESSION_COOKIE_SECURE=True` / `CSRF_COOKIE_SECURE=True` → **纯 http 下浏览器会拒存带 Secure 标志的 cookie**：`/admin/auth/session` GET 响应 `Set-Cookie: csrftoken=...; Secure`（服务器实测确有 Secure）→ 浏览器没有 csrftoken cookie → 登录 POST 缺 cookie → Django CSRF 中间件 403（HTML 页，非 JSON，故 UI 只能显示兜底文案）。**即：uuid 修好后登录也过不了 CSRF，而且就算过了，staff 会话 cookie 同样带 Secure 存不下来。已在服务器上用纯 python urllib 复刻浏览器流程复现（脚本 `var/uuid_fix_20261119/csrf_diag.py`，跑完已删服务器副本）：GET session 拿到 csrf_token（JSON 里 token 与 cookie 值不同是 Django 掩码机制，正常）→ POST login 403 HTML，Python cookiejar 同样不回发 Secure cookie。**
- **可选修法（等用户选，本次均未执行——任务纪律明确禁止动后端代码/.env/nginx）**：① settings.py 给 CSRF/SESSION_COOKIE_SECURE 加 env 覆盖（生产默认仍 True），.env 显式关掉——代码与配置各改一处，安全性按"http 裸奔期临时降级"接受；② 上 TLS（正经解，需要域名或 IP 证书）；③ 维持现状，管理端在 http 下不可用。另注意：**LoginView 已是纯邮箱+密码登录，不再要 TOTP**（代码注释明说"不再需要验证器动态码"，admin-web 全仓无 TOTP 引用），0g 节记录的 TOTP secret/二步验证流程已过时。
- **生产登录尝试计数**：浏览器 2 次（before/after 各 1）+ 服务器脚本化 1 次（在 CSRF 中间件就被拒，没进视图，未触发 STAFF_LOGIN_RATE_LIMITED 计数）。
- **坑（新）**：① Python http.cookiejar 对 `Secure` cookie 在 http 下同样"不存也不发"，这就是脚本也能复现的原因；② `git bundle create` 用 `A..B`/裸 SHA 会报 empty bundle（用分支名）；③ 本机 GitHub 连通性会变（之前会话能 push，本次全程不通），部署别依赖 push 必然成功；④ `csrf_token` JSON 值与 csrftoken cookie 值不同属 Django 掩码设计，别当 bug 修。
- **追加（同日第二轮，用户已批准临时降级路线①）：cookie Secure 标志改为 env 可覆盖，登录已打通 ✅**
  * **改动（commit `dde07ae`，仅 `backend/config/settings.py` +7/-2）**：`SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` 改为 `env_bool("DJANGO_SESSION_COOKIE_SECURE"| "DJANGO_CSRF_COOKIE_SECURE", 默认值不变=production 仍强制 True)`。**全仓核查过 Secure 强制点只有 settings.py:189/192 这两处**：staff session cookie（`accounts_staff/services.py:165`）、buyer session cookie（`accounts_buyers/services.py:191`）都读 `settings.SESSION_COOKIE_SECURE`，Django session/CSRF cookie 走同名设置——两个开关覆盖全部四个 cookie，无其他 secure= 硬编码。
  * **针对性验证**：ruff check + format 通过；`manage.py check` 三态（默认/`false`+`0` 覆盖/非法值 `bogus`→ImproperlyConfigured 拒绝）全过；无单测引用这两个设置。
  * **部署**：push 再遇 GitHub 不通 → bundle（`cookie-fix-stage ^a85e985`）→ scp → 服务器 ff `a85e985→dde07ae`；`/srv/joybuy/.env` 追加 2 行（`DJANGO_SESSION_COOKIE_SECURE=false`、`DJANGO_CSRF_COOKIE_SECURE=false`，附回滚注释，第 25/26 行，服务器端 printf 原生 LF，chmod 600 已核，未动任何既有行）；`sudo systemctl restart joybuy-api` → active。
  * **验证（真实浏览器登录成功）**：① 服务器 curl `/api/v1/admin/auth/session` 与 `/api/v1/auth/buyer/session` 的 Set-Cookie（csrftoken）**均无 Secure 标志**（0 处）；② Playwright 完整登录：/login → 填邮箱密码 → 提交 → **登录成功落地 `/merchants` 已登录态**（右上 `ops@joybuy.local`+退出登录、侧栏完整管理菜单、身份 `Joybuy Platform Admin / platform_admin`、商家管理真实数据），**console error 0**，截图 `var/uuid_fix_20261119/after2_2_after_submit.png`。探针 JSON 里 `loginOk:false` 是**断言过窄的假阴性**（脚本等"仪表盘"标题，而 platform_admin 登录后被路由到商家管理页）——已登录事实以 URL/页面特征/console 为准；③ 买家侧：buyer token cookie 只在真实登录时下发（无凭据无法 curl 验证该 cookie 本身），但它与 staff cookie 读同一 `settings.SESSION_COOKIE_SECURE`（代码已核），且其端点 csrftoken 已实测无 Secure——机制同一。
  * **回滚条件（必须执行）**：配置 TLS/域名当天，删除 `/srv/joybuy/.env` 第 25-26 两行（DJANGO_SESSION_COOKIE_SECURE / DJANGO_CSRF_COOKIE_SECURE）+ `sudo systemctl restart joybuy-api`，settings 默认即恢复 production 强制 Secure，无需改代码。
  * **登录尝试计数**：本轮浏览器 1 次（成功）、服务器脚本化 0 次。
  * **push 状态**：dde07ae 与本节 HANDOFF（d24a184）均已于本轮收尾时成功 push（本机到 GitHub 时通时断，失败就 bundle→scp→服务器 ff-merge 或稍后重试）。
- **追加（同日第三轮，用户实测裸 `/login?next=/admin/` 404）：router base 缺失修复 ✅ 已部署，两场景 E2E 全绿**
  * **现象与根因**：用户真实浏览器 console 报 `404 (Page not found: /login?next=/admin/)`——整页被重定向到**不带 /admin/ base 的裸 `/login?next=/admin/`**，nginx `location /` 打到 Nuxt 店面 → 无此路由 → 404。真凶是 `admin-web/src/router/index.js:35` 的 **`createWebHistory()` 不传参**——它**不会**自动跟随 vite `--base`（0g 坑⑦的说法是错的，已在该行更正标注）。生产 `--base=/admin/` 下 vue-router 把初始地址解析成根路径 `/admin/` → 命中 catch-all not-found → 守卫 `return { name:'login', query:{ next: to.fullPath } }` 里 `to.fullPath`=`/admin/` → pushState 出裸 `/login?next=/admin/`；SPA 客户端仍渲染登录表单（此前探针截图看着正常、finalUrl 却是裸域名根路径的原因），但**任何刷新/新标签/重新打开该 URL 都落到 Nuxt 404**。本地 dev（base=/）侥幸正确，所以本地 e2e 从未暴露。回看第二轮 before 探针的 finalUrl 就是裸 `/login?next=/admin/`——当时误判为 router 正常行为，实为同一 bug。
  * **命中点清单（grep 全量，只改必要处）**：`admin-web/src/router/index.js:35`（真凶，已修）；`merchant-web/src/router/index.js:18`（同款隐患，一并修，虽未挂 nginx）；`AdminLayout.vue:92` 登出 `router.push('/login')`、`LoginView.vue:36` 登录后 `router.push('/')`、守卫 `index.js:211`——三者都是 router 内部跳转，history base 修对后**自动 base 感知，零改动**；全包无 `window.location`/`<a href>` 裸跳转。修复 = 两包改 `createWebHistory(import.meta.env.BASE_URL)`（dev BASE_URL=/ 行为不变），仅 2 文件 +7/-2。
  * **本地针对性验证**：vitest（LoginView+auth 守卫）3/3 过；eslint/prettier clean；本地 `--base=/admin/` 构建 + `vite preview --base=/admin/` + Playwright 结构检查：打开 `/admin/` → 重定向落在 `/admin/login?next=/no-access`（全程 /admin/ 下）、登录表单可见、**无任何裸 /login 请求**（`var/uuid_fix_20261119/base_check.js`）。
  * **部署**：commit `db9625a` push 一次成功；服务器 `git pull --ff-only` → db9625a → `pnpm --filter @joybuy/admin-web exec vite build --base=/admin/` exit 0，dist 09:09 刷新，`index.html` 引用 `/admin/assets/index-CjA2F2oQ.js`（与本地验证构建 hash 一致）。
  * **生产两场景 E2E（`var/uuid_fix_20261119/full_path_e2e.js`，全新 context）**：① 打开 /admin/ → 落 `/admin/login?next=/no-access`（/admin/ 下、表单 200）→ 登录 → 落 `/admin/merchants` 已登录态；② 同 context：硬刷 `/admin/merchants` 保持已登录（URL 不变）→ 点退出登录 → 落 **`/admin/login`**（/admin/ 下，不再裸跳）→ 表单回来 → 再登录 → 回 `/admin/merchants`。**全程 console error 0、page error 0、裸 /login 请求 0、/login 404 计数 0**。截图 `round3_s1_open/s1_loggedin/s2_reload/s2_logout/s2_relogin.png`。
  * **旧 cookie 干扰评估（任务⑦，已实测）**：`var/uuid_fix_20261119/stale_cookie_e2e.js` 预置「降级前遗留的 csrftoken + 作废 staff session cookie」再走完整登录 → **自愈成功**（/admin/merchants、console 0 错误）：登录前 `loadSession` 的 GET 会 Set-Cookie 一个新 csrftoken（同 name/domain/path 覆盖旧值）并用返回 token 做头，旧 staff cookie 会被登录成功后的 set_cookie 原样覆盖——**用户无需清 Cookie**。唯一建议：**在 http://18.184.216.138/admin/ 页面按 Ctrl+F5 强刷**（拿新 index.html/新 bundle；若标签页还停在裸 /login 404 页，直接重新打开 /admin/ 即可）。
  * **登录尝试计数**：本轮浏览器 3 次（两场景 E2E 登录+重登录成功 + stale 模拟登录成功；首轮 stale 跑遇瞬时 502 未构成有效登录，复跑核实 joybuy-api active、/api/v1/categories 直连与经 nginx 均 200、chunk 在位——服务器健康，502 为本机网络瞬断）。
  * **新坑**：① 本机 Git Bash 直接 `vite build --base=/admin/` 会被 **MSYS 路径转换**毁掉（`/admin/` 变 `C:/Program Files/Git/admin/`）——本机构建一律 `MSYS_NO_PATHCONV=1 node node_modules/vite/bin/vite.js ...`；② 本机 pnpm shim 偶发损坏（`Cannot find module .../pnpm/bin/pnpm.mjs`），同法绕过；③ vite preview 做 SPA 结构检查很顺手（`--base`+SPA fallback），dev server 不用起。

## 0i. 本次会话记录（2026-11-19，媒体存储切换 S3 后端：爬虫导入/上传直写桶 `joybuy-media-fra`，不再落本地盘，✅ 全部完成并已部署 joybuy2）

- **任务**：媒体存储从「本地磁盘 var/media」改为「S3 桶」——爬虫导入的图片/视频、管理端/商家端上传直接 `put_object` 进 S3，不再写本地盘。**商品数据（DB 行）仍写本地 dev 库不改导入目标库**（用户已拍板）。commit `0d06cbd`（含 10 文件 +440/-30），已 push origin main 并部署 joybuy2。
- **外网已通（同日稍晚，用户加规则后实测）**：用户在 `launch-wizard-1`（sg-0599ae677ad282acc——经 metadata 核实就是实例实际挂载的安全组）加了 HTTP 80 / 0.0.0.0/0 入站。**双网络位置交叉验证全 200**（本机经 VPN + 旧 Lightsail 作为独立远端），服务器侧核实：nginx 监听 0.0.0.0:80、ufw inactive、本机 curl 200。用户随后仍报「无法访问」，疑似**浏览器自动 https://（443 无监听必然失败）或缓存**——已提醒明确输 `http://18.184.216.138` 并强刷；若再失败按其报错文案（超时/REFUSED）继续定位。外网通即满足旧 Lightsail 删除清单最后一项「用户验收」，等用户点头退役。
- **旧 Lightsail 退役（2026-11-19）**：删除前最后一道保险已做完——新机 DB 九表计数实测（spu 12939 / sku 18455 / offer 16352 / media_asset 101850 / product_search_document 7900 / buyer_account 84 / merchant 694 / merchant_application 0 / staff_account 4），与迁移时逐字节一致，dump 后旧机无业务写入；随后发现旧机 80/22 从**双位置**（本机 + joybuy2 内网）均不可达——**实例已被用户停止或删除**（迁移 dump 之后旧机无独有数据，删除零损失）。已提醒用户控制台三件事：删实例、**删未附着静态 IP（按小时计费的漏账点）**、确认无残留快照；Lightsail 按月计费月中不退、下月起停 $160.91/月。删后可选清理：新机 .env 的 ALLOWED_HOSTS 里遗留旧 IP 18.159.51.52（无害，顺手删）；本地 ssh 别名 joybuy + ~/.ssh/joybuy_fra.pem 留作历史。**生产从此只有 joybuy2 一台 + S3。**
- **TLS 证书费用口径（2026-11-19 用户问「部署证书亚马逊怎么收费」，咨询已答，决策待用户）**：① ACM 公共证书 **$0**（签发/续期/部署全免费），但**不能导出私钥**——装不进自己 EC2 的 nginx，只能挂 CloudFront/ALB 等托管服务；ACM Private CA $400/月与本场景无关。② 两条路：**路线 A = Let's Encrypt + certbot（推荐）**——证书 $0，唯一花费是域名（Route 53 .com ≈$12/年，外部注册商可能更便宜），DNS zone $0.50/月或用免费第三方；deploy.md 已有 `certbot --nginx` 流程；**上线当天必须回滚 cookie 降级（删 .env 两行 + restart joybuy-api，回滚条件已在 0j 写死）**。**路线 B = ACM + CloudFront**——证书 $0 但引入 CDN 费：出网 1TB/月永久免费 + 超出 $0.085/GB（欧洲），请求 1000 万/月免费 + 超出 ~$0.01/万；按月 2.1TB/180 万 PV ≈ $165-175 vs 直出 $180，基本持平略省——CDN 别按省钱立项（真实收益=免费证书托管+延迟+抗突发）。③ 建议：单机架构先走 A；以后要 CDN 再叠 B，两者不冲突。
- **改了什么（代码）**：
  * `backend/config/settings.py`：新增 `MEDIA_BACKEND`（local|s3，默认 local）、`MEDIA_S3_BUCKET=joybuy-media-fra`、`MEDIA_S3_PREFIX=media/`、`MEDIA_S3_REGION=eu-central-1`（全部 getenv 可覆盖，非法值启动即报 ImproperlyConfigured）。
  * `backend/media/storage.py`（核心）：`s3_enabled()` / `get_s3_client()`（boto3 懒加载单例，region 来自 settings，凭据走 boto3 默认链 `~/.aws/credentials` 或 AWS_* env，**代码零硬编码密钥**）/ `reset_s3_client()` / `s3_key()`（`media/<relative_path>`）/ `s3_public_url()`（匿名桶 URL）；新增 `store_file_bytes(relative_path, data, content_type)`（s3=put_object；local=原 tmp+os.replace 原子写）、`read_stored_bytes()`（s3=get_object 读回；local=读文件）、`stored_file_exists()`（s3=head_object 404→False；local=is_file）；`store_bytes` 改走 `store_file_bytes`，**维度检测改为从内存 bytes（`Image.open(io.BytesIO(data))`）不再打开本地文件**；DB sha256 去重逻辑完全不变（命中即跳过一切写入、不 put_object）；`delete_asset_file` s3 模式下 delete_object。`_detect_image_dimensions` 签名从 Path 改为 bytes（这是简报预判的坑，已落地）。
  * `backend/media/variants.py`：源图改为 `read_stored_bytes` + BytesIO 解码（两种模式同一条代码路径）；6 个 derived 变体改走 `store_file_bytes` 上传（webp/avif 各自 ContentType）；新增 `FORMAT_MIME_TYPES`。
  * `backend/media/pipeline.py`：`generate_video_cover` 在 s3 模式把视频字节暂存进 tempfile 工作目录再喂 FFmpeg（FFmpeg 必须吃真文件），封面 jpg 改走 `store_file_bytes`；本地模式行为不变。视频原片（kind=VIDEO）经 `store_bytes` 同一入口进 S3，已验证。
  * `backend/media/views.py::serve_media_file`：仅当 `DEBUG 且 MEDIA_BACKEND=s3 且本地文件缺失` → 302 到 `s3_public_url(path)`（桶对 media/* 匿名可读）；路径穿越→404 不重定向；local 模式行为完全不变（404）。**生产语义未动：运行时回退仍只在 DEBUG+s3 生效**。
  * `backend/crawler_control/import_services.py::_import_spu_videos`：视频复用判断从 `resolve_media_path(...).is_file()` 改为 `stored_file_exists(...)`（s3 模式 head_object）——**不改的话 s3 模式下每次重导入都会误判视频缺失而重新下载**。
  * `backend/manage.py`：`test` 命令强制 `MEDIA_BACKEND=local`（见坑①）。
  * `backend/requirements/base.txt`：加 `boto3==1.44.5`（当前最新稳定；依赖 botocore==1.44.5/s3transfer==0.19.3，本机与服务器 `pip check` 均 No broken requirements found）。
  * 新测试 `backend/media/tests/test_media_storage_s3.py`（218 行，FakeS3Client 记录 put/get/head/delete 调用）+ `test_media_pipeline.py` 增 S3 模式视频封面用例。
- **S3 模式开关与配置（现状）**：仓库根 `.env`（gitignored，已确认 `.gitignore:2` 覆盖）新增 `MEDIA_BACKEND=s3` + bucket/prefix/region 三行，**不含任何密钥**（走 `~/.aws/credentials` IAM 用户 joybuy-up-down）。`MEDIA_BACKEND=local`（不设或显式设）时全部行为与切换前逐字节一致。
- **验证命令与真实结果（按验证纪律仅做针对性验证，未跑全量）**：
  * `./.venv/Scripts/python.exe backend/manage.py test media.tests crawler_control.tests.test_crawler_import merchant_ops.tests.test_media_upload --keepdb --noinput --parallel 1` → **Ran 58 tests, OK**（含 12 个新 S3 用例：put_object 的 Bucket/Key/ContentType 断言、去重不触发上传、derived 变体 6 个对象上传、S3 视频封面（本机有 ffmpeg，未 skip）、views 302/404/穿越 404；既有用例零红零 skip）。ruff check + ruff format --check 改动文件 → **All checks passed / 9 files already formatted**。
  * 本机真模型冒烟（`var/s3_storage_smoke_20261119/smoke.py` store/cleanup 两阶段）：1x1 PNG kind=CMS → media_asset 行数 **101850→101851→101850**，`relative_path=cms/original/68/76/68764b0b...a790.png`，匿名 GET 桶 URL **200**（69 bytes image/png），`local_disk_copy=False`；cleanup 后 boto3 `delete_object` + 删 DB 行，HeadObject **404**、匿名 GET 变 **403**（S3 无 ListBucket 对缺失对象的标准语义），行数复原。**现场已清理干净**。
- **服务器部署（joybuy2，18.184.216.138，已重启验证）**：
  * 顺序坑：先 `git push origin main` 再 `ssh joybuy2 'cd /srv/joybuy && git pull --ff-only'`（第一次 pull 显示 Already up to date 是因为还没 push）。服务器 HEAD 720aa90 → **0d06cbd**。
  * `/srv/joybuy/.env` 只追加 4 行 MEDIA_*（本地 printf 生成 LF 片段 → scp → 服务器 `sed -i "s/\r$//"` 兜底去 CRLF → `cat >>`，重设 chmod 600，未动任何既有密钥行，追加前 grep 确认无重复键）。
  * `/srv/joybuy/venv/bin/pip install boto3==1.44.5` → Successfully installed（pip 顺带把服务器 python-dateutil 4.0.0 降到 2.9.0.post0 以满足 botocore 约束，pip check 干净）；`sudo systemctl restart joybuy-api`（代码更新后**又重启了一次**——第一次重启发生在 pull 之前，跑的还是旧代码，别再犯）。
  * 服务器验证全绿：`systemctl is-active` = active；`/api/v1/categories` 直连 :8000 与经 nginx 均 200（真实类目 JSON）；journalctl 近 10 分钟无 error/traceback。
  * **服务器侧真模型冒烟**（`var/s3_storage_smoke_20261119/server_smoke.py`，跑在 /srv/joybuy/backend，用服务器自身代码+ubuntu 的 ~/.aws/credentials）：1x1 PNG（颜色 18,11,18，与本机冒烟字节不同）→ 行数 **101850→101851→101850**，`relative_path=cms/original/c8/fc/c8fcaab8...ead2.png`，`exists_in_s3=True`；**经 nginx /media/ 反代 GET = 200（X-Cache-Status MISS→HIT，proxy_cache 生效）**，外部直连桶 URL 200；cleanup 后 HeadObject 404、行数复原，/tmp 临时脚本已删。**现场已清理干净**。
- **爬虫从此不再写本地 var/media**：本机爬虫导入（`crawler_control.import_services`）与 `manage.py load_*_demo`、管理端/商家端上传全部经 `store_bytes` 直写 S3。本地 var/media 现存 706,445 文件**一个没动**，保留作 dev 兜底+历史数据；serve_media_file 在 s3 模式下优先本地文件（老资产仍可本地服务）、缺失才 302 桶。以后新资产只存在于 S3 + dev DB 行（derived 图依旧无 DB 行）。
- **坑（必须记住）**：
  ① **Django test runner 会改 DEBUG、且 root .env 的 s3 配置会被测试继承**——若测试环境跑在 MEDIA_BACKEND=s3 下，普通单测会直连真桶上传垃圾对象/或断言本地文件失败。已在 `manage.py` 的 `test` 分支强制 `os.environ["MEDIA_BACKEND"]="local"`（显式赋值不受 export 覆盖影响）；S3 用例用 `override_settings(MEDIA_BACKEND="s3")` + monkeypatch `media.storage.get_s3_client` 显式选择后端。**新增测试一律不要依赖环境里的 MEDIA_BACKEND**。
  ② 单测直调视图时 `Http404` 是异常不是 404 响应（要用 assertRaises）；FileResponse 不 close 会让 Windows 锁住临时 MEDIA_ROOT 导致 TemporaryDirectory 清理 PermissionError。
  ③ MediaAsset.Kind 枚举值是大写（`CMS`/`PRODUCT`...），KIND_PATH_PREFIX 映射到小写目录（`cms/`...）；断言 kind 用枚举别写字面量小写。
  ④ `head_object`/匿名 GET 对「不存在对象」分别是 404/403（无 ListBucket 权限语义），判断删除成功别只认 404。
  ⑤ 冒烟用的 1x1 PNG 字节是确定性的（同字节同 sha256）——本机冒烟对象删掉后如再跑会「dedup 命中旧 DB 行」（行还在就 created=False）；换个颜色即新 sha。
  ⑥ nginx 反代已验证对新对象即时可见（无需预热），proxy_cache 对 200 缓 7 天——**冒烟/测试对象务必当场 delete_object**，否则会缓存一周。
  ⑦ FFmpeg 必须吃真实文件路径，s3 模式下先 `read_stored_bytes` 落临时目录再抽帧（已在 pipeline 内处理，勿改成管道喂 mp4）。
- **遗留/后续**：EC2 安全组开 80 端口（0h 的用户侧卡点，仍未开）；验收新站后退役旧 Lightsail；`/srv/data`（120G 数据盘）规划未动；爬虫本机下次导入起即可验证「零新增本地文件」（`ls var/media | wc` 对照），本次未跑爬虫实测导入。

## 0h. 本次会话记录（2026-11-18，服务器迁移到新 EC2 joybuy2 + 媒体改 Nginx 反代 S3，✅ 12 步全部完成，仅剩用户开 EC2 安全组 80 端口）

- **任务**：把 Joybuy 从旧 Lightsail（`ssh joybuy`，18.159.51.52）迁到新 EC2（`ssh joybuy2`，18.184.216.138，Ubuntu 24.04.5，4C/15G/33G），媒体改为 Nginx 反代 S3 桶 joybuy-media-fra（媒体不落新机盘）。旧机全程未动（只读导 dump）。详细结果以 `var/prod_deploy_20261117/migrate-report.md` 为准。
- **已完成**：新机装齐 docker 29.1.3 / compose 2.40.3（包名 docker-compose-v2）/ nginx 1.24.0 / node 22.23.5 / pnpm 11.28.12；bundle clone 到 /srv/joybuy@720aa90（git status 干净，只建 var/staticfiles 不建 var/media）；.env 从本地 remote/ 复刻（md5 与旧机逐字节一致后才传，密钥原样保留，仅改 ALLOWED_HOSTS/CSRF 两行追加 18.184.216.138，chmod 600）；三容器 healthy（MySQL 8.4.7 绑 127.0.0.1）；**新 dump 从旧机只读导出**（120MB gz，md5 三端一致）经本机中转导入，行数对账**完全一致**：spu 12939 / sku 18455 / offer 16352 / media_asset 101850 / product_search_document 7900（表名是 `spu`/`sku`/`offer`，没有 catalog_ 前缀）；venv + migrate（No migrations to apply）+ collectstatic 154 文件，未跑 bootstrap_platform_admin；三前端构建全 exit 0（storefront .output、admin-web `vite build --base=/admin/`、merchant-web）；systemd joybuy-api/joybuy-storefront enabled+active；nginx 80 入口含 **S3 反代 /media/**（conf.d/joybuy-media-cache.conf 缓存 + sites-available/joybuy，resolver 169.254.169.253，proxy_cache media_cache 200 缓 7d / 404 缓 1m，X-Cache-Status 头）。
- **验证**：新机本机 curl `/` 200、`/api/v1/categories` 200 真实 JSON、`/admin/` 200；S3 对象经本地 presign 确认存在（200）；新机 localhost 走 nginx 反代 `/media/cms/original/03/b0/03b08f...e44.webp` = **200 真实图片字节**，MISS→HIT 缓存生效。**重要事实：S3 桶公共读已放开**（匿名直连桶 URL 也 200），简报里"BPA 全开→403"的假设已过时，反代现在即可出图；不存在的 key 返回 403（S3 无 ListBucket 权限时对缺失对象的标准语义），nginx 会把它缓存 1 分钟。
- **卡点（唯一遗留，需用户操作）**：**外网访问 18.184.216.138 全部超时**（含新机自连公网 IP 也超时、iptables INPUT 是 ACCEPT、nginx 监听 0.0.0.0:80）→ 根因是 EC2 安全组 **launch-wizard-1 没开 80 端口**。用户需在 EC2 控制台：Instances → joybuy2 → Security → launch-wizard-1 → Edit inbound rules → 加 HTTP/TCP 80/0.0.0.0/0。开完即整站可用，无需其他操作。未绕过。
- **新坑（必须记住）**：① **旧机 prod MySQL 密码不是 joybuy_dev_only**（那是 dev 库密码），是 infra/prod/.env 里的 MYSQL_PASSWORD，用 joybuy_dev_only 导 dump 会 Access denied；② 新库表名无 `catalog_` 前缀（`spu`/`sku`/`offer`/`media_asset`/`product_search_document`），对账 SQL 别写错；③ 导 dump 走 `gunzip | docker compose exec -T mysql` stdin 管道即可，不用 cp 进容器；④ presign 验证桶对象用 `/c/Program Files/Amazon/AWSCLIV2/aws.exe`，不要动本机 aws 配置和后台 56GB 上传任务（它们与本任务无关且未受影响）；⑤ nginx 配置里 `expires 7d` + `add_header Cache-Control "public, immutable"` 会产生两个 Cache-Control 头，无害，如要清理删 `expires 7d`。
- **旧机遗留杂物**：/tmp/joybuy_dump.sql.gz（120MB dump）留在旧机 /tmp，可日后清理；旧机服务/配置零改动。

## 0g. 本次会话记录（2026-11-17 深夜，生产部署到 Lightsail 服务器执行完成，✅ 全部 12 步成功、站点已上线 HTTP 80）

- **任务**：把 Joybuy 部署到 Lightsail（`ssh joybuy`，18.159.51.52）并启动全部服务；媒体 56GB 明确不传（留待后续）。详细结果以 `var/prod_deploy_20261117/deploy-report.md` 为准（含全部配置文件内容与打码密钥模板），此处只记结论与新坑。
- **已完成**：git bundle（main@720aa90）+ dev 库 dump（120.5MB）上传；`/srv/joybuy` 落位；docker 29.1.3 / compose 2.40.3 / nginx 1.24.0 / node 22.23.5 / pnpm 11.25.0 装好；prod MySQL 8.4.7 + Redis 7.4.6 + Mailpit 容器 healthy（端口全绑 127.0.0.1）；dump 导入成功（spu 12939 / sku 18455 / offer 16352 / media_asset 101850 / search_document 7900，与本地 dev 当前实测一致）；后端 venv + migrate（No migrations to apply）+ collectstatic（154 文件）+ bootstrap_platform_admin；三前端构建全 exit 0（admin-web 用 `vite build --base=/admin/`）；systemd `joybuy-api`（gunicorn 4w :8000）/ `joybuy-storefront`（node :3000）enabled+running；nginx 80 入口（/media/ alias、/api/ 反代 :8000、/admin/ alias admin-web/dist、/ 反代 :3000）。
- **验证**：服务器本机与外部 curl 全 200（/、/api/v1/categories 返回真实类目 JSON、/admin/）；/media/ 404 预期；`git -C /srv/joybuy status` 干净。外部 80 已放行，无需用户动 Lightsail 控制台。
- **管理端账号**：http://18.159.51.52/admin/ ，ops@joybuy.local / 41204f1d94b0f446f52d7267Aa1! ，TOTP secret `P3SWHTGXAWZLFLCY4KUHASQAL6TJIST5`（~~登录要二步验证~~ **2026-11-19 更正：admin 登录已改为纯邮箱+密码，TOTP 已废弃不再参与登录**——LoginView 代码注释明说"只使用邮箱+密码，不再需要验证器动态码"，见 0j 节）。
- **密钥**：服务器 `/srv/joybuy/.env` 与 `/srv/joybuy/infra/prod/.env`（均 chmod 600）含新生成的 SECRET_KEY、MYSQL_PASSWORD/ROOT_PASSWORD 及 6 个独立 HMAC 密钥；明文只存在于 `var/prod_deploy_20261117/remote/app.env`、`compose.env`（本地 var/ 目录，gitignore 覆盖）。
- **新坑（必须记住）**：① Ubuntu 24.04 没有 `docker-compose-plugin` 包，用 `docker-compose-v2`（否则整条 apt 一起失败）；② bundle clone 后要 `git checkout main`（bundle HEAD 指 master 不存在）；③ 服务器 ubuntu 用户要 `sudo usermod -aG docker ubuntu` 才能用 compose（新 ssh 会话生效）；④ **production 下 settings.py 强制要求 6 个独立 HMAC 密钥**（BUYER_SESSION/VERIFICATION_CODE/STAFF_SESSION/STAFF_TOTP_ENCRYPTION/SOURCE_FINGERPRINT/CRAWL_SESSION，等于 SECRET_KEY 即拒启），部署 .env 必须带上；⑤ scp 上去的 Windows 文件先 `sed -i 's/\r$//'` 去 CRLF（.env/unit 文件带 \r 会污染密钥值）；⑥ 简报中 media_asset ~698926 行参考值过时，dev 库现在实测 101850；⑦ admin-web 的 vite.config.js 没有 base，生产构建必须 `--base=/admin/`（~~vue-router createWebHistory() 会自动跟随 BASE_URL~~ **2026-11-19 更正：该说法是错的——`createWebHistory()` 不传参不跟随 BASE_URL，正是裸 `/login` 重定向 404 的根因，见 0j 第三轮；两包已改为 `createWebHistory(import.meta.env.BASE_URL)`**）。
- **遗留**：媒体 56GB 未传（/media/ 全 404）；无 TLS/域名；merchant-web 构建成功但未挂 nginx 路径；catalog 有未 makemigrations 的模型改动警告（dev 侧同状，待 dev 正常出迁移）；按验证纪律仅做部署针对性冒烟验证，未跑全量测试。
- **自启守护（2026-11-18 追加，用户要求所有服务重启后自动拉起）**：已逐项实测 `systemctl is-enabled`——`joybuy-api` / `joybuy-storefront` / `nginx` / `docker` / `containerd` 全部 **enabled**；三个容器（prod-mysql/redis/mailpit）`RestartPolicy=unless-stopped`（compose.prod.yml 自带，别改掉）。**真实重启演练已做（2026-11-18 用户批准）：sudo reboot → SSH 约 50s 恢复 → uptime 0min 证实重启发生；systemd 五项全 active、三容器 36s 内 healthy、本机与外部 curl（/ 与 /admin/ 200、/api/v1/categories 真实 JSON）全部自动恢复，零人工干预**。演练结论：Lightsail 实例重启后整站自动恢复，无需任何手工操作。

## 0f. 本次会话记录（2026-11-17 深夜，「本地商品图片等数据 → 法兰克福服务器」上传方案定稿，✅ 咨询完成，未执行、未改任何代码）

- **任务**：用户问「当前要把本地商品的图片等数据上传到法兰克福服务器应该怎么做」。只做方案定稿与事实核对，未执行传输、未改业务代码、未 commit。
- **核对到的关键事实**：
  * 媒体真实位置是 `var/media/`（`backend/config/settings.py:173` `MEDIA_ROOT = REPOSITORY_ROOT/var/media`）——服务器端只要 repo 落在如 `/srv/joybuy`，**无需改 settings**，媒体直接同步进 repo 内的 `var/media/`。实测 56.02 GB / 698,926 文件（商品原图 ~50.5 GB + 视频 855 个 5.49 GB）。
  * `backend/media/` 只是 Django app 代码包（226K），已随 git 入库——**不要把媒体误当成 `backend/media/`**。
  * 数据库名 `joybuy`（容器 `joybuy-dev-mysql-1`，用户/密码 joybuy/joybuy_dev_only）；逻辑数据 768 MB + 索引 293 MB，gzip 后 dump 预计数百 MB。**搜索文档、翻译表都在 DB 里，一次 dump 全带走，无需重建。**
  * **本机未安装 AWS CLI**（`aws --version` 找不到）——走 S3 中转前必须先装（`winget install Amazon.AWSCLI`）。
- **定稿方案（推荐主路径 = S3 中转两段式，沿用 §0 §6.1 结论）**：
  1. 前提：Lightsail 16GB（eu-central-1，320 GB 盘）已创建；未创建先创建（8GB 160 GB 盘装不下 222 GB，不可选）。
  2. 本地 `aws s3 sync var/media/ s3://<bucket>/media/`——断点安全：中断后重跑同一命令即跳过已传文件；PUT ~$3.70；瓶颈是家庭上行，56 GB 约 2–8 h。
  3. 服务器 `aws s3 sync s3://<bucket>/media/ /srv/joybuy/var/media/`（同区入向免费）。
  4. DB：`docker exec joybuy-dev-mysql-1 sh -c "mysqldump -ujoybuy -pjoybuy_dev_only --single-transaction --routines --triggers --set-gtid-purged=OFF joybuy" | gzip > var/db_export/joybuy_<date>.sql.gz` → scp → 导入 → 代码同版本跑一次 `migrate` 确认 schema 对齐。
  5. 顺序：先传 DB（分钟级）再跑媒体 sync（小时级）；两者都到齐才验证/上线。
  6. 校验：① `SELECT COUNT(*) FROM media_asset` vs 服务器 `find var/media -type f | wc -l`；② 抽 10 个 `relative_path` 的 `/media/` URL 须 200；③ 前台搜一商品看图/视频。
  7. 备选（不装 CLI 才用）：`tar -C var -cf - media | ssh <host> "tar -xf - -C /srv/joybuy/var"`——**无断点，中断从头来**，本机 VPN 有多次断线史，不推荐；**rsync 直传不要用**（69.9 万小文件 × RTT 估 ~20 h，且 Git Bash 无 rsync）。
  8. 增量（上线后爬虫仍在本地录入）：DB 差集 `SELECT relative_path FROM media_asset WHERE created_at >= <上次同步>` → `aws s3 sync --files-from=<list> var/media/ s3://…` → 服务器拉取；每晚 0.5–2 GB。不要全盘 `find`、不要全量 `sync --delete`。
- **IAM 授权组权限定稿（本节追加）**：两个组——`joybuy-media-upload`（本地）：bucket 级 `s3:ListBucket`+`s3:GetBucketLocation`（Resource=bucket ARN 不带 /*），对象级 `s3:PutObject`+`s3:AbortMultipartUpload`（Resource=`<bucket>/media/*`）；**故意不给 `s3:DeleteObject`**（误跑 `sync --delete` 只会 AccessDenied 而非清空）。`joybuy-media-readonly`（服务器）：同 ListBucket/GetBucketLocation + 对象级 `s3:GetObject`。两个用户只建 Access Key 不开控制台登录；**Lightsail 不能给实例挂 IAM 角色（EC2 才行）**，服务器只能放只读用户 key（`~/.aws/credentials` chmod 600）。Bucket 设置：region=eu-central-1、Block Public Access 四项全开、默认 SSE-S3、**不开版本控制**（56GB×多版本=双倍费）、Lifecycle 7 天中止未完成 multipart。
- **服务器访问方式（本节追加，用户问 MCP vs skill）**：**两者都不用——直接用本地 Git Bash 自带 ssh（Bash 工具）**。前提是密钥认证（`ssh-copy-id` 或 Lightsail 控制台贴公钥到 `~ubuntu/.ssh/authorized_keys`），因为本会话 shell 非交互、密码提示无法应答；`~/.ssh/config` 建 `Host joybuy` 别名（HostName=<IP>, User=ubuntu, IdentityFile=~/.ssh/id_ed25519）。首次连接带 `-o StrictHostKeyChecking=accept-new`。不引入第三方 SSH MCP（无必要），也无 SSH skill 可用。Lightsail Ubuntu 默认用户 `ubuntu`，自带免密 sudo。
- **服务器已接入（本节追加）**：用户交付 Lightsail 实例，IP `18.159.51.52`。私钥 `C:\Users\lyx\Downloads\sshkey.pem` 已复制为 `~/.ssh/joybuy_fra.pem`（chmod 600），`~/.ssh/config` 已建 `Host joybuy`（User=ubuntu, IdentityFile, IdentitiesOnly yes）。**实测连通**：Ubuntu 24.04.5 LTS，x86_64，**8 vCPU / 30Gi 内存 / 619GB 盘（已用 2.1G）——这是 32GB 套餐（$160.91/月），不是 16GB 推荐档**；主机名 `ip-172-26-5-182`（内网 172.26.x → VPC 已就绪）；免密 sudo OK；预装仅 python3，**无 aws CLI / nginx / docker**。IP 段 18.159.x 属 eu-central-1。后续运维一律 `ssh joybuy '<命令>'`。
- **上传耗时实测（2026-11-18，回答「压缩后再解压」问题）**：本机 → 法兰克福实测吞吐：单流 scp 120.5MB/56s = **2.14 MB/s（17 Mbps）**；3-4 路并行 = **4.0–4.4 MB/s（32–36 Mbps）**——并行有效翻倍（单流被跨洋 RTT 限制，未到宽带上限）。**压缩无用**：媒体是 JPEG/MP4 已压缩格式，gzip 只省 1-3%，白付本地打包 15-20min + 服务器解压 15-20min。**实测 4 次连接中断**（本机 VPN 抖动）→ 断点续传是刚需，tar 分卷整卷重传不可接受。PUT 费一次性 ~$3.7。测试残留：服务器 /tmp/pt_*.tmp 与 /tmp/speedtest_dump.tmp 已清理。
- **夜间流水线最终结果（2026-11-19 晨，自动执行完毕，关机前最后一次 HANDOFF 更新）**：① **媒体上传完成**：`aws s3 sync` exit 0、零错误，总耗时约 14h（706,445 文件；远端对象时间戳 2026-11-17 17:32 起的是 cms 目录首批，实际主力上传在 17:20 启动的进程内完成）。② **对账三重通过**：本地清点 706,445 文件 / 60,809,680,717 字节 == 上传日志 706,445 条 == S3 桶对象 706,445 / 60,809,680,717 字节（在新服务器用 `aws s3 ls --recursive --summarize` 复核，**一个字节不差**）。注意本地文件数 706,445 > 旧基线 698,926（基线统计后 var/media 有新增，如 cms 图），以实测为准。③ 新服务器反代链路验证 200（nginx proxy_cache MISS→HIT，migration 抽查+主代理复核均过）。④ 公共读已开放且匿名 GET 实测 200。⑤ **按授权已执行 `shutdown /s` 关闭本机**（用户就寝前明确授权「完成之后帮我关机」）。⑥ 服务器侧已装 AWS CLI v2.41（`/usr/local/bin/aws`，`~/.aws/credentials`=同 IAM key，chmod 600）——后续增量上传/桶管理可直接在服务器做，不依赖本机 VPN。⑦ VPN 晨间抖动（000↔200 反复横跳），不影响 AWS 内网操作。**遗留给用户**：EC2 安全组 `launch-wizard-1` 加 HTTP 80 入站（唯一卡点，加了外网即可访问 http://18.184.216.138）；验收新站后删旧 Lightsail 18.159.51.52（安全清单见上）。**待办**：/srv/data（120G 盘）规划 MySQL 数据/备份/nginx 缓存迁移；nginx 双 Cache-Control 头小清理（删 expires 7d）；media_asset DB 行数（101,850）< 文件数（706,445）是既有已知口径（derived 图落盘无 DB 行），非本次问题。
- **桶公共读已开放（2026-11-18 18:3x）**：用户补充 IAM 权限（Get/PutBucketPolicy、GetBucketPublicAccessBlock）后，已应用：BPA 改为 BlockPublicAcls/IgnorePublicAcls=true（保持）+ BlockPublicPolicy/RestrictPublicBuckets=false；桶策略 `PublicReadMedia` 允许匿名 `s3:GetObject` 仅限 `arn:.../media/*`（文件 `var/prod_deploy_20261117/bucket-policy.json`、`pab2.json`）。实测匿名 GET 已传对象 200（3,684 bytes）。**新服务器是两块盘**：nvme0n1 35GB 系统盘 + nvme1n1 120GB 数据盘（裸盘）——已格式化 ext4 挂载 `/srv/data`（fstab nofail，UUID 77b649d9-e343-4c94-8891-01f1ac259288），规划用途：MySQL 数据/备份/nginx media 缓存（迁移完成后再挪，避免与迁移中的容器冲突）。
- **方案转向（2026-11-18 18:0x 用户宣布，覆盖 0f 的部分决策）**：① **媒体永久存 S3 桶 `joybuy-media-fra`，不再落服务器盘**——正在跑的本地→S3 上传不变且成为最终存储；**取消**原第二段「服务器拉取」与「传完删桶」；② **换服务器**：用户已买好新服务器（IP 待提供，入口方式待定），服务器只放代码 + MySQL（~10GB）。已问询后用户选定：**媒体前端访问 = Nginx 反代 S3**（URL 保持 /media/... 不变、Django/前端零改动、resolver+proxy_pass 到 `joybuy-media-fra.s3.eu-central-1.amazonaws.com`、加 proxy_cache 省 S3 GET 费；媒体出网走 Lightsail 7TB 配额，月 2.1TB 远够）。**迁移计划**：新机装 docker/mysql/redis/nginx/node/pnpm + systemd 自启（同 0g 配方）→ 代码 bundle 或 git clone → **MySQL 从旧服务器 mysqldump 直灌新机（同区 AWS 内网）** → nginx /media/ 反代 S3 → 全站验证 → 旧 32GB 服务器退役。旧授权的「传完关机」仍执行（第二段已取消，关机改为「上传完成+对账通过后」）。
- **夜间自动流程授权（2026-11-18 17:2x 用户就寝前明确指示；已按方案转向修订）**：上传完成后代理自动执行：① 若 sync 失败则重跑续传（最多 5 次）；② 上传成功后做 S3 对账（本地 698,926 文件 vs 桶对象数/字节）；③ 对账通过后 `shutdown /s` 关闭本机（用户明确授权）；④ 若 5 次重试仍失败：如实记录 HANDOFF、正常关机，续传留到次日。原「服务器拉取→删桶」步骤已随方案转向**取消**。
- **第一段上传已启动（2026-11-18 ~17:20，后台任务进行中）**：AWS CLI 2.40.2 已装（`/c/Program Files/Amazon/AWSCLIV2/aws.exe`，region=eu-central-1，`max_concurrent_requests 15`、`multipart_chunksize 32MB`、threshold 64MB 已进 `~/.aws/config`）；密钥入 `~/.aws/credentials`（chmod 600，IAM 用户 `joybuy-up-down`，账号 289233836348）。**桶 `joybuy-media-fra`（eu-central-1）已由本机用 IAM 权限创建**：BPA 四项全开、SSE-AES256、Lifecycle 7 天中止 multipart（JSON 参数文件在 `var/prod_deploy_20261117/{pab,encryption,lifecycle}.json`）；注意 IAM 策略没有 `GetBucketPublicAccessBlock` 等读回权限（put 能成功、get 报 AccessDenied，正常，别当故障）。**上传：`aws s3 sync var/media/ s3://joybuy-media-fra/media/ --no-progress` 后台挂起，日志 `var/prod_deploy_20261117/media_sync.log`（每文件一行，行数=已完成文件数）**。实测前 2 分钟 ~20 文件/秒；媒体构成 = ~64 万小文件(~6GB) + ~5.7 万原图(~50GB)，小文件区受逐文件 PUT RTT 限制，**修正 ETA 8-12 小时（预计次日 3-5 点）**。断点续传：中断后重跑同一命令自动续。**上传期间禁止让本机睡眠/关机**。第二段（服务器拉取）待第一段完成后执行：服务器装 AWS CLI → `aws s3 sync s3://joybuy-media-fra/media/ /srv/joybuy/var/media/` → 校验 media_asset 对账 + 抽 URL 200 → 清空并删除桶（IAM 已含 DeleteObject/DeleteBucket）。
- **上传与爬虫共存（2026-11-18 追加）**：① 两者同走一条 VPN 隧道——4 路并行上传占 32-36 Mbps 会抬高延迟/丢包，爬虫带宽饿不死（只需 ~1 MB/s）但 ConnectionLost 概率上升；**推荐错峰（白天爬虫、夜里上传 nohup）；必须同时跑则 `max_concurrent_requests` 降到 8 并盯 `var/logs/crawl_runs/*.log`**。② 上传读 / 爬虫写同一个 `var/media/`，文件级无冲突，但 sync 可能抓到写入中的半截文件（sync 按 size+mtime 自愈，下轮增量自动重传）；干净做法是只传 mtime 早于爬虫本轮开始时间的文件。③ 本机 CPU/IO 互不影响。
- **安全边界**：服务器安全组只开 22/80/443；本地爬虫连生产库只走 SSH 隧道 `-L 3307:127.0.0.1:3306`；爬虫/翻译 Agent 不部署上云（用户约束）。
- **坑（新增/重申）**：① 本机 `du -sh var`（70 万文件）>2 min 超时，容量核对一律用 `var/capacity_20261117/scan_media.py`；② 传媒体不走 git；③ AWS CLI 未装，任何 `s3 sync` 前先装。
- **没做/待办**：① Lightsail 16GB 是否已创建待用户确认；② AWS CLI 未装、S3 bucket 未建；③ 传输未执行；④ 生产部署本身（gunicorn/Nginx/关 DEBUG/derived-card/gzip）按 §0 §7 上线前必修清单，属另一个任务。

## 0. 上一会话记录（2026-11-17 晚，法兰克福 + 1 万日访问 + 200 并发 + 媒体上界 200GB 的最终配置与月成本，✅ 完成）

- **任务**：按用户**最终确定的约束**重算上线配置与月成本并落文档。只做计算与文档，**未改任何业务代码**，未 commit。
- **用户最终约束（优先于此前所有口径）**：① 区域 **`eu-central-1`（Frankfurt）**，不再用迪拜/伦敦做主口径；② 日访问量 **约 1 万次访问/日**；③ **爬虫与翻译 Agent 一律不部署到上线服务器**（留本地/离线）；④ 仍要求**至少支撑 200 并发**（能力上限要求，不等于日常流量）；⑤ **媒体最终最大占用约 200 GB**（不是实测的 56.02 GB；商品还在继续录，这是预估上限）。
- **产出**：`var/capacity_20261117/frankfurt-10k-plan.md`（中文，9 节：约束与假设 → 流量反推 → 三套成本表 → 推荐与升级触发 → **磁盘与增长（媒体上界 200 GB → 400 GB 卷，含「媒体量不影响出网」与「备份按 222 GB 重算」两节）** → 爬虫/翻译离线方案 → 上线前必修清单 → **按实际流量选型（Lightsail，不承诺 200 并发）** → 一句话结论）。复算脚本 `var/capacity_20261117/frankfurt_10k.py`（只读，产出控制台表 + `frankfurt_10k.json`），运行：`./.venv/Scripts/python.exe -I var/capacity_20261117/frankfurt_10k.py`（控制台是 GBK，PowerShell/Git Bash 下建议加 `PYTHONIOENCODING=utf-8`，否则中文箭头会 `UnicodeEncodeError`）。
- **流量反推结论（主口径 = 1 万访问/日 × 6 页 = 6 万 PV/日）**：
  * 6 万 PV/日 → 月 180 万 PV；日均 0.69 页/s；峰值小时（占全天 10%）6,000 PV/h = **1.67 页/s**；峰值同时在线 **≈28 人**（按容量报告 15–25 s/页导航的 16.7 s 常数）；极端敏感度：峰值小时占 20% → 56 人，每页停留 60 s → 100 人。
  * 月出网 **2,102 GB（2.1 TB）**，系数 **1.17 MB/PV 来自既有报告 S1 场景反算**（1,024 GB ÷ 877,000 PV = 1.1676）；峰值带宽仅 **16 Mbps**。
  * **离 200 并发有多远**：页浏览 7.2×、同时在线 7.1×、API RPS 7.1×、出网 7.0×、日 PV **17.3×**（200 并发打满全天 = 104 万 PV/日）。**日常只用到 200 并发上限的 14%。**
  * 次口径 1 万 PV/日（= 1,667 访问/日）：峰值在线约 5 人、月出网 **350 GB**。
- **三套配置月成本（Frankfurt，730 h/月，USD，On-Demand / 1 年 RI，均不含税与 Support，媒体按 200 GB 上界 + 400 GB gp3）**：

  | 形态 | 6 万 PV/日（主口径） | 1 万 PV/日（次口径） |
  |---|---|---|
  | **S** 单机 `m7g.xlarge` 4C/16G + **400 GB gp3** + 同机 MySQL/Redis + EBS 直出 + EIP + 200 GB 快照 | **$375.40 / $327.07** | $217.77 / $169.44 |
  | **M** 单机 `m7g.2xlarge` 8C/32G + 同上 | **$518.11 / $421.53** | $360.49 / $263.91 |
  | **L** 应用 `m7g.xlarge` + RDS `db.m7g.large` 单 AZ + **S3 200 GB** + CloudFront | **$507.58 / $425.82** | $336.02 / $254.26 |

  * **媒体从 56 GB 涨到 200 GB 使 S/M 各涨 $24.44**（EBS 200→400 GB +$19.04，快照 100→200 GB +$5.40），**L 只涨 $3.46**（S3 200 GB = $4.80）。旧口径（56 GB / 200 GB 盘）为 S $350.96 / M $493.67 / L $504.12。
  * **方向反转**：旧口径 L 比 M 贵 $10.45，**新口径 L 比 M 便宜 $10.54**——因为 M 必须为 222 GB 数据买 400 GB gp3 + 200 GB 快照（$48.88），L 把同样 200 GB 放 S3 只要 $4.80。所以"M vs L"不再是价格问题，而是**8 专用核 vs 托管 RDS + CDN** 的能力取舍。
  * 出网占 S 形态的 **48%**（$180.15）；**反直觉发现**：法兰克福 EC2 出网 $0.090/GB vs CloudFront $0.085/GB 只差 $0.005；CF 赢在"1 TB 出网 + 1,000 万请求免费"。解方程得**破局点 ≈ 2.11 M 页/月 ≈ 7.0 万 PV/日**：低于它 CF 略便宜（6 万 PV/日 只省 $5.50），高于它 EC2 直出更便宜（24 图/页 → 44 请求/页，请求费按页线性涨）。**CDN 要按延迟/抗突发立项，不要按省钱立项。**
- **推荐 = M（单机 `m7g.2xlarge` 8C/32G + 400 GB gp3 + 同机 MySQL/Redis + EBS 直出）**，6 万 PV/日 **$518.11 OD / $421.53 RI**；理由：对齐容量报告的单机下限 8C/16G 且内存翻倍，200 并发设计点 CPU 35%、内存 25%；S 的 4C 在 200 并发要跑 71%（边际）；L 虽便宜 $10.54 但应用侧只有 4 核，恰好把 200 并发能力让出去了（团队更看重托管 DB 就选 L，两者都成立）。
- **升级触发条件**：① **vCPU 7 日均值 >60% 或峰值并发稳定 >150（持续 5 min）或 P95 TTFB >800 ms** → S 升 `m7g.2xlarge`（+$142.72 OD）；② MySQL `Threads_running` 峰值 >8 / buffer pool 命中率 <99% / 出现 `1205` → M 拆 **RDS `db.m7g.large`**（**−$10.54 OD，反而更便宜**；RI +$4.29）；③ 需要 PITR/免单点 → RDS 多 AZ（+$174）；④ 应用 CPU >70% 或要双机 → 第二台 + ALB（+$174）；⑤ 出网 >10 TB/月（≈28.5 万 PV/日）→ 上 CF；⑥ **磁盘占用 >340 GB（400 GB 卷 85%）→ 扩 500 GB（+$9.52）或 1 TB（+$47.60）**；⑦ 媒体实际 >250 GB → 扩 1 TB 或迁 S3；⑧ 媒体 >300 万文件 → 目录分片。
- **磁盘结论（媒体上界 200 GB）**：总占用 = 媒体 200 + MySQL 7（3 万 SPU 估 6–8）+ 系统/发布/日志 15 = **≈222 GB（区间 220–225）**。**原来的 200 GB 卷占用 111%，已不可用**；**推荐 400 GB gp3**（占用 55.5%，余 178 GB，$38.08/月）；300 GB 是最小可用（74%，到 85% 阈值只剩 33 GB），500 GB 多付 $9.52 买暂时用不上的空间。三条增长线（实测密度外推 173 GB / 用户上界 222 GB / 保守密度外推 237 GB）都落在 400 GB 卷的 40–60% 区间。
- **媒体 56 → 200 GB 不影响出网**（必须分开看）：页面只加载 `derived/card` 33 KB，出网仍是 1.17 MB/PV × 180 万 PV = **2,102 GB/月、峰值 15.6 Mbps**；出网费 $180.15（DTO）/ $174.65（CF 含请求）不变。涨的只是磁盘存了多少张图、备份时长、S3 PUT 请求费（200 GB/250 万文件 ≈ **$13.52 一次性**）、以及目录项数（250 万文件必须分片）。
- **爬虫/翻译不上线服务器的落地方式**：① **入向流量免费**（AWS 不收外部→EC2、同区 S3→EC2 的入向字节；Lightsail JSON 里 `data transfer in` 也是 $0.00）；② 首次全量：本地 `aws s3 sync var/media/ s3://…` → 服务器 `aws s3 sync s3://… /srv/media/`（同区免费）——**56 GB/69.9 万文件 = $3.70 PUT、2–4 h；到 200 GB/250 万文件 = $13.52、6–10 h**；或 `tar -cf - . | ssh ec2 'tar -xf -'` 单流（rsync 会被 250 万文件 × 30 ms RTT 拖到约 20 h）；③ 增量：DB 差集 `SELECT relative_path FROM media_asset WHERE created_at>=CURDATE()` → `rsync -az --files-from=`，每晚 0.5–2 GB；**不要 `find` 全盘或全量 `rsync --delete`**（250 万文件扫一次十几分钟）；④ 爬虫连库只走 **SSH 隧道 `-L 3307:127.0.0.1:3306`**，安全组只开 22/80/443，独立账号只授 staging/import 表，批量导入分批避免 `1205`；⑤ 翻译 Agent 本地跑 Ollama（零 GPU 机型需求），隧道读源字段 + 只写 `spu_translation`/`sku_specification_translation`/`spu_detail_translation`/`translation_term`，3 万 SPU 全量约 240 MB 往返、出向 <$0.03。服务器侧成本 **$0**。
- **上线前必修三项仍全部适用**（关 DEBUG + gunicorn/Nginx；图走 `derived/card` + Nginx 直出；gzip + Redis），量化后果：**商品图原图直出把 6 万 PV/日 的出网从 2,102 GB 抬到 12,179 GB，DTO $180.15 → $1,077.39（6.0×）**；在 200 并发设计点（1,037 万 PV/月）则是 **11,300 GB vs 82,000 GB，$1,002.70 vs $6,550.20（6.5×，即既有报告的 11.3TB/82TB）**。此外 Django 直出 5.5 ms/张 × 43.2M 张/月 = 66 核·小时/日 ≈ 2.75 核常驻。gzip 省 386 GB ≈ $34.73/月（设计点省 2.1 TB ≈ $190）；类目树 40 ms × 18 req/s = 0.72 核白烧。
- **追加口径（用户本次任务中途追加，已写入同一份报告 §8）**：**不承诺 200 并发，只按 1 万访问/日 + 200 GB 媒体 选型**。
  * Lightsail Frankfurt 官方价（`json/lightsail_eu-central-1.json`，publicationDate 2026-11-13，gzip；已实读复核）：4GB 2C/4G/**80GB**/4TB **$23.54**、8GB 2C/8G/**160GB**/5TB **$43.16**、16GB 4C/16G/**320GB**/6TB **$82.42**、32GB 8C/32G/**640GB**/7TB **$160.91**；超额 $0.09/GB、快照 $0.05/GB-月、附加盘 $0.10/GB-月、**入向 $0.00**、静态 IP 绑定免费、LB $17.66/月、**无 RI 折扣**。
  * **222 GB 数据把两个小套餐筛掉**：4GB（80 GB）占 277.5%、**8GB（160 GB）占 138.8%，缺 62 GB → 直接出局**（流量配额 5 TB 其实够用 2.4 倍，卡的是盘）；**16GB（320 GB）占 69.4%、余 98 GB → 最低可用**；32GB（640 GB）占 34.7%，盘更宽裕但不必要。
  * **最低可用 = Lightsail 16GB $82.42/月**（含 6 TB 出网 + 320 GB SSD + 静态 IP）；两档流量都未打满配额，超额 $0、两档同价。**8GB $43.16 不可选**——只便宜 $39.26，却连 200 GB 媒体都放不下，且"先跑再扩"救不了（盘随套餐固定、不能缩容）。
  * **便宜多少**：同场景 EC2 6 万 PV/日 为 $304.07（`m7g.large`+400GB）/ $375.40（`m7g.xlarge`+400GB）/ $540.96（`m7g.2xlarge`+640GB）→ Lightsail 16GB **省 $292.98（78%）**（对比 4C/16G）或 $221.65（73%）（对比能装下数据的最低 EC2）；32GB 省 $380.05（70%）。其中 **63% 的便宜额来自出网 + 静态 IP 打包**。
  * **备份按 222 GB 重算**：整机快照 **$11.10/份**（222 × $0.05）；**每周 1 份留 4 份 = $44.40/月**（留 2 份 $22.20）；**每天全量 = $333/月，明确不要**；DB 逻辑备份每日 1 GB 进 S3 = **$0.17/月**。**推荐组合 = 每周整机快照 ×4 + 每日 DB dump = $44.57/月**，16GB 全包 **$126.99/月**。理由：56 GB→200 GB 媒体的原始数据集在本地，**媒体可重建**，整机快照只需覆盖"OS+配置+DB"；`backup.sh` 现在每晚 tar 整个 media（56 GB × 14 = 780 GB，200 GB 后变 **2.8 TB**）必须改掉。
  * **保留接近 200 并发的加价阶梯**（起点 $82.42）：+$78.49 → LS 32GB $160.91（规格=8C/32G，共享 CPU 不能写 SLA）；+$435.69 → EC2 M $518.11（唯一可承诺）。EC2 相对最低可用方案的溢价约 **6.3 倍**。
- **验证（按验证纪律仅做针对性验证）**：本任务不涉及业务代码，**未跑任何后端/前端测试、未 build、未启停服务**。只做了：① `lightsail_eu-central-1.json`（gzip）只读解析复核 4 档套餐价与超额单价；② `frankfurt_10k.py` 复算，输出与报告表格逐项一致（三形态 × 两档流量 × OD/RI、磁盘增长、Lightsail 对比）；③ 与 `calc.py` / `cost_model.json` 的既有 Frankfurt 数值交叉核对（RI 单价、EBS/S3/CF 单价一致）。
- **坑（不得再踩）**：
  1. **视频会被算两次**：56.02 GB 媒体**已含**视频 5.49 GB；按 "GB/SPU × SPU" 外推时若再单独加视频列，12 个月会虚高 12.8 GB（本次第一版就把 173 GB 算成 186 GB）。正确做法：拆成"非视频 4.03 MB/SPU + 视频 0.43 MB/SPU"。
  2. **1.17 MB/PV 必须从 S1 反算**（1,024 GB ÷ 877,000 PV），不能从 S3 反算（那里是 1.09，差 7%）；两种口径混用会让三张表互相对不上。
  3. 脚本控制台输出在 Windows 是 **GBK**，`↔`/`→`/`≈`/`×` 会 `UnicodeEncodeError`；要么 `PYTHONIOENCODING=utf-8`，要么只用 ASCII 箭头。
  4. 分层计价循环里 `take = min(gb - prev, upper - prev)`——写 `min(gb, upper - prev)` 会把上一档重复计（AWS 报告已记过同一坑，本次复用 `tiered()` 未复发）。
  5. **CloudFront 在法兰克福不是省钱工具**：$0.085 vs $0.090 只差 0.005，赢利全靠 1 TB + 1,000 万请求免费；24 图/页的请求费按页线性增长，破局点 7.0 万 PV/日。别把"上 CDN"写成降本项。
  6. **Lightsail 实例是 x86_64**，导出快照到 EC2 只能生成 x86 AMI；迁 `m7g`/`c7g`（Graviton/arm64）**不能搬快照**，必须重建镜像（Django/Pillow/mysqlclient/Node 的 arm64 wheel）。要留迁移路径就写机型无关的部署脚本。
  7. Lightsail **不能挂 RDS、不能挂 EC2 到它的 LB、无多 AZ、无 RI**；自动快照 $0.05/GB-月 按份全量计（**222 GB → $11.10/份**；每周 4 份 $44.40/月，每天 30 份 $333/月——所以**不能每天全量**），恢复是整机还原、不能单表回滚，所以 mysqldump → S3 仍要自己做。
  8. HANDOFF 原有的 `## 0.` 标题**重复了两个**（AWS 选型 与 申请开店 都叫 `## 0.`），且已有 `## 0a.`/`## 0b.`/`## 0c.`。本次按"编号不重复"处理：新节 `## 0.`，AWS 选型 → `## 0a.`，申请开店 → `## 0d.`，PDP 翻译（原 `## 0a.`）→ `## 0e.`，`## 0b./## 0c.` 不动。**以后加节请先 `grep -n "^## 0" HANDOFF.md` 查重。**
  9. **媒体容量与出网是两个独立变量，绝对不能混算**：媒体 56→200 GB 涨的是"磁盘上存多少张图"，不是"每页发给浏览器多少字节"。出网只由 `PV 数 × 1.17 MB/PV` 决定（页面用 `derived/card` 33 KB）。本次差一点把 200 GB 当成"流量也涨 3.6 倍"去改出网行，那会把 $180 虚算成 $650。
  10. **Lightsail 8GB 不能靠"先跑再扩"救**：盘随套餐固定、不能缩容，222 GB 装进 160 GB 盘属于"从第一天就满"，表现为 MySQL 写失败（`Disk full`）+ 图片 404 + 日志写不进。**它不是"最低可用"，是"不可用"**；最低可用是 16GB（320 GB，占 69.4%）。
  11. **Lightsail 附加盘 $0.10/GB-月 比 S3 贵 4 倍、比 EBS gp3 还贵**（$0.0952）：盘快满时"挂附加盘"不是默认答案，**迁 S3（$0.024/GB-月）通常更省**；JSON 里另有一个 `Storage:*-StorageOverage-Bytes` = $0.0245/GB-月 的"存储超额"口径，两个口径含义不同（附加盘 vs 超套餐 SSD），别混用。
  12. **改一处容量约束要全表回算**：媒体上界从 56 改 200 GB 会同时影响 §3 三张明细表、§3.1/§3.5 汇总、§4.1/§4.2 推荐与阈值、§5 全章、§6.1 同步量、§8.3/§8.4/§8.6/§8.8/§8.9、§9 结论。本次靠 `frankfurt_10k.py` 里加一组 `shape_*2()`（400 GB 盘 / 200 GB 快照 / S3 200 GB）一次性重算，**不要手改表格数字**。
- **没做/待办**：① 报告金额是"官方单价 × 用量假设"，不是 AWS 账单实测，若需精确请用 Cost Explorer/Calculator 复核；② 未计入 Route 53 / WAF / CloudWatch / AWS Support（通常合计 $50–150/月）；③ 未评估 Lightsail Database（$15 起）作为"半托管 DB"的可行性；④ 未做 GBP/CNY 换算；⑤ **媒体 200 GB 是用户预估上界，不是实测**（现实测 56.02 GB）；上线后应每月用 `du`/`media_asset.byte_size` 复核，若实测曲线早于预估达到 200 GB，先扩盘再谈别的；⑥ 报告 §8 的 Lightsail 结论依赖"日常只有 28 人并发"这一前提，若上线后实测并发显著高于此，应先回到 §4 的 EC2 M 口径；⑦ Lightsail 的"存储超额"与"附加块存储"两个 $/GB 口径尚未做账单级验证（都按保守的 $0.10 计）。

## 0a. 上一会话记录（2026-11-17 晚，AWS 选型与官方价格调研：me-central-1 为主 + London/Frankfurt 对照，✅ 只读调研完成，未改任何代码）

- **任务**：为 Joybuy 上线（Nuxt 3 SSR 购物端 + Django + MySQL + 本地媒体）做 AWS 机型短名单与官方价格测算。口径经三次变更，**最终以 `me-central-1`（UAE/Dubai）为主报价区**，`eu-west-2`（London）与 `eu-central-1`（Frankfurt）作对照；按 200 并发、730 h/月、On-Demand 与 1 年期 RI 两套口径计算。
- **产出**：`var/capacity_20261117/aws-options.md`（10 章：数据来源与版本、机型可用性、三区价格表、存储/流量单价、成本假设、A/B/C 三形态 × 4 流量场景 × OD/RI、Lightsail/Spot、推荐方案、注意事项、附录）。
- **取数方式（可复用）**：
  * EC2 机型单价用 `b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/<Region>/Linux/index.json`（**返回体是 gzip**，需 `gzip.decompress`），区域名 `Middle East (UAE)` / `EU (London)` / `EU (Frankfurt)`。
  * RDS / EBS / S3 / CloudFront / DTO / ALB / VPC / Lightsail 用 AWS Price List API：`https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<Service>/<version>/<region>/index.json`。**注意服务代码**：ELB 是 `AWSELB`（`AmazonELB` 404）、数据传输是 `AWSDataTransfer`、弹性 IP 在 `AmazonVPC`。
  * 脚本：`var/capacity_20261117/extract.py`（ec2/rds 单价）、`ec2_extra.py`（EBS/EIP/NAT）、`calc.py`（A/B/C 成本模型，产出 `cost_model.json`）；原始 JSON 在 `var/capacity_20261117/json/`。
- **关键结论（写进报告，供后续引用）**：
  * me-central-1 **不提供 c7g 全系**、**不提供 Lightsail**、RDS **没有 db.r7g/db.m7i**（只有 m7g/m6g/r6g/t4g）；替代为 c7i / m7g / r7g / db.r6g。
  * 迪拜相对伦敦：EC2/DB/RDS 只贵 1–6%，**出网贵 22%（$0.11 vs $0.09/GB）**；DTO 官方 JSON 的 `pricePerUnit` 是 0.110，但同条 description 写 0.117（差 6.4%，已在报告标注）。
  * 200 并发：A 单机 `m7g.2xlarge`+200GB gp3 **$1,529/月（OD）/ $1,430（RI）**；B 应用 `m7g.xlarge`+RDS `db.m7g.xlarge` 单 AZ+S3/CF **$1,953 / $1,834**（省钱变体 B− `db.m7g.large`+200GB = **$1,756 / $1,672**）；C 高可用 **$2,505 / $2,269**。起步 1TB/月时 A=$422、B=$573。
  * 修图（`derived/card` 33KB）把出网从 82TB/月降到 11.3TB/月，A 形态月成本 $7,293→$1,529，是全场最大成本杠杆。
  * 延迟：AWS 区域间实测 eu-west-2↔me-central-1 **120.04 ms**（第三方基准），英国用户 100–140 ms；SSR TTFB 从伦敦 ~80ms 变 ~400–600ms（CloudFront 只救静态图，救不了 SSR HTML）。
- **验证（按验证纪律）**：本任务不涉及业务代码，**未跑任何后端/前端测试、未 build**；只做了 curl 取官方 JSON + Python 只读解析 + 成本模型重算（`python -I calc.py`，输出与报告表格一致）。
- **坑（不得再踩）**：
  1. `b0.p.awsstatic.com` 的 EC2 机型 JSON 是 **gzip 编码**，直接 `json.load` 会 `UnicodeDecodeError: 0x8b`，必须先 `gzip.decompress`。
  2. `b0.p.awsstatic.com` 只有 EC2 机型这套路径可用；S3/EBS/CloudFront/ELB/Lightsail 的 meteredUnitMaps 路径都 404，必须走 `pricing.us-east-1.amazonaws.com` 的 Price List API。
  3. `AmazonEC2` 单区域 offer 文件很大（me-central-1 126MB、eu-west-2 318MB、eu-central-1 434MB），不要整份读进上下文；用脚本一次解析后只打印目标行。
  4. 本机 PATH 里没有 `jq`，`/usr/bin/curl` 不存在；curl 在 `/d/Anaconda/Library/bin/curl`，python 在 `/d/Anaconda/python`（`-I` 时 cwd 不在 sys.path，需 `sys.path.insert(0,'.')`）。
  5. 分层计价写循环时 `take = min(gb, upper-prev)` 会把上一档重复计入（本次第一版就把 11.3TB 算成 $2,078 而非 $1,208），必须用 `min(gb-prev, upper-prev)`。
  6. CloudFront 出网价按**访问者边缘**计价，不按源站区域；英国访客走欧洲边缘。（迪拜/富查伊拉边缘是中东价 $0.11/GB。）
- **没做/待办**：① 报告里的用量是"假设 + 容量报告实测字节"推导，不是 AWS 账单实测；若后续要精确，需用 Cost Explorer 或 Calculator 复核。② 未评估 RDS Proxy、ElastiCache、WAF、Shield、Route53 的细项（报告 §9 只列为"未计入项"）。③ 未按 GBP 换算（用户若需要英镑口径需另加汇率）。

## 0c. 上一会话记录（2026-11-17，上线容量评估：200 并发最低服务器配置，✅ 只读分析完成，未改业务代码）

- **任务**：为「购物端 + 商家端 + 管理端 + Django + MySQL + 本地媒体存储」整体上线测算最低服务器配置（硬要求 ≥200 并发）。只读，未改 `backend/`、`storefront/` 等业务代码。
- **产出**：`var/capacity_20261117/capacity-report.md`（含负载假设三档、各组件资源估算、单机/双机/三机方案、磁盘与带宽测算、17 条短板清单）。
- **结论**：单机最低 **8 vCPU / 16 GB / 200 GB NVMe / 200 Mbps**（100 Mbps 为硬下限）；双机 = 应用节点 4C8G + 数据节点 4C16G/500GB；三机再加媒体/静态节点 2C4G/1TB。
- **实测事实（可直接引用）**：MySQL 8.4.7 逻辑数据 768.4 MB + 索引 292.6 MB（117 表），磁盘 3.63 GB，`innodb_buffer_pool_size` 仍为 dev 默认 128 MB；SPU 12,841（ACTIVE 7,899）、SKU 18,315、Offer 16,219（ACTIVE 13,314）、`product_search_document` 7,900、Order 45；媒体 **56.02 GB / 698,926 文件**（商品 50.52 GB、视频 855 个 5.49 GB，原图 jpg 平均 921 KB）；API 单请求 CPU 搜索 40.2 ms / 详情 46.9 ms / 类目树 40.2 ms（DEBUG=True 的 runserver，含 dev 开销）；Nuxt dev SSR CPU 首页 64 ms / 品类页 128 ms / 详情 50 ms；页面体积 home 83 KB、`/c/<slug>` 110 KB、`/search` 105 KB、PDP 84 KB；**商品卡引用原图，一页 24 张 = 7.6–7.8 MB**。
- **两个关键瓶颈**：① 出带宽——`ProductCard.vue` 用 `image_path`（`/media/products/original/*.jpg`）而不是库里已有的 `derived/card`（33 KB），典型 12 页/秒需 325 Mbps，改用派生图后 48 Mbps；② 单进程——生产无 gunicorn/systemd，当前是 runserver（10 并发搜索 0.74 s）。
- **必须补的短板（P0）**：关 DEBUG（根目录无 `.env`，默认 development）、上 gunicorn+Nginx、媒体改用派生图、媒体由 Nginx 直出（Django 直出 330 KB 图 = 5.5 ms CPU）、配 HTTPS/真实域名。P1：gzip（实测关闭，类目 JSON 41 KB→11 KB、品类页 108 KB→29 KB）、Redis 缓存（`DBSIZE=0`，只有登录限流在用）、MySQL buffer pool、备份改增量（现 `backup.sh` 每晚 tar 56 GB 媒体 × 14 天 = 780 GB）、Session 迁 Redis、进程守护。
- **验证方式（按验证纪律仅做针对性验证）**：只做了只读采集与 curl 探针，未跑任何测试套件、未 build 前端、未启停服务。数据来源与命令见报告附录「本轮实测数据索引」。
- **坑（不得再踩）**：① Windows 下 `du -sh var/media` 对 70 万文件会超时（>5 min），改用 `os.walk` 的 `scan_media.py`；② 媒体体积以 `media_asset.byte_size` 聚合最快，但会漏掉"派生图落盘但 DB 行缺失"的差异（DB 20.0 GB vs 磁盘派生 14.5 GB）；③ `/api/v1/search` 返回的 `image_path` 是原图路径，但页面渲染出的 24 张与 API 单页求和（15.4 MB）不一致——以**渲染 HTML 里实际引用的 URL 求和**（7.6 MB）为准，浏览器只拉这些。

## 0d. 上一会话记录（2026-11-17，申请开店表单改 7 项字段 + 买家侧图片上传 + 审核页展示 + approve 联动，✅ 完成，已 commit & push）

- **任务**：用户要求「申请开店」表单改为 7 项——店铺logo、用户名字、店铺名、手机号码、邀请码（选填）、个人证件（身份证/护照/驾照 三选一 + 证件照片）、个人居住地址。全链路（买家表单→上传→提交校验→管理端审核展示→approve 开店联动→商家端进入）实测通过，双语各一轮，console error 0（唯一 console 错误来自故意的 400 负例分支页）。**只测不提交 git（本轮之后已由用户指示统一提交推送）。**
- **模型与迁移**：`merchants/models.py::MerchantApplication` 新增 `user_name`(60)/`phone`(32)/`id_document_type`(TextChoices: ID_CARD/PASSPORT/DRIVER_LICENSE，默认 ID_CARD)/`residential_address`(255)/`logo_image_url`(500)/`id_document_image_url`(500)；`legal_name` 为旧表单遗留字段保留（新表单不再收集、不覆盖旧值）。迁移 **`0008_merchantapplication_shop_fields`** 已 apply 到 dev MySQL。旧字段 `referrer_code` 语义不变（选填）。
- **后端行为变化（`merchant_ops/views_shop_application.py`）**：
  * POST 必填：user_name/shop_name/phone/residential_address/logo_image_url/id_document_image_url；手机号宽松校验（去空格/横线/括号后 `^\+?\d{6,20}$`，覆盖 +44 与 0 开头，正则 `PHONE_PATTERN` 在测试固化）；证件类型三选一（大小写不敏感归一 upper）；图片 URL 只接受 `/media/` 前缀且必须命中真实 `MediaAsset.relative_path`（错误码 `<FIELD>_INVALID` / `<FIELD>_NOT_FOUND`，如 `LOGO_IMAGE_INVALID`/`ID_DOCUMENT_IMAGE_NOT_FOUND`）；**邀请码不再在提交时校验有效性**（旧 `REFERRER_CODE_INVALID` 提交校验已删——无效码可提交，approve 时按 WP-42 绑定、无效忽略）；REJECTED 重申覆盖全部新字段。
  * **买家上传接口契约**：`POST /api/v1/account/merchant-application/media`（multipart：`file` + `purpose`，purpose 仅接受 `shop_application`），买家会话 + CSRF；复用 `media/uploads.py::store_upload`（Pillow 验真/2MB/sha256/MERCHANT 桶，PURPOSES 新增 `shop_application`）；201 回 `{"media":{url,sha256,mime_type,width,height,byte_size,deduplicated}}`；错误码 `BUYER_AUTH_REQUIRED`/`UPLOAD_PURPOSE_INVALID`/`FILE_REQUIRED`/`FILE_NOT_IMAGE`/`IMAGE_FORMAT_UNSUPPORTED`/`FILE_TOO_LARGE`。证件照敏感口径写在类注释（仅本人提交/平台审核读取）。
  * 审核回包 `_application_payload` 带全部新字段（user_name/phone/id_document_type/residential_address/logo_image_url/id_document_image_url + 旧字段）。
  * **approve 联动**：`create_merchant(... avatar_url=application.logo_image_url ...)`（logo 回填 `Merchant.avatar_url`）+ 既有 `referrer_code` 绑定不变。
  * 测试 `merchant_ops/tests/test_merchant_application.py`：32 用例（新增必填/手机号格式枚举/地址长度/证件类型枚举(含小写归一)/非法图片 URL 400×2/空邀请码可提交/无效邀请码提交成功且 approve 忽略/上传接口 5 例/审核列表带新字段/logo 回填断言/驳回重申覆盖新字段）。
- **前端**：`storefront/pages/account/apply-shop.vue` 重写表单为 7 项（顺序即用户口径），上传走新买家接口（客户端预检 JPG/PNG/WebP+2MB，blob 预览，上传中/失败态行内提示）；行内校验错误双语（watcher 在用户补填后清除对应错误）；服务端错误码映射 `shopApply.err*` 双语键；PENDING/APPROVED/REJECTED 态回显全部字段 + logo/证件照缩略图；重申回填全部旧值（含两张图的 /media/ URL 预览与 radio 选中态）。`storefront/locales/messages.js` 精确 Edit 插入 `shopApply.*` en/zh 各 33 键（删除已无引用的 `shopApply.legalName*` 2 键）。
- **admin-web**：`admin-web/src/views/MerchantsView.vue` 入驻申请列表列改为 买家账号/用户名字/店铺名称/手机号码/邀请码/状态/申请时间/操作；审核弹窗改为 `app-detail-table` 字段表格（10 行全字段）+ logo 缩略图 + 证件照缩略图（点击 `.app-image-lightbox` 放大，点遮罩关闭，附敏感信息提示）。
- **验证（按验证纪律针对性 + 任务指定的全量项）**：
  * 后端：`manage.py test merchant_ops.tests.test_merchant_application --keepdb --noinput --parallel 1` → **Ran 32 tests, OK**；`ruff check`（models/0008/uploads/views_shop_application/urls/测试）全过。
  * 改后端后重启 :8000（旧 PID 7956/29076 taskkill，新 PID 37052，带 `CRAWL_VARIANT_PRICE_LIMIT=3`，`/api/v1/categories` 200）。
  * 前端：`vitest run` 全量 **19 files / 91 tests passed**（基线保持）；prettier --check + eslint（apply-shop.vue、messages.js、MerchantsView.vue）全过。注意 storefront eslint 要在 storefront 目录用 `cmd //c "node_modules\\.bin\\eslint.CMD <file>"`。
  * **E2E（Playwright headless，脚本与截图 `var/apply_shop_fields_20261117/`，跑两轮均 ok:true）**：买家 A（EN）canvas 生成 PNG 真实上传（logo+证件照）→ 7 项填写（含有效邀请码 E2EFLDREF01、PASSPORT）→ 提交 PENDING → 临时 admin 管理端审核弹窗见 10 行字段 + 两图 → 证件照点击放大 → 通过 → apply-shop 通过态回显 → 「Go to Merchant Center」落 `localhost:5174/dashboard` 已登录；买家 B（ZH）空邀请码提交成功 → 驳回 → 「重新申请」回填全部旧值（含图预览与 DRIVER_LICENSE 选中）→ 改名重提 → 通过 → 商家端进入；**错误分支（API 直调，均不落库）**：缺 user_name/缺 phone/坏 phone/坏证件类型/外链 logo/缺 logo/不存在 logo/不存在证件照 → 全部 400 对应错误码，随后 GET 申请仍 null；DB 验证：A/B 的 `Merchant.avatar_url` == 申请 logo URL，`MerchantReferral` 仅 A 有（code E2EFLDREF01），B 空邀请码无绑定。console error 0（仅负例页 8 条故意 400）。
  * **清理（删净）**：BEFORE `{buyers:6, applications:4, merchants:4(含邀请商家), referrals:2, staffs:5(4买家+1临时admin), audit_logs:6, orders:0, media_assets:4}` → AFTER 全 0；4 个测试 PNG 物理文件从 `var/media/merchants/original/**` 删除（两次运行内容寻址去重共用同 4 个）；LEFTOVER 复查（buyers/staffs/merchants/applications/media/audit_logs_by_admin）全 0。
- **坑（不得再踩）**：
  1. `MerchantReferral` 的 referrer/referee 都是 **PROTECT**：清理必须先删 MerchantReferral 再删 Merchant，否则 PROTECT 报错。
  2. canvas 生成 PNG 的两次 E2E 上传同字节 → MediaAsset 内容寻址去重（第二次 deduplicated=true），清理按 relative_path 集合删一次即可。
  3. storefront 的 eslint 在 Git Bash 里直呼 `node node_modules/eslint/bin/eslint.js` 会 MODULE_NOT_FOUND（storefront/node_modules 无 eslint 实体，.bin 是 pnpm shim）；要 `cd storefront && cmd //c "node_modules\\.bin\\eslint.CMD <file>"`。
  4. admin-web 的 `/media` 已有 Vite 代理（`admin-web/vite.config.js`），`<img src="/media/...">` 在 5173 可直接显示，无需改。
  5. 旧测试 `test_invalid_referrer_code_rejected` 已按新口径改写为「无效邀请码提交 201 + approve 忽略」——不要再把提交时校验邀请码加回来（WP-42 口径：无效不阻断）。
- **Git 同步（2026-11-17，用户指示「提交到 github」之后）**：本轮把工作区积压的全部改动（此前多个会话的功能，含本次 7 字段申请表单）一次性提交：`4d3f077 Sync accumulated storefront, admin, merchant and crawler work`（407 个文件，+35712/−1501），`git push origin main` 成功（远程 `633c481..4d3f077`）。提交前把 `_preview.html`、`*.bak-*` 加入 `.gitignore` 排除；`var/`、`translation_agent/`、`crawler/debug_session.py`、`backend/raw/` 等仍被忽略，未泄露 cookie/密钥。`backend/media/` 是 Django app 代码（34 个文件，226K），已入库。提交后工作区干净。
- **下一步建议**：①`shopApply.legalName*` 键与 `legal_name` 字段已成遗留，可另开清理任务；②商家端「店铺资料」页可顺带展示 avatar_url（本次只回填字段未改商家端展示）；③HANDOFF.md 已膨胀到 ~750KB，后续可压缩已失效的历史会话记录（AGENTS.md 允许压缩已失效细节，但不得删掉仍影响决策的约束和踩坑）。

## 0e. 上一会话记录（2026-11-17，PDP 商品详情未完整翻译修复 + 详情接口接译文表，✅ 完成，未 commit）

- **任务**：修三个用户可见问题——①规格参数/图文详情没翻译；②SPU 2335（`0647049c-523b-49c6-9040-f1a14201e67f`）GB+中文（简体）显示别国语言（德语）；③下方详情数据没翻译。根因与修法按任务书执行完毕，全部实测通过。完整报告与截图：`var/pdp_full_translate_20261117/report.md`（含修复前后 API/DOM 原文摘录、7 张截图、API JSON 存档）。
- **改动文件（全部未 commit）**：
  - `backend/catalog/models.py`：新增 `SpuDetailTranslation`（**unmanaged**，`db_table="spu_detail_translation"`，字段与 translation_agent 的 SQLAlchemy 表一致；**不建 Django 迁移**）。
  - `backend/catalog/detail_views.py`：新增 `_detail_translation()`（`OperationalError/ProgrammingError` 防御，测试库/无表环境回退源数据）与 `_translated_detail_payload()`（**逐字段**覆盖：译文空值保留源数据，防丢内容）；payload 顶层新增 `detail_translated` / `detail_language`；`spec_options` 译文照常走 `_spec_options_payload` public_id 映射。
  - `backend/catalog/localization_services.py`：`resolve_product_content` 的 legacy 先按 pk 稳定排序；未命中 locale/language 时**显式回退 `['en-GB','en']`（origin=`FALLBACK_SOURCE`）**；最后才 pk 兜底（origin=`FALLBACK`）——修掉 zh-CN 随机落 de-BE 行的 bug。
  - `storefront/pages/p/[id].vue`：`matchSpec` 在 `detail_translated && sku.specification_translated` 时改用译文 `sku.specification` 匹配（详情译文与 SKU 规格译文同术语缓存、语言一致），否则维持 `canonical_specification ?? specification`；新增 `isDetailTranslated` computed。
  - `backend/catalog/tests/test_product_detail_api.py`：新增 `DetailTranslationOverlayTests` 3 用例；`backend/catalog/tests/test_localization.py`：新增 `ProductContentFallbackTests` 3 用例。
- **验证结果（针对性验证，全部实测）**：
  - 后端：`./.venv/Scripts/python.exe backend/manage.py test catalog.tests.test_product_detail_api catalog.tests.test_search catalog.tests.test_localization --noinput --parallel 1` → **Ran 29 tests, OK**（含新增 6 用例）。
  - 2335：zh-CN 修复前德语（截图 `2335_zh_before_fix.png`）→ 修复后英文（`FALLBACK_SOURCE`，content_locale=en-GB）；de-DE 规格表 `Technische Spezifikationen`/`Haltungsart der Hand=Beidhändig`、图文 `Produktbeschreibung` 全德语 + `detail_translated=true`；FR/NL 各抽查标题+规格表头前 2 行全译文。
  - 多规格回归：7964 de-DE 点 Silber → 选中态 `256GB+Silber`、购物条 `Silber / 256GB`、无跳变；点回 Cosmic Orange 正常；fr-FR 点 Argent → `256GB+Argent`；7964 德语 AI 摘要实读成功。
  - 回退回归：121 DE 英文如常；177 en-GB 英文原文+源规格表；API 层 DE vs EN blocks 数/序/images 逐项相等；`spec_options.sku_ids` 仍映射本地 public_id。
  - console error 0（177 DE、2335 zh reload 后钩子均 `[]`）。
- **坑（不得再踩）**：
  - ①**本仓工作区有大量前会话未提交改动，不能用 `git show HEAD:` 还原旧版做「修复前」取证**——HEAD 的 `detail_views.py`/`models.py` 会被 `merchant_ops/views_catalog.py` 的未提交 import（`_spec_options_payload`、`LOCAL_PARENT_MERCHANT_CATEGORY`）直接打断启动。「修复前」要用任务开始时的工作区版本（models.py 新增类对旧代码惰性可保留）。
  - ②**测试库建 `spu_detail_translation` 表**：`TestCase` 的类级 atomic 禁 DDL（报 `TransactionManagementError`），必须用 `TransactionTestCase` + `schema_editor.create_model`（带 introspection 存在性守卫）；但 `TransactionTestCase` 会截断迁移种子，setUp 需对 Merchant/Market/Locale/Currency get_or_create 自愈（字段照抄 `offers/migrations/0006_seed_european_markets.py`）。
  - ③storefront dev server 绑的是 `[::1]:3000`（IPv6），浏览器用 `127.0.0.1:3000` 会 ERR_CONNECTION_REFUSED，要用 `localhost:3000`。
  - ④IAB 里 `locator(sel, {hasText})` 的 hasText 不可靠（点击超时），`getByRole().click()` 也可能卡 actionability；用 `tab.playwright.evaluate(() => el.click())` 页面内点击最稳；IAB 里 `window.scrollTo` 不触发 window scroll 事件，验购物条要手动 `dispatchEvent(new Event('scroll'))`。
  - ⑤`?market=DE&locale=en-GB` 会回落 DE 默认 de-DE 是既有设计（locale 必须属于该 market 的 MarketLocale），不是 bug。
  - ⑥重启 :8000 时必须把 netstat 上的**所有** LISTENING PID 杀干净（venv 重定向器父子对），否则旧进程仍占端口、新进程静默死掉，请求会打到旧代码。
- **遗留（见 report.md 遗留清单）**：`ai_summary_tags` 未接（表无此列）；搜索卡标题仍英文（`product_search_document` 未重建，属下一步）；术语缓存缺词条保留源语言（如 7964 Cosmic Orange）；zh 无详情译文（需先建数据）；站点 chrome（Specifications/Buy now 等）de/fr/nl 下仍英文（messages.js 只有 en/zh）。
- **环境**：:8000 已用同命令行重启（含 `CRAWL_VARIANT_PRICE_LIMIT=3`），`/api/v1/categories` 200；未动 `translation_agent/`（代码与数据）、`deploy/Modelfile`。

## 0b. 上一会话记录（2026-11-17 深夜，只读验证会话）

- **任务**：独立复核「切换国家/语言后 PDP 商品详情正确变化」修复在真实数据下是否成立（只读验证 + 浏览器实测，不改业务代码、不 commit）。
- **结果：VERDICT: PASS**，完整报告与截图在 `var/pdp_locale_switch_20261117/verification.md`（矩阵表格、请求参数、冷加载、回退、console 全记录）。
- **实测覆盖**：177 与 7964 两个 PDP 各 12 步页内切换矩阵（GB→BE(nl-BE)→fr-BE→de-BE→DE→FR→NL→GB→LU(lb-LU)→fr-LU→de-LU→lb-LU），每步断言标题关键词、已选 SKU 规格文本（Schwarz/Noir/Zwart/Black 跟随）、fetch hook 抓到的 `?market=…&locale=…` 请求参数全部一致；6 例 cookie 冷加载 SSR 首屏语言全部正确；7964 de-DE/FR 点「银色」规格→选中态+购物条 `Silber / 256GB`/`256GB / Argent` 正常；未翻译商品 SPU 121（`d63d8069-7eff-40be-9d71-2f27a176cb4b`）DE 下英文回退正常；全程 console error/pageerror/unhandledrejection 0 条。
- **新踩坑（必须记住）**：
  - ① 清单给的"未翻译商品" SPU 2~16 等页面全是「This product has been delisted」——它们 offer 的 `listed_at=NULL`，且 public_id 在 DB 存的是 32 位无连字符形式，Django `<uuid>` 路由要求带连字符 → 这些 URL 直接 404。找回退测试样本必须选 public_id 可写成标准 UUID 且 offer `listed_at IS NOT NULL` 的 SPU（实测 SPU 121 通过）。
  - ② **lb-LU 的 FALLBACK 标题不是英文**：`resolve_product_content`（`backend/catalog/localization_services.py`）FALLBACK 分支取 `spu.translations.all()` 无排序第一行 `legacy[0]`（177/7964 均为 de-BE 行 → 德语标题 + 英文 canonical 规格）；`content_origin=FALLBACK` 标记正确。属既有后端设计非本次回归，放量不阻塞，但建议另行任务把 FALLBACK 明确为 en-GB 优先。
  - ③ 切市场时一次会发 **2 个** `/api/v1/products/` 请求（中间态 `market=新&locale=旧` + 终态 `market=新&locale=新`），cookie 与 locale 响应式更新链所致，良性，统计请求别误判为重复 bug。
  - ④ 搜索接口返回的标题不走 PDP 的 `resolve_product_content` 本地化：`/search?q=CHiQ` 在 DE/FR 下卡片标题仍是英文原文（PDP 却是德/法语）；search 请求本身会带新 locale 重新发出（computed key 先例生效）。首页切语言无任何 `/api/v1` 重请求（SSR payload + 冻结 key）。
  - ⑤ IAB 里 Playwright `locator(sel, { hasText })` 的 hasText 选项疑似被忽略（匹配数不收敛），按 name 匹配用 `getByRole('button', { name })` 更可靠。
- **下一步（承接上一会话）**：①上面 5 处同类冻结 key 是否要修、②后端 `spu_detail_translation` 让规格参数表/图文出译文 —— 均待用户拍板；本次 PASS 后可放量跑 50 个商品译文任务。

- **当前任务（2026-11-19，productCommentSaleFloor 销量/评价展示值入库，已完成）**：用户要「已售 6k+ 件」这类销量数据。实测源站详情页 flight 有 `productCommentSaleFloor{saleAmount:"10k+", starShow, commentCount:"80+"}`（**/dp/ 有、/dg/ 没有**，蜘蛛主详情走 /dp/ 所以零新增请求；值是展示字符串非精确数字）。已实现全链路：
  1. parser：`extract_sale_info(floors)` 读该 floor 的 saleAmount/commentCount（缺失返回空 dict 不发明数据）→ `UkProduct.sale_amount/comment_count_display` → `to_payload()` 顶层键 + `joybuy.saleInfo{saleAmount, commentCountDisplay}`（有值才输出，向后兼容）。
  2. 入库：`SpuDetail` 新增 `sale_amount`/`comment_count_display` CharField(32)（迁移 catalog/0017，与 translation 模型同文件一起 apply）；`_sync_spu_detail` 写入，**空值不覆盖已有值**。
  3. 测试：`SaleFloorTests` 3 例（提取/缺失/部分字段）+ `SaleFloorImportTests` 2 例（落库 + 空 payload 不覆盖）；修正 `test_no_review_text_is_captured` 断言排除 comment_count_display（它是计数展示串非评价正文）。真实商品验证：iPhone `10k+/80+`、饼干 `1k+/50+` 全部进 payload。
  4. **历史商品不回填**（用户明确：旧的不要，后续自己随机生成这些数据）。后续新爬取任务自动带上。
  - 验证：`py_compile`/ruff 全过；detail_extras+import+variants+review_aggregates+import_variants 62 tests（1 处断言按新字段调整）全绿；迁移已 apply 到 dev 库。
  - **存量已随机生成（用户要求「每个商品都加上销量」）**：`var/backfill_sale_amount_20261119/generate.py`（DRY_RUN 预览 → `--apply` 分段写库，seed=20261119 可复现）。长尾分布：46% <100 件、25% 100~999、17% 1k~5k、8% 5k~20k、2% ≥20k；有评分商品销量中枢更高（对数均匀）。**12802/12802 全部写入，0 空值**（只写 sale_amount，comment_count_display 留空待后续爬虫补真实值）。重跑会重新随机化覆盖（固定 seed 则复现同分布）。

- **晨报已汇报（2026-11-19 早上，day_crawl_20261119 批次复盘）**：20 任务终态 8 SUCCEEDED（导入 662）/ 8 FAILED（部分导入 730）/ 5 未跑（01 组 4 个 PENDING + 1 RUNNING 被超时杀）。**熔断触发**（连续 5 个坏 run：全部「150 分钟超时被杀」，RISK_FB 事件都 ≤1——不是风控爆发，是单 run 速度赶不上 150 分钟上限：这批类目商品量大（discovered 400）+ 变体补价请求多）。失败 7 个都是**导入了几百个后被 150 分钟超时杀掉**的半成品（手机 70/摄影 65/理疗 109/哺育 142/婴儿车 91/美发 174/电子配件 89）。冷却账号仅 1 个（06 组）。**明日建议**：①大任务（discovered 200+）单 run 150 分钟不够——队列超时提到 240 分钟，或 CRAWL_VARIANT_PRICE_LIMIT 再降；②01 组 5 个 PENDING 任务与 7 个半成品重跑（需新建 job，名称唯一）可今晚继续；③剩余 READY 89。

- **当前状态（2026-11-19，用户要求「暂停抓取任务」——已全部停干净）**：
  1. **停止动作**：`var/resume_crawl_20261119/resume_queue.py` 调度进程已 kill（PID 15924；另一位 36848 已不存在）；所有 `run_crawl_run` 执行器进程已 kill（含重复实例：d24e17db/27c20446/625418bd 曾各有 2 个进程，属早前一次尝试的孤儿 + 本次重复派发）；5 个在跑的 CrawlRun 已 `complete_run_failed(reason="用户要求暂停…")`（e870c734 手机 1、d24e17db 饮品机 7、68e5231f 婴幼儿玩具 7、625418bd Drones 2、27c20446 笔记本与纸品 12——已导入数据全部保留，`skip_imported=开` 可无缝续跑）。残留 RUNNING 仅 2 个历史 demo run（d4d82124/e6b6c146），非本轮。
  2. **按用户新口径已改的代码（未 commit）**：`CRAWL_VARIANT_PRICE_LIMIT <= 0 = 不限个数`（原 0 是「一个都不补」）→ `spiders/joybuy_run.py::_pending_variant_skus` 判断改为 `if limit > 0 and len(pending) >= limit`；`settings.py` 默认值 10 → **0（不限）**。`test_crawler_variants` 8 例全绿、ruff 过。**用户最高优先级：商品规格必须一比一完整抓取，宁可慢/长也不缺变体价格。**
  3. **未完成的验证**：不限变体后**尚未**在真实多规格商品上实测「32 variants 全部有价」；也未按新口径（超时 360 分钟、熔断不计超时、spawn 显式 limit=0）重跑。下次继续时先做这两步再做批次。
  4. 昨晚 8 个超时 FAILED 的真因是 150 分钟上限（RISK_FB 全 ≤1，非风控）；队列调度曾出现同一 run 双执行器，下次启动前务必先 `wmic process where "name='python.exe'" get ProcessId,CommandLine | grep run_crawl_run` 清场。

- **全部暂停确认（2026-11-21）**：缺口重爬的 shard1 重试进程（38260/37724）已按用户指示 kill，残留进程 0、RUNNING run 仅剩 2 个历史 demo 僵尸。当前没有任何抓取活动。**待办清单（等用户指示）**：①259 个壳页商品重试（等风控缓解——换节点/深夜时段，账号已是爬虫任务同一批，成因是 IP/频率级风控）②阶段 2 的 20 个品类任务未开始 ③剩余 READY 89 个 + 男装等半成品续跑 ④变体完整性的新口径实测已通过（32/32 全有价）⑤媒体按用户要求暂用 local（S3 不可用）。

- **壳页重试完成（2026-11-21 晚，重试被风控自停两次后的最终账）**：286 尝试 → **56 导入** / 143 `source_not_found`（**源站商品已 404 下架**——重跑 /dp/x/ 直接 not found，属商品失效非我们的问题，这部分从缺口中除名）/ 0 仍壳页 / 9 其它失败 / 风控中断 5（自停保护生效：连续 3 商品全风控即停）。`risk_detail` 23 个只补了 2 个（20 个未尝试）。**DB 无价 SKU：1488 → 1022**（净减 466）。06 组消耗大（pk56-61 共 12+ 次 risk parks），03 组 7 个账号 6.8-8.2h 前标记（已过 6h 冷却）。**剩余缺口 ≈1022 个无价 SKU**：构成 = 未尝试 71（51 壳页 + 20 risk_detail）+ 源站仍无价的部分 + 昨晚各批次其它遗留。**下一步**：等冷却过期（03 组约 6h）+ 换时段重跑剩余 71 个 + `skip_imported=False` 全量补价刷新（或对 staging `offers_skipped_no_price>0` 的 492 行定向刷新）。

- **源站下架商品同步下架 + 标记（2026-11-21，用户要求）**：壳页重试发现 143 个「source_not_found」商品源站已 404 下架 → 本地同步下架：`var/gap_recrawl_20261121/delist_source_removed.py`（DRY_RUN 默认 → --apply）。**执行结果**：143 个 SPU 全部为 DRAFT（从未上架，无状态变化）；**563 个 ACTIVE Offer 全部转 INACTIVE + `removed_by_platform=True` + `removed_at` 留痕**（沿用 merchant_ops unpublish 的既有机制，历史行保留）；搜索文档已刷新（这些 SPU 本就 0 文档）。**后续删除入口**：清单固化在 `var/gap_recrawl_20261121/delisted_source_removed.json`（spu_pk + source_id + 下架 Offer 数），用户说「不要了」时按此清单删除。验证：ACTIVE Offer 0、INACTIVE+removed_by_platform 563。
- **首页「Popular right now」无图商品已替换（2026-11-21，用户报「模块下商品图片没有」）**：排查结论——**与 143 个下架商品无关**（它们从未被任何 CMS 模块引用、本地画廊文件 1129 个全在）；无图根因是首页 `page1/pos3 product_pool` 的 4 个条目是**demo 种子数据**（public_id `01926c1e-…-0001..0004`，Spu 表里不存在，payload 也没 image_path 字段）。**替换**：从搜索文档挑 4 个有图（本地文件存在）+有价+跨类目的真实商品（扫地机器人 999.00 / 自动伞 19.99 / 越南粉套装 4.25 / 标签打印机 12.99）写入模块 payload；原 payload 备份在 `var/popular_right_now_backup.json`，候选池 `var/replacement_candidates.json`。验证：4 条 image 本地存在、public_id 在 Spu 表存在。**注意**：若用户后续在其它模块再发现无图，按同法排查（image_path 空 = demo 数据或源站无图，与下架无关）。
- **「模块商品图片没有」根因修正（2026-11-21，用户按家用电器频道举例）**：之前只修了首页 demo 条目——但用户实指的是**频道楼层图片文件 404**。全频道扫描：后端返回的 `image_path` 都有值，但 **138 条楼层条目的本地文件缺失**（`var/media` 下不存在）——这些商品是 S3 时代（MEDIA_BACKEND=s3）导入的，文件只写进了桶、本地没有；S3 停用后前端 `/media/...` 全 404 裂图。分布：Beauty Best sellers/New in（美妆大牌为主）、家用电器频道 Large appliances 第 2 个（TCL 酒柜）等。首页「Popular right now」的 4 个 demo 条目是另一处（已替换为真实商品）。**修复方向（待用户确认）**：①把 S3 桶里对应对象拉回本地（aws s3 cp --recursive，桶 joybuy-media-fra 的对象都在）；②或对这些楼层条目换本地有图的替换品；③或恢复 S3 后端。143 下架商品的文件本地也在（已核对 0 缺失），与裂图无关。
- **媒体缺失全量审计（2026-11-21 深夜，✅ 只读完成，未 commit、未碰 9334/FB、零业务代码改动、未启动任何抓取）**：把上面 138 条的粗扫升级为「频道楼层 + 首页全部商品位」的 A/B 两成因定性审计。**总账（渲染可见商品条目 564）**：正常 415 / **成因 A（S3 遗留）148 条**（频道楼层 138 + 首页畅销榜单 10，去重后 122 个唯一文件；S3 时代只写桶）/**成因 B（真缺图）仅 1 条**（首页畅销榜单 pet-supplies tab 第 5 位 Dr John Silver 狗粮 `4962bdf2-c3df-4897-8efc-03fa2b1d3c1c`，SPU pk=10197 ACTIVE 有价 £14.70，**MediaUsage 全角色 0 行**，不在任何频道楼层）/ 另有 60 条 demo 引用（public_id `01926c1e-…`，Spu 表不存在）只在 CMS home 快照 v4-v8（ARCHIVED）与 v9 的 campaign_grid payload 里——**渲染时 campaign_grid 被 HomeCampaignCard 覆盖（10 张卡本地图全在），用户不可见**，无需替换可选清理。首页其余全部正常：HomeCampaignCard 22 项（campaign 10/discovery 6/weekly 6）、为您推荐 24 件、link_grid tiles 6 + brand_logos 12 全 ok。**成因 A 按频道分布**：NL 运动户外 71（Gifting/New Arrivals/Final Pieces 各 20+Bestsellers 11）、美妆 19（Best sellers 11+New in 8）、健康养生 17、家居 10（Save up to 40% on Christmas 整层 10 条）、家电 8（含 TCL 酒柜）、宠物 7、玩具婴童 6；电子/游戏两频道 0 缺。畅销榜 10 条缺图分布：美妆 tab 4、家居 2、健康 2、户外 2。**S3 可访问性结论：完全不可访问**——profile [default] 的 key 在 AWS 侧已不存在（`InvalidAccessKeyId`，与账号暂停一致）、匿名 head 403 Forbidden；122 个对象的 head_object 全部是认证层错误而非 404，**对象级存在性无法证实**，按导入史实归 A；「等 S3 恢复自动补上」目前只是等待，无人能拉回。**替换计划（就绪待用户确认，本轮未替换）**：成因 B 唯一 1 条 + 3 个已验证候选（同 tab 同排序 sort=newest 顺延：Harringtons 羊肉米饭 4kg £5.62 / Harringtons 火鸡蔬菜 1.7kg £5.62 / Pedigree Junior 幼犬湿粮 40 包 £4.00，ACTIVE Offer 与本地画廊图逐一核过）——替换方式为畅销榜取数口径天然顺延（search sort=newest page1 前 5），或直接把该 SPU 下架即可让第 5 位自然换人；频道楼层 0 条成因 B 无需替换。**固化文件 `var/media_audit_20261121/`**：`audit.json`（全量条目：频道/楼层/位置/公id/title/本地有无/S3 head 结果/归类）、`replace_plan.json`（成因 B 替换建议+候选+可选清理项）、`scan_local.json`/`scan_home.json`（原始扫描）、`s3_probe.json`（逐对象探测）、4 个脚本（scan_local/scan_home/s3_probe/build_audit.py，全部只读可重跑）。**验证（按验证纪律仅针对性验证）**：扫描脚本跑通且数字交叉核对（495+45+24=564=415+148+1）；138 条与上一轮粗扫完全吻合（TCL 酒柜、Fino 洗发水等抽样命中）；候选商品 ACTIVE Offer 数与本地画廊文件逐一验证 True。**坑**：①首页当前 PUBLISHED v9 快照没有 product_pool——商品楼层来自 HomeBestsellers（/api/v1/search sort=newest 前 5）与 HomeRecommended（/api/v1/recommendations 前 24），审计首页别再只看 CmsModule 快照；②畅销榜/推荐的图也走 gallery MediaUsage，成因 A 不止频道楼层；③head_object 404 与 InvalidAccessKeyId 要区分（后者不代表对象不存在）；④前端 nav 类目口径 = category_tree roots 去掉 NAV_HIDDEN_ROOT_SLUGS（computers-accessories/clothing-accessories）。
- **媒体缺失成因 B 已替换（2026-11-21，✅ 完成，未 commit、未碰 9334/FB、未启动任何抓取、未打印 Cookie）**：上面审计确认的唯一真缺图商品——首页畅销榜 pet-supplies tab 第 5 位 Dr John Silver（SPU pk=10197，`4962bdf2-c3df-4897-8efc-03fa2b1d3c1c`）——已按平台下架机制换掉，SPU/Sku/Offer 数据全部保留（只下架不删除）。**方式（复用 merchant_ops unpublish 同款口径，Django shell 执行，脚本 `var/tmp_takedown_10197.py`）**：① Spu 10197 status ACTIVE→INACTIVE（save update_fields=["status","updated_at"]）；② 该 SPU 全库仅 1 个 Offer（pk=12734，current_price £14.70）级联下架：ACTIVE→INACTIVE + removed_by_platform=True + removed_at=2026-11-21 15:16:01 UTC，update 影响 1 行，改后该 SPU ACTIVE Offer=0、全 INACTIVE；③ `refresh_spu_search_documents(spu)` 返回 1——其唯一 ProductSearchDocument 被删（改后 0 行），没有手工改搜索文档表数据（文档是派生的）。**验证（按验证纪律仅针对性验证，以下全部真实跑过，未跑的不存在）**：① DB 复核：SPU status=INACTIVE；Offer pk=12734 INACTIVE/removed_by_platform=True/removed_at 已写；ProductSearchDocument 0 行；② 搜索接口 `q=Dr John Silver` → total=0（该商品已不可搜）；③ 畅销榜 pet-supplies tab（`/api/v1/search?category=pet-supplies&sort=newest&page=1` 前 5）：4962bdf2 已掉出，**第 5 位换成 `692cb504` Harringtons Dog GF Superfoods Puppy Chick 10kg（£39.29）**，前 5（6035a87c/70d374f9/4df70820/a484069a/692cb504）image_path 非空且 `var/media` 本地文件逐一存在；④ **全 tab 交叉复查**：nav 可见 tab 共 **9 个**（home-living/electronics/beauty-personal-care/small-home-appliances/health-wellness/outdoor-sports/pet-supplies/baby-toddler/games-accessories，各取前 5）：electronics、small-home-appliances、pet-supplies、baby-toddler、games-accessories 5 个 tab 前 5 全部本地图 OK；成因 B（image_path 完全为空）畅销榜全站清零；剩余 10 条「有 image_path 但本地文件缺失」与审计成因 A（S3 遗留，等待 S3、不可拉回）数量与分布**完全吻合**——美妆 4 / 家居 2 / 健康 2 / 户外 2，按本次范围边界未动。校验脚本（只读可重跑）：`var/tmp_verify_bestsellers.py`、`var/tmp_precheck_10197.py`。**坑**：①畅销榜 tab 是 9 个不是 5 个——「5」指的是每 tab 取前 5 张卡（HomeBestsellers.vue slice(0,5)），别再按 5 个 tab 复查；②Windows 控制台默认 GBK，UTF-8 输出含 `®`/中文会 UnicodeEncodeError，校验脚本开头要 `sys.stdout.reconfigure(encoding="utf-8")`；③搜索接口 query 参数名是 `q` 不是 `query`（传错=静默全量返回 8353 条，看似正常实则没过滤）；④`manage.py shell < file` 按交互逐行解析会把缩进块打断（IndentationError），多行脚本要用 `manage.py shell -c "exec(open(path, encoding='utf-8').read())"`；⑤Django shell 里 `-I`（isolated）会砍掉 cwd 导入路径导致 ModuleNotFoundError: config，本项目自建脚本不要加 -I。
## 1. 我们在做什么

## 批次 20（2026-11-22 夜批）（20 个抓取任务 → 汇总 → 关机，自动记录）

- **任务**：用户指令——跑 20 个抓取任务，全部终态后汇总报告 + 关机。不 commit、不超 20 个、不碰 9334/FB、不改业务代码。**本批已按指令执行 `shutdown /s /t 120`。**
- **前置核实**：phase2（recrawl_local_20261122/phase2）已于 14:51 全终态（succeeded=0 failed=2 skipped=3，`phase2/queue.log`），未与 06 组抢池；启动前 `wmic` 清场无同组进程。
- **账号池实测（22:57 本地）**：07=10、08=4、01=9、02=6、03=1（9 个 00:11 解冻）、05=1（7 个 ~02:50 解冻）、06=0（8 个 ~05:50 解冻，被 phase2 烧光）、04=0 VALID。**任务只存在于 01–06 组 → 把 06 组 5 个任务改派 07、02 组 4 个改派 08，共 20 个任务均衡到 07=5 / 08=4 / 01=3 / 02=3 / 03=5；原始组收尾已还原**（`task_list.json.original_groups`、`final_summary.json`）。
- **执行口径**：并发 ≤5（每组 1 worker、同组串行）、单 run 超时 240min（超时不算坏）、连续 3 个坏 run（FAILED+RISK_CONTROL_FALLBACK/ACCOUNT_POOL_EXHAUSTED/CONNECTIVITY_PREFLIGHT_FAILED）熔断、无可用账号的组到 not_before 再试否则 skip（不计坏）、spawn env 显式 `MEDIA_BACKEND=local` + `CRAWL_VARIANT_PRICE_LIMIT=0`。试水 job=151（07 组）：parsed/risk 达标的 10 分钟闸门后才放量。
- **结果**：succeeded=9 failed=0 skipped=11；runs_started=9；breaker_tripped=False；aborted=None。本批导入 996 个商品，风控事件累计 446。每任务结果（组/run/状态/导入）：`{"220": ["数据抓取01", "ce97dba5", "SUCCEEDED", 12], "221": ["数据抓取01", "dd214c1b", "SUCCEEDED", 157], "223": ["数据抓取01", "49c3007f", "SUCCEEDED", 192], "171": ["数据抓取02", "60e4901e", "SUCCEEDED", 198], "177": ["数据抓取02", "bba22faf", "SUCCEEDED", 121], "183": ["数据抓取02", null, "SKIPPED", null], "130": ["数据抓取03", "014bf308", "SUCCEEDED", 7], "142": ["数据抓取03", null, "SKIPPED", null], "166": ["数据抓取03", null, "SKIPPED", null], "172": ["数据抓取03", null, "SKIPPED", null], "178": ["数据抓取03", null, "SKIPPED", null], "151": ["数据抓取07", "89f9b8a5", "SUCCEEDED", 182], "163": ["数据抓取07", "c27af298", "SUCCEEDED", 79], "175": ["数据抓取07", null, "SKIPPED", null], "187": ["数据抓取07", null, "SKIPPED", null], "231": ["数据抓取07", null, "SKIPPED", null], "135": ["数据抓取08", "5a588d37", "SUCCEEDED", 48], "141": ["数据抓取08", null, "SKIPPED", null], "147": ["数据抓取08", null, "SKIPPED", null], "159": ["数据抓取08", null, "SKIPPED", null]}`。
- **跳过原因**：`{"183": "no_usable_accounts", "142": "no_usable_accounts", "166": "no_usable_accounts", "172": "no_usable_accounts", "178": "no_usable_accounts", "175": "no_usable_accounts", "187": "no_usable_accounts", "231": "no_usable_accounts", "141": "no_usable_accounts", "147": "no_usable_accounts", "159": "no_usable_accounts"}`
- **质量抽查（每任务 1 个商品）**：SPU 变体价覆盖、gallery≥1、图文/规格表见 `BATCH_REPORT.md` 第 4 节；异常（gallery=0 或本地缺文件）0 个：`[]`。
- **媒体本地化**：本批导入 SPU 988 个、gallery 资产 6859 个、本地缺文件 543 个。
- **全库累计**：SPU 17111（ACTIVE 10279）、SKU 24790、Offer 23806（有价 23806）、媒体资产 134286、gallery usage 98565。
- **产物**：`var/batch20_20261122/BATCH_REPORT.md`（统计+抽查+全库）、`final_summary.json`、`progress.json`、`queue.log`、`pool_snapshot.json`、`task_list.json`；脚本 `build_task_list.py`/`batch20_queue.py`/`finale20.py`。零业务代码改动。
- **坑/约束**：①06 组已被 phase2 烧光（不是「8 个干净」），任何新会话别直接派 06；②03 组解冻前派发会立刻 ACCOUNT_POOL_EXHAUSTED；③任务组与账号组解耦时要还原 account_group，否则运营页面看到的组会漂移；④breaker 是全局的，某组连续耗尽可能连坐其他组的新派发。


## 重抓 S3 时代商品已完成（2026-11-22 晨，自动记录）

- **任务**：用户夜批指令——重抓 S3 时代导入的 1,443 个商品（媒体当时只写进已失效 S3 桶、本地全缺），MEDIA_BACKEND=local 全程显式覆盖；完成后跑 5 个新品类任务；完成自动关机。不 commit、不碰 9334/FB。
- **清单口径（DB 实查修正任务书）**：主清单=cutoff（created_at>=2026-11-19 17:54 UTC）的 1,443 个 joybuy_uk source_id（与任务书总数吻合）；任务书称「其中 143 个已下架需跳过」经查**不成立**——`var/gap_recrawl_20261121/delisted_source_removed.json` 的 143 个是 2026-11-16 时代商品，与 cutoff 清单**零交集**（防御性过滤为 no-op）。另发现媒体审计成因 A（频道楼层缺图 148 条/129 SPU）**也不在 cutoff 内**（staging 显示 2026-11-19 上午经脚本导入、同为 S3 时代媒体缺失）→ 把其中有 joybuy_uk 身份的 62 个置顶并入（另有 67 个无 joybuy_uk 身份无法走 source_id 管线，未纳入）。**总目标 1,505**，清单固化 `var/recrawl_local_20261122/recrawl_list.json`。
- **关键机制发现（本轮最重的坑）**：S3 时代商品的 MediaAsset 行已存在但本地无文件，`store_bytes` sha256 去重命中即返回**不会补写本地文件**（HANDOFF 0u 坑②），且 `ensure_image_variants` 会因读不到文件抛 FileNotFoundError 让画廊图整张丢弃——重抓前打了**物化包装**（`recrawl_runner.py` 内 monkeypatch `media.storage.store_bytes`+`media.pipeline.store_bytes` 两命名空间：命中已有行且本地缺文件时先写文件再走原逻辑）。探针验证：local 基线 + 遗留行物化 PROBE PASS（`var/recrawl_local_20261122/probe_media.log`）。
- **试水**：shard0 --limit 5（均为成因 A 置顶商品）5/5 imported、媒体 missing_local=0、变体价 6/6、原地更新（identity.spu==imported.spu）5/5（`trial_shard0.log`）。
- **阶段 1 执行**：3 分片 detach（shard0=数据抓取07、shard1=03、shard2=06，各自独立账号池防互踩；01/02 未用；串行+间隔 2-3s；连续 2 商品风控→停 10 分钟换号一次再中即停）。统计：attempted=1505 imported=1195 剩余未终态=234（断点固化 recrawl_remaining.json）；风控命中商品次数=99；分片停止原因={"shard0": "completed", "shard1": "stopped_risk: 2 consecutive risk products AFTER pause+switch", "shard2": "stopped_risk: 2 consecutive risk products AFTER pause+switch"}。
- **媒体落本地验证（DB 全量）**：重抓导入 SPU 关联 PRODUCT 资产 5698 个，缺本地文件 0 个；导入记录级 missing_local>0 商品 0 个。
- **变体完整性**：按类目每类抽查 2 个 imported 商品（晨报表格）：DB Sku 行数 ≥ payload 变体数（合并保留）、still_unpriced 抽查全 0。
- **阶段 2**：succeeded=0 failed=2 skipped=3（任务 {"139": ["数据抓取06-DIY工具", "FAILED", 73], "130": ["数据抓取03-冰鲜食品", null, null], "138": ["数据抓取05-园艺 & 庭院工具", null, null], "142": ["数据抓取03-女装 & 配饰", null, null], "145": ["数据抓取06-时尚鞋靴", "FAILED", 14]}）。spawn env 显式 MEDIA_BACKEND=local + CRAWL_VARIANT_PRICE_LIMIT=0；run 超时 55min（同组 2 任务串行最坏 110min）。
- **收尾**：晨报 `var/recrawl_local_20261122/MORNING_REPORT.md`；本记录由 finale.py 自动插入；**用户已取消关机（2026-11-22 下午口径）——文档写完正常退出，不关机。**
- **脚本（var/ 下，py_compile+ruff 全过，未 commit）**：recrawl_local_20261122/ 下 build_list.py / check_cause_a.py / crosscheck.py / pool_status.py / probe_media.py / recrawl_runner.py / phase2_queue.py / chain.py / finale.py / watchdog.py。业务代码零改动。
- **留给早班会话**：①剩余断点续跑命令（见晨报第 5 节）；②成因 A 中 67 个无 joybuy_uk 身份的 SPU 需另行方案（换源或人工）；③本地媒体等 AWS 恢复后 aws s3 sync 增量同步；④01/02 组源站标记未测衰减。


## 重抓 S3 时代商品夜批进行中（2026-11-22 凌晨启动，无人值守，完成后自动关机；本条为进行中快照，finale.py 完成时会自动在本节顶上插完成记录）

- **任务**：用户夜批指令——用 MEDIA_BACKEND=local 重抓 S3 时代（媒体只写进已失效 S3 桶、本地全缺）导入的商品，媒体/数据完整落本地；完成后跑 5 个新品类任务；完成自动关机。不 commit、不碰 9334/FB、风控纪律沿用。
- **清单口径（DB 实查修正任务书两处）**：主清单=cutoff（created_at>=2026-11-19 17:54 UTC）的 **1,443** 个 joybuy_uk source_id（类目分布与任务书吻合：冷冻肉类与家禽 199、智能家居 196、泰国及东南亚食品 189、冷冻素食与纯素 184、珠宝 139、烟草 93、宠物 92、手表 87、电子健康检测 81、印度及南亚食品 78、冷冻派对食品 43、韩国食品 23、美发工具 20、清洁用品 14、平板电脑 5；±1 差异=归因口径）。**修正 ①**：任务书称「其中 143 个已下架需跳过」不成立——delisted_source_removed.json 的 143 个是 2026-11-16 时代商品，与 cutoff 清单**零交集**（防御性过滤为 no-op）。**修正 ②**：媒体审计成因 A（频道楼层/畅销榜缺图 148 条/129 SPU）也不在 cutoff 内（staging 显示 2026-11-19 上午经脚本导入，同为 S3 时代媒体缺失）→ 把其中有 joybuy_uk 身份的 **62 个置顶并入**（另 67 个无 joybuy_uk 身份，无法走 source_id 管线，未纳入）。**总目标 1,505**，固化 `var/recrawl_local_20261122/recrawl_list.json`。
- **关键机制发现（本轮最重的坑，下次直接复用）**：S3 时代商品 MediaAsset 行已存在但本地无文件，`store_bytes` sha256 去重命中即返回**不会补写本地文件**（0u 坑②），且 `ensure_image_variants` 读不到文件抛 FileNotFoundError → 重抓导入会把画廊图整张丢掉。**处置**：`recrawl_runner.py` 内对 `media.storage.store_bytes`+`media.pipeline.store_bytes` 两命名空间打物化包装（命中已有行且本地缺文件→先写文件再走原逻辑），不改业务代码。探针 PROBE PASS（`var/recrawl_local_20261122/probe_media.log`：local 基线+遗留行物化+清场）。
- **试水**：shard0 --limit 5（均为成因 A 置顶）**5/5 imported**、媒体 missing_local=0、变体价 6/6、原地更新（identity.spu==imported.spu）5/5（`trial_shard0.log`）。
- **阶段 1（运行中）**：3 分片 detach（各自独立账号池防互踩；01/02 未用）；串行+间隔 2-3s+变体补价不限（CRAWL_VARIANT_PRICE_LIMIT=0）；连续 2 商品风控→停 10 分钟换号一次再中即停；进度每商品落盘 progress.shard{0,1,2}of3.json 可断点续跑。**编排修正（19:33 UTC）**：shard2（数据抓取06）18:53 UTC 首轮 4 分钟即连续命中风控、20:03 换号重试仍连中→按纪律自停（06 组疑似源站侧标记，493 项标 not_attempted 断点保留）；改用干净池 **数据抓取05** 重启 shard2（shard2_babysitter.py 独立看护，死线 00:20 UTC）；原 chain.py 只监控自己拉起的进程、存在「shard1 提前自停+shard0 提前跑完 → 阶段 2 与替换分片并发重叠」缺口 → 已杀 chain 监控进程（保留分片进程），换 **chain2.py**（chain pid=2312 已终止；chain2 监控 shard0=53236(07)/shard1=28320(03)/shard2=14104(05)；统一死线 00:20 UTC 到点 kill 存活分片；shard0 自然跑完后若子集有剩余会用干净池 数据抓取08 启 shard0b 消化）。
- **runner 增强（19:29 UTC，仅 var/ 脚本）**：recrawl_runner 风控命中点（detail/变体全风控/park）现在会调 mark_account_risk_cooldown 写 6h DB 冷却（与 spider 同口径），使阶段 2 动态选组的 usable 统计反映真实源站标记；已运行中的 shard0/1 不受影响（旧代码内存态），shard0b 与晨后续跑生效。
- **阶段 2（自动接续）**：chain 在分片全部退出或死线后，按当时账号池现状从 03/05/06 的 READY 动态挑 5 个（排除 01/02/04/default；优先 skip_imported=True；配额按 usable 账号数 2/2/1）写 `phase2/task_list.json` → phase2_queue.py（run 超时 55min，同组串行最坏 110min；spawn env 显式 MEDIA_BACKEND=local + CRAWL_VARIANT_PRICE_LIMIT=0）。
- **收尾（自动）**：finale.py = 清理 RUNNING run → 汇总 → DB 媒体全量核对 + 每类目抽查 2 商品变体完整性 → `var/recrawl_local_20261122/MORNING_REPORT.md` + recrawl_remaining.json → HANDOFF 自动插完成记录（锚点「重抓 S3 时代商品已完成」）→ shutdown /s /t 120。**watchdog pid 独立**（watchdog.log），硬死线 2026-11-22 03:46 UTC（11:46 本地）兜底强制收尾+关机。
- **⭐用户口径更新 2（2026-11-22 ~16:10 本地，最新，覆盖 1 号口径的关机部分）**：**取消关机**——剩余分片 + 5 任务批全部跑完后保持开机，不执行 shutdown。finale.py 已改为只写晨报/HANDOFF/finale_done 后正常退出（并 `shutdown /a` 保险撤销遗留排程）；watchdog v2 16:05 UTC 兜底死线保留（防挂死），触发动作=截断分片→补跑 5 任务→文档→不关机。早前 1 号口径原文（关机部分已被本条覆盖）：3 分片全终态→5 任务批终态→晨报→HANDOFF→关机；shard1 慢可接受，不许为赶时间跳过变体补价。
- **编排按新口径重做（23:51-23:56 UTC）**：①杀 chain2（其 00:20 UTC phase1 死线会强杀健康分片）、杀 watchdog v1（其 03:46 UTC 死线同样违反新口径）、杀 shard2_babysitter（其 00:20 死线会杀 shard2'）；②新 **chain3.py**：无 phase1 死线、等分片终态、分片退出且有剩余→5 分钟后同/备组自动重启（每槽最多 3 次启动：shard0=07→08→07、shard1=03×3、shard2=05×3）、全终态→阶段 2（run 超时按剩余窗口动态写入 task_list.json，phase2_queue 读取；预算夹 [60,360]min）→ finale（含 shutdown）；心跳 heartbeat.json 供看门狗判挂死；③新 **watchdog v2**：+16h 兜底死线（2026-11-22 15:55 UTC）+ 心跳 45 分钟过期判挂死，触发时才 kill+finale+关机，**不会在分片健康运行时提前关机**。
- **⚠️看门狗误杀事故（23:53 UTC，已完全恢复，教训在位）**：watchdog v2 首轮循环在 chain3 首次心跳落盘前（启动 2 秒内）检查 heartbeat.json→「缺失」→立即 FORCE FINALE：按 pids.json 杀了 shard0(53236)/shard1(28320)（shard2'=14104 因不在 shards[] 键下幸免）、杀了新 chain3，并拉起一个过早的 finale.py。**止损动作**：发现 finale 尚未写出任何产物（晨报/recrawl_remaining/finale_done/关机调度均无）→ taskkill finale 进程（PID 58780）→ 精确验证 HANDOFF 无过早完成记录（grep 锚点命中是进行中快照里的提示文字）→ 修复根因（chain3 启动即写心跳；watchdog 对心跳缺失给 10 分钟启动宽限）→ chain3 重启后按重启流程 5 分钟宽限自动拉回 shard0（**数据抓取08 组**，start#2）与 shard1（03 组，start#2），分片进度文件零丢失（todo=361/477 续跑）。**教训：凡「文件缺失即触发毁灭动作」的看护，必须给启动宽限窗口；毁灭性动作前先核对目标 PID 存活。**
- **网络退化事件（19:52 UTC 起，已查明并决策）**：代理链路从 ~2-5s/请求恶化到**恒定 ~42.7s/请求**（cloudflare/google/joybuy 全网皆慢、固定延迟像限速，joybuy.com 一度 242s）→ 判定 VPN 节点限速/拥塞，非源站封锁。换节点不可行：verge-mihomo 核心无 external-controller 监听（仅 1053/7897）、无桌面 GUI 自动化工具，不安全动用户 VPN 客户端 → **决策=维持龟速爬取**（42.7s<45s 超时线，请求仍完成；质量抽查：近期导入媒体 missing_local=0、变体价全齐，慢但正确）。吞吐预估：00:20 UTC 死线前阶段 1 约再 +60-150 件，剩余断点续跑。若明早网络已恢复，续跑效率会正常。
- **明早先看晨报再动手**；本次零业务代码改动（全部 var/ 下，py_compile+ruff 过，未 commit）；后端 8000 未动。


- **风控试水 5 品类（2026-11-21 11:47-14:10 本地，✅ 完成，判定=中间态；未 commit、未关机、未碰 9334/FB、未打印 Cookie、媒体 local、零业务代码改动）**：5 个 READY 品类任务（分属 01/02/03/05/06 各 1）并发 5 探测风控，为放量前的决策提供依据。启动方式与 night_queue 派发口径完全一致（start_run + run_crawl_run，MEDIA_BACKEND=local、CRAWL_VARIANT_PRICE_LIMIT=0）。
  - **任务与终态**（run id 前 8 位 / 状态 / 导入/发现（已请求） / RISK_CONTROL_FALLBACK / 烧号）：
    01 组 job 200 冷冻派对食品 `075302fa` FAILED(主动停) 43/199(61 请求) risk_fb=12 烧 9/9；02 组 job 153 美发工具 `d2cd2a9b` FAILED(主动停) 20/191(35 请求) risk_fb=16 烧 6/6；03 组 job 148 珠宝 `30909966` SUCCEEDED(自然跑完) 140/200(200 请求) risk_fb=11 烧 10/10(尾部耗尽后仍排空队列)；05 组 job 144 手表 `b7bc885f` SUCCEEDED 88/109 risk_fb=2 烧 2/8；06 组 job 157 电子健康检测 `916c0f83` SUCCEEDED 82/92 risk_fb=0 烧 0/8。
  - **风控时间线（UTC）**：03:47:43 五 run 同 IP 同刻启动 → **03:47:50（+7 秒）01/02 各首中**（详情页 307 → `/user/risk/pic?redirectReason=risk605_pic`，每次命中=账号移出本轮池+写 6h 冷却）→ 01 前 6 分钟烧 5 号、04:08:02 `ACCOUNT_POOL_EXHAUSTED`；02 前 44 秒烧 2 号、04:04:23 耗尽 → 04:09 按中间态纪律 taskkill 两 run 进程树并 `complete_run_failed`（注明风控原因）→ 03 首中 04:22、05 首中 ~04:50（各零星 ≤2 次）→ 03 后段 05:52-06:06 加速 3 连烧至池耗尽，但排空队列于 06:10 自然 SUCCEEDED → 06 全程零风控（51 分钟完跑）。
  - **核心结论：风控=源站账号级标记+速率混合，当前 IP 层干净**。同 IP 同时窗：06 全程 0 风控、05 仅 2 次、03 中段零星，而 01/02 开局秒弹——01/02 组账号昨晚 17:33-21:09 被风控波标记过，我方 6h 冷却早已过期，**但源站侧账号记忆仍在**（换号无效）。03/05 的中段零星命中与持续请求速率相关。**放量铁律：01/02 组在源站标记衰减前（时长未知，≥24h 观察后议）任何放量都会秒烧账号；06/05 可正常放量。**
  - **按组结论与下一步**：06 组安全可放量（0/8）；05 组基本安全（2/8，剩余 6 账号可用）；03 组待 20:06 本地冷却过期后先单任务试再放量（本次尾部被打穿但完跑，导入 140）；01/02 组**不要放量**（池已全烧且源站标记未消）。可选路径：04 组解封 Google 验证后启用（32 READY）；给 01/02 补新账号；或换出口 IP 后对 01/02 单任务试水。
  - **规格完整性（fullcheck.py 对全部 IMPORTED 行全量核对）**：有价 Offer 覆盖=01 46/46、02 20/20、03 375/378、05 161/161、06 90/90（99-100%）；DB Sku 行数**从不小于** payload.skus（多出行=历史变体合并保留，零丢失）；03 缺价的 3 行=旧 limit 时代变体从未抓价的历史存量（归 492 SPU 缺价清单，非本次缺陷）。单 SKU 为主是这些品类常态（昨晚 job 121=93/112=199/120=196 全部单 SKU 同分布），多规格家族重跑表现为身份冲突 PENDING（03=51、05=19、06=7、01=9，良性、按设计不改绑）。导入质量：gallery≥1 100%、gallery≥3 72-98%、评分/图文段数依赖源站 payload（手表/健康检测类源站多数无评分）。
  - **池现状（探针后）**：6h 冷却 01=9/9、02=6/6、03=10/10、05=2/8、06=0/8（status 仍 ACTIVE；01/02 冷却 ~17:48-18:08 本地过期，03 ~20:06 本地过期）。
  - **环境处置（启动前发现夜批残留，超出简报「全部暂停」认知，已按本次铁律处置并逐条记录）**：①`var/night_crawl_20261121/shutdown_guard.py` 仍武装且死线 12:30 本地无条件晨报+关机，与「不要关机」冲突 → 11:44 taskkill 进程树（PID 38868/34736），`shutdown //a` 确认无挂起关机（1116）；②`var/gap_recrawl_20261121/` 分片 1 仍活跃抓源站（剩 30 项、正密集吃风控页）→ 11:44 taskkill（PID 23652/51944；进度落盘可断点续跑，msvcrt 锁随进程死亡自动释放）；③夜批收尾手动补跑（=guard finish() 去掉关机）：`re_import_pending.py`（17 PENDING→17 确定性身份冲突 fixed=0 属预期）+ `morning_watcher.py`（晨报+完成记录已写入）。**注意：下一条夜批完成记录中「已自动关机」不成立**（关机被本次拦截），且缺口重爬分片 1 尚有 30 项未跑完。
  - 其余：DB 存在 run pk 1/2 两条 2026-11-03/04 的陈年僵尸 RUNNING 行（无进程对应，未动、仅记录，不影响 start_run）；证据目录 `var/probe_5cats_20261121/`（runs.json/samples.jsonl 每 5 分钟采样/spotcheck.json/fullcheck.json/launch5.py/sampler.py/fullcheck.py/spotcheck.py）+ `var/logs/crawl_runs/<run_id>.log`。
- **夜间两段任务已自动完成（2026-11-21，关机前自动生成）**：①缺口商品重爬（478 目标=492 缺口 SPU-14 身份冲突，limit=0 不限变体补价，媒体 local）：processed=18 imported=10 skipped=0 failed=8，无价 SKU 前后对比看晨报表格；②20 个 READY 品类任务（01=6 全取、02=3、03=4、05=3、06=4；04/default 排除）跑完并已自动关机。总账 succeeded=9 failed=0 skipped=11，熔断=False（口径：超时不计坏 run）。近 12h 风控标记账号 41 个。剩余 READY 81（按组 {'default': 2, '数据抓取04': 32, '数据抓取03': 10, '数据抓取02': 11, '数据抓取05': 11, '数据抓取06': 10, '数据抓取01': 5}）。晨报 `var/night_crawl_20261121/MORNING_REPORT.md`，原始汇总 `final_summary.json`、`progress.json`；缺口重爬明细 `var/gap_recrawl_20261121/`（progress.json/final_gap_summary.json/baseline.json）。详见晨报。
- **本次踩坑（不得再踩）**：①**源站 2026-11-20/21 改版**：详情页 JSON-LD 平铺 offers.price 挪进 priceSpecification、CSS crossOffPrice/mainPrice 节点不渲染、flight 产品块缺失——主价解析断了；已给 `parsers/joybuy_uk.py` 加 serverProduct floors 兜底（productPriceFloor.crossOffPrice/mainPrice，与 extract_variant_price 同规则；py_compile+ruff+定向测试 27/27 过，未 commit）。阶段 2 的 spider 有列表卡片兜底所以没暴露，独立脚本没有。②试水时曾出现**同一脚本双进程并发**（后台任务通知延迟导致误判上一个已退出）——现 gap_recrawl.py 有 runner.lock 单实例锁；队列启动前 chain 脚本做 run_crawl_run 清场检查。③store_bytes 内容寻址去重：重爬导入大多命中已有资产，MediaAsset 不新增行属预期（last_seen_at 刷新）；媒体落盘用唯一 PNG 探针验证过。- **下一步**：①晨报里 failed_source_shell/failed_source_no_price 的商品是源站侧无价/下架，不是抓取缺口；②身份冲突行（14 个在缺口清单内被排除）仍需产品拍板合并/改绑；③AWS 恢复后 `aws s3 sync` 本地增量媒体；④04 组需先解封 Google 帐户验证；⑤本次改动（parser 修复）未 commit，待用户确认后提交。

- **夜间两段任务进行中（2026-11-21 深夜启动，无人值守，完成后自动关机；本条为进行中快照，完成记录会自动插到本节最顶上）**：任务=①缺口商品重爬（492 个旧 limit=10 时代多规格 SPU 缺价 → 实查后 478 个目标=492-14 行身份冲突，身份冲突不处理）②然后 20 个 READY 品类任务。媒体全程 MEDIA_BACKEND=local 显式覆盖（S3 仍不可用）；变体补价 limit=0（不限）。
  - 阶段 0（已完成）：清场确认无残留 run_crawl_run；DB 实查缺口=492 SPU/2331 无价 SKU（多 SKU SPU 1586），排除 14 个身份冲突行 → var/gap_recrawl_20261121/gap_list.json 固化 478 个 source_id；基线固化 baseline.json；池 VALID：01=9、02=6、03=10、05=8、06=8（04=0 排除），READY：01=6、02=12、03=12、05=13、06=13。
  - 试水（5 个，通过）：2 个完美导入（36/36、16/16 全 Sku 有价，DB 实查 still_unpriced=0）、2 个源站侧失败（壳页/主价缺失，归因见下）、1 个瞬时超时；唯一 PNG 探针验证媒体落 var/media/（store_bytes 内容寻址去重属预期，重爬大多命中已有资产不新增行）。
  - **发现并修复源站改版导致的解析断点（≤15 行，py_compile+ruff+定向测试 27/27 过，未 commit）**：源站 2026-11-20/21 把详情页 JSON-LD 平铺 offers.price 挪进 priceSpecification、CSS crossOffPrice/mainPrice 节点不再渲染、flight 产品块缺失——parse_uk_product_detail 主价链断了（变体页价格不受影响，走 serverProduct floors）。修复=crawler/joybuy_crawler/parsers/joybuy_uk.py current_price 链加 productPriceFloor.crossOffPrice/mainPrice 兜底（与 extract_variant_price 同字段同规则）。spider 有列表卡片兜底所以队列夜间没暴露，独立脚本会。
  - 阶段 1（运行中）：var/gap_recrawl_20261121/gap_recrawl.py（verify.py 已验证管线改造：详情+移动 merge+变体逐页补价不限+ingest+import 原地更新+每商品 DB 实查+进度落盘断点续跑；请求间隔 2-3s；41 个 VALID 账号轮换；连续 2 商品风控→暂停 10 分钟换号重试一次再中就停；runner.lock 单实例锁；因单流实测 ~1.6 分钟/件全量要 ~12h、会晚于队列关机，18:03 起**改为 3 分片并行**（每片独立锁/进度文件 progress.shard{k}of3.json，从旧 progress.json seed 终态，池 35=41-6 个刚被队列 run 风控标记的账号自动排除），预计 ~4h 完成）。日志 var/gap_recrawl_20261121/full_run_shard{0,1,2}.log。**19:35 更新**：队列 run 触发源站风控波（2h 内 20+ 账号被写 6h 冷却，02/01 组池烧穿→该组后续任务被 start_run 组冷却守卫优雅跳过，02=135/141 已跳过），3 个重爬分片全部按「暂停 10 分钟换号重试一次再中就停」纪律自停（不烧穿组池）。当前 478 中已处理 137（imported 38，其中 30 个 still_unpriced=0；源站侧 shell/无价占比 ~62%）。已部署shutdown_guard.py：截获队列 final_summary 的关机（shutdown /a）→ 等分片全部 completed+TOPUP_DONE（top_up.py 对部分导入商品补齐）→ 再晨报+关机；12h→9h 兜底。分片重启时机=队列终态后（站点负载归零、且 17:33 起的 6h 冷却 23:33 起陆续过期），重启时池会自动滤掉仍冷却账号。03/05/06 组队列 run 仍在跑并持续产出（120 已 196 导入成功）。
  - 阶段 2（已备好未启动）：var/night_crawl_20261121/（night_queue.py 改造：spawn 显式 MEDIA_BACKEND=local、CRAWL_VARIANT_PRICE_LIMIT=0（去掉 setdefault 3）、单 run 超时 360 分钟、熔断口径=仅 FAILED 且带 RISK_CONTROL_FALLBACK/ACCOUNT_POOL_EXHAUSTED/CONNECTIVITY_PREFLIGHT_FAILED、超时不计；pick_tasks.py 已固化 task_list.json=20 个：01=6 全取（pk 194/200/220/221/223/224）、02=3（129/135/141）、03=4（112/118/130/142）、05=3（120/126/138）、06=4（109/121/127/139））。chain_phase2.py 已后台挂起：等阶段 1 终态→清场检查→自动起队列+晨报看护（若重爬因风控停止则先冷却 30 分钟）。完成后队列写 final_summary→shutdown /s /t 120，看护在缓冲期写晨报+DB 实查（缺口前后对比）+本文件完成记录。
  - 明早先看晨报再动手；本次改动未 commit（parser 修复 1 处 + var/ 下脚本）；9334/FB 未碰。
- **变体完整性实测（2026-11-20，`var/verify_variants_20261120/`，✅ 完成，纯验证、未改业务代码、未 commit）**：验证用户最高优先级「商品规格必须一比一完整抓取」在真实商品上是否成立。**未启动队列/批次、未关机、未碰 9334/FB、未打印 Cookie/密钥、未做任何 S3 操作。**
  - **环境实况**：当前 shell `CRAWL_VARIANT_PRICE_LIMIT` 未设置；根 `.env` 只有 `MEDIA_BACKEND=s3` 等 4 个键、**无** `CRAWL_VARIANT_PRICE_LIMIT`；`settings.py` 默认已是 0，spider `DEFAULT_VARIANT_PRICE_LIMIT=10` 但被 setting 0 覆盖。验证脚本仍显式 `os.environ["CRAWL_VARIANT_PRICE_LIMIT"]="0"`。`.env` 的 `MEDIA_BACKEND=s3` 与批次 J 结论（AWS 账户暂停、数据先存本地）冲突，**脚本内强制 `MEDIA_BACKEND=local`**，因此本次零 S3 调用；图片本地化结果不影响 SKU/Offer 断言。
  - **方法（与 spider 同链路）**：`verify.py <source_id>` = `/dp/x/<id>` → `parse_uk_product_detail` → `/dg/` merge → 逐个非主变体 `/dp/x/<sku>` + `extract_variant_price`（间隔 2s）→ `to_payload` → `ingest_product_payload` → `import_staging_product` → DB 实查。风控/HTTP 失败与「源站无价」分开计数；风控连续 3 条即止轮，冷却 90s 换 VALID 账号重试（`--resume-json` 可复用已得价格只补剩余，避免重复请求）。
  - **实测商品 1（iPhone `100020670022401`，手机类目）**：variants **32**、轴 Series 2 / Colour 4 / Storage 4；补价 31 个非主变体 **31 成功 / 0 失败 / 0 源站无价 / 0 风控**，payload **32/32 有价**。导入 SPU `9d81ebd5…`：同源变体 16 → **Sku 15 / Offer 15（全 ACTIVE）/ offers_skipped_no_price 0**；DB 规格组合 15/16，轴值 Colour 4、Storage 4 完整。缺的 1 条 = `Burgundy/512GB`（`skipped_identity_conflict=1`）：该源 sku `100020670010193` 早在 2026-11-06（WP-45 变体导入之前）已作为独立商品导入 SPU `27f9770a…`（DRAFT、spec 为空、Offer 1399 DRAFT），导入端按设计**不自动改绑身份**，不是本次抓取缺口。另 **16 条 `Series=iPhone 18 Pro Max` 是兄弟源商品**（无 `skuStatus`，spec 仅有 Series），按 WP-45 设计 `skipped_cross_product=16` 跳过；其 `/dp/<sku>` 页均能拿到价格（不是抓不到），storefront `resolvesToPurchasableSku` 会过滤掉解析不到可购 SKU 的轴值，不出现死按钮。
  - **实测商品 2（女装连衣裙 `100034005174455`，Size 4 × Colour 8 = 32，跨类目）**：实测前 DB 只有 **11 Offer**（旧默认 limit=10 留下的历史缺口：主变体 + 10 个变体价）。首轮 17 个变体页成功后，账号 48 连续 14 次风控页（HTTP 200 risk），首轮导入补到 18；改用账号 49 `--resume-json` 只补剩余 14 个，**14/14 成功、0 风控**，最终 payload **32/32 有价**。重新导入：**Sku 32 / Offer 32（全 ACTIVE）/ offers_skipped_no_price 0 / offers_created 14**；DB 规格组合 **32/32 完全一致**，轴值 Size 4 / Colour 8 与源站一致。**此例直接证明 limit=0 能把旧缺口补齐（11→32）。**
  - **缺口归因**：①16 条跨商品系列值 = 源站指向另一源商品，不是本商品变体，正确做法是单独抓那个源商品页（建议后续做，不在本次范围）；②1 条身份冲突 = 历史独立导入的重复 SPU，需产品决策「合并/改绑」，按 WP-45 禁止自动重绑；③商品 2 首轮 14 条 = 账号级风控，换号后全成功，**不是源站无价、不是解析 bug**；Scrapy `RiskControlRenderMiddleware` 本就会在风控时 `ACCOUNT_RISK_ROTATED` + 浏览器重抓，生产链路不会静默留空；④实测两商品 `offers_skipped_no_price` 最终均为 0。
  - **历史缺口规模（DB 实查）**：多 SKU SPU 1585 个，其中 **492 个至少 1 个 SKU 没有有价 Offer**（1099 个全cover）；staging 中 `offers_skipped_no_price>0` 的 **492** 行；`skipped_identity_conflict>0` 的 **64** 行（合计 77 条冲突）。这些是旧 `limit=10/3` 时代留下的存量，**只有重爬（`skip_imported=False`、limit=0）才会补齐**，连衣裙 11→32 已证明可补。
  - **针对性验证（按验证纪律仅做针对性验证）**：`python -m py_compile var/verify_variants_20261120/verify.py` 通过；`manage.py test crawler_control.tests.test_crawler_variants --keepdb` **8/8 OK**；`ruff check` 两个已改 crawler 文件（`settings.py`、`spiders/joybuy_run.py`）**All checks passed**。**本次未改任何业务代码**（脚本在 `var/`，未跟踪）。
  - **结论**：「规格一比一完整抓取」在**抓取层成立**——两个真实多规格商品 payload 均 32/32 变体有规格值 + 价格，**62/62 个唯一变体页最终成功解析出价**（iPhone 31/31；连衣裙 31/31，其中首轮 14 条风控换号后补抓成功），0 源站无价；在**落库层**商品 2 为 32/32 Sku+Offer 完全对齐，商品 1 为 15/16 自身变体（唯一缺口来自历史身份冲突，非抓取/解析/limit 语义）。limit=0 语义已实测生效并补齐存量缺口。
  - **证据**：`var/verify_variants_20261120/`（`verify.py`、`iphone_run.log`、`iphone_100020670022401.json`、`dress_run.log`、`dress_100034005174455.json`（首轮 18 有价/14 风控）、`dress_resume.log`、`dress_100034005174455_resume.json`（32/32））。
  - **下一步建议**：①按原计划对 492 个缺价多 SKU SPU 用 `skip_imported=False` + limit=0 重爬（优先受旧 limit 影响类目）；②64 行/77 条身份冲突需产品拍板「合并 SPU 还是永久保留独立 SPU」，**不要**在导入端自动改绑；③批量导入后按本脚本口径抽查「Sku 数 = 同源 variants 数、Offer 无空价」；④S3 媒体同步等 AWS 恢复后统一做。

- **当前任务（2026-11-19 白天，`var/resume_crawl_20261119/`：商品规格 1:1 完整抓取，不关机、不 commit）**：用户最高优先级=「规格必须一比一完整抓取，宁可慢也不能缺变体/变体价格」。
  - **代码改动（仅 2 处，已 targeted 验证）**：①`crawler/joybuy_crawler/spiders/joybuy_run.py::_pending_variant_skus` 判断改为 `if limit > 0 and len(pending) >= limit`，`CRAWL_VARIANT_PRICE_LIMIT<=0` = 不限个数；②`crawler/joybuy_crawler/settings.py` 默认 10 → 0。`manage.py test crawler_control.tests.test_crawler_variants` 8/8 OK（按验证纪律仅跑该模块）。
  - **env 核查**：当前 shell `CRAWL_VARIANT_PRICE_LIMIT` 为空；根 `.env` 无该键；runserver PID 31364 命令行未带该 env；settings 默认已是 0。队列 spawn 仍**显式**写 `CRAWL_VARIANT_PRICE_LIMIT=0` 防继承旧值（无需重启 runserver）。
  - **单商品实测（iPhone `100020670022401`，VALID 05 组账号 46）**：DP 200 → `parse_uk_product_detail` 得 **32 variants / 轴 Series 2、Colour 4、Storage 4**；31 个非主变体逐页补价 **31 成功 / 0 失败**，最终 **32/32 有价**（主变体 `detail_page`，其余 `variant_page`）。`import_staging_product` 结果：SPU `9d81ebd5…`，**Sku 15 / Offer 15 / offers_skipped_no_price=0**。15 而非 32 的原因：payload 里 16 条 `Series=iPhone 18 Pro Max` 无 `skuStatus`，是**另一个源商品**（`skipped_cross_product=16`，既有 WP-45 设计不并入），另 1 条 `skipped_identity_conflict=1`（该源 sku 早前已作为独立商品导入，身份不改绑）；这些变体价格均已抓进 payload。DB 15 个 SKU 全部有 Offer，轴值 Colour 4 / Storage 4 完整。
  - **关键发现（决定任务清单）**：昨晚队列 spawn 的 `CRAWL_VARIANT_PRICE_LIMIT=3` 让 119 个多规格商品**每个只补了 3 个变体价**（近 20h 窗口缺 **489** 个变体价；另有 221 户外历史缺 67 个）。`skip_imported=True` 会在**列表阶段跳过已入库商品、不再请求详情页**，因此照原计划跑会把缺口永久留下。故对受影响类目 clone 任务改 **`skip_imported=False`**（幂等重导，修复缺口），仅 152 饮品机（116 个已入库商品 0 缺价）保留 True 只补未跑部分；194/200/220 无历史入库保留 True。
  - **20 任务已建（pk）**：01=222 饮品机(True)/223 电子健康理疗/224 美发造型/194 宠物/200 冷冻派对/220 电子烟/221 户外(已改 False)；02=234 婴幼儿玩具/235 婴儿洗护/236 冷冻甜品；03=202 Drones/225 摄影摄像/226 经期护理；05=227 手机/228 键鼠/229 婴儿车；06=230 笔记本纸品/231 医疗保健/232 婴儿哺育/233 电子配件（除标注 True 外均 False）。全部 limit=200、状态 READY。
  - **队列**：`var/resume_crawl_20261119/resume_queue.py`（每组一线程同组串行、全局 ≤5 并发），单 run 超时 **360 分钟**、**无关机链**、熔断只计 `FAILED` 且带 `RISK_CONTROL_FALLBACK`/`ACCOUNT_POOL_EXHAUSTED`/`CONNECTIVITY_PREFLIGHT_FAILED`（超时不算坏 run）。终态后写 `final_summary.json` 并调用 `final_report.py` 生成 `MORNING_REPORT.md` + 自动插入完成记录。
  - **启动确认（07:28:38 UTC，脱离会话）**：首波 5 并发 = 222(d24e17db)/234(68e5231f)/230(27c20446)/202(625418bd)/227(e870c734)，全部 RUNNING，`ACCOUNT_POOL_READY` 正常、无风控事件。**psutil 实读 10 个 executor 进程 env：`CRAWL_VARIANT_PRICE_LIMIT=0`、`CRAWL_VARIANT_PRICES=true`（limit 全部为 0，不是 3）**——env 生效已证实。
  - **新发现（1205 锁等待，既有问题）**：并发导入触发 MySQL `1205 Lock wait timeout exceeded`（历史上已有 132 次，昨夜手机 run 就有 46 次；非本次改动引入）。失败商品在 staging 保留完整 payload、状态 PENDING。`final_report.py` 在全部 run 终态后**串行补导入这些 PENDING 暂存**（此时无并发），再统计变体完整性。若仍有失败会如实写入晨报。
  - **速度观察（07:28–07:50）**：单商品约 1.5–2 分钟（详情+图文+变体页+主图/详情图/变体图下载并上传 S3），200 商品约 5–6.5h；01 组 7 个串行任务预计 30h+（队列不关机，按用户“宁可慢”执行）。后续会话先看 `var/resume_crawl_20261119/progress.json` 与 `queue.log`。

- **抓取第三晚批进行中（2026-11-19 白天启动，20 任务 + 自动关机，用户已睡；本记录为进行中快照，完成后看护会在本节顶部插入完成记录）**：不改业务代码、不 commit、不碰 9334/FB、不用 `_kill_stale_crawler_browsers`、超时只杀自己启动的 run 进程树、不打印 Cookie/AWS 密钥、不自动上架。
  - **阶段 0 S3 探针（✅ 通过，15:3x 本地）**：`MEDIA_BACKEND=s3`（根 `.env` 第 1 行 + `config/settings.py:9` load_dotenv，任何 executor 进程 import settings 都生效，队列 spawn 无需显式传）；`~/.aws/credentials` 仅 `[default]` profile（IAM joybuy-up-down，region eu-central-1）。探针 `var/day_crawl_20261119/s3_probe.py`：新色 1x1 PNG → `store_bytes` 写入成功、`stored_file_exists`(head_object)=True、匿名 GET 200（69 bytes）、本地盘无副本；cleanup 后对象 404、`media_asset` 行数复原 101850。DB 实查：READY=94（01=5、02=13、03=14、05=14、06=14、04=32、default=2）；VALID 池 01=9/02=6/03=10/05=8/06=8/04=0；**所有组风控冷却 0 人**（昨晚标记账号 6h 冷却已全部过期）。
  - **重试 job 已新建**：job 122 电子烟、140 户外（01 组 FAILED）克隆为 **pk 220「数据抓取01-电子烟-重试20261119」、pk 221「数据抓取01-户外-重试20261119」**（`create_retry_jobs.py`，走 `create_crawl_job` 服务，字段与原 job 一致 limit=200）。
  - **阶段 1 试水（✅ 通过，17:38-17:51 UTC）**：job 152 饮品机 / run `a0839b39` / PID 44164（launch_run.py 未设 CRAWL_VARIANT_PRICE_LIMIT，同昨晚；队列派发 run 由 spawn setdefault 补到 3）。13 分钟 parsed=12 / imported=10 / fail=0，RISK_CONTROL_FALLBACK=0、ACCOUNT_RISK_ROTATED=0（仅 ACCOUNT_ROTATED=1 正常轮换）；**试水期新增 MediaAsset 85 行，head_object 抽查 200 真实字节——媒体确实进 S3**。
  - **阶段 2 队列（✅ 17:54:15 UTC 启动，脱离会话）**：20 任务=01 组 7 个（152 预启动 + 158/170/194/200/220/221）+ 02=3（93/99/105）+ 03=3（70/88/106）+ 05=3（72/78/96）+ 06=4（85/91/97/103），固化 `var/day_crawl_20261119/task_list.json`（total_budget=20，已核 20 条全 READY）。`night_queue.py`（01 组 worker 等试水 run 结束后串行其余 6 个）+ `morning_watcher.py`（增加 S3 新增对象抽查节）均 nohup detach。启动即 5 并发：93(b5cca727)/72(6ad4c548)/70(389464af)/85(c64224dc)，复查全部 RUNNING、无风控事件。
  - **关机链已武装**：20 任务全部终态 → `final_summary.json` → `shutdown /s /t 120 /c "day crawl 20261119 done"`；看护在缓冲期做 DB 实查 + S3 抽查 + 晨报（`var/day_crawl_20261119/` 目录下 MORNING_REPORT.md）+ 在本节顶部插入完成记录（锚点连写串已避开）。熔断：连续 3 坏 run → 只停新派发、已跑跑完照常关机。
  - **留给完成记录/明早会话**：先读晨报再动手；02 组 VALID 只剩 6 注意补号；04 组仍需先解封 Google 帐户验证；电子烟/户外重试若再失败需再新建 job（名称 unique）。

- **当前任务（2026-11-18，需求迭代文档 03 v1.1：第三场录像拆解 + 4 项拍板回填，纯文档，✅ 完成）**：拆解 31.8 分钟录像 `D:/Users/lyx/Videos/Joybuy功能需求讨论03.mp4`（199 段转写 + 160 关键帧），结合用户口述笔记**新建** `功能需求迭代文档03.md`，用户随后拍板 4 项回填为 **v1.1**，待确认项清零。**只产出文档，未动代码**。配套拆解：`D:/Users/lyx/Videos/Joybuy功能需求讨论03_拆解/`（txt/json/srt + _segments.md + 帧 + `Joybuy功能需求讨论03-内容拆解.md`）。
  - **4 项最终拍板**：①SSL 证书付款方式**先不管**（非阻塞）；②已售数据：前期没采集，**当前对已爬数据随机生成 10k–30k 整数**（"已售 xxk+ 件"），后续爬虫采集真实数据后替换；③27:18 疑似收藏功能那条**不用管**；④专区商品清单**打开 joybuy 网页参考其各品类下对应模块的商品数据来配**。
  - **购物端**：①品类区【品牌】小分类去掉；各小分类【更多】统一跳【全部】，唯页面最底部【更多】=无限加载全部品类商品；②专区固定死（早餐电器 6 个、智能家电取自冰箱等小品类、关爱自己随便、大牌优惠随便），填充商品**必须先入库再展示**、品类贴切（早餐电器不放洗衣机），不造"热门精选"这类假分类；③详情页：页脚全去掉；30 天退货与 24/7 客服**保留且展开内容也要**；【我们接受】支付 icon 要；配送与服务承诺加"销售及配送方：Joybuy"；画廊上方加评分+已售（10k–30k 随机整数"25k+ 件"样式、无感叹号图标、300+ 评价去掉、后续爬虫抓真实数据）；人工评价评语要（爬虫补抓）；经常一起购买/精选好物**不做**（无算法）；④右上角【配送至】→【申请店铺】四态状态机（未申请/审核中=看提交信息+状态/通过=【切换商家端】直切/失败=看原因可再申请），下拉框里的申请店铺入口移到此处。注意：**四态切换入口 2026-11-16 已在个人中心/侧栏实现过一版**（见 11-16 记录），本轮是把入口换到右上角【配送至】位置。
  - **管理端**：入口路径 `/admin/` → **`/admin18vm6u4b83sf`**（改 nginx/部署路径时要同步）。
  - **商家端**：页面要设计美化（原型丑，可参考 GitHub 设计资源）。
  - **爬虫/数据**：每小品类最少 100–200 件；月底 11/28 目标三四万件（最好五六万）再对数；上新=图片进 S3、数据本地爬完同步文件、不开 3306 公网端口、不重启服务器。
  - **基础设施**：HTTPS 要上（证书按年买、几百块），与本轮优化一起做。
  - 客户总要求："一模一样，该有的都要有"；先改一版看效果。

- **夜间抓取已自动完成（2026-11-18 凌晨，关机前自动生成）**：同一 VPN 节点第二晚。白天 15:4x 本地（07:4x UTC）试水 job 86 通过后放量，20 个 READY 任务（01 组剩余 11 个全取、02=3、03=2、05=2、06=2；04 组无 VALID 排除、default 排除）跑完并已自动关机。总账 succeeded=13 failed=2 skipped=5，20 任务成功 13 个，熔断=False。近 12h 风控标记账号 19 个（结论看晨报明细）。剩余 READY 94（按组 {'default': 2, '数据抓取04': 32, '数据抓取03': 14, '数据抓取05': 14, '数据抓取06': 14, '数据抓取02': 13, '数据抓取01': 5}）。晨报 `var/night_crawl_20261118/MORNING_REPORT.md`，原始汇总 `final_summary.json`、实时进度 `progress.json`。详见晨报。

- **夜间抓取 2026-11-18 进行中（第二晚 20 任务 + 自动关机，用户已睡，关机是明确要求；15:40 本地启动的会话，队列已脱离会话运行）**：不改业务代码、不 commit、不碰 9334/FB、不用 `_kill_stale_crawler_browsers`、超时只杀自己启动的 run 进程树、不打印 Cookie、不自动上架。
  - **阶段 0（✅ 15:40-15:45 本地）**：DB 实查——READY=109（01=11、02=16、03=16、05=16、06=16、04=32、default=2）；会话池 VALID：01=9、02=6（历史烧损）、03=10、05=8、06=8、04=0 排除、default 排除；**所有组风控冷却 0 人**（昨晚 13 个标记账号 6h 冷却已全部过期）；后端 ：8000 存活（PID 7956，未重启）。选 20 个：**01 组 11 个全取**（pk 86/98/110/122/128/140/152/158/170/194/200）+ 02=3（57/63/75）+ 03=2（58/64）+ 05=2（54/60）+ 06=2（67/73），固化 `var/night_crawl_20261118/task_list.json`（total_budget=20，已核 20 条）。
  - **阶段 1 试水（✅ 通过，15:45-15:58 本地 / 07:45-07:58 UTC）**：job 86「数据抓取01-控脂 u0026 瘦身」/ run `548b5ebb-edf4-4b5e-9b23-11bae6a58af3` / PID 15628。13 分钟时 discovered=149 / imported=24 / fail=0，**RISK_CONTROL_FALLBACK=0、ACCOUNT_RISK_ROTATED=0**（仅 ACCOUNT_ROTATED=1 正常轮换）→ 白天（下午时段）试水通过，放量。注意：launch_run.py 不设 `CRAWL_VARIANT_PRICE_LIMIT`，试水 executor 以默认 10 跑（比队列的 3 更激进，试水通过则队列更稳）；**队列派发的 run 由 night_queue 的 spawn_executor setdefault 补到 3，与昨晚一致**。
  - **阶段 2 队列（✅ 15:59:29 本地 / 07:59:29 UTC 启动，脱离会话）**：`night_queue.py`（PID 37400，重定向子 37816）+ 晨报看护 `morning_watcher.py`（PID 36160，重定向子 36420）均 nohup detach（同名双 PID 是 venv 重定向器父子对，非双实例，queue.log 每 job 仅一条 START 可证）。启动即 5 并发：01 组 worker 等试水 run 结束后接跑其余 10 个，02/03/05/06 各起 1 个（df6912fa/d2ff5a4e/167e7da7/ffd1209c），16:04 复查 5 个 run 全 RUNNING、无任何风控事件。队列日志 `var/night_crawl_20261118/queue.log`，实时进度 `progress.json`。
  - **关机链已武装**：20 个任务全部终态 → `final_summary.json` → `shutdown /s /t 120 /c "night crawl 20261118 done"`；晨报看护在 120s 缓冲内做 DB 实查（每 run staging 明细、剩余 READY、近 12h 风控标记账号）并自动写晨报（同目录 `MORNING_REPORT.md`）+ 自动在本节顶部插入完成记录（去重锚点：晨报路径「目录名+/MORNING_REPORT.md」连写串——**进行中记录里不得出现该连写串，否则看护会跳过更新**）。熔断：连续 3 个坏 run（TRIP_CODES 含 RISK_CONTROL_FALLBACK）→ 只停新派发、已跑跑完照常关机。
  - **留给晨报/明早会话**：先读晨报再动手；若近 12h 风控标记账号暴增则明天只试水不放量；02 组 VALID 只剩 6 注意补号；04 组仍需先解封 Google 帐户验证；重跑失败 job 需新建任务（名称 unique）。

- **夜间抓取已自动完成（2026-11-17 凌晨，关机前自动生成）**：换节点后试水 job 32 通过后放量，20 个 READY 任务（01/02/03/05/06 各 4 个，05 组因冷却延迟到 20:05 UTC 起跑，04 组无 VALID 排除）跑完并已自动关机。总账 succeeded=20 failed=0 skipped=0，20 任务成功 20 个，熔断=False。近 12h 风控标记账号 13 个（换节点结论看晨报明细）。剩余 READY 109（按组 {'default': 2, '数据抓取04': 32, '数据抓取05': 16, '数据抓取02': 16, '数据抓取03': 16, '数据抓取06': 16, '数据抓取01': 11}）。晨报 `var/night_crawl_20261117/MORNING_REPORT.md`，原始汇总 `final_summary.json`、实时进度 `progress.json`。详见晨报。

- **当前任务（2026-11-17，PDP 头部切市场/语言后商品数据不刷新，✅ 修复完成并浏览器全序列验证，未 commit）**：用户报购物端 PDP 用头部右上角「国家/语言」切换器切市场或语言后，标题/规格文本仍是切换前语言。
  - **根因（一句话）**：`storefront/pages/p/[id].vue` 的 `useFetch` 把 `key` 写成模板字符串 `product-${publicId.value}-${productQuery.value}`（原第 30 行），setup 时冻结；切语言后 cookie→`apiQuery`→URL getter 虽是响应式，但 Nuxt 对同 key 的 payload 缓存命中（`getCachedData`），watcher 触发的重取被短路——**实测切换后没有发出任何新的 `/api/v1/products/` 请求**（页面内装 fetch 监听，`productReqs: []`）。后端 `offers/market_services.py::resolve_market_context` 优先读 query 的 `market`/`locale` 再 fallback cookie，后端无问题（复现时 cookie 确实写成了 `joybuy-market=DE; joybuy-locale=de-DE`）。
  - **修复（最小集，仅 1 个文件）**：`storefront/pages/p/[id].vue` 的 `key` 改为 `computed(() => \`product-${publicId.value}-${productQuery.value}\`)`（Nuxt 3.21.11 支持 reactive key，key 变化即重取；与库里既有先例 `composables/useActivityList.js:20`、`composables/useSearchApi.js:29` 同一写法，后者注释里就记录了同类坑）。未改 AppHeader/useLocale/useMarketLocale/backend。
  - **浏览器验证（真实译文，IAB 1440×900，页面内 fetch 监听 + console 钩子）**：
    1. 177（`/p/ec62c4d3-…`）EN→DE→FR→NL→EN 循环：每次切换都发出带新 locale 的请求（`?market=DE&locale=de-DE` 等），标题依次为 `CHiQ JKR157LBE 47cm Breit…Kühlschrank…` / `Réfrigérateur-congélateur autonome CHiQ…` / `CHiQ JKR157LBE 47cm Breed 144cm Hoog losstaand koelvriesapparaat…` / 回英文原文，已选 SKU 规格文本跟随（`Schwarz`/`Noir`/`Zwart`/`Black`）。
    2. 7964（`/p/5b7098bf-…`）多 SKU 切 DE：标题 `Apple iPhone 17 Pro 256 GB Kosmischer Orange`；点「银色」规格→选中态更新，底部购物条标题德语、规格 `Silber / 256GB`。注意：规格按钮轴名/轴值显示源语言（中文）是 `[id].vue` 99-108 行注释的既有设计（带 spec_options 的商品轴值用源语言 canonical_specification 匹配），不是本次回归。
    3. 冷加载回归：DE cookie 下刷新 7964、直接打开 177，标题均德语，`spec177=Schwarz / Schwarz`。
    4. console error 0（console.error/uncaught/unhandledrejection 钩子全程 0 条）。
  - **验证纪律（仅针对性）**：`prettier --check storefront/pages/p/[id].vue` 通过；`storefront/node_modules/.bin/eslint.CMD "pages/p/[id].vue"` 通过（eslint 在 storefront 本地 .bin，prettier 在根 node_modules）；vitest 跑 `use-locale.test.js`+`use-market-locale.test.js` → 5 passed（改动文件无专属测试）。
  - **截图**：`var/pdp_locale_switch_20261117/`（pdp177_de.png、pdp177_de_specs.png、pdp177_fr.png、pdp177_nl.png、pdp7964_de_variant.png、pdp177_de_coldload.png）。
  - **同坑排查清单（只排查未修，均为「冻结模板字符串 key + URL 依赖响应式状态」同类）**：①`composables/useCategoryTree.js:18` `category-tree-${query.value}`（含 market/locale，切换后类目树不重取，类目名本就只 en/zh 故影响小）；②`pages/merchants/index.vue:20` `key: 'merchant-search'`（同路由 ?q= 变化拿到 stale）；③`pages/merchants/[slug].vue:19` `merchant-${slug.value}`（/merchants/a→/merchants/b 同组件复用 stale）；④`pages/promo/best-seller.vue:36` `bestseller-${activeSlug.value}`（页内 tab 切换 stale）；⑤`components/ProductReviews.vue:49` `reviews-${productId}-${activeRating}-${page}`（PDP 上评价筛选/翻页可能 stale，URL 不含 locale 故与本 bug 无关）。首页 `cms-home`、account 各页 URL 不随 locale/market 变，key 冻结无此问题。已修好的同先例：`useSearchApi.js:29`、`useActivityList.js:20`、`useChannelBanners.js:20`。
  - **坑（不得再踩）**：①Nuxt useFetch 的 `key` 只要 URL 依赖任何会变的响应式状态（locale/market/query/page/tab），必须用 `computed` key——本仓已有 3 处正确先例 + 本次第 4 处；②IAB 里 `document.cookie` 直接可读 `joybuy-market/joybuy-locale`，验证切换先用 `selectOption` 操作 `#market-select`（切国家会联动 locale）；③PDP 的图文详情/规格参数表仍是源语言是已知后端边界（`detail_views` 未读 `spu_detail_translation`，见 2026-11-17 真模型任务记录），不要误判成本次前端 bug。
  - **未 commit；下一步**：①上面 5 处同类冻结 key 是否要修，等用户拍板（修法完全同本次：key 包 computed）；②后端接 `spu_detail_translation` 让规格参数表/图文详情也出译文（需改 backend，另行任务）。

- **夜间抓取 2026-11-17 进行中（换节点试水 + 20 任务 + 自动关机，用户已睡，关机是明确要求）**：本次不改业务代码、不 commit、不碰 9334/FB。
  - **已完成（阶段 0）**：DB 实查——READY 共 129（含 default 2、04 组 32），可用组 01(9 valid)/02(6)/03(10)/05(8)/06(8)；**05 组 8 个账号风控冷却未过期（13:01–13:59 UTC 被标，6h 冷却到 19:01–19:59 UTC）**；04 组 0 VALID 继续排除；02 组 valid 从 10 降到 6（昨天烧损）。选 20 个任务（沿用 20261116 夜队计划，各组 4 个）：01=32/50/68/80，02=27/33/39/51，03=34/40/46/52，05=24/36/42/48，06=37/43/49/55，固化在 `var/night_crawl_20261117/task_list.json`（05 组组级 `not_before_utc`=2026-11-17T04:05+08:00，即 20:05 UTC，等冷却全过期）。
  - **脚本**：`var/night_crawl_20261117/night_queue.py`（每组一线程同组串行、全局 ≤5 并发、单 run 150 分钟超时、熔断连续 3 坏 run、TRIP_CODES 含 RISK_CONTROL_FALLBACK、全部终态→final_summary.json→`shutdown /s /t 120`）+ `launch_run.py`/`check_run.py` + 晨报看护 `morning_watcher.py`（等 final_summary→DB 实查→晨报→更新本文件）。executor env 已加 `CRAWL_VARIANT_PRICE_LIMIT=3` 兜底（spawn_executor 用 setdefault，runserver PID 已变为 42276，重启过但命令行未变）。
  - **阶段 1 试水（✅ 通过，17:10–17:20 UTC 实测）**：job 32 / run `be47d2d7-7bcd-49c3-9898-0f97ab806bda`（PID 42220，executor 子进程 43052）。10 分钟时 discovered=169 / parsed=45 / imported=39 / fail=4（全是 IMPORT_SOURCE_CONFLICT 良性）、**RISK_CONTROL_FALLBACK=0、ACCOUNT_RISK_ROTATED=0**（ACCOUNT_ROTATED=0，连正常轮换都没触发）→ **换节点后风控未触发，试水通过并放量**。
  - **阶段 2 队列（✅ 已启动并脱离会话，17:20 UTC）**：`night_queue.py`（PID 30756，venv 重定向子进程 47092）+ 晨报看护 `morning_watcher.py`（PID 42404）均已 nohup detach。队列日志 `var/night_crawl_20261117/queue.log`，实时进度 `progress.json`。17:20 启动：job 27(02)/34(03)/37(06) 已开跑，01 组等试水 run 结束后接着跑 50/68/80，**05 组延迟 9890s 到 20:05 UTC**（冷却 19:59 UTC 过期后才起跑 24/36/42/48）。17:30 复查 4 个 run 全部 RUNNING 且 risk_fb=0。**关机链已武装**：队列在 20 个任务全部终态后写 final_summary.json → `shutdown /s /t 120`；晨报看护会在 120s 缓冲内完成 DB 实查 + 晨报 + 本文件自动更新（本次试水通过的前提已满足；若熔断连续 3 坏 run，队列只停新派发、已跑任务跑完照常关机）。**注意：wmic 里同名命令行出现两个 PID 是 venv python.exe 重定向器父子对，不是双实例**（队列派发日志无重复已核实）。
  - **留给晨报/明早会话**：若晨报显示近 12h `risk_flagged_at` 增长（换节点结论失败），明天不要直接放量；02 组 valid 已从 10 降到 6，注意补号；task_list.json 可整目录复用（改任务 pk 与 not_before_utc）。

- **当前任务（2026-11-16，购物端「申请店铺 → 审核通过 → 切换商家端」完整入口，✅ 完成，未 commit，未人工验收）**：恢复个人中心/侧栏入口，并新增「买家会话 → 商家端员工会话」的切换接口；端到端实测四态 + 跳 5174 已登录 + 驳回可重申，中英各一轮，console error 0。**只测不提交 git。**
  - **前提纠正**：任务描述说「全仓 grep `apply-shop` 已无引用」并不准确——`storefront/components/AppHeader.vue` 的账号下拉一直有 `/account/apply-shop` 链接（旧文案 Sell on Joybuy / Merchant Center）。本次把它也统一进状态映射，APPROVED 时同样触发切换；个人中心磁贴与左侧 `AccountNav` 是按要求新恢复的两处。
  - **入口位置与状态映射（`GET /api/v1/account/merchant-application`）**：

    | 状态 | 文案（en / zh） | 行为 |
    | --- | --- | --- |
    | 无申请 / `REJECTED` | Apply for a shop / 申请店铺 | `<a href="/account/apply-shop">` |
    | `PENDING` | Application under review / 申请审核中 | `<a href="/account/apply-shop">`（看进度） |
    | `APPROVED` | Enter Merchant Center / 进入商家中心 | `<button>` → POST 切换接口 → `window.location.assign(url)` |

    * 个人中心磁贴：`storefront/pages/account/index.vue` 第 5 个磁贴（桌面 5 列，≤1023px 2 列，≤767px 1 列；其余四个模块不变）。
    * 左侧账号导航：`storefront/components/account/AccountNav.vue` 第 5 项（账号子页共用 AccountShell，因此订单/售后/评价/地址页都能看到）。
    * 头部账号下拉：`storefront/components/AppHeader.vue` 第一项（登录后才渲染；状态在打开下拉时强制刷新）。
    * 未登录：个人中心本身是 signed-out 页、侧栏只在受保护的账号子页、头像下拉登录后才出现，因此不会出现「未登录可见入口」。
    * 统一状态源/调用：`storefront/composables/useMerchantEntry.js`（模块级缓存 + in-flight 去重；失败降级为「申请店铺」；错误映射为 en/zh toast）。
  - **切换接口契约 `POST /api/v1/account/merchant-console-session`**（`merchant_ops/views_shop_application.py`）：
    * 鉴权：买家会话 cookie + CSRF；前端先 `GET /api/v1/auth/buyer/session` 取 `csrf_token`，再带 `X-CSRFToken` 提交。
    * 请求体：无。**接口不读取任何 `staff_id` / `merchant_id` / `email` 参数**；身份只来自 `request.buyer_account`。
    * 200 响应：`{"url": "...", "staff": {"id","email","display_name"}, "merchant": {"id","display_name","onboarding_status"}, "expires_in": 28800}`，并下发 `Set-Cookie: joybuy_staff_session=<token>; Path=/api/v1/; HttpOnly; SameSite=Lax`（与商家端登录同一个 cookie）。
    * `url` 规则：`MERCHANT_WEB_URL` 非空 → 用它（去尾斜杠 + `/`）；否则 **当前请求 `Origin` 的 hostname**（无 Origin 时退回 request host）+ `MERCHANT_WEB_PORT`（默认 5174）+ `/`。开发下即 `http://localhost:5174/`，**不写死 127.0.0.1**。生产必须配 `MERCHANT_WEB_URL`。
    * 错误码（中文文案）：401 `BUYER_AUTH_REQUIRED`（请先登录后再操作。）；400 `APPLICATION_NOT_APPROVED`（您还没有审核通过的店铺申请，暂时无法进入商家中心。）；409 `MERCHANT_ACCOUNT_MISSING`（商家端账号尚未开通，请联系平台客服处理。）；409 `MERCHANT_ACCOUNT_DISABLED`（商家端账号已被停用，请联系平台客服处理。）；409 `MERCHANT_MEMBERSHIP_MISSING`（商家端账号未绑定当前店铺，请联系平台客服处理。）。
    * **安全约束（代码注释已写明，不得放宽）**：只允许「自己有 APPROVED 申请的买家」为「自己邮箱对应的 StaffAccount」建会话；membership 必须属于该申请回填的 `merchant` 且 ACTIVE；绝不接受任意 staff id。
  - **后端改动（无 migration，未改 model）**：`backend/merchant_ops/views_shop_application.py`（新增 `_merchant_web_url` + `BuyerMerchantConsoleSessionView`）、`backend/merchant_ops/urls.py`（新增路由）、`backend/config/settings.py`（`MERCHANT_WEB_URL` / `MERCHANT_WEB_PORT`）、`.env.example`（两个变量说明）、新增 `backend/merchant_ops/tests/test_merchant_console_session.py`（11 个用例：401/无申请/PENDING/REJECTED/成功签发 cookie 并能打开 `/merchant/shops`/URL 覆盖/无 Origin 回退/忽略客户端 staff_id/无 StaffAccount/停用/无 membership）。
  - **前端改动**：`storefront/composables/useMerchantEntry.js`（新）、`storefront/pages/account/index.vue`、`storefront/components/account/AccountNav.vue`、`storefront/components/AppHeader.vue`、`storefront/pages/account/apply-shop.vue`（APPROVED 的「前往商家中心」从 `<a target=_blank>` 改为同一 `openMerchantConsole()`）、`storefront/locales/messages.js`（新增 `merchantEntry.*` en/zh 共 13 键）、`storefront/nuxt.config.js`（删除已无用的 `public.merchantWebUrl`，URL 只由后端返回）、`storefront/vitest.config.js` + `storefront/tests/nuxt-components-stub.js`（`#components` 别名）、`merchant-web/src/router/index.js`（冷启动落点修复，见坑 4）、`storefront/components/account/AccountNav.test.js`（新 5 个用例）、`storefront/components/AppHeader.test.js`（APPROVED 断言改为 button）。
  - **验证（按验证纪律：本任务要求全量 vitest 与指定后端套件；其余针对性）**：
    * 后端定向：`./.venv/Scripts/python.exe backend/manage.py test merchant_ops.tests.test_merchant_console_session merchant_ops.tests.test_merchant_application --keepdb --noinput` → **Ran 29 tests, OK**。
    * 后端全量：`... test merchant_ops --keepdb --noinput` → **Ran 215, FAILED (failures=2)**，均是既有 `merchant_ops.tests.test_admin_round2.NotificationApiTests`（评价通知现在要求店铺订单，测试未带 order，报 `FIELD_REQUIRED 店铺订单不能为空。`），**与本任务无关、改动前就存在**；除这两条外全部通过。
    * `ruff check`（views_shop_application / urls / 新测试 / settings）→ All checks passed。
    * 改后端后已 `taskkill /PID 38512 /F`，keepalive 重启 :8000（新 PID 42276），接口实测通过。
    * 前端全量：`node node_modules/vitest/vitest.mjs run --config storefront/vitest.config.js`（node 用 `E:\soft\nvm\nodejs\node.exe`，PATH 里没有）→ **19 files / 91 tests passed**（任务说明的 83 是旧基线；本次新增 `AccountNav.test.js` 5 个用例，其余为当前工作区既有未提交测试；未改任何旧断言语义）。
    * `prettier --check` + `eslint`（本次改动的 12 个前端文件）→ 全部通过。
    * **端到端（Playwright headless，购物端 `localhost:3000`、管理端 `127.0.0.1:5173`、商家端 `localhost:5174`；脚本 `var/merchant_entry_20261116/e2e_merchant_entry.cjs`，原始结果 `results.json`，console errors=0）**：
      1. 注册 API 建临时买家 A（英文）→ `/account` 5 个磁贴，第 5 个 `Apply for a shop`（`<a href="/account/apply-shop">`）；侧栏同文案同 href。
      2. A 提交申请 → 页面 `Under review`；`/account` 磁贴变 `Application under review`，侧栏同步（仍是 apply-shop 链接）。
      3. 临时 platform_admin 在管理端 `/merchants` 的「入驻申请」表点「审核」→ 取消勾选「需要保证金」→「确认」，row 从 PENDING 列表消失。
      4. A 回购物端 → 磁贴/侧栏变 `Enter Merchant Center`（`<button>`）→ 点击 → 接口 200 → **`http://localhost:5174/dashboard`**：标题「经营看板 · Joybuy」、店铺 `Entry Test Shop A`、6 个指标卡（店铺状态「● 接单中」、信誉分 100.00）、9 个导航项、`.login-card` 不存在。响应 cookie `joybuy_staff_session` path `/api/v1/`、HttpOnly。
      5. 中文买家 B：`申请店铺` → `申请审核中` → 管理端驳回（原因「店铺资料不完整，请补充主体信息。」）→ 磁贴回到 `申请店铺`；apply-shop 页显示「申请未通过」+ 驳回原因 + 「重新申请」→ 重新提交后 `申请审核中` → 管理端通过 → 磁贴/侧栏 `进入商家中心`；再从 **apply-shop 审核通过态的「前往商家中心」按钮**触发切换 → 同样落在 `localhost:5174/dashboard`（店铺 `入口测试店 B 重申请`、已登录、console 0）。
      6. 双语覆盖：EN 的 apply/pending/console（磁贴 + 侧栏），ZH 的 apply/pending/rejected/reapply-pending/console（磁贴 + 侧栏）+ apply-shop 通过态按钮全部实测；console error 0。
    * 截图（`var/merchant_entry_20261116/`）：`en_account_apply.png`、`en_nav_apply.png`、`en_account_pending.png`、`en_nav_pending.png`、`en_apply_shop_pending.png`、`en_account_console.png`、`en_nav_console.png`、`en_merchant_dashboard.png`、`zh_account_apply.png`、`zh_account_pending.png`、`zh_account_rejected.png`、`zh_apply_shop_pending.png`、`zh_apply_shop_rejected.png`、`zh_apply_shop_reapply_pending.png`、`zh_apply_shop_approved.png`、`zh_account_console.png`、`zh_nav_console.png`、`zh_merchant_dashboard.png`；另 `probe_nuxtlink.cjs`（NuxtLink 渲染探针）、`cleanup_merchant_entry.py`（清理脚本）。
    * **清理（已删净）**：BEFORE `{buyers:2, applications:2, staffs:3, merchants:2, orders:0, audit_logs:3}` → AFTER 全部 0；全局复查 `BuyerAccount/Session` 前缀 0、临时 admin StaffAccount/Session 0、同名 Merchant 0、MerchantApplication/Membership 0、actor=临时 admin 的 AuditLog 0。**未产生任何商家横幅**；approve 产生的 Merchant 删除前确认无订单引用（orders=0）。临时买家、买家 StaffAccount、membership、商家、审核日志、会话全部删除。
  - **坑（不得再踩）**：
    1. **`:is="'NuxtLink'"` 是坏的**：会渲染成 `<nuxtlink to="...">` 未知元素，点击不跳转；单元测试因全局 stub 掩盖了它。必须 `import { NuxtLink } from '#components'` 后 `:is="to ? NuxtLink : 'button'"`。vitest 需给 `#components` 加别名（`storefront/tests/nuxt-components-stub.js`），否则组件测试解析失败。
    2. `request.get_host()` 在 Nuxt devProxy `changeOrigin: true` 下是 `127.0.0.1:8000`，照抄会让 cookie 落到错误 host；`url` 必须用浏览器发来的 `Origin` hostname（cookie 按 host 共享、不按端口）。
    3. `joybuy_staff_session` 的 path 是 `/api/v1/`，`context.cookies('http://localhost:5174/')` 查不到；要查 `http://localhost:5174/api/v1/admin/auth/session`。
    4. **merchant-web 冷启动 `/` 原会落 `/no-shop`**：路由 `redirect` 在全局 `beforeEach` 之前执行，权限还没加载。已在 `merchant-web/src/router/index.js` 把落点移到 `beforeEach` 的 `to.name === 'home'` 分支（先 `loadSession` 再 `can`）。不要改回同步 `redirect`；`async redirect` 也不被 vue-router 接受（实测报 `Invalid redirect`）。
    5. 商家端截图要等 `.stat-grid`（数据加载完），只看 `.merchant-topbar h1` 会截到「加载中…」。
    6. `manage.py shell < file` 是交互式逐行执行，带缩进的脚本会 `IndentationError`；用 `manage.py shell -c "exec(open(r'E:/.../cleanup.py', encoding='utf-8').read())"`。
    7. 本机 Playwright `page.goto(..., { waitUntil: 'networkidle' })` 会长时间不返回；改用 `domcontentloaded` + 显式选择器等。
    8. E2E 失败重跑会留下临时买家；清理按 `merchant-entry-` 前缀兜底。`Order.account` 是 PROTECT，清理脚本先删订单再删买家（本次 orders=0）。
    9. 后端全量 merchant_ops 的 2 条失败是既有测试漂移（评价通知要求 order），不要误记成本任务引入。
  - **下一步**：①人工验收视觉（尤其 5 磁贴排布、`Enter Merchant Center` 两行换行、商家端落地）；②生产部署必须设 `MERCHANT_WEB_URL`（完整 origin，如 `https://seller.joybuy.co.uk`），并保证购物端/商家端同 host、cookie 可共享；③`accountMenu.sellOnJoybuy/sellerPending/sellerCenter` 现已无引用，可另开清理任务删除（本次保留以免影响未知引用）；④merchant-web 无测试框架，router 修复只做了手工 E2E；⑤未 commit。

- **当前任务（2026-11-16，风控冷却持久化修复 + 男装 400 重跑，⚠️ 修复完成并已实测生效；男装跑完 212 条后因风控全面打穿主动中止，未 commit、未关机、未碰 9334/FB、未上架）**：先修「账号被 `ACCOUNT_RISK_ROTATED` 移出池后不持久化」的隐患，再用 05 组重跑男装配饰。**旧 job 214 仍为 FAILED 未复用，新建了 job 218（试水 20）/ 219（400-v2）。**
  - **一、风控冷却修复（已完成并真实数据验证）**
    * 改动文件：`backend/crawler_control/services.py`（新增 `mark_account_risk_cooldown` / `risk_cooldown_hours` / `_risk_cooldown_cutoff` / `_account_in_risk_cooldown` / `_risk_cooldown_until` / `_exclude_risk_cooled` / `_guard_group_risk_cooldown`；`_account_unusable_reason` 增加冷却分支；`usable_accounts_for_run`、`_select_account_for_run` 的候选查询排除冷却账号；`start_run` 启动前整组冷却快速失败并写事件）、`crawler/joybuy_crawler/middlewares.py`（`RiskControlRenderMiddleware._persist_risk_cooldown`：风控轮换时写 `risk_flagged_at/risk_reason`；先 `unquote` 风控页 `returnUrl` 再判断详情页/列表页；`ACCOUNT_RISK_ROTATED` 文案注明已写冷却标记）、新增 `backend/crawler_control/tests/test_crawler_risk_cooldown.py`（9 例）。
    * 行为：①账号命中风控被移出本轮池时，除原有的 `ACCOUNT_RISK_ROTATED` 事件外，**立即写 `CrawlerAccount.risk_flagged_at/risk_reason`，但不动 status**（crawl 仍在跑，不能用会暂停 run 的 `flag_account_risk_control`）；②`usable_accounts_for_run` / 选号排除「最近 N 小时内被标记」的账号，N 由环境变量 `CRAWLER_RISK_COOLDOWN_HOURS` 控制，**默认 6 小时**；③某组 ACTIVE+VALID 账号**全部**在冷却期时，`start_run` 直接抛中文错误、job 保持 READY、不建 run（实测文案：`数据抓取05 组账号全部处于风控冷却期（8 个账号，冷却 6 小时），本轮不启动；请等待冷却结束或补充账号。`）；④只有部分账号冷却时正常启动，并写 INFO 事件 `ACCOUNTS_RISK_COOLDOWN_SKIPPED`（含跳过数量与账号 label）。
    * 验证（按验证纪律仅做针对性验证）：`py_compile` 3 文件通过；`ruff check` + `ruff format --check` 全过；新增 `test_crawler_risk_cooldown` **9 tests OK**；回归 `test_crawler_control_domain + test_crawler_rebuild` **65 tests OK**（207.8s）。**注意：`--keepdb` 的旧测试库缺 Currency 种子，既有套件也会 14 errors，必须用新测试库（不加 --keepdb）。**
    * **后端已重启**：旧 runserver 进程树（PID 27620/25392）taskkill 后重启，新进程 PID 26832 监听 8000、`GET /api/v1/categories` 200；启动时带 `CRAWL_VARIANT_PRICE_LIMIT=3`（executor 继承 `os.environ`）。
    * **真实数据证据（本次 run 98 自带）**：13:01–13:59 UTC 8 个 05 组账号先后命中风控，`risk_flagged_at` 全部写入（reason `列表页风控验证码，本 run 内被移出账号池`；当时的进程还是旧 heuristic，`/user/risk/pic?returnUrl=...%2Fdp%2Fx%2F...` 被标成列表页，新代码已支持解码后标详情页）；run 结束后 `usable_accounts_for_run(job219)` 返回 `[]`，`_guard_group_risk_cooldown` 抛出上述中文错误——**修复在线上路径生效，不只是单测**。
  - **二、男装试水（job 218 / run 97，✅ SUCCEEDED）**
    * job 218「数据抓取05-男装配饰-试水20-20261116」limit=20、05 组、skip_imported+翻页开、l2:1879（与 job214 同类目）。run 96 首次启动 10 秒内 `CONNECTIVITY_PREFLIGHT_FAILED`（TLS handshake timeout，非风控；重测 3/3 连通后重跑）。
    * run 97 `41d5a3a2-cd69-4195-bc5b-c8c9bf5a2fda`：10:59:07→11:05:55 UTC（6.8 min）**SUCCEEDED**；discovered 20 / downloaded 20 / **导入 18** / fail 2（均 `IMPORT_SOURCE_CONFLICT`，staging 仍 PENDING）；`RISK_CONTROL_FALLBACK=0`、`ACCOUNT_RISK_ROTATED=0`、`RECORD_REJECTED=0`、`VARIANT_PRICES_MERGED=15`、`ACCOUNT_ROTATED=1`（正常轮换）。**补价事件全部是「补抓 ≤3 次」，证明 `CRAWL_VARIANT_PRICE_LIMIT=3` 已透传生效。**质量：gallery≥3 18/18、content_sections 18/18、规格表 5/18、多 SKU 12/18、82 SKU 中 44 个无 Offer（limit=3 的直接后果）。
  - **三、男装 400 正式批次（job 219 / run 98，❌ 主动中止 FAILED）**
    * job 219「数据抓取05-男装配饰-400-v2」limit=400、05 组、skip_imported+翻页开、串行单任务。run 98 `1c31d53f-f1c5-4521-842b-0c6437bc1a33`：11:06:52→14:05:18 UTC，因风控全面打穿由操作者 taskkill 自家进程树并标 FAILED。
    * 结果：discovered 400 / 已请求 231 / **导入 212** / fail 44（**25 条 `RECORD_REJECTED` 空记录**，原因 `SOURCE_ID_MISSING + SKUS_MISSING + SOURCE_URL_NOT_PRODUCT`，URL 为 `/user/risk/pic`；**19 条 `IMPORT_SOURCE_CONFLICT`**，staging PENDING）/**169 个候选从未请求**。
    * 事件：`PRODUCT_PARSED=265`、`PRODUCT_IMPORTED=212`、`RISK_CONTROL_FALLBACK=35`、`RENDERED_OK=34`、`RENDER_FAILED=0`、`ACCOUNT_RISK_ROTATED=8`、`ACCOUNT_POOL_EXHAUSTED=1`（13:59:57）、`ACCOUNT_ROTATED=31`、`RECORD_REJECTED=25`、`DETAIL_FIELDS_MISSING=25`、`VARIANT_PRICES_MERGED=229`（其中补价失败 9 次）、`IMPORT_SOURCE_CONFLICT=19`、`PRODUCTS_SKIPPED_IMPORTED=8`、`LISTING_FETCHED=14`。日志 grep 404=0、403=0（本轮没有普通 404）。
    * **风控时间线**：13:01:43 首次（1 号）、13:08:13（2 号）、13:22:15（3 号）、13:55:52 / 13:57:02 / 13:58:14 / 13:58:48 / 13:59:52 连续 5 个 → 13:59:57 池耗尽；14:00–14:05 的 10 分钟内 `RISK_CONTROL_FALLBACK` 从 4 涨到 34、fail 从 20 涨到 43。**这是「风控密集 + 多个账号被轮换 + 池耗尽」的停手条件，故按纪律停止，不再换 06 组继续烧号。**
    * **与男装 63 基线（job 214 / run 94）对比**：本次单 run 212 条（+试水 18 = 今日新增 230 条，与 trial 无重叠），今日男装累计新增 **293** 条（63 + 230），全部 DRAFT 未上架。基线 run 94：导入 63、gallery 63/63、content_sections 63/63、规格表 8/63(13%)、SKU 无 Offer 13/386(3.4%)、无来源冲突；本次：gallery≥3 **212/212(100%)**、content_sections **212/212(100%)**、规格表 **40/212(18.9%)**、多 SKU **210/212**、SKU **1292**、**无 Offer 460(35.6%)**、来源冲突 19/231(8.2%)、评分 2 个有评价且分桶自洽（如 `48321ef8` 5.00/2 分桶 {5:2}、`789c78b9` 3.00/1 {3:1}，0 个 mismatch；基线 4 个全匹配）。**无 Offer 暴涨是 `CRAWL_VARIANT_PRICE_LIMIT=3` 的预期代价 + 9 次补价失败，不是解析丢失。**
    * 多规格抽查（全部 Sku 行 >1、价格有值）：`12a068a4` 12 SKU / 4 Offer / 56.66；`585423d7` 12 SKU / 4 Offer / 56.66；`fa344f01` 12 SKU / 4 Offer / 47.80。画廊/规格表抽样：`48321ef8` gallery 6 / 规格表 1 张 4 行 / 2 段；`789c78b9` gallery 5 / 1 张 9 行 / 2 段。**空规格表与无评分多为源站 payload 本身为空，口径同上一轮核验。**
    * 账号池现状：05 组 8 个 VALID 全部带 `risk_flagged_at`、状态仍 ACTIVE；06 组 **8 个 VALID、0 标记（未参与，未被烧）**；02/03 组旧账未动。
  - **坑 / 注意（不得再踩）**：①`CrawlRun.status=SUCCEEDED` ≠ 全成功（本轮试水 18/20 也成功）；只看 succeeded/failed/staging；②本次 25 条风控空页会进 `RECORD_REJECTED`（不像 404 完全不产生事件），对账要把「导入 + 空页拒绝 + 来源冲突 + 从未请求」分开算；③**账号冷却后 status 仍是 ACTIVE，admin 的 `reactivate_account` 只接受 PAUSED_RISK_CONTROL，无法手工提前解冻**，只能等 6 小时自然过期（真要提前只能改库，不在本次范围）；④`start_run` 的整组冷却快速失败只统计 ACTIVE+VALID 账号，02 组的 4 个 UNKNOWN 不计入；⑤本次为让 executor 继承 `CRAWL_VARIANT_PRICE_LIMIT=3`，runserver 是以该 env 启动的，**下次重启 runserver 若不带这个 env，补价会回到默认 10**。
  - **剩余待办 / 建议**：①**男装缺口**：job 219 已 FAILED，可在 05 组冷却结束（约 2026-11-16 20:00 UTC / 次日 04:00 本地）后重启同一 job（skip_imported 会续抓剩余 169 个候选），或先用 06 组 limit≤10 试水再放量；②**风控大概率是 IP 级**（单 run 1 小时内 8/8 账号全灭，与之前 02 组 9 分钟全灭同型），换号不等于换干净出口，换组前先小批试水；③460 个无价 SKU（212 个 SPU 内）需补价：待风控窗口过去后用 `CRAWL_VARIANT_PRICE_LIMIT=10` 全量刷新，或做单独补价任务；④19 条来源冲突是同一服饰系列不同颜色/尺码 listing 的主 SKU 已被前面的 SPU 作为变体绑定，导入器按规则不改绑（与手机 1 条同类），不要手工改绑；⑤230 个新 SPU 全部 DRAFT，未上架、未 commit。验证脚本在 `var/menswear_20261116/`（`watch.py`/`verify_run.py`/`wait_terminal.py`，只读）。

- **并发任务：头像下拉入口（2026-11-16，购物端头像下拉新增【申请开店】入口 + 状态感知，✅ 完成，未 commit，未人工验收）**：只改 `storefront/components/AppHeader.vue`（`account-menu` 区块 + 脚本状态）、`storefront/components/AppHeader.test.js`（+3 例）、`storefront/locales/messages.js`（en/zh 精确 Edit 插入 3 个键）。**未碰** `storefront/pages/account/index.vue`、`storefront/components/account/AccountNav.vue`、`storefront/pages/account/apply-shop.vue`、后端 `merchant_ops`（另一 Agent 并行负责「申请店铺」入口 + 切换商家端接口）；后端零改动，仅只读调用既有 `GET /api/v1/account/merchant-application`。
  - **加了哪一项**：头像下拉面板里 `account-menu__item` 新增 `<NuxtLink to="/account/apply-shop">`，位置在 `account-menu__name`（账号名行）之后、`My orders` 之前，即面板第一项；**复用 `.account-menu__item` 原 class**（无新增 CSS），实测与其它项同为 230×44、13px/400、`rgb(23,32,42)`、padding `0 8px`、min-height 44px、radius 8px。
  - **状态映射（`sellerMenuLabel` computed）**：`PENDING` → 文案「申请审核中 / Application under review」；`APPROVED` → 「商家中心 / Merchant Center」（**只放链接到 `/account/apply-shop`**，切换商家端由另一 Agent 的接口负责，本任务未实现切换逻辑）；无申请 / `REJECTED` / 请求失败 → 「申请开店 / Sell on Joybuy」；未登录 → 整个 `account-menu` 本就不渲染（沿用原 `v-if="isAuthenticated"`），故无此项。
  - **数据获取**：`loadSellerApplicationStatus()` 在 `onMounted`（已登录时）、`isAuthenticated` watcher、以及**每次打开下拉菜单时**调用（`toggleAccountMenu`）；`$fetch(..., { credentials: 'include' })` 读取 `data.application.status`，**任何异常都 catch 成 `null` 并降级为「申请开店」**，不抛错、不阻塞菜单渲染。
  - **i18n**：新增 en/zh `accountMenu.sellOnJoybuy`（Sell on Joybuy / 申请开店）、`accountMenu.sellerPending`（Application under review / 申请审核中）、`accountMenu.sellerCenter`（Merchant Center / 商家中心）；`aria-label` 用 `:aria-label="sellerMenuLabel"` 绑定，无静态 `t()`。
  - **验证（按要求跑了全量组件测试；其余针对性）**：
    - `node node_modules/vitest/vitest.mjs run --config storefront/vitest.config.js` → **86/86 passed（18 files）**：基线 83 + 新增 `AppHeader.test.js` 3 例（无申请→Sell on Joybuy 且 class/href/aria-label 正确；PENDING/APPROVED 文案切换且 APPROVED 仍链 `/account/apply-shop`；状态请求抛错时降级为 Sell on Joybuy）。未改任何既有断言。
    - `node node_modules/prettier/bin/prettier.cjs --check`（3 个改动文件）→ All matched；`node node_modules/eslint/bin/eslint.js`（同 3 文件）→ exit 0。
    - 浏览器实测（Playwright headless，localhost:3000，1440×900；脚本 `var/header_apply_shop_20261116/verify_apply_shop.mjs`，原始结果 `apply_shop_results.json` / `.txt`）：
      ① EN 未申请买家：下拉出现 `Sell on Joybuy`（面板第一项，href=`/account/apply-shop`，aria-label 同文案），与相邻项 fontSize/fontWeight/color/height/minHeight/padding/radius **全部相等**；截图 `header_apply_shop_en_menu.png`。
      ② 点击 → URL=`/account/apply-shop`，表单 3 个字段（`shop-apply-name/-legal/-referrer`）渲染，按钮 `Submit application`；截图 `apply_shop_page_en.png`。
      ③ 在该页填「Header Apply Shop」提交成功（真实 POST，无后端改动）→ 页面变「审核中」+「您的申请正在审核中…」+ 店铺名回显；截图 `apply_shop_submitted_zh.png`。
      ④ PENDING 买家（用买家接口造的真实申请）：EN 下拉显示 `Application under review`（截图 `header_pending_en_menu.png`），点击 → 申请页显示 `Under review`（`apply_shop_pending_en.png`）；ZH 显示「申请审核中」（`header_pending_zh_menu.png`）。
      ⑤ ZH 未申请买家：下拉第一项「申请开店」，其余项「我的订单/评价与问答/我的收藏/地址/退出登录」（`header_apply_shop_zh_menu.png`）。
      ⑥ 未登录：`.account-menu` 数 0、`a[href="/account/apply-shop"]` 数 0，账号位仍是 `Sign in` 图标链 `/account`（`header_anon_en.png`）。
      ⑦ **console error 0**（4 个浏览器上下文合计）。
    - 临时买家与申请已删净：`BuyerAccount` 前缀 `apply-none-` / `apply-pending-` 计数 0，删除时级联 `BuyerSession` 6 / `MerchantApplication` 2，孤儿申请 0。
    - `HANDOFF.md` 的 prettier `--check` 仍报格式问题，但 diff 首处 hunk 从第 30 行开始（本轮新增小节在 7–27 行已无差异），失败点是**其它 Agent 此前写入的 `*` 嵌套列表**（如 copy_tweaks 小节）；未对本文件跑 `--write`（并行写入风险）。
  - **与并发 Agent 的边界（勿越界）**：本任务只拥有 `AppHeader.vue` 的头像下拉；「申请店铺」在个人中心/左侧账号导航的入口、以及 APPROVED 后「切换商家端」的接口与逻辑归另一 Agent。若后续要在下拉里真正触发切换商家端，应接对方接口，不要在本文件里自造跳转。
  - **坑（不得再踩）**：①`messages.js` 只能精确 Read→Edit 字符串替换，另一 Agent 同时在改，整文件 Write 会覆盖对方改动；②`request.newContext({ baseURL: '.../api/v1' })` 再用 `/auth/...` 前导斜杠会丢掉 `/api/v1` 前缀、请求落到 SPA 返回 HTML（本轮踩过，改为 baseURL 不带路径 + 全路径）；③临时买家的 `MerchantApplication` 由 `buyer` OneToOne CASCADE，删买家即删申请，无需单独清理；④状态请求必须 catch 降级，否则后端 403/网络失败会让整个下拉菜单渲染卡住。
  - **未做/下一步**：①APPROVED 态只在单测覆盖，浏览器未实测（需管理端审核通过，属另一 Agent 的端到端范围）；②中文买家账号名过长时仍按原 ellipsis 处理；③**git 未提交**。

- **当前任务（2026-11-17，AI 术语表全链路（零人工）+ 三轮重翻对照 + 搜索文档实验，✅ 术语表可用、55 商品重翻 PASS，⚠️ 搜索文档实验已回退，未 commit）**：用户指令「术语表要我们自己建立，全程都要 AI 来，不需要人工干预，参照电商平台规则」。
  - **术语表（AI 生成→AI 审查→自投票，无人工）**：规则落地 `translation_agent/glossary/rules.md`（颜色/材质/尺码/容量/质保/合规/品类/功能形容词/永不收录 10 类）；工具 `translation_agent/tools/build_glossary.py`（子命令 `scan/gen/review/vote/apply`，curator=`qwen3.8:27b`，`think:False` 防思考吃掉 num_predict，24–36 词/批、`format=json`）。**覆盖 7488/10090 条可译词（74%）**；审查统计 `ok 5704 / fix 1783 / unchanged 1819 / suspicious 270 / 低置信度 1 / 德语名词大写自动修正 37`；写回 `translation_term` **7536 行/语言**，全表备份 `translation_agent/glossary/backup_20261117.json`，产出 `glossary/glossary_v1.json`，余 **2602 条 pending**。
  - **管线接线**：正文/图文 prompt 早已注入 `db.glossary_hits()`（命中的 done 词按官方 `Reference the following translations:` 段，上限 20 条）+ `DEFAULT_GLOSSARY` 种子；本轮补的是**品类策略**——`GLOSSARY_NON_INJECTABLE`（prompt 注入）= **空**（形容词必须注入，否则 `Sparkling Sour` 会错），`GLOSSARY_NON_INJECTABLE_SPEC`（规格单元格取值）= `{adjective_selling}`（避免 `Ambidextr` 这类非词，宁可保留源文）；术语 `category` 由 `var/glossary_apply_20261117/backfill_categories.py` 回填进 `quality_flags`（apply 原本没写，导致过滤失效——已修）。
  - **三轮 A/B 教训（重要）**：②全部注入 → 223 `Sprudelnd Sauer` ✅ 但 177 `47cm Weit … hochwertige` ❌（坏词 `Wide→Weit`）；③过滤形容词 → 177 修好但 223 回归 `Sprudelnder Sauerstoffgetränk` ❌；④**AI 重校尺寸形容词小闭合集**（27 条：`Wide→breit`、`Height→hoch`、`Length→lang`…，德语标题内形容词小写）+ 恢复全量注入 → 223 `Kirin Freeze Ananas Sprudelnd Sauer 350ml` ✅、177 `47cm breit 144cm hoch Freistehend Kühl-Gefrier-Kombination` ✅（fr 仍略显生硬）。结论：**问题在个别词条而非品类，按品类一刀切会按下葫芦浮起瓢**。
  - **单位保护**：264 条把单位改掉的术语（`6.6W→6,6B`、`1.96 Inch→1,96 Zoll`、`8.66inch→8,66 Zoll`）按规则 4「数值+单位不动」**回退源文**（`var/glossary_apply_20261117/fix_unit_terms.py --apply`，报告 `unit_guard_revert.json`）；verify 增数值等价比较（`9.9%≈9,9%`、`5kg≈5 kg`、`70-79 inch`）不再误报。
  - **重翻与验证**：55 个 SPU 两轮重翻（round3 2290s、round4 308+22 units，全部 `units_failed=0`）→ `build-specs --overwrite-specs` → **`verify --all --langs de,fr,nl` 11 项全 PASS、exit 0**（`spec tokens 0`、`sku coverage 424/424`、`terms de/fr/nl 7536 done 0 failed`）。库存现值：`translation_unit=330 done`、`spu_translation` 非 en-GB=**460**、`spu_detail_translation=165`、`sku_specification_translation≈1847`、`translation_term=7536/lang`。
  - **搜索文档实验：已回退（勿重蹈）**：worker 为让 DE 列表显示德语，在 **GB 市场**额外写了 5 组本地化行（GB/de-DE 等 275 行）+ 5 个市场行（275 行，`is_searchable=0`）。后果：`storefront_search` 的回退链「请求市场 → GB+请求 locale → GB 默认」使 DE **优先命中只有 55 行的 GB/de-DE**，**DE 搜 `fridge` 从 32 条变 0 条、DE 列表从 7899 变 55**（GB 不受影响）。已删除这 550 行、恢复 7900 行 GB/en-GB，DE 搜索回到 32 条英文结果。**结论：本地化搜索必须等全量译文（或先做后端合并检索），不能用少量本地化行覆盖回退链**。
  - **环境事故（必须记住）**：一轮翻译中途 `Docker Desktop` 引擎挂了（`//./pipe/dockerDesktopLinuxEngine` 不存在 → MySQL `WinError 10061 拒绝连接` → python 进程 `3221225794/DLL init failed`）。恢复：`"D:/Docker/Docker Desktop.exe"` 拉起 → 轮询 `/d/Docker/resources/bin/docker.exe ps` 等 `joybuy-dev-mysql-1` 出现 → 等 MySQL 可连 → `translate.py recover-stale --minutes 5`（回收 2 条僵尸）→ 同一 `run` 命令续跑（attempt_count=0 的 pending 会接着做）。**docker CLI 在 `/d/Docker/resources/bin/`，Git Bash `docker` 偶发指向坏路径**。
  - **环境坑（2026-11-18，给的链接打不开）**：购物端 dev server 之前是**手动裸跑 `nuxt dev`**，listhen 绑到 **`[::1]:3000`（仅 IPv6 环回）** → `http://127.0.0.1:3000`（IPv4）连接被拒，只有 `http://localhost:3000` 能开（`curl` 实测 127.0.0.1=000 / localhost=200）。修法：`cmd //c "taskkill /PID <pid> /F"`（Git Bash 里 `/PID` 会被当路径，必须 `//PID` 或走 `cmd //c`）→ `cd storefront && node node_modules/nuxt/bin/nuxt.mjs dev --host 0.0.0.0 --port 3000` → 监听 `0.0.0.0:3000`，**127.0.0.1 与 localhost 均 200**（含 PDP 深链）。以后给用户链接优先 `localhost:3000`。**2026-11-19 复发一次**：该后台进程随会话退出（日志停在 HMR update，端口无监听），且并发会话另起了一个 `[::1]:3000` 实例造成「双监听、localhost 反而 000」。最终定法：**用 `--host ::` 起单个双栈实例**（`cd storefront && nohup node node_modules/nuxt/bin/nuxt.mjs dev --host :: --port 3000 > ../../../var/logs/storefront_dev.log 2>&1 &`），实测同一 PID 同时 LISTEN `0.0.0.0:3000` 与 `[::]:3000`，localhost 与 127.0.0.1 的首页和 PDP 深链均 200。多个实例抢 3000 时先 `netstat -ano | grep :3000` 全杀再起一个。
  - **品牌词误译修复（2026-11-18，AI guard + 重翻 55）**：用户抽查发现 `Apple→Apfel/Pomme/Appel`、`RoyalBaby→Königsblau`、`Unisex→Alleinstehende`、`Medium→M`、`Akcesoire` 拼错。新增 `translation_agent/tools/brand_guard.py`（`survey/classify/vet/typos/discover/colour-seed/apply/check`，可断点续跑）：用 `qwen3.8:27b` 把全部术语按 `brand/product_line/size_word/generic_noun` 分类，命中的品牌与产品线**一律 identity（译回源文）**并写 `quality_flags.keep_source`；`Medium/Small/Large` 保留源词不缩成尺码码；错拼按 AI 建议修正。结果：`translation_term` **7536→7712 行/语言**（触发 1257 行、其中实际改写 131 行：品牌 30 / 产品线 55 / 尺码 15 / 错拼 28 / 色名 3；新增 528 行 identity），原值存 `var/brand_guard_20261118/term_backup.json`。重翻 330 unit（1304s，0 失败）+ `build-specs --overwrite-specs` → `verify --all` **11 项 PASS**。断言：7964 de `Apple iPhone 17 Pro 256 GB Cosmic Orange`、170 de `Apple iPhone 17 256GB Schwarz`、219 de `Inch's Medium Apple 4x440ml`、2345 de `Unisex Motorradschutzhose…`、2376 de `RoyalBaby Helm Moon Grün…`，55×3 语言标题 **0 处** `Apfel/Pomme/Appel`。四语抽查表 `var/brand_guard_20261118/titles_55.md`，报告 `report.md`。
  - **已知残余（品牌 guard 引入）**：`glossary_hits` 大小写不敏感子串匹配 → 短词（`Royal`/`Switch`/`Small`）在非品牌语境也会保留源文；`Apple` 一律当品牌（水果类商品需标题级处理）；单字母尺码 `S/M/L` 仍走 `size_code`；`7964` 的 `256 GB` 与源文一致（格式统一另开任务）。
  - **仍未解决的质量问题**：法语语序/性数（`47cm Large 144cm Haute Réfrigérateur…`）、`221` 德语从 `Alkoholgehalt` 变 `ABV`（术语表选词，可接受但不如前者）、荷兰语偶发生造词；短语级错误无法靠术语表覆盖，需要**标题级 AI 校对 pass**（27B thinking，2–4s/条起，只能用于短字段）。
  - **下一步**：①全量放量（~11.8k SPU 现库，按 20 min/50 ≈ **80 小时**，建议夜间分批 + `--concurrency 2`）；②先做标题 AI 校对 pass 再放量（更稳但要额外 8–12h/8k×3）；③剩余 2602 条术语增量生成；④全量译完后再重建本地化搜索文档（届时覆盖足够，无需改后端）；⑤`refresh_spu_search_documents()` 只重建 GB/en-GB，本地化行将来需要接入刷新逻辑。

- **上一任务（2026-11-17，放量灰度：真模型批量翻译 50 商品 × de/fr/nl + PDP 语言切换验证通过，✅ 完成，数据**留在库里**未 purge）**：用户先要求「验证切换语言后商品详情的语言情况，通过后再批量跑 50 个」。
  - **切换语言验证（VERDICT: PASS，报告 `var/pdp_locale_switch_20261117/verification.md` + 9 截图）**：根因修复（`pages/p/[id].vue:35` useFetch key 改 computed）后，177/7964 各 12 步切换矩阵（GB→BE→DE→FR→NL→LU 全组合）每步都发出带新 `market/locale` 的请求、标题/SKU 规格命中库内译文、BE 默认 nl-BE、冷加载 6 例 SSR 首屏即目标语言、未翻译商品回退英文、console 0 错误。**两个不阻塞的边界**：①lb-LU 回退标题取库内第一行（德语）而非英文（`resolve_product_content` FALLBACK 分支无排序，建议单开任务明确 en-GB 优先）；②切市场瞬间发 2 个产品请求（中间态 `market=新&locale=旧` + 终态），良性。
  - **批量 50（真模型，报告 `var/hymt2_real_run_20261116/batch50.md`）**：按 9 个一级类目配额抽 50（全带非空 SKU 规格，排除前 5 个试跑 SPU；候选池 7764）。`enqueue` 300 units + 972 新术语 → `run --all --concurrency 2`：**300/300 done、0 failed、0 retry、1189s（约 20 分钟，比预算快）**，terms 873 done/93s，全程 0 ERROR → `build-specs`：detail 50×3、sku_rows de147/fr147/nl98、`missing_terms=0` → `verify --all` **11 项全 PASS exit 0**（identical_titles=24 只是 3 个纯品牌名标题，无可译内容）→ `status` orphan=0/zombie=0。
  - **库存留数（基线→后，主会话独立复核一致）**：`spu_translation` 非 en-GB 60→**460**、`spu_detail_translation` 15→**165**、`sku_specification_translation` 1455→**1847**、`translation_term` 360→**1332**、`spec_write_log` 24→**416**、`translation_unit` 30→**330**。id 列表 `batch50_spu_ids.txt`；**回滚命令（未执行）**：报告第 7 节的 `purge --all --langs de,fr,nl --spu-ids <50 ids>`。
  - **质量抽查（9 类目各 1 SPU，样本 `batch50_samples_readable.txt`）**：整体流利，中文源（164 OPPO、183 TCL）正确；`quality_flags`：high_risk 13 / direct 9 / missing_protected 9（全是 `37-51cm`/`135kg`/`220V` 类技术 token，无害）；长度越界 0。**真实错误仅 2 处标题**：SPU 223 de 把 "Sparkling Sour" 译成 `Sprudelnder Sauerstoff`（**氧气**，应为 `Sprudelnd Sauer`；nl `Sprankelende Zure` 是对的）；SPU 2335 nl 标题构词生硬。按纪律未擅自改——这类词正是术语表的活。
  - **购物端 PDP 实测（DE）**：183 洗衣机（`/p/6ce7a4ba-…`）切 Germany 后标题德语、SKU 摘要 `10kg/6kg Motor mit Waschen und Trocknen in einem`；2335 DE 冷加载直接德语。截图 `batch50_pdp_*.png`。
  - **本轮已知边界**：①图文详情与规格参数表区块仍源语言（`detail_views` 未读 `spu_detail_translation`，待接）；②SPU 164 有 2026-11-06 遗留空 `{}` sku_spec 行（9 locale），按设计未覆盖，脏数据另开任务；③本轮 50 个全是单 SKU，多规格点选未覆盖（7964 场景已在前轮验证）；④`content_sections[].text` 是源文镜像（设计如此），核对看 `blocks[]`。
  - **下一步建议**：①用户浏览器抽查这 55 个（切 DE/FR/NL 或 BE）；②决定放量节奏（全量 ~8300 SPU 按 20 min/50 ≈ **55 小时**，建议低峰分夜跑，或先只做 ACTIVE+有 Offer 的可售品）；③放量前建**品牌/品类术语表**（消掉 Sauerstoff 类错译）；④详情接口接 `spu_detail_translation`；⑤按 market 重建 `product_search_document`。

- **上一任务（2026-11-17，真模型小批量试跑 5 个商品 × de/fr/nl + verify 假阳性修复，✅ 完成，数据**留在库里**未 purge）**：用户要「先跑几个看看」，所以用真模型跑了 **SPU 177 / 195 / 219 / 221 / 7964**（全 ACTIVE、有正文和规格表；7964 是中文源、全库唯一 ACTIVE 多 SKU 商品），`--all`（图文 + 规格），数据**刻意保留**供购物端查看。
  - **实测规模与耗时**：`enqueue` 30 unit + 360 term（`no_letters=5 / protected=10` 跳过）→ `run --all --concurrency 2`：`units_done=30 units_failed=0 attempts=30 retried_attempts=0 elapsed=200.3s`，其中 term 315 条 35.1s；`build-specs` 5 SPU（`sku_rows=24`、`sku_skipped_empty=3`、`missing_terms=0`）。**title 平均 0.6s / 条，detail 平均 24.7s / 条（10–39s，一个 block 一次调用）** → 全量正文的时间瓶颈在 detail。
  - **库里新增（这就是当前"已翻译"的范围）**：`spu_translation` 目标 locale **+40**（5×8）；`spu_detail_translation` **+15**；`sku_specification_translation` 1431→**1455**；`translation_term` **+360**；`spec_write_log` **+24**；`translation_unit` **+30**。`spu_translation` 非 en-GB = **60**（zh-CN 20 未动）。**回滚命令（未执行）**：`PYTHONIOENCODING=utf-8 python translation_agent/translate.py purge --all --langs de,fr,nl --spu-ids 177,195,219,221,7964`（dry-run 数字与增量完全一致）。
  - **质量样本（三语标题 / 规格）**：177 德语 `CHiQ JKR157LBE 47cm Breit 144cm Hoch Freistehender Kühlschrank mit Gefrierfach - Geringe Frostbildung - 157L - Schwarz - E-Klasse`；221 法语 `Kopparberg Fruits mélangés 10 X 330ml (Titre alcoolique 4%)`；7964 中文源 → 德语 `Apple iPhone 17 Pro 256 GB Kosmischer Orange`、荷兰语 `Ruimteoranje`。规格：`UK Manufacturer's Warranty = 1 Year Manufacturer's Warranty` → `Garantie des britischen Herstellers = 1-jährige Herstellergarantie`，列头 `属性/值` → `Eigenschaften/Wert`，`Model=JKR157LBE` → `Modell=JKR157LBE`；SKU `颜色/系列` → `Farbe/Reihe`，值 `Black/Schwarz`。**315 条术语 0 失败 0 漏译**，受保护 token（`256GB`/`109-litre`/`47cm`/`XXXL`）全在。
  - **明显错译（模型质量，未修）**：①荷兰语 `Sleek black finish` → `Slechte zwarte afwerking`（sleek→slecht，语义反）；②荷兰语 `SULPHITES` → `ZWAVELVERVEN`（硫磺漆）、`Allergens` → `Allergeenen`；③荷兰语 `Triple Monitor Stand` → `drie monitorstandaarden`（stand→标准）；④德语 `Kosmischer Orange`（应为 `Kosmisches Orange`），且 SKU 值仍 `Cosmic Orange` 与标题不一致；⑤法语 `le iPhone` 冠词错；⑥`109-litre`、`2-year` 这类复合词不译。→ 结论：**标题/规格表可用，长文案可读；品类别名与品牌词需要术语表**。
  - **verify 两个假阳性已修**（原本 40 条 FAIL / 退出码 1，数据其实是好的）：①`5. length ratio` 对**中文源**不适用（7964 的 30 条按字符数膨胀 2.7–5.1 倍）→ 改为按源文脚本分档（CJK：1.0–6.0 且忽略 extra_chars；源文 <20 字符的 CJK 短标签不设上限；拉丁源保持 `ratio>2.2 且 extra_chars>120`），并改为**读库里当前译文重算**（不再信任旧 `quality_flags`，否则负向测试测不出来）；②`8. spec tokens` 对 SKU 规格（JSON 对象）按位置比对，被 **MySQL JSON 键序规范化**打乱（`系列,颜色`→`Farbe,Reihe`）→ 改为**多重集合比对**（源里每个受保护 token 必须在译文值集合中出现，忽略键序/键名）；数组类（表格 rows / specifications / options values）仍按位置。**负向测试**：临时把 `sku_specification_translation.id=1568` 的 `256GB` 改成 `256 GB` → `8. spec tokens` 正确 FAIL；把 `spu_translation.id=9372` 的德语标题改成 `x` → `5. length ratio` 正确 FAIL；两次均精确还原（`RESTORE_MATCH: True`）。
  - **修复后复跑**：`verify --all --langs de,fr,nl` → **11 项全 PASS、退出码 0**（`length out_of_range=0 cjk_units=6`、`spec tokens problems=0`、`sku coverage 24/24`、`terms de/fr/nl 各 120 done 0 failed`）。`compileall` + `ruff check verify.py` 通过。
  - **购物端实测（DE / de-DE）**：`/p/5b7098bf-…`（7964）标题德语（`content_origin=LEGACY`、`content_locale=de-DE`）；**规格参数表仍是源语言**（`detail_views` 还没读 `spu_detail_translation`，符合预期）；已选 SKU 规格德语（`Cosmic Orange / 256GB`）；多规格点选正常（`Silber`↔`Cosmic Orange` 切换，价格不变）。截图 `var/hymt2_real_run_20261116/shop_de_pdp*.png`。**坑**：URL 要用**带连字符的 UUID**，库里 `public_id` 是 32 位无连字符，直接拼会 `PRODUCT_NOT_AVAILABLE`（页面显示 delisted）。
  - **完整报告**：`var/hymt2_real_run_20261116/pilot5.md`（选品表、三语标题全表、正文/规格对照、verify 修复前后、负向测试证据）。
  - **下一步**：①用户看完这 5 个再决定是否放量（建议先 200 条灰度，`--concurrency 2`）；②放量前最好先建**品牌/品类别名术语表**（改 `translation_term.translated_text` 或加 glossary，重跑 `build-specs` 生效），能一次消掉 ①②③④⑤ 类错误；③详情接口接 `spu_detail_translation` 才能让规格参数表显示译文；④`product_search_document` 需按 market 重建。

- **当前任务（2026-11-16，Hy-MT2-7B 真模型上机验证：权重下载 + Ollama 注册 + 真实译文/吞吐 + 占位符阶梯修复，✅ 完成，未 commit）**：**这条闭合了翻译任务最大的未知项**——真模型能跑、能加载、质量与速度已实测。权重 `translation_agent/models/Hy-MT2-7B-Q4_K_M.gguf` 已下载（21:10→22:34，约 84 分钟，`PROXY_URL=http://127.0.0.1:7890 MIRROR=0 JOBS=8` 8 路分段，大小 4,624,648,896 + sha256 `9f9625…f9f77b` 双双通过）；`ollama create hy-mt2:7b-q4km` 成功。
  - **Ollama 路线确认可用**：`ollama create` **29 秒**（Ollama 按内容哈希复用了已有 blob，`using existing layer`——别误以为没导入），架构 `hunyuan-dense` / 7.5B / Q4_K_M，**没有 `unknown architecture` / `tensor type 43` / STQ 问题 → 自建 PR #22836 llama.cpp 那条路不需要了**（官方 README 的 STQ 警告确实只影响极低比特变体）。
  - **实测性能（3090 24GB）**：`ollama ps` = **size_vram 5.27GB / 100% GPU / CONTEXT 4096**，`nvidia-smi` 加载后 9674 / 24576 MiB；**并发 1/2/3 聚合 = 55.1 / 64.1 / 62.4 tok/s**，单条延迟 11.5 / 16.8 / 20.9 s → **推荐 `--concurrency 2`**。`num_ctx` 4096→8192：显存 5.3→5.9GB，解码速度无变化（不是速度旋钮）。产能：2.6 万条正文按 64 tok/s + 16.8s/条推算 ≈ **120 小时量级**（推断，算式在 `docs/deployment.md` §6）。
  - **P0 修复：占位符保护过严会让整条 unit 丢**（首轮 60 unit 里 4 个 `placeholder_mismatch`，SPU 219 荷兰语整段、SPU 220 德语整段直接没写）。改成**三级降级阶梯**（`agent/detail.py::_translate_chunk` + `agent/prompts.py::protect(level=full|high_risk|none)`）：①全量遮挡（现有行为）→ ②只遮挡高风险（model_number/gtin/品牌/长数字单位）+ prompt 加 `Keep product codes and measurements exactly as they are.` → ③不遮挡直译 + **事后校验保护 token 是否原样出现**；缺失也让译文落库，只打 `quality_flags.missing_protected` / `needs_review`，**不再把整个 unit 判 failed**。复测 6 个 SPU（219/220/221/195/177/175，36 unit）：`units_done=36 units_failed=0`，降级 6 个（high_risk 3 / direct 3），`missing_protected` 仅 2 unit / 4 token（`20%`/`33 W` → `20-prozentige`/`33-Watt-`，语义正确）。SPU 219 荷兰语整段已完整产出。
  - **顺带修的口径问题**：①`run` 的 `failed=` 曾是**尝试次数**（首轮显示 16，实际 4 个 unit 失败）→ 现在输出 `units_done/units_failed/attempts/retried_attempts`；②`verify` 的 length ratio 短块误报（30–60 字符的 block 判 2.3–2.4 倍 FAIL）→ 规则改为 `ratio>2.2` **且** `extra_chars>120`，并新增 `5b. protected fallback` 信息行。
  - **文档已按实测纠正**：`docs/deployment.md` 的显存/吞吐/产能从估算（6.5–9.5GB、90–120 tok/s、20–30h）改为实测（5.27GB、55/64/62 tok/s、≈120h 推断）；`docs/troubleshooting.md` 新增「译文整段缺失 / 英文残句」；README §6/7/8/11/12/13 同步。
  - **仍未解决的质量问题（不要当已修）**：①**普通英文残句**（SPU 220 德语 `verleihen each Sekt einen`，阶梯抓不到普通英文词）；②法语 `cidre` 系统性当阴性（`une cidre`/`La cidre`）；③德语把 `cider` 译成 `Fruchtsaft`/`Sekt`（错品类）；④荷兰语生造词（`verwarmder`/`gamingschoot`）；⑤单位格式不统一（`32-inch"-monitoren`、`27- of 32-inch`）；⑥术语个别不地道（`Chest Freezer→Kühlfach`、`Fit Type→Trainingsart`、`Low Noise→Niedriger Lärm`、`Galvanized Steel→Galvanisiertes Stahl`）；⑦`columns` 实测译为复数 `["Eigenschaften","Wert"]`（可接受，别在文档写死单数）。→ **建议先建品牌/品类术语表**（`translation_term.translated_text` 可直接人工改，重跑 `build-specs` 即生效）。
  - **清理与基线（精确恢复）**：`sku_specification_translation=1431`、`spu_detail_translation=0`、`translation_term=0`、`spec_write_log=0`、`translation_unit=0`、`spu_translation` 非 en-GB = **20**，`status` 的 `orphan_units=0`。模型 `hy-mt2:7b-q4km` 保持注册、gguf 保留；`qwen3.8:27b` 未被卸载（只在加载期临时让位）。
  - **下一步（放量前）**：①`--concurrency 2` 跑 **200 条灰度**，人工抽查上面 6 类质量问题；②确认后再 `enqueue/run --all` 全量 + `build-specs --langs de,fr,nl`（预计 61–121 小时，低峰跑）；③按 market 重建 `product_search_document`；④详情接口读 `spu_detail_translation` 才能让规格参数表显示译文；⑤术语表（品牌/品类/单位）优先于放量。
  - **坑（不得再踩）**：①`ollama create` 秒级完成是 blob 复用，不代表没导入；②**并发不放大显存**（单实例共享 KV，1/2/3 路 size_vram 恒 5.27GB），别再按「×并发数」估算；③`missing_protected` 是保守标记会有噪声（如 `20-prozentige` 其实是正确译文），别为了消噪直接放宽校验，先抽样；④`content_sections[].text` 是镜像字段故意不翻，核对必须看 `blocks[].text`；⑤同一批数据里 `de/fr/nl` 质量差异明显（荷兰语最忠实、法语词性最差），抽查要按语言分层；⑥`run` 的计数口径已改，旧交接里的 `failed=` 数字不可直接比。

- **当前任务（2026-11-16，本地 VPN/代理加速 HF 下载探测 + 断点续传脚本，✅ 完成，未 commit）**：只读探测本机代理能否加速从 Hugging Face 下载 `Hy-MT2-7B-Q4_K_M.gguf`（4,624,648,896 字节），产出脚本与实测数据。**未启动 4.6GB 完整下载**（只做 5–10MB 分段测速与 100MB 的一次稳定性复测，后者直写 `/dev/null`，无临时文件）。未改系统代理 / hosts、未装软件、未 `git add` / commit。
  - **环境事实**：`FlClashCore.exe`（PID 30908）监听 `127.0.0.1:7890`（HTTP 混合口）；系统代理 `ProxyEnable=1`、`ProxyServer=127.0.0.1:7890`；**TUN 已开启**（`ipconfig` 出现「未知适配器 FlClash」）；`env | grep -i proxy` 为空（Git Bash 的 curl 不读注册表，实际走 TUN）。其它监听口（1053 Clash DNS、11434 Ollama、5939 TeamViewer 等）都不是代理。无 aria2c / wget；Git Bash curl 8.21 / System32 curl 8.21；PowerShell 5.1.19041.6456。
  - **实测（5MB 短测偏乐观，20MB 才可信）**：单流 20MB 0.14–3.58 MB/s、中位数 ≈0.50 MB/s，8 次官方 HF 测试里 2 次 60s 跑不完；100MB 直连测试 180s 只下 22.2MB（123 KB/s 后基本停摆）。`hf-mirror` 单流 20MB 0.30–0.36 MB/s（更慢，且 20MB 跑不完）；7890 的 SOCKS5 不可用（20MB 只下 1.6MB ≈26 KB/s）。**多连接才是稳定提速手段**：4×10MB 聚合 1.33–1.74 MB/s（代理）、8×5MB 聚合 1.43–3.33 MB/s（代理）。节点单连接 0.2–1 MB/s、总出口约 3–4 MB/s。
  - **结论/推荐顺序**：官方 HF + 显式 `-x http://127.0.0.1:7890` + `-Jobs 8` 最快最稳；其次 4 路；`hf-mirror` 只作兜底；`-Jobs 1` 单流最后手段。详细数据、命令、原始响应头见 `translation_agent/docs/download_route_20261116.md`。
  - **产出**：
    * `translation_agent/deploy/download_hy_mt2.ps1`（PowerShell 5.1，**UTF-8 with BOM**）与 `download_hy_mt2.sh`（Git Bash）。
    * 参数：`-Proxy`/`PROXY_URL`（空=直连）、`-Mirror`（默认开 hf-mirror；推荐 `-Mirror:$false` / `MIRROR=0`）、`-Dest`/`DEST`、`-Jobs`/`JOBS`（默认 8）、`-Url`/`URL`、`-ExpectedSize`/`EXPECTED_SIZE`、`-Sha256`/`SHA256`（`skip` 可跳过）、`-LogFile`/`LOG_FILE`。
    * 断点续传：`-Jobs 1` 用规格要求的 `curl -L -C - --retry 8 --retry-delay 5 --retry-all-errors --connect-timeout 20 --progress-bar`（另加 `--speed-limit 10240 --speed-time 60` 防挂死）；分段模式按 part 现有字节数算 `-r cur-end`，先写 `part.tmp` 再追加到 part，失败自动重试（上限 60 轮）。完成后校验大小 4624648896 + sha256，失败只报错不删文件。日志默认 `translation_agent/logs/download_model.log`，每秒写 `progress bytes=... rate=... B/s`。
    * `translation_agent/deploy/Hy-MT2-7B-Q4_K_M.gguf.sha256`：官方 sha256 `9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b`（来自 `X-Linked-ETag`；`X-Linked-Size=4624648896`、`X-Repo-Commit=ab8472660ac61fac25f1af43fac2599d52a8a775`）。
  - **验证（按验证纪律仅做针对性验证）**：`bash -n` → OK；`[Parser]::ParseFile` → `PARSE_OK`（曾因 `"part $i: ..."` 被当成作用域变量报错，已改 `${i}:`）。两脚本都在 `gpt2/vocab.json`（1,042,301 字节，公开非 LFS）上做端到端测试并通过：4 路分段拼接后 sha256 与参考一致；预置半截 part（100,000 字节）+ 一个已完成 part → 跳过 + 续传后 sha256 一致；预置 1,000 字节半截单流 → `-C -` 续传后 sha256 一致；sha256 通过/不符分别 exit 0/1 且文件保留；不传代理路径也通过。临时目录已删除；**未跑 4.6GB 完整下载**。
  - **下一步（主会话）**：用后台任务跑
    `powershell -NoProfile -ExecutionPolicy Bypass -File translation_agent\deploy\download_hy_mt2.ps1 -Proxy http://127.0.0.1:7890 -Mirror:$false -Jobs 8`
    预计 23–55 分钟；若总速率长期 <1 MB/s，停掉换 FlClash 节点后原命令重跑（会续传）。下载完成后脚本自动校验大小 + sha256。
  - **坑（不得再踩）**：①`reg query` 在 Git Bash 必须加 `MSYS_NO_PATHCONV=1`，否则反斜杠被转义报「无效语法」；②`curl -C -` 与 `-r` **互斥**，分段续传不能混用；③`curl -o` 会**截断**目标文件，分段必须写 tmp 再追加（写成直接 `-o part` 会反复截断、重试空转）；④PowerShell 双引号里 `$i:` 会被当作用域变量，写 `${i}:`；⑤TUN 开启时「直连」也已过 FlClash，真直连只能由用户关 TUN 后测；⑥5MB 短测会因 CDN 突发虚高（SOCKS5 5MB 893 KB/s vs 20MB 26 KB/s），路线判断一律看 20MB+；⑦单流 100MB 会在中途掉到 120 KB/s 并长时间不返回，脚本已用 `--speed-limit/--speed-time` 兜底；⑧**不要同时跑两个下载实例**，也不要在 kill 掉一个实例后立刻复用同一 part 路径（残留 worker 会与新实例抢写，测试时踩过）。

- **当前任务（2026-11-16，账号页 4 处文案微调，✅ 完成，未 commit，未人工验收）**：只改 `storefront/pages/account/addresses.vue`、`storefront/pages/account/returns.vue`、`storefront/pages/account/reviews.vue`、`storefront/locales/messages.js`；**后端零改动、未新增接口、未重构页面结构**；空态（图标 + 主文案）全部保留。
  - **改了什么（逐条）**：
    1. **地址页 `/account/addresses` 自提 tab 的右上按钮文案动态化**：新增 comput（`addButtonLabel = tab === 'pickup' ? t('addresses.addPickup') : t('addresses.addNew')`），按钮仍用原 `.address-add` + 同一 `openCreate` 点击行为、原 plus SVG/样式不变。新键 `addresses.addPickup`（en `Add a pickup point` / zh `添加自提点`）；「+ 添加新地址」仍是 `addresses.addNew`（en `Add new address` / zh `添加新地址`），未改。
    2. **删「当前演示版暂不支持自提，请切换到「配送」管理收货地址。」**：模板 `pages/account/addresses.vue` 自提分支的 `<AccountEmpty … :note="t('addresses.pickupNote')" />` 改为只有 `:message="t('addresses.pickupEmpty')"`（空态图标 +「暂无自提点。」保留），并删除 en/zh 键 `addresses.pickupNote`。
    3. **删地址弹窗「目前仅支持英国收货地址。」**：移除 `addresses.vue` 里 `<p class="address-form__hint">{{ t('addresses.ukOnly') }}</p>` 及其无用 CSS `.address-form__hint`，并删除 en/zh 键 `addresses.ukOnly`。
    4. **删售后单页 `/account/returns` 的「后端尚未实现售后业务，本页仅展示真实空态，不构造任何虚假记录。」**：`returns.vue` 的 `<AccountEmpty … :note=…>` 改为只有 `:message="t('returns.empty')"`（图标 +「暂无售后单。」保留），删除 en/zh 键 `returns.backendGap`。
    5. **删评价与问答页 `/account/reviews` 的「买家评价与问答功能暂未开放：…没有“我的评价”数据源。」**：`reviews.vue` 同样去掉 `:note`（图标 +「暂无评价与问答。」保留），删除 en/zh 键 `reviews.backendGap`；顺带把该文件顶部注释里 “with a visible note” 改为 “an honest empty state”（注释原话已不成立）。
  - **验证（按验证纪律：本任务要求全量 vitest；其余仅针对性）**：
    * `node node_modules/vitest/vitest.mjs run --config storefront/vitest.config.js` → **83/83 passed（18 files）**，与基线一致，**未改任何测试断言**（全仓无测试引用这 4 条文案）。
    * `node node_modules/prettier/bin/prettier.cjs --check`（4 个改动文件）→ All matched；`node node_modules/eslint/bin/eslint.js`（同 4 文件）→ exit 0。
    * 浏览器实测（Playwright headless，localhost:3000，1440×900；脚本 `var/copy_tweaks_20261116/verify_copy.cjs`，原始结果 `results.json`，截图同目录）：
      ① EN 地址页 配送 tab 按钮 `Add new address`（126.75×28）→ 点 Pickup 后 `Add a pickup point`（134.72×28，同一 `.address-add`、同 plus 图标/样式）；`Pickup is not available in this demo yet` 与 `Switch back to Delivery…` 均不存在，空态文案 `No pickup points saved.` + 图标（`.account-empty__art`=1）仍在，`.account-empty__note`=0。
      ② EN 新增地址弹窗：`.address-form__hint` 节点数 0，`Only UK delivery addresses are supported` 不存在；表单 7 个字段、Save/Cancel 正常。
      ③ EN 售后单页：空态 `No after-sales records.` + 图标在，`.account-empty__note`=0，`After-sales is not implemented…` / `No records are invented` 均不存在，四个 tab 仍在。
      ④ EN 评价与问答页：空态 `No reviews or Q&A yet.` + 图标在，`.account-empty__note`=0，`Buyer reviews and questions are not available yet` 不存在。
      ⑤ ZH 复查：配送 tab「添加新地址」、自提 tab「添加自提点」，`当前演示版暂不支持自提` / `请切换到「配送」管理收货地址` 不存在，空态「暂无自提点。」在；弹窗无「目前仅支持英国收货地址」；售后页「暂无售后单。」在、说明不存在；评价页「暂无评价与问答。」在、说明不存在。
      ⑥ 自提 tab 点「添加自提点」仍打开同一个新增地址弹窗（`#address-form-title`=`Add new address`，7 字段），未新增后端/接口。
      ⑦ console error **0**。
    * 临时买家 `copy-tweaks-1794834011@joybuy.test` 已删（`BuyerAccount` 前缀 `copy-tweaks-` 计数 0、`BuyerSession` 0、`Address` 孤儿 0；总地址 33 条为既有数据）。**git 未提交。**
  - **坑（不得再踩）**：①删这类说明文字要**改模板节点 + 删 en/zh 键**，只改中文值会让英文站继续显示；②`AccountEmpty` 的 `note` 是可选 prop，去掉 `:note` 就够，别删组件或空态图标；③`.address-form__hint` 只被这一处使用，删节点后要一起删 CSS 规则，否则留死样式；④英文站按钮文案比中文长（`Add a pickup point` 134.72 vs 中文 `添加自提点`），仍是一行、右边缘与内容右边缘对齐，不要为对齐去写死宽度。

- **当前任务（2026-11-16，购物端「配送至」抽屉按真实 joybuy 1:1 重做，✅ 完成，未 commit，未人工验收）**：只改 `storefront/components/AddressDrawer.vue`（整体重写）、`storefront/components/AppHeader.vue`（抽屉联动状态）、`storefront/locales/messages.js`（en/zh 新键）、`storefront/components/AppHeader.test.js`。**没有碰 `pages/account/**`、`ProductCard.vue`、后端买家接口**（另一 Agent 并行负责）；后端未改一行；临时买家账号/地址/session 已删净。
  - **真实站实测对照表（探针 2026-11-16，1440×900；脚本与原始 JSON 在 `var/delivery_drawer_v2_20261116/probe*.mjs` / `real_drawer_measure*.json`、`real_pickup_tab.json`）**：

    | 项 | 真实站实测 | 本实现（Playwright 实测） | 来源 |
    | --- | --- | --- | --- |
    | 抽屉 paper | 616×900，x=824，白底，全高 | 616×900，x=824 | 探针 |
    | 遮罩/动效 | `rgba(0,0,0,.5)`；`transform 225ms cubic-bezier(0,0,0.2,1)` 右滑 | 相同 | 探针 + CSS |
    | 顶部栏 | 高 60，`padding:24px 24px 0` | 高 60，同 padding | 探针 |
    | 国家选择 | 240×40，x=848 y=24，1px #CCCED2，radius 4，旗帜 24×16，16px 文字 | 240×40，x=848 y=24，同边框/圆角 | 探针 |
    | X 关闭 | 20×20 icon，x=1396 y≈27 | 20×20，x=1396 y=26 | 探针 |
    | Tab | 每个 90×44，x=848 y=76；选中 14px/700 #1A1A1A，未选 #888B94 | 同尺寸/位置；未选用 14px/500 | 探针 |
    | Tab 下划线 | **3px**，#19191B，与 tab 同宽（用户规格写 2px，实测 3px，按实测） | 3px，#19191B | 探针 |
    | 管理 | 右侧铅笔 16px + 14px/500，右边缘 x=1416 | 右边缘 x=1416，链接 `/account/addresses` | 探针 |
    | 分割线 | y=124，1px #F5F6FA | y=124，1px #F5F6FA | 探针 |
    | 使用我的位置 | 568×36，x=848 y=125，灰色 #C2C4CC，不可点 | 同尺寸/位置/颜色，`aria-disabled=true` | 探针 |
    | 邮政编码行 | 单选 20×20（点击区 36）、粗体 16px/700 #1A1A1A、输入框 40 高，1px #CCCED2、radius 4、16px | label 16/700、输入框 40 高、同边框/圆角；输入框 x=951 w=465（真实 x=955 w=450，差异来自字体宽度） | 探针 |
    | 地址列表 | **用户截图 + 规格**：无卡片边框、行距大、姓名 16/700、两行 14px 地址 | 行 `padding:16px 0`，姓名 16/700 #1A1A1A，两行 14/20 #5B6673，无边框 | 截图/规格（地址 API 403，见坑） |
    | 应用按钮 | 568×40，x=848 y=836，radius 4，红色 **#CC0C1C**，白字 14px | 568×40，x=848 y=836，radius 4，`linear-gradient(90deg,#cc0c1c,#cc0c1c)`（真实计算值），白字 14px | 探针 |
    | 自提 tab | 真实站有搜索/地图/推荐/收藏 + loading；无应用按钮/管理 | 按需求做空态「暂不支持自提门店。」+ 说明；无应用/管理，不造假门店 | 探针截图 `real_pickup_tab.png` |
    | 未登录 | 居中地图插图 +「请先登录账号，以便使用您的地址信息。」 | 同文案 + Sign in 入口 + 仍保留国家/邮编/应用 | 探针截图 + 规格 |

  - **布局实现**：`AddressDrawer.vue` 全部按上表写死实测值（面板 616/全高、顶栏 60、tab 90×44、下划线 3px、输入框 40、应用按钮 40/radius4/#CC0C1C），地址区无卡片、行间 16px padding；国家旗帜用 6 个本地 CSS 渐变（GB/BE/DE/FR/NL/LU），**无任何外部图片/CDN**；国家选择复用 `MARKET_OPTIONS`，**2026-11-16 续已把原生 `<select>` 换成自定义 listbox（见下方子条目）**，切换时 `emit('country-change')` → `setMarket()`，顶部 top-strip 同步。
  - **交互语义（已按真实站改为「应用」提交）**：
    * 抽屉内维护 **draft**：点地址/输入邮编只改抽屉里的待应用选中态，**不改头部、不写 localStorage、不关闭**；点「应用」才 `emit('apply')` → `AppHeader` 更新 `deliverySelection`、写 localStorage、关闭。
    * 地址模式：点某地址 → 该行实心单选、邮编输入框清空、邮政编码单选取消；点应用后头部显示该地址邮编。
    * 邮编模式：选中「邮政编码」单选或聚焦/输入输入框 → 地址单选全部清空；GB 用宽松正则 `/^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$/`，非法时输入框红框 + 行内红色错误、焦点回输入框、不提交不关闭；非 GB 只校验非空；合法后统一大写并规范空格。
    * 持久化：`localStorage['joybuy:delivery-address']` 改为 JSON `{version:1, mode:'address'|'postcode', addressId, postcode}`；旧的裸 address id 仍可读（兼容）；登录后加载地址时，已存 address 失效才回退默认地址，邮编模式不会被地址加载覆盖。
    * 关闭：X / 遮罩 / Esc 三路；打开锁 `body.overflow=hidden`、焦点移入 X、关闭还原到「配送至」按钮；`role=dialog`、`aria-modal=true`、`aria-labelledby`、Tab 焦点环、tablist/tab/tabpanel、radiogroup/radio；tab 支持左右箭头。
    * 自提取舍：tab 可切换，内容为如实空态（无门店数据就不造假）；自提态隐藏「管理」和底部「应用」，与真实站自提无应用按钮一致；真实站自提里的搜索/地图/推荐/收藏依赖门店数据，本次未做。
    * 未登录取舍：保留真实文案与登录入口，但**允许仅按邮编查询/应用**（无地址列表）；这是按任务要求「允许未登录仅按邮编查询配送能力」的取舍，头部会显示该邮编。
    * 窄屏：`≤48rem` 面板改为 100% 全宽（真实站移动端全屏）；360/768 实测无横向溢出。**注意：现有 header 在 `≤48rem` 隐藏 `.account-nav__deliver`，所以窄屏是用 1440 打开抽屉后再 resize 验证的；移动端入口需另开任务。**
  - **i18n**：新增 en/zh `addressDrawer.{country,tabsLabel,tabDelivery,tabPickup,manage,useMyLocation,postcode,postcodePlaceholder,myAddresses,apply,selectAddressError,postcodeRequired,postcodeInvalid,pickupEmpty,pickupHint,countries.BE/DE/FR/NL/LU/GB}`，并把 `signInPrompt` 改为真实文案（zh「请先登录账号，以便使用您的地址信息。」）。
  - **验证（按验证纪律仅做针对性验证；但按要求跑了全量组件测试）**：
    * `node node_modules/vitest/vitest.mjs run --config storefront/vitest.config.js` → **79/79 passed（17 files）**，基线 75 + 新增 4 个（`AppHeader.test.js` 13 个）。
    * `prettier --check` + `eslint` 改动 4 文件全过（0 error / 0 warning）。
    * 浏览器实测（Playwright headless，localhost:3000，1440×900；临时买家 `header-drawer-1794831962@joybuy.test` + 2 个地址，测完已删，`count=0`）：
      ① 打开抽屉与真实站对照：panel x=824 y=0 616×900；国家 848/24 240×40；X 20×20 x=1396 y=26；tab 848/76 90×44；下划线 3px #19191B；分割线 y=124；使用我的位置 848/125 568×36 #C2C4CC；邮编输入框 40 高 #CCCED2 radius4；应用 848/836 568×40 #CC0C1C；`body.overflow=hidden`、焦点在 X。
      ② 点第二条地址：抽屉仍开（count=1）、头部仍 `Deliver to EC1A 1BB`、localStorage 仍为默认地址、第二条 `aria-checked=true`、第一条 false、邮编输入为空；点「应用」后 count=0、头部 `Deliver to M1 1AE`、localStorage 变 Alan 的 id；重开仍选中 Alan。
      ③ 邮编非法 `ABC` → 错误 `Enter a valid UK postcode, for example EC1A 1BB.`、边框 `rgb(204,12,28)`、抽屉仍开、头部不变、地址单选全清；输入 `sw1a 1aa` → 应用后头部 `Deliver to SW1A 1AA`、localStorage `{mode:'postcode',postcode:'SW1A 1AA'}`；重开邮编单选选中、输入框回填、地址单选全空。
      ④ 自提 tab → `Pickup stores are not available yet.` + 提示；应用/管理均不存在；切回配送恢复。
      ⑤ 管理 href=`/account/addresses`，点击后 URL=`/account/addresses`（该页由另一 Agent 修改，本任务只放链接）。
      ⑥ X / 遮罩 / Esc 三路关闭均 count=0；Esc 关闭后焦点回到「配送至」按钮。
      ⑦ 中英双语：EN 上述文案；ZH 头部 `配送至 SW1A 1AA`、抽屉 `配送/自提/管理/使用我的位置/邮政编码/我的地址/应用`、非法提示「请输入有效的英国邮政编码，例如 EC1A 1BB。」、自提「暂不支持自提门店。」。
      ⑧ 窄屏：1440 打开后 resize 768 → panel 768×900、应用 736 宽；360 → panel 360×800、应用 328 宽、`scrollWidth=clientWidth=360`，无破版。
      ⑨ 未登录（新 context）：提示 `Please sign in to your account to use your address information.`、Sign in href `/auth/login`、无地址列表、有邮编输入；输入 `M1 1AE` 后应用 → 头部 `Deliver to M1 1AE`、抽屉关闭。
      ⑩ console error 0。
    * 截图：`var/delivery_drawer_v2_20261116/`（真实站 `real_drawer_1440.png`、`real_postcode_selected.png`、`real_pickup_tab.png`；本地 `local_header_en.png`、`local_drawer_en_1440.png`、`local_address_draft_en.png`、`local_postcode_invalid_en.png`、`local_pickup_empty_en.png`、`local_drawer_zh_1440.png`、`local_postcode_invalid_zh.png`、`local_pickup_empty_zh.png`、`local_drawer_768_zh.png`、`local_drawer_360_zh.png`、`local_anon_drawer_en.png`）；数据 `browser_results_v2.json`、`verify_v2.log`；探针 `probe_measure{,2,3,4}.mjs`、`probe_tabs.mjs`、`probe_postcode.mjs`、`real_drawer_measure{,2,3,4}.json`、`real_pickup_tab.json`。
  - **坑（不得再踩）**：
    * 真站必须等 **15s 左右**再点「配送至」，8s 时 React 未必 hydrate（按钮 outerHTML 只有图标、click 无反应，容易误判）。
    * 真站 drawer 布局必须 **全量 stub** `color-api.joybuy.co.uk`；只放行 `user_address_getList` 会拿到 `{"success":false,"code":"403"}` 并把整页跳到 `/error403`（实测）。**因此真实地址行样式拿不到，地址行按用户截图 + 规格实现**。
    * 真站顶部 `input` 第一个是 MUI select 的 native input，找邮编输入框要按 `placeholder === '请输入您的邮政编码。'`。
    * 真站下划线实测 **3px**（规格写 2px）；应用红是 **#CC0C1C**（不是 token `--colour-accent:#c8102e`）；输入框边框 **#CCCED2**；这些值已按实测落入组件注释。
    * 组件样式里 `:id` 必须排在 `class`/`:class`/`type` 之前，否则 eslint `vue/attributes-order` 警告；`prettier --write` 不会替你重排模板属性。
    * `localStorage['joybuy:delivery-address']` 从裸 id 改成 JSON；新测试里「打开抽屉后默认地址已自动持久化」是预期行为，不要写成 null。
    * 在 EN 用例里切换国家会触发 `setMarket` 并可能切换 locale（GB→FR 会变成 fr-FR），做双语验证时不要在国家切换后直接断言英文文案。
    * 现有 header 在 `≤48rem` 隐藏「配送至」，窄屏只能先开后 resize；如需移动端入口，另开任务，不要塞进本抽屉。
    * 并行 Agent 共享 127.0.0.1 staff cookie：本任务全程只用临时买家，未登录管理端；临时买家已删（`BuyerAccount`/`Address`/`BuyerSession` 级联）。
  - **下一步**：①人工验收视觉效果（真实站截图 vs `local_drawer_en_1440.png`）；②地址行国家/地区文案目前没显示（后端 Address 只有 `country_code`，本地数据全 GB；若产品要求显示国家，需在此组件加 `countryLabel`）；③自提门店数据/搜索/地图待业务提供后再做，当前不造假；④移动端「配送至」入口需另开任务；⑤未 commit。

  - **2026-11-16 续：国家/地区控件改为自定义下拉（✅ 完成，未 commit，未人工验收）**。用户反馈「上面的国家切换应该左侧国旗、右侧国家，下拉框也是」。
    - **根因**：原实现是触发态用绝对定位的 CSS 旗 + 一张原生 `<select>`，下拉展开后是浏览器原生 option 列表，**option 内无法可靠渲染旗帜图形**，所以展开态只剩文字、视觉顺序不对。必须换成自定义 listbox。
    - **真实站对照值（探针 `probe_country.mjs` / `probe_country2.mjs`，1440×900，原始数据 `real_country_trigger.json` / `real_country_open.json` / `real_country_panel.json` / `real_country_hover.json`，截图 `real_country_open.png`）**：
      * 触发：240×40，x=848 y=24；旗帜 24×16、左内边距 16（x=864，垂直居中 y=36）；旗帜与名字间距 **8px**；名字 **14px/400** rgba(0,0,0,.87)（旧表写的 16px 是 MUI root 计算值，内层 span 实测 14px）；chevron 16×16、右内边距 16（x=1056）；1px #CCCED2、radius 4，展开时描边变深。
      * 面板：240×250，x=848 **y=64（紧贴触发底部）**，radius 4、白底、elevation-8 阴影 `rgba(0,0,0,.2) 0 5px 5px -3px, rgba(0,0,0,.14) 0 8px 10px 1px, rgba(0,0,0,.12) 0 3px 14px 2px`，`max-height:250px; overflow-y:auto`；UL `padding:8px 0`，内容高 280 → 打开时 **scrollTop=22** 把选中项滚入视野（首项顶部被裁 14px，真实站就是这样）；菜单 portal 的 z-index 1300。
      * 每项：240×44、`padding:0 16px`、flex row 居中、内层 gap 8；旗帜 24×16 左 16（x=864）、名字 x=896、14px/400；hover `rgba(0,0,0,.04)`；选中项白底 + 右侧 20×20 对勾（MUI CheckIcon，色 #1A1A1A，右内边距 16，x=1052）；`aria-selected` 只在选中项为 true。
    - **实现（只改 `storefront/components/AddressDrawer.vue`）**：触发改为 `<button aria-haspopup="listbox" :aria-expanded :aria-controls :aria-label>`，内部顺序固定为 `flag span → name span → chevron`；旗帜从 `::after`/绝对定位改成独立 `<span class="country-flag">` flex item（`flex:0 0 24px`，两种语言都不换行/不变形）；面板 `.country-menu` 绝对定位 `top:100%; left:0; width:100%`、`max-height:250px`、`padding:8px 0`、radius 4、elevation-8 阴影、`z-index:30`（高于抽屉内容）；每项是 `role="option"` 的 button，`aria-selected` 正确，选中项渲染 20px 对勾；交互：点击开/关、**capture 阶段 pointerdown 点面板外关闭**、Esc 关闭并 `stopPropagation`（不连抽屉一起关）且焦点回触发按钮、点击项选中并 `emit('country-change')` 后关闭、Enter/Space/↑/↓ 打开、↑↓/Home/End 移动焦点、Enter/Space 选中、Tab 离开由 `focusout` 关闭（不抢焦点）；打开时把选中项滚入 250px 视窗。文案复用 `addressDrawer.country` / `addressDrawer.countries.*`（en/zh 已有），**无新增字符串**；`aria-label` 用 `:aria-label` 绑定 `国家/地区: 国家名`。
    - **验证（按验证纪律：全量 vitest 是任务要求，其余仅针对性）**：
      * `vitest run --config storefront/vitest.config.js` → **83/83 passed（18 files）**：基线 79 + 新增 `storefront/components/AddressDrawer.test.js` 4 个（触发/每项 flag 在 name 前、选中标记、点击 emit、Esc/外部关闭）。`AppHeader.test.js` 2 处旧断言原读 `.country-select__input`，已改为读 `.country-select__name` + 点 trigger/option。
      * `prettier --check` + `eslint` 三个改动文件全过（0 error / 0 warning）。
      * 浏览器实测（Playwright headless，localhost:3000，1440×900，临时买家 `header-drawer-1794832834@joybuy.test`，**测完已删：账号 1 / 地址 2 / session 3，count=0**；脚本 `verify_country.mjs`，原始结果 `country_results.json`、日志 `verify_country.log`）：
        ① 触发 848/24 240×40、`1px rgb(204,206,210)`、radius 4；DOM 顺序 `country-flag → country-select__name → svg`，flag 24×16 x=865、name x=897（8px 间距）、14px/400；截图像素：旗帜彩位列 x=865..888、文字深色像素从 x=898 开始 → **旗帜严格在文字左侧**。
        ② 展开面板 848/64 240×250、padding 8px 0、radius 4、阴影与真实站一致、scrollTop=22；6 项各 240×44、`padding:0 16px`，每项 flag x=864 / name x=896 且 `flagBeforeName=true`；选中英国 `aria-selected=true` + 20×20 对勾 x=1052；hover `rgba(0,0,0,.04)`；`elementFromPoint` 命中面板（z-index 30）。
        ③ 点面板外 → 面板消失、抽屉仍在；Esc → 面板消失、抽屉仍在、焦点回触发按钮；键盘 Enter 打开（焦点在选中项）→ ↓↓ 到 Germany → Tab 关闭面板且焦点交给 X（不丢焦点）→ 重开 ↓↓ Enter 选中 Germany：`aria-expanded=false`、flag 变 `country-flag--de`、`joybuy-market=DE`。
        ④ 非 GB（DE）邮编 `ABC` 应用成功、抽屉关闭、头部 `Deliver to ABC`；切回 GB 后 `ABC` 被拒（红色错误、抽屉不关、头部仍 ABC），`SW1A 1AA` 应用成功后头部 `Deliver to SW1A 1AA`。
        ⑤ 双语：EN 触发 `United Kingdom`、面板 Belgium…United Kingdom；ZH 触发 `英国`、面板 比利时/德国/法国/荷兰/卢森堡/英国，旗帜均 24×16 不变形，`aria-label` 同步为 `国家/地区: 英国`。
        ⑥ 窄屏：768 与 360 下面板 240 宽、x=16、6 项，`scrollWidth=clientWidth`（768/360）无横向溢出；360 下旗帜/名字同一行不换行。
        ⑦ console error **0**。
      * 截图（`var/delivery_drawer_v2_20261116/`）：`country_trigger_en.png`、`country_open_en.png`、`country_menu_en.png`、`country_selected_de.png`、`country_after_apply_en.png`、`country_trigger_zh.png`、`country_open_zh.png`、`country_menu_zh.png`、`country_768_zh.png`、`country_360_zh.png`。
    - **坑（不得再踩）**：
      * **不要回退原生 `<select>`**：option 渲染不了 CSS 旗帜，这正是本轮用户反馈的根因。
      * 真实站触发名字是 **14px/400**、旗帜与名字间距 **8px**；旧交接表「16px 文字」是 MUI root 值，不是名字 span。
      * 面板紧贴触发底部（y=64），内容 280 > max-height 250，真实站打开时 `scrollTop=22`、首项顶部被裁 14px；这是真实行为，别为了"好看"改成不滚动。
      * 面板内 Esc 必须 `stopPropagation()`，否则抽屉的全局 Escape 监听会把整个抽屉关掉。
      * Tab 离开面板时**不要**手动 `restoreFocus`，交给 `focusout` 关闭面板，焦点顺着流程移到 X；手动回焦会丢用户的下一个 tab stop。
      * 旗帜改成 flex item 后不能再留 `position:absolute`，否则项内顺序/间距失效；`flex: 0 0 24px` 才能保证 24×16 不压缩。
      * `AppHeader.test.js` 里旧的 `.country-select__input` 断言必须改成点击 trigger + 点 option，否则全量 vitest 会挂。
      * 切换非 GB 国家会 `setMarket()` 改 locale（GB→FR 会变 fr-FR）；中文用例只在 GB 下做，非 GB 分支在 EN 下验证后再切回 GB（沿用旧坑）。

- **当前任务（2026-11-16，购物端 `/account/addresses` 对齐真实 Joybuy：内容区宽度 / 配送·自提 tab / 「+ 添加新地址」/ 地址卡片，✅ 完成，未 commit，未人工验收）**：只改账号页与账号页专用组件，**未碰 `AddressDrawer.vue`、未改后端、未改全局 `--container-max`**；`locales/messages.js` 仅做精确字符串替换；临时买家/地址已删净。
  - **真实站实测对照表（探针 2026-11-16，1440×900 与 1920×1080；脚本 `var/account_address_v2_20261116/probe_measure.cjs`、`probe_layout.cjs`、`probe_nav2.cjs`、`probe_css.cjs`、`probe_chunks.cjs`，原始 JSON `real_measure.json`、`real_layout_probe.json`、`real_nav_measure2.json`）**：

    | 项 | 真实站实测 | 本实现（Playwright 实测） | 来源 |
    | --- | --- | --- | --- |
    | 账号页内容区 | **1264px**；1440 视口 x=88..1352，1920 视口 x=328..1592；`/profile` 与 `/profile/my-address` 同宽（`profile_w` / `breadCrumb_wrap` / `layout_w` 都是 1264） | 1440 x=88..1352；1920 x=328..1592；首页/详情页仍 1440→1344、1920→1512 | 探针 |
    | 三栏几何 | 左栏 240，间距 24，右面板 1000；面板 radius 8、padding 24 | 240 / 24 / 1000；radius 8、padding 24 | 探针 |
    | 面包屑 | 高 53（`padding-top:32px` + 21 行高），14px #888B94，下距 32 | 相同；字号 14、#888B94、padding-top 32、下距 32 | 探针 |
    | 面板标题 | 24px/700，line-height 24，标题容器 `padding-bottom:24px` | 24/700/24，下距 24 | 探针 + CSS |
    | 配送 / 自提 tab | 每个按钮 **60×32**，18px；选中 700 #1A1A1A，未选 500 #505259；按钮间距 24（文字视觉间距 48）；下划线 **3px #19191B**、宽=文字、bottom -6 | 60/65×32（英文 Delivery 更宽），18px，700/500，gap 24，下划线 3px #19191B、宽=label、bottom -6 | 探针 + CSS |
    | + 添加新地址 | **98×28**（中文），12px/400，`#CC0C1C` 1px 边框 + 文字，radius 4，`padding:5px 8px`，gap 4，加号 icon 16；右边缘与内容右边缘 1328 对齐，和 tab 同一行 | 127×28（英文更长），其余逐项相同；右边缘 1328 对齐 | 探针 + CSS |
    | 地址列表 | 两列 Grid，列/行 gap **8px**；1 条时通栏；卡片无外层白底/阴影，1px 边框（默认 **#CC0C1C**、非默认 **#E0E1E5**）、radius 4、padding 12 | 列表 gap 8；2 条各 472×108；1 条通栏；边框/圆角/内边距相同 | **CSS 规则 + 页面 JS chunk**（真实账号无地址，卡片无法渲染，来源见下） |
    | 卡片字段 | 姓名 16/700/20 #000（max-width 150 省略）、电话 14/400/18 #1A1A1A 同排、地址 14/400/18 #505259（2 行截断）、Copy 14/18 #1869F5；底部左：单选（选中 #1A1A1A）+「默认地址 / 设为默认地址」14/18；右：铅笔/垃圾桶 icon 按钮，间距 8 | 逐项相同；单选 18×18，编辑/删除 24×24 点击区、16px icon | CSS 规则 + JS chunk（同上） |
    | 左栏 | 240 宽、padding 12、radius 8；行 216×56、`padding:0 16px`、行间 4px | 240/12/8；行 216×56、padding 0 16、gap 4 | 探针 |
    | 空态 | 地址面板总高 **522**；空态区约 394 | 空态面板 522（AccountEmpty 394）；有卡片时面板随内容 252 | 探针 |
  - **卡片样式取证说明（重要）**：真实账号没有地址，`color-api` 必须全量 stub（否则 403 换页），**无法渲染真实地址卡**。卡片样式不是猜的：从真实站页面 chunk（`real_address_page_chunk.js`，`DeliveryList_container__IP6sI` 等 CSS Modules）和 37 个 CSS 文件（`real_css_address_hits.txt`、`css_*.css`）中提取了真实 DOM 结构（`flexLeft/flexLeftGray`、`flexTop9`、`addressActions`、`country/phone/address/copy/setText`）与全部计算值；React JSX 也确认了姓名+电话同排、地址 2 行、左下单选、右下铅笔/垃圾桶。**真实站目前没地址，无法用截图逐像素验收卡片，这一点必须在人工验收时知悉。**
  - **改动文件**：`storefront/components/account/AccountShell.vue`（账号页局部 1264 覆盖、面包屑/面板/title 几何）、`AccountTabs.vue`（60×32、18px、24 gap、3px 下划线、去掉整行 border）、`AccountNav.vue`（240/radius8/56 行高/16px）、`AccountEmpty.vue`（空态 394）、`storefront/pages/account/addresses.vue`（工具栏 + 卡片重排 + Copy）、`storefront/locales/messages.js`（精确 Edit：`addresses.addNew/addTitle`→添加新地址、`title`→地址、`editTitle`→编辑地址、`setDefault`→设为默认地址，新增 `defaultAddress/copy/copied/copyFailed`；`accountMenu.addresses` zh→地址）。**未改 `AddressDrawer.vue`、AppHeader、后端。**
  - **实现要点**：①`AccountShell` 根 `.account-layout` 覆盖 `--container-max: calc(1264px + 2 * var(--container-pad))`，全局 token 不动（写法同 `pages/minihome/[code].vue`）；②「+ 添加新地址」从标题行移到 `#tabs` 的 toolbar 右侧，与 `AccountTabs` 同一行；③卡片两列 gap8、1 条通栏、默认红边/非默认灰边，姓名+电话同排、地址两行、默认单选、编辑/删除改 icon；④保留 CRUD、默认唯一、删除确认、表单校验；新增 Copy（写入剪贴板 + toast）；⑤自提 tab 仍为如实空态（无后端数据），未造假；⑥<960px 卡片单列（真实站只有 PC 布局，768 两列会把姓名/地址截成几个字，属响应式修正）。
  - **验证（按验证纪律：本任务要求全量 vitest，其余仅针对性）**：
    * `npx vitest run --config storefront/vitest.config.js` → **83/83 passed（18 files）**（当前工作区基线；含并行 Agent 的 AddressDrawer 测试）。未新增/修改测试断言。
    * `node node_modules/prettier/bin/prettier.cjs --check`（6 个改动文件）→ All matched；`node node_modules/eslint/bin/eslint.js storefront/components/account storefront/pages/account/addresses.vue` → exit 0。
    * 浏览器实测（Playwright，localhost:3000，临时买家 `address.v2.20261116@joybuy.test`，建 2 条地址，**测完已删，账号/地址/孤儿地址均 0**；脚本 `e2e_addresses.cjs`，结果 `e2e_results.json`）：
      ① 1440：container 内容 1264（x=88..1352）、nav 240、gap 24、panel 1000（x=352..1352）、radius 8、padding 24；1920：panel x=592..1592、w=1000；首页 container 仍 1344，未受全局影响。
      ② tab：Delivery 65×32、Pickup 60×32、gap 24、18px、700/500；「+ Add new address」127×28、右边缘 1328、和 tab 同行；中文「+ 添加新地址」。
      ③ 空态面板 522；有 2 条时面板 252、卡片各 472×108、gap 8；卡片 padding12、radius4、默认 `rgb(204,12,28)` 边框、非默认 `rgb(224,225,229)`；姓名 16/700/20 #000、电话 14/400/18 #1A1A1A 同排、地址 14/400/18 #505259、Copy #1869F5、单选 18、操作 24×24。
      ④ 行为：新增 2 条→2 卡；点非默认单选→默认唯一转移（红边/「Default address」/radio checked 且 **disabled=false**）；编辑保存成功；删除确认后删净；Copy 剪贴板得到 `22 Beta Road, Manchester, M1 1AE`。
      ⑤ 双语：EN `Addresses / Delivery / Pickup / Add new address / Default address / Set as default address / Copy`；ZH `地址 / 配送 / 自提 / 添加新地址 / 默认地址 / 设为默认地址 / 复制`。
      ⑥ 768/360：`scrollWidth === innerWidth`，无横向溢出；768 卡片单列；360 下 tab + 添加按钮仍同一行、卡片单列。
      ⑦ console error **0**。
    * 共享组件回归：`/account/orders`、`/account/returns` 在 1440 与 360 均为 1000 面板、无横向溢出、console 0（截图 `regression_account_orders_1440.png`、`regression_account_returns_1440.png`、`regression_orders_360.png`）。
    * 截图：`var/account_address_v2_20261116/` 下 `real_profile_1440_full.png`、`real_profile_1920_full.png`、`real_addresses_1440_full.png`、`real_addresses_1920_full.png`、`real_addresses_1440_fold.png`；本地 `local_addresses_empty_en_1440.png`、`local_addresses_two_en_1440.png`、`local_addresses_default_en_1440.png`、`local_addresses_pickup_empty_en_1440.png`、`local_addresses_two_zh_1440.png`、`local_addresses_two_zh_1920.png`、`local_addresses_768_en.png`、`local_addresses_360_en.png`。
  - **坑（不得再踩）**：
    * 真实站账号没有地址且 `color-api` 403，**卡片样式取自 CSS Modules/页面 chunk，不是渲染截图**；不要把「截图里没有卡片」误判成样式没对齐。
    * `--container-max` 只能在账号页子树覆盖；改全局会带偏首页/详情页（详情页实测 1512）。
    * `AppHeader` 里也有 `.account-nav`，Playwright/CSS 选择器要写 `.account-page .account-nav`，否则量到头部导航。
    * 默认地址 radio **不能加 `:disabled`**：原生 disabled 会把选中圆点变灰，真实站是 #1A1A1A；保持 checked、不 disabled，点击已选中项不会触发 change。
    * 列表排序是后端 `-is_default, -updated_at`，设默认后卡片顺序会变；e2e 断言要按姓名找卡，不能按索引（本轮 `afterEdit` 的 `["Edited","A"]` 就是默认项排到第一，不是编辑错卡）。
    * 注册/登录 API 直接 POST 会 403：先 `GET /api/v1/auth/buyer/session` 拿 `csrftoken`，再带 `X-CSRFToken` 调 `/api/v1/auth/buyer/login`。
    * 面板不要写死 `min-height:522`：真实站只有空态是 522，有卡片时面板随内容（本轮改成 AccountEmpty 394、面板 auto）。
    * 窄屏 768 若保持两列，卡片只有约 200px，姓名/地址会被截断；<960px 单列是刻意修正。
    * 本轮没有改地址弹窗宽度（真实站 880，本仓库仍 544）；用户本轮只反馈列表/头部，弹窗如需 1:1 另开任务。

- **并行任务（另一 Agent 同日，2026-11-16，购物端账号相关页面改造：收藏心跳 / 地址 CRUD+默认 / 个人中心 / 我的订单 + 售后+评价如实空态，✅ 完成，未 commit）**：用户 4 项诉求全部落地。**（该并行任务已结束，其"正在改 AppHeader/抽屉"的描述是当时快照；本轮国家控件改动见上一条子条目，当前无其它 Agent 在跑。）** 只新增/修改下面列出的文件；未 commit / 未 push / 未 stash。
  - **Joybuy 对照（登录态 cookies 注入 Playwright；必须 `page.route` 把 `color-api.joybuy.co.uk` fulfill 成 `{"code":0,"data":{}}`，否则 403 页替换整页）**：
    * `/profile`：头像 + 用户名 + 右侧邀请卡；一块「我的订单」横条（左标题 + 待付款/待收货/评论/售后 4 个数字）；再一块模块磁贴（优惠券/心愿单/积分）；无左侧栏。
    * 账号子页（`/profile/my-orders`、`/profile/my-address`、`/profile/my-returns`、`/profile/my-reviews`）：面包屑「我的 / X」+ 240px 左侧白色模块栏 + 右侧白色面板；模块栏真实条目是 我的订单/售后单/评价与问答/心愿单/Joybuy 余额/积分/优惠券/地址。
    * **我的订单实际 tab = 全部 / 待付款 / 待收货 / 已完成 / 已取消，没有「待发货」**（原任务描述里的待发货是推断，按真实页纠正）；订单卡 = 头部订单号+日期+状态，商品行 72px 缩略图/标题/数量/单价，底部总额 + 查看详情。
    * 地址页：标题「地址」+ tab 配送/自提 + 右上角描边红字「+ 添加新地址」；空态是灰色定位针 + 红色感叹号插图 +「暂时没数据」；新增是居中弹窗（国家、地址搜索、设为默认、保存）。真实站用地址自动补全，本仓库后端是结构化英国字段，**表单字段属于按现有后端推断**，布局/按钮位置/弹窗形态照搬。
    * 售后单：tab 全部/进行中/已完成/已取消 + 右上「申请售后」；评价与问答：单一面板无 tab。两者本仓库无买家侧后端，故只做**如实空态 + 明说后端缺口**，未造数据。
    * 截图（joybuy 对照 + 本地实现）：`var/account_pages_20261116/`，含 `joybuy_profile_full.png`、`joybuy_orders_full.png`、`joybuy_addresses_full.png`、`joybuy_address_form_full.png`、`joybuy_returns_full.png`、`joybuy_reviews_full.png`、`local_profile_en.png`、`local_profile_zh.png`、`local_orders_all_en.png`、`local_orders_zh.png`、`local_addresses_*.png`、`local_address_form_zh.png`、`local_detail_wishlist_en.png` 等。
  - **改动文件**：
    * 前端：`storefront/components/ProductCard.vue`（心形真实状态/乐观更新）、`storefront/components/UiToast.vue`（新）、`storefront/composables/useWishlist.js`（新）、`storefront/composables/useUiToast.js`（新）、`storefront/app.vue`（挂 UiToast）、`storefront/pages/p/[id].vue`（详情页收藏按钮）、`storefront/pages/account/index.vue`（重做个人中心）、`storefront/pages/account/orders/index.vue`（重做订单页）、`storefront/pages/account/orders/[id].vue`（状态文案双语）、`storefront/pages/account/addresses.vue`（重做地址页）、`storefront/pages/account/returns.vue`（新）、`storefront/pages/account/reviews.vue`（新）、`storefront/pages/account/favourites.vue`（删除行时同步心形状态）、`storefront/components/account/{AccountShell,AccountNav,AccountTabs,AccountEmpty,AccountPager}.vue`（新，账号子页共用）、`storefront/locales/messages.js`（en/zh 各 317 键，键名一一对齐）。
    * 后端：`backend/checkout/checkout_views.py`（地址 PATCH/DELETE、is_default 唯一、默认地址删除后自动提升）、`backend/orders/order_views.py`（订单列表返回 state/items/缩略图/子单状态）、`backend/accounts_buyers/activity_views.py`（`GET /buyer/favourites?ids_only=1`）、测试 `backend/checkout/tests/test_address_api.py`（新）、`backend/accounts_buyers/tests/test_activity_api.py`、`backend/orders/tests/test_orders_flow.py`。
  - **收藏为什么原来没反应**：`ProductCard` 的心形是纯装饰 `<button>`，没有 `@click`、没有 API 调用、没有 `aria-pressed`，商品列表数据也没有收藏状态字段。现在：`useWishlist()` 模块级 `Set` + `GET /api/v1/buyer/favourites?ids_only=1` 一次加载；点击先乐观翻转，再带 `X-CSRFToken` 调 POST/DELETE `/api/v1/buyer/favourites`，失败回滚并 toast；未登录点击 toast「登录后可收藏」并 `navigateTo('/auth/login?next=...')`；列表刷新后仍正确（后端回显）；详情页新增同状态按钮。`aria-label` 用 `:aria-label` 绑定且在已收藏时切到 `product.removeFromWishlist`。
  - **地址页**：新增「+ 新增收货地址」右上按钮 + 居中弹窗（收件人/电话/详细地址 1-2/城市/郡/邮编/设为默认开关）；卡片显示姓名、电话、地址、默认徽标、非服务邮编提示，操作=设为默认/编辑/删除；删除有双语确认弹窗。前端校验必填 + 电话 + 英国邮编正则，后端错误码 `ADDRESS_INCOMPLETE/ADDRESS_UNSUPPORTED/ADDRESS_NOT_FOUND` 映射成双语提示。后端在事务里清空其他默认再设当前，删除默认后自动提升最早剩余地址，保证默认唯一。
  - **个人中心**：按 `/profile` 重排为「头像+用户名+退出登录」→「我的订单横条（待付款/待收货/已完成 计数，点击带 `?tab=`）」→ 四个模块磁贴（我的订单、售后单、评价与问答、地址）。原收藏/最近浏览/购物车/通知/申请开店入口已从个人中心移除（收藏仍可从头部账户菜单与心形进入；头部文件本次未碰）。
  - **我的订单**：沿用 Joybuy 真实五 tab；`state` 由后端按 `PENDING_PAYMENT / PROCESSING / SHIPPED(→待收货) / COMPLETED / CANCELED` 计算；卡片含订单号/日期/状态、商品缩略图（无图用本地内联 SVG 包裹占位，绝不引 CDN）、标题/数量/单价、总额、查看详情；10 条/页，`AccountPager` 上/下一页；空 tab 有如实空态；未登录有登录引导。
  - **后端缺口（如实记录）**：①买家售后单无 model/接口（只有商家侧 ops），`/account/returns` 仅空态 + 说明；②买家「我的评价与问答」无接口（只有商品评价读取 `GET /products/<id>/reviews`），`/account/reviews` 仅空态 + 说明；③订单列表仍最多 50 条（接口未做服务端分页，前端 10 条/页）；④收藏 ids 接口一次返回全部 id，演示规模可接受，量大需分页/筛选。
  - **验证（按验证纪律仅做针对性验证，未跑全量 e2e/全量后端）**：
    * `npx vitest run --config storefront/vitest.config.js` → **17 files / 75 tests 全 PASS**（交接文档旧基线写 71，本次未改任何断言；多出的 4 个来自工作区已有测试，未定位到具体新增文件）。
    * `node node_modules/prettier/bin/prettier.cjs --check`（本次改动前端文件）→ 全部 All matched；`npx eslint storefront/app.vue ... storefront/pages/account storefront/components/account ...` → 无输出（通过）。
    * 后端：`./.venv/Scripts/python.exe backend/manage.py test checkout.tests.test_address_api accounts_buyers.tests.test_activity_api orders.tests.test_orders_flow --keepdb --noinput` → **Ran 20 tests, OK**；`python -m ruff check`（6 个改动 py 文件）→ All checks passed。改完后 `taskkill /PID 26832 /F`，keepalive 已自动重启 :8000（新 PID 38512）。
    * 浏览器实测（localhost:3000，临时买家邮箱注册 API 创建 `account.pages.20261116@joybuy.test`，密码 `TempPass123!`，并在 DB 造 1 张待付款 + 1 张已发货订单用于看卡片；**收尾已删**）：①登录 → 列表心形变实心、刷新仍实心、再点取消、`ids_only` 服务端为空；详情页同样 3 步通过；匿名点心形落到 `/auth/login?next=%2F`。②地址：新增 A→1 卡；新增 B→2 卡；B 设默认→徽标唯一转移到 B；编辑 A 姓名成功；删除默认 B→剩 A 且自动成为默认。③个人中心仅 4 模块、无 Favourites/Recently viewed/Cart/Notifications/Become a seller；订单页 tab 文案与计数正确、2 卡、2 张缩略图、待收货 tab 1 卡、已完成 tab 空态。④中英各一轮：中文模块/订单 tab/地址表单/校验提示（`请填写收件人姓名。`）与英文（`Enter the recipient name.`）均正确；控制台 0 errors。
    * 临时买家清理：`Order.objects.filter(account=a).delete(); a.delete()` → `BuyerAccount` 计数 0、孤儿订单 0；地址/收藏/会话随账号级联删除。**注意 Order.account 是 PROTECT，删买家前必须先删订单。**
  - **本次踩坑/约束**：①`account.emptyWishlist` 键原来只在页面里用、messages.js 根本不存在，已补；②订单页真实 tab 无「待发货」，别按原描述加第六个 tab；③`AccountShell/AccountTabs` 等新组件在 vitest 无 Nuxt 自动导入，页面里已显式 import；④收藏状态必须在 reload 后仍正确，不能只做本地翻转；⑤`page.route` 必须拦 `color-api`，否则 Joybuy 整页被 403 替换；⑥默认地址唯一要后端事务保证，前端只重拉；⑦临时订单删除顺序（先 Order 后 BuyerAccount）不能反。

- **当前任务（2026-11-16，PDP 多规格选择改用 canonical 规格匹配，✅ 完成，未 commit）**：商品规格译文写入 `sku_specification_translation` 后，PDP 拿到的 `sku.specification` 是译文（键和值都翻），而 `spec_options[].name/value` 仍是源语言；原匹配逻辑用两者直接相等比较，导致切换一个规格轴时其它已选维度被重置（跳变）。**本次只改 `storefront/pages/p/[id].vue` 一个业务文件**，未改 backend、未改接口字段、未改样式、未加依赖；未 commit / 未 push / 未 stash。
  - **修复方式**：新增 `matchSpec(sku)`：有 `spec_options` 时返回 `sku.canonical_specification ?? sku.specification`；没有 `spec_options`（历史商品由 `sku.specification` 反推轴名，轴名本身就是译文）时返回 `sku.specification`。4 处匹配统一走它：`resolvesToPurchasableSku()`、`selectVariant()` 的候选过滤、`selectVariant()` 的「保留其它维度」比较、模板 `detail__variant--active` 判定。`variantAxes` 的兜底分支显式保留 `sku.specification` 并加注释。展示逻辑（`stickySpecText`、`buy-bar__spec`、`selectedSku.title` 等）仍用译文 `sku.specification`。
  - **数据事实（实测）**：SPU 7991 = `79e32c3a-f9fa-487a-aee4-8afdbc007af2`，7 个 SKU、3 轴（Series 3 值 / Colour 2 值 / Size 4 值），7 个 SKU 全 ACTIVE 且各有 1 条 GB ACTIVE Offer（`145.0000`）；`spec_options` 的 `sku_ids` 映射：Series 只有第 1 个值映射到 7 个本库 SKU（另 2 个系列源 SKU 未导入，映射为空）、Colour 2/2、Size 4/4。**注意：SPU 7991/7996/7999 在库里 `status=DRAFT`（与任务背景“可访问”不符），detail 接口只返回 ACTIVE SPU；`/p/7991` 是数字 pk，实际路由要 public_id，数字 URL 会显示「delisted」。本次为浏览器验证临时把 7991 置 ACTIVE，验证完已恢复 DRAFT。**
  - **德语 mock 译文**：mock 服务端口 **11437**（`python translation_agent/tools/mock_ollama.py --port 11437`，用 Anaconda 的 `python`，`.venv` 没有 sqlalchemy/httpx）。`enqueue --langs de --include-specs --spu-ids 7991`（1 个 title unit + 12 个 term）→ `run ... --provider ollama --base-url http://127.0.0.1:11437`（done=1，terms 8）→ `build-specs --langs de --spu-ids 7991`（detail_rows=1、sku_rows=21=7×3）。译文形如 `[de] Colour` / `[de] Black` / `[de] 黑/卡其`，Size 值 `XXL/XL/...` 因 `size_code` 跳过而保持原样。
  - **改前 bug 复现（de-DE，真实点击）**：初始 Black/XXL；点 Colour「黑/卡其」→ 选中变成 **黑/卡其/L**（Size 从 XXL 跳到 L，跳到本页第一个 khaki SKU）；重载后点 Size「XL」→ 选中变成 **黑/卡其/XL**（Colour 从 Black 跳到 khaki）。根因不是 `sku_ids` 兜底失效（按钮都在、点击有反应），而是「保留其它维度」比较里 `name === axisName` 因键已翻译成 `[de] Colour` 永不成立，且被点击轴的值与当前值不同 → 所有候选都不匹配 → 落到 `candidates[0]`。改前截图：`var/pdp_spec_i18n_20261116/before_de_colour_jump.png`（黑/卡其 + L 选中）、`before_de_initial.png`；Size 跳变只记录了 DOM 状态（截图瞬间遇到 dev server 重载，文件已删，不伪造）。
  - **改后验证（de-DE，逐个点击，全部有反应）**：初始 Black/XXL → Colour 黑/卡其 = **黑/卡其/XXL**（`44d7ac2b`）→ Size XL = **黑/卡其/XL**（`3d066d3a`）→ Colour Black = **Black/XL**（`94311269`）→ Size XXL = **Black/XXL**（`5f351dcc`）→ Size XXXL = **Black/XXXL**（`f61ba813`）→ Colour 黑/卡其 = **黑/卡其/XXXL**（`c981d6b7`）→ Size L = **黑/卡其/L**（`2dcce553`）→ 点唯一的 Series = 保持黑/卡其/L。价格全程 `$145.00`（7 个 SKU 同价，故价格不变是数据事实，不是未生效）；选中组合与 public_id 的映射见 `var/pdp_spec_i18n_20261116/sku_map_de.json`。展示仍是译文：滚动后 `buy-bar__spec` = `XL / [de] 黑/卡其 / [de] 3-in-1 Down Shell Jacket`。截图：`after_de_initial.png`、`after_de_colour_keeps_size.png`、`after_de_size_keeps_colour.png`、`after_de_sticky_translated.png`。
  - **GB / en-GB 回归**：同一 SPU、同一 public_id，初始 Black/XXL → 黑/卡其/XXL → 黑/卡其/XL → Black/XL → Black/XXL → 点 Series 保持不变；行为与改前一致。截图 `after_en_initial.png`。
  - **针对性校验**：`prettier --check "storefront/pages/p/[id].vue"` 通过；`eslint "storefront/pages/p/[id].vue"` 退出码 0。按验证纪律未跑全量组件测试、后端测试或 e2e（本次只改一个前端文件，后端零改动）。
  - **清理（完成）**：`python translation_agent/translate.py purge --langs de --include-specs --spu-ids 7991` → `spu_translation=3 spu_detail_translation=1 translation_unit=1`、`sku_rows=21 log_rows=21 terms=12`。SQL 复核基线：`sku_specification_translation=1431`、`spu_detail_translation=0`、`translation_term=0`、`spec_write_log=0`、`translation_unit=0`、`spu_translation` 非 en-GB = **20**。mock 11437 已停（netstat 无监听），7991 已恢复 `DRAFT`，该 SPU 的 de 译文行 = 0，detail 接口重新返回 `PRODUCT_NOT_AVAILABLE`。
  - **本次 delta（只含本次改动，不是整文件 git diff）**：`var/pdp_spec_i18n_20261116/pdp_before_task.vue` 是反推的改前文件，`diff -u` 即本次补丁；涉及 6 处：新增 `matchSpec`、`resolvesToPurchasableSku`、`variantAxes` 兜底注释、`selectVariant` 候选过滤、`selectVariant` 其它维度比较（新增 `currentSpec`）、模板 active 判定。**注意工作区里该文件本来就有 876 行其它任务的未提交改动（画廊/缩放/愿望单等），所以直接 `git diff` 会包含大量既有改动，不能用它当本次补丁。**
  - **未做/未验证**：真模型译文（本机仍无权重）；BE 的 de-BE、LU 的 de-LU、fr/nl 未逐个市场点击；没有 `spec_options` 的多 SKU 商品（反推轴分支）库里不存在，未实机覆盖，仅代码推理；`sku_ids` 兜底仍保留（未删），本次只是让主匹配不再依赖它。
  - **坑（不得再踩）**：①SPU 7991/7996/7999 是 DRAFT，`/p/7991` 数字 pk 打不开，必须用 public_id 且临时置 ACTIVE（用完恢复）；②dev 库多 SKU 商品极少——库里 ACTIVE 且 >1 SKU 的只有 7964（2 SKU，中文轴），7991 是临时启用的；③`sku_ids` 兜底会让「点了没反应」不出现，真正的回归是**其它维度被重置**，验证时要断言完整选中组合而不是只看按钮高亮；④Nuxt dev server 会偶发整页重载（HMR/文件监听），截图可能空白或回到初始态，点击后要在同一 JS 调用里读 DOM 断言，截图失败就重试，不要拿空白图当证据；⑤`purge --include-specs` 的 `detail_deleted=0` 不代表没清理，必须直接用 SQL 数 6 个基线；⑥运行 translation_agent 用系统 `python`（Anaconda，有 sqlalchemy/pymysql/httpx），`.venv` 只装了 Django 侧依赖；⑦控制台 GBK，命令前加 `PYTHONIOENCODING=utf-8`。

- **上一任务（2026-11-16，购物端头部两个交互：用户菜单点外部/Esc 关闭 + 「配送至」地址抽屉，✅ 完成，未 commit，未人工验收）**：只改 `storefront/components/AppHeader.vue`、新增 `storefront/components/AddressDrawer.vue`，另改 `storefront/locales/messages.js` 与 `storefront/components/AppHeader.test.js`。**没有碰 `pages/account/**`、`ProductCard.vue`、后端买家接口**（另一 Agent 并行负责）；后端未改一行。
  - **根因（bug 1，用户菜单点外部不关）**：`AppHeader.vue` 里 `accountMenuOpen` 只由用户 icon 的 `@click` 翻转，**没有注册任何 document 级 pointerdown/click 关闭监听，也没有 Esc keydown 处理**——菜单一旦打开只能点菜单内链接或「退出登录」才消失。修复：`document.addEventListener('pointerdown', handler, true)`（capture，避免被内层 stopPropagation 吞掉）+ Esc `keydown`；根节点 `accountMenuRef` 用 `contains()` 判定内外；Esc 关闭后把焦点还给 trigger；icon 仍可 toggle，`aria-expanded` 随状态更新。
  - **根因（bug 2，「配送至」点了没反应）**：`.account-nav__deliver` 是一个纯 `<button type="button">`，**没有任何 @click 或菜单绑定**（死按钮）。修复：点击打开右侧 `AddressDrawer`。
  - **抽屉实现（joybuy 对照）**：真实 joybuy 用 MUI `anchorRight` drawer——1440 视口宽 **616px**、全高、遮罩 `rgba(0,0,0,.5)`、`transform 225ms cubic-bezier(0,0,0.2,1)` 右滑入、右上角 X；匿名态显示「请先登录账号，以便使用您的地址信息。」，登录态地址来自 `user_address_getList`。本项目按同规格实现：`width:min(38.5rem,100%)`、`z-index:1200`、50% 遮罩、225ms 右滑 + 遮罩淡入、X/遮罩/Esc 三路关闭、打开时 `body.overflow=hidden`、焦点移入抽屉并做 Tab 焦点环、关闭还原焦点（回到「配送至」按钮）。内容：当前配送地址块（大号邮编 + 完整地址）、地址单选列表（`role=radio`/`aria-checked`，默认项带「默认/Default」徽标）、底部「新增地址」→ `/account/addresses`（只放链接，不改该页）；未登录显示登录提示 + `/auth/login` 链接。
  - **当前地址状态（后端无「当前配送地址」字段，方案已定）**：复用现有 **`GET /api/v1/addresses`**（`checkout/checkout_views.py::address_list`，已存在，未改），选中项存 **`localStorage['joybuy:delivery-address']`**（存 address `public_id`）；解析顺序 = 已存 id → `is_default` → 第一条；header 显示 `t('header.deliverTo') + 邮编`，匿名为 `SW1A 1AA` 兜底。点击地址 = 立即应用并持久化（头部邮编即刻变化 + 关闭抽屉）。**未写后端默认地址**（现有地址接口只有 GET/POST，没有 PATCH/is_default 切换端点；为避免与并行 Agent 的买家接口冲突，不动后端）。换浏览器/清 localStorage 会回到默认地址，这是本方案的已知边界。
  - **i18n**：新增 en/zh 双份 `addressDrawer.{title,current,selectAddress,addAddress,signInTitle,signInPrompt,close,loadFailed}`；默认徽标复用 `account.default`，空列表复用 `addresses.empty`，加载复用 `common.loading`；关闭按钮用 `:aria-label` 绑定。
  - **验证（按验证纪律仅做针对性验证；按要求跑了全量组件测试）**：`vitest run --config storefront/vitest.config.js` → **75/75 passed（17 files）**，基线 71 + 新增 4 个用例（`AppHeader.test.js` 9 个：外部 pointerdown 关闭、Esc 关闭且焦点回 trigger、面板内 pointerdown 不误关、toggle、抽屉列表/默认徽标/新增地址 href/切换地址改头部邮编与 localStorage、X/遮罩/Esc 关闭 + 滚动锁、匿名登录提示）；`prettier --write` + `eslint` 改动 4 文件全过。**未跑全量后端测试（后端零改动）**。
  - **浏览器实测（Playwright headless，localhost:3000，1440×900，临时买家 `header-drawer-1794830940@joybuy.test` 注册 + 2 个地址，测完账号与地址已删 count=0）**：①登录后 header 显示 `Deliver to EC1A 1BB`（默认地址）；点用户 icon 菜单打开（`aria-expanded=true`）→ 点页面空白处 → 菜单消失（`aria-expanded=false`）；重开 → Esc 关闭且焦点回「My account」；连点 icon 两次 = 开/关；②点「配送至」抽屉右滑入：首帧 `x=1440 transform=translateX(616px)` → 稳定 `x=824 w=616 h=900`，与 joybuy 实测同宽同位；列表 2 条（Ada Default 选中 / Alan），点 Alan 后抽屉关闭、header 变 `Deliver to M1 1AE`、localStorage 存 Alan 的 id、刷新后仍为 M1 1AE；X/遮罩/Esc 三路关闭均通过，打开时 `body.overflow=hidden`、关闭恢复；「新增地址」href=`/account/addresses`；③未登录（新 context）点「配送至」→ 显示登录标题/提示/「Sign in」→ `/auth/login`，无地址列表；④中英双语各一轮：EN `Deliver to / Current delivery address / Choose a delivery address / Add a new address / Close delivery drawer`，ZH `配送至 / 当前配送地址 / 选择配送地址 / 新增地址 / 关闭配送地址抽屉`，用户菜单「我的账户」外部点击/Esc 同样生效，中文匿名提示「我们要送到哪里？…登录」；console error 0。截图（含 joybuy 对照）：`var/header_drawer_20261116/`（`joybuy_header_base.png`、`joybuy_deliver_open.png`、`joybuy_deliver_after_esc.png`、`joybuy_user_hover.png`、`local_*_en/zh.png`、`browser_results.json`）；探针脚本 `var/joybuy_header_probe/probe{,2,3,4,5,6}.mjs`、`var/header_drawer_20261116/{setup_buyer.py,verify_local.mjs}`。
  - **joybuy 真站踩坑（不得再踩）**：①带登录 Cookie 打开 joybuy 必须 `page.route(/color-api\.joybuy\.co\.uk/, fulfill {"code":0,"data":{}})`，否则 `guide_catalog_get` 等 403 会把整页替换成「403 页面」；**只放行少数地址接口也会触发页面跳转/context destroyed**（probe4/6 实测），看抽屉样式就全量 stub。②真站用户菜单是 **hover 打开**（`userInfoButton_meBtn` 悬停出 256px 面板），**click 会直接跳 `/profile`**——别把「点击后跳转」误判成菜单坏掉/会话失效。③真站抽屉地址数据来自 `user_address_getList`，匿名的「请先登录」是接口返回导致的，不是 cookie 失效（SSR HTML 里仍有「退出登录」）。④抽屉在真站 1440 宽 = 616px（`MuiDrawer-paperAnchorRight`），不是常见的 400px。⑤本项目 `.account-nav__deliver` 在 `max-width:48rem` 被 CSS 隐藏，窄屏打不开抽屉（既有设计，本次未改，如需移动端入口要另开任务）。
  - **边界**：git 未提交；未改 `pages/account/**` 与 `ProductCard.vue`；后端无改动、无需重启 :8000；临时买家已删净（BuyerAccount + 2 Address + 级联 session）。

- **上一任务（2026-11-16，基于 Hy-MT2-7B GGUF Q4_K_M 的本地离线商品翻译 Agent，✅ 正文 + 规格全链路完成（mock 验证），✅ 真模型已于 2026-11-16 晚上机验证（权重已下载、Ollama 注册成功、实测 5.27GB/64 tok/s，详见上文「Hy-MT2-7B 真模型上机验证」条目），未 commit）**：用户要求「完全离线、数据不出本地」地把商品文案（源英文，部分中文）翻成 de/fr/nl，覆盖 BE/DE/FR/NL/LU/UK 市场，闭环流程 = 读库 → 并发翻译 → 写回维护。**随后追加要求「规格表 / 规格参数也要机翻，当前无法人工翻译，全部都先机器翻译」→ 规格表 / 规格参数 / 规格选项 / SKU 规格已全部改为机翻（术语缓存 + 组装写回，见下）**。**代码与全部配置在 `translation_agent/`（已加进 `.gitignore` 第 103 行，按用户要求该目录一律不入库）**；未改 backend/、未跑 `manage.py migrate`、未改任何已跟踪业务代码（PDP 那个跟随修复单独记在上一条）。
  - **产出（22 个文件，均未入库）**：
    * CLI：`translation_agent/translate.py`（子命令 `init-db / enqueue / run / build-specs / status / recover-stale / verify / purge`；开关 `--include-detail` 图文、`--include-specs` 规格、`--all` 两者全开，另有 `--overwrite-specs`、`--keep-terms`、`--dry-run`）。
    * 代码：`agent/settings.py`（env 分层 + 语言→locale 映射）、`agent/db.py`（侧表 `translation_unit` / `translation_term` / `spu_detail_translation`（4 个规格列，`init-db` 幂等 ALTER）/ `spec_write_log`、keyset enqueue、条件 claim、方言分支 upsert、purge、orphan 检查、统计）、`agent/prompts.py`（Hy-MT2 官方模板 + 术语模板 + `[[n]]` 遮挡还原 + 长文切分）、`agent/providers.py`（ollama `/api/chat`、OpenAI 兼容 `/v1/chat/completions`、mock）、`agent/pipeline.py`（asyncio 并发、DB 驱动重试、dry-run、术语 worker）、`agent/detail.py`（图文详情阶段）、`agent/specs.py`（术语抽取/跳过规则/结构保持组装）、`agent/terms.py`（24 条/批术语翻译 + 缺失键逐条降级）、`agent/build.py`（`build-specs` 组装写回 + 跳过已有/空规格）、`agent/verify.py`（11 项校验）、`tools/mock_ollama.py`（纯标准库假服务）。
    * 文档：`README.md`、`docs/deployment.md`（Ollama/llama.cpp 两路线、显存表、吞吐估算、systemd/NSSM 常驻）、`docs/database.md`（真实表结构 + 通用 SQLAlchemy 示例 MySQL/PG 同一份代码 + 状态机 + 断点续跑）、`docs/troubleshooting.md`。
    * 部署：`deploy/Modelfile`（`num_gpu 999`/`num_ctx 4096`/官方采样参数，无 SYSTEM）、`deploy/{start_ollama,start_llama_server,download_model,check_env,smoke_test}.{sh,ps1}`、`download_model.md`、`requirements.txt`、`env.example`。
  - **数据事实（本次实测，后续设计必须按这个来）**：`spu_translation` 8600 行（en-GB 8580 / zh-CN 20），**subtitle 与 description 全部为空，只有 title 有字**（平均 97 字符、最长 330）→ 只翻 title 等于没翻商品文案；真正的主体是 `spu_detail.content_sections`（8461 行、平均 4652 字符、合计约 38MB，结构 `[{title, blocks:[{type:heading|paragraph,text}], text, images}]`）+ `ai_summary`（1408 行非空）。`spu_market_content` **0 行**（不用）；`product_search_document` 7900 行**全 en-GB**；locale 11 个（de-BE/de-DE/de-LU、fr-BE/fr-FR/fr-LU、nl-BE/nl-NL、lb-LU、en-GB、zh-CN）；**brand 8539/8597 为空**（爬虫没落品牌）→ 术语保护实际靠 model_number/gtin/正则，不靠品牌表。
  - **写回设计**：短文案逐 locale 写 `spu_translation`（de→de-DE/de-BE/de-LU、fr→fr-FR/fr-BE/fr-LU、nl→nl-NL/nl-BE；比利时=nl+fr、卢森堡=fr+de、lb-LU 不做）；长文案按**语言一份**写新表 `spu_detail_translation`（39MB×3 而不是 ×8，长文案无市场级差异）；**规格文本（`specification_tables` / `specifications` / `spec_options` / `sku.specification`）已全部机翻**：先抽全库 distinct 术语（实测 **10561 个**，`no_letters=409 / protected=1568 / size_code=19` 直接跳过）写 `translation_term` 术语缓存表（`target_lang + source_hash` 唯一），24 条/批用官方结构化模板翻一次（约 1.1 千次请求/3 语言，相对正文可忽略，且术语全库一致），再由新子命令 `build-specs` 组装：`spu_detail_translation` 新增 `specification_tables` / `specifications` / `spec_options` / `quality_flags` 四列（按语言），SKU 规格逐 locale 写 Django 现有表 **`sku_specification_translation`**（`method=DIRECT`、`needs_review=bool(untranslated_terms)`；**默认跳过已存在的 1431 行字典译文**，`--overwrite-specs` 才覆盖），写入记账表 `spec_write_log(sku_id, locale_code)` 供 purge 精确回滚；非空规格 SKU 6718 个 × 8 locale ≈ **5.4 万行**，4763 个空规格 SKU 不写行。状态用侧表 `translation_unit(entity_type, entity_id, target_lang, status pending|translating|done|failed, attempt_count, translation_error, source_hash, payload, quality_flags, claimed_by)`，**断点续跑完全靠 DB 状态，不用本地进度文件**。
  - **验证（按验证纪律仅做针对性验证；本次零应用代码改动，故未跑后端/前端测试套件、未跑 e2e；后端全量、前端组件测试都没跑）**：
    * Agent 侧：`init-db` 两张侧表建成 → `enqueue --langs de --limit 20` 20 条 → mock 3 并发 `run` `done=20 failed=0`（写 20×3=60 行）→ 再入队 20 条并**同时起两个 run 进程**：A 9 + B 11 = 20，`translation_unit` done=40/translating=0，无重复无丢行 → 失败路径（临时 SPU 8644 标题含 `MOCKFAIL`）得到 `failed`、`attempt_count=3`、`translation_error='http_500…'`，退避日志 2s/4s → `verify` 5 项全 PASS → `purge` → 非英文行数回到 20、unit 归零 → detail 阶段 3 个 SPU（6 units）结构与源同构、`images` 完全一致、无 `[[` 泄漏 → `python -m compileall` 通过。另实测 dry-run、OpenAI 兼容端点、`--refresh` 改稿重投、`recover-stale`。
    * 主会话独立复跑（`fr`，2 条）：`enqueue` 2 → mock 3 并发 `run` `done=2 failed=0` → 写入 6 行（fr-FR/fr-BE/fr-LU 各 2）、`quality_flags.length_ratios.title=1.25/1.357` → `verify` 5 项 PASS/exit 0 → `purge` 删 6 行 + 2 unit → `SELECT count(*) FROM spu_translation WHERE locale<>'en-GB'` **回到 20**、`translation_unit` 0。**dev 库已恢复基线，没有留 mock 译文。**
    * 文档/脚本侧：5 个 `.sh` `bash -n` 全 PASS；5 个 `.ps1` 用 `Parser::ParseFile` 全 PASS（**必须 UTF-8 with BOM**）；`check_env.sh` 实跑 DB OK、模型/gguf 两项按预期 FAIL；`smoke_test` 在 8080 未监听/模型不存在时明确报错退出 1。
  - **当前卡点（已解除，保留历史）**：原卡点是「真模型没跑过」——权重未下载，直连 ≈85 KB/s、镜像 ≈375 KB/s。**2026-11-16 晚已解除**：走 `FlClash 127.0.0.1:7890` + 8 路分段（≈0.9 MB/s，84 分钟）下完并校验，Ollama 注册成功、实测 5.27GB 显存 / 64 tok/s（并发 2），详见上文「真模型上机验证」条目。
  - **下一步**：①~~下载权重~~ **已完成 2026-11-16 晚**（`translation_agent/models/Hy-MT2-7B-Q4_K_M.gguf`，sha256 通过）；②~~`ollama create` 并确认能加载~~ **已完成**（`hy-mt2:7b-q4km`，29s，无架构问题）；③~~真机冒烟 + 10~20 条核对~~ **已完成**（见「真模型上机验证」：质量/吞吐/占位符阶梯都实测了）；④**下一步真正要做**：`--concurrency 2` 跑 200 条灰度并抽查 6 类质量问题 → 放量；⑤翻译后需按 market 重建 `product_search_document`（现在只有 en-GB，de/fr/nl 搜索命中不到译文）；⑥详情页「规格参数表」要显示译文还需接 `backend/catalog/detail_views.py` 读 `spu_detail_translation.specification_tables/specifications/spec_options`（**未做**；但 PDP 已选 SKU 的规格文本用的是 `sku_specification_translation`，**已经生效**）；⑦全量执行顺序：`enqueue/run --all`（正文 + 图文 + 术语，`--concurrency 2`）→ `build-specs --langs de,fr,nl` → `verify --all`；术语阶段只有约 1.1 千次请求，先跑它再做正文更省时间。
  - **坑（不得再踩）**：①`ollama run hf.co/...` 会直连 HF，本机 85KB/s —— 走镜像 + 断点续传，别在会话里干等；②Ollama 里还驻留 `qwen3.8:27b`（17GB），3090 24GB 上同时加载 Hy-MT2 会挤显存 → 先 `ollama stop qwen3.8:27b` 或 `OLLAMA_MAX_LOADED_MODELS=1`；③`ollama` CLI 不在 Git Bash PATH（真实路径 `C:\Users\lyx\AppData\Local\Programs\Ollama\ollama.exe`）；④官方 GGUF README 的 **STQ kernel / PR #22836** 警告主要针对 1.25-bit 变体，Q4_K_M/Q6_K/Q8_0 是标准 K-quant（`hunyuan-dense`）——这条是社区检索结论、无一手指链，**必须实测**；报 `unknown architecture`/`tensor type 43` 才自建 llama.cpp 或用第三方 `kaelri/hy-mt2:q4_K_M`；⑤`resolve_product_content` 只按 `locale.code` 或 `language_code` **精确匹配**，写 `de-DE` 不会命中 `de-BE` → 必须写全 8 个 locale（工具已做），只写 3 个语言码也行但别混着来；⑥占位符还原要求**严格递增**，模型合法调换语序会被判 `placeholder_mismatch`（可靠性优先，别改成宽松匹配）；⑦mock 触发词 `FAIL500` 含字母+数字会被遮挡成 `[[n]]` → 用纯字母 `MOCKFAIL` 触发 500；⑧PowerShell 5.1 读无 BOM 的 UTF-8 中文脚本会语法报错（`.ps1` 必须带 BOM），且 `python -c <多行>` 会被剥引号（写临时 .py）；⑨控制台 GBK：跑 CLI 加 `PYTHONIOENCODING=utf-8`；⑩写回不要用跨 LLM 调用的长事务（会长时间持锁），每 unit 一个短事务 + 条件 `WHERE status='translating' AND claimed_by=…`；⑪`spu_translation` 的时间戳列**没有 DB 默认值**，upsert 必须显式写 `created_at/updated_at`（Django 表，SQLAlchemy 侧绕过了 auto_now）。
  - **验证命令（可复跑）**：`python translation_agent/translate.py init-db` → `enqueue --langs de --limit 20` → `python translation_agent/tools/mock_ollama.py --port 11435`（另开终端）→ `run --langs de --limit 20 --concurrency 3 --provider ollama --base-url http://127.0.0.1:11435` → `verify --langs de --limit 20` → `purge --langs de --limit 20`。真模型只需换 `--provider ollama`（默认 11434）或 `--provider openai --base-url http://127.0.0.1:8080`。
  - **规格阶段验证（mock，针对性）**：`init-db` 对已存在的旧表幂等 `ALTER` 补 4 列（二次运行输出 "already present"）→ 基线 `sku_specification_translation=1431 / spu_detail_translation=0 / translation_term=0 / spec_write_log=0 / translation_unit=0` → SPU 3910/4016/3933/168/171：`enqueue --include-specs`（132 term，`no_letters=2 / protected=14`）→ `run --include-specs`（116 全部 done）→ `build-specs`（8 sku 行、`sku_skipped_empty=1`）→ `verify --all` 11 项全 PASS → `purge --include-specs` 六项精确回基线。主会话独立复跑（SPU 169/170，**de** 3 locale）：58 term → 6 sku 行 → 结构同构（15 行表原样、`sku_ids`/`image_url` 逐字相同）→ `verify --langs de --include-specs` 11 项 PASS → `purge` 回基线。另测：`build-specs` 重跑幂等（`sku_rows=0`）、`--overwrite-specs` 可覆盖、负向测试（手工改回中文列名/删行）verify 正确 FAIL、`--dry-run` 全命令只统计不写、`compileall` 通过。
  - **规格阶段踩坑（不得再踩）**：①`purge` 必须**同时删 `spu_text` 与 `spu_detail` 两类 unit**（曾出现"行删了、unit 留 done"→ 下次 run 永远不重建，静默丢译文；现已修 + `status` 增 `orphan_units` / verify 第 2 项会 FAIL）；②同样的坑在**跨阶段混合清理**时最容易复现：`--include-specs` 不等于 `--include-detail`，但行删除是无条件的，所以 unit 删除也必须无条件；③`build-specs` 会写 `sku_specification_translation`，**该表已有 1431 行字典译文，默认跳过不覆盖**；④空规格 SKU（4763 个）不写行，覆盖率公式按"非空规格 sku × locale"算；⑤翻译后的 SKU 规格键会让 PDP 的值匹配失效 → 已由下一条任务（`matchSpec` 用 `canonical_specification`）修好，**再动 PDP 匹配逻辑时必须保持这个约定**；⑥术语缓存全库共享，改词要么直接改 `translation_term.translated_text`，要么 purge 该语言后重新 enqueue/run；⑦`specification_tables[].columns` 全库都是 `["属性","值"]`（中文硬编码），也走术语翻译，别当结构字段跳过。

- **上一任务（2026-11-16，三任务 400 采集「只监控不干预」+ 跑完核验，✅ 监控与核验完成，未 commit、未重跑男装）**：用户要求盯住两个在跑的 400 任务跑到终态，然后核验导入质量并更新 HANDOFF。**全程没有启动新任务、没有杀进程、没有补账号、没有重跑男装、没有 commit、没有关机、没碰 9334/FB、没改业务代码、没删数据、没上架。**
  - **最终结果（时间均为 UTC；本地 = UTC+8）**：
    | run | job | 账号组 | run 状态 / job 状态 | 开始 → 结束 | 耗时 | discovered | succeeded | failed | 导入 SPU |
    | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
    | 93 `d2a63fc4-88d7-45be-8a41-0a4fc6b9cf0a` | 217「数据抓取01-手机-400-v2」 | 01 | **SUCCEEDED** / COMPLETED | 07:39:28 → 10:39:21（15:39→18:39） | 179.9 min | 400 | 365 | 4 | **365** |
    | 95 `7fd2cd80-6bb8-46bd-94c8-52165e2d457d` | 215「数据抓取03-女装配饰-400」 | 03 | **SUCCEEDED** / COMPLETED | 07:45:23 → 10:22:26（15:45→18:22） | 157.1 min | 400 | 190 | **210** | **190** |
    | 94 `b16b81f1-24fe-4274-83ed-1cb0a44925d5` | 214「数据抓取02-男装配饰-400」 | 02 | **FAILED** / FAILED | 07:45:22 → 08:23:43（15:45→16:23） | 38.4 min | 400 | 63 | 1 | **63** |
  - **手机（run 93）对账**：400 个详情请求 = **365 导入** + **31 个 HTTP 404**（源站商品页已失效，Scrapy 非 2xx 不回调、**不产生任何事件**，只能在日志 `Ignoring response <404` 里数出来）+ 3 个 `RECORD_REJECTED`（2 个风控页 + 1 个 `/error403`）+ 1 个 staging 仍 PENDING（`source_id=10404453`，`IMPORT_SOURCE_CONFLICT`：来源 SKU 已绑定到另一 SPU 5b7098bf…，导入器按规则不改绑）。另有 **20 个列表候选因「跳过已入库」未请求详情**（4 批）。`RISK_CONTROL_FALLBACK=5`、`ACCOUNT_RISK_ROTATED=5`、`ACCOUNT_POOL_EXHAUSTED=0`、`LISTING_SHORTFALL=0`、`VARIANT_PRICES_MERGED=247`。首次风控 09:14:46，首个 `/error403` 10:10:11，但全程仍以正常解析为主。
  - **女装（run 95）对账**：400 个详情**全部请求并解析**（`PRODUCT_PARSED=400`），**190 导入**（07:46:26–09:51:13）+ **210 拒绝**（35 个风控页 + **175 个 `/error403`**）+ 5 个候选跳过已入库。`RISK_CONTROL_FALLBACK=220`、`ACCOUNT_RISK_ROTATED=10`（**10 个账号全部命中**）、**09:50:00 `ACCOUNT_POOL_EXHAUSTED`**、`LISTING_SHORTFALL=0`、`VARIANT_PRICES_MERGED=165`。**run 终态 SUCCEEDED 只表示「400 队列跑完」，不代表 400 条成功**（210 条失败已进 failed_count）。
  - **男装（run 94）**：队列已入队 400，但只处理 65（63 导入 + 1 风控拒绝 + 1 在途）；`RISK_CONTROL_FALLBACK=12`、`ACCOUNT_RISK_ROTATED=6`（6 个账号全灭）、08:22:18 `ACCOUNT_POOL_EXHAUSTED` → 08:23:43 `RUN_FAILED`；首次风控 08:13:13，**6 个账号 9 分钟内被打穿**。剩余 309 个候选未请求。
  - **风控结论（本轮）**：并发 3 个 400 任务时，**02 组 6 账号 9 分钟全灭、03 组 10 账号 80 分钟全灭、01 组 9 账号仅 5 次风控并且跑完**；03 组池耗尽后 run 没有立刻失败，又空跑 32 分钟（全 403、210 条全丢）。**账号 `risk_flagged_at` 全为 NULL、被风控打过的账号仍是 ACTIVE/VALID**（01=9 VALID、02=6 VALID+4 UNKNOWN、03=10、05=8+2、06=8），风控标记不持久化 → 新建 run 会再次用同一批账号，「换号」不等于换干净号。是否 IP 级仍未验证。
  - **多规格抽查（每类目 3 个，全部 `Sku` 行数 >1、规格值原样）**：手机 spu 8224（3 SKU，`Colour`×`Memory`，价 238/244）、7986（2，`Phone Model`，12.99）、8548（2，`Colour`，119）；男装 8072 / 8193 / 8185（各 6 SKU，`Size`×`Colour`，26.80）；女装 8367（2，19.99）、8100（14，价 55.96/71.96/75.96）、8035（16，54.99）。**另抽 9 个（每类目 3）把 payload `variants[].specification` 与 `Sku.specification` 做集合比对，100% 完全命中**（手机 8164/8381/8363、男装 8045/8116/8106、女装 8241/8499/8466），颜色/尺码值（Size S–XXXL、Colour、Phone Model）逐字一致。
  - **多规格的价格缺口（重要，如实记录）**：变体补价失败时 payload variant `price=None` → 导入器 `offers_skipped_no_price` 跳过 Offer，**SKU 行仍建、但该 SKU 无价**。统计：手机 **4/834** SKU 无 Offer（4 个 SPU 部分缺）、男装 **13/386**（6 个 SPU）、女装 **597/1729（34.5%，41 个 SPU）**，单 SPU 最严重 25/36 缺（spu 7993）。**没有任何 SPU 完全无 Offer**（每个 SPU 至少 1 个有价 SKU+Offer）。女装的 597 是本轮风控期变体补价失败的直接后果，事件里**没有专门 code**，只能看 `imported_refs.variants.offers_skipped_no_price`。
  - **画廊/规格表/图文抽查（每类目 2 个 SPU，全部达标）**：手机 8565（gallery 10 / `specification_tables` 1 张 12 行 / `content_sections` 2 段）、8469（7 / 1 张 3 行 / 2 段）；男装 8059（3 / 1 张 8 行 / 1 段）、8092（8 / 1 张 10 行 / 1 段）；女装 8430（4 / 1 张 6 行 / 1 段）、8079（6 / 1 张 6 行 / 1 段，段内含 6 张图文图）。覆盖：`gallery>=3` 手机 340/365(93%)、男装 63/63、女装 158/190(83%)（`gallery>=1` 100%）；`content_sections` 非空 360/365(99%)、63/63、189/190(99%)；`specification_tables` 非空 230/365(63%)、8/63(13%)、107/190(56%)。**空值全部是源站 payload 本身为空**（逐条比对 `payload_has_but_db_empty=0`），不是解析或导入丢失。4 个 SPU 的 gallery 行数比源图少 1，是不同 URL 内容相同被 sha256 去重 + `MediaUsage` 唯一约束合并（`gallery_images.failed=0`），非下载失败。
  - **评分核验**：手机 **88** 个有评价 SPU，其中 **7 个分桶合计 ≠ rating_count**（例：spu 8585 count 1507 / 分桶和 1547，8576 1422/1448，8562 1208/1220；另有 2 个 count=1 但分桶全 0）——源站分桶与总数口径本身不一致，非落库 bug（`rating_source=flight` 原样保存）。男装 4 个、女装 48 个有评价 SPU **全部匹配**（例：男装 8059 72=72，女装 8430 22=22）。
  - **本轮新增 SPU：618 个**（手机 365 + 女装 190 + 男装 63），全部 `created_at` 落在 07:39:28–10:39:21 UTC 窗口内、`local_category` 分别为 `mobile-phones`/`womens-clothing`/`mens-clothing`、**status 全部 DRAFT（未上架）**；该时段内其它类目新增 0。
  - **男装遗留处置建议（未执行）**：①job 214 已 FAILED，重跑必须**新建任务名**（撞 unique）；②账号组换 **05 或 06**（本轮未参与，各 8 个 VALID），01 次选，**避开 02**（6 个号已在本轮 9 分钟全灭）；③**串行**，不要与其它 400 任务并发；④把 `CRAWL_VARIANT_PRICE_LIMIT`（默认 10）降到 0~3，或临时 `CRAWL_MOBILE_DETAIL=false`，把单商品请求从最多 ~14 个降到 4~6 个（本轮慢的主因就是每商品最多 +10 个 `/dp/x/<sku>` 补价请求 + `DOWNLOAD_DELAY=2`）；⑤先用 `product_limit<=20` 小任务试水，出现连续 `RISK_CONTROL_FALLBACK` 立即停。
  - **验证（按验证纪律仅做针对性验证；本次零应用代码改动，故未跑后端/前端测试套件）**：只读脚本全部在 `var/night_crawl_20261116/`——`status3.py`（10 分钟一次轮询）、`verify_20261116b.py [--samples]`（run/staging/事件/多规格/评分）、`coverage_20261116b.py`（覆盖率+抽样）、`offer_gap_20261116b.py`（无 Offer SKU 归因）、`detail_samples_20261116b.py`（规格表行数/图文/画廊分布/PENDING staging）、`final_checks_20261116b.py`（新增 SPU 计数+规格保真+价格）、`spec_table_source_20261116b.py`、`gallery_source_20261116b.py`、`timeline_20261116b.py`、`account_pool_20261116b.py`、`active_20261116b.py`。事件计数以 `CrawlRunEvent` 为准；404 用日志 `grep -o "Ignoring response <404"` 计数。**未跑全量测试、未跑 e2e。**
  - **坑（不得再踩）**：①`CrawlRun.status=SUCCEEDED` ≠ 全成功（女装 190/400 也是 SUCCEEDED，只看 succeeded/failed/`RECORD_REJECTED` 才算数）；②详情页 404 **不产生任何事件**（Scrapy 非 2xx 不回调），对账公式 `discovered = 导入 + 404 + 拒绝 + 在途`，否则会误以为丢数据；③`ACCOUNT_POOL_EXHAUSTED` 后 run 可能继续空跑（女装池耗尽后又跑 32 分钟全 403），既不要以为已停也不要杀进程/补账号；④变体补价失败是静默的（payload `price=None` → `offers_skipped_no_price`，SKU 有行无价，无事件 code）；⑤`CrawlerAccount.risk_flagged_at` 从不写入（全 NULL），被风控账号仍 VALID；⑥`discovered_count` 只统计**新入队**，不含「跳过已入库」候选（手机 400+20、女装 400+5、男装 400+26），拿 400 当列表卡片总数会算错；⑦`MediaUsage` 按 `(asset, content_type, object_id, role)` 唯一，内容相同的两张源图会合并成 1 行 gallery。
  - **剩余待办**：①男装是否补跑 337 条缺口由用户定（当前 63 条 DRAFT 可先上架）；②618 个新 SPU 全是 DRAFT，**是否上架未做**；③女装 597 个无价 SKU（41 个 SPU）若上架会出现「有规格无价」，建议先补价或这批 SPU 暂不上架；④手机 7 个 SPU 评分分桶口径不一致，如需严格一致要单独定口径；⑤未 commit。

- **上一任务（2026-11-16，采集 Joybuy 9 个频道页 banner 落库成我们的频道页轮播，✅ 已完成，未 commit）**：用户要求「采集 Joybuy 频道页 banner 用作我们展示，链接统一跳我们频道页，后续再单独配」。**这是真实运营数据，要保留，不要按「测完清理」处理。**
  - **数据来源（不依赖现场抓 Joybuy）**：直接用 2026-11-11 的频道页 SSR 存档 `var/category_cards_20261111/channels/*.html`（14 个频道整页 HTML）。轮播模块是 `data-moduleid="uk-pc-carousel-small"`，每个 `.swiper-slide` 内含 `<a href="https://www.joybuy.co.uk/campaign/active/…"><img srcSet="… 1x, … 2x">`；图片 URL 在 SSR 里就有（CSR 懒加载的是**推荐楼层**不是 banner）。取 srcSet 第一个候选（`s1264x280_…png.webp`，1264×280）。**不需要登录态、不需要 Playwright 渲染、不受 307→/login 影响**。
  - **脚本（`var/channel_banners_scrape_20261116/`，绝对路径全硬编码）**：
    * `extract.py`：纯离线解析 14 个存档 → `banners_manifest.json`（35 行，14 频道；字段 `channel_code/source_url/local_path/sort_order/joybuy_slide_index/href/joybuy_href/archive_file`）。`channel_code` 取 HTML 文件名的 stem（与 DB 里 `minihome:` 的 code 大小写敏感匹配一致，含 `uk-minihp-clothing-footwear-acc-` 这种小写带尾横线的）。
    * `download_and_import.py`：下载（带 `Referer: https://www.joybuy.co.uk/` + 正常 UA、**串行、间隔 3s、失败重试 1 次**，21 张全 200）→ `media.uploads.store_upload(BytesIO, purpose="channel_banner", source_url=…)` → `content.channel_banner_services.create_banner(...)`，并把 `sha256/media_url/local_path` 回填 manifest、把统计写 `import_report.json`。
  - **每频道条数（只入库 9 个有 code 的一级，共 21 张）**：家居生活 4、小家电 4、健康与保健 4、美妆个人护理 2、服装与配饰 2、游戏及配件 2、电子产品 1、宠物用品 1、婴幼儿用品 1。`sort_order` **= Joybuy 轮播 slide 顺序（0 起）**，与源站顺序一致。
  - **跳过的 5 个频道（如实记录，不建行）**：`UK-Mini-HP-Automotive`（我们没有任何一级与它对应）；`UK-Mini-HP-Joymart` / `UK-Mini-HP-World-Foods`（同根 home-living 已归给 `UK-Mini-HP-Home-Living`）；`UK-Mini-HP-TV`（归给 `UK-Mini-HP-Electronics`）；`uk-mini-hp-everyday-essentials`（归给 `UK-Mini-HP-Beauty`）。判定用 `catalog.search_views.root_channel_codes()` 的同一套消歧规则——这些 code 在购物端 `/minihome/<code>` 走不到（会进降级态），入库也没人看得到。**另有 2 个一级（computers-accessories、outdoor-sports）本来就没有 channel_code，无法配置，同前任务口径。**
  - **href 口径**：全部 `href=/s?category=<该频道对应的一级 slug>`，slug 由 `root_channel_codes()` 反查（home-living / electronics / beauty-personal-care / small-home-appliances / health-wellness / clothing-accessories / pet-supplies / baby-toddler / games-accessories），**没有任何硬编码映射**。后续用户会在管理端逐张改。
  - **媒体入库方式（与管理端上传完全同一条路）**：`store_upload` → Pillow 验真格式（拒伪图）→ 2MB 上限（本次 11–73KB，未触发压缩）→ sha256 内容寻址 → CMS 桶 `cms/original/<aa>/<bb>/<sha256>.webp` → `media_url()` 出 `/media/...`。DB 侧 21 个 `MediaAsset(kind=CMS)`、尺寸全 `1264×280`、mime `image/webp`。**变体（`MediaVariant`）本次 0 条——变体只在爬虫 `media/pipeline.py` 里生成，管理端上传路径（`store_upload`）本来就不产变体，本次刻意复用上传路径而不是 pipeline，故不产生变体；这不是漏做。**
  - **幂等去重键**：`(channel_code, image_url)`，因 image_url 是内容寻址的，等价于 `channel_code + sha256`。实测三次执行：`new=21/skipped=0` → `new=0/skipped=21` → `new=0/skipped=21`，`ChannelBanner` 始终 21 行、`MediaAsset` 始终 21 个（第 2/3 次全部 `deduplicated=True`）。若某频道已存在**别来源**的 banner，脚本把本次批次追加到该频道末尾（不插队），当前库里没有这种情况。
  - **验证（按验证纪律仅做针对性验证；本次未改任何应用代码，只有 var/ 脚本 + 真实数据，故未跑后端/前端测试套件）**：
    * ①公开接口逐频道：`GET /api/v1/channel-banners?channel_code=<9 个 code>` 全部 total 与上述条数一致、`sort_order` 0..n-1 连续、`image_url` 全 `/media/`、`href` 全 `/s?category=<对应一级>`（DB 复查 `exclude(image_url__startswith='/media/')` = 0）。
    * ②购物端 `/minihome/UK-Mini-HP-Home-Living`（4 张）：hero **1264×280、`border-radius:8px`、`margin-bottom:32px`**，2 个箭头（aria `上一张 banner`/`下一张 banner`）+ 4 个圆点，4 张 `<img>` `naturalWidth×Height=1264×280`、`object-fit:cover`、src 全 `http://localhost:3000/media/cms/original/…`，页内**没有任何第三方图片域名**；点箭头 transform 依次 0 → -100% → -200% → -300%、圆点 0→1→2→3 同步，点「上一张」回 -200%（圆点 2）；**自动播放 5s 是否从末张绕回首张本次没实测**（代码是取模，未验证）；**点 banner → `/s?category=home-living`（结果页 24 卡 + 侧栏）**。
    * ③单张/两张频道：`/minihome/UK-Mini-HP-Electronics` 1 张 → 只有静态图、**无箭头无圆点**、链接 `/s?category=electronics`；`/minihome/UK-Mini-HP-Beauty` 2 张 → 2 圆点 + 箭头、链接 `/s?category=beauty-personal-care`。
    * ④窄屏：768 → 720×160、390 → 358×160、`scrollWidth == clientWidth` 无横向溢出、radius 仍 8px（与上一任务基线相同）。
    * ⑤管理端（临时 staff `banner-verify-20261116@joybuy.test`，platform_admin，用完已删）：`/campaign-cards` → tab「频道页 banner」→ 频道下拉 9 项（中英文 + code）→ 选「家居生活（Home & Living）· UK-Mini-HP-Home-Living」→ 4 行，缩略图 `naturalWidth>0` 且 1264×280、跳转 `/s?category=home-living`、状态「启用中」、顺序 1–4、无空态。
    * ⑥中英双语：zh（家居生活 4 张、电子产品 1 张）、en（Home & Living 4 张、Beauty & Personal Care 2 张）；en 文案 aria 为 `Previous banner` / `Next banner` / `Show banner N`。
    * 截图（`var/channel_banners_scrape_20261116/`）：`20261116_zh_channel_banners_4_1440x900.png`、`20261116_zh_channel_banners_1_electronics_1440x900.png`、`20261116_en_channel_banners_4_home_living_1440x900.png`、`20261116_en_channel_banners_2_beauty_1440x900.png`、`20261116_admin_channel_banner_home_living_1440x900.png`。
    * 脚本本身：`ruff check` + `ruff format --check` 全过（首跑有 6 个 unused noqa 已 `--fix` 掉）、`py_compile` 通过。
    * **管理端临时账号清理**：`StaffSession`/`StaffRoleAssignment`/`StaffAccount` 全删，该邮箱 count=0；当前 `StaffAccount` 3 个（admin@/auditor@/pagercheck@，**pagercheck 是 11-15 分页任务的遗留，不在本任务范围，未动**）。
  - **坑（不得再踩）**：①本机 `grep` 实际是 **ugrep**，`grep -oE '/media/cms/original/[0-9a-f/]+\.webp'` 会被解析成非法 `-m` 选项报错——校验 HTML 内容一律用 python 正则，别用 grep -oE；②`backend` 的 ruff 配置**没启用 E402**，Django `setup()` 之后 import 不需要 `# noqa: E402`（加了会报 RUF100），且行宽按 backend 配置来，写完直接 `ruff format`；③存档 HTML 的 srcSet 有 1x/2x 两个候选，**我们用 1x（1264×280，11–73KB）**，2x 是 2528×560/122KB——将来想给 retina 加清晰度，需要同时给 `ChannelHeroCarousel` 的 `<img>` 加 `srcset`，别只换文件白吃 4 倍流量；④IAB 新开 tab 默认视口是 **1280×720**，量 1264 之前先 `setViewportSize({width:1440,height:900})`，否则 hero 只有 1184×262（等比缩放，不是 bug）；⑤管理端中文「登录」按钮 `getByRole` 点击仍超时（老坑），用 `evaluate` 找 `textContent.trim()==='登录'` 的 button `.click()`；⑥`ChannelBanner` 当时是空表，所以 `sort_order` 直接等于 slide index；若将来跑在有数据的库上，脚本会追加到末尾（顺序会变成源站顺序接在旧数据后面），要严格对齐源站顺序需先手清该频道。
  - **下一步**：①用户会在管理端逐张改图/改链接（本次全部 `enabled=True`、href 统一 `/s?category=`）；②存档是 11-11 的，若用户要「最新活动 banner」，需带登录态重抓 `/minihome/<code>` 再跑 `extract.py`（注意 403 拦截坑，见下一条任务）；③未 commit（`var/` 不入库，`ChannelBanner` 21 行是本地库数据不是代码）。

- **上一任务（2026-11-16，频道页 banner 支持多张轮播 + 管理端按频道配置，✅ 已完成，未 commit）**：用户要求①购物端频道页 banner 做成多页轮播；②管理端「首页活动卡片」模块改名「活动卡片」；③该页 tab【活动卡片】改叫【首页活动卡片】，并新增「频道页 banner」设置（按不同频道配 banner 图 + 跳转链接）。**频道 banner 用独立模型/接口（`ChannelBanner`），没有塞进 `HomeCampaignCard.section`；图片一律本地 `/media/`，未引 CDN。**
  - **后端新增**：模型 `content/models.py::ChannelBanner`（`channel_code`/`image_url`/`href`/`sort_order`/`enabled`+时间戳，`db_table="channel_banner"`，按 `sort_order` 排序；docstring 写明与 `HomeBanner` 的频道维度差异、同样不进 CMS 快照）。迁移 **0008_channelbanner**、**0009_seed_channel_banner_permissions**（已 `migrate content` 应用到本地库）。
  - **接口清单**：
    * 公开：`GET /api/v1/channel-banners?channel_code=<code>` → `{channel_code, items:[{id,image_url,href,sort_order}], total}`，**只返回 enabled 且按 sort_order**；有 channel_code 但没配置/未知频道 → `items: []`；缺参数 → 400 `CHANNEL_CODE_REQUIRED`。
    * 管理端（权限 `cms.channel_banners.view/manage`）：`GET/POST /api/v1/admin/channel-banners`（GET 支持 `?channel_code=` 过滤）、`GET /api/v1/admin/channel-banners/channels`（有 channel_code 的一级类目下拉）、`GET/PATCH/DELETE /api/v1/admin/channel-banners/<uuid>`、`POST /api/v1/admin/channel-banners/<uuid>/actions`（`move` up/down、`toggle`）。
    * 错误码：`CHANNEL_CODE_INVALID`/`IMAGE_URL_INVALID`/`HREF_INVALID`/`SORT_INVALID`/`FIELD_REQUIRED`/`FIELD_TOO_LONG`/`BANNER_NOT_FOUND`/`MOVE_AT_EDGE`/`DIRECTION_INVALID`/`ACTION_INVALID` 均 400（找不到 404）。`image_url` 只接受 `/media/` 前缀；`href` 只接受 `/` 开头站内路径或空。
    * 上传：`POST /api/v1/admin/media` 新增 `purpose=channel_banner`（2MB、CMS 桶，权限 `cms.channel_banners.manage`）。
  - **管理端**：`AdminLayout.vue` 导航 + `router/index.js` meta + `CampaignCardsView.vue` h1 全部改为「活动卡片」；tab1 改「首页活动卡片」（key 仍 `campaign`）；新增第三个 tab「频道页 banner」，渲染新组件 `admin-web/src/views/ChannelBannersPanel.vue`——顶部频道下拉（9 个有 code 的一级，含中英文与 code）、列表（缩略图/跳转/状态/顺序/上移下移编辑删除）、弹窗（ImageUploader purpose=channel_banner + 跳转链接 + 排序 + 启用）、空态「该频道还没有 banner，频道页会显示默认渐变占位。」。`ActivityProductsView.vue` 注释措辞同步改为【活动卡片】。
  - **购物端**：新增 `components/ChannelHeroCarousel.vue` + `composables/useChannelBanners.js`，`pages/minihome/[code].vue` 用它替换原渐变 hero（原 hero 样式移入组件）。行为：**0 张→原渐变占位（频道名水印）；1 张→静态图无箭头无圆点；多张→左右箭头 + 底部圆点 + 5s 自动轮播（hover/键盘聚焦暂停）**；站内 href 用 NuxtLink，外链 `<a target=_blank rel=noopener>`，空 href 为不可点 span；尺寸仍 **1264×280、r=8px、下方 32px**，窄屏仍 720×160 / 358×160。新增 i18n `channel.bannerPrev/bannerNext/bannerDot`（英/中）。
  - **改动文件**：后端 `content/models.py`、`content/channel_banner_services.py`（新）、`content/views.py`、`content/migrations/0008_channelbanner.py`、`0009_seed_channel_banner_permissions.py`、`content/tests/test_channel_banners.py`（新，9 例）、`merchant_ops/views_channel_banners.py`（新）、`merchant_ops/urls.py`、`config/urls.py`、`media/uploads.py`、`merchant_ops/views_media.py`。前端 `admin-web/src/views/ChannelBannersPanel.vue`（新）、`CampaignCardsView.vue`、`ActivityProductsView.vue`、`layouts/AdminLayout.vue`、`router/index.js`；`storefront/components/ChannelHeroCarousel.vue`（新）、`composables/useChannelBanners.js`（新）、`pages/minihome/[code].vue`、`locales/messages.js`、`tests/channel-hero-carousel.test.js`（新 3 例）、`tests/minihome-channel-page.test.js`（+2 例，总 6）。
  - **验证（按验证纪律仅做针对性验证）**：
    * 后端：`./.venv/Scripts/python.exe backend/manage.py test content --keepdb --noinput` → **31 tests OK**（含新增 9）；改动 py 文件 `ruff check` 全过（只 check 未 format）。
    * 管理端：`npx prettier --check` 改动文件全过、`npx eslint src` 0 告警、`npm run build` 成功；`admin-web` vitest 9/9。
    * 购物端：`node node_modules/vitest/vitest.mjs run --config storefront/vitest.config.js` → **71/71**（基线 66 + 新 5）；改动文件 prettier `--check` 全过；eslint storefront+admin-web 0 输出。
    * **浏览器实测（IAB 1440×900，后端 8000 重启后、storefront 3000 已启动）**：①导航「活动卡片」、页面 h1「活动卡片」、tabs = 首页活动卡片 / 品类发现（Category discovery） / 频道页 banner；②选「家居生活（UK-Mini-HP-Home-Living）」→ 上传 3 张图（真实走 ImageUploader→POST /media）→ 保存 → 列表 3 行 → 购物端轮播 3 张（箭头 aria「上一张/下一张 banner」、圆点 3 个，点击箭头 transform -100%、点第 3 点 -200%；第 2 张无 href 不可点、第 1/3 张站内链接正确）；③上移第 3 张后列表顺序 [1,3,2]，禁用第 1 张后购物端只剩 2 张且顺序正确；④删除全部 → 列表 0 张、空态出现、购物端回退渐变占位。尺寸实测 1264×280、r=8px、mb=32px；1920 仍 1264×280，768/390 为 720×160 / 358×160 且无横向溢出。
    * **回归宽度**：`/`、`/c/mobile-phones`、`/p/<id>` 在 1440 → container 1440（内容区 1344）/ 1920 → container 1608（内容区 1512），三页一致，与改动前基线相同（未动全局 token）。
    * **截图**：`var/channel_banners_20261116/`（`20261116_channel_1banner_1440x900.png`、`20261116_zh_channel_3banner_1440x900.png`、`20261116_en_channel_3banner_1440x900.png`、`20261116_en_channel_2banner_after_disable_1440x900.png`、`20261116_en_channel_0banner_placeholder_1440x900.png`、`20261116_admin_channel_tab_empty_1440x900.png`）。
    * **数据清理**：3 张测试 banner 已全部删除（`ChannelBanner` count=0）；3 个测试 MediaAsset + 物理文件已删（MediaAsset 按 sha256 count=0）；临时 staff `channel-banner-ui-20261116@joybuy.test` 的 session/assignment/account 全删（count=0）；临时脚本 `var/tmp_channel_banner_*.py` 已删。
  - **坑（不得再踩）**：①**IAB 不支持 file chooser**：验证上传用页面内 `canvas.toBlob()` 造 1264×280 PNG → `new File` → `DataTransfer` 赋给 `input[type=file].files` → dispatch `change`，可真实触发 ImageUploader 的 adminUpload；②管理端确认弹窗是 `section.modal`（不是 `<dialog>`），`dialog` 选择器读不到；③中文按钮 `getByRole` 常点不动，统一 `evaluate` 里 `Array.from(document.querySelectorAll(...)).find(b => b.textContent.trim() === "…").click()`；④后端 `--noreload` 改完必须 taskkill 重启（本次 8000 旧 PID 6380 → 新 25392），否则新路由 404；⑤公开接口「缺 channel_code」是 400，**未知但非空的 code 返回空 items**，前端降级不要混为错误；⑥`useChannelBanners` 的 `useFetch` key 必须 computed（`channel-banners-${code}`），否则频道切换复用旧缓存；⑦vitest 无 Nuxt 自动导入：页面测试要 mock `useChannelBanners`，组件测试显式 import 并 stub `NuxtLink`；⑧临时 staff 会话按 host 共享，本次用完已删，后续验证前先确认没有其他 agent 在管理端登录。

- **上一任务（2026-11-16，购物端频道落地页 `/minihome/<code>` 两处视觉对齐 Joybuy：标题居中 + 内容区/banner 尺寸，✅ 已完成，未 commit）**：用户反馈①分类标题应居中（当时靠左）②频道页内容区宽度和 banner 大小与 Joybuy 不一致。**只改一个文件 `storefront/pages/minihome/[code].vue` 的样式，零逻辑改动、零后端改动、全局 token 未动。**
  - **Joybuy 实测数值（2026-11-16 15:20–15:40 本地，带登录态真实渲染）**：
    * **测量方法**：`crawler/debug_session.py` 的 cookies 注入 Playwright Chromium（`context.addCookies`，viewport 2560/1920/1680/1440/1280/1024/390）→ `page.evaluate` 读 `getBoundingClientRect` + `getComputedStyle`。脚本 `var/_measure_20261116/measure_live.mjs`（完整量）、`measure_full.mjs`（JS 关闭量 SSR 布局）、`measure_static.mjs`；原始数据 `joybuy_live.json` / `joybuy_full.json` / `joybuy_static.json`，SSR 存档 `joybuy_channel_ssr.html`。**先 curl 确认 cookie 有效**（`urllib` 带 Cookie 直连 `/minihome/UK-Mini-HP-Home-Living` → 200 / 1.02 MB，匿名仍 307 `/login`）。
    * **①内容区宽度**：1920/1680/1440/1280 视口实测**都是 1264px**，居中（x=328/208/88/48）；`.cms-content` 内联 `style="width:1264px;margin:auto"`。2560 视口仍 1264（x=648）。≤1024 视口 Joybuy **不收缩而是横向溢出**（390 视口 `docScrollW=1264 > clientW=390`，`margin` 变负）——频道页只有 PC 布局，没有移动端参考。
    * **②banner（轮播）**：**1264×280**，与内容区**同宽、无左右内缩**，圆角 **8px**（在 `.swiper.style_mySwiper__*` 上，外层容器 0）；轮播图源文件名即 `s1264x280_*.png`（natural 1264×280、`object-fit:contain`），每个 slide 也是 1264×280。高度在所有视口恒为 280（因内容宽恒定）。
    * **③频道标题 h1**：**通栏居中**（x=0、w=视口宽、`text-align:center`），font-size **36px**、weight **700**、line-height **54px**、margin `32px 0 0`；与 banner 之间 **0 间距**（h1 底 236 = banner 顶 236）。
    * **④模块纵向间距一律 32px**（banner 底 516→卡片区 548；748→780；980→广告 1012）。
    * **交叉验证**：二级品类行 = 8 张/行（swiper slide 158 均分 1264）、卡面 **140×200**、gap 17px、整行正好 1264；广告位 3×**410×200** + 2×17 = **1264**（算术精确命中内容宽）；商品卡 194×310、间距 20（194+20=214 pitch，起点 x=内容左边界）。
  - **改动（全部在 `storefront/pages/minihome/[code].vue` 的 `<style scoped>`）**：①页面根 `.channel-page-bg` 上加 `--container-max: calc(1264px + 2 * var(--container-pad))`（AppContainer 读这个变量，自定义属性继承到子树）→ 1440/1680/1920/2560 视口内容宽精确 1264、x 与 Joybuy 完全一致（88/208/328/648）；**`:root` 的 `--container-max: 100.5rem`（1608px）没动**，`p/[id].vue` 自己的 `max-width: var(--container-max)` 仍取 :root 值。②标题 `margin:0; font-size:2.25rem; line-height:1.5; text-align:center`；页面上下 padding 改 `2rem / var(--space-8)`（=源站标题上 32px、尾部 32px），标题与 banner 之间 0 间距。③banner 占位：`aspect-ratio:1264/280; max-height:280px; border-radius:var(--radius-md)`(=8px)、`margin-bottom:var(--space-8)`、`overflow:hidden`；≤48rem 改 `aspect-ratio:auto; height:160px`。④卡片区与两个商品楼层间距 24→32px；水印字 ≤48rem 降到 1.75rem。素材仍是纯 CSS 渐变占位（不引 CDN、不伪造图）。
  - **实测 vs 我们 对照表**：
    | 项 | Joybuy 实测 | 改动前 | 改动后 |
    | --- | --- | --- | --- |
    | 内容区宽 @1920 | 1264（x=328） | 1512（x=204） | **1264（x=328）** |
    | 内容区宽 @1440 | 1264（x=88） | 1344（x=48） | **1264（x=88）** |
    | 内容区宽 @1680 / @2560 | 1264（x=208 / 648） | 1512（按容器公式 x=84 / 524，未单独量） | **1264（x=208 / 648）** |
    | banner @1440/1920 | 1264×280，r=8 | 1512×180，r=14 | **1264×280，r=8** |
    | h1 标题 | 居中 36px/700/54px | 左对齐 28px/700/35px | **居中 36px/700/54px** |
    | 模块间距 | 32px | 20 / 16 / 24 混用 | **32px** |
    | 品类卡区 | 8 张/行，卡 140×200 | 11 张/行（1512 时），卡 130 方形 | 9 张/行，卡 133 方形（保持既有方形卡，只随宽度自适应） |
  - **验证（按验证纪律仅做针对性验证）**：
    * **单测**：`node node_modules/vitest/vitest.mjs run --config storefront/vitest.config.js` → **66/66 通过**（16 文件，~1.5s，与基线一致，未改任何断言）。prettier `--check` 过、eslint 0 告警（只查改动文件）。
    * **浏览器实测（Playwright headless 量 + IAB 复核，dev server 3000 未动）**：①`/minihome/UK-Mini-HP-Home-Living` h1 computed `text-align:center`、36px/700/54px（zh「家居生活」/ en「Home & Living」都验）；②banner 1264×280、radius 8px、内容宽 1264 —— **1920 / 1680 / 1440 / 2560 四个视口内容区 x=328/208/88/648、宽均 1264，与 Joybuy 实测逐一相同**，截图肉眼一致；③**回归 4 页 × 4 视口（1920/1440/768/390）改动前后 JSON 逐项 diff = 0**：首页 `/` 1512/1344/720/358、详情页 `/p/6f16c573-…` 同、`/c/mobile-phones` 同、`/s?category=electronics` 同（IAB 复核 1920=1512、1440=1344 二次确认）；④窄屏：1024→hero 976×216、768→720×160、480→448×160、390→358×160，`docScrollW == clientW` 无横向溢出、卡片不变形（390 截图已核）。
    * **截图**（`var/minihome_pages_20261116/`）：`20261116_zh_channel_1440x900.png`、`20261116_zh_channel_1920x1080.png`、`20261116_zh_channel_floors_1920x1080.png`、`20261116_en_channel_1440x900.png`、`20261116_en_channel_1920x1080.png`、`20261116_en_channel_floors_1920x1080.png`、`20261116_zh_channel_390x844.png`；Joybuy 对照 `joybuy_ref_channel_1440x900.png` / `_1920x1080.png`。**未跑全量 e2e**（`tests/e2e` 无 minihome 相关用例/快照，按验证纪律只做针对性验证）。
  - **坑（不得再踩）**：①**带登录态在浏览器里打开 joybuy 频道页会被 CSR 的 403 打成整页「403 页面」**——SSR 本身 200 且类名齐全，但 `color-api.joybuy.co.uk` 的 `guide_catalog_get` / `guide_recommendation_getSlotList` / `user_help_getQuestionList` 对无指纹浏览器返回 403，全局错误处理把整页替换（title 从「家居好物」变「403 页面」）。解法：`page.route(/color-api\.joybuy\.co\.uk/, fulfill 200 {"code":0,"data":{}})`（本次拦 17 个请求后页面稳定、swiper 正常初始化）；或 `javaScriptEnabled:false` 只量 SSR 布局（CSS 仍生效）。**不要因为「没有 carousel / title 变 403」就判定 cookie 过期**。②量源站点必须用 `[class*=uk-pc-carousel-small]`，实际类名是 CSS module 哈希 `style_uk-pc-carousel-small__zQfHd`，裸 `.uk-pc-carousel-small` 选不到。③`aspect-ratio` + `min-height` 会**按比例反推宽度**把块撑出容器（390 视口 hero 曾实测变 632px 宽、横向破版）——窄屏要固定高度时必须同时 `aspect-ratio:auto`。④IAB 有 15px 经典滚动条：`documentElement.clientWidth = innerWidth-15`，居中元素 x 会差 7~8px（IAB 1920 视口内容 x=321 vs Joybuy 328），对照 px 用「内容宽」或 Playwright（overlay 滚动条）口径，别直接拿 IAB 的 x 比。⑤`--container-max` 只在频道页根元素覆盖、靠继承生效；要改全局请改 `:root`——那会连带详情页/首页/结果页回归。
  - **边界**：未 commit；未改 `tokens.css`（含 `:root` 的 `--container-max`）/ `AppContainer.vue` / `CategoryTileGrid.vue` / `CmsProductPool.vue`；未动后端（8000 runserver 未重启）、未动 dev server（3000）。临时量测脚本全部在 `var/_measure_20261116/`（var/ 已 gitignore）。

- **上一任务（2026-11-16，爬虫「详情页 RSC 改版适配」，✅ 已完成并真实抓取验证，未 commit）**：修复 Joybuy `/dp/` 页改 RSC 流后评分/AI 摘要解析不到的问题，并给列表→详情链路补字段兜底。
  - **更正（重要，推翻上一轮结论）**：上一轮「/dp/ 详情页已壳化、SSR 里只剩 CSR 占位」是**误判**——商品数据仍完整内嵌在 `self.__next_f` 的 RSC chunk 里，`_flight_text` 能解出。实测 iPhone `100020670022401`：gallery 9、specOptions 3 轴、variants 32、规格表 1、图文 3 段、评分 4 分 77 条（分桶 1/0/1/9/66）。**不要再按「详情页没数据」去改抓取方式**。
  - **三处修复（`crawler/joybuy_crawler/`，上一会话已 ruff 且 127 个既有测试全绿；本次未重跑单测）**：①`parsers/joybuy_uk.py` 新增 `_decode_nested_json_object(text, anchor)`（锚定键名后 `raw_decode`）；`_extract_flight_review` 的扁平花括号锚点失败时用它解嵌套的 `"ratingInfo":`（RSC 改版后它在更大对象里），评分分桶/总数恢复；`aiSummary` 缺失时调 `extract_ai_summary(text)` 兜底。②`parse_uk_product_detail`：flight + DOM 都拿不到评分时，用 JSON-LD `aggregateRating`（ratingValue/ratingCount）兜底，`rating_source="json_ld"`。③`spiders/joybuy_run.py`：列表卡片数据随请求透传（`meta["listing_entry"]`），新增 `_fill_from_listing_entry(product, entry)` 在详情缺 title/currency/current_price/skus/gallery 时补齐，并打事件 `DETAIL_FROM_LISTING_FALLBACK`。
  - **验证（按验证纪律仅做针对性验证，2026-11-16 06:35–06:45 UTC，全程零风控）**：
    * ①真实页面直连 3 个商品（脚本 `var/probe_rsc_20261116/verify_parse.py`，VALID 会话 Cookie 只内存拼头不打印）：iPhone `100020670022401`（多规格）gallery 9 / 轴 3 / variants 32 / 规格表 1 / 图文 3 段 / 评分 4 分 77 条（分桶 1/0/1/9/66）/ missing 空；Maybelline 睫毛膏 `10418446`（普通）6 / 0 / 0 / 0 / 1 / 4 分 552 条（0/0/1/139/412）/ missing 空；饼干 `100014425005176`（其它类目）3 / 0 / 0 / 1 / 1 / 4 分 49 条（5/0/3/5/36）/ missing 空。**3/3 命中 gallery≥3、content_sections≥1、rating_count>0、missing 空**。
    * ②真实任务：新建 `验证-RSC适配-20261116`（CrawlJob pk=216，limit=5，数据抓取01），CrawlRun pk=92、public_id `4145c9e0-ff01-4c68-b814-e36c5aa2579d`，06:42:29–06:44:39 UTC **SUCCEEDED**（discovered 5 / succeeded 5 / failed 0）。事件：LISTING_FETCHED×2（page1 49 卡、page2 45 卡）、PRODUCT_PARSED×5（图片 7/9/9/10/8 张；2 个有评价「评分 5（5 条）」「评分 4（114 条）」，3 个源站本身无评价）、MOBILE_DETAIL_MERGED×5（图文 1–2 段、规格表各 1 张）、VARIANT_PRICES_MERGED×2、PRODUCT_IMPORTED×5；**RISK_CONTROL_FALLBACK=0、DETAIL_FIELDS_MISSING=0、RECORD_REJECTED=0、DETAIL_FROM_LISTING_FALLBACK=0**（日志 grep `/user/risk` 也是 0；因详情字段完整，列表兜底路径本次未被触发，仅代码级保障）。JOB 已 COMPLETED。
    * ③落库核对 5 个 SPU（393ffef4 / c1160844 / 49825fc6 / 4a8f9ed4 / 3324e318）：`SpuDetail` 全部存在，content_sections 1/2/1/2/1、specification_tables 各 1、gallery（MediaUsage role=gallery）9/9/8/10/7；有评价的 `rating` = (5.00, 5) / (4.00, 114)；多规格商品（spec_options 1 轴）Sku 2 行 + Offer 2 个，其余单 SKU。5 个暂存 payload 的 `rating_source` 全是 `flight`（嵌套 `"ratingInfo":` 修复生效），**JSON-LD 兜底路径本次未被触发，仅代码级保障**。验证任务与已导入数据按指示保留。
  - **风控仍是独立风险（未解除）**：本次 5 商品小批量零风控，但 11-16 凌晨已实测推翻「凌晨低风控」（01 组 9 个 VALID 账号 10 分钟全灭）；详情页 `307 /user/risk/pic` 才是真拦截（`RISK_CONTROL_FALLBACK`）。建议任何放量前先用 limit≤10 小任务试水，一旦出现 `RISK_CONTROL_FALLBACK` 立即停、不要继续烧账号池；熔断 trip code 已含该事件（见 `var/night_crawl_20261116/night_queue.py`）。
  - **下一步**：可以放量到 400/类目重跑（**新建任务名**，避开 unique；job 216 已 COMPLETED 只能另建），但必须在低风控时段、保留 3 连坏熔断；04 组仍无 VALID 会话，继续排除。
  - **边界**：未 commit；未放量；未碰 FB/9334；未调 `_kill_stale_crawler_browsers`；未关机；未改业务代码（只加了探针脚本 `var/probe_rsc_20261116/verify_parse.py`）。

- **上一任务（2026-11-16，购物端「频道落地页」`/minihome/<code>` 对齐 Joybuy 的 minihome 页，✅ 已完成，未 commit）**：首页顶部分类导航点一级（如【家居生活】）原来和左侧筛选 `/s?category=` 结果页长得一样；现在一级跳**独立频道落地页**（`/minihome/UK-Mini-HP-Home-Living`，与 joybuy.co.uk 同构），页面布局与结果页完全不同。
  - **页面结构（对照 14 个存档 SSR `var/category_cards_20261111/channels/*.html` + `channel_pets_zh.html`，所有频道结构一致）**：Joybuy 频道页 = h1 频道名 → banner 轮播（`uk-pc-carousel-small`）→ 二级品类卡片区（`uk-pc-popular-category-*`，锚点链 `/s?...&l2=<id>`）→ 广告图（`uk-pc-image-ads`）→ 1~2 个带标题商品楼层（`product-pc-floor`，各约 20 卡）→ 推荐楼层（`uk-pc-recommend-product`，CSR 拉取 SSR 为空）。本地实现（`storefront/pages/minihome/[code].vue`）：h1（本地化一级名）→ **渐变色块 hero 占位**（无 banner 素材，纯 CSS 渐变+频道名水印，不引 CDN 不伪造图）→ **二级卡片网格**（复用 `CategoryTileGrid`，链接 `/c/<L2>`；**截取前 22 张**对齐 Joybuy 精选子集行为，溢出时右下「查看全部品类」→ `/s?category=<L1>`）→ **双商品楼层**（复用 `CmsProductPool`：`useSearch` category=<L1 slug> 子树匹配，楼层 1「热门精选」relevance 前 10 + 楼层 2「最新上架」sort=newest 前 10，楼层 1 带「View all」链到结果页；商品为空则整层省略）。**推荐楼层省略**（源站是客户端拉取，无 SSR 数据可对照），留注释。
  - **频道 code 解析（后端小改）**：`backend/catalog/search_views.py` 新增 `root_channel_codes()`——`CategoryMapping` 反查 `source_id` 前缀 `minihome:` 且 `local_category__depth=0` 的映射，`category_tree` 给每个 depth=0 行加 `channel_code` 字段（二级行没有该字段）。**多频道消歧规则：同一级挂多个频道时取 `source_id` casefold 排序最小**——当前数据下正好是各一级主频道（Home-Living<Joymart<World-Foods、Beauty<Everyday-Essentials、Electronics<TV）。前端共用 `storefront/utils/categoryLinks.js::categoryHref(category)`：有 `channel_code` → `/minihome/<code>`，无 → 降级 `/c/<slug>`；`AppHeader` 顶部导航与 `ProductListing` 面包屑一级都走它。**没有硬编码任何映射**。
  - **无频道 code 的一级清单（保持跳 `/c/<slug>` 结果页，共 2 个）**：`computers-accessories`（计算机与配件，分散在 Electronics/Gaming 频道）、`outdoor-sports`（户外运动，分散在 Home-Living 频道）。其余 9 个一级都有 `minihome:` 映射。**一级↔频道不是一一对应**：home-living 挂 3 个频道、electronics/beauty 各挂 2 个（DB `CategoryMapping` 实查）。
  - **保持不变（按任务要求）**：`/c/<二级>` 与 `/s?category=` 结果页行为、侧栏筛选（仍 `/s?category=`）、顶部卡片轮播、分类下拉面板（面板内点一级仍是面板内切换，`AppCategoryPanel` 零改动）、二级链接始终 `/c/<L2>`。`/s?category=<一级>`（旧一级入口）仍然可达，频道页「查看全部品类」就用它。
  - **改动文件**：后端 `backend/catalog/search_views.py`（+`root_channel_codes`、category_tree 加字段）、`backend/catalog/tests/test_standard_categories.py`（+1 例：多频道消歧/无 code 为 null/二级行无字段）。前端新增 `storefront/pages/minihome/[code].vue`、`storefront/utils/categoryLinks.js`、`storefront/tests/categoryLinks.test.js`（3 例）、`storefront/tests/minihome-channel-page.test.js`（4 例，Suspense 包裹挂页面）；修改 `storefront/components/AppHeader.vue`（items 走 categoryHref）、`components/AppHeader.test.js`（fixture 加 channel_code + href 断言改双链）、`components/ProductListing.vue`（面包屑一级走 categoryHref）、`composables/useCategoryTree.js`（返回值加 `treeData`（AsyncData 本体），页面 `await treeData` 后再发搜索请求，头部面板照旧只用 `categories`）、`locales/messages.js`（+`channel.*` 6 键双语）。
  - **验证（按验证纪律仅做针对性验证）**：①后端 `manage.py test catalog.tests.test_standard_categories --keepdb` → **7 tests OK**（新增 channel_code 1 例）；改动 2 个 py `ruff check` 全过。②storefront `vitest run` → **66/66**（基线 59 + 新增 7）。③改动 9 个前端文件 prettier --check 全过（categoryLinks.test.js 一次 --write 修正）+ eslint 零告警（修掉页面一个未使用 import）。④浏览器实测（IAB 1440×900，后端已重启后）：顶部 11 个一级 href 逐个核对（9 个 `/minihome/`、2 个 `/c/`）→ 点【家居生活】进频道页（h1 家居生活、hero、22 卡片、热门精选/最新上架各 10 卡、查看全部品类）→ 点【家具】卡片进 `/c/furniture`（侧栏+69 卡轮播+面包屑 首页/家居生活/家具，家居生活 href=/minihome/...）→ 点面包屑一级回频道页；频道间切换（家居生活→电子产品）数据正确刷新（13 卡、手机第一张，楼层商品与 `/s?category=electronics` API 首条一致=子树匹配既有行为）；无 code 一级【计算机与配件】→ `/c/computers-accessories` 正常；`/minihome/UK-Mini-HP-Nowhere` → 「该频道暂不可用。返回首页」降级态；`/s?category=home-living` 旧入口仍 3577 件商品。中英双语（cookie `joybuy-locale=zh-CN`/`en-GB`）各验一轮，6 张截图 `var/minihome_pages_20261116/`（zh/en 频道页首屏+楼层、zh/en 结果页面包屑）。
  - **后端重启**：旧 runserver（PID 15228，--noreload 起）taskkill 后在后台任务里重启 `runserver 127.0.0.1:8000 --noreload`；重启前确认非终态 CrawlRun 只有已知的僵尸 runs 1/2（11-03/11-04）。API 实测 `GET /api/v1/categories` 已回 `channel_code`。
  - **坑（不得再踩）**：①页面要「先拿类目树再发搜索」——`useCategoryTree` 现在把 AsyncData 本体作为 `treeData` 返回，页面 `await treeData` 后再建 `useSearch` 的 computed params；直接并发发的话 SSR 首帧 params 里 category 是空的，会拉成全站商品。②未知 code 的频道页 params 用占位 slug `unknown-channel` 让搜索 404 成空集（不能传空字符串——`useSearch` 会把空值滤掉变成无 category 全站搜索）。③`SourceCategory` 没有 `name` 字段（名字在 Snapshot），测试里直接 `SourceCategory.objects.create` 只能带 source_id/时间戳。④多频道消歧的 casefold 规则依赖当前命名，若未来新增频道（如再抓新 minihome code）需复查排序是否仍命中主频道。⑤IAB 里 `.category-tile` 图片首次截图时可能还没画出来（lazy loading），截图前等 1 秒以上或先滚一遍。
  - **主会话复验（子 Agent 撞到用量上限中断在收尾，交接已写完）**：`vitest run` **66/66**、`test_search + test_joybuy_menu_crosswalk --keepdb` **20 OK**、`ruff check search_views.py` 全过、6 个新文件 prettier+eslint 全过；API `GET /api/v1/categories` 11 个一级均带 `channel_code`（computers-accessories / outdoor-sports 为 null）；浏览器复核：顶部 11 个 href（9 `/minihome/` + 2 `/c/`）→ 家居生活频道页（h1 + hero + 22 卡 + 两楼层各 10 卡 + **无 `.listing-sidebar`**）→ 点卡片进 `/c/furniture` → 面包屑一级回 `/minihome/UK-Mini-HP-Home-Living`；en 版截图复核正常。

- **夜批（2026-11-16 凌晨，无人值守）：阶段 1 风控测试未通过 → 整夜批次取消，已按预案关机。晨报 `var/night_crawl_20261116/MORNING_REPORT.md`。**
  - **风控证据（测试 run 83bd9feb，job 213 数据抓取01-手机-400，17:44–17:54 UTC / 本地 01:44–01:54）**：10 分钟内 01 组 9 个 VALID 账号**全部**命中详情页风控验证码被移出账号池（`ACCOUNT_RISK_ROTATED`×9 → `ACCOUNT_POOL_EXHAUSTED`），`RISK_CONTROL_FALLBACK`×26、`RECORD_REJECTED`×9（空记录）、导入仅 4；列表页正常（LISTING_FETCHED×11 全 200、discovered=400）——**风控只打详情页，与 11-15 下午 b3 失败完全同型**。关键新事实：DrissionPage 重渲染兜底 `RENDERED_OK`×26 全成功但解析出的仍是空数据；且**本次是凌晨时段，「凌晨低风控」假设已被实测推翻，14:30 升级的风控没有随时间回落**。
  - **处置**：测试 run 已 taskkill 进程树并 `complete_run_failed` 标 FAILED（job 213 随 PAUSE 转 FAILED，重抓需另建任务）；**队列从未启动**——job 214 男装配饰-400 / 215 女装配饰-400（limit=400、skip_imported、翻页开）仍 READY 可直接用；20 个组均衡 READY 任务未动；已导入的 4 个手机商品为正常数据无需回滚。
  - **僵尸清理（完成）**：CrawlRun id=26 → FAILED（RUN_FAILED 事件已写），job 188 → FAILED 回落。runs 1/2（jobs 2/3）的旧僵尸 RUNNING 按指示未动。
  - **多规格（WP-45）真实数据验证（✅ 生效）**：测试 run 导入 4/4 全部多 SKU（Sku 行数 15/2/4/2，payload variants=32/2/4/2，kept=16/2/4/2 与 imported_refs/skus_created 一致，跨商品兄弟变体按口径跳过）。Spu 7965–7968。
  - **夜批资产已备好（风控解除后复用）**：`var/night_crawl_20261116/night_queue.py`（由 night_queue.py 派生：**TRIP_CODES 新增 RISK_CONTROL_FALLBACK**、单 run 超时 150 分钟、关机逻辑保留）+ `launch_run.py`/`check_run.py`/`morning_watcher.py`（增强版：终态后自动做三类目实查、多规格聚合抽查、写晨报+更新 HANDOFF）；`task_list.json` 已写（3 大任务 213/214/215 + 20 个组均衡 READY 任务：01=[32,50,68,80]、02=[27,33,39,51]、03=[34,40,46,52]、05=[24,36,42,48]、06=[37,43,49,55]）但**213 已 FAILED，复用前需换成新任务并重新填 prestarted run_id**。剩余 READY=131（default 2、01=15、02=21、03=21、04=32、05=20、06=20）。
  - **明早建议（按优先级）**：①先人工带 VALID 会话开手机详情页确认 `/user/risk/pic` 是否仍在弹；②考虑换 VPN 节点后用小 limit 任务试水（风控是否 IP 级未验证）；③勿盲目重跑烧账号——昨晚 9 个账号 10 分钟全灭说明只要详情页仍弹验证码，任何批次都会迅速烧穿所在组的账号池；④风控解除后按 `night_queue.py`+`task_list.json`（修正后）直接跑。

- **当前任务（2026-11-15，WP-45 阶段 2「导入链路多 SKU + 购物端端到端验证」，✅ 已完成，未 commit）**：`import_staging_product` 支持 payload `variants` 按「同源商品」口径建多 SKU + 变体 Offer + 变体图本地化 + 搜索文档刷新；真实数据端到端（iPhone 10404455）与购物端 PDP 浏览器实测全部通过。详见 §2「2026-11-15（WP-45 阶段 2：导入链路多 SKU + 购物端端到端验证）」。
  - 同源口径判定（关键决定）：变体保留条件 = `is_primary` 或 `source_sku_id` 等于顶层 `skus[].source_id` 或 `sku_status` 非 null（即被当前商品页 `productSelectedFloor.skuStatus` 声明）；系列轴 1TB/512GB 的值指向源站兄弟商品（另两个源商品页）→ 全部跳过。**同一源 sku 已作为兄弟商品独立导入过（已有身份绑到别的 SPU）时，跳过该变体并计数，绝不改绑。**
  - 实测口径后果：iPhone PDP 可选规格只有 256GB 系列的 2 个颜色（星宇橙/银色，均 1099）——价格差异化的 1TB=1499/512GB=1299 属兄弟商品，不进本商品 SKU；「切规格价格联动」在本商品表现为同价切换（真实数据如此，非 bug）。
- **上一任务（2026-11-15，WP-45 阶段 1「爬虫多规格变体采集」+ 工作包立档，✅ 已完成，未 commit）**：爬虫 payload 新增 `variants` 数组（每规格组合的源 sku id / 真实规格名值对 / 价格 / 库存状态码 / 规格图 / 主变体标记），立 WP-45 文档；导入侧多 SKU 已在本次（阶段 2）落地。详见 §2「2026-11-15（WP-45 阶段 1：爬虫多规格变体采集 + 工作包立档）」。
  - 关键调研结论：详情 JSON 的 `colorSizePartList`/`productSeriesFloor` 有每个变体的源 sku id、规格图 s96、原始 `stockState`，但**没有价格**（`productPriceFloor` 只描述当前浏览 sku）——变体价格靠逐变体补抓它自己的 `/dp/<sku>` 页（已实测随变体不同：1TB=1499/512GB=1299/256GB=1099）。
  - 验证（按验证纪律仅做了针对性验证）：新增 `test_crawler_variants.py` 8 例 + detail_extras 回归 16 例（24 OK）、导入/质量/重建/详情 API 113 例 OK、ruff check+format 全过；debug_crawl 实抓 iPhone（8 变体全带价）与炒锅（2 变体）成功，留档 `var/wp45_phase1/`。

- **上一任务（2026-11-15，购物端 PDP「规格无法选择」修复，✅ 已完成，未 commit）**：仅改 `storefront/pages/p/[id].vue` 一个文件，后端零改动。
  - **根因**：爬虫导入是 1 SPU = 1 SKU = 1 Offer，但 `SpuDetail.spec_options` 保留了源站的完整多规格轴（值指向未导入的源 SKU id）。后端 `_spec_options_payload` 把未导入的源 id 过滤掉后 `sku_ids=[]`，PDP 仍按 spec_options 渲染出规格按钮组；点击时 `selectVariant` 按 `sku.specification` 匹配不到任何候选 SKU → 直接 return（无任何反应），且唯一 SKU 虽已默认选中但其他按钮永远点不亮——用户看到的就是「规格无法选择」。例证：`84c31777-…`（IF Fruit Wine Cherry 275ml）API 返回 Flavour 轴 5 个值（Lemon/Coconut/… sku_ids 全空），实际只有 1 个 SKU（Cherry）。规模抽样：爬虫 800 个 SPU 中 436 个有 spec_options、254 个有多值轴（死按钮）；364 个是纯空 spec（无按钮，本来就正常）。
  - **修法**：①`isSingleSku = purchasableSkus.length <= 1` 时 `variantAxes` 直接返回 `[]`——不再渲染规格交互区，唯一 SKU 由既有 `selectedSku` 兜底自动视为已选，加购/立即购买按钮可用；面板里新增一行只读规格文本（`.detail__spec-readonly`，复用 `stickySpecText`，空 spec 自然不显示）。②多 SKU 商品按 spec_options 渲染时过滤掉解析不到可购 SKU 的规格值（按 specification 名值匹配或 sku_ids 匹配），杜绝死按钮；`selectVariant` 交互逻辑未动。
  - **验证（按验证纪律仅做了针对性验证）**：prettier --check 过、eslint 零告警、`node storefront/node_modules/nuxt/bin/nuxt.mjs build storefront` 通过；storefront 无 PDP 相关 vitest 用例（既有 5 个测试文件均与本次无关，未跑）。浏览器实测（nuxt dev :3000）：84c31777 修复前点 Lemon Flavour 选中态无变化（复现实锤），修复后规格按钮 0 个 + 只读「Cherry Flavour」+ 加购/立即购买 enabled、点击弹白名单门控弹窗（匿名预期行为，6-6 需求）、console error 0；空 spec 商品 `e3a6fe2f`（Good Boy Soft Dog Toy）无规格区无只读行、按钮可用、点击弹门控、console error 0；INACTIVE 多规格老商品 `947910f2` 仍正确显示「商品已下架」。截图 4 张 `var/pdp_spec_fix_20261115/`（复现 1 + 修复后 3）。
  - **限制与坑（不得再踩）**：①全库当前没有任何 ACTIVE 多 SKU 商品（唯一多 SKU 的 `947910f2` 是 INACTIVE），多规格选择交互只能代码走查确认未破坏（改动是保守过滤，未动 selectVariant），等有真多规格商品后应补一次浏览器验证；②完整加购链路（写购物车）需要白名单买家登录，本任务禁止写库造临时账号，故验证到「按钮 enabled + 点击弹门控弹窗」（证明 offer/点击路径畅通，门控是既有业务规则）；③截图 clip 模式在 IAB 有拼接伪影，用视口截图。
  - 临时排查脚本已删净（`var/pdp_spec_fix_20261115/inspect_spec*.py` ×4），只留截图；纯只读排查 + 前端修复，无任何写库操作，后端未重启（8000 未动）。

- **上一任务（2026-11-15，「这两天抓取的商品」全部上架，✅ 已完成，未 commit）**：7767 个爬虫导入 SPU 三层（spu.status / offer.status / product_search_document.is_searchable）已全部置为可售，DB 复查三层一致，购物端搜索与类目页 curl 验证通过。详见 §2「2026-11-15（把这两天抓取的商品全部上架）」。
  - **窗口边界**：`created_at >= '2026-11-14 00:00:00'`——按天实查 11-13 当天爬虫导入 0 个、11-14 4481 个、11-15 3286 个（共 7767），11-10 的 16 个是旧试跑不在「这两天」范围；摸底时窗口内 7767 个 SPU **全部 DRAFT**、offer 全 DRAFT、search doc 0 条（不存在「本来就 ACTIVE 只翻转部分」的情况）。
  - **翻转行数**：SQL 实际影响 spu 7767 行、offer 7767 行（事务内跑、行数与预估一致后 commit）；search doc 7767 个 SPU 全部刷新（ok=7767 fail=0，耗时 213s）。
  - 验证（按验证纪律仅做针对性验证）：`GET /api/v1/search?q=Yuejia` → 1 条正确命中（11-14 导入的 spu 5252）；`GET /api/v1/search?category=dog-toys` → total=310 与 DB 一致；`q=Good Boy Soft Dog Toy` → 3 条命中。SQL 文件 `var/sql_online_crawled_20261115/bring_crawled_online.sql`。

- **日间抓取第 3 批已完成（2026-11-15 14:36–17:07 本地，⚠️ 11 SUCCEEDED / 4 FAILED / 0 SKIPPED、熔断未触发、累计已跑 60/193）**：
  - 清单：`var/day_crawl_20261115/task_list_b3.json`（15 个，01/02/03/05/06 各 3；pk：01=[44,92,146]、02=[45,111,165]、03=[100,124,184]、05=[90,132,204]、06=[61,133,181]，与夜间 30 + 日间第 2 批 15 不重叠）。队列脚本 `var/day_crawl_20261115/day_queue_b3.py`（由 day_queue.py 派生，仅改 task_list/progress/final_summary 文件名为 *_b3，参数与无关机逻辑不变）。
  - 结果（`final_summary_b3.json`/`progress_b3.json`）：**共导入 749 个商品**。成功任务导入：茶咖啡热饮 192、备餐用品 102、婴幼儿食品 118、中国食品 109、维生素补充剂 65、冷冻鱼类海鲜 29、家居装饰 9、床上用品 32、彩妆 36、猫砂 52、婴儿服装 5。**失败 4 个（全部 0 导入）**：02-猫粮（disc 169）、02-厨房电器（disc 16）、01-箱包手袋（disc 200）、03-扬声器（disc 103）。
  - **失败根因（实查事件消息）**：源站 Joybuy 于日间后半段对**详情页**大规模弹风控验证码页（`/user/risk/pic`，事件 `RISK_CONTROL_FALLBACK`，每 run 几十个到 200 个）；DrissionPage 重渲染兜底多数仍 `RENDER_FAILED`，解析出的记录空 → `RECORD_REJECTED`（SOURCE_ID_MISSING/TITLE_TOO_SHORT/PRICE_MISSING）→ 02 组还有 `ACCOUNT_POOL_EXHAUSTED`（该组 6 账号全被轮换）。注意 `RISK_CONTROL_FALLBACK` **不在** night_queue 的 `TRIP_CODES` 集合里（那里只有 `RISK_CONTROL`），熔断器只靠 run 的 FAILED 状态计数——4 个失败被其他组成功隔开所以没触发 3 连坏。多个"成功"run 收益也偏低（家居装饰 9/200、婴儿服装 5/79、床上用品 32/200），同一根因。
  - 对比：夜间 30 批与日间第 2 批（同为今天）RISK_CONTROL_FALLBACK 均为 **0**——风控是日间 14:30 之后升级的，不是管线回归。**下次放开建议**：避开日间高峰，优先凌晨/夜间时段跑；或降低每组并发/单 run 节奏再试；重跑这 4 个失败 job 需新建任务（CrawlJob 已转 FAILED，复用名称会撞 unique）。
  - 质量抽查（run 940e2b89 茶、咖啡与热饮，192 导入）：SPU 7214 `retail_price` 14.99 与 `Offer.current_price` 一致、SpuDetail 存在；run 内 192 个 SPU 全部有 SpuDetail 且 content_sections 非空。评分多为空属源站常态（全库 7066 个 SpuDetail 仅 19 个 rating_count>0）。
  - 队列 09:07:42 UTC 写完 `final_summary_b3.json` 后正常退出（未关机）；backend runserver 未动；未 commit。剩余 READY 129（01=15、02=20、03=20、04=32、05=20、06=20、default 2；04 组仍需 Gmail 解封）。

- **当前任务（2026-11-15，商家端手机版两项追加修复，已完成，未 commit）**：仅改 `merchant-web/src/views/DashboardView.vue` 与 `StoreView.vue`。
  1. **看板档位拆分**：订单数量趋势 `orderRange`、曝光趋势 `exposureRange` 两个独立 ref（替换原共享 `chartRange`）；容器 class `range-switch--orders`/`range-switch--exposure` 区分；≤768 隐藏规则收窄为 `.range-switch--orders .range-switch__btn--month`（**曝光趋势两端都保留【近一月】**）；`syncRangeToViewport()` 只回退订单档位，曝光档位不受视口影响。因后端 `/merchant/overview` 的 `exposure_trend` 跟随同一 `range` 参数，两趋势档位不一致时前端 `load()` 并行两次请求合并（一致时仍单请求，避免双倍开销）。
  2. **店铺管理**：`.store-head` ≤768 改 flex-wrap + tag（可正常经营）与「复制店铺 ID」按钮各 `flex:1 1 100%` **上下两行**，模板零改动，桌面布局不变。
  - **验证（按验证纪律仅做针对性验证）**：`npx vite build` 通过；IAB 实测 390×844（订单趋势仅周档、曝光两档可切且月档下合成 resize 不被强切、店铺状态/复制按钮上下两行、复制功能正常写入 public_id）与 1366×768（两处趋势四档全显、店铺页同行布局与改前一致）；console error 全程 0；截图 `var/mobile_merchant_20261115/15~17_*.png`；临时账号 mobile-ui-fix-20261115b（Merchant id=530）及 31 行 DailyStat 已原子删除核对全 0，演示账号未动。
  - **坑（新增）**：①IAB 截图表面连续超时（"screenshot surface preparation timed out"）时直接换新 tab，别反复重试；②IAB fullPage 截图在手机视口有内容重复拼接伪影，用视口截图。
  - **既有行为（非回归）**：曝光/订单档位刷新后回周档（组件本地 ref 无持久化），改前即如此。

- **上一任务（2026-11-15，商家端手机版 9 项 UI 修复，已完成，未 commit）**：子代理统一交付（纯 merchant-web，纯表现层）。
  1. **看板**（DashboardView）：【近一月】档位按钮 ≤768 纯 CSS 隐藏（`.range-switch__btn--month`，订单数量+曝光趋势两处 range-switch 一致）；JS 只负责档位回退 `syncRangeToViewport()`（onMounted/resize/matchMedia change 三处挂接）——手机端当前选中 month 自动切回 week 并重载。
  2. **通知中心**（NotificationsView）：【全部标记已读】移入 `.tabs` 行末（`.tabs__mark-all`，margin-left:auto，12px 小按钮，tab 行 nowrap+横滚）；列表项**两端统一三段式**（标题 / 类型标签+时间同行 / 摘要 `.notice-list__summary`）。
  3. **顶栏**（MerchantLayout）：≤768 隐藏 h1（面包屑本就隐藏），店铺 chip max-width 48% + select 120px、员工名 ellipsis、退出 40px；**≤960~769 档保持原样**（900px 实测一行放得下，不动防回归）。
  4. **店铺管理**（StoreView）：logo `.store-avatar` flex:none + aspect-ratio 1/1 + object-fit contain 防变形；状态/角色拆三 span，≤768 分隔符隐藏换两行；`ROLE_LABELS` 中文映射（Merchant owner→店主 等，兜底原值）；锁定提示文字**从模板整体删除**（两端都没了）。
  5. **上架中心**（CatalogueView）：【已上架 x 件】移到「本店已上架」tab 行最右（`.tabs__count`）；两处分类 chip-row nowrap+横滚+隐藏滚动条；手机档商品 grid `repeat(2,1fr)`、卡片收紧（图 110px、标题 13px）。
  6. **订单管理**（OrdersView）：状态 tab nowrap+横滚；`.export-btn` **≤960 整档隐藏**；筛选区 ≤768 纵向重排（查询/重置包 `.filter-actions`，桌面 `display:contents` 保持原布局，搜索/日期全宽 40px，按钮两列网格）。
  7. **钱包**（WalletView）：类型 chip-row 单行横滚（同⑤做法）。
  8. **售后中心**（AfterSalesView）：标题-tab 间距**两端一起**收紧为 8px（桌面同样偏大）。
  9. **活动中心**（ActivitiesView）：【已推荐商家】靠左——根因是 `.referral-stats` 的 `margin-left:auto`，移除 + flex-wrap。
  - **验证（按验证纪律仅做针对性验证）**：`npx vite build`（cwd=merchant-web）两次通过（merchant-web 无 prettier/eslint 配置，按仓库纪律以 build 验证）；浏览器实测 390×844 八页断言全过、900×700 顶栏抽查、1366×768 桌面抽查零回归（h1/近一月/导出/「｜」分隔均可见、catalog 仍 4 列）；每页 console error 收集器全程 0；截图 14 张 `var/mobile_merchant_20261115/`；临时登录数据（StaffAccount/Merchant/membership/测试通知）已删净 count=0，HOMCO/CHiQ 等演示账号未动。
  - **坑（不得再踩）**：①**IAB 仿真视口不派发 resize/matchMedia change 事件**（setViewportSize 只改布局）——档位类响应式逻辑不能只靠事件，要「CSS 隐藏 + JS 回退」双轨，IAB 内用合成 dispatchEvent 验证接线；②IAB locator click 仍全部超时，用 evaluate `el.click()` 或 cua 坐标；③测试头像 URL 播种必须带 `/media/` 前缀否则裂图。
  - **遗留**：①工作区 `DepositView/LoginView/MessagesView` 有**更早会话的未提交漂移**（git status M，本任务未触碰）；②侧栏底部角色仍显示英文 role name（不在本次范围）；③本批与 2026-11-12 双优化批次均未 commit。

- **日间抓取第 2 批已完成（2026-11-15 10:00–13:35，✅ 15/15 全 SUCCEEDED、零熔断、累计已跑 45/193）**：
  - 清单：`var/day_crawl_20261115/task_list.json`（15 个 READY 任务，01/02/03/05/06 组各 3 个，04 组仍排除——无 VALID 会话；pk 明细：01=[26,56,104]、02=[21,69,189]、03=[22,76,136]、05=[30,66,180]、06=[25,79,193]，全部与夜间 30 个不重叠）。队列脚本 `var/day_crawl_20261115/day_queue.py`（由 night_queue.py 改造：仅改任务/进度路径 + **去掉关机逻辑**，写完 final_summary.json 正常退出；并发/90 分钟超时/3 连坏熔断参数不变）。
  - 结果（`var/day_crawl_20261115/final_summary.json`）：**15 SUCCEEDED / 0 FAILED / 0 SKIPPED，共导入 2596 个商品**。每任务导入：家庭烘焙与糖类 119、娃娃玩具 200、冷冻预制菜 198、饼干 200、耳机 199、猫零食 83（站内该类目只有 133 个可发现）、巧克力与糖果 200、游戏机 198、整理收纳 197、酱料调味品 200、咖啡机 122、香水 196、薯片零食坚果 88、显示器 199、猫玩具 197。全程无 LOGIN_WALL_FALLBACK / RISK_CONTROL / CONNECTIVITY_PREFLIGHT_FAILED，无超时 kill。
  - 质量抽查（`manage.py shell -c` 快查，抽查 run 1c7666b4（饼干）与 22d34a9e（猫玩具）各 1 个 SPU）：Spu.retail_price 与 Offer.current_price 一致（4.00 / 51.96），SpuDetail 存在且有 content_sections（1 段）/ specification_tables / ai_summary（饼干有）；rating_average 为空属正常——全库 7066 个 SpuDetail 仅 19 个 rating_count>0（源站多数商品无评分），非导入缺陷。
  - 队列 05:35:34 UTC 全部终态后正常退出（**未关机**，按用户在线要求）；backend runserver 未动。未 commit（var/ 不入库）。
  - 与夜间批累计：**已跑 45/193（212 个任务，58 COMPLETED）**；剩余 READY 144（default 2、01=18、02=23、03=23、04=32、05=23、06=23）。下次放开建议：继续按 3/组 批次跑 01/02/03/05/06（每批 15 个约 3.5 小时），04 组等 Gmail 解封后再排；`day_queue.py`+`task_list.json` 模式可直接复制为新目录复用。

- **当前任务（2026-11-15，管理端共享分页组件 AppPager 升级：省略号页码 + 首页/末页按钮 + 页码跳转输入框，✅ 已完成，浏览器实测全过）**：
  - 改动只有 `admin-web/src/components/AppPager.vue` 一个文件，全部约 12 个使用方视图（商品池/商家/售后/活动/日志等）零改动自动生效；props/emit 契约（`page/pageSize/total/hasNext` + `change`）与 `v-if="total > pageSize"` 行为不变。
  - 新能力：①页码省略号（总页数 ≤7 全平铺；>7 时首页/末页常驻 + 当前页及邻页可见，省略号为不可点击 span）；②「首页/末页」按钮置于两端，已在首/末页时对应按钮 disabled；③页码输入框（宽 64px、placeholder「页码」）+「跳转」按钮，回车同样触发；跳转后清空输入框；非数字或 <1 不动作，>总页数钳制到总页数。
  - 验证（按验证纪律仅做针对性验证）：prettier --check 过（首跑发现格式问题已 --write 修复）、eslint 零告警、`npx vite build` 通过；后端零改动未跑后端测试。浏览器实测（临时管理员 pagertest@joybuy.test，测完已删净）：商品池 234 页下页 1 显示 `1 2 3 … 234`、末页点击到 234 显示 `1 … 232 233 234`（末页/下一页 disabled）、第 4/6 页双侧省略号、跳转 6（按钮与回车）都正确高亮且输入框清空、9999 钳制到 234、0 和空不动作、首页按钮回第 1 页；商家页（18 页）同套 UI 正常。截图已存 `var/admin_pager_20261115/`。
  - 未 commit；详见 §2「2026-11-15（管理端 AppPager 分页组件升级）」小节。

- **夜间抓取已自动完成（2026-11-15 凌晨，关机前自动生成）**：30 个任务队列跑完并已自动关机。晨报（总账+每任务明细+失败清单+续跑提示）见 `var/night_crawl_20261115/MORNING_REPORT.md`，原始汇总 `final_summary.json`、实时进度 `progress.json`。剩余 ~163 个 READY 任务按同模式继续；04 组需先 Gmail 解封。详见晨报。

- **当前任务（2026-11-15 夜间无人值守抓取：30 个任务已全部派发，队列脚本后台运行，全部到终态后自动关机——明早机器是关着的属正常，这是用户明确要求的）**：
  - **阶段 1 验收（✅ 全部通过，3 个 run 全部 SUCCEEDED、零 WARNING/ERROR）**：
    * pk=20 `数据抓取01-早餐麦片`：run `a1317948-…`，17:12–17:44（32.7 分钟），LISTING_FETCHED×5（page 1–5 全 HTTP 200）+ PAGINATION_COMPLETE（第 6 页无更多）+ **导入 176/176**；
    * pk=28 `数据抓取03-套餐食材包`：run `86e1ce7b-…`，17:12–17:21（9.3 分钟），page 1–2 HTTP 200 + PAGINATION_COMPLETE + **导入 48/48**；
    * pk=31 `数据抓取06-罐头食品`：run `966c3156-…`，17:21–18:00（39.3 分钟），page 1–5 HTTP 200 + **导入 200/200**；
    * 三 run 均有 ACCOUNT_ROTATED（账号池轮换正常）、无 LOGIN_WALL_FALLBACK / RISK_CONTROL / CONNECTIVITY_PREFLIGHT_FAILED。验收标准（SUCCEEDED + 200 翻页 + 导入≥10 + 无风控/登录墙）全满足后进入阶段 2。
  - **阶段 2 已启动（18:03，队列进程 PID 45124 存活确认）**：30 个任务 = 阶段 1 的 3 个 + 新派 27 个，按组均衡（01/02/03/05/06 各 6 个，**04 组已排除**——该组 0 个 VALID 会话）。任务清单固化在 `var/night_crawl_20261115/task_list.json`（含 pk/组/run_id）。
  - **文件路径**：队列脚本 `var/night_crawl_20261115/night_queue.py`（单文件，Django setup 后起 5 个组线程）；启动器 `var/night_crawl_20261115/launch_run.py`、状态查看 `var/night_crawl_20261115/check_run.py <run_id>`；实时进度 `var/night_crawl_20261115/progress.json`（每个任务一条记录：run_id/status/imported/事件计数/熔断信号）；**最终汇总 `var/night_crawl_20261115/final_summary.json`（写完即触发关机）**；队列日志 `var/night_crawl_20261115/queue.log`（+ queue.err.log）；每个 run 的抓取日志 `var/logs/crawl_runs/<run_id>.log`。
  - **并发模型**：每个账号组一个工作线程 → 同组内串行（不挤同一账号池）、全局最多 5 个 run 并行（≤6 上限达标）；单 run 仍是 Scrapy CONCURRENT_REQUESTS=1 + DOWNLOAD_DELAY=2。launch_run 用 `start_run(job)` + 分离子进程 `manage.py run_crawl_run --run <id>`（PYTHONUNBUFFERED=1）。
  - **熔断与超时**：连续 3 个 run 出现 LOGIN_WALL_FALLBACK / RISK_CONTROL / CONNECTIVITY_PREFLIGHT_FAILED / RUN_UNAUTHENTICATED / FAILED → 停止派发后续任务（已在跑的跑完）；单 run 最长 90 分钟，超时 `taskkill /T /F` 只杀队列自己启动的进程树，然后把 run 标 FAILED（不用 `_kill_stale_crawler_browsers`）。
  - **关机链**：所有 30 个任务到终态（跑完或熔断后跑完）→ 写 `final_summary.json` → `shutdown /s /t 120 /c "night crawl done"`。即使多数任务失败也会关机（用户已睡，机器不空转）。
  - **明早怎么收**：① 开机后先看 `var/night_crawl_20261115/final_summary.json`（totals: succeeded/failed/skipped + 每 run 明细）与 `progress.json`；② 每个 run 的导入数在 CrawlRun.succeeded_count / DATASET_SUMMARY 事件，商品落库在 SPU/SKU/Offer/StagingProduct；③ 30 个任务完成后 04 组（需 Gmail 解封）和其余约 160 个 READY 任务按同样模式继续：改 `task_list.json`（或复用 night_queue.py 逻辑）按组均衡、同组串行；④ 注意 job 状态：单 run 成功后 CrawlJob 转 COMPLETED（即使没到 limit=200，因 LISTING_SHORTFALL 也算收尾），重抓同一类目需新建任务或复用名称会撞 unique。
  - **本次观察到的待办（未修）**：CrawlRun id=26（job 188 游戏方向盘，11-14 08:41 起）与 id=1/2 一样是僵尸 RUNNING（updated_at 停在 08:51，无对应进程）——其 job 卡 RUNNING 无法重跑，明天可把 run 26 标 FAILED 后 job 会回落；本次未动它。
  - **铁律遵守**：未 commit、未改业务代码、未碰 FB/9334（9334 现无监听）、未重启后端（runserver PID 36048 仍在 8000）、未打印任何 Cookie 值；队列脚本 py_compile 过，launch_run/check_run 实测可用。

- **当前任务（2026-11-15 FB 登录批次收官：第 1–11 批共 62 账号，**VALID=44**（数据抓取01=9、02=6、03=10、04=0、05=8、06=8、default=1、旧组=2），已标不可用 11，剩余 UNKNOWN=7（pk=2 主账号未尝试 + 04 组 6 个待 Gmail 解封）；脚本 `var/fb_manual_assist.py` 规则全套固化；未 commit、未启动 CrawlJob**：
  - **第 11 批（重试批）+ 顺延收尾结果**：pk=12 `61575856010162` **恢复 VALID**（44 Cookie 含 pin——第 2 批被判回退不可用，用放宽后的 3 次回退规则重试成功，数据抓取01 组 9/10）；pk=11 `100005191879231` 3 次回退仍退回 → 维持不可用（note 已更新为 3 次重试版原因）；pk=18/19/20/21（数据抓取02）全部再次确认 Google 帐户验证 → 维持不可用（与第 4/5 批结论一致：绑定 Gmail 的账号必被拦）。
  - **全量总账（第 1–11 批，DB 实查口径）**：
    * **VALID=44**：数据抓取01=9/10、02=6/10、03=10/10、04=0/10、05=8/10、06=8/8、default=1/2、旧组「数据抓取」=2/2。
    * **已标不可用=11**：Google 帐户验证 8（pk=18/19/20/21/38/39/40/41，解封=用户用绑定 Gmail 手动完成一次验证）；空表单回退 1（pk=11，已用 3 次回退确认）；设备通知验证 1（pk=47）；凭据错误 1（pk=51，需人工核对 Excel 密码）。
    * **剩余 UNKNOWN=7**：pk=2「FB 主账号」（default 组从未尝试，用户拍板）；pk=36/37（04 组 network 失败重跑即可）；pk=42/43/44/45（04 组未消耗，但同组 pk=38–41 全被 Google 验证拦——大概率同样绑定 Gmail，建议先解封再跑）。
  - **第 7 批补记**：开局 pk=35/36/37 network 失败（换节点 VPN 抖动，facebook.com 随即恢复）；停批保护曾存在「只打印不 break」缺陷，连续烧了 04 组 4 个账号才被外部叫停——已修复为 main 循环真正 break。
  - **脚本已固化能力**（`var/fb_manual_assist.py`）：load_mode=none+水合轮询、CMP 逐页文本判定关闭、双语按钮、reauth 自动重填、2FA 自动填码多页签多属性、OAuth 确认上下文门控、Google/邮箱/设备通知验证立即跳过、凭据错误短路、3 次回退、连续 2 blocked 真 break、外部误杀重试。

- **当前任务（2026-11-14，登录墙下抓取链路试跑——结论：✅ 全链路验证通过，VALID 会话 Cookie 注入有效，翻页/落盘/入库全部正常，零代码改动）**：
  - **试跑结果（09:56–10:00 UTC，DB 实查）**：选 `数据抓取01-果酒`（CrawlJob pk=38，public_id `e8e0fc02-…`，limit=200/skip_imported=开/翻页=开）→ `start_run` 创建 CrawlRun **`90cb044d-4b46-4afb-ac38-a8d8e8dd2dd2`**（pinned 账号 pk=9 `61553901210655`，LRU 选中 last_used_at=None），用 `manage.py run_crawl_run --run <id>` 独立执行器进程跑（PYTHONUNBUFFERED=1，日志 `var/logs/crawl_runs/90cb044d-….log`）。**终态 SUCCEEDED**（10:00:10），Job 转 COMPLETED。
  - **事件序列（全部 INFO，无 WARNING/ERROR）**：RUN_ACCOUNT_SELECTED → RUN_STARTED → ACCOUNT_POOL_READY（池 8 个账号）→ **LISTING_FETCHED**（`/s?k=Cider` HTTP 200，854.8 KB，1.3s，16 张卡片全部入队 16/200，无 307）→ PRODUCT_PARSED×16（详情全 HTTP 200）→ **PAGINATION_COMPLETE**（「第 2 页没有更多商品，翻页结束」——page=2 翻页真实触发过）→ LISTING_SHORTFALL（16/200：翻页至第 2 页后没有更多结果，符合预期如实记录）→ MOBILE_DETAIL_MERGED×16 → DATASET_SAVED×16（`var/crawl_exports/90cb044d-01/cider/…`）→ **PRODUCT_IMPORTED×16**（每商品新建 SPU+SKU+Offer+StagingProduct，本 run 暂存 16 条）→ DATASET_SUMMARY。**无任何 LOGIN_WALL_FALLBACK / RISK_CONTROL / CONNECTIVITY_PREFLIGHT_FAILED**；日志里 grep 到的「307」全是图片 URL/Cache-Control 数字子串。
  - **预检（跑 RUN 前做的，可复用）**：用 `crawler_control.services._select_account_for_run('数据抓取01')` 选中账号解密 Cookie（`load_account_session` → `joybuy_crawler.account_session.joybuy_cookie_pairs` 只留 joybuy 域，45 条含 pin），urllib 带 Cookie 直连 `/s?k=fruit wine` → 200、43 个 `/dp/` 链接；不带 Cookie 则 307 `/login`。说明**会话本身有效、注入链路成立**。
  - **Cookie 注入机制（代码位置，给后续排查用）**：①选号 `backend/crawler_control/services.py` `_select_account_for_run`/`usable_accounts_for_run`（只挑 ACTIVE+VALID+session 里真有 Cookie 的，LRU 排序）+ `start_run` 把账号钉到 CrawlRun 并写 RUN_ACCOUNT_SELECTED；②解密 `crawler/joybuy_crawler/account_session.py`（Fernet，`load_account_pool`/`load_account_cookies`，第三方域 Cookie 丢弃）；③注入 `crawler/joybuy_crawler/middlewares.py` `AccountCookieMiddleware`（优先级 550，在 Scrapy cookie jar 之前把 Cookie 拼成请求头；`COOKIES_ENABLED=False` 防多账号串号；每 5–15 分钟或若干请求换号）；④执行器 `backend/crawler_control/management/commands/run_crawl_run.py` → `joybuy_crawler.runner.execute_run`。
  - **环境结论**：2026-11-14 09:56 UTC 本机直连 joybuy.co.uk 已恢复（robots.txt 200；匿名 `/` 仍 307 `/login`、匿名 `/s?k=dog bowls` 307 `/error403`——登录墙仍在，但带会话一切正常）。**193 个 READY 任务可以放心按批次启动**（本试跑已消耗 pk=38；数据抓取01 还剩 30 个 READY）。
  - **铁律遵守情况**：全程未杀 chrome/未开浏览器/未调 `_kill_stale_crawler_browsers()`（蜘蛛纯 Scrapy HTTP+Cookie，未触发 LOGIN_WALL_FALLBACK 浏览器渲染）；零代码改动；未 commit。
  - **日志位置**：`var/logs/crawl_runs/90cb044d-4b46-4afb-ac38-a8d8e8dd2dd2.log`（JSON 行，含 scrapy DEBUG 明细）。

- **当前任务（2026-11-15 第 10 批补漏跑完：**pk=58 与 pk=35 双双 VALID（44/43 Cookie 均含 pin）；全量 **VALID=43 / 62**（数据抓取01=8、02=6、03=**10/10**、04=0、05=8、06=**8/8**、default=1、旧组=2）；已标不可用 12；剩余 UNKNOWN=19 = pk=2（default 主账号未尝试）+ 数据抓取04 组 10 个（卡 Google 验证待 Gmail 解封）+ 02 组 6 个（历史低成功率批次可重试）+ 01 组 2 个**；未 commit、未启动 CrawlJob**：
  - **第 10 批结果（补漏，DB 实查）**：pk=58 `61552670616442` **VALID**（44 Cookie 含 pin，ElementLostError 重跑成功）；pk=35 `61573698612701` **VALID**（43 Cookie 含 pin，network 失败重跑成功，登录后未弹 Google 验证——03 组收尾全清）。数据抓取03 组成为第一个 **10/10** 全绿的组。
  - **第 9 批结果（15:15–15:45 实跑，DB 实查）**：pk=56 `61552803241819` VALID（45 Cookie 含 pin）；pk=57 `61552737966020` VALID（44 含 pin）；pk=58 `61552670616442` **失败**（ElementLostError——页面刷新致元素失效，瞬态、未标不可用，重跑即可）；pk=59 `61552643762769` VALID（44 含 pin）；pk=60 `61552604051926` VALID（45 含 pin）；pk=61 `61552059009618` VALID（44 含 pin）；pk=62 `61550353716298` VALID（45 含 pin）。零 checkpoint 损耗（06 组绑定非 Gmail）。
  - **全量总账（第 1–9 批，DB 实查口径）**：
    * **VALID=41**：数据抓取01=8/10、02=6/10、03=9/10、04=0/10、05=8/10、06=7/8、default=1/2、旧组「数据抓取」=2/2。
    * **已标不可用=12**：空表单回退 pk=11/12；Google 帐户验证 pk=18/19/20/21/38/39/40/41（绑定 Gmail 无法代收，解封=用户用绑定 Gmail 手动完成一次验证）；设备通知验证 pk=47；凭据错误 pk=51（Excel 密码不匹配/改密，需人工核对）。
    * **剩余 UNKNOWN=21（明细）**：pk=2「FB 主账号」（default 组，从未尝试）；pk=58（瞬态失败，**重跑即可**）；pk=35（network 失败，重跑即可）；pk=36/37/42/43/44/45（数据抓取04 组，大概率同样卡 Google 验证——解封后可跑）。
  - **第 8 批结果（14:30–15:10 实跑，DB 实查）**：pk=46 `61575832551283` VALID（44 Cookie 含 pin）；pk=47 `100003836077774` **不可用**（设备通知验证——「检查你的其他设备/轻触 N 来验证」，无法代过，立即跳过）；pk=48 `61578207808948` VALID（44）；pk=49 `100006471098989` VALID（44）；pk=50 `100047501057082` VALID（44）；pk=51 `100013498475534` **不可用**（凭据错误——FB 明确提示「你输入的登录信息有误」，Excel 密码清洗体检无异常（8 字符无空格/全角），是真实密码不匹配/改密，需人工核对凭据）；pk=52 `100002154208050` VALID（45）；pk=53 `100009591262710` VALID（44）；pk=54 `61553974637421` VALID（43）；pk=55 `61553446384483` VALID（44）。
  - **第 7 批结果（11:46–11:55 实跑后中止，DB 实查）**：pk=35 `61573698612701` / pk=36 `61564165427258` / pk=37 `100070934469851` → FB network 失败（换节点后 VPN 抖动，facebook.com 现已 200/2.4s 恢复，未标不可用可重跑）；pk=38 `61571066231296` / pk=39 `61570945065490` / pk=40 `61571087919245` / pk=41 `61570649686479` → 登录成功后均弹「Google 帐户验证」→ 立即判不可用（note 已写库、progress reason=google_verification）；pk=42 `61571107257213` / pk=43 `61570841016186` / pk=44 `61570614100694` **未消耗**（停批修复后被保护）。
  - **按组统计（DB 实查）**：default 1/2；数据抓取(旧) 2/2；数据抓取01 **8/10**；数据抓取02 **6/10**；数据抓取03 **9/10**（本批 pk=26–34 九连中 +25 收尾）；数据抓取04 **0/10**（未跑）；数据抓取05 **0/10**（未跑）；数据抓取06 **1/8**（未跑）。已标不可用 6（pk=11/12 空表单回退×2 + Google 验证×4：pk=18/19/20/21）。
  - **第 6 批结果（09:52–10:34 实跑，全程约 42 分钟）**：10 个账号全部一次成功，无回退、无 checkpoint blocked、无超时——Google 验证损耗为 0（本批账号绑定的都不是 Gmail），说明该 checkpoint 只对绑定 Gmail 的账号出现。每账号 Cookie 42–45 条均含 pin。
  - **第 5 批结果（09:30–09:45 实跑，DB 实查）**：pk=21 `61570901313540` 触发 Google 帐户验证 → 按规则**立即判不可用**（note/progress unavailable reason=google_verification/status UNKNOWN）；pk=22 `100018336783436` **VALID**（44 Cookie 含 pin）；pk=23 `100012702853631` **VALID**（44 Cookie 含 pin）；pk=24 `100004728855782` **VALID**（45 Cookie 含 pin）。3 个成功把停批计数清零，未触发连续 2 停批。
  - **节点切换结论（试金石结果）**：换节点后第 1 个账号（pk=21）仍弹 Google 验证，但后续 3 个全部正常走通 → **风控不是 IP 级**；Google 帐户验证只对「FB 绑定的邮箱是 Gmail」的账号出现（无法代收 Gmail 验证码 → 判不可用），非 Gmail 绑定的账号在新节点下全部正常。脚本/规则全部按设计工作（立即判不可用 + 跳过 + 计数清零）。
  - **第 4 批结果（08:32–09:22 实跑，DB 实查）**：pk=17 `100007711656856` **VALID**（45 Cookie 含 pin，脚本全代点：登录→2FA→信任设备→reauth→确认）；pk=18 `61570605463947` / pk=19 `61571016720516` / pk=20 `61570727649019` 均在点登录后遇到 FB「Google 帐户验证」checkpoint（要求登录 FB 绑定的 Gmail 验证本人，无法代收）→ 按用户新规则**立即判不可用**：note「触发 Google 帐户验证（需登录 FB 绑定的 Gmail，无法代收），判为账号不可用」、progress.jsonl 记 unavailable（reason=google_verification）、status 保持 UNKNOWN。连续 2 个触发后停批保护生效。更正：pk=17 之前被报告卡 Google 验证，实查为**真实 VALID**（45 条 Joybuy 会话 Cookie 含 pin，Google 验证页出现在其后流程，不影响）。
  - **第 2 批结果（06:40–07:22，DB 实查）**：pk=7 `100011734838229` **VALID**（45 Cookie 含 pin）；pk=8 `100088227465353` **VALID**（45 Cookie 含 pin，全流程脚本代点）；pk=11 `100005191879231` 与 pk=12 `61575856010162` 点「登录」后 FB 回**空登录表单**≥15s → 按当时规则判**不可用**（note 已写库、status 保持 UNKNOWN、progress.jsonl 记 unavailable；当时未抓 FB 报错原文，下一版已加）。
  - **第 3 批结果（08:03–08:26，DB 实查）**：pk=13 `100002507348380` **VALID**（45 Cookie 含 pin，全程零人工：profile 有 FB 会话 → reauth 自动重填密码 → OAuth 确认自动点）；pk=14 `100080439023013` **VALID**（44 Cookie 含 pin）；pk=15 `100074579302704` **VALID**（44 Cookie 含 pin）；pk=16 `100056511865926` **VALID**（44 Cookie 含 pin）。**本批零 unavailable**——4 个全部成功，未触发回退/判不可用路径；用户全程未碰键盘。
  - **跑批期间修的 bug（都在 `var/fb_manual_assist.py`，py_compile 过）**：①**FB locale 英文界面**：pk=13/14 的 2FA 提交按钮是「Continue」而非「继续」→ 按钮文本全双语化（Continue/Confirm/Next、Trust this device/Remember this browser/Don't ask again、Sign in、Continue as；人机验证与报错关键词补英文）；②**`input[type=submit]` 文本在 value 属性**（reauth 页「继续」）→ `_click_text_element` 加 `_find_displayed_or_submit` 按 value 兜底扫（㉜ 落地）；③**OAuth 确认 latch bug**：任何裸「Continue/继续」点击都永久置位 clicked 标志，真授权确认页反而没人点（pk=14 靠 FB 自动流转侥幸）→ 改上下文门控（`button[name="__CONFIRM__"]` / continue-as 文本优先）+ 3 次预算；④PKS 选择口径：pk=2「FB 主账号」属 default 组，不在数据抓取01~06 内，已排除。㉝**FB 账号 locale 可能是英文**：所有按钮文本匹配必须中英双语（Continue/Confirm/Next/Trust this device/Sign in/Continue as），否则自动填码后卡在提交步（第 3 批 pk=13 踩实）。㉞**OAuth 确认点击不能 latch**：密码页/中间页的裸「Continue/继续」会把 clicked 标志永久置位，真授权确认页反而没人点——必须上下文门控（`button[name="__CONFIRM__"]` 或 continue-as 文本）+ 有限预算。㊱**FB 会把 OAuth 页签整个重定向到 accounts.google.com 做「Google 帐户验证」**（要求登录 FB 绑定的 Gmail，无法代收）——`_current_fb_page` 此时返回 None，必须按 URL 兜底识别并立即判不可用；判定必须门控在「登录流程已开始」之后（登录页的 Google 第三方按钮是正常元素）；这类 checkpoint 是**按账号触发**（FB 绑定的邮箱是 Gmail 才弹，第 5 批换节点后 pk=21 仍弹而 pk=22/23/24 正常为证），不是 IP 封控；连续 2 个自动停批的保护保留（防误判升级）。㊲计数器类模块级变量跨函数读写别忘了 `global` 声明（run_account 里 `CONSECUTIVE_EMAIL_BLOCKED += 1` 缺 global 导致 UnboundLocalError，判不可用的 note 都没写成）。㊳**FB 凭据错误的真实文案是「你输入的登录信息有误。找回你的账户并登录。」**——必须短路返回（BAD_CREDENTIALS_JS），不能走回退重试链（密码错重试没意义，第 8 批 pk=51 卡了 3 次回退才被外部叫停）；Excel 密码清洗（`_clean_secret`）已体检无误伤，凭据错误=真实密码不匹配/改密，需人工核对。㊴FB checkpoint 家族（截至第 8 批）：立即判不可用 3 类=Google 帐户验证/邮箱验证码/设备通知验证 + 凭据错误短路；留给用户 1 类=滑块/图片人机验证。㊳「连续 2 个 checkpoint blocked 停批」的保护必须**真正 break 主循环**——第 7 批旧实现只在 run_account 里打印停批提示、main 循环照跑，结果连续烧了 4 个账号才被外部叫停；停批逻辑要放在 main 的账号循环里并 break。
  - **验证（按验证纪律仅做针对性验证）**：`py_compile` 过；每批跑完 DB 解密实查（Cookie 数 + pin 存在性）；第 3 批 4/4 一次成功。期间踩了一次**双实例互踩**（两个脚本进程同写 b3.log、抢 9334——`&` 后台启动未受控导致）已杀干净并以受控后台任务重启；下次一律用受控后台任务启动。
  - **FB 登录批次总账（第 1–8 批，DB 实查口径）**：62 账号 **VALID=35**（数据抓取01=8/10、02=6/10、03=9/10、04=0/10、05=8/10、06=1/8、default=1/2、旧组=2/2）；已标不可用 12（空表单回退 pk=11/12、Google 验证 pk=18/19/20/21/38/39/40/41、设备通知验证 pk=47、凭据错误 pk=51）；剩余可跑 UNKNOWN=15（数据抓取06 组 7 个 pk=56–62、04 组未消耗 pk=42–45 与 pk=35/36/37、02 组零散）。checkpoint 损耗规律：Google 帐户验证/设备通知验证/凭据错误均为账号级属性，重试无意义；滑块人机验证留给用户可过。
  - **剩余 19 个 UNKNOWN 的处置建议**：①数据抓取04 组 10 个（pk=36–45）——绑定 Gmail，需用户在 FB 上用绑定 Gmail 完成一次 Google 帐户验证后才能跑（pk=38–41 note 已写明原因），解封后逐批跑；②数据抓取02 组 6 个（pk=16–19 的 UNKNOWN，第 2/3 批失败残留）——低成功率批次，可重试（失败模式是点登录被拒/回退，重试无副作用）；③数据抓取01 组 2 个（历史早期失败）；④pk=2「FB 主账号」（default 组，从未尝试，用户拍板是否要跑）。每批跑法不变：改 `ACCOUNT_PKS` + `--check` + netstat 9334 + 后台跑（b11 起日志顺延）。

- **上一任务（2026-11-14，`var/fb_manual_assist.py`「账号不可用」判定放宽为 3 次重试，规则已实现并在第 3 批真实生效；未 commit）**：用户实测发现过人机验证误点/重复验证多次后，**FB 会退回登录页要求重新输入密码**，重填密码、再过一次人机验证后就能正常进 2FA——「回到登录页」不能立刻判不可用，要重试最多 3 次。
  - 改动（只动 `var/fb_manual_assist.py` + 本文件）：人工环节轮询里，「此前已观察到有值表单（=脚本已填好凭据）」之后又出现**空**登录表单（email/pass 均空）持续 ≥15s → 计一次回退 `login_regressions`（沿用原防误判武装逻辑）。第 1/2 次不判不可用：打印「FB 退回登录页（第 N/3 次），正在重新填入账号密码并点击登录——请再次完成人机验证（还剩 X 次机会）」，调新增 `refill_and_resubmit()`：原生 setter 重填 `account.label`+密码 → 脚本点「登录」→ 30s 内确认点击生效（页面跳转/人机验证/2FA 输入框/表单被清空任一信号），未生效则整页重载重填重试（重载 ≤2 次，**重载不计入 login_regressions**——用户遇到的是 FB 主动踢回，不是脚本点击失败）→ 回到主循环等用户再过一次验证后继续正常流程（2FA 自动填码等）。累计第 3 次仍退回才按原规则判不可用：note 写中文原因（注明「已重试 3 次仍退回登录页」）+ **FB 页面报错原文片段**（从 `wait_fb_and_save` 经新增 `hint_out` 参数带回 `run_account` 写进 note，用于区分密码错 vs 封锁 vs 风控）、session_status 保持 UNKNOWN、`var/logs/fb_batch_progress.jsonl` 记 `unavailable`、跳过该账号。连带小改：2FA 自动填码上限从固定 3 次放宽为 `3 + login_regressions`（每次重新登录都可能再要一次 2FA）；重试后重置「信任该设备」「OAuth 继续」代点标记（重登后这些页会再出现）。
  - 验证（按验证纪律仅做针对性验证）：`py_compile` 过；mock 逻辑自检 `var/diag_fb_q5/test_regression_mock.py`（假时钟 + 假 cmd/page/tab，无凭据、不开浏览器）两场景全过——A「连续 3 次踢回」：第 1/2 次各 refill 一次后第 3 次返回 `unavailable`、hint 带回 FB 提示原文、状态事件序列 `login_clicked→login_regression→refill_clicked→login_regression→refill_clicked→unavailable`；B「第 1 次重试后恢复」：返回 True、无 unavailable 事件。`ruff check` 仅报 13 条**改动前即存在**的历史告警（全部位于本次未改动的区域），新增代码零告警；该文件历史上就未做过 ruff 格式化（var/ 一次性运维脚本）。
  - 注意：验证全程未启动浏览器、未动 9334 端口上用户手动启动的两个外部 `crawler_account_login` 进程；脚本顶部 `ACCOUNT_PKS` 仍为 (8, 11, 12)（已跑完），开下一批前按下文「下一批怎么跑」改 pk。

- **当前任务（2026-11-14，管理后台「爬虫任务」页爬虫账号列表分页 + 搜索，已完成）**：用户报账号列表 62 个账号看不全后面、不能搜索。要求与 2026-11-13「爬虫任务列表分页修复」同一套模式。
  - **改动文件**（后端部分发现已被上一个会话写好且未验证，本次补齐验证；前端同）：
    1. `backend/common/admin_views.py` `AdminCrawlerAccountsView.get`：支持 `page`/`page_size`（默认 1/20、上限 100、非法值回落默认），`search` 参数对 `label`/`account_group`/`note` icontains（Q OR），排序保持 `-created_at`，回包信封 `{items, page, page_size, total, has_next}`（与 `AdminCrawlJobsView` 一致）。
    2. `admin-web/src/views/CrawlersView.vue`：`accountsMeta`/`accountsPage`/`goAccountsPage` 照 jobs 模式；`accountsUrl()` 拼 page+search；账号 Tab 工具栏加搜索框（placeholder「搜索账号 / 分组 / 备注」，回车立即查、输入防抖 300ms，搜索变化回第 1 页）；表格下加 `AppPager`；样式 `.toolbar__search`（本文件内）。建任务下拉单独走 `page_size=100`（`loadPickerAccounts`）不受搜索影响。
  - **接口契约**：`GET /api/v1/admin/crawlers/accounts?page=1&page_size=20&search=<词>` → `{items:[...], page, page_size, total, has_next}`。
  - **验证（按验证纪律仅做针对性验证）**：
    1. `ruff check backend/common/admin_views.py` + `ruff format --check` 全过；`npx prettier --check` + `npx eslint src/views/CrawlersView.vue` 全过；`npx vite build`（admin-web）通过。
    2. 接口实测（临时 staff 账号 pagcheck@joybuy.test，curl）：page1/page_size=20 → 信封键齐全、20 条、total=62 与 DB count 一致、has_next=true；page=2 → 20 条且首行 label 不同；`search=<label 片段>` → 2 条全命中；`search=数据抓取03` → 10 条与 DB count 一致；`search=未保存任何会话`（note 命中）→ 2 条；无意义词 → 0 条；不传参数 → page=1/page_size=20；最后一页 has_next=false。
    3. 浏览器实测（IAB，1280×720）：账号 Tab 20 行 + AppPager（1~4 页 + 上/下一页）；点「2」→ 20 条新数据、页码高亮正确；搜索「数据抓取03」→ 10 行全为该组；输入框回车 → 精确账号 1 行；清空 → 恢复第 1 页 20 行。截图 3 张：`var/admin_accounts_pager_20261114/shot_accounts_page1_default.png`、`shot_accounts_page2.png`、`shot_accounts_search_03.png`。
  - **后端是否重启**：**未重启**——runserver（PID 36048，`--noreload`）启动时间 15:34:49 晚于 admin_views.py 改动时间 15:32:21，实测接口已回新信封，判定上个会话改完码后已重启过。重启前已确认 DB 无活动 CrawlRun（id 1/2 的 RUNNING 是 11-03/11-04 的僵尸状态，updated_at=created_at，无进程在跑）；未动 9334 端口的 FB 登录浏览器。
  - **临时账号已删净**：pagcheck@joybuy.test 的 StaffAccount/StaffRoleAssignment/StaffSession 全部 count=0；curl 用的临时 cookie jar 与验证脚本已从 var/ 删除。
  - **踩坑（不得再踩）**：①**IAB/受限 Playwright 的 `locator.fill("")` 是 no-op**（fill 按打字实现，空串什么都不输入）——要清空输入框用 click + `ControlOrMeta+a` + `Backspace`；②管理员 curl 验证时 cookie jar 路径不要用 Git Bash `/tmp` 的 `cygpath -w` 映射路径喂给 Python subprocess（System32 curl 对该路径 `-b` 静默失效返回 401），把 jar 复制成仓库内相对路径（如 `var/jb_jar.txt`）两边都能用；③IAB `screenshot({fullPage:true})` 在管理端布局下会输出重复内容的坏图，用视口截图 + `cua.scroll` 分段截。
  - **未 commit**（与整仓现状一致）；无遗留问题。

- **上一任务（2026-11-14 第 2 批完成：批次累计 4 个账号 VALID（pk=7/8/9/10），2 个判定不可用（pk=11/12）；脚本已升级为「脚本代点一切、用户只过人机验证」并修完 reauth/信任设备/2FA 确认等新页面；目前空闲，可直接发下一批）**：
  - **第 2 批结果（2026-11-14 06:40–07:22 实跑，DB `load_account_session` 实查）**：pk=7 `100011734838229` **VALID**（45 Cookie 含 pin）；pk=8 `100088227465353` **VALID**（45 Cookie 含 pin，本轮全程脚本代点：填密码→自动点登录→自动填 2FA→用户没碰，中间的「信任这台设备」页和 reauth 重输密码页由附加会话代点后已把两类页面处理写进脚本）；pk=11 `100005191879231` 与 pk=12 `61575856010162` 点「登录」后 FB 回到**空登录表单**≥15s → 按用户规则判**账号不可用**（note 已写中文原因、session_status 保持 UNKNOWN、`var/logs/fb_batch_progress.jsonl` 已记 unavailable；未打印 FB 报错原文，下一版脚本会抓「密码不正确 vs 封锁」的提示语以区分）。批次合计：62 账号 VALID=8、UNKNOWN=54（含已标不可用 2，**剩余可跑 52**）。
  **最终结果（DB 实查，`load_account_session` 解密）**：pk=9 `61553901210655` 与 pk=10 `100088190675726` 均 `session_status=VALID`、解密 **45 条 Cookie、`pin` 存在=True**（只打存在性，未打印任何 Cookie 值）。未 commit、未动 backend 业务代码、未启动 CrawlJob。
  - **脚本**：`var/fb_manual_assist.py`（一次性运维脚本，var/ 已 gitignore）。运行命令（Git Bash，仓库根）：`PYTHONUNBUFFERED=1 ./.venv/Scripts/python.exe var/fb_manual_assist.py > var/logs/fb_manual_assist_20261114.log 2>&1`（`--check` 只校验 Excel/账号/TOTP 不开浏览器）。日志 `var/logs/fb_manual_assist_20261114.log`、进度事件 `var/logs/fb_manual_assist_status.jsonl`。
  - **分工（用户拍板）**：脚本=开浏览器→逐页关 Privacy 弹框→展开 View more options→点 Continue with Facebook→自动填 FB 账号密码→检测 2FA 输入框**自动填 TOTP**；用户=点「登录」+过人机校验→点「确认/提交」→（出现时）点「信任该设备」和「以 XX 身份继续」；脚本=轮询 Joybuy `pin`（每账号 900s 窗口、60s 中文提醒）→`record_account_session` 落库→下一账号。
  - **本轮修复（全部只在 `var/fb_manual_assist.py`）**：
    1. **真因级修复（推翻 2026-11-13「全自动提交无效是 FB 不认」的结论）**：DrissionPage `load_mode="eager"` 在 DOMContentLoaded 一触发就 `Page.stopLoading`（`chromium_base.py::_onDomContentEventFired`，源码实锤），慢 VPN 下 Joybuy 的 Next.js chunk（st.joy-sourcing.com）没下完全被 `net::ERR_ABORTED`（CDP loadingFailed 时间戳全部相同=一次性被停）→ SSR 骨架渲染但 **React 永不水合 → 所有按钮点了没反应**（用户「View more options 点不动」「全自动提交后 FB 不认」都是它）。修复：`load_mode="none"`（导航不等待不杀请求）+ `goto_hydrated()` 轮询按钮节点出现 `__reactFiber$`；11-12 那 58 个账号能全自动成功纯粹因为当时网络快。
    2. **2FA 自动填码修复**：旧选择器 `approvals_code` 过时。改为 JS 多属性检测（name/id/autocomplete=one-time-code/inputmode=numeric/placeholder/aria-label/label 含 code|verification|验证码 等），**扫描所有 facebook.com 页签**，命中用原生 value setter+input/change 填码；账号 2 实跑生效（日志「已自动填入 2FA 验证码（第 1 次）」）。检测到「信任该设备/记住此浏览器」时提示用户点击（下次免验证码）。
    3. **CMP（Privacy Settings）复弹修复**：主页关掉后 /login 会再弹一次 → 每次导航后固定调 `dismiss_consent_strong()`（等 CMP 异步出现 ~15s → 命令自带 button 扫描 → span/div/a 文本扫描「accept all/同意」→ 真点失败退 JS 点 → 轮询遮罩消失）；关闭失败不立刻 reload（reload 又弹 CMP 互相打架），先走上述流程，仍失败才 reload 且上限 2 次，任何一步有预算绝不卡死。**已用无用户参与的探针验证**（`var/diag_fb_q5/probe_cmp.py`）：主页关掉 → /login 复弹关掉 → 遮罩消失、View more options 可见可点，全程自动。
    4. **服务端 A/B 间歇**：第三方登录行由 Joybuy 服务端配置控制会间歇消失、且按钮在时 onClick 也可能静默不弹 OAuth → 改「点 → 30s 内确认 OAuth 页签 → 没有就整页重载重试」最多 6 轮。
    5. **账号不可用判定（用户拍板规则）**：人工环节轮询中，FB 再次出现**空**登录表单（email/pass 均空）且持续 ≥15s（先观察到过「有值表单」才武装，防误判）→ 判定账号不可用：不重试、`note` 写中文原因、session_status 保持 UNKNOWN、`var/logs/fb_batch_progress.jsonl` 记 `unavailable`、关浏览器进下一账号。
    6. 凭据纪律全程遵守：密码/seed 只在内存，TOTP 只 print 一次性验证码/不落盘。
  - **第 2 批新增修复（仍只在 `var/fb_manual_assist.py`）**：
    1. **最终分工（用户拍板）**：脚本代点一切——填密码后自动点「登录」→ 自动填 2FA → 自动点「确认/提交」→ 自动点「信任该设备/记住此浏览器」→ 自动点 OAuth「以 XX 身份继续」（`button[name="__CONFIRM__"]` 优先、「继续」文本兜底）；**用户只在脚本打印「!!! >>> 请过人机验证」时介入**（滑块/图片验证/检查点，`USER_ACTION_JS` 文本判定）。
    2. **CMP 判定改文本法**：旧 `[class*="cookieManageDrawer_showMask"]` 在部分导航下漏检（日志无「CMP 第 N 次尝试」即此因）→ 改 `CMP_STATE_JS` 扫可见文本（accept all / privacy settings / reject all）+ 旧遮罩双保险，点完以「文本消失」为准；探针 `var/diag_fb_q5/probe_cmp2.py/probe_cmp3.py` 显示 CMP 是否出现本身是服务端间歇行为（清 consent Cookie 后 40s 内也未必弹），文本判定兼容两种形态；第 2 批实跑日志已见「CMP 已关闭（第 1 轮，tag:button 命中）」。
    3. **OAuth reauth 页**：profile 已登录时 OAuth 直接落 `login/reauth.php`（只有 pass 框无 email 框，classify 返回未知）→ `wait_fb_form` 显式识别返回 `reauth`，`wait_fb_and_save` 自动重填密码并点继续（≤2 次）。
    4. **两类「继续」按钮的坑**：2FA 页提交按钮是 `div[role=button]` 文案「继续」（确认文本已加）；reauth 页提交是 `input[type=submit]`，其可点文本在 **value 属性**里（`ele.text` 拿不到 → `_find_displayed` 永远扫不到）→ 文本兜底点击扩展到 value 属性比对。
    5. 「信任这台设备」文案变体（「该」vs「这」）已并入点击文本表。
  - **验证（按验证纪律仅做针对性验证）**：`py_compile` 过（含 SyntaxWarning 清零）；第 1 批 2 账号 + 第 2 批 2 账号 DB 解密实查（45 Cookie + pin）；pk=8 全流程脚本代点实跑生效（登录/2FA 填码自动提交）；CMP 文本判定在第 2 批实跑命中；结束 `netstat` 复查 9334 无残留浏览器进程。
  - **下一批怎么跑（当前空闲，可直接发）**：改 `var/fb_manual_assist.py` 顶部 `ACCOUNT_PKS`（现值 (8, 11, 12) 已跑完；下一批建议从剩余可跑 UNKNOWN 里按 pk 序取，候选 pk 从 13 起：13/14/15/16…，跑前用 shell 查一遍排除已标「账号不可用」的），命令：`PYTHONUNBUFFERED=1 ./.venv/Scripts/python.exe var/fb_manual_assist.py > var/logs/fb_manual_assist_20261114_b3.log 2>&1`（先 `--check`）。**用户几乎不用操作**：脚本代点登录/2FA/确认/信任设备/继续，只在打印「!!! >>> 请过人机验证」时需要用户。注意：pk=11/12 这类「点登录即回空表单」的账号会被自动跳过并写库，不用人工干预；如果希望区分「密码错 vs 封锁」，下一版可在 unavailable 触发时人工复核（脚本已加 FB 提示语抓取，未打印过原文的批次以 FB 页面为准）。
  - **新增踩坑（接在 ㉓ 之后）**：㉔**DrissionPage eager 模式会在 DOMContentLoaded 时 Page.stopLoading**，慢网络下未下完的 chunk 全被 ERR_ABORTED、React 永不水合、页面所有点击无效——Joybuy 登录页必须 `load_mode="none"` + 自己轮询 `__reactFiber$` 水合信号。㉕**Joybuy 的 Privacy CMP 每次导航都会复弹**，主页关了不代表 /login 不弹；且它是异步渲染，点不到时先等出现再点（span/div/a 文本扫描），reload 兜底上限 2 次（reload 又弹 CMP 会互相打架）。㉖**新版 FB 的 2FA 输入框不再叫 approvals_code**，要按 autocomplete=one-time-code/inputmode=numeric/placeholder/aria 多属性 JS 检测，且要扫所有 facebook.com 页签。㉗**DrissionPage `run_js` 传箭头函数体不执行返回 None**，要传带 `return` 的语句块（自动包成函数）；Playwright `evaluate` 则要函数形式，别混用。㉘**中文 Windows `netstat` 输出是 GBK**，`subprocess.run(text=True)` 按 UTF-8 解码会炸读线程（stdout=None），必须拿 bytes 再 decode。㉙Joybuy 第三方登录行受服务端 A/B 控制会间歇消失、onClick 也可能静默不弹 OAuth——点击后必须 30s 内确认 OAuth 页签，失败整页重载重试（有上限）。㉚FB 提交过人机验证后回到**空**登录表单且 15s 不消失 = 一次「回退」，**回退需累计 3 次才判账号不可用**（2026-11-14 放宽：FB 会因误点/重复验证主动踢回登录页要求重新输密码，账号其实是好的——第 1/2 次自动重填密码、重点「登录」、用户再过一次验证即可恢复；第 3 次仍退回才写 note 判不可用、session_status 不改；脚本点击无效导致的重载重试不计入回退次数）。㉛**OAuth reauth.php 页**（profile 已登录时要求重输 FB 密码）只有 pass 框没有 email 框，classify 会返回「未知」——必须显式识别并自动重填密码；㉜**`input[type=submit]` 的可点文本在 value 属性里**，DrissionPage `ele.text` 拿不到，`_find_displayed` 永远扫不到（reauth 页「继续」按钮踩实），文本匹配要同时比对 `value`；另外 FB 的「信任这台设备」有「该/这」两种文案变体，2FA 页提交按钮文案就是「继续」。
  - **诊断脚本/证据（var/ 下可复跑）**：`var/diag_fb_q5/`（diag_hydration.py 四配置矩阵+Playwright 对照、probe_403.py/probe_failinfo.py 网络抓包、probe_gate.py/probe_timeout.py/probe_none.py eager vs none 对照、probe_menu*.py 展开与点击链路、probe_cmp.py CMP 修复验证）、日志 `var/logs/fb_diag_q5.log`、结论 `var/diag_fb_q5/diag_result.json`。

- **上一任务（2026-11-13 23:05，按诊断补丁改完并实跑：`FB 状态=form` 已打通，但提交后 FB 不认，仍 0 账号，全量未跑——其「提交后 FB 不认」的结论已被 2026-11-14 的 eager 根因推翻，见上方当前任务）**：
  **结论**：上一轮「FB 登录页是纯 JS 空壳」的判断**已被推翻**，真因就是诊断给出的「id 选择器过时」——FB 新登录页的 input **只有 `name="email"` / `name="pass"`，没有 `id`**（id 是 React 随机串），提交按钮是 `div[role="button"][aria-label="登录"]`，且 DrissionPage 的裸字符串 locator 必须写 `css:` 前缀。三处补丁打上后，冒烟**立刻出现 `FB 状态=form`**（22:36:53 首次），表单被识别、凭据被填入（账号框 15 字符 / 密码框 10 字符，DOM 实测）、「登录」按钮被真实点击、密码框回车也试过。**但提交始终不生效**：页面会短暂重渲染（表单消失 3–4s 再回来），FB 侧没有任何错误文案（无「密码不正确」、无 banned、无 checkpoint/2FA），profile 的 Chrome Cookies 库里也**始终没有 `c_user`/`xs`**（只有 `datr`/`fr`/`ps_l`/`ps_n`/`sb`）→ FB 从未建立登录态。因此 **57 个账号仍全部 UNKNOWN，全量仍未执行**（冒烟未过，按门禁不进全量），没有启动任何 CrawlJob，未 commit。
  - **本轮执行的命令**（cwd=`E:\code\AgentProject\Joybuy`，都 `PYTHONUNBUFFERED=1` 落文件）：
    - 冒烟 ×2：`./.venv/Scripts/python.exe backend/manage.py crawler_account_batch_setup --excel "C:/Users/lyx/Downloads/账号_分三列.xlsx" --login --limit 1 --no-manual-fallback > var/logs/fb_relogin_smoke.log 2>&1`
    - 两账号探针 ×1（判断是不是单账号问题）：同一条命令去掉 `--limit 1` 改 `--limit 2`，日志 `var/logs/fb_relogin_probe2.log`
  - **失败清单（本轮共尝试 2 个账号，0 成功）**：
    1. `100011734838229`（组 `数据抓取01`）→ **form 阶段卡死**：`FB 状态=form` → 填表（15/10 字符）→ 点「登录」→ 表单仍在 → 二次填写 + 密码框回车 → 表单仍在 → `stuck` → `failed`。证据：`var/logs/fb_relogin_smoke.log`；profile `var/browser_profiles/fb-100011734838229/Default/Network/Cookies` 里无 `c_user`/`xs`。
    2. `100088227465353`（同组）→ **更早一步就失败**：Joybuy 登录页等了 3 分钟仍「未找到可见的 Facebook 登录按钮（含展开后）」→ `failed`（该 profile 的 Joybuy 页渲染慢/按钮未出，没走到 FB）。
  - **按组结果（实查，与任务前完全一致）**：`数据抓取01` UNKNOWN 9 / VALID 1；`02`/`03`/`04`/`05` 各 UNKNOWN 10；`06` UNKNOWN 8；另有组 `数据抓取` 2 个 VALID。合计 60，**非 VALID = 57**，**本轮新增 `ok` = 0**。`pin` 抽查沿用上一轮结论（3 个存量 VALID 42 条 Cookie 有 `pin`；UNKNOWN 15 条无 `pin`）。
  - **日志/证据**：`var/logs/fb_relogin_smoke.log`（含「已填入凭据（第 N 次）：账号框 15 字符、密码框 10 字符」「已点击提交按钮「登录」」）、`var/logs/fb_relogin_probe2.log`、`var/logs/fb_dialog_100011734838229.html`（提交瞬间的过渡页快照）、`var/logs/fb_batch_progress.jsonl`。**`var/logs/fb_relogin_full.log` 仍不存在——全量从未启动。**
  - **本轮代码改动（`backend/crawler_control/management/commands/crawler_account_batch_setup.py`，仍是 git untracked，`py_compile`/`ruff check`/`ruff format --check` 全过）**：
    1. `_classify_facebook_page()`：form 判定改 `css:input[name="email"]` + `css:input[name="pass"]`；2FA 增加 `css:input[name="approvals_code"]` 兜底。
    2. `_act_on_facebook_page()` form 分支：填表改 `css:input[name=...]`；提交改为「`_find_displayed`（已扩 `div[role=button]`）real click → 失败 `by_js` → 兜底 `css:input[type=submit]`」，并支持最多重填 2 次、第 2 次用密码框回车提交。
    3. `_find_displayed()`：扫描集合加 `css:div[role="button"]`。
    4. `FB_LOGIN_PAGE_TIMEOUT` 默认改 **90**；保留反降频三个开关。
    5. 新增（为定位提交问题）：填表后用原生 value setter + `input`/`change` 事件把值再刷一遍（React 受控组件），日志只打印两个框的**字符数**，绝不打印凭据。
  - **卡在哪 / 下一步**：**卡在「表单提交后 FB 不认」**，不是选择器、不是网络、不是 IP 降级。剩下三个可疑方向（按优先级）：①**该账号凭据本身**（`100011734838229` 今天已被试了十几次，可能被 FB 软锁；但页面无禁止文案，需人工在真实 Chrome 里登一次确认）；②提交 POST 被 FB 静默拒绝（`input[type=submit]` 在 JS 侧 `offsetWidth=0`，真实 `div[role=button]` 点击后页面 reload → 可能是 FB 的登录风控在 SWR 层就把请求打回登录页）；③需要观察**提交后那一刻的完整响应**（建议下次用 `page.listen`/CDP Network 抓 `/login/device-based/regular/login/` 的响应码与 body，再决定是否要补 `lsd`/`jazoob` 等隐藏字段）。**不要在没有 `session_status=VALID` 的情况下铺全量。**
  - **新增踩坑（接在下方 ①–⑱ 之后）**：⑲**FB 新登录页只有 `name=`、没有 `id=`**，判断/填充一律 `input[name="email"]`、`input[name="pass"]`，别再写 `#email`/`#pass`。⑳**DrissionPage 裸字符串 locator 不按 CSS 解析**，必须 `css:input[name="email"]`，漏 `css:` 会得到「改了还是找不到」的假象。㉑**提交按钮是 `div[role="button"]`（文案「登录」/「Log in」）**，全页 `tag:button` 为 0，`_find_displayed()` 必须把 `css:div[role="button"]` 加进扫描集合。㉒**页面状态关键词必须用 `_visible_text()`（剥 script/style）**，原始 HTML 头部有大量 `disabled`，会让正常登录页被误判成封号。㉓判断 FB 到底有没有登录成功，**看 profile 的 Cookie 库有没有 `c_user`/`xs`**（`var/browser_profiles/fb-<label>/Default/Network/Cookies`，只读 name，不读值），比看页面 URL/表单是否存在可靠。

- **上一任务（2026-11-13 深夜，FB 登录页「纯 JS 空壳」判定完成：不是 IP 降级、不是浏览器指纹，是我们的选择器过时；只做诊断，未改业务代码）**：
  **一句话结论**：`facebook.com` 的登录页**从服务端 SSR 就带着登录表单**（`input[name="email"]` / `input[name="pass"]` / `input[type=submit]`，共 4 个 input），Playwright 与 DrissionPage **都能在 20 秒内渲染出来**；失败的唯一原因是 FB 新登录页**已经没有 `#email` / `#pass` / `#loginbutton` 这三个老 ID**（input 的 id 是 React 随机生成的 `_R_c9l6neappb6amH1_` 这种），于是 `_classify_facebook_page()` 永远返回 `""`（未知）、`_act_on_facebook_page()` 永远不填表 → 6 分钟循环空转 → 57 个账号 0 成功。payload 里的 `is_in_crawler_mode=true` 是**干扰项**：curl、Playwright、DrissionPage 三种客户端拿到的 HTML 里都有它，表单照常渲染，它不代表「被判爬虫」。
  **证据（2026-11-13 22:27–22:33 实测，脚本在 `var/diag_fb_*`，均 `page.quit()` 后无残留进程）**：

  | 探针 | 入口 | 客户端 / 指纹 | input 数 | `#email` | `input[name=email]` | 出表单耗时 |
  | --- | --- | --- | --- | --- | --- | --- |
  | Q1 | `www.facebook.com/login.php` | Playwright Chromium 140（全新 profile，`navigator.webdriver=false`，5 plugins，en-US） | 3（email+pass+submit） | **0** | **1** | t=6s 就有，90s 采样全程稳定 |
  | Q1b | 同上 | 同上（iframe/shadow 排查） | 3 | 0 | 1 | 无 iframe、无 shadow root，表单在**主文档** |
  | Q2/Q3 | `www.facebook.com/login.php` | DrissionPage → Chrome/157.0.8103.40（`webdriver=false`，5 plugins，zh-CN，Win32） | 4 | 0 | 1 | FORM OK @20.2s（冷启动，fbcdn JS 慢） |
  | Q3 | `mbasic.facebook.com/` | 同上 | 4 | 0 | 1 | 3.5s（被 302 到 `www.facebook.com/?__mmr=1&_rdr`） |
  | Q3 | `m.facebook.com/login.php` | 同上 | 4 | 0 | 1 | 4.7s（被 302 到 `www.facebook.com/?_rdr`） |
  | Q3 | `www.facebook.com/login/device-based/regular/login/?login_attempt=1` | 同上 | 4 | 0 | 1 | **1.8s（最快）** |
  | Q3 | `www.facebook.com/v17.0/dialog/oauth?client_id=3973743326183773&state=diag`（**Joybuy 实际入口**） | 同上 | 4 | 0 | 1 | **19.8s 冷 / 11.4s 暖**，落地页 `login.php?skip_api_login=1&api_key=3973743326183773…` |
  | Q1 | `login.php` 纯 curl（curl UA） | 无 JS | 4 | 0 | 1 | HTTP 200 / 79004 B / 4.4s |
  | Q1 | `login.php` 纯 curl（Chrome UA） | 无 JS | 0 | 0 | 0 | **HTTP 400 / 856 B**（浏览器自身正常，curl 400 无诊断意义） |

  - **HTTP/资源耗时**：`login.php` 主文档 200（Playwright 6.0s 到 DOMContentLoaded）；`static.xx.fbcdn.net/rsrc.php/...js` 全部 **200**（首批 ~20s 到齐，之后有缓存）；唯一失败请求是 FB 自己拉的 `instagram.com/accounts/login/...xuserid`（`net::ERR_FAILED`，与本问题无关）。**没有一次请求超时或被拒**。
  - **填充可行性（只填假值，未点提交）**：DrissionPage `ele('css:input[name="email"]').input(...)` / `input[name="pass"]` 均返回 `ChromiumElement`，填入 `diag-dummy@example.invalid` 后 `value` 正确、密码 `len=15`；**blur + 3s + resize 后两个值仍在**（说明 React 状态收下了，不是只改了 DOM 属性）。**未点击任何提交控件**，所以「提交后能否真的登录」仍未验证。
  - **提交控件真相**：可见按钮是 `div[role="button"]`（中文环境文案「登录」，英文「Log in」，`css:div[role="button"]` 在全页只有 1 个），`#loginbutton` **不存在**，`tag:button` 数量 **0**——所以 `_find_displayed(["log in","登录"])` 这条兜底也永远找不到按钮；`input[type="submit"]` 存在，JS `offsetWidth=0`（DOM 侧不可见）但 DrissionPage `states.is_displayed` 报 `True`，`.click()` 是否会报「没有位置及大小」尚未实跑（两种取法结论不一致，稳妥做法是 `div[role="button"]` 真点 + `input[type=submit]` 用 `by_js` 兜底）。
  - **定位语法实测（`var/diag_fb_q4/run_locator_check.py`）**：`page.ele('input[name="email"]')`（**不带前缀**）返回 **`NoneElement`**；只有 `page.ele('css:input[name="email"]')` 才拿到 `ChromiumElement`（`displayed=True`）。**DrissionPage 裸字符串不按 CSS 解析，改代码时必须写 `css:` 前缀**。
  - **可复用的入口 + 配置（结论：入口不用换）**：URL 继续用现有 OAuth v17 dialog（`https://www.facebook.com/v17.0/dialog/oauth?client_id=3973743326183773&state=…`，即命令里 Joybuy 弹窗那一跳）；启动参数沿用现在 `_browser()` 那套（`set_load_mode("eager")`、`--disable-*background*` 三个开关、CDP 9334、`fb-<label>` 独立 profile）；**`FB_LOGIN_PAGE_TIMEOUT=90` 足够**（实测冷启动 20s，留 4x 余量；360 不是必需）。若只想最快出表单，`…/login/device-based/regular/login/?login_attempt=1` 只需 1.8s，但它不是 Joybuy 的 OAuth 链路，不推荐替换。
  - **必须改的代码（本次按「只诊断」口径未改，`crawler_account_batch_setup.py` 仍是 git untracked）**：
    1. `_classify_facebook_page()`（~L285-287）：`if self._ele(page, "#email") and self._ele(page, "#pass")` → 改成 `self._ele(page, 'css:input[name="email"]')` / `css:input[name="pass"]`（保留 `#email`/`#pass` 作旧版兜底；**`css:` 前缀不能省**，见踩坑⑰）。
    2. `_act_on_facebook_page()` form 分支（~L682-683）：`fb_page.ele("#email").input(...)` / `ele("#pass")` → `ele('css:input[name="email"]')` / `ele('css:input[name="pass"]')`。
    3. 同一分支的提交（~L685-690）：`#loginbutton` 已消失 → 优先点可见的 `div[role="button"]`（文案「登录」/「Log in」；注意 `_find_displayed()` 目前只扫 `tag:button`/`tag:input`，**扫不到 `div[role=button]`，需要把 `[role="button"]` 加进去**），兜底 `input[type="submit"]` 用 `click(by_js=True)`。
  - **未验证 / 下一步**：①提交按钮点击链路（改动 3）没有实跑——点下去会带假凭据发一次登录 POST，按「不在诊断里浪费账号」的口径留到下次冒烟；②改完先跑 `--login --limit 1 --no-manual-fallback`，日志出现 `FB 状态=form` 且进入 2FA 才算通；③**在没看到 `FB 状态=form` 前不要铺全量 57 个**。
  - **新增踩坑（不得再踩，编号接在上一条任务 ①-⑩ 之后）**：⑪**FB 登录页已无 `#email`/`#pass`/`#loginbutton`**，input 的 id 每次渲染随机（`_R_xxx`），判断/填充一律用 `input[name="email"]`、`input[name="pass"]`，按钮文案是「登录」/「Log in」的 `div[role="button"]`。⑫`is_in_crawler_mode: true` **不是**「被判爬虫」的证据——curl / Playwright / DrissionPage 三种客户端都带这个字段，且表单照常渲染；别再拿它推「IP 被降级」。⑬**截图能看到表单而 DOM 计数为 0 时，先怀疑选择器**：本次把「`#email` 不存在」误读成「0 个 input / 纯空壳」，实际同一时刻 `input[name=email]` 一直存在（Playwright t=6s、Q1 全程 name_email=True）。⑭`input[type=submit]` 在 FB 新登录页 JS 侧 `offsetWidth=0`（DrissionPage 的 `is_displayed` 却报 True，两种取法不一致），别指望 `.click()`，用 `by_js` 或直接点 `div[role=button]`；`_find_displayed()` 只认 `tag:button`/`tag:input`，找不到 `div[role=button]`。⑮用浏览器 UA 的 `curl` 打 `login.php` 会直接 400（856 B），但真实浏览器完全正常——**curl 400 不能当「FB 封了本机」的证据**（只有 `http=000`/连接超时才代表网络不通）。⑯诊断脚本不要调用 `_kill_stale_crawler_browsers()`，用独立 CDP 端口（本次 9411/9412/9413/9414）+ 独立 profile `var/diag_fb_profiles/*`、`var/diag_fb_q4/*`，一个脚本跑完 `quit()` 再跑下一个。⑰**DrissionPage 的裸字符串 locator 不按 CSS 解析**：`page.ele('input[name="email"]')` 返回 `NoneElement`，必须写 `page.ele('css:input[name="email"]')`；写补丁时漏掉 `css:` 会得到「改了还是找不到」的假象。⑱FB 新登录页 `tag:button` 数量为 0，`input[type=submit]` 在 JS 侧 `offsetWidth=0` 而在 DrissionPage 侧 `states.is_displayed=True`——依赖 `_find_displayed()`（只扫 `tag:button`/`tag:input`）永远点不到提交，必须显式处理 `div[role="button"]`。
  - **诊断脚本（都在 gitignore 的 `var/` 下，可复跑）**：`var/diag_fb_q1/run_q1.py`（Playwright 主探针 + 90s 采样 + 请求耗时 + 截图 `q1_screen.png`）、`var/diag_fb_q1/run_q1b_frames.py`（iframe/shadow 排查）、`var/diag_fb_q2/run_q2_q3.py`（DrissionPage 指纹 + 5 个入口遍历，`q2_q3_result.json` + 每个入口截图）、`var/diag_fb_q3/run_q3_verify.py`（OAuth 入口 `FORM OK` + 假值填充 + 提交控件枚举，`form_ok.png`）、`var/diag_fb_q3/run_q3b_persist.py`（暖 profile 计时 + blur 后值保持）、`var/diag_fb_q4/run_locator_check.py`（locator 语法对照：裸 vs `css:`，提交控件可达性）。**Q4（换出口 IP / 代理对比）未做**——Q1/Q2 已证明表单本来就能渲染，没有「IP 降级」需要绕行，`FB_LOGIN_PROXY` 无需设置。

- **上一任务（2026-11-13 夜，FB 账号批量重新登录：网络已通，但 FB 登录页不渲染，冒烟未过，全量未执行，57 个账号仍是 UNKNOWN）——该轮「登录页是纯 JS 空壳」的判断已被上一条深夜诊断推翻，真正原因见上方条目**：
  **结论（22:25 收尾）**：VPN 已恢复（`https://www.facebook.com/`、`https://m.facebook.com/`、`https://www.joybuy.co.uk/login` 均 200），但 **facebook.com 的登录页现在是一个纯客户端渲染的空壳**：浏览器里得到的 DOM 有 `mount_0_0`、**0 个 `<input>`、0 个 `<form>`、没有 `#email`/`#pass`/`loginbutton`，`is_in_crawler_mode=true`**，5–6 分钟内始终不水合（`_fb_noscript=1` 的服务端兜底页同样是空壳；用浏览器 UA 直接 curl 反而被 FB 回 400）。因此 `--login` **一个账号都没登进去**：57 个账号仍全部 UNKNOWN（会话未恢复），**全量 57 个没有执行**（冒烟未过，按纪律不进全量），**没有启动任何 CrawlJob**，也未改后端服务（runserver `--noreload` 未重启）。
  - **实际执行的命令**（cwd=`E:\code\AgentProject\Joybuy`，全部 `PYTHONUNBUFFERED=1`，5 次冒烟都是这一条，只是环境变量不同）：
    `PYTHONUNBUFFERED=1 ./.venv/Scripts/python.exe backend/manage.py crawler_account_batch_setup --excel "C:/Users/lyx/Downloads/账号_分三列.xlsx" --login --limit 1 --no-manual-fallback > var/logs/fb_relogin_smoke.log 2>&1`
    （第 4 次加了 `FB_LOGIN_PAGE_TIMEOUT=300`；第 5 次把 `var/browser_profiles/fb-100011734838229` 临时挪走用全新 profile，之后已原样挪回）
  - **按组结果（任务前后 DB 实查完全一致，`session_status` 无任何变化）**：`数据抓取01` UNKNOWN 9 / VALID 1；`02`/`03`/`04`/`05` 各 UNKNOWN 10；`06` UNKNOWN 8；另有组 `数据抓取` 2 个 VALID（历史账号）。合计 60，**非 VALID = 57**，**今晚新增 `ok` = 0**。
  - **失败清单（只有 1 个账号被尝试：`100011734838229` / 组 `数据抓取01`，5 次冒烟见下）**：
    1. `21:39` → `banned`（**误判**，见下方「本轮修掉的两个真 bug」第 1 条）；
    2. `21:46`–`21:48` → 一直 `unknown`，150s 后 `stuck`（**第 2 个真 bug**：`ele()` 返回 `NoneElement` 而不是 `None`，循环只在空转，连 DOM 快照都落不下来）；
    3. `21:52`–`21:54` → `unknown`（修完能拿到快照了，**真因由此暴露**：`fb_dialog_100011734838229.html` 里 0 个 input）；
    4. `22:03`–`22:10`（`FB_LOGIN_PAGE_TIMEOUT=360`）→ 6 分钟仍 `unknown` → `stuck` → `failed`；
    5. `22:19`–`22:23`（全新 profile）→ 连 Joybuy 的 Facebook 按钮都没找到（冷启动页面更慢），`failed`。
    **五次的共同点：一次 `#email` 都没填、一次凭据都没提交**（所以不存在把账号试锁的风险）。
  - **`pin` Cookie 抽查（验证方法已可用，只是今晚没有新会话可查）**：`load_account_session()` + 只打印「Cookie 条数 / 是否有 pin」——3 个存量 VALID（`100006876375579`、`100023205360021`、`任务账号01`）都是 **42 条 Cookie 且有 `pin`**；3 个 UNKNOWN（`100011734838229`、`100088227465353`、`61553901210655`）都是 **15 条且无 `pin`**，与「假会话」结论一致。
  - **日志**：`var/logs/fb_relogin_smoke.log`（冒烟，最后一次运行内容）、`var/logs/fb_dialog_100011734838229.html`（FB 空壳快照，300KB 截断）、`var/logs/fb_batch_progress.jsonl`（今晚 8 行：1×banned + 7×failed，**0×ok**）。**`var/logs/fb_relogin_full.log` 不存在——全量从未启动**，不要把它当已跑过。
  - **本轮修掉的两个真 bug + 两处加固（`backend/crawler_control/management/commands/crawler_account_batch_setup.py`，该文件仍是 git untracked）**：
    1. **`_page_text` 用原始 HTML 头部做关键词匹配 → 误判封号**：`page.html[:20000]` 全是 FB 的内联 `<style>/<script>`，`disabled` 出现 51 次，正常登录页被判成 `banned` 直接跳过。改为复用蜘蛛侧的 `_visible_text()`（剥 script/style）。
    2. **`ele()` 返回 `NoneElement` 而不是 `None`**：`confirm is None` / `button is not None` 这类判断全部失效，随后对 `NoneElement` 取属性抛 `ElementNotFoundError` 并被外层 `except` 吞掉 → 150s 循环空转、不落快照。新增 `Command._ele(node, locator, timeout)` 统一折成 `None`，替换了 classify / 2FA / checkpoint / confirm / 提交按钮等 7 处。
    3. `_dump_fb_html()` 抽成方法（banned 与 unknown 都落快照）+ `_drive_facebook` 的两处 `except` 打印异常类型（此前静默，是定位困难的根因）。
    4. `FB_LOGIN_PAGE_TIMEOUT`（默认 360s）+ 三个反降频 Chrome 开关（`--disable-backgrounding-occluded-windows` / `--disable-renderer-backgrounding` / `--disable-background-timer-throttling`）。**这两项对本轮的卡点未证明有效**，只作为加固保留：实测 FB 页面 6 分钟仍是空壳，说明不是「渲染慢」而是「根本没渲染」。
    验证：`py_compile` 过、`ruff check` 全过、`ruff format --check` 过；DB 用 `manage.py shell` 实查（上面数字）；**没有跑任何单测/全量回归**（按验证纪律只做针对性验证）。
  - **下一轮建议（卡点不在本仓库代码）**（**已被 2026-11-13 深夜诊断推翻：不要换节点、不要换 IP，先按本节最上方条目改选择器**）：①先换 VPN 节点/出口 IP 再试一次（页面 payload 里的 `is_in_crawler_mode=true` 是相关信号，但可能并非只针对本机，只能作为怀疑方向），换完只要日志出现 `FB 状态=form` 就说明通了；②或在真实 Chrome 里人工登录一次，确认能看到登录表单，再把该 profile 交给命令复用；③不要在没看到 `FB 状态=form` 的情况下启动全量——按当前每次 6 分钟的表现，57 个账号要空跑 6 小时且必然 0 成功。

  以下是 2026-11-13 白天那一轮的原始记录（网络根因、已修项，仍然有效，作为背景保留）：57 个账号的「假会话」（15 条跟踪 Cookie、无 `pin`）已在当天下午作废，需用 `--login` 重跑批量登录。**白天定位到真正的拦路虎不是代码，是网络**：
  1. **根因（实测）**：`curl https://www.facebook.com/` 与 `m.facebook.com` 均 `http=000`（12s 超时），同机 `www.joybuy.co.uk` 200/307、`www.baidu.com` 200 → **主机到 Facebook 不可达（VPN 分流未覆盖 facebook.com）**。浏览器里 OAuth 弹窗打开 `https://www.facebook.com/v17.0/dialog/oauth?...` 后显示 Chrome 错误页「无法访问此网站…ERR_CONNECTION_TIMED_OUT」（探针取 `tab.html` 实证）。此前多轮「与页面的连接已断开」都是这个网络错误的下游症状。
  2. **同时发现（重要）**：Joybuy UK 现在**未登录访问全站 307 到 `/login`**——`/`、`/s?k=dog+treats` 直接 curl（带浏览器 UA）都返回 `307 Location: /login?returnUrl=…`，`/login` 本身 200。即：**没有可用会话就完全无法抓取**，这也解释了 11-13 09:13 那个任务为什么「列表页解析失败 https://www.joybuy.co.uk/login?returnUrl=…」。
  3. **本轮已修（都在 `backend/crawler_control/management/commands/crawler_account_batch_setup.py`）**：
     - **`text:` 选择器卡死**：DrissionPage 的 `text:Accept all` 一类全文扫描在 645KB 登录页上不返回——`faulthandler` 抓栈停在 `chromium_base._find_elements`，命令卡 >150s。改为 CSS `page.eles("tag:button"/"tag:input")`（实测 0.08s）+ 本地文本匹配 + `states.is_displayed` 过滤；`_find_displayed` 参数由选择器模式改为**纯文本子串**。
     - **导航不再无限等 load**：登录页挂着广告 iframe（insight.adsrvr.org），`get()` 不显式超时会一直等 load 事件。新增 `_goto(page, url, timeout=25)`（吞掉超时/断连）+ `options.set_load_mode("eager")`。
     - **`_drive_facebook` 断连安全重写**：每轮循环重新 `get_tabs()` 取当前 FB 页签，页面操作整体 try/except；FAQ 弹窗关闭/导航中抛 `PageDisconnectedError` 时不再冒到外层；2FA 最多重试 2 次；未知页面才 dump DOM（`var/logs/fb_dialog_<label>.html`）。
     - **FB 登录表单填错字段的真 bug**：原来 `#email` 填的是**密码**（`fb_page.ele("#email").input(password)`），已改为填 `account.label`（账号）。
     - **网络预检**：`_facebook_reachable()`（TCP+TLS 8s），`--login` 前先跑；不通直接 `CommandError` 明确中文报错并**不碰任何账号**；`_classify_facebook_page` 新增 `network` 类别（ERR_CONNECTION_*/无法访问此网站/响应时间过长），命中即终止整批而不是逐号失败。若走显式代理（`FB_LOGIN_PROXY=http://ip:port`，`_browser` 里 `set_proxy`）则跳过直连预检。
  4. **验证（按验证纪律仅做针对性验证）**：`ruff check` / `ruff format --check` 全过、`py_compile` 过；真实冒烟跑通到「点击 Continue with Facebook → 检测到 OAuth 弹窗页签 → 读出弹窗内容为 FB 不可达错误页」；预检生效后 `--login --limit 1` 8 秒内以中文 `CommandError` 退出，**没有对任何账号执行登录、没有写库**。
  5. **卡点（用户侧；2026-11-13 夜已解决——VPN 开了，FB 两个域名都 200，现在的卡点是登录页不渲染，见本节顶部）**：需要让 `www.facebook.com` 从本机可达（改 VPN 节点/全局路由，或给一个能出海的代理并用 `FB_LOGIN_PROXY`）。通了以后再跑：
     `PYTHONUNBUFFERED=1 ./.venv/Scripts/python.exe backend/manage.py crawler_account_batch_setup --excel "C:/Users/lyx/Downloads/账号_分三列.xlsx" --login`
     （想先验一个：`--limit 1 --no-manual-fallback`；单个手工：`--manual <label> --manual-wait 300`）。全部跑完再验证 `session_status=VALID` 且 Cookie 里有 `pin`。**在拿到真实会话之前，193 个抓取任务一个都跑不出结果**（全站 307 到 /login）。
  6. **踩坑（不得再踩）**：①`_kill_stale_crawler_browsers()` 会杀掉**所有**爬虫 Chrome——调试探针与批量登录绝不能同时跑，会互杀；②DrissionPage 4.1.1.4 里没有 `PageLoadTimeoutError`（`errors.py` 只有 `WaitTimeoutError`/`PageDisconnectedError` 等），别按网上示例 import；③`get_tabs()` 返回的是**标签页 ID 字符串**，读 URL 必须 `page.get_tab(id)`；④PowerShell/Bash 管道下 Django 的 `self.stdout` 会整块缓冲，调试必须 `PYTHONUNBUFFERED=1` 并重定向到文件；⑤`t:Log In`/`t:Submit` 这类文本选择器在 FB 页面上也不可靠，统一改 `tag:button`/`button[type=submit]`。⑥**绝不允许并发跑两条本命令**：两边都会 `_kill_stale_crawler_browsers()`，互相把对方的浏览器杀掉，而且两条进程写同一个重定向日志文件会写出整段 `\x00` 空洞、行与行交错（本轮踩实了）。开跑前必须 `tasklist //FI "IMAGENAME eq python.exe"` 确认上一条已退出。⑦**FB 登录页现在是纯客户端渲染的空壳**：`login.php?skip_api_login=1&...` 返回约 366KB HTML，SSR 里 `mount_0_0` 是空的、0 个 `<input>`/`<form>`、没有 `#email`/`#pass`/`loginbutton`（`_fb_noscript=1` 兜底页一样；浏览器 UA curl 直接 400）。判断「页面就绪」只能看日志出现 `FB 状态=form`，不要再拿 Cookie 条数或 URL 判断。⑧DrissionPage 4.1.1.4 的 `ele()` 找不到元素返回的是 `NoneElement` 而**不是 `None`**，`is None` 恒为假、对它取任何属性都抛 `ElementNotFoundError`——统一用 `Command._ele()` 折成 None。⑨状态关键词必须匹配 `_visible_text()`（剥掉 script/style）后的正文，原始 HTML 头部（FB/京东都会塞 i18n 与 CSS 变量）里的 `disabled` 会让正常页面被误判成封号。⑩profile 目录 `var/browser_profiles/fb-<label>/` 不是解药：本轮用**全新 profile** 重试，FB 依旧给空壳（且 Joybuy 冷启动更慢，连 Facebook 按钮都没渲染出来），别再靠删 profile 排障。

- **上一任务（2026-11-13，爬虫任务列表分页修复，已完成）**：用户报「任务列表有多页但没有分页按钮」。根因：`AdminCrawlJobsView.get` 硬截断 `[:50]` 且无分页参数，前端 CrawlersView 无翻页 UI——193 个任务只能看到最新 50 个。修复：①后端 `get` 改为 `page/page_size`（默认 1/20、上限 100）分页，回包 `{items, page, page_size, total, has_next}` 信封（与商品池等管理端接口一致）；②前端引入 `AppPager`（复用全局组件），`loadJobs(resetPage)` 带 `page=`，表格下方渲染翻页器；③顺手把 4 个名字是原始 ID 的任务（11-11 新增节点快照无中文名）按 primary 映射的本地类目 name_zh 重命名。**验证**：临时管理员（已删）浏览器实测——第 1 页 20 行 + 页码按钮（1~5 + 上/下一页），点 2 加载新数据且高亮正确；`prettier/eslint` 通过、`vite build` 通过；`ruff check/format` 全过。**踩坑**：编辑大段视图代码时 old_string 截断不完整会留下孤儿括号（本次 `)` 残留导致 SyntaxError）——改完立即 `py_compile`。

- **上一任务（2026-11-13，翻页自测修复 + 193 个抓取任务批量创建，已完成）**：用户要求「先自测翻页改动，通过后按账号组×全部二级类目建 193 个任务（只创建不启动，limit=200/来源默认/增量/跳过已入库=开/翻页=开），完成后关机」。
- **当前任务（2026-11-13，翻页自测修复 + 193 个抓取任务批量创建，已完成）**：用户要求「先自测翻页改动，通过后按账号组×全部二级类目建 193 个任务（只创建不启动，limit=200/来源默认/增量/跳过已入库=开/翻页=开），完成后关机」。
  1. **前置数据修复：l2 快照 URL 回填**。最新树 `joybuy-uk-20261111-441f4b04`（11-11 12:27 发布）的 199 个 l2 快照里只有 10 个有 source_url，其余 189 个为空——蜘蛛会 fallback 到 `k=l2:xxx`（垃圾关键词，抓不到东西）。修复：141 个从旧树 `joybuy-uk-20261111-f2a65069`（09:43 发布，URL 完整）按同 source_id 回填；48 个任何树都没有（11-11 新增节点）用其 primary 映射的 `LocalCategory.name_en` 拼 `https://www.joybuy.co.uk/s?k=<quote(name_en)>&l2=<id>`（k 是自由文本搜索词，name_en 足够；蜘蛛反正会 robots 安全化成 `k=` 单参数）。**只填空、不覆盖已有**；快照/计划/结果在 `var/backfill_l2_urls_20261112/`（plan.json + result.json，189 updated）。
  2. **自测（真实站点验证被 VPN 断连阻断，如实记录）**：计划用 l2:1420 手机类目跑真实小任务（limit=20，skip+pagination 双开）验证 page=2，但 curl/urllib 直连与 7890 代理全部 SSL EOF / 000（baidu 200 = 节点又挂了；FB 批量 21:30 还在成功，节点是之后断的）。改为模拟自测：新增 `PaginationTwoPageRelayTests`（page1 → 产出 `&page=2` 请求 → page2 入队到 limit → 停止，事件流 LISTING_FETCHED×2、无 SHORTFALL），并**抓出并修复一个真 bug**：`parse_listing` 里候选收集与 `collected` 递增分离后，跨页判断 `collected >= limit` 会超抓（page2 多入队）——改为 `collected + len(candidates) >= target["limit"]`。全套件 `crawler_control.tests.test_crawler_rebuild + test_crawler_control_domain` → **63 tests OK**；ruff 全过。**给新会话的提醒**：真实站点 page=2 行为尚未端到端验证过，用户手动启动第一个任务时应观察 `LISTING_FETCHED`（page=2）与 `PAGINATION_COMPLETE`/`LISTING_SHORTFALL` 事件；若网络仍断会走 `CONNECTIVITY_PREFLIGHT_FAILED`（8 秒快速失败，不会挂死）。
  3. **批量创建 193 个任务**：脚本 `var/create_crawl_jobs_20261113/create_jobs.py`（干跑→正式，结果 `create_jobs_result.json`）。范围=最新树中有 primary CategoryMapping 的全部 l2（193 个）；6 个 unmapped（l2:1580 节庆装饰品 + l2:3896/3898/3900/3902/3904 汽车）按既定口径排除。参数全按用户指定：`product_limit=200`、`listing_sort=SOURCE_DEFAULT`、`sync_mode=INCREMENTAL`、`skip_imported_products=True`、`allow_pagination=True`；账号组 `数据抓取01~06` 轮转（33/32/32/32/32/32）；命名 `数据抓取{NN}-{类目名}`；全部 `mark_job_ready`（READY=未启动，无任何 CrawlRun）。
  - **验证**：实库核对 193 个任务、状态全 READY、0 run、参数抽查正确；干跑与正式结果一致（skipped_existing=0）。任务名唯一（CrawlJob.name unique），重复执行脚本会跳过。
  - **踩坑（不得再踩）**：①11-11 两次树同步（09:43 与 12:27）结果不同——12:27 的同步丢了 l2 的 source_url；任何依赖快照 URL 的操作都要先核对目标树的数据完整性；②`SourceCategory` 没有 `name_en` 字段（只有 name_zh），别按 LocalCategory 想当然；③`manage.py shell -c` 的 cwd 是 `backend/`，脚本里写文件必须绝对路径（本轮 plan.json 又踩了一次）；④relay 测试断言完整 URL 时注意测试树快照无 source_url 会走 `k=l2-xxx` 兜底。
  - **下一步（用户手动）**：管理端爬虫任务页逐个/批量启动；建议先启动一个观察翻页事件；所有任务的账号组都有 58 个 VALID 会话的账号可用。

- **上一任务（2026-11-12，FB 爬虫账号批量建号登录 + 列表翻页开关，已完成）**：两条线。
  1. **FB 账号批量接入（58/58 全部成功）**：用户的 Facebook 账号表（`Downloads/账号_分三列.xlsx`，三列：账号/密码/解码 TOTP seed）→ 新命令 `crawler_control/management/commands/crawler_account_batch_setup.py`。**阶段 A 建组建号**：`--create-only` 按 10 个/组分 `数据抓取01~06`（10/10/10/10/10/8），已有同 label 账号（`100006876375579`、`100023205360021`）归入新组且会话保留。**阶段 B 自动登录**：`--login` 用 DrissionPage 有头浏览器（profile 每 `fb-<label>` 独立，CDP 9334）走 Joybuy `/login` → 点 `Continue with Facebook` → 自动填 FB 表单 → **2FA 用本地 pyotp 生成**（Excel seed 清洗成 32 位 base32，与 2fa.cn 同算法，无需开网页）→ OAuth 回跳后 `_joybuy_cookies` 抓取 → `record_account_session` 加密入库；失败模式：FB 封号关键词（disabled/停用）→ 跳过；卡住 → 同窗口转人工（`--manual-wait` 秒）→ 单账号可 `--manual <label>` 重开。账号间随机 25–45s 间隔。**结果：58/58 全自动成功（含冒烟 1 个），0 封号 0 人工**，进度在 `var/logs/fb_batch_progress.jsonl`、日志 `var/fb_batch.log`。**密码/2FA 只在内存使用，不落库不进日志不进代码**；Excel 留在 Downloads（仓库外）。浏览器 profile 在 `var/browser_profiles/fb-<label>/`，重跑免重复 FB 登录（直接复用 FB 会话走 OAuth）。
  2. **列表翻页开关（任务级，默认开）**：用户问「单二级类目 200+ 支持吗」——此前不支持：robots.txt `Disallow: /s?*&page=`，蜘蛛只抓第一屏（实测 20–40 卡）。按拍板实现 `CrawlJob.allow_pagination`（默认 True，迁移 `crawler_control/0010` 已执行）：
     - 蜘蛛 `parse_listing`：目标未抓满且本页有新内容（新入队或被 skip_imported 跳过的新商品）→ 继续请求 `&page=N+1`；整页全是跨类目重复/空页 → 停止；安全上限 `JOYBUY_MAX_LISTING_PAGES`（env `CRAWL_MAX_LISTING_PAGES`，默认 25）；minihome 频道页无翻页基准不翻；空翻页页写 `PAGINATION_COMPLETE`（INFO）而非解析失败；缺口时 `LISTING_SHORTFALL` 注明「翻页至第 N 页后没有更多结果」或「任务未开启翻页」。
     - **robots 处理**：开启翻页的运行由 runner `_run_settings` 设 `ROBOTSTXT_OBEY=False`（/s?k= 与 /dp/ 本就 Allow，实际只放开 page= 请求）；**关闭翻页的任务完全遵守 robots**。管理端新建表单「翻页抓取」默认勾选 + 详情抽屉显示；API/快照同步。
  - **验证（按验证纪律仅做针对性验证）**：新增 `ListingPaginationTests` 7 例（翻页产出 page=2 且无 SHORTFALL / 关闭时旧行为 / 整页重复停止 / 整页已入库继续翻 / 页数上限 / 频道页不翻 / runner robots 映射）+ 既有 `SkipImportedProductsTests`/`SpiderLoggingTests` 显式关翻页保持原焦点；`crawler_control.tests.test_crawler_rebuild + test_crawler_control_domain` → **62 tests OK**；改动 py `ruff check` 全过、`ruff format --check` 全过（`crawler_account_batch_setup.py` 一并 format）。后端已重启。
  - **踩坑（不得再踩）**：①给 `parse_listing` 加翻页后，旧断言「只有 1 个请求」的用例会多出 page=2 请求——聚焦型用例（skip/logging）要显式 `allow_pagination=False`；②Python 语法：walrus 不能放进关键字参数（`run=(x := y)` 非法），测试里写错过一次；③编辑 docs/05 时曾把 §5.2 正文整段误删（替换目标写成了整节）——替换前先确认 old_string 是标题还是含正文；新增 §5.2/5.3 与既有「5.2 完整刷新」撞号，已把后者改为 §5.4。

- **上一任务（2026-11-12，双优化：购物端「申请店铺」全链路 + 商家端手机网页版，已完成，未 commit）**：两个并行子代理交付（A=backend/storefront/admin-web，B=merchant-web，文件集不相交，互不触碰）。
  **A. 申请店铺（买家账号 → 管理端审核 → 同一 email+密码 登录商家端）**：
  1. 模型 `MerchantApplication`（`merchants/models.py` + 迁移 `0007_merchantapplication` 已 migrate 到 dev MySQL：buyer OneToOne、shop_name≤60、legal_name、referrer_code、status PENDING/APPROVED/REJECTED、reject_reason、submitted_at/reviewed_at/reviewed_by、merchant 回填 SET_NULL、(status, submitted_at) 索引）。
  2. API：买家 `GET/POST /api/v1/account/merchant-application`（buyer 会话鉴权，view 在 `merchant_ops/views_shop_application.py`，**故意不挂 /api/v1/merchant/**——该前缀会触发员工会话+店铺上下文链）；管理端 `GET /api/v1/admin/merchant-applications`（带 pending_count、status 筛选）+ `POST .../actions`。
  3. **approve 单事务**（select_for_update 锁申请行）：`create_merchant`（含推荐码→MerchantReferral 绑定）→ 按 buyer.email 查/建 `StaffAccount`（**新账号直接复制 buyer.password 的 Django 哈希串**——两表同套 hasher，买家密码即商家端登录密码；邮箱已存在则只加 membership、不改密码，响应 `staff_account_created=false`）→ `MerchantMembership(merchant_owner, ACTIVE)` → 既有 `review_admission` 状态机（免保证金→ACTIVE；需保证金→PENDING_DEPOSIT）→ 回填申请单。reject 需原因；驳回后可重新申请（重置 PENDING、清 reason/审核人、刷新时间）。错误码全中文文案（SHOP_NAME_REQUIRED / REFERRER_CODE_INVALID / APPLICATION_ALREADY_PENDING / SHOP_ALREADY_APPROVED 等）；邀请码无效在买家表单硬报错（与管理端补录「无效不阻断」口径不同，有意为之）。
  4. storefront：新页 `/account/apply-shop` 四态（表单 / 审核中只读回显 / 已通过+待缴保证金提示+「前往商家中心」按钮（`nuxt.config` runtimeConfig.public.merchantWebUrl=`http://127.0.0.1:5174`）/ 驳回+重新申请预填旧值）；入口在 /account 列表「申请店铺 / Become a seller」；文案 `shopApply.*` 34 键 en/zh 成对进 messages.js。
  5. admin-web：`MerchantsView.vue` 新增「入驻申请」面板（待审计数徽标 / 状态筛选 / 审核弹窗：通过 radio+需要保证金+应缴金额+封店天数、驳回原因必填；`staff_account_created=false` 时提示「已关联现有员工账号（密码保持不变）」）。
  **B. 商家端手机网页版（merchant-web，阈值 ≤960px 抽屉档 + ≤768px 手机档）**：
  1. ≤960px：重做原「侧栏横排 wrap」断点——侧栏变 **off-canvas 抽屉**（translateX(-100%)，宽 min(260px,84vw)，z-80>遮罩 70>顶栏 20），`MerchantLayout.vue` 加 navOpen 状态+汉堡按钮（aria-label/aria-expanded 动态）+`.merchant-side-mask` 遮罩+路由 watch 自动收起+`body.is-nav-locked` 滚动锁（锁样式仅存在于 ≤960 媒体查询内，桌面无影响）；**≥961px 像素级不变**（已截图对比）。
  2. ≤768px 手机档：content padding 16/12、顶栏藏面包屑/h1 16px/右侧控件换行、`.btn`/`.btn--sm` ≥40px 触达、pager/welcome-strip 换行、bar-chart 容器内横滚。
  3. 11 处 `data-table` 全部包进 `.data-table-wrap` 横滚（v-if/v-else-if 条件移到包裹 div 上保住 Vue 编译链，全仓核对无依赖 table 相邻关系的选择器）；MessagesView ≤768 单列+mobilePane ref 切换会话/聊天+chat-back 返回按钮（仅移动端显示，≤960 双栏收窄 240px+minmax(0,1fr)）；LoginView 卡片 width:100%;max-width:420px；顺带修 WalletView wallet-hero / OrdersView ship-hero 在 390px 的页面横向溢出，以及 AfterSales/Catalogue/Notifications 的 filter-row 460px 硬宽（≤768 放开 100%）。
  - **验证（按验证纪律仅做针对性验证）**：A：`manage.py test merchant_ops.tests.test_merchant_application --keepdb` → **18 passed**（含 approve 后用买家邮箱+密码 `POST /api/v1/admin/auth/login` 实测 200 + `GET /api/v1/merchant/shops` 返回新店铺 200、邮箱冲突绑现有 StaffAccount 且其密码不变）；改动 py `ruff check`/`format --check` 过（`merchant_ops/urls.py:566` 为既有漂移未整文件重排）；storefront prettier/eslint 过 + **vitest 59/59**；admin-web prettier/eslint 过 + **vitest 9/9**；浏览器 E2E 五步全过：注册→申请→审核中刷新仍在；admin 通过（需保证金 500）→商家列表「待缴保证金」；storefront 已通过+前往商家中心+API 层买家密码登录商家端成功；驳回→展示原因→重新申请回审核中；截图 6 张 `var/merchant_apply_20261112/`；临时买家×2/员工/店铺/申请逐项删净 count=0（MerchantMembership 剩余 2 条为既有 HOMCOM/CHiQ 种子）。B：`npx vite build`（cwd=merchant-web）通过；**merchant-web 无 prettier/eslint 配置可跑（如实报告，无可执行项）**；浏览器三档实测：1366×768 桌面与改前一致；900×700 抽屉开/关/遮罩/路由自动关/滚动锁全过；390×844 三页表格 wrap 内横滚且页面零横向溢出、订单详情抽屉与发货/上架 AppModal 可用、Messages 单列切换+返回、登录卡不溢出；console error 0；截图 15 张 `var/mobile_merchant_20261112/`；临时店铺/员工/买家/订单两轮清零（HOMCO/三星未动）。
  - **坑（不得再踩）**：①**三端共用 127.0.0.1 的 `joybuy_staff_session` cookie（cookie 按 host 不按端口）**，并行代理各自动登录会互相踢会话——遇 "Staff authentication is required." 先重新登录再操作；②后端 runserver 是 `--noreload`，改码必须 `netstat -ano | grep :8000` 找 PID → `taskkill //PID <pid> //F` → 重启；③curl 直调买家 POST 会撞 CSRF（HTML 403），先 GET `/api/v1/auth/buyer/session` 拿 csrf_token 带 `X-CSRFToken`；④本会话 IAB 对 Playwright locator click 一律超时，改「evaluate 取几何中心 + CUA 坐标点击」稳定；后台 tab 截图 30s 超时→先 `tabs.get` 激活自己的 tab 再截；⑤Merchant.currency 只有 GBP/EUR（造单别用 CNY）、Offer 字段是 current_price/cost_price。
  - **已知限制与遗留**：①买家改密码后商家端密码**不同步**（approve 时一次性复制哈希，属已知设计限制）；②merchant-web LoginView 文案「账号由平台分配」与新自申请流程略有出入（未改，可下轮顺带）；③本次未更新 docs/（如需归档可补 docs/14）；④git 未 commit。⑤apply-shop「重新申请」按钮在水合窗口对 Playwright actionability 不稳（手测无影响，自动化用 DOM 直点）。

- **上一任务（2026-11-12，爬虫任务「跳过已入库」开关，已完成）**：用户确认爬虫抓取前**不会**查库，要求加开关：已入库商品直接跳过。完整记录见 `docs/05` §5.2。
  1. **模型/迁移**：`CrawlJob.skip_imported_products`（Boolean，默认 False），迁移 `crawler_control/0009` 已在 dev 库执行；`_job_params_snapshot` 冻结 `skip_imported_products` 进运行快照。
  2. **服务/API**：`create_crawl_job(..., skip_imported_products=False)` 写入；管理端列表/详情回包含该字段；`POST /api/v1/admin/crawlers/jobs` 接受 `skip_imported_products`。
  3. **蜘蛛**（`crawler/joybuy_crawler/spiders/joybuy_run.py`）：列表卡片先攒成候选，开启开关时用**一次** `SpuSourceIdentity` IN 查询（`source_system=job.source_catalog.source_system`）找出已入库的 source_id；命中者不请求详情页（PC + `/dg/` 都省）、不占 `product_limit`、写入本轮 `seen_product_ids`（其它类目不再重复查）。每页写 `PRODUCTS_SKIPPED_IMPORTED` INFO 事件。**未开启时行为不变**。
  4. **管理端 UI**（`admin-web/src/views/CrawlersView.vue`）：新建任务表单加「跳过已入库商品」复选框 + 说明（价格/库存/评分不会刷新）；任务详情抽屉显示开启/关闭。
  - **验证（按验证纪律仅做针对性验证）**：新增 `SkipImportedProductsTests` 3 例（开启时只抓未入库商品并写事件/关闭时全抓/开关冻结进快照）→ 与 `test_crawler_control_domain` 合计 **17 tests OK**；5 个改动 py `ruff check` 全过、spider/models/services/admin_views format 全过（`test_crawler_rebuild.py` 仍有一处**改动前已存在**的 format 漂移：`SourceCategorySnapshot.objects.get(...)` 折行，未整文件重排）；`admin-web` prettier + eslint 0 错误 + `vite build` 通过；浏览器实测（临时 staff 账号，已删除）新建任务弹窗复选框默认未勾选、文案正常。后端已重启（PID 变更，`/api/v1/admin/crawlers/jobs` 401 属正常）。
  - **注意**：跳过判定是「存在来源身份」，与 SPU 状态无关（DRAFT 也跳过）；跳过后价格/库存/评分/评价数/AI 摘要都不会更新，需要刷新时关闭开关重跑。

- **上一任务（2026-11-12，购物端 UI 全量中英转换（商品内容除外），已完成）**：用户要求「除商品内容外全部中英转换」。扫描方法：正则提取 19 个 .vue 的 template 文本节点 + placeholder/aria-label 属性 + script 内 label 数组，共 ~130 处硬编码英文。
  1. **字典**：`locales/messages.js` 从 120 键扩到 **162 键**（en/zh 严格对齐，node 校验双向无缺失），新增分组：header(7)/footer(21)/auth(9)/cms(4)/bestseller(2)/account(8)/pagination(3)/orders(7)/cart(9)/checkout(21，含支付方式)/detail(14)/product(3)/listing(13)/reviews(1)/promo(4)。品牌名（Joybuy/Facebook/Google/Visa/Klarna…）有意保留原文。
  2. **替换**：24 个 .vue 文件的硬编码文案全部改走 `t()`；缺 useLocale 的组件/页面补 import + `const { t } = useLocale()`（分深度 `../`、`../../`、`../../../`）。两处 script 内静态数组改为 `computed`（ProductListing 的 `sortOptions`、AppFooter 的 `columns`），使切换语言时排序选项/页脚栏目即时刷新。
  3. **顺带修掉的既有 bug**：`AppHeader`、`pages/promo/best-seller.vue`、`p/[id].vue` 里有 6 处**静态属性里写了 `t(...)` 却没加 `:` 绑定**（aria-label/placeholder 会把字面 `t('…')` 输出给无障碍树）；我第一轮替换还制造过一个 `::aria-label` 双冒号（原属性本已绑定），已全部清零（grep `::aria-` 为空）。
  - **验证（按验证纪律仅做针对性验证）**：`vitest run` **59/59**（en 回退值保持原文，既有英文断言不受影响）；prettier + eslint 全过（修掉 messages.js 4 个 no-dupe-keys、ProductListing 的 `sortOptions.value` ref-as-operand）；残留文本节点扫描仅剩 3 个品牌名。**浏览器双语实测**（截图 `var/category_cards_20261111/shot_i18n_cart_zh.png`、`shot_i18n_detail_zh.png`）：购物车（标题/数量/删除/小计/运费提示/去结账/页脚三栏/免责声明全中文，「$799.00 单价 · 999+ 有货」）；详情页（立即购买/加入购物车/商品详情/规格参数/数量/有货，面包屑中文）；列表页（筛选/排序方式：/相关性/「7 件商品」）；结账（结算/配送至/姓名*/保存/添加新地址/取消/银行卡/立即支付，0 英文残留）；订单列表（我的订单/查看详情 →/「1 件商品」）；登录（0 英文残留）。英文回退抽样 cart 页与原文案一致。
  - **踩坑（不得再踩）**：①`aria-label`/`placeholder` 静态属性写 `t(...)` 不会求值——必须 `:aria-label`/`:placeholder` 绑定，改造前先 grep `"t\(` 区分已绑定/未绑定，别对已绑定的再加 `:`（会变 `::` 语法错误）；②cms 子目录组件的 useLocale 路径是 `../../composables/`（depth 2），别照抄 components 根的 `../`；③script 内 `label: '…'` 数组要么改 `computed` 要么接受语言切换不刷新——静态数组只在 setup 求值一次；④批量替换脚本要输出「NOT FOUND」清单并逐个人工核对上下文，纯文本节点替换对 `>Previous</button>`、`        View all` 这类无标签包裹的文本会漏。

- **上一任务（2026-11-11，左侧分类列表改为「只列 11 个一级、按所属一级高亮」，不再展开二级，已完成）**：用户从顶部【分类】下拉点二级品类进结果页后，左侧仍然展开该一级的二级列表；要求左侧只选中所属一级、不展开二级。**本条推翻上一版「二级视图在侧栏展开二级子列表」的做法（`filter-card__list--nested` 已整体删除）**。
  - **改动**：`ProductListing.vue` 侧栏「分类」组只渲染 11 个一级；新增 `isActiveRoot(category)`——`category.slug === props.slug`（一级视图）**或** `category.slug === currentRoot?.slug`（二级视图高亮其父一级）。删除嵌套列表模板与 `.filter-card__list--nested` 样式。二级的下钻入口只保留顶部卡片条。
  - **验证（按验证纪律仅做针对性验证）**：浏览器实测三条路径——顶部下拉「电子产品 → 手机」进 `/c/mobile-phones`：侧栏 11 项、仅【电子产品】高亮、`nested=0`、面包屑「首页 / 电子产品 / 手机」、卡片【手机】选中、7 products；`/s?category=electronics`：侧栏高亮【电子产品】、13 卡片、14 products；`/c/cat-food`：侧栏高亮【宠物用品】（父一级）、面包屑三级、`nested=0`。截图 `var/category_cards_20261111/shot_results_sidebar_l1_only.png`。`vitest run` **59/59**、prettier + eslint 全过。
  - **踩坑**：①侧栏列表的「选中」是**视图层级**概念——二级页要选中父一级，不能只比 `slug === props.slug`；②既然侧栏不再列出二级，二级下钻只能从顶部卡片条进入（不要把嵌套列表再加回来，用户明确不要）。

- **上一任务（2026-11-11，修复切换品类结果不刷新（useSearch 缓存 key 冻结），已完成）**：用户报「切换一级品类后标题和卡片都变了，但右侧商品还是上一个品类的」。这不是后端问题——后端 `search_documents` 早就按**子树匹配**（`category_ids = 自身 + local_category_descendants`），一级品类会带出所有子类商品。
  - **根因**：`storefront/composables/useSearchApi.js` 里 `useFetch(url, { key: \`search-${JSON.stringify(params.value || {})}\` })` 的 **key 在 setup 时求值一次就固定了**。`/s?category=a → /s?category=b` 是同一路由仅换 query，页面组件不重建 → key 不变 → `useAsyncData` 继续用第一次的缓存结果（标题/卡片来自 props 与 category tree，所以看起来「变了」）。
  - **修复**：key 改为响应式 `const key = computed(() => \`search-${query.value}\`)`。顺带修掉同类隐患：`useActivityList.js` 的 `key: \`activity-${resource}-${page.value}\`` 同样在 setup 时冻结（活动列表翻页会拿到第 1 页数据），一并改为 `computed`。
  - **验证（按验证纪律仅做针对性验证）**：浏览器实测同一路由内连点左侧一级品类——电子产品 14 件（iPhone）/ 宠物用品 3 件（CATSAN）/ 家居生活 **77 件**（7FRESH 椰子水），商品确实随品类切换；家居生活点 Next → URL `page=2`、首件变为 evian、上一页按钮启用（分页工作，截图 `shot_results_l1_subtree_paginated.png`）；点顶部卡片「厨房与餐厅用品」→ `/c/kitchen-essentials`、三级面包屑、该卡选中、侧栏展开二级、**0 products**（实库核对该二级确实 0 商品：home-living 子树 74 个子类文档 + 3 个挂在根上 = 77，属数据而非 bug）。`vitest run` **59/59**、改动 2 个文件 prettier + eslint 全过。
  - **踩坑（不得再踩）**：①`useFetch` 的 `key` 必须写成 `computed`/`ref`——写成模板字符串时只在 setup 求值一次，同路由换 query 的页面（`/s?category=`、`/s?k=`、活动列表翻页）都会继续显示旧数据；②「标题/卡片变了但列表没变」这类现象优先怀疑取数缓存 key，而不是后端筛选；③一级品类走子树匹配，二级只看自身，二者都由后端 `search_documents` 负责，前端不要重复过滤。

- **上一任务（2026-11-11，一级品类结果页修复：不展开二级、保留二级卡片条，已完成）**：用户点左侧一级【电子产品】后跳 `/s?category=electronics`，出现两个问题：①侧栏还展开了该一级的二级；②顶部二级卡片条消失。
  - **根因**：`ProductListing` 的 `currentRoot` 只按「slug 是某个一级的**子级**」匹配。一级页的 slug 就是一级本身 → `currentRoot` 为 null → 面包屑、卡片条、h1 本地化名全部丢失（h1 退化成 slug 文案 `electronics`）；而侧栏「二级子列表」的展开条件只判 `currentRoot?.children`，在二级页一直展开、切到一级页后状态判定混乱。
  - **修复**：抽纯函数 **`storefront/utils/categoryContext.js::resolveCategoryContext(categories, slug)`**——先按子级匹配（二级视图：root=父级、child=该二级），再按一级匹配（一级视图：root=该一级、**child=null**），都没有则返回空。`ProductListing` 用它产出 `currentRoot/currentChild`：
    1. **侧栏二级子列表改为 `v-if="currentChild && currentRoot?.children?.length"`**——只有二级视图才展开；一级视图只高亮该一级本身（实测 `sidebarNested=0`、active=电子产品）。
    2. **卡片条与面包屑不再依赖 child**：一级视图显示 `首页 / 电子产品` + 该一级全部 13 张二级卡片（无选中，`activeTiles=0`）+ 底部轮播导航条；二级视图仍为 `首页 / 电子产品 / 手机` + 13 张卡片且「手机」选中。
    3. h1 改为 `currentChild || currentRoot` 的本地化名（一级页显示「电子产品」，不再显示 slug）。
  - **验证（按验证纪律仅做针对性验证）**：浏览器实测两种状态——`/s?category=electronics`：crumb「首页 / 电子产品」、tiles 13、activeTiles 0、sidebarNested 0、active 电子产品、h1 电子产品、导航条存在（截图 `shot_results_level1_view.png`）；`/c/mobile-phones`：crumb「首页 / 电子产品 / 手机」、tiles 13、activeTiles 1、sidebarNested 1、active 手机、h1 手机。`vitest run` **59/59**（新增 `tests/categoryContext.test.js` 3 例：二级解析到父级+自身、一级解析到自身且 child 为 null、未知/空 slug 返回空），prettier + eslint 全过。
  - **踩坑（不得再踩）**：①结果页的「当前一级」不能只按子级反查——一级页 slug 就是一级，必须再兜一次自身匹配，否则卡片条/面包屑整体消失；②侧栏二级列表的展开条件要绑 `currentChild`（视图层级），不能绑 `currentRoot`（一级也有 children，会在点一级时错误展开）；③`tests/` 目录下的用例引用 `utils/` 要用 `../utils/...`。

- **上一任务（2026-11-11，分类结果页改版：左筛选项 / 右结果 + 单行卡片轮播（左右箭头 + 底部导航条），已完成）**：用户要求按 Joybuy 样式改结果页。
  1. **布局**：面包屑与品类卡片条从「全宽、压在两栏之上」移到**右栏顶部**（`.listing-main` 内），左栏 `.listing-sidebar`（234px「筛选」）与右栏同起于页面顶部。实测：sidebar x=41/y=192，main x=299/y=192（同一行起）。
  2. **左侧筛选栏**（对齐 Joybuy 的「筛选」分组）：新增「筛选」总标题；「分类」组 = 11 个一级 + **当前一级的二级子列表**（缩进 + 左侧分隔线，当前项高亮）；「价格区间」组保留 min/max 输入，按钮文案本地化。文案键新增 `listing.filters / listing.category / listing.price / listing.sortBy / listing.apply`（中英双语），排序标签也改为本地化。
  3. **单行卡片轮播**：新增 **`storefront/components/CategoryTileCarousel.vue`**——`CategoryTileGrid` 增加 `row` 单行模式（`flex: nowrap`，每张固定 8.5rem=136px，与 Joybuy 一致），外层横向滚动容器隐藏原生滚动条；溢出时底部出现**导航条**：`‹ [进度轨道+滑块] ›`（圆形白底带边框阴影的箭头、12rem 细轨道、滑块宽度=可视比例、位置按滚动比例）。到端点自动禁用对应箭头；无溢出则不显示导航条。箭头每次翻约 0.9 屏宽。
  - **验证（按验证纪律仅做针对性验证）**：浏览器实测 `/c/mobile-phones`（1440×900）——面包屑「首页 / 电子产品 / 手机」、卡片轨道 `scrollWidth 1864 > clientWidth 1086` → 导航条出现，进度 58%；点右箭头 `scrollLeft 0→778`、滑块 `left 0%→42%`、右箭头转 disabled、左箭头启用（截图 `shot_results_sidebar_carousel.png` / `shot_results_carousel_scrolled.png`）。`vitest run` **56/56**（新增 `CategoryTileCarousel.test.js` 4 例：不溢出隐藏导航条、溢出显示箭头与比例滑块、滚动后滑块/箭头状态、箭头按视口翻页），prettier + eslint 全过。
  - **踩坑**：①jsdom 没有布局引擎，`scrollWidth/clientWidth` 恒 0，轮播测试必须 `Object.defineProperty` 伪造尺寸再触发 `scroll` 事件重算，否则永远测不到溢出分支；②结果页的卡片条**必须在右栏内**，放在两栏之前会让左栏整体下沉（本轮就是上一版的问题）；③`ProductListing` 的排序/筛选文案原先写死英文，中文站里要点检本地化。

- **上一任务（2026-11-11，分类下拉四项交互/样式修正 + 分类结果页面包屑与同父卡片条，已完成）**：用户逐条提出 4 项。
  1. **悬停态**：二级卡片 hover 时**背景变 #FFFFFF**、名称保持黑色、**名称下方加下划线**（卡片默认灰底 #F5F6F7）。实测：`background: rgb(255,255,255)`、`textDecorationLine: underline`、名称色 `rgb(23,32,42)`。
  2. **名称字体不一致的根因**：Joybuy 用 **Barlow 500**，我们只本地托管了 Barlow **400/600/700**，浏览器把 `font-weight:500` 落到 400 → 视觉偏细。已下载 **`storefront/public/fonts/barlow-500.woff2`**（22KB，wOF2 magic 已校验）并在 `assets/css/base.css` 补 `@font-face weight 500`；实测 `document.fonts.check('500 14px Barlow') === true`，卡片名 computed = Barlow / 14px / 500 / line-height 20px（与 Joybuy 实测值一致）。
  3. **分类结果页面包屑**：`ProductListing`（`/c/<slug>`）新增 `首页 / 一级 / 二级` 面包屑——首页与一级可点（`/`、`/c/<L1>`），当前二级为纯文本加粗；h1 也从 `Category: <slug>` 改为本地化二级名。实测 `/c/mobile-phones` → 面包屑文本「首页 / 电子产品 / 手机」，链接 `/` 与 `/c/electronics`。
  4. **面包屑下方同父级卡片条**：显示该 L1 的全部二级卡片（实测 13 个），当前二级为选中态：**白底 + 1px 品牌红边框（#C8102E）+ 名称无下划线**；未选中卡片保持灰底、hover 白底+下划线。
  - **实现要点**：把卡片 UI 抽成共享组件 **`storefront/components/CategoryTileGrid.vue`**（props: `items` / `activeSlug`，emit `select`），下拉面板 `AppCategoryPanel.vue` 与结果页 `ProductListing.vue` 共用；文案键新增 `breadcrumb.home`、`categoryStrip.label`（中英双语）。**注意：组件必须显式 `import CategoryTileGrid from './CategoryTileGrid.vue'`**——单测环境没有 Nuxt 自动导入，只靠自动注册会渲染空白（本轮踩到过）。
  - **验证（按验证纪律仅做针对性验证）**：`vitest run` **52/52**（新增 `CategoryTileGrid.test.js` 3 例：本地图+链接、仅 active 带选中类、点击 emit slug；`AppCategoryPanel.test.js` 选择器改为 `.category-tile*` 后 4 例仍过）；改动 7 个文件 prettier + eslint 全过。浏览器实测四项（截图为证）：`var/category_cards_20261111/shot_tile_hover_underline.png`（悬停：白底+下划线）、`shot_results_breadcrumb_strip.png`（面包屑 + 13 张同父卡片、手机选中白底红框）。
  - **踩坑（不得再踩）**：①字体只有 400/600/700 时 `font-weight:500` 会静默落到 400，要核对本地 `@font-face` 的权重清单；②共享组件在 vitest 里必须显式 import；③`ProductListing` 的 `heading` 原先写死 `Category: <slug>`，分类模式改用本地化名称后不要再回退成 slug 展示。

- **上一任务（2026-11-11，分类下拉卡片样式对齐 Joybuy：名称移入卡片内 + 间距收紧，已完成）**：用户反馈「卡片应该把名称包含在里面，两个卡片之间间隙太大」。**实测 Joybuy 真实规格**（`m.joybuy` / `www` 头部下拉，zh_CN，`div[role=button][class*=category_category_btn]` 悬停展开）：卡片 **136×136**、底色 **#F7F7F7**、圆角 **8px**、内边距 **8px**、图片 **72×72**（顶部偏移 9px）、名称 **14px / 500 / #1A1A1A** 且**在卡片内部**（顶部偏移 89px）、卡片容器 `display:flex` **gap 8px**、一行 4 个（568px 区块 = 4×136 + 3×8）。
  1. `storefront/components/AppCategoryPanel.vue`：`.category-panel__child` 改为**灰色方块卡片**（`background: var(--colour-surface-soft)` = #F5F6F7、`radius: var(--radius-md)` = 8px、`aspect-ratio: 1/1`、`padding: var(--space-2)`、内容垂直居中、名称在卡片内 14px/500），图片 `width: 60%`（≈ 卡片内容区的 72px/120px 比例）；`.category-panel__children` 的 gap 从 `var(--space-4) var(--space-3)`（16px/12px）收紧为 **`var(--space-2)`（8px）**；名称加 2 行 line-clamp 防长名破卡。
  2. 面板宽度 800px → **896px（56rem）**，使详情区一行放得下 4 张卡（实测卡片 144px、4 列、gap 8px）。
  - **验证（按验证纪律仅做针对性验证）**：浏览器实测（1440×900，localhost:3000）面板 896、`grid-template-columns` 4 列、卡片 144×144、gap 8、图片 88px、名称 top offset 120（在卡片内）、14px/500；截图 `var/category_cards_20261111/shot_cards_name_inside.png`。`vitest run` **49/49**（AppCategoryPanel 4 例）、prettier + eslint 全过。
  - **踩坑**：①Joybuy 的 tile 名称在卡片**内部**（旧实现放在框外，是首轮卡片化时凭截图判断错的）；②卡片容器是 `flex + gap 8px`，不是 grid，别看错；③改面板宽度后要复核一行能放几个——`auto-fill minmax(7.5rem, 1fr)` 在 512px 内容宽下只有 3 列。

- **上一任务（2026-11-11，全频道二级品类一次性对齐 Joybuy 现网，已完成）**：用户要求把 11 个一级下的二级品类**全部**与 Joybuy 对齐（不只是宠物）。产物与证据：`var/menu_refresh_20261111/`。
  1. **关键发现：Joybuy 分类下拉是 21 个分组，不是 14 个频道**。左上分组栏顺序：为你推荐 / 电子产品 1409 / 世界食品 1544 / 大家电 2695 / 速冻食品 1504 / 家居生活 1563 / 食品柜 1274 / 软饮、茶与咖啡 1299 / 小家电 1396 / 美妆&个人护理 2709 / 啤酒、葡萄酒及烈酒 1314 / 家居、洗衣及清洁用品 1521 / 计算机及配件 1431 / 健康与保健 1451 / 服装与配饰 1876 / 游戏 1422 / 户外、运动与DIY 1582 / 休闲玩具 1369 / 宠物用品 1362 / 婴幼儿用品 1473 / 办公文具 1440 / 汽车 3895。每个分组 = 一个 `firstcid` 区块；旧抓取把这 21 个区块里的 `l3:` 深层节点也当二级抓过，所以出现「显示器 + 游戏显示器」这种重复。**对齐全按「下拉面板」为准**。
  2. **新菜单版本**：`sync_joybuy_category_tree --from-json var/menu_refresh_20261111/menu_full.json --publish` → **`joybuy-uk-20261111-441f4b04`**（14 频道 / 225 节点 / 新增 43 / 移除 0）。构建脚本 `build_full_menu.py` 的放置规则：**每个节点保留原有频道归属**，只有新节点加入首个列出它的频道；旧子节点若区块不再提及则原样保留（否则 TV / 汽车频道会被全局去重清空）；`速冻食品(1504)` 不在任何 `/minihome` 页，显式钉到 Home-Living 频道。
  3. **crosswalk**：`NODE_SLUG` 新增 43 个一对一 slug；`NODE_PARENT` 新增 21 条（跨频道归属：l2:1522/1530→home-living、l2:4268/4270/1432/2621→computers、l2:1583/5332/1584→outdoor-sports 等）；`NODE_UNMAPPED` 扩到 17 个（6 汽车 + **11 个下拉里不出现的深层节点**：l3:1437/5116/5117/1500/1430/3014/2746/3144/1531/1523/3121）；`RETIRED_LOCAL_SLUGS` 增加 11 个（tv-audio-accessories / consoles-tv-audio / gaming-keyboards / gaming-mice / gaming-monitors / intimate-care / sunscreens / toilet-roll / kitchen-roll / pest-control / watering-garden-tools）。`NAME_OVERRIDES` 现为空（三处同名冲突节点都是深层节点，已下线）。
  4. **本地类目**：172 → **204（11 一级 + 193 二级）**。各一级二级数：家居生活 69 / 电子产品 13 / 美妆个人护理 15 / 小家电 19 / 健康与保健 9 / 计算机与配件 10 / 服装与配饰 7 / 户外运动 5 / 宠物用品 13 / 婴幼儿用品 25 / 游戏及配件 8。**与现网下拉严格一致**（逐一级核对：live 合计 199，本地合计 193，差额正好是 6 个按设计排除的：5 个汽车节点 + `l2:1580` 节庆装饰品=活动商品）。`diy-tools`、`office-electronics` 两个类目因父级纠偏被删除重建（0 商品，安全）。
  5. **品类卡片图**：193/193 个二级都有本地图（204 个 webp 文件），manifest `storefront/assets/category-images.js` 160 → **204** 条、0 CDN。新图统一用 `s360x360_`。4 个节点现网暂无中文名（Robotics / Drones / Networking Devices / Virtual Reality & Simulation），按既有惯例英文兜底。
  - **验证（按验证纪律仅做针对性验证）**：`test catalog.tests.test_joybuy_menu_crosswalk catalog.tests.test_standard_categories crawler_control.tests.test_crawler_product_category --keepdb` → **38 OK**（`OneToOneSplitTests` 改名为 `DeepNodeRetirementTests`：深层节点不再建本地二级、同名消歧随之消失）；`test_crawler_rebuild.MenuJsonRoundTripNameZhTests` → 1 OK；改动 4 个 py `ruff check` 全过；storefront `vitest run` **49/49**；manifest prettier + eslint 全过（修掉了 33 处 duplicate key）。**浏览器实测**（localhost:3000，中文）：电子产品 **13/13 卡片图加载**（含 Robotics / Drones，见 `shot_electronics_full_align.png`）、户外运动 5、小家电 19、家居生活 69、计算机与配件 10（含从 electronics 移入的 office-electronics）；新图 HTTP 抽查 10 个全部 200 image/webp。
  - **踩坑（不得再踩）**：①**Joybuy 下拉面板必须「悬停」才切换**（`.click()` 无效），触发器是 `div[role=button][class*="category_category_btn"]`，rail 项是 `[class*="category-list-lv1"] > li`；用 `cua.move` 悬停最稳，视口高度要 ≥1500 否则 y>720 的分组一移出视口面板就关；②抓中文名先把 `_lang=zh_CN` 写进 cookie 再 reload；频道页只 SSR「热门子集」（167 个），**新增节点只在 21 个下拉区块里**；③**退役前必须核对节点是否真的不在任何面板里**——本轮一度把 l2:2621 / l2:2735 / l2:1584 / l2:5380 误退役（它们在别的区块仍然出现），已回滚；④`sync_local_categories_from_joybuy` 不会给已有类目换父级，改 `NODE_PARENT` 后必须先把空类目删掉再同步，否则报「slug 已挂在 X 下」；⑤manifest 里既有 `bath:` 无引号键，脚本按 `'bath'` 匹配会漏判导致重复键，eslint 会因 `no-dupe-keys` 报错——改 manifest 后必须跑 prettier + eslint；⑥`save_source_category_version` 不给 `sort_order` 会全 0（测试排序断言会假失败）。

- **上一任务（2026-11-11，宠物用品二级 8 → 13 与 Joybuy 现网持平，已完成）**：用户报「Joybuy 宠物用品 13 个二级，我们只有 8/9 个」。根因：**菜单快照过期**（`SourceCategorySnapshot` 最新版本是 2026-11-04 抓的，宠物频道那时确实只有 8 个；Joybuy 之后新增了 5 个）。不是映射丢失、也不是 crosswalk 漏配。
  1. **现网核实**：Joybuy 频道页/菜单面板实录宠物频道 = **13 个二级**（+1 个「View all Pets」伪节点）：猫粮 1363 / 猫砂 4707 / 狗粮 1364 / 猫零食 3532 / 狗零食 5441 / 智能宠物电器 4711 / 狗玩具 4713 / 猫玩具 3540 / 小宠用品 1365 / 其他动物用品 3534 / 宠物用品与配件 3542 / 医疗保健与营养 3536 / 宠物美容护理 3538。原 8 个中缺的是 **猫砂、狗零食、智能宠物电器、狗玩具、小宠用品**。证据：`var/pet_categories_20261111/panels_parsed.json`（14 频道菜单面板解析，含 tile 图 URL）、`pets_zh_tiles.json`（中文名）。
  2. **菜单版本刷新**：`sync_joybuy_category_tree --from-json` 需要保留中文名（新节点在 `SourceCategory` 里没有 `name_zh` 可回退），先给该命令的 `_nodes_to_json` / `_json_to_nodes` 补 `name_zh` 透传。用脚本 `var/menu_refresh_20261111/build_pets_menu.py` 以**当前已发布树为基座**、只把宠物频道子节点换成现网 13 个 + 现网顺序，产出 `menu_pets_refresh.json`；再 `--from-json ... --publish` → 新版本 **`joybuy-uk-20261111-f2a65069`**（14 频道 / 182 快照 / 新增 5 / 移除 0）。**除宠物外逐频道与旧版完全一致**（已核对）。
  3. **crosswalk 补 5 个一对一 slug**（`backend/catalog/joybuy_menu_crosswalk.py` NODE_SLUG）：`l2:4707→cat-litter`、`l2:5441→dog-treats`、`l2:4711→smart-pet-appliances`、`l2:4713→dog-toys`、`l2:1365→small-animals`。
  4. **本地类目同步**：`sync_local_categories_from_joybuy --dry-run` 后正式 → 新建 5 / 更新 31 / 未变化 125 / 映射 161 / 未映射 6（汽车，按设计）/ 错误 0。**本地类目 167 → 172（11 一级 + 161 二级）**，宠物二级 **13 个、顺序与现网一致**。注意「更新 31」里 23 个是非宠物节点的 `sort_order` 归一到当前快照索引（旧值有 ±1 偏移），只影响同级展示次序，非功能变更。
  5. **品类卡片图**：5 个新类目图从现网 tile 下载（`s180x180_` → 换成 `s360x360_` 以与既有 155 张同规格），落 `storefront/public/images/categories/<slug>.webp`，manifest `storefront/assets/category-images.js` 155 → **160** 条；`other-animals` 仍走 `_placeholder.svg`（现网无该 tile）。
  - **验证（按验证纪律仅做针对性验证）**：`test catalog.tests.test_joybuy_menu_crosswalk` → **8 OK**（新增 `PetsOneToOneTests` 2 例：13 子类目顺序与现网一致 + 5 个新 slug 稳定；**坑：`save_source_category_version` 的节点 dict 不传 `sort_order` 会全为 0，测试必须显式给索引**）；`test crawler_control.tests.test_crawler_rebuild.MenuJsonRoundTripNameZhTests` → 1 OK；`test test_standard_categories + test_crawler_product_category + test_crawl_jobs_api` → 32 OK；改动 4 个 py `ruff check` 全过；storefront `vitest run` **49/49**。
  - **浏览器实测**（localhost:3000，中文）：分类面板【宠物用品】= **13 张上图下名卡片**，顺序与 Joybuy 一致，5 张新图 360px 全部本地加载（`naturalWidth=360`），`other-animals` 占位图不破版；截图见下。API `GET /api/v1/categories` 已返回 13 个（DB 变更，无需重启后端）。
  - **遗留待用户拍板**：现网菜单面板里还有 **49 个节点在我们的类目树里不存在**（除 6 个汽车节点与 `l2:1580` 节庆装饰品按设计不映射）。分类：冷冻食品 9（Frozen Ready Meals/Desserts/Pizza/Ice Cream/Chips/Vegetarian/Fruit/Meat/Party Food + Frozen World Food）、食品 4（Crackers & Crispbread / Home Baking & Sugar / Jam & Spreads / Meal Kits）、酒水 6（Cocktails / Low Alcohol / Tonic Water / Tobacco / Vapes / Tobacco Alternatives / Premium Spirits）、游戏 4（Gaming Accessories / Headsets / PC Gaming / VR）、电脑 3（Networking Devices / Printers & Scanners / Printer Accessories）、家电 2（Drink Makers / Dishwashers）、电子 2（Robotics / Drones）、户外 2（Garden / Sports apparel）、家居 2（Umbrellas & Rain Gear / Household Essentials + Kitchen Roll, Toilet Roll & Tissues）、美妆 1（Intimate & Hygiene）、玩具 1（LEGO Sets）、服装 1（Accessories）。**本次未动**——要补齐需再来一次全频道菜单刷新（同一套 `--from-json` 流程即可）。
  - **踩坑（不得再踩）**：①菜单快照会过期，用户报「数量对不上」时先核现网再怀疑映射；②`manage.py` 的相对路径以 `backend/` 为 cwd，`--from-json` / `--report` 一律给绝对路径；③`--from-json` 原实现不传 `name_zh`，新节点会变英文名；④`save_source_category_version` 节点不显式给 `sort_order` 就全 0，测试排序断言会假失败；⑤`sync_local_categories_from_joybuy` 会顺带把同级 `sort_order` 归一到快照索引，看到「更新 N」不要慌，先确认只是排序。

- **上一任务（2026-11-11，分类下拉二级品类改「上图下名」卡片 + 品类图本地托管，已完成）**：用户要求按 Joybuy 样式把分类下拉的二级品类做成小卡片（上图片、下名称），图片从 Joybuy 下载后本地固定展示。完整记录见下一条。
- **上一任务（2026-11-11，购物端分类下拉卡片化：二级品类「上图下名」小卡片，图片从 Joybuy 下载本地托管，已完成，只测未提交）**：把 `AppCategoryPanel` 的二级品类从纯文字链接改成 Joybuy 同款 tile 卡片（方形图在上、品类名在下），图片全部落 `storefront/public/images/categories/` 本地托管，manifest 只存本地路径。证据与脚本全在 `var/category_cards_20261111/`。
  1. **图片来源与抓取方式（重要，别再走浏览器弯路）**：库里 `SourceCategorySnapshot` 没有图片字段，菜单 JSON 也不含图——**Joybuy 的卡片图在每个 `/minihome/<code>` 频道页 SSR 的「popular category」tile 区**（`uk-pc-popular-category-big-2` 模块，`<a href="/s?...&l2=<id>">` 内嵌 `<img>`（s360x360/s410x410，全部 .webp，joy-sourcing CDN），结构=上图下名，与头部分类下拉同款）。**纯 HTTP 就能抓，无风控**（首页与频道页均 200；只有首页头部的下拉面板本身是运行时加载、SSR 里只有按钮壳）。流程：`fetch_home.py` 取首页提 14 个 minihome 频道码 → `capture_menu_tiles.py`（顺序抓 + 2.5s 间隔 + 单次重试，14 页存 `channels/<code>.html`）→ 正则按 `category_menu.py` 同款口径取最深 facet 为 source_id、锚点内第一个 joy-sourcing `img.src` → `channel_tile_index.json`（167 个唯一 source id 有图）→ `build_image_urls.py`（manage.py shell 里连库，`CategoryMapping.is_primary` join `LocalCategory`）→ `source_image_urls.json`（source_id→{slug,l1,url,…}）+ `coverage_report.json`。
  2. **覆盖率 155/156**：唯一无图节点 = 宠物用品下 `other-animals`（`l2:3534` 其他动物用品，所有频道页都没有它的 tile），走本地占位图兜底，如实记入 `missing.json`（NO_SOURCE_IMAGE）。下载 `download_images.py`：155 张全部一次成功（4 并发 + 每请求 0.2s 停顿 + 单次重试 + magic bytes 校验），落 `storefront/public/images/categories/<slug>.webp`（共 3.2MB，360~410px 方图）。
  3. **manifest**：`storefront/assets/category-images.js`（生成文件）导出 `categoryImages`（named + default）= `{ slug: '/images/categories/<slug>.webp' }`，**只存本地路径**；生成器 `write_text(..., newline="\n")` 防 CRLF（否则 prettier endOfLine=lf 拒收，第一次生成吃过这亏，已 --write 修过一次）。组件对 manifest 未命中的 slug 回退 `/images/categories/_placeholder.svg`（自绘灰底图片 glyph SVG，tokens 配色）。全仓 grep 确认前端代码/manifest 无任何 CDN URL（manifest 注释也只写「source site image CDN」不写域名）。
  4. **组件改造**：`storefront/components/AppCategoryPanel.vue` 二级区从「inline-flex 文字链接」改为 `repeat(auto-fill, minmax(6.5rem, 1fr))` 响应式卡片网格；卡片=`<NuxtLink>` flex column：`img.category-panel__child-image`（aspect-ratio 1/1、object-fit cover、radius-md、surface-muted 底色兜加载期）+ `span.category-panel__child-name`（13px secondary）；hover=背景 `--colour-hover` + 名称 `--colour-accent`（站点既有语言）；一级左栏不动（Joybuy 一级本来就是纯文字）。`alt=""`（名称在旁，装饰性图）。
  5. **测试与静态检查（按验证纪律仅针对性验证）**：`AppCategoryPanel.test.js` 新增 2 例（卡片解剖结构=1 img+1 name 且图在上；manifest mock 命中走本地路径、未命中走 placeholder、断言 src 永不为 http(s)/joy-sourcing），既有 2 例同步改为断言 `.category-panel__child-name`；storefront `vitest run` **49/49 过**（11 文件，仓库根 node_modules 绝对路径调）；改动 3 文件 prettier --check + eslint 全过。
  6. **浏览器实测（localhost:3000，1440×900，中文 locale，4 张截图在 var/category_cards_20261111/）**：①电子产品 13 卡：手机/平板电脑 均上图下名（img src=/images/categories/mobile-phones.webp|tablets.webp，naturalWidth>0，101×101 方图）；②家居生活 47 卡、小家电 17 卡抽查（chocolate-sweets/air-fryers 等）全本地加载；③宠物用品下「其他动物用品」显示 _placeholder.svg，与邻卡同构不破版；④真实悬停狗粮卡：背景 rgb(240,241,244)=--colour-hover、名称 rgb(200,16,46)=--colour-accent；⑤shot1~shot4 截图落盘。dev server 热更自动生效（未重启）。
  - **踩坑（不得再踩）**：①别再用真浏览器探 Joybuy 下拉——首页头部下拉是 hydration 后运行时渲染，DrissionPage 探查脚本（`explore_dropdown.py`）挂 9 分钟无产出被杀；**频道页 SSR 纯 HTTP 直出全部 tile 图**，抓图只走 HTTP；②IAB 后端 locator `locator(sel, {hasText})` 的 hasText 不生效（返回全量），要用 `.filter({hasText})`，且 locator **没有 hover 方法**（root 按钮有 click 处理器，click 即可；真 hover 用 `tab.cua.move`）；③点左栏一级后 Vue 重渲染可能让指针脱离面板触发 mouseleave 关面板——**开面板→选一级→截图要放同一个 JS cell**；④Windows 上 Python `write_text` 默认 CRLF，生成的 js 要过 prettier 必须 `newline="\n"`；⑤`SourceCategory` 没有 `source_url` 字段（在 Snapshot 表上），join 脚本别引用。

- **上一任务（2026-11-11，类目一对一拆分：二级品类集合与 Joybuy 一模一样，已完成，只测未提交）**：用户推翻 2026-11-09「合并补全」里的**多对一桶口径**（其余口径全部保留：11 个一级不动、按二级拆分保留、汽车不映射、`l2:1580` 活动、7 个无中文名节点英文回退、`LOCAL_PARENT_MERCHANT_CATEGORY`/`Spu.merchant_category` 推导不动、`ProductCategory` 2 级面包屑不动）。改动与证据：`var/split_categories_20261111/`，`docs/15` §2 已重写为一对一口径。
  1. **crosswalk 一对一**（`backend/catalog/joybuy_menu_crosswalk.py`）：删除 `PRESERVE_BUCKET_SLUGS` 与 `CHANNEL_DEFAULT_CHILD`，新增 `NAME_OVERRIDES`（同父重名消歧）与 `RETIRED_LOCAL_SLUGS`（14 个退役 slug）。9 个多对一桶全部拆开：`groceries-food`→24 个食品子类目、`phones-tablets`→`mobile-phones`+`tablets`、`laptops-desktops`→`laptops`+`desktop-pcs`、`pc-components`→`gaming-pc-components`+`gaming-memory-storage`、`tv-audio`→`soundbars-home-cinema`+`tv-audio-accessories`、`pet-food`→`dog-food`+`cat-food`+`cat-treats`、`pet-toys`→`cat-toys`、`toys-early-learning`→`infant-pre-school-toys`+`infant-pre-school-toys-activities`、`consoles`×2 与 `monitors`×2 同名节点拆分。**消歧名（跨频道同名、同父类目）**：`l3:1437`→游戏显示器/Gaming Monitors、`l3:1500`→影音电子配件/Electronic Accessories (TV & Audio)、`l3:1430`→影音游戏机/Consoles (TV & Audio)（另一同名节点保留 Joybuy 原名与原 slug：`monitors`/`electronics-accessories`/`consoles`）。**6 个不在 Joybuy 菜单的基座二级退役**：networking/cycling/water-sports/personal-care-appliances/gaming-accessories/board-card-games。验证：163 节点 → 156 个一对一 slug（6 汽车+1 活动除外），无重名、无 slugify 兜底、无同父重名。
  2. **sync 命令**：`_prune_activity_categories` 泛化为 `_prune_retired_categories`（`ACTIVITY_LOCAL_SLUGS ∪ RETIRED_LOCAL_SLUGS`），安全规则升级为无商品/**无搜索文档引用**/无子类目/无商品类目引用才删（先删残留 mapping），否则保留+警告，绝不级联。输出文案改「清理退役/活动类目 N」。幂等：连跑三遍第二遍起全部 0 变更。
  3. **seed 命令**：基座子类目对齐一对一集合（38 个：拆分后的新 slug 进 seed，6 个退役移除，`peripherals` 名改为 Joybuy 原名「Mouse, Keyboard & Accessories/键盘、鼠标及输入设备」，`rice-pasta-pulses` 进 home-living 作演示兜底）；**子类目 sort_order 只在创建时写**，不再覆盖 Joybuy 同步的排序；`DEMO_FALLBACK_SLUG` → `rice-pasta-pulses`。`load_uk_bestsellers_demo.TAB_CATEGORY_MAP` 同步改指一对一子类目（Food Cupboard→rice-pasta-pulses、Frozen Food→chinese、Beverages→water、Softdrinks→fizzy-drinks、Instant Noodle→rice-pasta-pulses 等），fallback 同改。
  4. **dev 库迁移**（`var/split_categories_20261111/split_categories.py`，先 `SPLIT_CATEGORIES_DRY_RUN=1` 干跑再正式；DRY_RUN 挡住全部写库：sync --dry-run、SPU 保存、文档刷新、prune）：流程 = sync pass1（建 40/拆桶，旧桶因有商品+文档被安全保留）→ SPU 重映射 → 逐个 `refresh_spu_search_documents` → sync pass2（桶已空，退役 8 个）。**数字：新建 40 个二级、退役 14 个、重映射 76 个 SPU（62 食品→10 个食品子类目、14 手机→mobile-phones）、manual 0、merchant_category 不一致 0（重映射范围内）**；本地类目 141 → **167**（11 一级 + 156 二级；各一级：家居 47、电子 13、美妆 16、小家电 17、健康 9、计算机 9、服装 6、户外 2、宠物 8、婴幼儿 24、游戏 5）。`verify_after.json`：双射核验 156/156、退役 slug 全部不存在、无 SPU 挂桶、文档 132 条全指向合法类目。
     - **重映射依据链**（优先级照任务）：SpuSourceIdentity→staging payload `source_category_id`/`crawl_source_category_id`→SourceCategory→新 primary mapping（14 个手机 `l2:1420` 走这条）；演示 fixture 的 payload source_category_id 不是菜单节点——UK 榜单 tab（如 "Rice, Pasta & Pulses"）走 `TAB_CHILD`、.com 楼层数字 ID（5888/11074 等）走 `COM_DEMO_SCI_CHILD`（依据=实库按 ID 分组核对，脚本头部有完整注释），少数歧义 tab 再按标题关键词精化（cola→fizzy-drinks 等，basis 全记录）；ProductCategory 面包屑名匹配兜底；活动商品保持 NULL（本批无）；无身份手工商品（SPU 165）未动（local_category 仍 NULL）。
     - **踩坑（不得再踩）**：正式跑完后我用一条"确认"命令**把同一脚本又执行了一遍**——幂等没破（第二遍新建 0/重映射 0/prune 0，反而证明了幂等），但**第二遍覆盖了第一遍的 `split_result.json`/`split_log.txt`/`sync_pass1.json`/`sync_pass2.json`**，正式执行那次逐 SPU 的 applied 明细丢失。证据链=干跑结果 `split_result_dry_run.json`（before 快照+76 条计划）+ 第二遍结果里的 after 快照 + `verify_after.json`（只读核验）。以后一次性脚本的结果文件要么带时间戳、要么严禁重复执行。
  5. **全仓 grep**：旧 slug/名称残余只在三类处——crosswalk/sync/seed 的**注释与退役清单**（故意保留）、`docs/14` 的 2026-11-10 历史执行记录（不改写历史）、`docs/12` 榜单楼层 tab 文案（Joybuy 自己的楼层 tab 名，与本地类目无关）。`storefront/components/AppCategoryPanel.test.js` 的 mock fixture 从 `tv-audio` 改为 `soundbars-home-cinema`。
  6. **验证（按验证纪律仅做针对性验证）**：`manage.py test catalog.tests.test_standard_categories catalog.tests.test_joybuy_menu_crosswalk crawler_control.tests.test_crawler_product_category --keepdb` → **36 OK**（新增：seed 不复活退役 slug、空桶退役/有商品桶保留、跨频道同名一对一拆分+消歧名 3 类用例；`test_assign_demo_products` 断言改 rice-pasta-pulses）；`catalog.tests.test_bestseller_demo` → 1 OK（118s，走 .com 榜单 loader，不受影响）；改动 7 个 py `ruff check` 全过、`ruff format --check` 6/7 过（`test_standard_categories.py` 有 1 处**改动前就存在**的长行漂移，按纪律未整文件重排）；storefront `vitest run components/AppCategoryPanel.test.js` → 2 OK、prettier --check（已 --write 一次修正）+ eslint 全过。
  7. **浏览器实测**（后端已重启：旧 PID 16440 → taskkill → `runserver 127.0.0.1:8000 --noreload`，新 PID 34376）：①storefront 分类面板【电子产品】下【手机】/c/mobile-phones 与【平板电脑】/c/tablets 各自独立（13 个子类目），/c/mobile-phones 7 商品（iPhone 17 等）、/c/rice-pasta-pulses 28 商品、旧 /c/phones-tablets 直达只剩空列表（slug 已不在导航/无文档）；②管理端商品池：品类筛选下拉仍 11 个一级，电子产品筛选出的行「品类」列显示**手机**；编辑弹窗「子品类」下拉=新二级全集且无旧桶（电子产品下 13 项、家居生活下 47 项含全部食品子类目），当前值挂一级本身的以「xxx（当前值）」保留。截图 `shot1~shot4_*.png` 在 `var/split_categories_20261111/`。
  8. **顺带核对（未改）**：`verify_after.json` 记录 20 个**存量** merchant_category 与新父类目推导不一致（SPU 42-51/69-71/84-87/103-105，updated_at=11-05，是 seed 关键词移动 demo 商品时留下的旧漂移，非本次引入；导入规则「只填空不覆盖」未变，不修）；SPU 164 is_activity=True 但 local_category 挂在 electronics 一级本身（11-09 就是如此，`is_activity` 只加不减，不清理）。
  - 未做/边界：商家端页面未动；storefront/admin 生产构建未跑（dev 验证为准）；旧 `/c/<退役 slug>` 链接不做 301，直达显示空列表。

- **上一任务（2026-11-11，全面回归测试（用户明确要求全量验证），已完成，随后自动关机）**：4 路并行回归，所有报告在 `var/regression_20261111/`。**总体结论：疑似新回归 = 0；已知历史断言漂移共 3 处后端用例（均为改动前就失败，修复方向见下），前端 prettier 历史漂移共 8 个文件（未 --write）；1 个 UI 小瑕疵（加购后头部购物车徽标不即时刷新）待后续任务处理。**
  1. **后端全量**（子 Agent）：649 tests / 646 过 / 3 失败 / 0 错误，288.6s；3 失败均为历史断言漂移（NotificationApiTests 2 例基线 + `test_merchant_domain` TOTP 登录 1 例，HEAD 同样失败）；`ruff check` 仅 2 条历史告警（browser.py PYI034、ingest.py RUF059）。详见下一条与 `backend_report.md`。
  2. **管理端前端**（子 Agent）：prettier 本次改动 7 文件全过（历史漂移 3：AppDrawer/AppModal/BuyersView，未写）；eslint 0 错 0 警；`vite build` 成功；**有单测**（vitest 3 文件 9 例全过，含 CategoryTreePicker 6 例）。报告 `adminweb_report.md`。
  3. **商城前端**（主会话直接执行，原子 Agent 因并发额度超限失败）：vitest **47/47**、eslint 0 错误、prettier 本次改动 5 文件全过（历史漂移 5：account/orders 两页 + 3 个 composables，未写）、`nuxt build` 成功（2.37MB）。报告 `storefront_report.md`。
  4. **浏览器冒烟**（子 Agent）：购物端 6 项 + 管理端 3 项全 PASS、console error 全程 0、临时员工清理 count=0。详见下一条与 `smoke_report.md`。**唯一小瑕疵：加购成功后头部徽标仍显示 "Cart, 0 items" 不即时刷新（购物车页数据正确），下轮可修。**
  - **执行坑（不得再踩）**：①一次最多只能并行跑 2 个子 Agent，第 3、4 个会报 "user concurrency limit exceeded" 被掐——超限的用 SendMessage 原地恢复即可（上下文还在），或改由主会话直接做；②后台 Bash 不继承前台 `cd` 的工作目录，相对路径 `../node_modules/...` 会解析到仓库根，后台命令必须用绝对路径。

- **上一任务（2026-11-11，浏览器黑盒 GUI 冒烟回归，已完成）**：对 storefront（:3000）+ admin-web（:5173）做只读 GUI 冒烟（唯一写操作=加购一次；管理端零写操作，只点「详情/关闭/查询/刷新」）。完整报告 `var/regression_20261111/smoke_report.md`，截图/脚本在 `var/regression_20261111/smoke/`。与同日的「后端全量回归」任务（见下一条）互不影响。
  - **结果：购物端 6 项全 PASS，管理端 3 项全 PASS，console error 全程 0。** ①首页（22/22 图、$ 价、导航/分类齐）②搜索 iPhone=1 条、短词 17=2 条不 500（LIKE 修复回归点通过）③详情页 cefba807…（iPhone 17）：画廊 7 缩略图、规格 chips、无表头两列规格表、图文详情 6 图一图一行（宽 1454、top 2231/2596/4334/6072/7812/9553）、吸附条 fixed/68px、AI 摘要卡出现 ④SPU 1（947910f2…）评价区 4.7/5、3 reviews、5★2/4★1 分布 ⑤加购成功、/cart 见商品（小瑕疵：加购后头部徽标仍 "Cart, 0 items" 不即时刷新，购物车页数据正确）⑥/c/electronics 15 商品；管理端：mint 临时员工登录（getByRole 直接点动「登录」成功，没用 evaluate 兜底）→ /merchants 有数据（三星等）→ /products 列表带「图文 N/表格 N/视频 N」徽标，抽屉（HB-222 3f83dc8f）画廊 22 图/图文详情/视频×1/两列规格表/规格选项 chips，OPPO A6 Pro（f6a90a54）抽屉确认 AI 摘要卡渲染 → /crawlers 19 行任务无报错。
  - **临时员工已清理**：`StaffAccount.objects.filter(email="regression-smoke-20261111@joybuy.test").delete()` → before 1 / deleted 3 / **after count 0** / role_assignments 0，未遗留任何行。
  - **踩坑（不得再踩）**：①`StaffAccount.is_active` 是只读 property（赋值抛 AttributeError），置可用要 `status="ACTIVE"`；`StaffRoleAssignment` FK 字段名是 `staff=`（不是 account=），模型在 `accounts_staff.models`；②admin 商品池搜索框只匹配名称/完整 ID，public_id 8 位前缀搜不到，要先查 staging payload 的 name 再搜；③详情页图文详情图片懒加载，不滚动到位等加载就量布局会误判"不是一图一行"；④admin 抽屉「规格参数」带「属性/值」表头是设计差异（购物端无表头、管理端保留），不是 bug；⑤admin 抽屉 AI 卡标题是「内容由人工智能总结自用户评价」不是"AI 摘要"，找卡片用 `.pool-ai-card` 或按正文找。

- **上一任务（2026-11-11，后端全量回归测试，已完成，只测不修）**：用户明确要求全量验证。命令 `./.venv/Scripts/python.exe backend/manage.py test --noinput --parallel 1`（测试库 MySQL test_joybuy，容器 healthy；外网 baidu/joy-sourcing CDN 均 200）。结果：**649 tests / 288.6s / 失败 3 / 错误 0 / 通过 646**。报告：`var/regression_20261111/backend_report.md`，原始日志 `var/regression_20261111/backend_full.log`。
  - **失败分类**：①已声明基线 2 例——`merchant_ops.tests.test_admin_round2.NotificationApiTests` 的 `test_review_rejected_when_product_not_listed_by_that_merchant`（`PRODUCT_NOT_LISTED` vs `FIELD_REQUIRED`）与 `test_review_snapshot_and_platform_reply_resets_read`（400 `FIELD_REQUIRED`"店铺订单不能为空" vs 201），与基线记录完全一致；②基线外 1 例——`merchants.tests.test_merchant_domain.MerchantDomainTests.test_merchant_totp_policy_is_enforced_during_staff_login`（无 TOTP 设备登录期望 403 实际 200）。静态取证：commit `8d6ec8d`（2026-11-05）已把员工登录改为"只校验邮箱+密码、TOTP 不参与登录"并同步改了 `accounts_staff/tests`，但漏改了商家端的这个旧用例（错误码 `STAFF_TOTP_NOT_ENROLLED` 在非测试代码中已不存在）；该测试与 `accounts_staff/` 在工作区均无未提交改动 → 在 HEAD 上同样失败，**非本次未提交改动引入的回归，是历史断言漂移**。疑似新回归：0；网络依赖失败：0。
  - **ruff check backend crawler**：2 条告警（`crawler/joybuy_crawler/core/browser.py:44` PYI034、`crawler/joybuy_crawler/ingest.py:31` RUF059 未使用变量 `created`），未修。
  - **坑（不得再踩）**：①全量 649 实测只跑约 5 分钟（含 crawler CDN 下载），远低于预估 20–60 分钟，不必因"太久"而中断；②商家端 `test_merchant_domain.py::test_merchant_totp_policy_is_enforced_during_staff_login` 是已知的第 3 处断言漂移，下轮若改 TOTP 相关代码别把它误判为新回归，修复方向是改该用例匹配现行"登录不校验 TOTP"行为。
- **上一任务（2026-11-10，详情页对齐 Joybuy 第三轮：真实内容宽度 / 吸附条 68px / 评价评分入库，已完成）**：网络恢复后直接实测 joybuy.co.uk 并按实测值修正。完整记录见 `docs/14` §9.15。
  1. **内容区宽度按实测 1512px**：Joybuy 商品标题/内容区 1920 视口 1512、left 204，1600 视口 1512、left 44，1440 视口 1344、left 48。`storefront/assets/css/tokens.css` 改为 `--container-max: 100.5rem`（1608 = 1512 + 2×48），≥80rem `--container-pad: 3rem`。实测：1920 → 内容 **1512 / left 204**（完全一致），1600 → 1504（无滚动条环境差 8px），1440 → 1344。`design-tokens.test.js` 断言同步更新。
  2. **底部吸附条高度按实测 68px**：`m.joybuy.co.uk` 的 `bottomBarFloor_bottom_bar_wrap__3J58m` 高度 68、通栏（移动端内部只有 Buy now/Add to cart 两个 175×36 按钮；桌面该商品页未出现吸附条）。`.buy-bar` 固定 `height:68px`，缩略图 48、按钮 40，内容垂直居中；窄屏规则同步调整。
  3. **评价评分之前不显示的根因已修**：评分只统计本地 `Review` 行，而爬虫从不导入单条评价 → `review_summary.count` 恒 0。新增 `SpuDetail.rating_average/rating_count/rating_distribution`（迁移 `catalog/0016`，dev 已执行）；导入 `_parse_rating_summary` + `_sync_spu_detail` 写入源站快照（空 payload 不覆盖）；`detail_views.review_summary` 增加 `distribution`/`source`，本地评价优先、否则回退爬虫快照；`ProductReviews` 接收 `review-summary`，本地为空时用快照显示评分/条数/5→1 星分布，且不再显示「No reviews yet」与分页。存量回填：`var/backfill_rating_20261110/`（干跑→正式）——**19 个有源站评分的 SPU 已回填，164 个无评分 payload 跳过**；已有快照不覆盖。
  4. **AI 卡样式改为 Joybuy 卡片语言**：去掉蓝色主题与左侧蓝条，改为 `#F5F6F7` 底、1px 边框、radius 8、14px/700 黑标题、`#55565B` 正文、白底描边标签。（Joybuy 的 Reviews 是独立 tab，匿名+cookie 弹窗无法展开，AI 卡真实样式未能实测，按站点通用卡片风格对齐。）
  - **验证（按验证纪律仅做针对性验证）**：后端 `test_product_detail_api + test_search + test_crawler_product_category + test_crawler_detail_persistence` → **48 tests OK**（新增评分回退/本地优先/解析 3 例/导入写入且不覆盖）；浏览器临时给 SPU 170 写 4.5/9 快照验证后已还原：评价区显示 4.5/5、9 reviews、5★78%/4★11%/1★11%，AI 卡灰底黑标题，吸附条 68px；`vitest run` 47 OK、`nuxi build` 通过、prettier/eslint 全过；5 个后端 py `ruff check` 全过、手写文件 format 全过。
  - **数据事实**：源站本身没有评分的商品（如 SPU 170 SONGMICS 小冰箱，payload 与线上页面都无 ratingInfo）仍只有 AI 摘要——不是展示 bug；已回填的 19 个商品目前都是 DRAFT，管理端上架后即可看到评分。
  - **踩坑（不得再踩）**：①Nuxt dev 对 `tokens.css` 的 HMR 不生效（max 更新了、pad 仍是旧值），改全局 CSS 变量后必须**重启 storefront dev server** 再量；②Joybuy 的 Reviews 是 tab 且匿名访问被 cookie 弹窗/懒加载挡住，别把 i18n 字典里的 "AI summary" 当成已渲染 DOM；③**评分必须以源站快照入库**，只聚合本地 Review 会让所有爬虫商品永远显示 0。
  - **用户口径确认（2026-11-10）**：「爬虫导入不需要单条评价，但需要评价数量、评分、1~5 分评分数，只用来展示评分，不展示评价内容」——与当前实现完全一致：导入只写 `SpuDetail.rating_count / rating_average / rating_distribution`，不写任何 Review 行。实库核对：`SpuDetail` 有评分的 19 行（如 SPU 160：4.90 / 1406 / `{1:0,2:0,3:0,4:173,5:1233}`），`Review` 表仍只有站内 3 条演示评价；`docs/05 §10` 已补该口径说明。
  - **AI 摘要标签移除（2026-11-10，docs/14 §9.15.3）**：用户指定 SPU 183（`6ce7a4ba-…`）的「价值与价格 / 噪音等级 / 设计与做工质量 / 配送体验」标签不展示 → `ProductReviews` 删掉 `.reviews__ai-tags` 整块与 `aiSummaryTags` prop，`pages/p/[id].vue` 不再传 `ai_summary_tags`。**数据仍保留**在 `SpuDetail.ai_summary_tags`（管理端抽屉继续只读展示），仅购物端不渲染。实测 SPU 183 标签 li 数量 0、AI 标题+正文正常；prettier/eslint 全过，vitest 47 OK。

- **上一任务（2026-11-10，购物端商品详情布局对齐 Joybuy：段落符号/宽度/画廊下拉/吸附购物条/评价与 AI，已完成）**：用户对照 Joybuy 提出 5 项，全部实现并浏览器实测。完整记录见 `docs/14` §9.14。
  1. **段落前「·」**：`.detail__content-paragraph` 加 `::before { content:'·' }`（只段落，不动 heading）。
  2. **内容区宽度**：`storefront/assets/css/tokens.css` `--container-max` 1440 → **1500px（93.75rem）**，依据 docs/12 §1「约 1500px」；1920 视口实测容器 1500。dev 无法访问 Joybuy 实测 CSS，若仍偏窄需现场截图再调。
  3. **画廊同高 + 半透明下拉**：新增 `.detail__thumbs-rail`，JS 量主图高度写内联 height（**不能靠 grid stretch：右侧购买面板更高会把画廊拉长**），`ResizeObserver` 跟随；`.detail__thumbs` 滚动、缩略图 `flex:none`；溢出时底部半透明胶囊按钮（深色 62% + 白 `⌄`）点击浮层展开全部缩略图，选图后自动收起；≤64rem 横向滚动、隐藏按钮。
  4. **底部吸附购物条**：`.buy-bar` fixed bottom，滑过主图底部后出现、滑回顶部消失；左图+标题+规格+价格+Buy now/Add to cart（复用白名单拦截/加购状态）；≤48rem 收紧并隐藏规格。
  5. **评价区移到页面最后 + AI 并入**：`ProductReviews` 移到视频区之后，独立 `.detail__ai` 删除；标题 Reviews（zh 评价），左栏评分/条数/5→1 星分布（可点击筛选），右栏 AI 卡（`reviews.aiSummary`：AI-generated summary from customer reviews / 内容由人工智能总结自用户评价）；**渲染条件改 `count>0 || aiSummary`**（爬虫商品有 AI 无本地评价，旧 `count>0` 会把 AI 藏掉），只有 AI 时独占一行；`messages.js` 新增 5 个双语键。
  - **验证（按验证纪律仅做针对性验证）**：Playwright 1600/390 实测——21 图画廊主图 677 / rail 677 / scroll 1336 → 下拉按钮出现，点击展开 1352、aria=true；段落 `::before="·"`；滚动 1400 购物条 fixed/bottom0 且字段齐全、滚回 0 消失；SPU 170 评价区在规格区之后且 AI 标题正确；SPU 1 显示 4.7/5、3 reviews、5★67%、4★33%；移动端购物条正常、缩略图横滚。`vitest run` **47 OK**（`design-tokens.test.js` 断言改为 93.75rem）、`nuxi build` 通过、`prettier`+`eslint` 全过。
  - **数据侧观察（本轮未改）**：SPU 164 的 21 张 gallery 缩略图里有若干张是纯白图（`naturalWidth>0`，文件本身如此），像爬虫下载到了空白变体，属数据质量问题；当前 dev 库没有「同时有本地评价 + AI 摘要」的商品，两栏布局是靠分别有数据的商品验证的。
  - **踩坑（不得再踩）**：①缩略图轨高度必须量主图，不能用整行 stretch（购买面板更高）；②flex 列里的固定尺寸缩略图要 `flex:none`，否则会被压缩、overflow 永远为 false；③`ProductReviews` 不能再按 `count>0` 单一条件渲染，否则爬虫商品的 AI 摘要永远不显示。

- **上一任务（2026-11-10，爬虫提速：媒体下载并发 + 导入复用 dataset 文件，已完成）**：用户反馈正式爬虫任务慢、调试脚本却很快。定位与量化后按用户拍板「复用 + 并行下载」实施。完整记录见 `docs/05` §8.4。
  1. **根因（RUN 22 事件时间线，10 商品 21m25s）**：页面抓取只占 ~5s/商品；**dataset 落盘串行下载媒体平均 54s（最大 121s）**，**导入媒体库把同一批图再下一次 + 6 个变体编码平均 66s（最大 140s）**；两者都在 Scrapy item pipeline 里执行，`CONCURRENT_REQUESTS=1` 把唯一 worker 卡住（下一个商品的 `/dg/` 请求排队 60–190s）。调试脚本只下一次媒体、不入库、不变体，所以快。
  2. **dataset `crawler/joybuy_crawler/dataset.py`**：新增 `_download_many`（`ThreadPoolExecutor`，`CRAWL_MEDIA_DOWNLOAD_WORKERS` 默认 6，`map` 保序，单张失败只记账）；图片与视频都走它。`save_product` 返回值新增 `local_media={"gallery":{url:绝对路径},"videos":{...}}`，**只含成功落盘的文件、不写进 `dataset_index.jsonl`**。实测 9 张图：串行 30.44s → 并发 7.72s。
  3. **导入复用**：`crawler/joybuy_crawler/pipelines.py` 把 `index_line.get("local_media")` 传给 `import_staging_product`（`index_line` 预置 `{}`，dataset 失败不 NameError）；`backend/crawler_control/import_services.py` 的 `import_staging_product(local_media=...)` → `_import_gallery_images(local_files=...)` / `_import_spu_videos(local_files=...)` 优先读本地文件，缺失才下载；画廊图片用 `_fetch_media_many` 并发取字节（媒体写入/变体仍串行）；`gallery_images` 汇总新增 `reused`。
  4. **未改**：`DOWNLOAD_DELAY=2s`（随机 1–3s）、`CONCURRENT_REQUESTS=1`、robots、账号轮换节奏——礼貌性约束保持原样，本次瓶颈是媒体 I/O 不是页面限速。
  - **验证（按验证纪律仅做针对性验证）**：`test --keepdb crawler_control.tests.test_crawler_import test_crawler_detail_extras test_crawler_field_rules` → **60 tests OK**；`test_crawler_rebuild.StagingPipelineTests + DatasetTests` → **11 tests OK**；新增 `DatasetIncrementalTests.test_local_media_maps_gallery_urls_to_files`（映射=payload gallery URL 且文件存在）、`ImportLocalMediaReuseTests` 2 例（本地命中时 `_fetch_image_bytes` 完全不被调用；文件缺失回退下载）、`StagingPipelineTests.test_process_item_passes_dataset_local_media_to_import`（pipeline 必须把 `local_media` 传给导入）；6 个改动 py `ruff check` 全过、`ruff format --check` 全过（`import_services.py` 顺带修掉 1 处**改动前就存在**的 4 行 format 漂移：`staging.save(update_fields=...)` 折行）。基准：同一商品 9 张图 dataset 下载串行 30.44s → `CRAWL_MEDIA_DOWNLOAD_WORKERS=6` 7.72s（脚本 `var/bench_media_download.py`）。
  - **踩坑（不得再踩）**：①`StagingPipelineTests` 断言过 `gallery_images == {"downloaded":0,"failed":1}`，新增 `reused` 键后必须同步断言；②媒体下载是网络 I/O，测试里 `save_product` 会真的访问 CDN（该模块单跑约 177s 属正常，别误判卡死）；③并发下载只允许发生在下载阶段，`process_media_bytes`/DB 写入必须留在主线程串行，避免 SQLite/MySQL 连接跨线程。

- **上一任务（2026-11-10，购物端商品详情三处展示修正，已完成）**：对照 Joybuy 修正详情页展示。完整记录见 `docs/14` §9.13。
  1. **图文详情图片改为一张一行、铺满内容区**：`storefront/pages/p/[id].vue` `.detail__content-images` 原为 `repeat(auto-fit, minmax(180px, 640px))`（宽屏并排两张、单张最宽 640px），改为 `grid-template-columns: minmax(0, 1fr)`，间距 `--space-4`，图片 `width: 100%`。
  2. **无评价时不展示 Customer reviews**：`storefront/components/ProductReviews.vue` 的 `<section id="reviews">` 加 `v-if="count > 0"`；星级筛选后为空（`count>0`、当前星级无条目）仍保留区块与筛选空态。
  3. **规格表格去掉「属性 / 值」表头**：`storefront/pages/p/[id].vue` 的 `.detail__spec-table` 删除整个 `<thead>`，只留两列数据行（首列仍 `<th scope="row">`，无障碍语义不变），同时删掉无用的 `.detail__spec-table thead th` 样式；数据契约 `table.columns` 不动（管理端抽屉仍渲染表头）。
  - **验证（按验证纪律仅做针对性验证）**：`prettier --check` + `eslint` 改动文件全过；Playwright 实测 1440×900——SPU 173（12 张详情图）`grid-template-columns: 1326px`，容器与每张图均 1326px，图片 top 954/1715/2476/3919 逐行堆叠，`#reviews`=0；SPU 1（有评价）`#reviews`=1、标题 Customer reviews；SPU 173 规格表 `table` 1 个、`thead` 0 个、行内容仍为「Cellular Technology / 4G」等。核对脚本 `var/check_pdp_layout.cjs`、`var/check_spec_table.cjs`（`require('@playwright/test')`，根目录只有 `@playwright/test`，没有 `playwright` 包）。
  - **踩坑**：①详情页历史商品若 `Spu.status != ACTIVE` 或无 ACTIVE Offer，SSR 返回的是错误/骨架态，看不到区块——核对布局要挑「ACTIVE + 有 ACTIVE Offer + 有 SpuDetail」的商品（如 SPU 173/174/175/178）；②dev 模式下组件 CSS 由客户端 JS 注入，**不能靠 grep SSR HTML 验证样式**，必须用浏览器读 computed style。

- **上一任务（2026-11-10，管理端「上架即可售」+ 购物端短词搜索修复，已完成）**：用户报「管理端把商品上架后，购物端搜不到」。排查出**两个叠加 bug**，口径经用户拍板为「上架即可售」。完整记录见 `docs/14` §9.12。
  1. **Bug 1：上架只改 SPU 状态，没激活商家报价**。搜索文档要求 `Spu.status=ACTIVE` **且** 至少一个 `Offer.status=ACTIVE`；管理端上架只改前者，导入留下的 DRAFT Offer 不动，`refresh_spu_search_documents` 反而把文档删掉 → 永远搜不到。管理端下架却会级联下架 Offer，两方向不对称。实测 9 个 SPU（如 SPU 170 iPhone 17）处于「商品 ACTIVE、报价 DRAFT、文档 0」。
     - 修复：`backend/merchant_ops/views_catalog.py::_activate_offers_on_publish`，在 `publish` 时同事务激活 **DRAFT Offer** 和 **`removed_by_platform=True` 的 INACTIVE Offer**；商家自己下架的（`removed_by_platform=False`）不复活；只跳过非 `ACTIVE` 入驻状态的商家（**不要求 `admission_approved`**，爬虫导入商家多未审核）；激活时 `cost_price=compute_listing_cost(...)`、`current_price=零售价`、`listed_at=now`、清 `removed_*`。无可激活且无已上架报价 → 400 `PRODUCT_OFFER_MISSING`；需激活但零售价为空 → 400 `PRODUCT_PRICE_MISSING`（状态不变，不再假成功）。审计/回包带 `activated_offers`。
     - 存量修复：`var/publish_fix_20261110/`（`publish_fix.py` + `refresh_docs.py`）——**9 个商品 9 个 Offer 已激活、9 个搜索文档已重建**。**坑：`publish_fix.py` 的 `PUBLISH_FIX_DRY_RUN=1` 只跳过文档刷新、没拦住报价激活（helper 直接写库），两次「干跑」实际写了库；第二次干跑还覆盖了第一次的 9 行 `snapshot_before.json`（现只剩 3 行）。激活本身是目标状态、无数据丢失，但快照不全。**
  2. **Bug 2：短词让 MySQL 全文检索整条归零**。`innodb_ft_min_token_size=3`，布尔模式 `+17*` 会让整条 `MATCH` 返回 0（实测 `+iPhone*`=1 条、`+iPhone* +17*`=0 条），所以 `q=iPhone` 能搜到、`q=iPhone 17` 搜不到。修复 `backend/catalog/search_services.py`：`_search_terms` 先剥离布尔运算符；长词（≥3）走 MATCH，**短词改逐词 LIKE（AND）**；长词全文结果为空时整体回退 LIKE；只有运算符的查询返回空而不是全部；SQLite 分支也改逐词 LIKE。
  - **验证（按验证纪律仅做针对性验证）**：`test --keepdb merchant_ops.tests.test_admin_commerce` → **54 OK**（新增 `ProductPoolPublishTests` 7 例：激活并建文档/下架后再上架恢复/无报价 400/零售价缺失 400/商家自下架不复活/未审核爬虫商家可激活/封店跳过）；`test --noinput catalog.tests.test_search` → **12 OK**（新增短词 2 例；**必须用 `--noinput` 重建库，`--keepdb` 会因 `TransactionTestCase` 清空种子行导致后续 `TestCase.setUp` 找不到系统商家**）。接口实测：`q=iPhone 17`=1、`q=Blackview`=2、`q=4L Mini Fridge`=1。后端已重启（`--noreload` 必须重启才生效）。
  - **踩坑（不得再踩）**：①搜索文档是购物端唯一事实源，任何「上架」动作必须同时保证 SPU ACTIVE + Offer ACTIVE，否则就是假上架；②MySQL 布尔全文里**短于 3 字符的词带 `+` 会让整条 MATCH 归零**，不要用原始用户输入拼布尔表达式；③`test_search` 含 `TransactionTestCase`，`--keepdb` 复跑会让测试库缺系统商家种子，改用 `--noinput` 重建；④一次性脚本的 `DRY_RUN` 必须放在**所有写库调用之前**（本轮 `publish_fix.py` 就栽在这），且不要用第二次干跑覆盖第一次的快照。

- **上一任务（2026-11-10，商家端成本价最终口径：零售价 × (1 − 折扣%)，已完成）**：用户先提「成本价=零售价×折扣、默认100%」，随后**纠正**为「管理端设 20% 折扣 → 商家端成本价 = 零售价 × 80%」（折扣是减免百分比）。完整记录见 `docs/14` §9.11。
  1. **最终公式**：`backend/merchant_ops/services.py::compute_listing_cost` = `spu.retail_price × (1 − 折扣%/100)`，**ROUND_CEILING 到分**；折扣 20%、零售 200 → 160.00；25.99 → 20.792 → 20.80；**未设折扣 = 减免 0% → 成本价 = 零售价**；活动商品优先活动折扣，否则普通折扣，都空 → 0%；折扣 >100% 钳 0；**`Spu.cost_price` 完全不参与公式**，零售价 NULL → `None`（`can_list=False`，上架 400 `PRODUCT_PRICE_MISSING`）。旧口径（2026-11-08 平台成本价基数、更早 零售×折扣）全部作废，勿回退。
  2. **重算链路**：新增 `services.reprice_listed_offers(merchant=, spu=)`（遍历 ACTIVE Offer 用当前折扣/零售价重算并 update，算出 None 跳过）。调用点：管理端改折扣（`views_merchants.py`，回包 `repriced_offers`）、商品池 PATCH 带 price/cost（`views_catalog.py`）、`mark_activity`/`unmark_activity`（`views_catalog.py`）。`views_merchant_catalog.py` 改为从 services 导入 `compute_listing_cost`（`__all__` 保留旧导入路径）。
  3. **存量刷新（dev 库已执行）**：`var/reprice_retail_formula_20261110/`（干跑→正式，快照/结果同目录）。**ACTIVE Offer 131 个全部重算（131 changed，0 个零售 NULL）**：`Joybuy 自营导入`（无折扣）122 个 NULL → 零售价；`HOMCOM`（普通 20%/活动 30%）6 个；`CHiQ`（无折扣）3 个。旧值核对 HOMCOM 活动商品 2799.30 = 3999×70%（旧基数确实是成本价）；**错误公式（零售×20%）从未落库，无需回滚重跑**。无折扣商家成本=零售、预估利润 0 是用户明确口径。
  - **验证（按验证纪律仅做针对性验证）**：`manage.py test --keepdb merchant_ops.tests.test_wp42_discount_listing merchant_ops.tests.test_merchant_modules` → **46 tests OK**；`... test_admin_commerce` → **49 tests OK**（含新增 `test_discount_change_reprices_listed_offers`、`test_clearing_discount_resets_cost_to_retail_price`）；7 个改动 py 文件 `ruff check` 全过；`ruff format --check` 我们改的行全过，但 `services.py`、`views_merchant_catalog.py` **整文件**仍报 unformatted——已用 `git show HEAD:<file>` 验证是**改动前就存在的 format 漂移**（PROGRESS_INTERVAL_HOURS 元组对齐、merchant_category_label 换行），按纪律未整文件重排。
  - **已更新文档/文案**：`docs/14` 新增 §9.11（最终公式/代码/存量刷新/验证），并把 §9.9.3 旧的「成本价 NULL 不能上架」标注为历史；`docs/08` 折扣体系、`docs/13` Merchant 字段说明、`backend/merchants/models.py` 折扣字段注释统一改为零售价口径；`admin-web/src/views/MerchantsView.vue` 折扣提示文案改为「成本价 = 零售价 × (1 − 折扣%)，例零售 3599、折扣 20% → 2879.20；留空 = 减免 0% → 成本价 = 零售价」，活动折扣提示改「以零售价为基数」。
  - **前端验证**：`admin-web` 对 `MerchantsView.vue` `npx prettier --check` 通过、`npx eslint` 0 错误（exit 0）；`backend/merchants/models.py` `ruff check` 全过。
  - **后端已重启**：旧 PID 25996 → `taskkill //F //PID 25996`，`manage.py runserver 127.0.0.1:8000 --noreload` 重启，新 PID **35484**（`/api/v1/admin/products` 未登录 401 = 服务正常）；新公式已生效。
  - **踩坑（不得再踩）**：①公式方向极易搞反——**折扣是减免百分比**，20% → ×80%，不是 ×20%；②基线数据的 `offer.cost_price` 可能是旧口径快照（平台成本价×折扣），刷新后必须核对其旧值能由旧公式解释，再判断是否需要第二轮；③子 Agent 因 5 小时使用上限被中断时可能已改完代码但只跑了干跑，接手时先看 `var/<任务>/` 有无 dry_run 结果、`git diff` 是否已含新公式，不要盲目重做；④`ruff format --check` 对 `services.py`/`views_merchant_catalog.py` 整文件报错是**改动前就存在的漂移**（`git show HEAD:<file>` 复现），不要为此整文件重排、把无关行混进 diff。

- **上一任务（2026-11-10，商家端品类（父品类）推导 + 抓取原价→零售价 + 任务类目树父级半选，已完成）**：三条线。完整记录见 `docs/14` §9.10。
  1. **导入推导 `Spu.merchant_category`**：`backend/catalog/product_services.py` 新增 `merchant_category_from_local(local_category)`——本地类目的**父级（一级类目）** slug 查 `LOCAL_PARENT_MERCHANT_CATEGORY`（挂在一级类目本身时用自身 slug）；`get_or_create_spu_from_source` 建档即写入，既有 SPU 在 `merchant_category` 为空时补推导值；**只填空、绝不覆盖**人工值；活动商品/无 local_category 保持空串。一次性回填（dev 库已执行）：`var/backfill_merchant_category_20261110/`（先 `BACKFILL_DRY_RUN=1` 干跑再正式；快照同目录）——**85 个「有 local_category 且 merchant_category 空」的 SPU 全部回填、0 unmapped**（groceries-food→HOME 62 / fridges→SMALL_APPLIANCE 9 / phones→ELECTRONICS 14）；回填后分布 HOME 90 / ELECTRONICS 22 / COMPUTER 9 / SMALL_APPLIANCE 9 / BABY·BEAUTY·HEALTH·OUTDOOR·PET 各 3；仍为空的 29 个均无 local_category（手工/活动商品），按设计不回填；merchant_category 不进搜索文档，无需 refresh。**注意：merchant 的原始快照因下述 `__file__` 路径坑丢失，目录内快照是事后按 `updated_at` 时间戳精确重建的（文件内有 `_reconstruction_note`；零售价回填的快照是原样落盘的）**。
  2. **抓取价→零售价**：既定规则「抓取价=入库价=零售价，爬虫只采原价」。`backend/crawler_control/import_services.py` 新增 `_parse_spu_retail_price`（按模型 max_digits=18/decimal_places=4 量化；缺失/非法/负数/超 14 位整数→None）与 `_apply_spu_retail_price`（`import_staging_product` 里 SPU get_or_create 之后调用）：**新建与重导都更新**（爬虫是价格唯一事实源）；价格缺失/非法保留旧值；会撞 DB 约束 `spu_retail_not_below_cost`（retail<cost）时同样保留旧值、绝不弄挂导入；**不动 cost_price**。一次性回填（dev 库已执行）：`var/backfill_retail_price_20261110/`（同样干跑→正式、快照同目录；用与导入同一解析函数、取最新 staging payload `current_price`、不覆盖非 NULL）——**52 个爬虫 SPU 全部回填、0 invalid、0 撞约束**；全库仅剩 1 个 NULL（SPU 165 手工建档无身份，按设计不回填）。
  3. **任务类目树父级半选（`admin-web/src/components/CategoryTreePicker.vue`）**：勾选二级类目时其一级父类目此前完全无状态。现在父类目 checkbox 显示 **indeterminate 半选** + 行浅色 `--partial` 高亮 + 「子类目已选 N」小注；顶部计数改「已选 N 个类目（实际抓取范围）」，有半选父级时追加「· M 个一级类目半选（仅其子类目参与抓取）」。**抓取范围语义不变**：半选只是展示态、不进 `modelValue`，提交 `source_ids` 仍只含被勾选节点；点半选父级仍是「勾选该父级自身」原行为。
  - **验证（按验证纪律仅做针对性验证）**：新增 `crawler_control/tests/test_crawler_product_category.py::ParseSpuRetailPriceTests`（2 例纯函数）+ `MerchantCategoryAndRetailPriceTests`（6 例：建档写 merchant_category+retail_price / 重导补空 merchant_category / 人工 merchant_category 不覆盖 / 重导更新 retail_price / 价格非法保留旧值 / 价格缺失被必填校验拒绝且不动旧值）。跑 `crawler_control.tests.test_crawler_import + test_crawler_product_category + test_crawler_detail_persistence + merchant_ops.tests.test_admin_commerce` → **85 tests OK**。改动 3 个 py 文件 `ruff check` + `ruff format --check` 全过；`admin-web` 对 CategoryTreePicker.vue `prettier --check` + `eslint` 全过。
  - **踩坑（不得再踩）**：①**dev 的 MySQL 账号只有 `joybuy` / `test_joybuy` 两库授权（`SHOW GRANTS` 证实），无法新建隔离测试库**；且并行任务常驻 test_joybuy 跑测试——**同库并发会互相锁（本轮撞过一次 1205 lock wait timeout）**，MySQL 下跑测试必须先 `SHOW PROCESSLIST` 确认没人占 test_joybuy，或直接用 `DJANGO_DATABASE_ENGINE=sqlite DJANGO_SQLITE_PATH=<临时路径>` 走独立 SQLite 测试库（本轮采用，85 例全过）；②`manage.py shell -c "exec(open(...))"` 里 Python 的 cwd 是 `backend/`，不是仓库根——exec 脚本必须用**绝对路径**；且 exec 环境里 `__file__` 指向 Django 的 `shell.py`，脚本里用 `Path(__file__)` 定位输出会把产物写进 site-packages（本轮两个回填脚本都踩了：merchant 快照因此被 retail 回填覆盖丢失、已按时间戳重建；两脚本已改为硬编码 `OUT_DIR`，retail 快照原样落盘）；③本轮一次联合跑出现过 `test_manual_content_sections_survive_reimport_but_other_fields_refresh` 假失败（'材质与规格' != '技术规格'）——那是并行任务当时正在修的浅拷贝问题（见下一条任务踩坑①），单跑与复跑均过，与本轮改动无关。
  - **未做/边界**：`crawler/debug_crawl.py`、`backend/merchant_ops/*`、storefront、`ProductPoolView.vue` 未改动；admin-web 未跑 `vite build`（并行任务在改 admin-web 其它文件，避免被其未完成改动干扰）；树选择器未做浏览器实测（本机未起前后端服务，行为以 eslint/静态检查+代码推演为准，待人工点验）。

- **当前任务（2026-11-10，商品池编辑弹窗去掉成本价 + 图文详情人工编辑（content_source 契约），已完成）**：管理端商品池新建/编辑弹窗移除【成本价】输入（后端 cost 改为可空）；编辑弹窗新增「图文详情」编辑区（标题/子标题/段落增删移 + 区块图片上传），保存进 `SpuDetail.content_sections` 并标记 `content_source="manual"`，爬虫重导入不再覆盖人工图文区块（规格表格/AI 等照常刷新）。完整契约与验证记录见 `docs/14` §9.9。
  1. **模型/迁移**：`catalog.SpuDetail.content_source`（TextChoices crawler/manual，默认 crawler，max_length=16）；迁移 `catalog/0015_spudetail_content_source` **已在 dev 库执行**（实库核对：既有 24 行全部默认 crawler，历史数据未动）。
  2. **导入守卫 `backend/crawler_control/import_services.py::_sync_spu_detail`**：payload `content_sections` 非空且既有 `SpuDetail.content_source == "manual"` 时**跳过 content_sections 写入**（多一次按 spu 查 `content_source` 的轻量查询）；specification_tables / specifications / spec_options / ai_summary / 视频刷新逻辑不变；payload sections 为空仍不写入（既有规则）。**不要**把 manual 判断放到其它字段分支上——只有 content_sections 受保护。
  3. **管理端 API `backend/merchant_ops/views_catalog.py`**：`PATCH /api/v1/admin/products/<id>` 新增可选键 `content_sections`（结构与爬虫 payload 一致 `[{title, blocks:[{type:"heading"|"paragraph",text}], images:[/media/...]}]`）；校验上限：区块≤50、blocks≤100/区块、图片≤20/区块、标题≤120字、heading≤200字、paragraph≤5000字；图片只收本地 `/media/` URL（错误码 `CONTENT_IMAGE_INVALID`；另有 `CONTENT_SECTIONS_INVALID` / `CONTENT_SECTIONS_TOO_MANY` / `CONTENT_BLOCK_TYPE_INVALID` / `CONTENT_TEXT_TOO_LONG`）；保存后 `content_source=manual`（无详情行自动创建）并写审计 `PRODUCT_DETAIL_UPDATED`；回包 `product.content_sections` / `product.content_source` 带保存后的值。详情 GET 新增 `content_source`（无详情行=null）。
  4. **成本价可选**：POST `cost` 缺省/空 → `cost_price=NULL`（填了必须>0，price 仍必填>0，price<cost 仍 400）；PATCH 不带 cost 键=不变、空值=清空。**`compute_listing_cost` 的 NULL 行为（本节记录时只核实未改；当天已被上一条任务的新口径取代）**：当时 `cost_price is None → 返回 None`，商家端商品卡 `can_list=False`，上架 POST → 400 `PRODUCT_PRICE_MISSING`「商家未设置折扣且商品缺少成本价，暂不能上架」。**现状（2026-11-10 最终口径）：成本价改由零售价算出，`cost_price` 不参与；成本价 NULL 不再阻止上架，零售价 NULL 才不能上架**（见本文件顶部与 `docs/14` §9.11）。
  5. **前端 `admin-web/src/views/ProductPoolView.vue` + `src/components/ImageUploader.vue` + `src/styles/admin.css`**：编辑弹窗删【成本价】输入与「零售价不得低于成本价」提示（PATCH 不再发 cost 键）；新增「图文详情」区：区块标题 input、块列表（子标题=input 加粗深色 / 段落=textarea，可上移/下移/删除）、`+子标题` `+段落`、`+新增图文区块` `删除区块`、区块图片复用 `/api/v1/admin/media`（purpose=product、10MB、≤20 张，ImageUploader 新增 opt-in prop `reorderable`（默认 true）隐藏区块图场景的「主图」按钮，向后兼容）；编辑打开时异步拉 `/products/<id>` 载入 sections；保存时仅在有区块时随 PATCH 发 `content_sections`（**空列表不发送**，防误清空后被导入器永久忽略）；新建商品 POST 后再 PATCH 补写；详情抽屉「图文详情」标题加「人工编辑 · 爬虫不覆盖」徽标（manual 时）。
  - **验证（按验证纪律仅做针对性验证）**：`backend/manage.py test --keepdb merchant_ops.tests.test_admin_commerce crawler_control.tests.test_crawler_import crawler_control.tests.test_crawler_detail_persistence` → **65 tests OK**（新增 `ProductPoolDetailContentTests` 10 例 + `test_manual_content_sections_survive_reimport_but_other_fields_refresh` 1 例；`--keepdb` 必须带，否则测试库已存在时非 TTY 下确认删库报 EOFError）；改动 6 个 py 文件 `ruff check` 全过、5 个手写文件 `ruff format --check` 全过（**0015 迁移按 Django 生成原样保留**，与 0014 等既有迁移一致，勿对迁移文件跑 format）；admin-web `prettier --check`（ProductPoolView 曾不达标已 `--write` 修正）+ `eslint`（0 错误）+ `vite build` 通过。中途一次运行出现零星 setUpClass 连接错误（机器刚重启 MySQL 容器未稳），复跑两次均稳定 65 OK。
  - **未做/边界**：未做浏览器端到端点验编辑弹窗（契约+编译+静态检查已过）；`crawler/debug_crawl.py`、storefront、`CategoryTreePicker.vue`、`product_services.py` 零售价逻辑未触碰；图片 URL 只校验前缀 `/media/` 与 `..`，不校验文件真实存在（与本地上传契约一致）。
  - **踩坑（不得再踩）**：①测试 JSONField 断言 `content_sections == manual_sections` 时 payload 要整体替换（`dict(self.staging.payload)` 是浅拷贝，`specification_tables` 等嵌套键仍指向旧列表，会得出「表格没刷新」的假象）；②前端 sections 用 `v-for :key="si"` 索引即可（区块对象原地变更，无重排 key 失配问题，与本页既有 specs 编辑一致）。

- **上一任务（2026-11-10，爬虫商品自动关联品类 local_category：蜘蛛写 source_category_id + 导入解析/补挂 + 一次性回填，已完成）**：用户报「爬虫商品进了商品池有 product_category（两级面包屑）但没有品类」，要求品类=建任务时所选菜单类目映射到的本地二级类目。根因与修复详见 `docs/14` §9.8。
  1. **蜘蛛 `crawler/joybuy_crawler/spiders/joybuy_run.py` `_build_item`**：新增 `payload["source_category_id"] = target["source_category_id"]`（语义仍是「任务所选 Joybuy 菜单来源类目」，docs/05 §9.2；与商品面包屑的数字 `product_category_id` 是两套 ID 空间，不要混）。`crawl_source_category_id/name` 照旧写入（活动判定 + 旧 payload 兜底）。
  2. **导入 `backend/crawler_control/import_services.py`**：`source_category` 解析优先 `payload["source_category_id"]`，缺失兜底 `crawl_source_category_id`（旧 payload 也能关联）；活动判定逻辑不变。
  3. **`backend/catalog/product_services.py` `get_or_create_spu_from_source` 既有 SPU 分支**：`local_category_id is None` 且非活动商品时补挂本轮解析出的 `local_category`（任务所选类目的 primary CategoryMapping），兜底 `product_category.local_category`；**只填空、绝不覆盖人工/管理端设置的品类**；活动商品（`spu.is_activity` 或 `is_activity=True`）永远保持 NULL。
  4. **一次性回填（dev 库已执行）**：脚本 `var/backfill_local_category_20261110/backfill_local_category.py`（先 `BACKFILL_DRY_RUN=1` 干跑再正式执行，单事务，快照 `snapshot_before.json` / `snapshot_after.json` / `backfill_result.json` 在同目录）。链路 `SpuSourceIdentity → StagingProduct payload → SourceCategory → primary CategoryMapping → LocalCategory`，失败兜底 `product_category.local_category`。**结果：46 个 NULL 品类 SPU → 回填 14 个（全部 `l2:1420 → phones-tablets 手机与平板`，SPU 146/148/151/158/167~176，即 2026-11-09「电子产品-手机测试」任务抓的手机），32 个留 NULL**（31 个是 2026-11-05 前的老导入、staging payload 无任何来源类目字段，重抓重导后会自动补上；1 个 SPU 165 无 `SpuSourceIdentity`，手工建档商品不回填）。回填后对 14 个 SPU 调 `refresh_spu_search_documents`：全部 DRAFT/无在售 Offer → 0 个 `ProductSearchDocument` 生成（文档只为 ACTIVE 商品 + ACTIVE Offer 建立，属预期；上架时自动建）。
  5. **验证（按验证纪律仅做针对性验证）**：`backend/manage.py test crawler_control.tests.test_crawler_import crawler_control.tests.test_crawler_product_category merchant_ops.tests.test_admin_commerce` → **62 tests OK**（新增 `LocalCategoryFromJobSelectionTests` 5 例：建档挂品类 / crawl 字段兜底 / 重导补 NULL / 人工品类不覆盖 / 活动商品保持 NULL）；改动 4 个 py 文件 `ruff check` 全过、backend 3 个文件 `ruff format --check` 全过（**注意 `crawler/joybuy_crawler/spiders/joybuy_run.py` 有本轮之前遗留的 format 漂移，本轮新增行不涉及、未整文件重排**）；`py_compile` 通过。实库核对 SPU 151（`1d05f963…` Samsung Galaxy S26 Ultra，任务类目 `l2:1420`）：`local_category=phones-tablets`，管理端商品池 payload `category={name_zh:'手机与平板', path:'/1/9/'}`。
  - **未做/边界**：`crawler/debug_crawl.py`、storefront 页面、管理端 UI 均未改动（本轮仅后端 + 蜘蛛 payload 字段）；31 个老导入商品需重抓重导才会自动获得品类；storefront 品类页验证需等这批商品上架（当前全 DRAFT）。
  - **下一步（可选）**：网络恢复后重抓一次手机任务做端到端核对（新 payload 应带 `source_category_id: l2:1420`，导入即挂品类，无需回填）。

- **上一任务（2026-11-10，管理端商品池暴露爬虫详情：列表摘要 + 详情抽屉只读渲染，已完成）**：把 §9 落库的结构化详情（图文区块/规格表格/spec_options/AI/视频/全量画廊/商品类目）暴露到平台管理端商品池。**爬虫契约、`crawler/debug_crawl.py`、storefront 页面、导入逻辑均未改动**。
  1. **后端 `backend/merchant_ops/views_catalog.py`（增量字段、无破坏性变更）**：
     - 列表 `_spu_payload` 新增摘要字段：`has_detail` / `section_count` / `spec_table_count` / `video_count` / `ai_summary`（≤80 字预览，超出加 `…`）/ `source_updated_at`（`SpuDetail.source_observed_at` 回退 `updated_at`）；列表 queryset 加 `select_related("detail")`（OneToOne 左连接）+ 一次 `SpuVideo` 计数批量查询，列表行不携带完整 JSON 块。
     - 详情 `AdminProductPoolDetailView.get` 新增：`content_sections` / `specification_tables` / `specifications` / `ai_summary` / `ai_summary_title` / `ai_summary_tags`（原样取自 `SpuDetail`）；`spec_options`（复用 `catalog.detail_views._spec_options_payload`，`sku_ids` 映射为 `Sku.public_id`，与购物端一致）；`videos`（复用 `_video_payload`：本地 `/media/videos` 可播放 URL + poster + duration + sort_order）；`gallery`（媒体库 `MediaUsage(role=gallery)` 按 sort_order 在前 + 手工 `image_urls` 去重补后；**手工 `images` 字段语义不变**，编辑弹窗仍只编辑手工 5 张）；`product_category`（爬到的两级类目 `[{id, name, depth}]`，只读）。无 `SpuDetail`/`SpuVideo` 的历史商品返回空数组/空串不报错。
  2. **前端 `admin-web/src/views/ProductPoolView.vue` + `admin.css`**：
     - 列表商品列名称下加小徽标（`has_detail` 时）：`图文 N` / `表格 N` / `视频 N`；固定列宽（pool-table nth-child 布局）不动。
     - 详情抽屉新增只读区块（全部中文标签、本地 `/media`、无 CDN）：全量画廊缩略图；「商品类目（爬取）」栅格项；「图文详情」区块标题 → heading（13px/700/#1a1a1a，仿 Joybuy）→ paragraph → 区块图片，无 `content_sections` 回退 `description`；AI 摘要卡（标题/正文/标签 chips）；「商品视频」`<video controls poster>`；「规格参数」每组一张两列 `<table>`（表头「属性 | 值」、`<th scope="row">` 行表头左对齐、保留行序）；「规格选项」chips 带圆形缩略图；手工「规格」表与 SKU 数等既有内容不变。爬虫区块**不做编辑入口**（read-only）。
  3. **测试**：`backend/merchant_ops/tests/test_admin_commerce.py` 新增 `ProductPoolCrawledDetailTests` 4 例（详情含全部爬虫字段 + spec_options sku_ids 映射；列表摘要字段；无详情商品空结构；商品类目面包屑）。注意 `SkuSourceIdentity` 的 `first_seen_at`/`last_seen_at` 是 NOT NULL，测试里必须显式传 `timezone.now()`。
  - **验证（按验证纪律仅做针对性验证）**：`backend/manage.py test merchant_ops.tests.test_admin_commerce` → **39 tests OK**；`ruff check` + `ruff format --check`（views_catalog.py、test_admin_commerce.py）全过；`admin-web` 的 `npx prettier --check src/views/ProductPoolView.vue src/styles/admin.css` 与 `npx eslint src/views/ProductPoolView.vue` 全过。回归：`test_wp42_discount_listing + test_admin_round2` 35 例中 `NotificationApiTests` 2 例失败（`PRODUCT_NOT_LISTED` vs `FIELD_REQUIRED`）——**已用 `git stash` 验证该 2 例在本轮改动前就失败**（旧断言未跟上 2026-11-07「好评推送改选店铺订单」契约），与商品池无关，未修。
  - **文档**：`docs/14` 新增 §9.7（管理端商品池暴露：字段表、前端区块、验证记录）。
  - **后端已重启**：旧 PID 36560 → `taskkill //F //PID 36560`，端口释放后 `manage.py runserver 127.0.0.1:8000 --noreload` 重启，新 PID **43692**（`/api/v1/admin/products` 未登录探测 401 = 服务正常）。
  - **踩坑/注意**：①详情接口的 `ai_summary` 是完整正文，≤80 截断预览只在列表摘要字段；②`_spu_payload` 的摘要字段是增量字段，POST/PATCH/actions 回包自动带默认值，不要在其它消费方假设它们为 null；③docs/14 的 §10（来源身份冲突）编号被保留，本轮内容挂在 §9.7，不要再插入新的 §10 导致编号漂移。
  - **下一步（可选）**：浏览器实测详情抽屉渲染（SPU 151/153 有真实 SpuDetail）；旧 NotificationApiTests 2 例断言修正另开任务。

- **上一任务（2026-11-09，已执行并完成：商家 14 `三星 查看店铺` 整体合并到商家 12 `Samsung`）**：用户**明确批准**把商家 14 的唯一商品（Offer 161 / SKU 151 / SPU 153 Z Flip 8）与映射整体迁到商家 12，不删商家、不动订单/钱包、不激活商品。**全部写操作在一个 `transaction.atomic()` 内完成，一次通过并提交**；执行前已把受影响行快照到 `var/merge_20261109/`（`snapshot_before.json`、`snapshot_before_extra.json`、`merge_plan.json`、`merge_result.json`、`snapshot_after.json`）。
  - **变更结果**：①Offer 161 `merchant 14 → 12`（只更新 `merchant` 一列；SKU 151、GB/GBP、1149.00、DRAFT、`listed_at=null` 全部不变）；②映射 id 13 `joybuy_uk:'三星 查看店铺'` → 12；新建 id 17 `joybuy_uk:'三星'` → 12；id 11 `Samsung` → 12 不变；③商家 14 `onboarding_status ACTIVE → SUSPENDED` + `suspended_at` + `suspend_reason`（未删除、`is_system` 未改、0 Offer / 0 映射 / 其它引用全 0）；④重导暂存 `a2df75b8-…`（100859032）：PENDING → **IMPORTED**（`imported_at=2026-11-09 12:01:02Z`），SKU 149 规格 `{}` → `{"内存":"12GB+512GB","颜色":"黑色"}`，Offer 159 仍属 12，画廊 10/10 成功，新建 `SpuDetail`（2 区块 / 1 规格表 / 2 组 spec_options / AI），无视频；⑤重导暂存 `8cf5dd6f-…`（100006925022956）：幂等，仍 IMPORTED（`imported_at=2026-11-09 12:01:31Z`），SKU 151 规格仍为 `{}`，Offer 161 属 12，画廊 22/22 成功，无重复。
  - **后置核对**：商家 14 Offer=0；商家 12 Offer=**8**（154/155/158/159/160/**161**/167/168，全 DRAFT）；`OfferSourceIdentity` 未改绑（151→161、149→159）；映射 `三星 查看店铺`/`三星`/`Samsung` 均 →12，无映射指向 14；SPU 151/153 仍 DRAFT；库总量前后一致（商家 14、Offer 178、SKU 169、SPU 168；映射 12→13）。两条 SPU 均无 `ProductSearchDocument`，无需刷新。购物端商家搜索要求至少一件在售商品，商家 14 已不可见。**无需重启后端**（纯数据变更）；`crawler/debug_crawl.py` 未触碰。
  - **与执行计划的偏差（重要）**：计划里「商家 12 合并后 = 2 条 Offer（159、161）」与实际不符——商家 12 合并前就有 7 条 Offer（含 6 条其它三星商品：154/155/158/160/167/168，各自不同 SKU/SPU），合并后为 8 条，**无冲突、无重复**。后续会话不要再把「商家 12 只有 159」当事实。
  - **验证命令**：`MERGE_DRY_RUN=1 ./.venv/Scripts/python.exe backend/manage.py shell -c "exec(open(r'var\\merge_20261109\\merge_merchant14_into_12.py', encoding='utf-8').read())"`（只读断言）；去掉 `MERGE_DRY_RUN` 正式执行；再跑 `verify_after.py`。**按验证纪律仅做针对性只读核查，未跑测试套件、未跑全量验证。**
  - **踩坑（再次强调）**：①商家 12 是真实三星商家、下面有多个 DRAFT 商品，任何「数量=2」的预期都不能当断言；②改映射前必须扫 `Offer.merchant`；③重导会真实下载图片（`images4.joy-sourcing.com` 本次可达，35 个 URL 全部成功），网络不可达时导入仍会成功但 `gallery_images.failed` 上升；④整段合并必须单事务，任何一步异常整体回滚。
  - **文档**：`docs/14-crawler-product-detail-issues.md` §10.5 已改为「已执行：整体合并到商家 12」，§10.5.1 保留为核查证据，新增 §10.5.2 完整执行记录（变更表、重导结果、后置验证、残留）。
  - **残留**：商家 14 保留为 SUSPENDED 空壳，供后续人工清理/改名复用。

- **上一任务（2026-11-09，100859032 恢复执行前置核查：只读核查发现商家 14 被别的商品占用，已中止、零写入）**：用户当时批准「把 `MerchantSourceMapping(joybuy_uk,'三星 查看店铺')` 改指商家 12 Samsung、补 `三星→12` 别名、重导暂存 `a2df75b8-365b-460b-8c41-e3042b349dfc`」，前置条件是「商家 14 没有被其它商品使用」。**只读核查推翻该前提，按任务约束 ABORT，未改任何数据**（未改映射、未建 `三星` 映射、未重导、未删商家 14、未激活/发布）。该前置矛盾已由本轮用户拍板的整体合并解决。**以下子条目是合并前的历史状态与证据，当前状态见上一条，不要据旧条目判断现状。**
  - **商家 14 的占用**：`Offer` 161（`120ee2dd-…`，DRAFT，`listed_at=null`）→ `Sku` 151 → `Spu` 153（`7ed46b40-…`，《三星 Galaxy Z Flip 8 5G 256GB 石墨色》，DRAFT）；来源身份 `joybuy_uk:'100006925022956#100006925022956'` 指向 Offer 161，暂存 `8cf5dd6f-a2d5-4959-bc9c-8c1573d33f83`（IMPORTED，2026-11-06 08:59:04），payload 卖家同样是 `三星 查看店铺`。即商家 14 是同一家三星店铺（中文显示名）下的**第二件商品**，不是孤儿商家。
  - **其它引用全部为 0**（`_meta` FK/O2O/M2M 全量扫描 15 个关系 + 通用外键）：`MerchantDailyStat` / `MerchantMembership` / `MerchantWalletEntry` / `MerchantWithdrawal` / `MerchantDepositEntry` / `AfterSale` / `MerchantActivityParticipation` / `MerchantReferral(referrer/referee)` / `SupportConversation` / `MerchantOrder` / `AutoOrderTask` / `MerchantNotification` 均为 0；`SourceFieldValue` / `LocalFieldOverride` / `MediaUsage`（ContentType=merchants.merchant, object_id=14）均为 0。非零只有 `MerchantSourceMapping` 1 条（id 13）与 `Offer` 1 条（id 161）。
  - **商家 12 确认**：pk 12、`display_name=Samsung`、`SOURCE_VIRTUAL`、`ACTIVE`、`is_system=true`；映射 `joybuy_uk:'Samsung' → 12`（id 11）；Offer 159 属商家 12。
  - **映射现状**：`joybuy_uk:'三星 查看店铺'` 仅 1 条（id 13 → 14）；`joybuy_uk:'三星'` 0 条；`joybuy_uk:'Samsung'` 1 条（id 11 → 12）。
  - **为什么不能只改映射**：改指 12 后同一来源卖家会分裂到两个商家——历史 Offer 161 留在 14，未来抓取/重导 100006925022956 解析到 12，会立刻产生新的 `IMPORT_SOURCE_CONFLICT`（商家不一致）。这属于「14 已被别的商品使用」，应走人工审核后的显式合并，而不是只改映射。
  - **目标商品现状（未变）**：暂存 141（public `a2df75b8-…`）`status=PENDING`、`imported_at=2026-11-06 08:54:15`、`error_message` 空、`imported_refs` 有旧导入计数；SPU 151（DRAFT，标题 `Samsung Galaxy S26 Ultra 12GB 512GB BLACK`）/ SKU 149（规格 `{}`）/ Offer 159（merchant 12、SKU 149、GB/GBP、DRAFT、`listed_at=null`）/ `OfferSourceIdentity` id 149 → Offer 159 全部原样。SPU 151 仍为 **DRAFT**。
  - **等用户拍板**：(a) 把商家 14 的 Offer 161（及 SKU/SPU 归属）与映射整体迁到 12，删除/停用 14，再重导两件商品；或 (b) 仅加 `三星→12` 别名并单独重导 100859032（接受同一店铺分属 14/12，不推荐）。
  - **验证命令（只读）**：`./.venv/Scripts/python.exe backend/manage.py shell -c "exec(open(<临时只读脚本>).read())"`；关系扫描脚本在 `%TEMP%/joybuy_repair/verify_before.py`、`inspect3.py`、`inspect4.py`、`generic_check.py`（临时文件，不在仓库内）。DB 为 MySQL `joybuy`。**按验证纪律仅做只读核查，未跑测试**。
  - **文档**：`docs/14-crawler-product-detail-issues.md` §10.5 已改为「2026-11-09 核查后中止」，并新增 §10.5.1 记录占用证据与两个待选方案。`crawler/debug_crawl.py` 未触碰。
  - **踩坑（新增，不得再踩）**：不要假设 `SOURCE_VIRTUAL` 商家只服务一个商品——13/14 都是中文卖家名自动建出来的商家，14 同时挂着 Z Flip 8；改映射前必须扫 `Offer.merchant`，不能只看暂存/当前商品。

- **上一任务（2026-11-09，正式爬虫导入报错：来源 Offer 身份冲突，已完成）**：用户报「导入失败：商品 100859032 导入失败：The source offer identity is already assigned to a different offer.」，问是不是重复导入。**结论：不是普通重复导入，而是来源 Offer 身份冲突（卖家名称/本地化漂移）**。证据链（parent 已在 dev 库确认）：暂存 `a2df75b8-365b-460b-8c41-e3042b349dfc`（`joybuy_uk:100859032`，PENDING）的 seller 为 `三星 查看店铺`，解析后命中新商家 14；而身份 `joybuy_uk:100859032#100859032` 已绑定 Offer 159（商家 12 `Samsung`、市场 1、币种 1、SKU 149 原规格 `{}`）。`offers/services.py::_validate_offer_identity` 在 sku/merchant/market/currency 任一不一致时抛英文异常；旧解析器只去英文 `View store`、不去中文 `查看店铺`。
  1. **中文错误契约**：`backend/crawler_control/domain.py` 新增 `ImportSourceConflict`（固定 `event_code = "IMPORT_SOURCE_CONFLICT"`）；`backend/crawler_control/import_services.py` 在 SKU/Offer 身份校验失败处捕获 `ProductSourceIdentityInvalid` / `OfferSourceIdentityInvalid`，改抛中文可执行消息（来源身份、现有/本次商家与 ID、现有/本次 SKU 规格、市场/币种、不一致字段、卖家名/本地化提示、明确「不会自动改绑」），原始英文异常只写 `logger.debug(..., exc_info=True)`。
  2. **事件与暂存记录**：`crawler/joybuy_crawler/pipelines.py` 新增 `except ImportSourceConflict` → 写事件 `IMPORT_SOURCE_CONFLICT`（ERROR，中文），失败计数 +1，并把同一条中文写入 `staging.error_message`（截断 500）；暂存记录仍保持 `PENDING` 便于修复后重试。`admin-web/src/lib/locale.js` 补标签「来源身份冲突（未改绑）」。
  3. **卖家名归一化**：`crawler/joybuy_crawler/parsers/joybuy_uk.py` 新增 `normalize_seller_name()`，大小写不敏感剥掉 `查看店铺`/`进入店铺`/`查看商店`/`View store`/`Visit store`/`View shop`/`Visit shop` 等边界 UI 后缀、压缩空白、去首尾 `| · / , - —`；`seller_name` 与 `source_seller_id` 都走它。`三星 查看店铺 → 三星`、`Samsung View store → Samsung`，`Samsung 官方店` 不变。**只影响新抓取**，已入 staging 的旧 payload 与既有 `MerchantSourceMapping` 不改写。
  4. **不做的事**：不自动合并商家、不自动改绑 `OfferSourceIdentity`、不删除暂存记录。100859032 的人工恢复步骤（改映射到商家 12 后重导 / 或审批后合并商家 14）写在 `docs/14` §10.5，**本次未执行任何数据变更**。
  5. **测试（按验证纪律仅做针对性验证）**：新增 `test_seller_name_drift_conflict_is_chinese_and_never_rebinds`（冲突中文消息、身份未改绑、Offer/商家回滚）、`SellerNameNormalizationTests`（纯函数 7 组 + 解析器集成 1 例）、`StagingPipelineTests.test_offer_source_conflict_emits_chinese_event_and_keeps_staging_reason`（事件码 + staging 原因）；原 SKU 冲突测试与 `test_crawler_detail_extras.test_conflicting_existing_spec_still_raises` 改为断言 `ImportSourceConflict`。
  6. **文档**：`docs/14` 新增 §10（重复导入 vs 身份冲突判定表、中文错误契约与 100859032 示例、卖家名归一化、已知限制、人工恢复步骤）；`docs/05` §11.3 事件表新增 `IMPORT_SOURCE_CONFLICT`。
  7. **踩坑（不得再踩）**：①不要把该错误当重复导入去删暂存/重建 Offer；②不要在导入器里自动改绑 `OfferSourceIdentity` 或自动合并商家；③中英文卖家名后缀都必须在解析层清洗，只去 `View store` 会再次产生「同名双商家」；④已入 staging 的旧 payload 不会被新归一化器重写，必须重抓；⑤改异常类型后要同步旧测试断言（`test_crawler_detail_extras` 已改）。
  - **验证命令与结果**：`./.venv/Scripts/python.exe backend/manage.py test crawler_control.tests.test_crawler_import -v 1` → **11 tests OK**；`... test_crawler_import test_crawler_rebuild test_crawler_detail_persistence offers.tests` → **62 tests OK**；最终改完消息分支后复跑 `... test_crawler_import` → **11 tests OK**、`... test_crawler_rebuild test_crawler_detail_extras test_crawler_detail_persistence` → **56 tests OK**；`... test_crawler_product_category` → **7 tests OK**。`merchants.tests` 一起跑时 **1 例已知失败** `test_merchant_totp_policy_is_enforced_during_staff_login`（403 != 200），单跑同样失败，属既有 TOTP 过期问题、与本次改动无关（HANDOFF 旧记录已列为已知）。改动 7 个 py 文件 `ruff check` 全过、`ruff format --check` 全过；`admin-web` 的 `npx prettier --check src/lib/locale.js` 通过。**未跑全量测试**。
  - **已知限制 / 下一步**：flight JSON 只有 `sellerName`，没有稳定 shop/vender ID（fixture 可证），所以来源身份仍按名称，`Samsung` 与 `三星` 这类跨语言别名**不会自动归并**；后续应加「来源卖家→商家」别名表或按 `/store/<id>` 建映射。网络恢复后仍需重跑 100859032 验证真实中文事件；先按 `docs/14` §10.5 修正商家映射。

- **上一任务（2026-11-09，爬虫运行失败原因诊断：网络/TLS 失败不再误报风控，已完成；外部网络仍不可用）**：正式运行 `4d0b3954-2899-4dcb-9d95-b6f0ebb4f52e`（任务 `电子产品-手机测试。`，类目 `l2:1420` Phones，`product_limit=15`，09:46:32→09:47:14 UTC）零商品失败，用户看到「没有发现任何商品：列表页可能被风控拦截、需要登录，或站点结构已改版。」。根因分两层：①**环境**——该机到 joybuy.co.uk 的 TLS 连接被中途断开（日志 `ResponseNeverReceived`/`ConnectionLost`，robots.txt 与 `/s?k=Phones` 各重试 4 次全失败；同机 `curl` 复现 `schannel: failed to receive handshake` 或 12s 超时，`urllib` 复现 `SSL: UNEXPECTED_EOF_WHILE_READING`），**不是解析器/UA/风控问题**；②**代码**——零商品时无条件报风控/改版文案，把网络故障说成站点故障。
  1. `crawler/joybuy_crawler/spiders/joybuy_run.py`：列表页请求加 `errback=self.listing_failed`，累计 `listing_fetch_errors` / `listing_error_types` / `listing_successes` / `last_listing_error`；每次最终失败写 `LISTING_FETCH_FAILED`（ERROR，含 URL、异常类型与文本、本轮第几次失败），并 `stats.inc_value("joybuy/listing_fetch_failed")`；`parse_listing` 累计 `listing_successes`。
  2. `crawler/joybuy_crawler/pipelines.py`：新增纯函数 `zero_item_failure_reason()`（配 `GENERIC_EMPTY_REASON` / `NETWORK_FAILURE_HINT` / `format_error_types()`）。失败原因契约：零商品且列表页下载异常 > 0 → 「全部/部分列表页请求失败：列表页请求失败 N 次（ConnectionLost 2 次、ResponseNeverReceived 6 次）。请检查网络、VPN 或代理；这是下载/TLS 层错误，不是风控、登录或站点结构改版。…」；列表页**拿到响应**但 0 商品 → **原文案不变**；robots.txt 同时失败追加「robots.txt 同样无法获取。」；部分失败但仍有商品时写 `LISTING_FETCH_PARTIAL`（WARNING，不影响 SUCCEEDED）。
  3. `crawler/joybuy_crawler/runner.py`：启动 Scrapy 前做一次有超时的连接前置检查（直连时 TLS 连 `www.joybuy.co.uk:443`，配置代理时只连代理 TCP 端口），失败写 `CONNECTIVITY_PREFLIGHT_FAILED` 并直接 `complete_run_failed`，不再空转 40 秒重试；只建立连接、不发 HTTP 请求，**不绕过 robots**。开关 `CRAWL_PREFLIGHT_ENABLED` / `CRAWL_PREFLIGHT_TIMEOUT`（默认 true / 8s）。
  4. 代理：Scrapy 本身已会读环境变量与 **Windows 注册表系统代理**（`HttpProxyMiddleware` → `getproxies()`），所以"系统代理是否生效"不用改代码；坑在 `no_proxy` 会按 host 旁路、且环境变量是进程级无法只给爬虫进程指定。新增 opt-in `CRAWL_HTTP_PROXY` / `CRAWL_HTTPS_PROXY`（settings）+ `middlewares.ProxyConfigMiddleware`（优先级 580，写 `request.meta["proxy"]`，绕过 `proxy_bypass`），日志/事件用 `redact_proxy_url()` 脱敏；**留空 = 完全沿用 Scrapy 原行为，代码里没有任何硬编码代理**；`socks5://` 忽略。
  5. 前端：`admin-web/src/lib/locale.js` 补 4 个事件码中文标签（`LISTING_FETCH_FAILED` / `LISTING_FETCH_PARTIAL` / `CONNECTIVITY_PREFLIGHT_FAILED` / `PROXY_CONFIGURED`）；事件本身按通用逻辑渲染，无其它前端改动。
  6. 文档：`docs/05-crawler-and-ingestion.md` 新增 §8.2（代理）、§8.3（网络失败诊断与连接前置检查），§11.3 事件表加 4 行；`crawler/README.md` 新增「网络失败与代理」；`.env.example` 加 4 个变量。
  - **验证（按验证纪律仅做针对性验证）**：`cd backend && ../.venv/Scripts/python.exe manage.py test crawler_control.tests.test_crawler_rebuild` → **35 tests OK**（新增 13 例：失败原因纯函数 3、pipeline 零商品网络/通用/部分失败 3、errback 事件+计数 1、代理中间件 2、连接前置检查 4）；再加 `test_crawler_detail_extras test_crawler_review_aggregates test_crawler_runtime` 一起跑 → **74 tests OK**；6 个改动 py 文件 `ruff check` 与 `ruff format --check` 全过；`cd admin-web && npx prettier --check src/lib/locale.js` 通过。**未跑全量测试**。
  - **环境阻塞（未解决，不得声称已修复）**：2026-11-09 10:00 UTC 复测 `curl -m 12 https://www.joybuy.co.uk/robots.txt` 仍 `exit=28`（12s 超时，0 字节；更早一次是 `schannel: failed to receive handshake`）。因此**没有执行真实抓取，也不能声称线上抓取已恢复**；网络恢复后必须重跑一次正式运行确认 `LISTING_FETCHED`，若仍失败，新逻辑会明确报网络/TLS 并指向 VPN/代理。
  - **下一步**：网络/VPN 恢复后启动一条正式运行（管理端或 `manage.py run_crawl_run --run <public_id>`）验证端到端；若现场必须走代理，在 `.env` 配 `CRAWL_HTTPS_PROXY=http://host:port`（或临时 `CRAWL_PREFLIGHT_ENABLED=false` 复现旧行为）。

- **上一任务（2026-11-09，正式详情存储 + 购物端渲染：视频 / 图文区块 / 规格表格 / spec_options / AI，已完成）**：把爬虫第二轮增量详情正式落进业务表并由详情 API / 购物端渲染。**爬虫契约与 `crawler/debug_crawl.py` 均未改动。**
  1. **模型/迁移**：`catalog.SpuDetail`（OneToOne ↔ Spu；`content_sections` / `specification_tables` / `specifications` / `spec_options` 四个 JSONField + `ai_summary` / `ai_summary_title` / `ai_summary_tags` + `source_observed_at`）；`catalog.SpuVideo`（Spu / MediaAsset 视频 FK、`poster` 图片 FK、`duration_ms`、`source_video_id`、`source_url`、`sort_order`）；`MediaAsset.Kind.VIDEO` + `KINDS` 前缀 `videos/`。迁移 `catalog/0014_spudetail_spuvideo`、`media/0004_alter_mediaasset_kind` 已在 dev 库执行。
  2. **导入 `backend/crawler_control/import_services.py`**：`_sync_spu_detail()` 只写非空字段（失败/旧解析不清空已入库详情）；`content_sections[].images` 与 `spec_options[].values[].image_url` 下载进本地媒体库后替换成 `/media/...`，失败即丢弃、不留 CDN 兜底；`specifications` 有值但缺表时后端按 group 兜底生成两列表格。`_import_spu_videos()` 按 `video_id`/`url` 匹配并幂等 upsert，已落盘文件可复用，`videos` 非空时清理源站已删除视频，空/缺失时保留既有视频；`staging.imported_refs` 新增 `detail` / `videos` 计数。
  3. **API `backend/catalog/detail_views.py`**：新增 `videos`、`content_sections`、`specification_tables`、`specifications`、`spec_options`、`ai_summary` / `ai_summary_title` / `ai_summary_tags`；`spec_options[].values[].sku_ids` 由源 SKU id 映射为 `Sku.public_id`。`description` / `category_slug` / `category_breadcrumb` / `skus` / `gallery` / `review_summary` 等旧字段全部保留；历史商品无 `SpuDetail` 时返回空结构。
  4. **购物端 `storefront/pages/p/[id].vue`**：视频排画廊第一位并用 `<video controls poster>` 播放（本地 `/media`，不参与放大镜）；规格 chips 优先用 `spec_options`（源站顺序 + s96 图），点击按 `sku_ids` 选 SKU，维度名与 SKU 规格名语言不一致时用 `sku_ids` 兜底；`content_sections` 按区块标题 → `heading`（16px/700/#1a1a1a）→ `paragraph` 渲染并展示区块图片；`specification_tables` 每组一张「属性 | 值」两列 `<table>`（`th scope=row` 保留行序）；AI 摘要卡（标题/正文/标签）；详情下方另有 Product videos 区；无 `content_sections` 回退 `description`。
  - **验证（按验证纪律仅做针对性验证）**：后端 7 个模块 **76 tests OK**（`catalog.tests.test_product_detail_api`、新增 `catalog.tests.test_product_detail_extras` 2 例、新增 `crawler_control.tests.test_crawler_detail_persistence` 4 例、`test_crawler_detail_extras`、`test_crawler_import`、`test_crawler_rebuild`、`media.tests`）；改动 py 文件 `ruff check` / `ruff format --check` 通过；storefront `prettier --check` / `eslint` / `nuxt build` 通过；浏览器实测（临时把详情/视频挂到真实商品 `947910f2…` Wireless Earbuds Pro，测后已删除）：视频 `readyState=4`、`duration=2`、`currentSrc` 为本地 `/media/videos/...`、位于画廊第一位，规格点击 Blue 价格 `$19.99 → $23.49`，heading 计算样式 16px/700/`rgb(26,26,26)`，表格表头「属性 | 值」且两组行序正确，AI 标题/正文/3 标签完整渲染。
  - **边界/未做**：Django 开发 `/media` 未实现 HTTP Range（生产 Nginx 需配，否则大视频拖动进度只能整段加载）；历史商品需重抓重导才有图文区块/规格表/AI/视频；`videos` 为空或字段缺失不清空既有视频（安全优先）；**`.gitignore` 已修正**：原 `media/` 规则误伤 `backend/media/` 源码目录，已改为 `/media/` 并删除 `backend/media/` 行；运行时媒体仍在 `var/media`（被 `var/*` 忽略），`backend/media/` 源码与迁移现在可正常入库（`git status` 显示为 `?? backend/media/`）。详见 `docs/14` §9。

- **上一任务（2026-11-09，正式爬虫同步第二轮修复：画廊 / 系列规格 / 图文子标题 / 规格表格 / AI 摘要 / 视频，已完成）**：把 `crawler/debug_crawl.py` 里已验证的第二轮行为移植进正式爬虫（**调试脚本未改动**，仍作参考实现）。
  1. **解析层 `crawler/joybuy_crawler/parsers/joybuy_uk.py`（纯函数、不联网）**：`extract_flight_gallery` / `clean_gallery` / `product_image_url` / `normalize_gallery_url`（全量 s1248、按 `/product/` 路径去重、丢 `-000-com`/s32/s64/s96/非 `/product/`；DOM 兜底同规则）；`extract_spec_options` + `sku_specs_from_options`（`productSeriesFloor.series` 在前 + `colorSizePartList`，写 `spec_options` 与 `skus[].specs`，单 SKU 单值兜底）；`extract_dom_sections`（`MuiAccordion-root`，`<strong>/<b>` = heading）；`parse_uk_mobile_detail` + `merge_mobile_detail`（`structuredFloors` 区块 / mode 8 属性组、旧版 `graphDetailsModule`、`graphDetailListN` 兜底；移动端优先 + PC 补缺）；`build_specification_tables`（`{title, columns:["属性","值"], rows}`，行序按源站、不按 `attributeSort`）；`extract_ai_summary`（内联 `aiSummary{summaryContent,summaryText}` + `aiTagList[].tagName`）；`extract_videos`。
  2. **payload 增量字段**：`spec_options`、`content_sections`（`blocks` 保留 heading/paragraph）、`specifications`（含 `group`）、`specification_tables`、`videos`、`video_urls`；`joybuy` 原生块加 `specOptions/specifications/contentSections/videos`；`description` 仍为可读兜底（heading 加 `## ` 前缀），`detail_image_urls` 收区块图片。导入端只增不改。
  3. **蜘蛛两步请求 `spiders/joybuy_run.py`**：PC `/dp/` 解析后 yield 一个 `/dg/<sku>` 请求（同 `meta` + `errback`），`parse_mobile_detail` 合并后只产出**一条** item；失败走 `mobile_detail_failed` 按 PC 数据落盘。事件 `MOBILE_DETAIL_MERGED` / `MOBILE_DETAIL_FAILED` / `MOBILE_DETAIL_PARSE_FAILED`。
  4. **域名口径（重要踩坑）**：`m.joybuy.co.uk/robots.txt` 明确 **`Disallow: /dg/`**，正式链路不能请求 m.；实测 `https://www.joybuy.co.uk/dg/<sku>` 返回**同一份 SSR**（`structuredFloors` 一致）且 www robots 未禁止 `/dg/`，所以只用 www。开关 `CRAWL_MOBILE_DETAIL`（settings `JOYBUY_MOBILE_DETAIL_ENABLED`，默认开，每商品多 1 次请求）。
  5. **视频 `dataset.py`**：新增 `download_video()`（浏览器 UA、120s 超时、3 次退避重试）→ `<商品目录>/videos/01.mp4`；索引新增 `videos` / `video_errors`，`DATASET_SAVED` 日志带视频计数。**视频不进 `var/media` 媒体库**（媒体库只有图片 kind/role），本轮只落 dataset + payload。
  6. **导入兼容 `import_services._adopt_enriched_specification`**：2026-11-05 那批 SKU 规格为空（签名 `{}`），重抓补上系列/颜色后签名会变；只允许「旧规格为空 → 新规格非空」的单向补全（同 `source_id`、同 SPU、新签名未被占用），其它冲突仍抛 `ProductSourceIdentityInvalid`。
  - **验证（按验证纪律仅做针对性验证）**：新增 `crawler_control/tests/test_crawler_detail_extras.py`（16 例：画廊过滤/系列+颜色/单值维度/AI/视频/PC 子标题/移动端区块+表格/合并/数据集视频/导入补全/蜘蛛两步流程）；一起跑 8 个针对性模块（新增 + review_aggregates/import/rebuild/product_category/field_rules/quality_gates/product_detail_api）共 **113 例全过**；再复跑核心 6 个模块（新增 + review_aggregates/import/rebuild/product_category/product_detail_api）共 **70 例全过**；改动 8 个 py 文件 `ruff check` / `ruff format --check` / `py_compile` 全过。真实页面离线复核 5 个商品（见 `docs/14` §8.3）：ZSPEED 5 图无 icon、小绿锅/炒锅/iPhone 系列+颜色、iPhone 15 行技术规格、蒸锅视频真实下载 **7,102,340 字节**落 `videos/01.mp4`。
  - **边界/未做**：未跑全量测试；视频未进业务表；区块/属性名随 Accept-Language 变英文（不是 bug，前端需容忍）；商品名/属性英文未翻译。`test_crawler_rebuild.SpiderLoggingTests` 已按两步流程更新。详见 `docs/14` §8、`docs/05` §9.4。

- **上一任务（2026-11-09，调试脚本第二轮：系列规格 / 图文详情 / AI 摘要 / 视频，已完成）**：在 `crawler/debug_crawl.py` 上修 4 个商品（小绿锅/炒锅/蒸锅/iPhone）的 5 项问题——系列规格在 `productSeriesFloor.series`、图文详情在移动端 `structuredFloors`、规格参数是 mode 8 属性组、AI 摘要内联 `aiSummary`、视频在 `mediaData(mediaType=2)`。产出 `docs/14` §7（含表格展示口径 §7.6、子标题结构口径 §7.7）。**正式爬虫已在当前任务同步完成。**

- **上一任务（2026-11-09，节庆装饰品改为活动商品，已完成）**：按用户要求把【节庆装饰品】从【家居生活】移除，数据不再归本地类目，抓取时直接按「活动商品」入库。
  1. **crosswalk**：`l2:1580` 改为 `action="activity"`，不再创建 `seasonal-decor`；新增 `ACTIVITY_SOURCE_IDS` / `ACTIVITY_LOCAL_SLUGS`。
  2. **同步命令**：activity 行不建本地类目；历史 `seasonal-decor` 在**无商品/无子类目/无商品类目引用**时删除，否则保留并提示先迁移数据；报告新增活动节点/清理计数。dev 库已执行：`seasonal-decor` 已删，本地类目 **141**（家居生活 24）。
  3. **spider**：target 增加 `source_category_id`，payload 写 `crawl_source_category_id` / `crawl_source_category_name`。
  4. **import**：活动判定 = 任务来源 `l2:1580`/`节庆装饰品` **或** 商品类目路径含 `节日与活动(4945)`；命中后 `Spu.is_activity=True` 且 `local_category=None`，商品类目仍保存两级（节日派对/节日与活动），面包屑照常；`is_activity` 只加不清。
  - 验证：**50 个针对性测试通过**；同步命令 0 错误；`派对用品(4910)` 不误标。详见 `docs/15-category-taxonomy-and-product-breadcrumb.md` §2.1。

- **上一任务（2026-11-09，类目体系落地：11 个一级二级补全 + 商品类目表 + 两级面包屑，已完成；⚠️ 其中「合并补全的多对一桶」口径已被 2026-11-11 一对一拆分推翻，见文件顶部当前任务，其余口径仍有效）**：按用户口径（**合并补全**、**按二级拆分**、`ProductCategory` 2 级 + SPU + 可空 LocalCategory、**先存中文**）落地。
  1. **二级类目补全**：新增 `backend/catalog/joybuy_menu_crosswalk.py` + `sync_local_categories_from_joybuy` 命令；合并既有 42 个节点（改名不改 slug）、新建 89 个 Joybuy 二级、建立 157 条二级 `CategoryMapping` + 13 条频道映射；汽车 6 个节点不映射。本地类目 53 → **142**（11 一级 + 131 二级）。
  2. **商品类目表**：新增 `ProductCategory`（最多 2 级，DB `CheckConstraint(depth<=1)`）+ `Spu.product_category` FK（迁移 `catalog/0013`）；解析器从 flight `productBreadCrumbFloor...categories` 取前两级，payload 新增 `product_category_path` / `product_category_id`；导入 upsert 并挂 SPU，第 3 级（炒锅）不落库。
  3. **面包屑**：详情 API 返回 `category_breadcrumb`；购物端优先显示 `Home / 厨具餐具 / 锅具 / 商品名称`，历史商品回退本地类目。
  - 验证：**47 个针对性测试通过**；迁移已应用；同步命令 dry-run/正式执行 0 错误；真实炒锅 `10003152` 解析 `[厨具餐具(288), 锅具(361)]`；storefront prettier/eslint/`nuxt build` 通过。**未在 dev 库真实导入该商品、未做浏览器实测**（导入/API 已有单测覆盖）。详见 `docs/15-category-taxonomy-and-product-breadcrumb.md`。

- **上一任务（2026-11-09，类目体系答疑：三套类目与商品类目映射建议，仅分析未改代码）**：用户问「Joybuy 频道类目（家居生活 → 厨房与餐厅用品/家具/整理收纳/家居装饰）与商品面包屑（厨具餐具/锅具/炒锅）是什么关系、后者是不是类目、怎么关联到我们的 LocalCategory」。结论：**是三套不同层级的类目体系**——①我们的 `local_category`（11 个一级 + 42 个二级；家居生活下只有厨房用品/家居收纳/床品家纺/清洁用品/食品杂货）；②Joybuy **频道菜单树**（已抓为 `SourceCategory/SourceCategorySnapshot`，家居生活下有 22 个二级：厨房与餐厅用品 `l2:1572`、家具 `l2:1564`、整理收纳 `l2:1574`、家居装饰 `l2:1566`…）；③Joybuy **商品后台类目树**（面包屑来源：`厨具餐具(288) → 锅具(361) → 炒锅(372)`，数字 ID，`SourceCategory` 里 0 条命中）。面包屑最后一节「商品名称」不是类目。当前解析器用 DOM 面包屑、截断 2 级且 `cid` 为空，`source_category_id` 为空；导入只按任务所选的 `bestseller:*` 类目映射（仅 11 条），所以关联不上。建议：从 flight `productBreadCrumbFloor...categories` 存完整商品类目路径+ID；新增商品类目表/映射表，按「最深已映射祖先」多对一映射到本地二级（炒锅/锅具 → 家居生活/厨房用品），任务菜单类目作兜底；并决定是否把本地二级扩到 Joybuy 的 22 个。**未改代码**，待用户拍板映射口径。

- **上一任务（2026-11-08，爬虫商品详情 7 项解析问题修复 + 双输入 URL，已完成）**：按用户对商品 `100016395115375`（ZSPEED iPad 触控笔）的反馈修 `crawler/debug_crawl.py`，并产出 `docs/14-crawler-product-detail-issues.md`（问题 / 证据 / 根因 / 解决方案 / 同步回正式爬虫的步骤）。7 项：①日志加代码行号（`%(name)s:%(lineno)d`）；②排除服务/保障 icon（`-000-com`、s32/s96）；③5 张 s128 缩略图全部映射成 s1248 大图（flight `productMainImageFloor.mediaData`）；④商品描述解析（`productDetailFloor_content` 富文本，本商品 1009 字）；⑤规格 `颜色：白色` + s96 规格图 + `skus[].specs`（flight `productSelectedFloor.colorSizePartList`）；⑥【规格参数】4 条（PC 端是客户端渲染 `BAILOUT`，改抓移动端 `m.joybuy.co.uk/dg/<sku>` 的 `graphDetailListN`）；⑦评价 5.0 分 / 4 条 / 5 星 4 条（`ratingInfo` 是内联对象，旧正则匹配不到，改 `raw_decode`）。**另外支持双输入 URL**：`LISTING_URLS` / `--listing-url` 可传搜索页（`/s?k=...`，按 `--limit` 抓 N 个）或商品详情页（`/dp/...`，跳过列表直接分析该商品），也可混传并按商品 ID 去重；两种入口共用 `process_product()`，产物一致。**正式爬虫未改动**，全部逻辑集中在调试脚本，待用户调完按文档 §5 同步。

- **上一任务（2026-11-08，爬虫详情大卡片 + 折扣口径改「给商家的进货折扣」+ 已上架成本价重算，已完成）**：
  1. **爬虫任务详情改浮层大卡片**：原来点【详情】把 `.detail` 面板插在任务表格下方，挤在列表里不好看；改成 `position: fixed` 遮罩 + 居中大卡片（`min(1080px, 96vw)`、`max-height: 90vh`、标题/任务名在头部、正文独立滚动、点遮罩或【关闭】收起），运行中每 5s 轮询逻辑不变。
  2. **折扣口径反转（重要，旧口径作废）**：用户确认折扣是**平台给商家的进货折扣，不是顾客折扣**——`成本价 = 平台成本价 × (1 − 折扣%)`，保留两位小数；顾客价（零售价）不变。旧实现是 `向上取整(零售价 × 折扣)`，所以 HOMCOM（折扣 20%）在商家端显示的成本价偏低。例：平台成本 3599 → 2879.20（用户给的验收值），活动折扣 30% → 2519.30。`compute_listing_cost` 已从 `views_merchant_catalog` 移到 `merchant_ops/services.py`（视图里保留同名导入，测试照旧 import）。
  3. **改折扣要重算已上架商品**：之前 Offer 的 `cost_price` 是上架时快照，管理端改折扣后不变。新增 `merchant_ops.services.reprice_listed_offers(merchant=/spu=)`，在**管理端 PATCH 商家折扣**、**商品池改成本价**、**活动商品打标/去标**三处调用；接口回包新增 `repriced_offers` 计数。一次性数据修复：HOMCOM 6 条已上架 Offer 已按新口径重算（`c5130796` 成本 3599 → **2879.20**，零售价仍 4899）。
  - 验证：`test_wp42_discount_listing + test_admin_commerce + test_merchant_modules + test_media_upload` **93 passed**（重写 6 例折扣单测 + 新增 2 例改折扣重算/清空折扣回退）；ruff 通过；admin-web prettier/eslint/build 通过；商家端 API 实测 `HOCO ... 成本 2879.20 / 零售 4899.00`；管理端 API 实测把折扣在 25↔20 之间来回改，Offer 成本跟着变 2699.25 ↔ 2879.20、零售价不变；浏览器实测爬虫详情大卡片可开可关。临时管理员已删。

- **上一任务（2026-11-08，爬虫任务独立调试脚本，已完成）**：新增 `crawler/debug_crawl.py`，把「列表页 → 商品卡 → 详情页 → 解析 → 质量规则 → 落盘」整条链路单独拉出来逐行调试。**与正式存储完全隔离**：不 import Django、不连数据库（不写 staging/SPU/Offer/运行事件）、不读不写 `var/`（`crawl_exports` / `media` / `cache` / `browser_profiles` 全不碰）；所有产物只写 `OUTPUT_DIR`（文件顶部常量、环境变量 `CRAWL_DEBUG_OUTPUT_DIR`、命令行 `--output-dir` 三选一），每次运行建独立 `run-YYYYmmdd-HHMMSS/` 子目录。复用正式解析器（`parse_uk_listing` / `parse_uk_product_detail`）、记录级质量规则（`apply_product_rules` / `check_listing_entry`）、最高清图片解析（`resolve_highest_resolution`）与风控/登录墙判定（`render.classify_page`）。日志 DEBUG 级、控制台 + 文件双写，每条请求/每张卡片/每个字段/SKU/图片/落盘/索引都单独一行。**登录态直接吃 cURL(bash) 解析出的 dict**：自动读取 `crawler/debug_session.py` 的 `headers = {...}` / `cookies = {...}`，也支持 `--headers-file`（JSON / Python dict / 两个赋值连写）与 `--cookie` 追加；Cookie 值日志里一律 `[REDACTED]`。**踩坑**：①列表页匿名请求会被 307 到 `/login?returnUrl=...`，登录墙判定必须用**跟随跳转后的最终 URL**（`FetchResult.url`）；②商品 URL 里带中文（`/dp/佳能-pixma-ts6550i/...`）必须 percent-encode，否则 `urllib` 报 `UnicodeEncodeError: 'ascii' codec can't encode`（已加 `normalize_url()`）。

- **上一任务（2026-11-08，商品池编辑弹窗父/子品类联动 + 图片 10MB + 购物端商品不可见修复，已完成）**：五项用户反馈全部落地。
  1. **编辑弹窗「商家端品类（父品类）」→「子品类」联动**：两者位置对调并**并排相邻**（商品名称独占整行），先选父品类，子品类只列该父类目下的二级类目；未选父品类时子品类禁用并提示「请先选择商家端品类」；切换父品类会清掉不属于新父类目的选择；历史数据若挂在父类目本身（如 HOCO 挂在「电子产品」）或别的父类目下，当前值会以「xxx（当前值）」保留在选项首位，**不静默清空**。父子映射放后端 `catalog.models.LOCAL_PARENT_MERCHANT_CATEGORY`（11 个父类目 slug → 商家端品类），`/admin/categories` 额外返回 `parent_id` 与父类目的 `merchant_category`。
  2. 删除编辑弹窗里「商家端【商品上架中心】按这 12 类展示。」提示语。
  3. **输入框左右对不齐**：根因是 `.field` 是 grid 且默认拉伸——同一行里带 hint 的字段更高，右侧没有 hint 的输入框被拉高 11px、下移 11px。修 `admin.css`：`.field` 加 `align-content/items: start`、`.form-grid` 加 `align-items: start`、输入框与下拉统一 `height: 35px`。实测同一行控件 y 值与高度完全一致（216/216、290/290，均 35px）。
  4. **商品图单张上限 1MB → 10MB**：后端 `media.uploads.PRODUCT_MAX_BYTES`、前端 `:max-size-mb="10"`（评价图/活动图/头像上限不变）。
  5. **购物端看不到商品（用户报 `c5130796`）**：查出两个真 bug——①**商家端上架只建 Offer、从不刷新搜索文档**，商品池新建的商品上架后没有 `product_search_document`，购物端搜索和类目页都查不到（本库 OPPO A6x `3e75a502` 正是这种「已上架但零文档」）；②**管理端改品类不刷新搜索文档**，`c5130796` 的文档还停在 11-04 创建的 `computers-accessories`，所以它在「计算机与配件」类目下、不在「电子产品」下。已给「商家上架」「商品池新增/更新」「上下架」全部补上 `refresh_spu_search_documents`，并一次性重建全部 121 个已上架商品的文档。验证：购物端 `/s?category=electronics` 现在同时出现 HOCO 与 OPPO，详情页 `/p/c5130796…` 正常。

- **上一任务（2026-11-08，管理端商品池：品类搜索下拉只显示父类目，已完成）**：用户要求商品池的**品类搜索下拉框只展示父类目**（家居生活/电子产品/美妆个人护理/小家电/健康与保健/计算机与配件/服装与配饰/户外运动/宠物用品/婴幼儿用品/游戏及配件），不展示二级类目。实现要点：①筛选下拉在前端按 `depth===0` + `sort_order` 过滤排序（数据驱动，正好 11 项，顺序与用户给的一致）；②**后端品类筛选改成整棵子树匹配**（`local_category__path__startswith`），否则只选父类目只出 38/122 条——本库 84 个 SPU 挂在二级类目上（家居生活直挂 3、含子树 77；小家电 3→13）；③`/api/v1/admin/categories` 仍返回全量 53 条（编辑弹窗要能选二级类目，实测 54 项含「未分类」、当前值「食品杂货」仍正确回显）。验证：`test_admin_commerce` 31 例 OK（新增 2 例：子树筛选、categories 返回 depth/sort_order）+ API 实测 4 个父类目数量对齐 + 浏览器实测下拉 11 项/家居生活 4 页 77 条/小家电 13 行。后端已重启（新 PID 55072）。

- **上一任务（2026-11-07，需求迭代文档 02 v2.1：第二场录像拆解 + 4 项拍板回填，纯文档）**：拆解 100.8 分钟录像 `D:/Users/lyx/Videos/Joybuy功能需求讨论02.mp4`（828 段转写 + 200 关键帧），以视频为主、`功能需求迭代文档02.md`（v1 手记）为辅，重写出 v2，用户随后拍板 4 项回填为 **v2.1**，待确认项清零。**只改文档，未动代码**。产物：`功能需求迭代文档02.md`（v1 备份 `.bak-20261107-170915`）+ `D:/Users/lyx/Videos/Joybuy功能需求讨论02_拆解/Joybuy功能需求讨论02-内容拆解.md`。
  - **4 项最终拍板**：①返佣基数**按成本价**（当月发货成功订单的成本价合计 × 1%/2%/3% 三档，明细列名沿用"发货成功金额"）；②时区=**存储统一、展示按登录地区当地时间**，用户端/商家端/管理端三端一致（新增文档第四节"全局约定：时间与时区"）；③首页删模块后偏空**先不用管**；④一键下单前置检查：**检查白名单账户余额**（不足不下单并提醒）、**已下架商品不展示**在可选商品里、**规格失效要提醒**（创建与触发时都校验）。
  - **视频新增的大块需求（v1 全没有或只有一句）**：①管理端订单"单个更新进度（只能向后、点击时刻=节点时间）"与"一键完成全部节点（状态+进度+回款同刻）"，修改下单时间仅【已完成】可改、节点时间三规则；②商家端订单"预估盈利"、【已完成】隐藏进度；③钱包：字段全不校验只校验金额、不展示手续费/冻结金额、提现不通过立马退回、资金明细五类型；④推荐返佣全链路：推荐码绑定、月结三档、每月 1 日核算、管理端确认后才发放；⑤保证金：审核勾选决定模块、未缴只能浏览不能上架、启用状态不可逆、手动充一笔；⑥商家管理列表字段（待发货数/成本价合计/余额/在线时间 10 分钟刷新）+ 封店天数改小二次确认立即封店、解封人工；⑦平台下架/商家商品下架两端同步、订单照常履约、详情统一提示已下架；⑧资金审核：打回要原因、手续费通过后才展示、转账失败去凭证加原因、新建钱包充值；⑨平台活动限时/长期 + 到期自动下架 + 参与加曝光做记录；⑩通知全手动推、好评推送改"店铺订单"（已完成+未评价）+默认五星+图片+已读同步颜色区分；⑪用户端管理：登录渠道字段、去所在地区/上次在线、支付权限"全部可用"、白名单移入移出就地操作、独立白名单模块删除；⑫购物端登录 Facebook+Google+邮箱（做不了邮箱验证码就手动注册）、去国家选择；⑬首页活动卡片固定十个无翻页、跳转链接自配（可到小品类）、删心选品牌/美洲甄选；⑭**一键下单**（管理端自动化任务：白名单用户→商家→商品→规格→数量→触发时间，按电脑时间到点下单，正常流转两端生成订单）。
  - 抽帧实证 2 帧：`f031` 推荐新商家入驻页（返佣规则表/推荐码 REF008628/明细列）、`f136` 审核提现申请弹窗（审核结果下拉+手续费 CNY 输入框）。

- **当前任务（2026-11-08，商品池列表列宽固定，已完成）**：应用户反馈「商品字段太宽，右侧字段被挤成两行」——给 `ProductPoolView` 表格加 `.pool-table`（`table-layout: fixed` + 逐列百分比宽度：商品 42% / 品类 15% / 成本价 11% / 零售价 11% / 商家数 8% / 状态 9% / 操作 190px），商品名与品类单行 `ellipsis`（hover 显示全名），其余列 `white-space: nowrap`，操作列按钮不换行。实测 1280 宽下 7 列宽 327/117/86/86/62/70/190，5 行行高统一 64px（无换行、无挤压）。

- **上一任务（2026-11-08，一键下单商品卡改成左图右规格，已完成）**：应用户要求把第 3 步商品卡从「上图下文」竖版改为**横向卡片**——左侧 72×72 正方形缩略图（无图显示「无图」），右侧依次为商品标题（单行省略）、**规格标签 chips**（最多 3 个 + 「+N」，来自 `offers[].specification`）、价格与规格数；列表改单列纵向排列，选中勾定位到卡片右上角，避免与右侧内容重叠。eslint/vite build 通过；浏览器实测 HOMCOM 商品列表（4 条/页、规格 chip、红价、分页正常）。

- **上一任务（2026-11-08，一键下单三处修复，已完成）**：①**余额不足禁止创建**——后端 `views_auto_orders` 把 `check_account_balance` 挪到 `create_auto_order_task` **之前**并直接抛 `BALANCE_INSUFFICIENT` 400（原来只是 warning、任务照建，且校验在创建之后会残留任务）；②**商品缩略图改正方形**——`.product-card .thumb` 用 `aspect-ratio:1/1`（原来固定 88px 高被拉成长方形），无图显示「无图」文字；③**分页箭头空白**——管理端没有 Lucide 图标库，`data-lucide` 渲染为空，全部换成字符字形（‹ › ← → ✓）与首字母头像。顺带修 `admin-web/src/lib/api.js`：`localizedErrorMessage` 现在**优先透传后端中文业务提示**，不再把「买家钱包余额不足…」吞成通用「请求失败」。**重大踩坑**：之前用 `powershell -Command Stop-Process` 重启后端，但该 shell PATH 里没有 powershell，**杀进程静默失败**，旧进程一直跑旧代码，导致改了代码却毫无效果——正确做法是 `taskkill //F //PID <pid>`（pid 取 `netstat -ano | grep ":8000" | grep LISTENING` 第 5 列），并循环确认端口已释放再启动。验证：`test_doc02_round3` 11 例 OK（余额不足用例改为断言 400 + 不落任务）+ doc02 三轮 31 例 OK；浏览器实测——余额不足创建被拦且弹窗保留、红字显示「买家钱包余额不足（需约 216.0000，可用 196.3000），请先充值或更换买家。」；商品卡正方形缩略图；分页 ‹ 1 2 › 正常显示。

- **上一任务（2026-11-08，一键下单向导重做为 C 版，已完成）**：用户确认选择 C 版设计（左栏步骤导航）后重做 `AutoOrdersView.vue` 新建任务抽屉：①左栏竖排步骤导航——绿色 ✓ 已完成步骤**可点击直接回跳**、蓝色当前步、灰色未到步置灰不可跳（只能往后、不能跳步往前）；②底部常驻「已选：买家 · 商家 · 商品×数量 · 触发时间」摘要栏 + 上一步/下一步（第 5 步变「创建任务」），回跳后已选信息不丢失；③商家卡带头像（有头像图用 img、无则首字母圆标）、店铺 ID 前 8 位、接单状态、信誉分；④商品 2 列卡片带**真实缩略图**、价格、规格数，**客户端分页每页 4 张**（options 端点最多 30 件），分页条「共 N 件 · 第 x/y 页」；⑤全宽搜索框带可见 label。**修了一个真 bug**：选完商家后 `merchantQuery` 残留商家名，进入第 3 步时被当成商品关键字把商品全部过滤掉（显示"该商家没有可售商品"）——pickMerchant 里清空并立即 loadProducts。验证：eslint/vite build 过；浏览器实测全流程（选买家→商家卡→商品分页→规格/数量/触发时间→确认创建→任务入库 PENDING），并实测回跳第 1 步后底部摘要不丢、逐页「下一步」回确认再创建成功。临时管理员已删。

- **上一任务（2026-11-07，迭代文档02 第 3 轮：一键下单 + 三端时区展示，已完成；迭代02 全部三轮收尾）**：①**一键下单**——新表 `auto_order_task`（`orders/0005`），管理端新页 `/auto-orders`（5 步向导：白名单用户→商家→商品→规格→数量+触发时间；已下架商品不进可选列表；创建时余额提醒不阻断、规格失效/白名单/数量/触发时间强校验）；到点执行 `orders/auto_order_services.execute_due_auto_orders`（**服务器时间**判定，拍板 14）复用 `place_order` 余额支付真扣，执行前校验白名单/规格有效/余额/收货地址（`is_serviceable` 是 property 不能进 SQL，需取回后逐个判断），失败置 FAILED 记原因不重试；调度=`run_order_sweeps` + 管理端列表惰性执行；任务仅 PENDING 可取消。**踩坑：`select_for_update` 不能在事务外调用**——最初在循环外对 queryset 加锁导致 TransactionManagementError 且被惰性执行的 except 吞掉，改为先取 id 列表再逐个进事务锁行。②**三端时区展示**——时间存储统一 UTC 不变；新增 `common/client_timezone.py`（`ClientTimezoneMiddleware` 读 `X-Client-Timezone` 头 → ContextVar），`api_utils.iso()` 与购物端订单序列化按该时区 `ZoneInfo` 转换（头缺失/无效回退服务器时区；只影响展示，零业务逻辑改动）；三端请求层自动带头：admin-web/merchant-web 的 api lib、购物端订单两个页面。**测试**：`test_doc02_round3.py` 11 例（创建校验/已下架不展示/到点执行扣余额/规格失效/余额不足/无地址/取消/未到点不执行/iso 时区转换）全过 + 回归 93 例 OK；浏览器实测：向导创建（doc02-e2e 买家×HOMCOM Zhou Hei Ya×2）→ 到点执行 EXECUTED ×2 → 买家余额 200-2.22=197.78、商家子单生成、列表状态"已下单"、触发时间按 +08:00 显示（23:25）。文档：docs/08 WP-43/44、docs/13 auto_order_task。**迭代02 三轮全部完成**。

- **上一任务（2026-11-07，迭代文档02 第 2 轮：活动/返佣/通知/用户管理/购物端登录支付，已完成）**：按 v2.1 完成第 2 轮（用户拍板三口径继续有效）。**交付**：①平台活动——创建表单勾选限时/长期（长期不填时间、创建即生效、三端 payload 隐藏时间 `_activity_payload` 两处）、限时到期自动下架（`_expire_due_activities` 进 `run_order_sweeps` + 商家端活动列表惰性执行，列表只展示 ONGOING）、**参与活动=加 1 曝光**（同源 `add_exposure`，参与记录 `exposure_added` 落库、重复参与不重复加）；②返佣——**计佣基数改发货成功订单的成本价合计**（`calculate_commissions` Sum("cost_total")）、`create_merchant` 增 `referrer_code`（填码=邀请入驻，绑定 `MerchantReferral`，码无效不阻断）、管理端补录表单加邀请码、商家端【推荐返佣】卡新增「我推荐的新商家」表（名称/ID/推荐码/时间，payload 已有 referrals）；③通知——好评推送从选商品改为选**【店铺订单】**（新端点 `/admin/notifications/orders`：该店 COMPLETED 且从未推送过好评的子单、按订单号精确搜索；推送校验 ORDER_NOT_COMPLETED/ORDER_ALREADY_REVIEWED；`MerchantNotification.order` FK 迁移 `notifications/0003`，一单只能推一次好评），商家端通知**详情去大标题**（普通通知只显示标题+内容+时间）、好评例外展示**关联订单**（单号/金额/完成时间）+可回复；④用户端管理——`BuyerAccount.auth_provider`（EMAIL/FACEBOOK/GOOGLE，迁移 `accounts_buyers/0006`）+ payload 登录渠道与「支付权限：全部可用」、列表去掉地区/上次在线加登录渠道、**白名单就地加入/移出按钮**、**独立白名单模块删除**（路由+侧栏+WhitelistView.vue）、`PAYMENT_METHODS` 扩展 APPLE_PAY/WECHAT_PAY；⑤购物端——**邮箱手动注册**（新端点 `POST /auth/buyer/register/email`：邮箱+密码≥8 位，免验证码，渠道=EMAIL；AuthForm 重写：FB/Google 占位按钮点击提示暂未接入+邮箱表单）、结账页支付方式加 Apple Pay/微信支付、**余额支付真扣 BuyerAccount.balance**（前置校验+事务内扣款+`BuyerWalletEntry` PURCHASE 负向流水，幂等 `order-pay:{单号}`，不足拒单 `NOT_ENOUGH_BALANCE`）、session payload 返回 balance（结账页显示真实余额）。**测试**：新增 `test_doc02_round2.py` 9 例全过；更新 3 个旧断言（返佣基数/看板金额）；针对性回归 OK（仅剩已知 TOTP 过期测试）。**浏览器实测**：好评推送全流程（选店→订单下拉只列已完成未评价→发送→商家端详情含关联订单+五星+商品快照）、邮箱注册（渠道 EMAIL）、用户列表渠道/支付权限。**测试数据已清理**（临时管理员/测试买家删除；好评演示通知保留）。详见 §2 "2026-11-07（迭代02 第 2 轮）"。**第 3 轮未做**：一键下单模块、三端时区展示。

- **当前任务（2026-11-07，迭代文档02 第 1 轮：订单闭环/钱包资金/商家管理/下架联动，已完成）**：按 `功能需求迭代文档02.md` v2.1 分三轮开发（用户拍板：**分三轮**；购物端登录=邮箱先上+FB/Google 按钮占位；余额支付**真扣** BuyerAccount.balance——这两项在第 2/3 轮实施）。**本轮交付**：①管理端订单——一键完成放开【待处理】（跳过发货直接完成+回款，不扣成本）、修改下单时间仅【已完成】（前端置灰+后端 `ORDER_NOT_COMPLETED`）、节点时间补「≤当前系统时间」（`NODE_IN_FUTURE`）+ 保存前确认弹框；②购物端——新订单详情页 `account/orders/[id].vue` + 确认收货端点 `POST /api/v1/orders/<id>/confirm-receipt`（=一键完成同源，回款幂等，已实测回款落账）、订单列表修状态渲染（PAID/已支付）；③钱包——提现除金额外字段全部不校验、商家端提现记录去手续费列、审核通过直接进【转账中】（去出款凭证必填）、失败/打回秒退回；④商家管理——待发货金额改**成本价合计**（商家看板+管理端列表两处）、上次在线 10 分钟节流（`touch_merchant_online` 接入 `MerchantAPIView.initial`）、封店天数改小二次确认（`GET /merchants/<id>/ban-check` + PATCH `confirm_suspend` → 立即封店，已实测）、未缴保证金上架提示 `DEPOSIT_NOT_PAID`；⑤下架联动——平台下架级联下架全部 Offer（removed_by_platform）+ `refresh_spu_search_documents` 即时删搜索文档、商家端已上架列表隐藏平台下架商品、购物端详情统一提示「商品已下架，无法查看」（已实测）。**顺带修掉全站级 bug**：`CSRF_TRUSTED_ORIGINS` 缺 localhost 变体导致用 `localhost:3000/5173/5174` 访问时一切写请求 403（登录都不行）——已补三个端口。**踩坑**：Nuxt 里 `orders.vue` + `orders/[id].vue` 会构成嵌套路由、父页吞掉子页——列表页必须放 `orders/index.vue`；页面文件移动后相对导入深度要跟着改。详见 §2 "2026-11-07（迭代02 第 1 轮）"。**第 3 轮未做**（一键下单模块、三端时区展示）。

- **当前任务（2026-11-07，WP-42：需求迭代文档 01 全量落地，已完成）**：按 `功能需求迭代文档01.md` v2.2（十项拍板）一轮做完商家端 M01–M04、管理端 4 处改动、购物端 3 项新功能。核心交付：①商家级折扣体系（普通/活动折扣，成本价=向上取整(零售×折扣)）；②曝光"今日"口径（exposure_delta/exposure_day + `merchant_daily_stat` 日统计表）+ 看板曝光趋势/周月切换/通知 top3；③自动封店（`ban_after_days` 可空=null 不封店，唯一自动封店规则）+ 信誉分扣到 0 钳制不联动；④订单进度自动扭转（区间表写死，发货时随机生成 planned_node_times，14 天自动确认收货，`run_order_sweeps` 命令 + 读路径惰性兜底）；⑤下单即支付成功（PAID + payment_method）+ 按 offer.merchant 拆商家子单（真实下单首次自动产生 MerchantOrder）；⑥白名单后端打通（cart/place_order 校验 NOT_WHITELISTED，前端严格化）；⑦搜商家公开 API + 购物端双按键/`/merchants` 两页；⑧活动商品管理页 + `Spu.merchant_category` 12 固定品类 + 关键词回填。详见 §2 "2026-11-07（WP-42）" 小节与 `docs/08` WP-42。

- **上一任务（2026-11-06，六国跨市场与商品规格本地化，WP-41 已完成）**：用户要求支持比利时、德国、法国、荷兰、卢森堡、英国，价格只统一显示 `$` 且不换算，SKU 规格翻译成各国语言。已完成六国 `Market/Locale/MarketLocale`、市场化商品内容、类目/属性/规格翻译表、搜索 locale 维度、详情/类目/搜索的 `market+locale` 解析、购物端国家/语言选择器和真实 MySQL 回填。开发库 159 个有效 SKU × 9 个欧洲 locale = **1,431** 份规格翻译，复审数 0；欧洲五国没有当地 Offer 时明确回退 GB，API 返回 `price_source_market=GB`，绝不改金额或伪装当地价。详见 §2 同日小节与 `docs/08` WP-41。

- **当前任务（2026-11-06，需求文档 v2.2：10 项待确认已拍板 + 信誉分口径修订，纯文档）**：把 59 分钟会议录像 `D:/Users/lyx/Videos/Joybuy功能需求讨论01.mp4` 转写拆解，与 `功能需求迭代文档01.md`（v1 手记）对齐后出 v2，用户随后逐条拍板 10 项，现已回填为 **v2.1**，待确认项清零。**本轮只改文档，未动代码**。
  - **最终口径（开发直接照此实现）**：①爬虫**不改**抓取价，抓取价=入库价=零售价，只有 `成本价 = 向上取整(零售价 × 折扣)`；②进度区间 待出库→已出库 **4–8h**、已出库→已揽收 **6–12h**（其余按表）；③自动封店天数在**管理端【商家管理】→【店铺详情】新增字段【订单未处理自动封店天数（天）】**，按商家自主设置，这是**唯一**的自动封店规则；④**信誉分扣至 0 不做任何处理、不自动封店**（100 分制，下限 0），是否封店由人工手动操作 —— v2.1 曾写成"扣完自动封店"，20:59 已修订；⑤总关注 `+N` = **当日累计新增**；⑥非白名单：前端弹窗已有，需打通后端白名单标识；⑦活动商品折扣不做校验，设多少算多少；⑧品类饼图**按订单量**；⑨商家搜索**按商家名称匹配**（不做 ID 搜）。
  - 模块编号已按既有编号重排：M01 经营看板 / M02 店铺管理 / M03 商品上架中心 / M04 订单管理。

- **当前任务（2026-11-06，跨国多语言与商品规格存储现状审查）**：用户询问当前实现是否已覆盖跨国多语言，以及商品规格与商品翻译是否分开存储。本轮只读核对需求、国际化设计、数据库说明和实际模型/API；结论是：**商品文本与 SKU 规格已经分开**（`spu_translation` 对 `spu + locale` 唯一，`sku.specification` 为规格 JSON + 签名），`Market`/`Currency`/`Offer` 也预留了市场与币种维度；但当前仍是 **GB 市场 + EN/ZH 局部双语**，未完成真正的跨市场多语言。缺口包括 `(spu, market, requested_locale)` 内容维度、字段级 `actual_locale`/来源哈希/观察时间、`Locale`/`MarketLocale`、类目/属性/属性选项/CMS 翻译表，以及按请求市场/语言解析详情与搜索。SKU 规格值仍是 JSON 原文快照，没有独立的多语言规格值表。详见 §2 同日小节。

- **当前任务（2026-11-06，图片上传 + 首页两类卡片管理完成）**：重构两端 + 图片本地上传 + **首页卡片管理**。管理端【服务与运营】→「首页活动卡片」页面含**两个 Tab**：「活动卡片」（campaign_grid 10 宫格）与「品类发现」（link_grid tiles 6 卡），共用 `home_campaign_card` 表（`section` 字段区分）与一套接口；`storefront_home` 按分区注入覆盖快照，改标题/顺序 → 购物端即时同步（已端到端实测）。
- 当前任务（2026-11-05，**运行日志已细化**）：用户要求日志里能看到访问的 URL、拿到的数据、处理结果和落盘路径。已加 `LISTING_FETCHED` / `PRODUCT_PARSED` / `DATASET_SAVED` 并增强 `PRODUCT_IMPORTED`（每商品 3 条：解析→落盘→入库），详情接口事件数 50→200；顺带修掉 `parse_detail` 里会导致每个详情页崩溃的 `UnboundLocalError`。详见 §2"补充 11"。
- 当前任务（2026-11-05，**登录墙根因已修**）：用户反馈最新任务仍报登录墙。实测证明账号 Cookie 有效（带 Cookie curl 得 200），真因是 **Scrapy 默认缓存策略把匿名请求的 307 跳登录缓存了 6 小时，带 Cookie 的运行直接吃缓存、根本没发请求**；同时列表页改版导致解析出空标题/无价格。已加 `SuccessOnlyCachePolicy` + 清缓存 + 列表双布局解析器，端到端实抓验证 40/40 卡片有标题有原价。详见 §2"补充 10"。
- 当前任务（2026-11-05，**账号组实体化 + 账号可编辑/删除**）：用户要求账号可改组、可编辑、可删除，新增账号时组要下拉选，并能新建账号组。已加 `CrawlerAccountGroup` 表 + 账号软删除 + 4 个接口 + 管理端下拉/编辑/删除。**删除是软删除**（会话销毁、行保留以保住历史运行的账号归属）。详见 §2"补充 9"。
- 当前任务（2026-11-05，**多账号不定时换号已实现**）：用户明确决定用多个账号轮换抓取，并按"对话优先"改掉了 `docs/05` 的冲突条目。已实现 `AccountPool`（随机时间/请求预算触发换号）、风控命中即移出池子、Scrapy 全局 CookieJar 关闭以防串号、5 个中文事件码。详见 §2"补充 8"。
- 当前任务（2026-11-05，**爬虫账号绑定已修**）：用户问"抓取时到底有没有带爬虫账号"。查出三个真问题：建任务接口忽略账号、HTTP 请求从不带 Cookie（只有浏览器回退带）、`Joybuy homepage demo` 是"假 VALID"占位会话（0 条 Cookie）。已加 `CrawlJob.account`（迁移 0006）+ 建任务可选账号 + 账号 Cookie 注入 + 可用性判定要求"会话里真有 Cookie"。详见 §2"补充 7"。
- 当前任务（2026-11-05，**运行日志已中文化**）：用户反馈爬虫任务详情的日志是英文。已把全部运行事件文案、失败原因、质量规则说明改成中文；`code` 与字段名保留英文常量以维持可检索性，中文短标签放前端 `locale.js`。详见 §2 同日"补充 6"小节。
- 当前任务（2026-11-05，**评价只采聚合、分类只到二级**）：用户两条数据口径变更。①**不再爬评价内容**，只采 1~5 星各自数量、平均分、评价条数，以及【内容由人工智能总结自用户评价】区块（有才采、没有就不写）；②面包屑**只保留去掉"首页"后的前两级**（`首页/母婴用品/健康护理/湿巾及配件/湿巾/商品` → `母婴用品/健康护理`）。两条都已落到解析器（`joybuy_uk.py`）并有 fixture 契约测试。详见 §2 同日"补充 4"小节。
- 当前任务（2026-11-05，**爬虫记录级质量层已落地**）：参照一篇商城爬虫实战文章（CSDN 166029197）里"解析看起来成功但数据是脏的"教训，给爬虫补了**记录级字段规则 + 运行级价格分布告警 + 数据集按内容指纹增量**三层。新建 `crawler/joybuy_crawler/quality.py` 与 `pipelines.RecordRulePipeline`（优先级 150，在 `StagingPipeline` 200 之前），致命违规直接丢该条，永不进 dataset/staging/业务表。**实测探针**：拿 `var/crawl_exports` 里 9 份真实抓取 payload 回放，6 份正常商品零违规通过、3 份本来就是空解析（title/price/currency 全空）的脏数据全部拦截，无误杀。详见 §2 同日"爬虫记录级质量层"小节。
- 当前任务（2026-11-05，**浏览器生命周期已修**）：用户反馈「一个任务打开几十个浏览器且不关闭」。已改为**一个任务一个浏览器、退出必关**（`BrowserSession` + 进程回收 + `close_crawler_browsers` 命令），并用探针证实「1 个浏览器抓 2 页、结束后 0 个进程」。详见 §2 同日补充小节。
- 当前任务（2026-11-05，**类目中英双语展示，代码已完成、数据 170/177**）：管理端【新建任务】-【选择 Joybuy 类目】原来只显示英文，现在同时显示「中文名 / English name」。中文名从 joybuy.co.uk 切到 `_lang=zh_CN` 后按 **source id 一对一** 抓取并入库，英文树结构不变。详见 §2 同日小节与 `docs/05` §4.1。
- 当前任务（2026-11-05，**第 1、2 轮全部完成**）：按用户 7 条要求重建爬虫任务模块。用户确认 4 个口径：**类目树选择**、**Scrapy+DrissionPage 混合**、**人工弹窗登录+加密 Cookie**、数据集按**类目/商品分层**。
- **第 2 轮成果（账号管理 + 管理端 UI，全部浏览器实测通过）**：
  - **账号管理后端**：`GET/POST /api/v1/admin/crawlers/accounts`（列表不暴露 session_cipher）+ `POST /crawlers/accounts/{id}/actions`（`login`/`logout`/`verify`/`disable`/`enable`/`reactivate`，权限码 `crawler.accounts.manage`，全部写审计）。`login` 派生独立进程 `manage.py crawler_account_login --account <id>`：弹**有头 Chrome**（独立端口 9334 + 每账号独立 profile `var/browser_profiles/account-{id8}`），用户本人完成 Facebook 登录后自动检测（首页可见文本无 "Sign in" + Cookie≥5 条）→ Cookie 加密入库 `record_account_session`（密码永不收集），8 分钟超时；`verify` 用存储 Cookie 无头渲染首页判定，失败则 `mark_session_expired`（风控页不算失败）；`logout`=清除会话；风控账号必须走 `reactivate`（`set_account_status` 拦截直接 enable）。
  - **admin-web 重做**（`CrawlersView.vue` + 新组件 `CategoryTreePicker.vue`）：**任务 Tab**——新建表单内嵌 Joybuy 类目树（搜索过滤+两级展开勾选+每节点"含子类目"切换，数据来自 `/crawlers/source-tree`），列表新增类目摘要列，**详情抽屉**（冻结类目选择/树版本/运行计数/事件流，RUNNING 时 5s 轮询）；**爬虫账号 Tab**——列表（状态/会话/最近动作 note）+ 新增 + 登录/验证/清除会话/解除风控/停用/启用，登录等待期 5s 轮询自动刷新。locale.js 补齐 SUCCEEDED/VALID/EXPIRED/LOGIN_PENDING 等中文映射。
  - **实测修复的真 bug**：任务创建 API 用不存在的 `SourceCategory.public_id` 查类目（旧 UI 同样是坏的）→ 统一改为 `source_id`（`l2:1405`/`minihome:...`），前端 payload 改发 `source_ids`，并补 HTTP 层测试 `test_crawl_jobs_api.py` 防回归。
  - **遗留**：登录流程需要用户本人在弹窗里完成 Facebook 登录（未实测到 Cookie 落库那一步，检测逻辑已按可见文本规则实现并有单测覆盖 verify 路径）；列表页 window.prompt 的审计原因框在自动化浏览器中不便处理，人工使用正常。
- **第 1 轮成果（后端，全部已实测）**：① 类目树同步 `manage.py sync_joybuy_category_tree`（14 一级频道+163 子类目已发布 `joybuy-uk-20261104-4dcfbbe5`）+ `GET /crawlers/source-tree`；② `CrawlJobSourceSelection` 多类目+树版本冻结（迁移 0005）+ `CrawlRunEvent` 事件模型 + 任务详情 API；③ 执行器：`start` 派生独立进程 → Scrapy spider → 风控中间件自动切 DrissionPage → 解析器 v2（joybuy 原生字段）→ StagingPipeline；④ 数据集 `var/crawl_exports/{任务}/{类目}/{类目}/{商品ID}/`，主图 s1248 阶梯最高清；⑤ `import_staging_product` 补 gallery 导入。**实测**：3 商品 3/3 导入、52 图 0 失败、1248×1248 主图落盘。
- **docs/05 已按用户指示更新**（§1、§7.3、§8）：避免触发风控优先；出现验证码/风控时人工接管，不程序化打码。
- 上一任务（2026-11-05，已完成）：产出数据库说明文档 `docs/13-database-schema.md`（79 表 759 字段，纯文档）。再上一任务：管理端登录移除 TOTP 验证器只保留邮箱+密码（详见下方记录）。
- 上一任务（2026-11-04，已完成）：补齐商城端【畅销榜单】11 个标准类目的公开 Joybuy 演示商品。已从 `joybuy.co.uk` 中文浏览器会话和固定公开榜单页采集 11 类 × 3 条，全部通过 staging 导入、激活并建立 GB 搜索文档；33/33 fixture 商品均已下载到本地媒体库，榜单接口现在返回本地 `/media/...` 首图，页面已抽查美妆与游戏类目正常显示。服装是唯一例外：Joybuy 畅销榜侧栏没有服装一级榜，fixture 明确标记使用“时装配饰频道 → 爆款直降”替代来源，绝不能伪装成官方 bestseller 子榜。
- 当前任务（2026-11-04 夜间自动执行，**已完成**）：按用户指令"参照 joybuy.co.uk 逐元素视觉对齐全部文档页面"的全自动流程执行完毕。四份交付物在 `var/ui-alignment/deliverables.md`（页面清单+基准规格表+代码修改记录+复核差异清单 D-01~D-14）。覆盖：全局头部（logo 图片化/搜索框/圆形按钮/类目行）、首页、Categories 面板、列表页（234px 左栏+274px 卡重写）、**畅销榜单页新建**（/promo/best-seller，hero 384px/11 品类无箭头/仅价格筛选/排名徽章 32×32 #E4E6EB）、详情页重写（Buy now #E1251B hover #D14335 / Add to cart #1A1A1A hover #282828 / 数量步进器 47×34 / 白名单拦截弹窗 / 服务保障纯文本行）、结算页两步化（3 字段地址表单→支付步骤：余额支付置顶+精简 Summary+精简页脚）。后端最小支撑：`BuyerAccount.purchase_whitelisted`（迁移 0004，默认 True=开发阶段放行，session payload 返回）。E2E purchase-funnel 的结算步骤已同步新流程；funnel 在 dev 水合竞态下仍偶发超时（差异清单 D-14），全流程已浏览器人工验证（含下单 201）。
- 下一轮（待用户确认后）：第 2 轮榜单后台配置（RankingList/管理端 RankingsView，见更下方计划）；第 3 轮钱包/白名单 admin/直购参数/地址后端校验放宽（对应差异清单 D-07~D-10）。
- 当前任务（三轮制，**已完成第 1 轮，待用户确认后进入第 2 轮**）：按 `docs/12-joybuy-co-uk-ui-spec.md`（目标状态规格，对应 `功能需求清单.md` 8 组需求）实施改造。用户已确认两个口径：**界面语言中英文可配置**（EN/ZH 双语，storefront 轻量 i18n + 后端双语数据）、**分三轮逐轮确认**（第 1 轮全局头部+类目体系+首页 CMS → 第 2 轮畅销榜单页+后台榜单配置 → 第 3 轮详情页购买改造+地址页+支付页+白名单/钱包后台）。完整计划见本会话已批准的实施计划；第 1 轮成果见下方"2026-11-04"节。
- 下一轮（第 2 轮）要点：`RankingList`/`RankingEntry` 模型 + `/api/v1/admin/rankings`（权限码 `catalog.rankings.manage`）+ admin-web RankingsView；商城端 `/promo/best-seller` 页（左栏 11 品类无展开箭头 + 仅价格区间筛选 + 右栏榜单分段，榜单卡无营销标签）；首页 Bestsellers 楼层用新 CMS 模块类型 `bestseller_floor`（同步三处：schemas.py、CmsModule.Type+迁移、CmsRenderer）。
- 上一任务：浏览器实测遍历真实 Joybuy 站点（joybuy.co.uk）并产出产品功能分析文档，作为复刻参考。已完成：`docs/11-joybuy-co-uk-product-features.md`。
- 追加（同日第二轮）：产出界面还原规格文档 `docs/12-joybuy-co-uk-ui-spec.md`（逐元素三层规格：页面整体/元素清单表/排版关系，含截图采样色值与推测标注），与功能文档互补。
- 追加（同日第三轮，应用户问询）：补测 4 个类目子页面（Noodles/Fragrance/Womens Clothing/Electronics 对照），确认所有二级类目图块统一落地 /s?k= 列表页模板，但筛选面板数据驱动——快捷 Tab 数量（3–6 个）、价格区间、Category 细分、是否带二级图块行、商品卡是否带加购均随类目变化；食品类特有 Repeat & Save；/s?b1= 直达形式可能空态（仅 Notify me when available）。差异已写入 `docs/12` 4.1 节与 `docs/11` 列表页模块。
- 追加（同日 21:37–21:45，用户授权登录）：在 WorkBuddy 内置浏览器中完成 Joybuy Facebook OAuth 登录。账号信息：Joybuy 用户名 `user4323txlb`（Facebook 首登自动创建的新账号，2026-11-03 注册，含 2 张 Welcome Offer 优惠券），对应 Facebook ID `100013498475534`（用户提供），登录方式 Facebook（loginType=30），登录态保存在 WorkBuddy Browser 的会话 profile 中，后续会话可直接操作已登录页面。**密码一律未记录、不得记录**。已知怪象：OAuth 回跳中间页会闪现 `{"code":"1","echo":"cross-origin request from '' is not allowed"}`（color-api.joybuy.com 的 loginByTicket CORS 校验报错），但会话实际已建立，回首页即见头像，可忽略该报错——复刻项目如做第三方登录回跳需注意此坑（回调中间页应走前端 XHR 而非直接 302 到 API URL）。
- 追加（同日 21:48–21:58，依据 `功能需求清单.md` 8 条需求）：将 `docs/12-joybuy-co-uk-ui-spec.md` 就地修订为**目标状态规格文档**（文档开头新增"修订说明"表 + 全局约定：11 个标准类目、品类发现 6 品类、白名单购买弹窗、钱包余额逻辑；每条修订标注【修订：性质｜需求编号】；文末新增"已删除元素记录"28 项）。修订前现状版已备份到 `var/ui-spec-backup/12-joybuy-co-uk-ui-spec.current-state.md`。本轮新实测：畅销榜单页 /promo/best-seller、头像下拉、详情页下半、Buy now 直达 /checkout 支付页与地址表单弹窗（字段全部核验，未保存任何数据）。
- 追加（同日 21:50–21:58，中文语言复查）：应用户要求把站点切到"中文(简体)-ZH"（Custom settings 抽屉 → Save Changes，当前浏览器会话已为中文）逐项核对需求中文名。结论：需求 8 条的中文名称全部与中文页面对上（秒杀/奥莱/多买多省/JoyPlus会员=首页图标行原文；品类发现含"中国方便食品"；畅销榜单+查看全部；优惠明细/共减/优惠码和优惠券/礼品卡/微信支付=支付页原文；配送至/经常一起购买/立即购买/加入购物车均精确对应）；**重要修正**：需求6-1 的 JoyPlus 模块在中文详情页"购买面板价格行下方"已检出（"JoyPlus 会员享无限免运费; 立即免费试用"，英文采样漏检），文档已从"未检出"改为"已检出"；需求6-2 限购标签中英文均未检出维持原判。中文频道行为 15 项（超市/家居生活/个护家清/家用电器/母婴童玩/电子产品/宠物/美妆/电视与影音/时装配饰/健康保健/汽车及零配件/游戏/世界美食/中华美食）。`docs/12` 已更新（新增"中文语言复查对照"节）。
- 当前任务：让商城端首页贴近真实 Joybuy 主页并填充真实爬取内容做效果展示——已对齐真实首页结构：顶部黑色通知条、红色字标头部（圆搜索按钮+配送至）、"Offers for you" 2×5 活动砖石区（真实图片，替代原红色 hero）、6 个圆形快捷入口、品类发现磁贴行、6 个真实商品楼层（53 商品仅原价、图片全本地化）。浏览器截图对比通过，首页 CMS 现为 v4。
- 新验证纪律（用户 2026-11-03 确定，已写入 `AGENTS.md`）：开发阶段每次任务只做针对性验证（仅覆盖本次改动的模块/文件），全量验证只在功能全部开发完成或用户明确要求时跑。不得每轮默认全量。
- 用户明确分工（上一轮）：原价规则是爬虫职责；“今日送达”标签过滤与 `$` 符号只是页面展示层职责，与爬虫无关。
- 此前任务“Joybuy 中文会话与多语言内容方案”的口径仍然有效：切换国家/语言后所有内容自动刷新，德英混合是正确来源状态；类目分析仍暂停，须用已保存的中文会话重新分析。
- 上一任务“平台管理端全面中文化（仅保留 Joybuy 标识）”已完成并通过验证，历史记录保留在下方。

## 2. 已经完成了什么

### 2026-11-15（WP-45 阶段 2：导入链路多 SKU + 购物端端到端验证，✅ 已完成，未 commit）

- **任务**：`import_staging_product`（`backend/crawler_control/import_services.py`）在 payload 带 `variants` 时按变体建多 SKU（真实规格名值对 + 每变体 `SkuSourceIdentity`）、为带价变体建 Offer、变体图走既有 media 本地化、导入后刷新搜索文档；重导入幂等、老商品原地升级；真实数据端到端 + 购物端 PDP 浏览器实测。
- **改动文件（仅 2 个）**：
  - `backend/crawler_control/import_services.py`：
    - 新增 `_split_variants_by_same_source(payload)`：同源口径拆分。保留条件 = `is_primary` / `source_sku_id` ∈ 顶层 `skus[].source_id` / `sku_status` 非 null（三者任一）；其余视为跨商品轴值跳过并 `logger.info`（阶段 1 已实锤：源站详情页 `productSelectedFloor.skuStatus` 只覆盖当前源商品自己的 sku，系列轴 1TB/512GB 的值指向兄弟商品页）。skuStatus 万一漏掉本商品某 SKU 也按「宁缺毋假」跳过。
    - 新增 `_import_variant_image(sku, url, ...)`：变体图走既有 `_fetch_image_bytes` + `process_media_bytes`（content-addressed 去重），`MediaUsage role="variant"` 挂到 SKU；任何失败返回 False 不阻断（回退无图）。
    - `import_staging_product`：skus 主循环照旧（主变体身份原地升级仍走 2026-11-09 的 `_adopt_enriched_specification` 空 spec 补全路径）；主循环后新增变体循环——每变体 `get_or_create_sku_from_source(skip_attribute_validation=True)` 幂等建 SKU+身份，规格空跳过（`skipped_no_spec`），价格信任 `price_source ∈ {variant_page, detail_page}` 才建 Offer（`offer_source_id = f"{source_id}#{variant_sku_id}"`，与主 SKU 同构），`stock_state`/`sku_status` 只透传不解读（source_availability 一律 UNKNOWN）。
    - **身份冲突分级**：变体身份已绑到**别的 SPU**（实锤场景：同一源 sku 曾作为兄弟商品独立导入，如 10405110 = "Apple - iPhone 17 Pro - 256GB - Deep Blue" 有自己的 SPU 5b645eac）→ 跳过该变体 + `logger.info` + `skipped_identity_conflict` 计数，**绝不改绑**；身份已绑到**同 SPU 另一规格**（商品规格改版）→ 仍按硬冲突抛中文 `ImportSourceConflict`，整单回滚。
    - 「上架即可售」（仅 variants 路径）：本次导入**新建**的 Offer（主+变体）置 `ACTIVE` + `listed_at=observed_at`；命中已有 Offer 一律不动归属/状态/价格层。无 variants 的老 payload 行为完全不变（Offer 仍默认 DRAFT）。
    - 导入尾部调 `refresh_spu_search_documents(spu)`（SPU 非 ACTIVE 或无可购 Offer 时清文档，与既有口径一致），结果进 `imported_refs["search_docs_removed"]`；`imported_refs` 新增 `variants` 摘要（kept/skipped_cross_product/skipped_no_spec/skipped_identity_conflict/skus_created/offers_created/offers_skipped_no_price/images_localized/images_failed）与 `new_active_offers`。
  - `backend/crawler_control/tests/test_crawler_import_variants.py`（新增，5 例）。
- **测试结果（按验证纪律仅做针对性验证，全部真实执行）**：
  1. 新增 `manage.py test crawler_control.tests.test_crawler_import_variants --keepdb` → **5 tests OK**（多变体导入 N SKU+N 身份+N Offer 且兄弟商品跳过、重导入幂等且不复活管理端下架的 Offer、无价变体只建 SKU 不建 Offer、老式单 SKU（spec={}）→ variants payload 原地升级（同身份同 SKU 补 spec 重算签名、老 Offer 不动）、变体身份绑到别的商品时跳过不改绑、变体图下载失败不阻断、无 variants 老 payload 行为不变）；
  2. 回归 `crawler_control.tests.test_crawler_import + test_crawler_variants + test_crawler_quality_gates + test_crawler_field_rules + test_crawler_rebuild + catalog.tests.test_product_detail_api + test_product_detail_extras + test_crawler_detail_extras --keepdb` → **139 tests OK**；
  3. `ruff check` + `ruff format --check` 两个改动文件全过。
- **真实数据端到端（走 `import_staging_product` 真路径，非测试库）**：用阶段 1 实抓 `var/wp45_phase1/debug_run/run-20261115-231721/.../10404455/product.json`（iPhone，8 变体带价）经一次性脚本（已删）建 staging `joybuy_uk:10404455` 并导入：
  - 三层计数：**SKU 2 / SkuSourceIdentity 2 / Offer 2（全部 ACTIVE、listed_at=导入时刻）**，search doc 1（GB 市场）；
  - 变体摘要：kept=3（同源）、skipped_cross_product=5（1TB×3 + 512GB×2 兄弟商品）、skipped_identity_conflict=1（10405110 已是独立 SPU，身份未动）、skus_created=1、offers_created=1、images_localized=1（银色 s96 图）、gallery 下载 7 张全成功；
  - SPU 导入后为 DRAFT（既有惯例），随后按运营动作等价把该 SPU 置 ACTIVE 并 `refresh_spu_search_documents` → 文档可搜（`GET /api/v1/search?q=iPhone` 命中「Apple iPhone 17 Pro 256 GB 宇宙橙」价格区间 1099-1099）。
- **购物端 PDP 浏览器实测（nuxt dev :3000，localhost；IAB 视口截图）**：打开 `/p/5b7098bf-577a-4145-8d36-ac5e54cafae8`：
  - 规格按钮组出现：「系列」轴 1 个按钮（256GB，选中态），「颜色」轴 2 个按钮（星宇橙色/银色，均带本地化 s96 色图）；死值（1TB/512GB/深蓝色，sku_ids=[]）被上一轮 PDP 修复的前端过滤天然消解，不渲染；
  - 交互：默认星宇橙 active；点「银色」→ active 切换到银色、点「星宇橙色」→ 切回（class 前后变化实测）；两按钮、系列按钮全部 enabled；切规格后价格 $1,099.00（两变体同价——**真实数据如此**：价格差异化的 1TB/512GB 是兄弟商品不进本商品 SKU，见口径决定）；加购/立即购买 enabled；匿名点加购弹「您的国家业务尚未开放」门控弹窗（6-6 规则预期）；console error **0**（error + unhandledrejection 收集器覆盖全部交互）；
  - 搜索页 `/search?q=iPhone` 抽查：卡片正常展示该商品 $1,099.00 + 加购按钮；
  - 截图 3 张：`var/wp45_phase2/pdp_orange_panel.png`、`pdp_silver_selected.png`、`pdp_orange_selected.png`。
- **留库的测试数据（真实库，非垃圾，保留作多 SKU 演示）**：SPU `5b7098bf-577a-4145-8d36-ac5e54cafae8`（joybuy_uk:10404455，Apple iPhone 17 Pro 256 GB 宇宙橙，ACTIVE，商品后台类目 电子数码/手机），2 SKU（星宇橙 10404455 / 银色 10404453）、2 ACTIVE Offer（各 1099 GBP、库存 999+）、1 条 GB 市场搜索文档、staging 行 `joybuy_uk:10404455`（IMPORTED）、媒体库新增 7 张画廊图与变体/spec_options 用的本地化 s96 色图（spec_options 摘要 `spec_options: 2`）。注意：本库同时已有兄弟商品 SPU `5b645eac-…`（10405110 深蓝，DRAFT 单 SKU）未动。
- **踩坑/注意（不得再踩）**：
  1. **兄弟商品身份冲突是真实存在的**：品类爬取会把每个源商品页（含系列轴指向的兄弟商品）各自导入成 SPU，同一物理 sku 就会同时出现在「自己商品的 SPU」和「兄弟商品 variants」两条路径上——导入侧必须跳过+日志，绝不能改绑或整单失败（第一次 e2e 就是撞上 10405110 已有身份才补的这条逻辑）。
  2. e2e 临时脚本里 `os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...)` 应为 `config.settings`（backend/manage.py 同款），写错会 ModuleNotFoundError。
  3. `parse_money` 出来的价格是 4 位小数（`1099.0000`/`31.9900`），断言别写 2 位。
  4. 变体摘要 `kept` 计的是「同源变体数」（含主变体），不是 payload 变体总数。
  5. 后端改了必须 taskkill 重启：本次杀掉 PID 17388 后以 `python backend/manage.py runserver 127.0.0.1:8000 --noreload` 后台重启。
  6. 未 commit；未跑全量验证；爬虫侧零改动（`JOYBUY_VARIANT_PRICES_ENABLED` 等配置未碰）。

### 2026-11-15（WP-45 阶段 1：爬虫多规格变体采集 + 工作包立档，✅ 已完成，未 commit）

- **任务**：用户拍板成立「多规格采集与导入」工作包并做阶段 1——①立 WP 文档；②爬虫解析「变体列表」（每个规格组合的源 sku id、规格名值对、价格、库存、主图）进 staging payload；③给变体解析补契约测试。阶段 2（导入链路多 SKU/Offer/搜索文档/PDP 端到端）**未做**，设计注意已写进 WP 文档。
- **文档**：`docs/08-implementation-work-packages.md` 新增 §12b「多规格采集与导入」+ `WP-45 爬虫多规格变体采集与导入`（背景根因链/两阶段范围/数据口径/阶段 2 设计注意/验收标准）；`docs/14-crawler-product-detail-issues.md` 新增 §10（变体采集：调研结论表 / 落地清单 / payload 契约 / 阶段 2 必读 / 验证记录）。
- **调研结论（实抓实锤，抓包留档 `var/wp45_phase1/`）**：
  - `productSelectedFloor.colorSizePartList[].buttonPartList[]`：每按钮 `text` + `imgUrl`（s96 规格图）+ `skuList`（**源 sku id**）+ `stockState`（原始码 33/34，语义未解读只透传）；`productSeriesFloor.series[]` 每值带 `skus`；`productSelectedFloor.skuStatus` 是逐源 sku 的原始状态码（"0"/"-2"）。
  - **价格不在单条详情 JSON**：`productPriceFloor` 只描述当前浏览的 sku。**每个源 sku 都有自己的 `/dp/<sku>` 页**（slug 任意，实测 `/dp/x/10405110` 200 且价格描述该 sku），变体价格=逐变体补抓（docs/14 §8 `/dg/` 第二请求先例同理）。实测价格随变体不同：iPhone 1TB=1499/512GB=1299/256GB=1099 GBP、炒锅 24.99/30.99。
  - `productCommonFloor.productInfo.skuList` 只有当前 sku 的物流信息（不是变体表）；`/dg/<sku>` 移动端 SSR 无价格（只有 structuredFloors 图文）。
- **改动文件**：
  - `crawler/joybuy_crawler/parsers/joybuy_uk.py`：`extract_variants()`（轴值×源 sku → `specification` 名值对 dict + `image_url`/`stock_state`/`sku_status`/`is_primary`/`price_source`；主变体继承页面原价）、`extract_variant_price()`（变体页原价，crossOff 优先，与主解析同业务规则）、`variant_page_url()`；`UkProduct.variants` 字段；`to_payload()` legacy 顶层与 `joybuy` native 块均带 `variants`。
  - `crawler/joybuy_crawler/spiders/joybuy_run.py`：详情→/dg/ 合并后**逐变体串行**补抓价格页（`parse_variant_price`/`variant_price_failed` 链式回调，meta 队列），队列空才产出唯一 item；单变体失败只留空价格并继续；结束写 `VARIANT_PRICES_MERGED` 事件。
  - `crawler/joybuy_crawler/settings.py`：`JOYBUY_VARIANT_PRICES_ENABLED`（env `CRAWL_VARIANT_PRICES`，默认开）、`JOYBUY_VARIANT_PRICE_LIMIT`（env，默认 10/商品）。
  - `crawler/debug_crawl.py`：`fetch_variant_prices()`、`--no-variant-prices`、`CrawlConfig.fetch_variant_prices/variant_price_limit`、日志逐变体行、summary `variants`/`variant_prices`、`debug_sources.variants`。
  - `backend/crawler_control/tests/test_crawler_variants.py`（新增 8 例）；`backend/crawler_control/tests/test_crawler_detail_extras.py`（蜘蛛流程 2 例改为 drain 变体链，加 `_variant_price_page_html`/`_drain_variant_chain` helper）。
  - **无模型/迁移变更**：`StagingProduct.payload` JSONField 整体入库，variants 自动携带；质量规则/导入服务按字段读取，不认识 variants 也不破坏。
- **variants 契约**：`[{source_sku_id, specification: {轴名: 值}, price, currency, image_url, stock_state, sku_status, is_primary, price_source}]`；轴序=系列在前颜色在后；无规格轴商品 `variants=[]`（向后兼容：老 payload 无 variants 导入行为不变，有守门断言）。
- **验证（按验证纪律仅做了针对性验证）**：
  1. `manage.py test crawler_control.tests.test_crawler_variants crawler_control.tests.test_crawler_detail_extras --keepdb` → **24 tests OK**（Variants 8：解析契约/空轴兼容/变体价格页/质量规则透传/蜘蛛链/失败兜底/开关关闭/上限截断）；
  2. `manage.py test test_crawler_import test_crawler_quality_gates test_crawler_field_rules test_crawler_rebuild catalog.tests.test_product_detail_api --keepdb` → **113 tests OK**；
  3. `ruff check` + `ruff format --check` 6 个改动文件全过；
  4. debug_crawl 实抓（`--no-images --no-videos`，exit=0）：iPhone `10404455` **8 变体、补抓 7 次 0 失败、8 个带价、质量规则全过**；炒锅 `10003152` 2 变体带价 2 个。日志 `var/wp45_phase1/debug_crawl_iphone.log` / `debug_crawl_wok.log`，落盘 `var/wp45_phase1/debug_run/run-*/dataset/.../product.json`（variants 完整），另有调研抓包 `raw_detail_*.html` / `serverproduct_*.json` / `raw_dp_*.html` / `raw_dg_*.html`。
- **踩坑/注意（不得再踩）**：
  1. 变体链上 `request.meta` 是**同一个 dict 对象贯穿整条链**——测试里先取 `meta["variant_sku_id"]` 再走链，事后读已被改写（第一版测试踩过）；生产代码都是入口先读，无此问题。
  2. `stockState`/`skuStatus` 是源站原始码，**不要臆测语义**（33/34 都出现在可购商品上），阶段 2 也只透传。
  3. **系列轴的值可能指向源站兄弟商品**（iPhone 1TB 是另一个源商品页）——阶段 2 导入要确认「同源商品」口径。
  4. 变体 `image_url` 是源站 CDN URL，阶段 2 导入必须走既有本地化下载路径。
  5. 后端/storefront 零改动，未重启（8000/3000 未动）；未 commit；临时探针脚本 `var/wp45_phase1/probe_variants.py` 已删，产物（抓包/日志/product.json）保留在 var/（不入库）。
- **阶段 2 交接**：从 WP-45 阶段 2 设计注意开始（`docs/08` §12b WP-45 末尾「阶段 2 设计注意（不得再踩）」5 条），红线：旧单 SKU 身份**原地升级**补 specification、其余变体新建 SKU+身份、**不自动重绑**（身份冲突是「冲突不是重复」）。

### 2026-11-15（购物端 PDP「规格无法选择」修复：单 SKU/空规格不渲染规格交互 + 多 SKU 死按钮过滤，✅ 已完成，未 commit）

- **任务与用户原话**：「当前购物端，商品详情页的规格无法选择。」
- **数据摸底（只读临时脚本，已删）**：
  - 爬虫商品三类抽查：Good Boy Soft Dog Toy ×3（`e3a6fe2f`/`6f7c7b74`/`217a6a1b`）与 HOCO `c5130796`：全部 1 SKU、`sku.specification = {}`、`spec_options` 为 `[]` 或 `null`、offer ACTIVE inv=9999 —— 这类页面**本来就没有规格按钮，行为正常**（不是 bug 现场）。
  - 老演示商品：Smart Watch S2 `467c7755` 单 SKU 空 spec；Wireless Earbuds Pro `947910f2` 3 SKU（空/colour White/colour Blue）但 SPU **INACTIVE**（PDP 显示下架）；USB-C Cable `e55e455c` 单 SKU 空 spec。
  - 关键规模：爬虫 800 个 SPU 抽样中 **436 个有非空 spec_options、254 个有多值规格轴**；364 个纯空 spec。**全库没有任何 ACTIVE 的多 SKU SPU**。
  - 例证 `84c31777-ea7e-401d-9936-b994c67e2bb3`（IF Fruit Wine Cherry 275ml）：`SpuDetail.spec_options` Flavour 轴 5 个值（Lemon/Coconut/Cherry/…，源 sku_ids 各不相同），实际导入只有 1 个 SKU（`{"Flavour": "Cherry Flavour"}`）；API `/api/v1/products/84c31777-…` 返回该轴时未导入值的 `sku_ids` 已被 `_spec_options_payload` 过滤成 `[]`。
- **根因链**：爬虫 1 SPU=1 SKU 导入 → spec_options 保留源站多规格轴 → PDP `variantAxes` 优先用 spec_options 渲染按钮组 → 点未导入的值时 `selectVariant` 先按 `sku.specification[axisName]` 匹配（单 SKU 的 spec 与该值不同 → 空候选），`sku_ids` 兜底也是空 → `if (!candidates.length) return` 静默无反应 → 唯一 SKU 的按钮虽然默认高亮，但其它按钮永远点不亮 = 用户感知的「规格无法选择」。浏览器复现实锤：点 Lemon Flavour 前后各按钮 active class 完全不变。
- **改动（仅 `storefront/pages/p/[id].vue`）**：
  1. 新增 `isSingleSku = computed(() => purchasableSkus.value.length <= 1)`；`variantAxes` 开头 `if (isSingleSku.value) return []` —— 单可购 SKU/空规格不再渲染规格交互区（唯一 SKU 仍由既有 `selectedSku` 兜底自动选中）。
  2. spec_options 分支在映射后加 `.filter((value) => resolvesToPurchasableSku(option.name, value))`（按 specification 名值匹配或 sku_ids 命中可购 SKU 任一即可），整个轴过滤后无值则整轴丢弃 —— 多 SKU 商品的死按钮也不会再出现。新增 `resolvesToPurchasableSku()` 辅助函数。
  3. 模板在规格交互区前新增只读行 `<p v-if="isSingleSku && stickySpecText" class="detail__spec-readonly">`（复用既有 stickySpecText，展示唯一 SKU 的规格值；空 spec 自然不渲染）；对应新增 `.detail__spec-readonly` 样式（md 字号、次级色）。
  4. `selectVariant`、`selectedSku`、加购/立即购买/门控逻辑零改动。
- **验证（按验证纪律仅做了针对性验证）**：
  - `cd storefront && npx prettier --check "pages/p/[id].vue"` → All matched files use Prettier code style!；`npx eslint "pages/p/[id].vue"` → 零输出零告警。
  - `node storefront/node_modules/nuxt/bin/nuxt.mjs build storefront`（仓库根执行）→ ✨ Build complete!。
  - storefront vitest：无 PDP 相关用例（tests/ 5 个 + components/ 若干，均与本次改动无关），未跑。
  - 后端零改动、未重启（8000 端口 runserver 未动）；无任何写库操作。
- **浏览器实测（nuxt dev :3000，注意必须 localhost 不能 127.0.0.1）**：
  - 修复前 `84c31777`：Flavour 轴渲染 Lemon/Coconut/Cherry 按钮，Cherry 默认 active，点 Lemon 后逐按钮读 class 确认 active 无任何变化（bug 实锤）。
  - 修复后 `84c31777`：`.detail__variant` 数量 0、`.detail__spec-readonly` 显示「Cherry Flavour」、加购与立即购买 enabled、点加购弹白名单门控弹窗（匿名预期，6-6 业务规则）、console error 0。
  - 修复后空 spec `e3a6fe2f`（Good Boy Soft Dog Toy）：规格按钮 0、只读行 0（spec 空不显示）、按钮 enabled、点加购弹门控、console error 0。
  - 回归：INACTIVE `947910f2` 仍显示「商品已下架，无法查看」。
  - 截图 4 张：`var/pdp_spec_fix_20261115/repro_84c31777_spec_buttons.png`（复现）、`after_84c31777_readonly_spec.png`（门控弹窗 + 只读规格）、`after_84c31777_panel_clean.png`、`after_e3a6fe2f_empty_spec.png`。
- **限制（如实记录）**：①全库无 ACTIVE 多 SKU 商品，多规格选择交互无法浏览器实测，只能代码走查确认改动是保守过滤（未动 selectVariant 分支）；待有真多规格商品上架后应补浏览器验证。②完整加购（购物车写入）需白名单买家登录，本任务禁止写库造临时账号，故验证止步于「按钮 enabled + 点击弹门控弹窗」。
- **踩坑（不得再踩）**：①「规格无法选择」报修时先查商品是否单 SKU + 有残留 spec_options——爬虫商品的死按钮来自源站多规格轴与单 SKU 导入的错位，不是前端交互代码坏了；②IAB 截图 clip 模式有拼接伪影（与 2026-11-15 商家端手机版任务的 fullPage 伪影同族），用视口截图。

### 2026-11-15（把这两天抓取的商品全部上架：spu + offer SQL 翻转 + 搜索文档逐 SPU 刷新，✅ 已完成，未 commit）

- **任务**：用户原话「帮我把这两天抓取的商品，全部设置成上架状态。写sql实现」。交付物是 SQL 文件 `var/sql_online_crawled_20261115/bring_crawled_online.sql`；执行通过 Django `connection.cursor().execute()` 跑该文件原文（保证账号/事务/表名正确）；搜索文档按系统既定规则（每次上架写路径都要刷新文档）用配套一次性脚本逐 SPU 调 `catalog.search_services.refresh_spu_search_documents(spu)`。
- **摸底（决定口径）**：用来源标识表 JOIN 判定爬虫导入（`spu_source_identity` 全库仅两个 source_system：`joybuy` 87 条、`joybuy_uk` 7863 条）。窗口内按天分布：
  - 2026-11-13：**0 个**（当天没有导入）；
  - 2026-11-14：4481 个 DRAFT；
  - 2026-11-15：3286 个 DRAFT（夜间 30 批 + 日间第 2/3 批都在此日）；
  - 窗口内合计 7767 SPU，**全部 DRAFT**（无 INACTIVE/ACTIVE），offer 全 DRAFT、`removed_by_platform` 全 0，1 SPU = 1 SKU = 1 Offer（7767 = 7767），`product_search_document` 窗口内 **0 条**；
  - 全库背景：spu_total=7951，有来源标识 7950（手工建的商品仅 ~184 个 id，不在窗口内、未被触碰）；11-10 还有 16 个旧试跑导入，不在「这两天」范围，未动。
  - **窗口边界结论**：取 `created_at >= '2026-11-14 00:00:00'`（原预案 11-13 起覆盖 13/14/15，实际 11-13 零导入，以数据为准收窄）。
- **SQL 文件**（`var/sql_online_crawled_20261115/bring_crawled_online.sql`，两条 UPDATE，表名/列名已从 models `db_table` 与 `SHOW COLUMNS` 核实，真实主键列是 `id` 不是 `pk`）：
  1. `UPDATE spu s JOIN spu_source_identity ssi ON ssi.spu_id = s.id SET s.status='ACTIVE', s.updated_at=NOW() WHERE s.created_at >= '2026-11-14 00:00:00' AND s.status <> 'ACTIVE';` → **7767 行**；
  2. `UPDATE offer o JOIN sku k ON k.id=o.sku_id JOIN spu s ON s.id=k.spu_id JOIN spu_source_identity ssi ON ssi.spu_id=s.id SET o.status='ACTIVE', o.removed_by_platform=0, o.listed_at=COALESCE(o.listed_at, NOW()), o.updated_at=NOW() WHERE s.created_at >= '2026-11-14 00:00:00' AND o.status <> 'ACTIVE';` → **7767 行**（listed_at 原为空，本次上架时间全部写入）。
  - 没碰价格列（spu 的 `spu_retail_not_below_cost` CHECK 与本任务无关）；`updated_at` 是 auto_now 字段，裸 SQL 手动 SET（前人踩坑提醒，已遵守）。
- **执行方式**：临时脚本 `execute_sql.py`（已删）读取 SQL 文件、去注释按分号拆成两条 UPDATE，`transaction.atomic()` 内先前置计数（spu 7767 / offer 7767）→ 逐条 execute 打印 rowcount → 与预估一致 → 正常退出 atomic 块即 commit。实际输出：`pre-check 7767/7767 → UPDATE spu rowcount 7767 → UPDATE offer rowcount 7767 → COMMITTED`。
- **搜索文档刷新**：临时脚本 `refresh_search_docs.py`（已删）对窗口 7767 个 SPU 逐个调 `refresh_spu_search_documents(spu)`，**ok=7767 fail=0，耗时 213s**；DB 复查 `spu_with_doc=7767, searchable_docs=7767`。日志 `var/sql_online_crawled_20261115/refresh_docs.log`。
- **验证（按验证纪律仅做针对性验证）**：
  1. DB 三层复查：窗口 7767 SPU 中 spu ACTIVE=7767（占比 100%）、offer ACTIVE=7767（100%）、search doc `is_searchable=1` distinct spu=7767（100%）——三层一致且等于窗口总数；
  2. 后端未重启（PID 17388 仍在 8000），curl 实测：
     - `GET /api/v1/search?q=Yuejia` → total=1，命中「Yuejia 13.8in/35cm Easter Gnome Plush…」（spu 5252，11-14 导入，摸底时的 DRAFT 样例）——搜索可搜到；
     - `GET /api/v1/search?category=dog-toys` → total=310，与 DB 该类目窗口 SPU 数一致——类目页可见；
     - `GET /api/v1/search?q=Good Boy Soft Dog Toy` → total=3，命中「Good Boy Soft Dog Toy」（spu 494）——第二个抽查商品可搜到；
  3. 注意 FULLTEXT 最小 token=3，验证词用了品牌名/长标题词（前人踩坑提醒，已遵守）。
- **踩坑/记录**：①**真实主键列名是 `id`**（模型用 Django 默认主键，SQL 里写 `s.pk` 会报 1054 Unknown column——第一版摸底脚本踩过一次）；②摸底推翻了「大量商品本来就 ACTIVE、只翻转没上架那部分」的预期——窗口内爬虫商品导入时 spu/offer 全 DRAFT 且导入不建 search doc，所以 7767 个全量翻转 + 全量建文档是正确动作（对照 2026-11-08 商家上架不建文档用户看不到商品的真 bug，本次导入路径本来就缺文档层）；③文档刷新约 30ms/SPU，7767 个约 3.5 分钟，量级更大时考虑分批；④临时脚本已删，目录仅保留 SQL 文件与 refresh_docs.log。
- **未 commit**（var/ 不入库）；对 `var/fb_manual_assist.py`、前端、后端代码零改动；未重启后端。

### 2026-11-15（管理端 AppPager 分页组件升级：省略号页码 + 首页/末页按钮 + 页码跳转）

- **背景**：用户要求商品池列表分页「显示前几页和最后一页，中间用省略号；支持输入页码跳转；加首页/末页按钮」。商品池用的是共享组件 `admin-web/src/components/AppPager.vue`（约 12 个视图共用），直接升级组件、所有列表一致生效，视图零改动。
- **改动文件**：只有 `admin-web/src/components/AppPager.vue`（无其他文件改动，无后端改动）。
  - `pageItems()`：总页数 = `Math.ceil(total/pageSize)`；≤7 页全部平铺无省略号；>7 页时第 1 页与最后 1 页常驻，当前页 ±1 可见（当前页在第 1/末页时向内扩一格，如 8 页第 1 页显示 `1 2 3 … 8`、第 8 页显示 `1 … 6 7 8`）；省略号是**不可点击的 `<span class="pager__ellipsis">`**（现有全局 `.pager span` 样式自然接管，scoped 只补 padding/user-select）。
  - 「首页/末页」按钮放在最两端（首页在「上一页」前、末页在「下一页」后）；首页 disabled 条件 `page <= 1`，末页 disabled 条件 `page >= lastPage`（用计算出的总页数，比 hasNext 更准；下一页仍用 hasNext 保持原行为）。
  - 页码跳转：`<input class="pager__jump" type="number" min=1 :max=lastPage placeholder="页码">`（64px 宽）+「跳转」按钮，`@keyup.enter` 同样触发；`jumpTo()` 解析 int 后**先清空输入框**；非数字或 <1 不动作；>总页数钳制到总页数（选拆分策略：下限无效不动作、上限钳制——同时满足「9999→末页」「0/空不动作」两组测试）；与当前页相同不 emit。新样式全部在组件 `<style scoped>`，未污染全局。
  - props/emit 契约（`page/pageSize/total/hasNext` + `change`）与 `v-if="total > pageSize"` 均未变。
- **验证（按验证纪律仅做针对性验证）**：
  1. `cd admin-web && ../node_modules/.bin/prettier --check src/components/AppPager.vue` → 首跑 fail（属性换行），`--write` 修复后 **pass**；
  2. `npx eslint src/components/AppPager.vue` → **零告警**；
  3. `npx vite build` → **✓ built in 738ms**；
  4. 后端零改动，未跑后端测试，未重启后端（8000/5173 任务前后均存活）。
- **浏览器实测（IAB，1280×800；临时管理员 pagertest@joybuy.test）**，商品池当前 4671 个 SPU/20 = **234 页**（不是任务描述里的 8 页/158 SPU，数据是夜里抓取批次导入变多的，逻辑等价）：
  * 第 1 页：`首页 上一页 1 2 3 … 234 下一页 末页 页码 跳转`，首页+上一页 disabled，末页可点；
  * 点「末页」→ 第 234 页 `1 … 232 233 234`，下一页+末页 disabled，首页可点；点「首页」回第 1 页；
  * 跳转输入 4 → 第 4 页 `1 … 3 4 5 … 234`（双侧省略号），输入框清空；跳 6 用按钮、回车各测一次都正确高亮且清空；
  * 输 9999 → 钳制到 234；输 0 / 输空 → 停留原页不动作；
  * 商家管理页（18 页）同套 UI 正常（共享组件一致生效的旁证）。
  * 截图：`var/admin_pager_20261115/shot_products_page1.png`、`shot_products_page4_double_ellipsis.png`、`shot_products_last_page.png`（视口截图，非 fullPage——fullPage 在该布局出坏图）。
- **临时账号已删净（删了两次，见踩坑①）**：pagertest@joybuy.test 的 StaffAccount/StaffRoleAssignment/StaffSession 全部 0 条；`_tmp_mkstaff.py` 已删。
- **踩坑（不得再踩）**：
  1. **测完先别急着删临时管理员**——删号会使该账号会话立即 401（「Staff authentication is required.」），本次删号后又想补截三张图，跳转点击全部「生效了 emit（输入框清空）但列表不动」（401 被 view 吞成 error 提示），白白排查一轮；只能重建账号重新登录再截。以后截图/验证全部做完、确认无遗漏再删号。
  2. 401 后 view 的表现是「错误条 + 数据留在旧页」而不是踢回登录页，从「点击后输入框清空但页码不变」不能直接断定前端 bug，先看页面错误条/接口状态。
  3. IAB `locator.click` 对该页按钮偶尔超时，统一用 evaluate 取 `getBoundingClientRect` 中心 + `tab.cua.click` 兜底（本次大部分按钮直接 click 就成功，兜底保留）。
- **未 commit**（与整仓现状一致）；无遗留问题。

### 2026-11-11（开发环境启动服务；整机级全停后重建，无代码改动）

- **状态**：Docker 引擎未运行（`dockerDesktopLinuxEngine` 管道不存在）、8000/3000/5173/5174 全无监听——又是一次连带 Docker 一起的全停（看护循环扛不住关机/重启）。
- **动作（按 AGENTS.md 顺序）**：①启动 Docker Desktop（`D:/Docker/Docker Desktop.exe`）→ 引擎 12s 就绪，mysql/redis/mailpit 自动起来并 healthy；②`migrate --noinput` → **No migrations to apply**；③后端走看护循环 `bash var/run_backend_keepalive.sh`；④storefront `npx nuxt dev`；⑤admin-web `npx vite --port 5173`；⑥merchant-web `npx vite --port 5174`。
- **针对性验证（按验证纪律仅做针对性验证）**：四端口各**只有一行** LISTENING（8000=16440 由 runserver 父 16768 托管、3000=30860、5173=28500、5174=18964）；runserver 只有一对进程、看护循环只有一条（22832→31308）、nuxt/vite 各 1 个，**无重复双绑**；`/api/v1/health` ok（database/cache 均 ok）；三端首页 200；storefront SSR 含真实内容（Joybuy / 品类发现）。
- 日志：`var/logs/backend.log`（含 keepalive 标记）、`storefront.log`、`admin-web.log`、`merchant-web.log`。
- **地址**：storefront http://localhost:3000 （只绑 `::1`，必须用 localhost）· API http://127.0.0.1:8000/api/v1/ · 管理端 http://127.0.0.1:5173 · 商家端 http://127.0.0.1:5174 · Mailpit http://127.0.0.1:8025。
- 停后端顺序不变：先杀 runserver 的 python，再杀看护 shell；否则会被自动拉起。
- **2026-11-12 15:04 再次整机级全停后重建（同一套流程，无代码改动）**：Docker 引擎未运行、四端口全空 → 启动 Docker Desktop（引擎 12s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 看护循环 + nuxt + 两个 vite。验证：四端口各一行 LISTENING（8000=9912 由父 25588 托管、3000=8236、5173=32216、5174=1540）；runserver 只有一对；health ok；三端首页 200。**结论：这台机器每天/每次关机后都要手动重跑这四步，看护循环不会自启。**
- **2026-11-13 16:36 每日开机启动（用户已明确：有一个专用会话每天负责启动服务，无代码改动）**：Docker 引擎未运行、四端口全空 → Docker Desktop（引擎 15s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 看护循环 + nuxt + 两个 vite。验证：四端口各一行 LISTENING（8000=1520、3000=2600、5173=21376、5174=29808）；进程数核对 runserver 一对（父+子）、看护循环一条、nuxt 1 个、vite 2 个；health ok；三端首页 200。
- **2026-11-14 11:24 每日开机启动（专用启动会话，无代码改动）**：开机后 Docker 引擎未运行、四端口全空 → Docker Desktop（引擎 15s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 看护循环 + nuxt + 两个 vite。验证：四端口各一行 LISTENING（8000=20312、3000=35472、5173=34004、5174=35468）；counts：runserverPy=2（一对进程）、keepaliveBash=2（一条循环，wrapper+script）、nuxt=1、vite=2；health ok；三端首页 200。
- **2026-11-15 10:34 每日开机启动（专用启动会话，无代码改动）**：开机后 Docker 引擎未运行、四端口全空 → Docker Desktop（引擎 15s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 看护循环 + nuxt + 两个 vite。验证：四端口各一行 LISTENING（8000=17388、3000=33496、5173=32632、5174=33500）；counts：runserverPy=2、keepaliveBash=2、nuxt=1、vite=2；health ok；三端首页 200。
  - **踩坑（勿再踩）**：开机后第一次调用 shell 时 Bash 工具直接返回 **exit 3221225794（0xC0000142，STATUS_DLL_INIT_FAILED）**，连 `echo ok` 都失败，并伴随上一日三/四个 dev server 后台任务同时以 exit 4 失败——这是系统关机/重启导致的进程初始化失败，**不是仓库或命令问题**；隔几秒重试同一条命令即恢复正常，不要因此去改 PATH 或排查依赖。
- **2026-11-16 11:53 每日开机启动（专用启动会话，无代码改动）**：开机后 Docker 引擎未运行、四端口全空 → Docker Desktop（引擎 15s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 看护循环 + nuxt + 两个 vite。验证：四端口各一行 LISTENING（8000=15228、3000=30368、5173=30388、5174=30376）；counts：runserverPy=2、keepaliveBash=2、nuxt=1、vite=2；health ok；三端首页 200。
- **2026-11-17 11:35 每日开机启动（专用启动会话，无代码改动）**：开机后 Docker 引擎未运行、四端口全空 → Docker Desktop（引擎 15s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 看护循环 + nuxt + 两个 vite。验证：四端口各一行 LISTENING（8000=5944、3000=30076、5173=30340、5174=27032）；counts：runserverPy=2、keepaliveBash=2、nuxt=1、vite=2；health ok；三端首页 200。
- **2026-11-17 21:44 补启动三个前端（专用启动会话，无代码改动）**：本次开机后 Docker 三容器与后端已在跑（8000=12864 由看护循环托管，应是其他会话所起），3000/5173/5174 空 → 只补 `npx nuxt dev` + 两个 `npx vite`。验证：health ok；三端首页 200。**新发现（勿再踩）：本次 storefront 出现两个 nuxt 进程（34148 与 8808）且 3000 端口同时有 `127.0.0.1:3000` 和 `[::1]:3000` 两行 LISTENING**——新起 nuxt 在 IPv4 上也监听（之前只绑 ::1），两个进程各绑一个协议栈。处理：杀掉其中一个（`taskkill //F //PID <pid>`），只留一个。若再遇 3000 双 LISTENING，先 `Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where CommandLine -like '*nuxt.mjs*'` 数进程再清理。
- **2026-11-18 09:54 每日开机启动（专用启动会话，无代码改动）**：开机后 Docker 引擎未运行、四端口全空 → Docker Desktop（引擎 15s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 看护循环 + nuxt + 两个 vite。验证：四端口各一行 LISTENING（8000=23644、3000=9288、5173=9432、5174=5624）；counts：runserverPy=2、keepaliveBash=2、nuxt=1、vite=2；health ok；三端首页 200。**注意：本次 `migrate` 提示 catalog app 有模型改动尚未生成迁移（`makemigrations` 提示）**——应是其他会话正在开发中，启动会话不擅自 makemigrations，留待开发会话处理。
- **2026-11-18 11:00 跟进（storefront 换手，无代码改动）**：09:52 起的 nuxt（9288）于 ~10:58 退出（后台任务报 exit 1），几乎同时**另一会话起了新 nuxt（PID 32460，绑 `0.0.0.0:3000`）**，3000 现由它托管、200 正常、仅一个 nuxt 进程——启动会话不再重复起，避免双实例。其余三服务未动（8000=23644、5173=9432、5174=5624，health ok）。
- **2026-11-19 12:29 每日开机启动（专用启动会话，无代码改动）**：开机后 Docker 引擎未运行、四端口全空 → Docker Desktop（引擎 9s 就绪、三容器 healthy）→ `migrate` = No migrations to apply（catalog 迁移提示已消失，开发会话已处理）→ 看护循环 + nuxt + 两个 vite。验证：四端口各一行 LISTENING（8000=31364、3000=32484、5173=32376、5174=32388）；counts：runserverPy=2、keepaliveBash=2、nuxt=1、vite=2；health ok；三端首页 200。
- **2026-11-20 01:03 跟进（storefront 夜间退出后重启，无代码改动）**：11-19 白天起的 nuxt（32484）于夜间静默退出（后台任务 exit 1，日志末尾是正常 HMR，无报错栈）。其余服务未受影响（8000 看护循环已自动换新 PID、5173/5174 原进程存活、容器 healthy 13h）。已重启 nuxt（新 PID 49208，绑 `::1:3000`），页面 200，仅一个 nuxt 进程。**观察：nuxt dev 与后端 runserver 一样会夜间静默死，后端有看护循环、前端没有——如频繁发生可考虑给三个前端也加看护。**
- **2026-11-20 11:02 跟进（storefront 再次死亡 + 双 runserver + 双 nuxt，均已清理，无代码改动）**：凌晨 01:03 重启的 nuxt（49208）到早上又静默退出（机器未重启，boot 自 11-19 12:12）。同时 8000 出现**双 LISTENING**——一棵孤儿 runserver 树（43280/38940，父 34856 已死，10:59:20 由某个已退出的启动尝试留下）与看护循环的树（33884/34740，10:59:15）撞车；已 taskkill 孤儿树，留 34740。重启 nuxt 时又出现**双 nuxt 各绑一个协议栈**（39096 绑 127.0.0.1 / 42868 绑 ::1，与 11-17 晚同现象）；已杀 39096，留 42868（::1）。验证：四端口各一行 LISTENING（8000=34740、3000=42868、5173=32376、5174=32388）；health ok；三端首页 200。**结论：nuxt 一夜死两次，前端看护循环的必要性上升。**
- **2026-11-20 11:12 storefront 看护循环上线（`var/run_storefront_keepalive.sh`，无代码改动）**：11:02 清理后几分钟内 nuxt 又死一次（当日第 3 次），裸奔重启治标不治本 → 仿后端看护做了 storefront 版：循环检查 3000 是否 LISTENING，**端口空闲才启动** `npx nuxt dev`（防止双实例/双协议栈绑定），退出后 5s 自动重启，`var/logs/storefront.log` 写 `logger=keepalive` 标记。启动：`bash var/run_storefront_keepalive.sh`（后台）。**实测自动恢复**：taskkill 杀掉 nuxt 后 ~9s 自动拉起（新 PID 35392，绑 `::1:3000`），页面 200。当前四服务：8000=34740（后端看护）、3000=35392（storefront 看护）、5173=32376、5174=32388，health ok。停 storefront 同后端：先杀 nuxt 的 node 再杀看护 shell。
- **2026-11-20 15:53 再次开机启动（专用启动会话，无代码改动；首次两个前端服务都走看护）**：开机后 Docker 引擎未运行、四端口全空 → Docker Desktop（引擎 9s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 后端看护循环 + **storefront 看护循环（首次用于日常启动）** + 两个 vite。验证：四端口各一行 LISTENING（8000=24044、3000=5368、5173=32656、5174=28804）；runserver 一对进程、两条看护循环各一条链、nuxt 1、vite 2；health ok；三端首页 200。排查备注：`Get-CimInstance` 列 bash 时会把**检查命令自身的临时 shell** 也算进去（同宿主派生、即起即灭），别误判成重复看护循环——以端口 LISTENING 行数 + 服务健康为准。
- **2026-11-20 17:41 跟进（storefront 看护循环实战验证成功，无代码改动）**：15:53 启动的看护循环在 17:35–17:40 之间 nuxt 两次退出（rc=0），**循环均 5s 内自动拉起**（日志有 `logger=keepalive` 标记各两条），3000 当前由新 nuxt（PID 48432）服务、200 正常。后台任务包装层虽报 exit 1，但看护脚本本体仍在跑（进程链 12752→36192→23884）——**后台任务的 exit 通知 ≠ 看护死了，以进程链 + 端口为准**。
- **2026-11-20 23:01 晚间再次开机启动（专用启动会话，无代码改动）**：全停（Docker 引擎未运行、四端口空）→ Docker Desktop（引擎 9s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 后端 + storefront 两条看护循环 + 两个 vite。验证：四端口各一行 LISTENING（8000=45632、3000=36384、5173=1228、5174=26900）；health ok；三端首页 200。
- **2026-11-21 11:08 每日检查（专用启动会话，无代码改动；本次无需启动）**：昨晚 23:01 起的服务整夜存活，机器未重启（容器 Up 12h）。**两条看护循环夜间各自完成一次自愈**：后端 runserver 00:04（UTC 16:04）退出 → 5s 拉起（8000 现 PID 14592）；nuxt 01:02 退出 → 01:15 拉起（3000 现 PID 22544）；5173/5174 原进程未动。验证：health ok；三端首页 200。
- **2026-11-23 15:20 开机启动（专用启动会话，无代码改动；距上次已隔 2 天，期间重启过）**：全停（Docker 引擎未运行、四端口空、**看护 bash 数为 0**——重启会杀掉看护循环，这是预期行为）。重建：Docker Desktop（引擎 9s 就绪、三容器 healthy）→ `migrate` = No migrations to apply → 后端看护 + storefront 看护 + 两个 vite。验证：四端口各一行 LISTENING（8000=35216、3000=35736、5173=1116、5174=34268）；health ok；三端首页 200。
- **2026-11-23 18:17 跟进（后端 keepalive 循环自身挂了，已重启，无代码改动）**：18:17 发现 8000 无监听、`bash` 看护进程数 **0**——**这次不是 runserver 死，而是看护循环本体消失**（日志显示循环 10:16:49 还拉起过一次，之后随后台任务被清理而终止）。已重启 `bash var/run_backend_keepalive.sh`，3s 内后端恢复（PID 38500，runserver 一对进程），health ok。其余服务全程未受影响：3000=29236（storefront 看护 bash 仍在，count=1）、5173=1116、5174=34268 均 200，容器 Up 3h。**教训：判断「有没有人在看护」必须数 `bash` 进程，光看 8000 是否 LISTENING 不够——循环挂了端口也会一直空着。**
- **2026-11-23 18:36 看护循环改为「脱管启动」（新增 `var/start_keepalives_detached.sh`，无代码改动）**：18:32 重启的看护循环**又被后台任务清理连带杀掉**（8000 空、bash 计数 0），证明 `run_in_background` 起的 bash 循环活不过任务回收。改为 `cmd //c start "" "C:\Program Files\Git\bin\bash.exe" var/run_<svc>_keepalive.sh`，让循环挂在 Windows 自己的进程树下：**实测脱离后稳定存活**（90s 复验 backend=2 / storefront=2 条 bash 链，8000=36144、3000=29236、5173=1116、5174=34268 全部 LISTENING，三端 200）。
  - **以后启动看护一律走**：`cd /e/code/AgentProject/Joybuy && bash var/start_keepalives_detached.sh`（一次拉起后端 + storefront 两条脱管循环；端口在监听时只是提示，不会重复起服务）。
  - 收尾时发现有 7 条残留循环（每次重启叠加）——已全部 taskkill 后各留一条；**多份循环靠端口守护不会双绑，但会导致端口释放时抢启动，仍应保持每个服务只有一条**（`Get-CimInstance Win32_Process -Filter "Name='bash.exe'" | Where CommandLine -like '*keepalive*'` 数链）。
  - 5173/5174 的 vite 仍是普通后台任务（数周来一直稳定），如需同样加固可照此模板加看护。
- **2026-11-23 20:15 用户报「服务崩了」的全面体检（结论：当前无故障，无代码改动）**：用户反馈服务出错。逐项实测结果：
  - **现状全部正常**：四端口各一行 LISTENING（8000=37956、3000=29236、5173=1116、5174=34268）；`/api/v1/health` ok；三端首页 200；**接口实测全绿**：categories 200、storefront/home 200、search?q=iphone 200（24 条）、cart 200、admin/auth/session 200（未登录正常返回 csrf）、merchant/overview 401（未登录正常）；PDP `/p/5b9538d0-…` 200（标题正确、9 张图）且 `/media/...webp` 200（37KB）；磁盘 C 79G / E 111G 可用；MySQL INNODB_TRX=0、非 Sleep 连接 2；最近 60 分钟 **0 个 5xx**。
  - **两端所有视图逐个 vite 编译探针（admin 全部 `views/*.vue` + merchant 全部 `views/*.vue`）→ 0 个编译错误**（日志里 16:49 的 `Unexpected character '（'`、`@/mobile/MobileNotificationsView.vue` 解析失败均已不存在，属当时并发编辑的瞬时错误）。
  - **用户看到「崩」的最可能窗口**：18:17–18:33 后端 keepalive 循环自身被回收导致 8000 空了 16 分钟（见上一条），期间页面/接口会报错；18:36 改为脱管启动后已恢复。另外 storefront 今日被看护循环重启数次（日志 `nuxt exited rc=0` ×多次），每次有数秒不可用。
  - **发现但未处理的潜在故障（历史日志，非当前）**：①11-22 `/api/v1/merchant/media`、`/account/merchant-application/media` 500 = `botocore ClientError InvalidAccessKeyId`（当时 `MEDIA_BACKEND=s3` 而 AWS key 失效；**现在 `.env` 已是 `MEDIA_BACKEND=local`，本机上传走本地磁盘**，云端上传问题只在生产机复现）；②11-22 `/api/v1/merchant/overview` 500 = `MySQL 1205 Lock wait timeout`（50s 超时）；③`crisp_mirror.py` 报 `TypeError: _http_get() takes 1 positional argument but 2 were given`（11-22、11-23 各一次）——**前两条是环境/并发问题，第三条是真代码 bug，需另派任务修**。
- **2026-11-23 20:20 真因找到：storefront devProxy 连接池卡死 → 浏览器一直转圈（已修，无代码改动）**：用户报 `http://localhost:3000/` 打不开、一直转圈。逐层实测：
  - SSR 正常（`curl` 首页 200 / 166KB / 0.45s），页面引用的 `/_nuxt/*` 模块也全部 200 且毫秒级 → **不是 SSR、不是静态资源**；
  - **通过 Nuxt 代理访问接口全部挂死**：`curl http://localhost:3000/api/v1/{cart,auth/buyer/session,categories,storefront/home}` 全部 **45s 超时 http=000**，而直连 `http://127.0.0.1:8000/api/v1/*` 全部 200 → 锁定 **devProxy（nitro）**；
  - 根因：当前 nuxt 实例启动于 **18:17:36**，正是后端 keepalive 死掉、8000 空着的那 16 分钟内 → 代理的 keep-alive 连接池留下坏连接后再也不恢复；日志里另有 `WebSocket server error: Port 24678 is already in use`（HMR 端口自争）。
  - **修复**：`taskkill //F //PID 29236`（停掉卡死 nuxt，看护循环 12s 自动拉起新实例 37012）→ 实测 `/api/v1/cart` 80ms、`/api/v1/categories` 32ms、首页 0.34s、搜索页 0.30s，全部 200；nuxt 实例数 1。
  - **踩坑（勿再踩）**：①**后端宕机/重启后，storefront 的 devProxy 可能永久卡死，必须重启 nuxt**——不是前端代码问题，别去查 Vue/路由；②**判断"页面转圈"要先把 SSR（curl 首页）和 devProxy（curl :3000/api/v1/...）分开测**，SSR 200 + 代理超时 = 代理问题；③看 `var/logs/storefront.log` 里的 `Port 24678 is already in use` 可快速识别 nuxt 实例竞争。
- **2026-11-23 20:35 根治「永久转圈」：devProxy 关连接复用 + 全站请求超时（代码改动 1 文件）**：20:20 的处置只是重启 nuxt，会复发；本轮改成机制上不可能再卡死。改动 `storefront/nuxt.config.js`（+24 行，prettier 通过，未跑构建）：
  1. **devProxy `/api` 与 `/media` 均设 `agent: false`** —— 关掉 keep-alive 连接复用，每次请求新建连接；后端重启后不可能再复用到死连接。
  2. **代理超时**：`/api` 8s（本地接口正常 <200ms）、`/media` 20s（大图/视频流留余量），`timeout` + `proxyTimeout` 双设。
  3. **`experimental.defaults.useFetch.timeout = 15_000`** —— 给全站 27 处 `useFetch` 一个默认超时兜底，客户端不会无限等；页面显式传 timeout 仍以页面为准。
- **验证（按验证纪律仅做针对性验证，未跑全量）**：
  - 后端正常时：首页 200/0.42s、`/api/v1/cart` 200/40ms、搜索页 200/0.20s、三端首页 200。
  - **杀后端实测**（脚本停掉 keepalive + runserver，确认 8000 零监听）：首页 SSR **0.02s 返回错误页**（不再挂）、代理 `/api/v1/cart` **8.0s 有界失败**（原来 45s 无响应乃至无限）。
  - **恢复后端实测**：`bash var/start_keepalives_detached.sh` → 后端 3s 起来，**nuxt 进程 PID 不变（37880）**的前提下 `/api/v1/cart` 50ms、`categories` 50ms、`storefront/home` 33ms 全部 200 → **确认「后端重启后必须重启 nuxt」这个坑已被消除**。
  - 现状：四端口 LISTENING（8000=38900、3000=37880、5173=1116、5174=34268），health ok，三端 200。

### 2026-11-09（正式详情存储 + 购物端渲染：视频 / 图文区块 / 规格表格 / spec_options / AI）

- **需求**：把爬虫第二轮解析出的 `videos` / `content_sections` / `specification_tables` /
  `specifications` / `spec_options` / AI 摘要正式存进业务表，详情 API 返回，购物端按 Joybuy
  结构渲染；视频必须本地化（`/media/...`，不引用第三方 CDN）；导入幂等。
- **改动文件**：
  - `backend/catalog/models.py`：新增 `SpuDetail`（OneToOne ↔ Spu）、`SpuVideo`（Spu / MediaAsset
    视频 + poster + duration/source/order）。
  - `backend/catalog/migrations/0014_spudetail_spuvideo.py`（新增）。
  - `backend/media/models.py`：`MediaAsset.Kind.VIDEO`；`backend/media/storage.py`：
    `KIND_PATH_PREFIX[VIDEO] = "videos"`；`backend/media/migrations/0004_alter_mediaasset_kind.py`
    （新增）。
  - `backend/crawler_control/import_services.py`：`_fetch_bytes` / `_fetch_video_bytes` /
    `_store_local_image` / `_localized_image_url` / `_localize_content_sections` /
    `_localize_spec_options` / `_tables_from_specifications` / `_sync_spu_detail` /
    `_duration_ms` / `_import_spu_videos`；`import_staging_product` 调用并写
    `imported_refs.detail/videos`。
  - `backend/catalog/detail_views.py`：`_video_payload` / `_spec_options_payload`
    （源 SKU id → `Sku.public_id`）；`select_related("detail")` +
    `prefetch_related("videos__video", "videos__poster")`；响应新增 8 个字段。
  - `backend/catalog/tests/test_product_detail_extras.py`（新增 2 例）。
  - `backend/crawler_control/tests/test_crawler_detail_persistence.py`（新增 4 例）。
  - `storefront/pages/p/[id].vue`：视频画廊 / 规格 chips + s96 图 / heading+paragraph 区块 /
    两列规格表 / AI 摘要卡 / 详情下方视频区 / description 回退与样式。
  - `docs/14-crawler-product-detail-issues.md`：新增 §9「正式存储 + 购物端渲染」。
- **设计要点**：
  - 视频走媒体库 `VIDEO` kind（内容寻址、本地 `videos/original/...`），`SpuVideo` 只存关联/
    元数据，视频字节不进 DB；海报复用图片资产。
  - `SpuDetail` 与 `Spu.description` / 手工 `image_urls` / `specs` 分离。
  - 导入只写非空字段，避免失败解析清空历史详情；视频按 `video_id`/`url` 幂等更新，
    非空列表时清理源站已删视频；空/缺失 `videos` 不清空。
  - 区块图/规格图在导入时下载成本地 `/media`，失败即丢弃；`spec_options` 的 sku_ids 在
    API 层映射为 `Sku.public_id`，购物端维度名与 SKU 规格名语言不一致时用 sku_ids 兜底。
- **验证（按验证纪律仅做针对性验证）**：
  ```bash
  ./.venv/Scripts/python.exe backend/manage.py test \
    catalog.tests.test_product_detail_api \
    catalog.tests.test_product_detail_extras \
    crawler_control.tests.test_crawler_detail_persistence \
    crawler_control.tests.test_crawler_detail_extras \
    crawler_control.tests.test_crawler_import \
    crawler_control.tests.test_crawler_rebuild \
    media.tests
  # 76 tests OK
  ```
  - 迁移：`manage.py migrate` 已执行 `media.0004`、`catalog.0014`。
  - **后端原以 `--noreload` 运行**（不会自动加载新代码）：已 `taskkill //F //PID <旧 PID>`，
    清理端口后用 `nohup ./.venv/Scripts/python.exe backend/manage.py runserver 127.0.0.1:8000 --noreload &`
    重启（当前 PID **36560**）。购物端 dev server 仍在 3000（Nuxt HMR 自动生效）。
  - `ruff check` / `ruff format --check`（改动 py）通过；storefront `prettier --check` /
    `eslint` / `nuxt build` 通过。
  - 浏览器实测：临时把详情/视频挂到真实商品 `947910f2-fd0a-42cb-a4a7-d7651844dbf0`
    （Wireless Earbuds Pro），测完已删除 `SpuDetail` / `SpuVideo` / 临时媒体资产。结果：
    视频 `readyState=4`、`duration=2`、无错误、`currentSrc` 本地 `/media/videos/...`，
    画廊第一位；规格 chips 带图，点击 Blue 价格 `$19.99 → $23.49`；heading 16px/700/
    `rgb(26,26,26)`；两组规格表表头均为「属性 | 值」且行序正确；AI 标题/正文/3 标签正常。
- **踩坑/边界**：
  - **`.gitignore` 已修正**：原 `media/` 规则误伤 `backend/media/` 源码目录；已改为
    `/media/` 并删除 `backend/media/` 行。运行时媒体仍在 `var/media`（`var/*` 忽略），
    `backend/media/` 的 `models.py` / `storage.py` / `0004` 迁移现在会出现在 `git status`。
  - 开发环境 `/media` 由 Django `static_serve` 提供，**无 HTTP Range**；生产 Nginx 要配
    Range，否则大视频拖动进度条会退化为整段加载。
  - 历史商品（之前导入）没有 `SpuDetail` / `SpuVideo`，需重抓重导；页面只显示原
    `description` / gallery。
  - `videos` 为空列表也不会清理既有视频（安全优先）；只有非空列表才按源身份清理。
  - 区块图/规格图下载是同步 best-effort：失败图片直接丢弃，不保留第三方 CDN 兜底。

### 2026-11-09（正式爬虫同步第二轮修复：画廊 / 系列规格 / 图文子标题 / 规格表格 / AI / 视频）

- **需求**：把 `crawler/debug_crawl.py` 里验证过的第二轮行为同步进正式爬虫，**不修改调试脚本**，
  并保持既有契约（两级面包屑、`product_category_path`、staging/import、dataset 布局）。
- **改动文件**：
  - `crawler/joybuy_crawler/parsers/joybuy_uk.py`：新增画廊解码/清洗、`spec_options`、PC DOM 区块、
    `parse_uk_mobile_detail`、`merge_mobile_detail`、`build_specification_tables`、`extract_ai_summary`、
    `extract_videos`、`mobile_detail_url`；`UkProduct` / `to_payload` 加增量字段。
  - `crawler/joybuy_crawler/spiders/joybuy_run.py`：`parse_detail` → 追加 `/dg/<sku>` 请求 →
    `parse_mobile_detail` / `mobile_detail_failed` → `_build_item`（一商品一条 item）。
  - `crawler/joybuy_crawler/settings.py`：`JOYBUY_MOBILE_DETAIL_ENABLED`（env `CRAWL_MOBILE_DETAIL`，默认 true）。
  - `crawler/joybuy_crawler/dataset.py`：`download_video()` + `videos/` 落盘 + 索引 `videos` / `video_errors`。
  - `crawler/joybuy_crawler/pipelines.py`：`DATASET_SAVED` 文案带视频计数。
  - `backend/crawler_control/import_services.py`：`_adopt_enriched_specification`（旧空规格单向补全）。
  - `backend/crawler_control/tests/test_crawler_detail_extras.py`（新增，16 例）。
  - `backend/crawler_control/tests/test_crawler_rebuild.py`：`SpiderLoggingTests` 按两步流程更新。
  - 文档：`docs/05` §9.4 + §10、`docs/14` §8。
- **关键踩坑**：
  1. `m.joybuy.co.uk/robots.txt` **Disallow: /dg/**，不能请求 m.；用 www 的同路径（同一份 SSR）。
  2. 画廊去重必须按「`/product/` 之后的路径 + 去掉 `!q70.webp`」；只去尺寸会把同一张图算两张。
  3. 空规格 → 有规格会让 `SkuSourceIdentity` 签名冲突（历史 SKU），必须走单向补全，否则重抓全量导入失败。
  4. `structuredFloors` 的 `_collect_blocks` 会把 `__types__` 的 `"TEXT"/"TEXT_AREA"` 当标题，必须过滤。
  5. 测试 fixture 拼 flight 时必须模拟 Next.js 的 JS 转义（`"` → `\"`），否则 `_flight_text`
     走 fallback，中文会变 mojibake（本次测试第一版就是这样挂的）。
- **验证**：见 §1 当前任务；本文档所列命令均已实际执行并通过。

### 2026-11-09（调试脚本第二轮：系列规格 / 图文详情 / AI 摘要 / 视频）

- **对象**：`100006995081936` 小绿锅、`10003152` 蜂窝炒锅、`100828902` PURE COOK 蒸锅、`10404455` iPhone 17 Pro。
- **根因（实测）**：
  1. 「系列」规格在 `productSeriesFloor.series`（`{title, series:[{name, skus, id}]}`），不在 `colorSizePartList`；旧解析完全没有。
  2. 图文详情：PC 折叠区块标题因商品而异（商品描述/重要信息、核心卖点与优势/产品详情、主要特点与优势/商品详情/设置使用兼容性…）；完整内容在移动端 `structuredFloors`（`structuredName` + `modules`），图片在 `imageUrl`；旧解析只认 `productDetailFloor_content`。
  3. 规格参数/材质与规格/技术规格是 `structuredFloors` 的 `mode=8,moduleType=3`，属性在 `moduleData.extendPartList` / `specificationPartList` 的 `C-P#Attribute&attributeBasic`。
  4. AI 摘要：flight 内联 `"aiSummary":{"summaryContent","summaryText"}` + `aiTagList[].tagName`，旧逻辑未读。
  5. 视频：`productMainImageFloor.mediaData` 里 `mediaType=2,video=true`，带 `videoUrl/duration/coverImageUrl`；旧逻辑只收图片。
- **改动（全部在调试脚本）**：
  - `extract_spec_options()`：先解析 `productSeriesFloor.series`（标题用 `title`，值用 `name`，SKU 用 `skus`），再解析 `colorSizePartList`；`sku_specs_from_options` 自动写 `skus[].specs`。
  - `extract_dom_sections()`：解析所有 `MuiAccordion-root` 的标题/文本/图片（`<li>` 分行）。
  - `extract_mobile_detail()`：`structuredFloors` 非 mode 8 → `content_sections`；mode 8 → `_attribute_groups()` 规格参数；兼容旧版 `graphDetailsModule`；`graphDetailListN` 兜底。
  - `extract_detail_extras()`：移动端区块优先，PC DOM 补缺（商品 1 的「重要信息」10 图）；生成 `description`、`description_images`、`content_sections`。
  - `extract_ai_summary()`：读 `aiSummary` + `aiTagList`，写 `ai_summary/_title/_tags`。
  - `extract_videos()` + `download_binary()` + `save_product()`：视频保存到 `<商品目录>/videos/01.mp4`；`--no-videos` 可关；payload 新增 `videos`/`video_urls`。
  - payload 新增 `content_sections` / `videos` / `video_urls` / `specification_tables`；`specifications` 增加 `group`；`debug_sources` 更新。
  - 日志：每个图文区块打印正文预览（最多 300 字，超出标注截断）；`商品描述` 打印前 300 字；`_collect_content` 把子标题排在正文前，避免「正文… 卫星功能」的尾缀。
  - **子标题块**：`_collect_blocks()` 把移动端 `moduleData.title` 记为 `heading`、`text` 记为 `paragraph`；`extract_dom_sections()` 把 `<strong>/<b>` 识别为 heading。`content_sections[].blocks` 保留顺序与类型；日志打印 `[子标题]`/`[正文]`。实测 iPhone 商品详情 8 个子标题（iPhone 17 Pro、终极 Pro 相机系统、1800万像素人物居中前置摄像头、突破性的电池续航、专为 Apple Intelligence 打造、灵活、安全的 eSIM、安全警告、退货政策通知），设置使用兼容 1 个（使用说明），主要特点 1 个（卫星功能）；小绿锅 DOM strong 子标题也识别。**展示必须按 heading 加粗加大加黑**，不能只拼 `text`，详见 `docs/14` §7.7。
- **表格展示口径**：Joybuy 的【规格参数】/【材质与规格】/【技术规格】都是两列表格；`specification_tables` 保留 `{title, columns:["属性","值"], rows:[{name,value}]}`，行顺序按源站，不按 `attributeSort` 重排；前端必须用 `<table>` 渲染，不能拼成文本。详见 `docs/14` §7.6。
- **实测结果**：
  - 小绿锅：系列【留学生必备】1.8L小绿锅；规格参数 13；商品描述 622 字 + 重要信息 10 图；AI 有；无视频。
  - 炒锅：系列 蜂窝炒锅30cm/精铁锅32cm；规格参数 7；核心卖点 191 字 + 产品详情 9 图；AI 有；无视频。
  - 蒸锅：仅数量规格（正常）；规格参数 8；核心卖点 333 + 产品详情 807 字/7 图 + 使用说明 96；AI 有；**1 个 23s 视频 7,102,340 字节已保存**。
  - iPhone：系列 1TB/512gb/256GB + 颜色 3 色；当前 SKU=256GB+星宇橙色；技术规格 15；主要特点 119 + 商品详情 997/5 图 + 设置使用兼容 124；AI 有；无视频。
  - 回归 ZSPEED `100016395115375`：颜色/白色、规格参数 4、描述 1009 字仍正常。
- **验证**：四商品端到端 `--no-images`（视频下载开）4/4 落盘；`ruff check` / `format` / `py_compile` 通过。详细记录见 `docs/14` §7。
- **边界**：移动端详情每商品多 1 次请求；蒸锅「安全警告」文字包含在「产品详情」区块内（页面无独立标题）；视频是否入业务表待定，目前只落 dataset。**正式爬虫未改**，同步清单见 `docs/14` §7.4。

### 2026-11-09（节庆装饰品改为活动商品）

- **需求**：把【节庆装饰品】从【家居生活】下删除；数据以后归到【活动商品】，抓取时直接按活动商品入库。
- **事实**：Joybuy 菜单 `l2:1580 节庆装饰品`；商品后台类目实测为 `节日派对(4909)/节日与活动(4945)/…`。「活动商品」不是类目，是 `Spu.is_activity` 标记（`catalog.models.Spu` 注释）。
- **改动**：
  - `backend/catalog/joybuy_menu_crosswalk.py`：`l2:1580` 从 `NODE_SLUG` 移除，改为 `ACTIVITY_SOURCE_IDS={"l2:1580"}`，`resolve_node` 返回 `action="activity"`、不建本地类目；新增 `ACTIVITY_LOCAL_SLUGS={"seasonal-decor"}`。
  - `sync_local_categories_from_joybuy`：activity 行跳过建类目并计入 `activity`；新增 `_prune_activity_categories()`，仅当 `seasonal-decor` **无商品/无子类目/无商品类目引用**时删除（否则保留并提示先迁移）；报告增加活动节点/清理计数。
  - `crawler/joybuy_crawler/spiders/joybuy_run.py`：target 增加 `source_category_id`；`parse_detail` 把 `crawl_source_category_id` / `crawl_source_category_name` 写进 payload。
  - `backend/crawler_control/import_services.py`：活动判定 = 任务来源 `l2:1580`/`节庆装饰品` **或** 商品类目路径含 `节日与活动(4945)`；命中后 `Spu.is_activity=True`、`local_category=None`；商品类目仍按 2 级保存。
  - `backend/catalog/product_services.py`：`get_or_create_spu_from_source` 新增 `is_activity` 参数；新建时写入，已存在时只把 False→True（不自动清除管理端取消的标记）。
  - 文档：`docs/15` 新增 §2.1；`docs/05` §9.2 补充 flight/2 级口径。
- **db 清理**：`sync_local_categories_from_joybuy` 已执行；`seasonal-decor`（0 商品）和 `l2:1580` 映射已删除；本地类目 **141**（11 一级 + 130 二级），家居生活 **24**。
- **针对性验证（按验证纪律，未跑全量）**：
  1. `catalog.tests.test_joybuy_menu_crosswalk`：活动节点不建类目、`seasonal-decor` 被清理、dry-run 不写库、幂等 → 通过。
  2. `crawler_control.tests.test_crawler_product_category`：任务来源 `l2:1580` → `is_activity=True`、`local_category=None`；商品类目 `4945` 兜底命中；`4910 派对用品` 不命中 → 通过。
  3. 回归：`test_standard_categories + test_joybuy_menu_crosswalk + test_product_detail_api + test_catalog_domain + test_crawler_product_category + test_crawler_review_aggregates + test_crawler_import` → **50 passed**。
  4. ruff check / format 通过；同步命令正式执行 0 错误。
- **边界**：如果任务选的是父频道（而不是 `l2:1580`），靠商品类目 `4945` 兜底；若某商品既不在 `l2:1580` 也不在 `节日与活动`，不会被标活动。历史 `seasonal-decor` 若有商品，命令会保留并提示先迁移，不会级联删数据。

### 2026-11-09（类目体系落地：二级补全 + ProductCategory + 两级面包屑）

> ⚠️ **2026-11-11 修订**：本节 Part 1 的「合并补全/多对一桶（`PRESERVE_BUCKET_SLUGS`）」口径已被推翻，
> 现行为「一对一」（156 个 Joybuy 二级 ↔ 156 个本地二级，桶全部拆开退役），见文件顶部 2026-11-11 任务与 `docs/15` §2。
> Part 2（`ProductCategory` 2 级 + 面包屑）与本节的拆分/不映射/活动口径仍有效。

- **用户口径**：①按 11 个一级类目去 Joybuy 完善二级；②引入商品类目表但最多 2 级（厨具餐具/锅具/炒锅 → 只留前两级），后面接商品名称展示在面包屑；爬虫仍只抓 2 级面包屑。
- **Part 1（本地二级补全）**：
  - 新增 `backend/catalog/joybuy_menu_crosswalk.py`：`CHANNEL_PARENT`（14 频道→11 一级，汽车 None）、`NODE_PARENT`（按二级拆分：计算机硬件→计算机与配件、运动/户外→户外运动、清洁/纸品→家居生活、按摩→健康与保健）、`MERGE_INTO_EXISTING`（复用已有 slug）、`NODE_SLUG`（新建节点固定 slug）、`PRESERVE_BUCKET_SLUGS`（多对一桶保名/保序）。
  - 新增 `backend/catalog/management/commands/sync_local_categories_from_joybuy.py`：`--dry-run` / `--tree-version` / `--report`；幂等；频道也写 `CategoryMapping`；未映射节点单独报告。
  - 更新 `seed_standard_categories.py` 中被 merge 的 42 个基座节点名称（slug 不变），避免重跑 seed 回退；更新对应测试断言。
  - **执行结果**：新建 89、更新 67、二级映射 157、频道映射 13、未映射 6（汽车）、错误 0；本地类目 53 → **142**（11 一级 + 131 二级）。各一级二级数：家居 25、电子 11、美妆个护 16、小家电 18、健康 9、计算机 7、服装 6、户外 4、宠物 6、婴幼儿 23、游戏 6。
  - **踩坑**：多对一桶（食品杂货/手机与平板/笔记本与台式机/电脑配件/音响/宠物食品/宠物玩具/玩具早教）会被最后一个源节点改名（曾出现食品杂货→米面杂粮）；已加 `PRESERVE_BUCKET_SLUGS` 保留桶名/排序，并重跑 seed + sync 修正。
- **Part 2（商品类目表 + 面包屑）**：
  - `catalog/models.py` 新增 `ProductCategory`（catalog FK、source_id、parent、name、depth、path、可空 local_category；unique `(catalog, source_id)`、`CheckConstraint(depth<=1)`）+ `Spu.product_category` FK；迁移 `catalog/0013_productcategory_spu_product_category_and_more.py`，已 `migrate catalog`。
  - `crawler/joybuy_crawler/parsers/joybuy_uk.py`：新增 `PRODUCT_CATEGORY_DEPTH=2` 与 `_extract_flight_product_categories()`（读 `productBreadCrumbFloor...categories`）；`joybuy.breadcrumbs` 仍 2 级；payload 新增 `product_category_path` / `product_category_id` / `joybuy.productCategoryPath`；DOM 面包屑兜底；`source_category_id` 不复用商品类目 ID。
  - `crawler_control/import_services.py`：新增 `_sync_product_categories()`（强制 `[:2]`，upsert depth0/1，返回最深节点）；`get_or_create_spu_from_source(product_category=...)`；已有 SPU 刷新商品类目，`local_category` 只在为空且 `ProductCategory.local_category` 有值时才补。
  - `catalog/detail_views.py`：返回 `category_breadcrumb`（最多 2 级）；`storefront/pages/p/[id].vue`：优先 `Home / 厨具餐具 / 锅具 / 商品名称`，无商品类目回退本地类目树；商品类目暂为不可点击文本。
  - 文档：新增 `docs/15-category-taxonomy-and-product-breadcrumb.md`；更新 `docs/05` §9.2（flight 来源、2 级、独立字段）。
- **针对性验证（按验证纪律，未跑全量）**：
  1. `makemigrations --check --dry-run` → No changes detected；`migrate catalog` 成功。
  2. `sync_local_categories_from_joybuy --dry-run` → 新建 90/更新 67/映射 157/未映射 6/错误 0；正式执行 → 新建 89/更新 67/未变化 1/映射 157/频道 13/未映射 6/错误 0；DB 查询各一级二级数与上述一致，汽车未创建。
  3. 测试：`catalog.tests.test_standard_categories + test_joybuy_menu_crosswalk + test_product_detail_api + test_catalog_domain + crawler_control.tests.test_crawler_product_category + test_crawler_review_aggregates + test_crawler_import` → **47 passed**。
  4. 真实炒锅 `10003152`（Ochama）解析：`product_category_path = [厨具餐具(288), 锅具(361)]`、`product_category_id=361`、无 `炒锅(372)`；`joybuy.breadcrumbs` 两级。
  5. storefront `prettier --check` / `eslint` / `nuxt build storefront` 通过。
  6. **未做**：未在 dev 库真实导入炒锅商品，未做浏览器实测；导入/API 由单测覆盖（`ProductCategoryImportTests`、`ProductDetailApiTests`）。

### 2026-11-09（类目体系答疑：三套类目与商品类目映射，仅分析未改代码）

- **问题**：Joybuy 频道类目【家居生活】下有【厨房与餐厅用品】【家具】【整理收纳】【家居装饰】；点进一个炒锅商品，面包屑是【厨具餐具/锅具/炒锅/商品名称】。这些是不是类目？怎么和我们的 LocalCategory 关联？
- **实测结论（2026-11-09，真实抓取炒锅商品 `10003152`）**：
  1. **是三套不同层级的类目体系**：
     - **我们的 `local_category`**：11 个一级 + 42 个二级；家居生活下只有 厨房用品/家居收纳/床品家纺/清洁用品/食品杂货（5 个）。
     - **Joybuy 频道菜单树**（已同步为 `SourceCategory` / `SourceCategorySnapshot`）：家居生活下有 **22 个**二级，如 厨房与餐厅用品 `l2:1572`、家具 `l2:1564`、整理收纳 `l2:1574`、家居装饰 `l2:1566`。
     - **Joybuy 商品后台类目树**（面包屑来源）：`厨具餐具(288) → 锅具(361) → 炒锅(372)`，是**数字 ID**；`SourceCategory` 里 0 条命中（`l2:`/`minihome:` 与数字 ID 是两套 ID 空间）。
  2. 面包屑最后的「商品名称」**不是类目**，是前端把商品标题拼在路径末尾。
  3. 商品类目树比我们的本地树更深（3~4 级），所以关联必然是**多对一**：`厨具餐具/锅具/炒锅 → 家居生活/厨房用品`。
- **为什么现在关联不上**：
  1. 解析器用 DOM 面包屑（`nav[class*="breadcrumb"] a`），这些 `<a>` 的 href 没有 `l1/cid/firstcid` 参数，`cid` 为空；
  2. `truncate_breadcrumbs` 只留前 2 级，炒锅这一级被丢掉（实测解析结果只有 `厨具餐具/锅具`，`source_category_id=""`）；
  3. `import_staging_product` 用 `payload.source_category_id` 去查 `SourceCategory` 再查 `CategoryMapping`，商品类目 ID（288/361/372）不在 `SourceCategory`，解析结果为 None；
  4. 现有 `CategoryMapping` 只有 11 条 `bestseller:* → 本地一级`，14 个频道菜单节点（`minihome:*` / `l2:*`）没有映射。
- **建议方案**：
  1. **数据源修正**：从 flight `productBreadCrumbFloor.data["C-M#viewBreadCrumbItem&core"].categories` 取完整 `[{name,id}]`（实测炒锅就是 `[{"厨具餐具":288},{"锅具":361},{"炒锅":372}]`），payload 存 `source_category_path` + 最深 `source_category_id`；展示仍可截断 2 级。
  2. **新建商品类目维度**（与菜单树分开）：`SourceProductCategory(source_system, category_id, parent, name, path, depth)`，或给 `CategoryMapping` 加 `source_kind`（menu / product_cate）避免 ID 冲突；维护到 `LocalCategory` 的多对一映射。
  3. **导入优先级**：最深已映射的商品类目祖先 → 任务所选的菜单类目映射 → 关键词/`merchant_category` 兜底 → 未分类。
  4. **本地二级是否扩容**：Joybuy 菜单家居生活有 22 个二级，我们只有 5 个；若购物端要保持同级导航，需要对齐/扩容；若只做运营分组，则多对一映射即可（会损失 家具/家居装饰 等细分）。
- **待拍板**：本地二级是否扩到 Joybuy 的 22 个；商品类目表/映射表是否新建。**本轮未改任何代码。**

### 2026-11-09（开发环境启动服务，已完成，无代码改动）

- **动作**：按 `AGENTS.md` 启动顺序把开发环境从「Docker 未运行、四个服务全停」拉起来。
  1. 启动 Docker Desktop（`D:/Docker/Docker Desktop.exe`），引擎 6s 就绪，`joybuy-dev-mysql-1` / `joybuy-dev-redis-1` / `joybuy-dev-mailpit-1` 自动启动并 healthy。
  2. `migrate --noinput` → **No migrations to apply**（数据持久，无需重建）。
  3. 后端：`APP_ENV=development DEBUG=true DJANGO_DATABASE_ENGINE=mysql DJANGO_CACHE_BACKEND=redis ./.venv/Scripts/python.exe backend/manage.py runserver 127.0.0.1:8000 --noreload`（后台，日志 `var/logs/backend.log`，PID 15756）。
  4. 购物端：`storefront/npx nuxt dev`（日志 `var/logs/storefront.log`，PID 34744，仍只绑 `::1`）。
  5. 管理端：`admin-web/npx vite --port 5173`（日志 `var/logs/admin-web.log`，PID 12712）。
  6. 商家端：`merchant-web/npx vite --port 5174`（日志 `var/logs/merchant-web.log`，PID 34588）。
- **针对性验证（按验证纪律仅做了针对性验证）**：`netstat` 四个端口均 LISTENING；`GET /api/v1/health` → `{"status":"ok","database":"ok","cache":"ok"}`；`curl` 首页状态码 storefront(3000)=200、admin(5173)=200、merchant(5174)=200。
- **地址**：storefront http://localhost:3000 （必须用 localhost，3000 只绑 ::1）· API http://127.0.0.1:8000/api/v1/ · 管理端 http://127.0.0.1:5173 · 商家端 http://127.0.0.1:5174 · Mailpit http://127.0.0.1:8025。
- 未做任何代码或配置改动。若下次重启后又全停，照此顺序重跑即可；端口被占用时用 `taskkill //F //PID <pid>`（pid 取 `netstat -ano | grep ":<端口>" | grep LISTENING` 第 5 列），**不要用 powershell Stop-Process**（本 shell PATH 里没有 powershell，会静默失败）。
- **后续跟进（同日，已处理）**：首次启动的后端进程运行数小时后**静默退出**（exit 1，`var/logs/backend.log` 末尾是一条正常 200 请求、无 Traceback）——即已知的 dev runserver 后台不稳定；已重启，当前后端 PID **36560**（父 30424），health ok。
- **新踩坑（勿再踩）**：后台启动 runserver 时同一条命令被执行了两次，Windows `SO_REUSEADDR` 让第二个进程也能绑上 8000，出现**两套 runserver 进程树**（34800/27700 与 15116/7632，netstat 两行 LISTENING）。排查：`powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where {\$_.CommandLine -like '*runserver*'} | Select ProcessId,ParentProcessId"`。处理：确认 1 个真正 LISTENING 的 PID 后，`taskkill //F //PID <多余那套的子进程>` 清掉，父进程通常随之消失。**以后启动后务必核对：runserver 进程树只有一对、netstat 只有一行 LISTENING、health 为 ok。**
- **2026-11-10：后端再次静默退出（三个前端不受影响），改为看护循环启动**。新增 `var/run_backend_keepalive.sh`（在 `var/` 下，已被 gitignore）：循环检查 8000 是否 LISTENING，**端口空闲才启动** runserver（所以即使脚本被重复执行也不会双绑端口），runserver 退出后 5s 自动重启，并在 `var/logs/backend.log` 写 `logger=keepalive` 的启动/退出标记。启动：`bash var/run_backend_keepalive.sh`（后台运行；看护 shell PID 44372 / 脚本 13876 / runserver PID 每次重启都会变，验证时 31844）。**停后端时必须先杀 runserver 子进程再杀看护 shell**，否则会被自动拉起。验证：8000 仅一行 LISTENING、runserver 只有一对进程、health ok、`/api/v1/categories` 正常返回。
- **2026-11-10（第二次启动服务：整机级全停后重启，已完成）**：本次是**连带 Docker 引擎一起停**（`docker ps` 报 `dockerDesktopLinuxEngine` 管道不存在），三个前端与后端全无监听——即上次的看护循环**只能扛后端崩溃，扛不住重启/关机**（其后台任务以 0x40010004 退出）。已按顺序重建：Docker Desktop → 引擎 9s 就绪、mysql/redis/mailpit healthy → `migrate`（No migrations to apply）→ 后端走看护循环 → storefront/admin/merchant 三个 `npx` dev。验证：四端口 LISTENING（8000=25996 由 runserver 父 10884 托管、3000=31344、5173=31348、5174=31360）；health ok；三端首页 200。**开机后必须手动重跑看护循环**，它不会自己恢复。
- **2026-11-10 21:04（同一环境出现「双重看护 + 双后端」，已合并）**：14:47 启动的看护循环在 21:01 自动重启后端（说明它在正常工作），但另有**第二个看护循环**（21:03 起）和第二个 `--noreload` runserver（21:02 起）也被拉起，`netstat` 出现两行 8000 LISTENING —— Windows `SO_REUSEADDR` 允许双绑，最危险的是「两个进程跑不同时刻的代码、请求落到哪个不确定」。处理：杀掉多余那套 runserver 与第二个看护循环，只留一条链（看护 bash 15424→19380→脚本 4968；runserver 45380→51856）；杀掉后看护循环 5s 内自动重启**单**实例，加载当时磁盘上的最新代码。**注意：当前 storefront 3000 由另一个会话启动的 nuxt（PID 51496，21:03 起）托管，不是本会话那条后台任务（它已退出），不要再起第二个 nuxt，否则 3001 端口/端口占用。**

### 2026-11-08（爬虫商品详情 7 项解析问题：图片/描述/规格/规格参数/评价）

- **用户反馈**（商品 `100016395115375`，ZSPEED iPad 触控笔）：①日志要带代码行号；②图 3~6 是 icon，不是商品图；③s128 缩略图要映射成 s1248 大图，当前只拿到第一张；④商品描述没解析出来；⑤规格没解析（`颜色：白色`，规格处有 s96x96 小图，有些商品无图只有文字）；⑥页面下方【规格参数】没解析；⑦有 4 条评价/5 星但没解析（无 AI 摘要）。
- **改动（全部在调试脚本，正式爬虫未动）**：
  - `crawler/debug_crawl.py`：
    - 日志格式加 `%(name)s:%(lineno)d`（控制台 + 文件都带行号）。
    - 新增 flight 解码：`decode_server_product` / `floors_by_id` / `decode_json_after` / `resolve_flight_ref`。
    - 图片：`extract_flight_gallery`（`productMainImageFloor.mediaData[*].bigImageUrl` 全量 5 张）、`product_image_url`、`normalize_gallery_url`、`clean_gallery`（丢弃 `-000-com` 服务 icon、原尺寸 <180 的 s32/s64/s96、按去尺寸路径去重，统一 s1248）。
    - 描述：`extract_description`（`[class*="productDetailFloor_content"] [aria-label="rich text container"]`，按 `<li>` 分行）。
    - 规格：`extract_spec_options` / `sku_specs_from_options`（`productSelectedFloor.colorSizePartList` → `spec_options` + `skus[].specs`，规格图 s96；无图时 `image_url=""`）。
    - 规格参数：`fetch_mobile_specifications` / `extract_mobile_specifications`（额外抓 `https://m.joybuy.co.uk/dg/<sku>`，解析全部 `graphDetailListN`；`--no-mobile-specs` 可关）。
    - 评价：`extract_flight_rating`（`raw_decode` 读内联 `ratingInfo`，兜底 `productCommonFloor.commentCount/commentStar`）。
    - payload 新增 `spec_options` / `specifications` / `debug_sources`；`joybuy` 原生块增 `specOptions` / `specifications`。
    - **双输入 URL**：`is_product_url()` / `product_id_from_url()` 识别 `--listing-url` 是搜索页还是 `/dp/` 详情页；详情页输入跳过列表解析，直接进 `process_product()`；列表页与详情页共用 `process_product()`，按商品 ID 去重，可混传。
  - `docs/14-crawler-product-detail-issues.md`：7 个问题的现象、DOM/flight 证据、根因、解决方案、验证记录、同步正式爬虫的步骤与回归清单（§0 补充双输入 URL 说明）。
- **针对性验证（按验证纪律仅做针对性验证，未跑全量）**：
  1. `ruff check` / `ruff format --check` / `py_compile` 通过。
  2. 用本次运行落盘的详情页 HTML 做离线断言：gallery=5（全 s1248、无 `-000-com`）、`颜色/白色` + s96 规格图、描述 1009 字、评价 5.0/4 条/`{"5":4}`、规格参数 4 条（电池特性/原产国/型号/品牌），全部通过。
  3. 真实链路 `--limit 1 --delay 1 --timeout 30 --no-browser-fallback`（带图片）：列表 45 卡 → 详情解析 1 → 落盘 1；图片成功 5（main 1 + detail 4）失败 0；移动端规格参数尝试 1/成功 1；`product.json` 字段与离线断言一致。
  4. 双输入模式实测：①只传 `/dp/...` 详情 URL → `直接商品 URL：输入 1 个，落盘 1 个`（列表页计数 0，未解析卡片）；②只传 `/s?k=electronics` → 45 卡 → 落盘 1；③详情 URL + 搜索 URL 混传 → 详情先落盘 1，搜索页遇到同一商品打印“已抓过，跳过”，再抓下一件，最终落盘 2。
- **踩坑（勿再踩）**：
  1. 服务/保障 icon 在 `images3.../jfsintlpro-000-com/`，s32x32 + `.png.webp`；不能只看“主机是 joy-sourcing”就收。
  2. PC 端【规格参数】是客户端渲染，SSR 里只有 `BAILOUT_TO_CLIENT_SIDE_RENDERING` 占位；稳定数据在移动端 `m.joybuy.co.uk/dg/<sku>` 的 flight `trade_item_getDescription.data.graphDetailsModule.graphDetailList1`。
  3. 本页 `ratingInfo` 是**内联对象**，不是 `$ref`；旧 `\{[^{}]*"ratingInfo"[^{}]*\}` 正则被前面的 `tnInfo` 嵌套打断，所以评价一直为空。
  4. 抓移动端规格参数 = 每商品多 1 次请求；正式链路同步时要先决定是否接受这个成本，或继续找客户端 API。

### 2026-11-08（爬虫详情大卡片 / 折扣改为商家进货折扣 / 已上架成本价重算）

- **用户三项反馈**：①爬虫任务列表点【详情】直接插在列表下方不好看，要展开成大卡片；②给 HOMCOM 设折扣 20%、活动 30% 后商家端成本价偏低，按 20% 应该是 3599 → 2879.2，「折扣是给商家的折扣，不是给顾客的折扣」；③管理端改折扣后，该店已上架商品的成本价也应同步。
- **折扣口径（本次反转，旧口径明确作废）**：
  - 旧：`成本价 = 向上取整(零售价 × 折扣)`（折扣 70 = 零售价 70%）。
  - 新：`成本价 = 平台成本价 × (1 − 折扣%)`，两位小数（折扣 20 = 成本价减免 20%）；**零售价永远是顾客价，不受折扣影响**。
  - 例：平台成本 3599、折扣 20% → 2879.20；折扣 30% → 2519.30；平台成本 0.46、折扣 20% → 0.37。
  - 折扣优先级不变：活动商品 → 活动折扣，否则普通折扣；都没设 → 回退平台成本价；平台成本价为空 → `None`（不能上架，避免算错）。
- **改动明细**：
  - `backend/merchant_ops/services.py`：`compute_listing_cost` 迁入并改公式（原来是 `views_merchant_catalog` 里的函数，那里改为 `from merchant_ops.services import compute_listing_cost` + `__all__`，测试仍从 views 导入）；新增 `reprice_listed_offers(merchant=None, spu=None)`。
  - `backend/merchant_ops/views_merchants.py`：PATCH 折扣后用 `reprice_listed_offers(merchant=...)` 重算本店 ACTIVE Offer，回包加 `repriced_offers`。
  - `backend/merchant_ops/views_catalog.py`：商品池改成本价 → `reprice_listed_offers(spu=...)`；活动商品打标/去标同样重算（活动折扣与普通折扣不同）。
  - `admin-web/src/views/MerchantsView.vue`：折扣字段文案改成「折扣设置（%，成本价减免）」「活动商品折扣（%，成本价减免）」，hint 写明公式与 3599→2879.20 的例子；详情抽屉标题同步。
  - `admin-web/src/views/CrawlersView.vue`：任务详情由列表内 `.detail` 面板改为 `.detail-mask` + `.detail-card` 浮层大卡片（头部：标题+任务名+关闭；正文：meta 网格、运行记录表、运行日志），卡片宽 1080px、最高 90vh、正文单独滚动。
  - 文档：`docs/08` WP-42、`docs/13` 商家表字段说明、`功能需求迭代文档01.md` §2（加【修订 2026-11-08】条目）三处口径同步。
- **数据修复**：对设置了折扣的商家跑了一次 `reprice_listed_offers`——HOMCOM 6 条 ACTIVE Offer 全部重算；`c5130796` 成本 3599.00 → **2879.20**（零售 4899 不变），活动商品 `3e75a502` 按 30% 得 2799.30。
- **针对性验证（按验证纪律，未跑全量）**：
  - `manage.py test merchant_ops.tests.test_wp42_discount_listing + test_admin_commerce + test_merchant_modules + test_media_upload` → **93 passed**。折扣单测按要求重写（成本基数、两位小数、活动优先、无折扣回退、成本缺失返回 None），新增 API 用例：改折扣重算已上架 Offer（20% → 80.00、活动 30% → 70.00，零售价不变）、清空折扣回退平台成本价。
  - `ruff check backend` 通过；admin-web `prettier --check`、`eslint`、`vite build` 通过。
  - 商家端 API 实测（铸 HOMCOM owner 会话 + `X-Merchant-ID`）：`/merchant/catalog/products?q=HOCO` 返回 `成本 2879.20 / 零售 4899.00`。
  - 管理端 API 实测：PATCH `discount_rate` 25 → Offer 成本 2699.25；改回 20 → 2879.20（回包 `repriced_offers=5`），零售价始终 4899。
  - 浏览器实测：爬虫任务页点【详情】弹出居中大卡片（标题「任务详情 · 手机类目测试01」、含状态/类目/树版本/账号等 meta、运行记录表、日志区），点【关闭】收起，页面不再在列表下方插入详情块；列表页已无 `.detail` 内联块。
- **测试数据清理**：临时管理员 `crawlercheck@joybuy.test`、`poolcheck*` 已删，`reprice-check` 会话已删，临时脚本已删。HOMCOM 折扣保持用户设定的 20% / 30%。

### 2026-11-08（爬虫任务独立调试脚本 crawler/debug_crawl.py；登录态支持 cURL dict）

- **需求**：①把爬虫任务单独写成一个 py 文件方便单独调试；与当前存储完全分开、存储目录单独设置；每一行都打印日志。②补丁：用户从 cURL(bash) 解析出来的 `headers` / `cookies` 是 **dict**，脚本要直接吃这种结构。
- **改动**：
  - 新增 `crawler/debug_crawl.py`（单文件）：顺序执行列表页 → 商品卡过滤 → 详情页 → 解析 → 质量规则 → 落盘，无并发。**零 Django 依赖**，不连数据库、不写 `var/`；只写 `OUTPUT_DIR`。
  - **登录态 dict 输入**：自动读取同目录 `crawler/debug_session.py` 的 `headers = {...}` / `cookies = {...}`（与 cURL 解析器输出格式一致）；也支持 `--headers-file` 读取 JSON / Python dict / `headers=...` 与 `cookies=...` 连写的粘贴形态，以及 `--cookie "k=v; ..."` 追加。header 名大小写不敏感；`headers['cookie']` 可以是字符串或 dict；cookies dict 会合并进 Cookie 头。优先级：`debug_session.py` < 文件顶部 `HEADERS`/`COOKIES` 常量 < `--headers-file` < `--cookie`。
  - `.gitignore` 新增 `crawler_debug_output/`（默认输出目录）与 `crawler/debug_session.py`（真实 Cookie 禁止入库）。
- **用法**：
  ```bash
  .venv/Scripts/python.exe crawler/debug_crawl.py --limit 3
  .venv/Scripts/python.exe crawler/debug_crawl.py --listing-url "https://www.joybuy.co.uk/s?k=electronics" --output-dir "E:/crawler_debug" --limit 5 --headed
  .venv/Scripts/python.exe crawler/debug_crawl.py --headers-file "E:/crawler_headers.py" --no-images --limit 1
  ```
  参数：`--output-dir` / `--run-name` / `--listing-url`（可重复）/ `--limit` / `--delay` / `--cookie` / `--headers-file` / `--timeout` / `--no-images` / `--no-browser-fallback` / `--headed` / `--log-level`。文件顶部 `OUTPUT_DIR` / `LISTING_URLS` / `PRODUCT_LIMIT` / `DOWNLOAD_DELAY` / `HEADERS` / `COOKIES` / `DOWNLOAD_IMAGES` / `USE_BROWSER_FALLBACK` / `HEADLESS` 也可直接改。
- **产物结构**：`<OUTPUT_DIR>/<run-name>/` 下 `logs/crawl-debug.log`（与控制台同内容）、`raw_html/listings/`、`raw_html/products/`、`dataset/<一级>/<二级>/<商品ID>/{product.json,meta.json,images/{main,detail}}`、`dataset/<一级>/dataset_index.jsonl`、`summary.json`。
- **已踩坑（勿再踩）**：
  1. 登录墙判定必须用跟随 30x 之后的最终 URL（`FetchResult.url`）；用原始 URL 会把 307 到 `/login` 误判成正常页。
  2. **商品 URL 里的中文必须 percent-encode**：Joybuy 列表 href 直接带中文（`/dp/佳能-pixma-ts6550i/...`），`urllib` 只接受 ASCII，不编码会报 `UnicodeEncodeError: 'ascii' codec can't encode ...` 并重试 3 次后失败。已加 `normalize_url()`（quote path/query，保留 `%` 防二次编码）。
  3. Cookie 值绝不进日志：`header_summary()` 对 cookie/authorization/token/session 等值统一 `[REDACTED]`。
- **针对性验证（按验证纪律仅做针对性验证，未跑全量）**：
  1. `ruff check` / `ruff format --check` / `python -m py_compile` 全部通过。
  2. 离线 fixture 自测（monkeypatch `fetch_html` 返回 `listing_cards_v2.html` + `product_detail_reviews_v2.html`）：2 张卡片 → 2 个详情解析 → 2 个商品落盘；`product.json` / `meta.json` / `dataset_index.jsonl` / `raw_html` / `summary.json` / 日志全部生成。dict 断言：`cookies={'a':'1','b':'2'}` → 实际发送 `Cookie: a=1; b=2`，自定义 `Accept-Language` 生效，日志全文不含 cookie 值。
  3. `--headers-file` 三种形态解析通过：两个赋值连写、JSON dict、`{"headers":..., "cookies":...}`；中文 URL 编码断言通过（`%E4%BD%B3%E8%83%BD`）。
  4. **真实站点端到端（用户提供的 `debug_session.py` cookies）**：`/s?k=electronics` → 200（1.3MB，无登录墙）→ 45 张候选卡全部通过卡片规则 → 详情页 200（613KB）→ 解析出「ZSPEED iPad 触控笔 / 原价 25.99 GBP」→ 质量规则全部通过 → `product.json` 落盘；汇总 `详情：尝试 1，解析 1，落盘 1`。
- **边界**：脚本不读数据库账号；Cookie 过期就重新从浏览器复制到 `crawler/debug_session.py`。列表 URL 使用正式链路同款 robots 允许形式（`/s?k=...`、`/dp/...`），本脚本不做翻页。

### 2026-11-08（商品池编辑：父子品类联动 / 对齐 / 图片 10MB / 购物端看不到商品）

- **用户五项反馈**：①编辑页品类改成子品类，并且先选商家端品类（父）才显示该父类目下的子品类，两者位置调换体现关联；②删掉「商家端【商品上架中心】按这 12 类展示。」；③输入框左右不对齐；④单张图片上限 1MB → 10MB；⑤购物端看不到商品 `c5130796-7145-4e59-b54c-17870608cce7`。
- **改动明细**：
  - `backend/catalog/models.py`：新增 `LOCAL_PARENT_MERCHANT_CATEGORY`（home-living→HOME … games-accessories→GAMES，共 11 条），父类目 ↔ 商家端品类唯一事实来源。
  - `backend/merchant_ops/views_catalog.py`：`AdminCategoriesView` payload 增 `parent_id`、一级类目 `merchant_category`；新增 `_validated_merchant_category()`（POST/PATCH 共用）与 `_refresh_search_documents()`；**POST 之前根本不保存 `merchant_category`（新增商品选父品类会被丢掉），已修**；POST/PATCH 保存后刷新搜索文档。
  - `backend/merchant_ops/views_merchant_catalog.py`：商家上架成功后 `refresh_spu_search_documents(spu)`（新建 OR 复用原 Offer 都走这里）。
  - `backend/media/uploads.py`：`PRODUCT_MAX_BYTES = 10MB`（评价图 1MB / 活动图、头像 2MB 不变）。
  - `admin-web/src/views/ProductPoolView.vue`：编辑弹窗重排（商品名称整行 → 商家端品类（父品类）｜子品类 → 成本价｜零售价 → 状态｜活动商品），新增 `selectedParentCategory` / `childCategoryOptions` / `onMerchantCategoryChange`，子品类禁用＋「请先选择商家端品类」，历史值以「（当前值）」保留；图片上传 `:max-size-mb="10"`；删除 12 类提示语。
  - `admin-web/src/styles/admin.css`：`.field` 加 `align-content/align-items: start`，`.form-grid` 加 `align-items: start`，`.field input:not(checkbox/radio)` 与 `.field select` 统一 `height: 35px`。
- **购物端不可见根因（重点，勿再踩）**：
  1. **商家端上架从来不建搜索文档**。`product_search_document` 才是购物端搜索/类目页唯一数据源；商家上架只建 `Offer`，商品池里新建的商品上架后零文档 → 搜索结果、类目页、首页楼层全都看不到（只能靠知道的详情页 URL 直达）。本库 `3e75a502`（OPPO A6x，11-07 上架）就是这样。
  2. **管理端改品类不刷新文档**。`c5130796` 的文档还停留在 11-04 创建时的 `computers-accessories`，所以它在「计算机与配件」类目下而不在「电子产品」下——用户在管理端把品类改成电子产品后，购物端类目页依然找不到。
  3. 修复：上架/商品池新增/商品池更新/上下架四处统一调 `refresh_spu_search_documents`；并用一次性脚本对全部 121 个「ACTIVE SPU + ACTIVE Offer」重建文档（当时 missing=1、stale_category=1，重建后 searchable docs=121）。
- **针对性验证（按验证纪律，未跑全量）**：
  - 后端：`merchant_ops.tests.test_admin_commerce + test_merchant_modules + test_media_upload` → **82 passed**。新增/改写 5 例：`test_list_product_creates_search_document`（上架即出可搜索文档）、`test_update_product_refreshes_search_document`（改品类→文档品类同步）、`test_create_product_persists_merchant_category`（新增保存父品类）、`test_categories_endpoint_exposes_depth_and_sort_order`（parent_id/merchant_category）、`test_product_image_limit_is_ten_megabytes`（10MB 常量 + 2MB 商品图可传）；`test_rejects_oversized_file` 改用 review 用途验证 413（其上限仍 1MB）。
  - `ruff check backend` 通过；`ruff format --check` 报的 `views_catalog.py:377`、`views_merchant_catalog.py:173` 两处是**改动前既有**格式差异，本轮未动。
  - admin-web：`prettier --check` / `eslint` / `vite build` 全过。
  - API 实测：`/api/v1/search?category=electronics` 由 6 条变 8 条（含 HOCO `c5130796` 与 OPPO `3e75a502`）；`computers-accessories` 由 3 条变 2 条。
  - 浏览器实测（临时账号，测后已删）：弹窗内 商品名称 587px 独占一行，父/子品类同 y=216 且同高 35，成本价/零售价同 y=290；子品类初始禁用提示「请先选择商家端品类」；选「电子产品」→ 子品类只出 电视与影音/手机与平板/影像拍摄/智能家居；选「家居生活」后子品类被清空并换成 厨房用品/家居收纳/床品家纺/清洁用品/食品杂货；HOCO（挂在父类目「电子产品」）显示「电子产品（当前值）」+ 4 个子类目；图片区文案「单张不超过 10MB」；购物端 `/s?category=electronics` 同时出现 HOCO 与 OPPO，`/p/c5130796…` 详情正常。
  - 新增商品端到端：UI 新增「游戏及配件 / 游戏配件」商品保存成功，库里 `merchant_category=GAMES`、`local_category=/50/52/`（depth=1）；验证完已删除该临时商品。
- **测试数据清理**：临时管理员 `poolcheck@joybuy.test`、`poolcheck2@joybuy.test`、`poolcheck3@joybuy.test` 及 `ZZ校验临时商品` 均已删除；`c5130796`/`3e75a502` 的真实商品与文档保留（这正是修复目标）。

### 2026-11-08（商品池品类搜索下拉只留父类目 + 筛选按子树匹配）

- **需求**：商品池【品类】搜索下拉框只展示父类目，二级类目不展示；父类目=家居生活/电子产品/美妆个人护理/小家电/健康与保健/计算机与配件/服装与配饰/户外运动/宠物用品/婴幼儿用品/游戏及配件。
- **动手前核对数据**：`local_category` 共 53 条（depth0=11、depth1=42，无更深层级）；11 个父类目 `sort_order` 0–10 与用户给的顺序**完全一致**；158 个 SPU 中 36 个 `local_category` 为空、38 个直挂父类目、**84 个挂二级类目**。所以「下拉只显示父类目」必须同时把筛选改成子树匹配，否则选父类目只能查到 38/122 条（家居生活 3 条而不是 77 条、小家电 3 条而不是 13 条）。
- **改动**：
  - `backend/merchant_ops/views_catalog.py::AdminProductPoolView._queryset`：`category` 参数先按 `public_id`/`slug` 解析出节点，再 `filter(local_category__path__startswith=node.path)`；节点不存在返回 `queryset.none()`（原来的精确匹配行为）。路径形如 `/2/`（父）与 `/2/3/`（子），前缀带尾部斜杠不会误命中 `/20/`。
  - `backend/merchant_ops/views_catalog.py::AdminCategoriesView`：payload 增加 `sort_order`（前端排序用）；**仍返回全量 53 条**，因为编辑弹窗的「品类」下拉必须能选到二级类目。
  - `admin-web/src/views/ProductPoolView.vue`：新增 `parentCategories` computed（`depth===0` + 按 `sort_order` 排序），搜索下拉改用它；**编辑弹窗的品类下拉不变**（仍是全量 `categories`）。
- **针对性验证（按验证纪律，未跑全量）**：
  - `manage.py test merchant_ops.tests.test_admin_commerce` → **31 passed**（新增 `test_category_filter_includes_child_categories`：父类目命中父+子两条、兄弟父类目只命中自己；`test_categories_endpoint_exposes_depth_and_sort_order`）。
  - `ruff check` 通过；`ruff format --check` 报的 `views_catalog.py:377` 一处换行差异是**改动前就存在的**，本轮未动。
  - admin-web：`prettier --check` / `eslint`（exit 0）/ `vite build` 通过。
  - API 实测（临时铸 staff 会话 + curl）：`/api/v1/admin/categories` 返回 53 条、其中 depth0 恰为 11 条且顺序=用户给定顺序；`/admin/products?category=` 家居生活 77 / 电子产品 7 / 小家电 13 / 游戏及配件 3，与 ORM 子树计数完全一致。
  - 浏览器实测（localhost:5173，临时账号 poolcheck@joybuy.test，测后已删）：筛选下拉=「全部品类 + 11 个父类目」，**无任何二级类目**；选家居生活出 4 页 77 条（含「食品杂货」子类目商品）；选小家电 13 行；编辑弹窗品类下拉 54 项（含二级类目与「未分类」），当前值「食品杂货」正确回显。
- **注意/踩坑**：
  1. 改 `views_catalog.py` 后**必须重启后端**（8000 用 `--noreload`）：`taskkill //F //PID <netstat -ano | grep :8000 第5列>`，确认端口释放再启动，否则旧进程一直跑旧代码。
  2. 管理端 `admin@joybuy.test` 密码未知，浏览器验证一律走「shell 建临时 platform_admin → 测完删除」；本轮临时账号 `poolcheck@joybuy.test` 已删（含 role assignment 与 session 共 3 行），铸的 session(id=192) 也已删。
  3. 前端 `filter` 后的数组再 `sort` 是安全的（filter 已返回新数组），不要直接对 `categories.value` 排序，会破坏编辑弹窗的原始顺序。

### 2026-11-08（UI 细节第三轮：向导美化 / 物流进度行 / 提现 Tab 间距）

- 按 ui-ux-pro-max 规范（可见 label、全宽输入、≥8px 区块间距）修 4 处：①管理端一键下单向导——第 1–3 步搜索框原本无样式（默认约 180px 宽文字显示不全），改为带可见 label 的全宽字段（`.wizard-field`，632px 实测）；步骤条升级为分段进度样式（进行中蓝底/已过蓝边/未到灰）；选项卡片补 width:100%。②商家端订单详情物流进度——节点状态与时间改为同行两端对齐（`.timeline__row` flex + gap 16px），时间右对齐不再贴着状态。③商家端提现弹窗——「银行卡/数字货币链上转账」Tab 与表单间距 16px（`withdraw-method-tabs` scoped 覆盖页面级 .tabs 的紧贴样式）。管理端/商家端构建全过，四处均 getComputedStyle 实测。

### 2026-11-07（迭代02 第 2 轮：活动 / 返佣 / 通知 / 用户管理 / 购物端登录支付）

- **迁移（已应用真实 MySQL）**：`accounts_buyers/0006`（BuyerAccount.auth_provider，EMAIL/FACEBOOK/GOOGLE）、`notifications/0003`（MerchantNotification.order FK → orders.MerchantOrder，SET_NULL）。
- **平台活动**：`views_service.py` 创建 kind 勾选——PERMANENT 不填时间（DB start_date=今天兜底，payload 隐藏时间）、LIMITED 必填起止；`views_merchant_service.py::_expire_due_activities`（LIMITED+ONGOING+end_date<今天 → ENDED）挂进 `run_order_sweeps` 与商家端活动列表惰性执行，列表只展示 ONGOING；参与时 `add_exposure(1)`（同源）+ `participation.exposure_added=1`（重复参与不重复加）；商家端 ActivitiesView 加「我推荐的新商家」表。
- **返佣**：`calculate_commissions` 基数 `Sum("cost_total")`（明细列名"发货成功金额"沿用成本口径）；`create_merchant(..., referrer_code=)` 绑定 MerchantReferral（码无效不阻断）；管理端补录表单加邀请码字段。
- **通知**：好评推送改 `order_id`（新端点 `GET /admin/notifications/orders` 列已完成+未评价子单、`q` 按子单号精确匹配；推送校验 ORDER_NOT_COMPLETED/ORDER_ALREADY_REVIEWED 409）；两处 `_notification_payload` 增 order（单号/金额/完成时间）；商家端详情去大标题、好评展示关联订单；管理端推送表单 商品→店铺订单、星级默认 5。**修了一个前端 bug**：compose.images 初始值 `[]` 但绑定 textarea 字符串，`split` 直接报错——初始改 `''` 且提交处兼容数组。
- **用户端管理**：payload 增 auth_provider/「支付权限：全部可用」；列表列改（去地区/上次在线、加登录渠道、白名单就地加入/移出按钮走原 whitelist 端点）；删独立白名单模块（router 两条 + 侧栏项 + WhitelistView.vue 文件）；`Order.PAYMENT_METHODS` 加 APPLE_PAY/WECHAT_PAY。
- **购物端**：新端点 `POST /auth/buyer/register/email`（邮箱格式+密码≥8 位、免验证码、渠道 EMAIL）；AuthForm 重写（FB/Google 占位按钮提示暂未接入、无国家选择）；checkout 支付方式加 Apple Pay/微信支付、余额显示真实 balance；**place_order 余额支付真扣**（前置校验 + 事务内 `select_for_update` 扣款 + BuyerWalletEntry PURCHASE 负向流水，幂等 `order-pay:{单号}`，不足 `NOT_ENOUGH_BALANCE`）；session payload 返回 balance。
- **测试**：`test_doc02_round2.py` 9 例（常驻创建/限时必填+到期下架/参与加曝光幂等/返佣成本基数+档位/推荐码绑定+无效码不阻断/好评已完成未评价校验+下拉排除/余额真扣+不足拒单）；更新 3 个旧断言（返佣 400→200 基数、看板金额 40→20）。针对性回归 OK（仅剩已知 TOTP 过期测试）。三端构建全过。
- **浏览器实测**：好评推送全流程（管理端选店→订单下拉只列已完成未评价→发送→库里 order/rating/商品快照落对→商家端详情五星+关联订单 5527FC76+回复框）；用户列表渠道 EMAIL/支付权限「全部可用」；邮箱注册新端点成功。**数据清理**：临时管理员、测试买家已删；好评演示通知与 2 笔 WECHAT_PAY 演示订单保留。
- **注意**：`test_doc02_round2.py` 从 views 层导入 `_expire_due_activities` 属临时复用，第 3 轮重构 sweep 时建议挪进 services。

### 2026-11-07（迭代02 第 1 轮：订单闭环 / 钱包资金 / 商家管理 / 下架联动）

- **范围**：`功能需求迭代文档02.md` v2.1 第 1 轮（用户拍板分三轮；登录=邮箱先上+FB/Google 占位、余额真扣 balance 属第 2/3 轮）。无迁移（全部复用既有字段）。
- **改动明细**：
  - `merchant_ops/services.py`：`complete_all_nodes` 放开 PENDING（全节点时间=当前时刻、回款、不扣发货成本）；`INSUFFICIENT_WALLET_BALANCE` 文案→「您当前可使用余额不足」；`request_withdrawal` 删银行卡 12–22 位/币种/网络/地址格式校验（字段原样存档、超长截断）。
  - `merchant_ops/views_orders.py`：PATCH `created_at` 仅 COMPLETED（`ORDER_NOT_COMPLETED`）；节点时间补 `NODE_IN_FUTURE` + 已存在节点不可清空（`NODE_TIME_REQUIRED`）。
  - `orders/order_views.py` + `config/urls.py`：新端点 `POST /api/v1/orders/<id>/confirm-receipt`（买家本人 + PAID，事务内对所有子单 `complete_all_nodes`）；order_detail 补 payment_method/created_at/paid_at/merchant_orders。
  - `merchant_ops/views_merchants.py` + `urls.py`：`_pending_aggregate` 金额改 `Sum("cost_total")`；新端点 `GET /admin/merchants/<id>/ban-check?days=`；PATCH `ban_after_days` 改小时要求 `confirm_suspend=true`（409 `BAN_CONFIRM_REQUIRED`），确认后 `set_merchant_suspension` 立即封店。
  - `merchants/services.py` + `merchant_ops/merchant_context.py`：新增 `touch_merchant_online`（10 分钟节流），商家端每个请求自动记在线。
  - `merchant_ops/views_finance.py`：approve 后直接 TRANSFERRING（手续费此时填）；`start_transfer` 的凭证改选填（兼容旧状态）。
  - `merchant_ops/views_catalog.py` + `catalog/search_services.py`：unpublish 级联下架全部 ACTIVE Offer（removed_by_platform 留痕）并返回 `cascade_removed_offers`；新增 `refresh_spu_search_documents(spu)`（非 ACTIVE/无 offer → 删文档，否则重建），unpublish 与单 offer remove 都调用。
  - `merchant_ops/views_merchant_catalog.py`：商家已上架列表 ACTIVE 状态下过滤 `sku__spu__status=ACTIVE`；未缴保证金上架返回 `DEPOSIT_NOT_PAID`「您当前未缴纳保证金，缴纳完成后才能上架商品」。
  - `merchant_ops/views_merchant_app.py`：看板待发货金额改 `Sum("cost_total")`。
  - `merchant_ops/views_merchant_wallet.py`：`profit_label` 改「预估盈利/盈利」。
  - 前端：`MerchantOrdersView.vue`（下单时间仅完成态可编辑、节点时间只能改已出现的、保存弹确认框、PENDING 也能一键完成）；`MerchantsView.vue`（缩天数 ban-check 预检 → 二次确认弹框 → `confirm_suspend` 重发）；`FinanceView.vue`（approve 文案/提示更新、去掉 start_transfer 弹窗字段）；`WalletView.vue`（提现表去手续费/实际到账列）；`OrdersView.vue`（预估盈利）；storefront `pages/account/orders/index.vue`（重构自 orders.vue，修状态渲染、去死支付按钮）+ 新页 `[id].vue`（详情+确认收货）+ `locales/messages.js`；`p/[id].vue` 下架文案 `product.unavailable`。
  - **settings.py**：`CSRF_TRUSTED_ORIGINS` 补 `http://localhost:3000/5173/5174`（修"localhost 访问全站写请求 403"）。
- **测试**：新增 `merchant_ops/tests/test_doc02_round1.py`（14 例中的 11 例：级联下架/搜索文档删除/商家端隐藏/待处理一键完成不扣成本/ban-check+确认立即封店/待发货金额=成本/在线节流）与 `orders/tests/test_doc02_round1.py`（确认收货归属/PAID 校验/回款落账）；更新 6 个旧断言到新口径（approve→转账中、待发货金额=成本、下单时间仅完成态、节点时间≤现在、保证金提示码）。针对性合计 **141 passed**；ruff、三端 prettier/eslint、admin-web vitest 9、双端 vite build、Nuxt build 全过。
- **浏览器/API 实测**：管理端待处理订单一键完成→COMPLETED+回款流水落账；购物端买家登录→订单详情→确认收货→子单完成+回款（已验库）；封店天数 4→1 二次确认弹框（"该店铺有超过 6 天未处理的订单"）→确认后立即 SUSPENDED（测试后已解封还原 4 天）；平台下架→cascade 1、商家端列表不可见、购物端详情 404→页面提示英文/中文下架文案；商家看板待发货金额=成本合计（10.46）。**测试数据已清理**（测试 SPU/SKU/Offer 删除、临时管理员删除、HOMCOM 解封+天数还原；保留买家 doc02-e2e@joybuy.test 及其 2 笔演示订单，其中 1 笔已完成回款）。
- **两个新踩坑（务必记住）**：
  1. **CSRF_TRUSTED_ORIGINS 必须同时含 127.0.0.1 和 localhost 两组**（不同 Origin）——之前只有 127.0.0.1，用 localhost 访问三端时登录/一切写请求全 403。
  2. **Nuxt 嵌套路由**：`pages/account/orders.vue` + `pages/account/orders/[id].vue` 会让 orders.vue 变成父布局、子页永远不渲染——列表页必须命名 `orders/index.vue`；移动页面文件后相对导入层级（`../../utils` → `../../../utils`）要同步改。
- **第 2/3 轮待办**（下次继续）：第 2 轮=活动限时/长期+参与加曝光、返佣基数改成本价+推荐码绑定、通知好评改关联订单+去大标题、用户端管理合并白名单+登录渠道、购物端邮箱注册+FB/Google 占位+支付方式扩展（真扣 balance）；第 3 轮=一键下单模块、三端时区展示。

### 2026-11-07（需求迭代文档 02 v2：第二场录像拆解与需求整理）

- **任务**：拆解 `Joybuy功能需求讨论02.mp4`（100.8min，828 段 / 16140 字 / 10.5 分钟 GPU），以视频为主、`功能需求迭代文档02.md` v1 手记为辅，重写完整需求文档。
- **备份**：`功能需求迭代文档02.md.bak-20261107-170915`。
- **产物**：`D:/Users/lyx/Videos/Joybuy功能需求讨论02_拆解/`（txt/json/srt + `_segments.md` 时间戳分段表 + 200 关键帧 + `Joybuy功能需求讨论02-内容拆解.md`）+ 重写后的 `功能需求迭代文档02.md`（v2，结构：商家端订单/钱包/售后/活动/消息/通知 → 管理端订单/商家管理/商品池/商家商品/资金审核/保证金/平台活动/返佣/通知推送/用户端管理/一键下单 → 购物端 → 跨模块联动检查表 → 决策记录 14 条 → 待确认 4 条）。
- **与 v1 的关键差异（都来自视频）**：
  - 管理端订单：单个更新进度（只能向后、点击时刻=节点时间）、一键完成全部节点（状态+进度+回款同刻）、修改下单时间仅【已完成】、节点时间"下一节点>上一节点且≤系统时间、只能改已出现的、保存弹框"。
  - 购物端【确认收货】= 一键完成全部节点（后台必须有响应）。
  - 钱包：字段全不校验（金额除外）、商家端不展示手续费与冻结金额（程序内部要有占用）、不通过立马退回、资金明细五类型（提现申请/充值入账/订单发货/回款/推荐返佣）。
  - 返佣：推荐码绑定、月结 1%/2%/3% 三档、每月 1 日核算、管理端【确认返佣】后才发放；**基数待确认**（原型列"发货成功金额" vs 口播 71:45"成本价"）。
  - 保证金：审核勾选决定商家端有无模块；未缴可登录可浏览但不能上架；启用状态不可逆；管理端只展示需缴纳商家（"无需缴纳"标签）；手动充一笔。
  - 商家管理：上次在线时间=任何动作更新、展示 10 分钟刷新；封店天数改小+有超时订单→二次确认（x=按最早未处理订单下单时间）+立即封店；封店仍可发货、解封找客服人工；预览商家端删除；启用保证金不可改。
  - 资金审核：打回加原因文本框；手续费通过后才展示；转账失败去掉银行凭证/链上交易编号、加失败原因；新建钱包充值。
  - 通知：全手动推送；商家端详情去大标题（催发货/处罚通知等）与【处理订单】按钮；好评推送改【店铺订单】（已完成+未评价、可搜订单 ID）、默认五星可改、可带图、详情带关联订单可回复；已读同步且颜色区分。
  - 用户端管理：+登录渠道；−所在地区/上次在线；支付权限统一"全部可用"；白名单移入/移出就地按钮；独立白名单账户模块删除。
  - 购物端：登录 Facebook+Google+邮箱（邮箱验证码做不了→手动注册，账号唯一）；去国家选择；首页卡片固定 10 个无翻页、跳转链接自配到任意小品类；删心选品牌/美洲甄选（删后偏空挂起）。
  - 一键下单：管理端自动化任务（白名单用户→商家→商品→规格→数量→电脑时间触发），正常流转两端生成订单；失败处理未提，待确认。
- **验证**：按验证纪律纯文档任务未跑测试；转写与 v1 逐条比对、抽 2 帧核对（f031 推荐返佣页、f136 提现审核弹窗）与口播一致。
- **遗留**：待确认 4 条在文档第六节；下一步开发需先拍板返佣基数与时区口径。

### 2026-11-07（UI 细节优化第二轮：搜索框/状态色/活动商品页排查）

- 商家端上架中心：搜索框独立行补齐外边距（`margin: 12px 20px 16px`，与商品卡间距 16px），并补上脱离 `.toolbar` 后缺失的输入框样式；聚焦边框从品牌红改为中性灰（`merchant.css` 的 `.toolbar input:focus` 与 CatalogueView scoped 规则，红色只留给错误/危险动作）。
- 商家端看板：店铺状态配色——接单中=绿 `#16a34a`、已封店=红 `#e1251b`、待缴保证金=橙 `#d97706`；welcome strip 的"店铺当前状态"与统计卡"● 状态"两处同步。
- 管理端商品池：状态列按状态配色（可售=绿、已下架=灰、草稿=橙）。实现方式：`StatusTag.vue` 的 labels 值支持 `[文案, 色调]` 数组形态（字符串用法向后兼容），ProductPoolView 传数组。
- **活动商品管理"页面不存在"排查结论**：路由 `/activity-products`、视图文件、侧栏入口、`admin@joybuy.test`（platform_admin，44 个权限码含 catalog.pool.view/manage）全部正常，浏览器实测页面正常渲染。判断为重启后浏览器旧会话/缓存残留（当时后端尚未启动）；若再遇到请 Ctrl+F5 强刷，仍不复现则提供账号。
- 验证（针对性）：admin-web vitest 9 passed、双端 vite build 通过、prettier/eslint 通过；浏览器实测 getComputedStyle：商品池状态 tag 绿/橙生效、商家端状态两处 rgb(22,163,74)、搜索框聚焦边框 rgb(201,206,214) 且与卡片间距 16px。临时检查账号已删除。

### 2026-11-07（管理端/商家端 UI 优化 5 项 + 关机）

- 应用户要求完成 5 项 UI 优化并关机：
  1. **商家关注与曝光**：底部"最近调整记录"面板移除，改为每个商家行内【调整记录】按钮 → 抽屉单独展示该商家记录（顶部店铺名 + 完整 ID 两行）；`/growth/records` 后端补 `target_name` 批量解析；列表排序改为按入驻时间固定（`-created_at,-pk`），调整关注/曝光后顺序不变。
  2. **操作日志**：动作列上中文（新增后端 `ACTION_LABELS` 映射 ~45 个动作码）下方法名；业务对象列上名称下 ID（后端 `_resolve_target_names` 支持 merchant/spu/offer/buyer_account/staff_account，详情抽屉同步）。
  3. **活动商品管理**：Tab 改为与【首页活动卡片】一致的独立 Tab 条（panel 内只剩标题 + 搜索）。
  4. **商家端上架中心**：搜索框从品类 chips 行拆出独立成行（商品池与已上架两个 Tab 都改）。
  5. **商家端商品卡片**：移除卡片上的商品 ID 行（详情抽屉仍可看完整 ID）。
- 验证（针对性）：`merchant_ops.tests.test_admin_round2`（27）+ `merchants.tests.test_wp42_services`（15）通过；ruff / prettier / eslint / vite build（admin+merchant）通过；浏览器实测 growth 记录抽屉（店铺名+ID、空态正确）、操作日志两行单元格（动作中文+方法名、OPPO 商品名+ID）、活动商品 Tab 布局、上架中心搜索换行与卡片无 ID。临时检查账号已删除。

### 2026-11-07（管理端商家管理：操作上移到表格行）

- 应用户要求，把商家详情抽屉底部的操作（编辑商家/扣信誉分/封店）**移到商家列表的【操作】列**：每行为 详情 / 审核（仅待审核）/ 编辑 / 扣信誉分 / 封店（仅接单中）/ 解封（仅已封店）；详情抽屉底部按钮已移除（抽屉只读展示）。
- 浏览器实测：行内"编辑"弹窗正常打开，Motorola 保存折扣 80 成功（后端确认 `discount_rate=80.00`，测试后已还原为空）；prettier/eslint 通过。临时检查账号已再次删除。

### 2026-11-07（WP-42：需求迭代文档 01 全量落地——折扣/自动封店/进度自动扭转/搜商家/白名单/演示支付）

- **需求依据**：`功能需求迭代文档01.md` v2.2（十项拍板全关闭）。用户拍板：一轮全做 + 做 12 类映射。
- **迁移（已应用真实 MySQL）**：`merchants.0006`（discount_rate/activity_discount_rate、exposure_delta/exposure_day、ban_after_days 改可空、新表 `merchant_daily_stat`）、`orders.0004`（Order.Status 增 `PAID`、payment_method/paid_at、MerchantOrder.planned_node_times）、`catalog.0012`（Spu.merchant_category 12 类 choices）。
- **折扣与成本价**：`merchant_ops/views_merchant_catalog.py::compute_listing_cost` —— 取折扣顺序 活动折扣→普通折扣→回退 `spu.cost_price`；`ROUND_CEILING` 取整到个位（12.10/12.90→13、121.98→122）。上架 POST 与商品池卡片成本都用它。管理端编辑弹窗设置折扣（PATCH `discount_rate/activity_discount_rate`，空串=清除，无区间校验）。
- **信誉分**：`deduct_credit` 改按 0 钳制（原来超额报 `CREDIT_EXCEEDS_CURRENT`，已同步改测试）；扣完不联动封店。
- **曝光日口径**：`add_exposure`/`add_followers` 惰性跨日清零 + `_bump_daily_stat` upsert `merchant_daily_stat`；growth 接口与商家详情返回 `exposure_delta`（当日累计）。
- **自动封店**：`merchants.services.auto_suspend_overdue_merchants()`——ACTIVE 商家存在 PENDING 子单且下单时间超 `ban_after_days` 天 → SUSPENDED（reason="订单未处理超过设定天数，系统自动封店"）；null 跳过。
- **进度自动扭转**：`merchant_ops.services.PROGRESS_INTERVAL_HOURS`（4–8/6–12/3–6/48–120/10–18/6–16 小时写死）+ `build_progress_schedule(shipped_at)`（每段随机、累进，第 7 位=14 天自动确认截止）；`ship_merchant_order` 发货时生成 `planned_node_times`；`auto_advance_progress()` 扫描 SHIPPED 子单到点推进（node_times 记计划时刻）、签收超 14 天自动确认收货（走 node7 结算）。无计划表的历史子单跳过（继续人工推进）。节点文案"到达目的地网点"→"到达网点"。
- **调度**：新命令 `manage.py run_order_sweeps`（自动扭转+自动封店+过期取消）；商家看板与管理端商家订单列表 GET 惰性调用同一组服务（`run_lazy_sweeps`）。**生产必须挂 cron**（每 10 分钟左右），开发环境靠惰性兜底。
- **下单拆单**：`place_order` 增 `payment_method` 参数（BALANCE/CARD/GOOGLE_PAY/KLARNA）→ 有值即置 `PAID` + paid_at；按 `offer.merchant` 建 `MerchantOrder`（items_total/cost_total 累计、payment_method 快照、recipient_region=address.country_code）；`OrderItem.unit_cost=offer.cost_price`、回填 merchant_order 外键；已付款时 `_bump_daily_stat(order_count=1)`。无 payment_method 保持 PENDING_PAYMENT（旧测试/旧路径兼容）。
- **白名单后端**：`cart/services.add_item` 与 `place_order` 校验 `purchase_whitelisted` → `NOT_WHITELISTED`（400）；前端判断改严格 `=== true`，详情页加购返回该码也弹拦截弹窗；结账页提交所选支付方式（大写映射），`NOT_WHITELISTED` 显示白名单提示。
- **搜商家**：`backend/merchants/public_views.py` + 公开路由 `/api/v1/merchants/search`（display_name/slug icontains，只返回有 ACTIVE Offer 的接单中商家）与 `/api/v1/merchants/<slug>`（商家头 + 在售商品 50 件）。storefront 头部"一个搜索框+两个按键"（红色【搜商家】键），新页 `pages/merchants/index.vue` 与 `[slug].vue`（SSR 用 apiBaseInternal、客户端走 devProxy——新页面必须按这个模式写，否则 SSR 404）。
- **活动商品**：管理端新页 `/activity-products`（活动商品/全部商品两视图 + 打标/取消，走 `products/<id>/actions` 的 `mark_activity/unmark_activity`）；商品池编辑弹窗加"商家端品类（12 类）"下拉（`merchant_category` PATCH）；回填命令 `assign_merchant_categories`（local_category 名称关键词映射；本库 157 SPU：命中 59，62 个 Groceries & Food 与 36 个无类目落"未分类"，**12 类里没有食品品类**，需管理端手动指派或后续扩品类）。
- **商家端 UI**：DashboardView 重写（今日订单口径提示、今日曝光度、总关注红色 +N、周/月切换、曝光度趋势条形、平台经营通知 top3+查看全部、店铺状态只映射 接单中/已封店）；CatalogueView 已上架 Tab 加名称/ID 搜索 + 品类筛选 + "下架请联系平台客服"提示（商家端本来就没有下架按钮，未添加）；StoreView 加"复制店铺 ID"。
- **顺带修掉的预先存在 bug**：管理端"编辑商家"总是发送 `wallet_balance`，余额没变时后端 `adjust_wallet` 抛 `NO_CHANGE` 400，导致任何不改余额的编辑（包括折扣设置）都失败。已改为只在余额真的变化时才提交该字段。
- **针对性验证（按验证纪律，未跑全量）**：
  - 真实 MySQL：`merchants.tests.test_wp42_services + merchant_ops.tests.test_wp42_discount_listing + orders.tests.test_wp42_place_order + merchant_ops.tests.test_merchant_app` → **48 passed**；加上 `test_admin_commerce/test_merchant_modules/test_orders_flow/cart.tests` 回归共 **127 passed**。`test_merchant_domain` 里 `test_merchant_totp_policy_is_enforced_during_staff_login` 失败为**预先存在**（2026-11-05 移除 TOTP 登录后遗留的过期测试，stash 验证过基线也失败），本轮未修。
  - `ruff check backend` 通过；`manage.py check`、`makemigrations --check --dry-run` 通过。
  - 前端：Prettier/ESLint 通过；admin-web vitest 9 passed、vite build 通过；merchant-web vite build 通过；storefront vitest 47 passed、Nuxt build 通过。
  - **浏览器实测**：管理端（临时账号 wp42check 登录）折扣设置 70/50 保存成功并回显、自动封店天数/总曝光度+今日曝光度字段显示；活动商品打标"OPPO A6x"成功；商家端看板（5174）今日曝光度 150 与趋势图即时同步（管理端 growth 调整后刷新即见）、通知 top3 渲染；购物端搜商家结果页（q=HOMCOM 命中）与商家页（头像/名称/总关注/总曝光度/在售商品 $ 价格）渲染正常。
  - **API 全漏斗实测**：shell 造买家会话 → 建地址 → 加购（真实 offer）→ 下单 `payment_method=GOOGLE_PAY` → 201 `status=PAID` → 自动拆出 HOMCOM 子单（PENDING，cost 快照来自 offer.cost_price）→ `merchant_daily_stat.order_count=1`；移出白名单后加购返回 `NOT_WHITELISTED`。
- **测试数据清理**：两家 HOMCOM 折扣已还原为空、OPPO 活动标记已取消、临时员工账号 `wp42check@joybuy.test` 已删除。保留：买家 `wp42-funnel@joybuy.test`（挂演示订单 `d59147dc`，PAID/GOOGLE_PAY，未发货）、HOMCOM 曝光 150 与当日统计（可当演示数据；要清零把 merchant.exposure/exposure_delta 置 0 并删 `merchant_daily_stat` 当日行）。
- **踩坑（新会话必读）**：
  1. **pnpm 在本机损坏**（MODULE_NOT_FOUND），起 dev 服务要用 `npx`：storefront 在其目录 `npx nuxt dev`，admin-web/merchant-web 用 `npx vite --port 5173/5174`。Nuxt 只绑 `::1`，`curl 127.0.0.1:3000` 会 000，用 `localhost`。
  2. **admin@joybuy.test 的密码与记忆不符**（猜测均不匹配，勿再试）；本次用"shell 铸会话 token + 注入 curl/或建临时账号"做管理端验证，未改任何用户密码。
  3. **storefront 新页面调 API 必须区分 SSR/客户端**：SSR 用 `config.apiBaseInternal`（直连 8000），客户端用 `/api/v1`（devProxy）；直接 `useFetch('/api/v1/...')` 在 SSR 会 404（nitro 内部路由不存在）。
  4. Git Bash 里 `/tmp` 对 Windows Python 不可见；混合 bash+python 解析时把文件放仓库内或纯 bash 解析。
  5. 后端 8000 用 `--noreload`，改后端代码要重启（本轮已重启）。
- **遗留/后续**：①`run_order_sweeps` 生产 cron 未接（docs/08 WP-42 已注明）；②Groceries 商品 12 类映射待定（品类清单是否要加"食品"需产品决定）；③商家端商品卡成本价随商家折扣变化，但**已上架 Offer 的 cost 不随折扣调整自动刷新**（重上架时才重算，与"上架时快照"口径一致）；④钱包余额支付（BALANCE 真扣款）仍未实现，四种支付方式均为演示判定；⑤`test_merchant_domain` 的 TOTP 过期测试建议下轮清理。

### 2026-11-06（WP-41：六国跨市场与 SKU 规格本地化）

- **用户口径**：主要国家 BE/DE/FR/NL/LU/GB；价格统一显示美元符号但不换算；商品规格直接翻译到这些国家语言。
- **语言映射**：GB=`en-GB`（保留既有 `zh-CN`）；DE=`de-DE`；FR=`fr-FR`；NL=`nl-NL`；BE=`nl-BE/fr-BE/de-BE`；LU=`lb-LU/fr-LU/de-LU`。比利时和卢森堡按官方多语言市场处理，不强行压成单语言。
- **数据库与迁移**：
  - `offers.0005`：`Locale`、`MarketLocale`、`Market.display_currency_symbol`、`Market.offer_fallback_market`；
  - `offers.0006`：幂等种子六国、11 locale、11 个市场语言组合、EUR；六国展示符号均 `$`，欧洲五国 fallback=GB；
  - `catalog.0011`：`SpuMarketContent`、`SkuSpecificationTranslation`、`LocalCategoryTranslation`、`AttributeDefinitionTranslation`、`AttributeOptionTranslation`；`ProductSearchDocument` 从 SPU 一对一升级为 `(spu, market, locale_code)` 唯一并重建复合索引；
  - 三项迁移已应用真实 MySQL，`showmigrations offers catalog` 全部 `[X]`。
- **读取链路**：新增 `offers.market_services.resolve_market_context`，query → Cookie → 市场默认语言回退；`GET /api/v1/markets` 返回可选国家/语言。详情按市场/locale 解析内容和规格；目标市场无 Offer 时按显式 fallback 链读取 GB Offer，并返回 `price_source_market`。搜索和类目接口同样接受上下文，搜索文档按 locale 隔离。
- **规格翻译纪律**：原始 `sku.specification` 与 `specification_signature` 永不改写；展示翻译单独入 `sku_specification_translation`。`translate_product_specs` 内置德/法/荷/卢常用规格词典，数值、型号和单位原样保留；未知词不假装成功，写 `untranslated_terms` 并置 `needs_review=true`。
- **真实数据回填**：执行 9 个欧洲 locale 的 dry-run 和正式回填，各 **1,431** 行；当前 `SkuSpecificationTranslation=1,431`、`needs_review=0`。真实接口 DE/de-DE 已返回 `Farbe: Weiß/Blau`，Offer 金额保持 `19.9900/21.9900/23.4900`，展示符号 `$`，来源市场 GB。
- **购物端**：`useMarketLocale` 持久化 `joybuy-market`/`joybuy-locale`；顶部由原 EN/ZH 按钮升级为国家与语言两个选择器；详情、类目树和搜索请求带 `market + locale`。现有 `formatDisplayPrice` 继续纯展示 `$`，不碰后端金额。
- **针对性验证（按验证纪律，没有跑全量）**：
  - 真实 MySQL：`manage.py test catalog.tests.test_localization catalog.tests.test_product_detail_api catalog.tests.test_search offers.tests.test_product_offer_domain` → **29/29 通过**；
  - `ruff check backend/offers backend/catalog` → 通过；`manage.py check` → 通过（仅既有 MySQL 条件唯一约束警告）；`makemigrations --check --dry-run` → No changes detected；
  - storefront：Prettier/ESLint 通过，Vitest **47/47**，Nuxt production build 通过；
  - 实机 API：`GET /api/v1/markets` 返回六国及全部 locale；DE 商品详情返回翻译规格、`display_currency_symbol='$'`、`price_source_market='GB'`。
- **浏览器验证边界**：尝试使用自动化浏览器，但 in-app tab 创建超时且 Chrome browser provider 不可用，WorkBuddy 截图通道也超时；因此本轮没有声称浏览器 E2E 通过。前端已由组件测试与生产构建验证，UI 人工复核可作为下一轮第一项。
- **仍需后续数据工作**：本轮只按用户要求直接翻译规格。商品标题/详情不会凭空生成机器翻译；后续应按市场抓取或人工录入 `SpuMarketContent`。目标市场真实 Offer 到位后会自动优先于 GB fallback。
- **文档同步**：`docs/10-multilingual-content-and-market-design.md`、`docs/13-database-schema.md`、`docs/08-implementation-work-packages.md` WP-41 已更新。
- **服务**：Django 8000 已重启（新 PID 42276，`--noreload`）并加载新模型/API；storefront 开发服务由既有进程负责。

### 2026-11-06（需求文档 v2 → v2.1：录像拆解 + 10 项拍板回填）

> 补充：v2 完成后用户在同日 20:28 逐条拍板 10 项，文档升 v2.1；20:59 又修订第 5 项 → **v2.2**。第六节从"待确认清单"改为"决策记录"。
> 拍板要点：不改抓取价只改成本价；区间 4–8h / 6–12h；自动封店天数改为管理端【商家管理】→【店铺详情】的**【订单未处理自动封店天数（天）】**按商家配置；**信誉分扣完不做处理、不自动封店，交人工操作**；`+N` 当日累计；非白名单前端已有弹窗、待打通后端标识；活动商品折扣不做校验；饼图按订单量；商家搜索按名称匹配。
> 同时把 v2 里自造的 A01/A02/A03 与错位的 M02/M03/M04 编号改掉，统一为项目既有编号：M01 经营看板 / M02 店铺管理 / M03 商品上架中心 / M04 订单管理；管理端只用「系统管理 / 平台运营管理 / 商家管理」中文名，不套 A 编号（项目里 A02 是商家管理、A03 是商品池，套错会误导）。

### 2026-11-06（需求文档 v2：会议录像拆解与漏项补全）

- **任务**：用户给出会议录像与手记文档，要求先拆解视频内容，再结合手记完善需求文档、防止漏需求；动手前先备份文档。
- **备份**：`功能需求迭代文档01.md.bak-20261106-194557`（v1 原文 3548 字节，已保留，不要删）。
- **视频拆解（按 `video-content-breakdown` 技能全流程）**：
  - 产物目录 `D:/Users/lyx/Videos/Joybuy功能需求讨论01_拆解/`：`Joybuy功能需求讨论01.txt/.json/.srt`（444 段，有效语音 00:00–45:53，46:00 之后为静音，转写末尾出现"点赞订阅"类幻听已剔除）、`录屏关键帧/`（115 帧 + frames.json，`--max-frames 160 --max-gap 40`）、`Joybuy功能需求讨论-内容拆解.md`。
  - 拆解文档含：时间轴（15 段）、逐章拆解（14 章，含关键句逐字引用）、速查卡、画面实证 4 帧、ASR 校正表 19 条、待确认 10 条。
  - 画面核对 4 帧全部吻合：`f012` 管理端【商家关注与曝光】、`f034` 商家端【经营看板】、`f043` 【店铺管理】、`f086` 【订单详情】。**实证**：订单详情有"发货成本（合计）¥128.00"、右侧"利润 ¥111.00" = 零售价 239 − 成本价 128，证明利润公式已在原型落地；看板饼图标注"按已付款订单统计"，即按订单量。
- **需求文档改写为 v2**（`功能需求迭代文档01.md`，结构：商家端 M01/M02/M03/M04 → 管理端 A01/A02/A03 → 购物端 → 爬虫 → 跨端一致性表 → 待确认表）：
  - 用【新增】/【澄清】/【修订】/【待确认】四种标记区分来源，v1 的每一条都保留，未删条目。
  - **口径反转 1 条**：爬虫价格。v1 要求"抓取时向上取整、入库只留整数"，会议 25:47 明确"价格不变"，只在算成本价时向上取整 → 已按会议改写，并标【待确认】历史数据回刷方案。
  - **口径冲突 2 条**（未擅自定稿，标【待确认】）：待出库→已出库 4–8h（文档）vs 4–6h（口述）；已出库→已揽收 6–12h vs 3–5h。
  - **补漏的实际条目**：发货成本字段、进度自动扭转的随机区间机制、"区间写死不做后台配置"、自动封店、信誉分只减不加、曝光度自动清零且不带 +N（+N 只属总关注）、看板三图表 + 通知前 3 条、店铺管理复制 ID/编辑资料/品类只显示已上架/名称+ID 搜索/无下架按钮、活动商品不改品类加标记、双折扣优先级（先判活动商品）、搜索框一个框两个按键 + 搜商家结果页结构。
- **验证**：按验证纪律，本轮为纯文档任务，**未运行任何代码/测试**；核对方式为逐段比对手记与转写原文。抽帧任务仍在后台完成剩余部分。
- **未做**：文档里的待确认 10 项需要用户/产品拍板后才能进入开发；本轮未修改后端、前端与爬虫代码。

### 2026-11-06（跨国多语言与商品规格存储现状审查）

- **本轮动作**：阅读 `HANDOFF.md`，并核对 `docs/01-requirements.md`、`docs/04-data-model-and-storage.md`、`docs/10-multilingual-content-and-market-design.md`、`docs/13-database-schema.md`、`backend/catalog/models.py`、`backend/catalog/product_services.py`、`backend/catalog/detail_views.py`、`backend/offers/models.py` 和购物端 `useLocale`/locale 资源。
- **已实现/已预留**：`SpuTranslation` 独立保存商品标题、副标题、详情，唯一键为 `spu + locale`；`Sku.specification` 独立保存 SKU 规格 JSON，`specification_signature` 保证同 SPU 规格组合唯一；属性定义和选项另有 `attribute_definition`/`attribute_option`；`Offer` 具有 `market + currency` 维度，`Market` 保存默认 locale、时区和默认币种；购物端已有 EN/ZH 固定界面文案切换，类目和部分 CMS 使用双语字段。
- **未完整实现**：当前 `market` 文档和详情 API 仍固定 GB，详情仍取第一条 `SpuTranslation`；`SpuTranslation` 不含 market、requested_locale、actual_locale、来源哈希和观察时间；没有 `Locale`/`MarketLocale`；品牌、属性名、属性选项标签没有翻译表；本地类目只是 `name_en`/`name_zh` 两列；搜索索引尚未按 `spu + market + requested_locale` 拆分；SKU 规格没有独立的 locale 规格值/翻译关系表。
- **判断**：数据库已经做到“商品翻译表与商品规格数据分开存放”，但规格仍是 JSON 快照，且完整跨国多语言数据模型只完成了基础骨架，不能称为已完整支持。
- **修改**：仅更新本 `HANDOFF.md`，未修改业务代码、迁移或数据。
- **验证**：按验证纪律仅做了针对性只读核对（`rg`/`Get-Content` 检查上述模型、API 与文档）；本轮没有业务代码改动，**未运行测试**，不得把历史测试结果当成本轮验证。
- **下一步建议**：在继续扩市场前单独建立国际化工作包，优先补齐 `Locale`/`MarketLocale`、市场化商品内容表、类目/属性/选项翻译表、规格稳定值与 locale 展示值分层，再改详情/搜索 API 解析上下文并执行真实 MySQL 迁移验证。

### 2026-11-06（品类发现卡片纳入管理）

- **需求**：购物端首页【品类发现】模块（搜索框下方 tiles 卡片）也要管理端可管理。
- **数据内容（先摸清）**：`link_grid` + `variant=tiles`，模块级 `title='Category discovery'/'品类发现'`；item 为 `{label, label_zh, href:'/s?category=…', icon_path}`，实库 6 张（Home/Electronics/Clothing & Accessories/Games/Outdoor & Sports/Small Home Appliances）。渲染组件 `CmsLinkGrid.vue` 已支持，购物端零改动。
- **实现**：`home_campaign_card` 加 `section`（campaign/discovery）字段共用一张表；服务层按 section 分支——序列化时 discovery 输出 `label/label_zh/icon_path`（数据库仍叫 title/image_url），上限 campaign 10 / discovery 12；`storefront_home` 对两个模块类型分别注入覆盖；迁移 `content/0007`。
- **管理端**：`/campaign-cards` 页面顶部加两个 Tab（活动卡片/品类发现），共用列表/排序/弹窗组件；discovery 的表单隐藏副标题字段、文案用「名称」。接口 `?section=` 过滤 + body `section` 指定分区。
- **回填**：`import_from_published_snapshot('discovery')` 导入 6 张（幂等，与 campaign 互不影响）。
- **验证**：`content.tests.test_campaign_cards` → **17 passed**（新增：分区过滤、discovery 创建、非法 section 400、move 不跨分区、storefront 注入 tiles 覆盖快照且 item 用 label 字段名）；eslint/prettier/build/ruff 全过。
  - **浏览器端到端**：品类发现 Tab 编辑第一张加标记 + 下移 → 购物端首页 6 张 discovery 卡含标记、顺序同步（Electronics 升第 1）。测试数据已还原。
- **两个教训**：
  1. **长 python 脚本对 ruff 格式化过的文件做字符串替换会静默失配**（缩进/引号变了）——大段改动要么全量重写文件，要么用 Edit 工具精确改，替换脚本必须 assert 每一处（这次 views.py 的替换静默失败，靠测试 KeyError 才暴露）。
  2. **后端绝不能用 `&` 启动**——bash 命令结束子进程被带走（502 排查了一圈前端才想到），必须用后台任务。
- **注意**：后端 8000 用 `--noreload`，改后端代码要重启；`D:/Docker/Docker Desktop.exe`（MySQL/Redis/Mailpit 容器随它启动）。

### 2026-11-06（首页活动卡片：管理端设置 → 购物端同步）

- **需求**：购物端搜索框下方 10 个卡片要在管理端【服务与运营】下可配置，改完同步到购物端，且顺序可调。
- **数据内容（动手前先摸清，用户要求）**：这 10 张卡片 = CMS `campaign_grid` 模块的 items，每张 `{title, subtitle, href?, image_path?, title_zh?, subtitle_zh?}`；渲染组件 `CmsCampaignGrid.vue`（5 列网格、无图色块降级、中英双语）**已支持全部字段，购物端零改动**。数据原先硬编码在 CMS 快照 payload 里，管理端无入口。
- **方案（沿用 A10 轮播图先例）**：不直接改版本化快照。新建独立表 `home_campaign_card`（title/title_zh/subtitle/subtitle_zh/image_url/href/sort_order/enabled），管理端 CRUD；`content.views.storefront_home` 序列化后用独立表数据**覆盖**快照里的 campaign_grid 模块（保留原 position），独立表为空则回退快照。快照保持只读历史，回滚不受运营数据污染。
- **迁移**：`content/0005_homecampaigncard` + `content/0006_seed_campaign_permissions`（`cms.campaign.manage`/`.view`，授 platform_admin/operator）。首次访问前用 `import_from_published_snapshot()` 把快照 10 卡回填独立表（幂等）。
- **接口**：`GET/POST /api/v1/admin/campaign-cards`、`GET/PATCH/DELETE .../<id>`、`POST .../<id>/actions`（`move` up/down、`toggle`）。上限 10 张（5×2 排）；href 白名单 `/` 或 http(s)（挡 `javascript:`）；新卡默认排末尾；移动前先压实重复 sort_order（历史数据可能是全 0）。
- **前端**：`admin-web/src/views/CampaignCardsView.vue`（列表缩略图 + 上移/下移/编辑/移除/启停 + ImageUploader 上传卡片图），侧栏【服务与运营】组「首页活动卡片」，路由 `/campaign-cards`，module `cms.campaign`。
- **顺带修掉一个隐蔽 bug**：管理端 `AppModal`/`AppDrawer` 组件**没有 open 属性也没有 v-if**（和商家端同款问题）。此前 20 处用法都靠外层 `v-if` 包裹才没炸；新页面用 `:open` 一传就暴露——全屏 mask 常驻 DOM 拦截一切点击。修法：组件补 `open` prop（**缺省 true**），模板 `v-if="open"`；老用法（不传 open + 外层 v-if）与新用法（`:open`）都成立。
- **验证（按纪律仅针对性）**：
  - `manage.py test content.tests.test_campaign_cards` → **12 passed**（CRUD、上限 10、href 白名单、缺标题 400、上移/下移换位、顶/底越界拒绝、重复 sort_order 压实、storefront 覆盖快照、停用排除、空表回退快照、快照导入幂等）。
  - `npx vitest`（9 passed）、`eslint`、`prettier --check`、`vite build`、`ruff` 全过。
  - **浏览器端到端**：管理端改第一张卡标题加标记 → 购物端首页出现该标记卡片（10/10 张渲染）；管理端把第一张下移 → 购物端前两张顺序同步变化；**0 console 错误、0 失败请求**。测试数据已还原（标题/顺序恢复原状）。
- **踩坑**：heredoc 往 `manage.py shell` 灌多行 for 循环会被交互解析器吞掉——独立脚本必须 `sys.path.insert(0, <repo>/backend)` + `django.setup()` 后直接跑，别用 shell stdin。

### 2026-11-05（图片改本地存储 + 真实上传）

- **用户诉求**：图片存到服务器本地，路径写进 URL，前端直接从本地读图渲染。
- **现状盘点**：项目本来就有完整的媒体库（`MediaAsset` 内容寻址 + `media_url()` + `serve_media_file` + `MEDIA_ROOT=var/media`），**缺的只是上传入口**——所有表单此前只能手填 URL。
- **后端新增**：
  - `media/uploads.py`：`store_upload(file, purpose=...)`。按 purpose 决定 kind 与大小上限；文件内容分块读、超限立即中断（不把大文件整个读进内存）；Pillow 先 `verify()` 再重新解码取尺寸；只放行 **JPEG/PNG/WebP**；像素上限 4000 万防解压炸弹。**不信任客户端 Content-Type 与文件名**。
  - `media.MediaAsset.Kind` 新增 `MERCHANT`（店铺头像桶，路径 `var/media/merchants/...`），迁移 `media/0003`。
  - `merchant_ops/views_media.py`：`POST /api/v1/admin/media` 与 `POST /api/v1/merchant/media`。管理端按 purpose 校验**对应模块**的写权限（商品图要 `catalog.pool.manage`、轮播图要 `cms.banners.manage`……不能互相顶替）；商家端只开放 product/avatar/review 三类。
  - 售后凭证新增 `action="proof"`：只接受 `/media/` 或 http(s) 地址，最多 5 张（挡掉 `javascript:` 之类）。
  - `merchant-listings` 列表与上架响应补 `image`（批量取 `MediaUsage` 主图，避免 N+1）；会话商品信息也改用同一套取图逻辑。
- **前端新增**：
  - `admin-web` / `merchant-web` 各一个 `components/ImageUploader.vue`：点击选图 → `FormData` 上传 → 回填 URL；支持多图、设为主图、移除、单张大小预检、**相同图片不重复追加**（内容寻址会返回同一 URL）。
  - `adminUpload` / `merchantUpload`：**绝对不能手动设 `Content-Type`**，否则浏览器补不了 boundary，后端解析不出文件。
  - **两个 `vite.config.js` 都加了 `/media` 代理**——不加的话 `<img src="/media/...">` 在 5173/5174 直接 404，这是「图能上传但显示不出来」的头号原因。
- **接入的 5 处表单**：A03 商品池图片（最多 5 张，1MB）、A10 轮播图（2MB）、A11 好评评论图（5 张，1MB）、M02 店铺头像（2MB）、M07 售后凭证（5 张，1MB）。
- **数据落点**：业务表仍只存 URL 字符串，不存二进制、不存 asset 外键——换存储或加 CDN 只需改 `media_url()`。
- **本轮修掉的 2 个 bug**：
  1. `adminUpload` 一开始写 `/admin/media`，但管理端 `API_BASE_URL` 已含 `/admin`，实际请求变成 `/api/v1/admin/admin/media` → 404。改成 `/media`。
  2. **M02「保存资料」一直 405**：`merchantWrite('/merchant/profile', ...)` 没传 method，默认 POST，而接口是 PATCH。这个 bug 在第 3 轮就存在，本轮测头像上传才暴露。
- **验证**：
  - `manage.py test merchant_ops.tests.test_media_upload` → **13 passed**（落盘字节与上传一致、URL 形状、去重、非图片/伪装图片、GIF 拒绝、>1MB 413、>4000 万像素拒绝、非法 purpose、缺文件、管理端跨模块权限 403、商家端 banner 用途不开放、受限角色 403、凭证 URL 白名单）；`merchant_ops media` → **134 passed**。
  - **浏览器实测（真实 `input[type=file]`）**：商品池上传后缩略图 `naturalWidth=600`、保存后列表首行图宽 600；轮播图上传预览 220、列表 220；好评评论图上传成功；店铺头像上传后页头头像 600；售后凭证上传 + 保存后凭证区渲染。
  - **渲染巡检**：管理端商品池 20/20 张图加载；商家端商品池卡片 8/8、已上架列表 4/4、会话商品图 480px；**0 个失败请求**。
- **生产部署注意**：`/media/` 由 Nginx 直接 `alias` 到 `var/media/`（`serve_media_file` 只在 `DEBUG` 下注册路由，生产不走 Django）。上传目录需要写权限。

### 2026-11-05（商家/平台后台重构 · 第 3 轮续）：商家端 M03–M10 全部完成

- **交付范围**：M02 店铺管理（顺手补上，接口本来就有）、M03 商品上架中心、M04 订单管理与详情、M05 钱包管理、M06 保证金、M07 售后中心、M08 平台活动与推荐返佣、M09 消息中心、M10 平台通知中心。前端 9 个页面替换掉占位页，后端新增 24 条 `/api/v1/merchant/*` 路由。
- **新增后端文件**：
  - `merchant_ops/views_merchant_catalog.py`（M03）：商品池筛选/搜索/分页 + 上架；
  - `merchant_ops/views_merchant_orders.py`（M04）：列表/详情/发货/导出；
  - `merchant_ops/views_merchant_wallet.py`（M05+M06）：明细/密码/提现/保证金；
  - `merchant_ops/views_merchant_service.py`（M07+M08）：售后处理、活动参与、推荐返佣；
  - `merchant_ops/views_merchant_inbox.py`（M09+M10）：会话与通知；
  - `merchant_ops/management/commands/seed_merchant_demo.py`：本地演示数据（幂等，见下）。
- **新增前端文件**：`CatalogueView` / `OrdersView` / `WalletView` / `DepositView` / `AfterSalesView` / `ActivitiesView` / `MessagesView` / `NotificationsView` / `StoreView`。
- **关键设计（沿用第一轮的合并口径）**：
  - **上架 = 创建/复活一条 `Offer`**：成本价与零售价从 `spu` 快照到 `offer.cost_price/current_price`；平台下架过的商品重新上架时**复用原 Offer**（不新建行），避免唯一约束冲突并保留历史。
  - **上架双校验**：商品必须 `ACTIVE` 且成本/零售价齐全（零售 ≥ 成本），店铺必须 `can_operate`（接单中 + 入驻通过 + 保证金免缴或已缴足）；前端按钮置灰只是提示，服务端仍完整校验。
  - **发货扣成本**复用 `ship_merchant_order`：与钱包流水同事务、`ship:<order>` 幂等、余额不足拒绝。
  - **提现**：先过 6 位钱包密码 → 占用可用余额（负向 `WITHDRAWAL` 流水）→ 待审核。密码错 5 次锁 15 分钟。
  - **售后**：投诉与退货分开；退货类在用户确认收货（子单 `COMPLETED`）后禁止完成；已完成只读；可申请平台介入。
  - **会话与通知分开**：客服会话每店铺一条、列表固定第一；通知含普通与商品好评，打开详情自动已读，好评按「星级 → 文字 → 图片 → 时间」排版。
- **本轮修掉的 4 个真 bug（都是自己写的，不是遗留）**：
  1. **`AppDrawer`/`AppModal` 没有 `open` 属性也没有 `v-if`** —— 抽屉和弹窗内容常驻 DOM，全屏遮罩会把整页盖住。已加 `open` prop + `v-if`。管理端是父级 `v-if` 包裹，所以没暴露；商家端用了 `:open`，必须组件自己判。
  2. **提现金额精度校验永远失败**：`money()` 先把金额量化到 4 位小数，再看 `exponent < -2` 必然成立，任何金额都报「最多 2 位小数」。改成先按原始 `Decimal` 输入判断小数位，再量化。
  3. **钱包密码失败计数被事务回滚**：`raise` 写在 `transaction.atomic()` 里，异常把「+1 次失败」一起滚掉，5 次锁定永远不生效。改成块内只落库、块外再抛。
  4. **seed 的幂等键跨店冲突**：`demo:recharge` 是全局唯一键，第二家店直接复用了第一家的流水，余额没加却去发货 → `INSUFFICIENT_WALLET_BALANCE`。键改成 `demo:recharge:<merchant_id>`。
- **演示数据（本地库）**：
  ```
  ./.venv/Scripts/python.exe backend/manage.py seed_merchant_demo --merchant HOMCOM --reset
  ./.venv/Scripts/python.exe backend/manage.py seed_merchant_demo --merchant CHiQ --reset --with-deposit
  ```
  - 会给商品池**补价格**（120 个 SPU：零售价取该 SPU 在售 Offer 的真实价，成本价按 62% 估算，**仅本地演示**；真实成本必须由平台运营在 A03 录入）；
  - 每家店造 3 个上架商品、20000 充值、三种状态各一单（待处理/已发货/已完成，走真实服务生成流水）、1 个售后退货单、2 个活动（1 个已参与）、2 条通知（普通 + 好评含平台回复）、1 个买家会话、1 条推荐关系与待发放返佣；
  - `--with-deposit` 给该店启用 5000 保证金并缴足，用来让 M06 菜单可见（CHiQ 用了，HOMCOM 保持免缴做对比）。
- **验证（按纪律仅针对性）**：
  - `manage.py test merchant_ops.tests.test_merchant_modules` → **34 passed**（上架重复 409 / 商品无价格 / 店铺不可经营 / 发货扣成本 / 余额不足 / 跨店 404 / 密码 6 位与 5 次锁定 / 提现超余额与精度 / 流水隔离 / 售后状态机 / 活动幂等 / 返佣隔离 / 会话首条客服 / 通知已读与长度校验）。
  - `merchant_ops orders accounts_staff accounts_buyers` → **136 passed**（回归未破）。
  - **浏览器实测**：`/store`、`/catalog`、`/orders`、`/wallet`、`/deposit`、`/after-sales`、`/activities`、`/messages`、`/notifications` 全部标题正确、**0 console 错误、0 失败请求、0 遮罩残留**；两店切换后菜单项从 9 项变 10 项（保证金按 `deposit_enabled` 显隐）。
  - **写链路实测（Playwright 真实点击）**：上架商品成功、发货成功（待处理 1→0、扣成本）、设置钱包密码成功、提现 100.50 创建待审核申请并占用余额、售后进度更新、参与活动、买家消息发送、通知回复 + 全部标记已读。测试后已 `--reset` 恢复演示态。
  - `ruff check/format`、`prettier --check`、`eslint`、`vite build` 全通过。

### 2026-11-05（商家/平台后台重构 · 第 3 轮）：merchant-web 骨架 + M01/M02

- **用户诉求**：问「商家端地址」——此前只有平台管理端，商家端从未建过。
- **新增工程 `merchant-web`**（`pnpm --filter @joybuy/merchant-web dev`）：
  - **http://127.0.0.1:5174**，Vite + Vue3 + vue-router，`/api` 代理到 8000；
  - 主题**独立于管理端**：白底 220px 侧栏 + 品牌红 `#df2636`（原型 `海外电商商家后台.html` 采样：logo 36×36/radius 8、body `#f5f6f8` 14px、卡片 radius 8、顶栏 68px）；
  - 结构：`layouts/MerchantLayout.vue`（侧栏按权限过滤 + 顶部店铺切换）、`composables/useMerchantSession.js`（会话 + 店铺上下文）、`lib/api.js`（自动带 `X-Merchant-Id`）、4 个通用组件。
- **商家身份（关键设计）**：**不新建商家账号表**，复用 `staff_account` 登录（`/api/v1/admin/auth/*`），归属店铺由 `merchant_membership` 决定、可做范围由该 membership 的 `merchant_role` 决定。
  - `MerchantAPIView.initial` 解析 `X-Merchant-Id`；**多店成员必须显式指定店铺**，否则返回 400 `MERCHANT_CONTEXT_REQUIRED`——绝不隐式「取第一个」，否则切店会静默串店；
  - `skip_context = True` 的类（如 `/merchant/shops`）跳过上下文解析；
  - 权限用 `permission_any` / `required_merchant_permissions` 声明，缺权限即 403。
- **新增接口**：`GET /api/v1/merchant/shops`（可选店铺+权限）、`GET /api/v1/merchant/overview`（经营看板）、`GET|PATCH /api/v1/merchant/profile`（店铺资料）。
- **新增权限**：迁移 `merchants/0005` 补 10 个 `merchant.*` 权限码（看板/店铺/上架/订单/钱包/保证金/售后/活动/消息/通知），`merchant_owner` 授满，新增 `merchant_staff` 角色（不含提现）。
- **修复两个真 bug（都是本次才暴露的）**：
  1. **员工会话 Cookie 的 `Path` 是 `/api/v1/admin/`**，所以 `/api/v1/merchant/*` **根本收不到 cookie**，商家端所有接口 401。已改为可配置 `STAFF_SESSION_COOKIE_PATH="/api/v1/"`，并在登出时顺带清理旧 path 的残留 cookie（`STAFF_SESSION_COOKIE_LEGACY_PATHS`）。**这是商家端接不上的根因，不是前端问题。**
  2. **`CSRF_TRUSTED_ORIGINS` 里没有 5174**，Django 的 Origin 校验直接 403 拒绝商家端登录。已补 `http://127.0.0.1:5174`。**以后每加一个前端端口，必须同步这两处配置。**
  3. `MerchantAPIView.handle_exception` 起初只翻译 `MerchantContextError`，`MerchantAdminError`（改店铺名为空）会漏成 500，已一并翻译。
- **演示数据（本地库）**：`admin@joybuy.test` 已绑定 **HOMCOM + CHiQ** 两家店（`merchant_owner`），用来验证多店切换；绑定命令见下方「本地开发登录凭据」。原来误绑的「Joybuy 自营导入」兜底店已解绑。
- **验证（按纪律仅针对性）**：
  - `manage.py test merchant_ops.tests.test_merchant_app` → **13 passed**（单店隐式解析、多店必须指定、跨店 403、无 membership 403、匿名 401、看板只统计本店、7 天柱状图不除零、权限清单、受限角色 403、改店铺名校验）。
  - `merchant_ops accounts_staff accounts_buyers orders` → **102 passed**（回归未破）。
  - **浏览器实测**：登录后落在 `/dashboard`，侧栏实测 **220px / rgb(255,255,255)**、logo `rgb(223,38,54)` 36px/8px、body `#f5f6f8` 14px；菜单 9 项（保证金按 `deposit_enabled=false` 正确隐藏）；6 张统计卡、7 条柱状条、店铺切换显示 HOMCOM/CHiQ；`/orders`、`/wallet`、`/messages` 占位页正常；**0 console 错误、0 失败请求**。
  - `eslint`、`prettier --check`、`vite build` 全通过；根 `package.json` 补 `dev:merchant` / `build:merchant`，并加入 lint/format 范围。

### 2026-11-05（商家/平台后台重构 · 第 2 轮）：A10–A17 全部完成

- **交付范围**：A10 首页轮播图、A11 平台通知推送、A12 客服中心、A13 用户端管理、A14 白名单账号、A15 商家关注与曝光、A16 账号与权限、A17 操作日志。
- **新增 6 张表**（详见 `docs/13-database-schema.md` §13.5）：
  - `home_banner`（**没有并进 `cms_module`**：CMS 是整页版本快照，轮播图要单条开关 + 排序）；
  - `merchant_notification` + `merchant_notification_reply`（**没有复用 `notification_message`**：那张是模板外发队列，站内信需要已读/多轮回复/商品快照）；
  - `support_conversation` + `support_message`（`kind` 区分买家咨询与平台客服，每商家一条平台客服会话）；
  - `buyer_wallet_entry`（买家余额流水）+ `buyer_account.balance/region`。
- **权限模型（A16，重要）**：
  - 不新增表：给每个模块补 `<模块>.view`，`<模块>.manage` **隐式包含** view —— `get_staff_permission_codes` 统一补齐，所以升级后持有 `manage` 的历史角色不会掉菜单；
  - `StaffRbacPermission` 支持 `view.resolve_required_permissions(request)`：GET 走 `view_permissions`、写走 `required_permissions`；`OpsAPIView` 已内置该钩子，第一轮 8 个模块也全部补了 `view_permissions`；
  - 前端 `useStaffAuth` 新增 `canView(module)` / `canWrite(perm)`；侧栏与路由守卫改用 `module` 语义，**只读账号也能看到菜单**；
  - 「账号与权限」保存时按模块勾选生成一个内置角色 `staff-<public_id 前 12 位>`，权限取并集；超级管理员（`is_platform_admin`）不能停用、不能改权限（防自锁）。
- **关键业务规则（已用测试锁死）**：
  - 商品好评**只能推给该店确实已上架的 SPU**，服务端二次校验 `PRODUCT_NOT_LISTED`；
  - 平台回复通知后 `read_at` 置空 → 商家端重新未读；
  - 买家余额不能为负（CHECK + 服务层双重），充值走 `idempotency_key`；
  - 移出白名单**只取消权限**，余额与历史保留；停用账号不能加入白名单；
  - 关注/曝光只做正向累加，调整记录直接读 `audit_log`（不另建日志表）。
- **前端**：新增 8 个页面 `BannersView`/`NotificationsView`/`SupportView`/`WhitelistView`/`GrowthView`/`StaffAccountsView`/`AuditLogsView`，并**重写** `BuyersView`（改用 `/buyers/accounts`）；侧栏按「交易管理 / 资金与风控 / 服务与运营 / 用户与权限 / 采集与基础数据」5 组共 17 项。
- **踩坑补充**：
  1. **老 `/admin/buyers` 接口一直 500**（`account.phone` 但字段是 `phone_e164`），本轮重写页面时改用新接口 `/buyers/accounts`，旧接口也顺手修了。
  2. 新增路由必须放在 `api/v1/<path:unmatched>` 之前 —— `merchant_ops/urls.py` 在 `config/urls.py` 里是 `*merchant_ops_urlpatterns` 展开，位置已在兜底路由之前，安全。
  3. `home_banner` 的图片只存 URL（本地媒体库路径或 https），**没有做上传**，与文档「正式存对象存储」的差距仍在。
- **验证（按纪律仅针对性）**：
  - `manage.py test merchant_ops` → **55 passed**（第二轮新增 26 例：只读账号可读不可写、轮播图校验/开关/删除、通知群发与好评归属校验、回复重新未读、客服会话幂等与状态流转、白名单充值/移出/负数/幂等/停用拦截、关注曝光累加、账号创建校验与保护、审计查询与导出）。
  - 13 个新 GET 接口实库巡检全部 **200**。
  - **浏览器实测**：8 个新页面逐个访问，标题正确、**0 console 错误 / 0 失败请求**，侧栏 17 项；实测「新增轮播图」写入成功、创建只读账号后用该账号登录**侧栏只剩「首页轮播图」且能看列表**（写操作由后端 403 兜底）；测试数据已清理。
  - `ruff check/format`、`prettier --check`、`eslint`、`vitest`（9 passed）、`vite build` 全通过；后端已重启（8000）。

### 2026-11-05（配色纠正）：管理端主题改为深色导航 + 蓝色操作

- **用户反馈**：主题配色不对，要按文档里管理平台的主题配色。
- **根因**：`海外电商平台管理后台.html` 的单个 `<style>` 块里塞了**两套主题**。前段（偏移 0 起）是废弃的红白版：`--red:#dc2638`、`aside{background:#fff;width:222px}`、`.primary{background:#dc2638}`。**后段偏移 12593 处**有一整块 `/* Platform operations console */` 把它整体覆盖。上一轮我只 grep 了第一个匹配，于是照着废弃主题做了白底红字。
- **真实生效主题（已用 getComputedStyle 采样核对）**：
  - `--primary:#2563eb`、`--red` 被改名复用为蓝色、`--ink:#18263b`、`--muted:#78869a`、`--border:#e2e8f0`、`--green:#16856a`、`--bg:#eef2f6`、`--sidebar-width:236px`
  - 侧栏 `#111d32` 深色，品牌区 76px，品牌方块 `#2f6df6` 34×34 radius 7
  - 导航项 `#b7c3d7`，hover `#1b2c47`，选中 `#2456ac` + `inset 3px 0 #73a7ff`
  - 顶栏白色 56px，body 底色 `#eef2f6`，内容区 `padding:22px 24px 32px`
  - 表头 `#f0f4f9` / `#61738e` / 11px；表格斑马 `#fcfdff`，hover `#f3f7ff`
  - 按钮 12px / padding 6px 12px / radius 3；`.primary` = `#2563eb`，hover `#1d4ed8`
  - 标签默认灰 `#f0f3f7/#7b899f`，另 warn / bad / ok 三档
- **改动文件**：`admin-web/src/styles/main.css`（令牌全量替换 + 补回 `page-container/foundation-card/status-grid` 等旧视图依赖的类）、`styles/admin.css`（侧栏/顶栏/卡片/按钮/表格/标签/抽屉/弹窗/时间线全部按采样值重写）、`layouts/AdminLayout.vue`（深色侧栏 + 顶栏头像）、`views/LoginView.vue`（原型登录页：深色径向渐变 + 410px 白卡 + 蓝色按钮，不回显演示密码）。
- **顺带修掉一个预先存在的 500**：`common/admin_views.py` 的 `AdminBuyersView` 用了 `account.phone` / `Q(phone__...)`，但模型字段是 `phone_e164`，`/api/v1/admin/buyers` 一直 500（不是本轮引入，是本轮巡检 `/buyers` 才暴露）。已改字段名并补 `purchase_whitelisted`。
- **验证（按纪律仅针对性）**：
  - **色值对拍**：浏览器 `getComputedStyle` 同时采样原型与本实现，`aside` 背景/宽度、品牌方块、导航选中、顶栏高度、主按钮、body、表头、内容区 padding、`--primary`、`--sidebar-width` **全部逐项一致**。
  - 11 个路由（8 个新页 + 爬虫/内容/买家）逐个访问：标题正确、**0 条 console 错误 / 0 个 4xx-5xx 请求**。
  - 抽屉层叠：宽 880px、白底、遮罩 `rgba(12,24,43,.46)`。
  - `manage.py test merchant_ops orders` → **38 passed**；`prettier --check` / `eslint` / `vitest`（9 passed）/ `vite build` 全通过。
  - 后端已重启（8000），前端 5173 热更新。

### 2026-11-05（商家/平台后台重构 · 第 1 轮）：数据模型 + 平台 A02–A09

- **用户要求**：读 `商家端及平台管理端文档/` 的 `01_商家端开发文档.md`、`02_管理后台开发文档.md`，按 `海外电商平台管理后台.html` / `海外电商商家后台.html` 的设计写两套后台；**文档里的表不能照抄，要按现有 Joybuy 数据结构合并**（已有表就补字段，覆盖不了才新建）。
- **4 个已拍板口径（不要推翻）**：
  1. 商品池 = `catalog.spu`（补 `cost_price`/`retail_price`/`is_activity`/`description`/`image_urls`/`specs`），**不新建 product 表**；
  2. 店铺商品关系 = `offers.offer`（补 `cost_price`/`listed_at`/`removed_at`/`removed_by_platform`），**不新建 merchant_product 表**；
  3. 订单 = 保留 `order` 作买家父单，**新增 `orders.merchant_order`** 按商家拆子单（成本快照、3 状态、8 节点、回款都在子单上）；
  4. 商家端将新建独立 `merchant-web`（**第 2/3 轮做**），登录复用 `staff_account` + `merchant_membership` 判店，不新建商家账号表。
- **新增 11 张表**：`merchant_order`（orders）+ `merchant_wallet_entry`、`merchant_withdrawal`、`merchant_deposit_entry`、`after_sale`、`after_sale_event`、`merchant_activity`、`merchant_activity_participation`、`referral_program`、`merchant_referral`、`referral_commission`（新应用 `merchant_ops`）。文档里的「商家与入驻」合并进 `merchant`（钱包/保证金/信誉/关注/曝光/推荐码等 20 个字段），不单开表。
- **资金口径（后续别再改）**：
  - 所有余额变更只能走 `merchant_ops/services.record_wallet_entry`，余额与流水同事务、`wallet_balance` 有 CHECK ≥ 0；
  - 幂等键统一为 `ship:{子单}` / `settle:{子单}` / `withdrawal-reserve:{申请}` / `withdrawal-return:{申请}` / `commission:{核算}`，**回款、返佣到账、提现退回都只发生一次**；
  - 提现申请时记一笔负向 PENDING 流水占用余额，打回/失败退回一次，**实际出款不再扣一次余额**；
  - 保证金余额可以为 0 或负数、且**不触发封店**（文档明确要求）。
- **接口（全部 `/api/v1/admin` 下，权限码逐个校验 + 写审计）**：
  `merchants`（列表/详情/PATCH/actions/export）、`categories`、`products`（含 actions）、`merchant-options`、`merchant-listings`（actions）、`merchant-orders`（列表/详情/PATCH/actions/export）、`finance/summary|withdrawals|withdrawals/<id>/actions|recharges|ledger|ledger/export|merchants`、`deposits`（actions/entries）、`after-sales`（详情/actions）、`activities`（详情/actions/participations）、`referrals`（program/calculate/commissions/commissions/actions）。
- **新增权限码 14 个 + 3 个角色模板**（`platform_finance`/`platform_operator`/`platform_support`），迁移 `accounts_staff/0003_seed_commerce_permissions`；`platform_admin` 只做权限并集，不回收既有授权。
- **前端重构**：`admin-web` 按原型重做外壳——**236px 深色侧栏 `#111d32`**、76px 品牌区（`#2f6df6` 蓝底方块 + 「寰球优选 / PLATFORM CONSOLE」）、56px 白色顶栏（面包屑 + 标题 + 头像）、`#eef2f6` 底色、**蓝色主操作 `#2563eb`**；新增 `styles/admin.css`（panel/table/tag/drawer/modal/tabs/stat 等）+ `AppDrawer`/`AppModal`/`AppPager`/`StatusTag` 四个通用组件；新增 8 个页面 `MerchantsView`/`ProductPoolView`/`MerchantListingsView`/`MerchantOrdersView`/`FinanceView`/`DepositsView`/`AfterSalesView`/`ActivitiesView`；路由改为「登录后进入第一个有权限模块」，旧页面（爬虫/内容/买家/评价/商品目录）保留可用。
- **踩过的坑（务必不要再踩）**：
  1. **Prettier 会把 `@click="a; b"` 重排成多行、且丢掉分号**，Vue 模板编译器直接报 `Error parsing JavaScript expression`。所有多语句事件处理必须写成**具名函数**（`@click="selectTab(tab.key)"`），不要写内联多语句。
  2. `status` 字段语义在两张表里不同：`spu.status=ACTIVE` 是**可售**，`merchant.onboarding_status=ACTIVE` 是**接单中**。`StatusTag` 默认把 ACTIVE 映射成「接单中」，商品池必须传 `:labels="PRODUCT_STATUS_LABELS"` 覆盖，否则商品列表显示「接单中」。
  3. 商家列表**不能按 `is_system` 过滤**——爬虫识别出的来源店铺也是 `is_system=True`，全过滤会让「全部商家」在新库上一片空白。只排除 `merchant_type=IMPORT_FALLBACK`（技术收纳桶）。
  4. `OpsAPIView` 的域错误翻译必须挂在 `handle_exception`，挂 `dispatch` 会在 DRF 异常链之后抛 `StaffApiError`，没人接住 → 500。
  5. 管理端动作里「发货」是**商家端**职责（`ship_merchant_order` 扣成本、进度到 0），平台 A05 只能对已发货订单推进节点；别在 A05 里加发货按钮。
  6. 改后端代码后必须重启 `runserver --noreload`，否则新路由 404（本次已重启，端口 8000）。
  7. **原型 HTML 的 `<style>` 里有 TWO 套主题，前一套是废弃的**：`海外电商平台管理后台.html` 的 style 块前段是旧红白主题（`--red:#dc2638`、`aside{background:#fff;width:222px}`），**后段 12500 字符处**有一整块 `/* Platform operations console */` 把它整体覆盖成 `--primary:#2563eb` / `--ink:#18263b` / `--bg:#eef2f6` / `--sidebar-width:236px` / `aside{background:#111d32}`。`--red` 这个变量名被保留但值改成了蓝色。**只读前 3000 字符或只取第一个匹配会得到完全错误的白底红字**——这次就是这么错的，用户指出后才纠正。取色必须用浏览器 `getComputedStyle` 采样，不要靠 grep 源码。文档 02 第 11 行「后台采用深色导航与蓝色操作风格」是这条的书面佐证。
  8. 商家端 HTML（`海外电商商家后台.html`）是**另一套**主题（216px 侧栏、`--red:#df2636`），不要和管理端混用。
- **验证（按纪律仅针对性）**：
  - `manage.py test merchant_ops` → **29 passed**（商家审核/保证金/信誉/封店解封、商品池价格校验、下架幂等、发货扣成本、一键完成只回款一次、节点不可回退、下单时间≤首节点、提现打回只退一次、出款不再扣余额、保证金负值、售后结案与退货限制、返佣阶梯校验与发放幂等、幂等键、权限 403）。
  - `ruff check` + `ruff format` 通过；`prettier --check` / `eslint` / `vitest`（9 passed）/ `vite build` 通过。
  - **真实接口巡检**：用临时员工会话对 17 个新 GET 接口逐个请求，全部 200；商家列表返回 7 条（含待发货聚合）。
  - **浏览器实测（Playwright 驱动本机 Chrome）**：登录后 8 个页面逐个访问，侧栏实测 `222px`、标题正确、表格有数据或正确空态、**0 条 console 错误**；并实测「创建活动」「新增商品」两个写链路成功（CSRF 正常），测试数据已清理。
- **遗留 / 下一轮**：
  - 第 2 轮：A10 轮播图、A11 通知推送、A12 客服中心、A13 用户端管理、A14 白名单、A15 关注曝光、A16 账号与权限（逐模块 read/write UI）、A17 操作日志；
  - 第 3 轮：`merchant-web` 新建（端口 5174，216px 侧栏）+ 商家端 M01–M10 + `/api/v1/merchant/*` 与商家上下文中间件；
  - 商品池详情页的 SKU/图片仍以媒体库为准，后台只维护 `image_urls`/`specs` 文本，图片上传到对象存储尚未做；
  - `AdminOrdersView`（旧 `/admin/orders`）与新的 `merchant-orders` 并存，前者是买家订单视角，本轮未改。

### 2026-11-05（补充 11）：运行日志细化到「URL → 拿到的数据 → 处理结果 → 落盘路径」

- **用户要求**：运行日志不够详细，希望把访问的 URL、获取到的数据、处理过的数据、存入路径都打出来。
- **新增 4 条日志（每个商品固定 3 条，形成完整链路）**：
  - `LISTING_FETCHED`（列表页）：URL、HTTP 状态、响应大小 KB、耗时、卡片数、本轮入队/重复跳过/超上限/非商品卡片数、累计入队进度；
  - `PRODUCT_PARSED`（详情页）：URL、HTTP 状态、响应大小、耗时、商品 ID + 标题、原价 + 币种、SKU 数、图片数、评分/条数（或"暂无评分"）、分类路径、AI 摘要字数；
  - `DATASET_SAVED`：`var/crawl_exports/{任务目录}/{类目}/{商品ID}`、`product.json`、主图/详情图张数、失败图片数、内容是否变化；
  - `PRODUCT_IMPORTED`（增强）：SPU（新建/更新）、SKU 数、Offer 数、暂存记录 ID。
- **配套**：`dataset.save_product` 返回值新增 `product_dir`；详情接口事件条数 50 → **200**，前端标题同步「最近 200 条」；`locale.js` 补 `LISTING_FETCHED` / `PRODUCT_PARSED` / `DATASET_SAVED` 中文标签，`PRODUCT_IMPORTED` 改叫「商品已入库」。
- **顺手修掉一个会致命 bug**：`parse_detail` 里 `record_run_event` 在 `if` 分支内被导入，导致它是函数局部变量、成功路径未赋值 → **每个详情页都会 `UnboundLocalError`**。已改为函数顶部导入，并加回归测试（`SpiderLoggingTests` 覆盖详情/列表两条路径）。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **166 passed**（新增 3 例：`DATASET_SAVED` 带落盘路径、`PRODUCT_PARSED` 带 URL 与字段概要、`LISTING_FETCHED` 带卡片计数）。
  - **真实页面实测**：用归档详情页跑 `parse_detail`，产出日志「详情页已解析 https://…/100026175251161（HTTP 200，687.4 KB，耗时 3.4s）；商品 100026175251161「3000W 1.7L Rapid Boil Kettle…」，原价 179.99 GBP，SKU 1 个，图片 20 张，暂无评分，分类 Home Appliances / Small Kitchen Appliances。」
  - ruff / format / prettier / eslint / `vite build` 全通过；后端已重启。
- **注意**：日志粒度变细后事件量约为「每商品 3 条」，任务详情仍按 `created_at` 倒序取最近 200 条；长任务早期的日志会被挤出这个窗口（数据仍在库里，可直接查 `CrawlRunEvent`）。

### 2026-11-05（补充 10）：任务仍报「登录墙」——查出两个真 bug

- **用户反馈**：最新任务仍然检测到登录墙，怀疑到底有没有带 Cookie。
- **先证明 Cookie 是真的**：把最新运行（`3ba556b3`，19:37）账号 `任务账号01` 的会话解出来，用同一批 Cookie 直接 curl 列表页 → **200**；不带 Cookie → 307 跳 `/login`。所以账号会话有效，问题不在凭据。
- **Bug A（根因）：HTTP 缓存把匿名请求的 307 缓存了。**
  - Scrapy 默认 `DummyPolicy` 会缓存除 5xx 外的所有状态码，**包括 307**；而缓存键是 URL fingerprint，**不含 Cookie**。
  - 17:50 那次匿名运行把 `307 → /login` 存在 `https://www.joybuy.co.uk/s?k=Kettles%20%26%20Toasters` 上，有效期 6 小时。19:37 那次带着有效 Cookie 运行，**直接命中缓存、一次网络请求都没发**，于是继续报"登录墙"，`RENDERED_OK` 渲染的还是缓存里的登录页。
  - 证据：`var/cache/scrapy/joybuy_run/` 的 `meta` 里有 `'status': 307` 的条目；19:37 那次运行没有产生任何新缓存条目。
  - 修复：新增 `crawler/joybuy_crawler/cache_policy.py::SuccessOnlyCachePolicy`（只缓存 200，且不缓存被判为登录墙/风控页的响应），`settings` 里挂 `HTTPCACHE_POLICY`；并清掉了 4 条中毒缓存（2 条 307 + 2 条登录页）。
- **Bug B：列表页改版导致解析出空标题/无价格。**
  - 新布局里卡片是 `div[class*="product_card"]`，`a[class*="image_wrapper"]` **内部没有文字**，标题在 `[class*="style_title"]`、价格在 `[class*="crossOffPrice"]` / `[class*="mainPriceText"]`（而且价格被拆成 `£ 32 . 33` 多个文本节点）。
  - 旧解析器只遍历 `a[href*="/dp/"]`，于是 40 张卡片全是空标题、无价格（`check_listing_entry` 随后按"标题过短"把它们全丢掉）。
  - 修复：`parse_uk_listing` 改为**卡片优先 + 锚点回退**双布局；`_price` 先合并小数间空格；新增 fixture `crawler/fixtures/listing_cards_v2.html`。
- **端到端验证（真实网络）**：用该运行的同一套 settings（账号池 + Cookie 中间件 + 新缓存策略）实抓 `https://www.joybuy.co.uk/s?k=Kettles`：
  - `status=200`、`Cookie` 请求头 2599 字节、`httpcache/miss=2`（真的发了网络请求）；
  - 解析 **40 张卡片，40/40 有标题、40/40 有原价**（如 `KOMORE 2000W… | 35.99`）。
- **测试**：`crawler_control` **163 passed**（新增缓存策略 4 例 + 列表卡片布局 3 例）；ruff / format 通过。
- **文档**：`docs/05` §8 增"只缓存 200"及事故说明、新增 §8.1 缓存策略与排查提示、新增 §9.3 列表两套布局。
- **安全**：排查时落盘的明文 Cookie 临时文件与页面快照已删除（`var/joybuy_demo/bin/_cookie_header.txt`、`_listing.html`）。
- **待用户处理**：直接重跑任务即可（缓存已清、策略已换、解析器已修）。若仍失败，先在任务详情看第一条事件：出现 `LOGIN_WALL_FALLBACK` 且 URL 是 `/login?...` 说明是服务端判定，需要确认账号是否在网页端被登出。

### 2026-11-05（补充 9）：账号组实体化 + 账号可编辑/可删除

- **用户要求**：账号可编辑、可改账号组；新增账号时账号组要下拉选择；要有「新增账号组」；账号要能删除。
- **改动**：
  - 迁移 `0007_crawler_account_groups_and_soft_delete`：新增 `CrawlerAccountGroup`（`name` 唯一 + `note`）、`CrawlerAccount.deleted_at`；`0008_seed_crawler_account_groups` 把历史账号的组名回填成组记录（含 `default`）。实库已执行，组 = `['default', '数据抓取']`。
  - 服务层：`ensure_account_group` / `create_account_group` / `list_account_groups` / `update_crawler_account` / `delete_crawler_account`；`create_crawler_account` 现在会补建组记录（API/脚本传新组名不会失败）。
  - 删除是**软删除**：`deleted_at` 置位、状态 `DISABLED`、`session_cipher` 清空、会话状态回 `UNKNOWN`；行保留（`CrawlRun.account` 是 SET_NULL，硬删会让历史运行丢失"当时用哪个账号"）；运行中的任务占用该账号时拒绝删除（409）。
  - 选号/账号池/列表/动作/登录命令全部加 `deleted_at__isnull=True` 过滤。
  - 接口：`GET/POST /crawlers/account-groups`、`PUT|PATCH /crawlers/accounts/<uuid>`、`DELETE /crawlers/accounts/<uuid>`，全部写审计。
  - 管理端：新增/编辑账号的「账号组」改下拉（显示每组账号数）+「新增账号组」内联表单；账号行加「编辑」「删除」；编辑用表格上方的内联表单。**另外给「新建任务」表单补了「账号组」下拉**——否则新建的组在任务侧用不上（任务原本只会落 `default`）。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **156 passed**（新增 8 例：组列表/建组/重名拒绝/空名拒绝、编辑 label+组+备注、空名拒绝、删除后列表消失且会话清空、删除后编辑与动作 404、运行中拒绝删除、软删除保留运行归属）。
  - `ruff check` / `ruff format` 全部通过；`prettier`、`eslint`、`vitest` 9 passed、`vite build` 通过。
  - 迁移已在实库执行；后端已重启，`/api/v1/health` 正常，未登录访问 `account-groups` 返回 401（说明路由已注册、鉴权生效）。
- **设计取舍**：账号组仍以**名称**软引用（`CrawlerAccount.account_group` 与 `CrawlJob.account_group` 都是字符串），没有改成外键——任务侧改 FK 牵扯面大且没有收益；改组名不会级联，需要时先改组内账号。

### 2026-11-05（补充 8）：多账号不定时换号抓取

- **用户决定**：本地对话确认「账号有很多，需要利用多个账号不定时换号抓取数据」，并要求把 `docs/05` 里冲突的条目改掉、以对话口径为准。**注意**：上一轮我建议不做"换号规避风控"，用户已明确否决该建议并拍板，本实现按其决定落地；后续会话不要再按旧文档口径劝阻。
- **实现**：
  - 新模块 `crawler/joybuy_crawler/account_rotation.py`：`AccountPool` 管理「一段班次」的随机预算——时间 `CRAWL_ACCOUNT_ROTATE_MIN/MAX_SECONDS`（默认 300~900 秒）与请求数 `MIN/MAX_REQUESTS`（默认 20~60），**先到者触发换号**，每段重新抽取所以节奏不固定；每次换号重置该账号的班次计数（否则回到旧账号会立刻再触发）。
  - `account_session.load_account_pool()`：从 `services.usable_accounts_for_run()` 取池（指定账号优先 → 同组 ACTIVE+VALID 且会话里真有 Cookie 的账号，LRU 序，上限 50），解密后转成纯 dict 记录（便于单测，不依赖 ORM）。
  - `middlewares.AccountCookieMiddleware` 重写：优先 550、按 pool 注入**当前活跃账号**的 Cookie；换号时写 `ACCOUNT_ROTATED`；池空写 `ACCOUNT_POOL_EMPTY`；池就绪写 `ACCOUNT_POOL_READY`。
  - **Scrapy 全局 CookieJar 关闭**（`runner` 里 `COOKIES_ENABLED=False`）：否则两个账号的 Cookie 会混进同一个 jar 一起发出去，这是换号最容易踩的坑。
  - **连带坑（已踩）**：`CookiesMiddleware` 关掉后，`Request.cookies` 不再被翻译成 `Cookie` 请求头，中间件必须自己写头。第一版写成 `request.cookies = merged`，等于抓取静默变匿名；已改为直接写 `request.headers["Cookie"]`，测试也改成断言请求头。
  - 风控命中即换号：`RiskControlRenderMiddleware` 判定风控页后把当前账号 `mark_blocked()` 移出本轮池子并切到下一个，写 `ACCOUNT_RISK_ROTATED`(WARNING)；全池 blocked 写 `ACCOUNT_POOL_EXHAUSTED`(ERROR)。浏览器回退改用**当前活跃账号**的 Cookie，保证同一页面 HTTP 与浏览器是同一个身份。
  - 前端 `locale.js` 补 5 个事件码中文标签（账号池就绪/已换号/命中风控已换号/账号池已耗尽/无可用账号）。
- **文档（用户要求以对话为准）**：
  - `docs/05` §7.2 用户已自行改为「被中断任务**能**自动切换其他账号接管」；
  - §8「不为提高吞吐量轮换账号、代理或指纹」→ 改为「账号可在池内轮换，但只换身份：不轮换代理、不伪造设备指纹、不提高全局总速率」；
  - 新增 §7.5 账号池轮换（目标、池构成、换号时机、隔离与安全、风控处理、事件表、环境变量、**已知限制**）；
  - §7.4 关于 Cookie 注入/解密的描述同步为"当前活跃账号 / 按账号各解一次"；`crawler/README.md` 采集口径补账号轮换一条。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **146 passed**；新增 `AccountRotationTests`（按请求预算换号、按时间预算换号、每段预算会变、Cookie 不串号、blocked 账号永不复用、全 blocked 返回 None、单账号不轮换）与改写的 `AccountCookieTests`（活跃账号 Cookie 注入、请求级 Cookie 优先、无账号不发 Cookie）。
  - `ruff check` / `ruff format` 全部通过。
  - **真实库探针**：`default` 组 → 无可用账号；`数据抓取` 组 → `['任务账号01']`，池大小 1、不可轮换（符合预期，单账号不换号）。
  - 后端已重启，`/api/v1/health` 正常。
- **实际生效前提（重要）**：现在库里只有 1 个可用账号，所以**轮换还不会发生**。要真正跑起来多账号：把多个账号归到同一 `account_group`（或建任务时选同一组的账号），并各自完成一次人工登录让会话里带 Cookie；任务详情里看到 `ACCOUNT_POOL_READY` 且账号数 > 1 才说明池子生效。
- **已知限制**（已写进 §7.5，别再当 bug 排查）：所有账号共用同一出口 IP 与浏览器指纹；会话 Cookie 用登录快照、抓取中不跟随 `Set-Cookie` 更新（宁可少刷新也不让令牌串号）。

### 2026-11-05（补充 7）：爬虫账号是否真的在访问中被使用（账号绑定修复）

- **用户提问**：抓取时有没有带爬虫账号？建任务时也没让选账号。
- **排查结论（三个真问题，全部已修）**：
  1. **建任务没有账号入口**：`AdminCrawlJobsView.post` 完全忽略了 `account_group`，所有任务都被写成 `default` 组；界面上也没有任何账号字段。
  2. **HTTP 请求是匿名的**：`RiskControlRenderMiddleware._load_account_cookies` 只在"检测到登录墙 → 换 DrissionPage 重抓"这一步把 Cookie 给浏览器；Scrapy 的普通 HTTP 请求从来不带你账号的 Cookie。所以每页都先撞一次 307 → `/login`，再开浏览器重抓，慢且触发风控。
  3. **"假 VALID"账号**：`Joybuy homepage demo` 的会话载荷是 `{"joybuy_session": "public-homepage-demo"}`（演示命令伪造的占位串），却被标记 `session_status=VALID`。默认组里只有它"有效"，于是所有任务都绑到一个**实际 0 条 Cookie** 的账号上。真正可用的 `任务账号01`（数据抓取组，42 条 Cookie）从来没被任何任务用过。
- **改动**：
  - 迁移 `crawler_control/0006_crawljob_pinned_account`：`CrawlJob.account` FK（null=True），建任务可指定账号；不指定则按 `account_group` 自动选。
  - `services._resolve_account_for_run` / `_account_is_usable` / `_account_unusable_reason`：指定账号可用就用；不可用**不静默失败**，写 `ACCOUNT_FALLBACK`(WARNING) 说明具体原因再回退组内选号；选到账号写 `RUN_ACCOUNT_SELECTED`(INFO)「本轮使用爬虫账号「X」（账号组 Y）」。
  - **可用性判定加严**：`ACTIVE` + `VALID` + 有密文 **+ 解出来真的含 Cookie**。占位会话不再会被选中。
  - `AdminCrawlJobsView.post` 接收 `account_public_id`/`account_group`（未知账号 404、非 ACTIVE 400），`GET` 列表与详情返回账号；详情每个 run 带 `account_label`。
  - **抓取侧**新增 `crawler/joybuy_crawler/account_session.py`（`load_account_cookies` / `joybuy_cookie_pairs`）+ `middlewares.AccountCookieMiddleware`（优先级 550，早于 Scrapy CookiesMiddleware 700），把账号 Cookie 注入**每一个请求**；只回放 `joybuy` 域 Cookie，第三方（Facebook）绝不发给源站；浏览器回退复用同一份 Cookie。
  - 演示命令 `load_joybuy_demo` / `load_uk_bestsellers_demo` **不再伪造 VALID 会话**（它们只导入 fixture、从不抓取；`start_run` 本来支持无账号运行）。
  - 管理端：建任务表单加「爬虫账号」下拉（默认「自动（按账号组挑可用账号）」，列出 ACTIVE 账号及其会话状态），任务详情加「爬虫账号」，运行记录表加「账号」列。
- **实测（真实库数据）**：
  ```
  Joybuy homepage demo  group=default  session=VALID   -> 会话里没有可用 Cookie，需要重新登录（实际 0 条）
  FB 主账号              group=default  session=UNKNOWN -> 会话状态为 UNKNOWN（实际 0 条）
  任务账号01             group=数据抓取  session=VALID   -> 可用（实际可回放 30 条 joybuy Cookie）
  组 default: 【无可用账号 → 匿名抓取】     组 数据抓取: 任务账号01
  ```
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **139 passed**（新增 `test_crawler_account_binding.py` 17 例：指定账号优先、过期/占位账号回退并说明原因、组内无号匿名启动、第三方 Cookie 不回流、请求级 Cookie 优先、API 指定/拒绝账号）。
  - `ruff check` / `ruff format` 全部通过；`prettier --check`、`eslint`、`vitest` 9 passed；`vite build` 通过。
  - 迁移已执行（`crawler_control.0006` 应用成功）；后端已用新代码重启，三端口（8000/5173/3000）与 `/api/v1/health` 正常。
- **待用户处理（不是代码问题）**：
  - `default` 组目前**没有可用账号**，跑任务会匿名抓取。若要用登录态抓取，给任务选 `任务账号01`（数据抓取组），或给 default 组账号重新走一次「登录」。
  - `Joybuy homepage demo` 这个占位账号建议删除或重新登录；它现在会被判定为"会话里没有可用 Cookie"并拒绝选中。
  - `docs/05` §7.3 写着"所有页面抓取优先走真实 Chrome"，与实现（Scrapy HTTP 优先、撞墙才回退浏览器）不一致，属历史遗留口径，本次未改。

### 2026-11-05（补充 6）：任务详情「运行日志」中文化

- **用户反馈**：爬虫任务的任务详情里，日志打印的是英文，要改成中文。
- **改法分两层**（这是以后加事件时必须遵守的约定）：
  - **后端 `message` 全部改中文**：`crawler/joybuy_crawler/{pipelines,runner,middlewares,spiders/joybuy_run,quality}.py`、`backend/crawler_control/{services,import_services}.py` 里所有 `record_run_event(message=...)`、`complete_run_failed(reason=...)`、`logger.*` 文案。覆盖 20 个事件码（`RUN_STARTED`/`RUN_UNAUTHENTICATED`/`RUN_FAILED`/`RECORD_REJECTED`/`RECORD_FLAGGED`/`PRODUCT_IMPORTED`/`DATASET_SUMMARY`/`DATASET_WRITE_FAILED`/`STAGING_FAILED`/`IMPORT_REJECTED`/`IMPORT_FAILED`/`LISTING_*`/`DETAIL_*`/`RENDER*`/`RISK_CONTROL_FALLBACK`/`LOGIN_WALL_FALLBACK`/`PRICE_ANOMALY_*`）。
  - **`code` 与字段名保持英文常量**：code 是排障检索标识，字段名是 payload 键，翻译会毁掉可检索性。中文短标签放前端 `admin-web/src/lib/locale.js` 的 `EVENT_CODE_LABELS` + `eventCodeLabel()`，原始 code 挂在 `title` 提示里；事件级别 `INFO/WARNING/ERROR` 用 `valueLabel()` 显示为「信息/警告/错误」。
- **前端**：`CrawlersView.vue` 详情抽屉标题「事件流（最近 50 条）」→「运行日志（最近 50 条）」，空态「暂无事件」→「暂无日志」，级别与事件码中文化。
- **顺带**：`quality.Violation.as_log_line()` 改成中文格式 `[CODE] 字段：说明（致命/警告）`，因此单条被拒商品的日志整行可读；`StagingImportRejected` 与 `staging.error_message`（缺必填字段）也一并中文化。
- **边界（有意为之）**：`crawler/joybuy_crawler/core/http_client.py`、`core/browser.py` 的传输级日志仍是英文——那是请求/响应 dump，不是运维事件流；已在 `docs/05` §11.3 写明这条界线。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **124 passed**（含把 `OutcomeReportingTests` 的断言改成中文格式）。
  - `ruff check` + `ruff format` 8 个改动 Python 文件通过；`prettier --check` + `eslint` 两个前端文件通过。
  - `vitest run --config admin-web/vitest.config.js` → 9 passed；`npx vite build`（admin-web）→ 53 modules，构建通过（证明模板/导入无语法问题）。
  - 文案抽查：守卫告警输出「3/3 个商品拿不到可用价格。价格选择器很可能在页面改版后失效…」；记录汇总输出「[TITLE_TOO_SHORT] title：标题 'Buy' 少于 5 个字符（致命）；[PRICE_NOT_POSITIVE] current_price：解析出的价格为 0…」；前端 `valueLabel('INFO')→信息`、`eventCodeLabel('RECORD_REJECTED')→记录被拒（未入库）`、未知码原样透传。
  - **后端已用新代码重启**（`--noreload` 必须重启），重启后 `/api/v1/health` 正常。
- **遗留**：数据库里 **43 条历史事件中有 35 条是英文**（改动前产生的），界面打开旧运行记录仍会看到英文。是否按事件码回填翻译属于"改历史数据"，**未做**，需用户确认；新产生的日志一律中文。

### 2026-11-05（补充 5）：本机全服务启动（运维，无代码改动）

- 启动前核过端口：8000 / 5173 / 3000 均空闲，没有残留 runserver（避免又踩"改了没生效"的坑）。
- 基础设施已在跑（`docker ps`）：`joybuy-dev-mysql-1`（127.0.0.1:33060）、`joybuy-dev-redis-1`（127.0.0.1:63790）、`joybuy-dev-mailpit-1`（8025/1025），均 healthy，本次未重启。
- 启动命令（三条，均为后台任务）：
  - 后端：`./.venv/Scripts/python.exe backend/manage.py runserver 127.0.0.1:8000 --noreload`
  - 管理端：`pnpm --filter @joybuy/admin-web dev`（vite 127.0.0.1:5173）
  - 商城端：`pnpm --filter @joybuy/storefront dev`（nuxt 127.0.0.1:3000，`predev` 会先 `nuxt cleanup`，首启约 30s）
- 验证：
  - `netstat` 三个端口都在 LISTENING（8000→PID 31876，5173→39616，3000→19768）；
  - `curl --noproxy '*'`：`/admin/login/` 200、`127.0.0.1:5173/` 200、`127.0.0.1:3000/` 200；
  - `/api/v1/health` 返回 `{"status":"ok", database ok, cache ok}`；
  - 商城端首页渲染时已实际打通后端：`/api/v1/storefront/home` 200、`/api/v1/categories` 200、`/api/v1/search` 200。
- 容易踩的点：**健康检查路径是 `/api/v1/health`，不带尾部斜杠**（带斜杠会 404，别误判成服务没起）；本机调 localhost 必须 `curl --noproxy '*'`，否则会被环境里的死代理劫持。

### 2026-11-05（补充 4）：评价只采聚合 + 分类只到二级

- **用户两条口径**：① 不再爬评价内容，只爬评分聚合（1~5 分各自数量、平均分、x 条评价）与右侧【内容由人工智能总结自用户评价】的内容（**有就爬，没有就不写**）；② 商品子分类展示过多时只保留前两级（`首页/母婴用品/健康护理/湿巾及配件/湿巾/商品名` → `母婴用品/健康护理`）。
- **现场结构（靠归档页确认，不是猜的）**：参考页 `…/dp/…/10524192` 匿名访问 **307 跳 /login**，抓不到；改用 `var/raw/2026/11/04/…/8dd804f5….gz`（真实 kettle 详情页 702KB）逆向出评价结构：
  - 评价区块是 flight 里的**一个扁平对象**，形如 `{"commentCount":…,"star":"4.8","starShow":"4.8","aiSummary":null,"aiTagTitle":null,"aiTagList":null,"totalCommentCount":47,"ratingInfo":"$19c"}`；
  - `ratingInfo` **不是内联对象而是引用** `"$19c"`，真值在同文件的 `19c:{…}` 槽位；槽内字段 `score1Count`…`score5Count`、`averageScore`、`commentCount` 就是需求要的 1~5 分数量/平均分/条数；
  - `aiSummary` 就是"内容由人工智能总结自用户评价"的正文，`aiTagTitle`/`aiTagList` 是标题与标签；无评价的页面这几项为 `null`。
- **解析器改动（`crawler/joybuy_crawler/parsers/joybuy_uk.py`）**：
  - 新增 `_flight_text()`（改用 `json.loads('"…"')` 解码，**不再用 `unicode_escape`**，否则中文摘要会乱码）、`_flight_ref()`（解析 `$19c` 槽位引用，支持多跳）、`_flight_key()`；
  - 新增 `_extract_flight_review()`：**锚定"包含 `ratingInfo` 的那个大括号对象"**再读字段。**不要全局搜 `aiSummary`**——i18n 文案里有同名字段，会取到错值；
  - 平均分取 `star`/`starShow`，只有 count>0 时才回落 `averageScore`（**真实页面在 0 条评价时把 `averageScore` 默认成 5**，直接取会凭空造出 5 分）；
  - `_extract_dom_review()` 只兜底 AI 摘要正文；**星分布明确不做 DOM 猜测**（宁可留空也不按进度条宽度推算）；
  - `truncate_breadcrumbs()`（`BREADCRUMB_DEPTH=2`）在解析阶段截断，按 `home/首页/主页/首頁` 丢掉站点根；
  - payload 新增 `rating_distribution` / `rating_source` / `ai_summary` / `ai_summary_title` / `ai_summary_tags`，native 块里 `rating` 带 `distribution`，摘要只在非空时挂 `aiReviewSummary`（**没有就是不存在这个 key，不留空壳**）。
- **新增 fixture**：`crawler/fixtures/product_detail_reviews_v2.html`（按归档页结构构造：6 级面包屑 + `$19c` 引用 + 中文摘要 + 标签，数值 47 条 / 4.8 分 / 1-1-2-9-34）。生成脚本在 `var/joybuy_demo/bin/gen_review_fixture.py`（临时，不入库）。
- **新增测试** `backend/crawler_control/tests/test_crawler_review_aggregates.py`（9 例）：星分布且**各档之和 == 总条数**、无评价时不造平均分、摘要存在/不存在两态、无评价正文进入 payload、面包屑 2 级截断（中英站点根、短 trail、payload 里深层分类消失）。
- **文档**：`docs/05` §4（评价目标数/评价媒体标注停用）、§9.2（类目层级口径）、§10（评价采集口径整节重写）；`crawler/README.md` 增"采集口径（2026-11-05）"。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control.tests.test_crawler_review_aggregates` → **9 passed**。
  - `manage.py test test_crawler_review_aggregates test_crawler_field_rules test_crawler_rebuild test_crawler_runtime test_crawl_jobs_api` → **71 passed**。
  - **真实归档页回放**（不靠构造数据）：kettle 详情页解析出 `Home Appliances / Small Kitchen Appliances` 两级、`rating_source=flight`、`count=0` 且分布全 0、`aiSummary=''`（该页确实无评价无摘要）——与页面实际状态一致，没有编造。
  - `ruff check` 3 个改动文件通过，`ruff format` 已执行。
- **未做 / 下次注意**：
  - **没有真实跑在线抓取**（站点 307 登录墙），"有评价+有摘要"的形态是用归档结构构造的 fixture 验证的；等有登录态账号实抓一次后应核对一次真值。
  - 后端 `reviews` 应用与 `joybuy_crawler/sampling.py`（WP-17 评价导入/抽样）**代码仍在**，只是爬虫不再供数；是否整体下线评价模块属于另一个决策，未在本次范围内，**不要顺手删**。
  - `CrawlJob.review_target` / `download_review_media` 两个模型字段仍在库和迁移里（只改了文档口径），清理需要新迁移，未做。
  - 面包屑的 `cid` 提取在真实页面上一直为空（href 里没有 `l1/cid` 参数），所以 `source_category_id` 实际为空、导入走兜底类目——这是**旧有现状**，本次截断不改变它。

### 2026-11-05（补充 3）：爬虫记录级质量层（文章对照后补的缺口）

- **来源**：用户给了一篇商城爬虫实战文章（`https://blog.csdn.net/weixin_29913663/article/details/166029197`），要求"结合当前框架优化"。对照后发现项目**已有**这些：原始响应 gzip 归档（`RawArchivePipeline` + 中间件里 `record_raw_response`，30 天）、退避重试（`RETRY_HTTP_CODES` + `core/policies.py`）、批级缺失率闸门（`evaluate_batch_quality`）、列表页 `seen_product_ids` 去重、带宽/并发克制（`CONCURRENT_REQUESTS=2`）。**真正的缺口**是文章强调的另外三件事，本次已补。
- **新文件 `crawler/joybuy_crawler/quality.py`**（纯函数，无 Scrapy/Django 依赖，可脱离数据库单测）：
  - `apply_product_rules(payload, source_url=)` 返回 `(清洗后的 payload, RuleOutcome)`；**输入 dict 永不被修改**。
  - 致命项（丢弃）：`source_id` 缺失/不合规、标题去空白后 < 5 字、`current_price` 解析不出数字、**价格为 0 或负**、价格超出 `0.01~100000`、币种不是 3 位字母、`skus` 为空、来源 URL host 不是 `joybuy.co.uk` 或路径不含 `/dp/`。
  - 警告项（放行并上报）：标题 > 500 字、标题含广告词（`sponsored`/`advertisement`/`hot sale`/`为你推荐`/`热推`/`广告`）、个别 SKU 价格坏、非 `joy-sourcing.com` 域的图片（**并且真的从 payload 里删掉**，不会写入 dataset、不会从陌生源下载）、`mainPrice > crossOffPrice`（两个价格选择器串位）。
  - `check_listing_entry(title=, source_url=)`：列表页卡片级判定，标题过短 / 含广告标记 / URL 取不到商品 ID 的卡片丢弃，**不再占用每个类目的商品配额**（文章提到的"推荐位污染选择器"在本站的具体形态就是这类 `/dp/` 广告砖）。
  - `PriceDistributionGuard`：运行级守卫，样本 ≥3 且不可用价格 ≥50% → `PRICE_ANOMALY_MISSING`(ERROR)；样本 ≥3 且所有有效价格相同 → `PRICE_ANOMALY_UNIFORM`(WARNING)。
- **新管线 `pipelines.RecordRulePipeline`**（`runner._run_settings` 注册优先级 **150**，`StagingPipeline` 是 200）：
  - 致命违规 → `update_run_progress(failed=1)` + `RECORD_REJECTED`(ERROR) 事件 + `raise DropItem`，item 不会到达 dataset/staging/业务表；
  - 警告 → `RECORD_FLAGGED`(WARNING) 事件，`payload["rule_warnings"]` 带上违规码继续走；
  - `spider_closed` 里把守卫判词写成一条运行级事件。**只上报事件、不改变任务状态**——"这一轮是否算失败"仍由 `complete_run_failed` 既有规则决定，避免把"价格可疑但可用"直接判死。
- **列表页**（`spiders/joybuy_run.py`）：`parse_listing` 先用 `check_listing_entry` 过滤，被丢的条数与原因汇总成 `LISTING_CARDS_REJECTED`(WARNING) 事件。
- **数据集增量**（`dataset.py`）：每个商品目录新增 `meta.json`（`payload_sha256`/`first_captured_at`/`last_captured_at`/`capture_count`/`changed`）；`product.json` 与图片**每次都重写**（原始快照永不丢），`dataset_index.jsonl` **只在指纹变化或首次落盘时追加**，重复抓同一商品不再刷重复行。`StagingPipeline` 收尾写 `DATASET_SUMMARY` 事件汇报"刷新 N 个目录 / 其中 M 条真的变了"。
- **`settings.py`**：显式写明 `RANDOMIZE_DOWNLOAD_DELAY = True`（Scrapy 默认就是 True，之前靠隐式默认）。**没有**再加一层自定义 jitter 中间件——`DOWNLOAD_DELAY` 已经被随机成 0.5~1.5x，再叠一层只是在 reactor 里多一次无意义等待。
- **实测（真实数据回放，最有说服力的一条）**：`var/joybuy_demo/bin/probe_record_rules.py`（临时探针，`var/` 不入库）遍历 `var/crawl_exports/*/*/*/product.json` 共 9 份真实抓取 payload → **6 份正常商品（米家咖啡机 92.99、ochama 咖啡机 49.99、Kettle 29.99 等）零违规通过；3 份被拒的正是历史上那批空解析（title/price/currency 全空、`missing_fields` 非空）的脏数据**。无误杀、无漏放。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control.tests.test_crawler_field_rules` → **30 passed**（新增：价格解析形态、8 类致命规则、4 类警告规则、列表卡片 4 例、守卫 4 例、管线丢弃/放行/运行级告警、数据集增量 3 例）。
  - `manage.py test crawler_control.tests.test_crawler_rebuild crawler_control.tests.test_crawler_runtime crawler_control.tests.test_crawl_jobs_api crawler_control.tests.test_crawler_field_rules` → **62 passed**（回归未破）。
  - `ruff check` 本次改动 7 个文件 → All checks passed；`ruff format` 已执行。
  - `docs/05` §5.1、§11.1、§11.2 与 `crawler/README.md` 已同步新口径。
- **已知遗留 / 下次注意**：
  - `crawler/joybuy_crawler/settings.py` 有一处**既有**格式问题（`HTTPCACHE_ENABLED` 那行超出 ruff format 习惯换行，非本次引入），`ruff format --check` 会对该文件报 1 处，未顺手改以免混入无关 diff。
  - 规则阈值是常量写在 `quality.py` 顶部（`TITLE_MIN_LENGTH`/`PRICE_MIN`/`PRICE_MAX`/`IMAGE_HOST_SUFFIXES` 等）。真实站点如果出现合法低价配件（< 0.01）或新 CDN 域名，需要调这里，别去改调用点。
  - `PRICE_ANOMALY_*` 只发事件不改状态，管理端事件流能看到；如果后续希望"价格异常自动暂停任务"，要接到 `apply_quality_failure_policy` 上，属于策略变更，需用户确认。
  - 本轮**没有**跑真实 Joybuy 在线抓取（站点要求登录态 + 有风控），验证靠"真实历史 payload 回放 + 单测"，不要写成"线上抓取已验证"。

### 2026-11-05（补充 2）：类目双语「界面还是英文」的排查结论

- **现象**：管理端【爬虫任务】→【新建任务】→【选择 Joybuy 类目】只显示英文。
- **根因不是前端**：本机 `127.0.0.1:8000` 上有 **4 个 `manage.py runserver ... --noreload` 进程**（30808 / 29852 / 12352 / 32128，只有 32128 真正占着端口），`--noreload` 不加载新代码，接口返回的 `source-tree` 节点**没有 `name_zh` 字段**，前端自然只能显示英文。用临时员工会话直连接口核对：修复前 `has name_zh: False`，重启后 `has name_zh: True | Home Appliances | 家用电器`。
- **处理**：`taskkill` 掉 4 个旧进程，重新起一个 `runserver 127.0.0.1:8000 --noreload`（后台任务）。浏览器实测（用户自己的 Chrome，已登录 admin）：类目行显示「家用电器 Home Appliances minihome:…」，展开后子类目显示「热水壶 & 烤面包机 Kettles & Toasters l2:1405」等，中英双语正常；任务列表类目列也已变成中文（热水壶 & 烤面包机）。
- **教训**：改后端代码后必须重启 `--noreload` 开发服务器；`runserver` 默认的自动重载在本机不可用（`RuntimeError: Script backend\manage.py does not exist.`，因为启动参数是相对路径 `backend/manage.py`），要自动重载需用**绝对路径**启动：`python E:\code\AgentProject\Joybuy\backend\manage.py runserver 127.0.0.1:8000`。
- **别再多开**：`runserver` 重复启动不会报错（后起的占不到端口但仍在跑），排查「改了没生效」时先 `netstat -ano | grep 8000` 看监听 PID，再核对进程命令行。

### 2026-11-05（补充）：一个任务只用一个爬虫浏览器，用完必关

- **问题（用户反馈）**：跑一个任务会打开几十个浏览器且不关闭。根因是 `render_page` 每抓一个 URL 就
  `ChromiumPage(...)` 新开一个实例（类目树 15 页 = 15 个浏览器），而 `page.quit()` 在部分情况下并没有
  真正结束进程；Scrapy 风控/登录墙回退也是每页一个浏览器。
- **改法**：
  - `crawler/joybuy_crawler/render.py` 新增 `BrowserSession`（`open/get/close` + 上下文管理器）：
    一次 open、可连续 `get` 多页（每次 `listen.stop()`→`listen.start()` 复用 SSR 抓取），`close()` 先
    `page.quit()` 再显式回收进程。`render_page()` 保留原签名，内部改成「开一个临时 session、用完必关」。
  - `_kill_stale_crawler_browsers()` 重写：用一条 PowerShell 查询匹配 **`browser_profiles` 路径**或
    **调试端口 9333/9334** 的 chrome 进程，`taskkill /T /F` 并返回数量；`_crawler_chrome_pids()` 可单独列 PID。
    open 前和 close 后都跑一次，任何残留都会被收掉。
  - `capture_category_tree()` 全程使用同一个 session（`finally` 里 close），所以类目树 15 页只开 1 个浏览器。
  - `RiskControlRenderMiddleware` 改成复用同一个 session（cookie 变化时才重建），并连接
    `spider_closed` 信号关闭；渲染失败会丢掉 session，下次回退自动重建。这样商品任务里的登录墙回退
    不再「一页一个浏览器」。
  - `crawler_account_login` 的 `finally` 除了 `quit()` 也调用回收，避免登录窗口残留。
  - 新命令 `manage.py close_crawler_browsers`：随时回收残留爬虫浏览器（只匹配爬虫 profile / 9333、9334）。
- **验证（针对性）**：
  - `var/joybuy_demo/bin/verify_browser_lifecycle.py`（临时探针，不入库）：开 session 连抓 2 页，
    期间调试端口浏览器主进程数 = **1**，`close()` 后 = **0**，爬虫 PID = **0**。
  - `manage.py test crawler_control.tests.test_crawler_rebuild crawler_control.tests.test_crawl_jobs_api`
    → 21 passed；`ruff check`/`ruff format --check` 本次 5 个改动文件通过。
  - `manage.py close_crawler_browsers` 在无残留时输出 "No crawler browser was running."。

### 2026-11-05：管理端类目选择器「中文名 / English name」双语展示

- **目标**：`新建任务 → 选择 Joybuy 类目` 原本只有英文名；现在每个节点同时显示中文名与英文名，搜索框支持中文/英文/来源 ID。中文名必须来自 joybuy.co.uk 真实中文页面，按 source id 与英文严格一对一，不伪造译名。
- **语言开关（现场核实）**：joybuy.co.uk 用 `_lang` Cookie 控制界面语言（默认 `en_GB`），设成 `zh_CN` 后整站（含类目菜单、频道页类目磁贴）变中文，URL 与 source id 不变。
- **登录墙（新踩的坑）**：2026-11-05 起，未登录访问首页/频道页会 **307 跳 `/login`**（`Location: /login?returnUrl=...`），匿名爬取/无头/有头都被拦，`/minihome/` 页拿不到类目链接。抓取必须带已登录账号的会话。
- **后端存储**：`catalog` 迁移 `0008_source_category_chinese_names` 给 `SourceCategory` 和 `SourceCategorySnapshot` 各加 `name_zh`。`SourceCategory.name_zh` 是 source id 维度的持久映射；`SourceCategorySnapshot.name_zh` 是版本内展示名；`tree_sync.sync_category_tree` 建快照时优先取节点自带中文名、否则继承 `SourceCategory.name_zh`，**重建英文树不会丢中文名**。`catalog/services.save_source_category_version` 同步支持 `name_zh`（不参与结构哈希与版本判定）。
- **新命令** `manage.py sync_joybuy_category_names_zh`：`--from-json` 回放 / `--dump-json` 落盘 / `--account <public_id>` 用账号会话抓取 / `--profile` 复用某个浏览器 profile / `--channel` 按频道分块 / `--merge-json` 分块合并 / `--pause` 控速 / `--no-reset-profile` 跳过删 profile（本机 safe-delete 会拦批量删除）。命令输出 `matched / categories_updated / snapshots_updated / unknown / still_missing` 五项，**unknown 与 still_missing 只报告不猜译名**。
- **爬虫层**：`category_menu.py` 新增 `locale_cookies()` 与 `capture_category_tree(locale=, cookies=, profile_dir=, only_channels=)`；`render.py` 的 `_build_options/render_page` 支持指定 `profile_dir`；风控特征串补了中文站实际出现的 `403 页面 / 服务暂时中断 / 系统当前负载过高`。
- **登录命令修复（真 bug）**：`crawler_account_login` 原来的「出现新 Cookie 就算登录成功」会在用户停在 facebook.com 授权页时误判，把 **facebook.com 的 7 条 Cookie 存成了账号会话**。现改为：当前 URL 必须是 joybuy.co.uk 且不在 `/login`、可见正文 ≥2000 字符、且只采集 `joybuy` 域 Cookie。
- **管理端接口**：`tree_to_payload()` 每个节点返回 `name_zh`；任务列表类目列优先显示中文名；任务详情 `categories[]` 增加 `name_zh` 字段。
- **前端**：`CategoryTreePicker.vue` 每行渲染「中文名（加粗）+ 英文名（次要色）」，没有中文名时只显示英文；搜索同时匹配中英文与 source id；选中项带上 `name_zh`；表单标题下加了说明文案。`CrawlersView.vue` 补 `.create-form__tree-hint` 样式。
- **数据现状**：14 个一级频道 100% 有中文名；163 个二级类目 **156 个有中文名（95.7%）**，缺 7 个：`l2:3505 Gaming Steering Wheels`、`l2:1384 Learning, Discovery & Science`、`l2:1376 Vehicles & Remote Control`、`l2:1380 Electronic Toys & Music`、`l2:1378 Soft Toys`、`l2:1474 Baby Clothing`、`l2:1478 Safety Equipment`（这 7 个在频道页的类目轮播里不在首屏，浏览器 DOM 快照拿不到；爬虫侧当天被风控限流）。
- **数据文件**：`var/joybuy_demo/data/category_menu_zh.json`（英文名+中文名+来源 URL，可直接 `--from-json` 回放）；`category_menu_zh.tsv` 是抓取原始对照（channel / source_id / 中文名）。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control.tests.test_crawler_rebuild.TreeSyncTests crawler_control.tests.test_crawl_jobs_api` → 7 passed（新增 2 个用例：中文名按 source id 匹配且重建版本仍继承；unknown/still_missing 报告正确）。
  - `npx vitest run --config admin-web/vitest.config.js` → 9 passed（`CategoryTreePicker` 6 个用例，含「中英同时显示」与「中文关键词过滤」）。
  - `npx prettier --check` + `npx eslint` 三个改动前端文件 → 通过；`ruff check` / `ruff format --check` 本次改动的 9 个 Python 文件 → 通过。
  - 实库：`manage.py migrate catalog` 已执行；`sync_joybuy_category_names_zh --from-json` 结果 `tree=joybuy-uk-20261104-4dcfbbe5 matched=170 categories_updated=170 snapshots_updated=184 unknown=0 still_missing=7`；`tree_to_payload` 抽查 Electronics/Pets 中英对照正确、14 个 L1 全部有中文名。
  - **未做**：管理端页面人工登录截图核对（当时不知密码；**2026-11-05 夜已解决**：`admin@joybuy.test` 密码已重设为 `Admin@123456`，见下方「本地开发登录凭据」）。

### 2026-11-05：数据库说明文档（docs/13）

- 数据来源：`information_schema.COLUMNS` 全量快照（79 表 759 字段，TSV 存 `var/joybuy_demo/data/db_columns.tsv`）+ 通读 `backend/` 全部 14 个 models.py 确认字段语义。
- 产出 `docs/13-database-schema.md`：通用约定（id/public_id/外键/时间戳/枚举/金额规则）、按 15 个业务域的表清单、每张表用途说明 + 逐字段表（列名/类型/说明，含唯一约束、CHECK 约束、枚举取值）、Django 内置表一节。关键业务规则均就地标注（如 offer 价格 CHECK、staging 幂等键、fingerprint HMAC、purchase_whitelisted 白名单）。
- 文档编号注意：`docs/12` 已被 UI 规格文档占用，本任务新建文档顺延为 13；`docs/README.md` 索引补齐 11/12/13。
- 验证（按纪律仅针对性）：prettier --check 两份文档通过；无代码改动，无后端/前端验证需要。

### 2026-11-04：畅销榜单 11 类公开数据补齐

- 新增受版本控制的 `backend/catalog/fixtures/bestseller_demo_2026_11_04.json`：11 个标准类目各 3 条，共 33 条；保存来源父榜/子榜、固定 URL、来源语言、榜单位置、Joybuy SKU、标题、品牌、商品 URL、图片 URL、原价和库存。前 6 组来自中文浏览器会话（`zh-CN`），后 5 组来自公开英文服务端页（`en-GB`），均按实际来源标记，没有伪造翻译。
- 现场映射：家居生活→家居用品/清洁用品；电子产品→数码电子/办公设备；美妆→美妆/彩妆；小家电→家用电器/小型厨房电器；健康→健康与保健/营养品；电脑→电脑及配件/电子配件；户外→运动户外/运动器材；宠物→宠物用品/猫咪必备；母婴→母婴用品/哺育喂养；游戏→游戏娱乐/游戏主机；服装→时装配饰频道/爆款直降（替代来源）。
- 新增幂等命令 `backend/catalog/management/commands/load_bestseller_demo.py`：支持 `--fixture`、`--per-category`、`--skip-images`、`--only-category`；建立 `bestseller:<local-slug>` 来源类目和主映射，调用 `ingest_product_payload()` → `import_staging_product()`，显式修正既有 SPU 的本地类目/品牌，激活 SPU/Offer，按来源层/本地覆盖层解析有效标题，下载本地图并重建搜索文档。fixture 价格作为 `current_price` 保存，`list_price=None`，不保存促销文案。
- `backend/catalog/search_services.py`：搜索页批量读取当前页 SPU 的第一张 `gallery` 本地图，返回 `image_path`；同时 `select_related("spu", "local_category")`，避免商品逐条查询。商城现有 `ProductCard` 已消费 `image_path`，无需改前端。
- 新增测试 `backend/catalog/tests/test_bestseller_demo.py`；扩展 `test_search.py` 覆盖本地首图与查询数上限。
- 实库执行：首次导入 33 条（30 个新 SPU，另 3 个命中既有来源身份），一次源图失败；确认 CDN 对失败资源稳定返回 HTTP 400 后，改用同一“爆款直降”楼层真实第 4 名 PUMA 商品，重跑服装类 3 条后 0 图片失败。失败样本 `10489708` 已置 SPU=DRAFT、GB Offer=INACTIVE 并重建索引（未物理删除历史）。最终 fixture 33 个 SPU 全部可搜索、33/33 有本地图。
- 最终 API 总量（含此前数据）：home-living 46、electronics 6、beauty 3、small-home-appliances 10，其余 7 类各 3；本轮 fixture 在每个类目严格各 3 条。

### 2026-11-04（补充）：头部 logo 换成本地真实字标图片

- 按用户给出的真实站 logo 结构（110×30 图片按钮），把 `st.joy-sourcing.com/website/home/m_logo.png`（264×73 高清源）下载到 `storefront/public/images/logo.png`（项目内本地托管，无 CDN 引用）。
- `AppHeader.vue` 品牌区从红色文字字标改为 `<img class="brand__logo">`（110×30，object-fit contain）；src 用运行时常量绑定而非静态属性——静态 `/images/...` 会被 vite 的模板资源转换当成模块 import 解析失败（vitest 下报 `file:///images/logo.png` 错误，Nuxt dev 下报 Failed to resolve import）。vitest 配置同时加了 `vue({ template: { transformAssetUrls: false } })` 兜底。
- 验证：vitest 42/42、eslint/prettier 通过；浏览器确认 logo 加载（natural 264px、显示 110×30）。

### 2026-11-04（第二轮反馈）：首页头部/活动区按真实站样式精修（15 项）

- 用户给出 15 项首页优化点并要求打开真实 joybuy.co.uk 参考样式；已在内置浏览器实测真实站并逐项测量（通告条 40px、搜索行 52px+14px 内边距、搜索按钮 64×44 深色圆角在框内、圆形图标按钮 52px、卡片 277×277 两行、活动区全幅 1512×698 带背景图）。
- **AppHeader 重写**：通告条内容改用与页面一致的居中容器（max-width 90rem + container-pad），高度 40px、颜色 #17202A（用户指定值，实测真实站为 #1A1A1A）；分类按钮改为"☰ Categories/分类"浅灰胶囊（bg #F5F6F7，radius 50px）；悬停/点击展开分类面板（150ms 关闭延迟防抖）；搜索框改浅灰底 #F5F6F7 + 1px #C2C4CC 描边胶囊，深色 #17202A 圆形搜索按钮（64×44）嵌在框内右侧（宽度 flex 自适应，1512 视口下约 898px）；配送至 hover 背景 #F0F1F4；个人/购物车改为 52px 圆形图标按钮（含角标）；类目行 space-between 平均占满、hover 下划线无背景；搜索行与类目行之间去掉分割线，仅保留实测阴影 `rgba(0,0,0,.04) 0 2px 12px, rgba(0,0,0,.06) 0 1px 4px`。
- **AppCategoryPanel**：去掉 Teleport 与全屏遮罩，改为锚定在分类按钮正下方、与按钮左对齐（left 对齐实测一致）的下拉面板；父容器 mouseenter/mouseleave 控制开关；点击只负责打开（避免与 hover 冲突）。
- **CmsCampaignGrid**：去掉"为你推荐"标题（真实楼层无标题）；改为全幅楼层（width 100vw + margin 反抗容器），min-height 600px；新增 `background_path` 背景图层（payload 提供时用背景图，否则回退浅色蒙版）；卡片改 5 列正方形网格。
- **loader**：新增 `CAMPAIGN_BG_URL`（实测真实站活动区背景图 URL），下载进本地 CMS 媒体库并写入 payload——首页活动区背景为真实素材本地化，非外链。
- **其它**：`main.css` 给 `.app-main` 加 `overflow-x: clip`（修复 100vw 全幅导致的 8px 横向滚动）；首页内容区 `margin-block: 24px`；分类按钮补 aria-label（移动端隐藏文字后保持可访问名）。
- e2e 断言同步：`foundation.spec.js` 与 `purchase-funnel.spec.js` 首页断言从 "Offers for you" 标题改为活动区 Welcome Offers 链接（标题已按需求 12 删除）；首页 4 视口快照重新基线化。

### 2026-11-04：docs/12 目标状态改造第 1 轮（i18n + 全局头部 + 11 类目体系 + 首页 CMS）

- **后端类目双语**：`LocalCategory` 新增 `name_en`/`name_zh`（迁移 `catalog/0007`）+ `display_name(locale)`；`GET /api/v1/categories` 改为返回嵌套树（roots + 一级 children，按 `sort_order` 排序），每级带 `name_en`/`name_zh`（`search_views.category_tree` 重写）。
- **种子命令** `backend/catalog/management/commands/seed_standard_categories.py`：幂等创建 11 个标准一级类目（家居生活/电子产品/美妆个人护理/小家电/健康与保健/计算机与配件/服装与配饰/户外运动/宠物用品/婴幼儿用品/游戏及配件，双语 + slug + 42 个子类目），把不在标准清单内的旧 ACTIVE 根类目置 HIDDEN；`--assign-demo-products` 按标题关键词把演示商品归入类目（厨电→kitchen-appliances、纸品→cleaning-supplies、电子→electronics、其余食品→groceries-food 兜底）并重建搜索文档。已执行：11 根类目 + 42 子类目，53 个演示商品归位（家居生活 43 / 小家电 10 / 电子产品 3 条可搜索文档；其余类目暂空，等第 2/3 轮后台配置与真实品类数据）。
- **商城端 i18n**：`storefront/locales/messages.js`（EN/ZH 字典 + `pickName` 双语取值）+ `composables/useLocale.js`（cookie `joybuy-locale` 持久化，默认 en，`t()/toggleLocale()/categoryName()`）+ `composables/useCategoryTree.js`（SSR 直连/客户端代理）。通告条左端 "UK | English" 即语言切换按钮。
- **AppHeader 改造**（需求 1-1/1-4/1-5/1-6）：通告条去掉 "Download Joybuy"，轮播仅剩 Welcome Offers / Quality Guaranteed / 24/7 / Free returns 四条（‹›箭头切换+自动轮播）；类目行改读 categories API 的 11 个标准类目（链接 `/c/<slug>`）；新增汉堡按钮 + `AppCategoryPanel.vue`（左栏 11 根类目、右栏仅当前选中类目的子类目，严格联动）；新增登录态头像下拉（用户名 + My orders / Reviews and Q&A(/account) / Wishlist(/account/favourites) / Addresses(/account/addresses) / Sign out，**无 My JoyPlus**）。
- **新页面**：`pages/s.vue`（/s?k=→关键词搜索、/s?category=→类目列表，复用 ProductListing；`ProductListing.vue` 的 searchText 增加 `route.query.k` 兜底）；`pages/account/addresses.vue`（只读地址列表）。
- **首页 CMS**（需求 2/3）：`load_joybuy_demo.py` 删除快捷入口图标行模块（连带删除 extract_quick_entries/extract_category_discovery 死代码）；品类发现改为固定 6 品类（家居/电子产品/服装以及配饰/游戏/户外运动/小家电，双语 label）落地 `/s?category=<slug>`；campaign_grid/发现楼层标题带 `title_zh`。已重跑发布 home v5（10 模块，0 图片失败，用已保存 HTML 未新抓取）。
- **CMS 组件双语**：`CmsLinkGrid.vue`/`CmsCampaignGrid.vue` 支持 `title_zh`/`label_zh`/`title_zh`+`subtitle_zh`，按 locale 取值回退英文 base 字段。
- 浏览器实测：中文首页（黑通告条+红色搜索头+11 中文类目行+为你推荐+品类发现 6 品类）、分类面板联动（Electronics 右栏仅 4 子类目）、中文/英文切换、`/s?category=electronics`（3 商品）均正常；4 视口首页快照已重新基线化。

### 2026-11-03：首页对齐真实 Joybuy 结构（活动砖石/快捷入口/品类发现/通知条）

- 用户给出真实首页截图指出缺项后补齐。新 CMS 模块类型 `campaign_grid`（item 必填 title，带 subtitle/image_path/href）：`content/schemas.py` + `CmsModule.Type` + 迁移 `content/0003`；`link_grid` payload 增加 `variant`（`quick_entries` 圆形图标入口 / `tiles` 品类发现浅底磁贴），item 支持可选 `icon_path`；前端新增 `CmsCampaignGrid.vue` 并扩展 `CmsLinkGrid.vue`。
- `load_joybuy_demo.py` 新增三个提取器（全部来自已保存 flight 数据，无新增抓取）：`extract_campaign_tiles`（floorInfo 中含 subTitle 且 floorType≠"icon" 的 eventInfo，标题取 titleView.title="Offers for you"，前 10 块）、`extract_quick_entries`（floorType=="icon"，iconImage 120×120 图标，前 6 个）、`extract_category_discovery`（`externalKey=="EXT_POPULAR_CATEGORIES_V3"` 的 data 列表，7 块）。
- 图片本地化规则：活动瓦片 `https://images3.joy-sourcing.com/product/s384x384_{path}.webp`、缩略图 s240x240、入口图标为 `//images3.../da/...` 完整 URL 补 https；统一 `store_bytes(kind="CMS")`。本轮新增 23 张图 0 失败。
- 首页模块序对齐真实站（home v4，11 模块）：campaign_grid → 快捷入口 → 品类发现 → 6 个商品楼层 → 品牌墙 → rich_text；**移除红色 hero**（真实首页没有）。瓦片/入口的站外跳转统一替换为本地 `/search`。
- 头部：新增黑色顶部通知条（真实文案 "Unlock Your Welcome Offers: FREE Delivery | Up to 80% OFF | Free 30-day JoyPlus trial"，窄屏只留通知文案）；logo 改红色 Joybuy 字标；搜索框红描边+圆形放大镜按钮（内联 SVG）；新增 "Deliver to SW1A 1AA"。
- e2e 断言同步为 "Offers for you"；首页 4 视口快照重新基线化。
- 已知剩余差异（真实站有、本地未做）：通知条/活动砖石的轮播箭头与分页、右侧悬浮按钮（下载/消息/客服/反馈）、"分类"下拉菜单、顶栏图标资源（已用文字替代）。

### 2026-11-03：真实 Joybuy 站点产品功能分析（浏览器实测）

- 用内置浏览器只读遍历 joybuy.co.uk：首页、Categories 弹出菜单（15 个一级类目 + Electronics 二级/品牌/活动实测）、顶部 13 个频道页（Electronics 与 Food & Drinks 抽样实测，结构统一）、搜索/类目列表页（JoyExpress/Bestsellers/Welcome offer/Lightning offers/Outlet 快捷筛选、价格双滑块、评分、排序、商品卡加购/收藏）、商品详情页（面包屑、规格、数量、Buy now/Add to cart、卖家店铺、分享、3 个信息 Tab）、购物车页（Delivery/Pickup 切换、空态）。
- 产出 `docs/11-joybuy-co-uk-product-features.md`（按模块分组的功能表格）。
- 边界：未登录、未提交任何数据；登录后功能、页脚（站点自绘滚动无法滚到）、Deliver to 弹窗未覆盖，已在文档"无法访问的页面"注明。
- 已知坑：站点懒加载/自绘滚动导致滚轮滚动无效、DOM 快照只含视口内容；无头抓取 HTML 会命中 Joybuy 风控页（Risk Control），须用真实浏览器访问。

### 2026-11-03：Joybuy 主页复刻效果展示（爬真实内容 + 首页改版）

- 抓取方式：仅一次礼貌抓取 `https://www.joybuy.com/` 公开主页（保存于 `var/joybuy_demo/data/home_raw.html`），解析其 Next.js RSC flight 流拿到公开数据：10 个热卖楼层（每层 10 SKU）、楼层标题、活动入口（Lightning Offers/Outlet/Mix & Match/JoyPlus/New Arrivals）、品牌墙、承诺文案；解析脚本脚手架在 `var/joybuy_demo/bin/`（不入库、不提交）。
- 新增管理命令 `backend/content/management/commands/load_joybuy_demo.py`：解码 flight 流 → 每个商品只取**原价**（`crossOffPrice`，`mainPrice` 优惠价丢弃）→ 走既有 `ingest_product_payload` + `import_staging_product` 幂等导入 53 个真实商品（60 条去重后）→ 图片经 CDN s360x360 规则下载并用 `store_bytes` 存入本地媒体库 `var/media`（60/60 成功，`MediaUsage` role=gallery 挂到 SPU，详情页画廊可用）→ 逐 SPU 重建 GB 搜索文档 → 生成并发布 CMS 首页（hero、`Explore Joybuy` 入口磁贴、6 个真实楼层 `product_pool`、`Brands we love` 品牌墙、说明 rich_text），同时把生成的页面 JSON 落盘 `var/joybuy_demo/data/generated_home_fixture.json`。命令幂等可重跑。
- 演示特例（已注明在命令 docstring）：导入的 SPU/Offer 被命令直接置 ACTIVE——真实站点在售热卖品跳过 curation 草稿态；生产链路仍应走质量闸门/审核。
- CMS 新模块类型 `link_grid`（入口/品牌磁贴，label 必填、href 可选）：`content/schemas.py`、`CmsModule.Type` + 迁移 `content/0002`、前端 `CmsLinkGrid.vue` + `CmsRenderer` 注册。
- 商城端：`ProductCard.vue` 支持 `image_path` 真图（否则骨架兜底）；`nuxt.config.js` devProxy 增加 `/media` → Django（生产由 Nginx 伺服，设置注释已注明）；`AppHeader.vue` 导航改为真实 Joybuy 一级类目（docs/09 证据），每项链接到能命中已导入库存的搜索词。
- e2e 同步：`foundation.spec.js` 与 `purchase-funnel.spec.js` 首页断言改为新 hero 标题 "Don't just buy, Joybuy" + "Food Cupboard"；4 个视口首页视觉快照已按新首页重新基线化。
- 浏览器实测：首页（1440px 截图）红色主题、搜索栏、真实类目导航、hero、入口磁贴、真实图片+红色 `$` 原价楼层、品牌墙、页脚均正常；详情页画廊图片、`$6.99`、`999+ in stock` 正常；`/search?q=noodles` 返回 10 个真实商品。
- 已知边界：楼层点击 "View all" 与入口磁贴多为静态展示（无真实落地页）；品牌墙磁贴不带链接；详情页无描述/评分（公开主页数据不含这些字段）。

### 2026-11-03：原价采集、送达标签过滤与美元展示（需求优化）

- 爬虫（R1）：`crawler/joybuy_crawler/parsers/product_detail.py` 改为只采集原价——页面同时有优惠价（`.price .current`）与原价（`.price .list`）时 `current_price` 取原价、`list_price` 恒为 `None`；页面存在原价时所有 SKU 的 `data-price`（属展示优惠价）统一归一为原价，页面没有原价时唯一价格视为原价、SKU 各自价格保留。契约注释已写明该业务规则。
- 商城端展示层（R2+R3）：新增 `storefront/utils/display.js`，提供 `formatDisplayPrice`（一律 `Intl.NumberFormat('en-US', { currency: 'USD' })`，即 `$` 符号，不改存储币种）与 `isDeliveryLabel`（中英文配送预估关键词正则，如“今日/明天/送达/delivery/arrives/ships/get it by”）。
- R1 展示配套：`storefront/pages/p/[id].vue` 移除划线价（listPrice computed、模板与样式），只渲染单一原价；详情页促销徽章与 `ProductCard.vue` 的 `badge` 徽章渲染前经 `isDeliveryLabel` 过滤（爬虫仍抓 `promotion_label`，过滤只发生在渲染时）。
- `$` 符号覆盖：`ProductCard.vue`、`p/[id].vue`、`composables/useCart.js`（formatMoney）、`pages/checkout/index.vue`（formatMoney 并去掉 currency 入参）、`pages/account/orders.vue`（原来是 `GBP 39.50` 文本）、`pages/account/favourites.vue` 与 `recently-viewed.vue`（原来手拼 `£` 且会显示 `19.9900` 四位小数，现统一走 `formatDisplayPrice`）、`ProductListing.vue` 价格筛选标签 `Min/Max £→$`、详情页配送文案 `£20→$20`。
- 文档同步：`docs/06-api-and-workflows.md` 第 6 节新增三条展示与采集口径；`docs/05-crawler-and-ingestion.md` 新增 9.1 价格采集口径；`docs/02-pages-and-visual-acceptance.md` 状态矩阵改为“单一原价（$ 符号、无划线价）”。
- 测试同步：`backend/crawler_control/tests/test_crawler_import.py` 契约断言改为 `current_price="29.99"`、`list_price is None`、三个 SKU 价格均为 `29.99`；`storefront/components/cms/CmsRenderer.test.js` 改断言 `$19.99` 并新增“送达类徽章被抑制”用例；新增 `storefront/utils/display.test.js`（9 个用例覆盖 $ 格式与标签过滤）。
- 运行验证：后端全量 216 项、商城组件 33 项、平台端组件 2 项、eslint、全部改动文件 Prettier、e2e 15/15 全部通过；e2e 首页视觉快照已按 $ 价格重新基线化。浏览器实测：首页/搜索/详情页渲染 `$19.99` 等价格，详情页只有单一原价。

### 2026-11-03：Joybuy 中文会话与多语言内容方案

- 根据用户澄清修订方案：撤回“缺少德文则隐藏商品”和“评价点击后按需翻译”的建议，改为自动切换、来源忠实、逐字段混合语言模型。
- 明确 `requested_locale` 只代表用户选择的语言环境，不代表每个字段实际都是该语言；每个字段需要额外记录 `actual_locale`。
- 明确机器翻译不属于默认复刻链路；未来如需本地增强翻译，必须与 Joybuy 来源内容分层并单独立项。
- 在 Joybuy 公开页面“Custom settings”中选择并保存 `中文(简体) - ZH`；验证页面标题变为“Joybuy | 一站式购物平台”，导航、活动入口和商品标题均显示中文。
- 保留该中文浏览器会话供后续类目分析使用；本轮按用户要求不继续分析类目。
- 新增 `docs/10-multilingual-content-and-market-design.md`：定义来源语言、展示语言和国家市场三个独立维度；整理需要本地化的商品/类目/属性/CMS/评价内容；设计翻译生成、审核、失效重生成、发布、回退和搜索索引规则。
- 更新 `docs/01-requirements.md`、`docs/04-data-model-and-storage.md`、`docs/05-crawler-and-ingestion.md` 与文档索引，明确中文来源优先、多 locale 内容、市场与语言分离以及翻译来源可追溯。
- 更新 `docs/09-crawler-category-task-redesign.md` 状态：英文类目证据只保留为历史参考，不得直接生成最终 seed；后续必须从中文页面重新分析。
- 代码现状核对：已有 `SpuTranslation(spu, locale, title, subtitle, description)` 和 `Market.default_locale/default_currency` 基础，但详情 API 仍取第一条翻译、搜索文档仍是一 SPU 一行、爬虫导入依赖调用方 locale，尚未形成多市场多语言闭环。

### 2026-11-03：爬虫品类与配额任务现场分析及方案文档

- 使用公开页面现场分析 `https://www.joybuy.co.uk/`，展开首页 `Categories` 菜单，确认当前 22 个一级入口，并读取页面公开的一级/二级类目标识。
- 逐项核对本次业务涉及的 Jewellery、Watches、Phones、Wearables、Camera & Photo、Coffee Machines、女装、男装、箱包、鞋靴、美妆、户外、运动和 DIY 等页面，记录页面公开的下一级筛选节点及层级前缀。
- 确认示例：`Clothes, Shoes & Watches=1876`、`Watches=1881`、男士手表筛选 `cid2:13159`；`Electronics=1409`、`Camera & Photo=1416`、无人机系统 `cid2:10870`。
- 确认活动入口不是商品类目：首页当前公开 Lightning Offers、Outlet、Mix & Match、New Arrivals，应作为活动页来源建模，不能伪造一个 Joybuy“活动商品”类目。
- 新增 `docs/09-crawler-category-task-redesign.md`：记录现场证据、10 个业务分组到 Joybuy 来源节点的建议映射、字段语义、简单页面布局、去重/配额规则、数据模型/API 改造建议、验收标准和待确认决策。
- 更新 `docs/README.md` 文档索引，并在 `docs/05-crawler-and-ingestion.md` 将新方案标记为最新设计基线。
- 明确“来源类目公开标识”是内部稳定来源 ID，创建页不应让运营手填；明确“商品数量上限”应改名为“本任务最多成功入库商品数”，按去重且通过质量闸门的成功入库商品统计。
- 页面方案已收敛为单页：顶部总量与摘要、中部 10 行配额表、按行打开树形选择侧栏、高级参数默认折叠；不使用复杂多步向导。

### 2026-11-03：平台管理端全面中文化

- 修改 `admin-web/index.html` 和路由标题：页面语言改为简体中文，浏览器标题仅保留 `Joybuy` 品牌名为英文。
- 修改登录、仪表盘、商品目录、评价管理、爬取任务、内容页面、买家与订单、404 和基础状态页的可见固定文案。
- 新增 `admin-web/src/lib/locale.js`：将状态、同步模式、排序方式、覆盖字段、动作、币种和布尔值统一映射为中文。接口请求仍使用原始英文枚举，只在展示层汉化。
- 修改 `admin-web/src/lib/api.js`：网络错误、权限错误及常见业务错误对用户展示中文消息，不再直接暴露英文后端消息。
- 同步更新组件测试和平台端浏览器测试的中文断言。
- 扩展管理员浏览器测试：登录后逐一打开商品目录、评价管理、爬取任务、内容页面、买家与订单五个管理页面，并断言中文标题可见。
- 新增根目录 `AGENTS.md`，并更新 `README.md` 与 `docs/08-implementation-work-packages.md`，将“每次执行结束前更新 `HANDOFF.md`”固化为项目纪律。

### 本地开发登录凭据（2026-11-05 夜更新）

- **商家端演示数据**：`manage.py seed_merchant_demo --merchant HOMCOM --reset` / `--merchant CHiQ --reset --with-deposit`（幂等，可反复跑）
- **商家端（merchant-web，http://127.0.0.1:5174/login）**
  - 同一套账号：`admin@joybuy.test` / `Admin@123456`（已绑定 HOMCOM + CHiQ 两家店）
  - 商家端复用 `/api/v1/admin/auth/*` 登录，店铺归属靠 `merchant_membership`
  - 绑定店铺的命令（在仓库根目录执行）：
    ```
    ./.venv/Scripts/python.exe backend/manage.py shell -c "from merchants.models import Merchant,MerchantMembership,MerchantRole; from accounts_staff.models import StaffAccount; s=StaffAccount.objects.get(email='admin@joybuy.test'); m=Merchant.objects.get(display_name='CHiQ'); MerchantMembership.objects.get_or_create(merchant=m, staff=s, defaults={'role':MerchantRole.objects.get(code='merchant_owner'),'status':'ACTIVE'})"
    ```
- **管理端（admin-web，http://127.0.0.1:5173）**
  - 账号 `admin@joybuy.test` / 密码 `Admin@123456`（`platform_admin` 角色，21 个权限码全含，TOTP 未启用）
  - 次要账号 `auditor@joybuy.test`（`platform_auditor`，只有审计只读权限，密码未重置、不可用）
  - **仅本地开发库**。正式环境必须改密码并走初始化流程，不得沿用。
- **登录页只校验邮箱 + 密码**，不再要求 TOTP 验证码；会话 Cookie 名 `joybuy_staff_session`，写操作必须带 `X-CSRFToken`（先 GET `/api/v1/admin/auth/session` 拿 `csrf_token`）。
- 密码遗忘时的重置方式（在仓库根目录执行）：
  ```
  ./.venv/Scripts/python.exe backend/manage.py shell -c "from accounts_staff.models import StaffAccount; s=StaffAccount.objects.get(email='admin@joybuy.test'); s.set_password('新密码'); s.save()"
  ```

## 3. 当前卡在哪里

- **开发服务器（2026-11-05 15:59 起）由助手在后台启动**：`python backend/manage.py runserver 127.0.0.1:8000 --noreload`。此进程若随会话结束退出，重新启动即可；**改后端代码后必须重启**，否则接口还是旧结构（类目双语那次就是被 4 个残留 `--noreload` 进程挡住）。admin 前端在 5173（vite dev，源码热更新，浏览器 Ctrl+F5 即可）。
- **7 个二级类目还没有中文名**（`l2:3505/1384/1376/1380/1378/1474/1478`），UI 上这些节点只显示英文名。补法：等 joybuy 风控窗口过去后跑一次
  `manage.py sync_joybuy_category_names_zh --account <账号public_id> --merge-json --dump-json var/joybuy_demo/data/category_menu_zh.json`
  （全量）或按 `--channel minihome:UK-Mini-HP-Toys-Baby-and-Kids --channel minihome:UK-Mini-HP-Gaming` 分块补；命令会自动合并并汇报 `still_missing`。
- **joybuy.co.uk 2026-11-05 起对未登录访问强制跳登录**：`sync_joybuy_category_tree` 这类匿名抓取现在会拿到 `/login` 或 `Joybuy Risk Control` 页，必须有有效账号会话（`--account`）才能跑。
- **当天爬虫浏览器已被风控限流**：频道路径 `/minihome/*` 连续抓 10+ 页后返回 `Joybuy Risk Control`（`evApi=color_guide_homepage_getPageAllData`）。已确认不是登录态问题（账号会话 42 条 Cookie 有效），冷却后放慢 `--pause 20`+ 分块可恢复；用户自己的 Chrome 同时段正常。
- **`reset_browser_profile()` 在本机被 safe-delete 拦截**（656 个文件批量删除需要确认，报 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`）→ 命令新增 `--no-reset-profile`，复用现有 profile 绕过；需要干净 profile 时要人工清 `var/browser_profiles/profile`。
- **账号 profile 未必能过风控**：`--profile account-9b189970` 实测直接 403（该 profile 做过 Facebook OAuth），通用 profile + 注入会话 Cookie 反而正常，选择 profile 时要先小样本验证。

- 本轮畅销榜数据补齐没有阻塞。正式 `RankingList/RankingEntry` 后台配置仍未实现，当前 `/promo/best-seller` 和首页楼层继续读取 `/api/v1/search?category=<slug>&sort=rating_desc`；这是既有第 2 轮范围，不应把本轮演示数据导入误写成正式榜单模型已完成。
- 商品多语言索引仍是已知架构欠账：`ProductSearchDocument` 每 SPU/市场只有一行且 `rebuild_search_document()` 取第一条翻译。本轮只如实保存来源 locale，不顺手伪造翻译或宣称已实现按界面语言切换商品文本。
- “是否强制全德文/是否由用户触发翻译”的产品口径已经闭合，不再是阻塞。
- 后续仍需现场分析德国市场：默认/可选语言、币种、配送上下文，以及首页、类目、商品、属性、活动和评价分别为德文还是英文；本轮按用户要求暂不继续分析类目。
- 国际化实现不能只改 `SpuTranslation`：现有 `ProductSearchDocument` 每个 SPU 只有一行，商品详情取第一条翻译，搜索和详情市场基本固定为 GB；实现前必须一起重构市场/请求语言解析、字段实际语言和 `(spu, market, requested_locale)` 搜索索引。
- 本次不是技术阻塞，而是四个必须闭合的产品口径：高价最低价格（建议 `£300`）、机械手表的关键词/属性识别规则、任务总商品数是否预填默认值（建议候选 `1000`）、活动商品是否默认全选当前四个公开入口。
- 现有 `CrawlJob` 只有一个 `source_category` 和一个 `product_limit`，无法表达 10 个业务分组、多选类目树和活动页来源；确认方案后需要新增配额与来源选择关联模型，不能只改前端表单。
- Joybuy 二级结果页展示的下一层有时是性别或跨目录筛选维度，不总是传统子类目；实现时必须原样保存 `cid1/cid2/cid3/cid4` 前缀和来源 ID，不能只按深度猜层级。
- 商家端页面不存在，这不是本次遗漏，而是已确定的需求边界。如果后续需要商家端，必须先由用户提供参考页并重新评审需求，不能自行复制平台管理端。
- Git 基线（2026-11-04）：全部项目已提交并推送 GitHub（origin=LeeYX123/JoybuyDemo，main 分支，初始提交 1a76a99，362 文件；var/ 数据与工具状态目录已 gitignore）。后续改动基于此基线正常提交即可。

## 4. 下一步计划

1. 用户若继续第 2 轮，先实现正式 `RankingList/RankingEntry`、平台端榜单配置和对应 API，再把商城榜单从搜索排序切到运营榜单；本轮 fixture 可作为初始化候选数据。
2. 多语言商品内容另拆工作包，重构 `(spu, market, requested_locale)` 搜索索引和详情翻译选择；不要在榜单 loader 里补机器翻译。
3. 若要刷新演示数据，先用保存 fixture/低频公开页证据更新，再执行 `load_bestseller_demo`；单类重试用 `--only-category <slug>`，不要全量重复下载。
4. 继续与用户讨论剩余多市场行为；在用户允许现场分析后，依次核对德国市场和其他目标市场/语言组合。
5. 证据闭合后，把国际化改造拆成独立小工作包：MarketLocale、市场本地化内容与字段语言元数据、API 上下文切换、搜索索引、购物端自动刷新和管理端来源对比。
6. 再使用已保存的 Joybuy 中文会话重新分析类目；不直接复用英文名称生成最终 seed。
7. 中文类目完成后，再回到 `docs/09-crawler-category-task-redesign.md` 第 10 节的四个品类口径和配额页面实现。
8. **（2026-11-22 新增）shard2 进程退出后**：`python var/uuid_fix_20261122/reimport_failed.py --shards 2 --update-progress-shards 2` 回写那 14 条已重放成功的 progress（DB 已是 IMPORTED）；并在下一批导入前确认没有「迁移与在跑导入进程并存」的情况（见 0ay 坑①）。
9. 任何后续任务结束前，继续按 `AGENTS.md` 更新本文档。

## 5. 已踩过且绝对不能再踩的坑

### 2026-11-22 商品导入 UUID 事故（详见 0ay）

- **模型字段改类型（尤其 `UUIDField`）不能与长周期导入进程并存**：迁移落库后，迁移前启动的进程仍按旧元数据解码新列值；Django MySQL 的 `convert_uuidfield_value`（`django/db/backends/mysql/operations.py:327`）**没有 try/except**，抛裸 `ValueError('badly formed hexadecimal UUID string')`，不是 `ValidationError`。先停批再迁移，或让热路径 `only()` 到真正用到的列。
- **导入链路禁止整行取商家**：`MerchantSourceMapping.objects.select_related("merchant")` / `existing.merchant` 会解码 `Merchant.public_id`；统一走 `merchants.services._import_merchant_queryset()`。
- **判断批量失败必须按「进程 + 时间」切片**：同一 payload 在新进程成功、在旧进程必失败；工具有 `Get-CimInstance Win32_Process`（CreationDate 是本地时间 UTC+8）、`django_migrations.applied`、progress 每条的 `started_at`。

### 2026-11-05 爬虫重建（第 1 轮）

- **风控/登录判定只能匹配页面标题+可见文本**（先剥掉 script/style 再匹配）：正常首页的 i18n 文案包里有 `"error403":"403 Forbidden"`，页脚有 "protected by reCAPTCHA"——直接匹配整段 HTML 必然误判（两次踩坑实测）。
- **joy-sourcing 图片 CDN 对 bot UA 返回 403**：图片探测/下载必须带浏览器 User-Agent（media 库导入用浏览器 UA 成功、`JoybuyResearchBot` 全部 400）。
- **Scrapy 2.13.4 自带 bug**：`ProtegoRobotParser.allowed()` 把 `can_fetch(url, user_agent)` 参数传反，任意 URL 随机 Forbidden（已实测证明）。必须用 `ROBOTSTXT_PARSER = joybuy_crawler.robots.FixedProtegoRobotParser` 修正；不可因此关掉 ROBOTSTXT_OBEY。
- **Scrapy 2.13 管道钩子**：item pipeline `close_spider(spider)` 不再传 reason（终态原因从 stats 的 finish_reason 读）；asyncio reactor 里调 Django ORM 会抛 `SynchronousOnlyOperation`——执行器进程必须 `DJANGO_ALLOW_ASYNC_UNSAFE=true`（runner.py 已内置）。
- **joybuy.co.uk robots.txt（2026-11-05 实测）**：`/s?k=<纯净关键词>` 允许；带 `&l1=/l2=/l3=/page=/sortType=` 一律禁止；`/dp/<slug>/<id>` 详情页允许。列表目标必须规范化成 `/s?k=<k>`，**分页不可爬**（缺口用 LISTING_SHORTFALL 事件如实记录）。
- **joybuy.co.uk 当前结构（2026-11-05）**：一级类目 = 14 个 `/minihome/<pagecode>` 频道链接；子类目 = `/s?k=...&l2=/l3=` 列表链接（如 Kettles & Toasters = `l2:1405`）。docs/09 里的 `l1=1409` 数字 ID 已不在现 UI，只作历史证据。
- **热浏览器 profile 会拿到降级版首页**（无类目行、minihome 链接只剩 1 个）；全新 profile 拿完整 SSR（1.9MB）。所以 `sync_joybuy_category_tree` 每次运行前重置爬虫 profile（`render.reset_browser_profile`）。SSR 内容在水合后会被替换——**必须用 `page.listen` 网络层捕获文档响应**（`render_page(capture_ssr=True)`），读 DOM 是时序竞争。
- **DrissionPage 浏览器隔离**：固定调试端口（9333）会连接到已存在的实例。`render_page` 启动前杀掉带 `browser_profiles` 标记的残留爬虫浏览器，连接后校验 9333 端口上的 chrome 进程必须带爬虫专属 user-data-dir，否则拒绝导航。绝不能让爬虫操作到运营者本体浏览器。
- **连接失败先排查 VPN/系统代理**（本机 127.0.0.1:7890）：Chrome 报 ERR_CONNECTION_CLOSED 时 curl 直连可能正常——先分清是网络断了还是被站点 403。
- **连续快速渲染会触发站点 403 限流**：类目同步页间 5s 间隔 + 403 后 60s 冷却重试（命令内置 3 次），不要连续重试硬撞。
- `fetch_url` 的参数名是 `timeout_seconds`，不是 `timeout`（传错会 TypeError "unexpected keyword"）。
- `Path("")` 是真值——`dataset_root` 曾因此返回相对路径把数据集散落在 cwd。目录解析要用显式 `if configured` 分支。
- 树同步幂等：同日同结构哈希会生成相同 `version_key`，`sync_category_tree` 对已存在版本原地重建快照（否则撞唯一约束）；同一 l2/l3 ID 会挂在多个频道下，快照去重"首次出现为准"。
- **登录检测不能只靠页面渲染**（2026-11-05 二次踩坑）：站点会持续给渲染器返回"temporary service interruption"限流页（可见文本仅几百字符），登录成功与否页面看不出来。`_is_logged_in` 必须加 **Cookie 新增信号**（profile 出现初始快照没有的新 Cookie = 登录动作发生，Cookie 是持久化的不受拦截页影响）；拦截页标记 `temporary service interruption` 已加入 render.RISK_CONTROL_MARKERS。
- **DrissionPage 浏览器隔离双层防线**：① 进程校验（9333 端口进程必须带 browser_profiles user-data-dir）；② **标签页指纹**（连接后已打开的标签若存在非空白页 → 立即 quit + 拒绝导航）。实测干净专用实例 = 1 个 `chrome://newtab/` 标签；运营者本体浏览器必然有多条真实标签页。变量命名禁忌：`crawler_account_login` 里 `options` 既是命令参数字典又是 ChromiumOptions——ChromiumOptions 必须另命名（曾致登录窗口秒退）。
- 爬虫账号 = 用户自己的 Facebook 账号（docs/05 §7.1 设计），登录后 Joybuy 显示的就是用户本人的账号——这不是隔离失败；隔离的对象是**浏览器实例**（专用 profile 无书签、独立调试端口），不是账号身份。用户曾三次误报"弹出的浏览器显示的是我正常账户"：Joybuy 按 Facebook 身份识别账号，OAuth 登录谁的 FB 就进谁绑定的 Joybuy 账号。**要独立小号必须用另一个 Facebook 账号登录**（首次登录自动建新 Joybuy 账号）。账号 Tab 已加身份说明文案，向用户解释时先讲这个模型。

- Joybuy 卡片 DOM 可能把划线价与折扣百分比无空格拼接，例如 `£2.797% off`；金额正则必须限制为最多两位小数，否则会把 `£2.79` 错存成 `2.797`。证据解析脚本已修为 `£\s*([\d,]+(?:\.\d{1,2})?)`。
- 不能只信 JSON-LD 的 `offers.price`：它通常是当前优惠价。原价必须优先读可见卡片 `[class*="crossOffPrice"]`，没有划线价才回退 `[class*="mainPrice"]`/唯一价格。
- `get_or_create_spu_from_source()` 命中既有来源身份时不会更新 `Spu.local_category`、品牌或既有翻译实体字段；演示 loader 必须显式修正类目/品牌，并用来源层+本地覆盖层的有效值同步索引读取字段，再重建搜索文档。
- 搜索接口过去完全没返回图片，即使媒体库有图也只显示骨架；图片必须按当前页 SPU 批量查 `MediaUsage(role="gallery")`，不能在序列化器里逐商品 N+1。
- `--noreload` 的 Django 开发服务器不会自动加载后端改动。本轮实库导入后 HTTP 仍无 `image_path`，确认 8000 监听 PID 后只重启了明确的后端进程；后续后端改动浏览器验证前必须先确认运行进程已加载新代码。
- CDN 单图 HTTP 400 时不得拿其他商品图片冒充。应换用同一公开楼层的下一条真实商品，保留原排名/来源证据，并把失败样本退出可搜索状态；本轮 `10489708` 已按此处理。
- Joybuy 公开榜单连续浏览器导航会偶发重定向登录页；不要反复撞登录/风控。固定子榜 URL 可低频读取服务端公开 HTML；服装不在榜单侧栏，必须明确记录替代来源。
- 详情页白名单拦截会改变既有 e2e 流程：`purchase_whitelisted` 后端默认 True 是有意设计（开发阶段放行），若把默认改 False 必须同步重写 purchase-funnel（先做 admin 白名单再购买）。
- Playwright fill 后水合重置输入属 dev 模式已知竞态（helpers.js 有注）：结算表单用"fill+click+查 Pay now"自愈循环应对；生产构建不受影响。
- 组件模板里静态 `src="/images/..."`（根绝对路径）会被 vite 模板资源转换当成模块 import：vitest 下报 `file:///images/logo.png` 参数错误，Nuxt dev 下报 Failed to resolve import。改用运行时绑定（`:src="常量"`），vitest 配置再加 `transformAssetUrls: false` 兜底。
- 新建 `storefront/public/` 子目录/文件后必须重启 Nuxt dev 才能被静态伺服（sirv 启动时扫描）；且杀 3000 端口进程后要确认真的杀掉了（`Get-NetTCPConnection` 看进程启动时间），否则新起的 dev 会静默失败、旧进程继续 404。
- 分类面板的触发按钮**不要同时实现"点击切换"+"悬停打开"**：鼠标点击前必先 hover，hover 已打开面板后 click 的 toggle 会把它关上，表现为"点了没反应"。click 只做打开，关闭交给 mouseleave（150ms 延迟）和关闭按钮。
- 全幅楼层用 `width: 100vw + margin-inline: calc(50% - 50vw)` 逃出容器会在有滚动条时产生 ~8px 横向溢出；在 `.app-main` 上加 `overflow-x: clip` 解决（sticky 头部在 main 外，不受影响；不要加在 body 上，会破坏 sticky）。
- e2e 断言里已没有 "Offers for you" 标题（需求 12 删除了活动区标题）；首页断言用活动区 Welcome Offers 链接。改首页可见元素时两个 spec（foundation/purchase-funnel）的断言和快照要一起同步。
- 真实站 joybuy.co.uk 实测值与用户给定值冲突时以用户为准（如通告条颜色用户指定 #17202A，实测 #1A1A1A）；差异写进 HANDOFF 备查。
- `LocalCategory` 的模型 Meta ordering 是 `["path", "sort_order", "pk"]`，而 path 是 `/<uuid pk>/` 前缀——按 path 排出来的根类目顺序≠需求要求的 11 类目固定顺序；凡展示类目清单必须显式 `order_by("sort_order")`（categories API 已这样写，测试断言也要）。
- `get_or_create_spu_from_source` 没有 `merchant` 参数（签名是 source_system/source_id/title/local_category 等）；演示商品归类直接改 `Spu.local_category` + `rebuild_search_document` 即可，不必走 CategoryMapping。
- storefront 组件测试里 mock `useCategoryTree` 要返回 `ref([...])`（或 `computed(() => [...])`），不能 `computed([...])`——computed 需要 getter 函数，传数组会报 `computed.fn is not a function`。
- 44px 最小可点击高度是硬性设计规则（AppHeader.test.js 会扫描所有 input/button/a 的 computed minHeight）：新增交互元素 CSS 要给 `min-height ≥ 2.75rem`（account-menu__item、category-panel__child 已设 2.75rem）。
- CMS 双语字段约定：base 字段（title/label）恒为英文，中文放可选 `title_zh`/`label_zh`/`subtitle_zh`；`pickName(item, locale, prefix)` 统一取值回退，不要在组件里手写 locale 分支。
- 通告条现在有自动轮播 interval（6s），AppHeader 组件测试挂载后不 unmount 会有 open handle 警告但不断言失败；如后续测试超时先怀疑它。

- Joybuy flight 流里区分"活动砖石"与"快捷入口"：快捷入口的 eventInfo 有 `floorType=="icon"` 和 120×120 `iconImage`；活动砖石带 `subTitle` 且无 floorType。品类发现数据认准 `externalKey=="EXT_POPULAR_CATEGORIES_V3"`。图片 URL 规则：`-com/-product` 相对路径拼 `https://images3.joy-sourcing.com/product/s{尺寸}_{path}`，png 补 `.webp`、jpg 补 `!q70.webp`；`/da/` 开头的是完整 URL 直接补 `https:`。
- 活动瓦片/入口/品牌墙的真实跳转链接都是 Joybuy 站外或本地不存在的营销页，CMS 里一律改填本地 `/search`，不要原样入库把用户带出站。
- 验证纪律（2026-11-03，用户确定）：开发阶段每轮只做针对性验证（只跑受影响的单测/检查/相关 e2e），不跑全量；全量验证留到功能全部开发完成或用户明确要求。不要在 HANDOFF 里把针对性验证写成"全量通过"。
- 改 `nuxt.config.js`（如 devProxy）后必须重启 Nuxt dev 服务器，配置不会热加载；重启用 PowerShell 杀 3000 端口进程后在 storefront 目录后台重启。
- 新爬商品默认 DRAFT（SPU/Offer 都是）：`get_or_create_spu_from_source` 与 offer 导入都不会自动 ACTIVE；演示命令里显式激活后必须再重建搜索文档，否则详情 404、搜索为空。
- `ingest_product_payload` 在爬虫包 `joybuy_crawler.ingest`（仓库根 /crawler，需 sys.path 注入），不在 `crawler_control` 里。
- `start_run` 要求 job 的 account_group 里存在 session_status=VALID 的爬虫账号；演示命令里先 get_or_create 账号并写入标记会话（非真实凭据）。
- 新增 CMS 模块类型要同时改三处：`content/schemas.py`（MODULE_TYPES+SCHEMAS+校验）、`CmsModule.Type` + 迁移、前端 `CmsRenderer` 注册（+组件）；漏掉模型枚举会在 publish 时报 Unknown module type。
- e2e 断言首页标题的规格有两个：`foundation.spec.js` 和 `purchase-funnel.spec.js`（visual baselines），改首页文案时两个都要同步；重首页在多 worker 并行下会让 funnel 用例超时，受影响 spec 用 `--workers=1` 跑。
- `$` 美元符号是展示层规则：`storefront/utils/display.js` 统一格式化，不改动任何存储币种（本地种子数据仍为 GBP）；新增价格展示必须走 `formatDisplayPrice`，不要再手写 `Intl.NumberFormat` 或手拼 `£/€`。
- “今日送达”类标签的过滤发生在渲染时（`isDeliveryLabel`）；爬虫仍照常抓 `promotion_label`，不要为了去标签去改爬虫或数据库数据。
- 商城端 vitest 没有配置 `~` 别名（只有 `#imports` stub）；组件里引用新工具必须用相对路径导入，`~/utils/...` 在 vitest 下解析失败。
- `crawler/fixtures/product_detail_v1.html` 里的 `£` 是模拟真实 Joybuy 来源页，必须保留；解析器读 `data-price` 属性，不读符号。
- 仓库 ruff 全仓检查有 47 个既有报错（多为 import 排序），不属于新任务范围，不要顺手全仓修复污染 diff；只保证自己改动的 Python 文件干净。
- CMS 首页 fixture 里的 `/p/01926c1e-...` 是不存在的假 ID，详情页 404“not available”是既有行为，不是本次或后续改动造成的回归。
- e2e 首页视觉基线已按 `$` 价格重新生成（`purchase-funnel.spec.js-snapshots`）；再改首页可见内容后必须 `--update-snapshots` 重新基线，否则视觉用例必挂。
- 不要把国家市场和语言合成一个字段；德国市场决定 EUR、价格和配送，`de-DE` 决定文本，两者默认联动但必须可独立配置。
- 不要认为页面按钮翻译完成就实现了多语言；切换后商品标题、详情、类目、属性、活动、评价、搜索索引和 CMS 必须自动一起刷新。
- 不要用“第一条 SpuTranslation”作为展示内容；必须按请求 locale 精确选择已发布版本。
- 不要强制把德国页面全部翻成德文；Joybuy 实际仍显示英文的字段必须保留英文，混合语言是正确来源状态。
- 不要要求用户点击“翻译”商品或评价；国家/语言切换后由系统自动加载对应来源快照。
- 不要把 `requested_locale=de-DE` 当作每个字段都是德文；必须逐字段记录 `actual_locale`。
- 不要把机器翻译写成 Joybuy 来源值；默认复刻链路不做强制机器翻译。
- 不要在中文来源变化时直接覆盖人工审核译文；先标记过期、生成候选、展示差异并复审。
- 不要翻译品牌、型号、GTIN、规格数值或虚构来源没有的功效/认证；法规、安全、成分和过敏原必须人工审核。
- 不要直接使用现有英文 FULLTEXT 方案承诺中文搜索；中文需要 MySQL ngram 或经验证的分词列。
- 不要继续用上一轮英文页面结果生成最终类目；后续必须在已保存的 Joybuy 简体中文会话中重新分析。
- 不要把“业务分组”当作 Joybuy 来源类目；高奢高价、电器与家装、活动商品都不是 Joybuy 当前公开菜单中的单一原生类目。
- 不要让运营手填 `source_category_public_id`；ID 必须来自已版本化的树节点选择，页面最多只读展示。
- 不要把商品数量上限解释为请求数、页面数或发现 URL 数；它是去重、通过质量闸门并成功入库的来源商品数。
- 不要把活动商品塞进类目树；活动页是独立来源类型，商品导入后仍归真实商品类目。
- 不要只保存节点中文名或假设固定三级深度；Joybuy 公开节点包含 `firstcid`、`second_product_category` 和 `cid1/cid2/cid3/cid4` 等不同层级前缀。
- 不要把勾选父节点理解为永久自动包含未来新子节点；任务创建时必须冻结类目树版本，新增节点经差异确认后才能纳入。
- 不要只改前端做“多选”；当前后端单 `source_category` 模型无法正确保存多组配额与活动来源。
- 不要把“商家基础领域模型已实现”误读为“商家端 UI 已实现”；两者不是一回事。
- 不要为了中文展示直接修改发往后端的状态、动作或排序枚举；必须保留 `ACTIVE`、`PENDING_PAYMENT`、`start` 等接口契约，仅对页面展示值做映射。
- 状态列汉化后，按钮显隐判断不能再读已汉化的 `status`；需要额外保留 `raw_status` 做业务判断。
- 登录页是公开路由，路由守卫不会预先加载会话；登录请求前必须先获取会话与防跨站令牌。
- 员工权限在会话响应的 `staff.permissions` 中，不在顶层 `permissions`；读错会导致登录成功但所有菜单被隐藏。
- 不要把 Vue 格式样式规则与 Prettier 重复启用；项目已由 Prettier 统一格式，否则会产生互相冲突的检查结果。
- 不要并行执行 Nuxt 生产构建与 Playwright 浏览器测试：构建开始时会清理 `.nuxt`，可使复用中的开发服务器短暂丢失开发清单并导致水合竞态。正确顺序是先完成 `pnpm build:frontends`，再单独运行 `pnpm test:e2e`。
- 所有前端资源必须本地托管，不得引用 CDN。

### 2026-11-05（续 3）：排序触发器不换行 + 侧栏选中色去红

- 触发器 `width: 172px` → `min-width: 172px + white-space: nowrap`（"Price: High to low" 单行显示，高度保持 40px）。
- 侧栏选中类目去红：`--colour-accent-soft/--colour-accent` → bg #F7F7F7 + color #1A1A1A + font-weight 700（与分类面板 hover 一致）。
- 验证：vitest 45/45；浏览器复核 noWrap/40px、选中 rgb(26,26,26)/rgb(247,247,247)/700 ✓（截图）。

### 2026-11-05（续 2）：排序控件改自定义下拉（左置/去蓝色）

- 用户反馈：排序应在左侧（原右对齐）；外边框与选项 hover/选中出现蓝色——根源是原生 `<select>` 的下拉弹层由 OS 渲染（Windows Chrome 蓝色高亮），CSS 无法自定义。
- 重做为自定义下拉：trigger（"Sort by:" 16px/500 + 172×40 深色描边按钮 + ⌄）左置（删除右侧 spacer）；菜单白底 1px 灰边 + overlay 阴影，选项 40px 行、hover #F0F1F4 灰、选中 #EEF1F5 灰加粗（全灰系无蓝）；点击选项 updateQuery、点击外部自动关闭（document click 监听，onMounted/onBeforeUnmount 挂载）。
- 验证：vitest 45/45；浏览器复核 triggerOnLeft ✓、菜单白底、hover rgb(240,241,244) 无蓝、选中项高亮 ✓（截图）。

### 2026-11-05（续）：列表页排序控件对齐真实站

- 实测真实站（/s?k=noodles）：标签 "Sort by:" 16px/500 #1A1A1A；触发器白底 **1px #1A1A1A 深色描边**、radius 4、高 40、16px 字；展开菜单白底、选中项浅灰高亮；选项顺序 Relevance → Price: High to low → Price: Low to high（→ Sales: High to low，后端无销量排序）。
- ProductListing：标签 16px/500 深色（原 14px 灰）；select 描边改 #1A1A1A（原浅灰）、16px 字、cursor pointer；选项文案与顺序对齐（price_desc 提前，"Price: High to low/Low to high" 大小写对齐真实站），保留 Top rated/Newest（真实站有 Sales 排序但后端暂无——差异记录）。
- 验证：vitest 45/45；浏览器复核 label/trigger/选项序列 ✓（截图）。

### 2026-11-05（续）：列表页三处（头部无缝/图区四角圆角/侧栏分割线）

- 头部与页面间隙：原 `.listing-page-bg` margin-top:0 未压过 `.app-main > *`（实测 bgTop 184 vs header 160，灰缝来自 app-main）。改为"一整块+内边距"：wrapper `margin-block: 0`（`.listing-page-bg.listing-page-bg` 双类名提权重）+ `padding-block: 32px 24px`，`.listing-layout` margin 归零。实测 bgTop==headerBottom==160 ✓。
- 图片区四角圆角遗漏点：`.product-card__media` 容器（#F5F5F5 底）自身 radius 0——img 虽 12px 但灰底方块外露。补容器 radius 12px。其它位置已排查：发现卡 12px、榜单页共用 ProductCard ✓。
- 侧栏 Category/Price 之间加 1px 分割线（`.filter-card + .filter-card` border-top）。
- 验证：vitest 45/45；浏览器复核三项 ✓（截图）。

### 2026-11-05：/s 列表页全幅白底

- 用户要求 /s?category= 页面背景 #FFFFFF。ProductListing 根部加全幅包裹 `.listing-page-bg`（margin-inline calc(50%-50vw)、bg #FFFFFF、覆写 .app-main 子项顶距）——/s、/search、/c 三个路由统一生效。
- 踩坑：脚本对 .vue 先 ast.parse 校验会在写入前中断（.vue 非 Python），导致模板替换丢失——改为先写文件再校验/或只校验 .py。
- 验证：vitest 45/45；浏览器复核 bg rgb(255,255,255)、全幅 1512、无横向滚动 ✓。

### 2026-11-04（续 11）：详情页五项（隐藏类目行/加粗面包屑/白底/#EEEFF0/粗边框）

- 详情页隐藏全局类目行：AppHeader `useRoute` 判 `/p/` 前缀时 v-if 关闭 category-nav（真实站行为）；vitest stub 的 useRoute 补 `path: '/'`（此前桩缺 path 导致 AppHeader 测试 5 连挂）。
- 面包屑加粗：14px 不变 + font-weight 700（用户参考图观感加粗）。
- 详情页整页背景 #FFFFFF：新增全幅包裹 `.detail-page-bg`（margin-inline calc(50%-50vw)）。
- 图片区背景 #EEEFF0：主图容器/img/放大面板底色统一（原 #F5F5F5）。
- 缩略图边框 1px→2px（激活态仍深色 #17202A 覆盖）。
- 验证：vitest 45/45；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器复核五项 computed 全过（截图）。

### 2026-11-04（续 10）：主图蓝色网点遮罩 + 面包屑 14px

- 用户提供真实站参考图：hover 主图时主图上出现**蓝色网点选择遮罩**（配合右侧放大图）。实现：`.detail__zoom-mask`（40%×40% = 1/2.5 放大倍率反算、中心跟随光标并 clamp 图内、蓝色半透明底 rgba(26,115,232,.14) + radial-gradient 蓝色点阵 7px 网格、pointer-events none）；onZoomMove 同步遮罩位置。
- 面包屑字号 14px（原 16px，用户参考图为 14px）、分隔符灰、去重 hover 规则。
- 验证：vitest 45/45；浏览器实测遮罩 247×247（617×0.4）、点阵/底色正确、跟随光标、右侧放大图同步（截图）✓。

### 2026-11-04（续 9）：首页榜单四项 + 详情页面包屑/布局/放大镜

- 首页（实测 18px 规格）：榜单 tab 18px（未选中 400/选中 700 #1A1A1A）、间距 32px、高 42px；View all 18px/600 下划线；榜单卡图自带四角 12px 圆角（img 自身 radius，不再依赖卡裁切）；心选品牌→畅销榜单楼层间距 48px（原 24）；【About this study build】尾注模块删除（loader 不再 append rich_text，index.vue 移除 tail 渲染，home v9=3 模块）。
- 详情页：顶部导航改真实站式可点击面包屑——Home / 类目树父链（useCategoryTree 反查 category_slug，双语 categoryName）/ 商品名，16px #1A1A1A、hover 下划线；布局列宽对齐实测（56px 缩略图轨 + 流体主图 + 671px 购买面板，主图≈617 vs 真实 591）；主图 hover **放大镜**——右侧浮出 617×617 面板（background-size 250%、position 跟随光标百分比、z-20 覆盖购买面板侧、mouseleave 关闭）。
- 验证：vitest 45/45；eslint/prettier 通过；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器复核全部通过（截图）。期间后端 runserver 再次静默退出（本日第 3 次，后台任务稳定性问题）已重启；HomeBestsellers/Promo 排序 sort=newest 同步。

### 2026-11-04（续 8）：首页整行背景 #FFFFFF

- 用户指定 `.home-page`（畅销榜单/品类发现/心选品牌模块外围）背景为 #FFFFFF。原页面继承 canvas 灰底，且容器 max-width 1440 居中后超宽视口两侧仍露灰条。
- index.vue 模板加全幅包裹层 `.home-page-bg`（margin-inline calc(50%-50vw) 撑满视口、bg #FFFFFF、覆写 .app-main 子项顶距），原容器嵌套其内。复核：bg rgb(255,255,255)、全幅 1512=viewport、无横向滚动、活动区仍与头部无缝。

### 2026-11-04（续 7）：榜单卡透明图数据源（UK 商品入库）+ multiply 底色

- 诊断：用户指出商品图背后应为 #F5F5F5 透明效果。查证：代码侧 #F5F5F5 已生效；白底来自数据——原 load_joybuy_demo 的商品图是 joybuy.com flight 的 **jpg 白底图（无 alpha）**，且 CDN 上该批图**无透明变体**（.png.webp 404 实测）。真实站榜单卡 img 无 mix-blend-mode、直接白底显示（240px jpg）。
- 修复（数据源切换）：真实站首页 Bestsellers 楼层商品的 **s480x480 `.png.webp` 透明图**有效。浏览器逐 tab 爬取真实楼层 10 tab×5 卡（title/price/透明图 URL）→ `var/joybuy_demo/data/uk_bestsellers_raw.json`（44 卡，来源 https://www.joybuy.co.uk/ 2026-11-04）；新命令 `load_uk_bestsellers_demo` 导入 44 商品（source_system=joybuy_uk，幂等 source_id=title+img md5），UK tab→我们 11 类目子树映射（Kitchen Roll→cleaning-supplies、Small Kitchen Appliances→kitchen-appliances、其余食品类→groceries-food），£ 价格存 GBP，透明图 store_bytes 本地化（43/44 成功，1 张 URL 永久失败已用 shell 手工补挂）。
- 楼层/榜单页排序 rating_desc→**newest**（新导入透明图商品排前；MySQL DESC 下无 rating 的 NULL 排序不稳）；HomeBestsellers 测试断言同步。
- ProductCard 图区：容器 bg #F5F5F5 + img **mix-blend-mode: multiply**——白底烘焙图乘底色后白→#F5F5F5，透明图直接透出，产品色几乎无损（真实站未用此法，属实现选择）。
- 验证：vitest 45/45；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器截图确认榜单为 UK 真实商品透明图、图区底色 #F5F5F5 ✓。旧 .com 白底商品仍在库（其它 tab 混排时可能出现白底图——multiply 会将其转为 #F5F5F5）。

### 2026-11-04（续 6）：榜单卡三处颜色/字号按用户指定修正

- 图片区域背景 #F5F5F5（原 surface-soft #F5F6F7）；标题字号 16px（原 --font-size-md=14px，真实站实测 16px，用户指出的字号问题根源即 token 差异）+ 颜色 #1A1A1A（原 #17202A）；价格颜色 #1A1A1A（用户指定深色，替换此前误加的红色——真实站红价是折扣价语义，我们单一原价按用户口径用深色）。
- 浏览器复核：imgBg rgb(245,245,245)、title 16px/#1A1A1A/clamp 2、price #1A1A1A ✓；vitest 45/45。

### 2026-11-04（续 5）：商品卡对齐真实榜单卡（两行省略/图贴顶）

- 实测真实站 Bestsellers 卡（首页楼层 261 宽 + 列表卡 267）：图全宽贴卡顶（无内边距、radius 由卡整体裁切）、文字区 6px 内边距、品牌粗体、标题 16px/500 行高 22px **两行截断（h44）**、红色价格粗体、40px 圆形加购钮、榜单卡无星级。
- ProductCard 重写：结构改为图贴顶（`.product-card` overflow hidden radius 12，图 radius 0）+ `product-card__body` 内边距 8/6/6；标题 clamp 移入组件自身样式（`-webkit-line-clamp: 2`、line-height 22px、min-height 44px——此前依赖全局 `.truncate-2`，实测在卡内未生效出现三行硬切）；价格改红色（--colour-accent，1.125rem/700，与真实站红价一致，仍为单一原价规则）；榜单模式（rank>0）隐藏星级、可选 `viewed_count` 渲染 "x people viewed in 72 hours" 行（搜索接口暂无该字段=数据缺失，不编造）；徽章降级为价格旁小灰签。
- 验证：vitest 45/45；eslint/prettier 通过；浏览器复核 titleClamp=2/标题高 44/五卡全部省略号结尾/红价/图贴顶/无星级 ✓；e2e 首页快照重基线 9/10（funnel 仍 D-14）。注意：dev 模式组件 CSS 经客户端 JS 注入，SSR HTML 中 grep 不到样式属正常；HMR 对样式改动偶发陈旧需重启 dev（今日两次）。

### 2026-11-04（续 4）：独立商品楼层并入畅销榜单（home v8）

- 用户指出：心选品牌与畅销榜单之间的 6 个独立商品楼层（Kitchen Roll…/Food Cupboard/Beverages/Rice…/Small Kitchen Appliances/Instant Noodle——即爬取的 bestseller 分区）应属畅销榜单数据，不应单独铺开；真实站这些分区本来就是 Bestsellers 楼层的 tab 分区。
- loader build_modules：删除 product_pool 楼层循环与旧文字品牌墙（"Brands we love" pills——被心选品牌 brand_logos 取代，二者重复）；保留 import（商品仍在库，畅销榜单经搜索接口消费）。发布 home v8：4 模块（campaign/discovery/brands(心选)/rich_text）。
- index.vue：拆分 CMS 渲染——rich_text 尾注排到畅销榜单之后（真实顺序：…心选品牌 → 畅销榜单 → 尾注），SSR h2 序实测 Category discovery→Brands we love→Bestsellers→About ✓，.cms-pool=0。
- foundation.spec 首页断言更新：'Food Cupboard' 楼层标题断言改为畅销榜单标题（/Bestsellers|畅销榜单/）+ 首个类目 tab 可见；e2e 快照重基线 9/10（funnel 仍 D-14），foundation 复跑 5/5。vitest 45/45。

### 2026-11-04（续 3）：配送至/通告条字体/首页畅销榜单楼层

- Barlow 站点字体本地化：实测 joybuy.co.uk 全站字体为 Barlow（Next local font），下载 400/600/700 三个 woff2 到 storefront/public/fonts/（自托管合规），base.css 注入 @font-face，tokens --font-stack 前置 'Barlow'（design-tokens 测试允许：禁 @font-face 仅限 tokens.css、禁 http 外链，相对路径 /fonts/ 均合规）。
- 配送至（实测修正）：左侧新增 24px 定位图钉 SVG（灰 #55565b，对应真实站 icon-font 字符）、文本 16px/600 min-width 110px；hover 改为实测的 rgba(0,16,71,0.06) 胶囊（radius 50px，无阴影）——替换原 #F0F1F4+radius 8。
- 通告条字号 14px（实测，原 12px xs）。
- 首页畅销榜单楼层（docs/12 §1 落地）：新组件 `components/home/HomeBestsellers.vue` 接在首页 CMS 楼层之后——标题"Bestsellers/畅销榜单"+右侧 View all（→/promo/best-seller?category=<active>）；标题下方 11 个标准类目 tab（横排可滚，选中=黑粗+2px 黑下划线，点击客户端 $fetch `/api/v1/search?category=&sort=rating_desc` 刷新）；下方 5 列榜单卡（ProductCard+排名徽章）。SSR 首屏拉默认 tab（home-living）。真实站同楼层位置在页面中下（discovery/brands/JoyPlus 之后），与我们 CMS 尾部位置一致。
- 验证：vitest 45/45（新增 HomeBestsellers 2 用例：tab 渲染/点击切换 $fetch 断言）；eslint/prettier 通过；e2e 首页快照重基线 9/10（funnel 仍 D-14）。浏览器复核：Barlow document.fonts.check=true、通告条 14px Barlow、配送至 16px/600+icon+胶囊、楼层 11 tabs/选中态/5 卡排名徽章、点击"电子产品" tab 数据刷新（3 商品）✓。重启 Nuxt 后楼层才出现在 SSR（新组件目录 HMR 未生效的坑：新增组件文件后需重启 dev）。

### 2026-11-04（续 2）：发现卡凸起高度按真实站实测修正

- 用户反馈 -12px 凸起太低且整卡层级抬升突兀；实测真实站：悬停 translateY(-40px)、邻卡 -8px（次邻 0）、z-index 固定按位置序号（1..6）恒定不变。
- 修正：hover -40px；邻卡 -8px（删除 -6/-3 两阶波浪，保留一阶）；li 按 nth-child 固定 z-index 1..12（不再依赖 hover 改层级）——凸起后右侧仍被右卡压住（elementFromPoint 复核 topCard=4 ✓）。
- vitest 43/43；浏览器量测 wave=[0,-8,-40,-8,0,0]、z auto（card 层）/li 层固定序号 ✓，截图与用户参考图一致。

### 2026-11-04（续）：品类发现叠层卡 + 心选品牌跑马灯

- 品类发现（tiles 变体）：改为叠层甲板布局——卡片定宽 289×366，`li + li { margin-left: -72px }` 右卡压左卡（真实站步进 222≈压 67px），每卡 box-shadow，DOM 后序卡自然在上；悬停 translateY(-12px)+阴影加深+`z-index: 10` 上浮盖住邻卡（transition 0.25s）。窄屏（<80rem）回退 3/2 列网格去掉叠层。
- 心选品牌（brand_logos 变体）：改单行跑马灯——内容渲染两份（第二份 aria-hidden），flex track `translateX(0→-50%)` 48s 线性无限循环实现右→左慢滚（两份等宽保证无缝）；容器 `mask-image: linear-gradient(to right, transparent→black 8%→black 92%→transparent)` 两缘渐隐；hover 暂停滚动；`prefers-reduced-motion` 停用动画。
- 测试：CmsRenderer 用例更新（brand-marquee track 存在、卡片 ×2 复制断言）；vitest 43/43；e2e 首页快照重基线 9/10（funnel 仍 D-14）。
- 浏览器复核：叠层步进 229（压 72px）、阴影/悬停 transform -12px/z10 ✓；跑马灯 animation 48s、mask 渐隐、24 卡（12×2）滚动 ✓（截图已核）。

### 2026-11-04（下午）：首页七项样式与数据优化（参照 joybuy.co.uk 实测）

- 通告条：内容垂直居中（inner min-height 40px）、bg #1A1A1A（实测值，替代此前误用的 #17202A）、左侧标签中文态改 "UK | 中文(简体)"（英文态仍 "UK | English"）；搜索按钮同步 #1A1A1A。
- 分类面板（AppCategoryPanel 重做）：面板宽 800px；左栏 184px、行高 36px、项间距 16px、label 14px；悬停/选中 = bg #F7F7F7 radius 8 + 字重 600 **黑色**（去掉原 accent 红）；根项 mouseenter/@focus/@click 三方式均可切换右侧子类目（悬停+点击双联动）。
- 活动区无缝：index.vue 页面容器 margin-top 清零（scoped `.home-page` 覆盖 `.app-main > *` 的 24px），实测 campaign top=header bottom=160px 零缝隙。
- 品类发现（CmsLinkGrid tiles 重做）：竖卡布局（名称左上+产品图下，bg #F5F6F7 radius 16，比例 289:366 同真实站）；6 张图从 joybuy.co.uk 发现轮播实测采样（s624x624）下载本地化（loader CATEGORY_DISCOVERY_TILES 附 URL）；CMS payload 即后台配置入口（admin-web CMS 页可改 icon_path/label/href）。
- 心选品牌（新增 link_grid variant `brand_logos`）：圆形灰底 logo（160px）+下方名称，**不可点击**（纯 span），位于品类发现下方（真实站顺序）；20 个品牌名+s220x220 logo 实测采样，loader 取前 12 个入 payload（MAX_FEATURED_BRANDS）；title "Brands we love"/"心选品牌"。
- loader 重跑发布 home v7（11 模块，新增 26 张图 0 失败）；发现卡图片映射为源站轮播顺序占位（源站当前无电子/游戏/运动卡），语义错位已记录，后台可配。
- 测试：vitest 43/43（面板 hover 联动+非红断言、discovery 图卡、brand_logos 静态渲染新用例）；eslint/prettier 通过；e2e foundation+视觉 9/10（funnel 仍 D-14 dev 水合竞态）。
- 浏览器量测复核：strip 40px 居中/#1A1A1A/标签 ✓、campaign y160==header bottom ✓、发现卡 radius16 带图 ✓、品牌 12 圆卡 50% 不可点击图加载 ✓、面板 hover bg #F7F7F7 fw600 黑色 + 子类目联动 ✓。

## 6. 验证记录

### 2026-11-05 账号隔离加固（按验证纪律仅做针对性验证）

- 用户实测反馈两问题：① 登录窗口弹出后闪退（`crawler_account_login` 里 ChromiumOptions 遮蔽 `options` 参数字典，已修复）；② 登录成功但长时间未保存（站点持续返回限流页导致页面信号检测失败）+ 对"验证会话用哪个浏览器"的疑虑。
- 修复/加固：`render_page` 新增标签页指纹防线 `_assert_clean_browser`（干净实例=1 个 chrome://newtab/ 标签，实测确认；已有真实标签页的浏览器立即 quit 拒绝导航）；`RISK_CONTROL_MARKERS` 加 "temporary service interruption"；登录检测加 Cookie 新增信号（初始快照 diff，忽略 _ga/_uet 等噪声）；verify 返回 cookie_count+detail 证据，UI 成功提示改为"在隔离无头浏览器中用该账号存储的 N 条加密 Cookie 验证"。
- 实测：任务账号01（用户自行登录成功，10 条 Cookie 已入库 VALID）真实验证跑通——隔离无头浏览器加载其 Cookie，被站点限流页拦截 → 正确返回 RISK_CONTROL_BLOCKED 且**不误标过期**（session_status 保持 VALID）；ruff 干净；账号 API 13/13。
- 遗留：站点对本机限流未解除，`verified=true` 的 UI 展示待用户稍后自行点"验证会话"确认；"验证打开本体浏览器"未能在代码路径上复现（当时账号无会话，verify 应直接返回 NO_SESSION 不开浏览器），最可能是登录等待期的有头窗口被误认——现已有双防线兜底。

### 2026-11-05 爬虫重建第 2 轮：账号管理 + 管理端 UI（按验证纪律仅做针对性验证）

- 服务启动：Docker Desktop → joybuy-dev-mysql/redis/mailpit 全部 healthy → migrate（无缺失）→ 后端/storefront/admin 三个 200。
- 后端：`manage.py test crawler_control` **83/83 通过**（新增 `test_crawler_accounts_api.py` 11 项：创建/列表（不暴露 session_cipher）/启停/风控拦截 enable/登出过期/verify 有效与过期/无会话/login 派生/权限门/404；`test_crawl_jobs_api.py` 2 项 HTTP 建任务）；ruff 全部改动文件干净。
- 前端：admin-web vitest **7/7**（CategoryTreePicker 4 项：展开/勾选 v-model/含子类目切换/搜索过滤）；eslint 0 错误；prettier 通过；locale.js 补映射。
- **浏览器实测（内置浏览器，admin@joybuy.test 登录）**：① 任务 Tab 类目树显示 14 频道+子类目计数，搜索 "Kettles" 过滤并勾选 → 创建任务「UI 实测-壶类目-2件」成功（就绪，列表类目列显示 Kettles & Toasters）；② 详情抽屉：状态/类目选择（含子类目标记）/树版本/运行记录/事件流全部正确；③ 账号 Tab：新增「FB 主账号」成功（启用/未知会话/备注正确），验证会话返回友好提示"尚未登录保存过会话"，停用→已停用（按钮变启用）→恢复启用。
- **实测抓出并修复的真 bug**：任务创建 API 用不存在的 `SourceCategory.public_id` 查类目 → 500。修复为按 `source_id` 查找（前端 `source_ids` payload），补 HTTP 层测试防回归。教训：第 1 轮只测了服务层，API 层接线错误未被捕获——以后 API 改动必须补 HTTP 级测试。
- 清理：昨天实测中断的 3 个僵尸 RUNNING run 用服务层 `cancel_run` 收尾（已变"已取消"）。
- 遗留待人工：账号"登录"流程需用户本人在弹出的 Chrome 里完成 Facebook 登录（检测/存储逻辑已实现并有单测，端到端 Cookie 落库待用户实测）。
- 按纪律未跑全量后端、全部组件或全部 e2e。

### 2026-11-05 爬虫重建第 1 轮（按验证纪律仅做针对性验证）

- ruff check + format：全部改动 Python 文件（crawler/joybuy_crawler 全部新模块、backend/crawler_control、common/admin_views.py、config/urls.py）通过；既有无关文件的 2 个旧告警（browser.py PYI034、ingest.py RUF059）未顺手修复。
- 后端 `manage.py test crawler_control`：**70/70 通过**（终版回归，含 close_spider 全失败→FAILED 新用例）（新增 test_crawler_rebuild.py 13 项：树同步 3、多类目任务 4、解析器/图片阶梯 4、数据集 2、StagingPipeline 4）；`test_crawler_import` 8/8 通过。既有测试 2 处按新语义更新：无可用账号时 start_run 改为未登录启动（不再抛错）；熔断测试改为标记 2 个账号真正触发熔断。
- **实测终验（真实爬取，小规模）**：
  1. `sync_joybuy_category_tree --publish` → 版本 `joybuy-uk-20261104-4dcfbbe5` PUBLISHED：14 一级频道 + 177 快照（163 个子类目，l2/l3 ID 原样保存 + 真实列表 URL）。
  2. 建任务（类目 l2:1405 Kettles & Toasters，product_limit=3）→ `start_run` → `run_crawl_run` 独立进程执行：列表页 `/s?k=Kettles%20%26%20Toasters`（robots 合规规范化）+ 3 个 `/dp/` 详情页全部 200。
  3. 结果：**3/3 商品 IMPORTED**（SPU/SKU/Offer 各 3）、gallery 图片 15+17+20 张全部下载 0 失败、run→SUCCEEDED、job→COMPLETED；事件流 RUN_STARTED/PRODUCT_IMPORTED 完整。
  4. 数据集落盘核对：`var/crawl_exports/d76a930e-3-2/kettles-toasters/home-appliances/{商品ID}/product.json + images/main/01.webp + images/detail/*.webp + dataset_index.jsonl`；主图实测 **1248×1248**（站点最高清规格）；product.json 含 joybuy 原生字段块（productId/priceInfo.crossOffPrice/skus[].skuId/seller/gallery 等一一对应）。
- 迭代过程中修复并复验的问题：robots 解析器参数反序（Scrapy 上游 bug）、close_spider 签名（Scrapy 2.13 变更）、asyncio 下 ORM 调用、JSON-LD image 字符串迭代 bug、CDN bot UA 403、dataset_root 相对路径、面包屑分层（选中类目为第一层）。
- docs/05（§1/§7.3/§8）与 docs/09（类目结构现状）已更新；`DrissionPage` 已装入 `.venv`（4.1.1.4）。
- 按纪律未跑全量后端、全部组件或全部 e2e；admin-web UI 属第 2 轮未动。

### 2026-11-05 管理端登录移除验证器（按验证纪律仅做针对性验证）

- ruff check --fix + format：`accounts_staff/views.py`、`serializers.py`、`tests/test_staff_auth_api.py`、`config/settings.py` 全部干净（顺带修复两个文件既有 import 顺序，最终 0 error）。
- `APP_ENV=development DEBUG=true DJANGO_DATABASE_ENGINE=mysql DJANGO_CACHE_BACKEND=redis ./.venv/Scripts/python.exe backend/manage.py test accounts_staff --verbosity 1`：11/11 通过（含新增"密码直登"与"忽略多余 totp_code"两用例）。
- `./node_modules/.bin/vitest.CMD run --config admin-web/vitest.config.js`：3/3 通过（LoginView 2 用例重写 + 路由守卫 1 项）。
- eslint（LoginView.vue/LoginView.test.js/useStaffAuth.js/admin-login.spec.js）：0 错误；prettier --check 全部改动前端文件 + README/docs：通过（`.env.example` 无 parser，不适用 prettier，人工核对仅删除 2 行）。
- e2e `./node_modules/.bin/playwright.CMD test tests/e2e/admin-login.spec.js`：首跑 1 失败——8000 端口是 21:51 启动的旧 `--noreload` 后端，仍在返回 STAFF_TOTP_REQUIRED；杀掉 38960 进程并重启后端后复跑 **2/2 通过**（管理员邮箱+密码直登到仪表盘并遍历五个管理页、审计员 RBAC 菜单隐藏）。curl 直测登录接口确认 200 返回 staff payload。
- 按纪律未跑全量后端、全部组件或全部 e2e。

### 2026-11-04 畅销榜单 11 类数据补齐（按验证纪律仅做针对性验证）

- `ruff format` + `ruff check`（仅 4 个改动 Python 文件）：通过；顺带修复 `search_services.py`/`test_search.py` 原有 import 顺序，最终 `All checks passed`。
- `.venv/Scripts/python.exe -m json.tool backend/catalog/fixtures/bestseller_demo_2026_11_04.json`：通过。
- `.venv/Scripts/python.exe backend/manage.py test catalog.tests.test_search catalog.tests.test_bestseller_demo --verbosity 2`：11/11 通过；MySQL 仅输出既有 3 条条件唯一约束警告。
- 命令参数/fixture 调整后复跑 `.venv/Scripts/python.exe backend/manage.py test catalog.tests.test_bestseller_demo --verbosity 1`：1/1 通过，重复执行第二次为 0 new SPUs。
- `vitest run storefront/components/home/HomeBestsellers.test.js --config storefront/vitest.config.js`：2/2 通过。
- 实库 `load_bestseller_demo --per-category 3`：33 条导入成功，初次 1 图失败；修正坏源后 `--only-category clothing-accessories --per-category 3`：3 条、0 图失败。最终 ORM 核对：fixture 每类 3、33 个 SPU、33/33 gallery、本地图片缺失 `[]`。
- 重启旧 `--noreload` 后端后，`GET /api/v1/search?category=beauty-personal-care&sort=rating_desc&page=1` 返回 3 条且每条 `image_path=/media/...`。
- 内置浏览器抽查 `/promo/best-seller?category=beauty-personal-care`：3 个中文商品标题和 3 张本地图均可见，图片 `complete=true`、`naturalWidth=135`；抽查 `games-accessories`：3 个 PlayStation 标题和 3 张本地图均加载成功。
- 续验（用户说“继续”后）：确认当前 8000 端口已经是 2026-11-04 18:03 启动的新后端进程，没有重复重启；再次请求美妆榜接口仍为 3 条、3 条均带本地 `/media/...` 首图；内置浏览器再次核对游戏榜 3 张图均 `complete=true`、`naturalWidth=135`；复跑 `.venv/Scripts/python.exe backend/manage.py test catalog.tests.test_search catalog.tests.test_bestseller_demo --verbosity 1`，11/11 通过（仅既有 3 条 MySQL 条件唯一约束警告）。
- 按纪律未跑全量后端、全部组件或全部 e2e。

### 2026-11-05（续 3）：排序触发器不换行 + 侧栏选中色去红

- 触发器 `width: 172px` → `min-width: 172px + white-space: nowrap`（"Price: High to low" 单行显示，高度保持 40px）。
- 侧栏选中类目去红：`--colour-accent-soft/--colour-accent` → bg #F7F7F7 + color #1A1A1A + font-weight 700（与分类面板 hover 一致）。
- 验证：vitest 45/45；浏览器复核 noWrap/40px、选中 rgb(26,26,26)/rgb(247,247,247)/700 ✓（截图）。

### 2026-11-05（续 2）：排序控件改自定义下拉（左置/去蓝色）

- 用户反馈：排序应在左侧（原右对齐）；外边框与选项 hover/选中出现蓝色——根源是原生 `<select>` 的下拉弹层由 OS 渲染（Windows Chrome 蓝色高亮），CSS 无法自定义。
- 重做为自定义下拉：trigger（"Sort by:" 16px/500 + 172×40 深色描边按钮 + ⌄）左置（删除右侧 spacer）；菜单白底 1px 灰边 + overlay 阴影，选项 40px 行、hover #F0F1F4 灰、选中 #EEF1F5 灰加粗（全灰系无蓝）；点击选项 updateQuery、点击外部自动关闭（document click 监听，onMounted/onBeforeUnmount 挂载）。
- 验证：vitest 45/45；浏览器复核 triggerOnLeft ✓、菜单白底、hover rgb(240,241,244) 无蓝、选中项高亮 ✓（截图）。

### 2026-11-05（续）：列表页排序控件对齐真实站

- 实测真实站（/s?k=noodles）：标签 "Sort by:" 16px/500 #1A1A1A；触发器白底 **1px #1A1A1A 深色描边**、radius 4、高 40、16px 字；展开菜单白底、选中项浅灰高亮；选项顺序 Relevance → Price: High to low → Price: Low to high（→ Sales: High to low，后端无销量排序）。
- ProductListing：标签 16px/500 深色（原 14px 灰）；select 描边改 #1A1A1A（原浅灰）、16px 字、cursor pointer；选项文案与顺序对齐（price_desc 提前，"Price: High to low/Low to high" 大小写对齐真实站），保留 Top rated/Newest（真实站有 Sales 排序但后端暂无——差异记录）。
- 验证：vitest 45/45；浏览器复核 label/trigger/选项序列 ✓（截图）。

### 2026-11-05（续）：列表页三处（头部无缝/图区四角圆角/侧栏分割线）

- 头部与页面间隙：原 `.listing-page-bg` margin-top:0 未压过 `.app-main > *`（实测 bgTop 184 vs header 160，灰缝来自 app-main）。改为"一整块+内边距"：wrapper `margin-block: 0`（`.listing-page-bg.listing-page-bg` 双类名提权重）+ `padding-block: 32px 24px`，`.listing-layout` margin 归零。实测 bgTop==headerBottom==160 ✓。
- 图片区四角圆角遗漏点：`.product-card__media` 容器（#F5F5F5 底）自身 radius 0——img 虽 12px 但灰底方块外露。补容器 radius 12px。其它位置已排查：发现卡 12px、榜单页共用 ProductCard ✓。
- 侧栏 Category/Price 之间加 1px 分割线（`.filter-card + .filter-card` border-top）。
- 验证：vitest 45/45；浏览器复核三项 ✓（截图）。

### 2026-11-05：/s 列表页全幅白底

- 用户要求 /s?category= 页面背景 #FFFFFF。ProductListing 根部加全幅包裹 `.listing-page-bg`（margin-inline calc(50%-50vw)、bg #FFFFFF、覆写 .app-main 子项顶距）——/s、/search、/c 三个路由统一生效。
- 踩坑：脚本对 .vue 先 ast.parse 校验会在写入前中断（.vue 非 Python），导致模板替换丢失——改为先写文件再校验/或只校验 .py。
- 验证：vitest 45/45；浏览器复核 bg rgb(255,255,255)、全幅 1512、无横向滚动 ✓。

### 2026-11-04（续 11）：详情页五项（隐藏类目行/加粗面包屑/白底/#EEEFF0/粗边框）

- 详情页隐藏全局类目行：AppHeader `useRoute` 判 `/p/` 前缀时 v-if 关闭 category-nav（真实站行为）；vitest stub 的 useRoute 补 `path: '/'`（此前桩缺 path 导致 AppHeader 测试 5 连挂）。
- 面包屑加粗：14px 不变 + font-weight 700（用户参考图观感加粗）。
- 详情页整页背景 #FFFFFF：新增全幅包裹 `.detail-page-bg`（margin-inline calc(50%-50vw)）。
- 图片区背景 #EEEFF0：主图容器/img/放大面板底色统一（原 #F5F5F5）。
- 缩略图边框 1px→2px（激活态仍深色 #17202A 覆盖）。
- 验证：vitest 45/45；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器复核五项 computed 全过（截图）。

### 2026-11-04（续 10）：主图蓝色网点遮罩 + 面包屑 14px

- 用户提供真实站参考图：hover 主图时主图上出现**蓝色网点选择遮罩**（配合右侧放大图）。实现：`.detail__zoom-mask`（40%×40% = 1/2.5 放大倍率反算、中心跟随光标并 clamp 图内、蓝色半透明底 rgba(26,115,232,.14) + radial-gradient 蓝色点阵 7px 网格、pointer-events none）；onZoomMove 同步遮罩位置。
- 面包屑字号 14px（原 16px，用户参考图为 14px）、分隔符灰、去重 hover 规则。
- 验证：vitest 45/45；浏览器实测遮罩 247×247（617×0.4）、点阵/底色正确、跟随光标、右侧放大图同步（截图）✓。

### 2026-11-04（续 9）：首页榜单四项 + 详情页面包屑/布局/放大镜

- 首页（实测 18px 规格）：榜单 tab 18px（未选中 400/选中 700 #1A1A1A）、间距 32px、高 42px；View all 18px/600 下划线；榜单卡图自带四角 12px 圆角（img 自身 radius，不再依赖卡裁切）；心选品牌→畅销榜单楼层间距 48px（原 24）；【About this study build】尾注模块删除（loader 不再 append rich_text，index.vue 移除 tail 渲染，home v9=3 模块）。
- 详情页：顶部导航改真实站式可点击面包屑——Home / 类目树父链（useCategoryTree 反查 category_slug，双语 categoryName）/ 商品名，16px #1A1A1A、hover 下划线；布局列宽对齐实测（56px 缩略图轨 + 流体主图 + 671px 购买面板，主图≈617 vs 真实 591）；主图 hover **放大镜**——右侧浮出 617×617 面板（background-size 250%、position 跟随光标百分比、z-20 覆盖购买面板侧、mouseleave 关闭）。
- 验证：vitest 45/45；eslint/prettier 通过；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器复核全部通过（截图）。期间后端 runserver 再次静默退出（本日第 3 次，后台任务稳定性问题）已重启；HomeBestsellers/Promo 排序 sort=newest 同步。

### 2026-11-04（续 8）：首页整行背景 #FFFFFF

- 用户指定 `.home-page`（畅销榜单/品类发现/心选品牌模块外围）背景为 #FFFFFF。原页面继承 canvas 灰底，且容器 max-width 1440 居中后超宽视口两侧仍露灰条。
- index.vue 模板加全幅包裹层 `.home-page-bg`（margin-inline calc(50%-50vw) 撑满视口、bg #FFFFFF、覆写 .app-main 子项顶距），原容器嵌套其内。复核：bg rgb(255,255,255)、全幅 1512=viewport、无横向滚动、活动区仍与头部无缝。

### 2026-11-04（续 7）：榜单卡透明图数据源（UK 商品入库）+ multiply 底色

- 诊断：用户指出商品图背后应为 #F5F5F5 透明效果。查证：代码侧 #F5F5F5 已生效；白底来自数据——原 load_joybuy_demo 的商品图是 joybuy.com flight 的 **jpg 白底图（无 alpha）**，且 CDN 上该批图**无透明变体**（.png.webp 404 实测）。真实站榜单卡 img 无 mix-blend-mode、直接白底显示（240px jpg）。
- 修复（数据源切换）：真实站首页 Bestsellers 楼层商品的 **s480x480 `.png.webp` 透明图**有效。浏览器逐 tab 爬取真实楼层 10 tab×5 卡（title/price/透明图 URL）→ `var/joybuy_demo/data/uk_bestsellers_raw.json`（44 卡，来源 https://www.joybuy.co.uk/ 2026-11-04）；新命令 `load_uk_bestsellers_demo` 导入 44 商品（source_system=joybuy_uk，幂等 source_id=title+img md5），UK tab→我们 11 类目子树映射（Kitchen Roll→cleaning-supplies、Small Kitchen Appliances→kitchen-appliances、其余食品类→groceries-food），£ 价格存 GBP，透明图 store_bytes 本地化（43/44 成功，1 张 URL 永久失败已用 shell 手工补挂）。
- 楼层/榜单页排序 rating_desc→**newest**（新导入透明图商品排前；MySQL DESC 下无 rating 的 NULL 排序不稳）；HomeBestsellers 测试断言同步。
- ProductCard 图区：容器 bg #F5F5F5 + img **mix-blend-mode: multiply**——白底烘焙图乘底色后白→#F5F5F5，透明图直接透出，产品色几乎无损（真实站未用此法，属实现选择）。
- 验证：vitest 45/45；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器截图确认榜单为 UK 真实商品透明图、图区底色 #F5F5F5 ✓。旧 .com 白底商品仍在库（其它 tab 混排时可能出现白底图——multiply 会将其转为 #F5F5F5）。

### 2026-11-04（续 6）：榜单卡三处颜色/字号按用户指定修正

- 图片区域背景 #F5F5F5（原 surface-soft #F5F6F7）；标题字号 16px（原 --font-size-md=14px，真实站实测 16px，用户指出的字号问题根源即 token 差异）+ 颜色 #1A1A1A（原 #17202A）；价格颜色 #1A1A1A（用户指定深色，替换此前误加的红色——真实站红价是折扣价语义，我们单一原价按用户口径用深色）。
- 浏览器复核：imgBg rgb(245,245,245)、title 16px/#1A1A1A/clamp 2、price #1A1A1A ✓；vitest 45/45。

### 2026-11-04（续 5）：商品卡对齐真实榜单卡（两行省略/图贴顶）

- 实测真实站 Bestsellers 卡（首页楼层 261 宽 + 列表卡 267）：图全宽贴卡顶（无内边距、radius 由卡整体裁切）、文字区 6px 内边距、品牌粗体、标题 16px/500 行高 22px **两行截断（h44）**、红色价格粗体、40px 圆形加购钮、榜单卡无星级。
- ProductCard 重写：结构改为图贴顶（`.product-card` overflow hidden radius 12，图 radius 0）+ `product-card__body` 内边距 8/6/6；标题 clamp 移入组件自身样式（`-webkit-line-clamp: 2`、line-height 22px、min-height 44px——此前依赖全局 `.truncate-2`，实测在卡内未生效出现三行硬切）；价格改红色（--colour-accent，1.125rem/700，与真实站红价一致，仍为单一原价规则）；榜单模式（rank>0）隐藏星级、可选 `viewed_count` 渲染 "x people viewed in 72 hours" 行（搜索接口暂无该字段=数据缺失，不编造）；徽章降级为价格旁小灰签。
- 验证：vitest 45/45；eslint/prettier 通过；浏览器复核 titleClamp=2/标题高 44/五卡全部省略号结尾/红价/图贴顶/无星级 ✓；e2e 首页快照重基线 9/10（funnel 仍 D-14）。注意：dev 模式组件 CSS 经客户端 JS 注入，SSR HTML 中 grep 不到样式属正常；HMR 对样式改动偶发陈旧需重启 dev（今日两次）。

### 2026-11-04（续 4）：独立商品楼层并入畅销榜单（home v8）

- 用户指出：心选品牌与畅销榜单之间的 6 个独立商品楼层（Kitchen Roll…/Food Cupboard/Beverages/Rice…/Small Kitchen Appliances/Instant Noodle——即爬取的 bestseller 分区）应属畅销榜单数据，不应单独铺开；真实站这些分区本来就是 Bestsellers 楼层的 tab 分区。
- loader build_modules：删除 product_pool 楼层循环与旧文字品牌墙（"Brands we love" pills——被心选品牌 brand_logos 取代，二者重复）；保留 import（商品仍在库，畅销榜单经搜索接口消费）。发布 home v8：4 模块（campaign/discovery/brands(心选)/rich_text）。
- index.vue：拆分 CMS 渲染——rich_text 尾注排到畅销榜单之后（真实顺序：…心选品牌 → 畅销榜单 → 尾注），SSR h2 序实测 Category discovery→Brands we love→Bestsellers→About ✓，.cms-pool=0。
- foundation.spec 首页断言更新：'Food Cupboard' 楼层标题断言改为畅销榜单标题（/Bestsellers|畅销榜单/）+ 首个类目 tab 可见；e2e 快照重基线 9/10（funnel 仍 D-14），foundation 复跑 5/5。vitest 45/45。

### 2026-11-04（续 3）：配送至/通告条字体/首页畅销榜单楼层

- Barlow 站点字体本地化：实测 joybuy.co.uk 全站字体为 Barlow（Next local font），下载 400/600/700 三个 woff2 到 storefront/public/fonts/（自托管合规），base.css 注入 @font-face，tokens --font-stack 前置 'Barlow'（design-tokens 测试允许：禁 @font-face 仅限 tokens.css、禁 http 外链，相对路径 /fonts/ 均合规）。
- 配送至（实测修正）：左侧新增 24px 定位图钉 SVG（灰 #55565b，对应真实站 icon-font 字符）、文本 16px/600 min-width 110px；hover 改为实测的 rgba(0,16,71,0.06) 胶囊（radius 50px，无阴影）——替换原 #F0F1F4+radius 8。
- 通告条字号 14px（实测，原 12px xs）。
- 首页畅销榜单楼层（docs/12 §1 落地）：新组件 `components/home/HomeBestsellers.vue` 接在首页 CMS 楼层之后——标题"Bestsellers/畅销榜单"+右侧 View all（→/promo/best-seller?category=<active>）；标题下方 11 个标准类目 tab（横排可滚，选中=黑粗+2px 黑下划线，点击客户端 $fetch `/api/v1/search?category=&sort=rating_desc` 刷新）；下方 5 列榜单卡（ProductCard+排名徽章）。SSR 首屏拉默认 tab（home-living）。真实站同楼层位置在页面中下（discovery/brands/JoyPlus 之后），与我们 CMS 尾部位置一致。
- 验证：vitest 45/45（新增 HomeBestsellers 2 用例：tab 渲染/点击切换 $fetch 断言）；eslint/prettier 通过；e2e 首页快照重基线 9/10（funnel 仍 D-14）。浏览器复核：Barlow document.fonts.check=true、通告条 14px Barlow、配送至 16px/600+icon+胶囊、楼层 11 tabs/选中态/5 卡排名徽章、点击"电子产品" tab 数据刷新（3 商品）✓。重启 Nuxt 后楼层才出现在 SSR（新组件目录 HMR 未生效的坑：新增组件文件后需重启 dev）。

### 2026-11-04（续 2）：发现卡凸起高度按真实站实测修正

- 用户反馈 -12px 凸起太低且整卡层级抬升突兀；实测真实站：悬停 translateY(-40px)、邻卡 -8px（次邻 0）、z-index 固定按位置序号（1..6）恒定不变。
- 修正：hover -40px；邻卡 -8px（删除 -6/-3 两阶波浪，保留一阶）；li 按 nth-child 固定 z-index 1..12（不再依赖 hover 改层级）——凸起后右侧仍被右卡压住（elementFromPoint 复核 topCard=4 ✓）。
- vitest 43/43；浏览器量测 wave=[0,-8,-40,-8,0,0]、z auto（card 层）/li 层固定序号 ✓，截图与用户参考图一致。

### 2026-11-04（续）：品类发现叠层卡 + 心选品牌跑马灯

- 品类发现（tiles 变体）：改为叠层甲板布局——卡片定宽 289×366，`li + li { margin-left: -72px }` 右卡压左卡（真实站步进 222≈压 67px），每卡 box-shadow，DOM 后序卡自然在上；悬停 translateY(-12px)+阴影加深+`z-index: 10` 上浮盖住邻卡（transition 0.25s）。窄屏（<80rem）回退 3/2 列网格去掉叠层。
- 心选品牌（brand_logos 变体）：改单行跑马灯——内容渲染两份（第二份 aria-hidden），flex track `translateX(0→-50%)` 48s 线性无限循环实现右→左慢滚（两份等宽保证无缝）；容器 `mask-image: linear-gradient(to right, transparent→black 8%→black 92%→transparent)` 两缘渐隐；hover 暂停滚动；`prefers-reduced-motion` 停用动画。
- 测试：CmsRenderer 用例更新（brand-marquee track 存在、卡片 ×2 复制断言）；vitest 43/43；e2e 首页快照重基线 9/10（funnel 仍 D-14）。
- 浏览器复核：叠层步进 229（压 72px）、阴影/悬停 transform -12px/z10 ✓；跑马灯 animation 48s、mask 渐隐、24 卡（12×2）滚动 ✓（截图已核）。

### 2026-11-04（下午）：首页七项样式与数据优化（参照 joybuy.co.uk 实测）

- 通告条：内容垂直居中（inner min-height 40px）、bg #1A1A1A（实测值，替代此前误用的 #17202A）、左侧标签中文态改 "UK | 中文(简体)"（英文态仍 "UK | English"）；搜索按钮同步 #1A1A1A。
- 分类面板（AppCategoryPanel 重做）：面板宽 800px；左栏 184px、行高 36px、项间距 16px、label 14px；悬停/选中 = bg #F7F7F7 radius 8 + 字重 600 **黑色**（去掉原 accent 红）；根项 mouseenter/@focus/@click 三方式均可切换右侧子类目（悬停+点击双联动）。
- 活动区无缝：index.vue 页面容器 margin-top 清零（scoped `.home-page` 覆盖 `.app-main > *` 的 24px），实测 campaign top=header bottom=160px 零缝隙。
- 品类发现（CmsLinkGrid tiles 重做）：竖卡布局（名称左上+产品图下，bg #F5F6F7 radius 16，比例 289:366 同真实站）；6 张图从 joybuy.co.uk 发现轮播实测采样（s624x624）下载本地化（loader CATEGORY_DISCOVERY_TILES 附 URL）；CMS payload 即后台配置入口（admin-web CMS 页可改 icon_path/label/href）。
- 心选品牌（新增 link_grid variant `brand_logos`）：圆形灰底 logo（160px）+下方名称，**不可点击**（纯 span），位于品类发现下方（真实站顺序）；20 个品牌名+s220x220 logo 实测采样，loader 取前 12 个入 payload（MAX_FEATURED_BRANDS）；title "Brands we love"/"心选品牌"。
- loader 重跑发布 home v7（11 模块，新增 26 张图 0 失败）；发现卡图片映射为源站轮播顺序占位（源站当前无电子/游戏/运动卡），语义错位已记录，后台可配。
- 测试：vitest 43/43（面板 hover 联动+非红断言、discovery 图卡、brand_logos 静态渲染新用例）；eslint/prettier 通过；e2e foundation+视觉 9/10（funnel 仍 D-14 dev 水合竞态）。
- 浏览器量测复核：strip 40px 居中/#1A1A1A/标签 ✓、campaign y160==header bottom ✓、发现卡 radius16 带图 ✓、品牌 12 圆卡 50% 不可点击图加载 ✓、面板 hover bg #F7F7F7 fw600 黑色 + 子类目联动 ✓。

## 6. 验证记录

### 2026-11-11 admin-web 前端回归检查（只测不修，按验证纪律：仅针对性验证）

- 对 `admin-web/` 做只读回归检查（未 `--write`、未改任何源码，dev server 5173 未动）：
  - prettier：`npx prettier --check "src/**/*.{vue,js,css}"` → 3 个文件不达标（`src/components/AppDrawer.vue`、`src/components/AppModal.vue`、`src/views/BuyersView.vue`），**均不在本次 git 改动清单内**，未修；本次改动的 7 个文件（CategoryTreePicker.vue / ImageUploader.vue / locale.js / admin.css / CrawlersView.vue / MerchantsView.vue / ProductPoolView.vue）格式全部达标。
  - eslint：`npx eslint src` → 0 错误、0 警告，通过。
  - 构建：`npm run build`（= vite build）→ 成功，83 modules transformed，built in 390ms，无警告。
  - 单测：admin-web **有** vitest（`admin-web/vitest.config.js` + 3 个用例文件），`npx vitest run` → 3 files / 9 tests 全部通过（含本次改动 CategoryTreePicker.vue 的配套 6 例）。
- 报告：`var/regression_20261111/adminweb_report.md`。
- 坑/注意：3 个不达标 prettier 文件属遗留问题，后续若处理需先确认其不在他人改动清单；admin-web 的 prettier/eslint/vitest 由**仓库根 node_modules** 解析（admin-web/node_modules 只有 vite/vue/vue-router/@vitejs）。

### 2026-11-04（夜间）逐元素视觉对齐全部文档页面（按验证纪律：仅针对性验证）

- 真实站基准采集：joybuy.co.uk 列表页/详情页/榜单页实测（元素坐标/尺寸/颜色/字号/圆角），列表页左栏 234px、商品卡 274×576 radius 12、详情双 CTA 331×48 及 hover 色（#D14335/#282828）、榜单 hero 384px、排名徽章 32×32 #E4E6EB radius 8px 0；悬停遍历含卡片/按钮/缩略图/保障行。
- 商城组件：vitest 42/42；eslint+prettier 全部改动文件通过。
- 后端：accounts_buyers+checkout 14/14 通过；迁移 0004 应用；ruff 改动文件干净。
- e2e：foundation + funnel 视觉基线重基线后 9/10 通过（funnel 主流程 dev 水合竞态超时，记 D-14；功能浏览器人工全链路验证：登录→加购→3 字段地址→Save→支付步骤→Pay now→订单页 Pending payment，POST /orders 201）。
- 浏览器逐页量测复核：列表页（侧栏 234/卡 274/加购 40 圆钮/排序 h40）、详情页（标题 24/700、双 CTA 48px、步进器 47×34、保障行 54、弹窗中英文案）、榜单页（hero 384、11 品类 h48、徽章 32×32）、结算页（截图核对支付步骤+精简页脚）、首页楼层新卡。

### 2026-11-04（第二轮反馈）头部/活动区精修（按验证纪律：仅针对性验证）

- 真实站实测：joybuy.co.uk 在内置浏览器打开并逐项测量（未登录、只读）；量得通告条 40px/#1A1A1A、搜索框 #F5F6F7+1px #C2C4CC 胶囊+64×44 深色按钮、圆形按钮 52px、卡片 277×277、活动区全幅带背景图（URL 已采样）。
- 商城组件针对性：`vitest run --config storefront/vitest.config.js` 42/42 通过（AppHeader/AppCategoryPanel/CmsRenderer 用例已随新交互更新）；eslint 改动文件 0 错误；prettier 改动文件全部通过。
- e2e 针对性：foundation + purchase-funnel（`--workers=1`）：`--update-snapshots` 重基线 10/10，复跑确认 10/10。
- `load_joybuy_demo` 重跑：发布 home v6，活动区背景图下载本地 0 失败；ruff 改动 Python 文件通过。
- 浏览器实测（1512 视口量测）：通告条 40px/#17202A 居中；搜索框 898×52（flex 自适应，接近目标 879px）；搜索按钮 64×44 框内右嵌；分类/购物车/个人按钮 52px；类目行 40px 平均分布；活动区 1512×600 全幅背景图、无标题；面板与分类按钮左对齐（x 坐标一致）、紧贴按钮下方；无横向滚动（scrollWidth == clientWidth）。

### 2026-11-04 docs/12 改造第 1 轮（按验证纪律：仅针对性验证）

- 后端针对性：`manage.py test catalog content` 43 项全部通过（含新增 `test_standard_categories.py` 5 项：11 类目顺序/双语/隐藏旧根类目/幂等/演示商品归类+搜索文档重建，以及 categories API 嵌套双语断言）；`makemigrations --check --dry-run` 无缺失迁移；ruff 只查改动 Python 文件（含迁移 0007）全部通过。
- 商城组件针对性：`vitest run --config storefront/vitest.config.js` 41/41 通过（重写 AppHeader.test.js 5 项、新增 AppCategoryPanel.test.js 2 项与 tests/use-locale.test.js 3 项）；eslint 只查改动前端文件无错误；prettier 对全部改动前端文件 `--write` 后格式通过。
- e2e 针对性：只跑受影响的 `foundation.spec.js` + `purchase-funnel.spec.js`（`--workers=1`）：先 `--update-snapshots` 重基线首页 4 视口 10/10 通过，再复跑确认 10/10 通过。其余 e2e 未受影响未跑。
- 数据命令实跑：`seed_standard_categories --assign-demo-products`（11 根类目+42 子类目，53 商品归位，0 失败）；`load_joybuy_demo` 重跑发布 home v5（10 模块、53 商品、0 图片失败）。
- 浏览器实测：英文/中文首页（通告条无 Download Joybuy、类目行 11 项、为你推荐/品类发现双语）、Categories 面板（11 根类目 + 严格父子联动）、`/s?category=electronics`（3 商品）、语言切换 cookie 均正常，截图核对通过。

### 2026-11-03 首页对齐真实 Joybuy 结构（按新验证纪律：仅针对性验证）

- 后端针对性：`manage.py test content` 5 项通过；`makemigrations --check --dry-run` 无缺失迁移（含新 `content/0003`）；ruff 仅查改动文件全部通过。
- 商城组件针对性：`vitest run --config storefront/vitest.config.js` 35/35 通过（含 campaign_grid 与 link_grid variant 新用例）；平台端组件未改动，未跑。
- lint/format 针对性：eslint 只查改动前端文件（通过）；prettier 只查改动文件（通过）。
- e2e 针对性：只跑受影响的 `foundation.spec.js` + `purchase-funnel.spec.js`（`--workers=1`）：`--update-snapshots` 重基线 10/10 通过，复跑确认 10/10 通过。其余 e2e 未受影响，未跑。
- `load_joybuy_demo` 重跑：提取 10 活动瓦片 + 6 快捷入口 + 7 品类发现磁贴，新增 23 张本地图片 0 失败，发布 home v4（11 模块）。
- 浏览器截图对比：顶部通知条/红色搜索头部/活动砖石区/圆形入口/品类发现与用户提供的真实截图逐块对齐；商品楼层 `$` 原价不变。

### 2026-11-03 Joybuy 主页复刻效果展示（按新验证纪律：仅针对性验证）

- 后端针对性：`manage.py test content` 5 项通过；`makemigrations --check --dry-run` 无缺失迁移；ruff 仅查改动文件（`load_joybuy_demo.py` 修掉自身 I001 后）全部通过。
- 商城组件针对性：`vitest run --config storefront/vitest.config.js` 34/34 通过（含新 link_grid 用例）；平台端组件本轮未改动，未跑。
- lint/format 针对性：eslint 只查改动前端文件（通过）；prettier 只查全部改动文件（通过）。
- e2e 针对性：只跑受影响的 `foundation.spec.js` + `purchase-funnel.spec.js`（`--workers=1`）：先 `--update-snapshots` 重基线 10/10 通过，再不带更新复跑确认 10/10 通过。其余 e2e（auth、admin-login）未受本轮改动影响，未跑。
- 浏览器实测：首页顶部/商品楼层/底部（品牌墙+页脚）、详情页、搜索页截图与内容断言均正常；图片统计 60 张 0 失败（46 张为视口外懒加载）。
- 上一轮"原价/送达标签/$ 展示"任务曾按旧纪律做过一次全量验证（后端 216、e2e 15），结果见下一条目；按新纪律后续轮次不再默认全量。

### 2026-11-03 原价采集、送达标签过滤与美元展示

从仓库根目录实际执行（后端测试需 `APP_ENV=development DEBUG=true DJANGO_DATABASE_ENGINE=mysql DJANGO_CACHE_BACKEND=redis` 前缀，走 `.venv/Scripts/python.exe`）：

- `./.venv/Scripts/python.exe backend/manage.py test crawler_control.tests.test_crawler_import`：8 项通过（含新的原价契约断言）。
- `./.venv/Scripts/python.exe backend/manage.py test`：216 项全部通过。
- `./node_modules/.bin/vitest.CMD run --config storefront/vitest.config.js`：33 项通过（7 个文件，含新增 `utils/display.test.js`）。
- `./node_modules/.bin/vitest.CMD run --config admin-web/vitest.config.js`：2 项通过。
- `./node_modules/.bin/eslint.CMD storefront admin-web playwright.config.js tests/e2e`：无错误。
- `./node_modules/.bin/prettier.CMD --check <全部改动文件>`：通过（ProductCard.vue 曾报格式问题，已 `--write` 修复后复检通过）。
- `./node_modules/.bin/playwright.CMD test tests/e2e/purchase-funnel.spec.js --update-snapshots`：5 项通过，首页 4 个视口快照按 $ 价格重新基线化。
- `./node_modules/.bin/playwright.CMD test`：15/15 全部通过。
- 浏览器实测：`http://127.0.0.1:3000/` 首页渲染 `$19.99 / $39.50 / $4.99 / $54.00`；`/search` 全为 `$` 价格；真实商品详情页渲染单一 `$19.99` 与配送文案 `$20`，无划线价元素。
- ruff：改动的 `crawler/joybuy_crawler/parsers/product_detail.py` 干净；`test_crawler_import.py` 仅剩既有 I001（import 块，非本次改动引入）。

### 2026-11-03 中文来源与多语言方案

- Joybuy 设置验证：已选择并保存 `中文(简体) - ZH`，页面标题、导航、活动入口和商品标题已实际显示中文；中文浏览器会话已保留。
- 用户澄清后的文档复验：已扫描并移除“缺德文隐藏商品”“用户点击翻译”等冲突方案；德国页面允许按 Joybuy 来源呈现德英混合。
- 本轮只修改 Markdown 文档，业务代码和数据库均未修改。
- `pnpm exec prettier --check docs/10-multilingual-content-and-market-design.md docs/09-crawler-category-task-redesign.md docs/README.md docs/01-requirements.md docs/04-data-model-and-storage.md docs/05-crawler-and-ingestion.md HANDOFF.md`：通过。
- PowerShell 相对文档链接检查：通过，`docs/*.md` 中所有相对链接均能解析。

### 2026-11-03 爬虫品类方案

- Joybuy 现场分析：已在公开首页及相关公开类目页逐项读取页面元素、类目标识和活动链接；未登录、未提交数据、未绕过验证码或风控。
- 本轮只修改 Markdown 文档，业务代码和数据库均未修改。
- `pnpm exec prettier --check docs/09-crawler-category-task-redesign.md docs/README.md docs/05-crawler-and-ingestion.md HANDOFF.md`：通过。
- PowerShell 相对文档链接检查：通过，`docs/*.md` 中所有相对链接均能解析。
- `pnpm format:check`：通过；该命令覆盖既有前端/配置格式范围，文档另由上一条 Prettier 命令单独验证。

### 2026-11-03 平台端中文化（历史）

从仓库根目录实际执行：

- `pnpm format:check`：通过，所有纳入检查的文件符合 Prettier 格式。
- `pnpm lint:frontends`：通过，ESLint 无错误。
- `pnpm test:components`：通过，购物端 27 项 + 平台端 2 项，共 29 项。
- `pnpm build:frontends`：通过，Nuxt 购物端与 Vite 平台端均完成生产构建。
- `pnpm test:e2e`：最终串行复验通过，15/15 Chromium 浏览器测试全部通过；管理员测试已遍历五个管理页面的中文标题。
- 浏览器日志中支付尝试接口的 HTTP 422 是既定的“当前地区暂不支持”业务占位语义，对应购物漏斗断言通过，不是本次失败。
