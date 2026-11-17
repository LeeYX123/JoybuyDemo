<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  total: { type: Number, default: 0 },
  hasNext: { type: Boolean, default: false },
})
const emit = defineEmits(['change'])

const jumpInput = ref('')

const lastPage = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

function pageItems() {
  const last = lastPage.value
  if (last <= 7) {
    return Array.from({ length: last }, (_, index) => ({ type: 'page', value: index + 1 }))
  }
  const current = Math.min(Math.max(props.page, 1), last)
  let start = Math.max(2, current - 1)
  let end = Math.min(last - 1, current + 1)
  if (current === 1) end = Math.min(last - 1, 3)
  if (current === last) start = Math.max(2, last - 2)
  const items = [{ type: 'page', value: 1 }]
  if (start > 2) items.push({ type: 'ellipsis', key: 'left' })
  for (let index = start; index <= end; index += 1) items.push({ type: 'page', value: index })
  if (end < last - 1) items.push({ type: 'ellipsis', key: 'right' })
  items.push({ type: 'page', value: last })
  return items
}

function jumpTo() {
  const target = Number.parseInt(jumpInput.value, 10)
  jumpInput.value = ''
  if (Number.isNaN(target) || target < 1) return
  const clamped = Math.min(target, lastPage.value)
  if (clamped !== props.page) emit('change', clamped)
}
</script>

<template>
  <div v-if="total > pageSize" class="pager">
    <button type="button" class="btn btn--sm" :disabled="page <= 1" @click="emit('change', 1)">
      首页
    </button>
    <button
      type="button"
      class="btn btn--sm"
      :disabled="page <= 1"
      @click="emit('change', page - 1)"
    >
      上一页
    </button>
    <template
      v-for="item in pageItems()"
      :key="item.type === 'page' ? `p${item.value}` : `e${item.key}`"
    >
      <span v-if="item.type === 'ellipsis'" class="pager__ellipsis">…</span>
      <button
        v-else
        type="button"
        class="btn btn--sm"
        :class="{ 'btn--primary': item.value === page }"
        @click="emit('change', item.value)"
      >
        {{ item.value }}
      </button>
    </template>
    <button
      type="button"
      class="btn btn--sm"
      :disabled="!hasNext"
      @click="emit('change', page + 1)"
    >
      下一页
    </button>
    <button
      type="button"
      class="btn btn--sm"
      :disabled="page >= lastPage"
      @click="emit('change', lastPage)"
    >
      末页
    </button>
    <input
      v-model="jumpInput"
      class="pager__jump"
      type="number"
      min="1"
      :max="lastPage"
      placeholder="页码"
      @keyup.enter="jumpTo"
    />
    <button type="button" class="btn btn--sm" @click="jumpTo">跳转</button>
  </div>
</template>

<style scoped>
.pager__ellipsis {
  padding: 0 3px;
  user-select: none;
}

.pager__jump {
  width: 64px;
  height: 26px;
  padding: 4px 7px;
  font-size: 11px;
  color: var(--ink);
  border: 1px solid var(--border);
  border-radius: 3px;
  background: #fff;
}

.pager__jump:focus {
  outline: none;
  border-color: var(--primary);
}
</style>
