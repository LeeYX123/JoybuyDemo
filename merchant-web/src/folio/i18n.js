// ---------------------------------------------------------------------------
// folio/i18n.js — 渲染后 DOM 本地化层。
//
// 静态稿原码（base-1..4.js + merchant-mobile.js）保持一字不改：所有界面文案
// 仍按中文原样渲染，本模块在渲染完成后遍历 DOM：
//   1. 精确字典 locale-en.js/PHRASES（中文原文 → 英文）
//   2. 正则模式 locale-en.js/PATTERNS（带变量的文案，如「共 8353 件」）
// 只替换文本节点与 placeholder/title/aria-label/alt，绝不碰 input/textarea
// 的 value；商品名、店名、买家昵称、消息正文等用户数据通过 NO_TRANSLATE
// 容器跳过。
//
// 幂等与还原：
// - 每个被翻译的文本节点在 WeakMap 里保存中文原文；重复 localize 时英文
//   文本不会再次命中字典（en→en 不变），切回中文时按保存的原文还原。
// - 属性同理按「元素 + 属性名」保存原文。
// - MutationObserver 监听 body 子树（childList + characterData + 四个可译
//   属性），30ms 防抖后自动重跑，覆盖静态稿频繁 innerHTML re-render。
// ---------------------------------------------------------------------------
import {
  translateEn,
  translateZh,
} from './locale-en.js'

export const LANGUAGE_KEY = 'joybuy.merchant.language'
// 商品数据用的原始 locale（en-GB / zh-CN / de-DE …）。界面只有中/英两档，
// 但后端按这个值取 SpuTranslation，所以必须单独存一份原值。
export const LOCALE_KEY = 'joybuy.merchant.locale'
export const LANGUAGE_EVENT = 'joybuy:languagechange'

// 购物端 locale（useLocale.localeCode 已归一化）→ 商家端商品数据 locale。
// 只做别名收敛；未列出的直接透传（如 de-DE / ja-JP）。
const LOCALE_ALIASES = {
  en: 'en-GB',
  'en-GB': 'en-GB',
  'en-US': 'en-GB',
  zh: 'zh-CN',
  'zh-CN': 'zh-CN',
  'zh-TW': 'zh-CN',
  de: 'de-DE',
  fr: 'fr-FR',
  nl: 'nl-NL',
  lb: 'lb-LU',
  ja: 'ja-JP',
  ko: 'ko-KR',
}

export function normalizeLocale(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  return LOCALE_ALIASES[raw] || LOCALE_ALIASES[raw.split('-')[0].toLowerCase()] || raw
}

// 界面语言只有中/英：中文（zh*）→ zh，其余一律 → en（用户口径）。
export function uiLangForLocale(locale) {
  return /^zh/i.test(String(locale || '')) ? 'zh' : 'en'
}

export function getProductLocale() {
  try {
    const saved = window.localStorage.getItem(LOCALE_KEY)
    if (saved) return normalizeLocale(saved)
  } catch {
    /* ignore */
  }
  return getLang() === 'en' ? 'en-GB' : 'zh-CN'
}

const CJK = /[\u3400-\u9fff\uf900-\ufaff]/
const TRANSLATABLE_ATTRS = ['placeholder', 'title', 'aria-label', 'alt']
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'CODE', 'PRE'])
// 用户数据容器：这些节点里的文本不翻译（商品名/店名/买家昵称/消息正文/
// 通知内容/售后问题描述/地址值等）。属性仍会按需翻译（例如通知行的
// aria-label 前缀「未读通知：」）。
const NO_TRANSLATE_TEXT = [
  '.identity-name',
  '.shop-switch',
  '.product-name',
  '.product h3',
  '.order-item h2',
  '.detail-product h3',
  '.chat-product-context h3',
  '.bubble',
  '.conversation-text small',
  '.notice-summary',
  '.system-notice',
  '.service-case h2',
  '.review-text',
  '.review-author',
  '.od-information dd',
  '.order-art',
  // 手机端订单卡：只跳过第一个 span（订单号），后面的状态 tag 必须翻译。
  '.merchant-order .order-top > span:first-child',
].join(',')

