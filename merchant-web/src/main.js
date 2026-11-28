import { createApp } from 'vue'

import App from './App.vue'
import router from './router/index.js'
import './styles/main.css'
import './styles/merchant.css'

// ---------------------------------------------------------------------------
// 桌面 → 手机版切换协议：手机版是与本 Vue 文档相互独立的 mobile.html 文档。
// - m. 主机：永远手机版（由 mobile.html 侧保证，这里只在误入时送走）；
// - 其他主机：视口 <760 进手机版；回桌面由 mobile.html 在 >780 时换回本文档
//   （滞回 20px，防止边界宽度来回抖动；切换=换文档，接受一次跳转）。
// ---------------------------------------------------------------------------
function goToMobile() {
  location.replace('/mobile.html?p=' + encodeURIComponent(location.pathname + location.search))
}

if (window.location.hostname.startsWith('m.') || window.innerWidth < 760) {
  goToMobile()
} else {
  let resizeTimer = null
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      if (!window.location.hostname.startsWith('m.') && window.innerWidth < 760) {
        goToMobile()
      }
    }, 250)
  })

  createApp(App).use(router).mount('#app')
}
