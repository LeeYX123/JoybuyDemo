<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">Skip to main content</a>
    <AppHeader />
    <main id="main-content" class="app-main" tabindex="-1">
      <slot />
    </main>
    <AppFooter />
    <UiToast />
    <!-- 需求 21：全站右下角【客服】入口（Crisp 原生挂件已由 plugins/crisp.client.js
         的开关默认关闭）。 -->
    <SupportChatLauncher />
  </div>
</template>
