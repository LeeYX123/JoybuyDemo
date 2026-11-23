import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MerchantChatPanel from './MerchantChatPanel.vue'

// 需求 19.3-5/19.3-6：面板契约——打开即 get-or-create 会话并拉消息、
// 自己右对齐/商家左对齐、乐观发送后被服务端消息替换、403 白名单提示、
// 空白与超长消息不发送、5s 轮询增量。

const MERCHANT = { slug: 'demo-shop', display_name: 'Demo Shop', avatar_url: '' }
const BASE = '/api/v1/account/merchant-chat'
const MESSAGES_URL = `${BASE}/threads/thread-1/messages`

function message(id, senderKind, body, createdAt) {
  return { id, sender_kind: senderKind, body, created_at: createdAt, read_at: null }
}

let wrapper
let fetchMock
let requests

function createFetchMock(overrides = {}) {
  return vi.fn(async (url, options = {}) => {
    const method = options.method || 'GET'
    requests.push({ url, method, options })
    const key = `${method} ${url}`
    const custom = overrides[key]
    if (custom) return custom(options)
    if (url === '/api/v1/auth/buyer/session') return { csrf_token: 'csrf-token' }
    if (key === `POST ${BASE}/threads`) return { thread: { id: 'thread-1' } }
    if (key === `GET ${MESSAGES_URL}`) {
      return {
        thread: { id: 'thread-1' },
        messages: [message(1, 'merchant', 'Hello from the shop', '2026-11-22T10:00:00+00:00')],
      }
    }
    if (key === `POST ${MESSAGES_URL}`) {
      const body = JSON.parse(options.body).body
      return {
        message: message(2, 'buyer', body, '2026-11-22T10:01:00+00:00'),
        thread: { id: 'thread-1' },
      }
    }
    throw new Error(`unexpected request: ${key}`)
  })
}

beforeEach(() => {
  requests = []
  fetchMock = createFetchMock()
  globalThis.$fetch = fetchMock
  // 捕获轮询回调，测试里手动触发，避免等真实 5s。
  vi.spyOn(globalThis, 'setInterval').mockImplementation((callback) => {
    globalThis.__pollCallback = callback
    return 1
  })
  vi.spyOn(globalThis, 'clearInterval').mockImplementation(() => {})
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.restoreAllMocks()
  delete globalThis.$fetch
  delete globalThis.__pollCallback
})

