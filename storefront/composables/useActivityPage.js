import { computed } from 'vue'
import { useFetch, useRuntimeConfig, useRoute } from '#imports'

// 活动页 / 店铺页数据（2026-11-25）：/active/<真站id>、/store/<真站id> 共用。
// 后端只读接口按 (kind, external_id) 返回 hero + 分区；页面停用/不存在时
// 接口 404，这里把 data 置空由页面渲降级态，不抛错阻断渲染。
export function useActivityPage(kind) {
  const route = useRoute()
  const config = useRuntimeConfig()
  const externalId = computed(() => String(route.params.id || ''))

  // 与 useCart/useChannelModules 同口径：SSR 走内网地址，浏览器端走同源
  // /api/v1（dev 由 nitro devProxy 转发，生产由 Nginx 转发）。
  // 只用 apiBaseInternal 会让客户端导航（首页点卡片）请求 127.0.0.1:8000，
  // 跨域被拦 → data 为空 → 页面误显示「该页面暂不可用」。
  const url = computed(() =>
    import.meta.server
      ? `${config.apiBaseInternal}/activity-pages/${kind}/${externalId.value}`
      : `/api/v1/activity-pages/${kind}/${externalId.value}`,
  )
  const { data, pending } = useFetch(url, {
    key: `activity-page-${kind}-${externalId.value}`,
    ignoreResponseError: true,
  })

  const page = computed(() => (data.value && !data.value.error ? data.value : null))
  // 慢网络/客户端导航时 data 还没到，pending 为真——页面必须先渲染骨架，
  // 不能把「还在加载」当成「页面不存在」（2026-11-26 用户反馈）。
  const loading = computed(() => pending.value && !page.value)
  return { page, pending, loading }
}