// 在 NO_TRANSLATE 容器内部仍需翻译的 UI 控件（容器是为了跳过用户数据，
// 但挂在上面的操作按钮/静态说明是界面文案）：
// - 通知卡片（.system-notice 整卡跳过）里的「查看详情」按钮；
// - 平台客服会话行（.conversation.pinned）的静态副标题「平台专属客服 · 单独联系」。
const NO_TRANSLATE_EXCEPTIONS = [
  '.system-notice button',
  '.system-notice .link',
  '.conversation.pinned .conversation-text small',
].join(',')

let lang = 'zh'
let observer = null
let timer = null
let applying = false
let titleOrig = null
const textOrig = new WeakMap() // Text -> { raw }
const attrOrig = new WeakMap() // Element -> Map(attr -> raw)

function normalizeLang(value) {
  if (value === 'en' || value === 'English') return 'en'
  return 'zh'
}

export function getLang() {
  try {
    const saved = window.localStorage.getItem(LANGUAGE_KEY)
    if (saved) lang = normalizeLang(saved)
  } catch {
    /* localStorage 不可用时使用内存值 */
  }
  return lang
}

export function setLang(next) {
  lang = normalizeLang(next)
  try {
    // 壳脚本（merchant-desktop.js / merchant-mobile.js）读的就是这两个中文面值，
    // 不能写 'en'/'zh'，否则它们的语言标签与选中态会退化。
    window.localStorage.setItem(LANGUAGE_KEY, lang === 'en' ? 'English' : '简体中文')
    // 手动切换时商品数据跟着切到对应 locale（handoff 带入的第三方 locale 由
    // applyLocaleFromUrl 在其后覆盖）。
    window.localStorage.setItem(LOCALE_KEY, lang === 'en' ? 'en-GB' : 'zh-CN')
  } catch {
    /* localStorage 不可用时使用内存值 */
  }
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN'
  document.documentElement.dataset.merchantLang = lang
  localize()
  window.dispatchEvent(new CustomEvent(LANGUAGE_EVENT, { detail: { lang } }))
}

// 从商家端地址栏的 ?lang=<locale> 落地语言（购物端【切换商家端】带入）。
// 返回 { locale, lang } 或 null（无参数）。只写 localStorage，不改地址栏。
export function applyLocaleFromUrl(search = typeof location !== 'undefined' ? location.search : '') {
  let raw
  try {
    raw = (new URLSearchParams(search).get('lang') || '').trim()
  } catch {
    return null
  }
  if (!raw) return null
  const locale = normalizeLocale(raw)
  const next = uiLangForLocale(locale)
  setLang(next)
  try {
    // 覆盖 setLang 写的中/英默认值：商品数据按购物端原始语言请求。
    window.localStorage.setItem(LOCALE_KEY, locale)
  } catch {
    /* ignore */
  }
  return { locale, lang: next }
}

// JS 主动取译文（toast / 动态 title 等）。中文模式下返回原文。
export function t(zh) {
  if (getLang() !== 'en') return zh
  return translateZh(String(zh)) || zh
}

export function tf(text) {
  return getLang() === 'en' ? translateZh(String(text)) || text : translateEn(String(text)) || text
}

function isSkippedText(node) {
  const parent = node.parentElement
  if (!parent) return true
  if (SKIP_TAGS.has(parent.tagName)) return true
  if (parent.closest('[data-i18n-skip]')) return true
  // 例外优先于用户数据容器（容器仍跳过其余文本，只放行挂在上面的 UI 控件）。
  if (parent.closest(NO_TRANSLATE_EXCEPTIONS)) return false
  return Boolean(parent.closest(NO_TRANSLATE_TEXT))
}

function splitWhitespace(raw) {
  const match = String(raw).match(/^(\s*)([\s\S]*?)(\s*)$/)
  return { lead: match[1], core: match[2], trail: match[3] }
}

