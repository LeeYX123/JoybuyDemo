import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 2026-11-27 缺陷修复的针对性单测：买家会话在客户端「节流再校验」。
// 场景：SSR 首帧把 merchant_application_status 写进 payload，管理端在另一个
// 标签页审核通过后，商城端必须能在下次路由/切回标签页时拿到新状态，且 TTL 内
// 的连续导航不能各发一次请求。

function sessionPayload(status) {
  return {
    authenticated: true,
    account: { email: 'buyer@example.test', merchant_application_status: status },
    csrf_token: 'csrf-test',
  }
}

let fetchMock

async function loadComposable() {
  // 模块级节流时间戳需要在每个用例里重新初始化。
  vi.resetModules()
  const mod = await import('./useBuyerAuth')
  return mod.useBuyerAuth
}

describe('useBuyerAuth.revalidate', () => {
  beforeEach(() => {
    fetchMock = vi.fn(async () => sessionPayload('PENDING'))
    vi.stubGlobal('$fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('刷新申请状态并把结果写进共享派生状态', async () => {
    const useBuyerAuth = await loadComposable()
    const auth = useBuyerAuth()
    expect(auth.merchantApplicationStatus.value).toBe(null)

    fetchMock.mockResolvedValueOnce(sessionPayload('APPROVED'))
    await auth.revalidate()

    expect(auth.merchantApplicationStatus.value).toBe('APPROVED')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('TTL 内的连续导航合并为一次请求，force 可绕过', async () => {
    const useBuyerAuth = await loadComposable()
    const auth = useBuyerAuth()

    await auth.revalidate()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await auth.revalidate()
    await auth.revalidate({ minInterval: 5_000 })
    expect(fetchMock).toHaveBeenCalledTimes(1)

    fetchMock.mockResolvedValueOnce(sessionPayload('REJECTED'))
    await auth.revalidate({ force: true })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(auth.merchantApplicationStatus.value).toBe('REJECTED')
  })

  it('并发调用复用同一次在途请求', async () => {
    const useBuyerAuth = await loadComposable()
    const auth = useBuyerAuth()

    const first = auth.revalidate({ force: true })
    const second = auth.revalidate({ force: true })
    await Promise.all([first, second])

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('再校验失败时保留已登录态，不清空会话', async () => {
    const useBuyerAuth = await loadComposable()
    const auth = useBuyerAuth()
    fetchMock.mockResolvedValueOnce(sessionPayload('PENDING'))
    await auth.revalidate()
    expect(auth.isAuthenticated.value).toBe(true)

    fetchMock.mockRejectedValueOnce(new Error('network down'))
    await auth.revalidate({ force: true })

    expect(auth.isAuthenticated.value).toBe(true)
    expect(auth.merchantApplicationStatus.value).toBe('PENDING')
  })

  it('显式 refresh（登录/提交申请后）同样刷新快照时间', async () => {
    const useBuyerAuth = await loadComposable()
    const auth = useBuyerAuth()

    fetchMock.mockResolvedValueOnce(sessionPayload('PENDING'))
    await auth.refresh()

    await auth.revalidate()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
