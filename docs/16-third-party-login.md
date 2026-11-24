# Facebook / Google 登录接入方案（申请 + 接入）

> 目标：购物端登录页在「邮箱 + 密码」之外，增加 **Continue with Google** 与 **Continue with Facebook**。
> 需求来源：`功能需求迭代文档02.md` 13（登录方式保留 Facebook + Google + 邮箱）、平台后台「登录渠道」字段。
> 本文档分两部分：**A. 去哪申请、填什么**（人工，需真实账号）；**B. 代码怎么接**（本仓库具体改法）。
> 编写时间 2026-11-24，控制台界面按当时实测路径描述；Google 控制台近两年改版频繁，菜单名若不一致以「Branding / Audience / Data access / Clients」四个分区为准。

---

## 0. 先明确两个硬约束（决定方案形状）

1. **会话 cookie 是 host-only**（`accounts_buyers/services.py:240` `set_buyer_session_cookie`，不设 domain）。
   所以 OAuth 回调**必须落在商城同一个 host**上，否则 Set-Cookie 到不了浏览器会话。
   本仓库生产 nginx 是单域（`/`→3000、`/api/`→8000），回调走 `/api/v1/auth/buyer/oauth/<provider>/callback` 天然同域；
   本地开发走 Nuxt devServer 的 `/api` 代理（`storefront/nuxt.config.js:41`），回调落在 `localhost:3000` 也成立。
   > 反例：回调写成 `http://localhost:8000/...` 或 `https://api.example.com/...` 就会写错 host。
2. **`buyer_account_has_identifier` 约束要求 email 或 phone 至少有一个非空**（`models.py:49-53`）。
   Google 一定给邮箱；**Facebook 可能不给邮箱**（用户拒绝 `email` 权限，或账号只绑了手机号）。
   **需求已明确：这类用户也要能登录下单**，所以唯一键放成 `(provider, subject)`（Facebook 用其 app-scoped id），
   并把这条约束放宽到「email/phone 二选一 **或** 已绑定三方身份」（见 B1-2）。**不再做补录邮箱的强制页。**

---

## A. 申请凭据

### A1. Google（约 20 分钟，免费，无需企业资质）

准备：一个能长期持有的 Google 账号（建议用公司邮箱并加入同一 GCP 组织），后续它就是这个 OAuth 客户端的 owner。

| 步骤 | 操作 | 关键点 |
|---|---|---|
| 1 | `console.cloud.google.com` → 顶部项目选择器 → **新建项目**，命名如 `joybuy-prod`（建议再建 `joybuy-dev`） | 建完**必须切到新项目**再往下做，否则配到了别的项目上 |
| 2 | 左侧菜单 → **API 和服务 → Google Auth Platform**（老入口叫「OAuth 同意屏幕」）→ 首次进入点 **Get started** | 新版是 4 步向导：App information → Audience → Contact information → Finish |
| 3 | App name（**用户会在授权页看到，填品牌名**）、User support email（要能收信） | 名字后续改动需重新走品牌验证 |
| 4 | Audience（用户类型）→ 选 **External** | Internal 只对同 Workspace 组织成员生效；个人 Gmail 项目没有组织，被迫 External。**这一步建完不能改**，选错只能新建项目 |
| 5 | Contact information → 填运维邮箱 → 勾选同意用户数据政策 → **Create** | |
| 6 | **Data access** → Add or remove scopes → 勾 `openid`、`.../auth/userinfo.email`、`.../auth/userinfo.profile` | 这三个都是 **non-sensitive**，发布时**不需要 Google 验证、不需要安全评估**。只勾这三个，别贪多 |
| 7 | **Branding** → 填 App name、首页 URL、**隐私政策 URL**、服务条款 URL、**Authorized domains**（填生产域名，如 `joybuy.example.com`）、开发者联系邮箱 | 生产发布前必须填齐，否则同意页信息不全、审核会打回 |
| 8 | **Audience** → Test users → Add users，把要联调的 Google 账号加进去 | External 默认 `Testing` 状态，**只有名单内账号能登**（上限 100）；不在名单会报 `Error 403: access_denied` |
| 9 | **Clients** → Create client → Application type 选 **Web application** | 别选 Desktop/iOS/Android，选错就是 `redirect_uri_mismatch` 灾难 |
| 10 | Authorized JavaScript origins：可留空（我们是服务端跳转，不用 JS SDK）；**Authorized redirect URIs 必须逐字填**：<br>`http://localhost:3000/api/v1/auth/buyer/oauth/google/callback`<br>`https://<生产域名>/api/v1/auth/buyer/oauth/google/callback` | 协议、端口、路径、结尾斜杠都要一模一样，**多一个 `/` 就失败**。改动生效可能延迟几分钟到几小时 |
| 11 | Create → **立刻复制 Client ID 与 Client secret**（secret 只在创建时完整显示一次，之后只看得到后四位） | 丢了只能在同一个 client 里「添加密钥」再换，别删 client |
| 12 | 联调通了以后：**Audience → Publish app** 切到 In production | 只有基础身份 scope 时可直接发布、无需验证；不发布会一直停在 Testing（有 testing 警告横幅，且测试名单限制） |

