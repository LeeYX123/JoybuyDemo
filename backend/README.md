# Backend

Django 5.2 LTS、Django REST Framework 和后续 Celery 领域服务目录。MySQL 与 Redis 是默认运行后端；SQLite 和内存缓存仅用于本地无容器的快速测试。

## 环境准备

从仓库根目录执行：

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements\dev.txt
Copy-Item .env.example .env
# 编辑 .env 中的 CHANGE_ME 值
```

启动 `infra/compose.dev.yml` 后执行：

```powershell
& .\.venv\Scripts\python.exe backend\manage.py migrate
& .\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

接口入口：

- API 根：<http://127.0.0.1:8000/api/v1/>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- 买家会话与 CSRF 令牌：<http://127.0.0.1:8000/api/v1/auth/buyer/session>

健康检查同时执行数据库 `SELECT 1` 和 Redis 缓存读写，任何一项失败都会返回 HTTP 503。

## 买家账户 API

WP-05 提供与 Django 管理员/后续员工认证相互独立的买家账户和 Cookie 会话：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/auth/buyer/session` | 获取登录状态及 CSRF 令牌 |
| `POST` | `/api/v1/auth/buyer/verification-codes` | 发送注册验证码 |
| `POST` | `/api/v1/auth/buyer/register` | 使用邮箱或 E.164 手机号注册并登录 |
| `POST` | `/api/v1/auth/buyer/login` | 使用邮箱或手机号及密码登录 |
| `POST` | `/api/v1/auth/buyer/logout` | 吊销当前买家会话并清除 Cookie |

先请求会话接口取得响应体中的 `csrf_token` 和 CSRF Cookie；所有 `POST` 请求都必须携带同源 Cookie，并通过 `X-CSRFToken` 请求头提交该令牌。买家会话使用专用的 `joybuy_buyer_session` HttpOnly Cookie，不会接受 Django 员工会话 Cookie。

开发和测试环境默认在验证码响应中返回 `test_code`，便于自动化测试；非开发环境禁止开启 `VERIFICATION_CODE_TEST_MODE`。当前生产发送通道只支持配置 SMTP 后发送邮件，手机短信适配器尚未接入，未配置的通道会返回 HTTP 503。会话令牌与验证码原文均不会写入数据库。

买家认证的可调参数位于根目录 `.env.example`，包括独立 HMAC 密钥、会话与验证码有效期、验证码尝试次数、发送限流和登录失败限流。生产环境必须使用彼此独立且不同于 `DJANGO_SECRET_KEY` 的 HMAC 密钥。

## 员工认证、RBAC 与 TOTP

WP-06 提供独立于买家和 Django 管理站点的员工认证边界：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/admin/auth/session` | 获取员工登录状态及 CSRF 令牌 |
| `POST` | `/api/v1/admin/auth/login` | 密码及按需 TOTP 登录 |
| `POST` | `/api/v1/admin/auth/logout` | 吊销当前员工会话 |
| `GET` | `/api/v1/admin/rbac/me` | 获取当前员工的全局角色和权限 |
| `PUT` | `/api/v1/admin/staff/{staff_id}/roles` | 需要 `staff.roles.manage` 权限，更新角色并写审计日志 |

员工使用专用 `joybuy_staff_session` HttpOnly Cookie，Django 管理站点使用 `joybuy_django_session`，买家则使用 `joybuy_buyer_session`。所有管理写接口必须提交 CSRF 令牌。角色分配审计会记录操作者、请求 ID、IP、原因及变更前后角色。

数据库迁移会创建 `platform_admin` 和 `platform_auditor` 两个系统角色，以及 `staff.roles.manage`、`audit.logs.view` 权限。首次部署后使用交互式命令创建初始平台管理员：

```powershell
& .\.venv\Scripts\python.exe backend\manage.py bootstrap_platform_admin `
  --email admin@example.test `
  --display-name "Platform Admin"
```

命令会安全地提示输入密码，并仅在本次执行中显示 TOTP Base32 密钥和 `otpauth://` URI。立即将其加入验证器；平台管理员没有已配置的 TOTP 设备时不能登录。TOTP 密钥使用 `STAFF_TOTP_ENCRYPTION_KEY` 加密后存储，验证码不可重放。

员工会话 HMAC 密钥、TOTP 加密密钥、会话时长、时间步容差和登录限流配置均列在根目录 `.env.example`。生产环境要求员工会话和 TOTP 使用彼此独立且不同于 `DJANGO_SECRET_KEY` 的密钥。

本地开发可设 `STAFF_TOTP_LOGIN_ENFORCED=false` 跳过验证器（密码直登，会话标记为已验证）；生产保持默认 `true` 强制 TOTP。

