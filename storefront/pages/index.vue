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
const mainModules = computed(() => modules.value)
const pageTitle = computed(() => data.value?.page?.title || 'Joybuy')

useHead(() => ({ title: pageTitle.value }))
</script>

<template>
  <!-- The whole home row is white (#FFFFFF) behind every floor, and the
       campaign floor sits flush against the header (real site: no gap), so
       this full-bleed wrapper carries the background and kills the top
       margin that .app-main applies to its children. -->
  <div class="home-page-bg">
    <AppContainer class="home-page">
      <div class="home-content">
        <template v-if="modules.length > 0">
          <CmsRenderer :modules="mainModules" />
          <!-- Bestsellers floor with category tabs (docs/12 §1). -->
          <HomeBestsellers class="home-bestsellers-floor" />
        </template>
        <section v-else-if="error" class="home-unavailable" role="status">
          <p>The home page is temporarily unavailable. Please try again shortly.</p>
        </section>
      </div>
    </AppContainer>
  </div>
</template>

<style scoped>
/* Full-bleed white row: escapes the centered container so the strips on
 * ultra-wide viewports are white too (scoped attr beats .app-main > *). */
.home-page-bg {
  margin-top: 0;
  margin-inline: calc(50% - 50vw);
  background: #ffffff;
}

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
