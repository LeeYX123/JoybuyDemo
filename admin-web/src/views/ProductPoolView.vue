<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPicker from '@/components/AppPicker.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const STATUS_TABS = [
  { key: '', label: '全部商品' },
  { key: 'ACTIVE', label: '可售' },
  { key: 'INACTIVE', label: '已下架' },
  { key: 'DRAFT', label: '草稿' },
]

const state = reactive({
  status: '',
  q: '',
  category: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

// 商品池的 ACTIVE 表示「可售」，与店铺的「接单中」不是同一个语义。
// [文案, 色调]：可售=绿、已下架=灰、草稿=橙（StatusTag 支持数组形态）。
const PRODUCT_STATUS_LABELS = {
  ACTIVE: ['可售', 'ok'],
  INACTIVE: ['已下架', ''],
  DRAFT: ['草稿', 'warn'],
}

const categories = ref([])
// 筛选下拉只展示父类目（二级类目不展示）；后端按子树匹配，选父类目同样能查到子类目商品。
const parentCategories = computed(() =>
  categories.value
    .filter((item) => (item.depth ?? 0) === 0)
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
)

// 2026-11-28 可搜索下拉框：筛选改为选商品（名称/UUID 均可搜，服务端分页搜索）。
// 商品池 2 万+，禁止全量拉取。
function fetchProductFilterOptions(q, page) {
  const params = new URLSearchParams({ page: String(page) })
  if (q.trim()) params.set('q', q.trim())
  return apiRequest(`/products?${params.toString()}`)
}

const detail = ref(null)
const detailLoading = ref(false)

// 详情抽屉画廊：爬虫导入的媒体库画廊在前，手工图片兜底（编辑弹窗仍只用手工 images）。
const detailGallery = computed(() => {
  if (detail.value?.gallery?.length) return detail.value.gallery
  return detail.value?.images || []
})

// 爬到的商品类目（最多两级），如「厨具餐具 / 锅具」。
const productCategoryText = computed(() =>
  (detail.value?.product_category || []).map((item) => item.name).join(' / '),
)

const editorOpen = ref(false)
const editorBusy = ref(false)
const editorError = ref('')
const editorId = ref('')
const editor = reactive({
  name: '',
  category: '',
  merchant_category: '',
  price: '',
  description: '',
  activity: false,
  status: 'ACTIVE',
  images: [],
  specs: [],
  // 图文详情（content_sections）人工编辑：结构与后端契约一致
  // [{title, blocks: [{type: 'heading'|'paragraph', text}], images}]。
  sections: [],
  sectionsLoading: false,
})

// 商家端商品上架中心的 11 个固定品类（WP-42 文档 M03 §3）。
// 在编辑表单里它就是「父品类」：先选它，再选它下面的子品类。
const MERCHANT_CATEGORIES = [
  { value: 'HOME', label: '家居生活' },
  { value: 'ELECTRONICS', label: '电子产品' },
  { value: 'BEAUTY', label: '美妆个人护理' },
  { value: 'SMALL_APPLIANCE', label: '小家电' },
  { value: 'HEALTH', label: '健康与保健' },
  { value: 'COMPUTER', label: '计算机与配件' },
  { value: 'APPAREL', label: '服装与配饰' },
  { value: 'OUTDOOR', label: '户外运动' },
  { value: 'PET', label: '宠物用品' },
  { value: 'BABY', label: '婴幼儿用品' },
  { value: 'GAMES', label: '游戏及配件' },
]

// 「商家端品类（父）」→「子品类」联动：子品类只列所选父类目下的二级类目。
const selectedParentCategory = computed(
  () =>
    parentCategories.value.find((item) => item.merchant_category === editor.merchant_category) ||
    null,
)

const childCategoryOptions = computed(() => {
  const parent = selectedParentCategory.value
  const options = parent
    ? categories.value
        .filter((item) => item.depth === 1 && item.parent_id === parent.id)
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
    : []
  // 历史数据可能还挂在父类目本身或另一个父类目下，保留当前值避免静默清空。
  const current = categories.value.find((item) => item.id === editor.category)
  if (current && !options.some((item) => item.id === current.id)) {
    options.unshift({ ...current, legacy: true })
  }
  return options
})

function onMerchantCategoryChange() {
  const parent = selectedParentCategory.value
  const valid =
    parent &&
    categories.value.some(
      (item) => item.id === editor.category && item.depth === 1 && item.parent_id === parent.id,
    )
  if (!valid) editor.category = ''
}

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.status) params.set('status', state.status)
    if (state.category) params.set('category', state.category)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/products?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function loadCategories() {
  try {
    const payload = await apiRequest('/categories')
    categories.value = payload.items
  } catch {
    categories.value = []
  }
}

async function openDetail(row) {
  detail.value = null
  detailLoading.value = true
  try {
    const payload = await apiRequest(`/products/${row.id}`)
    detail.value = payload.product
  } catch (error) {
    state.error = error.message
  } finally {
    detailLoading.value = false
  }
}

async function openEditor(row = null) {
  editorId.value = row?.id || ''
  editor.name = row?.name || ''
  editor.category = row?.category?.id || ''
  editor.merchant_category = row?.merchant_category || ''
  editor.price = row?.price || ''
  editor.description = row?.description || ''
  editor.activity = Boolean(row?.activity)
  editor.status = row?.status || 'ACTIVE'
  editor.images = [...(row?.images || [])]
  editor.specs = (row?.specs || []).map((item) => ({ ...item }))
  if (editor.specs.length === 0) editor.specs.push({ name: '', value: '' })
  // 图文详情：列表接口不带完整区块，编辑时按商品 ID 再拉一次详情；
  // 新建商品从空白开始。
  editor.sections = []
  editor.sectionsLoading = false
  editorError.value = ''
  editorOpen.value = true
  if (row?.id) {
    editor.sectionsLoading = true
    try {
      const payload = await apiRequest(`/products/${row.id}`)
      editor.sections = normalizeSections(payload.product?.content_sections || [])
    } catch (error) {
      editorError.value = error.message
    } finally {
      editor.sectionsLoading = false
    }
  }
}

// 把爬虫/后端返回的 content_sections 规整成编辑器可绑定的结构。
function normalizeSections(sections) {
  return (Array.isArray(sections) ? sections : []).map((section) => ({
    title: section?.title || '',
    blocks: (Array.isArray(section?.blocks) ? section.blocks : [])
      .filter((block) => block && typeof block.text === 'string')
      .map((block) => ({
        type: block.type === 'heading' ? 'heading' : 'paragraph',
        text: block.text,
      })),
    images: Array.isArray(section?.images) ? [...section.images] : [],
  }))
}

function addSection() {
  editor.sections.push({ title: '', blocks: [], images: [] })
}

function removeSection(index) {
  editor.sections.splice(index, 1)
}

function addBlock(sectionIndex, type) {
  editor.sections[sectionIndex]?.blocks.push({ type, text: '' })
}

function removeBlock(sectionIndex, blockIndex) {
  editor.sections[sectionIndex]?.blocks.splice(blockIndex, 1)
}

function moveBlock(sectionIndex, blockIndex, delta) {
  const blocks = editor.sections[sectionIndex]?.blocks
  if (!blocks) return
  const target = blockIndex + delta
  if (target < 0 || target >= blocks.length) return
  const [item] = blocks.splice(blockIndex, 1)
  blocks.splice(target, 0, item)
}

// 提交前清洗：去掉空文本块与完全空白的区块（后端会做同样的校验）。
function buildContentSections() {
  return editor.sections
    .map((section) => ({
      title: (section.title || '').trim(),
      blocks: section.blocks
        .filter((block) => block.text.trim())
        .map((block) => ({ type: block.type, text: block.text.trim() })),
      images: (section.images || []).filter(Boolean),
    }))
    .filter((section) => section.title || section.blocks.length || section.images.length)
}

function addSpec() {
  editor.specs.push({ name: '', value: '' })
}

function removeSpec(index) {
  editor.specs.splice(index, 1)
}

async function saveProduct() {
  editorBusy.value = true
  editorError.value = ''
  // 成本价不再由弹窗维护（爬虫商品没有成本价，商家上架按折扣折算），
  // PATCH 不带 cost 键即保持原值不动。
  const payload = {
    name: editor.name,
    category: editor.category || null,
    merchant_category: editor.merchant_category,
    price: editor.price,
    description: editor.description,
    activity: editor.activity,
    status: editor.status,
    images: editor.images.filter(Boolean).slice(0, 5),
    specs: editor.specs.filter((item) => item.name.trim() && item.value.trim()),
  }
  const sections = buildContentSections()
  // 只有确实编辑了区块才发 content_sections：空列表不发送，
  // 避免「误清空」后被导入器永久忽略人工内容（manual 不会被爬虫覆盖）。
  if (editorId.value && sections.length) {
    payload.content_sections = sections
  }
  try {
    let productId = editorId.value
    if (productId) {
      await adminWrite(`/products/${productId}`, payload, 'PATCH')
    } else {
      const created = await adminWrite('/products', payload)
      productId = created.product?.id || ''
    }
    // 图文详情走同一个 PATCH 契约；新建商品要先拿到 ID 再补写图文详情。
    if (productId && !editorId.value && sections.length) {
      await adminWrite(`/products/${productId}`, { content_sections: sections }, 'PATCH')
    }
    editorOpen.value = false
    await load()
    if (productId && detail.value?.id === productId) {
      await openDetail({ id: productId })
    }
  } catch (error) {
    editorError.value = error.message
  } finally {
    editorBusy.value = false
  }
}

async function toggleStatus(row) {
  const action = row.status === 'ACTIVE' ? 'unpublish' : 'publish'
  try {
    await adminWrite(`/products/${row.id}/actions`, { action })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

function categoryLabel(category) {
  if (!category) return '未分类'
  return category.name_zh || category.name_en || category.name
}

function selectStatus(key) {
  state.status = key
  load(true)
}

function resetFilters() {
  state.q = ''
  state.category = ''
  state.status = ''
  load(true)
}

function goPage(page) {
  state.page = page
  load()
}

function closeDetail() {
  detail.value = null
  detailLoading.value = false
}

onMounted(() => {
  loadCategories()
  load()
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>商品池管理</h1>
        <p>
          维护平台商品的品类、图片、规格、价格与可售性。商品池复用主档
          SPU，商家上架时在此取成本价快照。
        </p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="openEditor()">新增商品</button>
      </div>
    </div>

    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in STATUS_TABS"
          :key="tab.key"
          type="button"
          :class="{ 'is-active': state.status === tab.key }"
          @click="selectStatus(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="toolbar">
        <AppPicker
          v-model="state.q"
          :fetcher="fetchProductFilterOptions"
          placeholder="选择商品（名称 / 商品编号搜索）"
          :option-meta="(option) => (option.price ? `¥ ${option.price}` : '')"
          @change="load(true)"
        />
        <select v-model="state.category" @change="load(true)">
          <option value="">全部品类</option>
          <option v-for="item in parentCategories" :key="item.id" :value="item.id">
            {{ item.name_zh || item.name_en || item.name }}
          </option>
        </select>
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 16px 20px">
        {{ state.error }}
      </p>

      <div class="data-table-wrap">
        <table class="data-table pool-table">
          <thead>
            <tr>
              <th>商品</th>
              <th>品类</th>
              <th>成本价</th>
              <th>零售价</th>
              <th>商家数</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td class="pool-cell-product">
                <div class="pool-product">
                  <img v-if="row.images?.length" :src="row.images[0]" alt="" class="thumb" />
                  <div class="pool-product__text">
                    <span class="cell-strong" :title="row.name">{{ row.name }}</span>
                    <!-- 2026-11-27 全站编号改造：商品编号（UUID，商品回退 UUID 后）整号展示。 -->
                    <span class="cell-sub"
                      >{{ row.id }}<template v-if="row.activity"> · 活动商品</template></span
                    >
                    <span v-if="row.has_detail" class="pool-badges">
                      <span class="badge-mini">图文 {{ row.section_count }}</span>
                      <span v-if="row.spec_table_count" class="badge-mini"
                        >表格 {{ row.spec_table_count }}</span
                      >
                      <span v-if="row.video_count" class="badge-mini"
                        >视频 {{ row.video_count }}</span
                      >
                    </span>
                  </div>
                </div>
              </td>
              <td>{{ categoryLabel(row.category) }}</td>
              <td class="num">{{ row.cost ? `¥ ${row.cost}` : '—' }}</td>
              <td class="num">{{ row.price ? `¥ ${row.price}` : '—' }}</td>
              <td class="num">{{ row.stores }}</td>
              <td><StatusTag :value="row.status" :labels="PRODUCT_STATUS_LABELS" /></td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                  <button type="button" class="btn btn--sm" @click="openEditor(row)">编辑</button>
                  <button type="button" class="btn btn--sm" @click="toggleStatus(row)">
                    {{ row.status === 'ACTIVE' ? '下架' : '恢复' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="7" class="data-table__empty">没有匹配的商品。</td>
            </tr>
            <tr v-if="state.loading">
              <td colspan="7" class="data-table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <AppPager
        :page="state.meta.page || 1"
        :page-size="state.meta.page_size || 20"
        :total="state.meta.total || 0"
        :has-next="state.meta.has_next"
        @change="goPage"
      />
    </div>

    <AppDrawer
      v-if="detail || detailLoading"
      :title="detail ? detail.name : '商品详情'"
      wide
      @close="closeDetail"
    >
      <p v-if="detailLoading" class="inline-loading">加载中…</p>
      <template v-if="detail">
        <div v-if="detailGallery.length" class="thumb-row">
          <img v-for="url in detailGallery" :key="url" :src="url" alt="" class="thumb thumb--lg" />
        </div>
        <dl class="detail-grid" style="margin-top: 16px">
          <div>
            <dt>商品 ID</dt>
            <dd>{{ detail.id }}</dd>
          </div>
          <div>
            <dt>品类</dt>
            <dd>{{ categoryLabel(detail.category) }}</dd>
          </div>
          <div v-if="productCategoryText">
            <dt>商品类目（爬取）</dt>
            <dd>{{ productCategoryText }}</dd>
          </div>
          <div>
            <dt>成本价</dt>
            <dd>{{ detail.cost ? `¥ ${detail.cost}` : '—' }}</dd>
          </div>
          <div>
            <dt>零售价</dt>
            <dd>{{ detail.price ? `¥ ${detail.price}` : '—' }}</dd>
          </div>
          <div>
            <dt>商家数</dt>
            <dd>{{ detail.stores }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd><StatusTag :value="detail.status" :labels="PRODUCT_STATUS_LABELS" /></dd>
          </div>
          <div>
            <dt>活动商品</dt>
            <dd>{{ detail.activity ? '是' : '否' }}</dd>
          </div>
          <div>
            <dt>SKU 数</dt>
            <dd>{{ detail.sku_count ?? detail.skus?.length ?? 0 }}</dd>
          </div>
        </dl>

        <h3 class="section-title">
          图文详情
          <span v-if="detail.content_source === 'manual'" class="badge-mini pool-content__manual">
            人工编辑 · 爬虫不覆盖
          </span>
        </h3>
        <div v-if="detail.content_sections?.length" class="pool-content">
          <section
            v-for="(section, si) in detail.content_sections"
            :key="si"
            class="pool-content__section"
          >
            <h4 v-if="section.title">{{ section.title }}</h4>
            <template v-for="(block, bi) in section.blocks" :key="bi">
              <div v-if="block.type === 'heading' && block.text" class="pool-content__heading">
                {{ block.text }}
              </div>
              <p v-else-if="block.text" class="pool-content__paragraph">{{ block.text }}</p>
            </template>
            <div v-if="section.images?.length" class="thumb-row">
              <img
                v-for="url in section.images"
                :key="url"
                :src="url"
                alt=""
                class="thumb thumb--lg"
              />
            </div>
          </section>
        </div>
        <p v-else style="white-space: pre-wrap">{{ detail.description || '暂无描述。' }}</p>

        <div v-if="detail.ai_summary" class="pool-ai-card">
          <div class="pool-ai-card__title">
            {{ detail.ai_summary_title || '内容由人工智能总结自用户评价' }}
          </div>
          <p>{{ detail.ai_summary }}</p>
          <div v-if="detail.ai_summary_tags?.length" class="pool-ai-card__tags">
            <span v-for="tag in detail.ai_summary_tags" :key="tag">{{ tag }}</span>
          </div>
        </div>

        <template v-if="detail.videos?.length">
          <h3 class="section-title">商品视频</h3>
          <div class="pool-video-list">
            <video
              v-for="(video, vi) in detail.videos"
              :key="vi"
              class="pool-video"
              controls
              :poster="video.poster || undefined"
              :src="video.url"
            ></video>
          </div>
        </template>

        <template v-if="detail.specification_tables?.length">
          <h3 class="section-title">规格参数</h3>
          <div v-for="(table, ti) in detail.specification_tables" :key="ti" class="pool-spec-table">
            <h4 v-if="table.title">{{ table.title }}</h4>
            <table class="data-table">
              <thead>
                <tr>
                  <th class="pool-spec-table__name">属性</th>
                  <th>值</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in table.rows" :key="row.name">
                  <th scope="row">{{ row.name }}</th>
                  <td>{{ row.value }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>

        <template v-if="detail.spec_options?.length">
          <h3 class="section-title">规格选项</h3>
          <div class="pool-spec-options">
            <div
              v-for="option in detail.spec_options"
              :key="option.name"
              class="pool-spec-options__row"
            >
              <span class="pool-spec-options__name">{{ option.name }}</span>
              <span v-for="value in option.values" :key="value.value" class="pool-spec-chip">
                <img v-if="value.image_url" :src="value.image_url" alt="" />
                {{ value.value }}
              </span>
            </div>
          </div>
        </template>

        <h3 class="section-title">规格</h3>
        <table v-if="detail.specs?.length" class="data-table">
          <thead>
            <tr>
              <th>规格名称</th>
              <th>规格值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="spec in detail.specs" :key="spec.name">
              <td>{{ spec.name }}</td>
              <td>{{ spec.value }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">暂无规格。</p>
      </template>
    </AppDrawer>

    <AppModal
      v-if="editorOpen"
      :title="editorId ? '编辑商品' : '新增商品'"
      :busy="editorBusy"
      confirm-text="保存"
      @cancel="editorOpen = false"
      @confirm="saveProduct"
    >
      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>
      <div class="form-grid editor-grid">
        <div class="field field--full">
          <label for="product-name">商品名称</label>
          <input id="product-name" v-model="editor.name" type="text" maxlength="80" />
        </div>
        <div class="field">
          <label for="product-merchant-category">商家端品类（父品类）</label>
          <select
            id="product-merchant-category"
            v-model="editor.merchant_category"
            @change="onMerchantCategoryChange"
          >
            <option value="">未分类</option>
            <option v-for="item in MERCHANT_CATEGORIES" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </div>
        <div class="field">
          <label for="product-category">子品类</label>
          <select
            id="product-category"
            v-model="editor.category"
            :disabled="!selectedParentCategory"
          >
            <option value="">
              {{ selectedParentCategory ? '未分类' : '请先选择商家端品类' }}
            </option>
            <option v-for="item in childCategoryOptions" :key="item.id" :value="item.id">
              {{ item.name_zh || item.name_en || item.name }}{{ item.legacy ? '（当前值）' : '' }}
            </option>
          </select>
        </div>
        <div class="field">
          <label for="product-price">零售价（元）</label>
          <input id="product-price" v-model="editor.price" type="number" min="0.01" step="0.01" />
        </div>
        <div class="field">
          <label for="product-status">状态</label>
          <select id="product-status" v-model="editor.status">
            <option value="ACTIVE">可售</option>
            <option value="INACTIVE">已下架</option>
            <option value="DRAFT">草稿</option>
          </select>
        </div>
        <div class="field">
          <label class="checkline">
            <input v-model="editor.activity" type="checkbox" /> 活动商品
          </label>
        </div>
      </div>

      <ImageUploader
        v-model="editor.images"
        purpose="product"
        multiple
        :max="5"
        :max-size-mb="10"
        label="商品图片"
        hint="最多 5 张，首张为主图。上传后存到服务器本地，URL 由后端返回。"
      />

      <div class="field" style="margin-top: 12px">
        <label for="product-desc">商品描述</label>
        <textarea id="product-desc" v-model="editor.description" rows="3" />
      </div>

      <h3 class="section-title">图文详情</h3>
      <p class="field__hint" style="margin: 0 0 8px">
        按「区块 →
        子标题/段落/图片」维护商品页图文详情；保存后爬虫重导入不再覆盖图文内容（规格表格等仍会自动刷新）。
      </p>
      <p v-if="editor.sectionsLoading" class="empty-state">图文详情加载中…</p>
      <template v-else>
        <div v-for="(section, si) in editor.sections" :key="si" class="pool-editor-section">
          <div class="form-grid form-grid--tight pool-editor-section__head">
            <div class="field">
              <input
                v-model="section.title"
                type="text"
                placeholder="区块标题，如 商品详情"
                maxlength="120"
              />
            </div>
            <button type="button" class="btn btn--sm" @click="removeSection(si)">删除区块</button>
          </div>
          <div
            v-for="(block, bi) in section.blocks"
            :key="bi"
            class="pool-editor-block"
            :class="{ 'pool-editor-block--heading': block.type === 'heading' }"
          >
            <span class="pool-editor-block__label">
              {{ block.type === 'heading' ? '子标题' : '段落' }}
            </span>
            <input
              v-if="block.type === 'heading'"
              v-model="block.text"
              type="text"
              maxlength="1000"
              placeholder="子标题内容（加粗展示）"
            />
            <textarea
              v-else
              v-model="block.text"
              rows="3"
              maxlength="50000"
              placeholder="段落内容"
            ></textarea>
            <div class="pool-editor-block__tools">
              <button
                type="button"
                class="btn btn--sm"
                :disabled="bi === 0"
                @click="moveBlock(si, bi, -1)"
              >
                上移
              </button>
              <button
                type="button"
                class="btn btn--sm"
                :disabled="bi === section.blocks.length - 1"
                @click="moveBlock(si, bi, 1)"
              >
                下移
              </button>
              <button type="button" class="btn btn--sm" @click="removeBlock(si, bi)">删除</button>
            </div>
          </div>
          <div class="pool-editor-add">
            <button type="button" class="btn btn--sm" @click="addBlock(si, 'heading')">
              + 子标题
            </button>
            <button type="button" class="btn btn--sm" @click="addBlock(si, 'paragraph')">
              + 段落
            </button>
          </div>
          <ImageUploader
            v-model="section.images"
            purpose="product"
            multiple
            :reorderable="false"
            :max="20"
            :max-size-mb="10"
            label="区块图片"
            hint="本区块展示图片，最多 20 张，上传后存到服务器本地。"
          />
        </div>
        <button type="button" class="btn btn--sm" @click="addSection">+ 新增图文区块</button>
      </template>

      <h3 class="section-title">规格</h3>
      <div
        v-for="(spec, index) in editor.specs"
        :key="index"
        class="form-grid form-grid--tight"
        style="margin-bottom: 8px"
      >
        <div class="field">
          <input v-model="spec.name" type="text" placeholder="规格名称，如颜色" maxlength="30" />
        </div>
        <div class="field">
          <input v-model="spec.value" type="text" placeholder="规格值，如黑色" maxlength="200" />
        </div>
        <button type="button" class="btn btn--sm" @click="removeSpec(index)">移除</button>
      </div>
      <button type="button" class="btn btn--sm" @click="addSpec">新增规格</button>
    </AppModal>
  </section>
</template>

<style scoped>
/* 编辑弹窗固定两列：父品类与子品类必须并排相邻，才看得出层级关系。 */
.editor-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.editor-grid .field--full {
  grid-column: 1 / -1;
}

/* 商品列定宽 + 名称单行省略，避免长标题把右侧字段挤成两行。 */
.pool-table {
  table-layout: fixed;
}

.pool-table th,
.pool-table td {
  white-space: nowrap;
  vertical-align: middle;
}

/* 商品列吃掉剩余宽度（固定布局下由它吸收），其余列按内容定宽。 */
.pool-cell-product {
  width: auto;
}

.pool-table th:nth-child(1),
.pool-table td:nth-child(1) {
  width: 42%;
  white-space: normal;
}

.pool-table th:nth-child(2),
.pool-table td:nth-child(2) {
  width: 15%;
  overflow: visible;
  word-break: break-word;
}

.pool-table th:nth-child(3),
.pool-table td:nth-child(3),
.pool-table th:nth-child(4),
.pool-table td:nth-child(4) {
  width: 11%;
}

.pool-table th:nth-child(5),
.pool-table td:nth-child(5) {
  width: 8%;
}

.pool-table th:nth-child(6),
.pool-table td:nth-child(6) {
  width: 9%;
}

.pool-table th:nth-child(7),
.pool-table td:nth-child(7) {
  width: 190px;
}

.pool-product {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.pool-product__text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pool-product__text .cell-strong {
  overflow: visible;

  white-space: normal;
  word-break: break-word;
}

/* 操作列的按钮不换行、不撑宽。 */
.pool-table td:nth-child(7) .row-actions {
  flex-wrap: nowrap;
}
</style>
