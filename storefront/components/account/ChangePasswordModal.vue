<script setup>
import { computed, ref, watch } from 'vue'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { noAutofill } from '../../utils/noAutofill'

// 需求 C（2026-11-28）：【修改密码】弹窗——桌面 AppHeader 头像下拉与手机
// 账号页共用。校验：新密码 ≥8 位且与确认一致；旧密码错误走后端
// INVALID_CREDENTIALS 映射本地化文案。后端改密成功会撤销该账号全部会话并
// 在同一响应里重签当前会话（写回 cookie），因此用户保持登录不被踢出；
// 成功后刷新共享会话状态。
const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'success'])

const { t } = useLocale()
const { refresh } = useBuyerAuth()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const submitting = ref(false)
const succeeded = ref(false)

watch(
  () => props.open,
  (value) => {
    if (value) {
      oldPassword.value = ''
      newPassword.value = ''
      confirmPassword.value = ''
      error.value = ''
      submitting.value = false
      succeeded.value = false
    }
  },
)

function close() {
  if (!submitting.value) emit('close')
}

const canSubmit = computed(
  () => oldPassword.value && newPassword.value && confirmPassword.value && !submitting.value,
)

async function submit() {
  error.value = ''
  if (newPassword.value.length < 8) {
    error.value = t('account.changePassword.errorTooShort')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = t('account.changePassword.errorMismatch')
    return
  }
  submitting.value = true
  try {
    const session = await $fetch('/api/v1/auth/buyer/session', { credentials: 'include' })
    const response = await $fetch('/api/v1/account/change-password', {
      method: 'POST',
      body: {
        old_password: oldPassword.value,
        new_password: newPassword.value,
        confirm_password: confirmPassword.value,
      },
      headers: { 'X-CSRFToken': session?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (response?.error) {
      const code = response.error?.code || ''
      if (code === 'INVALID_CREDENTIALS') {
        error.value = t('account.changePassword.errorOldWrong')
      } else if (code === 'PASSWORD_TOO_SHORT') {
        error.value = t('account.changePassword.errorTooShort')
      } else if (code === 'PASSWORD_MISMATCH') {
        error.value = t('account.changePassword.errorMismatch')
      } else {
        error.value = response.error?.message || t('account.changePassword.errorGeneric')
      }
      return
    }
    // 改密成功：旧会话已全部撤销、响应已写回新会话 cookie；刷新共享会话，
    // 当前浏览器保持登录态。
    await refresh()
    succeeded.value = true
    emit('success')
    setTimeout(() => {
      emit('close')
    }, 1200)
  } catch {
    error.value = t('account.changePassword.errorGeneric')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="pwd-modal" role="dialog" aria-modal="true" aria-labelledby="pwd-title">
      <div class="pwd-modal__backdrop" @click="close"></div>
      <div class="pwd-modal__card">
        <h2 id="pwd-title" class="pwd-modal__title">{{ t('account.changePassword.title') }}</h2>

        <p v-if="succeeded" class="pwd-modal__success" role="status">
          {{ t('account.changePassword.success') }}
        </p>

        <form v-else class="pwd-modal__form" novalidate @submit.prevent="submit">
          <label class="pwd-modal__field">
            <span>{{ t('account.changePassword.old') }}</span>
            <input
              v-model="oldPassword"
              type="password"
              v-bind="noAutofill"
              :placeholder="t('account.changePassword.oldPlaceholder')"
              data-testid="pwd-old"
              required
            />
          </label>
          <label class="pwd-modal__field">
            <span>{{ t('account.changePassword.new') }}</span>
            <input
              v-model="newPassword"
              type="password"
              v-bind="noAutofill"
              minlength="8"
              :placeholder="t('account.changePassword.newPlaceholder')"
              data-testid="pwd-new"
              required
            />
          </label>
          <label class="pwd-modal__field">
            <span>{{ t('account.changePassword.confirm') }}</span>
            <input
              v-model="confirmPassword"
              type="password"
              v-bind="noAutofill"
              :placeholder="t('account.changePassword.confirmPlaceholder')"
              data-testid="pwd-confirm"
              required
            />
          </label>

          <p v-if="error" class="pwd-modal__error" role="alert" data-testid="pwd-error">
            {{ error }}
          </p>

          <div class="pwd-modal__actions">
            <button
              type="button"
              class="pwd-modal__cancel"
              data-testid="pwd-cancel"
              @click="close"
            >
              {{ t('account.changePassword.cancel') }}
            </button>
            <button
              type="submit"
              class="pwd-modal__save"
              :disabled="!canSubmit"
              data-testid="pwd-save"
            >
              {{ submitting ? t('account.changePassword.saving') : t('account.changePassword.save') }}
            </button>
          </div>
        </form>

        <button
          class="pwd-modal__x"
          type="button"
          :aria-label="t('account.changePassword.cancel')"
          @click="close"
        >
          ×
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.pwd-modal {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}

.pwd-modal__backdrop {
  position: absolute;
  inset: 0;
  background: rgb(0 0 0 / 45%);
}

.pwd-modal__card {
  position: relative;
  width: min(400px, 100%);
  padding: var(--space-5);
  border-radius: var(--radius-lg, 12px);
  background: var(--colour-surface, #fff);
  box-shadow: rgb(0 0 0 / 18%) 0 12px 40px 0;
}

.pwd-modal__title {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-lg, 20px);
  font-weight: var(--font-weight-bold);
}

.pwd-modal__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pwd-modal__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-sm, 14px);
  color: var(--colour-text-secondary, #505259);
}

.pwd-modal__field input {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border, #d9dbe0);
  border-radius: 6px;
  font: inherit;
}

.pwd-modal__error {
  margin: 0;
  color: var(--colour-error, #c0392b);
  font-size: var(--font-size-sm, 14px);
}

.pwd-modal__success {
  margin: 0;
  color: var(--colour-success, #1d7d4f);
  font-size: var(--font-size-md, 15px);
}

.pwd-modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-2);
}

.pwd-modal__cancel {
  min-height: 40px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong, #9a9ca3);
  border-radius: 6px;
  background: var(--colour-surface, #fff);
  cursor: pointer;
  font: inherit;
}

.pwd-modal__save {
  min-height: 40px;
  min-width: 96px;
  padding: 0 var(--space-4);
  border: 0;
  border-radius: 6px;
  background: var(--colour-text, #1a1a1a);
  color: var(--colour-white, #fff);
  cursor: pointer;
  font: inherit;
  font-weight: var(--font-weight-semibold);
}

.pwd-modal__save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pwd-modal__x {
  position: absolute;
  top: 10px;
  right: 12px;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--colour-text-secondary, #505259);
  font-size: 1.25rem;
  cursor: pointer;
}

.pwd-modal__x:hover {
  background: var(--colour-hover, #f0f1f2);
}
</style>
