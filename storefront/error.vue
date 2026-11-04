<script setup>
const props = defineProps({
  error: {
    type: Object,
    required: true,
  },
})

const statusCode = computed(() => props.error.statusCode || 500)
const title = computed(() => (statusCode.value === 404 ? 'Page not found' : 'Something went wrong'))
const description = computed(() =>
  statusCode.value === 404
    ? 'The page you requested does not exist or has moved.'
    : 'The storefront could not complete this request. Please try again.',
)

const returnHome = () => clearError({ redirect: '/' })
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#error-content">Skip to error details</a>
    <AppHeader />
    <main id="error-content" class="app-main" tabindex="-1">
      <AppContainer narrow>
        <section class="error-panel" aria-labelledby="error-title">
          <BaseBadge tone="error">Error {{ statusCode }}</BaseBadge>
          <h1 id="error-title">{{ title }}</h1>
          <p class="error-panel__description">{{ description }}</p>
          <div class="error-panel__actions">
            <BaseButton variant="primary" @click="returnHome">Return home</BaseButton>
            <BaseButton variant="secondary" @click="reloadNuxtApp()">Try again</BaseButton>
          </div>
        </section>
      </AppContainer>
    </main>
    <AppFooter />
  </div>
</template>

<style scoped>
.error-panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
  margin-block: var(--space-12);
  padding: var(--space-8);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
  box-shadow: var(--shadow-card);
}

.error-panel__description {
  color: var(--colour-text-secondary);
}

.error-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}
</style>
