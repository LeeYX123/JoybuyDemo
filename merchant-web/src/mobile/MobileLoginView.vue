<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useMerchantSession } from '@/composables/useMerchantSession'

// 手机壳登录页：静态稿没有画登录页，字段逻辑与桌面 LoginView 完全同源
// （useMerchantSession.login），仅套移动壳样式。
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
  <div class="m-login">
    <div class="m-login__card">
      <div class="m-login__brand">
        <span class="m-login__logo" aria-hidden="true">J</span>
        <div>
          <strong>商家中心</strong>
          <small>JOYBUY SELLER</small>
        </div>
      </div>

      <h1>登录你的店铺</h1>

      <form @submit.prevent="submit">
        <div class="m-field">
          <label class="m-field__label" for="m-login-email">登录邮箱</label>
          <input
            id="m-login-email"
            v-model="email"
            class="m-input"
            type="email"
            autocomplete="username"
            required
            placeholder="name@joybuy.test"
          />
        </div>
        <div class="m-field">
          <label class="m-field__label" for="m-login-password">密码</label>
          <input
            id="m-login-password"
            v-model="password"
            class="m-input"
            type="password"
            autocomplete="current-password"
            required
            placeholder="请输入登录密码"
          />
        </div>
        <p v-if="error" class="m-error" role="alert">{{ error }}</p>
        <button type="submit" class="m-btn m-btn--primary m-btn--block" :disabled="submitting">
          {{ submitting ? '正在登录…' : '登录' }}
        </button>
      </form>

      <p class="m-login__note">账号由平台分配；登录后可操作的店铺由平台绑定的成员关系决定。</p>
    </div>
    <p class="m-login__footer">JOYBUY · SELLER OPERATIONS</p>
  </div>
</template>

<style scoped>
.m-login {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: calc(24px + env(safe-area-inset-top)) var(--m-gutter) 24px;
  background: var(--m-canvas);
}

.m-login__card {
  width: 100%;
  max-width: 390px;
  padding: 24px 20px;
  background: var(--m-paper);
  border: 1px solid var(--m-line);
  border-radius: var(--m-panel-radius);
}

.m-login__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}

.m-login__logo {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 9px;
  background: var(--m-accent);
  color: #fff;
  font-size: 20px;
  font-weight: 700;
}

.m-login__brand strong {
  display: block;
  font-size: 17px;
  color: var(--m-ink);
}

.m-login__brand small {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  letter-spacing: 1.6px;
  color: var(--m-muted);
}

h1 {
  margin: 0 0 18px;
  font-size: var(--m-text-title);
  letter-spacing: -0.02em;
  color: var(--m-ink);
}

form {
  display: grid;
  gap: var(--m-space-4);
}

.m-error {
  margin: 0;
}

.m-login__note {
  margin: 18px 0 0;
  padding-top: var(--m-space-4);
  border-top: 1px solid var(--m-line);
  font-size: 12px;
  color: var(--m-muted);
  line-height: 1.6;
}

.m-login__footer {
  margin-top: 20px;
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--m-muted);
}
</style>
