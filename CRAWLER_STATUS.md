# CRAWLER_STATUS — 爬虫信息专档

> **定位：爬虫信息唯一台账。以后爬虫任务/账号/冷却/风控信息一律记入本文档；HANDOFF 只放指针不放明细。**
> 纪律：本档不得记录任何 FB 账号密码（项目约定密码从不采集、不落库，见 `backend/crawler_control/models.py` CrawlerAccount docstring）。

- **快照时间**：2026-11-25 19:30（本地 UTC+8）= 2026-11-25 11:30 UTC（取自 DB `SELECT NOW()`，库内时间戳均为 UTC）
- **快照数据来源**：本地 dev MySQL 容器 `joybuy-dev-mysql-1` / 库 `joybuy`，查询 + 三次经用户授权的 ORM 写库（11-24 30 个 FAILED 克隆重跑；11-25 中午清理外部中断僵尸 run 225/226 并重启队列；11-25 晚按用户指令干净暂停批次——run 227/228 转 FAILED、job 246/247 回 READY，见 §1.4 批次记录）：
  - 任务：`crawl_job`（273 行）、`crawl_run`（228 行）、`crawl_run_event`、`source_category`
  - 账号：`crawler_account`（77 行，含软删 1 行）、`crawler_account_group`、`crawler_circuit_breaker`
- **机制描述来源**：`backend/crawler_control/models.py`、`services.py`、`quality_services.py`、`import_services.py`（引用格式 文件:行号，基于 2026-11-24 快照时的工作区代码）
- 查询命令示例（Git Bash，控制台建议 ASCII）：
  `docker exec joybuy-dev-mysql-1 sh -c "mysql --default-character-set=utf8mb4 -ujoybuy -pjoybuy_dev_only joybuy -e '<SQL>'"`

---

## 1. 任务台账（crawl_job）

### 1.1 状态汇总（2026-11-25 11:30 UTC 刷新，**批次已按用户指令干净暂停、待恢复**）

| status | 数量 | 说明 |
|---|---|---|
| COMPLETED | 156 | 终态：已完成（154 旧 + 重跑批次 job 244/245） |
| CANCELED | 35 | 终态：已取消（5 旧 + 30 个原 FAILED 已按用户指令标记取消，见 §1.4） |
| READY | 80 | 待启动（旧 52 + 重跑批次 28 个未完成克隆任务，含暂停回队的 246/247） |
| RUNNING | 2 | **均为 11 月初 demo 僵尸行（job 2/3，用户已知情）**；重跑批次已全部暂停 |
| FAILED | 0 | 原 30 个 FAILED 已全部转 CANCELED 并克隆为新任务 |
| DRAFT | 0 | — |
| PAUSED | 0 | — |
| **合计** | **273** | |

关联 `crawl_run`（228 行）：SUCCEEDED 177 / FAILED 43 / RUNNING 3 / CANCELED 5；无 PENDING、无 PAUSED。
RUNNING 的 3 个 run：run 1、2、220（僵尸，用户已知情、不动）。重跑批次 run 227/228 已于 11:26 UTC 标记 FAILED（interrupted-by-user-pause），当前**无批次进程在跑**。

字段说明：CrawlJob 目标 = 类目（`source_category` + 多类目选区 `crawl_job_source_selection`）+ `product_limit`；**没有关键词字段、没有页数字段**（`allow_pagination` 控制列表翻页，models.py:172-178；关闭时只抓第一屏并记 LISTING_SHORTFALL）。下表"类目"列取 `source_category.name_zh`（多类目任务只显示主类目，空 = 该任务主类目 name_zh 为空，任务名里通常带类目名）。

### 1.2 非终态任务明细（RUNNING 2 + READY 80 = 82；FAILED 0，原 30 个见 §1.4）

#### RUNNING（2，均为僵尸行，用户已知情、待另行处理；**重跑批次已全部暂停**）

| id | 名称 | 目标 | limit | 分组 | 创建(UTC) | 备注 |
|---|---|---|---|---|---|---|
| 2 | Joybuy homepage demo import | demo | 500 | default | 11-03 10:33 | run 1 自 11-03 RUNNING，0 进展（僵尸行） |
| 3 | Joybuy UK bestsellers demo import | demo | 500 | default | 11-04 12:03 | run 2 自 11-04 RUNNING，0 进展（僵尸行） |

#### READY（80，待启动；重跑批次 28 个在此排队，**批次状态=用户暂停待恢复**，恢复命令见 §1.4）

