<script setup>
// /s: the listing template behind category discovery (docs/12 §4).
// ?k= searches by keyword; ?category=<slug> lists a standard category.
const route = useRoute()

const categorySlug = computed(() => String(route.query.category || ''))
const keyword = computed(() => String(route.query.k || route.query.q || ''))

// ADR 0001: the m. host renders the mobile listing (docs/20 §1); the
// desktop template below is untouched.
const { isMobileHost } = useMobileView()

useHead(() => ({
  title: categorySlug.value
    ? `Category: ${categorySlug.value}`
    : keyword.value
      ? `Search: ${keyword.value}`
      : 'Browse products',
}))
</script>

<template>
  <MobileListing
    v-if="isMobileHost"
    :mode="categorySlug ? 'category' : 'search'"
    :slug="categorySlug"
  />
  <ProductListing v-else :mode="categorySlug ? 'category' : 'search'" :slug="categorySlug" />
</template>