function localizeTextNode(node) {
  const { lead, core, trail } = splitWhitespace(node.nodeValue || '')
  if (!core) return
  const stored = textOrig.get(node)
  if (getLang() === 'en') {
    if (!CJK.test(core)) {
      // 已经是英文（或纯数字/品牌）——保持幂等，不重复翻译。
      if (stored && core === translateZh(stored.raw)?.trim()) return
      return
    }
    const en = translateZh(core)
    if (en == null || en === core) return
    if (!stored || stored.core !== core) {
      textOrig.set(node, { raw: node.nodeValue || core, core })
    }
    node.nodeValue = lead + en + trail
    return
  }
  // 切回中文：按保存的中文原文还原（保留原始空白）。
  if (stored) {
    node.nodeValue = stored.raw
  }
}

function localizeAttributes(el) {
  for (const attr of TRANSLATABLE_ATTRS) {
    const raw = el.getAttribute(attr)
    if (raw == null || !CJK.test(raw)) continue
    const core = raw.trim()
    if (!core) continue
    let store = attrOrig.get(el)
    if (getLang() === 'en') {
      const en = translateZh(core)
      if (en == null || en === core) continue
      if (!store) {
        store = new Map()
        attrOrig.set(el, store)
      }
      store.set(attr, raw)
      el.setAttribute(attr, en)
    } else if (store && store.has(attr)) {
      el.setAttribute(attr, store.get(attr))
    }
  }
}

function localizeTitle() {
  if (getLang() === 'en') {
    const current = document.title
    if (!CJK.test(current)) return
    if (titleOrig == null) titleOrig = current
    const en = translateZh(current.trim())
    if (en) document.title = en
  } else if (titleOrig != null) {
    document.title = titleOrig
    titleOrig = null
  }
}

export function localize(root = document.body) {
  if (!root) return
  if (applying) return
  applying = true
  try {
    const start = root.nodeType === Node.TEXT_NODE ? root : root
    if (start.nodeType === Node.TEXT_NODE) {
      if (!isSkippedText(start)) localizeTextNode(start)
    } else {
      const walker = document.createTreeWalker(start, NodeFilter.SHOW_TEXT)
      let node = walker.nextNode()
      while (node) {
        if (!isSkippedText(node)) localizeTextNode(node)
        node = walker.nextNode()
      }
      for (const el of start.querySelectorAll('*')) {
        localizeAttributes(el)
      }
      if (start.nodeType === Node.ELEMENT_NODE) localizeAttributes(start)
    }
    if (start === document.body) localizeTitle()
  } finally {
    applying = false
  }
}

// 清掉地址栏里的 ?lang=（避免刷新/前进后退时重复覆盖 localStorage），
// 其余 query 与 hash 原样保留。
export function stripLocaleParam() {
  if (typeof location === 'undefined' || typeof history === 'undefined') return
  if (!location.search) return
  const params = new URLSearchParams(location.search)
  if (!params.has('lang')) return
  params.delete('lang')
  const query = params.toString()
  try {
    history.replaceState(
      history.state,
      '',
      location.pathname + (query ? `?${query}` : '') + location.hash,
    )
  } catch {
    /* ignore */
  }
}

export function startAutoLocalize() {
  if (observer || typeof MutationObserver === 'undefined') return
  const schedule = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      if (getLang() === 'en') localize(document.body)
    }, 30)
  }
  observer = new MutationObserver(schedule)
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: TRANSLATABLE_ATTRS,
  })
  if (getLang() === 'en') localize(document.body)
}

export function stopAutoLocalize() {
  if (observer) observer.disconnect()
  observer = null
  if (timer) clearTimeout(timer)
  timer = null
}

// 测试/调试入口：不参与业务逻辑。
// 同时挂成 __MERCHANT_I18N__：classic 壳脚本（merchant-desktop.js /
// merchant-mobile.js）通过它触发语言切换，不能再 import ES 模块。
export function installDebugI18n() {
  const api = {
    getLang,
    setLang,
    t,
    tf,
    localize,
    normalizeLocale,
    getProductLocale,
    startAutoLocalize,
    stopAutoLocalize,
  }
  window.__JOYPLAY_I18N__ = api
  window.__MERCHANT_I18N__ = api
}
