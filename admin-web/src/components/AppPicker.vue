<script setup>
// AppPicker（2026-11-28）：全站统一的「可搜索下拉框」。
//
// 所有需要输入 商家 / 用户 / 商品 / 报价 / 订单 等实体的地方都换成它：
// 输入防抖远程搜索（fetcher 由调用方注入），支持按 ID 和名称查询，
// 下拉项两行显示：名称 + ID 全号（UUID 36 位整号，不截断）。
//
// - 单选：v-model 绑定实体 ID（提交值不变，仍是 ID）。
// - 多选（multiple）：v-model 绑定 ID 数组，选项以 chips 呈现，顺序即选择顺序。
// - 定位：下拉通过 Teleport 渲染到 body、按触发器 getBoundingClientRect 定位，
//   滚动/窗口变化实时重算——在 AppModal（body 滚动区）/AppDrawer/普通页面里都不会被裁切。
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  // 单选：ID 字符串；multiple 时为 ID 数组。
  modelValue: { type: [String, Number, Array], default: '' },
  // (query, page) => Promise<{ items: Array, page?, total?, has_next? }>
  fetcher: { type: Function, required: true },
  optionLabel: {
    type: Function,
    default: (option) =>
      option?.name ?? option?.title ?? option?.account ?? String(option?.id ?? ''),
  },
  optionId: { type: Function, default: (option) => String(option?.id ?? '') },
  // 下拉项 ID 行的可选补充（如 余额 / 库存 / 商家），拼接在 ID 后。
  optionMeta: { type: Function, default: null },
  placeholder: { type: String, default: '输入名称或 ID 搜索' },
  disabled: { type: Boolean, default: false },
  clearable: { type: Boolean, default: true },
  multiple: { type: Boolean, default: false },
  // 预置选项：编辑场景回显 label / 多选 chips 种子（[{ id, name | title | account }]）。
  initialItems: { type: Array, default: null },
  pageSize: { type: Number, default: 20 },
  emptyText: { type: String, default: '没有匹配的选项' },
  inputId: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'change'])

const query = ref('')
const open = ref(false)
const options = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const page = ref(1)
const hasNext = ref(false)
const activeIndex = ref(-1)
const inputEl = ref(null)
const rootEl = ref(null)
const popEl = ref(null)

// 触发器/下拉位置（Teleport 到 body 后用 fixed 定位）。
const popStyle = ref({ display: 'none' })
const dropUp = ref(false)

// id -> label 缓存：来自预置选项与搜索命中的选项，用于回显与 chips。
const labelMap = ref(new Map())

let searchToken = 0
let debounceTimer = null
let popFrame = null

function rememberOptions(list) {
  const next = labelMap.value
  for (const option of list || []) next.set(props.optionId(option), props.optionLabel(option))
  // Map 原地更新后替换引用，保证 computed 感知。
  labelMap.value = new Map(next)
}

watch(
  () => props.initialItems,
  (items) => {
    if (items?.length) rememberOptions(items)
  },
  { immediate: true },
)

function labelOf(id) {
  return labelMap.value.get(String(id)) || String(id ?? '')
}

const singleSelected = computed(
  () => !props.multiple && props.modelValue !== '' && props.modelValue != null,
)

const chips = computed(() => {
  if (!props.multiple || !Array.isArray(props.modelValue)) return []
  return props.modelValue.map((id) => ({ id: String(id), label: labelOf(id) }))
})

const selectedIds = computed(() => {
  if (props.multiple) return new Set((props.modelValue || []).map(String))
  return new Set(
    props.modelValue != null && props.modelValue !== '' ? [String(props.modelValue)] : [],
  )
})

// 关闭状态回显选中项名称；打开状态显示输入中的关键字。
const displayText = computed(() => {
  if (open.value) return query.value
  if (props.multiple) return ''
  if (singleSelected.value) return labelOf(props.modelValue)
  return ''
})

function scheduleSearch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    search(1)
  }, 300)
}

