// 旧商品 URL 301（批次 CB2 同款多规格合并）。
//
// `/p/<被合并的旧 id>` 命中后端别名表时在 SSR 渲染前 301 到保留商品；
// 未命中/后端不可用时一律继续（`return`），绝不因为别名查询挡住 PDP。
// 逻辑与缓存在 `utils/pdpAlias.js`，这里只做 HTTP 适配。
// 注意：server 侧必须用 Nuxt 别名（~~ = 项目根），相对路径在 Nitro 打包后会
// 解析到错误的盘符根目录（实测 `E:\storefront\utils\...`）。
import { createAliasCache, resolvePdpAlias } from '~~/utils/pdpAlias'

const aliasCache = createAliasCache()

export default defineEventHandler(async (event) => {
  const path = event.path || ''
  if (!path.startsWith('/p/')) return

  const config = useRuntimeConfig(event)
  const apiBase = String(config.apiBaseInternal || '').replace(/\/$/, '')
  if (!apiBase) return

  const target = await resolvePdpAlias({
    path,
    cache: aliasCache,
    fetchCanonical: async (publicId) => {
      try {
        const payload = await $fetch(`${apiBase}/products/aliases/${publicId}`, {
          timeout: 3000,
          headers: { accept: 'application/json' },
        })
        return payload?.canonical_public_id || ''
      } catch {
        return ''
      }
    },
  })
  if (target) {
    return sendRedirect(event, target, 301)
  }
})
