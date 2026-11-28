/* eslint-disable no-undef, no-irregular-whitespace */
// ---------------------------------------------------------------------------
// folio/api.js — 商家端手机版（folio 静态稿直copy 架构）的数据层。
//
// 渲染代码 = 静态稿原码（base-1..4.js + merchant-mobile.js）。本文件只做两件事：
// 1. 把真实 API 响应映射成静态稿全局状态对象的同构字段（products/orders/
//    conversations/systemNotices/withdrawals/balance/...）；
// 2. 用真实 API 版本覆盖静态稿的「动作函数」与「演示持久化」（save/persistV2/
//    OrderLifecycle 模拟轮询/PBKDF2 本地哈希/CSV 导出/演示审核件）。
// 渲染函数与模板字符串除「数据槽位」外一行未动。
// ---------------------------------------------------------------------------
import {
  apiRequest,
  merchantWrite,
  merchantUpload,
  setCurrentShop,
  getCurrentShop,
} from '../lib/api.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

// 商城（storefront）地址：单一来源。
// 优先级：构建期 VITE_STOREFRONT_URL > 按 host 推导 > 兜底产线 www。
// 使用点：①头部「切换去商城」redirect_url 缺字段时的兜底；②未登录/登出/
// 空店铺回商城（商家端不再提供登录表单，进商家端唯一入口是购物端
// 【切换商家端】→ POST /account/merchant-console-session 签发 staff 会话）。
export function storefrontUrl() {
  const configured = String(import.meta.env.VITE_STOREFRONT_URL || '').trim().replace(/\/+$/, '')
  if (configured) return configured
  if (typeof location !== 'undefined') {
    const host = location.hostname.toLowerCase()
    // 本地开发：与商家端同 host 的 :3000（storefront dev 端口；m.localhost 手机壳同理）。
    if (host === 'localhost' || host === '127.0.0.1' || host === '[::1]' || host.endsWith('.localhost')) {
      return `${location.protocol}//${location.hostname}:3000`
    }
    // 产线：merchant.joyfumi.com / m.joyfumi.com 都回 www 商城。
    if (host.endsWith('joyfumi.com')) return 'https://www.joyfumi.com'
  }
  return 'https://www.joyfumi.com'
}
const STOREFRONT_URL = storefrontUrl()

// 静态稿会把演示数据写进 localStorage；启动时全部清掉并停用写入口。
const DEMO_STORAGE_KEYS = [
  'balance', 'listed', 'joined', 'sent', 'read',
  'withdrawalsV2', 'chatsV2', 'readNoticesV2', 'merchantV2Seed',
  'followerStateV1', 'followerPreview30V1', 'shipmentDatesV1',
  'reviewRepliesV1', 'supportMessagesV1', 'walletSecurityV1', 'shopProfileV1',
  'afterRowsV2', 'afterAuditV2', 'resetRequestV2', 'passwordGuardV2',
  'payoutExamplesV2', 'followerAuditV2', 'shippingAuditV2',
  'platformProductReviewsV1', 'merchantOrderSyncV2', 'orderLifecycleV3',
  'merchantOrderSubmissionsV3', 'merchantReferralRecords', 'merchantReferralRules',
  'merchantReferralBindings', 'merchantReferralCodeDirectoryV1',
  'appliedReferralReceipts', 'merchantLastActiveV1',
]

function wipeDemoStorage() {
  for (const key of Object.keys(window.localStorage)) {
    if (DEMO_STORAGE_KEYS.includes(key) || key.startsWith('confirmationReceiptsV2_') || key.startsWith('appliedConfirmationReceiptsV2_')) {
      window.localStorage.removeItem(key)
    }
  }
}

// ---------------------------------------------------------------------------
// 内部数据仓库
// ---------------------------------------------------------------------------
// 列表分页口径与静态稿一致：商品/店铺商品/钱包流水每页 8 条，订单每页 8 条。
// 所有列表都由服务端 page/page_size 驱动，本地不再切片（pageWindow 只负责页码窗口）。
const PAGE_SIZE = 8
const ORDERS_PAGE_SIZE = 8

function emptyPage() {
  return { items: [], total: 0, page: 1, size: PAGE_SIZE, loading: false, stale: false }
}

const state = {
  merchant: null,
  shops: [],
  overview: null,
  charts: { week: null, month: null },
  wallet: null,
  entries: [],
  withdrawalsApi: [],
  withdrawalsDraft: [],
  deposit: null,
  depositItems: [],
  catalogPage: { ...emptyPage(), q: '', category: '全部品类' },
  listingsPage: { ...emptyPage(), q: '', category: '全部品类' },
  ordersPage: {
    ...emptyPage(),
    size: ORDERS_PAGE_SIZE,
    counts: {},
    q: '',
    status: '全部订单',
    start: '',
    end: '',
  },
  entriesPage: { ...emptyPage(), kindLabel: '全部类型' },
  catalogMode: 'catalog',
  catalogCount: 0,
  afterSales: [],
  activities: [],
  notifications: [],
  conversations: [],
  // 需求 3（2026-11-29）：买家↔商家会话（/merchant/chats）与平台客服会话
  // （/merchant/conversations）分开拉；商家端消息中心两者合并成一个列表。
  chatThreads: [],
  supportConvId: '',
  referral: null,
  referralRecords: [],
  reviews: [],
  productIds: [],
  convLoaded: {},
  // 需求 3：买家↔商家会话当前已加载的会话 id（切换会话即重拉，刷新商品上下文）。
  threadLoadedFor: '',
  reviewDetailLoaded: {},
  categories: [],
}

// 这些全局变量由静态稿 base-3.js 的分页模板读取（页码窗口/总数/加载态）。
// 模块是严格模式，必须显式挂到 window 上，classic script 才能按标识符解析。
window.cataloguePages = 1
window.catalogueTotal = 0
window.catalogueCount = 0
window.catalogueLoading = false
window.shopPages = 1
window.shopTotal = 0
window.shopLoading = false
window.ordersPages = 1
window.ordersTotal = 0
window.ordersPageNo = 1
window.ordersLoading = false
window.ordersPageSize = 8
window.walletPages = 1
window.walletTotal = 0
window.walletLoading = false
window.walletPageSize = 8

// ---------------------------------------------------------------------------
// 格式化工具
// ---------------------------------------------------------------------------
const num = (v) => {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function fmtDT(iso) {
  if (!iso) return ''
  const s = String(iso)
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(s)) return s.slice(0, 16)
  return s.replace('T', ' ').slice(0, 16)
}

function fmtHM(iso) {
  const s = fmtDT(iso)
  return s ? s.slice(11, 16) : ''
}

