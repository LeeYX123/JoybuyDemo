# Admin Web

Vue 3 + Vite + JavaScript 平台管理端基座。当前只提供应用壳、路由、API 客户端和错误页，不包含登录、业务表格或管理功能。

## 命令

从仓库根目录执行：

```powershell
pnpm install --frozen-lockfile
pnpm dev:admin
pnpm build:admin
```

默认地址：<http://127.0.0.1:5173>。

复制 `admin-web/.env.example` 为 `admin-web/.env` 可覆盖 API 地址。管理端使用独立员工 Cookie 会话；API 客户端不读写 localStorage。