拿到的东西：

```
GOOGLE_OAUTH_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-xxxx
```

已知坑：
- 同一 OAuth client **6 个月无流量会被 Google 自动删除**（提前 30 天邮件通知），生产别用一次性测试项目。
- 授权页要重新出现：`prompt=select_account`（每次选账号）或让用户去 `myaccount.google.com/linkedapps` 撤销。
- 我们**不需要 refresh token**（只取一次 profile），所以不用管 Testing 状态 7 天 refresh token 过期那套限制。

### A2. Facebook / Meta（约 30–60 分钟，开发阶段免费；Live 需合规项齐全）

准备：一个**真实 Facebook 个人账号**（要能收短信/邮箱验证），建议同时有 Meta Business 账号（后续 Business Verification 要用）。

| 步骤 | 操作 | 关键点 |
|---|---|---|
| 1 | `developers.facebook.com` → 右上角 Get Started，用个人 FB 账号注册开发者 | 需验证邮箱/手机；建议直接开启两步验证，否则部分功能被限制 |
| 2 | My Apps → **Create App** → 填 App name（**登录对话框里会显示**）+ App contact email | Business portfolio 这步可以先 Skip |
| 3 | Use case 选 **「Authenticate and request data from users with Facebook Login」** | **只选这个**。选「Manage everything on your Page」之类会带一堆用不上的权限，且 **use case 加了就不能删** |
| 4 | Dashboard → Use cases → 该用例 → **Customize** → Settings：Client OAuth Login = On、Web OAuth Login = On、**Enforce HTTPS = On**、Valid OAuth Redirect URIs 填 `https://<生产域名>/api/v1/auth/buyer/oauth/facebook/callback` | 开发阶段 `http://localhost:*` 的回调 Meta **自动放行**，不必登记；一旦切 Live 就必须 https（本地想继续用就换 tunnel 域名，或让 dev 继续用 Development 模式的独立 App） |
| 5 | App settings → **Basic**：App ID、App Secret（点 Show，需输 FB 密码）、App Domains（只填域名，**不带协议**）、Privacy Policy URL、Terms of Service URL、App Icon、Category | Privacy Policy / Data Deletion / Icon / Category 是**切 Live 的硬性前置**，缺一个就卡在 Development |
| 6 | 权限：确认 `public_profile` + `email` 已授予 | 这两个**不需要 App Review**（官方明确「do not require app review and are automatically granted」）。任何超出这两个的权限才要 review + 录屏 + 用途说明 |
| 7 | App roles → Roles → 加 **Administrator / Developer / Tester** | **Development 模式下只有这些角色能登录**。本地联调必须把自己的测试 FB 账号加成 Tester，否则登录页直接报「App not active」 |
| 8 | 切 **Live**（右上角 App Mode 开关）：需补齐上面第 5 步合规项；如果后续申请高级权限，还要 **Business Verification**（营业执照等） | 只做登录的话，Live 后所有 FB 用户都能登，无需 review |
| 9 | Data Deletion：Live 前要填 **Data Deletion Instructions URL**（可指向你的隐私说明页），否则审核/上线受阻 | |

