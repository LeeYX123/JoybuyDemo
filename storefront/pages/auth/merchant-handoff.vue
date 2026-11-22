<script setup>
import { onMounted, ref } from 'vue'
import { NuxtLink } from '#components'
import { navigateTo, useHead, useRoute } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useUiToast } from '../../composables/useUiToast'

// 商家端「切换去商城」的购物端落地页（2026-11-22）。
//
// 商家端是 m.localhost:5174 / localhost:5174，购物端是 localhost:3000；
// 从商家端写 Domain=.localhost 的 cookie 会被 Chromium 拒绝（localhost 是
// public-suffix 特例），所以后端只发 60 秒一次性 handoff token，由本页在
// 购物端自己的 host 上兑换并种 host-only session cookie。
//
// 本页是登录入口，不能加登录守卫。所有兑换动作都在客户端 onMounted 里做：
// SSR 阶段没有 token 兑换所需的 CSRF cookie。
const route = useRoute()
const { t } = useLocale()
const { exchangeMerchantHandoff } = useBuyerAuth()
const { show } = useUiToast()

const processing = ref(true)
const errorMessage = ref('')

useHead({ title: () => t('auth.handoff.title') })

onMounted(async () => {
  const raw = route.query.token
  const token = typeof raw === 'string' ? raw : ''

  if (!token) {
    processing.value = false
    errorMessage.value = t('auth.handoff.invalid')
    return
  }

  try {
    const response = await exchangeMerchantHandoff(token)
    if (response?.error) {
      processing.value = false
      errorMessage.value =
        response.error.code === 'HANDOFF_TOKEN_INVALID'
          ? t('auth.handoff.invalid')
          : response.error.message || t('auth.handoff.generic')
      return
    }
    processing.value = false
    show(t('auth.handoff.success'))
    await navigateTo('/account')
  } catch {
    processing.value = false
    errorMessage.value = t('auth.handoff.generic')
  }
})
</script>

<template>
  <div class="merchant-handoff">
    <div class="merchant-handoff__panel">
      <template v-if="processing">
        <p class="merchant-handoff__status" data-testid="merchant-handoff-processing" role="status">
          {{ t('auth.handoff.processing') }}
        </p>
      </template>
      <template v-else-if="errorMessage">
        <h1 class="merchant-handoff__title">{{ t('auth.handoff.title') }}</h1>
        <p class="merchant-handoff__error" data-testid="merchant-handoff-error" role="alert">
          {{ errorMessage }}
        </p>
        <NuxtLink class="merchant-handoff__action" to="/auth/login">
          {{ t('auth.handoff.backToLogin') }}
        </NuxtLink>
      </template>
    </div>
  </div>
</template>

<style scoped>
.merchant-handoff {
  display: flex;
  justify-content: center;
  padding-block: var(--space-16, 4rem) var(--space-10, 2.5rem);
}

.merchant-handoff__panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
  max-width: 23.75rem;
  padding: var(--space-8, 2rem) var(--space-6, 1.5rem);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
  text-align: center;
}

.merchant-handoff__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--colour-text);
}

.merchant-handoff__status {
  margin: 0;
  color: var(--colour-text-secondary);
  font-size: var(--font-size-md);
}

.merchant-handoff__error {
  margin: 0;
  color: var(--colour-error);
  font-size: var(--font-size-md);
  line-height: 1.5;
}

.merchant-handoff__action {
  align-self: center;
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-5, 1.25rem);
  border-radius: var(--radius-md, 0.5rem);
  background: var(--colour-text);
  color: var(--colour-white);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  line-height: 1.75rem;
  text-decoration: none;
}

.merchant-handoff__action:hover,
.merchant-handoff__action:focus-visible {
  background: var(--colour-accent-dark);
}
</style>
