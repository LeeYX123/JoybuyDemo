import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

// Shared instance so the test can drive what the component receives.
const auth = {
  login: vi.fn(),
  loadSession: vi.fn(async () => ({
    authenticated: false,
    staff: null,
    permissions: [],
    csrf_token: 'test-token',
  })),
  isAuthenticated: ref(false),
  session: ref({ authenticated: false, staff: null, permissions: [], csrf_token: 'test-token' }),
}

vi.mock('@/composables/useStaffAuth', () => ({
  useStaffAuth: () => auth,
}))

import LoginView from './LoginView.vue'

describe('LoginView', () => {
  it('logs in with email and password only and redirects to the dashboard', async () => {
    auth.login.mockResolvedValue({ authenticated: true })

    const router = createRouter({
      history: createWebHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push('/')
    const wrapper = mount(LoginView, { global: { plugins: [router] } })

    await wrapper.find('input[type="email"]').setValue('admin@joybuy.test')
    await wrapper.find('input[type="password"]').setValue('Joybuy-Admin-2026!')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(auth.login).toHaveBeenCalledWith('admin@joybuy.test', 'Joybuy-Admin-2026!')
    // 登录页只有邮箱和密码两个输入框，不再出现验证器动态码。
    expect(wrapper.findAll('input')).toHaveLength(2)
    expect(wrapper.find('input[autocomplete="one-time-code"]').exists()).toBe(false)
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('shows a friendly error when credentials are wrong', async () => {
    auth.login.mockRejectedValue(
      Object.assign(new Error('The email or password is incorrect.'), {
        code: 'STAFF_LOGIN_FAILED',
      }),
    )

    const router = createRouter({
      history: createWebHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    const wrapper = mount(LoginView, { global: { plugins: [router] } })

    await wrapper.find('input[type="email"]').setValue('admin@joybuy.test')
    await wrapper.find('input[type="password"]').setValue('wrong-password')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('邮箱或密码不正确。')
    expect(router.currentRoute.value.path).toBe('/')
  })
})