拿到的东西：

```
FACEBOOK_OAUTH_APP_ID=1234567890
FACEBOOK_OAUTH_APP_SECRET=xxxxxxxx
```

已知坑 / 必须记住的语义差异：
- **`id` 是 app-scoped**：同一个人在不同 App 里 ID 不同。所以 dev 与 prod 用两个 App 时，**用户不能跨环境复用**（本来也是两套库，问题不大）；但也意味着不能拿 FB ID 跟别处对账。
- **不返回 `email_verified`**，Graph API 没有任何验证标记字段；而且 `email` **可能为空**（用户取消勾选，或账号只绑手机）。→ 见第 3 节的合并策略。
- 错误 `URL Blocked: this redirect failed because it's not in the app's allowed redirect URIs` = 回调没登记或差一个字符；`App not active` = App 还在 Development 且你不是角色成员。
- 国内网络：控制台、`facebook.com/dialog/oauth`、`graph.facebook.com` 都需要可达；**服务端换 token 也要出网**，国内服务器要配代理出口（见 3.6）。

---

## B. 代码接入（本仓库具体改法）

### B1. 数据模型：新增 `BuyerIdentity`（migration 0008）

不要往 `BuyerAccount` 上加 `google_sub` / `fb_id` 两列 —— 一个账号可能先后绑定多个渠道，而且以后加渠道就要改表。
新建一张身份表，`(provider, subject)` 唯一：

```python
class BuyerIdentity(models.Model):
    class Provider(models.TextChoices):
        FACEBOOK = "FACEBOOK", "Facebook"
        GOOGLE = "GOOGLE", "Google"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey(BuyerAccount, on_delete=models.CASCADE, related_name="identities")
    provider = models.CharField(max_length=16, choices=Provider.choices)
    subject = models.CharField(max_length=191)          # Google sub / Facebook app-scoped id
    email_snapshot = models.EmailField(null=True, blank=True)
    display_name = models.CharField(max_length=120, blank=True, default="")
    avatar_url = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "buyer_identity"
        constraints = [models.UniqueConstraint(fields=["provider", "subject"], name="buyer_identity_unique")]
```

`BuyerAccount.password` 存 `make_password(None)`（Django 的 unusable password），保证 `check_password` 永远为 False，
这样 OAuth 账号无法用「猜密码」路径登录，也不会破坏 `password` 非空字段。

#### B1-2. 放宽 `buyer_account_has_identifier`（**无邮箱账号能建号的前提**）

现有约束（`models.py:49-53`）要求 `email` 或 `phone_e164` 至少一个非空。Facebook 允许用户不给邮箱，
若不放宽这条，**「没邮箱也能下单购物」这个需求在 DB 层就不成立**。

做法：给 `BuyerAccount` 加一个去规范化的布尔列，把不变量从「必有标识」改成「必有标识**或**已绑定三方身份」：

```python
# BuyerAccount 新增字段
identity_bound = models.BooleanField(default=False)

# 约束改为
models.CheckConstraint(
    condition=(Q(email__isnull=False) & ~Q(email=""))
    | (Q(phone_e164__isnull=False) & ~Q(phone_e164=""))
    | Q(identity_bound=True),
    name="buyer_account_has_identifier",
)
```

迁移 0008 一次做完：`AddField(identity_bound)` → `RemoveConstraint(buyer_account_has_identifier)` →
`AddConstraint(新条件)` → `CreateModel(BuyerIdentity)`。建 OAuth 账号时在**同一事务**里
`identity_bound=True` + 写 `BuyerIdentity`，两者不会脱节。

