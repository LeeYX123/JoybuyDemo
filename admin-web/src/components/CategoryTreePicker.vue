<script setup>
import { computed, ref } from 'vue'

// Joybuy source category tree picker (2 levels: channel → listing facet).
// Selecting a node adds { source_id, name, name_zh, include_descendants } to
// the job's frozen selection; the toggle flips include_descendants per node.
// 中文名来自 Joybuy 站点切到中文后的类目菜单，按 source_id 与英文名一一对应；
// 有中文名时同时展示「中文名 / English name」，没有时只显示英文名。
const props = defineProps({
  categories: {
    type: Array,
    default: () => [], // [{ source_id, name, name_zh, children: [{ source_id, name, name_zh }] }]
  },
  modelValue: {
    type: Array,
    default: () => [], // [{ source_id, name, name_zh, include_descendants }]
  },
})
const emit = defineEmits(['update:modelValue'])

const search = ref('')
const expanded = ref(new Set())

const filteredTree = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return props.categories
  const hit = (node) =>
    (node.name || '').toLowerCase().includes(keyword) ||
    (node.name_zh || '').toLowerCase().includes(keyword) ||
    String(node.source_id).toLowerCase().includes(keyword)
  return props.categories
    .map((node) => {
      if (hit(node)) return node
      const children = (node.children || []).filter(hit)
      if (children.length === 0) return null
      return { ...node, children }
    })
    .filter(Boolean)
})

function isSelected(sourceId) {
  return props.modelValue.some((item) => item.source_id === sourceId)
}

function selectionFor(sourceId) {
  return props.modelValue.find((item) => item.source_id === sourceId)
}

function toggleNode(node) {
  if (isSelected(node.source_id)) {
    emit(
      'update:modelValue',
      props.modelValue.filter((item) => item.source_id !== node.source_id),
    )
    return
  }
  emit('update:modelValue', [
    ...props.modelValue,
    {
      source_id: node.source_id,
      name: node.name,
      name_zh: node.name_zh || '',
      include_descendants: true,
    },
  ])
}

function toggleDescendants(sourceId) {
  emit(
    'update:modelValue',
    props.modelValue.map((item) =>
      item.source_id === sourceId
        ? { ...item, include_descendants: !item.include_descendants }
        : item,
    ),
  )
}

function toggleExpand(sourceId) {
  const next = new Set(expanded.value)
  if (next.has(sourceId)) next.delete(sourceId)
  else next.add(sourceId)
  expanded.value = next
}

function isExpanded(sourceId) {
  return expanded.value.has(sourceId)
}

const selectedCount = computed(() => props.modelValue.length)
</script>

<template>
  <div class="tree-picker">
    <input
      v-model="search"
      class="tree-picker__search"
      type="search"
      placeholder="搜索中文名 / 英文名 / 来源 ID…"
    />
    <p class="tree-picker__hint">已选 {{ selectedCount }} 个类目</p>
    <ul class="tree-picker__list">
      <li v-for="node in filteredTree" :key="node.source_id" class="tree-picker__node">
        <div
          class="tree-picker__row"
          :class="{ 'tree-picker__row--selected': isSelected(node.source_id) }"
        >
          <label class="tree-picker__label">
            <input
              type="checkbox"
              :checked="isSelected(node.source_id)"
              @change="toggleNode(node)"
            />
            <span class="tree-picker__names">
              <span class="tree-picker__name-zh">{{ node.name_zh || node.name }}</span>
              <span v-if="node.name_zh" class="tree-picker__name-en">{{ node.name }}</span>
            </span>
            <code class="tree-picker__id">{{ node.source_id }}</code>
          </label>
          <button
            v-if="(node.children || []).length"
            type="button"
            class="tree-picker__expand"
            @click="toggleExpand(node.source_id)"
          >
            {{ isExpanded(node.source_id) ? '收起' : `展开(${node.children.length})` }}
          </button>
        </div>
        <ul v-if="isExpanded(node.source_id) || search" class="tree-picker__children">
          <li
            v-for="child in node.children"
            :key="child.source_id"
            class="tree-picker__row tree-picker__row--child"
            :class="{ 'tree-picker__row--selected': isSelected(child.source_id) }"
          >
            <label class="tree-picker__label">
              <input
                type="checkbox"
                :checked="isSelected(child.source_id)"
                @change="toggleNode(child)"
              />
              <span class="tree-picker__names">
                <span class="tree-picker__name-zh">{{ child.name_zh || child.name }}</span>
                <span v-if="child.name_zh" class="tree-picker__name-en">{{ child.name }}</span>
              </span>
              <code class="tree-picker__id">{{ child.source_id }}</code>
            </label>
            <button
              v-if="isSelected(child.source_id)"
              type="button"
              class="tree-picker__desc"
              @click="toggleDescendants(child.source_id)"
            >
              {{ selectionFor(child.source_id)?.include_descendants ? '含子类目 ✓' : '仅当前类目' }}
            </button>
          </li>
        </ul>
      </li>
      <li v-if="filteredTree.length === 0" class="tree-picker__empty">
        {{ search ? '没有匹配的类目。' : '类目树尚未同步：请先运行 sync_joybuy_category_tree。' }}
      </li>
    </ul>
  </div>
</template>

<style scoped>
.tree-picker {
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  padding: var(--space-3);
}

.tree-picker__search {
  width: 100%;
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
  margin-bottom: var(--space-2);
}

.tree-picker__hint {
  font-size: var(--font-size-sm);
  color: var(--colour-text-soft, #666);
  margin-bottom: var(--space-2);
}

.tree-picker__list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 20rem;
  overflow-y: auto;
}

.tree-picker__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm, 6px);
}

.tree-picker__row--selected {
  background: var(--colour-surface-active, #f0f4ff);
}

.tree-picker__row--child {
  margin-left: var(--space-5);
}

.tree-picker__label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.tree-picker__names {
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.tree-picker__name-zh {
  font-weight: 500;
}

.tree-picker__name-en {
  color: var(--colour-text-soft, #666);
  font-size: var(--font-size-xs, 0.75rem);
}

.tree-picker__id {
  font-size: var(--font-size-xs, 0.75rem);
  color: var(--colour-text-soft, #888);
}

.tree-picker__expand,
.tree-picker__desc {
  min-height: 32px;
  padding: 0 var(--space-2);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
  font-size: var(--font-size-sm);
  white-space: nowrap;
}

.tree-picker__children {
  list-style: none;
  margin: 0;
  padding: 0;
}

.tree-picker__empty {
  padding: var(--space-3);
  color: var(--colour-text-soft, #666);
  font-size: var(--font-size-sm);
}
</style>
