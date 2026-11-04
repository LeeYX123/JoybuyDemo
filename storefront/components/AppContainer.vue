<script setup>
// Responsive page container: capped at the 1440 design width, with
// breakpoint-driven horizontal padding from the token scale.
const props = defineProps({
  as: {
    type: String,
    default: 'div',
  },
  narrow: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <component :is="props.as" class="container" :class="{ 'container--narrow': props.narrow }">
    <slot />
  </component>
</template>

<style scoped>
.container {
  width: 100%;
  max-width: var(--container-max);
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

.container--narrow {
  max-width: 48rem;
}
</style>