为什么不选另外两条路：
- **不删约束、只在应用层校验**：丢掉 DB 兜底，以后任何一个建号入口漏判就会写进「无标识也无身份」的孤儿账号。
- **塞假邮箱**（如 `fb_<sub>@facebook.invalid`）：会污染后台列表与 CSV 导出、可能被误用于发信、
  还会跟真实的「同邮箱合并」逻辑打架。`.invalid` 虽然不会真发出去，但没必要的复杂度。

> MySQL / SQLite 的唯一索引都允许多行 `NULL`，所以 `email` 继续保持 `unique=True, null=True` 即可，
> 多个无邮箱账号不会互相冲突，**不需要**动 `email` 的唯一约束。

### B2. 后端接口（挂在 `accounts_buyers/urls.py`，全部是 GET 跳转，只有 start/callback）

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/v1/auth/buyer/oauth/providers` | 返回 `[{provider, enabled, start_url}]`；**前端按它渲染按钮**，凭据没配时不出现死按钮 |
| GET | `/api/v1/auth/buyer/oauth/<provider>/start?next=/account` | 生成 state + PKCE → 302 到授权页 |
| GET | `/api/v1/auth/buyer/oauth/<provider>/callback?code&state` | 校验 state → 换 token → 取 profile → 建/查身份 → 建 session → 302 回商城 |

> 没有「补录邮箱」接口：Facebook 拿不到邮箱时**直接建号登录**（见 B3 第 3 条），不需要用户多填一步。

要点：
- 这两个 GET **不能被 `csrf_protect` 拦**（`BuyerCsrfAPIView` 只对不安全方法校验，GET 天然通过）；安全性完全靠 `state` + PKCE。
- `state` 用 `secrets.token_urlsafe(24)`，存 cache（`oauth:state:<state>`，TTL 600s），**callback 里取出即删**（参考现有 `consume_merchant_handoff_token` 的一次性写法）。
- `next` 必须校验：只接受以 `/` 开头且不以 `//` 开头的站内路径（沿用 `AuthForm.vue:35-41` 的白名单规则），否则就是开放重定向。
- 换 token / 取 profile 用 **stdlib `urllib.request`**，与 `backend/merchant_ops/crisp_mirror.py:143` 的 `_http_request` 写法一致 —— 现有 requirements 里没有 `requests`，不要为一个 OAuth 引依赖。
- 所有失败都以 **302 回 `/auth/login?oauth_error=<code>`** 收尾，不要把 provider 原始报错甩给用户（`docs/06` 也要求日志不含 code/token）。

授权 / token 端点（写进常量，别散落）：

```
Google  authorize : https://accounts.google.com/o/oauth2/v2/auth
        token     : https://oauth2.googleapis.com/token
        userinfo  : https://openidconnect.googleapis.com/v1/userinfo
        scope     : openid email profile

Facebook authorize: https://www.facebook.com/<VER>/dialog/oauth          # FACEBOOK_GRAPH_VERSION
         token    : https://graph.facebook.com/<VER>/oauth/access_token
         profile  : https://graph.facebook.com/<VER>/me?fields=id,name,email,picture.type(large)
         scope     : email,public_profile    # 注意：FB 用逗号分隔，Google 用空格
```

### B3. 账号查找与登录判定（唯一键 = provider + subject）

按 `(provider, subject)` 查 `BuyerIdentity`：

1. **命中** → 直接登录（`last_login_at` 更新，`BuyerAccount.auth_provider` 保持首次来源不变）。
2. **未命中，且 provider 返回了已确认邮箱**：
   - Google：`email_verified == true` 且本地存在同邮箱账号 → 可绑定后登录。
   - Facebook：**不自动合并**。Graph 不提供验证标记，且 FB 邮箱可被用户改成任意未验证地址；自动合并等于送一个「抢注他人邮箱 → 接管账号」的洞。走「该邮箱已注册，请先用邮箱密码登录后在账户设置里绑定」的提示。
