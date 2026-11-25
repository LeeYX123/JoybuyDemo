<script setup>
import { computed, ref, watch } from 'vue'
import { navigateTo, useHead, useRoute } from '#imports'
import { useLocale } from '../composables/useLocale'
import { useMarketLocale } from '../composables/useMarketLocale'
import { useBuyerAuth } from '../composables/useBuyerAuth'

// 登录/注册页：1:1 复刻 joybuy.co.uk（实测见 var/auth_page_20261124/，方案见 docs/17）。
// 三态状态机，对应真站 email-first：
//   identifier（第一屏）→ lookup 命中 → password；未命中 → register
//   `/auth/register` 直达 → 直接进入 register（邮箱可编辑）
// 视觉 token：主黑 #1A1A1A / 红 #E1251B / 灰字 #6E7078 / 灰底 #F5F6FA / 禁用 #C2C4CC / 描边 #BBBFC4
const props = defineProps({
  mode: {
    type: String,
    required: true,
    validator: (value) => ['login', 'register'].includes(value),
  },
  // 三方渠道由页面在 SSR 阶段取好传进来（见 pages/auth/*.vue），组件只负责渲染。
  providers: {
    type: Array,
    default: () => [],
  },
})

const { t } = useLocale()
const { availableLocales, localeCode, setMarketLocale } = useMarketLocale()
const route = useRoute()
const { login, registerEmail, isAuthenticated, lookupIdentifier } = useBuyerAuth()

const step = ref(props.mode === 'register' ? 'register' : 'identifier')
// 邮箱是否锁定（真站：从第一步带过来的邮箱显示为灰底只读 + 铅笔图标）
const emailLocked = ref(false)

const identifier = ref('')
const password = ref('')
const submitting = ref(false)
const formError = ref('')
const identifierError = ref('')
const passwordError = ref('')

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
// 后端 normalize_identifier 只认 E.164 电话（+ 开头 8~15 位）
const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/

// 登录成功回跳：沿用 ?next= 约定，缺省进账户页。
const nextPath = computed(() => {
  const target = route.query.next
  if (typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')) {
    return target
  }
  return '/account'
})

// 后端业务码 → 行内文案（响应体 { error: { code, message } }）
const ERROR_MESSAGE_KEYS = {
  INVALID_CREDENTIALS: 'auth.error.invalidCredentials',
  EMAIL_INVALID: 'auth.error.emailInvalid',
  PASSWORD_TOO_SHORT: 'auth.error.passwordTooShort',
  BUYER_ACCOUNT_EXISTS: 'auth.error.accountExists',
  BUYER_LOGIN_RATE_LIMITED: 'auth.error.rateLimited',
  BUYER_ACCOUNT_DISABLED: 'auth.error.accountDisabled',
  IDENTIFIER_INVALID: 'auth.identifierInvalid',
  IDENTIFIER_LOOKUP_RATE_LIMITED: 'auth.error.lookupRateLimited',
}
// 三方登录失败回跳带回来的 ?oauth_error=xxx
const OAUTH_ERROR_KEYS = {
  state_invalid: 'auth.error.oauthState',
  denied: 'auth.error.oauthDenied',
  email_exists: 'auth.error.accountExists',
  disabled: 'auth.error.accountDisabled',
  provider_unavailable: 'auth.error.oauthUnavailable',
  provider_error: 'auth.error.oauthUnavailable',
  provider_unavailable_network: 'auth.error.oauthUnavailable',
  rate_limited: 'auth.error.rateLimited',
}

watch(
  isAuthenticated,
  (authed) => {
    if (authed) navigateTo(nextPath.value)
  },
  { immediate: true },
)

// 从三方回调回来时把错误显示在表单里（真站是把错误挂在表单上方）。
const oauthErrorCode = computed(() => {
  const value = route.query.oauth_error
  return typeof value === 'string' ? value : ''
})
watch(
  oauthErrorCode,
  (code) => {
    if (!code) return
    formError.value = t(OAUTH_ERROR_KEYS[code] || 'auth.error.oauthUnavailable')
  },
  { immediate: true },
)

