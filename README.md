# Joybuy

Joybuy 是一个按固定公开页面基线实施的研究与演示项目。首期包含 Nuxt 3 购物端、Vue 3 平台管理端、Django/DRF API，以及 Scrapy + Playwright 数据采集流水线。

当前实现状态：`WP-00` 至 `WP-40` 已完成——全部 41 个工作包（阶段 A 工程基础、B 后端领域、C 爬虫与数据、D 购物端、E 平台管理端、F 联调质量、G 部署准备）均已实现并通过本地自动化验收：216 项后端测试、29 项前端测试、15 项 Chromium E2E（含平台管理页面、完整购物漏斗与四宽度结构检查）。生产部署按 `infra/prod/deploy.md` 在 Ubuntu 服务器执行；200 并发压测在预发布环境运行 `infra/loadtest/locustfile.py`。详见 [工作包状态与实施记录](./docs/08-implementation-work-packages.md)。

## 从这里开始

1. 阅读 [文档索引](./docs/README.md) 和 [产品范围](./docs/01-requirements.md)。
2. 查看 [工作包状态表](./docs/08-implementation-work-packages.md)，只选择依赖已满足的下一个工作包。
3. 复制环境变量模板：

   ```powershell
   Copy-Item .env.example .env
   ```

4. 为 `.env` 中所有 `CHANGE_ME` 项设置仅供本地使用的值。`.env` 不得提交。
5. 按 [基础设施入口](./infra/README.md) 启动本地依赖，再按 [后端入口](./backend/README.md) 迁移并启动 API。

## 仓库结构

| 路径          | 职责                                       | 首个负责工作包 |
| ------------- | ------------------------------------------ | -------------- |
| `backend/`    | Django、DRF、Celery 与领域服务             | WP-02          |
| `storefront/` | Nuxt 3 购物端                              | WP-03          |
| `admin-web/`  | Vue 3 + Vite 平台管理端                    | WP-03          |
| `crawler/`    | Scrapy、Playwright、解析器与 fixture       | WP-14          |
| `infra/`      | 本地与生产基础设施、Nginx、监控和运维脚本  | WP-01          |
| `var/`        | 本地媒体、原始响应、缓存与开发数据；不提交 | WP-01 起       |
| `docs/`       | 需求、架构、流程、验收标准与实施状态       | 已有           |

商家端首期不实现页面或业务，待用户提供参考网页后另行评审；不要把平台端复制为商家端。

## 环境地址

> 本节只列地址与端口；凭据、密钥一律从 `.env` / 服务器 `.env` 读取，不写入本文档。

### 本地开发环境（本机，2026-11-27 实测）

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 购物端 storefront（Nuxt dev） | http://127.0.0.1:3000 | 亦可 `http://localhost:3000`；手机版为响应式，窄视口（<768px）或 `?mobile-auto=1` 触发移动布局 |
| 后端 API（Django） | http://127.0.0.1:8000 | 健康检查 `GET /api/v1/health`；根路径返回 404 属正常 |
| 平台管理端 admin-web（Vite） | http://127.0.0.1:5173 | 标题「Joybuy 管理平台」 |
| 商家中心 merchant-web（Vite） | http://127.0.0.1:5174 | 标题「商家中心 · Joybuy」；手机版 `/mobile.html` |
| 邮件预览 Mailpit | http://127.0.0.1:8025 | SMTP 端口 `127.0.0.1:1025` |
| MySQL | 127.0.0.1:33060 | 库 `joybuy`；账号密码见 `.env` |
| Redis | 127.0.0.1:63790 | 缓存与限流 |
| 爬虫出站代理（可选） | 代理 `127.0.0.1:7997` / 控制 API `127.0.0.1:9098` | 本地独立 mihomo 实例，脚本见 `var/clash_crawler_proxy/`；非爬虫任务无需启动 |

开发态数据流：`5173/5174 → vite 代理 → 8000`；`3000（Nuxt SSR）→ 8000`；媒体文件走本地 `var/media/`（`MEDIA_BACKEND=local`）或对象存储（`MEDIA_BACKEND=s3`）。

### 生产环境（DigitalOcean，2026-11-27 实测）

| 入口 | 地址 | 说明 |
| --- | --- | --- |
| 购物端主站（规范域） | **https://www.joyfumi.com** | 桌面与响应式购物端 |
| 裸域 | https://joyfumi.com | 301 → `https://www.joyfumi.com` |
| 购物端手机站 | **https://m.joyfumi.com** | 按 host 判定渲染移动布局（不看窗口宽度） |
| 手机站备用域 | https://m.www.joyfumi.com | www 窄视口自动跳转到此域 |
| 商家中心 | **https://merchant.joyfumi.com** | 桌面 + 手机版（`/mobile.html`） |
| 平台管理端 | **https://www.joyfumi.com/admin18vm6u4b83sf/** | 邮箱 + 密码登录（无 TOTP）；入口路径为混淆串，`/admin/` 不再提供服务 |
| 后端 API | https://www.joyfumi.com/api/v1/ | 健康检查 `/api/v1/health` |
| 媒体（图片/视频） | https://www.joyfumi.com/media/&lt;relative_path&gt; | Nginx 反代 DO Spaces 桶 `joybuy-media`（fra1），带 7 天缓存 |
| 服务器直连（应急/调试） | http://161.35.23.231 | SSH 别名 `joybuy-do`（密钥认证） |