3. **未命中，且没有邮箱**（Facebook 常见）→ **直接建号并登录，不弹补录页**：
   ```python
   BuyerAccount(email=None, phone_e164=None, identity_bound=True,
                auth_provider=BuyerAccount.AuthProvider.FACEBOOK,
                password=make_password(None))
   BuyerIdentity(provider=FACEBOOK, subject=fb_id, email_snapshot=None, ...)
   ```
   `display_name` 交给现有 `_ensure_display_name`（生成 `user4323txlb` 格式并固定存库），
   `purchase_whitelisted` 走默认 True、`status=ACTIVE` → **可以正常加购、结账、下单**。
4. **账号被禁用**（`status != ACTIVE`）→ 302 带 `oauth_error=disabled`，不建 session。

> **已拍板（2026-11-24）**：
> - 唯一键 = `(provider, subject)`。**Facebook 的 ID 就是这类用户的账号唯一标识**，不依赖邮箱存在。
> - Google `email_verified == true` 且本地存在同邮箱账号 → **自动合并并绑定**；Facebook 一律不自动合并。
> - **允许账号没有邮箱**，登录后照常购物（不强制补录）。这一点直接决定 B1-2 的约束放宽。

#### B3-1. 无邮箱账号的连带影响（已逐处核查代码）

| 位置 | 现状 | 必须的处理 |
|---|---|---|
| `notifications/services.py:126-129` | `recipient=order.account.email`，`order.account.email.split("@")[0]` | 无邮箱时 `None.split` 抛异常。该方法有 try/except 兜底（订单取消不会失败），但**通知会静默丢失且日志刷错**。改为 `if not email: logger.info(...); return 0` |
| `merchant_ops/views_buyers.py:20,23` | `account.email or phone or ""` / `..., or "买家"` | 后台列表会显示空白账号名。fallback 改用 `account.display_name`（已固定存库） |
| `merchant_ops/views_buyers.py:75,246` | 只按 `email` / `phone_e164` 模糊搜 | 无邮箱用户在后台搜不到。补 `Q(display_name__icontains=query)` |
| `BuyerLoginSerializer` | 按 email / phone 查账号 | 无邮箱账号查不到 → 只能 SSO 登录，**这是正确行为**，不要为它开特例 |
| `storefront/pages/auth/forgot-password.vue:2` | 明确是 stub（不走后端） | 不用改；将来实现时，对无邮箱账号提示「请用 Facebook 登录」 |
| `orders` / `checkout` / `cart` 后端 | grep 确认**不读** buyer.email | 不影响下单，无需改动 |
| 会话、余额、白名单 | 全部按 `account.public_id` | 与邮箱无关，无需改动 |

#### B3-2. 已知的账号分裂（接受，不阻塞）

- 同一人**先用 Facebook（无邮箱）登录、后又用 Google 登录** → 会成为两个独立账号。
  Facebook 没给邮箱，系统没有任何可比的键，强行按「姓名/头像」猜合并只会制造误合并。
  要解决只能做「登录后在账户设置里手动绑定另一渠道」，属后续迭代。
- Facebook 下次授权时**若返回了邮箱**，可做一次温和回填：`account.email is None` 且该邮箱未被占用
  → 写入 `account.email`（唯一冲突则跳过并记日志）。可选优化，不做默认强行为，避免改坏已登录账号。

合并实现约束（不可省）：
- 合并/建号只在**同一事务**内完成：建 `BuyerIdentity` → 置 `identity_bound=True` → 更新 `last_login_at` → 建 session；
  中途失败整体回滚，不留半绑状态。
- **不覆盖**已有账号资料：`auth_provider` 保持首次来源（后台「登录渠道」看的是入口来源，不是最后一次），
  `display_name`（需求 13.5-6 已固定存库）、`balance`、`purchase_whitelisted` 一律不动。
