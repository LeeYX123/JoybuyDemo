import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 需求 21 批次 Y：全站【客服】入口契约——未登录先去登录（带 next）、登录后
// 打开面板即 get-or-create 并拉消息、乐观发送被服务端消息替换、5s 轮询增量、
// Escape 关闭并停轮询。
const { authState } = vi.hoisted(() => ({
  // 组件只读取 isAuthenticated.value，普通对象足够（测试里在 mount 前改值）。
  authState: { value: true },
}))

vi.mock('../composables/useBuyerAuth', () => ({
  useBuyerAuth: () => ({ isAuthenticated: authState }),
}))

vi.mock('#imports', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useRoute: () => ({ params: {}, query: {}, path: '/cart', fullPath: '/cart?ref=1' }),
  }
})

import SupportChatLauncher from './SupportChatLauncher.vue'
import { stubCalls } from '../tests/nuxt-imports-stub'

const BASE = '/api/v1/account/support-chat'
const MESSAGES_URL = `${BASE}/messages`

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
    if (key === `POST ${BASE}/thread`) {
      return { thread: { id: 'thread-1', last_message_at: null, buyer_unread: 0 } }
    }
    if (key === `GET ${MESSAGES_URL}`) {
      return {
        thread: { id: 'thread-1' },
        messages: [message(1, 'support', 'Hello from Joybuy support', '2026-11-22T10:00:00+00:00')],
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
  authState.value = true
  requests = []
  stubCalls.length = 0
  fetchMock = createFetchMock()
  globalThis.$fetch = fetchMock
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

async function mountLauncher() {
  wrapper = mount(SupportChatLauncher, {
    global: {
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

async function openPanel() {
  await wrapper.find('[data-testid="support-chat-launcher"]').trigger('click')
  await flushPromises()
  await flushPromises()
}

describe('SupportChatLauncher', () => {
  it('renders the launcher and keeps the panel closed until clicked', async () => {
    await mountLauncher()
    const launcher = wrapper.find('[data-testid="support-chat-launcher"]')
    expect(launcher.exists()).toBe(true)
    expect(launcher.text()).toContain('Support')
    expect(wrapper.find('[data-testid="support-chat-panel"]').exists()).toBe(false)
    expect(requests).toHaveLength(0)
  })

  it('creates the thread and shows existing support messages', async () => {
    await mountLauncher()
    await openPanel()

    expect(requests.some((call) => call.method === 'POST' && call.url === `${BASE}/thread`)).toBe(
      true,
    )
    const bubbles = wrapper.findAll('.support-chat__bubble')
    expect(bubbles).toHaveLength(1)
    expect(bubbles[0].text()).toContain('Hello from Joybuy support')
    expect(bubbles[0].classes()).not.toContain('support-chat__bubble--mine')
  })

  it('sends optimistically and replaces the bubble with the server message', async () => {
    await mountLauncher()
    await openPanel()

    await wrapper.find('[data-testid="support-chat-input"]').setValue('Where is my order?')
    await wrapper.find('[data-testid="support-chat-send"]').trigger('click')
    await flushPromises()

    const sendCall = requests.find((call) => call.method === 'POST' && call.url === MESSAGES_URL)
    expect(sendCall).toBeTruthy()
    expect(sendCall.options.body).toEqual({ body: 'Where is my order?' })
    expect(sendCall.options.headers['X-CSRFToken']).toBe('csrf-token')

    const bubbles = wrapper.findAll('.support-chat__bubble')
    expect(bubbles).toHaveLength(2)
    expect(bubbles[1].text()).toContain('Where is my order?')
    expect(bubbles[1].classes()).toContain('support-chat__bubble--mine')
    expect(wrapper.find('[data-testid="support-chat-input"]').element.value).toBe('')
  })

  it('polls with the last timestamp and appends the support reply', async () => {
    await mountLauncher()
    await openPanel()

    fetchMock.mockImplementation(async (url, options = {}) => {
      const method = options.method || 'GET'
      requests.push({ url, method, options })
      if (url === '/api/v1/auth/buyer/session') return { csrf_token: 'csrf-token' }
      if (method === 'GET' && url.startsWith(`${MESSAGES_URL}?after=`)) {
        return {
          thread: { id: 'thread-1' },
          messages: [
            message(9, 'support', 'Your parcel is on the way.', '2026-11-22T10:05:00+00:00'),
          ],
        }
      }
      throw new Error(`unexpected request: ${method} ${url}`)
    })

    await globalThis.__pollCallback()
    await flushPromises()

    const pollCall = requests.find(
      (call) => call.method === 'GET' && call.url.startsWith(`${MESSAGES_URL}?after=`),
    )
    expect(pollCall).toBeTruthy()
    expect(decodeURIComponent(pollCall.url)).toContain('2026-11-22T10:00:00+00:00')

    const bubbles = wrapper.findAll('.support-chat__bubble')
    expect(bubbles).toHaveLength(2)
    expect(bubbles[1].text()).toContain('Your parcel is on the way.')
    expect(bubbles[1].classes()).not.toContain('support-chat__bubble--mine')
  })

  it('redirects signed-out visitors to login with the current page as next', async () => {
    authState.value = false
    await mountLauncher()
    await wrapper.find('[data-testid="support-chat-launcher"]').trigger('click')
    await flushPromises()

    const navigate = stubCalls.filter((call) => call.name === 'navigateTo').at(-1)
    expect(navigate).toBeTruthy()
    expect(navigate.args[0]).toBe(`/auth/login?next=${encodeURIComponent('/cart?ref=1')}`)
    expect(wrapper.find('[data-testid="support-chat-panel"]').exists()).toBe(false)
    expect(requests).toHaveLength(0)
  })

  it('closes on Escape and stops polling', async () => {
    await mountLauncher()
    await openPanel()

    const stop = vi.spyOn(globalThis, 'clearInterval')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(wrapper.find('[data-testid="support-chat-panel"]').exists()).toBe(false)
    expect(stop).toHaveBeenCalled()
  })

  it('shows the sign-in notice when the API reports an expired session', async () => {
    fetchMock = createFetchMock({
      [`POST ${BASE}/thread`]: () => ({
        error: { code: 'BUYER_AUTH_REQUIRED', message: 'sign in' },
      }),
    })
    globalThis.$fetch = fetchMock
    await mountLauncher()
    await openPanel()

    const notice = wrapper.find('.support-chat__notice')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain('sign in to contact support')
    expect(wrapper.find('.support-chat__compose').exists()).toBe(false)
  })
})