生产基础设施：

| 组件 | 配置 |
| --- | --- |
| 应用服务器 | DigitalOcean Droplet，区域 FRA1（法兰克福），4 vCPU / 7.8 GB / 154 GB SSD |
| 数据库 | DigitalOcean Managed MySQL 集群（VPC 内网端点，强制 TLS，自动备份） |
| 对象存储 | DigitalOcean Spaces `joybuy-media` @ FRA1（`fra1.digitaloceanspaces.com`） |
| TLS | Let's Encrypt，覆盖 joyfumi.com / www / m / m.www / merchant 共 5 个域名，certbot 自动续期 |
| 对外端口 | 仅 Nginx 80/443；应用端口（Nuxt 3000、gunicorn 8000、Redis、Mailpit）均只绑 `127.0.0.1` |
| 第三方服务 | Google OAuth（买家登录，回调 `https://www.joyfumi.com/api/v1/auth/buyer/oauth/google/callback`）；Crisp 客服（Website ID 见 `.env`） |

## 命令约定

- 所有命令默认从仓库根目录执行；模块专用命令须明确写出工作目录。
- Windows 本地文档以 PowerShell 7 语法为准，生产环境脚本以 Ubuntu shell 为准。
- Python 命令统一使用模块形式，例如 `python -m pytest`；Node 命令使用项目锁定的包管理器，锁定前不得混用锁文件。
- 服务端口、凭据、市场和开关只从环境变量或秘密文件读取，不写入源码。
- 金额、时间和文件路径遵循架构文档：Decimal/最小货币单位、UTC、数据库只存相对路径。
- 每个工作包完成时，必须运行对应测试并更新工作包状态、实际变更、测试结果和遗留问题。
- 每次执行任务前先读取 `HANDOFF.md`，结束前按 `AGENTS.md` 的交接纪律更新 `HANDOFF.md`。

## 数据与秘密

- `.env`、密钥、OAuth/Cookie、数据库文件、转储、媒体、原始响应、缓存和日志均已由 `.gitignore` 排除。
- **备份与回滚**：数据库/媒体/配置的备份位置、校验值、恢复步骤统一记录在 [备份与回滚手册](./docs/BACKUP_AND_ROLLBACK.md)。
- `.env.example` 只包含公开配置名和无效占位值。
- 运行时资产放在 `var/`，数据库中不得保存本机绝对路径或盘符。
- 前端运行时资产必须本地托管，不得引用第三方 CDN。

## 当前可用检查

骨架检查：

```powershell
$required = 'backend','storefront','admin-web','crawler','infra','var','docs'
$missing = $required | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Container) }
if ($missing) { throw "Missing directories: $($missing -join ', ')" }

git check-ignore .env var/media/example.jpg backend/local.sqlite3 storefront/node_modules/example
if ($LASTEXITCODE -ne 0) { throw 'Ignore rules are incomplete.' }

git check-ignore .env.example
if ($LASTEXITCODE -eq 0) { throw '.env.example must remain trackable.' }
```

基础设施端口预检和后端快速测试：

```powershell
& .\infra\scripts\check-dev-ports.ps1

python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements\dev.txt
$env:APP_ENV = 'test'
$env:DEBUG = 'false'
$env:DJANGO_DATABASE_ENGINE = 'sqlite'
$env:DJANGO_SQLITE_PATH = ':memory:'
$env:DJANGO_CACHE_BACKEND = 'locmem'
& .\.venv\Scripts\python.exe backend\manage.py check
& .\.venv\Scripts\python.exe backend\manage.py migrate --noinput
& .\.venv\Scripts\python.exe backend\manage.py test
```

前端冻结安装与生产构建：

```powershell
pnpm install --frozen-lockfile
pnpm build:frontends
```

## 质量门

后端格式、静态检查、迁移和测试：

```powershell
& .\.venv\Scripts\python.exe -m ruff check --config backend\pyproject.toml backend
& .\.venv\Scripts\python.exe -m ruff format --check --config backend\pyproject.toml backend
& .\.venv\Scripts\python.exe backend\manage.py check
& .\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
& .\.venv\Scripts\python.exe backend\manage.py migrate --noinput
& .\.venv\Scripts\python.exe backend\manage.py test
```

前端静态检查、组件测试和构建：

```powershell
pnpm peers check
pnpm lint:frontends
pnpm format:check
pnpm test:components
pnpm build:frontends
```

首次运行浏览器测试需要安装固定 Chromium：

```powershell
pnpm exec playwright install chromium
pnpm test:e2e
```

GitHub Actions 工作流位于 `.github/workflows/ci.yml`。后端、前端或 E2E 任一命令失败都会使对应 CI job 失败；没有配置 `continue-on-error`。