| id | 名称 | 类目 | limit | 分组 | 创建/更新(UTC) |
|---|---|---|---|---|---|
| 1 | Joybuy homepage demo import | demo | 500 | default | 11-03 10:33 |
| 11 | UI 实测-壶类目-2件 | 热水壶 & 烤面包机 | 2 | default | 11-05 05:37 |
| 23 | 数据抓取04-烹饪调料 | 烹饪调料 | 200 | 数据抓取04 | 11-12 16:07 |
| 29 | 数据抓取04-米面杂粮 | 米面杂粮 | 200 | 数据抓取04 | 11-12 16:07 |
| 35 | 数据抓取04-苏打水和浓缩果汁 | （name_zh 空） | 200 | 数据抓取04 | 11-12 16:07 |
| 41 | 数据抓取04-烈酒 | 烈酒 | 200 | 数据抓取04 | 11-12 16:07 |
| 47 | 数据抓取04-小宠用品 | （name_zh 空） | 200 | 数据抓取04 | 11-12 16:07 |
| 53 | 数据抓取04-电子玩具 & 音乐玩具 | （name_zh 空） | 200 | 数据抓取04 | 11-12 16:07 |
| 59 | 数据抓取04-户外玩具 | 户外玩具 | 200 | 数据抓取04 | 11-12 16:07 |
| 65 | 数据抓取04-热水壶 & 烤面包机 | 热水壶 & 烤面包机 | 200 | 数据抓取04 | 11-12 16:07 |
| 71 | 数据抓取04-平板电脑 | 平板电脑 | 200 | 数据抓取04 | 11-12 16:07 |
| 77 | 数据抓取04-Networking Devices | （name_zh 空） | 200 | 数据抓取04 | 11-12 16:07 / 更新 11-13 08:45 |
| 83 | 数据抓取04-书写工具 | 书写工具 | 200 | 数据抓取04 | 11-12 16:07 |
| 89 | 数据抓取04-运动 & 体能 | 运动 & 体能 | 200 | 数据抓取04 | 11-12 16:07 |
| 95 | 数据抓取04-婴儿用品与床上用品 | 婴儿用品与床上用品 | 200 | 数据抓取04 | 11-12 16:07 |
| 101 | 数据抓取04-婴幼儿奶粉 | 婴幼儿奶粉 | 200 | 数据抓取04 | 11-12 16:07 |
| 107 | 数据抓取04-冰块与冰淇淋 | （name_zh 空） | 200 | 数据抓取04 | 11-12 16:07 |
| 113 | 数据抓取04-家居必需品 | （name_zh 空） | 200 | 数据抓取04 | 11-12 16:07 |
| 119 | 数据抓取04-洗衣用品 | 洗衣用品 | 200 | 数据抓取04 | 11-12 16:07 |
| 125 | 数据抓取04-日本食品 | 日本食品 | 200 | 数据抓取04 | 11-12 16:07 |
| 131 | 数据抓取04-家具 | 家具 | 200 | 数据抓取04 | 11-12 16:07 |
| 137 | 数据抓取04-礼物包装与贺卡 | 礼物包装与贺卡 | 200 | 数据抓取04 | 11-12 16:07 |
| 143 | 数据抓取04-男装 & 配饰 | 男装 & 配饰 | 200 | 数据抓取04 | 11-12 16:07 |
| 147 | 数据抓取02-配件 | （name_zh 空） | 200 | 数据抓取02 | 11-12 16:07 / 更新 11-22 19:06 |
| 149 | 数据抓取04-空气炸锅 | 空气炸锅 | 200 | 数据抓取04 | 11-12 16:07 |
| 155 | 数据抓取04-男士理容 | 男士理容 | 200 | 数据抓取04 | 11-12 16:07 |
| 161 | 数据抓取04-台式电脑 | 台式电脑 | 200 | 数据抓取04 | 11-12 16:07 |
| 166 | 数据抓取03-油烟机 & 排气扇 | 油烟机 & 排气扇 | 200 | 数据抓取03 | 11-12 16:07 |
| 167 | 数据抓取04-洗碗机 | （name_zh 空） | 200 | 数据抓取04 | 11-12 16:07 |
| 172 | 数据抓取03-私密和经期护理 | （name_zh 空） | 200 | 数据抓取03 | 11-12 16:07 |
| 173 | 数据抓取04-按摩与舒缓 | 按摩与舒缓 | 200 | 数据抓取04 | 11-12 16:07 |
| 178 | 数据抓取03-美黑及身体防晒 | 美黑及身体防晒 | 200 | 数据抓取03 | 11-12 16:07 |
| 179 | 数据抓取04-面部护肤 | 面部护肤 | 200 | 数据抓取04 | 11-12 16:07 |
| 185 | 数据抓取04-游戏耳机 | （name_zh 空） | 200 | 数据抓取04 | 11-12 16:07 |
| 191 | 数据抓取04-医疗保健与营养 | 医疗保健与营养 | 200 | 数据抓取04 | 11-12 16:07 |
| 196 | 数据抓取03-高端烈酒 | （name_zh 空） | 200 | 数据抓取03 | 11-12 16:07 / 更新 11-23 22:05 |
| 197 | 数据抓取04-世界烈酒 | 世界烈酒 | 200 | 数据抓取04 | 11-12 16:07 |
| 203 | 数据抓取04-派对装饰品 | 派对装饰品 | 200 | 数据抓取04 | 11-12 16:07 |
| 209 | 数据抓取04-游戏内存与存储 | 游戏内存与存储 | 200 | 数据抓取04 | 11-12 16:07 |
| 224 | 数据抓取01-美发造型-续跑20261119 | 美发造型 | 200 | 数据抓取01 | 11-19 07:26 |
| 225 | 数据抓取03-摄影摄像-续跑20261119 | 摄影摄像 | 200 | 数据抓取03 | 11-19 07:26 |
| 226 | 数据抓取03-经期护理-续跑20261119 | 经期用品 & 私密护理 | 200 | 数据抓取03 | 11-19 07:26 |
| 231 | 数据抓取06-医疗保健-续跑20261119 | 医疗保健 | 200 | 数据抓取06 | 11-19 07:26 / 更新 11-22 19:06 |
| 232 | 数据抓取06-婴儿哺育喂养-续跑20261119 | 婴儿哺育喂养 | 200 | 数据抓取06 | 11-19 07:26 |
| 233 | 数据抓取06-电子配件-续跑20261119 | 电子配件 | 200 | 数据抓取06 | 11-19 07:26 |
| 236 | 数据抓取02-冷冻甜品-续跑20261119 | （name_zh 空） | 200 | 数据抓取02 | 11-19 07:26 |
| 238 | 频道楼层补齐 20261124 | 家居生活 | 200 | default | 11-23 16:29 |
| 239 | 风控壳页薄商品补抓 20261124 | 宠物 | 50 | default | 11-24 05:48 |
| 240 | 户外频道 NL 补抓 20261124 | （name_zh 空） | 50 | default | 11-24 05:57 |
| 241 | 批次BB 户外详情小批补抓 20261124 | （name_zh 空） | 10 | default | 11-24 09:45 |
| 242 | 批次BB-2 户外54补抓 20261124 | （name_zh 空） | 60 | default | 11-24 11:32 |
| 243 | 批次BB-3 UK143补抓 20261124 | （name_zh 空） | 160 | default | 11-24 11:58 |
| 246 | 数据抓取02-猫粮（重跑20261125） | 猫粮 | 200 | 数据抓取03 | 11-24 16:47 |
| 247 | 数据抓取03-摄影摄像（重跑20261125） | 摄影摄像 | 200 | 数据抓取06 | 11-24 16:47 |
| 248 | 数据抓取05-手机（重跑20261125） | 手机 | 200 | 数据抓取01 | 11-24 16:47 |
| 249 | 数据抓取05-婴儿车、手推车及旅行配件（重跑20261125） | 婴儿车、手推车及旅行配件 | 200 | 数据抓取02 | 11-24 16:47 |
| 250 | 数据抓取06-婴儿哺育喂养（重跑20261125） | 婴儿哺育喂养 | 200 | 数据抓取08 | 11-24 16:47 |
| 251 | 数据抓取06-电子配件（重跑20261125） | 电子配件 | 200 | 数据抓取07 | 11-24 16:47 |
| 252 | 数据抓取01-电子烟（重跑20261125） | （name_zh 空） | 200 | 数据抓取05 | 11-24 16:47 |
| 253 | 数据抓取06-DIY工具（重跑20261125） | DIY工具 | 200 | 数据抓取03 | 11-24 16:47 |
| 254 | 数据抓取01-户外（重跑20261125） | 户外 | 200 | 数据抓取06 | 11-24 16:47 |
| 255 | 数据抓取06-时尚鞋靴（重跑20261125） | 时尚鞋靴 | 200 | 数据抓取01 | 11-24 16:47 |
| 256 | 数据抓取01-箱包手袋（重跑20261125） | 箱包手袋 | 200 | 数据抓取02 | 11-24 16:47 |
| 257 | 数据抓取01-饮品机（重跑20261125） | （name_zh 空） | 200 | 数据抓取08 | 11-24 16:47 |
| 258 | 数据抓取02-美发工具（重跑20261125） | 美发工具 | 200 | 数据抓取07 | 11-24 16:47 |
| 259 | 数据抓取01-电子健康理疗（重跑20261125） | 电子健康理疗 | 200 | 数据抓取05 | 11-24 16:47 |
| 260 | 数据抓取02-厨房电器（重跑20261125） | 厨房电器 | 200 | 数据抓取03 | 11-24 16:47 |
| 261 | 数据抓取01-美发造型（重跑20261125） | 美发造型 | 200 | 数据抓取06 | 11-24 16:47 |
| 262 | 数据抓取03-扬声器（重跑20261125） | 扬声器 | 200 | 数据抓取01 | 11-24 16:47 |
| 263 | 数据抓取01-游戏方向盘（重跑20261125） | （name_zh 空） | 200 | 数据抓取02 | 11-24 16:47 |
| 264 | 数据抓取01-冷冻派对食品（重跑20261125） | （name_zh 空） | 200 | 数据抓取08 | 11-24 16:47 |
| 265 | 数据抓取03-Drones（重跑20261125） | （name_zh 空） | 200 | 数据抓取07 | 11-24 16:47 |
| 266 | 数据抓取01-狗零食（重跑20261125） | （name_zh 空） | 200 | 数据抓取05 | 11-24 16:47 |
| 267 | 数据抓取01-手机-400（重跑20261125） | 手机 | 400 | 数据抓取03 | 11-24 16:47 |
| 268 | 数据抓取02-男装配饰-400（重跑20261125） | 男装 & 配饰 | 400 | 数据抓取06 | 11-24 16:47 |
| 269 | 数据抓取05-男装配饰-400-v2（重跑20261125） | 男装 & 配饰 | 400 | 数据抓取01 | 11-24 16:47 |
| 270 | 数据抓取01-饮品机-续跑20261119（重跑20261125） | （name_zh 空） | 200 | 数据抓取02 | 11-24 16:47 |
| 271 | 数据抓取05-手机-续跑20261119（重跑20261125） | 手机 | 200 | 数据抓取08 | 11-24 16:47 |
| 272 | 数据抓取06-笔记本与纸品-续跑20261119（重跑20261125） | 笔记本 & 书写纸品 | 200 | 数据抓取07 | 11-24 16:47 |
| 273 | 数据抓取02-婴幼儿玩具-续跑20261119（重跑20261125） | 婴幼儿玩具与活动用品 | 200 | 数据抓取05 | 11-24 16:47 |