async function mountPanel(props = {}) {
  wrapper = mount(MerchantChatPanel, {
    props: { open: true, merchant: MERCHANT, ...props },
    global: {
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('MerchantChatPanel', () => {
  it('creates the thread on open and renders seller messages on the left', async () => {
    await mountPanel()

    const createCall = requests.find(
      (call) => call.method === 'POST' && call.url === `${BASE}/threads`,
    )
    expect(createCall).toBeTruthy()
    expect(createCall.options.body).toEqual({ merchant: 'demo-shop' })

    const bubbles = wrapper.findAll('.merchant-chat__bubble')
    expect(bubbles).toHaveLength(1)
    expect(bubbles[0].text()).toContain('Hello from the shop')
    expect(bubbles[0].classes()).not.toContain('merchant-chat__bubble--mine')
  })

  it('appends the message optimistically and replaces it with the server one', async () => {
    await mountPanel()

    const input = wrapper.find('.merchant-chat__input')
    await input.setValue('Do you ship to London?')
    await wrapper.find('.merchant-chat__send').trigger('click')
    await flushPromises()

    const sendCall = requests.find((call) => call.method === 'POST' && call.url === MESSAGES_URL)
    expect(sendCall).toBeTruthy()
    expect(sendCall.options.body).toEqual({ body: 'Do you ship to London?' })
    expect(sendCall.options.headers['X-CSRFToken']).toBe('csrf-token')

    const bubbles = wrapper.findAll('.merchant-chat__bubble')
    expect(bubbles).toHaveLength(2)
    const mine = bubbles[1]
    expect(mine.text()).toContain('Do you ship to London?')
    expect(mine.classes()).toContain('merchant-chat__bubble--mine')
    expect(input.element.value).toBe('')
  })

  it('shows the whitelist notice, hides the composer and emits blocked on 403', async () => {
    fetchMock = createFetchMock({
      [`POST ${BASE}/threads`]: () => ({ error: { code: 'NOT_WHITELISTED', message: 'no' } }),
    })
    globalThis.$fetch = fetchMock
    await mountPanel()

    const notice = wrapper.find('.merchant-chat__notice')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain('cannot contact sellers')
    expect(wrapper.find('.merchant-chat__compose').exists()).toBe(false)
    expect(wrapper.emitted('blocked')).toBeTruthy()
    expect(requests.some((call) => call.url.startsWith(MESSAGES_URL))).toBe(false)
  })

  it('never sends blank or over-long messages', async () => {
    await mountPanel()

    await wrapper.find('.merchant-chat__send').trigger('click')
    await flushPromises()
    expect(requests.some((call) => call.method === 'POST' && call.url === MESSAGES_URL)).toBe(false)

    // happy-dom 的 setValue 会遵守 maxlength，直接写 value + input 事件模拟粘贴超长内容。
    const textarea = wrapper.find('.merchant-chat__input')
    expect(textarea.attributes('maxlength')).toBe('2000')
    textarea.element.value = 'x'.repeat(2001)
    await textarea.trigger('input')
    await wrapper.find('.merchant-chat__send').trigger('click')
    await flushPromises()
    expect(requests.some((call) => call.method === 'POST' && call.url === MESSAGES_URL)).toBe(false)
    expect(wrapper.find('.merchant-chat__send').attributes('disabled')).toBeDefined()
  })

  it('renders a platform support reply with its own label and style', async () => {
    // 批次 AA：Crisp 人工回复回传为 sender_kind=support，不能当成商家本人。
    fetchMock = createFetchMock({
      [`GET ${MESSAGES_URL}`]: () => ({
        thread: { id: 'thread-1' },
        messages: [
          message(1, 'merchant', 'Hello from the shop', '2026-11-22T10:00:00+00:00'),
          message(2, 'support', 'Support here, we are on it', '2026-11-22T10:02:00+00:00'),
        ],
      }),
    })
    globalThis.$fetch = fetchMock
    await mountPanel()

    const bubbles = wrapper.findAll('.merchant-chat__bubble')
    expect(bubbles).toHaveLength(2)
    const support = bubbles[1]
    expect(support.text()).toContain('Support here')
    expect(support.classes()).toContain('merchant-chat__bubble--support')
    expect(support.classes()).not.toContain('merchant-chat__bubble--mine')
    expect(support.find('.merchant-chat__tag').text()).toBe('Support')
    expect(bubbles[0].find('.merchant-chat__tag').exists()).toBe(false)
  })

  it('polls with the last server timestamp and appends the seller reply', async () => {
    await mountPanel()

    const poll = globalThis.__pollCallback
    expect(typeof poll).toBe('function')

    fetchMock.mockImplementation(async (url, options = {}) => {
      const method = options.method || 'GET'
      requests.push({ url, method, options })
      if (url === '/api/v1/auth/buyer/session') return { csrf_token: 'csrf-token' }
      if (method === 'GET' && url.startsWith(MESSAGES_URL)) {
        return {
          thread: { id: 'thread-1' },
          messages: [
            message(9, 'merchant', 'Yes, next-day delivery.', '2026-11-22T10:05:00+00:00'),
          ],
        }
      }
      throw new Error(`unexpected request: ${method} ${url}`)
    })

    await poll()
    await flushPromises()

    const pollCall = requests.find(
      (call) => call.method === 'GET' && call.url.startsWith(`${MESSAGES_URL}?after=`),
    )
    expect(pollCall).toBeTruthy()
    expect(decodeURIComponent(pollCall.url)).toContain('2026-11-22T10:00:00+00:00')

    const bubbles = wrapper.findAll('.merchant-chat__bubble')
    expect(bubbles).toHaveLength(2)
    expect(bubbles[1].text()).toContain('Yes, next-day delivery.')
    expect(bubbles[1].classes()).not.toContain('merchant-chat__bubble--mine')
  })

  // 竞态回归（验收 FAIL）：真实 Crisp 让首发 POST ~3.7s，5s 轮询会先拿到
  // 同一条服务端消息。轮询先认领乐观气泡、POST 随后返回同一 id，最终也只能有 1 条。
  for (const round of [1, 2, 3]) {
    it(`keeps one bubble when polling confirms the message before a slow POST returns (round ${round})`, async () => {
      fetchMock = createFetchMock({
        [`GET ${MESSAGES_URL}`]: () => ({ thread: { id: 'thread-1' }, messages: [] }),
      })
      globalThis.$fetch = fetchMock
      await mountPanel()

      const body = `Slow first send ${round}`
      const serverRow = message(42, 'buyer', body, '2026-11-22T10:02:00+00:00')
      let resolvePost = null

      // 慢 POST：手动 resolve，模拟首发被 Crisp 拖到 3.7s。
      fetchMock.mockImplementation((url, options = {}) => {
        const method = options.method || 'GET'
        requests.push({ url, method, options })
        if (url === '/api/v1/auth/buyer/session') {
          return Promise.resolve({ csrf_token: 'csrf-token' })
        }
        if (method === 'GET' && url.startsWith(`${MESSAGES_URL}?after=`)) {
          return Promise.resolve({ thread: { id: 'thread-1' }, messages: [serverRow] })
        }
        if (method === 'POST' && url === MESSAGES_URL) {
          return new Promise((resolve) => {
            resolvePost = () => resolve({ message: serverRow, thread: { id: 'thread-1' } })
          })
        }
        throw new Error(`unexpected request: ${method} ${url}`)
      })

      await wrapper.find('.merchant-chat__input').setValue(body)
      await wrapper.find('.merchant-chat__send').trigger('click')
      await flushPromises()

      // POST 未返回：只有一条 pending 乐观气泡。
      let bubbles = wrapper.findAll('.merchant-chat__bubble')
      expect(bubbles).toHaveLength(1)
      expect(bubbles[0].classes()).toContain('merchant-chat__bubble--pending')

      // 轮询先到：游标必须带乐观消息时间（不是空的全量拉取），并认领该气泡。
      await globalThis.__pollCallback()
      await flushPromises()
      const pollCall = requests.find(
        (call) => call.method === 'GET' && call.url.startsWith(`${MESSAGES_URL}?after=`),
      )
      expect(pollCall).toBeTruthy()

      bubbles = wrapper.findAll('.merchant-chat__bubble')
      expect(bubbles).toHaveLength(1)
      expect(bubbles[0].text()).toContain(body)

      // POST 随后返回同一 id：原地替换，不能再 append 第二条。
      resolvePost()
      await flushPromises()

      bubbles = wrapper.findAll('.merchant-chat__bubble')
      expect(bubbles).toHaveLength(1)
      expect(bubbles[0].text()).toContain(body)
      expect(bubbles[0].classes()).toContain('merchant-chat__bubble--mine')
      expect(bubbles[0].classes()).not.toContain('merchant-chat__bubble--pending')
      expect(wrapper.text().split(body)).toHaveLength(2)
    })
  }
})
