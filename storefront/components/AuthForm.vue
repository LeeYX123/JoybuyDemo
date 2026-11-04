<script setup>
import { computed, ref, watch } from 'vue'
import { navigateTo, useHead } from '#imports'

import { useBuyerAuth } from '../composables/useBuyerAuth'

// Unified auth form: login mode uses identifier+password; register mode
// adds the 6-digit verification code (dev responses include test_code so
// the flow is demoable; production sends real email/SMS).
const props = defineProps({
  mode: {
    type: String,
    required: true,
    validator: (value) => ['login', 'register'].includes(value),
  },
})

const { login, register, sendVerificationCode, isAuthenticated } = useBuyerAuth()

const identifier = ref('')
const password = ref('')
const code = ref('')
const channel = ref('EMAIL')
const codeSent = ref(false)
const devCode = ref('')
const submitting = ref(false)
const formError = ref('')
const notice = ref('')

const isRegister = computed(() => props.mode === 'register')
const identifierType = computed(() => {
  const value = identifier.value.trim()
  if (/^\+?\d[\d\s-]{6,}$/.test(value)) return 'phone'
  return 'email'
})
const identifierPlaceholder = computed(() =>
  isRegister.value
    ? channel.value === 'EMAIL'
      ? 'you@example.com'
      : '+44 7000 000000'
    : 'Email or phone number',
)

watch(isAuthenticated, (authed) => {
  if (authed) navigateTo('/account')
})
if (isAuthenticated.value) {
  navigateTo('/account')
}

function fieldErrors(payload) {
  if (!payload) return {}
  const raw = payload.error?.details || payload.details
  if (raw && typeof raw === 'object') {
    return Object.fromEntries(
      Object.entries(raw).map(([key, value]) => [key, Array.isArray(value) ? value[0] : value]),
    )
  }
  return {}
}

async function submit() {
  submitting.value = true
  formError.value = ''
  try {
    if (isRegister.value) {
      const response = await register({
        channel: channel.value,
        target: identifier.value.trim(),
        purpose: 'REGISTER',
        verification_code: code.value.trim(),
        password: password.value,
      })
      if (response?.error) {
        const errors = fieldErrors(response)
        formError.value =
          Object.values(errors)[0] || response.error?.message || 'Registration failed.'
        return
      }
      navigateTo('/account')
    } else {
      const response = await login({
        identifier: identifier.value.trim(),
        password: password.value,
      })
      if (response?.error) {
        const errors = fieldErrors(response)
        formError.value = Object.values(errors)[0] || response.error?.message || 'Sign in failed.'
        return
      }
      navigateTo('/account')
    }
  } finally {
    submitting.value = false
  }
}

async function request_code() {
  codeSent.value = false
  devCode.value = ''
  notice.value = ''
  formError.value = ''
  const response = await sendVerificationCode(channel.value, identifier.value.trim())
  if (response?.error) {
    const errors = fieldErrors(response)
    formError.value =
      Object.values(errors)[0] || response.error?.message || 'Could not send the code.'
    return
  }
  codeSent.value = true
  if (response?.test_code) {
    devCode.value = response.test_code
    notice.value = 'Development mode: the verification code is filled in automatically.'
    code.value = response.test_code
  } else {
    notice.value = 'Verification code sent. Check your inbox.'
  }
}

useHead(() => ({ title: isRegister.value ? 'Create account' : 'Sign in' }))
</script>

<template>
  <AppContainer narrow>
    <section class="auth-panel" aria-labelledby="auth-title">
      <h1 id="auth-title">{{ isRegister ? 'Create your Joybuy account' : 'Sign in' }}</h1>

      <form class="auth-form" novalidate @submit.prevent="submit">
        <div v-if="isRegister" class="auth-field">
          <label for="auth-channel">Verification channel</label>
          <select id="auth-channel" v-model="channel">
            <option value="EMAIL">Email</option>
            <option value="PHONE">Phone</option>
          </select>
        </div>

        <div class="auth-field">
          <label for="auth-identifier">{{
            isRegister
              ? channel === 'PHONE'
                ? 'Phone number'
                : 'Email address'
              : 'Email or phone number'
          }}</label>
          <input
            id="auth-identifier"
            v-model="identifier"
            :type="identifierType === 'phone' ? 'tel' : 'email'"
            autocomplete="username"
            :placeholder="identifierPlaceholder"
            required
          />
        </div>

        <div v-if="isRegister" class="auth-field auth-field--code">
          <label for="auth-code">Verification code</label>
          <div class="code-row">
            <input
              id="auth-code"
              v-model="code"
              inputmode="numeric"
              pattern="[0-9]*"
              maxlength="6"
              autocomplete="one-time-code"
              required
            />
            <BaseButton
              variant="secondary"
              type="button"
              :disabled="identifier.trim().length < 5"
              @click="request_code"
            >
              Send code
            </BaseButton>
          </div>
        </div>

        <div class="auth-field">
          <label for="auth-password">Password</label>
          <input
            id="auth-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
          />
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

.auth-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-6);
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

.auth-field input,
.auth-field select {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
}

.code-row {
  display: flex;
  gap: var(--space-2);
}

.code-row input {
  flex: 1;
  letter-spacing: 0.2em;
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
