import { describe, expect, it } from 'vitest'

import { pickName } from '../locales/messages'

// Bilingual label picking (docs/12: configurable EN/ZH target state).
describe('pickName', () => {
  const item = { name: 'Fallback', name_en: 'Home & Living', name_zh: '家居生活' }

  it('prefers the requested locale', () => {
    expect(pickName(item, 'zh')).toBe('家居生活')
    expect(pickName(item, 'en')).toBe('Home & Living')
  })

  it('falls back to the other language and then the base name', () => {
    expect(pickName({ name: 'Only base' }, 'zh')).toBe('Only base')
    expect(pickName({ name_en: 'English only' }, 'zh')).toBe('English only')
  })

  it('works for CMS label fields too', () => {
    const tile = { label: 'Games', label_zh: '游戏' }
    expect(pickName(tile, 'zh', 'label')).toBe('游戏')
    expect(pickName(tile, 'en', 'label')).toBe('Games')
  })
})
