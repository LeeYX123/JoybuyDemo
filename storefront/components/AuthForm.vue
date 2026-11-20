<script setup>
import { computed, ref, watch } from 'vue'
import { navigateTo, useHead, useRoute } from '#imports'
import { useLocale } from '../composables/useLocale'
import { useBuyerAuth } from '../composables/useBuyerAuth'

// 批次 B（迭代03 11.3）：登录/注册页 1:1 复刻 Joybuy 真站实测皮肤
// （实测值见 var/auth_page_20261119/measurement.md）：
// - 白底页面中央 380px 竖列，无卡片容器、无 tab（真站即无 tab）；
// - 邮箱/电话 + 密码同屏直填；表单下「注册/登录」切换链接 + 忘记密码入口；
// - 真站的第三方登录区（Google 等全部外部账号入口）与注册礼包文案按需求不渲染；
// - 只换视觉皮，不改认证契约（/auth/buyer/login、/auth/buyer/register/email）。
const props = defineProps({
  mode: {
    type: String,
    required: true,
    validator: (value) => ['login', 'register'].includes(value),
  },
})

const { t } = useLocale()
const route = useRoute()
const { login, registerEmail, isAuthenticated } = useBuyerAuth()

const identifier = ref('')
const password = ref('')
const submitting = ref(false)
const formError = ref('')
const identifierError = ref('')
const passwordError = ref('')

const isRegister = computed(() => props.mode === 'register')

// 登录成功回跳来源页：沿用 useWishlist 的 ?next= 约定，缺省进账户页。
const nextPath = computed(() => {
  const target = route.query.next
  if (typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')) {
    return target
  }
  return '/account'
})

watch(isAuthenticated, (authed) => {
  if (authed) navigateTo(nextPath.value)
})
if (isAuthenticated.value) {
  navigateTo(nextPath.value)
}

// 后端业务码 → 双语行内文案（响应体 { error: { code, message } }）。
const ERROR_MESSAGE_KEYS = {
  INVALID_CREDENTIALS: 'auth.error.invalidCredentials',
  EMAIL_INVALID: 'auth.error.emailInvalid',
  PASSWORD_TOO_SHORT: 'auth.error.passwordTooShort',
  BUYER_ACCOUNT_EXISTS: 'auth.error.accountExists',
  BUYER_LOGIN_RATE_LIMITED: 'auth.error.rateLimited',
  BUYER_ACCOUNT_DISABLED: 'auth.error.accountDisabled',
}

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
// 后端 normalize_identifier 只认 E.164 电话（+开头 8~15 位）。
const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/

function validateIdentifier() {
  const value = identifier.value.trim()
  if (!value) {
    identifierError.value = t('auth.identifierRequired')
    return false
  }
  if (isRegister.value) {
    if (!EMAIL_PATTERN.test(value)) {
      identifierError.value = t('auth.error.emailInvalid')
      return false
    }
    return true
  }
  if (!value.includes('@') && !PHONE_PATTERN.test(value)) {
    identifierError.value = t('auth.identifierInvalid')
    return false
  }
  return true
}

function validatePassword() {
  if (!password.value) {
    passwordError.value = t('auth.passwordRequired')
    return false
  }
  if (isRegister.value && password.value.length < 8) {
    passwordError.value = t('auth.passwordShort')
    return false
  }
  return true
}

function applyBackendError(response, fallbackKey) {
  const code = response?.error?.code || ''
  const key = ERROR_MESSAGE_KEYS[code]
  formError.value = key ? t(key) : response?.error?.message || t(fallbackKey)
}

async function submit() {
  formError.value = ''
  identifierError.value = ''
  passwordError.value = ''
  if (!validateIdentifier() || !validatePassword()) return

  submitting.value = true
  try {
    if (isRegister.value) {
      const response = await registerEmail(identifier.value.trim(), password.value)
      if (response?.error) {
        applyBackendError(response, 'auth.error.generic')
        return
      }
      navigateTo(nextPath.value)
    } else {
      const response = await login({
        identifier: identifier.value.trim(),
        password: password.value,
      })
      if (response?.error) {
        applyBackendError(response, 'auth.error.generic')
        return
      }
      navigateTo(nextPath.value)
    }
  } finally {
    submitting.value = false
  }
}

useHead(() => ({ title: isRegister.value ? t('auth.titleRegister') : t('auth.titleLogin') }))
</script>

