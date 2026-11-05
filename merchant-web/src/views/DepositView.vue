<script setup>
import { onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'

import AppPager from '@/components/AppPager.vue'
import { apiRequest } from '@/lib/api'

const PAGE_SIZE = 10
const router = useRouter()

const state = reactive({
  loading: true,
  error: '',
  deposit: null,
  items: [],
  total: 0,
  page: 1,
  hasNext: false,
})

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) })
    const payload = await apiRequest(`/merchant/deposit?${params}`)
    state.deposit = payload.deposit
    state.items = payload.items || []
    state.total = payload.total || 0
    state.hasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function goPage(page) {
  state.page = page
  load()
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

function goSupport() {
  router.push('/messages')
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>保证金管理</h1>
        <p>保证金由平台审核时确定，启用或免缴在首次审核通过后双向锁定。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="goSupport">联系客服缴纳</button>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.loading" class="inline-loading">加载中…</p>

    <template v-else-if="state.deposit">
      <p v-if="!state.deposit.enabled" class="notice notice--info">
        当前店铺在入驻审核时选择了免缴保证金，因此没有保证金记录。该规则在首次审核通过后已锁定，无需也无法补缴。
      </p>

      <div v-if="state.deposit.enabled" class="stat-grid">
        <div class="stat-card">
          <div class="stat-card__label">应缴金额</div>
          <div class="stat-card__value">¥ {{ state.deposit.required }}</div>
          <div class="stat-card__hint">审核时确定，不可修改</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">保证金余额</div>
          <div class="stat-card__value">¥ {{ state.deposit.balance }}</div>
          <div class="stat-card__hint">由平台客服充值入账</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">待缴金额</div>
          <div class="stat-card__value">¥ {{ state.deposit.pending }}</div>
          <div class="stat-card__hint">缴足后才能上架商品</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">缴纳状态</div>
          <div class="stat-card__value" style="font-size: 20px">
            <span :class="state.deposit.status === 'PAID' ? 'up' : 'down'">
              ● {{ state.deposit.status === 'PAID' ? '已缴纳' : '待缴保证金' }}
            </span>
          </div>
          <div class="stat-card__hint">
            {{ state.deposit.initial_paid ? '首次已缴足' : '首次未缴足，暂不能上架' }}
          </div>
        </div>
      </div>

      <p v-if="state.deposit.enabled" class="notice notice--info">
        保证金余额与钱包余额是两个账户：保证金不参与发货扣款，商家不能自行修改，充值请联系平台客服。
      </p>

      <div v-if="state.deposit.enabled" class="card">
        <div class="card__head"><h2>保证金记录</h2></div>
        <div class="card__body">
          <table v-if="state.items.length" class="data-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>类型</th>
                <th>金额</th>
                <th>变动后余额</th>
                <th>关联单号</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in state.items" :key="row.id">
                <td>{{ fmtDate(row.occurred_at) }}</td>
                <td>{{ row.kind_label }}</td>
                <td class="num" :class="Number(row.amount) >= 0 ? 'up' : 'down'">
                  {{ Number(row.amount) >= 0 ? '+' : '' }}{{ row.amount }}
                </td>
                <td class="num">¥ {{ row.balance_after }}</td>
                <td class="mono">{{ row.related_id || '—' }}</td>
                <td class="cell-sub">{{ row.note || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty-state">还没有保证金记录。</p>
        </div>
      </div>

      <AppPager
        :page="state.page"
        :page-size="PAGE_SIZE"
        :total="state.total"
        :has-next="state.hasNext"
        @change="goPage"
      />
    </template>
  </section>
</template>
