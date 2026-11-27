import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 需求 21 批次 Y + 需求 23.3 批次 AB：全站【客服】入口契约——未登录先去登录
//（带 next）、登录后打开面板先看到会话列表（header 清除/客服/× + 【客户服务】
// 卡片），点进会话是首屏（欢迎语 + 三条 FAQ + 输入框）、乐观发送被服务端消息
// 替换、FAQ 点击即发送、清除只清显示、发送订单弹层多选拼一条消息、5s 轮询增量、
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
const ORDERS_URL = '/api/v1/orders'

const ORDERS = [
  {
    public_id: 'aaaa1111-0000-0000-0000-000000000001',
    total: '12.50',
    currency: 'GBP',
    state: 'SHIPPED',
  },
  {
    public_id: 'bbbb2222-0000-0000-0000-000000000002',
    total: '40.00',
    currency: 'GBP',
    state: 'PENDING_PAYMENT',
  },
  {
    public_id: 'cccc3333-0000-0000-0000-000000000003',
    total: '7.99',
    currency: 'GBP',
    state: 'COMPLETED',
  },
]

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
    if (key === `GET ${ORDERS_URL}`) return { orders: ORDERS }
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

// 会话为空（只有接待语回退），用于验证会话首屏的欢迎语/FAQ。
function installEmptyThreadFetch() {
  fetchMock = createFetchMock({
    [`GET ${MESSAGES_URL}`]: () => ({
      thread: { id: 'thread-1', last_message_at: '2026-11-22T09:00:00+00:00' },
      messages: [],
    }),
  })
  globalThis.$fetch = fetchMock
}

// 批次 AB：面板首页是会话列表，消息流在会话视图里。
async function enterConversation() {
  await wrapper.find('[data-testid="support-chat-list-item"]').trigger('click')
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

  it('shows header, the service card, then the conversation first screen', async () => {
    installEmptyThreadFetch()
    await mountLauncher()
    await openPanel()

    expect(requests.some((call) => call.method === 'POST' && call.url === `${BASE}/thread`)).toBe(
      true,
    )

    // header：左【清除】/ 中【客服】/ 右【×】。
    expect(wrapper.find('[data-testid="support-chat-clear"]').exists()).toBe(true)
    expect(wrapper.find('.support-chat__title').text()).toBe('Customer Service')
    expect(wrapper.find('[data-testid="support-chat-close"]').exists()).toBe(true)

    // 列表卡片：标题 + 摘要（无消息时回退到接待语）+ 时间。
    const card = wrapper.find('[data-testid="support-chat-list-item"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('Customer Service')
    expect(card.text()).toContain('7*24 online support.')
    expect(card.find('.support-chat__item-time').text()).not.toBe('')

    await enterConversation()

    // 会话首屏：欢迎语 + 三条 FAQ + 输入框（placeholder 为需求指定文案）。
    expect(wrapper.find('[data-testid="support-chat-welcome"]').text()).toContain('Black Friday')
    expect(wrapper.findAll('[data-testid="support-chat-faq"]')).toHaveLength(3)
    expect(wrapper.find('[data-testid="support-chat-input"]').attributes('placeholder')).toBe(
      'Type your question',
    )
    expect(wrapper.findAll('.support-chat__bubble')).toHaveLength(0)
  })

  it('sends optimistically and replaces the bubble with the server message', async () => {
    await mountLauncher()
    await openPanel()
    await enterConversation()

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

  it('sends a FAQ sentence as a normal message and collapses the FAQ block', async () => {
    installEmptyThreadFetch()
    await mountLauncher()
    await openPanel()
    await enterConversation()

    await wrapper.findAll('[data-testid="support-chat-faq"]')[0].trigger('click')
    await flushPromises()

    const sendCall = requests.find((call) => call.method === 'POST' && call.url === MESSAGES_URL)
    expect(sendCall.options.body).toEqual({ body: 'Where is my parcel?' })
    const bubbles = wrapper.findAll('.support-chat__bubble')
    expect(bubbles).toHaveLength(1)
    expect(bubbles[0].text()).toContain('Where is my parcel?')
    expect(wrapper.findAll('[data-testid="support-chat-faq"]')).toHaveLength(0)
  })

  it('clears the rendered history only, and reloads it when re-entering', async () => {
    await mountLauncher()
    await openPanel()
    await enterConversation()
    expect(wrapper.findAll('.support-chat__bubble')).toHaveLength(1)

    await wrapper.find('[data-testid="support-chat-clear"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.support-chat__bubble')).toHaveLength(0)
    expect(wrapper.findAll('[data-testid="support-chat-faq"]')).toHaveLength(3)

    await wrapper.find('[data-testid="support-chat-back"]').trigger('click')
    await flushPromises()
    await enterConversation()
    expect(wrapper.findAll('.support-chat__bubble')).toHaveLength(1)
  })

  it('lists the 3 most recent orders and sends the selected ones as one message', async () => {
    await mountLauncher()
    await openPanel()
    await enterConversation()

    await wrapper.find('[data-testid="support-chat-order-open"]').trigger('click')
    await flushPromises()

    const checkboxes = wrapper.findAll('[data-testid="support-chat-order-checkbox"]')
    expect(checkboxes).toHaveLength(3)
    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)
    await wrapper.find('[data-testid="support-chat-order-confirm"]').trigger('click')
    await flushPromises()

    const sendCall = requests.find((call) => call.method === 'POST' && call.url === MESSAGES_URL)
    const lines = sendCall.options.body.body.split('\n')
    expect(lines).toHaveLength(2)
    expect(lines[0]).toContain(ORDERS[0].public_id)
    expect(lines[0]).toContain('$12.50')
    expect(lines[0]).toContain('To receive')
    expect(lines[1]).toContain(ORDERS[1].public_id)
    expect(lines[1]).toContain('$40.00')
    expect(wrapper.find('[data-testid="support-chat-order-dialog"]').exists()).toBe(false)
  })

  it('polls with the last timestamp and appends the support reply', async () => {
    await mountLauncher()
    await openPanel()
    await enterConversation()

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
    // 批次 AB：轮询进入会话视图才启用，所以先点进会话。
    await enterConversation()

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
