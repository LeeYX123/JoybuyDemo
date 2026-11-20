<script setup>
import { useLocale } from '../../composables/useLocale'

const { t } = useLocale()

useHead({ title: () => t('auth.titleRegister') })
</script>

<template>
  <AuthForm mode="register" />
</template>
