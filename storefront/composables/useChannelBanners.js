import { computed } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

// 频道页（/minihome/<code>）顶部 banner：管理端按频道配置，公开接口只返回
// enabled 的条目。没有配置时返回空数组，页面据此回退渐变占位。
export function useChannelBanners(code) {
  const config = useRuntimeConfig()
  const query = computed(() => {
    const value = String(code.value || '').trim()
    return value ? `?channel_code=${encodeURIComponent(value)}` : ''
  })
  const url = computed(() =>
    import.meta.server
      ? `${config.apiBaseInternal}/channel-banners${query.value}`
      : `/api/v1/channel-banners${query.value}`,
  )

  const { data } = useFetch(url, {
    // key 必须随频道 code 变化，否则频道间切换会复用上一频道的缓存。
    key: computed(() => `channel-banners-${code.value}`),
    default: () => ({ items: [] }),
  })

  const banners = computed(() => data.value?.items || [])
  return { banners }
}
