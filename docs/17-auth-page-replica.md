# 登录 / 注册页 1:1 复刻方案（含 Google / Facebook）

> 来源：2026-11-24 对 `https://www.joybuy.co.uk/login` 的实测 + 用户 grill 拍板。
> 实测产物：`var/auth_page_20261124/`（`login_live.png`、`login_probe.json`、`login_step2.png`、`login_step2_probe.json`、两个 probe 脚本）。
> 上一轮实测：`var/auth_page_20261119/measurement.md`（本次沿用其配色与字号结论）。

---

## 二次调整（2026-11-24 23:05，用户三条反馈）

| # | 反馈 | 处理 |
|---|---|---|
| 1 | Facebook 按钮不能藏在「View more options」后面，要和 Google 一样直接显示 | 后端 `/oauth/providers` 改为返回**全部支持的渠道 + enabled 标记**（未配置也返回）；前端把两个渠道**并排渲染**，未配置的那个渲染成同款按钮、点击给「该登录方式暂不可用」行内提示（凭据一到位即自动变成真实跳转）。「View more options」保留为真站同款装饰文案，不再承担展开职责 |
| 2 | 去掉英国国旗 icon，国家名改成语言名 | 地区行删掉 Union Jack SVG，可见文案改为**当前语言名**（`English` / `中文（简体）` / `Deutsch`…），原生 select 仍透明覆盖、可真实切换语言 |
| 3 | 退出登录后要重定向到登录页 | `AppHeader.signOut()` 与 `pages/account/index.vue` 的 `signOut()` 在 `logout()` 后统一 `navigateTo('/auth/login')`（原来分别停在原页 / 回首页） |

验证：组件测试 8 例（新增「两个按钮并排 + 未配置点击提示」「地区行显示语言名且无国旗」）通过；
e2e 4 例通过（含退出登录后 `toHaveURL(/\/auth\/login/)`）；storefront 全量 vitest 260 passed。

---

## 实现状态（2026-11-24 21:40–22:10，✅ 已完成）

| 层 | 文件 | 内容 |
|---|---|---|
| 后端 | `accounts_buyers/views.py` `BuyerIdentifierLookupView` | `POST /api/v1/auth/buyer/identifier/lookup`：限流 5 次/60s（命中未命中都计数）、恒定耗时（dummy check_password）、只返回 `{kind, exists}`；禁用账号也按 exists=true |
| 后端 | `config/settings.py` | `IDENTIFIER_LOOKUP_LIMIT` / `IDENTIFIER_LOOKUP_WINDOW_SECONDS` |
| 后端 | `accounts_buyers/urls.py` | 挂 `buyer-identifier-lookup` |
| 前端 | `components/AuthForm.vue` | 三态状态机（identifier / password / register）+ 真站版式（礼包行、分隔、三方按钮、View more options、地区选择器、Feedback、协议行） |
| 前端 | `composables/useBuyerAuth.js` | `loadOAuthProviders()`（供页面在 SSR 阶段 await）、`lookupIdentifier()`（不走写操作后的 refresh） |
| 前端 | `pages/auth/login.vue` / `register.vue` | 页面层 `await useAsyncData(...)` 取渠道后作为 prop 传给组件（避免组件异步 setup 与水合不齐） |
| 前端 | `locales/messages.js` | 5 个 locale 各补 20 个键（含 en 措辞对齐真站：`Email/Mobile`、`Create a password`、`Trusted Quality, Speedy Delivery`） |
| 测试 | `backend/accounts_buyers/tests/test_identifier_lookup.py` | 7 例（存在/不存在/手机号/禁用/非法/CSRF/限流） |
| 测试 | `storefront/tests/auth-form.test.js` | 7 例（三态切换、手机号提示、providers 渲染、直达注册、oauth_error 映射） |
| 测试 | `tests/e2e/auth.spec.js` | 重写 4 例（注册、未知邮箱→注册步、已有账号→密码步+错误、三方按钮） |

### 实现期的实测修正（推翻 §3 两处）

1. **礼包行不在 380 列内**：真站这行约 **640px 宽、单行**，比表单列宽。实现用 `margin-inline: -130px` 越出列宽，
   窄屏（≤720px）回落为多行。
2. **国旗不能用 emoji**：Windows 上 🇬🇧 会渲染成 "GB" 两个字母，改成内联 Union Jack SVG。

### 已知偏差（有意为之）

- 注册步主按钮是 `Create account`（真站为灰色禁用 `Verify email`）——按用户拍板，语义诚实优先。
- 第二步/第三步底部保留协议行（真站注册步只有 Feedback），因为决策 9 要求附属元素全渲染。
- `/auth/register` 直达页保留（真站 404）。
- **密码步版式仍是推断**（无真实账号可实测）：锁定邮箱 + 铅笔 + `Password` + `Sign in`。

### 验证

