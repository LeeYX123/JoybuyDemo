# 备份与回滚手册（Joybuy）

> **本文档是备份/回滚的唯一台账。** 每次新建备份、变更回滚点、或清理旧备份时，必须同步更新本文件（并注明日期、路径、大小、校验值）。
> 相关文档：生产部署见 `HANDOFF.md` 的 `0g`–`0d11` 各节；环境地址见 `README.md`「环境地址」章。

**最后更新：2026-11-27**

---

## 0. 三份数据在哪里（先看这张图）

| 数据 | 主副本位置 | 备份/回滚手段 | 丢失后果 |
| --- | --- | --- | --- |
| 数据库（MySQL） | DO Managed Clusters（VPC 内网、强制 TLS） | ① DO 平台自动备份/PITR；② 手工 dump（`/srv/backups/db/`）；③ 异地副本（Spaces `backups/db/`） | 商品、订单、账号全丢 |
| 媒体（图片/视频，约 120 万文件 / 110GB+） | DO Spaces 桶 `joybuy-media`（`media/` 前缀） | Spaces 自身持久化；本地 `var/media/` 另有完整副本 | 站点图片全裂 |
| 代码 | GitHub `LeeYX123/JoybuyDemo` main | 任意历史 commit 可回滚 | 可用 git 恢复 |
| 服务器配置（nginx / systemd / .env） | `/srv/joybuy`、`/etc/nginx/` | `/srv/backups/config/` 保存历史版本 | 需重建（HANDOFF 有配方） |

---

## 1. 生产数据库备份

### 1.1 服务器本地副本（`/srv/backups/db/`，权限 `700` 目录 / `600` 文件）

| 文件 | 生成时间 | 大小 | SHA256 | 内容 |
| --- | --- | --- | --- | --- |
| `joybuy_predeploy_20261127.sql.gz` | 2026-11-27 14:39 UTC | 219M（229,285,208 B） | `eb47982d9efd4fbd1f0c7031d8ed34c87c020e9b234d84ae27e330d4e6ecf558` | **全库 dump**，生成于「JY 编号体系 + 10 个迁移」部署之前 —— **当前首选回滚点** |
| `joybuy_dump_20261126.sql.gz` | 2026-11-26（原 `/tmp/joybuy_dump.sql.gz`） | 175M（183,262,892 B） | `a901b0533f477439fb3de56a65500fc51c2652830a0a4041fc804b3054fc0d1c` | 11-26 从 dev 导入生产时使用的那份 dump（md5 `56d9597c22b58df7a4b990f402fe5350`） |
| `product_backup_20261126/` | 2026-11-26 | 473M | 见目录内 `md5sums.txt` | **21 张商品域表**的写前镜像（`brand/local_category/media_asset/media_usage/spu/sku/offer/...`），商品数据同步专用回滚点 |

**生成命令（复用模板）**：

```bash
ssh joybuy-do 'cd /srv/joybuy && export $(grep -E "^MYSQL_PASSWORD=" .env | xargs) && \
  sudo mkdir -p /srv/backups/db && \
  mysqldump -h dbaas-db-4211065-do-user-49740357-0.i.db.ondigitalocean.com -P 25060 -u joybuy \
    -p"$MYSQL_PASSWORD" --ssl-mode=REQUIRED --single-transaction --routines --triggers \
    --set-gtid-purged=OFF joybuy | gzip > /tmp/joybuy_dump_$(date +%Y%m%d).sql.gz && \
  sudo mv /tmp/joybuy_dump_$(date +%Y%m%d).sql.gz /srv/backups/db/ && \
  sudo chmod 600 /srv/backups/db/*.gz && sudo sha256sum /srv/backups/db/*.gz'
```

### 1.2 异地副本（DO Spaces，防实例/磁盘故障）

| 对象键 | 大小 | 上传时间 |
| --- | --- | --- |
| `s3://joybuy-media/backups/db/joybuy_predeploy_20261127.sql.gz` | 229,285,208 B | 2026-11-27 14:46 UTC |
| `s3://joybuy-media/backups/db/joybuy_dump_20261126.sql.gz` | 183,262,892 B | 2026-11-27 14:46 UTC |

- 端点 `https://fra1.digitaloceanspaces.com`，凭据在服务器 `/srv/joybuy/.env`（`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`）。
- **`backups/` 前缀不是公开的**：桶策略只允许匿名读取 `media/*`，这两个 dump 需凭据才能下载（已核对）。
- 下载回本地：`aws s3 cp s3://joybuy-media/backups/db/<file> . --endpoint-url https://fra1.digitaloceanspaces.com`（本机用 `C:\Program Files\Amazon\AWSCLIV2\aws.exe`，凭据在 `~/.aws/credentials` 的 Spaces key，或临时 `export AWS_ACCESS_KEY_ID=...`）。

