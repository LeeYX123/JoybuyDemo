import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Deterministic category tree for the header row / panel linkage tests.
vi.mock('../composables/useCategoryTree', () => ({
  useCategoryTree: () => ({
    categories: ref([
      {
        slug: 'home-living',
        name: 'Home & Living',
        name_en: 'Home & Living',
        name_zh: '家居生活',
        channel_code: 'UK-Mini-HP-Home-Living',
        children: [
          { slug: 'kitchen-essentials', name_en: 'Kitchen Essentials', name_zh: '厨房用品' },
        ],
      },
      {
        slug: 'electronics',
        name: 'Electronics',
        name_en: 'Electronics',
        name_zh: '电子产品',
        children: [],
      },
    ]),
  }),
}))

// Mutable auth state so one file can exercise the signed-out header, the
// signed-in account menu and the shop-application entry states. The entry
// status comes from the shared buyer session payload (requirement 12.2: no
// extra request; the header derives its label from merchantApplicationStatus).
vi.mock('../composables/useBuyerAuth', async () => {
  const { ref } = await import('vue')
  const authenticated = ref(false)
  const applicationStatus = ref(null)
  // 需求 13.5-6：session payload 带 display_name（后端生成 user+数字+字母）。
  // 需求 C：payload 也带 auth_provider；mock 里默认**不带**该字段 —— 组件对缺省
  // 值按 EMAIL 处理（老 payload 语义），因此默认登录态是 6 行（含【修改密码】）。
  const DEFAULT_ACCOUNT = { email: 'buyer@example.com', display_name: 'user4323txlb' }
  const account = ref({ ...DEFAULT_ACCOUNT })
  return {
    __setAuthenticated: (value) => {
      authenticated.value = value
    },
    __setApplicationStatus: (value) => {
      applicationStatus.value = value
    },
    // 传入 'GOOGLE' / 'FACEBOOK' 切到 OAuth 渠道账号；传 null 回到缺省（EMAIL 语义）。
    __setAuthProvider: (value) => {
      account.value = value
        ? { ...DEFAULT_ACCOUNT, auth_provider: value }
        : { ...DEFAULT_ACCOUNT }
    },
    useBuyerAuth: () => ({
      isAuthenticated: authenticated,
      account,
      merchantApplicationStatus: applicationStatus,
      logout: vi.fn(),
      refresh: vi.fn(async () => {}),
    }),
  }
})

import {
  __setApplicationStatus,
  __setAuthProvider,
  __setAuthenticated,
} from '../composables/useBuyerAuth'
import AppHeader from './AppHeader.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  computed: {
    href() {
      if (typeof this.to === 'string') return this.to
      const query = new URLSearchParams(this.to?.query || {}).toString()
      return `${this.to?.path || ''}${query ? `?${query}` : ''}`
    },
  },
  template: '<a :href="href"><slot /></a>',
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
  await nextTick()
}

