<script setup>
const props = defineProps({
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
  total: { type: Number, default: 0 },
  hasNext: { type: Boolean, default: false },
})
const emit = defineEmits(['change'])

function pages() {
  const last = Math.max(1, Math.ceil(props.total / props.pageSize))
  const start = Math.max(1, props.page - 2)
  const end = Math.min(last, start + 4)
  const list = []
  for (let index = start; index <= end; index += 1) list.push(index)
  return list
}
</script>

<template>
  <div v-if="total > pageSize" class="pager">
    <button
      type="button"
      class="btn btn--sm"
      :disabled="page <= 1"
      @click="emit('change', page - 1)"
    >
      上一页
    </button>
    <button
      v-for="index in pages()"
      :key="index"
      type="button"
      class="btn btn--sm"
      :class="{ 'btn--primary': index === page }"
      @click="emit('change', index)"
    >
      {{ index }}
    </button>
    <button
      type="button"
      class="btn btn--sm"
      :disabled="!hasNext"
      @click="emit('change', page + 1)"
    >
      下一页
    </button>
  </div>
</template>
