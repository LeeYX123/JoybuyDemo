<script setup>
import { ref } from 'vue'

// ADR 0001: mobile shell for the m. host. Same pages as the desktop shell —
// only the chrome differs. The SupportChatLauncher doubles as the m. site's
// 40×40 floating feedback/support button (docs/19 §2.10).
const drawerOpen = ref(false)
</script>

<template>
  <div class="mobile-shell">
    <a class="skip-link" href="#main-content">Skip to main content</a>
    <MobileHeader @open-drawer="drawerOpen = true" />
    <main id="main-content" class="mobile-main" tabindex="-1">
      <slot />
    </main>
    <MobileFooter />
    <UiToast />
    <MobileDrawer :open="drawerOpen" @close="drawerOpen = false" />
    <SupportChatLauncher />
  </div>
</template>

<style scoped>
.mobile-shell {
  min-height: 100vh;
  background: #ffffff;
}

.mobile-main {
  min-height: 40vh;
}

/* Full-bleed rows inside the mobile shell (mirrors desktop .app-main rule,
 * which does not exist under the mobile layout). */
.mobile-main > * {
  margin-inline: calc(50% - 50vw);
}
</style>
