<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useStaffAuth } from '@/composables/useStaffAuth'

// 平台员工登录：只使用邮箱+密码，不再需要验证器动态码。
const { login, isAuthenticated } = useStaffAuth()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

// 后端错误码的中文话术（未命中的码原样展示后端消息）。
const ERROR_ZH = {
  STAFF_LOGIN_FAILED: '邮箱或密码不正确。',
  INVALID_STAFF_CREDENTIALS: '邮箱或密码不正确。',
  STAFF_LOGIN_RATE_LIMITED: '尝试次数过多，请稍后再试。',
  STAFF_AUTH_REQUIRED: '登录状态已过期，请重新登录。',
  STAFF_ACCOUNT_DISABLED: '该账号已被停用。',
}

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await login(email.value.trim(), password.value)
  } catch (caught) {
    error.value = ERROR_ZH[caught.code] || caught.message || '登录失败，请稍后再试。'
    return
  } finally {
    submitting.value = false
  }
  if (isAuthenticated.value) router.push('/')
}
</script>

<template>
  <div class="login-shell">
    <div class="login-brand">
      <span class="login-logo" aria-hidden="true">寰</span>
      <span>寰球优选 · 平台管理控制台</span>
    </div>

    <section class="login-card" aria-labelledby="login-title">
      <p class="login-eyebrow">PLATFORM CONSOLE</p>
      <h1 id="login-title">平台管理登录</h1>
      <form @submit.prevent="submit">
        <div class="field">
          <label for="login-email">员工邮箱</label>
          <input
            id="login-email"
            v-model="email"
            type="email"
            autocomplete="username"
            required
            placeholder="name@joybuy.test"
          />
        </div>
        <div class="field">
          <label for="login-password">密码</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            placeholder="请输入登录密码"
          />
        </div>
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <button type="submit" class="login-submit" :disabled="submitting">
          {{ submitting ? '正在登录…' : '登录' }}
        </button>
      </form>
      <p class="login-note">账号由超级管理员在「账号与权限」中分配；登录后仅显示已授权的模块。</p>
    </section>

    <p class="login-footer">GLOBAL · OPERATIONS</p>
  </div>
</template>

<style scoped>
.login-shell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 40px 20px;
  color: #ffffff;
  background:
    radial-gradient(ellipse at 15% 20%, #203c65 0, transparent 45%),
    radial-gradient(ellipse at 90% 85%, #173860 0, transparent 40%), #101d32;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 30px;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.login-logo {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: #2f6df6;
  font-size: 20px;
  font-weight: 700;
}

.login-card {
  width: 410px;
  max-width: 100%;
  padding: 34px 38px 28px;
  border-radius: 7px;
  background: #ffffff;
  box-shadow: 0 24px 70px #0003;
  color: #253041;
}

.login-eyebrow {
  margin: 0;
  font:
    10px Arial,
    sans-serif;
  letter-spacing: 2px;
  color: #8b9bb2;
}

.login-card h1 {
  margin: 10px 0 24px;
  font-size: 24px;
  font-weight: 600;
  color: #17263c;
}

.field {
  display: grid;
  gap: 6px;
  margin-top: 18px;
}

.field label {
  font-size: 12px;
  color: #5c6e88;
}

.field input {
  width: 100%;
  min-height: 0;
  padding: 11px 12px;
  border: 1px solid #d7e0ec;
  border-radius: 3px;
  background: #ffffff;
  color: #33455e;
  font-size: 13px;
}

.field input::placeholder {
  color: #a0adbf;
}

.field input:focus {
  outline: 0;
  border-color: #6d9ef3;
  box-shadow: 0 0 0 2px #2563eb13;
}

.login-error {
  margin: 14px 0 0;
  color: #d33d4e;
  font-size: 12px;
}

.login-submit {
  width: 100%;
  margin: 12px 0 0;
  padding: 11px;
  border: 1px solid #2563eb;
  border-radius: 3px;
  background: #2563eb;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 1px 2px #2563eb14;
}

.login-submit:hover:not(:disabled) {
  background: #1d4ed8;
  border-color: #1d4ed8;
}

.login-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-note {
  margin: 24px 0 0;
  padding-top: 18px;
  border-top: 1px solid #e9edf3;
  font-size: 11px;
  color: #8898af;
}

.login-footer {
  margin-top: 30px;
  font:
    9px Arial,
    sans-serif;
  letter-spacing: 2px;
  color: #637b9d;
}
</style>