async function search(targetPage) {
  const token = ++searchToken
  const term = query.value.trim()
  if (targetPage === 1) loading.value = true
  else loadingMore.value = true
  error.value = ''
  try {
    const payload = (await props.fetcher(term, targetPage)) || {}
    if (token !== searchToken) return // 已有过期响应（连续输入），丢弃
    const items = payload.items || []
    if (targetPage === 1) {
      options.value = items
      activeIndex.value = items.length ? 0 : -1
    } else {
      options.value = options.value.concat(items)
    }
    page.value = targetPage
    hasNext.value = Boolean(payload.has_next)
    rememberOptions(items)
  } catch {
    if (token !== searchToken) return
    if (targetPage === 1) options.value = []
    error.value = '搜索失败，请重试。'
    hasNext.value = false
  } finally {
    if (token === searchToken) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

async function openDropdown() {
  if (props.disabled || open.value) return
  open.value = true
  query.value = ''
  positionPop()
  await nextTick()
  inputEl.value?.focus()
  positionPop()
  // 每次打开都重新拉第一页：上一次的关键字结果不能残留。
  search(1)
}

function closeDropdown() {
  if (!open.value) return
  open.value = false
  activeIndex.value = -1
  query.value = ''
}

function toggleOpen(event) {
  // 点在输入框上交给 focus 处理（避免 focus 开、click 又关的抖动）。
  if (event?.target === inputEl.value) {
    if (!open.value) openDropdown()
    return
  }
  if (open.value) closeDropdown()
  else openDropdown()
}

function select(option) {
  const id = props.optionId(option)
  rememberOptions([option])
  if (props.multiple) {
    const current = Array.isArray(props.modelValue) ? props.modelValue.map(String) : []
    const next = current.includes(id) ? current.filter((item) => item !== id) : current.concat(id)
    emit('update:modelValue', next)
    emit('change', option)
    return
  }
  emit('update:modelValue', id)
  emit('change', option)
  closeDropdown()
}

function removeChip(id) {
  const current = Array.isArray(props.modelValue) ? props.modelValue.map(String) : []
  emit(
    'update:modelValue',
    current.filter((item) => item !== id),
  )
}

function clearValue() {
  emit('update:modelValue', props.multiple ? [] : '')
  emit('change', null)
  query.value = ''
  options.value = []
  hasNext.value = false
  inputEl.value?.focus()
}

function onInput(event) {
  // 输入框是受控的（:value=displayText），必须把 DOM 值同步回 query 再防抖搜索。
  query.value = event.target.value
  if (!open.value) open.value = true
  scheduleSearch()
}

function moveActive(delta) {
  if (!options.value.length) return
  const next = activeIndex.value + delta
  if (next < 0) {
    activeIndex.value = options.value.length - 1
  } else if (next >= options.value.length) {
    activeIndex.value = 0
  } else {
    activeIndex.value = next
  }
  nextTick(() => {
    popEl.value
      ?.querySelector(`[data-index="${activeIndex.value}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  })
}

function onKeydown(event) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (!open.value) openDropdown()
    else moveActive(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (open.value) moveActive(-1)
  } else if (event.key === 'Enter') {
    if (!open.value) return
    event.preventDefault()
    const option = options.value[activeIndex.value]
    if (option) select(option)
  } else if (event.key === 'Escape') {
    if (open.value) {
      event.preventDefault()
      closeDropdown()
    }
  }
}

// ---- Teleport 定位：打开、滚动（含弹窗内滚动容器）、窗口尺寸变化时重算。----
function positionPop() {
  if (!open.value) return
  const trigger = rootEl.value
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  if (!rect.width && !rect.height) return
  const viewport = window.innerHeight
  const spaceBelow = viewport - rect.bottom
  const spaceAbove = rect.top
  const flip = spaceBelow < 170 && spaceAbove > spaceBelow
  dropUp.value = flip
  const available = Math.max(flip ? spaceAbove - 10 : spaceBelow - 10, 120)
  const maxHeight = Math.min(300, available)
  popStyle.value = {
    display: 'block',
    position: 'fixed',
    left: `${Math.round(rect.left)}px`,
    width: `${Math.max(Math.round(rect.width), 320)}px`,
    maxHeight: `${maxHeight}px`,
    ...(flip
      ? { bottom: `${Math.round(viewport - rect.top + 6)}px` }
      : { top: `${Math.round(rect.bottom + 6)}px` }),
  }
}

function schedulePosition() {
  if (popFrame) return
  popFrame = requestAnimationFrame(() => {
    popFrame = null
    positionPop()
  })
}

function onDocMouseDown(event) {
  const target = event.target
  if (rootEl.value?.contains(target) || popEl.value?.contains(target)) return
  closeDropdown()
}

function onDocScroll(event) {
  // 弹窗/抽屉/页面任何滚动都会改变触发器视口位置：重算而不是关闭。
  if (popEl.value?.contains(event.target)) return
  schedulePosition()
}

watch(open, (value) => {
  if (value) {
    document.addEventListener('mousedown', onDocMouseDown, true)
    document.addEventListener('scroll', onDocScroll, true)
    window.addEventListener('resize', schedulePosition)
  } else {
    document.removeEventListener('mousedown', onDocMouseDown, true)
    document.removeEventListener('scroll', onDocScroll, true)
    window.removeEventListener('resize', schedulePosition)
    popStyle.value = { display: 'none' }
  }
})

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (popFrame) cancelAnimationFrame(popFrame)
  document.removeEventListener('mousedown', onDocMouseDown, true)
  document.removeEventListener('scroll', onDocScroll, true)
  window.removeEventListener('resize', schedulePosition)
})

defineExpose({ closeDropdown })
</script>

<template>
  <div ref="rootEl" class="app-picker" :class="{ 'app-picker--disabled': disabled }">
    <div
      class="app-picker__trigger"
      :class="{ 'is-open': open, 'is-multiple': multiple && chips.length }"
      role="combobox"
      :aria-expanded="open"
      @click="toggleOpen"
    >
      <template v-if="multiple && chips.length">
        <span v-for="chip in chips" :key="chip.id" class="app-picker__chip">
          <span class="app-picker__chip-label">{{ chip.label }}</span>
          <span class="app-picker__chip-id mono">{{ chip.id }}</span>
          <button
            type="button"
            class="app-picker__chip-remove"
            aria-label="移除已选项"
            @click.stop="removeChip(chip.id)"
          >
            ×
          </button>
        </span>
      </template>
      <input
        :id="inputId"
        ref="inputEl"
        class="app-picker__input"
        type="text"
        :value="displayText"
        :placeholder="chips.length ? '添加更多…' : placeholder"
        :disabled="disabled"
        :aria-label="placeholder"
        @input="onInput"
        @focus="openDropdown"
        @keydown="onKeydown"
      />
      <span
        v-if="clearable && !disabled && (singleSelected || chips.length)"
        class="app-picker__clear"
        role="button"
        aria-label="清空"
        @click.stop="clearValue"
        >×</span
      >
      <span class="app-picker__caret" aria-hidden="true">▾</span>
    </div>

    <Teleport to="body">
      <div v-if="open" ref="popEl" class="app-picker__pop" :style="popStyle">
        <p v-if="loading" class="app-picker__state">搜索中…</p>
        <p v-else-if="error" class="app-picker__state app-picker__state--error">{{ error }}</p>
        <template v-else-if="options.length">
          <button
            v-for="(option, index) in options"
            :key="optionId(option)"
            type="button"
            class="app-picker__option"
            :class="{
              'is-active': index === activeIndex,
              'is-selected': selectedIds.has(optionId(option)),
            }"
            :data-index="index"
            @mouseenter="activeIndex = index"
            @click="select(option)"
          >
            <span class="app-picker__option-body">
              <span class="app-picker__option-label">{{ optionLabel(option) }}</span>
              <span class="app-picker__option-id mono">
                {{ optionId(option)
                }}<template v-if="optionMeta"> · {{ optionMeta(option) }}</template>
              </span>
            </span>
            <span
              v-if="selectedIds.has(optionId(option))"
              class="app-picker__option-check"
              aria-hidden="true"
              >✓</span
            >
          </button>
          <button
            v-if="hasNext"
            type="button"
            class="app-picker__more"
            :disabled="loadingMore"
            @click="search(page + 1)"
          >
            {{ loadingMore ? '加载中…' : '加载更多' }}
          </button>
        </template>
        <p v-else class="app-picker__state">
          {{ query.trim() ? emptyText : '暂无数据，可输入关键字搜索' }}
        </p>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.app-picker {
  position: relative;
  min-width: 0;
}

.app-picker--disabled {
  opacity: 0.55;
}

/* 触发器对齐 .field input（高 35px）；工具条里由 admin.css 覆盖为 33px。 */
.app-picker__trigger {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  width: 100%;
  min-height: 35px;
  padding: 3px 26px 3px 10px;
  border: 1px solid #d7e0ec;
  border-radius: 3px;
  background: #ffffff;
  cursor: pointer;
}

.app-picker__trigger:hover {
  border-color: #b9cbe4;
}

.app-picker__trigger.is-open {
  border-color: #6d9ef3;
  box-shadow: 0 0 0 2px var(--primary-ring);
}

.app-picker__trigger.is-multiple {
  padding: 4px 30px 4px 6px;
}

.app-picker__input {
  flex: 1 1 auto;
  min-width: 60px;
  border: 0;
  background: transparent;
  padding: 4px 0;
  color: #33455e;
  font-size: 12px;
}

.app-picker__input:focus {
  outline: 0;
}

.app-picker__input::placeholder {
  color: #a0adbf;
}

.app-picker__clear {
  position: absolute;
  right: 24px;
  top: 50%;
  transform: translateY(-50%);
  color: #8493a9;
  font-size: 14px;
  line-height: 1;
  padding: 2px;
}

.app-picker__clear:hover {
  color: var(--red, #dc2638);
}

.app-picker__caret {
  position: absolute;
  right: 9px;
  top: 50%;
  transform: translateY(-50%);
  color: #8493a9;
  font-size: 10px;
  pointer-events: none;
}

/* 多选 chips：名称 + 全号 ID 两行，允许换行不截断。 */
.app-picker__chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 2px 6px;
  border: 1px solid #d7e0ec;
  border-radius: 3px;
  background: #f0f4f9;
}

.app-picker__chip-label {
  font-size: 12px;
  color: #33455e;
  white-space: normal;
  word-break: break-word;
}

.app-picker__chip-id {
  font-size: 10px;
  color: #8493a9;
  white-space: normal;
  word-break: break-all;
}

.app-picker__chip-remove {
  border: 0;
  background: none;
  color: #8493a9;
  font-size: 13px;
  line-height: 1;
  padding: 0 2px;
}

.app-picker__chip-remove:hover {
  color: var(--red, #dc2638);
}

/* 下拉面板：Teleport 到 body 的 fixed 定位，弹窗内也不会被裁切。 */
.app-picker__pop {
  z-index: 90;
  overflow-y: auto;
  padding: 4px;
  border: 1px solid #d7e0ec;
  border-radius: 4px;
  background: #ffffff;
  box-shadow: var(--shadow-pop, 0 10px 28px rgb(12 24 43 / 18%));
  overscroll-behavior: contain;
}

.app-picker__option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: 3px;
  background: transparent;
  text-align: left;
}

.app-picker__option.is-active {
  background: #eaf1fd;
}

.app-picker__option.is-selected {
  background: #e3f0ea;
}

.app-picker__option-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  flex: 1;
}

/* 名称 + ID 全号两行显示：都不截断。 */
.app-picker__option-label {
  font-size: 12px;
  color: #33455e;
  white-space: normal;
  word-break: break-word;
}

.app-picker__option-id {
  font-size: 10px;
  color: #8493a9;
  white-space: normal;
  word-break: break-all;
}

.app-picker__option-check {
  color: var(--green, #16856a);
  font-size: 12px;
  flex: none;
}

.app-picker__more {
  width: 100%;
  margin-top: 2px;
  padding: 6px;
  border: 0;
  border-top: 1px dashed #e4eaf2;
  background: none;
  color: var(--primary, #2563eb);
  font-size: 12px;
}

.app-picker__more:disabled {
  color: #8493a9;
}

.app-picker__state {
  margin: 0;
  padding: 10px 8px;
  font-size: 12px;
  color: #8493a9;
}

.app-picker__state--error {
  color: var(--red, #dc2638);
}
</style>
