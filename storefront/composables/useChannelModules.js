import { computed } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useMarketLocale } from './useMarketLocale'

// 频道页（/minihome/<code>）的商品楼层：管理端/默认配置落库，公开接口只返回
// enabled 楼层与有序商品（与 /search item 同构）。空数组时页面回退通用楼层。
export function useChannelModules(code) {
  const config = useRuntimeConfig()
  const { apiQuery } = useMarketLocale()
  const url = computed(() => {
    const value = String(code.value || '').trim()
    if (!value) return null
    const path = `/channels/${encodeURIComponent(value)}/modules`
    const query = new URLSearchParams(apiQuery.value).toString()
    const suffix = query ? `?${query}` : ''
    return import.meta.server
      ? `${config.apiBaseInternal}${path}${suffix}`
      : `/api/v1${path}${suffix}`
  })

  const { data } = useFetch(url, {
    // key 必须随频道 code + 语言变化，否则切换语言/频道会复用旧楼层。
    key: computed(() => `channel-modules-${code.value}-${apiQuery.value.locale || ''}`),
    default: () => ({ modules: [] }),
  })

  const modules = computed(() => data.value?.modules || [])
  return { modules }
}
