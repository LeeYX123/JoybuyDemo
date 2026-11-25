<script setup>
// Mobile category landing page (docs/19 §1.4): the drawer's 分类 row and the
// real m. site's category entry land here — 「为你推荐」 + 「全部分类」 2-col
// card grids (user-provided real-site screenshots, 2026-11-24). On the
// desktop host this route simply renders the same grid content; the desktop
// navigation has its own category panel, so nothing links here from there.
useHead(() => ({ title: 'Joybuy' }))
</script>

<template>
  <MobileCategories />
</template>
