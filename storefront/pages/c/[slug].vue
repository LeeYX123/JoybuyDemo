<script setup>
// /c/[slug]: category listing with filters, sorting and pagination.
const route = useRoute()

const slug = computed(() => String(route.params.slug || ''))

// ADR 0001: the m. host renders the mobile listing (docs/20 §1); the
// desktop template below is untouched.
const { isMobileHost } = useMobileView()

useHead(() => ({ title: `Category: ${slug.value}` }))
</script>

<template>
  <MobileListing v-if="isMobileHost" mode="category" :slug="slug" />
  <ProductListing v-else mode="category" :slug="slug" />
</template>