function todayStr() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function fmtDateCN(d) {
  const wd = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日　星期${wd}`
}

function moneyNumber(n) {
  // 2026-11-29 用户拍板：商家端金额符号与设计稿一致，统一 `$`（与购物端「全站 $」同口径）。
  return '$ ' + num(n).toLocaleString('en-US', { minimumFractionDigits: 2 })
}

// 无图商品 → 静态稿 art() 八款示意 SVG 的类型映射（现成函数，只喂类型）。
const ART_RULES = [
  [/耳机|电竞耳机/, 'headphones'],
  [/手表|血氧|健康|按摩/, 'watch'],
  [/灯|台灯|电热/, 'lamp'],
  [/音箱|手柄|鼠标|键盘|拓展坞|电脑|笔记本|数码|电子/, 'speaker'],
  [/鞋|靴/, 'shoe'],
  [/杯|壶|奶瓶|护肤|口红|保湿|化妆|美妆|瓶/, 'bottle'],
  [/包|袋|丝巾|开衫|连衣裙|衬衫|夹克|行李箱|箱|收纳|服|宠|猫|狗|婴/, 'bag'],
  [/礼盒|套装|装饰/, 'cup'],
]

function artTypeOf(name) {
  const s = String(name || '')
  for (const [re, type] of ART_RULES) if (re.test(s)) return type
  return 'bag'
}

const WD_STATE = {
  PENDING: '待审核',
  REJECTED: '已打回',
  APPROVED: '审核通过',
  TRANSFERRING: '转账中',
  FAILED: '转账失败',
  // 2026-11-28 用户口径：管理端点【转账成功】后商家端显示「转账成功」（原「已到账」）。
  // 推荐返佣的「已到账」是另一套状态（REF_STATE），不受影响。
  PAID: '转账成功',
}

// 提现「占用余额」的原始枚举（不再拿中文状态做条件判断，避免文案调整后错位）。
const WD_OPEN_STATES = ['PENDING', 'APPROVED', 'TRANSFERRING']

const AFTER_STATE = {
  PENDING: '待处理',
  PROCESSING: '处理中',
  PLATFORM: '平台介入中',
  COMPLETED: '已完成',
  REJECTED: '已驳回',
}

// 支付方式代码 → 展示文案（与 admin-web MerchantOrdersView 同一套口径）。
// 需求 4：订单详情【支付方式】展示真实值；后端 /merchant/orders 回传
// orders.Order.PAYMENT_METHODS 里的代码（BALANCE/VISA/PAYPAL…）。
const PAYMENT_METHOD_LABELS = {
  BALANCE: '余额支付',
  CARD: '银行卡',
  VISA: 'Visa',
  MASTERCARD: 'Mastercard',
  AMEX: 'American Express',
  UNIONPAY: '银联',
  GOOGLE_PAY: 'Google Pay',
  APPLE_PAY: 'Apple Pay',
  WECHAT_PAY: '微信支付',
  PAYPAL: 'PayPal',
  REVOLUT_PAY: 'Revolut Pay',
  NEW_PAY: 'NewPay',
  KLARNA: 'Klarna',
  MAESTRO: 'Maestro',
  JCB: 'JCB',
  DISCOVER: 'Discover',
  DINERS: 'Diners Club',
}

// ---------------------------------------------------------------------------
// FolioData — 渲染模板中的「数据槽位」读取口（base-2 的数据位改造指向这里）
// ---------------------------------------------------------------------------
window.FolioData = {
  stats: { today_order_count: 0, credit_score: '0', today_exposure: 0 },
  counts: { pending: 0, pendingShipment: 0, unread: 0 },
  deposit: { balance: 0, statusLabel: '正常', statusHint: '无需补缴' },

  dateLabel() {
    return fmtDateCN(new Date())
  },

  // 设计稿钱包四卡：今日回款 / 店铺总收益（后端 /merchant/wallet 的聚合字段）。
  settlementToday() {
    return num((state.wallet || {}).settlement_today)
  },

  storeProfitTotal() {
    return num((state.wallet || {}).shipping_profit_total)
  },

  // —— 顶部导航徽标（每次 render 现读，不再用首屏快照）——
  // 订单管理 = 未发货订单数（后端 counts.PENDING：已付款且 progress<1）；
  // 消息中心 = 未读会话数合计（打开会话时 base 层清零 + 服务端标记已读）。
  navPendingCount() {
    const counts = (state.ordersPage && state.ordersPage.counts) || {}
    return num(counts.PENDING)
  },

  navUnreadCount() {
    let list = []
    try {
      // base 脚本里的全局 conversations 才是「打开会话即清零」的那份数据；
      // 用 try/catch 兜住脚本尚未加载时的 TDZ。
      if (Array.isArray(conversations)) list = conversations // eslint-disable-line no-undef
    } catch {
      // 首帧 base 脚本还没执行，退回接口返回值
    }
    // 首帧退回接口数据：平台客服会话 + 买家会话（需求 3 后买家会话在 chatThreads）。
    const source = list.length ? list : [...state.conversations, ...state.chatThreads]
    return (source || []).reduce((sum, c) => sum + num(c.unread), 0)
  },

  // 顶部「平台通知」红标：普通通知看 readNotices，商品好评看 reviews[].merchantRead，
  // 同样每次 render 现读——点开一条通知 / 全部已读后立刻反映。
  navNoticeUnread() {
    let notices = null
    let readIdx = null
    try {
      if (Array.isArray(systemNotices)) notices = systemNotices // eslint-disable-line no-undef
      if (Array.isArray(readNotices)) readIdx = readNotices // eslint-disable-line no-undef
    } catch {
      // 首帧 base 脚本还没执行，退回接口返回值
    }
    const normalTotal = notices ? notices.length : state.notifications.filter((n) => n.kind !== 'REVIEW').length
    const normalRead = readIdx
      ? readIdx.length
      : state.notifications.filter((n) => n.kind !== 'REVIEW' && n.read).length
    const reviewUnread = (state.reviews || []).filter((r) => !r.merchantRead).length
    return Math.max(0, normalTotal - normalRead) + reviewUnread
  },

  // 需求 4：支付方式展示文案；未知代码原样返回，空值由调用方显示「未提供」。
  paymentLabel(code) {
    const value = String(code || '').trim()
    return PAYMENT_METHOD_LABELS[value] || value
  },

  // 需求 2：聊天图片上传（走后端 /merchant/media，purpose=chat；返回站内 /media/ URL）。
  async uploadChatImage(file) {
    const up = await merchantUpload(file, 'chat')
    const url = up.url || (up.media && up.media.url) || ''
    if (!url) throw new Error('图片上传失败，请重试')
    return url
  },

  bars(key, month) {
    const chart = state.charts[month ? 'month' : 'week']
    if (!chart || !Array.isArray(chart.order_bars) || !chart.order_bars.length) {
      return [0, 0, 0, 0, 0, 0, 0]
    }
    const size = month ? Math.min(30, chart.order_bars.length) : Math.min(7, chart.order_bars.length)
    const days = chart.order_bars.slice(-size)
    if (key === 'orders') return days.map((b) => num(b.count))
    const byDate = new Map((chart.exposure_trend || []).map((r) => [r.date, num(r.exposure)]))
    return days.map((b) => byDate.get(b.date) || 0)
  },

  barMax(key, month) {
    // 取「能被 4 整除的整数刻度上限」，让 y 轴四档刻度都是整数（原型固定 160/8000）。
    const nums = this.bars(key, month)
    const max = Math.max(1, ...nums)
    const digit = Math.pow(10, Math.floor(Math.log10(max)))
    const candidates = [digit, 2 * digit, 4 * digit, 5 * digit, 8 * digit, 10 * digit]
    const nice = candidates.find((c) => c >= max && c % 4 === 0)
    return nice || Math.max(4, Math.ceil(max / 4) * 4)
  },

  dayDate(i, month) {
    const chart = state.charts[month ? 'month' : 'week']
    const dates = (chart && chart.order_bars ? chart.order_bars.map((b) => b.date) : []) || []
    const raw = dates[i] || dates[dates.length - 1] || todayStr()
    return new Date(raw + 'T00:00:00Z')
  },

  categoryPie(month) {
    const chart = state.charts[month ? 'month' : 'week']
    const rows = (chart && chart.category_share ? chart.category_share : []).slice(0, 4)
    const totalSum = rows.reduce((s, r) => s + num(r.count), 0)
    // 无订单时按设计稿的四个品类占位为 0%，避免出现 4 行「其他 0%」的占位噪音。
    if (!rows.length || totalSum === 0) {
      return {
        names: ['电子产品', '家居生活', '活动商品', '户外运动'],
        vals: [0, 0, 0, 0],
        total: '0',
      }
    }
    const names = []
    const vals = []
    let assigned = 0
    rows.forEach((r) => {
      names.push(r.category || '其他')
      const pct = Math.round((num(r.count) / totalSum) * 100)
      vals.push(pct)
      assigned += pct
    })
    // 百分比取整后可能不等于 100，差额补到第一个非零片，保证 conic-gradient 闭合。
    const drift = 100 - assigned
    const idx = vals.findIndex((v) => v > 0)
    if (idx >= 0) vals[idx] = Math.max(0, vals[idx] + drift)
    return { names, vals, total: totalSum.toLocaleString() }
  },

  orderTotal(range) {
    const chart = state.charts[range === 'month' ? 'month' : 'week']
    const sum = chart && chart.order_bars
      ? chart.order_bars.reduce((s, b) => s + num(b.count), 0)
      : 0
    return `近${range === 'month' ? 30 : 7}天累计 ${sum.toLocaleString()} 笔`
  },

  exposureTotal(range) {
    const chart = state.charts[range === 'month' ? 'month' : 'week']
    const sum = chart && chart.exposure_trend
      ? chart.exposure_trend.reduce((s, r) => s + num(r.exposure), 0)
      : 0
    return `近${range === 'month' ? 30 : 7}天累计 ${sum.toLocaleString()} 次`
  },

  exposureToday() {
    return num(this.stats.today_exposure).toLocaleString()
  },

  depositRows() {
    return state.depositItems.map((e) => [
      fmtDT(e.occurred_at),
      e.kind_label || e.kind || '—',
      e.related_id || '—',
      (num(e.amount) >= 0 ? '+ ' : '− ') + moneyNumber(Math.abs(num(e.amount))),
      moneyNumber(e.balance_after),
      e.note || '',
    ])
  },

  productId(i) {
    return state.productIds[i] || '—'
  },
}

// ---------------------------------------------------------------------------
// 拉数
// ---------------------------------------------------------------------------
async function safe(promise, fallback) {
  try {
    return await promise
  } catch (error) {
    console.warn('[folio] 数据加载失败:', error && error.message)
    return fallback
  }
}

function pageQuery(size) {
  return `page=1&page_size=${size}`
}

async function fetchOverview(range) {
  const payload = await apiRequest(`/merchant/overview?range=${range}`)
  state.charts[range] = payload.charts || null
  if (range === 'week') state.overview = payload
  return payload
}

async function fetchAll() {
  // 每个模块独立容错：单个模块失败降级为空数据（页面显示空态），不阻断整个引擎。
  // 商品池/店铺商品/订单/钱包流水一律按服务端分页拉第 1 页，本地不再一次取 100 条。
  const [
    overview, overviewMonth, wallet, entries, withdrawals, deposit,
    catalog, listings, orders, afterSales, activities, notifications,
    conversations, chatThreads, referral,
  ] = await Promise.all([
    safe(fetchOverview('week'), null),
    safe(fetchOverview('month'), null),
    safe(apiRequest('/merchant/wallet'), null),
    safe(apiRequest(`/merchant/wallet/entries?page=1&page_size=${PAGE_SIZE}&kind=ALL`), { items: [], total: 0 }),
    safe(apiRequest('/merchant/wallet/withdrawals?page=1&page_size=100'), { items: [] }),
    safe(apiRequest(`/merchant/deposit?${pageQuery(50)}`), { deposit: null, items: [] }),
    safe(apiRequest(`/merchant/catalog/products?page=1&page_size=${PAGE_SIZE}`), { items: [], total: 0 }),
    safe(apiRequest(`/merchant/listings?page=1&page_size=${PAGE_SIZE}`), { items: [], total: 0 }),
    safe(apiRequest(`/merchant/orders?page=1&page_size=${ORDERS_PAGE_SIZE}`), { items: [], total: 0, counts: {} }),
    safe(apiRequest(`/merchant/after-sales?${pageQuery(50)}`), { items: [] }),
    safe(apiRequest(`/merchant/activities?${pageQuery(50)}`), { items: [] }),
    safe(apiRequest(`/merchant/notifications?${pageQuery(50)}`), { items: [] }),
    safe(apiRequest(`/merchant/conversations?${pageQuery(30)}`), { items: [] }),
    safe(apiRequest('/merchant/chats'), { items: [] }),
    safe(apiRequest('/merchant/referral'), null),
  ])
  if (!overview) throw new Error('商家数据加载失败，请刷新重试。')
  state.overview = overview
  state.charts.week = overview.charts
  state.charts.month = overviewMonth.charts
  state.merchant = overview.merchant
  state.wallet = wallet
  state.withdrawalsApi = withdrawals.items || []
  state.deposit = deposit.deposit
  state.depositItems = deposit.items || []
  state.afterSales = afterSales.items || []
  state.activities = activities.items || []
  state.notifications = notifications.items || []
  state.conversations = conversations.items || []
  state.chatThreads = chatThreads.items || []
  state.referral = referral

  // 列表分页状态归零（切店/首次进入）：全部回到第 1 页、默认筛选。
  Object.assign(state.catalogPage, {
    items: catalog.items || [], total: num(catalog.total), page: 1,
    loading: false, stale: false, q: '', category: '全部品类',
  })
  Object.assign(state.listingsPage, {
    items: listings.items || [], total: num(listings.total), page: 1,
    loading: false, stale: false, q: '', category: '全部品类',
  })
  Object.assign(state.ordersPage, {
    items: orders.items || [], total: num(orders.total), page: 1,
    loading: false, stale: false, counts: orders.counts || {},
    q: '', status: '全部订单', start: '', end: '',
  })
  Object.assign(state.entriesPage, {
    items: entries.items || [], total: num(entries.total), page: 1,
    loading: false, stale: false, kindLabel: '全部类型',
  })
  state.entries = entries.items || []

  // 派生数据
  const support = state.conversations.find((c) => c.kind === 'PLATFORM_SUPPORT')
  state.supportConvId = support ? support.id : ''
  state.withdrawalsDraft = state.withdrawalsApi.map((w) => draftWithdrawal(w))
  state.reviews = state.notifications
    .filter((n) => n.kind === 'REVIEW')
    .map((n) => reviewFromNotification(n))
}

function draftWithdrawal(w) {
  const bank = w.bank || null
  const chain = w.chain || null
  return {
    id: w.id,
    // 可读申请单号（后端 WD+日期+序号）；旧接口无该字段时退回 UUID。
    serial: w.serial || w.id,
    amount: num(w.amount),
    method: w.method === 'CHAIN' || chain ? '数字货币链上转账' : '银行卡',
    account: (bank && bank.account) || (chain && chain.address) || '',
    state: WD_STATE[w.state] || w.state,
    reason: w.reason || '',
    date: fmtDT(w.created_at),
    network: chain ? String(chain.network || '') : '',
    coin: chain ? String(chain.coin || '') : '',
    bank: bank
      ? { name: bank.name || '', holder: bank.holder || '', branch: bank.branch || '', code: bank.code || '' }
      : null,
    fee: num(w.fee),
    net: num(w.net_amount),
    // 未完结的提现申请占用可用余额，钱包页「冻结金额」直接汇总这个字段。
    // 用原始枚举判断（勿改回中文比较：PAID 文案已改为「转账成功」）。
    frozen: WD_OPEN_STATES.includes(w.state) ? num(w.amount) : 0,
    history: (w.history || []).map(
      (h) => `${fmtDT(h.at).slice(5, 16)} ${h.action}${h.note ? '，' + h.note : ''}`,
    ),
  }
}

function reviewFromNotification(n) {
  const p = n.product || {}
  return {
    id: n.id,
    title: n.title,
    content: n.content,
    createdAt: fmtDT(n.created_at),
    merchantRead: Boolean(n.read),
    images: Array.isArray(n.images) ? n.images : [],
    product: {
      name: p.name || p.title || '',
      id: p.id || '',
      category: p.category || '',
      price: num(p.price),
    },
    replies: [],
  }
}

// ---------------------------------------------------------------------------
// 状态对象映射（渲染函数消费的同构字段）
// ---------------------------------------------------------------------------
function ensureProductIndex(built, { id, name, category, price, cost }) {
  if (id && built.byId.has(id)) return built.byId.get(id)
  const idx = built.products.length
  built.products.push([name || '平台商品', category || '家居生活', num(price), num(cost), artTypeOf(name)])
  built.ids.push(id || '')
  if (id) built.byId.set(id, idx)
  return idx
}

const ORDER_STATUS = {
  全部订单: '',
  // 2026-11-28 三态口径：列表筛选用「待发货」，对应后端子单状态 PENDING
  // （progress<1，含未发货与仅到「待出库」）。
  待发货: 'PENDING',
  已发货: 'SHIPPED',
  已完成: 'COMPLETED',
}

const WALLET_KIND = {
  全部类型: 'ALL',
  提现申请: 'WITHDRAWAL',
  充值入账: 'RECHARGE',
  订单发货: 'ORDER_SHIPPING',
  订单回款: 'ORDER_SETTLEMENT',
  推荐返佣: 'REFERRAL_COMMISSION',
}

const WALLET_TYPE = {
  RECHARGE: '充值入账',
  ORDER_SHIPPING: '订单发货',
  ORDER_SETTLEMENT: '订单回款',
  REFERRAL_COMMISSION: '推荐返佣',
  WITHDRAWAL: '提现申请',
  ADJUSTMENT: '余额调整',
}

function pageCountOf(page) {
  return Math.max(1, Math.ceil(num(page.total) / page.size))
}

// 静态稿 base-3.js 的分页模板读这几个全局：页数/总数/加载态（页码窗口本身不变）。
function syncPagerGlobals() {
  window.cataloguePages = pageCountOf(state.catalogPage)
  window.catalogueTotal = num(state.catalogPage.total)
  window.catalogueCount = state.catalogCount
  window.catalogueLoading = Boolean(state.catalogPage.loading)
  window.shopPages = pageCountOf(state.listingsPage)
  window.shopTotal = num(state.listingsPage.total)
  window.shopLoading = Boolean(state.listingsPage.loading)
  window.ordersPages = pageCountOf(state.ordersPage)
  window.ordersTotal = num(state.ordersPage.total)
  window.ordersLoading = Boolean(state.ordersPage.loading)
  window.ordersPageSize = ORDERS_PAGE_SIZE
  window.walletPages = pageCountOf(state.entriesPage)
  window.walletTotal = num(state.entriesPage.total)
  window.walletLoading = Boolean(state.entriesPage.loading)
  window.walletPageSize = PAGE_SIZE
}

// 当前页码回写静态稿的全局变量（历史栈 viewState 依赖它们）。
function syncPageNumbers() {
  listingPage = state.catalogPage.page // eslint-disable-line no-undef
  shopProductPage = state.listingsPage.page // eslint-disable-line no-undef
  window.ordersPageNo = state.ordersPage.page
  merchantWalletPage = state.entriesPage.page // eslint-disable-line no-undef
}

function buildProductRow(it, mode) {
  return {
    id: it.product_id || it.id || '',
    name: it.name,
    category: it.merchant_category_label || (it.category && it.category.name_zh) || '家居生活',
    price: it.price,
    cost: it.cost,
    listed: mode === 'shop' ? true : Boolean(it.listed),
  }
}

// 渲染模板只认 products/orders/listed 三个全局数组；这里把它们重建成：
// [当前页商品] + [当前页订单引用的商品]。上架/订单分页都只换这一层数据。
function rebuildProducts() {
  const mode = current === 1 ? 'shop' : 'catalog' // eslint-disable-line no-undef
  state.catalogMode = mode
  const page = mode === 'shop' ? state.listingsPage : state.catalogPage
  const built = { products: [], ids: [], byId: new Map() }
  const listedIdx = []
  for (const it of page.items || []) {
    const row = buildProductRow(it, mode)
    const idx = ensureProductIndex(built, row)
    if (row.listed) listedIdx.push(idx)
  }
  state.catalogCount = built.products.length
  const builtOrders = buildOrders(built)
  products.splice(0, products.length, ...built.products) // eslint-disable-line no-undef
  orders.splice(0, orders.length, ...builtOrders) // eslint-disable-line no-undef
  state.productIds = built.ids
  listed = listedIdx // eslint-disable-line no-undef
  syncPagerGlobals()
}

async function ensureCategories() {
  if (state.categories.length) return state.categories
  const payload = await safe(apiRequest('/merchant/catalog/categories'), { items: [] })
  state.categories = payload.items || []
  return state.categories
}

async function resolveCategoryId(category) {
  if (!category || category === '全部品类') return ''
  const categories = await ensureCategories()
  const hit = categories.find((c) => c.name === category || c.id === category)
  return hit ? hit.id : ''
}

function revertCatalogGlobals() {
  const page = state.catalogPage
  search = page.q // eslint-disable-line no-undef
  category = page.category // eslint-disable-line no-undef
  listingPage = page.page // eslint-disable-line no-undef
}

function revertListingsGlobals() {
  const page = state.listingsPage
  search = page.q // eslint-disable-line no-undef
  category = page.category // eslint-disable-line no-undef
  shopProductPage = page.page // eslint-disable-line no-undef
}

function revertOrdersGlobals() {
  const page = state.ordersPage
  orderFilter = page.status // eslint-disable-line no-undef
  queryOrder = page.q // eslint-disable-line no-undef
  orderFrom = page.start // eslint-disable-line no-undef
  orderTo = page.end // eslint-disable-line no-undef
  window.ordersPageNo = page.page
}

function revertEntriesGlobals() {
  merchantWalletType = state.entriesPage.kindLabel // eslint-disable-line no-undef
  merchantWalletPage = state.entriesPage.page // eslint-disable-line no-undef
}

// ---------------------------------------------------------------------------
// 服务端分页取数（三类列表 + 钱包流水）
// ---------------------------------------------------------------------------
async function loadCatalogPage({ page, q, category: catLabel } = {}) {
  const target = state.catalogPage
  if (target.loading) return
  const desired = {
    page: Math.max(1, Math.floor(Number(page) || 1)),
    q: String(q == null ? target.q : q).trim(),
    category: catLabel || target.category || '全部品类',
  }
  target.loading = true
  syncPagerGlobals()
  render() // eslint-disable-line no-undef
  try {
    const params = new URLSearchParams({ page: String(desired.page), page_size: String(target.size) })
    if (desired.q) params.set('q', desired.q)
    const categoryId = await resolveCategoryId(desired.category)
    if (categoryId) params.set('category', categoryId)
    let payload = await apiRequest(`/merchant/catalog/products?${params}`)
    let pages = Math.max(1, Math.ceil(num(payload.total) / target.size))
    if (desired.page > pages) {
      params.set('page', String(pages))
      payload = await apiRequest(`/merchant/catalog/products?${params}`)
      target.page = pages
    } else {
      target.page = desired.page
    }
    target.items = payload.items || []
    target.total = num(payload.total)
    target.q = desired.q
    target.category = desired.category
    target.stale = false
    search = target.q // eslint-disable-line no-undef
    category = target.category // eslint-disable-line no-undef
    listingPage = target.page // eslint-disable-line no-undef
  } catch (error) {
    toast(error.message || '商品查询失败，请稍后重试') // eslint-disable-line no-undef
    revertCatalogGlobals()
  } finally {
    target.loading = false
    syncPagerGlobals()
    rebuildProducts()
    render() // eslint-disable-line no-undef
  }
}

async function loadListingsPage({ page, q, category: catLabel } = {}) {
  const target = state.listingsPage
  if (target.loading) return
  const desired = {
    page: Math.max(1, Math.floor(Number(page) || 1)),
    q: String(q == null ? target.q : q).trim(),
    category: catLabel || target.category || '全部品类',
  }
  target.loading = true
  syncPagerGlobals()
  render() // eslint-disable-line no-undef
  try {
    const params = new URLSearchParams({
      page: String(desired.page),
      page_size: String(target.size),
      status: 'ACTIVE',
    })
    if (desired.q) params.set('q', desired.q)
    const categoryId = await resolveCategoryId(desired.category)
    if (categoryId) params.set('category', categoryId)
    let payload = await apiRequest(`/merchant/listings?${params}`)
    let pages = Math.max(1, Math.ceil(num(payload.total) / target.size))
    if (desired.page > pages) {
      params.set('page', String(pages))
      payload = await apiRequest(`/merchant/listings?${params}`)
      target.page = pages
    } else {
      target.page = desired.page
    }
    target.items = payload.items || []
    target.total = num(payload.total)
    target.q = desired.q
    target.category = desired.category
    target.stale = false
    search = target.q // eslint-disable-line no-undef
    category = target.category // eslint-disable-line no-undef
    shopProductPage = target.page // eslint-disable-line no-undef
  } catch (error) {
    toast(error.message || '店铺商品加载失败，请稍后重试') // eslint-disable-line no-undef
    revertListingsGlobals()
  } finally {
    target.loading = false
    syncPagerGlobals()
    rebuildProducts()
    render() // eslint-disable-line no-undef
  }
}

async function loadOrdersPage({ page, q, status, start, end } = {}) {
  const target = state.ordersPage
  if (target.loading) return
  const desired = {
    page: Math.max(1, Math.floor(Number(page) || 1)),
    q: String(q == null ? target.q : q).trim(),
    status: status || target.status || '全部订单',
    start: String(start == null ? target.start : start).slice(0, 10),
    end: String(end == null ? target.end : end).slice(0, 10),
  }
  target.loading = true
  syncPagerGlobals()
  render() // eslint-disable-line no-undef
  try {
    const params = new URLSearchParams({ page: String(desired.page), page_size: String(target.size) })
    if (desired.q) params.set('q', desired.q)
    const statusCode = ORDER_STATUS[desired.status] || ''
    if (statusCode) params.set('status', statusCode)
    if (desired.start) params.set('start', desired.start)
    if (desired.end) params.set('end', desired.end)
    let payload = await apiRequest(`/merchant/orders?${params}`)
    let pages = Math.max(1, Math.ceil(num(payload.total) / target.size))
    if (desired.page > pages) {
      params.set('page', String(pages))
      payload = await apiRequest(`/merchant/orders?${params}`)
      target.page = pages
    } else {
      target.page = desired.page
    }
    target.items = payload.items || []
    target.total = num(payload.total)
    target.counts = payload.counts || {}
    target.q = desired.q
    target.status = desired.status
    target.start = desired.start
    target.end = desired.end
    target.stale = false
    orderFilter = target.status // eslint-disable-line no-undef
    queryOrder = target.q // eslint-disable-line no-undef
    orderFrom = target.start // eslint-disable-line no-undef
    orderTo = target.end // eslint-disable-line no-undef
    window.ordersPageNo = target.page
    // 侧栏/首页的待处理徽标始终用响应里的聚合计数，不是当前页条数。
    window.FolioData.counts.pending = num((target.counts || {}).PENDING)
  } catch (error) {
    toast(error.message || '订单加载失败，请稍后重试') // eslint-disable-line no-undef
    revertOrdersGlobals()
  } finally {
    target.loading = false
    syncPagerGlobals()
    rebuildProducts()
    render() // eslint-disable-line no-undef
  }
}

async function loadEntriesPage({ page, kindLabel } = {}) {
  const target = state.entriesPage
  if (target.loading) return
  const desired = {
    page: Math.max(1, Math.floor(Number(page) || 1)),
    kindLabel: kindLabel || target.kindLabel || '全部类型',
  }
  target.loading = true
  syncPagerGlobals()
  render() // eslint-disable-line no-undef
  try {
    const params = new URLSearchParams({ page: String(desired.page), page_size: String(target.size) })
    const kind = WALLET_KIND[desired.kindLabel] || 'ALL'
    if (kind !== 'ALL') params.set('kind', kind)
    let payload = await apiRequest(`/merchant/wallet/entries?${params}`)
    let pages = Math.max(1, Math.ceil(num(payload.total) / target.size))
    if (desired.page > pages) {
      params.set('page', String(pages))
      payload = await apiRequest(`/merchant/wallet/entries?${params}`)
      target.page = pages
    } else {
      target.page = desired.page
    }
    target.items = payload.items || []
    target.total = num(payload.total)
    target.kindLabel = desired.kindLabel
    target.stale = false
    state.entries = target.items
    merchantWalletType = target.kindLabel // eslint-disable-line no-undef
    merchantWalletPage = target.page // eslint-disable-line no-undef
  } catch (error) {
    toast(error.message || '资金明细加载失败，请稍后重试') // eslint-disable-line no-undef
    revertEntriesGlobals()
  } finally {
    target.loading = false
    syncPagerGlobals()
    render() // eslint-disable-line no-undef
  }
}

// 上架中心筛选（merchant-mobile 的搜索/分类 sheet 调用）：回第 1 页重新请求。
async function refreshCatalog({ q = '', category: catLabel = '全部品类' } = {}) {
  return loadCatalogPage({ page: 1, q, category: catLabel })
}

async function refreshListings({ q = '', category: catLabel = '全部品类' } = {}) {
  return loadListingsPage({ page: 1, q, category: catLabel })
}

function buildOrders(built) {
  const list = []
  for (const o of (state.ordersPage && state.ordersPage.items) || []) {
    const qtyN = Math.max(1, num(o.quantity) || 1)
    const unitPrice = Math.round((num(o.items_total) / qtyN) * 100) / 100
    const unitCost = Math.round((num(o.cost_total) / qtyN) * 100) / 100
    const pIdx = ensureProductIndex(built, {
      id: '',
      name: o.title || '平台商品',
      category: '家居生活',
      price: unitPrice,
      cost: unitCost,
    })
    const progress = o.status === 'PENDING' ? -1 : o.status === 'COMPLETED' ? 7 : num(o.progress)
    const ord = [o.id, pIdx, fmtHM(o.created_at), unitPrice, '']
    ord.orderMeta = {
      progress,
      nodeTimes: (o.node_times || []).map((t) => fmtDT(t)),
      date: fmtDT(o.created_at),
      unitPrice,
      unitCost,
      qty: qtyN,
      paymentMethod: o.payment_method || '',
      region: o.recipient_region || '',
      buyerId: null,
      settledAt: o.settled_at || '',
      autoRevision: 0,
    }
    list.push(ord)
  }
  return list
}

function buildConversations() {
  const colors = ['#dfe8f4', '#ede3d9', '#e3e9de', '#efe1e6']
  const convs = []
  let supportMsgs = null
  // 平台客服会话（SupportConversation）：置顶那一条，走 /merchant/conversations/*。
  // 历史上买家商品咨询也落这张表（spu 外键），现在真实买家咨询走 /merchant/chats，
  // 这里保留列表兼容旧数据（chatKind=CONVERSATION，纯文字）。
  for (const c of state.conversations) {
    if (c.kind === 'PLATFORM_SUPPORT') {
      supportMsgs = [['them', c.last_message || '您好，欢迎来到客服中心。', fmtHM(c.last_message_at)]]
      continue
    }
    convs.push({
      id: c.id,
      chatKind: 'CONVERSATION',
      name: c.peer_name || '买家',
      region: '',
      order: '',
      color: colors[convs.length % colors.length],
      initial: (c.peer_name || '客').slice(0, 1),
      unread: num(c.unread),
      // 旧数据也可能带商品快照（后端 c.product），照常渲染商品上下文条。
      contextProduct: c.product || null,
      messages: [
        c.last_message
          ? ['them', c.last_message, fmtHM(c.last_message_at)]
          : ['them', '（暂无消息）', ''],
      ],
    })
  }
  // 买家↔商家会话（MerchantChatThread）：真实「联系商家」入口，走 /merchant/chats/*。
  // 商品上下文随买家最近一次发消息切换（context_product，覆盖式快照）。
  for (const t of state.chatThreads) {
    const buyer = t.buyer || {}
    const preview = t.last_message || (t.last_message_image ? '[图片]' : '（暂无消息）')
    convs.push({
      id: t.id,
      chatKind: 'THREAD',
      name: buyer.display_name || '买家',
      region: '',
      order: '',
      color: colors[convs.length % colors.length],
      initial: (buyer.display_name || '客').slice(0, 1),
      unread: num(t.unread),
      contextProduct: t.context_product || null,
      messages: [['them', preview, fmtHM(t.last_message_at)]],
    })
  }
  if (!supportMsgs) supportMsgs = [['them', '您好，欢迎来到客服中心。充值、保证金、店铺及订单问题，都可以在这里咨询。', '09:00']]
  return { convs, supportMsgs }
}

function buildNotices() {
  const notices = []
  const readIdx = []
  state.notifications.forEach((n) => {
    if (n.kind === 'REVIEW') return
    const entry = ['平台通知', n.title, n.content, fmtDT(n.created_at), '']
    entry.__nid = n.id
    notices.push(entry)
    if (n.read) readIdx.push(notices.length - 1)
  })
  return { notices, readIdx }
}

function populateGlobals() {
  const stats = (state.overview && state.overview.stats) || {}
  const merchant = state.merchant || {}
  const wallet = state.wallet || {}
  const deposit = state.deposit || {}
  const ordersCounts = (state.ordersPage && state.ordersPage.counts) || {}

  window.FolioData.stats = {
    today_order_count: num(stats.today_order_count),
    credit_score: String(stats.credit_score || '0'),
    today_exposure: num(stats.today_exposure),
  }
  window.FolioData.counts = {
    pending: num(ordersCounts.PENDING),
    pendingShipment: num(stats.pending_shipment_count),
    unread: state.conversations.reduce((s, c) => s + num(c.unread), 0),
  }
  const pending = num(deposit.pending)
  window.FolioData.deposit = {
    balance: num(deposit.balance),
    statusLabel: pending > 0 ? '待补缴' : '正常',
    statusHint: pending > 0 ? '余额不足，请联系客服补缴' : '无需补缴',
  }

  const { convs, supportMsgs } = buildConversations()
  const { notices, readIdx } = buildNotices()

  // —— 全局状态对象（base 脚本声明的 let/const 绑定）——
  balance = num(wallet.balance) // eslint-disable-line no-undef
  sealed = !(merchant.can_operate ?? true) // eslint-disable-line no-undef
  enabled = Boolean(deposit.enabled) // eslint-disable-line no-undef
  immutableShopId = merchant.id || '' // eslint-disable-line no-undef
  // 2026-11-27 全站编号改造：静态稿里不属于本模块作用域的编号展示（base-1 店铺状态
  // 页、base-2 账号弹窗）从 dataset 读数据槽，避免再写死演示用 MER 号。
  document.documentElement.dataset.merchantId = merchant.id || ''
  shopProfile = { name: merchant.name || '商家店铺', avatar: merchant.avatar || '' } // eslint-disable-line no-undef
  walletSecurity = wallet.wallet_password_configured ? { remote: true } : null // eslint-disable-line no-undef
  passwordGuard = { // eslint-disable-line no-undef
    failures: 0,
    until: wallet.wallet_password_locked_until ? Date.parse(wallet.wallet_password_locked_until) : 0,
  }
  resetRequest = null // eslint-disable-line no-undef
  opsScenario = '接单中' // eslint-disable-line no-undef
  followerState = { // eslint-disable-line no-undef
    total: num(stats.follower_total),
    delta: num(stats.follower_delta),
    day: todayStr(),
  }

  // products/orders/listed 由当前页数据重建（上架中心第 1 页 + 订单第 1 页）。
  rebuildProducts()
  const realNodeLabels = (((state.ordersPage && state.ordersPage.items) || [])[0] || {}).node_labels
  milestones.splice(0, milestones.length, ...(Array.isArray(realNodeLabels) && realNodeLabels.length ? realNodeLabels : milestones)) // eslint-disable-line no-undef

  joined = state.activities // eslint-disable-line no-undef
    .map((a, i) => (a.joined ? i : -1))
    .filter((i) => i >= 0)
  sent = [] // eslint-disable-line no-undef
  read = [] // eslint-disable-line no-undef

  conversations = convs // eslint-disable-line no-undef
  supportMessages = supportMsgs // eslint-disable-line no-undef
  activeConversation = -1 // eslint-disable-line no-undef

  systemNotices.splice(0, systemNotices.length, ...notices) // eslint-disable-line no-undef
  readNotices = readIdx // eslint-disable-line no-undef
  noticeType = '全部通知' // eslint-disable-line no-undef

  withdrawals = state.withdrawalsDraft // eslint-disable-line no-undef
  payoutExamples = [] // eslint-disable-line no-undef
  // 钱包页「今日新增收益」→ 后端 overview.stats.shipping_profit_today（真实值），
  // 不再用静态稿基于演示发货日期的本地推算。
  todayProfit = () => num(((state.overview || {}).stats || {}).shipping_profit_today) // eslint-disable-line no-undef
  merchantWalletType = state.entriesPage.kindLabel // eslint-disable-line no-undef
  merchantWalletPage = state.entriesPage.page // eslint-disable-line no-undef
  fundKind = '全部类型' // eslint-disable-line no-undef
  fundQuery = '' // eslint-disable-line no-undef
  fundFrom = '' // eslint-disable-line no-undef
  fundTo = '' // eslint-disable-line no-undef

  afterRows = state.afterSales.map((a) => ({ // eslint-disable-line no-undef
    id: a.id,
    order: a.order_id,
    type: a.kind === 'RETURN' ? '退货订单' : '用户投诉',
    issue: a.issue || '',
    state: AFTER_STATE[a.state] || a.state,
    progress: a.progress || '',
  }))
  afterFilter = '全部售后' // eslint-disable-line no-undef
  afterAudit = {} // eslint-disable-line no-undef
  for (const a of state.afterSales) {
    afterAudit[a.id] = { // eslint-disable-line no-undef
      history: [],
      proof: (a.proof || []).map((url, j) => ({ name: `凭证${j + 1}`, data: url })),
      result: a.result || '',
    }
  }

  activityItems.splice(0, activityItems.length, ...state.activities.map((a) => { // eslint-disable-line no-undef
    const timeRange = a.kind === 'PERMANENT' || !a.start
      ? '长期有效'
      : `${String(a.start).replace(/-/g, '.')} — ${String(a.end || '').replace(/-/g, '.')}`
    const item = [
      a.title || '平台活动',
      a.kind === 'LIMITED' ? '限时活动' : '常驻活动',
      timeRange,
      a.description || '',
      // 卡片主图占位取活动名前 4 字；先剥掉演示前缀，避免出现「[dem」这种半截标签。
      String(a.title || '活动').replace(/^\[\s*demo\s*\]\s*/i, '').slice(0, 4) || '活动',
    ]
    item.__id = a.id
    return item
  }))
  activityCategory = '全部' // eslint-disable-line no-undef

  // 检索/筛选类纯 UI 状态归零（列表分页状态已在 fetchAll 里重置为第 1 页）
  search = state.catalogPage.q // eslint-disable-line no-undef
  category = state.catalogPage.category // eslint-disable-line no-undef
  orderFilter = state.ordersPage.status // eslint-disable-line no-undef
  selected = 0 // eslint-disable-line no-undef
  queryOrder = state.ordersPage.q // eslint-disable-line no-undef
  orderFrom = state.ordersPage.start // eslint-disable-line no-undef
  orderTo = state.ordersPage.end // eslint-disable-line no-undef
  listingPage = state.catalogPage.page // eslint-disable-line no-undef
  shopProductPage = state.listingsPage.page // eslint-disable-line no-undef
  shopProductFilterKey = '' // eslint-disable-line no-undef
  withdrawTab = '银行卡' // eslint-disable-line no-undef
  pendingListing = null // eslint-disable-line no-undef
  pendingWithdrawal = null // eslint-disable-line no-undef
  avatarDraft = '' // eslint-disable-line no-undef
  syncPageNumbers()
  syncPagerGlobals()
}

function applyAfterDetail(index, detail) {
  const r = afterRows[index] // eslint-disable-line no-undef
  if (!r || !detail) return
  r.state = AFTER_STATE[detail.state] || detail.state
  r.progress = detail.progress || ''
  r.result = detail.result || ''
  afterAudit[r.id] = { // eslint-disable-line no-undef
    history: (detail.events || []).map((e) => [fmtDT(e.created_at), e.action || '', e.content || '']),
    proof: (detail.proof || []).map((url, j) => ({ name: `凭证${j + 1}`, data: url })),
    result: detail.result || '',
  }
}

function applyOrderDetail(od) {
  const ord = orders.find((x) => x[0] === od.id) // eslint-disable-line no-undef
  if (!ord || !ord.orderMeta) return
  ord.orderMeta.progress = od.status === 'COMPLETED' ? 7 : od.status === 'PENDING' ? -1 : num(od.progress)
  ord.orderMeta.nodeTimes = (od.node_times || []).map((t) => fmtDT(t))
  ord.orderMeta.settledAt = od.settled_at || ''
}

async function refreshWallet() {
  const payload = await safe(apiRequest('/merchant/wallet'), null)
  if (payload) {
    state.wallet = payload
    // 资金明细列表的页码/总数由 entriesPage 维护，这里只刷新余额与安全状态，
    // 不用 /merchant/wallet 自带的「第 1 页」覆盖当前页数据。
    balance = num(payload.balance) // eslint-disable-line no-undef
    walletSecurity = payload.wallet_password_configured ? { remote: true } : null // eslint-disable-line no-undef
    passwordGuard = { // eslint-disable-line no-undef
      failures: 0,
      until: payload.wallet_password_locked_until ? Date.parse(payload.wallet_password_locked_until) : 0,
    }
  }
}

// ---------------------------------------------------------------------------
// 演示逻辑停用 + 动作函数真实化
// ---------------------------------------------------------------------------
function overrideActions() {
  // 1) 演示持久化与模拟器全部停用（渲染函数不动）。
  save = () => {} // eslint-disable-line no-undef
  persistV2 = () => {} // eslint-disable-line no-undef
  syncReferralReceipts = () => {} // eslint-disable-line no-undef
  recordMerchantOnline = () => {} // eslint-disable-line no-undef
  auditShipping = () => {} // eslint-disable-line no-undef
  runMerchantAutoProgress = () => false // eslint-disable-line no-undef
  merchantAutoProgressTimer = () => {} // eslint-disable-line no-undef
  syncConfirmedOrders = () => {} // eslint-disable-line no-undef
  scheduleFollowerMidnight = () => {} // eslint-disable-line no-undef
  normalizeFollowers = () => followerState // eslint-disable-line no-undef
  payoutExamples = [] // eslint-disable-line no-undef

  // 2) 资金明细 / 提现记录 → 真实数据
  // 资金明细 → 当前服务端页（含 WITHDRAWAL 的占款/退回流水，它本身就是资金变动）。
  allFundRows = () => state.entries.map((e) => { // eslint-disable-line no-undef
    const withdrawal = e.kind === 'WITHDRAWAL' && e.withdrawal_id
      ? state.withdrawalsDraft.find((w) => w.id === e.withdrawal_id)
      : null
    const rawState = withdrawal
      ? withdrawal.state
      : e.state === 'COMPLETED' ? '已完成' : e.state === 'FAILED' ? '失败' : '处理中'
    // 2026-11-28 用户要求：转账失败/打回原因要能在【资金明细】里直接看到。
    // 优先取提现单 reason；提现单不在当前缓存页时从流水 note 兜底
    // （后端退回流水写法为「提现退回 XXXXXXXX：原因」）。
    const noteReason = /^提现退回[^：]*：([\s\S]+)$/.exec(String(e.note || ''))
    const reason = withdrawal ? String(withdrawal.reason || '') : noteReason ? noteReason[1] : ''
    return {
      time: fmtDT(e.occurred_at),
      type: WALLET_TYPE[e.kind] || e.kind,
      id: e.id,
      order: e.order_id || '—',
      amount: num(e.amount),
      state: rawState,
      // 仅提现类且确有原因的行带值；无原因保持空串（列表不占位）。
      reason,
      // 提现申请只在本页能查到对应提现单时才接到「提现处理明细」。
      payout: withdrawal ? withdrawal.id : null,
    }
  })
  opsPayouts = () => state.withdrawalsDraft // eslint-disable-line no-undef

  // 3) 发货 → POST /merchant/orders/{id}/ship
  ship = async function (i) { // eslint-disable-line no-undef
    const o = orders[i] // eslint-disable-line no-undef
    if (!o || !o.orderMeta) return
    if (o.orderMeta.progress >= 0) { toast('该订单已发货，请勿重复提交'); return } // eslint-disable-line no-undef
    const onList = current === 3 // eslint-disable-line no-undef
    try {
      const payload = await merchantWrite(`/merchant/orders/${o[0]}/ship`, {})
      applyOrderDetail(payload.order)
      closeModal() // eslint-disable-line no-undef
      toast('发货成功，订单进入待出库阶段') // eslint-disable-line no-undef
      // 只刷新受影响的那一页：列表页原地重拉当前筛选/页码；详情页保持当前单不变。
      state.ordersPage.stale = true
      state.entriesPage.stale = true
      if (onList) {
        await loadOrdersPage({
          page: state.ordersPage.page,
          q: queryOrder, // eslint-disable-line no-undef
          status: orderFilter, // eslint-disable-line no-undef
          start: orderFrom, // eslint-disable-line no-undef
          end: orderTo, // eslint-disable-line no-undef
        })
      } else {
        render() // eslint-disable-line no-undef
      }
      await refreshWallet()
    } catch (error) {
      toast(error.message || '发货失败，请稍后重试') // eslint-disable-line no-undef
    }
  }

  // 4) 上架 → POST /merchant/listings（确认弹层沿用原码结构）
  const prevListProduct = listProduct // eslint-disable-line no-undef
  listProduct = function (i) { // eslint-disable-line no-undef
    if (listed.includes(i)) { toast('该商品已上架'); return } // eslint-disable-line no-undef
    if (!products[i]) return // eslint-disable-line no-undef
    prevListProduct(i)
  }
  confirmListing = async function (i) { // eslint-disable-line no-undef
    if (pendingListing !== i) return // eslint-disable-line no-undef
    pendingListing = null // eslint-disable-line no-undef
    const productId = state.productIds[i]
    if (!productId) { toast('商品数据缺失，无法上架'); return } // eslint-disable-line no-undef
    try {
      await merchantWrite('/merchant/listings', { product_id: productId })
      closeModal() // eslint-disable-line no-undef
      toast('商品已上架至您的店铺') // eslint-disable-line no-undef
      // 写操作只刷新受影响的那一页：保持当前页码与筛选，重拉后 listed 标记随之下发。
      state.listingsPage.stale = true
      state.catalogPage.stale = true
      if (current === 2) { // eslint-disable-line no-undef
        await loadCatalogPage({
          page: state.catalogPage.page,
          q: search, // eslint-disable-line no-undef
          category, // eslint-disable-line no-undef
        })
      } else if (current === 1) { // eslint-disable-line no-undef
        await loadListingsPage({
          page: state.listingsPage.page,
          q: search, // eslint-disable-line no-undef
          category, // eslint-disable-line no-undef
        })
      } else {
        render() // eslint-disable-line no-undef
      }
    } catch (error) {
      closeModal() // eslint-disable-line no-undef
      toast(error.message || '上架失败') // eslint-disable-line no-undef
    }
  }

  // 5) 钱包密码 → POST /merchant/wallet/password（弹层结构沿用原码）
  // 0mf-d：若本次设置是由「申请提现」在未设密码时引导出来的（__wpinThenWithdraw
  // 意图标记），设置成功后自动接回申请提现弹层；轻量重拉 wallet 保证 balance /
  // wallet_password_configured 最新。意图在 closeModal 里兜底清除（取消即作废）。
  saveWalletPassword = async function () { // eslint-disable-line no-undef
    if (passwordBusy) return // eslint-disable-line no-undef
    const pass = document.getElementById('newWpin').value
    const confirm = document.getElementById('confirmWpin').value
    const error = document.getElementById('passwordError')
    if (!/^\d{6}$/.test(pass)) { error.textContent = '钱包密码必须为6位数字'; return }
    if (pass !== confirm) { error.textContent = '两次输入的密码不一致'; return }
    passwordBusy = true // eslint-disable-line no-undef
    const button = document.getElementById('passwordSaveButton')
    button.disabled = true
    try {
      const body = { new_password: pass, confirm_password: confirm }
      if (walletSecurity) body.old_password = document.getElementById('oldWpin').value // eslint-disable-line no-undef
      await merchantWrite('/merchant/wallet/password', body)
      walletSecurity = { remote: true } // eslint-disable-line no-undef
      const thenWithdraw = window.__wpinThenWithdraw === true // eslint-disable-line no-undef
      window.__wpinThenWithdraw = false // eslint-disable-line no-undef
      closeModal() // eslint-disable-line no-undef
      render() // eslint-disable-line no-undef
      toast('钱包密码已设置') // eslint-disable-line no-undef
      if (thenWithdraw) {
        await refreshWallet()
        withdrawModal() // eslint-disable-line no-undef
      }
    } catch (err) {
      error.textContent = err.message || '密码保存失败，请重试'
    } finally {
      passwordBusy = false // eslint-disable-line no-undef
      button.disabled = false
    }
  }

  // 6) 提现验证弹层（去掉示例手续费/示例报价卡）+ 提交 → POST withdrawals
  verifyWithdrawalModal = function () { // eslint-disable-line no-undef
    const w = pendingWithdrawal // eslint-disable-line no-undef
    if (!w) return
    modal( // eslint-disable-line no-undef
      '验证钱包密码',
      `<p class="small">本次申请提现</p><h2 class="red" style="margin:15px 0">${money(w.amount)}</h2>` + // eslint-disable-line no-undef
      `<p class="small">收款方式：${w.method}　${esc(maskAccount(w))}</p>` + // eslint-disable-line no-undef
      (w.coin ? `<p class="small">币种：${esc(w.coin)}　链类型：${esc(w.network)}</p>` : '') +
      // 0mf-d：钱包密码输入防浏览器自动填充/保存（同 base-3 setWalletPassword 组合）。
      `<form id="withdrawPasswordForm" onsubmit="event.preventDefault();confirmWithdrawal()"><label class="field-label" for="withdrawWpin">钱包密码</label><input id="withdrawWpin" data-wpin="1" type="text" minlength="6" maxlength="6" inputmode="numeric" pattern="[0-9]{6}" autocomplete="off" spellcheck="false" autocapitalize="off" autocorrect="off" placeholder="请输入钱包密码" required style="width:100%;-webkit-text-security:disc"><p id="withdrawPasswordError" class="small red" role="alert"></p></form>`,
      '<button class="primary" id="withdrawConfirmButton" type="submit" form="withdrawPasswordForm">确认提现</button>',
    )
    wpinGuard() // eslint-disable-line no-undef
  }
  confirmWithdrawal = async function () { // eslint-disable-line no-undef
    if (passwordBusy || !pendingWithdrawal) return // eslint-disable-line no-undef
    const error = document.getElementById('withdrawPasswordError')
    const pass = document.getElementById('withdrawWpin').value
    const button = document.getElementById('withdrawConfirmButton')
    if (!/^\d{6}$/.test(pass)) { error.textContent = '钱包密码必须为6位数字'; return }
    passwordBusy = true // eslint-disable-line no-undef
    button.disabled = true
    try {
      const w = pendingWithdrawal // eslint-disable-line no-undef
      if (num(w.amount) > num(balance)) { error.textContent = '可用余额已变更，请重新申请'; return } // eslint-disable-line no-undef
      const body = { method: w.bank ? 'BANK' : 'CHAIN', amount: w.amount, wallet_password: pass }
      if (w.bank) {
        body.bank = { name: w.bank.name, account: w.account, holder: w.bank.holder, branch: w.bank.branch, code: w.bank.code }
      } else {
        body.chain = { coin: w.coin || 'USDT', network: w.network || 'TRC-20', address: w.account }
      }
      const payload = await merchantWrite('/merchant/wallet/withdrawals', body)
      state.withdrawalsDraft.unshift(draftWithdrawal(payload.withdrawal))
      withdrawals = state.withdrawalsDraft // eslint-disable-line no-undef
      pendingWithdrawal = null // eslint-disable-line no-undef
      closeModal() // eslint-disable-line no-undef
      await refreshWallet()
      // 新提现会在钱包流水里生成一条 WITHDRAWAL 占款记录：原地刷新当前页。
      if (current === 5) { // eslint-disable-line no-undef
        await loadEntriesPage({ page: state.entriesPage.page, kindLabel: merchantWalletType }) // eslint-disable-line no-undef
      } else {
        state.entriesPage.stale = true
        render() // eslint-disable-line no-undef
      }
      modal( // eslint-disable-line no-undef
        '提现申请成功',
        `<div class="success-icon">✓</div><p style="text-align:center">${money(w.amount)} 的提现申请已提交</p>` + // eslint-disable-line no-undef
        '<div class="rule">钱包密码验证通过。申请状态：待审核。您可以在提现申请记录中查看处理进度。</div>',
      )
    } catch (err) {
      error.textContent = err.message || '验证失败，请重试'
    } finally {
      passwordBusy = false // eslint-disable-line no-undef
      button.disabled = false
    }
  }

  // 7) 钱包密码找回：无对应后端流程，改为联系客服引导（原演示提交流程删除）。
  requestWalletReset = function () { // eslint-disable-line no-undef
    modal( // eslint-disable-line no-undef
      '找回钱包密码',
      `<div class="info"><div><label>店铺名称</label>${esc(shopProfile.name)}</div><div><label>店铺 ID</label>${esc(immutableShopId)}</div></div>` + // eslint-disable-line no-undef
      '<div class="rule">钱包密码找回需联系平台客服，核实店铺资料后由客服重置。</div>',
      action('联系客服', 'support()', true), // eslint-disable-line no-undef
    )
  }
  submitResetRequest = () => {} // eslint-disable-line no-undef
  completeWalletReset = () => {} // eslint-disable-line no-undef

  // 8) 消息发送
  //    - 买家↔商家会话（chatKind=THREAD）→ POST /merchant/chats/{id}/messages，
  //      需求 2：body + image_url 一起发（文字与图片至少一个）；
  //    - 平台客服/旧买家咨询（SupportConversation）→ POST /merchant/conversations/{id}/messages，纯文字。
  sendChat = async function () { // eslint-disable-line no-undef
    const el = document.getElementById('chatInput')
    const v = el.value.trim()
    let image = ''
    try {
      if (chatImageUploading) { toast('图片还在上传，请稍后再发送'); return } // eslint-disable-line no-undef
      if (chatImageDraft && chatImageDraft.conversation === activeConversation) image = chatImageDraft.url // eslint-disable-line no-undef
    } catch { /* base 脚本尚未加载（理论上不会走到） */ }
    if (!v && !image) { toast('请输入消息内容或添加图片'); return } // eslint-disable-line no-undef
    const conv = activeConversation === -1 ? null : conversations[activeConversation] // eslint-disable-line no-undef
    const convId = conv ? conv.id : state.supportConvId
    if (!convId) { toast('会话尚未就绪，请稍后再试'); return } // eslint-disable-line no-undef
    const isThread = Boolean(conv && conv.chatKind === 'THREAD')
    try {
      let msg
      if (isThread) {
        const payload = await merchantWrite(`/merchant/chats/${convId}/messages`, { body: v, image_url: image })
        const sent = payload.message || {}
        msg = ['me', sent.body || '', fmtHM(sent.created_at), sent.image_url || '']
        chatImageDraft = null // eslint-disable-line no-undef
        chatImageUploading = false // eslint-disable-line no-undef
        if (conv && payload.thread && payload.thread.context_product) conv.contextProduct = payload.thread.context_product
      } else {
        const payload = await merchantWrite(`/merchant/conversations/${convId}/messages`, { text: v })
        msg = ['me', payload.message.text, fmtHM(payload.message.created_at)]
      }
      if (conv) conv.messages.push(msg)
      else supportMessages.push(msg) // eslint-disable-line no-undef
      render() // eslint-disable-line no-undef
      document.getElementById('chatInput').focus()
      const h = document.getElementById('chatHistory')
      h.scrollTop = h.scrollHeight
    } catch (error) {
      toast(error.message || '发送失败') // eslint-disable-line no-undef
    }
  }

  // 9) 会话详情懒加载（列表只带最后一条，进线程再取全量；打开即已读）。
  //    需求 3：买家↔商家会话每次「切换到这个会话」都重拉一次详情，顺带刷新
  //    context_product——买家换了商品，商家端切回会话即可看到 B 商品。
  const folioRender = render // eslint-disable-line no-undef
  let threadLoading = false
  render = function () { // eslint-disable-line no-undef
    folioRender()
    maybeLoadThread()
  }
  function maybeLoadThread() {
    if (current !== 9 || threadLoading) return // eslint-disable-line no-undef
    const shell = document.querySelector('.chat-shell')
    if (!shell) return
    // dataset.view === 'thread' 是手机壳（merchant-mobile.js）的打开态标记；
    // 桌面版没有这个壳，选中会话即视为打开（__FOLIO_DESKTOP__ 守卫，手机路径零影响）。
    const wantsThread = shell.dataset.view === 'thread' || window.__FOLIO_DESKTOP__ === true
    if (!wantsThread) return
    const conv = activeConversation === -1 ? null : conversations[activeConversation] // eslint-disable-line no-undef
    const convId = conv ? conv.id : state.supportConvId
    if (!convId) return
    const isThread = Boolean(conv && conv.chatKind === 'THREAD')
    if (isThread) {
      if (state.threadLoadedFor === convId) return
    } else if (state.convLoaded[convId]) {
      return
    }
    threadLoading = true
    // 买家会话没有单独的详情接口：/messages 同时返回 thread（含商品上下文）+ messages。
    const path = isThread ? `/merchant/chats/${convId}/messages` : `/merchant/conversations/${convId}`
    apiRequest(path).then((payload) => {
      const rows = isThread ? (payload.messages || []) : ((payload.conversation || {}).messages || [])
      const msgs = rows.map((m) => [
        m.sender === 'MERCHANT' || m.sender_kind === 'merchant' ? 'me' : 'them',
        isThread ? (m.body || '') : m.text,
        fmtHM(m.created_at),
        isThread ? (m.image_url || '') : '',
      ])
      if (conv) {
        conv.messages = msgs.length ? msgs : conv.messages
        conv.unread = 0
        if (isThread && payload.thread) conv.contextProduct = payload.thread.context_product || conv.contextProduct || null
      } else {
        supportMessages = msgs.length ? msgs : supportMessages // eslint-disable-line no-undef
      }
      if (isThread) state.threadLoadedFor = convId
      else state.convLoaded[convId] = true
      threadLoading = false
      render() // eslint-disable-line no-undef
    }).catch(() => { threadLoading = false })
  }

  // 10) 通知：详情懒加载 + 已读 + 回复 → /merchant/notifications/*
  viewNotice = async function (i) { // eslint-disable-line no-undef
    const n = systemNotices[i] // eslint-disable-line no-undef
    if (!n) return
    if (n.__nid && !readNotices.includes(i)) { // eslint-disable-line no-undef
      await safe(apiRequest(`/merchant/notifications/${n.__nid}`), null)
      readNotices.push(i) // eslint-disable-line no-undef
    }
    render() // eslint-disable-line no-undef
    modal(n[0], `<h3>${n[1]}</h3><p>${n[2]}</p><p class="small">${n[3]}</p>`) // eslint-disable-line no-undef
  }
  markAllPushedNoticesRead = async function () { // eslint-disable-line no-undef
    await safe(merchantWrite('/merchant/notifications/mark-all-read', {}), null)
    readNotices = systemNotices.map((_, i) => i) // eslint-disable-line no-undef
    state.reviews.forEach((r) => { r.merchantRead = true })
    render() // eslint-disable-line no-undef
  }
  merchantProductReviews = () => state.reviews // eslint-disable-line no-undef
  saveMerchantReviewChange = (id, fn) => { // eslint-disable-line no-undef
    const r = state.reviews.find((item) => item.id === id)
    if (!r) return null
    fn(r)
    return r
  }
  const prevOpenPushedProductReview = openPushedProductReview // eslint-disable-line no-undef
  openPushedProductReview = async function (id) { // eslint-disable-line no-undef
    const r = state.reviews.find((item) => item.id === id)
    if (r && !state.reviewDetailLoaded[id]) {
      const payload = await safe(apiRequest(`/merchant/notifications/${id}`), null)
      if (payload && payload.notification) {
        const detail = payload.notification
        r.images = Array.isArray(detail.images) ? detail.images : r.images
        r.replies = (detail.replies || []).map((x) => ({
          id: x.id,
          role: x.role === 'MERCHANT' ? 'merchant' : 'platform',
          content: x.content,
          time: fmtDT(x.created_at),
        }))
        r.merchantRead = true
        state.reviewDetailLoaded[id] = true
      }
    }
    prevOpenPushedProductReview(id)
  }
  replyPushedProductReview = async function (id) { // eslint-disable-line no-undef
    const content = document.getElementById('pushedReviewReply').value.trim()
    const errEl = document.getElementById('pushedReviewError')
    if (!content || content.length > 1000) { errEl.textContent = '请输入1至1000字回复'; return }
    try {
      const payload = await merchantWrite(`/merchant/notifications/${id}/replies`, { content })
      const r = state.reviews.find((item) => item.id === id)
      if (r) {
        r.replies.push({ id: payload.reply.id, role: 'merchant', content: payload.reply.content, time: fmtDT(payload.reply.created_at) })
        r.merchantRead = true
      }
      openPushedProductReview(id) // eslint-disable-line no-undef
      toast('回复已发送') // eslint-disable-line no-undef
    } catch (error) {
      errEl.textContent = error.message || '回复失败'
    }
  }

  // 11) 售后：详情懒加载 + 进度/平台介入/完成/凭证 → /merchant/after-sales/*
  const prevHandleAfter = handleAfter // eslint-disable-line no-undef
  handleAfter = async function (i) { // eslint-disable-line no-undef
    const r = afterRows[i] // eslint-disable-line no-undef
    if (r && !r.__detailLoaded) {
      const payload = await safe(apiRequest(`/merchant/after-sales/${r.id}`), null)
      if (payload && payload.after_sale) {
        applyAfterDetail(i, payload.after_sale)
        r.__detailLoaded = true
      }
    }
    prevHandleAfter(i)
  }
  updateAfter = async function (i, done) { // eslint-disable-line no-undef
    const v = document.getElementById('afterReply').value.trim()
    const errEl = document.getElementById('afterError')
    if (!v) { errEl.textContent = '请填写处理说明'; return }
    const r = afterRows[i] // eslint-disable-line no-undef
    try {
      const payload = await merchantWrite(
        `/merchant/after-sales/${r.id}/actions`,
        done ? { action: 'complete', result: v } : { action: 'progress', progress: v },
      )
      applyAfterDetail(i, payload.after_sale)
      r.__detailLoaded = true
      closeModal() // eslint-disable-line no-undef
      render() // eslint-disable-line no-undef
      toast(done ? '售后已完成' : '售后进度已更新') // eslint-disable-line no-undef
      handleAfter(i) // eslint-disable-line no-undef
    } catch (error) {
      errEl.textContent = error.message || '更新失败'
    }
  }
  escalateAfter = async function (i) { // eslint-disable-line no-undef
    const v = document.getElementById('afterReply').value.trim()
    const errEl = document.getElementById('afterError')
    if (!v) { errEl.textContent = '请填写申请介入的原因'; return }
    const r = afterRows[i] // eslint-disable-line no-undef
    try {
      const payload = await merchantWrite(`/merchant/after-sales/${r.id}/actions`, { action: 'escalate', note: v })
      applyAfterDetail(i, payload.after_sale)
      r.__detailLoaded = true
      closeModal() // eslint-disable-line no-undef
      render() // eslint-disable-line no-undef
      toast('已申请平台介入') // eslint-disable-line no-undef
      handleAfter(i) // eslint-disable-line no-undef
    } catch (error) {
      errEl.textContent = error.message || '申请失败'
    }
  }
  addAfterProof = function (i, input) { // eslint-disable-line no-undef
    const f = input.files && input.files[0]
    if (!f) return
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(f.type) || f.size > 2 * 1024 * 1024) {
      toast('请选择2MB以内的 JPG、PNG 或 WebP 图片'); return // eslint-disable-line no-undef
    }
    const r = afterRows[i] // eslint-disable-line no-undef
    merchantUpload(f, 'review').then((up) => {
      const url = up.url || (up.media && up.media.url) || ''
      return merchantWrite(`/merchant/after-sales/${r.id}/actions`, { action: 'proof', images: [url] })
    }).then((payload) => {
      applyAfterDetail(i, payload.after_sale)
      r.__detailLoaded = true
      handleAfter(i) // eslint-disable-line no-undef
      toast('凭证已上传') // eslint-disable-line no-undef
    }).catch((error) => {
      toast(error.message || '凭证上传失败') // eslint-disable-line no-undef
    })
  }

  // 12) 活动 → POST /merchant/activities/{id}/join
  joinV2 = async function (i) { // eslint-disable-line no-undef
    if (joined.includes(i)) return // eslint-disable-line no-undef
    const a = activityItems[i] // eslint-disable-line no-undef
    if (!a || !a.__id) return
    try {
      await merchantWrite(`/merchant/activities/${a.__id}/join`, {})
      joined.push(i) // eslint-disable-line no-undef
      render() // eslint-disable-line no-undef
      toast('已记录活动参与意向') // eslint-disable-line no-undef
    } catch (error) {
      toast(error.message || '参与失败') // eslint-disable-line no-undef
    }
  }

  // 13) 推荐返佣 modal 数据源 → /merchant/referral
  currentMerchantReferralCode = () => (state.referral && state.referral.referral_code) || '' // eslint-disable-line no-undef
  merchantReferralRules = () => ({ // eslint-disable-line no-undef
    tiers: (state.referral && state.referral.tiers) || [],
    months: (state.referral && state.referral.valid_months) || 12,
    day: 1,
  })
  // 推荐返佣弹层沿用静态稿字段名：后端 referrals/commissions 需映射一次，
  // 否则「我推荐的新商家 / 推荐与返佣明细」两张表会渲染成 undefined。
  const REF_STATE = { PENDING_PAY: '待发放', PAID: '已到账' }
  ownReferralRecords = () => ((state.referral && state.referral.commissions) || []).map((c) => ({ // eslint-disable-line no-undef
    id: c.id,
    month: c.period,
    name: c.referee,
    newMerchant: '',
    shipped: num(c.shipped_amount),
    rate: num(c.rate),
    amount: num(c.amount),
    status: REF_STATE[c.state] || c.state,
    calculatedAt: fmtDT(c.calculated_at),
    settledAt: c.paid_at ? fmtDT(c.paid_at) : '—',
  }))
  ownBoundReferralMerchants = () => ((state.referral && state.referral.referrals) || []).map((r) => ({ // eslint-disable-line no-undef
    newMerchantName: r.name,
    newMerchant: r.merchant_id,
    code: r.code_used,
    approvedAt: fmtDT(r.joined_at),
  }))

  // 14) 店铺资料编辑 → /merchant/media 上传 + PATCH /merchant/profile
  chooseShopAvatar = function (input) { // eslint-disable-line no-undef
    const f = input.files && input.files[0]
    if (!f) return
    const error = document.getElementById('shopProfileError')
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(f.type) || f.size > 2 * 1024 * 1024) {
      error.textContent = '请选择2MB以内的 JPG、PNG 或 WebP 图片'
      input.value = ''
      return
    }
    pendingAvatarFile = f
    const reader = new FileReader()
    reader.onload = () => {
      avatarDraft = reader.result // eslint-disable-line no-undef
      document.getElementById('avatarPreview').innerHTML = `<span class="shop-avatar"><img src="${esc(avatarDraft)}" alt="新头像预览"></span>` // eslint-disable-line no-undef
      error.textContent = ''
    }
    reader.readAsDataURL(f)
  }
  saveShopProfile = async function () { // eslint-disable-line no-undef
    const name = document.getElementById('shopName').value.trim()
    const error = document.getElementById('shopProfileError')
    if (!name || name.length > 30) { error.textContent = '请输入1至30字的店铺名称'; return }
    try {
      let avatar
      if (pendingAvatarFile && avatarDraft) { // eslint-disable-line no-undef
        const up = await merchantUpload(pendingAvatarFile, 'avatar')
        avatar = up.url || (up.media && up.media.url) || ''
      } else if (!avatarDraft) { // eslint-disable-line no-undef
        avatar = ''
      } else {
        avatar = shopProfile.avatar // eslint-disable-line no-undef
      }
      const payload = await merchantWrite('/merchant/profile', { name, avatar }, 'PATCH')
      shopProfile = { name: payload.merchant.name, avatar: payload.merchant.avatar || '' } // eslint-disable-line no-undef
      pendingAvatarFile = null
      avatarDraft = '' // eslint-disable-line no-undef
      closeModal() // eslint-disable-line no-undef
      render() // eslint-disable-line no-undef
      toast('店铺资料已更新') // eslint-disable-line no-undef
    } catch (err) {
      error.textContent = err.message || '保存失败'
    }
  }

  // 15) 逐页服务端拉取：静态稿的分页/筛选按钮只改全局页码与筛选变量，
  //     这里在每次 render 前对比「页面当前数据」和「全局筛选状态」，不一致就
  //     按当前页码/筛选重新请求，请求回来后再渲染。页码窗口 pageWindow 不动。
  function syncRouteData() {
    if (current === 2) { // eslint-disable-line no-undef
      const page = state.catalogPage
      if (page.loading) return
      if (page.stale) {
        // 写操作后的补拉必须跟随「当前 UI 筛选/页码」，不能用写操作前的旧筛选。
        loadCatalogPage({ page: listingPage, q: search, category }) // eslint-disable-line no-undef
        return
      }
      if (
        search !== page.q || // eslint-disable-line no-undef
        category !== page.category || // eslint-disable-line no-undef
        listingPage !== page.page // eslint-disable-line no-undef
      ) {
        loadCatalogPage({ page: listingPage, q: search, category }) // eslint-disable-line no-undef
      }
    } else if (current === 1) { // eslint-disable-line no-undef
      const page = state.listingsPage
      if (page.loading) return
      if (page.stale) {
        loadListingsPage({ page: shopProductPage, q: search, category }) // eslint-disable-line no-undef
        return
      }
      if (
        search !== page.q || // eslint-disable-line no-undef
        category !== page.category || // eslint-disable-line no-undef
        shopProductPage !== page.page // eslint-disable-line no-undef
      ) {
        loadListingsPage({ page: shopProductPage, q: search, category }) // eslint-disable-line no-undef
      }
    } else if (current === 3) { // eslint-disable-line no-undef
      const page = state.ordersPage
      if (page.loading) return
      if (page.stale) {
        loadOrdersPage({
          page: window.ordersPageNo,
          q: queryOrder, // eslint-disable-line no-undef
          status: orderFilter, // eslint-disable-line no-undef
          start: orderFrom, // eslint-disable-line no-undef
          end: orderTo, // eslint-disable-line no-undef
        })
        return
      }
      if (
        queryOrder !== page.q || // eslint-disable-line no-undef
        orderFilter !== page.status || // eslint-disable-line no-undef
        orderFrom !== page.start || // eslint-disable-line no-undef
        orderTo !== page.end || // eslint-disable-line no-undef
        window.ordersPageNo !== page.page
      ) {
        // 筛选变化必须回第 1 页；只有纯翻页才沿用当前页码。
        const filtersDiffer =
          queryOrder !== page.q || // eslint-disable-line no-undef
          orderFilter !== page.status || // eslint-disable-line no-undef
          orderFrom !== page.start || // eslint-disable-line no-undef
          orderTo !== page.end // eslint-disable-line no-undef
        loadOrdersPage({
          page: filtersDiffer ? 1 : window.ordersPageNo,
          q: queryOrder, // eslint-disable-line no-undef
          status: orderFilter, // eslint-disable-line no-undef
          start: orderFrom, // eslint-disable-line no-undef
          end: orderTo, // eslint-disable-line no-undef
        })
      }
    } else if (current === 5) { // eslint-disable-line no-undef
      const page = state.entriesPage
      if (page.loading) return
      if (page.stale) {
        loadEntriesPage({
          page: merchantWalletPage, // eslint-disable-line no-undef
          kindLabel: merchantWalletType, // eslint-disable-line no-undef
        })
        return
      }
      if (
        merchantWalletType !== page.kindLabel || // eslint-disable-line no-undef
        merchantWalletPage !== page.page // eslint-disable-line no-undef
      ) {
        loadEntriesPage({
          page: merchantWalletPage, // eslint-disable-line no-undef
          kindLabel: merchantWalletType, // eslint-disable-line no-undef
        })
      }
    }
  }

  const pagingInnerRender = render // eslint-disable-line no-undef
  render = function () { // eslint-disable-line no-undef
    // 店铺商品/上架中心共用 products 数组：路由切换后按当前页重建一次，
    // 保证商品卡与订单引用的商品下标不错位。
    const mode = current === 1 ? 'shop' : 'catalog' // eslint-disable-line no-undef
    if (mode !== state.catalogMode) rebuildProducts()
    syncRouteData()
    pagingInnerRender()
  }
}

let pendingAvatarFile = null

// ---------------------------------------------------------------------------
// 空态 / 引导（登录表单已移除：商家端无登录页，未登录一律回商城 storefrontUrl()）
// ---------------------------------------------------------------------------
export async function logoutRequest() {
  try {
    await merchantWrite('/admin/auth/logout', {}, 'POST')
  } catch (error) {
    console.warn('[folio] 登出请求失败（忽略）:', error && error.message)
  }
}

export async function loadShops() {
  const payload = await apiRequest('/merchant/shops')
  state.shops = payload.items || []
  return state.shops
}

// 引擎脚本按原顺序注入（classic script，共享全局词法环境）。
const ENGINE_SCRIPTS = [
  '/src/folio/base-1.js',
  '/src/folio/base-2.js',
  '/src/folio/base-3.js',
  '/src/folio/base-4.js',
]

// 桌面版（window.__FOLIO_DESKTOP__ === true，由 boot-desktop.js 打标）：
// 同一引擎前 3 段，不注入手机壳（base-4 / merchant-mobile.js），改注 merchant-desktop.js。
const DESKTOP_ENGINE_SCRIPTS = [
  '/src/folio/base-1.js',
  '/src/folio/base-2.js',
  '/src/folio/base-3.js',
]

function injectScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = false
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('脚本加载失败: ' + src))
    document.body.appendChild(script)
  })
}

export async function bootEngine(entryRoute) {
  wipeDemoStorage()
  // 桌面版（boot-desktop.js 已置 __FOLIO_DESKTOP__）注入 base-1..3 + merchant-desktop.js；
  // 手机版维持原有注入序列不变（base-1..4 + merchant-mobile.js）。
  const desktop = window.__FOLIO_DESKTOP__ === true
  for (const src of desktop ? DESKTOP_ENGINE_SCRIPTS : ENGINE_SCRIPTS) await injectScript(src)

  // merchant-mobile.js 依赖的烘焙开关与头部工具数据，必须在注入它之前就位。
  window.__JOYPLAY_SHOPS__ = state.shops.map((s) => ({ id: s.id, name: s.name }))
  window.__JOYPLAY_SHOP_ID__ = getCurrentShop()
  window.__JOYPLAY_ACTIONS__ = {
    // POST /merchant/switch-to-mall：后端按同邮箱映射/创建买家账号，返回 60 秒
    // 一次性 handoff_token + 已拼好的 shopping 端 redirect_url。登录态由购物端
    // 在自己的 host 上兑换 token 后写入（跨 host cookie 会被浏览器拒绝，不能
    // 在这里拼 STOREFRONT_URL）。失败（400 STAFF_EMAIL_REQUIRED / 401）由
    // ApiError 抛出中文提示。
    switchToMall: async () => {
      const payload = await merchantWrite('/merchant/switch-to-mall', {})
      window.location.href = payload.redirect_url || STOREFRONT_URL
    },
    searchCatalog: (filters) => refreshCatalog(filters),
    searchListings: (filters) => refreshListings(filters),
    // 商家端手动切语言后重拉数据：商品名/售后商品等由后端按 locale 返回，
    // 只重绘 DOM 不够。列表会回到第 1 页（与整页刷新同口径）。
    reloadData: async () => {
      await fetchAll()
      state.convLoaded = {}
      state.threadLoadedFor = ''
      state.reviewDetailLoaded = {}
      populateGlobals()
      rebuildProducts()
      render() // eslint-disable-line no-undef
    },
    switchShop: (id) => switchShop(id),
    // 登出：清 staff 会话后回商城（商家端没有登录页；再进商家端请从
    // 购物端【切换商家端】进入）。桌面/手机统一行为。
    logout: async () => {
      await logoutRequest()
      location.replace(STOREFRONT_URL)
    },
    // 桌面版专属：/orders/:id 深链与浏览器前进/后退共用（merchant-desktop.js 调用）。
    ...(desktop ? { openOrder: (orderId) => openOrderById(orderId) } : {}),
  }
  if (desktop) {
    await injectScript('/src/folio/merchant-desktop.js')
  } else {
    window.__JOYPLAY_MOBILE__ = true
    window.__JOYPLAY_CONCEPT__ = 'folio'
    await injectScript('/src/folio/merchant-mobile.js')
  }

  // 拉取当前店铺的全部模块数据，再映射进静态稿全局状态对象。
  await fetchAll()
  populateGlobals()
  overrideActions()

  // 入口路由映射（?p= → 静态稿 route id），地址条还原为干净路径由 boot.js 完成。
  if (entryRoute) {
    if (entryRoute.route === 4) {
      let idx = orders.findIndex((o) => o[0] === entryRoute.orderId) // eslint-disable-line no-undef
      if (idx < 0) {
        // 订单详情深链：该单不一定在第 1 页，按订单号服务端定位后并入当前页。
        const hit = await locateOrderForEntry(entryRoute.orderId)
        if (hit) idx = orders.findIndex((o) => o[0] === entryRoute.orderId) // eslint-disable-line no-undef
      }
      if (idx >= 0) {
        selected = idx // eslint-disable-line no-undef
        current = 4 // eslint-disable-line no-undef
      } else {
        current = 3 // eslint-disable-line no-undef
      }
    } else {
      current = entryRoute.route // eslint-disable-line no-undef
    }
    render() // eslint-disable-line no-undef
    window.scrollTo(0, 0)
  }
}

// 订单详情深链定位：/merchant/orders?q=<订单号>（后端同时匹配子单/父单 UUID）。
// 结果并入 ordersPage 并标记 stale，返回列表页时再按默认筛选重拉第 1 页。
async function locateOrderForEntry(orderId) {
  try {
    const payload = await apiRequest(
      `/merchant/orders?page=1&page_size=${ORDERS_PAGE_SIZE}&q=${encodeURIComponent(orderId)}`,
    )
    const hit = (payload.items || []).find((it) => it.id === orderId || it.order_id === orderId)
    if (!hit) return null
    state.ordersPage.items = payload.items || []
    state.ordersPage.total = num(payload.total)
    state.ordersPage.counts = payload.counts || {}
    state.ordersPage.stale = true
    rebuildProducts()
    return hit
  } catch (error) {
    console.warn('[folio] 订单定位失败:', error && error.message)
    return null
  }
}

// 桌面版：浏览器前进/后退到 /orders/:id 时落位订单详情（bootEngine 入口分支的
// 会话内等价操作）。当前页找不到就服务端定位；找不到单子回订单列表（go 已被
// merchant-desktop.js 包装，地址条同步为 /orders）。返回是否成功落位详情。
async function openOrderById(orderId) {
  let idx = orders.findIndex((o) => o[0] === orderId) // eslint-disable-line no-undef
  if (idx < 0) {
    const hit = await locateOrderForEntry(orderId)
    if (hit) idx = orders.findIndex((o) => o[0] === orderId) // eslint-disable-line no-undef
  }
  if (idx < 0) {
    go(3) // eslint-disable-line no-undef
    return false
  }
  selected = idx // eslint-disable-line no-undef
  current = 4 // eslint-disable-line no-undef
  render() // eslint-disable-line no-undef
  window.scrollTo(0, 0)
  return true
}

export async function switchShop(id) {
  if (!id || id === getCurrentShop()) return
  setCurrentShop(id)
  try { window.localStorage.setItem('joybuy.merchant.shop', id) } catch { /* ignore */ }
  document.documentElement.dataset.folioBoot = 'pending'
  try {
    await fetchAll()
    window.__JOYPLAY_SHOP_ID__ = id
    // 头部店铺切换 select 同步显示当前店。
    const select = document.querySelector('.shell-tools select.shop-switch')
    if (select) select.value = id
    state.convLoaded = {}
    state.threadLoadedFor = ''
    state.reviewDetailLoaded = {}
    populateGlobals()
    // 重置纯 UI 状态到首页，避免上一店的 selected/activeConversation 悬空。
    current = 0 // eslint-disable-line no-undef
    selected = 0 // eslint-disable-line no-undef
    activeConversation = -1 // eslint-disable-line no-undef
    rebuildProducts()
    render() // eslint-disable-line no-undef
    window.scrollTo(0, 0)
    toast('已切换店铺') // eslint-disable-line no-undef
  } finally {
    document.documentElement.dataset.folioBoot = 'ready'
  }
}
