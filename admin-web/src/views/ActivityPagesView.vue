<script setup>
// 活动页 / 店铺页配置（2026-11-25，首页「为你推荐」10 模块配套）。
//
// 两类页面共用一套模型（kind=ACTIVITY|STORE），列表 + 详情编辑：
//   - 基础信息：真站 ID（决定本地 URL /active/<id> 或 /store/<id>）、标题、
//     店铺名（店铺页）、hero 大图、底色、启用开关；
//   - 分区：整幅图片模块（BANNER）与商品楼层（PRODUCTS，标题 + 选品 + 列数 +
//     查看更多）。真站活动页/店铺页的结构就是「hero + 若干分区」，后台按同构配置。
//   - 选品走商品池搜索（/products?q=），按真站顺序保存。
import { computed, onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: 'ACTIVE', label: '活动页（/active/<id>）' },
  { key: 'STORE', label: '店铺页（/store/<id>）' },
]

const state = reactive({
  kind: 'ACTIVE',
  items: [],
  loading: true,
  error: '',
  notice: '',
})

const pageEditorOpen = ref(false)
const pageBusy = ref(false)
const pageError = ref('')
const pageId = ref('')
const pageForm = reactive({
  external_id: '',
  title: '',
  title_zh: '',
  store_name: '',
  hero_image: '',
  background_color: '',
  enabled: true,
})

const detailOpen = ref(false)
const detail = ref(null)
const detailBusy = ref(false)

const sectionOpen = ref(false)
const sectionBusy = ref(false)
const sectionError = ref('')
const sectionId = ref('')
const sectionForm = reactive({
  kind: 'PRODUCTS',
  title: '',
  title_zh: '',
  title_color: '',
  title_background: '',
  image_url: '',
  href: '',
  columns: 5,
  show_more: false,
})

const pickerOpen = ref(false)
const pickerQuery = ref('')
const pickerRows = ref([])
const pickerLoading = ref(false)
const pickerSelected = ref([])

const kindLabel = computed(() =>
  state.kind === 'STORE' ? '店铺页' : '活动页',
)

