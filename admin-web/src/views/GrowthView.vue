<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const state = reactive({
  q: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
  notice: '',
})

const records = ref([])

const target = ref(null)
const kind = ref('')
const busy = ref(false)
const formError = ref('')
const form = reactive({ count: '' })

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/growth?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function loadRecords() {
  try {
    const payload = await apiRequest('/growth/records?page_size=20')
    records.value = payload.items
  } catch {
    records.value = []
  }
}

function openAction(row, action) {
  target.value = row
  kind.value = action
  form.count = ''
  formError.value = ''
}

async function submit() {
  if (!target.value) return
  busy.value = true
  formError.value = ''
  try {
    await adminWrite(`/growth/${target.value.id}/actions`, {
      action: kind.value,
      count: Number(form.count),
    })
    target.value = null
    state.notice = '调整已完成，商家看板会同步刷新。'
    await Promise.all([load(), loadRecords()])
  } catch (error) {
    formError.value = error.message
  } finally {
    busy.value = false
  }
}

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

function resetFilters() {
  state.q = ''
  load(true)
}

function goPage(page) {
  state.page = page
  load()
}

onMounted(() => {
  load()
  loadRecords()
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>商家关注与曝光</h1>
        <p>只做增量调整：关注同时累加总量与当天增量，曝光只增不减，均写审计记录。</p>
      </div>
    </div>

    <p v-if="state.notice" class="notice notice--ok" style="margin-bottom: 14px">
      {{ state.notice }}
    </p>
    <p v-if="state.error" class="notice notice--error" style="margin-bottom: 14px">
      {{ state.error }}
    </p>

    <div class="panel">
      <div class="toolbar">
        <input
          v-model="state.q"
          type="search"
          placeholder="店铺名称 / 店铺 ID"
          @keyup.enter="load(true)"
        />
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>店铺</th>
              <th>总关注</th>
              <th>当日增量</th>
              <th>曝光量</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <b>{{ row.name }}</b>
                <span class="cell-sub">{{ row.id.slice(0, 8) }}</span>
              </td>
              <td class="num">{{ row.followers }}</td>
              <td class="num">
                <span v-if="row.follow_delta" class="tag tag--ok">+{{ row.follow_delta }}</span>
                <span v-else class="cell-sub">—</span>
              </td>
              <td class="num">{{ row.exposure }}</td>
              <td>
                <span class="tag" :class="row.status === 'ACTIVE' ? 'tag--ok' : 'tag--gray'">
                  {{ row.status === 'ACTIVE' ? '接单中' : row.status }}
                </span>
              </td>
              <td>
                <div class="row-actions">
                  <button
                    type="button"
                    class="btn btn--sm"
                    @click="openAction(row, 'add_followers')"
                  >
                    新增关注
                  </button>
                  <button
                    type="button"
                    class="btn btn--sm"
                    @click="openAction(row, 'add_exposure')"
                  >
                    调整曝光
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="6" class="data-table__empty">没有匹配的店铺。</td>
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

    <div class="panel">
      <div class="panel__head"><h2>最近调整记录</h2></div>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>操作人</th>
              <th>动作</th>
              <th>店铺</th>
              <th>调整前</th>
              <th>调整后</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in records" :key="row.id">
              <td>{{ formatTime(row.occurred_at) }}</td>
              <td>{{ row.operator }}</td>
              <td>{{ row.action === 'MERCHANT_FOLLOWERS_ADDED' ? '新增关注' : '调整曝光' }}</td>
              <td class="mono">{{ row.target_id.slice(0, 8) }}</td>
              <td class="mono">
                关注 {{ row.before?.followers ?? '—' }} / 曝光 {{ row.before?.exposure ?? '—' }}
              </td>
              <td class="mono">
                关注 {{ row.after?.followers ?? '—' }} / 曝光 {{ row.after?.exposure ?? '—' }}
              </td>
            </tr>
            <tr v-if="records.length === 0">
              <td colspan="6" class="data-table__empty">还没有调整记录。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <AppModal
      v-if="target"
      :title="kind === 'add_followers' ? '新增关注' : '调整曝光'"
      confirm-text="确认"
      :busy="busy"
      @cancel="target = null"
      @confirm="submit"
    >
      <p v-if="formError" class="notice notice--error">{{ formError }}</p>
      <p>{{ target.name }} · 当前总关注 {{ target.followers }}，曝光量 {{ target.exposure }}</p>
      <div class="field">
        <label for="growth-count">本次新增数量（正整数）</label>
        <input id="growth-count" v-model="form.count" type="number" min="1" step="1" />
        <span class="field__hint">
          {{
            kind === 'add_followers'
              ? '同时累加总关注与当天增量；增量次日 0 点隐藏，总量不回退。'
              : '只支持正向累加，不支持负数调整。'
          }}
        </span>
      </div>
    </AppModal>
  </section>
</template>
