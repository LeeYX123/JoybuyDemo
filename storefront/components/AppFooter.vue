<script setup>
import { computed } from 'vue'
import { useRoute } from '#imports'
import { useLocale } from '../composables/useLocale'

const { t } = useLocale()

// Static footer structure for WP-20; link groups become data-driven later.
// On the checkout page the footer collapses to the docs/12 §8 minimal
// variant: brand slogan + supported payment methods only (requirement 8-8).
const route = useRoute()
const simplified = computed(() => route.path === '/checkout')

const columns = computed(() => [
  {
    title: t('footer.colCustomerService'),
    links: [t('footer.helpCentre'), t('footer.shipping'), t('footer.returns'), t('footer.contact')],
  },
  {
    title: t('footer.colAbout'),
    links: [t('footer.aboutUs'), t('footer.careers'), t('footer.joyplus'), t('footer.appDownload')],
  },
  {
    title: t('footer.colPolicies'),
    links: [
      t('footer.paymentMethods'),
      t('footer.pricePromise'),
      t('footer.privacy'),
      t('footer.terms'),
    ],
  },
])

const paymentBrands = ['Visa', 'Mastercard', 'Google Pay', 'Klarna']
</script>

<template>
  <footer class="site-footer" :class="{ 'site-footer--simplified': simplified }">
    <div v-if="simplified" class="site-footer__inner site-footer__slogan-row">
      <p class="site-footer__slogan"><strong>Joybuy</strong> | {{ t('footer.tagline') }}</p>
      <p class="site-footer__support">
        {{ t('footer.weSupport') }}
        <span v-for="brand in paymentBrands" :key="brand" class="site-footer__brand">{{
          brand
        }}</span>
      </p>
    </div>
    <div v-else class="site-footer__inner">
      <div class="site-footer__columns">
        <section v-for="column in columns" :key="column.title" class="footer-column">
          <h2 class="footer-column__title">{{ column.title }}</h2>
          <ul class="footer-column__list">
            <li v-for="link in column.links" :key="link">
              <a class="footer-column__link" href="#">{{ link }}</a>
            </li>
          </ul>
        </section>
      </div>

      <div class="site-footer__legal">
        <p>
          {{ t('footer.disclaimer') }}
        </p>
        <p>{{ t('footer.copyright') }}</p>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.site-footer {
  margin-top: auto;
  border-top: 1px solid var(--colour-border);
  background: var(--colour-surface);
}

/* Simplified checkout footer: slogan + payment brands only (docs/12 §8-8). */
.site-footer--simplified .site-footer__inner {
  padding-block: var(--space-6);
}

.site-footer__slogan-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.site-footer__slogan {
  margin: 0;
  font-size: var(--font-size-lg);
}

.site-footer__slogan strong {
  color: var(--colour-accent);
}

.site-footer__support {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.site-footer__brand {
  padding: 2px var(--space-2);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  background: var(--colour-surface-soft);
  color: var(--colour-text);
}

.site-footer__inner {
  max-width: var(--container-max);
  margin-inline: auto;
  padding: var(--space-10) var(--container-pad) var(--space-8);
}

.site-footer__columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-8);
}

.footer-column__title {
  margin-bottom: var(--space-3);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}

.footer-column__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.footer-column__link {
  display: inline-block;
  min-height: 44px;
  padding-block: var(--space-1);
  color: var(--colour-muted);
  text-decoration: none;
  font-size: var(--font-size-sm);
}

.footer-column__link:hover {
  color: var(--colour-accent);
  text-decoration: underline;
}

.site-footer__legal {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-6);
  justify-content: space-between;
  margin-top: var(--space-10);
  padding-top: var(--space-4);
  border-top: 1px solid var(--colour-border);
  color: var(--colour-muted);
  font-size: var(--font-size-xs);
}

/* 390/375: columns stack vertically. */
@media (max-width: 30rem) {
  .site-footer__columns {
    grid-template-columns: 1fr;
    gap: var(--space-6);
  }

  .site-footer__inner {
    padding-block: var(--space-8) var(--space-6);
  }
}
</style>