READY 分组小计（80）：数据抓取04 = 32、数据抓取03 = 10、default = 8、数据抓取06 = 7、数据抓取02 = 6、数据抓取01 = 5、数据抓取05 = 4、数据抓取07 = 4、数据抓取08 = 4。（重跑批次未完成的 28 个全部在 READY 排队（244/245 已 COMPLETED）；重跑新任务全部 concurrency=2，见 §1.4。）

注：job 244/245 已 COMPLETED（run 223/224 SUCCEEDED，11-24 16:57 UTC，各 imported=5）；job 246/247 暂停前部分导入保留（run 227/228 FAILED @ 11:26 UTC，imported 24 / 23），恢复重跑由导入幂等去重。

#### FAILED（0）

原 30 个 FAILED 已于 2026-11-24 16:47 UTC 全部置 CANCELED 并克隆为新任务（244-273），完整 old→new 映射、组分配与失败原因归档见 **§1.4 批次记录**。

### 1.3 最近运行足迹（快照时点）

- 最近一次成功 run：**#222**，2026-11-24 13:52:37 UTC（本地 21:52），job 243「批次BB-3 UK143补抓 20261124」（#221 同 job 13:48 亦成功）。
- 最近一次失败 run：**#218**，2026-11-24 12:33:08 UTC（本地 20:33），同 job 243。
- `var/logs/crawl_runs/` 最近 10 个日志文件（本地时间）：

