<script setup>
// /search: full-text search with the shared listing UI.
const route = useRoute()

const q = computed(() => String(route.query.q || ''))

useHead(() => ({ title: q.value ? `Search: ${q.value}` : 'Browse products' }))
</script>

<template>
  <ProductListing mode="search" />
</template>
