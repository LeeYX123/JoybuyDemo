<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from '#imports'

import { useLocale } from '../../composables/useLocale'

// Generic toggle-type settings page (user decision 2026-11-24): shows the
// module name, a short explanation and a switch — UI only, no logic behind
// it. Keys: account-security / notifications / personalisation / cookies.
const route = useRoute()
const router = useRouter()
const { t } = useLocale()

const MODULES = {
  'account-security': {
    titleKey: 'mobile.drawer.settings.accountSecurity',
    hintKey: 'mobile.settings.hint.accountSecurity',
  },
  notifications: {
    titleKey: 'mobile.drawer.settings.notifications',
    hintKey: 'mobile.settings.hint.notifications',
  },
  personalisation: {
    titleKey: 'mobile.drawer.settings.personalisation',
    hintKey: 'mobile.settings.hint.personalisation',
  },
  cookies: {
    titleKey: 'mobile.drawer.settings.cookies',
    hintKey: 'mobile.settings.hint.cookies',
  },
}

const meta = computed(() => MODULES[route.params.key] || null)
const enabled = ref(true)

function back() {
  router.back()
}
</script>

<template>
  <div v-if="meta" class="m-toggle">
    <MobilePageHeader :title="t(meta.titleKey)" @back="back" />
    <div class="m-toggle__body">
      <div class="m-toggle__card">
        <p class="m-toggle__hint">{{ t(meta.hintKey) }}</p>
        <button
          class="m-toggle__switch"
          :class="{ 'm-toggle__switch--on': enabled }"
          type="button"
          role="switch"
          :aria-checked="enabled"
          :aria-label="t(meta.titleKey)"
          @click="enabled = !enabled"
        >
          <span class="m-toggle__knob" aria-hidden="true"></span>
        </button>
      </div>
      <p class="m-toggle__note">{{ t('mobile.settings.uiOnlyNote') }}</p>
    </div>
  </div>
  <div v-else class="m-toggle m-toggle--empty">
    <p>{{ t('mobile.settings.unknown') }}</p>
  </div>
</template>

<style scoped>
.m-toggle__body {
  min-height: 100%;
  padding: 16px;
  background: #f5f6fa;
}

.m-toggle__card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-toggle__hint {
  flex: 1;
  margin: 0;
  color: #1a1a1a;
  font-size: 15px;
  line-height: 1.5;
}

.m-toggle__switch {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  width: 44px;
  height: 26px;
  padding: 2px;
  border: 0;
  border-radius: 13px;
  background: #c7c9cf;
  cursor: pointer;
  transition: background 0.2s ease;
}

.m-toggle__switch--on {
  background: #1a1a1a;
}

.m-toggle__knob {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #ffffff;
  transition: transform 0.2s ease;
}

.m-toggle__switch--on .m-toggle__knob {
  transform: translateX(18px);
}

.m-toggle__note {
  margin: 12px 4px 0;
  color: #9a9ca3;
  font-size: 12px;
}

.m-toggle--empty {
  padding: 32px 16px;
  background: #f5f6fa;
  color: #7a7d85;
}
</style>
