<script setup>
import { useAsyncData } from '#imports'
import { useLocale } from '../../composables/useLocale'
import { useBuyerAuth } from '../../composables/useBuyerAuth'

const { t } = useLocale()
const { oauthProviders, loadOAuthProviders } = useBuyerAuth()

// 三方登录渠道在 SSR 阶段取回：不 await 的话按钮会在水合后才出现（hydration mismatch）。
await useAsyncData('auth-oauth-providers', () =>
  oauthProviders.value.length ? Promise.resolve(oauthProviders.value) : loadOAuthProviders(),
)

useHead({ title: () => t('auth.titleRegister') })
</script>

<template>
  <AuthForm mode="register" :providers="oauthProviders" />
</template>