### 1.3 平台自动备份（DO 控制台）

- DO Managed Database 自带每日自动备份与 PITR，控制台可"恢复到某个时间点"（会新建集群，不覆盖原库）。**平台级恢复优先于手工 dump**（可回到故障前几分钟）。

### 1.4 ⚠️ 已知风险：`/tmp` 会被清空

历史上多个 dump 曾放在 `/tmp`（重启即丢）。**2026-11-27 已全部迁到 `/srv/backups/`**。以后新备份一律直接写 `/srv/backups/db/`，不要再放 `/tmp`。

---

## 2. 数据库回滚操作

### 2.1 整库回滚（会丢失备份之后的全部新数据，慎用）

```bash
# 1) 先停写入，避免回滚期间继续产生数据
ssh joybuy-do 'sudo systemctl stop joybuy-api'

# 2) 整库重灌（托管库用户 joybuy 对 joybuy 库有全量权限）
ssh joybuy-do 'cd /srv/joybuy && export $(grep -E "^MYSQL_PASSWORD=" .env | xargs) && \
  gunzip -c /srv/backups/db/joybuy_predeploy_20261127.sql.gz | \
  mysql -h dbaas-db-4211065-do-user-49740357-0.i.db.ondigitalocean.com -P 25060 -u joybuy \
    -p"$MYSQL_PASSWORD" --ssl-mode=REQUIRED joybuy'

# 3) 代码也要回到对应 commit（否则 schema 与代码不匹配）
ssh joybuy-do 'cd /srv/joybuy && git checkout <对应commit> && cd backend && ../venv/bin/python manage.py migrate --noinput'
ssh joybuy-do 'sudo systemctl start joybuy-api && systemctl is-active joybuy-api'
```

### 2.2 单表/单域回滚（推荐，影响面最小）

`product_backup_20261126/` 里是逐表 `.sql` 文件，可只回滚商品域：

```bash
ssh joybuy-do 'cd /srv/backups/db/product_backup_20261126 && ls   # 选要回滚的表
# 单表重灌（以 offer 为例）：先 DELETE 再导入，外键检查临时关闭
export $(grep -E "^MYSQL_PASSWORD=" /srv/joybuy/.env | xargs)
mysql -h ... -u joybuy -p"$MYSQL_PASSWORD" --ssl-mode=REQUIRED joybuy -e "SET FOREIGN_KEY_CHECKS=0; DELETE FROM offer; SET FOREIGN_KEY_CHECKS=1;"
mysql -h ... -u joybuy -p"$MYSQL_PASSWORD" --ssl-mode=REQUIRED joybuy < offer.sql'
```
> 回滚商品域后需重建搜索文档：`python manage.py rebuild_search_documents`（或按 HANDOFF 0d11 记录的逐 SPU 刷新口径）。

### 2.3 只回滚某次业务数据（如活动页、单个申请）

参见各次任务留档（均在 `var/`，见第 5 节），例如：
- 活动页数据回滚：重跑 `import_activity_pages --bundle <旧包> --apply`；
- 单个申请回滚到待审核：`var/rollback_app38_20261127/rollback.py`（DRY_RUN 默认，`APPLY=1` 执行）。

---

## 3. 服务器配置备份（`/srv/backups/config/`）

| 文件 | 说明 |
| --- | --- |
| `joybuy.bak.tls20261125` | 上 TLS 之前的 nginx 站点配置 |
| `joybuy.bak.tls20261125.postcertbot` | certbot 改完但 IP default_server 未修复时的中间态 |
| `joybuy.bak.m20261126` | 加 m 站 server 块之前 |
| `joybuy.bak.adminslug20261127` | 管理端入口改 `/admin18vm6u4b83sf/` 之前 |
| `.env.bak.oauth20261125` | 配置 Google OAuth 之前 |
| `.env.bak.tls20261125` | 删 cookie Secure 降级两行之前 |
| `.env.bak.www20261125` | 规范域切 www 之前 |

**恢复单个配置**：
```bash
ssh joybuy-do 'sudo cp /srv/backups/config/joybuy.bak.adminslug20261127 /etc/nginx/sites-available/joybuy && sudo nginx -t && sudo systemctl reload nginx'
```
> `.env` 恢复后必须 `sudo systemctl restart joybuy-api joybuy-storefront`，且注意这些旧 `.env` **不含**后来新增的键（`MEDIA_S3_*`、`AWS_*`、`STAFF_ADMIN_SESSION_COOKIE_NAME` 等），恢复时要按需补齐。