- 必须**留痕**：Django log 打一条 `buyer_identity_linked provider=GOOGLE account=<public_id>`（不含 email 明文、不含 token）。
- **已知风险（用户已接受）**：本仓邮箱注册不发验证码（`BuyerEmailRegisterView` 直接把 `email_verified_at` 置为 now，
  等于「假定已验证」），所以别人可以先用你的 Gmail 地址注册本地账号，等你用 Google 登录时就并进那个账号。
  缓解措施（后续迭代，不阻塞本次接入）：给邮箱注册补真实验证码，让 `email_verified_at` 变成可信字段。

### B4. 环境变量（写进 `.env` / `.env.example` / 生产 compose）

```
OAUTH_REDIRECT_BASE_URL=http://localhost:3000        # 生产填 https://<域名>，必须与回调登记逐字一致
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
FACEBOOK_OAUTH_APP_ID=
FACEBOOK_OAUTH_APP_SECRET=
FACEBOOK_GRAPH_VERSION=v23.0                          # 用申请时的最新版本，集中一处
OAUTH_STATE_TTL_SECONDS=600
```

`settings.py` 里按现有 `os.getenv` 风格读取，并派生：
`def oauth_enabled(provider)` 判断 client_id/secret 是否都非空 → 决定 `/providers` 返回什么。
未配置的 provider 直接 503，前端不渲染按钮（本地没凭据也能正常开发其余功能）。

### B5. 前端改动

| 文件 | 改动 |
|---|---|
| `storefront/components/AuthForm.vue` | 表单下方加「或」分隔 + 两枚按钮（Google / Facebook 官方品牌样式，图标用本地 SVG，禁止外链 CDN）；点击 `window.location.href = start_url`。同时兜住 `route.query.oauth_error` → 行内错误文案 |
| `storefront/composables/useBuyerAuth.js` | 加 `listOAuthProviders()`（GET `/oauth/providers`），或直接把 providers 塞进 session payload 少发一次请求 |
| `storefront/locales/messages.js` | 新增 `auth.oauth.continueGoogle / continueFacebook / or / error.state / error.emailExists / error.disabled / error.provider` —— **en / zh / de / fr / nl 五个 locale 都要补**，漏一个会显示 key 名 |

**没有补录页**：Facebook 无邮箱时后端直接建号，前端不需要 `/auth/complete-profile`，改动只有上面 3 处。

回调成功后的状态同步：`useBuyerAuth` 的 session 是 `useState` 共享的，跨整页跳转（302 回站内）会重新 SSR，天然拿到新 cookie；
若走 SPA 内部跳转需显式 `await refresh()`。

### B6. 出网（国内环境必看）

- 浏览器侧：授权页域名（`accounts.google.com` / `facebook.com`）必须可达，这是**用户浏览器**的网络问题，无法用服务端代理绕过。
- 服务端侧：`oauth2.googleapis.com`、`graph.facebook.com` 必须可达。国内 ECS 默认不通，需：
  - 给 Django 进程注入 `HTTPS_PROXY`/`HTTP_PROXY`，或
  - 走境外跳板/专线出口，或
  - 生产部署在境外区域。
  这块如果没打通，表现是「用户授权完回跳，停在登录页并报 provider 错误」，而浏览器一切正常 —— 排查时先看后端出网。

---

## 3. 分批实施计划

| 阶段 | 内容 | 交付物 | 验证方式（按本仓验证纪律，只做针对性验证） |
|---|---|---|---|
| P0 | 人工申请 4 个凭据 + 登记 2 个回调地址（A1/A2） | 凭据写进 `.env`，回调地址进文档 | 控制台截图留档 |
| P1 | `BuyerIdentity` + 迁移 0008（含放宽 `identity_bound` 约束）+ `oauth.py`（providers/start/callback）+ settings | 后端可用 | `pytest backend/accounts_buyers/tests/test_oauth_api.py`（**mock provider 的 token/profile 接口**，不打外网），覆盖：state 复用/过期、next 非法、**无邮箱建号成功**、禁用账号、同邮箱合并/不合并、无邮箱账号下单前置条件 |
| P2 | 登录页按钮 + providers 接口 + 5 locale 文案 + 无邮箱账号的后台展示/搜索兜底 | 前端可点 | `vitest run storefront/tests/auth-*.test.js`；`prettier --check` + `eslint` 改动文件 |
| P3 | 真机联调 | 可登录 | 用一个 Google 测试账号 + 一个 FB Tester 账号各走一遍真流程；**再用一个只绑手机号的 FB 账号**（授权时取消 email 勾选）验无邮箱建号 |
| P4 | 生产开关 | 上线 | 生产回调地址与 `OAUTH_REDIRECT_BASE_URL` 逐字核对；后台用户列表「登录渠道」显示 FACEBOOK/GOOGLE（`merchant_ops/views_buyers.py:25` 已支持，无需改） |

