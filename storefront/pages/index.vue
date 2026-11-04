<script setup>
import { computed } from 'vue'

// Home = published CMS page. SSR fetches Django directly via the internal
// base; the client re-fetches through the same-origin proxy. A missing page
// degrades to a friendly empty state instead of an error screen.
const config = useRuntimeConfig()
const apiBase = import.meta.server ? config.apiBaseInternal : config.public.apiBase

const { data, error } = await useFetch(`${apiBase}/storefront/home`, {
  key: 'cms-home',
})

const modules = computed(() => (Array.isArray(data.value?.modules) ? data.value.modules : []))
const pageTitle = computed(() => data.value?.page?.title || 'Joybuy')

useHead(() => ({ title: pageTitle.value }))
</script>

<template>
  <!-- The campaign floor must sit flush against the header (real site: no
       gap), so the page container itself carries no top margin here. -->
  <AppContainer class="home-page">
    <div class="home-content">
      <CmsRenderer v-if="modules.length > 0" :modules="modules" />
      <section v-else-if="error" class="home-unavailable" role="status">
        <p>The home page is temporarily unavailable. Please try again shortly.</p>
      </section>
    </div>
  </AppContainer>
</template>

<style scoped>
/* Override the global .app-main > * top margin so the full-bleed campaign
 * floor touches the header shadow (scoped attr raises specificity). */
.home-page {
  margin-top: 0;
}

.home-content {
  margin-block: 0 24px;
}

.home-unavailable {
  margin-block: var(--space-10);
  padding: var(--space-8);
  border: 1px dashed var(--colour-border-strong);
  border-radius: var(--radius-lg);
  color: var(--colour-muted);
  text-align: center;
}
</style>
