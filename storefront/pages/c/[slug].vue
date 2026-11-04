<script setup>
// /c/[slug]: category listing with filters, sorting and pagination.
const route = useRoute()

const slug = computed(() => String(route.params.slug || ''))

useHead(() => ({ title: `Category: ${slug.value}` }))
</script>

<template>
  <ProductListing mode="category" :slug="slug" />
</template>
