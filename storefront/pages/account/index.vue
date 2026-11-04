<script setup>
import { useHead } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'

// Account hub: session state, sign-out, and entry points. Favourites and
// recently-viewed land with their own work package.
const { isAuthenticated, account, logout } = useBuyerAuth()

async function signOut() {
  await logout()
  navigateTo('/')
}

useHead({ title: 'Your account' })
</script>

<template>
  <AppContainer narrow>
    <section v-if="isAuthenticated" class="account" aria-labelledby="account-title">
      <h1 id="account-title">Your account</h1>
      <p class="account__welcome">
        Signed in as
        <strong>{{
          account?.display_identifier || account?.email || account?.phone_number
        }}</strong>
      </p>

      <ul class="account__links">
        <li><NuxtLink to="/account/favourites">Favourites</NuxtLink></li>
        <li><NuxtLink to="/account/recently-viewed">Recently viewed</NuxtLink></li>
        <li><NuxtLink to="/cart">Cart</NuxtLink></li>
        <li><NuxtLink to="/account/notifications">Notifications</NuxtLink></li>
        <li><NuxtLink to="/account/orders">Orders</NuxtLink></li>
      </ul>

      <BaseButton variant="secondary" @click="signOut">Sign out</BaseButton>
    </section>

    <section v-else class="account account--signed-out" aria-labelledby="account-title">
      <h1 id="account-title">Your account</h1>
      <p>Sign in to see your favourites, orders and notifications.</p>
      <div class="account__actions row">
        <NuxtLink to="/auth/login"><BaseButton variant="primary">Sign in</BaseButton></NuxtLink>
        <NuxtLink to="/auth/register">
          <BaseButton variant="secondary">Create account</BaseButton>
        </NuxtLink>
      </div>
    </section>
  </AppContainer>
</template>

<style scoped>
.account {
  max-width: 30rem;
  margin-inline: auto;
  margin-block: var(--space-10);
  padding: var(--space-8);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.account__welcome {
  margin-top: var(--space-2);
  color: var(--colour-text-secondary);
}

.account__links {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-block: var(--space-6);
}

.account__links a {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  color: var(--colour-text);
  text-decoration: none;
  font-weight: var(--font-weight-semibold);
}

.account__links a:hover {
  background: var(--colour-surface-muted);
  color: var(--colour-accent);
}

.account--signed-out p {
  margin-block: var(--space-3) var(--space-5);
  color: var(--colour-text-secondary);
}

.account__actions :deep(a) {
  text-decoration: none;
}
</style>
