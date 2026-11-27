// 旧商品 URL 别名（批次 CB2 同款多规格合并）。
//
// 合并后旧 SPU 归档，但旧链接不能 404：`/p/<old_public_id>` 命中后端
// `GET /api/v1/products/aliases/<old_public_id>` 时 301 到 `/p/<keep>`。
// 这里只放纯逻辑（路径解析、缓存、跳转目标），真正的 HTTP 请求与 301 在
// `server/middleware/pdp-alias.js`，方便单测不起服务器。

/** 别名查询结果的进程内缓存时长：合并是低频写、旧链接是高频读。 */
export const PDP_ALIAS_CACHE_TTL_MS = 60_000

/** 缓存条数上限（超限整体清空，避免 dev 长跑内存无限涨）。 */
export const PDP_ALIAS_CACHE_MAX_ENTRIES = 5000

// 2026-11-27 全站编号改造：商品号最终仍是 UUID（JYP 方案已回退）；这里同时宽松
// 接受 JY 前缀编号，避免其它编号体系（订单/售后等）混入 `/p/` 时 301 失效。
// JY 前缀编号存储大写、查询不区分大小写（后端 `iexact`），这里统一归一成大写，
// 保证 301 目标 URL 与后端返回的规范号一致；旧 UUID 保持小写不变。
const JY_PUBLIC_ID_RE = /^JY[A-Z0-9]{8,}$/i
const LEGACY_UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const PDP_PATH_RE = /^\/p\/([^/]+)\/?$/

/** 归一化 `/p/<id>` 里的编号；非法（历史脏链接）返回空串。 */
function normalisePublicId(value) {
  const id = String(value == null ? '' : value).trim()
  if (JY_PUBLIC_ID_RE.test(id)) return id.toUpperCase()
  if (LEGACY_UUID_RE.test(id)) return id.toLowerCase()
  return ''
}

/**
 * 从请求路径里取出 PDP 的 public_id；不是 `/p/<JY 前缀编号 | 旧 UUID>` 时
 * 返回空串。其它 `/p/xxx`（历史脏链接）不查别名，保持原有 404 行为。
 */
export function pdpPublicIdFromPath(pathname) {
  const match = PDP_PATH_RE.exec(String(pathname || '').split('?')[0])
  if (!match) return ''
  let id = match[1]
  try {
    id = decodeURIComponent(id)
  } catch {
    return ''
  }
  return normalisePublicId(id)
}

/** 保留商品的落地地址（带上原查询串，如 ?offer=<id>）。 */
export function aliasRedirectTarget(canonicalPublicId, search = '') {
  const id = normalisePublicId(canonicalPublicId)
  if (!id) return ''
  const suffix = search ? (search.startsWith('?') ? search : `?${search}`) : ''
  return `/p/${id}${suffix}`
}

/**
 * 极简 TTL 缓存。`undefined` = 未缓存；空串表示「查过了，没有别名」，
 * 负结果同样缓存，避免每个旧链接请求都打后端。
 */
export function createAliasCache({
  ttlMs = PDP_ALIAS_CACHE_TTL_MS,
  maxEntries = PDP_ALIAS_CACHE_MAX_ENTRIES,
  now = () => Date.now(),
} = {}) {
  const store = new Map()
  return {
    get(key) {
      const hit = store.get(key)
      if (!hit) return undefined
      if (hit.expiresAt <= now()) {
        store.delete(key)
        return undefined
      }
      return hit.value
    },
    set(key, value) {
      if (store.size >= maxEntries) store.clear()
      store.set(key, { value, expiresAt: now() + ttlMs })
    },
    get size() {
      return store.size
    },
  }
}

/**
 * 解析一次 PDP 请求是否需要 301。
 *
 * @param {object} options
 * @param {string} options.path 请求路径（可含查询串）
 * @param {(publicId: string) => Promise<string>} options.fetchCanonical
 *   命中别名返回保留商品 id，未命中返回空串。
 * @param {ReturnType<typeof createAliasCache>} [options.cache]
 * @returns {Promise<string>} 需要 301 的目标地址；空串表示照常渲染。
 */
export async function resolvePdpAlias({ path, fetchCanonical, cache }) {
  const publicId = pdpPublicIdFromPath(path)
  if (!publicId) return ''
  const queryIndex = String(path).indexOf('?')
  const search = queryIndex >= 0 ? String(path).slice(queryIndex) : ''
  let canonical = cache ? cache.get(publicId) : undefined
  if (canonical === undefined) {
    try {
      canonical = (await fetchCanonical(publicId)) || ''
    } catch {
      // 别名服务不可用时不能挡住正常 PDP：本次按「无别名」处理，但不缓存，
      // 让后端恢复后下次请求能重新查到。
      return ''
    }
    if (cache) cache.set(publicId, canonical)
  }
  return aliasRedirectTarget(canonical, search)
}
