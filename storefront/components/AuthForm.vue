<script setup>
import { computed, ref, watch } from 'vue'
import { navigateTo, useHead } from '#imports'

import { useBuyerAuth } from '../composables/useBuyerAuth'

// 迭代02：登录/注册改造——
// - 登录方式 = Facebook + Google + 邮箱（不做手机号、登录页无国家选择）；
// - 邮箱注册免验证码：自填账号 + 密码即可注册成功（账号唯一，以系统 ID 区分用户）；
// - Facebook / Google 本机开发阶段为占位按钮（真实 OAuth 需开发者凭据 + 公网回调）。
const props = defineProps({
  mode: {
    type: String,
    required: true,
    validator: (value) => ['login', 'register'].includes(value),
  },
})

const { login, registerEmail, isAuthenticated } = useBuyerAuth()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const formError = ref('')
const notice = ref('')

const isRegister = computed(() => props.mode === 'register')

watch(isAuthenticated, (authed) => {
  if (authed) navigateTo('/account')
})
if (isAuthenticated.value) {
  navigateTo('/account')
}

function socialPlaceholder(provider) {
  formError.value = ''
  notice.value = `${provider} 登录暂未接入（需要开发者凭据与公网回调），请先使用邮箱注册 / 登录。`
}

async function submit() {
  submitting.value = true
  formError.value = ''
  try {
    if (isRegister.value) {
      const response = await registerEmail(email.value.trim(), password.value)
      if (response?.error) {
        formError.value = response.error?.message || 'Registration failed.'
        return
      }
      navigateTo('/account')
    } else {
      const response = await login({
        identifier: email.value.trim(),
        password: password.value,
      })
      if (response?.error) {
        formError.value = response.error?.message || 'Sign in failed.'
        return
      }
      navigateTo('/account')
    }
  } finally {
    submitting.value = false
  }
}

useHead(() => ({ title: isRegister.value ? 'Create account' : 'Sign in' }))
</script>

<template>
  <AppContainer narrow>
    <section class="auth-panel" aria-labelledby="auth-title">
      <h1 id="auth-title">{{ isRegister ? 'Create your Joybuy account' : 'Sign in' }}</h1>

      <div class="social-row">
        <button type="button" class="social-btn" @click="socialPlaceholder('Facebook')">
          <span class="social-btn__dot social-btn__dot--fb">f</span> Facebook
        </button>
        <button type="button" class="social-btn" @click="socialPlaceholder('Google')">
          <span class="social-btn__dot social-btn__dot--g">G</span> Google
        </button>
      </div>
      <p class="social-divider"><span>or use email</span></p>

      <form class="auth-form" novalidate @submit.prevent="submit">
        <div class="auth-field">
          <label for="auth-identifier">Email address</label>
          <input
            id="auth-identifier"
            v-model="email"
            type="email"
            autocomplete="username"
            placeholder="you@example.com"
            required
          />
        </div>

        <div class="auth-field">
          <label for="auth-password">Password</label>
          <input
            id="auth-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            :minlength="isRegister ? 8 : undefined"
            required
          />
          <span v-if="isRegister" class="auth-hint"
            >至少 8 位；注册即创建账号，无需邮箱验证码。</span
          >
        </div>

        <p v-if="formError" class="auth-error" role="alert">{{ formError }}</p>
        <p v-if="notice" class="auth-notice" role="status">{{ notice }}</p>

        <BaseButton variant="primary" size="lg" type="submit" :disabled="submitting">
          {{ submitting ? 'Please wait…' : isRegister ? 'Create account' : 'Sign in' }}
        </BaseButton>
      </form>

      <p v-if="isRegister" class="auth-switch">
        Already have an account? <NuxtLink to="/auth/login">Sign in</NuxtLink>
      </p>
      <p v-else class="auth-switch">
        New to Joybuy? <NuxtLink to="/auth/register">Create an account</NuxtLink>
      </p>

      <p v-if="!isRegister" class="auth-switch">
        <NuxtLink to="/auth/forgot-password">Forgot your password?</NuxtLink>
      </p>
    </section>
  </AppContainer>
</template>

<style scoped>
.auth-panel {
  max-width: 26rem;
  margin-inline: auto;
  margin-block: var(--space-10);
  padding: var(--space-8);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.social-row {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-6);
}

.social-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: 44px;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  font: inherit;
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.social-btn:hover {
  border-color: var(--colour-text-secondary);
}

.social-btn__dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.social-btn__dot--fb {
  background: #1877f2;
}

.social-btn__dot--g {
  background: #ea4335;
}

.social-divider {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: var(--space-4) 0 0;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.social-divider::before,
.social-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--colour-border);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.auth-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.auth-field label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.auth-field input {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
}

.auth-hint {
  color: var(--colour-muted);
  font-size: var(--font-size-xs, 12px);
}

.auth-error {
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.auth-notice {
  color: var(--colour-success);
  font-size: var(--font-size-sm);
}

.auth-switch {
  margin-top: var(--space-5);
  color: var(--colour-text-secondary);
  font-size: var(--font-size-sm);
}

.auth-switch a {
  color: var(--colour-accent);
  font-weight: var(--font-weight-semibold);
}
</style>
