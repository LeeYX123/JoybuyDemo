<script setup>
// Toggle-type settings modules (account-security / notifications /
// personalisation / cookies, each a UI-only switch) and the 法律信息 links
// page under one dynamic route. Mobile-only surface.
useHead(() => ({ title: 'Joybuy' }))
</script>

<template>
  <MobileLegalLinks v-if="$route.params.key === 'legal'" />
  <MobileSettingToggle v-else />
</template>
