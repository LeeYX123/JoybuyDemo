<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppPager from '@/components/AppPager.vue'
import AppPicker from '@/components/AppPicker.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

// 活动商品管理（WP-42，文档「二、管理端 → 平台运营管理 → 活动商品管理」）：
// 把商品打上/取消【活动商品】标记。该标记不改变商品原品类，
// 只影响商家端【商品上架中心】的活动商品分类与活动折扣取值。
//
// 列表列结构与【商品池管理】(ProductPoolView.vue) 对齐——同为 /products 列表接口
// （本页只是多带 activity=1 过滤），因此列 = 商品池所有列 −「商家数」列；
// 操作列只保留本页业务（详情 + 活动标记），不含商品池的「编辑」「下架」。

// 商品池的 ACTIVE 表示「可售」，与店铺的「接单中」不是同一个语义。
// [文案, 色调]：可售=绿、已下架=灰、草稿=橙（StatusTag 支持数组形态）。
const PRODUCT_STATUS_LABELS = {
  ACTIVE: ['可售', 'ok'],
  INACTIVE: ['已下架', ''],
  DRAFT: ['草稿', 'warn'],
}

const state = reactive({
  loading: true,
  error: '',
  notice: '',
  q: '',
  view: 'activity',
  items: [],
  meta: {},
  page: 1,
  busyId: '',
})

const columns = computed(() =>
  state.view === 'activity' ? '当前活动商品' : '全部商品（可打活动标记）',
)

const detail = ref(null)
const detailLoading = ref(false)

// 详情抽屉画廊：爬虫导入的媒体库画廊在前，手工图片兜底。
const detailGallery = computed(() => {
  if (detail.value?.gallery?.length) return detail.value.gallery
  return detail.value?.images || []
})

