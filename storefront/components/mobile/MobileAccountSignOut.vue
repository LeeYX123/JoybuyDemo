<script setup>
import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useUiToast } from '../../composables/useUiToast'

// Real sign-out block shared by the account pages (设置&隐私 bottom band).
const { isAuthenticated, logout } = useBuyerAuth()
const { t } = useLocale()
const { show } = useUiToast()

async function onSignOut() {
  try {
    await logout()
  } catch {
    show(t('auth.error.generic'), { type: 'error' })
  }
}
</script>

<template>
  <div v-if="isAuthenticated" class="m-signout">
    <button class="m-signout__btn" type="button" @click="onSignOut">
      {{ t('mobile.drawer.settings.signOut') }}
    </button>
  </div>
</template>

<style scoped>
.m-signout {
  margin-top: 16px;
}

.m-signout__btn {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 56px;
  padding: 0 16px;
  border: 0;
  background: #ffffff;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  text-align: left;
  cursor: pointer;
}
</style>
