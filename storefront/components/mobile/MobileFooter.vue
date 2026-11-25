<script setup>
import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

// Minimal mobile footer (docs/19 §2.10): the real m. site ships only a
// Trustpilot badge row; we add the desktop/mobile manual switch (ADR 0001)
// and the reused policy links.
const { t } = useLocale()
const { switchView } = useMobileView()

const policyLinks = [
  { label: () => t('footer.linkTerms'), to: '/pages/terms-conditions' },
  { label: () => t('footer.linkPrivacy'), to: '/pages/privacy-policy' },
  { label: () => t('footer.linkCookiePolicy'), to: '/pages/cookie-policy' },
  { label: () => t('footer.linkAccessibility'), to: '/pages/accessibility-statement' },
]
</script>

<template>
  <footer class="m-footer">
    <button class="m-footer__switch" type="button" @click="switchView('desktop')">
      {{ t('mobile.footer.switchDesktop') }}
    </button>
    <nav class="m-footer__links" :aria-label="t('footer.colPolicies')">
      <NuxtLink v-for="link in policyLinks" :key="link.to" class="m-footer__link" :to="link.to">
        {{ link.label() }}
      </NuxtLink>
    </nav>
    <p class="m-footer__copyright">{{ t('footer.copyright') }}</p>
  </footer>
</template>

<style scoped>
.m-footer {
  padding: 24px 16px 32px;
  background: #f5f6fa;
  text-align: center;
}

.m-footer__switch {
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 16px;
  border: 1px solid #e0e1e5;
  border-radius: 18px;
  background: #ffffff;
  color: #1a1a1a;
  font-size: 14px;
  cursor: pointer;
}

.m-footer__links {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px 16px;
  margin-top: 16px;
}

.m-footer__link {
  color: #55565b;
  font-size: 13px;
}

.m-footer__link:hover {
  color: var(--colour-accent, #e1251b);
}

.m-footer__copyright {
  margin: 16px 0 0;
  color: #9a9ca3;
  font-size: 12px;
}
</style>
