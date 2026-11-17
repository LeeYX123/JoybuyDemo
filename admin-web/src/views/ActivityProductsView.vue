<script setup>
import { computed, onMounted, reactive } from 'vue'

import AppPager from '@/components/AppPager.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

// 活动商品管理（WP-42，文档「二、管理端 → 平台运营管理 → 活动商品管理」）：
// 把商品打上/取消【活动商品】标记。该标记不改变商品原品类，
// 只影响商家端【商品上架中心】的活动商品分类与活动折扣取值。

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
          <input
            v-model="state.q"
            type="search"
            placeholder="输入商品名称 / ID"
            @keyup.enter="search"
          />
          <button type="button" class="btn" @click="search">查询</button>
        </div>
      </div>

      <p v-if="state.loading" class="inline-loading">加载中…</p>
      <div v-else class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>商品</th>
              <th>品类</th>
              <th>零售价</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <b>{{ row.name }}</b>
                <span class="cell-sub mono">{{ row.id.slice(0, 8) }}</span>
              </td>
              <td>{{ row.merchant_category_label || '未分类' }}</td>
              <td class="num">¥ {{ row.price || '—' }}</td>
              <td>
                <span v-if="row.activity" class="tag tag--red">活动商品</span>
                <span v-else class="tag tag--gray">普通商品</span>
              </td>
              <td>
                <button
                  type="button"
                  class="btn btn--sm"
                  :disabled="state.busyId === row.id"
                  @click="toggleActivity(row)"
                >
                  {{ row.activity ? '取消活动标记' : '设为活动商品' }}
                </button>
              </td>
            </tr>
            <tr v-if="!state.items.length">
              <td colspan="5" class="data-table__empty">
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

.toolbar__search input {
  min-width: 220px;
}
</style>
