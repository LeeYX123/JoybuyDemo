// 全站输入框关闭浏览器自动填充 / 保存 / 历史记忆（商城端登录与注册页除外）。
//
// 背景（HANDOFF「全站输入框禁用自动填充」）：
// - Chrome 对地址、姓名、电话、邮箱等字段有强启发式，`autocomplete="off"` 常被忽略；
//   `autocomplete="new-password"` 是 Chrome 明确尊重的令牌，对非密码字段同样抑制
//   autofill 建议，因此个人资料/地址/凭证类统一用它；
// - 搜索、日期、数量等非个人字段用 `off`，避免保留历史但仍不影响语义；
// - 规范未定义的随机 token 会被浏览器按默认（开启）处理，实测不建议使用，故不采用。
//
// 登录/注册页 `components/AuthForm.vue` 按需求保留浏览器正常行为，不要引用本模块。

const COMMON = {
  spellcheck: 'false',
  autocapitalize: 'off',
  autocorrect: 'off',
}

// 个人资料 / 地址 / 联系方式 / 密码类：Chrome 会忽略 off，用 new-password 抑制。
export const noAutofill = {
  ...COMMON,
  autocomplete: 'new-password',
}

// 搜索 / 筛选 / 日期 / 数量类：只是不要历史记忆，用 off 保留语义。
export const noAutofillSearch = {
  ...COMMON,
  autocomplete: 'off',
}