const providers = computed(() => (props.providers || []).filter((item) => item && item.start_url))
const showSocial = computed(() => step.value === 'identifier' && providers.value.length > 0)

// 地区选择器显示**语言名**（用户要求去掉国旗、不显示国家名）。
const localeName = computed(() => {
  const found = (availableLocales.value || []).find((item) => item.code === localeCode.value)
  return found?.name || ''
})

const isRegisterStep = computed(() => step.value === 'register')
const title = computed(() =>
  isRegisterStep.value ? t('auth.createAccountTitle') : t('auth.titleLogin'),
)
const subtitle = computed(() =>
  isRegisterStep.value ? t('auth.createAccountSubtitle') : t('auth.subtitleEncryption'),
)

function providerLabel(provider) {
  return t(
    provider.provider === 'google' ? 'auth.oauth.continueGoogle' : 'auth.oauth.continueFacebook',
  )
}

function oauthHref(provider) {
  const query = new URLSearchParams({ next: nextPath.value })
  return `${provider.start_url}?${query.toString()}`
}

// 凭据未配置的渠道：按钮照样并排显示（用户要求与 Google 一致），点击给行内提示。
function handleProviderClick(provider, event) {
  if (provider.enabled) return
  event.preventDefault()
  identifierError.value = ''
  formError.value = t('auth.error.oauthUnavailable')
}

function validateIdentifier() {
  const value = identifier.value.trim()
  if (!value) {
    identifierError.value = t('auth.identifierRequired')
    return false
  }
  if (!value.includes('@') && !PHONE_PATTERN.test(value)) {
    identifierError.value = t('auth.identifierInvalid')
    return false
  }
  if (value.includes('@') && !EMAIL_PATTERN.test(value)) {
    identifierError.value = t('auth.error.emailInvalid')
    return false
  }
  return true
}

