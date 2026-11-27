import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { messages } from '../locales/messages'

// 登录页状态机（docs/17）：identifier → lookup → password / register。
// 组件只依赖三个 composable，测试把它们整体 mock，出网为零。
const route = vi.hoisted(() => ({ query: {} }))

vi.mock('#imports', () => ({
  navigateTo: vi.fn(),
  useHead: vi.fn(),
  useRoute: () => ({ query: route.query }),
  // 组件在 SSR 阶段 await 一次渠道拉取；测试里直接同步执行 handler。
  useAsyncData: async (_key, handler) => ({ data: await handler() }),
}))

const auth = vi.hoisted(() => ({
  isAuthenticated: { value: false },
  login: vi.fn(),
  registerEmail: vi.fn(),
  lookupIdentifier: vi.fn(),
  oauthProviders: { value: [] },
}))

vi.mock('../composables/useBuyerAuth', async () => {
  const { ref } = await import('vue')
  // isAuthenticated 必须是真 ref：组件对它做了 watch。
  auth.isAuthenticated = ref(false)
  return {
    useBuyerAuth: () => ({
      isAuthenticated: auth.isAuthenticated,
      login: auth.login,
      registerEmail: auth.registerEmail,
      lookupIdentifier: auth.lookupIdentifier,
      oauthProviders: auth.oauthProviders,
      loadOAuthProviders: async () => auth.oauthProviders.value,
    }),
  }
})

vi.mock('../composables/useLocale', () => ({
  useLocale: () => ({
    t: (key) => messages.en[key] ?? key,
    locale: 'en',
  }),
}))

const setMarketLocale = vi.fn()
vi.mock('../composables/useMarketLocale', () => ({
  useMarketLocale: () => ({
    marketOption: { name: 'United Kingdom' },
    availableLocales: [{ code: 'en-GB', name: 'English' }],
    localeCode: 'en-GB',
    setMarketLocale,
  }),
}))

const AuthForm = (await import('../components/AuthForm.vue')).default

function mountForm(mode = 'login', providers = []) {
  return mount(AuthForm, {
    props: { mode, providers },
    // 批次 CA：登录页新增 <NuxtLink> 注册入口；测试里用轻量 stub 保持输出干净。
    global: {
      stubs: {
        NuxtLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
      },
    },
  })
}

async function submitIdentifier(wrapper, value = 'buyer@example.test') {
  await wrapper.find('#auth-identifier').setValue(value)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

describe('AuthForm email-first', () => {
  beforeEach(() => {
    auth.isAuthenticated.value = false
    auth.oauthProviders.value = []
    auth.login.mockReset()
    auth.registerEmail.mockReset()
    auth.lookupIdentifier.mockReset()
    route.query = {}
  })

  it('opens on the identifier step without promo banner and with a register entry', () => {
    const wrapper = mountForm()

    expect(wrapper.find('#auth-identifier').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Welcome Offers')
    expect(wrapper.text()).toContain('Create an account')
    expect(wrapper.text()).toContain('Continue')
    expect(wrapper.findAll('[data-testid="oauth-button"]')).toHaveLength(0)
    // 真站没有忘记密码入口
    expect(wrapper.text()).not.toContain('Forgot')
  })

  it('goes to the password step when the identifier exists', async () => {
    auth.lookupIdentifier.mockResolvedValue({ kind: 'EMAIL', exists: true })
    const wrapper = mountForm()

    await submitIdentifier(wrapper)

    expect(auth.lookupIdentifier).toHaveBeenCalledWith('buyer@example.test')
    expect(wrapper.find('#auth-password').exists()).toBe(true)
    expect(wrapper.find('#auth-locked-identifier').attributes('readonly')).toBeDefined()
    expect(wrapper.text()).toContain('Sign in')
  })

  it('goes to the create-account step when the email is unknown', async () => {
    auth.lookupIdentifier.mockResolvedValue({ kind: 'EMAIL', exists: false })
    const wrapper = mountForm()

    await submitIdentifier(wrapper)

    expect(wrapper.text()).toContain('Create your Joybuy account')
    expect(wrapper.find('#auth-register-email').exists()).toBe(true)
    expect(wrapper.find('#auth-register-password').exists()).toBe(true)
    expect(wrapper.text()).toContain('Create account')
  })

  it('refuses an unregistered mobile number with a pointer to email signup', async () => {
    auth.lookupIdentifier.mockResolvedValue({ kind: 'PHONE', exists: false })
    const wrapper = mountForm()

    await submitIdentifier(wrapper, '+447700900123')

    expect(wrapper.find('#auth-register-email').exists()).toBe(false)
    expect(wrapper.text()).toContain('This mobile number is not registered')
  })

  it('renders only providers whose credentials are configured', () => {
    route.query = { next: '/cart' }
    const wrapper = mountForm('login', [
      { provider: 'google', enabled: true, start_url: '/api/v1/auth/buyer/oauth/google/start' },
      {
        provider: 'facebook',
        enabled: false,
        start_url: '/api/v1/auth/buyer/oauth/facebook/start',
      },
    ])

    const buttons = wrapper.findAll('[data-testid="oauth-button"]')
    // Facebook 凭据未配置时按钮整条隐藏；填上凭据（enabled=true）后会自动出现
    expect(buttons).toHaveLength(1)
    expect(buttons[0].text()).toContain('Continue with Google')
    expect(wrapper.text()).not.toContain('Continue with Facebook')
    expect(buttons[0].attributes('href')).toBe('/api/v1/auth/buyer/oauth/google/start?next=%2Fcart')
  })

  it('renders both buttons when both providers are configured', () => {
    const wrapper = mountForm('login', [
      { provider: 'google', enabled: true, start_url: '/api/v1/auth/buyer/oauth/google/start' },
      { provider: 'facebook', enabled: true, start_url: '/api/v1/auth/buyer/oauth/facebook/start' },
    ])

    const buttons = wrapper.findAll('[data-testid="oauth-button"]')
    expect(buttons).toHaveLength(2)
    expect(buttons[1].text()).toContain('Continue with Facebook')
  })

  it('shows the language name (not the country) below the social buttons', () => {
    const wrapper = mountForm('login', [
      { provider: 'google', enabled: true, start_url: '/api/v1/auth/buyer/oauth/google/start' },
    ])

    const region = wrapper.find('.auth-region')
    expect(region.text()).toContain('English')
    expect(region.text()).not.toContain('United Kingdom')
    expect(region.find('svg.auth-region__flag').exists()).toBe(false)
  })

  it('starts directly on the create-account step for /auth/register', () => {
    const wrapper = mountForm('register')

    expect(wrapper.find('#auth-register-email').exists()).toBe(true)
    // 直达注册页的邮箱是可编辑的（不是从 lookup 带过来的锁定值）
    expect(wrapper.find('#auth-register-email').attributes('readonly')).toBeUndefined()
  })

  it('maps an oauth_error from the callback into an inline alert', () => {
    route.query = { oauth_error: 'disabled' }
    const wrapper = mountForm()

    expect(wrapper.find('[role="alert"]').text()).toContain('disabled')
  })
})
