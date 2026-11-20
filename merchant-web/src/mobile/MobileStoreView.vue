<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { useMerchantSession } from '@/composables/useMerchantSession'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳店铺管理：首页身份卡「编辑资料」的落点。
// 与桌面 StoreView 同端点（GET/PATCH /merchant/profile，头像上传复用
// merchantUpload），仅保留资料编辑主表单，桌面页的其余信息卡在手机壳
// 用状态摘要行替代。

const { activeShop } = useMerchantSession()

const state = reactive({
  loading: true,
  error: '',
  notice: '',
  merchant: null,
  form: { name: '', avatar: '' },
  saving: false,
  uploading: false,
})

const STATUS_TEXT = {
  DRAFT: '草稿',
  PENDING_REVIEW: '待审核',
  PENDING_DEPOSIT: '待缴保证金',
  ACTIVE: '接单中',
  REJECTED: '已驳回',
  SUSPENDED: '已封店',
}

const statusText = computed(() => STATUS_TEXT[state.merchant?.status] || state.merchant?.status || '—')

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

async function onAvatarChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  state.uploading = true
  state.error = ''
  try {
    const { merchantUpload } = await import('@/lib/api')
    const payload = await merchantUpload(file, 'shop-avatar')
    state.form.avatar = payload.media?.url || ''
    state.notice = '头像已上传，记得保存。'
    showToast(state.notice)
  } catch (error) {
    state.error = error.message
  } finally {
    state.uploading = false
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
    showToast(state.notice)
  } catch (error) {
    state.error = error.message
  } finally {
    state.saving = false
  }
}

onMounted(load)
</script>

<template>
  <div class="m-page">
    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-if="state.notice" class="m-notice">{{ state.notice }}</p>
    <p v-if="state.loading" class="m-loading">加载中…</p>

    <template v-else>
      <section class="m-card m-card--pad">
        <div class="m-store-status">
          <span class="m-hint">店铺状态</span>
          <b :class="state.merchant?.status === 'ACTIVE' ? 'is-ok' : ''">{{ statusText }}</b>
        </div>

        <form class="m-store-form" @submit.prevent="save">
          <span class="m-store-avatar" aria-hidden="true">
            <img v-if="state.form.avatar" :src="state.form.avatar" alt="" />
            <template v-else>{{ (state.form.name || '店').slice(0, 1) }}</template>
          </span>
          <label class="m-field">
            <span class="m-field__label">店铺头像</span>
            <input
              class="m-store-file"
              type="file"
              accept="image/*"
              aria-label="上传店铺头像"
              :disabled="state.uploading"
              @change="onAvatarChange"
            />
            <small class="m-hint">{{ state.uploading ? '上传中…' : '支持常见图片格式' }}</small>
          </label>
          <label class="m-field">
            <span class="m-field__label">店铺名称</span>
            <input v-model="state.form.name" class="m-input" type="text" required />
          </label>
          <button type="submit" class="m-btn m-btn--primary m-btn--block" :disabled="state.saving">
            {{ state.saving ? '保存中…' : '保存资料' }}
          </button>
        </form>
      </section>

      <p v-if="activeShop" class="m-hint" style="margin: 0">
        当前操作店铺：{{ activeShop.name }}（角色 {{ activeShop.role || '—' }}）
      </p>
    </template>
  </div>
</template>

<style scoped>
.m-store-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--m-line);
  margin-bottom: 14px;
}

.m-store-status b {
  font-size: 15px;
  color: var(--m-ink);
}

.m-store-status b.is-ok {
  color: var(--m-success);
}

.m-store-form {
  display: grid;
  gap: var(--m-space-4);
  align-items: start;
}

.m-store-avatar {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  overflow: hidden;
  border-radius: 12px;
  background: var(--m-tint);
  color: var(--m-accent);
  font-size: 25px;
  font-weight: 700;
}

.m-store-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.m-store-file {
  font-size: 13px;
  color: var(--m-muted);
}
</style>
