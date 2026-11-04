<script setup>
import { computed } from 'vue'
import { useRoute } from '#imports'

// Static footer structure for WP-20; link groups become data-driven later.
// On the checkout page the footer collapses to the docs/12 §8 minimal
// variant: brand slogan + supported payment methods only (requirement 8-8).
const route = useRoute()
const simplified = computed(() => route.path === '/checkout')

const columns = [
  {
    title: 'Customer service',
    links: ['Help centre', 'Shipping & delivery', 'Returns', 'Contact us'],
  },
  {
    title: 'About Joybuy',
    links: ['About us', 'Careers', 'JoyPlus membership', 'App download'],
  },
  {
    title: 'Payment & policies',
    links: ['Payment methods', 'Price promise', 'Privacy notice', 'Terms of use'],
  },
]

const paymentBrands = ['Visa', 'Mastercard', 'Google Pay', 'Klarna']
</script>

<template>
  <footer class="site-footer" :class="{ 'site-footer--simplified': simplified }">
    <div v-if="simplified" class="site-footer__inner site-footer__slogan-row">
      <p class="site-footer__slogan"><strong>Joybuy</strong> | Don't just buy, Joybuy</p>
      <p class="site-footer__support">
        We support
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
          Demo project for internal research. Not a real store: checkout and payment are disabled by
          design.
        </p>
        <p>© 2026 Joybuy replica study. All assets served locally.</p>
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
