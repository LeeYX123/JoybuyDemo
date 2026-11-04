# WP-40 生产部署手册（Ubuntu 24.04，单服务器）

按 `docs/08` 的拆分执行：WP-40A 基础服务 → WP-40B 应用发布 → WP-40C 验收与回滚。
本手册由代码仓库直接执行；所有秘密经环境变量注入，不入库。

## WP-40A 基础服务（约 40 分钟）

```bash
# 1. 系统依赖
sudo apt update && sudo apt install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx ffmpeg
sudo useradd -m -s /bin/bash joybuy || true

# 2. 数据目录（媒体/原始响应/备份）
sudo mkdir -p /srv/joybuy/data/{media,raw,exports,tmp} /srv/joybuy/backups
sudo chown -R joybuy:joybuy /srv/joybuy

# 3. 服务容器
cd /opt/joybuy && cp infra/prod/compose.prod.yml .
cp .env.prod.example .env   # 填写全部 CHANGE_ME（MySQL、HMAC、TOTP、指纹密钥）
docker compose -f compose.prod.yml up -d
docker compose -f compose.prod.yml ps   # 等待 healthy

# 4. Nginx + TLS
sudo cp infra/nginx/joybuy.conf /etc/nginx/sites-available/joybuy
sudo ln -sf /etc/nginx/sites-available/joybuy /etc/nginx/sites-enabled/
sudo certbot --nginx -d <your-domain>
```

## WP-40B 应用发布

```bash
# 后端：venv + 迁移 + gunicorn
python3.13 -m venv /opt/joybuy/venv
/opt/joybuy/venv/bin/pip install -r backend/requirements/prod.txt
cd backend && ../venv/bin/python manage.py migrate --noinput
../venv/bin/python manage.py collectstatic --noinput
../venv/bin/python manage.py bootstrap_platform_admin --email <ops@...> --display-name "Ops"
# 浏览器会话：/api/v1/admin/* 由 gunicorn提供服务；systemd 单元见 infra/prod/systemd/

# Celery worker + beat（爬虫/媒体/订单超时清扫）
# 前端：pnpm build 产物由 Nginx 静态/反代托管（见 joybuy.conf）
pnpm --filter @joybuy/storefront build && pnpm --filter @joybuy/admin-web build
```

## WP-40C 验收与回滚

- 健康检查：`GET /api/v1/health` 200（MySQL SELECT 1 + Redis 读写）。
- 核心 E2E：`playwright test tests/e2e/purchase-funnel.spec.js --host ...`（指向生产前冒烟环境）。
- 备份：`infra/scripts/backup.sh`（cron 每日），恢复 `infra/scripts/restore.sh <dump>`。
- 回滚：保留上一版本构建目录，`ln -sfn releases/<prev> current && systemctl reload joybuy`；数据库回滚用 `restore.sh` + binlog PITR。

## 已知边界（首期）

- 未配置 Prometheus/Grafana（WP-39 预留 systemd 日志 + Mailpit UI）。
- 短信供应商未接入：SMS 通知显式失败不伪造成功。
- 200 并发压测需在 WP-38 于预发布环境执行（脚本：`infra/loadtest/locustfile.py`）。
