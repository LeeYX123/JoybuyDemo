<script setup>
import { useHead } from '#imports'

import { useCart } from '~/composables/useCart'

// useCart is async (awaited useFetch); top-level await keeps SSR correct.

const { items, subtotal, needsAttention, formatMoney, updateItem, removeItem } = await useCart()

function onQuantityChange(item, event) {
  const quantity = Number.parseInt(event.target.value, 10)
  if (Number.isInteger(quantity) && quantity >= 1) {
    updateItem(item.public_id, quantity)
  }
}

useHead({ title: 'Cart' })
</script>

<template>
  <AppContainer>
    <section class="cart" aria-labelledby="cart-title">
      <h1 id="cart-title">Your cart</h1>

      <p v-if="items.length === 0" class="cart__empty" role="status">
        Your cart is empty. <NuxtLink to="/">Browse products</NuxtLink>
      </p>

      <template v-else>
        <p v-if="needsAttention" class="cart__warning" role="alert">
          Some items changed price or are no longer available. Review your cart before checkout.
        </p>

        <ul class="cart__list">
          <li
            v-for="item in items"
            :key="item.public_id"
            class="cart__row"
            :class="{ 'cart__row--invalid': !item.is_valid }"
          >
            <div class="cart__info">
              <NuxtLink class="cart__title" :to="`/p/${item.spu_public_id}`">
                {{ item.title }}
              </NuxtLink>
              <p class="cart__meta">
                {{ formatMoney(item.price) }} each · {{ item.inventory_display }} in stock
              </p>
              <p v-if="item.issue" class="cart__issue" role="status">
                {{ item.issue === 'SKU_NOT_AVAILABLE' ? 'No longer available' : 'Stock reduced' }}
              </p>
            </div>

            <label class="cart__qty">
              <span class="visually-hidden">Quantity</span>
              <input
                type="number"
                min="1"
                max="99"
                :value="item.quantity"
                :disabled="!item.is_valid"
                @change="onQuantityChange(item, $event)"
              />
            </label>

            <div class="cart__line">
              <span v-if="item.is_valid">
                {{ formatMoney(Number(item.price) * item.quantity) }}
              </span>
              <button type="button" class="cart__remove" @click="removeItem(item.public_id)">
                Remove
              </button>
            </div>
          </li>
        </ul>

        <div class="cart__summary">
          <p class="cart__subtotal">
            Subtotal <strong>{{ formatMoney(subtotal) ?? '—' }}</strong>
          </p>
          <p class="cart__note">
            Delivery is calculated at checkout. Payment is unavailable in this demo region.
          </p>
          <NuxtLink to="/checkout">
            <BaseButton variant="primary" size="lg">Go to checkout</BaseButton>
          </NuxtLink>
        </div>
      </template>
    </section>
  </AppContainer>
</template>

<style scoped>
.cart {
  margin-block: var(--space-8);
}

.cart__empty {
  margin-top: var(--space-5);
  color: var(--colour-muted);
}

.cart__warning {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--colour-warning-soft);
  color: var(--colour-warning);
  font-size: var(--font-size-sm);
}

.cart__list {
  margin-top: var(--space-5);
}

.cart__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  border-top: 1px solid var(--colour-border);
  padding-block: var(--space-4);
}

.cart__row--invalid {
  opacity: 0.6;
}

.cart__title {
  font-weight: var(--font-weight-semibold);
  color: var(--colour-text);
  text-decoration: none;
}

.cart__title:hover {
  color: var(--colour-accent);
}

.cart__meta {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.cart__issue {
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.cart__qty input {
  min-height: 44px;
  width: 4.5rem;
  padding: 0 var(--space-2);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
}

.cart__line {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  font-weight: var(--font-weight-semibold);
}

.cart__remove {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.cart__summary {
  margin-top: var(--space-6);
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-3);
}

.cart__subtotal {
  font-size: var(--font-size-lg);
}

.cart__note {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

@media (max-width: 30rem) {
  .cart__row {
    flex-wrap: wrap;
  }
}
</style>