- 后端：`manage.py test accounts_buyers merchant_ops.tests.test_switch_to_mall` → **61 OK**（含新增 7 例）。
- 前端：`vitest run --config storefront/vitest.config.js` → **249 passed**（含新增 7 例）。
- e2e：`playwright test tests/e2e/auth.spec.js` → **4 passed**。
- 截图：`var/auth_page_20261124/local_login.png`、`local_register.png`；列宽 380、按钮 380×48、x=530 与真站一致。

---

## 1. 先说三条硬事实（都会影响"一模一样"）

1. **真站当前没有 Facebook 按钮**。UK 站实测只有 `Continue with Google` 与 `Continue with JD`。
   用户拍板：**放 Google + Facebook**（迭代02 需求），样式照真站，JD 不出现。
2. **真站是 email-first 两步**：第一屏只有「Email/Mobile + Continue」；点 Continue 后由服务端判断，
   已存在 → 密码步，不存在 → 「Create your Joybuy account」注册步。第二步没有三方按钮、没有忘记密码。
   → 因此**必须有一个"账号是否存在"的接口**（见 §4），这是本次唯一新增的后端面。
3. **本站 /auth/register 是直达页**（真站 `/register` 直接 404），且有 2 个 e2e 依赖它。
   用户拍板：**保留**，让它直接进入"注册步"形态（邮箱可编辑），与登录页共用同一个组件状态机。

## 2. 用户拍板的 12 条（实现时不得擅自改）

| # | 决策 |
|---|---|
| 1 | 第三方按钮 = **Google + Facebook**（真站样式，JD 不渲染） |
| 2 | 登录页与注册页**一起改**（共用 `AuthForm`） |
| 3 | 流程复刻 **email-first 两步**（不是现在的同屏密码） |
| 4 | 三方按钮**接真实后端**，按 `/oauth/providers` 渲染，未配置的渠道不出现 |
| 5 | 新增 **lookup 接口** 判断账号是否存在（接受枚举风险，靠限流兜底） |
| 6 | **保留 `/auth/register` 直达页**（进入注册步，邮箱可编辑） |
| 7 | 输入框保留 **Email/Mobile** 文案；手机号只走密码登录，未注册的手机号提示「请用邮箱注册」 |
| 8 | 注册步主按钮叫 **「Create account」并且可用**（真站那颗是灰色禁用 `Verify email`，此处故意偏离以保持诚实） |
| 9 | 礼包行、View more options、地区选择器、Feedback、协议行 **全部照真站渲染** |
| 10 | 地区选择器 **做成真实可用的语言切换**（复用 `useLocale`） |
| 11 | **移除**第一屏的「忘记密码」入口（真站没有） |
| 12 | `tests/e2e/auth.spec.js` **本轮一并重写**（现有断言已与页面脱节） |

## 3. 实测数据（照抄用）

### 第一屏（`/login`，1440×900）

| 项 | 值 |
|---|---|
| 内容列 | x=530，宽 **380**，页面居中 |
| 标题 | `Sign in to Joybuy or create an account`，18px/700，居中，下距 4 |
| 副标题 | 🔒 `Data encryption`，14px，#6E7078 |
| 礼包行 | `New here? Register on this page to get Welcome Offers + an extra £5 off coupon ⓘ`，`£5` 为 #E1251B |
| label | `Email/Mobile`，16px/400，#1A1A1A，距输入框 8 |
| 输入区 | 容器 380×48，灰底 #F5F6FA；input 356×48，padding `16.5px 14px`，16px |
| 主按钮 | 380×48，bg #1A1A1A，radius 4，18px/600 白 |
| 分隔 | `— or —`，14px/500 #6E7078，两侧细线 |
| 三方按钮 | 380×48，白底 **1px solid #1A1A1A**，radius 4，16px/400，图标为**内联 SVG**（左侧 24px），两个按钮垂直间距 **12** |
| 查看更多 | `View more options`，14px/500 #6E7078 |
| 地区 | `United Kingdom ▾`（🇬🇧 图标 + 14px） |
| 反馈 | `Feedback`（气泡图标 + 14px/500 #1A1A1A） |
| 协议 | `By continuing, you agree to our` + `Privacy & Cookie Policy` / `Terms & Conditions`（12px，#6E7078，链接 12px/500 下划线） |

### 注册步（新邮箱 / 或 `/auth/register` 直达）

| 项 | 值 |
|---|---|
| 标题 | `Create your Joybuy account`，18px/700 |
| 副标题 | `Trusted Quality, Speedy Delivery`，14px #6E7078 |
| Email 行 | label `Email`；容器 380×48 灰底；输入 316×48，文字色 `rgba(0,0,0,.38)`；右侧 40×40 铅笔按钮（点它回到第一步/解锁） |
| 密码行 | label `Create a password`；356×48 白底 **1px #BBBFC4**，聚焦黑 |
| 主按钮 | 380×48；真站为禁用态 #C2C4CC + 白字 18px/600（本站改为可用黑底，文案 `Create account`） |
| 下方 | `Feedback`（无三方按钮、无忘记密码、无协议行） |