// 爬到的商品类目（最多两级），如「厨具餐具 / 锅具」。
const productCategoryText = computed(() =>
  (detail.value?.product_category || []).map((item) => item.name).join(' / '),
)

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({
      page: String(state.page),
      page_size: '10',
      activity: state.view === 'activity' ? '1' : '',
    })
    if (state.q.trim()) params.set('q', state.q.trim())
    if (state.view !== 'activity') params.delete('activity')
    const payload = await apiRequest(`/products?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function switchView(view) {
  state.view = view
  load(true)
}

function search() {
  load(true)
}

// 2026-11-28 可搜索下拉框：筛选改为选商品（名称/UUID 均可搜，服务端分页搜索）。
// 下拉候选跟随当前视图：活动页签只搜活动商品，全部页签搜全量。
function fetchActivityProductOptions(q, page) {
  const params = new URLSearchParams({ page: String(page) })
  if (state.view === 'activity') params.set('activity', '1')
  if (q.trim()) params.set('q', q.trim())
  return apiRequest(`/products?${params.toString()}`)
}

function goPage(page) {
  state.page = page
  load()
}

async function toggleActivity(row) {
  state.busyId = row.id
  state.error = ''
  state.notice = ''
  try {
    await adminWrite(`/products/${row.id}/actions`, {
      action: row.activity ? 'unmark_activity' : 'mark_activity',
    })
    state.notice = row.activity
      ? `已取消「${row.name}」的活动商品标记。`
      : `已把「${row.name}」设为活动商品。`
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    state.busyId = ''
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

function closeDetail() {
  detail.value = null
  detailLoading.value = false
}

// 与商品池同一套品类文案规则。
function categoryLabel(category) {
  if (!category) return '未分类'
  return category.name_zh || category.name_en || category.name
}

onMounted(() => load())
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>活动商品管理</h1>
        <p>
          把商品打上【活动商品】标记。标记不改变商品原品类；商家端上架时活动商品按活动折扣计算成本价。
        </p>
      </div>
      <div class="page-intro__actions">
        <span class="tag">共 {{ state.meta.total || 0 }} 件</span>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>

    <!-- 与【活动卡片】一致的独立 Tab 条（不与搜索同行）。 -->
    <div class="tabs">
      <button
        type="button"
        :class="{ 'is-active': state.view === 'activity' }"
        @click="switchView('activity')"
      >
        活动商品
      </button>
      <button
        type="button"
        :class="{ 'is-active': state.view === 'all' }"
        @click="switchView('all')"
      >
        全部商品
      </button>
    </div>

    <div class="panel">
      <div class="toolbar">
        <h2 class="section-title" style="margin: 0">{{ columns }}</h2>
        <div class="toolbar__search">
          <AppPicker
            v-model="state.q"
            :fetcher="fetchActivityProductOptions"
            placeholder="选择商品（名称 / 商品编号搜索）"
            :option-meta="(option) => (option.price ? `¥ ${option.price}` : '')"
            @change="search"
          />
          <button type="button" class="btn" @click="search">查询</button>
        </div>
      </div>

      <p v-if="state.loading" class="inline-loading">加载中…</p>
      <div v-else class="data-table-wrap">
        <table class="data-table activity-table">
          <thead>
            <tr>
              <th>商品</th>
              <th>品类</th>
              <th>成本价</th>
              <th>零售价</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td class="activity-cell-product">
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
              <td><StatusTag :value="row.status" :labels="PRODUCT_STATUS_LABELS" /></td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                  <button
                    type="button"
                    class="btn btn--sm"
                    :disabled="state.busyId === row.id"
                    @click="toggleActivity(row)"
                  >
                    {{ row.activity ? '取消活动标记' : '设为活动商品' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.items.length">
              <td colspan="6" class="data-table__empty">
                {{
                  state.view === 'activity'
                    ? '还没有活动商品，去「全部商品」里挑选并打标。'
                    : '没有匹配的商品。'
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <AppPager
        :page="state.meta.page || 1"
        :page-size="state.meta.page_size || 10"
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
          <span v-if="detail.content_source === 'manual'" class="badge-mini">
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
      </template>
    </AppDrawer>
  </section>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.toolbar__search {
  display: flex;
  gap: 8px;
}

/* 可搜索下拉框占原搜索输入框的宽度。 */
.toolbar__search :deep(.app-picker) {
  flex: 0 1 250px;
  min-width: 210px;
}

/* 共用的 AppPager 在 390 窄屏下按钮不换行，会把整页撑出横向滚动条，
   本页让它换行（只作用于本页的 pager 根节点，不改共用组件）。 */
.pager {
  flex-wrap: wrap;
}

/* 列宽与【商品池管理】的 .pool-table 一致（只是少一列「商家数」）。
   固定布局 + 名称列换行：全站禁止文字截断，超长名称换行而不是省略号。 */
.activity-table {
  table-layout: fixed;
  /* 窄屏（手机）时让表格在 .data-table-wrap 内横向滚动，而不是把列压扁。 */
  min-width: 860px;
}

.activity-table th,
.activity-table td {
  white-space: nowrap;
  vertical-align: middle;
}

.activity-table th:nth-child(1),
.activity-table td:nth-child(1) {
  width: 42%;
  white-space: normal;
}

.activity-table th:nth-child(2),
.activity-table td:nth-child(2) {
  width: 15%;
  overflow: visible;
  word-break: break-word;
}

.activity-table th:nth-child(3),
.activity-table td:nth-child(3),
.activity-table th:nth-child(4),
.activity-table td:nth-child(4) {
  width: 11%;
}

.activity-table th:nth-child(5),
.activity-table td:nth-child(5) {
  width: 9%;
}

.activity-table th:nth-child(6),
.activity-table td:nth-child(6) {
  width: 190px;
}

.activity-cell-product {
  width: auto;
}

/* 与商品池同一套商品单元：缩略图 + 名称 + 编号 + 详情徽标。 */
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
.activity-table td:nth-child(6) .row-actions {
  flex-wrap: nowrap;
}
</style>
