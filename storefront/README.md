# Storefront

Nuxt 3（Vue 3、JavaScript、SSR）购物端基座。当前只提供可运行的应用壳、API 客户端和错误页，不包含 Joybuy 视觉复刻或业务页面。

## 命令

从仓库根目录执行：

```powershell
pnpm install --frozen-lockfile
pnpm dev:storefront
pnpm build:storefront
```

默认地址：<http://127.0.0.1:3000>。

复制 `storefront/.env.example` 为 `storefront/.env` 可覆盖 API 地址。浏览器请求使用 Cookie，不把敏感令牌放入 localStorage。