| 文件（public_id 前缀） | 修改时间(本地) | 大小 |
|---|---|---|
| 7e91d3d5-daf9-43a7-806c-c2dd7430e402 | 11-24 06:05 | 2.4MB |
| 00623af9-de77-4e3e-aedd-2a0645faaf80 | 11-24 05:26 | 4.5MB |
| 3a9c52f9-9c31-4082-b9b1-e14a2eb6c94b | 11-24 04:29 | 1.8MB |
| 1e975e0d-6982-4e75-b976-9123277fbad3 | 11-24 04:14 | 7.1MB |
| 32f14fe3-d28a-4087-91ae-ccc4a3daabf9 | 11-24 03:55 | 8.2MB |
| f5d0637c-f8b6-4a2d-ab45-d4504aa505fe | 11-24 03:36 | 6.5MB |
| 6af5680f-94e5-4749-8d50-ffff1bb4c77a | 11-24 03:32 | 3.4MB |
| c3c579af-8189-40e1-967b-a820a8780768 | 11-24 03:30 | 1.5MB |
| 03d64634-1bee-44de-9896-361156f22286 | 11-24 03:14 | 3.4MB |
| cda68b16-f171-4889-ae51-772345115a19 | 11-24 03:00 | 4.3MB |

- 最新日志（7e91d3d5）内容止于 2026-11-23 22:05 UTC，`ConnectionLost` 计数 **0**，spider 正常关闭（结尾有少量 403/解析丢弃记录）。
- 注意：run 219–222（11-24 12:40–13:52 UTC）**没有**对应的新日志文件落盘（目录里当时最新文件止于 06:05 本地），这几个 run 的过程要看 `crawl_run`/`crawl_run_event` 表。
- 更新（11-25 00:51 本地）：重跑批次首批 **run 223/224** 日志已正常落盘（`73d553f5…` / `c2caa5fd…`），详见 §1.4。
- 更新（11-25 19:25 本地）：run 223/224 已 SUCCEEDED；外部中断事故与恢复见 §1.4（中断的 run 225/226 日志 `504886cb…` / `91e99386…` 止于 11-24 17:50 UTC 前后，无关闭行）；恢复后 run 227/228 日志 `b1ceeb24…` / `5852ec6c…` 正常落盘。
- 更新（11-25 19:30 本地）：**批次已按用户指令干净暂停**——run 227/228 转 FAILED（interrupted-by-user-pause），队列器与执行器进程全部退出，无爬虫进程残留；详见 §1.4。

---

### 1.4 批次记录：30 个 FAILED 任务标记 + 克隆重跑（用户授权，2026-11-24/25）

**批次动作**（2026-11-24 16:47 UTC 完成克隆写库，16:50:57 UTC 启动首批）：

- 对象：当时全部 30 个 FAILED 任务（协调者清单列了 29 个 id，按"30 个 FAILED"指令与 §1.2 台账补入第 30 个 **213**）。
- 原任务处理：status FAILED→CANCELED（走 `_transition_job` 合法转换）；名称追加 `[RETRIED_BY_JOB_<新id>]`（**CrawlJob 无 remark/error 字段**，schema 核实后标记写入 job 名称，并在原任务最后一个 run 上补 `JOB_RETRIED` 事件）。
- 新任务：克隆全部抓取参数（目标类目/多类目选区/product_limit/allow_pagination/skip_imported/sort/media 开关等原样）；**账号组打乱轮转**（7 个有效组以固定种子 20261124 洗牌后按 old id 升序轮转，每组 4-5 个）；**concurrency=2**；pinned account 清空（组内 LRU 自动选号）；status=READY。
- 绝未分配：数据抓取04（10 号全 UNKNOWN）、数据抓取（2）、default（1）。
- 启动机制：正规路径 `start_run(job)` + detached 执行器 `manage.py run_crawl_run --run <public_id>`（同 admin_views.py AdminCrawlJobActionsView）；队列器 `var/crawler_retry_20261124/retry_queue.py`（改编自 batch26_queue.py 现成模式），**全局并发 2**（同时最多 2 个 RUNNING，一个终态后启动下一个 READY）；单 run 超时 240 分钟（超时 kill+FAILED，不算熔断）；连续 3 个坏 run（FAILED 且带 RISK_CONTROL_FALLBACK/ACCOUNT_POOL_EXHAUSTED/CONNECTIVITY_PREFLIGHT_FAILED）停止派发；每次派发前检查全局熔断器。
- 启动环境：`CRAWL_MEDIA_DOWNLOAD_WORKERS=2`（89GB 媒体上传占用 VPN 隧道期间压低导入期媒体并发，import_services.py:494，执行器子进程继承）+ `MEDIA_BACKEND=local` + `CRAWL_VARIANT_PRICES=true` + `CRAWL_VARIANT_PRICE_LIMIT=0`（与 batch26 批次一致）。
- 底档文件：`var/crawler_retry_20261124/`（`retry_failed.py` 克隆脚本含幂等护栏；`mapping.json` 映射；`retry_queue.py` 队列；`queue.log`/`progress.json`/`final_summary.json` 运行记录）。

