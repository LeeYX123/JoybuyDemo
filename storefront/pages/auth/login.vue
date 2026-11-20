<script setup>
import { useLocale } from '../../composables/useLocale'

const { t } = useLocale()

useHead({ title: () => t('auth.titleLogin') })
</script>

<template>
  <AuthForm mode="login" />
</template>
