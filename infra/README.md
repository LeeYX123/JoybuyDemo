# Infrastructure

本目录提供本地 MySQL、Redis 和 Mailpit 基础设施。所有端口只绑定到 `127.0.0.1`，数据保存在命名卷中，普通重启和 `down` 不会删除数据。

## 首次启动

从仓库根目录执行：

```powershell
Copy-Item .env.example .env
# 编辑 .env 中的 CHANGE_ME 值
& .\infra\scripts\check-dev-ports.ps1
docker compose --env-file .env -f infra/compose.dev.yml up -d --wait
docker compose --env-file .env -f infra/compose.dev.yml ps
```

若刚安装 Docker 后当前终端仍提示找不到 `docker`，重新打开终端，或先把 Docker 安装目录下的 `resources/bin` 加入当前会话的 `PATH`。

默认端口：MySQL `33060`、Redis `63790`、SMTP `1025`、Mailpit UI `8025`。如有占用，在 `.env` 中覆盖对应端口后，将相同值传给端口检查脚本。

## 日常命令

```powershell
# 查看健康状态
docker compose --env-file .env -f infra/compose.dev.yml ps

# 查看日志
docker compose --env-file .env -f infra/compose.dev.yml logs -f --tail 100

# 停止但保留容器和数据
docker compose --env-file .env -f infra/compose.dev.yml stop

# 停止并移除容器，保留命名卷
docker compose --env-file .env -f infra/compose.dev.yml down

# 拉取锁定标签并重建容器
docker compose --env-file .env -f infra/compose.dev.yml pull
docker compose --env-file .env -f infra/compose.dev.yml up -d --force-recreate --wait
```

仅在明确需要丢弃全部本地数据库、Redis 和测试邮件时使用以下命令；`--volumes` 不可恢复：

```powershell
docker compose --env-file .env -f infra/compose.dev.yml down --volumes
```

Mailpit Web UI：<http://127.0.0.1:8025>。

WP-39 将补充监控、备份和恢复演练；WP-40 将补充 Ubuntu 生产部署。真实秘密、证书、数据库卷和备份不得提交。

