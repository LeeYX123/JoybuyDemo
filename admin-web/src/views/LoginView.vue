<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useStaffAuth } from '@/composables/useStaffAuth'

// 平台员工登录。平台管理员额外要求验证器动态码；
// 未携带有效动态码的首次尝试会被后端拒绝。
const { login, isAuthenticated } = useStaffAuth()
const router = useRouter()

const email = ref('')
const password = ref('')
const totpCode = ref('')
const needsTotp = ref(false)
const error = ref('')
const submitting = ref(false)

// 后端错误码的中文话术（未命中的码原样展示后端消息）。
const ERROR_ZH = {
  STAFF_LOGIN_FAILED: '邮箱或密码不正确。',
  STAFF_LOGIN_RATE_LIMITED: '尝试次数过多，请稍后再试。',
  STAFF_AUTH_REQUIRED: '登录状态已过期，请重新登录。',
  STAFF_ACCOUNT_DISABLED: '该账号已被停用。',
}

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await login(email.value.trim(), password.value, totpCode.value.trim())
  } catch (caught) {
    if (caught.code === 'STAFF_TOTP_REQUIRED') {
      needsTotp.value = true
      error.value = '请输入验证器上的动态码继续登录。'
    } else {
      error.value = ERROR_ZH[caught.code] || caught.message || '登录失败，请稍后再试。'
    }
    return
  } finally {
    submitting.value = false
  }
  if (isAuthenticated.value) router.push('/')
}
</script>

<template>
  <section class="login" aria-labelledby="login-title">
    <h1 id="login-title">平台管理登录</h1>
    <form class="login__form" @submit.prevent="submit">
      <label>
        <span>员工邮箱</span>
        <input
          v-model="email"
          type="email"
          autocomplete="username"
          required
          placeholder="请输入员工邮箱"
        />
      </label>
      <label>
        <span>密码</span>
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>
      <label v-if="needsTotp">
        <span>验证器动态码</span>
        <input v-model="totpCode" inputmode="numeric" maxlength="6" autocomplete="one-time-code" />
      </label>
      <p v-if="error" class="login__error" role="alert">{{ error }}</p>
      <button type="submit" :disabled="submitting">
        {{ submitting ? '正在登录…' : '登录' }}
      </button>
    </form>
  </section>
</template>

<style scoped>
.login {
  max-width: 24rem;
  margin: 4rem auto;
  padding: var(--space-6);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-5);
}

.login__form label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
}

.login__form input {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
}

.login__error {
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.login__form button {
  min-height: 44px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--colour-accent);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}

.login__form button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
