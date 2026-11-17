<script setup>
import { computed, onMounted, reactive } from 'vue'

import ImageUploader from '@/components/ImageUploader.vue'
import { apiRequest, merchantWrite } from '@/lib/api'

const state = reactive({
  loading: true,
  error: '',
  notice: '',
  merchant: null,
  form: { name: '', avatar: '' },
  saving: false,
})

async function load() {
  state.loading = true
  state.error = ''
  try {
    const payload = await apiRequest('/merchant/profile')
    state.merchant = payload.merchant
    state.form.name = payload.merchant.name || ''
    state.form.avatar = payload.merchant.avatar || ''
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function save() {
  state.saving = true
  state.error = ''
  state.notice = ''
  try {
    // 后端是 PATCH 部分更新：不传 method 会默认 POST，直接 405。
    const payload = await merchantWrite(
      '/merchant/profile',
      { name: state.form.name, avatar: state.form.avatar },
      'PATCH',
    )
    state.merchant = { ...state.merchant, ...payload.merchant }
    state.notice = '店铺资料已保存。'
  } catch (error) {
    state.error = error.message
  } finally {
    state.saving = false
  }
}

const STATUS_LABELS = {
  DRAFT: '草稿',
  PENDING_REVIEW: '待审核',
  PENDING_DEPOSIT: '待缴保证金',
  ACTIVE: '接单中',
  REJECTED: '已驳回',
  SUSPENDED: '已封店',
}

// 角色中文映射：接口返回的是角色名（Merchant owner）或角色码（merchant_owner）。
const ROLE_LABELS = {
  merchant_owner: '店主',
  'Merchant owner': '店主',
  merchant_catalog_manager: '商品管理员',
  'Merchant catalog manager': '商品管理员',
  merchant_viewer: '查看员',
  'Merchant viewer': '查看员',
}

const roleLabel = computed(
  () => ROLE_LABELS[state.merchant?.role] || state.merchant?.role || '—',
)

function fmtDate(value) {
  if (!value) return '暂无记录'
  return value.slice(0, 16).replace('T', ' ')
}

async function copyStoreId() {
  try {
    await navigator.clipboard.writeText(state.merchant.id || '')
    state.notice = '店铺 ID 已复制到剪贴板。'
    state.error = ''
  } catch {
    state.error = '复制失败，请手动复制：' + (state.merchant.id || '')
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>店铺管理</h1>
        <p>店铺名称与头像可自行修改；状态、信誉分与保证金规则由平台维护。</p>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>
    <p v-if="state.loading" class="inline-loading">加载中…</p>

    <template v-else-if="state.merchant">
      <div class="card">
        <div class="card__head"><h2>店铺资料</h2></div>
        <div class="card__body">
          <div class="store-head">
            <span class="store-avatar">
              <img v-if="state.merchant.avatar" :src="state.merchant.avatar" alt="" />
              <template v-else>{{ state.merchant.name?.slice(0, 1) }}</template>
            </span>
            <div>
              <strong>{{ state.merchant.name }}</strong>
              <div class="cell-sub store-meta">
                <span class="store-meta__status">
                  当前状态：{{ STATUS_LABELS[state.merchant.status] || state.merchant.status }}
                </span>
                <span class="store-meta__sep" aria-hidden="true">｜</span>
                <span class="store-meta__role">角色：{{ roleLabel }}</span>
              </div>
            </div>
            <span class="tag" :class="{ 'tag--ok': state.merchant.can_operate }">
              {{ state.merchant.can_operate ? '可正常经营' : '暂不可经营' }}
            </span>
            <button type="button" class="btn btn--sm" @click="copyStoreId">复制店铺 ID</button>
          </div>

          <div class="form-grid">
            <label class="field">
              <span class="field__label">店铺名称</span>
              <input v-model="state.form.name" type="text" maxlength="30" />
              <span class="field__hint">最多 30 个字符，会展示在商城与订单中。</span>
            </label>
            <div class="field">
              <span class="field__label">店铺头像</span>
              <ImageUploader
                v-model="state.form.avatar"
                purpose="avatar"
                :max-size-mb="2"
                label="店铺头像"
                hint="建议 200×200 的正方形，支持 JPG / PNG / WebP。"
              />
            </div>
          </div>

          <div class="form-actions">
            <button type="button" class="btn btn--primary" :disabled="state.saving" @click="save">
              {{ state.saving ? '保存中…' : '保存资料' }}
            </button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card__head"><h2>经营信息</h2></div>
        <div class="card__body">
          <dl class="detail-grid">
            <div>
              <dt>钱包余额</dt>
              <dd class="num">¥ {{ state.merchant.wallet_balance }}</dd>
            </div>
            <div>
              <dt>保证金余额</dt>
              <dd class="num">
                {{
                  state.merchant.deposit_enabled
                    ? `¥ ${state.merchant.deposit_balance}`
                    : '无需缴纳'
                }}
              </dd>
            </div>
            <div>
              <dt>信誉分</dt>
              <dd>{{ state.merchant.credit_score }} / 100</dd>
            </div>
            <div>
              <dt>未发货封店天数</dt>
              <dd>{{ state.merchant.ban_after_days }} 天</dd>
            </div>
            <div>
              <dt>总关注</dt>
              <dd class="num">{{ state.merchant.followers }}</dd>
            </div>
            <div>
              <dt>曝光量</dt>
              <dd class="num">{{ state.merchant.exposure }}</dd>
            </div>
            <div>
              <dt>推荐码</dt>
              <dd class="mono">{{ state.merchant.referral_code || '—' }}</dd>
            </div>
            <div>
              <dt>入驻时间</dt>
              <dd>{{ fmtDate(state.merchant.joined) }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.store-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
}

/* flex:none 防止容器被压缩导致 logo 变形；contain 保证任何比例图都不拉伸。 */
.store-avatar {
  flex: none;
  width: 56px;
  height: 56px;
  aspect-ratio: 1 / 1;
  border-radius: 10px;
  background: var(--red-soft);
  color: var(--red);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 600;
  overflow: hidden;
}

.store-avatar img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.store-head .tag {
  margin-left: auto;
}

/* 状态/角色分割：桌面同行「｜」分隔；手机端去掉分隔符、各自一行。 */
.store-meta__sep {
  margin: 0 4px;
}

@media (max-width: 768px) {
  .store-meta__sep {
    display: none;
  }

  .store-meta__status,
  .store-meta__role {
    display: block;
  }

  /* 手机端：状态 chip（可正常经营）与「复制店铺 ID」按钮上下各占一行。 */
  .store-head {
    flex-wrap: wrap;
    gap: var(--space-3, 12px);
  }

  .store-head .tag {
    margin-left: 0;
    flex: 1 1 100%;
    justify-content: center;
  }

  .store-head .btn {
    flex: 1 1 100%;
  }
}
</style>
