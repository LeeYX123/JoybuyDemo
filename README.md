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