## 商家领域基础

WP-07 新增 `merchants` 领域模块，提供：

- 商家类型、不可枚举公开 ID、入驻状态以及商家级员工 TOTP 开关；
- 店铺范围内的成员关系、角色和权限，同一员工可在不同商家拥有不同角色；
- `merchant_owner`、`merchant_catalog_manager`、`merchant_viewer` 三个系统角色；
- 成员管理、商品管理和订单查看三个租户权限；
- 来源卖家到本地虚拟商家的幂等映射服务；
- 缺失来源卖家时使用固定系统商家“Joybuy 自营导入”。

租户权限必须同时满足：商家处于 `ACTIVE`、成员关系处于 `ACTIVE`，且该商家内的角色拥有所需权限。平台全局角色不会隐式获得店铺身份；平台侧未来管理 API 使用独立的 `merchants.manage` 权限。

导入服务通过 `merchants.services.resolve_import_merchant` 调用。`source_system + source_seller_id` 是稳定映射键；相同来源卖家重复导入只更新来源元数据，不覆盖本地商家展示名；不同来源即使卖家 ID 相同也不会自动合并。商家管理 API、商家端页面、订单履约和经营分析不属于本工作包。

## 类目、品牌与属性基础

WP-08 新增 `catalog` 领域模块。来源类目采用两层结构：`SourceCategory` 保存稳定的来源标识，`SourceCategoryTreeVersion` 与 `SourceCategorySnapshot` 保存每次不可变的树结构、名称、父子关系和来源 URL。版本键相同且内容相同的导入是幂等的；版本键相同但结构不同会被拒绝。

本地导航使用独立的 `LocalCategory` 树，`CategoryMapping` 将本地类目映射到稳定来源标识，而不是某个快照。因此来源类目改名、移动或暂时消失不会自动重排本地导航。树服务入口包括：

- `catalog.services.save_source_category_version`：验证父节点、重复 ID 和环后原子发布新版本；
- `catalog.services.source_category_descendants`：查询指定来源版本内的完整子树；
- `catalog.services.create_local_category`：创建并维护本地物化路径；
- `catalog.services.move_local_category`：移动节点并原子更新所有后代路径和深度；
- `catalog.services.local_category_descendants`：查询本地导航子树。

目录模块同时提供品牌规范化去重、SPU/SKU 属性定义、单选/多选属性选项以及本地类目属性关联。平台管理员已获得 `catalog.taxonomy.manage` 权限。类目管理 API/UI、商品属性值和 Offer 不属于本工作包。

## 商品、Offer 与库存

WP-09 新增商品与销售模型。`catalog` 侧：`Spu`、`SpuTranslation`（locale 标题/副标题/详情）、`SpuSourceIdentity`、`Sku`（规格 JSON 及其规范化签名，SPU 内组合唯一）、`SkuSourceIdentity`。`offers` 侧：`Currency`、`Market`（迁移预置 `GBP`/`GB`，`Europe/London`）、`Offer`（merchant+sku+market+currency 组合唯一、Decimal 金额、`local_inventory` 默认 9999、`source_availability` 与本地库存分离）、`OfferSourceIdentity`、`PriceSnapshot`、`InventoryLedger`。

导入入口：

- `catalog.product_services.get_or_create_spu_from_source` / `get_or_create_sku_from_source`：按 `source_system + source_id` 幂等，SKU 规格经属性定义校验并生成规范化签名；
- `offers.services.import_offer_from_source`：金额只接受 Decimal 兼容字符串并按币种精度量化（拒绝浮点），同一观察时间幂等，价格写入快照；
- `offers.services.adjust_offer_inventory`：调整库存必须带幂等键，行锁下更新余额并写流水，余额不可为负。

所有金额列都是 `Decimal(18,4)`，`list_price >= current_price` 由数据库 CHECK 强制。

## 来源值与本地覆盖层

WP-10 提供可编辑字段的两层数据：`effective_value = approved_local_override ?? latest_source_value`。

- `catalog.override_services.apply_source_field_values(target, values, source_system=...)`：爬虫只写来源层 `SourceFieldValue`，按字段幂等并记录观察时间；`mark_source_fields_missing` 标记来源消失但保留行。
- `propose_local_override` / `review_local_override` / `clear_local_override`：覆盖写入 `LocalFieldOverride`（PENDING/APPROVED/REJECTED/CLEARED），每次变更递增版本并写 `LocalFieldOverrideVersion` 历史与审计日志；只有 APPROVED 覆盖生效，重新提议立即回退来源值并等待重新审核。
- `resolve_effective_value(s)` / `list_override_diffs`：解析最终有效值并输出来源值、覆盖值与差异。

