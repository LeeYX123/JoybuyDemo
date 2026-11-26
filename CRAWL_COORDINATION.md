# 频道卡落地页采集协同文档（夜批 2026-11-27）

> **本文件是建任务方（WorkBuddy/Moss）与爬取执行方（另一个 agent）的双向沟通板。**
> 双方都只 append 自己的段落；请求对方做的事写进「请求区」，对方完成后打勾并注明时间。
> 机器可读状态：`var/home_modules_20261125/overnight/crawl_state.json`（执行方维护）。
> 任务清单：`var/home_modules_20261125/overnight/job_list.json`（31 个任务，建任务方维护）。

## 一、背景与分工

首批 3 页（4VQ7 / 41xQ / 254vg）已上线。剩余 **31 个落地页**（28 个活动页 + 3 个店铺页）需要采集入库：

- **建任务方（Moss）**：已在库里创建 **31 个 PAGE_SET 任务（全部 READY，job#388~418）**，并预分配账号。爬取完成后负责：抓页面标题/标题配色 → 建页与快照选品 → 上架新商品 → 绑定频道卡 → 验收出报告。
- **执行方（另一个 agent）**：只负责**跑爬取队列**（含失败重试、换账号），跑完更新状态与进度。

## 二、执行方启动说明（一条命令，任务已建好，**无需再建任务**）

**31 个任务已全部创建（job#388~418，状态 READY，账号已预分配），直接启动队列即可：**

```bash
cd /e/code/AgentProject/Joybuy
.venv/Scripts/python.exe var/home_modules_20261125/overnight/run_crawl_queue.py
```

行为（脚本自带，无需人工干预）：

- 最多 **3 个任务并行**，每个任务预分配的账号见 `job_list.json`；
- `FAILED` / 单任务超 30 分钟 → **自动换账号重试**（最多 3 次尝试）；
- 执行器是 DETACHED 子进程，日志在 `var/logs/crawl_runs/<run_public_id>.log`；
- 全部到终态（SUCCEEDED / FAILED_FINAL）后自动退出，总时长上限 6 小时。

> 万一发现 job_list.json 里的任务在库里缺失（理论上不会），幂等重建命令：
> `.venv/Scripts/python.exe var/home_modules_20261125/overnight/create_jobs.py`
> （已存在的任务不会被改动，只补缺。）

## 三、给执行方的硬性要求（必读）

1. **保持执行器进程存活直到全部到终态**（或 6 小时上限）。中途退出请在本文件「请求区」说明已跑完哪些。
2. **不要改动任何业务数据**：不碰 `ActivityPage` / `ActivitySectionProduct` / `home_campaign_card` / 商品状态 / 搜索文档——建页选品是建任务方的事。
3. **不要新增/修改采集任务配置**（product_limit、账号分配已定）；发现配置问题写在「请求区」，不要自行改库。
4. 遇到 `CONNECTIVITY_PREFLIGHT_FAILED`（SSL EOF / 网络不可达）：脚本会自动重试；**连续 3 个任务都因网络失败** → 停止队列，在「请求区」写明，等待网络恢复。
5. 遇到 `RISK_CONTROL_FALLBACK` 大量出现（单任务 > 10 次）：跳过该任务（FAILED_FINAL），在「请求区」注明账号组，让建任务方决定是否换组。
6. **进度回报**：脚本自动追加到下方「执行进度」；如果脚本异常中断，请手动把「已 SUCCEEDED 的 job 清单」补进该段。
7. 全部完成后（31/31 到终态）在「请求区」@建任务方：「采集全部完成，可以开始建页」。

## 四、完成判定

- 单任务完成 = `crawl_run.status == 'SUCCEEDED'` 且 `CrawlPageManifest` 已生成（查询方式：`python manage.py shell -c "from crawler_control.models import CrawlPageManifest; print(CrawlPageManifest.objects.count())"`）；
- 缺件（LISTING_SHORTFALL）与 `IMPORT_SOURCE_CONFLICT` 是**正常现象**，不用处理——建任务方在选品阶段会用关键词补位；
- 白名单缺件 > 每层 5 件的页面会在最终报告里列出，不需要执行方重爬。

## 五、建任务方的计划（执行方可据此判断时机）

1. 执行方跑队列期间：建任务方**轮询 `crawl_state.json`**，每有 5 个页面 SUCCEEDED 就先做标题/配色探测（不碰爬取）。
2. 全部（或 ≥25 个）SUCCEEDED 后：统一建页选品 + 上架 + 绑卡 + 验收，产出 `overnight/overnight_report.md`。
3. 报告完成后在本文件「请求区」回复「建页完成」，执行方可下班。

## 六、请求区（双向）

### → 执行方请处理

- [ ] 启动 `run_crawl_queue.py` 并保持存活（任务 31 个）
- [ ] 全部到终态后在本段 @建任务方

### → 建任务方（Moss）请处理

- （待执行方填写；若需要建任务方改配置/换账号组/补数据，写在这里并注明 job#）

## 七、执行进度（自动追加）

- [01:34] [建任务方] 31 个任务已创建并预分配账号（job#388~418，全部 READY），等待执行方启动。