function validatePassword({ creating }) {
  if (!password.value) {
    passwordError.value = t('auth.passwordRequired')
    return false
  }
  if (creating && password.value.length < 8) {
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

function resetErrors() {
  formError.value = ''
  identifierError.value = ''
  passwordError.value = ''
}

/** 第一屏：问后端这个标识是否已注册，决定进密码步还是注册步。 */
async function submitIdentifier() {
  resetErrors()
  if (!validateIdentifier()) return

  submitting.value = true
  try {
    const response = await lookupIdentifier(identifier.value.trim())
    if (response?.error) {
      applyBackendError(response, 'auth.error.generic')
      return
    }
    if (response?.kind === 'PHONE' && response.exists === false) {
      // 本站不支持手机号注册（无短信通道），提示改用邮箱。
      identifierError.value = t('auth.error.phoneNeedsEmail')
      return
    }
    identifier.value = identifier.value.trim()
    emailLocked.value = true
    password.value = ''
    step.value = response?.exists ? 'password' : 'register'
  } finally {
    submitting.value = false
  }
}

async function submitPassword() {
  resetErrors()
  if (!validatePassword({ creating: false })) return

  submitting.value = true
  try {
    const response = await login({ identifier: identifier.value, password: password.value })
    if (response?.error) {
      applyBackendError(response, 'auth.error.generic')
      return
    }
    navigateTo(nextPath.value)
  } finally {
    submitting.value = false
  }
}

async function submitRegister() {
  resetErrors()
  if (!EMAIL_PATTERN.test(identifier.value.trim())) {
    identifierError.value = t('auth.error.emailInvalid')
    return
  }
  if (!validatePassword({ creating: true })) return

  submitting.value = true
  try {
    const response = await registerEmail(identifier.value.trim(), password.value)
    if (response?.error) {
      applyBackendError(response, 'auth.error.generic')
      return
    }
    navigateTo(nextPath.value)
  } finally {
    submitting.value = false
  }
}

/** 点铅笔回到第一步改邮箱（真站行为）。 */
function changeIdentifier() {
  resetErrors()
  step.value = 'identifier'
  emailLocked.value = false
  password.value = ''
}

useHead({ title: () => title.value })
</script>

<template>
  <section class="auth-page" aria-labelledby="auth-title">
    <div class="auth-column">
      <h1 id="auth-title" class="auth-title">{{ title }}</h1>
      <p class="auth-subtitle">
        <svg
          v-if="!isRegisterStep"
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
        <span>{{ subtitle }}</span>
      </p>

      <p v-if="step === 'identifier'" class="auth-promo">
        {{ t('auth.promoPrefix') }}
        <span class="auth-promo__amount">{{ t('auth.promoDiscount') }}</span>
        {{ t('auth.promoSuffix') }}
        <svg class="auth-promo__info" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.2" />
          <circle cx="8" cy="4.6" r="0.9" fill="currentColor" />
          <path d="M8 7v4.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
        </svg>
      </p>

      <!-- 第一屏：只收邮箱/手机号 -->
      <form
        v-if="step === 'identifier'"
        class="auth-form"
        novalidate
        @submit.prevent="submitIdentifier"
      >
        <div class="auth-field">
          <label class="auth-field__label" for="auth-identifier">
            {{ t('auth.identifierLabel') }}
          </label>
          <div class="auth-field__box auth-field__box--filled">
            <input
              id="auth-identifier"
              v-model="identifier"
              type="text"
              name="identifier"
              autocomplete="username"
              :placeholder="t('auth.identifierPlaceholder')"
            />
          </div>
          <p v-if="identifierError" class="auth-field__error" role="alert">
            {{ identifierError }}
          </p>
        </div>

        <p v-if="formError" class="auth-form-error" role="alert">{{ formError }}</p>

        <button class="auth-submit" type="submit" :disabled="submitting">
          {{ submitting ? t('auth.submitting') : t('auth.continue') }}
        </button>
      </form>

      <!-- 分隔 + 三方登录（仅第一屏；无可用渠道时整块不渲染） -->
      <template v-if="showSocial">
        <p class="auth-divider">
          <span>{{ t('auth.oauth.or') }}</span>
        </p>
        <div class="auth-social">
          <!-- 未配置凭据的渠道也并排显示（同款按钮），点击给「暂不可用」提示 -->
          <component
            :is="provider.enabled ? 'a' : 'button'"
            v-for="provider in providers"
            :key="provider.provider"
            class="auth-social__button"
            :href="provider.enabled ? oauthHref(provider) : undefined"
            :type="provider.enabled ? undefined : 'button'"
            data-testid="oauth-button"
            @click="handleProviderClick(provider, $event)"
          >
            <span class="auth-social__icon" aria-hidden="true">
              <svg v-if="provider.provider === 'google'" viewBox="0 0 24 24" width="24" height="24">
                <path
                  fill="#4285F4"
                  d="M23.5 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.45a5.52 5.52 0 0 1-2.39 3.62v3.01h3.86c2.26-2.08 3.58-5.15 3.58-8.82Z"
                />
                <path
                  fill="#34A853"
                  d="M12 24c3.24 0 5.96-1.08 7.92-2.91l-3.86-3.01c-1.07.72-2.44 1.15-4.06 1.15-3.12 0-5.77-2.11-6.71-4.95H1.3v3.09A12 12 0 0 0 12 24Z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.29 14.28a7.2 7.2 0 0 1 0-4.56V6.63H1.3a12 12 0 0 0 0 10.74l3.99-3.09Z"
                />
                <path
                  fill="#EA4335"
                  d="M12 4.77c1.76 0 3.34.61 4.58 1.79l3.42-3.42A11.52 11.52 0 0 0 12 0 12 12 0 0 0 1.3 6.63l3.99 3.09C6.23 6.88 8.88 4.77 12 4.77Z"
                />
              </svg>
              <svg v-else viewBox="0 0 24 24" width="24" height="24">
                <circle cx="12" cy="12" r="12" fill="#1877F2" />
                <path
                  fill="#fff"
                  d="M16.4 15.5l.53-3.5h-3.36V9.7c0-.96.47-1.9 1.98-1.9h1.53V4.8s-1.39-.24-2.72-.24c-2.77 0-4.58 1.68-4.58 4.72V12H6.7v3.5h3.08V24a12.2 12.2 0 0 0 3.8 0v-8.5h2.82Z"
                />
              </svg>
            </span>
            <span class="auth-social__label">{{ providerLabel(provider) }}</span>
          </component>
        </div>

        <button class="auth-more" type="button">{{ t('auth.viewMoreOptions') }}</button>

        <div class="auth-region">
          <span class="auth-region__label">{{ localeName }}</span>
          <label class="visually-hidden" for="auth-region-select">{{ t('auth.region') }}</label>
          <select
            id="auth-region-select"
            class="auth-region__select"
            :value="localeCode"
            @change="setMarketLocale($event.target.value)"
          >
            <option v-for="option in availableLocales" :key="option.code" :value="option.code">
              {{ option.name }}
            </option>
          </select>
          <svg
            class="auth-region__chevron"
            viewBox="0 0 12 12"
            width="12"
            height="12"
            aria-hidden="true"
          >
            <path
              d="M2.5 4.5 6 8l3.5-3.5"
              fill="none"
              stroke="currentColor"
              stroke-width="1.2"
              stroke-linecap="round"
            />
          </svg>
        </div>
      </template>

      <!-- 第二屏：已有账号 → 密码 -->
      <form
        v-if="step === 'password'"
        class="auth-form"
        novalidate
        @submit.prevent="submitPassword"
      >
        <div class="auth-field">
          <label class="auth-field__label" for="auth-locked-identifier">
            {{ t('auth.identifierLabel') }}
          </label>
          <div class="auth-field__box auth-field__box--filled auth-field__box--locked">
            <input
              id="auth-locked-identifier"
              :value="identifier"
              type="text"
              readonly
              aria-readonly="true"
            />
            <button
              class="auth-field__edit"
              type="button"
              :aria-label="t('auth.changeIdentifier')"
              @click="changeIdentifier"
            >
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                <path
                  d="M4 20h4.2L19 9.2a2.1 2.1 0 0 0 0-3l-1.2-1.2a2.1 2.1 0 0 0-3 0L4 15.8V20Z"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.4"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>
        </div>

        <div class="auth-field">
          <label class="auth-field__label" for="auth-password">
            {{ t('auth.passwordLabel') }}
          </label>
          <div class="auth-field__box auth-field__box--outline">
            <input
              id="auth-password"
              v-model="password"
              type="password"
              name="password"
              autocomplete="current-password"
            />
          </div>
          <p v-if="passwordError" class="auth-field__error" role="alert">{{ passwordError }}</p>
        </div>

        <p v-if="formError" class="auth-form-error" role="alert">{{ formError }}</p>

        <button class="auth-submit" type="submit" :disabled="submitting">
          {{ submitting ? t('auth.submitting') : t('auth.submitSignIn') }}
        </button>
      </form>

      <!-- 第三屏：新账号 → 创建账户 -->
      <form
        v-if="step === 'register'"
        class="auth-form"
        novalidate
        @submit.prevent="submitRegister"
      >
        <div class="auth-field">
          <label class="auth-field__label" for="auth-register-email">
            {{ t('auth.emailLabel') }}
          </label>
          <div
            class="auth-field__box auth-field__box--filled"
            :class="{ 'auth-field__box--locked': emailLocked }"
          >
            <input
              id="auth-register-email"
              v-model="identifier"
              type="email"
              name="email"
              autocomplete="email"
              :readonly="emailLocked"
              :aria-readonly="emailLocked ? 'true' : 'false'"
            />
            <button
              v-if="emailLocked"
              class="auth-field__edit"
              type="button"
              :aria-label="t('auth.changeIdentifier')"
              @click="changeIdentifier"
            >
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                <path
                  d="M4 20h4.2L19 9.2a2.1 2.1 0 0 0 0-3l-1.2-1.2a2.1 2.1 0 0 0-3 0L4 15.8V20Z"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.4"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>
          <p v-if="identifierError" class="auth-field__error" role="alert">
            {{ identifierError }}
          </p>
        </div>

        <div class="auth-field">
          <label class="auth-field__label" for="auth-register-password">
            {{ t('auth.passwordCreateLabel') }}
          </label>
          <div class="auth-field__box auth-field__box--outline">
            <input
              id="auth-register-password"
              v-model="password"
              type="password"
              name="password"
              autocomplete="new-password"
            />
          </div>
          <p v-if="passwordError" class="auth-field__error" role="alert">{{ passwordError }}</p>
        </div>

        <p v-if="formError" class="auth-form-error" role="alert">{{ formError }}</p>

        <button class="auth-submit" type="submit" :disabled="submitting">
          {{ submitting ? t('auth.submitting') : t('auth.submitCreateAccount') }}
        </button>
      </form>

      <button class="auth-feedback" type="button">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            d="M12 3.6c-4.7 0-8.5 3.2-8.5 7.1 0 2.2 1.2 4.2 3.1 5.5v3.2l2.9-1.7c.8.2 1.6.3 2.5.3 4.7 0 8.5-3.2 8.5-7.3s-3.8-7.1-8.5-7.1Z"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linejoin="round"
          />
          <path d="M12 7.4v3.6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          <circle cx="12" cy="13.6" r="0.85" fill="currentColor" />
        </svg>
        <span>{{ t('auth.feedback') }}</span>
      </button>

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
/* 实测值（var/auth_page_20261124/login_probe.json + login_step2_probe.json）：
   内容列 380；主按钮 380×48 #1A1A1A 18/600；三方按钮 380×48 白底 1px #1A1A1A 16/400、间距 12；
   输入容器 380×48 灰底 #F5F6FA，input 356×48 padding 16.5px 14px；密码框白底 1px #BBBFC4。 */
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

.auth-promo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  /* 真站这行比表单列宽（约 640px）且单行显示；两侧用负边距越出 380 列。 */
  margin: 18px -130px 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  text-align: center;
}

@media (max-width: 720px) {
  .auth-promo {
    margin-inline: 0;
    flex-wrap: wrap;
    font-size: 15px;
  }
}

.auth-promo__amount {
  color: #e1251b;
}

.auth-promo__info {
  flex: none;
  color: #6e7078;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 24px;
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

.auth-field__box--locked input {
  color: rgba(0, 0, 0, 0.38);
}

.auth-field__box input::placeholder {
  color: #9aa0aa;
}

.auth-field__edit {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 0;
  background: transparent;
  color: rgba(0, 0, 0, 0.54);
  cursor: pointer;
}

.auth-field__error {
  margin: 6px 0 0;
  color: #e1251b;
  font-size: 13px;
  line-height: 18px;
}

.auth-form-error {
  margin: 0;
  color: #e1251b;
  font-size: 13px;
  line-height: 18px;
}

.auth-submit {
  width: 100%;
  height: 48px;
  border: 0;
  border-radius: 4px;
  background: #1a1a1a;
  color: #fff;
  font: inherit;
  font-size: 18px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.auth-submit:disabled {
  background: #c2c4cc;
  cursor: default;
}

.auth-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 20px 0;
  color: #6e7078;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.auth-divider::before,
.auth-divider::after {
  content: '';
  width: 24px;
  height: 1px;
  background: #e5e7eb;
}

.auth-social {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.auth-social__button {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 48px;
  border: 1px solid #1a1a1a;
  border-radius: 4px;
  background: #fff;
  color: #1a1a1a;
  font-size: 16px;
  line-height: 23px;
  text-decoration: none;
}

.auth-social__icon {
  position: absolute;
  left: 14px;
  display: flex;
}

.auth-social__label {
  padding: 0 44px;
  text-align: center;
}

.auth-more {
  display: block;
  margin: 16px auto 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: #6e7078;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  line-height: 32px;
  cursor: pointer;
}

.auth-region {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 48px;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
}

.auth-region__select {
  /* 透明的原生 select 盖住整块：可见文案是语言名，点开可切换 */
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  background: transparent;
  opacity: 0;
  cursor: pointer;
  appearance: none;
}

.auth-region__label {
  padding-right: 16px;
}

.auth-region__chevron {
  flex: none;
  pointer-events: none;
  color: #1a1a1a;
}

.auth-feedback {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 24px auto 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  line-height: 36px;
  cursor: pointer;
}

.auth-agreement {
  margin: 24px 0 0;
  color: #6e7078;
  font-size: 12px;
  line-height: 24px;
  text-align: center;
}

.auth-agreement__link {
  font-weight: 500;
  text-decoration: underline;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