**映射表（old→new + 新组；limit 与原任务相同）**：

| old | new | 新组 | limit | 原失败原因（摘要） |
|---|---|---|---|---|
| 13 | 244 | 07 | 10 | 列表页无商品（疑似风控/改版） |
| 14 | 245 | 05 | 10 | 列表页无商品（疑似风控/改版） |
| 45 | 246 | 03 | 200 | 价格选择器失效 169/169 |
| 70 | 247 | 06 | 200 | Night queue timeout |
| 72 | 248 | 01 | 200 | Night queue timeout |
| 96 | 249 | 02 | 200 | Night queue timeout |
| 97 | 250 | 08 | 200 | Night queue timeout |
| 103 | 251 | 07 | 200 | Night queue timeout |
| 122 | 252 | 05 | 200 | 网络不可达（getaddrinfo 失败） |
| 139 | 253 | 03 | 200 | Phase2 queue timeout |
| 140 | 254 | 06 | 200 | Night queue timeout |
| 145 | 255 | 01 | 200 | Phase2 queue timeout |
| 146 | 256 | 02 | 200 | 价格选择器失效 200/200 |
| 152 | 257 | 08 | 200 | Night queue timeout |
| 153 | 258 | 07 | 200 | 02 组 ACCOUNT_POOL_EXHAUSTED 主动停止 |
| 158 | 259 | 05 | 200 | Night queue timeout |
| 165 | 260 | 03 | 200 | 价格选择器失效 16/16 |
| 170 | 261 | 06 | 200 | Night queue timeout |
| 184 | 262 | 01 | 200 | 价格选择器失效 103/103 |
| 188 | 263 | 02 | 200 | 僵尸 RUNNING 清理 |
| 200 | 264 | 08 | 200 | 01 组 ACCOUNT_POOL_EXHAUSTED 主动停止 |
| 202 | 265 | 07 | 200 | 用户暂停（可续跑） |
| 212 | 266 | 05 | 200 | 列表页无商品（疑似风控/改版） |
| 213 | 267 | 03 | 400 | Phase-1 风控试水失败（01 组 9 号全标记） |
| 214 | 268 | 06 | 400 | 风控熔断（02 组） |
| 219 | 269 | 01 | 400 | 风控打穿（05 组） |
| 222 | 270 | 02 | 200 | 用户暂停（可续跑） |
| 227 | 271 | 08 | 200 | 用户暂停（可续跑） |
| 230 | 272 | 07 | 200 | 用户暂停（可续跑） |
| 234 | 273 | 05 | 200 | 用户暂停（可续跑） |

新组分配小计：01=4、02=4、03=4、05=5、06=4、07=5、08=4。

**启动与观察记录**：
- 16:50:57 UTC（本地 11-25 00:50）首批两 run 启动：**run 223**（job 244，old 13，G07，执行器 pid 52848）/ **run 224**（job 245，old 14，G05，pid 53380）。
- 观察至 16:55 UTC（>3 分钟）：两 run 均正常抓取——列表页/详情页 200、PRODUCT_PARSED / MOBILE_DETAIL_MERGED / VARIANT_PRICES_MERGED / DATASET_SAVED 事件正常、商品图片下载 200；**ConnectionLost=0、ERROR 事件=0**；Overridden settings 确认 `CONCURRENT_REQUESTS=2` 生效；账号池就绪（G07 池 10 号、G05 池 8 号，与 §2.2 一致）。
- run 223/224 于 16:57 UTC **SUCCEEDED**（job 244/245 COMPLETED；各 discovered=10、imported=5、item 级 failed=5，小任务首屏仅 10 个候选所致）。

**中断事故与恢复（2026-11-25）**：
- **中断**：本地 11-25 01:50（UTC 11-24 17:50）前后，第二批两 run——**run 225**（job 246 猫粮，G03）/ **run 226**（job 247 摄影摄像，G06）——连同 `retry_queue.py` 队列器被**外部终止**（原因不明：日志无关闭/错误行、中途戛然而止；机器未关机，同机 89GB 媒体对账今早正常跑完）。停摆约 17 小时。
  - run 225 中断前：discovered=200 / downloaded=144 / **imported=129** / item 级 failed=15；run 226 中断前：discovered=200 / downloaded=80 / **imported=72** / failed=7。