async function load() {
  state.loading = true
  state.error = ''
  try {
    const payload = await apiRequest(`/activity-pages?kind=${state.kind}`)
    state.items = payload.items || []
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectKind(key) {
  state.kind = key
  state.notice = ''
  load()
}

function resetPageForm() {
  pageForm.external_id = ''
  pageForm.title = ''
  pageForm.title_zh = ''
  pageForm.store_name = ''
  pageForm.hero_image = ''
  pageForm.background_color = ''
  pageForm.enabled = true
}

function openCreatePage() {
  pageId.value = ''
  resetPageForm()
  pageError.value = ''
  pageEditorOpen.value = true
}

function openEditPage(row) {
  pageId.value = row.public_id
  pageForm.external_id = row.external_id
  pageForm.title = row.title
  pageForm.title_zh = row.title_zh || ''
  pageForm.store_name = row.store_name || ''
  pageForm.hero_image = row.hero_image || ''
  pageForm.background_color = row.background_color || ''
  pageForm.enabled = Boolean(row.enabled)
  pageError.value = ''
  pageEditorOpen.value = true
}

async function savePage() {
  pageBusy.value = true
  pageError.value = ''
  const body = {
    title: pageForm.title,
    title_zh: pageForm.title_zh,
    store_name: pageForm.store_name,
    hero_image: pageForm.hero_image,
    background_color: pageForm.background_color,
    enabled: pageForm.enabled,
  }
  try {
    if (pageId.value) {
      await adminWrite(`/activity-pages/${pageId.value}`, body, 'PATCH')
      state.notice = '页面已更新。'
    } else {
      await adminWrite('/activity-pages', {
        ...body,
        kind: state.kind,
        external_id: pageForm.external_id,
      })
      state.notice = '页面已创建。'
    }
    pageEditorOpen.value = false
    await load()
  } catch (error) {
    pageError.value = error.message
  } finally {
    pageBusy.value = false
  }
}

async function openDetail(row) {
  detailBusy.value = true
  detailOpen.value = true
  detail.value = null
  try {
    const payload = await apiRequest(`/activity-pages/${row.public_id}`)
    detail.value = payload.page
  } catch (error) {
    state.error = error.message
    detailOpen.value = false
  } finally {
    detailBusy.value = false
  }
}

async function refreshDetail() {
  if (!detail.value) return
  const payload = await apiRequest(`/activity-pages/${detail.value.public_id}`)
  detail.value = payload.page
  await load()
}

function openCreateSection(kind) {
  sectionId.value = ''
  sectionForm.kind = kind
  sectionForm.title = ''
  sectionForm.title_zh = ''
  sectionForm.title_color = ''
  sectionForm.title_background = ''
  sectionForm.image_url = ''
  sectionForm.href = ''
  sectionForm.columns = 5
  sectionForm.show_more = false
  sectionError.value = ''
  sectionOpen.value = true
}

function openEditSection(section) {
  sectionId.value = section.public_id
  sectionForm.kind = section.kind
  sectionForm.title = section.title || ''
  sectionForm.title_zh = section.title_zh || ''
  sectionForm.title_color = section.title_color || ''
  sectionForm.title_background = section.title_background || ''
  sectionForm.image_url = section.image_url || ''
  sectionForm.href = section.href || ''
  sectionForm.columns = section.columns || 5
  sectionForm.show_more = Boolean(section.show_more)
  sectionError.value = ''
  sectionOpen.value = true
}

async function saveSection() {
  sectionBusy.value = true
  sectionError.value = ''
  const body = {
    kind: sectionForm.kind,
    title: sectionForm.title,
    title_zh: sectionForm.title_zh,
    title_color: sectionForm.title_color,
    title_background: sectionForm.title_background,
    image_url: sectionForm.image_url,
    href: sectionForm.href,
    columns: sectionForm.columns,
    show_more: sectionForm.show_more,
  }
  try {
    if (sectionId.value) {
      await adminWrite(
        `/activity-pages/${detail.value.public_id}/sections/${sectionId.value}`,
        body,
        'PATCH',
      )
    } else {
      await adminWrite(`/activity-pages/${detail.value.public_id}/sections`, body)
    }
    sectionOpen.value = false
    await refreshDetail()
  } catch (error) {
    sectionError.value = error.message
  } finally {
    sectionBusy.value = false
  }
}

async function removeSection(section) {
  if (!window.confirm(`删除分区「${section.title || section.kind}」？`)) return
  await adminWrite(
    `/activity-pages/${detail.value.public_id}/sections/${section.public_id}`,
    {},
    'DELETE',
  )
  await refreshDetail()
}

async function openPicker(section) {
  pickerSelected.value = (section.products || []).map((item) => item.spu_public_id)
  pickerQuery.value = ''
  pickerRows.value = []
  pickerOpen.value = true
  await searchProducts()
}

async function searchProducts() {
  pickerLoading.value = true
  try {
    const query = new URLSearchParams({ page: '1' })
    if (pickerQuery.value.trim()) query.set('q', pickerQuery.value.trim())
    const payload = await apiRequest(`/products?${query.toString()}`)
    pickerRows.value = payload.items || []
  } catch (error) {
    state.error = error.message
  } finally {
    pickerLoading.value = false
  }
}

function togglePick(row) {
  const index = pickerSelected.value.indexOf(row.id)
  if (index >= 0) pickerSelected.value.splice(index, 1)
  else pickerSelected.value.push(row.id)
}

async function savePicks() {
  const section = detail.value.sections.find((item) => item.public_id === pickerSectionId.value)
  if (!section) return
  await adminWrite(
    `/activity-pages/${detail.value.public_id}/sections/${section.public_id}/products`,
    { products: pickerSelected.value },
    'PUT',
  )
  pickerOpen.value = false
  await refreshDetail()
}

const pickerSectionId = ref('')

function openPickerFor(section) {
  pickerSectionId.value = section.public_id
  openPicker(section)
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page__head">
      <div>
        <h1 class="page__title">活动页 / 店铺页</h1>
        <p class="page__hint">
          真站活动页与店铺页的本地复刻配置：hero 大图 + 若干分区（图片模块 /
          商品楼层）。新建后把链接挂到首页推荐卡（活动卡片）即可。
        </p>
      </div>
      <button type="button" class="btn btn--primary" @click="openCreatePage">
        新增{{ kindLabel }}
      </button>
    </div>

    <div class="tabs">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        :class="{ 'is-active': state.kind === tab.key }"
        @click="selectKind(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>

    <div class="card">
      <div class="card__body">
        <p v-if="state.loading" class="inline-loading">加载中…</p>
        <table v-else-if="state.items.length" class="data-table">
          <thead>
            <tr>
              <th style="width: 160px">Hero</th>
              <th>标题 / 真站 ID</th>
              <th style="width: 90px">分区</th>
              <th style="width: 90px">商品</th>
              <th style="width: 90px">状态</th>
              <th class="actions-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.public_id" :class="{ 'row--off': !row.enabled }">
              <td>
                <img v-if="row.hero_image" :src="row.hero_image" alt="" class="campaign-thumb" />
                <span v-else class="campaign-thumb campaign-thumb--empty">无图</span>
              </td>
              <td>
                <div class="cell-strong">{{ row.title }}</div>
                <div class="cell-sub mono">
                  {{ row.external_id }}
                  <template v-if="row.store_name">· {{ row.store_name }}</template>
                </div>
              </td>
              <td class="num">{{ row.section_count }}</td>
              <td class="num">{{ row.product_count }}</td>
              <td>
                <span class="tag" :class="row.enabled ? 'tag--ok' : 'tag--warn'">
                  {{ row.enabled ? '启用中' : '已停用' }}
                </span>
              </td>
              <td class="actions-col">
                <button type="button" class="btn btn--sm" @click="openDetail(row)">分区与选品</button>
                <button type="button" class="btn btn--sm" @click="openEditPage(row)">编辑</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">还没有{{ kindLabel }}。新建成后商城即可访问对应 URL。</p>
      </div>
    </div>

    <!-- 页面基础信息 -->
    <AppModal
      :open="pageEditorOpen"
      :title="pageId ? '编辑页面' : `新增${kindLabel}`"
      confirm-text="保存"
      :busy="pageBusy"
      @cancel="pageEditorOpen = false"
      @confirm="savePage"
    >
      <div class="form-grid">
        <label class="field">
          <span class="field__label">真站页面 ID（决定本地 URL，必填）</span>
          <input
            v-model="pageForm.external_id"
            type="text"
            :disabled="Boolean(pageId)"
            placeholder="活动页 7Uw83... / 店铺页 100000744"
          />
        </label>
        <label class="field">
          <span class="field__label">页面标题（英文）</span>
          <input v-model="pageForm.title" type="text" maxlength="200" />
        </label>
        <label class="field">
          <span class="field__label">页面标题（中文，选填）</span>
          <input v-model="pageForm.title_zh" type="text" maxlength="200" />
        </label>
        <label v-if="state.kind === 'STORE'" class="field">
          <span class="field__label">店铺名（店铺页顶栏）</span>
          <input v-model="pageForm.store_name" type="text" maxlength="160" />
        </label>
        <label class="field">
          <span class="field__label">底色（选填，如 #ffffff）</span>
          <input v-model="pageForm.background_color" type="text" maxlength="16" />
        </label>
        <div class="field">
          <span class="field__label">Hero 大图</span>
          <ImageUploader v-model="pageForm.hero_image" purpose="cms" label="Hero 图" />
        </div>
        <label class="field field--inline">
          <input v-model="pageForm.enabled" type="checkbox" />
          <span>启用（停用后商城访问 404）</span>
        </label>
      </div>
      <p v-if="pageError" class="notice notice--error">{{ pageError }}</p>
    </AppModal>

    <!-- 分区与选品 -->
    <AppModal
      :open="detailOpen"
      :title="detail ? `分区配置：${detail.title}` : '加载中…'"
      :confirm-text="'关闭'"
      :busy="detailBusy"
      @cancel="detailOpen = false"
      @confirm="detailOpen = false"
    >
      <div v-if="detail" class="sections">
        <div class="sections__bar">
          <button type="button" class="btn btn--sm" @click="openCreateSection('BANNER')">
            新增图片模块
          </button>
          <button type="button" class="btn btn--sm" @click="openCreateSection('PRODUCTS')">
            新增商品楼层
          </button>
        </div>
        <div v-if="!detail.sections.length" class="empty-state">还没有分区。</div>
        <div v-for="(section, index) in detail.sections" :key="section.public_id" class="section-row">
          <div class="section-row__head">
            <strong>{{ index + 1 }}. {{ section.kind === 'BANNER' ? '图片模块' : '商品楼层' }}</strong>
            <span v-if="section.title" class="cell-sub">{{ section.title }}</span>
            <span class="cell-sub">商品 {{ (section.products || []).length }}</span>
          </div>
          <img v-if="section.image_url" :src="section.image_url" alt="" class="section-row__img" />
          <div class="section-row__actions">
            <button type="button" class="btn btn--sm" @click="openEditSection(section)">编辑</button>
            <button
              v-if="section.kind === 'PRODUCTS'"
              type="button"
              class="btn btn--sm"
              @click="openPickerFor(section)"
            >
              选品
            </button>
            <button type="button" class="btn btn--sm btn--danger" @click="removeSection(section)">
              删除
            </button>
          </div>
        </div>
      </div>
    </AppModal>

    <!-- 分区编辑 -->
    <AppModal
      :open="sectionOpen"
      :title="sectionId ? '编辑分区' : '新增分区'"
      confirm-text="保存"
      :busy="sectionBusy"
      @cancel="sectionOpen = false"
      @confirm="saveSection"
    >
      <div class="form-grid">
        <label class="field">
          <span class="field__label">类型</span>
          <select v-model="sectionForm.kind" :disabled="Boolean(sectionId)">
            <option value="PRODUCTS">商品楼层</option>
            <option value="BANNER">整幅图片</option>
          </select>
        </label>
        <label v-if="sectionForm.kind === 'PRODUCTS'" class="field">
          <span class="field__label">模块标题（英文）</span>
          <input v-model="sectionForm.title" type="text" maxlength="200" />
        </label>
        <label v-if="sectionForm.kind === 'PRODUCTS'" class="field">
          <span class="field__label">模块标题（中文，选填）</span>
          <input v-model="sectionForm.title_zh" type="text" maxlength="200" />
        </label>
        <label v-if="sectionForm.kind === 'PRODUCTS'" class="field">
          <span class="field__label">标题字色（选填，默认 #a33838）</span>
          <input v-model="sectionForm.title_color" type="text" maxlength="32" placeholder="#ffffff" />
        </label>
        <label v-if="sectionForm.kind === 'PRODUCTS'" class="field">
          <span class="field__label">标题底色（选填，留空 = 纯文字标题）</span>
          <input
            v-model="sectionForm.title_background"
            type="text"
            maxlength="32"
            placeholder="#661414"
          />
        </label>
        <label v-if="sectionForm.kind === 'PRODUCTS'" class="field">
          <span class="field__label">列数</span>
          <select v-model.number="sectionForm.columns">
            <option :value="5">5 列（真站活动页）</option>
            <option :value="4">4 列</option>
          </select>
        </label>
        <label v-if="sectionForm.kind === 'PRODUCTS'" class="field field--inline">
          <input v-model="sectionForm.show_more" type="checkbox" />
          <span>显示【View more】（点击加载全部已采商品）</span>
        </label>
        <div class="field">
          <span class="field__label">
            {{ sectionForm.kind === 'BANNER' ? '图片（必填）' : '楼层头图（选填）' }}
          </span>
          <ImageUploader v-model="sectionForm.image_url" purpose="cms" label="分区图" />
        </div>
        <label v-if="sectionForm.kind === 'BANNER'" class="field">
          <span class="field__label">点击跳转（选填）</span>
          <input v-model="sectionForm.href" type="text" maxlength="1000" />
        </label>
      </div>
      <p v-if="sectionError" class="notice notice--error">{{ sectionError }}</p>
    </AppModal>

    <!-- 选品 -->
    <AppModal
      :open="pickerOpen"
      title="楼层选品（按勾选顺序保存）"
      confirm-text="保存选品"
      :busy="pickerLoading"
      @cancel="pickerOpen = false"
      @confirm="savePicks"
    >
      <div class="picker__bar">
        <input
          v-model="pickerQuery"
          type="text"
          placeholder="搜索商品标题 / 商品 ID"
          @keyup.enter="searchProducts"
        />
        <button type="button" class="btn btn--sm" @click="searchProducts">搜索</button>
        <span class="cell-sub">已选 {{ pickerSelected.length }} 个</span>
      </div>
      <p v-if="pickerLoading" class="inline-loading">加载中…</p>
      <div v-else class="picker__list">
        <label v-for="row in pickerRows" :key="row.id" class="picker__row">
          <input
            type="checkbox"
            :checked="pickerSelected.includes(row.id)"
            @change="togglePick(row)"
          />
          <img v-if="row.images && row.images.length" :src="row.images[0]" alt="" />
          <span class="picker__title">{{ row.name }}</span>
          <span class="cell-sub">{{ row.price || '—' }}</span>
        </label>
      </div>
    </AppModal>
  </div>
</template>

<style scoped>
.sections__bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.section-row {
  border: 1px solid var(--colour-border, #e5e7eb);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}

.section-row__head {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.section-row__img {
  display: block;
  max-width: 220px;
  max-height: 90px;
  margin-top: 8px;
  border-radius: 4px;
}

.section-row__actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}

.picker__bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.picker__list {
  max-height: 360px;
  overflow: auto;
}

.picker__row {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid #f1f2f4;
}

.picker__row img {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.picker__title {
  flex: 1;
  font-size: 13px;
}
</style>