### 密码步（无实测，按注册步同版式推断）

真站需要真实已有账号才能进这一屏，本轮**没能实测**（写入假设，不作为"实测值"对外宣称）：
标题沿用第一屏、Email 行锁定 + 铅笔、`Password` 白底描边、主按钮 `Sign in`（黑底可用）、无三方区。

## 4. 新增后端接口：`POST /api/v1/auth/buyer/identifier/lookup`

```jsonc
// 请求
{ "identifier": "buyer@example.com" }   // 邮箱或 E.164 手机号
// 响应 200
{ "kind": "EMAIL", "exists": true }     // kind: EMAIL / PHONE，exists: bool
// 失败
{ "error": { "code": "IDENTIFIER_INVALID" } }   // 400
{ "error": { "code": "IDENTIFIER_LOOKUP_RATE_LIMITED" } }  // 429
```

实现约束（`docs/16` 的安全口径同样适用）：

- 复用 `normalization.normalize_identifier` 与 `rate_limit_key/increment_rate_limit`；
  限流 **5 次 / 60 秒 /（IP + identifier 指纹）**，用 `settings` 变量而非硬编码。
- 响应时间对齐：命中与未命中都做一次 dummy `check_password`，避免靠耗时判断。
- **只返回布尔**，不返回账号 id / 登录渠道 / 注册时间等任何可关联信息。
- 该接口不需要登录，走 `BuyerCsrfAPIView` 的同一套 CSRF 约定（GET 取 token → POST 带 `X-CSRFToken`）。
- 日志不记 identifier 明文（沿用现有的 `rate_limit_key` 指纹思路）。

## 5. 前端改造

`storefront/components/AuthForm.vue` 从"两模式同屏表单"改成**三态状态机**：

```
identifier ──Continue──> lookup ──exists──> password ──Sign in──> /account
    │                             └─not───> register(邮箱锁定) ──Create account──> /account
    └─(/auth/register 直达)──────────────────> register(邮箱可编辑)
```

- `/auth/login` → 初始 `identifier`；`/auth/register` → 初始 `register`（邮箱可编辑）。
- 第二步顶部的铅笔按钮：密码步/注册步（来自 lookup）→ 回到 identifier 并保留已填值。
- 三方按钮**只在 identifier 步**渲染；`/oauth/providers` 为空时整块（含 `— or —`）不渲染。
- 地区选择器接现有 `useLocale`（真实切换），不再单独造一套语言状态。
- `oauth_error` 继续按 `?oauth_error=` 渲染行内错误。
- **文案 key（5 个 locale 都要补：en / zh / de / fr / nl）**：
  `auth.oauth.or`、`auth.oauth.continueGoogle`、`auth.oauth.continueFacebook`、
  `auth.viewMoreOptions`、`auth.region`、`auth.feedback`、`auth.promo`、
  `auth.createAccountTitle`、`auth.createAccountSubtitle`、`auth.emailLabel`、
  `auth.createPasswordLabel`、`auth.submitCreateAccount`、`auth.submitSignIn`、`auth.changeIdentifier`、
  `auth.error.identifierInvalid`、`auth.error.phoneNeedsEmail`、`auth.error.lookupRateLimited`。
- 文案口径按真站各语言版本（zh 用「使用Google账号继续」这类真站措辞，不直译英文）。

## 6. 验收

- 组件测试（vitest）：三态切换、lookup 命中/未命中、手机号未注册提示、三方按钮按 providers 渲染、
  `oauth_error` 映射。出网全部 mock。
- e2e（重写 `tests/e2e/auth.spec.js`）：① 新邮箱 → 注册步 → 创建账号 → 进账户页；
  ② 已有账号 → 密码步 → 错误密码出 alert；③ `/auth/register` 直达 → 注册步。
- 视觉：1440×900 三张截图（identifier / password / register）与真站对应截图逐项比对列宽、按钮尺寸、字号色值。
- 针对性 lint：改动文件的 `eslint` + `prettier --check`。

## 7. 已知风险 / 假设

1. **账号枚举**：lookup 会让外部能判断某邮箱是否注册。已按用户拍板接受，靠 5 次/分钟限流与恒定响应时间缓解；
   若要彻底消除，改回「第二屏统一密码 + 用户自己点创建账户」。
2. **密码步版式无实测**（见 §3），按注册步推断；若有真实账号可登录真站，应补一次实测再定稿。
3. **手机号注册**仍是空白：新手机号只能提示用邮箱注册，不做短信通道。
4. 真站 `/register` 是 404，本站保留直达页，属**有意偏离**（e2e 与站内入口依赖）。