- **清理**（11-25 11:14 UTC，ORM 脚本 `var/crawler_retry_20261124/cleanup_225_226.py`，走合法状态机）：run 225/226 RUNNING→FAILED（`RUN_FAILED` ERROR 事件注明 interrupted-by-external-kill + 中断前计数）；job 246/247 RUNNING→READY。已导入部分保留，靠导入幂等去重，重跑不会脏。
- **恢复**（11-25 11:15:04 UTC）：`retry_queue.py` 重启（`queue2.log`；参数不变：全局并发 2、单 run 超时 240min、`CRAWL_MEDIA_DOWNLOAD_WORKERS=2`；中断批次 progress.json 备份为 `progress_batch1_interrupted.json`）。244/245 正确跳过（status=COMPLETED），继续派发剩余 28 个：
  - **run 227**（job 246，G03，pid 40420）/ **run 228**（job 247，G06，pid 47944），观察至 11:20 UTC（>3 分钟）：正常抓取，ConnectionLost=0。
- 隧道状态变化：89GB 媒体上传已收官，`CRAWL_MEDIA_DOWNLOAD_WORKERS=2` 按用户指示维持不变。

**用户暂停（2026-11-25 19:26 UTC / 本地 11-25 19:26，批次当前状态=暂停待恢复）**：
- 用户指令干净暂停。执行顺序：taskkill 队列器进程树（shim 46264→主循环 39096→执行器 40420/38260、47944/43532 共 6 个 python 进程，venv shim 双层结构）→ ORM 状态转换（`var/crawler_retry_20261124/cleanup_227_228_pause.py`，DRY_RUN→--execute）：run 227/228 RUNNING→FAILED（`RUN_FAILED` ERROR 事件注明 **interrupted-by-user-pause** + 中断前计数）、job 246/247 RUNNING→READY。
- 暂停前计数：run 227（job 246 猫粮，G03）discovered=101 / downloaded=34 / **imported=24** / item 级 failed=10；run 228（job 247 摄影摄像，G06）discovered=200 / downloaded=25 / **imported=23** / failed=2。已导入部分保留，恢复重跑幂等去重。
- 暂停后验证：无 retry_queue / run_crawl_run python 进程残留；crawl_job RUNNING 仅剩 demo 僵尸 job 2/3（用户知情未动）；crawl_run RUNNING 仅剩僵尸 run 1/2/220；crawl_job 273 = COMPLETED 156 / CANCELED 35 / READY 80 / RUNNING 2；进度底档 `progress.json` 备份为 `progress_paused_20261125.json`。
- **恢复指令**（语义不变：读 mapping.json 派发，COMPLETED 自动 SKIP，READY 按序继续；建议恢复前先跑 cleanup 脚本同款检查或直接依赖 dispatch 的状态守卫）：
  `cd /e/code/AgentProject/Joybuy && MEDIA_BACKEND=local PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 .venv/Scripts/python.exe -I var/crawler_retry_20261124/retry_queue.py > var/crawler_retry_20261124/queue3.log 2>&1 &`
  （Git Bash 后台运行；日志接续写 queue3.log。恢复前确认 VPN TUN 模式开启。）

---

## 2. 账号池（crawler_account）

### 2.1 总览（快照时点）

- 总行数 **77**（含软删 1 行，deleted_at 非空）；在册 **76**
- **可用 = ACTIVE + session_status=VALID = 58 个**（`is_selectable` 定义 models.py:83-87）
- ACTIVE + session_status=UNKNOWN（无可用会话，不可选）：18 个
- DISABLED：在册 0 个（1 个 DISABLED 已随软删一起）
- **当前处于 6 小时风控冷却中的账号：0 个**（全部 58 个可用账号此刻均"已就绪"）
- 可用账号中有历史风控记录（risk_flagged_at 非空）：55/58（均已在冷却窗外，不影响选号）
- 最近 24 小时（UTC 11-23 16:34 起）被使用过（last_used_at）：19 个
- 全局熔断器：**未触发**（is_tripped=0；window_minutes=30，account_threshold=2）

### 2.2 分组 × 状态交叉表

| 分组 | ACTIVE+VALID（可用） | ACTIVE+UNKNOWN | DISABLED(已软删) | 小计 |
|---|---|---|---|---|
| default | 1 | 1 | — | 2 |
| 数据抓取 | 2 | — | 1 | 3 |
| 数据抓取01 | 9 | 1 | — | 10 |
| 数据抓取02 | 6 | 4 | — | 10 |
| 数据抓取03 | 10 | — | — | 10 |
| 数据抓取04 | 0 | 10 | — | 10 |
| 数据抓取05 | 8 | 2 | — | 10 |
| 数据抓取06 | 8 | — | — | 8 |
| 数据抓取07 | 10 | — | — | 10 |
| 数据抓取08 | 4 | — | — | 4 |
| **合计** | **58** | **18** | **1** | **77** |

要点：**数据抓取04 组 10 个账号全部无可用会话（ACTIVE+UNKNOWN）**，该组 READY 任务（32 个）实际无号可用（按 services.py:460-467 逻辑会以未登录状态启动）；数据抓取02、05 组各有少量非可用号。

### 2.3 非可用账号清单（在册 18 个 + 软删 1 个）

