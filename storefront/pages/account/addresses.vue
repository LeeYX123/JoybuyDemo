<script setup>
import { useHead } from '#imports'
import { useRequestHeaders } from '#imports'

import { useLocale } from '../../composables/useLocale'

// Buyer saved addresses (account menu entry, docs/12 global header).
// Read-only list here; editing lives in the checkout address step.
const config = useRuntimeConfig()
const { t } = useLocale()

const { data } = await useFetch(
  () => (import.meta.server ? `${config.apiBaseInternal}/addresses` : '/api/v1/addresses'),
  {
    key: 'account-addresses',
    headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
  },
)

const addresses = computed(() => (Array.isArray(data.value?.addresses) ? data.value.addresses : []))

useHead(() => ({ title: t('addresses.title') }))
</script>

<template>
  <AppContainer narrow>
    <section class="addresses" aria-labelledby="addresses-title">
      <h1 id="addresses-title">{{ t('addresses.title') }}</h1>

      <p v-if="addresses.length === 0" class="addresses__empty" role="status">
        {{ t('addresses.empty') }}
      </p>

      <ul v-else class="addresses__list">
        <li v-for="address in addresses" :key="address.public_id" class="addresses__row">
          <p class="addresses__name">
            {{ address.full_name }}
            <span v-if="address.is_default" class="addresses__default">Default</span>
          </p>
          <p class="addresses__detail">
            {{
              [address.line1, address.line2, address.city, address.county, address.postcode]
                .filter(Boolean)
                .join(', ')
            }}
          </p>
          <p class="addresses__detail">{{ address.phone }}</p>
        </li>
      </ul>
    </section>
  </AppContainer>
</template>

<style scoped>
.addresses {
  margin-block: var(--space-10);
}

.addresses__empty {
  margin-top: var(--space-5);
  color: var(--colour-muted);
}

.addresses__list {
  display: flex;
  flex-direction: column;
  margin-top: var(--space-5);
}

.addresses__row {
  padding-block: var(--space-3);
  border-top: 1px solid var(--colour-border);
}

.addresses__name {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  font-weight: var(--font-weight-semibold);
}

.addresses__default {
  padding: 0 var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--colour-surface-muted);
  color: var(--colour-text-secondary);
  font-size: var(--font-size-xs);
}

.addresses__detail {
  margin: var(--space-1) 0 0;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}
</style>
