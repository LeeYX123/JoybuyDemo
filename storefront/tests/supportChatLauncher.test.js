import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SupportChatLauncher from '../components/SupportChatLauncher.vue'

// 面板（需求 23.3 / 批次 AB）：会话列表 → 会话视图首屏（头像/欢迎语/FAQ/
// 发送订单/输入框）、FAQ 点击即发送、清除只清显示、订单弹层多选发送、
// 5s 轮询在进入会话时启用、返回列表即停。
//
// useBuyerAuth 用 mock 固定已登录（未登录跳转由 e2e 覆盖）；HTTP 走
// globalThis.$fetch 打桩（Nuxt 运行时里 $fetch 是全局函数，组件不导入它）。
vi.mock('../composables/useBuyerAuth', async () => {
  const { computed } = await import('vue')
  return {
    useBuyerAuth: () => ({ isAuthenticated: computed(() => true) }),
  }
})

const NuxtLinkStub = {
  name: 'NuxtLink',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

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

function installFetch({ messages = [], orders = [] } = {}) {
  const state = { messages: [...messages], orders, posts: [], gets: [] }
  let nextId = 100
  const mock = vi.fn(async (url, options = {}) => {
    const target = String(url)
    if (target.includes('/auth/buyer/session')) return { csrf_token: 'csrf' }
    if (target.endsWith('/support-chat/thread')) {
      return {
        thread: {
          id: 'thread-1',
          buyer_unread: 2,
          last_message_at: state.messages.at(-1)?.created_at || '2026-11-23T09:00:00+00:00',
        },
      }
    }
    if (target.includes('/support-chat/messages')) {
      if ((options.method || 'GET') === 'POST') {
        const payload = typeof options.body === 'string' ? JSON.parse(options.body) : options.body
        const body = payload.body
        const message = {
          id: nextId++,
          sender_kind: 'buyer',
          body,
          created_at: `2026-11-23T10:0${state.posts.length}:00+00:00`,
        }
        state.posts.push(body)
        state.messages.push(message)
        return { message, thread: { id: 'thread-1', buyer_unread: 0 } }
      }
      state.gets.push(target)
      const after = /after=([^&]+)/.exec(target)
      const list = after
        ? state.messages.filter(
            (item) => Date.parse(item.created_at) > Date.parse(decodeURIComponent(after[1])),
          )
        : state.messages
      return { messages: list, thread: { id: 'thread-1', buyer_unread: 0 } }
    }
    if (target.includes('/api/v1/orders')) return { orders: state.orders }
    throw new Error(`unexpected fetch: ${target}`)
  })
  globalThis.$fetch = mock
  return state
}

function mountLauncher() {
  return mount(SupportChatLauncher, {
    global: { stubs: { NuxtLink: NuxtLinkStub } },
  })
}

async function openPanel(wrapper) {
  await wrapper.get('[data-testid="support-chat-launcher"]').trigger('click')
  await flushPromises()
}

async function openConversation(wrapper) {
  await wrapper.get('[data-testid="support-chat-list-item"]').trigger('click')
  await flushPromises()
}

function bubbleTexts(wrapper) {
  return wrapper.findAll('.support-chat__text').map((node) => node.text())
}

let wrapper = null

beforeEach(() => {
  vi.useRealTimers()
})

afterEach(() => {
  if (wrapper) {
    wrapper.unmount()
    wrapper = null
  }
  delete globalThis.$fetch
  vi.useRealTimers()
})

describe('SupportChatLauncher 会话列表', () => {
  it('opens on the conversation list with the service card, time and unread badge', async () => {
    installFetch({ messages: [] })
    wrapper = mountLauncher()
    await openPanel(wrapper)

    expect(wrapper.find('[data-testid="support-chat-panel"]').exists()).toBe(true)
    const item = wrapper.get('[data-testid="support-chat-list-item"]')
    expect(item.text()).toContain('Customer Service')
    expect(item.text()).toContain('7*24 online support.')
    expect(item.find('.support-chat__item-time').text()).not.toBe('')
    expect(item.find('.support-chat__unread').text()).toBe('2')

    // 头部：清除 / 客服标题 / 关闭。
    expect(wrapper.get('[data-testid="support-chat-clear"]').exists()).toBe(true)
    expect(wrapper.get('.support-chat__title').text()).toBe('Customer Service')
    expect(wrapper.get('[data-testid="support-chat-close"]').exists()).toBe(true)
  })

  it('shows the conversation first screen after tapping the card', async () => {
    installFetch({ messages: [] })
    wrapper = mountLauncher()
    await openPanel(wrapper)
    await openConversation(wrapper)

    const welcome = wrapper.get('[data-testid="support-chat-welcome"]')
    expect(welcome.find('.support-chat__welcome-avatar').exists()).toBe(true)
    expect(welcome.text()).toContain('Black Friday has started')

    const faqs = wrapper.findAll('[data-testid="support-chat-faq"]')
    expect(faqs).toHaveLength(3)
    expect(faqs[0].text()).toBe('Where is my parcel?')

    expect(wrapper.get('[data-testid="support-chat-order-open"]').text()).toBe('Send order')
    const input = wrapper.get('[data-testid="support-chat-input"]')
    expect(input.attributes('placeholder')).toBe('Type your question')
    // 发送按钮在输入框容器内（框内右侧）且有 aria-label。
    expect(input.element.closest('.support-chat__field')).not.toBeNull()
    const send = wrapper.get('[data-testid="support-chat-send"]')
    expect(send.attributes('aria-label')).toBe('Send')
    expect(send.element.closest('.support-chat__field')).not.toBeNull()
  })
})

describe('SupportChatLauncher 发送与 FAQ', () => {
  it('sends the typed text with the in-field send button', async () => {
    const state = installFetch({ messages: [] })
    wrapper = mountLauncher()
    await openPanel(wrapper)
    await openConversation(wrapper)

    const input = wrapper.get('[data-testid="support-chat-input"]')
    await input.setValue('Hello support')
    const send = wrapper.get('[data-testid="support-chat-send"]')
    expect(send.attributes('disabled')).toBeUndefined()
    await send.trigger('click')
    await flushPromises()

    expect(state.posts).toEqual(['Hello support'])
    expect(bubbleTexts(wrapper)).toContain('Hello support')
    expect(input.element.value).toBe('')
  })

  it('sends a FAQ sentence as a normal message when clicked', async () => {
    const state = installFetch({ messages: [] })
    wrapper = mountLauncher()
    await openPanel(wrapper)
    await openConversation(wrapper)

    await wrapper.findAll('[data-testid="support-chat-faq"]')[0].trigger('click')
    await flushPromises()

    expect(state.posts).toEqual(['Where is my parcel?'])
    expect(bubbleTexts(wrapper)).toContain('Where is my parcel?')
    // 发了消息后回到普通消息流，FAQ 首屏不再展示。
    expect(wrapper.findAll('[data-testid="support-chat-faq"]')).toHaveLength(0)
  })
})

describe('SupportChatLauncher 清除', () => {
  it('clears the rendered history only, and re-entering reloads it from the server', async () => {
    installFetch({
      messages: [
        {
          id: 1,
          sender_kind: 'support',
          body: 'Welcome to Joybuy support',
          created_at: '2026-11-23T09:00:00+00:00',
        },
      ],
    })
    wrapper = mountLauncher()
    await openPanel(wrapper)
    await openConversation(wrapper)
    expect(bubbleTexts(wrapper)).toEqual(['Welcome to Joybuy support'])

    await wrapper.get('[data-testid="support-chat-clear"]').trigger('click')
    await flushPromises()
    expect(bubbleTexts(wrapper)).toEqual([])
    // 清空后重新回到首屏（欢迎语 + FAQ）。
    expect(wrapper.findAll('[data-testid="support-chat-faq"]')).toHaveLength(3)

    // 返回列表再进入 → 后端历史重新拉回来（Q4：不删库）。
    await wrapper.get('[data-testid="support-chat-back"]').trigger('click')
    await flushPromises()
    await openConversation(wrapper)
    expect(bubbleTexts(wrapper)).toEqual(['Welcome to Joybuy support'])
  })

  it('keeps the poll cursor after clearing so history is not re-appended', async () => {
    // 只伪造 interval，setTimeout 留给 flushPromises。
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    installFetch({
      messages: [
        {
          id: 1,
          sender_kind: 'support',
          body: 'Old message',
          created_at: '2026-11-23T09:00:00+00:00',
        },
      ],
    })
    wrapper = mountLauncher()
    await openPanel(wrapper)
    await openConversation(wrapper)
    await wrapper.get('[data-testid="support-chat-clear"]').trigger('click')
    await flushPromises()

    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()

    expect(bubbleTexts(wrapper)).toEqual([])
  })
})

describe('SupportChatLauncher 发送订单', () => {
  it('lists the 3 most recent orders, sends the selected ones as one text message', async () => {
    const state = installFetch({ messages: [], orders: ORDERS })
    wrapper = mountLauncher()
    await openPanel(wrapper)
    await openConversation(wrapper)

    await wrapper.get('[data-testid="support-chat-order-open"]').trigger('click')
    await flushPromises()

    const dialog = wrapper.get('[data-testid="support-chat-order-dialog"]')
    const checkboxes = dialog.findAll('[data-testid="support-chat-order-checkbox"]')
    expect(checkboxes).toHaveLength(3)
    expect(dialog.text()).toContain('#AAAA1111')
    expect(dialog.text()).toContain('$12.50')
    expect(dialog.text()).toContain('Shipped')

    const confirm = wrapper.get('[data-testid="support-chat-order-confirm"]')
    expect(confirm.attributes('disabled')).toBeDefined()

    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)
    expect(wrapper.get('[data-testid="support-chat-order-confirm"]').text()).toContain('(2)')
    await wrapper.get('[data-testid="support-chat-order-confirm"]').trigger('click')
    await flushPromises()

    expect(state.posts).toHaveLength(1)
    const lines = state.posts[0].split('\n')
    expect(lines).toHaveLength(2)
    expect(lines[0]).toContain(ORDERS[0].public_id)
    expect(lines[0]).toContain('$12.50')
    expect(lines[0]).toContain('Shipped')
    expect(lines[1]).toContain(ORDERS[1].public_id)
    expect(lines[1]).toContain('$40.00')
    expect(lines[1]).toContain('Pending payment')
    // 弹层关闭，消息流出现订单文本。
    expect(wrapper.find('[data-testid="support-chat-order-dialog"]').exists()).toBe(false)
    expect(bubbleTexts(wrapper)).toContain(state.posts[0])
  })
})

describe('SupportChatLauncher 轮询', () => {
  it('polls every 5s in the conversation and stops when going back to the list', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    const state = installFetch({
      messages: [
        {
          id: 1,
          sender_kind: 'support',
          body: 'Welcome',
          created_at: '2026-11-23T09:00:00+00:00',
        },
      ],
    })

    wrapper = mountLauncher()
    await openPanel(wrapper)
    await openConversation(wrapper)
    const base = state.gets.length

    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    expect(state.gets.length).toBe(base + 1)
    // 有已确认消息时轮询带增量游标 after。
    expect(state.gets.at(-1)).toContain('after=')

    await wrapper.get('[data-testid="support-chat-back"]').trigger('click')
    await flushPromises()
    const afterBack = state.gets.length
    await vi.advanceTimersByTimeAsync(10000)
    await flushPromises()
    expect(state.gets.length).toBe(afterBack)
  })
})
