import { describe, expect, it } from 'vitest'

import { messages } from '../locales/messages'

// 2026-11-28 购物端同批需求的文案完整性守卫：7 个语言块（en/zh/de/fr/nl/ja/ko）
// 必须有完全一致的 key 集合，且本批新增的 18 个 key（直购提示 / 账号邮箱 /
// 修改密码弹窗）在每个语言块都存在。跑在 vitest 里，避免只靠人工核对。
const LOCALES = ['en', 'zh', 'de', 'fr', 'nl', 'ja', 'ko']

const NEW_KEYS = [
  'accountMenu.changePassword',
  'account.emailLabel',
  'account.changePassword.title',
  'account.changePassword.old',
  'account.changePassword.oldPlaceholder',
  'account.changePassword.new',
  'account.changePassword.newPlaceholder',
  'account.changePassword.confirm',
  'account.changePassword.confirmPlaceholder',
  'account.changePassword.save',
  'account.changePassword.saving',
  'account.changePassword.cancel',
  'account.changePassword.errorTooShort',
  'account.changePassword.errorMismatch',
  'account.changePassword.errorOldWrong',
  'account.changePassword.errorGeneric',
  'account.changePassword.success',
  'checkout.buyingSolo',
]

describe('messages locale parity', () => {
  it('has an identical key set in all 7 locales', () => {
    const reference = Object.keys(messages.en).sort()
    for (const locale of LOCALES.slice(1)) {
      expect(Object.keys(messages[locale]).sort(), locale).toEqual(reference)
    }
  })

  it('contains every key added for direct purchase / email / change password', () => {
    for (const locale of LOCALES) {
      for (const key of NEW_KEYS) {
        expect(messages[locale][key], `${locale}:${key}`).toBeTruthy()
      }
    }
  })

  it('uses distinct copy for the change-password modal per locale', () => {
    const titles = LOCALES.map((locale) => messages[locale]['account.changePassword.title'])
    expect(new Set(titles).size).toBe(LOCALES.length)
  })
})
