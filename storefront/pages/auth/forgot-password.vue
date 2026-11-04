<script setup>
// Password reset needs a backend endpoint that arrives with the
// notifications work package; until then the page is an honest placeholder.
useHead({ title: 'Forgot password' })
</script>

<template>
  <AppContainer narrow>
    <section class="forgot" aria-labelledby="forgot-title">
      <h1 id="forgot-title">Password reset</h1>
      <p>
        Password reset by email is not available in this demo build yet. If you cannot sign in,
        contact customer support for assistance.
      </p>
      <NuxtLink to="/auth/login">Back to sign in</NuxtLink>
    </section>
  </AppContainer>
</template>

<style scoped>
.forgot {
  max-width: 26rem;
  margin-inline: auto;
  margin-block: var(--space-10);
  padding: var(--space-8);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.forgot p {
  margin-block: var(--space-3) var(--space-5);
  color: var(--colour-text-secondary);
}

.forgot a {
  color: var(--colour-accent);
  font-weight: var(--font-weight-semibold);
}
</style>
