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
export const LANGUAGE_EVENT = 'joybuy:languagechange'

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
  '.merchant-order .order-top > span',
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
    window.localStorage.setItem(LANGUAGE_KEY, lang)
  } catch {
    /* ignore */
  }
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN'
  document.documentElement.dataset.merchantLang = lang
  localize()
  window.dispatchEvent(new CustomEvent(LANGUAGE_EVENT, { detail: { lang } }))
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
export function installDebugI18n() {
  window.__JOYPLAY_I18N__ = { getLang, setLang, t, localize, stopAutoLocalize }
}
