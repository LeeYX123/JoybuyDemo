<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: 'activities', label: '平台活动' },
  { key: 'program', label: '返佣规则' },
  { key: 'commissions', label: '返佣发放' },
]

const state = reactive({
  tab: 'activities',
  kind: '',
  state: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
  notice: '',
})

const editorOpen = ref(false)
const editorBusy = ref(false)
const editorError = ref('')
const editorId = ref('')
const editor = reactive({
  title: '',
  kind: 'PERMANENT',
  start: '',
  end: '',
  description: '',
  image: '',
  sort_order: 0,
  is_referral: false,
})

const participations = ref(null)
const participationItems = ref([])

const program = ref(null)
const programBusy = ref(false)
const programError = ref('')
const programForm = reactive({ tiers: [], valid_months: 12 })

const commissionState = ref('PENDING_PAY')
const commissionPeriod = ref('')
const calculating = ref(false)

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  state.notice = ''
  try {
    if (state.tab === 'activities') {
      const params = new URLSearchParams({ page: String(state.page) })
      if (state.kind) params.set('kind', state.kind)
      if (state.state) params.set('state', state.state)
      const payload = await apiRequest(`/activities?${params}`)
      state.items = payload.items
      state.meta = payload
    } else if (state.tab === 'commissions') {
      const params = new URLSearchParams({ page: String(state.page) })
      if (commissionState.value) params.set('state', commissionState.value)
      if (commissionPeriod.value) params.set('period', commissionPeriod.value)
      const payload = await apiRequest(`/referrals/commissions?${params}`)
      state.items = payload.items
      state.meta = payload
    }
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function loadProgram() {
  try {
    const payload = await apiRequest('/referrals/program')
    program.value = payload.program
    programForm.tiers = (payload.program.tiers || []).map((tier) => ({ ...tier }))
    programForm.valid_months = payload.program.valid_months
  } catch (error) {
    state.error = error.message
  }
}

function switchTab(key) {
  state.tab = key
  state.page = 1
  state.error = ''
  if (key === 'program') {
    loadProgram()
  } else {
    load()
  }
}

function openEditor(row = null) {
  editorId.value = row?.id || ''
  editor.title = row?.title || ''
  editor.kind = row?.kind || 'PERMANENT'
  editor.start = row?.start || new Date().toISOString().slice(0, 10)
  editor.end = row?.end || ''
  editor.description = row?.description || ''
  editor.image = row?.image || ''
  editor.sort_order = row?.sort_order || 0
  editor.is_referral = Boolean(row?.is_referral)
  editorError.value = ''
  editorOpen.value = true
}

async function saveActivity() {
  editorBusy.value = true
  editorError.value = ''
  const payload = {
    title: editor.title,
    kind: editor.kind,
    start: editor.start,
    end: editor.end || null,
    description: editor.description,
    image: editor.image,
    sort_order: Number(editor.sort_order),
    is_referral: editor.is_referral,
  }
  try {
    if (editorId.value) {
      await adminWrite(`/activities/${editorId.value}`, payload, 'PATCH')
    } else {
      await adminWrite('/activities', payload)
    }
    editorOpen.value = false
    await load()
  } catch (error) {
    editorError.value = error.message
  } finally {
    editorBusy.value = false
  }
}

async function toggleActivity(row) {
  const action = row.state === 'ONGOING' ? 'end' : 'reopen'
  try {
    await adminWrite(`/activities/${row.id}/actions`, { action })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

async function openParticipations(row) {
  participations.value = row
  participationItems.value = []
  try {
    const payload = await apiRequest(`/activities/${row.id}/participations?page_size=50`)
    participationItems.value = payload.items
  } catch (error) {
    state.error = error.message
  }
}

function addTier() {
  programForm.tiers.push({ min: '0', rate: '0' })
}

function removeTier(index) {
  programForm.tiers.splice(index, 1)
}

async function saveProgram() {
  programBusy.value = true
  programError.value = ''
  try {
    await adminWrite(
      '/referrals/program',
      {
        tiers: programForm.tiers,
        valid_months: Number(programForm.valid_months),
      },
      'PUT',
    )
    await loadProgram()
    state.notice = '返佣规则已保存。新规则只影响之后核算的月份。'
  } catch (error) {
    programError.value = error.message
  } finally {
    programBusy.value = false
  }
}

async function calculate() {
  calculating.value = true
  state.error = ''
  try {
    const payload = await adminWrite('/referrals/calculate', {})
    state.notice = `已核算 ${payload.period}，生成 ${payload.count} 条待发放记录。`
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    calculating.value = false
  }
}

async function payCommission(row) {
  try {
    await adminWrite(`/referrals/commissions/${row.id}/actions`, { action: 'pay' })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

function formatTime(value) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function goPage(page) {
  state.page = page
  load()
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>平台活动与推荐返佣</h1>
        <p>创建带图片的活动，维护推荐阶梯并按笔确认发放返佣；核算只生成待发放，不会直接入钱包。</p>
      </div>
      <div class="page-intro__actions">
        <button
          v-if="state.tab === 'activities'"
          type="button"
          class="btn btn--primary"
          @click="openEditor()"
        >
          创建活动
        </button>
        <button
          v-if="state.tab === 'commissions'"
          type="button"
          class="btn"
          :disabled="calculating"
          @click="calculate"
        >
          {{ calculating ? '核算中…' : '核算上月返佣' }}
        </button>
      </div>
    </div>

    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          type="button"
          :class="{ 'is-active': state.tab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 16px 20px">
        {{ state.error }}
      </p>
      <p v-if="state.notice" class="notice notice--ok" style="margin: 16px 20px">
        {{ state.notice }}
      </p>

      <template v-if="state.tab === 'activities'">
        <div class="toolbar">
          <select v-model="state.kind" @change="load(true)">
            <option value="">全部类型</option>
            <option value="PERMANENT">常驻活动</option>
            <option value="LIMITED">限时活动</option>
          </select>
          <select v-model="state.state" @change="load(true)">
            <option value="">全部状态</option>
            <option value="ONGOING">进行中</option>
            <option value="ENDED">已结束</option>
          </select>
          <button type="button" class="btn" @click="load(true)">查询</button>
        </div>

        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>活动</th>
                <th>类型</th>
                <th>活动时间</th>
                <th>参与商家</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in state.items" :key="row.id">
                <td>
                  <div style="display: flex; gap: 10px; align-items: center">
                    <img v-if="row.image" :src="row.image" alt="" class="thumb" />
                    <div>
                      <span class="cell-strong">{{ row.title }}</span>
                      <span v-if="row.is_referral" class="cell-sub">推荐返佣常驻活动</span>
                    </div>
                  </div>
                </td>
                <td>{{ row.kind === 'LIMITED' ? '限时活动' : '常驻活动' }}</td>
                <td>{{ row.start }} ~ {{ row.end || '长期有效' }}</td>
                <td class="num">{{ row.participants }}</td>
                <td><StatusTag :value="row.state" /></td>
                <td>
                  <div class="row-actions">
                    <button type="button" class="btn btn--sm" @click="openParticipations(row)">
                      参与记录
                    </button>
                    <button type="button" class="btn btn--sm" @click="openEditor(row)">编辑</button>
                    <button type="button" class="btn btn--sm" @click="toggleActivity(row)">
                      {{ row.state === 'ONGOING' ? '结束' : '重新开放' }}
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="!state.loading && state.items.length === 0">
                <td colspan="6" class="data-table__empty">还没有创建活动。</td>
              </tr>
              <tr v-if="state.loading">
                <td colspan="6" class="data-table__empty">加载中…</td>
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
      </template>

      <template v-else-if="state.tab === 'program'">
        <div class="panel__body">
          <p v-if="programError" class="notice notice--error">{{ programError }}</p>
          <p class="field__hint">
            按每位新人的整月发货额匹配单一档位（不做分段累进）。核算后比例固定为当期快照，后续改规则不追溯。
          </p>
          <div
            v-for="(tier, index) in programForm.tiers"
            :key="index"
            class="form-grid form-grid--tight"
            style="margin-top: 12px"
          >
            <div class="field">
              <label :for="`tier-min-${index}`">档位最低金额（第 {{ index + 1 }} 档）</label>
              <input
                :id="`tier-min-${index}`"
                v-model="tier.min"
                type="number"
                min="0"
                step="0.01"
              />
            </div>
            <div class="field">
              <label :for="`tier-rate-${index}`">返佣比例（%）</label>
              <input
                :id="`tier-rate-${index}`"
                v-model="tier.rate"
                type="number"
                min="0"
                max="100"
                step="0.01"
              />
            </div>
            <div class="field">
              <span class="field__label">&nbsp;</span>
              <button
                type="button"
                class="btn btn--sm"
                :disabled="programForm.tiers.length <= 1"
                @click="removeTier(index)"
              >
                移除
              </button>
            </div>
          </div>
          <button type="button" class="btn btn--sm" style="margin-top: 10px" @click="addTier">
            新增档位
          </button>

          <div class="form-grid" style="margin-top: 16px">
            <div class="field">
              <label for="valid-months">返佣有效月数</label>
              <input
                id="valid-months"
                v-model="programForm.valid_months"
                type="number"
                min="1"
                step="1"
              />
            </div>
          </div>

          <div class="form-actions">
            <button
              type="button"
              class="btn btn--primary"
              :disabled="programBusy"
              @click="saveProgram"
            >
              {{ programBusy ? '保存中…' : '保存规则' }}
            </button>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="toolbar">
          <select v-model="commissionState" @change="load(true)">
            <option value="">全部状态</option>
            <option value="PENDING_PAY">待发放</option>
            <option value="PAID">已到账</option>
          </select>
          <input
            v-model="commissionPeriod"
            type="month"
            aria-label="核算月份"
            @change="load(true)"
          />
          <button type="button" class="btn" @click="load(true)">查询</button>
        </div>

        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>月份</th>
                <th>推荐商家</th>
                <th>新人商家</th>
                <th>新人月发货额</th>
                <th>比例</th>
                <th>返佣金额</th>
                <th>状态</th>
                <th>核算 / 到账</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in state.items" :key="row.id">
                <td>{{ row.period }}</td>
                <td>{{ row.referrer.name }}</td>
                <td>{{ row.referee.name }}</td>
                <td class="num">¥ {{ row.shipped_amount }}</td>
                <td class="num">{{ row.rate }}%</td>
                <td class="num">¥ {{ row.amount }}</td>
                <td><StatusTag :value="row.state" /></td>
                <td>
                  {{ formatTime(row.calculated_at) }}
                  <span class="cell-sub">{{
                    row.paid_at ? `到账 ${formatTime(row.paid_at)}` : '未到账'
                  }}</span>
                </td>
                <td>
                  <div class="row-actions">
                    <button
                      v-if="row.state === 'PENDING_PAY'"
                      type="button"
                      class="btn btn--sm btn--primary"
                      @click="payCommission(row)"
                    >
                      确认发放
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="!state.loading && state.items.length === 0">
                <td colspan="9" class="data-table__empty">当前筛选条件下没有返佣记录。</td>
              </tr>
              <tr v-if="state.loading">
                <td colspan="9" class="data-table__empty">加载中…</td>
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
      </template>
    </div>

    <AppDrawer
      v-if="participations"
      :title="`参与记录 · ${participations.title}`"
      @close="participations = null"
    >
      <table v-if="participationItems.length" class="data-table">
        <thead>
          <tr>
            <th>商家</th>
            <th>参与时间</th>
            <th>新增曝光</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in participationItems" :key="row.id">
            <td>{{ row.merchant }}</td>
            <td>{{ formatTime(row.joined_at) }}</td>
            <td class="num">{{ row.exposure_added }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state">还没有商家参与该活动。</p>
    </AppDrawer>

    <AppModal
      v-if="editorOpen"
      :title="editorId ? '编辑活动' : '创建活动'"
      confirm-text="保存"
      :busy="editorBusy"
      @cancel="editorOpen = false"
      @confirm="saveActivity"
    >
      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>
      <div class="form-grid">
        <div class="field">
          <label for="activity-title">活动标题</label>
          <input id="activity-title" v-model="editor.title" type="text" maxlength="160" />
        </div>
        <div class="field">
          <label for="activity-kind">活动类型</label>
          <select id="activity-kind" v-model="editor.kind">
            <option value="PERMANENT">常驻活动</option>
            <option value="LIMITED">限时活动</option>
          </select>
        </div>
        <div class="field">
          <label for="activity-start">开始日期</label>
          <input id="activity-start" v-model="editor.start" type="date" />
        </div>
        <div class="field">
          <label for="activity-end">结束日期（常驻可留空）</label>
          <input id="activity-end" v-model="editor.end" type="date" />
        </div>
        <div class="field">
          <label for="activity-sort">排序</label>
          <input id="activity-sort" v-model="editor.sort_order" type="number" min="0" step="1" />
        </div>
        <div class="field">
          <label class="checkline">
            <input v-model="editor.is_referral" type="checkbox" :disabled="Boolean(editorId)" />
            推荐返佣常驻活动（全平台只能有一个）
          </label>
        </div>
      </div>
      <div class="field" style="margin-top: 12px">
        <label for="activity-image">活动图片 URL</label>
        <input id="activity-image" v-model="editor.image" type="text" />
      </div>
      <div class="field" style="margin-top: 12px">
        <label for="activity-desc">活动说明</label>
        <textarea id="activity-desc" v-model="editor.description" rows="3" />
      </div>
    </AppModal>
  </section>
</template>