<template>
  <section class="auth-page" aria-labelledby="auth-title">
    <div class="auth-column">
      <h1 id="auth-title" class="auth-title">
        {{ isRegister ? t('auth.titleRegister') : t('auth.titleLogin') }}
      </h1>
      <p class="auth-subtitle">
        <svg
          v-if="!isRegister"
          class="auth-subtitle__icon"
          viewBox="0 0 12 12"
          width="12"
          height="12"
          aria-hidden="true"
        >
          <path
            d="M6 1a2.75 2.75 0 0 1 2.75 2.75V5H9a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h.25V3.75A2.75 2.75 0 0 1 6 1Zm0 1.2c-.86 0-1.55.7-1.55 1.55V5h3.1V3.75c0-.86-.69-1.55-1.55-1.55Z"
            fill="currentColor"
          />
        </svg>
        <span>{{ isRegister ? t('auth.subtitleRegister') : t('auth.subtitleEncryption') }}</span>
      </p>

      <form class="auth-form" novalidate @submit.prevent="submit">
        <div class="auth-field">
          <label class="auth-field__label" for="auth-identifier">
            {{ isRegister ? t('auth.emailAddress') : t('auth.identifierLabel') }}
          </label>
          <div class="auth-field__box auth-field__box--filled">
            <input
              id="auth-identifier"
              v-model="identifier"
              :type="isRegister ? 'email' : 'text'"
              :name="isRegister ? 'email' : 'identifier'"
              :autocomplete="isRegister ? 'email' : 'username'"
              :placeholder="isRegister ? t('auth.emailAddress') : t('auth.identifierPlaceholder')"
            />
          </div>
          <p v-if="identifierError" class="auth-field__error" role="alert">
            {{ identifierError }}
          </p>
        </div>

        <div class="auth-field">
          <label class="auth-field__label" for="auth-password">
            {{ isRegister ? t('auth.passwordCreateLabel') : t('auth.passwordLabel') }}
          </label>
          <div class="auth-field__box auth-field__box--outline">
            <input
              id="auth-password"
              v-model="password"
              type="password"
              name="password"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
            />
          </div>
          <p v-if="passwordError" class="auth-field__error" role="alert">{{ passwordError }}</p>
        </div>

        <p v-if="formError" class="auth-form-error" role="alert">{{ formError }}</p>

        <button class="auth-submit" type="submit" :disabled="submitting">
          {{
            submitting
              ? t('auth.submitting')
              : isRegister
                ? t('auth.submitRegister')
                : t('auth.continue')
          }}
        </button>
      </form>

      <div class="auth-links">
        <p v-if="isRegister" class="auth-links__row">
          {{ t('auth.alreadyHaveAccount') }}
          <NuxtLink to="/auth/login">{{ t('header.signIn') }}</NuxtLink>
        </p>
        <p v-else class="auth-links__row">
          {{ t('auth.newToJoybuy') }}
          <NuxtLink to="/auth/register">{{ t('auth.createAccount') }}</NuxtLink>
        </p>
        <p v-if="!isRegister" class="auth-links__row">
          <NuxtLink to="/auth/forgot-password">{{ t('auth.forgotPassword') }}</NuxtLink>
        </p>
      </div>

      <p class="auth-agreement">
        {{ t('auth.agreePrefix') }}
        <span class="auth-agreement__link">{{ t('auth.privacyPolicy') }}</span>
        {{ t('auth.and') }}
        <span class="auth-agreement__link">{{ t('auth.terms') }}</span>
      </p>
    </div>
  </section>
</template>

<style scoped>
/* 实测值（var/auth_page_20261119/measurement.md）：
   主黑 #1A1A1A / 红与错误 #E1251B / 灰字 #6E7078 / 灰底 #F5F6FA / 禁用 #C2C4CC / 描边 #BBBFC4 */
.auth-page {
  display: flex;
  justify-content: center;
  padding: 40px 16px 96px;
  background: #fff;
}

.auth-column {
  width: 380px;
  max-width: 100%;
}

.auth-title {
  margin: 0 0 4px;
  color: #1a1a1a;
  font-size: 18px;
  font-weight: 700;
  line-height: 24px;
  text-align: center;
}

.auth-subtitle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin: 0;
  color: #6e7078;
  font-size: 14px;
  line-height: 20px;
}

.auth-subtitle__icon {
  flex: none;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 32px;
}

.auth-field__label {
  display: block;
  margin-bottom: 8px;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 400;
  line-height: 23px;
}

.auth-field__box {
  display: flex;
  align-items: center;
  height: 48px;
  border-radius: 4px;
}

.auth-field__box--filled {
  background: #f5f6fa;
}

.auth-field__box--outline {
  border: 1px solid #bbbfc4;
  transition: border-color 0.15s ease;
}

.auth-field__box--outline:focus-within {
  border-color: #1a1a1a;
}

.auth-field__box input {
  width: 100%;
  height: 100%;
  padding: 0 14px;
  border: 0;
  background: transparent;
  border-radius: inherit;
  color: rgba(0, 0, 0, 0.87);
  font: inherit;
  font-size: 16px;
  outline: none;
}

.auth-field__box input::placeholder {
  color: #9ba0a8;
}

.auth-field__error {
  margin: 4px 0 0;
  color: #e1251b;
  font-size: 12px;
  line-height: 18px;
}

.auth-form-error {
  margin: 0;
  color: #e1251b;
  font-size: 14px;
  line-height: 20px;
}

.auth-submit {
  width: 100%;
  height: 48px;
  margin-top: 4px;
  border: 0;
  border-radius: 4px;
  background: #1a1a1a;
  color: #fff;
  font: inherit;
  font-size: 18px;
  font-weight: 600;
  cursor: pointer;
}

.auth-submit:disabled {
  background: #c2c4cc;
  cursor: not-allowed;
}

.auth-links {
  margin-top: 24px;
  text-align: center;
}

.auth-links__row {
  margin: 0 0 8px;
  color: #6e7078;
  font-size: 14px;
  line-height: 20px;
}

.auth-links__row a {
  color: #1a1a1a;
  font-weight: 500;
  text-decoration: underline;
}

.auth-links__row a:hover {
  color: #e1251b;
}

.auth-agreement {
  margin: 40px 0 0;
  color: #6e7078;
  font-size: 12px;
  line-height: 18px;
  text-align: center;
}

.auth-agreement__link {
  color: #6e7078;
  font-weight: 500;
  text-decoration: underline;
}
</style>
