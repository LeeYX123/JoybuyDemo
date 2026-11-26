<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppPager from '@/components/AppPager.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const state = reactive({
  q: '',
  whitelisted: '',
  status: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

const detail = ref(null)
const detailLoading = ref(false)

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.whitelisted) params.set('whitelisted', state.whitelisted)
    if (state.status) params.set('status', state.status)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/buyers/accounts?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function openDetail(row) {
  detail.value = null
  detailLoading.value = true
  try {
    const payload = await apiRequest(`/buyers/accounts/${row.id}`)
    detail.value = payload.buyer
  } catch (error) {
    state.error = error.message
  } finally {
    detailLoading.value = false
  }
}

async function toggleStatus(row) {
  try {
    await adminWrite(`/buyers/accounts/${row.id}/profile`, {
      action: row.enabled ? 'disable' : 'enable',
    })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

// 迭代02：白名单就地加入/移出（原独立白名单模块已删除）。
async function toggleWhitelist(row) {
  try {
    await adminWrite(`/buyers/accounts/${row.id}/whitelist`, {
      action: row.whitelisted ? 'remove' : 'add',
    })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

const AUTH_PROVIDER_LABELS = { EMAIL: '邮箱', FACEBOOK: 'Facebook', GOOGLE: 'Google' }

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

function resetFilters() {
  state.q = ''
  state.whitelisted = ''
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

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>用户端管理</h1>
        <p>查询商城注册用户、查看白名单标识与充值消费历史。买家余额与商家钱包是两套独立账户。</p>
      </div>
    </div>

    <div class="panel">
      <div class="toolbar">
        <input
          v-model="state.q"
          type="search"
          placeholder="用户名 / 邮箱 / 手机号 / 用户 ID"
          @keyup.enter="load(true)"
        />
        <select v-model="state.whitelisted" @change="load(true)">
          <option value="">全部账号</option>
          <option value="1">仅白名单</option>
          <option value="0">非白名单</option>
        </select>
        <select v-model="state.status" @change="load(true)">
          <option value="">全部状态</option>
          <option value="ACTIVE">启用</option>
          <option value="DISABLED">停用</option>
        </select>
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 0 20px 14px">
        {{ state.error }}
      </p>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>账号</th>
              <th>登录渠道</th>
              <th>启用</th>
              <th>白名单</th>
              <th>余额</th>
              <th>支付权限</th>
              <th>注册时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <b>{{ row.account || '—' }}</b>
                <span class="cell-sub">
                  {{ row.display_name ? `${row.display_name} · ` : '' }}{{ row.id.slice(0, 8) }}
                </span>
              </td>
              <td>
                <span
                  class="tag"
                  :class="row.auth_provider === 'EMAIL' ? 'tag--gray' : 'tag--info'"
                >
                  {{ AUTH_PROVIDER_LABELS[row.auth_provider] || row.auth_provider }}
                </span>
              </td>
              <td>
                <span class="tag" :class="row.enabled ? 'tag--ok' : 'tag--danger'">
                  {{ row.enabled ? '启用' : '停用' }}
                </span>
              </td>
              <td>
                <span class="tag" :class="row.whitelisted ? 'tag--info' : 'tag--gray'">
                  {{ row.whitelisted ? '白名单' : '普通' }}
                </span>
              </td>
              <td class="num">¥ {{ row.balance }}</td>
              <td>
                <span class="tag" :class="row.whitelisted ? 'tag--ok' : 'tag--gray'">
                  {{ row.payment_permission || '—' }}
                </span>
              </td>
              <td>{{ formatTime(row.joined_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                  <!-- 迭代02：白名单就地操作（原独立白名单模块已并入本页）。 -->
                  <button
                    type="button"
                    class="btn btn--sm"
                    :class="row.whitelisted ? 'btn--danger' : 'btn--primary'"
                    @click="toggleWhitelist(row)"
                  >
                    {{ row.whitelisted ? '移出白名单' : '加入白名单' }}
                  </button>
                  <button type="button" class="btn btn--sm" @click="toggleStatus(row)">
                    {{ row.enabled ? '停用' : '启用' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="8" class="data-table__empty">没有匹配的用户。</td>
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
      :title="detail ? `用户详情 · ${detail.account}` : '用户详情'"
      wide
      @close="closeDetail"
    >
      <p v-if="detailLoading" class="inline-loading">加载中…</p>
      <template v-if="detail">
        <dl class="detail-grid">
          <div>
            <dt>用户 ID</dt>
            <dd>{{ detail.id }}</dd>
          </div>
          <div>
            <dt>账号</dt>
            <dd>{{ detail.account }}</dd>
          </div>
          <div>
            <dt>用户名</dt>
            <dd>{{ detail.display_name || '—' }}</dd>
          </div>
          <div>
            <dt>邮箱</dt>
            <dd>{{ detail.email || '—' }}</dd>
          </div>
          <div>
            <dt>手机号</dt>
            <dd>{{ detail.phone || '—' }}</dd>
          </div>
          <div>
            <dt>登录渠道</dt>
            <dd>{{ AUTH_PROVIDER_LABELS[detail.auth_provider] || detail.auth_provider }}</dd>
          </div>
          <div>
            <dt>支付权限</dt>
            <dd>{{ detail.whitelisted ? '全部可用' : '不可支付' }}</dd>
          </div>
          <div>
            <dt>余额</dt>
            <dd>¥ {{ detail.balance }}</dd>
          </div>
          <div>
            <dt>白名单</dt>
            <dd>{{ detail.whitelisted ? '是' : '否' }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{{ detail.enabled ? '启用' : '停用' }}</dd>
          </div>
          <div>
            <dt>注册时间</dt>
            <dd>{{ formatTime(detail.joined_at) }}</dd>
          </div>
        </dl>

        <h3 class="section-title">充值 / 消费明细</h3>
        <table v-if="detail.ledger?.length" class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>金额</th>
              <th>变动后</th>
              <th>关联订单</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in detail.ledger" :key="entry.id">
              <td>{{ formatTime(entry.occurred_at) }}</td>
              <td>
                {{
                  entry.kind === 'RECHARGE'
                    ? '余额充值'
                    : entry.kind === 'PURCHASE'
                      ? '商城消费'
                      : '余额调整'
                }}
              </td>
              <td
                class="num"
                :style="{ color: Number(entry.amount) < 0 ? 'var(--red)' : 'var(--green)' }"
              >
                ¥ {{ entry.amount }}
              </td>
              <td class="num">¥ {{ entry.balance_after }}</td>
              <td class="mono">{{ entry.order_id ? entry.order_id.slice(0, 8) : '—' }}</td>
              <td>{{ entry.note || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">暂无资金明细。</p>
      </template>
    </AppDrawer>
  </section>
</template>
