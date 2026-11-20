import { createApp } from 'vue'

import App from './App.vue'
import router from './router/index.js'
import './styles/main.css'
import './styles/merchant.css'
// 手机壳 tokens 与公共构件（m- 前缀，不影响桌面壳既有变量）。
import './styles/mobile-tokens.css'

createApp(App).use(router).mount('#app')
