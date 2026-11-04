<script setup>
// /s: the listing template behind category discovery (docs/12 §4).
// ?k= searches by keyword; ?category=<slug> lists a standard category.
const route = useRoute()

const categorySlug = computed(() => String(route.query.category || ''))
const keyword = computed(() => String(route.query.k || route.query.q || ''))

useHead(() => ({
  title: categorySlug.value
    ? `Category: ${categorySlug.value}`
    : keyword.value
      ? `Search: ${keyword.value}`
      : 'Browse products',
}))
</script>

<template>
  <ProductListing :mode="categorySlug ? 'category' : 'search'" :slug="categorySlug" />
</template>