| id | label | 分组 | 状态 | session_status | 备注(note 摘要) |
|---|---|---|---|---|---|
| 2 | FB 主账号 | default | ACTIVE | UNKNOWN | 登录未在限时内完成，未保存任何会话；可重新登录再试 |
| 11 | 100005191879231 | 数据抓取01 | ACTIVE | UNKNOWN | FB 过人机验证后重试 3 次仍退回登录页，判定账号不可用（疑似被封/锁定/风控） |
| 18 | 61570605463947 | 数据抓取02 | ACTIVE | UNKNOWN | 触发 Google 帐户验证（需登录 FB 绑定的 Gmail），判为账号不可用 |
| 19 | 61571016720516 | 数据抓取02 | ACTIVE | UNKNOWN | 同上（Google 帐户验证） |
| 20 | 61570727649019 | 数据抓取02 | ACTIVE | UNKNOWN | 同上（Google 帐户验证） |
| 21 | 61570901313540 | 数据抓取02 | ACTIVE | UNKNOWN | 同上（Google 帐户验证） |
| 36 | 61564165427258 | 数据抓取04 | ACTIVE | UNKNOWN | note=自动 FB 登录成功已保存会话（15 条 Cookie），但当前 session_status=UNKNOWN（未验证/已失效） |
| 37 | 100070934469851 | 数据抓取04 | ACTIVE | UNKNOWN | 同上 |
| 38 | 61571066231296 | 数据抓取04 | ACTIVE | UNKNOWN | 触发 Google 帐户验证，判为账号不可用 |
| 39 | 61570945065490 | 数据抓取04 | ACTIVE | UNKNOWN | 同上（Google 帐户验证） |
| 40 | 61571087919245 | 数据抓取04 | ACTIVE | UNKNOWN | 同上（Google 帐户验证） |
| 41 | 61570649686479 | 数据抓取04 | ACTIVE | UNKNOWN | 同上（Google 帐户验证） |
| 42 | 61571107257213 | 数据抓取04 | ACTIVE | UNKNOWN | note=登录成功已保存会话，但 session_status=UNKNOWN |
| 43 | 61570841016186 | 数据抓取04 | ACTIVE | UNKNOWN | 同上 |
| 44 | 61570614100694 | 数据抓取04 | ACTIVE | UNKNOWN | 同上 |
| 45 | 61575789112146 | 数据抓取04 | ACTIVE | UNKNOWN | 同上 |
| 47 | 100003836077774 | 数据抓取05 | ACTIVE | UNKNOWN | 触发设备通知验证（需其它已登录设备确认），判为账号不可用 |
| 51 | 100013498475534 | 数据抓取05 | ACTIVE | UNKNOWN | FB 登录信息有误（密码不匹配或已改密），需人工核对凭据 |
| 6 | 100020413770869 | 数据抓取 | DISABLED | — | **已软删**（deleted_at=2026-11-05 11:36 UTC，fake-session 事故批次） |

非可用账号的 risk_flagged_at 均为 NULL（它们不是被风控冷却挡住的，而是没有可用会话本身）。

### 2.4 可用账号统计（58 个，不逐个列出）

按分组：数据抓取01 = 9、02 = 6、03 = 10、05 = 8、06 = 8、07 = 10、08 = 4、「数据抓取」= 2、default = 1。
其中 55 个有历史风控记录（冷却已过期）；最近 24h 内用过的 19 个（LRU 靠后，见 §3.2）。

---

## 3. 冷却与风控机制（代码提取的真实规则）

### 3.1 状态枚举（models.py）

- 任务 `CrawlJob.Status`：DRAFT / READY / RUNNING / PAUSED / COMPLETED / CANCELED / FAILED（models.py:91-98）
- 运行 `CrawlRun.Status`：PENDING / RUNNING / PAUSED / SUCCEEDED / FAILED / CANCELED（models.py:263-269）；暂停原因 `PauseReason`：NONE / MANUAL / RISK_CONTROL / FAILURE_POLICY（models.py:271-275）
- 账号 `CrawlerAccount.Status`：ACTIVE / PAUSED_RISK_CONTROL / DISABLED（models.py:36-39）；会话 `SessionStatus`：UNKNOWN / VALID / EXPIRED（models.py:41-44）
- 账号可选新任务的条件 `is_selectable`：status==ACTIVE **且** session_status==VALID（models.py:83-87）

### 3.2 选号规则（LRU，不是时间冷却）

- 启动 run 时：任务指定账号（pinned）优先；pinned 不可用则回退到 `account_group` 组内自动选号，并在 run 日志记 `ACCOUNT_FALLBACK`（services.py:405-427）。
- 自动选号 = 组内 ACTIVE+VALID+未软删、排除风控冷却中的账号，按 `last_used_at, pk` 升序（**最近最少使用优先**）取前 20/50 个候选（services.py:451、476；start_run 里写入 last_used_at：services.py:873-874）。
- 组内没有可用会话账号时**不阻塞**：run 以未登录（匿名）状态启动，记 `RUN_UNAUTHENTICATED`（services.py:460-467、899-906）。
- 2026-11-05 起一个 run 可轮换使用组内多个账号（usable_accounts_for_run，services.py:430-457）；"VALID 但无 Cookie 的会话"判为不可用（services.py:357-396，fake-session 事故的防御）。

### 3.3 风控冷却（6 小时，自动解除，无需人工）

