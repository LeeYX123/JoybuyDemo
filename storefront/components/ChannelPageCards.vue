<script setup>
// 频道页活动卡片（需求文档03 13.2，2026-11-23 多组升级）：品类卡下方/宠物页
// 第一个商品楼层下方的运营位图。
//
// 数据由页面经 composables/useChannelPageCards.js 拉取
// （GET /api/v1/cms/channel-page-cards?channel=<channel_code>，
//   → { channel, layout, groups: [{ group_index, layout, count }], items, total }）。
// 本组件只负责把 items/groups 归一化成「若干组」并逐组渲染
// （规则见 utils/channelCards.js）：
//   - 按 group_index 升序渲染各组，组内按 sort_order 升序；
//   - 每组按 layout 渲染 row2 / row3 / row3_scroll（ChannelCardRow）；
//   - groups 缺失 → 按 items[].group_index / items[].layout 分桶兜底；
//   - 空数据整块不渲染（不写「暂无」占位、不留空白）。
// 组与组之间 32px（真站模块纵向节奏），整块下方 32px 由外层 margin 负责。
import { computed } from 'vue'

import { normalizeChannelCardGroups } from '../utils/channelCards'

import ChannelCardRow from './ChannelCardRow.vue'

const props = defineProps({
  // 接口 items 原样传进来（组件内按 sort_order 再排一次）。
  items: {
    type: Array,
    default: () => [],
  },
  // 接口 groups（组顺序与每组布局）；缺失时按 items 兜底分桶。
  groups: {
    type: Array,
    default: () => [],
  },
})

const cardGroups = computed(() => normalizeChannelCardGroups(props.items, props.groups))
</script>

<template>
  <div v-if="cardGroups.length > 0" class="channel-cards">
    <ChannelCardRow
      v-for="group in cardGroups"
      :key="group.index"
      class="channel-cards__group"
      :items="group.items"
      :layout="group.layout"
    />
  </div>
</template>

<style scoped>
/* Module rhythm on the live site: 32px above/below every module
   (measurement.md §0.7), owned here so an empty module leaves no gap.
   多组时组与组之间同样是 32px。 */
.channel-cards {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  margin-bottom: var(--space-8);
}
</style>