验收清单：
- [ ] 三种入口（邮箱 / Google / Facebook）都能进 `/account`，头部显示名正确
- [ ] 同一 Google 账号二次登录不再建号（`buyer_identity` 只有 1 行）
- [ ] **无邮箱的 Facebook 账号能建号并登录**：`buyer_account.email IS NULL`、`identity_bound=1`、
      `buyer_identity` 有对应 `(FACEBOOK, <app-scoped id>)`、`display_name` 形如 `user4323txlb`
- [ ] **该无邮箱账号能加购 + 下单**（`purchase_whitelisted` 默认 True，结账不读 email）
- [ ] 该账号被取消订单时 `notify_order_canceled` 不抛异常（日志里是 skip 而不是 traceback）
- [ ] 后台用户列表能按 `display_name` 搜到该账号，账号列不显示空白
- [ ] 被 `DISABLED` 的账号走 SSO 登录被拒
- [ ] `next=/account` 生效；`next=//evil.com` 被拒
- [ ] 生产 cookie 是 host-only + HttpOnly + Secure，`/auth/buyer/session` 返回 `auth_provider=GOOGLE/FACEBOOK`
- [ ] 后端日志中无 `code=` / `access_token` / client_secret

---

## 4. 已知坑汇总（照着避）

1. **回调必须同域**：写成 `:8000` 或独立 API 域 → cookie 写不进商城，表现是"登录成功又回登录页"。本地因 cookie 不区分端口，localhost:8000 也会"看起来能用"，但生产必炸 —— 别在本地验证通过就以为对了。
2. **Facebook 可能没有邮箱**：唯一键必须是 `(provider, subject)`，且 `buyer_account_has_identifier` 约束要先放宽
   （否则建号直接被 DB 拒）。App 返回的 `email` 也不可信，**不能作为合并依据**。
2b. **无邮箱账号会踩到的现成代码**：`notifications/services.py:126` 的 `email.split("@")`（None 崩）、
   `merchant_ops/views_buyers.py:20,23` 的空白账号名与 `:75,246` 搜不到人。这三处不改，功能"能登录"但后台和通知都残缺。
3. **Facebook 的 `id` 是 app-scoped**，dev/prod 两个 App 之间不通用；它只是 identity 表的去重键，
   **对外仍是 `BuyerAccount.public_id`**，别把 FB ID 泄露到 URL / 前端 payload。
4. **Facebook Development 模式只有角色成员能登**，测试账号没加 Tester 会看到 "App not active"。
5. **Google External 默认 Testing**，测试账号没加到 Test users 会 403 access_denied；上线记得 Publish。
6. 回调地址**逐字匹配**，多斜杠、http/https、端口不同都失败；Google 侧改动有分钟级延迟。
7. `public_profile` + `email` 免 review，**别顺手申请更多权限**——会把上线周期从 0 天拖成数周。
8. 不要为 OAuth 引 `requests`/`google-auth`：本仓库后端出网统一 stdlib `urllib.request`。
9. 一次性 `state` 必须取出即删，并且**校验 provider 是否与签发时一致**（防止拿 A 渠道的 state 走 B 渠道回调）。
10. 国内服务器出网不通时，症状只在回跳之后出现，浏览器端没有任何报错线索。