- 运行中途账号命中风控（被轮换掉但 run 继续的场景）：`mark_account_risk_cooldown` 只写 `risk_flagged_at` + `risk_reason`，**账号状态保持 ACTIVE**（services.py:287-312）。
- 冷却时长：默认 **6.0 小时**，环境变量 `CRAWLER_RISK_COOLDOWN_HOURS` 可覆盖（services.py:46-47、315-325）。
- 判定：`risk_flagged_at > now - 6h` 即在冷却中；候选查询用 `_exclude_risk_cooled` 排除（services.py:333-354）。
- **解除条件：全自动**——`risk_flagged_at` 距今超过 6 小时即视为可再用，没有任何人工复位动作。
- 启动时若组内**部分**账号在冷却，正常启动但记事件 `ACCOUNTS_RISK_COOLDOWN_SKIPPED`（services.py:882-891）。

### 3.4 人工风控升级与恢复（PAUSED_RISK_CONTROL）

- `flag_account_risk_control`：账号置 PAUSED_RISK_CONTROL + 写 risk_flagged_at/reason，并暂停它正在跑的 run（pause_reason=RISK_CONTROL）与所在 job（services.py:227-265）。此路径同时向全局熔断器计数（services.py:260-264）。
- 恢复只能人工：`reactivate_account`，仅允许对 PAUSED_RISK_CONTROL 的账号操作，恢复时清空 risk_flagged_at（services.py:268-277）。

### 3.5 组级冷却守卫

- 若组内 ACTIVE+VALID 的账号**全部**处于 6h 冷却 → 拒绝启动（抛 CrawlAccountStateInvalid），job 留在 READY，等冷却结束（services.py:485-518）。背景：2026-11-16 数据抓取03 组曾用 10 个烧过的号重跑（services.py:492-494 注释）。

### 3.6 全局熔断器（crawler_circuit_breaker）

- 触发：`report_account_risk` 在 30 分钟窗口（window_minutes）内统计不同命中账号数 ≥ 阈值（account_threshold=**2**）→ `is_tripped=True`，并把所有 READY 任务批量暂停（quality_services.py:198-228；默认值 models.py:457-458）。
- 触发后：任何 run 都无法启动（`ensure_breaker_allows_run`，quality_services.py:246-251；start_run 入口检查 services.py:854-861）。
- 解除：**仅人工** `reset_circuit_breaker`（quality_services.py:254 起，需人工复核后调用）。
- 当前状态：未触发（快照时点 is_tripped=0）。

### 3.7 并发与限流（2026-11-25 00:53 刷新）

- 账号级 `rate_limit_per_minute` / `concurrency_limit`：**全部为空**（无账号设限）；任务级 `rate_limit_per_minute` 全部为空；重跑批次 30 个新任务（244-273）`concurrency=2`，其余任务仍为 1。
- 导入阶段媒体下载并发：环境变量 `CRAWL_MEDIA_DOWNLOAD_WORKERS`，默认 **6**（backend/crawler_control/import_services.py:493-494）——这是隧道带宽的主要消耗口，当前约束见 §4。

---

## 4. 运行约束（当前有效，2026-11-25 11:30 UTC 状态）

1. ~~本地 89GB 媒体上传占用隧道~~ **已收官（2026-11-25 白天完成对账）**，隧道空闲；`CRAWL_MEDIA_DOWNLOAD_WORKERS=2` 按用户指示维持不变。
2. 重跑批次（§1.4）**当前状态=用户暂停、待恢复**（11-25 19:26 本地干净暂停，无爬虫进程；恢复命令见 §1.4 用户暂停小节）。
3. 恢复后监控 `var/crawler_retry_20261124/queue3.log` 与 `var/logs/crawl_runs/*.log`：grep `ConnectionLost`，密集出现即暂停爬虫。历史各 run 观察期内该计数均为 0。
4. 爬虫必须走 VPN 且为 **TUN 模式**（否则 UK 站访问不稳/出口不对）——恢复批次前先确认。
5. 数据抓取04 组（32 个 READY 任务）无可用会话号——启动只会匿名抓，跑之前先补号或改分组；重跑批次已遵守此约束（未分配 04 组）。
6. **新坑（勿再踩）**：桌面机上的后台队列进程可能被外部终止（11-25 凌晨曾连执行器一起被杀，原因不明）。恢复流程已两次验证：清僵尸（run FAILED + job READY，均走合法状态机转换）→ 直接重跑 `retry_queue.py`（对 COMPLETED 任务自动 SKIP）。长批次建议每日核对 queue 日志与 DB RUNNING run 是否有新鲜心跳。

## 5. 维护约定

- **每次爬虫任务启动/结束、账号状态变化（新增/禁用/风控/恢复/补会话）后，必须更新本文档对应小节（§1/§2/§4）并刷新顶部"快照时间"与来源说明。**
- HANDOFF.md **只放一行指针**指向本档，不复制明细。
- 账号凭据（密码）永不入档；账号只用 label/public_id 标识。
- 只读查询命令模板见文档开头；禁止在快照更新时启动爬虫或写库。
- 历史背景（勿重复踩坑）：fake-session 事故（2026-11-05，57 个账号曾作废，会话必须含 Cookie 才算可用，services.py:357-376）；数据抓取02/01 组 ACCOUNT_POOL_EXHAUSTED（2026-11-16/11-21，试水纪律：池子全烧就停，别换号硬冲）；Night/Phase2 队列超时是夜间批跑常见失败形态，FAILED 任务可直接重跑（start_run 允许 FAILED→RUNNING）。