function mountHeader(props = {}) {
  const wrapper = mount(AppHeader, {
    props,
    attachTo: document.body,
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

const mountedWrappers = []

beforeEach(() => {
  __setAuthenticated(false)
  __setApplicationStatus(null)
  // 每个用例回到缺省 session（无 auth_provider → 组件按 EMAIL 处理）。
  __setAuthProvider(null)
})

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.body.style.overflow = ''
})

describe('AppHeader', () => {
  it('renders brand, pill categories trigger, round icons and the API category row', () => {
    const wrapper = mountHeader()
    expect(wrapper.get('.brand').attributes('aria-label')).toBe('Joybuy home')
    expect(wrapper.get('form.search').attributes('role')).toBe('search')
    expect(wrapper.get('#site-search').attributes('placeholder')).toBe('Search on Joybuy')
    // The categories trigger carries the label text (docs/12 header).
    expect(wrapper.get('.categories-button__label').text()).toBe('Categories')
    // 需求 11.5：未登录时右上角是文本【登录】按钮（无图标圆框），购物车仍是圆图标。
    expect(wrapper.get('.login-button').text()).toBe('Sign in')
    expect(
      wrapper.findAll('.icon-button').every((b) => b.classes().includes('icon-button--cart')),
    ).toBe(true)
    expect(wrapper.findAll('.icon-button').map((b) => b.attributes('aria-label'))).toEqual([
      'Cart, 0 items',
    ])
    // The 11 standard categories come from the API (requirement 1-1).
    expect(wrapper.findAll('.category-nav__link').map((link) => link.text())).toEqual([
      'Home & Living',
      'Electronics',
    ])
    // Roots with a channel code land on the channel landing page; roots
    // without one keep the /c/<slug> results page (minihome parity).
    expect(wrapper.findAll('.category-nav__link').map((link) => link.attributes('href'))).toEqual([
      '/minihome/UK-Mini-HP-Home-Living',
      '/c/electronics',
    ])
  })

  it('keeps the notice strip without the removed download and delivery lines', () => {
    const wrapper = mountHeader()
    const text = wrapper.get('.top-strip').text()
    expect(text).not.toContain('Download Joybuy')
    expect(text).not.toContain('Same-day')
    expect(text).toContain('Unlock Your Welcome Offers')
  })

  // 需求 17.1（纠正 16.1）：政策/内容页只隐藏一级品类行；【分类】按钮保留且下拉可用
  // （真站 /help/privacy-policy 存档：分类按钮 ×1、品类行 ×0）。
  it('hides only the category row with hideCategoryNav but keeps the trigger', async () => {
    const wrapper = mountHeader({ hideCategoryNav: true })
    expect(wrapper.find('.categories-button').exists()).toBe(true)
    expect(wrapper.find('.categories-anchor').exists()).toBe(true)
    expect(wrapper.find('.category-nav').exists()).toBe(false)
    expect(wrapper.findAll('.category-nav__link')).toHaveLength(0)
    // 其余元素与首页一致：黑条（语言）、logo、搜索、登录/申请店铺/购物车。
    expect(wrapper.get('.top-strip').exists()).toBe(true)
    expect(wrapper.get('#locale-select').exists()).toBe(true)
    expect(wrapper.get('.brand__logo').attributes('src')).toBe('/images/logo.png')
    expect(wrapper.get('form.search').exists()).toBe(true)
    expect(wrapper.get('.account-nav__apply').exists()).toBe(true)
    expect(wrapper.get('.login-button').exists()).toBe(true)
    expect(wrapper.get('.icon-button--cart').exists()).toBe(true)
    // 【分类】按钮在政策页可点开下拉。
    await wrapper.get('.categories-button').trigger('click')
    expect(wrapper.find('.category-panel').exists()).toBe(true)
  })

  it('keeps only the language selector in the top strip (requirement 11-4)', () => {
    const wrapper = mountHeader()
    expect(wrapper.find('#market-select').exists()).toBe(false)
    expect(wrapper.find('#locale-select').exists()).toBe(true)
  })

  it('opens the categories panel from the trigger button and on hover', async () => {
    const wrapper = mountHeader()
    expect(wrapper.find('.category-panel').exists()).toBe(false)
    // Click opens (touch users); closing happens via the close button or
    // mouse-leave, matching the real site's hover dropdown.
    await wrapper.get('.categories-button').trigger('click')
    expect(wrapper.find('.category-panel').exists()).toBe(true)

    await wrapper.get('.categories-anchor').trigger('mouseenter')
    expect(wrapper.find('.category-panel').exists()).toBe(true)
  })

  it('shows the cart count badge only when items exist', async () => {
    expect(mountHeader().find('.cart-count').exists()).toBe(false)

    const withCart = mountHeader({ cartCount: 3 })
    expect(withCart.get('.cart-count').text()).toBe('3')
    expect(withCart.get('.icon-button--cart').attributes('aria-label')).toBe('Cart, 3 items')

    const capped = mountHeader({ cartCount: 150 })
    expect(capped.get('.cart-count').text()).toBe('99+')
    expect(capped.get('.icon-button--cart').attributes('aria-label')).toBe('Cart, 99+ items')
  })

  it('keeps every interactive control reachable at 44px minimum height', () => {
    const wrapper = mountHeader()
    for (const control of wrapper.findAll('input, button, a')) {
      const minHeight = getComputedStyle(control.element).minHeight
      // jsdom computes styles from scoped CSS in the component source; the
      // design rule is 44px minimum for all interactive elements.
      if (minHeight && minHeight !== 'auto') {
        expect(Number.parseFloat(minHeight)).toBeGreaterThanOrEqual(44)
      }
    }
  })

  it('closes the account menu on an outside pointerdown and on Escape', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    const trigger = wrapper.get('button[aria-label="My account"]')
    expect(trigger.attributes('aria-expanded')).toBe('false')

    await trigger.trigger('click')
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
    expect(trigger.attributes('aria-expanded')).toBe('true')

    // Clicking anywhere outside the menu (here: the page body) dismisses it.
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(wrapper.find('.account-menu__panel').exists()).toBe(false)
    expect(trigger.attributes('aria-expanded')).toBe('false')

    // The trigger toggles open again, and Escape closes + restores focus.
    await trigger.trigger('click')
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()
    expect(wrapper.find('.account-menu__panel').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)

    // Clicking inside the panel does not dismiss it before the link runs.
    await trigger.trigger('click')
    wrapper
      .get('.account-menu__panel')
      .element.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
  })

  // -------------------------------------------------------------------------
  // Top-right shop application entry (requirement 12.2): the deliver-to pin
  // and its drawer trigger are gone; the entry mirrors the application status
  // carried by the buyer session payload (no extra fetch, no flash).
  // -------------------------------------------------------------------------
  it('removes the deliver-to entry and its drawer trigger entirely', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()

    expect(wrapper.find('.account-nav__deliver').exists()).toBe(false)
    expect(wrapper.find('.address-drawer').exists()).toBe(false)
    expect(wrapper.find('.account-nav__apply').exists()).toBe(true)
  })

  it('shows the apply link that returns from sign-in when signed out', () => {
    const wrapper = mountHeader()
    const entry = wrapper.get('.account-nav__apply')
    expect(entry.text()).toBe('Apply for a shop')
    expect(entry.element.tagName).toBe('A')
    expect(entry.attributes('href')).toBe('/auth/login?next=%2Faccount%2Fapply-shop')
  })

  it('links to the apply-shop page without an application', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()

    const entry = wrapper.get('.account-nav__apply')
    expect(entry.text()).toBe('Apply for a shop')
    expect(entry.element.tagName).toBe('A')
    expect(entry.attributes('href')).toBe('/account/apply-shop')
  })

  it('keeps the apply-shop link while the application is PENDING or REJECTED', async () => {
    __setAuthenticated(true)
    __setApplicationStatus('PENDING')
    const pending = mountHeader()
    await settle()
    expect(pending.get('.account-nav__apply').text()).toBe('Apply for a shop')
    expect(pending.get('.account-nav__apply').attributes('href')).toBe('/account/apply-shop')

    __setApplicationStatus('REJECTED')
    const rejected = mountHeader()
    await settle()
    expect(rejected.get('.account-nav__apply').text()).toBe('Apply for a shop')
    expect(rejected.get('.account-nav__apply').attributes('href')).toBe('/account/apply-shop')
  })

  it('switches to the Seller console action when the application is APPROVED', async () => {
    __setAuthenticated(true)
    __setApplicationStatus('APPROVED')
    const assign = vi.fn()
    window.location.assign = assign
    vi.stubGlobal(
      '$fetch',
      vi.fn(async (url) => {
        if (String(url).includes('buyer/session')) return { csrf_token: 'csrf-token' }
        if (String(url).includes('merchant-console-session')) {
          return { url: 'http://localhost:5174/' }
        }
        return {}
      }),
    )
    const wrapper = mountHeader()
    await settle()

    const entry = wrapper.get('.account-nav__apply')
    expect(entry.text()).toBe('Switch to Seller console')
    expect(entry.element.tagName).toBe('BUTTON')
    expect(entry.attributes('href')).toBeUndefined()

    await entry.trigger('click')
    await settle()
    expect(assign).toHaveBeenCalledWith('http://localhost:5174/')
  })

  it('drops the seller entry from the avatar dropdown (requirement 12.2)', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    await wrapper.get('button[aria-label="My account"]').trigger('click')
    await settle()

    const items = wrapper.findAll('.account-menu__item')
    // 需求 C（2026-11-28）：EMAIL 账号在【退出登录】上方多一行【修改密码】，
    // 因此缺省（无 auth_provider → EMAIL 语义）是 6 行。
    expect(items.map((item) => item.text().trim())).toEqual([
      'My orders',
      'Reviews and Q&A',
      'Favourites',
      'Addresses',
      'Change password',
      'Sign out',
    ])
    expect(wrapper.find('.account-menu__panel').text()).not.toContain('Apply for a shop')
    expect(wrapper.find('.account-menu__panel').text()).not.toContain('Merchant Center')
  })

  // 需求 C（2026-11-28）：OAuth 渠道（GOOGLE/FACEBOOK）账号没有平台密码，
  // 下拉不显示【修改密码】——此时 5 行；点其它行（链接行 + 头像/用户区块）不报错。
  // 注：不点【退出登录】，它的 handler 走 navigateTo 重定向到登录页。
  it('hides the change-password row for OAuth accounts (5 rows)', async () => {
    __setAuthenticated(true)
    __setAuthProvider('GOOGLE')
    const wrapper = mountHeader()
    await settle()
    await wrapper.get('.account-menu').trigger('mouseenter')
    await settle()

    const panel = wrapper.get('.account-menu__panel')
    const rows = wrapper.findAll('.account-menu__item')
    expect(rows.length).toBe(5)
    expect(rows.map((row) => row.text().trim())).toEqual([
      'My orders',
      'Reviews and Q&A',
      'Favourites',
      'Addresses',
      'Sign out',
    ])
    expect(panel.text()).not.toContain('Change password')
    expect(wrapper.find('[data-testid="account-menu-changePassword"]').exists()).toBe(false)
    // 修改密码弹窗也不应被打开（触发不了不存在的入口）。
    expect(wrapper.find('.pwd-modal').exists()).toBe(false)

    // 其余行照常可点：链接行不抛错、行结构完好（文字 + 右侧 icon）。
    for (const row of rows) {
      if (row.classes().includes('account-menu__item--sign-out')) continue
      await row.trigger('click')
      expect(row.find('.account-menu__icon').exists()).toBe(true)
    }
  })

  // -------------------------------------------------------------------------
  // 需求 13.5-5/6：头像 hover 即展开、移出 ~200ms 延迟关闭；面板用户行 =
  // 笑脸头像 + display_name；菜单行右侧带线性 icon。
  // -------------------------------------------------------------------------
  it('opens the account menu on hover and closes it ~200ms after mouse-leave', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    expect(wrapper.find('.account-menu__panel').exists()).toBe(false)

    await wrapper.get('.account-menu').trigger('mouseenter')
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)

    await wrapper.get('.account-menu').trigger('mouseleave')
    // 延迟关闭窗口内仍打开（防误移出）。
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
    await new Promise((resolve) => setTimeout(resolve, 260))
    expect(wrapper.find('.account-menu__panel').exists()).toBe(false)

    // 重新 hover 前 click 触发器仍可开合（触屏路径不回归）。
    await wrapper.get('button[aria-label="My account"]').trigger('click')
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
  })

  it('shows the smiley avatar and the backend display_name in the menu header', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    await wrapper.get('.account-menu').trigger('mouseenter')
    await settle()

    const panel = wrapper.get('.account-menu__panel')
    // 笑脸占位 SVG（真站 viewBox 0 0 56 56 内联复刻）：触发器 + 用户行各一个。
    expect(wrapper.findAll('svg[viewBox="0 0 56 56"]').length).toBeGreaterThanOrEqual(2)
    expect(panel.get('.account-menu__name').text()).toBe('user4323txlb')
    // 每行左右对齐：文字在前、icon 在后。
    // 需求 C：缺省 session（无 auth_provider → EMAIL）共 6 行（含【修改密码】）。
    const rows = wrapper.findAll('.account-menu__item')
    expect(rows.length).toBe(6)
    for (const row of rows) {
      expect(row.get('.account-menu__label').text().length).toBeGreaterThan(0)
      expect(row.find('.account-menu__icon').exists()).toBe(true)
    }
  })

  it('links the avatar + display_name block to /account and closes the menu (requirement 22.3-1)', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    await wrapper.get('.account-menu').trigger('mouseenter')
    await settle()

    const profileLink = wrapper.get('[data-testid="account-menu-profile"]')
    expect(profileLink.element.tagName).toBe('A')
    expect(profileLink.attributes('href')).toBe('/account')
    expect(profileLink.classes()).toContain('account-menu__user')
    // 头像 + 用户名整块都在链接内。
    expect(profileLink.find('.account-menu__avatar').exists()).toBe(true)
    expect(profileLink.get('.account-menu__name').text()).toBe('user4323txlb')

    await profileLink.trigger('click')
    await settle()
    expect(wrapper.find('.account-menu__panel').exists()).toBe(false)
  })

  // -------------------------------------------------------------------------
  // 需求 17.3：右上角顺序按真站 = 申请店铺 → 购物车 → 登录/头像。真站四份 SSR
  // 存档（2026-11-19）jdi-header-user-info 内 cartEntry(购物车)在前、
  // userInfoButton(头像)在后，CSS 无 row-reverse/order → 用 DOM 顺序实现。
  // -------------------------------------------------------------------------
  it('orders the top-right actions apply → cart → sign-in when signed out', () => {
    const wrapper = mountHeader()
    const nodes = wrapper.get('.account-nav').element.children
    expect(nodes[0].className).toContain('account-nav__apply')
    expect(nodes[1].className).toContain('icon-button--cart')
    expect(nodes[2].className).toContain('login-button')
  })

  it('orders the top-right actions apply → cart → account menu when signed in', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    const nodes = wrapper.get('.account-nav').element.children
    expect(nodes[0].className).toContain('account-nav__apply')
    expect(nodes[1].className).toContain('icon-button--cart')
    expect(nodes[2].className).toContain('account-menu')
  })

  // -------------------------------------------------------------------------
  // 需求 17.2：下拉一比一复刻真站 userInfoButton_meListDropdownLayer（CSS 原文）。
  // 结构断言（行数 / icon 右位 / 退出登录灰化类 / 用户区元素）；尺寸与颜色
  // （面板 280、行 56px、16px 字号、#6e7078）由 Playwright 计算样式实测
  // （vitest happy-dom + css:false 不注入 SFC 样式，computed style 全空）。
  // -------------------------------------------------------------------------
  it('renders the dropdown rows with trailing icons and the gray sign-out class', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    await wrapper.get('.account-menu').trigger('mouseenter')
    await settle()

    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
    expect(wrapper.find('.account-menu__user').exists()).toBe(true)
    expect(wrapper.find('.account-menu__name').exists()).toBe(true)

    const rows = wrapper.findAll('.account-menu__item')
    // 需求 C：EMAIL 账号多一行【修改密码】→ 6 行（4 个链接行 + 修改密码 + 退出登录）。
    expect(rows.length).toBe(6)
    expect(rows.map((row) => row.text().trim())).toEqual([
      'My orders',
      'Reviews and Q&A',
      'Favourites',
      'Addresses',
      'Change password',
      'Sign out',
    ])
    for (const row of rows) {
      // icon 右对齐：icon 是行内最后一个子元素（文字在前，CSS space-between）。
      const last = row.element.children[row.element.children.length - 1]
      expect(last.className).toContain('account-menu__icon')
    }
    // 退出登录灰化（17.2-5）：独立 modifier 承载 #6e7078（Playwright 验色）。
    expect(wrapper.find('.account-menu__item--sign-out').exists()).toBe(true)
  })
})
