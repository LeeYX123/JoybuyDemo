<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useMerchantSession } from '@/composables/useMerchantSession'

const { login, isAuthenticated, shops } = useMerchantSession()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await login(email.value.trim(), password.value)
  } catch (caught) {
    error.value = caught.message || '登录失败，请稍后再试。'
    return
  } finally {
    submitting.value = false
  }
  if (!isAuthenticated.value) {
    error.value = '登录状态未建立，请重试。'
    return
  }
  if (!shops.value.length) {
    error.value = '该账号还没有绑定店铺，请联系平台客服开通。'
    return
  }
  router.push('/')
}
</script>

<template>
  <div class="login-shell">
    <div class="login-card">
      <div class="login-brand">
        <span class="login-logo" aria-hidden="true">J</span>
        <div>
          <strong>商家中心</strong>
          <small>JOYBUY SELLER CENTER</small>
        </div>
      </div>

      <p class="login-eyebrow">SELLER SIGN IN</p>
      <h1>登录你的店铺</h1>

      <form @submit.prevent="submit">
        <div class="field">
          <label for="login-email">登录邮箱</label>
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

      <p class="login-note">账号由平台分配；登录后可操作的店铺由平台绑定的成员关系决定。</p>
    </div>
    <p class="login-footer">JOYBUY · SELLER OPERATIONS</p>
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
  background:
    radial-gradient(ellipse at 12% 18%, #fbd9dd 0, transparent 46%),
    radial-gradient(ellipse at 88% 82%, #f7e3e5 0, transparent 42%), var(--bg);
}

.login-card {
  width: 420px;
  max-width: 100%;
  padding: 34px 38px 28px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 20px 60px rgb(32 38 50 / 10%);
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 26px;
}

.login-logo {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: var(--red);
  color: #ffffff;
  font-size: 20px;
  font-weight: 700;
}

.login-brand strong {
  display: block;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.login-brand small {
  display: block;
  margin-top: 3px;
  font-size: 9px;
  letter-spacing: 1.8px;
  color: #9ba0a9;
}

.login-eyebrow {
  margin: 0;
  font-size: 10px;
  letter-spacing: 2px;
  color: #a2a7af;
}

.login-card h1 {
  margin: 8px 0 22px;
  font-size: 23px;
  font-weight: 700;
}

.field {
  display: grid;
  gap: 6px;
  margin-top: 16px;
}

.field label {
  font-size: 12px;
  color: #697383;
}

.field input {
  width: 100%;
  padding: 11px 12px;
  border: 1px solid #e3e6eb;
  border-radius: 5px;
  font-size: 13px;
}

.field input::placeholder {
  color: #b0b6bf;
}

.field input:focus {
  outline: 0;
  border-color: var(--red);
  box-shadow: 0 0 0 2px rgb(223 38 54 / 10%);
}

.login-error {
  margin: 14px 0 0;
  font-size: 12px;
  color: #c62f42;
}

.login-submit {
  width: 100%;
  margin-top: 14px;
  padding: 12px;
  border: 1px solid var(--red);
  border-radius: 5px;
  background: var(--red);
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.login-submit:hover:not(:disabled) {
  background: var(--red-hover);
  border-color: var(--red-hover);
}

.login-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-note {
  margin: 22px 0 0;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  font-size: 11px;
  color: #9ba0a9;
}

.login-footer {
  margin-top: 26px;
  font-size: 9px;
  letter-spacing: 2px;
  color: #a2a7af;
}
</style>
