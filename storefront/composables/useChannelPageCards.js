import { computed } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

// 频道页（/minihome/<code>）品类卡下方/宠物页楼层之间的活动卡片（13.2）：
// 管理端按频道配置，公开接口只返回 enabled 的条目。
// 2026-11-23 起接口按「组」返回（groups + items[].group_index），
// 组件侧归一化与布局规则见 utils/channelCards.js；没有配置时返回空数组，
// 页面据此整块不渲染。
export async function useChannelPageCards(channelCode) {
  const config = useRuntimeConfig()
  const url = computed(() => {
    const value = String(channelCode.value || '').trim()
    if (!value) return null
    const path = `/cms/channel-page-cards?channel=${encodeURIComponent(value)}`
    return import.meta.server ? `${config.apiBaseInternal}${path}` : `/api/v1${path}`
  })

  const { data } = await useFetch(url, {
    // key 必须随频道 code 变化，否则切换频道会复用上一频道的卡片。
    key: computed(() => `channel-page-cards-${channelCode.value}`),
    default: () => ({ items: [], groups: [] }),
  })

  const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
  const groups = computed(() => (Array.isArray(data.value?.groups) ? data.value.groups : []))
  return { items, groups }
}
