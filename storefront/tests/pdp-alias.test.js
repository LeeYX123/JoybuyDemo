import { describe, expect, it, vi } from 'vitest'

import {
  aliasRedirectTarget,
  createAliasCache,
  pdpPublicIdFromPath,
  resolvePdpAlias,
} from '../utils/pdpAlias'

// 2026-11-27 全站编号改造（商品号回退 UUID 后）：商品号仍是 UUID；前端解析
// 同时宽松接受 JY 前缀编号（订单等编号体系），避免旧/新链接 301 失效。
const OLD_ID = '08f6f1c1-2f0e-4f0c-9a5e-6b7d8e9f0a1b'
const KEEP_ID = '11111111-2222-4333-8444-555555555555'
const JY_ID = 'JYP001M4ANKUT'
const JY_KEEP_ID = 'JYP001U98GEW8'

describe('pdpPublicIdFromPath', () => {
  it('从 /p/<UUID> 提取 id（大小写归一、忽略查询串与尾斜杠）', () => {
    expect(pdpPublicIdFromPath(`/p/${OLD_ID}`)).toBe(OLD_ID)
    expect(pdpPublicIdFromPath(`/p/${OLD_ID.toUpperCase()}/`)).toBe(OLD_ID)
    expect(pdpPublicIdFromPath(`/p/${OLD_ID}?offer=abc`)).toBe(OLD_ID)
  })

  it('JY 前缀编号也被接受（归一为全大写，宽松兼容）', () => {
    expect(pdpPublicIdFromPath(`/p/${JY_ID}`)).toBe(JY_ID)
    expect(pdpPublicIdFromPath(`/p/${JY_ID.toLowerCase()}`)).toBe(JY_ID)
  })

  it('非 PDP 路径或非法编号返回空串（不查别名）', () => {
    expect(pdpPublicIdFromPath('/p/')).toBe('')
    expect(pdpPublicIdFromPath('/product/123')).toBe('')
    expect(pdpPublicIdFromPath('/p/not-an-id')).toBe('')
    expect(pdpPublicIdFromPath('/p/JY')).toBe('')
    expect(pdpPublicIdFromPath('/c/sports-nutrition-performance')).toBe('')
  })
})

describe('aliasRedirectTarget', () => {
  it('拼出保留商品地址并保留原查询串', () => {
    expect(aliasRedirectTarget(KEEP_ID)).toBe(`/p/${KEEP_ID}`)
    expect(aliasRedirectTarget(KEEP_ID, '?offer=abc')).toBe(`/p/${KEEP_ID}?offer=abc`)
    expect(aliasRedirectTarget(KEEP_ID, 'offer=abc')).toBe(`/p/${KEEP_ID}?offer=abc`)
  })

  it('目标编号大小写归一（UUID 小写、JY 编号大写）', () => {
    expect(aliasRedirectTarget(KEEP_ID.toUpperCase())).toBe(`/p/${KEEP_ID}`)
    expect(aliasRedirectTarget(JY_KEEP_ID.toLowerCase())).toBe(`/p/${JY_KEEP_ID}`)
  })

  it('没有保留 id 或 id 不合法时返回空串', () => {
    expect(aliasRedirectTarget('')).toBe('')
    expect(aliasRedirectTarget(null)).toBe('')
    expect(aliasRedirectTarget('keep-not-id')).toBe('')
  })
})

describe('resolvePdpAlias', () => {
  it('命中别名时返回 301 目标', async () => {
    const fetchCanonical = vi.fn().mockResolvedValue(KEEP_ID)
    await expect(
      resolvePdpAlias({ path: `/p/${OLD_ID}?from=merchant`, fetchCanonical }),
    ).resolves.toBe(`/p/${KEEP_ID}?from=merchant`)
    expect(fetchCanonical).toHaveBeenCalledWith(OLD_ID)
  })

  it('未命中时返回空串并缓存负结果（第二次不再查后端）', async () => {
    const cache = createAliasCache()
    const fetchCanonical = vi.fn().mockResolvedValue('')
    await expect(resolvePdpAlias({ path: `/p/${OLD_ID}`, fetchCanonical, cache })).resolves.toBe('')
    await expect(resolvePdpAlias({ path: `/p/${OLD_ID}`, fetchCanonical, cache })).resolves.toBe('')
    expect(fetchCanonical).toHaveBeenCalledTimes(1)
  })

  it('缓存过期后重新查询', async () => {
    let now = 0
    const cache = createAliasCache({ ttlMs: 1000, now: () => now })
    const fetchCanonical = vi.fn().mockResolvedValue(KEEP_ID)
    await resolvePdpAlias({ path: `/p/${OLD_ID}`, fetchCanonical, cache })
    now = 2000
    await resolvePdpAlias({ path: `/p/${OLD_ID}`, fetchCanonical, cache })
    expect(fetchCanonical).toHaveBeenCalledTimes(2)
  })

  it('后端异常不挡 PDP，且不缓存错误结果', async () => {
    const cache = createAliasCache()
    const failing = vi.fn().mockRejectedValue(new Error('boom'))
    await expect(
      resolvePdpAlias({ path: `/p/${OLD_ID}`, fetchCanonical: failing, cache }),
    ).resolves.toBe('')
    const ok = vi.fn().mockResolvedValue(KEEP_ID)
    await expect(
      resolvePdpAlias({ path: `/p/${OLD_ID}`, fetchCanonical: ok, cache }),
    ).resolves.toBe(`/p/${KEEP_ID}`)
  })

  it('非 PDP 路径不调用后端', async () => {
    const fetchCanonical = vi.fn()
    await expect(resolvePdpAlias({ path: '/c/home', fetchCanonical })).resolves.toBe('')
    expect(fetchCanonical).not.toHaveBeenCalled()
  })
})

describe('createAliasCache', () => {
  it('超过条数上限时清空，避免长跑内存增长', () => {
    const cache = createAliasCache({ maxEntries: 2 })
    cache.set('a', '1')
    cache.set('b', '2')
    expect(cache.size).toBe(2)
    cache.set('c', '3')
    expect(cache.size).toBe(1)
    expect(cache.get('a')).toBeUndefined()
    expect(cache.get('c')).toBe('3')
  })
})
