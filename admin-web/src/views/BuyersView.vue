<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
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

const profileTarget = ref(null)
const profileBusy = ref(false)
const profileForm = reactive({ region: '' })

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

function openProfile(row) {
  profileTarget.value = row
  profileForm.region = row.region || ''
}

async function saveProfile() {
  if (!profileTarget.value) return
  profileBusy.value = true
  try {
    await adminWrite(`/buyers/accounts/${profileTarget.value.id}/profile`, {
      action: 'set_region',
      region: profileForm.region,
    })
    profileTarget.value = null
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    profileBusy.value = false
  }
}

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
          placeholder="账号 / 邮箱 / 手机号 / 用户 ID"
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
              <th>地区</th>
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
                <span class="cell-sub">{{ row.id.slice(0, 8) }}</span>
              </td>
              <td>{{ row.region || '未设置' }}</td>
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
                <span class="cell-sub">{{ row.checkout_allowed ? '可进入支付' : '不可支付' }}</span>
                <span class="cell-sub">
                  {{ row.balance_pay_allowed ? '支持余额支付' : '不支持余额支付' }}
                </span>
              </td>
              <td>{{ formatTime(row.joined_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                  <button type="button" class="btn btn--sm" @click="openProfile(row)">
                    改地区
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
            <dt>邮箱</dt>
            <dd>{{ detail.email || '—' }}</dd>
          </div>
          <div>
            <dt>手机号</dt>
            <dd>{{ detail.phone || '—' }}</dd>
          </div>
          <div>
            <dt>地区</dt>
            <dd>{{ detail.region || '未设置' }}</dd>
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
          <div>
            <dt>上次在线</dt>
            <dd>{{ formatTime(detail.last_online_at) }}</dd>
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

    <AppModal
      v-if="profileTarget"
      title="修改用户地区"
      confirm-text="保存"
      :busy="profileBusy"
      @cancel="profileTarget = null"
      @confirm="saveProfile"
    >
      <div class="field">
        <label for="buyer-region">所在地区（ISO 代码，如 GB / CN）</label>
        <input id="buyer-region" v-model="profileForm.region" type="text" maxlength="32" />
        <span class="field__hint">
          未开放地区需加入白名单才能进入支付；已开放地区（GB / CN / HK / US）普通用户即可支付。
        </span>
      </div>
    </AppModal>
  </section>
</template>