字段注册表首期包含 `SpuTranslation` 的 `title/subtitle/description` 和 `Offer` 的 `promotion_label/current_price/list_price`；价格覆盖复用 WP-09 的金额校验。覆盖管理 API/UI 属于 WP-31。

## 媒体存储与变体

WP-11 新增 `media` 模块：`MediaAsset`（SHA-256 唯一）、`MediaVariant`（asset+preset+format 唯一）、`MediaUsage`（按角色关联业务对象）。存储为内容寻址：`{products|reviews|cms|icons|fonts}/original/{aa}/{bb}/{sha256}.{ext}`，数据库只存正斜杠相对路径，`media.storage.media_url` 生成 `/media/<path>` 本地地址；`resolve_media_path` 拒绝路径逃逸。相同字节全局只存一份。

- `media.storage.store_bytes(data, kind=..., mime_type=...)`：保存并按需提取图片宽高；图片解码失败不丢内容。
- `media.variants.ensure_image_variants(asset)`：生成 thumb/card/detail 三档 WebP+AVIF（Pillow 原生 AVIF），不放大原图，幂等重跑；衍生文件同样按内容哈希寻址。
- `media.variants.link_asset_to_object(asset, target, role=...)`：幂等记录用途。

开发环境 `DEBUG=true` 时 Django 直接提供 `/media/` 文件服务；生产由 Nginx 提供。视频转码接口与 FFmpeg 流水线属于 WP-18。

## 评价与虚拟用户

WP-12 新增 `reviews` 模块：`VirtualReviewer`、`Review`、`ReviewVersion`、`ReviewMedia`。来源评价人只以 `HMAC-SHA256(SOURCE_FINGERPRINT_HMAC_KEY, source_system + 稳定公开标识)` 指纹去重，不保存可逆来源标识；没有稳定标识的评价不创建虚拟用户，只在评价行保留来宾展示快照，昵称相同不合并。虚拟评价用户不能登录，也不与真实买家合并。

- `reviews.services.upsert_source_review(spu, source_system=..., source_id=...)`：按来源身份幂等；内容哈希变化时先在 `ReviewVersion` 保存旧内容再更新当前值；评分限定 1–5；`likes_count` 为 `NULL` 表示来源未展示。
- `mark_source_review_deleted`：来源删除软删除并记录 `deleted_at`，历史保留、前台按状态过滤；来源重新出现自动恢复。
- `attach_review_media`：评价图片/视频引用 WP-11 的 MediaAsset，幂等。

评价采样策略（默认 50、1–300、分层采样）属于 WP-17；本站真实评价首期不产生，仅保留 `origin` 标记。

## 爬虫控制与导入流水线

WP-13 至 WP-19 构成阶段 C 的服务端部分（运行基座见 `crawler/README.md`）：

- `crawler_control`：账号会话（Fernet 加密，拒绝密码类字段）、`CrawlJob/CrawlRun` 状态机、原始响应 gzip 归档（30 天保留，到期只删文件保留哈希）、`StagingProduct` 受控暂存；
- `crawler_control.import_services`：staging → SPU/SKU/Offer 幂等导入，卖家映射走 `merchants.services.resolve_import_merchant`，来源值只写 WP-10 来源层；
- `crawler_control.quality_services`：批次质量闸门（缺失率阈值，FAILED 冻结批次并按策略暂停）、完整刷新疑似失效跟踪（连续 2 次确认才 UNAVAILABLE）、全局熔断（窗口内 2 个账号命中风控即熔断，人工重置）、REJECTED 行重放；
- `reviews.import_services`：确定性分层采样导入（媒体优先、近期优先、seed 可复现），消失评价软删除、重现自动恢复。

## 验证

```powershell
& .\.venv\Scripts\python.exe backend\manage.py check
& .\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
& .\.venv\Scripts\python.exe backend\manage.py test
```

在没有 Docker 的机器上可用 SQLite 和内存缓存运行基座测试；这不是生产配置：

```powershell
$env:APP_ENV = 'test'
$env:DEBUG = 'false'
$env:DJANGO_DATABASE_ENGINE = 'sqlite'
$env:DJANGO_SQLITE_PATH = ':memory:'
$env:DJANGO_CACHE_BACKEND = 'locmem'
& .\.venv\Scripts\python.exe backend\manage.py migrate --noinput
& .\.venv\Scripts\python.exe backend\manage.py test
```

## 边界

- 业务模块必须遵守 `docs/03-architecture.md` 的领域边界。
- 爬虫不得从 spider 直接散写业务表，应通过 staging 或导入服务。
- API 错误使用统一 JSON 结构并返回 `X-Request-ID`。
- 本地上传、原始响应、数据库和缓存文件不进入版本控制。