**其他仍在 `/tmp` 的临时配置快照**（重启会丢，非关键）：`/tmp/joybuy.precertbot20261126`、`/tmp/joybuy.preredirect20261126`、`/tmp/joybuy-site-spaces.conf`、`/tmp/joybuy-main.bundle`。

---

## 4. 代码回滚

| 场景 | 操作 |
| --- | --- |
| 回滚到任意历史版本 | `ssh joybuy-do 'cd /srv/joybuy && git log --oneline'` 选 commit → `git checkout <sha>` → `pip install -r backend/requirements/prod.txt`（若依赖变）→ `manage.py migrate` → 重建前端 → 重启服务 |
| 关键 commit 参考 | `a285a4b`（2026-11-27 当前生产）、`7bd0ecd`（JY 编号体系）、`9abd1cf`（管理端会话隔离修复）、`3c65ae7`（11-27 首次同步上限）、`29990da`（11-26 m 站上线）、`8e5ad99`（11-25 水合修复） |
| 前端产物 | 不入库，必须重建：storefront `pnpm --filter @joybuy/storefront build`；admin-web `vite build --base=/admin18vm6u4b83sf/`；merchant-web `vite build` |
| 库迁移与代码必须配对 | 回滚代码后先看 `manage.py showmigrations`；JY 编号体系（`7bd0ecd`）**不可回退**（public_id 已被迁移重写，回退代码会导致新旧 ID 混用） |

---

## 5. 本地（开发机）留档

| 目录 | 大小 | 内容 / 用途 |
| --- | --- | --- |
| `var/do_migration_20261124/` | 263M | **dev 库 dump**（`joybuy_dump.sql.gz`，175M，md5 `56d9597c22b58df7a4b990f402fe5350`）+ Spaces 上传脚本 `upload_media.sh` / `verify_media.sh` + nginx Spaces 反代片段 |
| `var/product_sync_20261126/` | 242M | 商品域 dev→prod 增量 SQL（`inc_*.sql` + md5）+ 比对/上传脚本 |
| `var/merge_20261109/` | 112K | 商家 14 → Samsung(12) 合并快照 |
| `var/merchant_single_shop_20261122/` | 1.8M | 多店账号清理（CHiQ 迁 `chiq@joybuy.test`）前的备份 |
| `var/activity_sync_20261126/` | 1.2M | 活动页三表导出 SQL（`activity_data.sql`） |
| `var/rollback_app38_20261127/` | 4K | 单个开店申请回滚脚本（DRY_RUN 默认） |
| `var/do_sync_20261127/` | 2.4M | 11-27 同步部署的截图与脚本 |
| `var/admin_slug_20261127/`、`var/superadmin_20261127/`、`var/deploy_20261127/` | <1M | 管理端路径切换、超管创建、部署验证的脚本与截图 |

> `var/` 整个目录被 `.gitignore` 忽略：**这些留档只存在于本机**，别删、也别指望从 git 恢复。

---

## 6. 媒体（Spaces）

- 桶 `joybuy-media`（FRA1），对象键 `media/<relative_path>`，与本地 `var/media/` 一一对应（累计 120 万+ 对象 / 110GB+）。
- 每日增量上传：自动化任务 `automation-a81eea40`（每天 03:00 跑 `var/do_migration_20261124/upload_media.sh`）。
- **云端对象误删的恢复**：本地 `var/media/` 是完整副本 → 重跑 `upload_media.sh` 即回补。
- **本地 `var/media/` 丢失的恢复**：只能从 Spaces 反向拉取（`aws s3 sync s3://joybuy-media/media/ var/media/ --endpoint-url ...`）。
- 注意：Spaces 桶**未开版本控制**，覆盖即覆盖；改图请用新相对路径（内容寻址 sha256 天然满足）。

---

## 7. 清理与保留策略（建议）

| 对象 | 建议保留 | 说明 |
| --- | --- | --- |
| `/srv/backups/db/*.sql.gz` | 最近 3 份（约每周 1 份） | 磁盘 154G，当前占用 394M，无需紧张 |
| Spaces `backups/db/` | 同上 | 只放"迁移前/大改前"的关键点 |
| `/srv/backups/config/` | 全留 | 体积小，回滚常用 |
| 本地 `var/` 大目录（do_migration/product_sync） | 保留至少到下一次全新 dump | 是 dev 库与商品同步的唯一历史 |

---

## 8. 恢复演练记录

| 日期 | 演练内容 | 结果 |
| --- | --- | --- |
| 2026-11-27 | 备份迁移 `/tmp` → `/srv/backups` + 上传 Spaces | ✅ 两个 dump 大小与本地一致（229,285,208 / 183,262,892 B），SHA256 已记录；Spaces 列目录可见 |
| （待补） | 真实整库恢复演练（建议在预发/临时库做） | — |
