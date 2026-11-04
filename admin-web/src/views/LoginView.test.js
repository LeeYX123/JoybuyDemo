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
  it('shows a TOTP field after a STAFF_TOTP_REQUIRED error', async () => {
    auth.login.mockImplementation(async () => {
      throw Object.assign(new Error('A current TOTP code is required.'), {
        code: 'STAFF_TOTP_REQUIRED',
      })
    })

    const router = createRouter({
      history: createWebHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    const wrapper = mount(LoginView, { global: { plugins: [router] } })

    await wrapper.find('input[type="email"]').setValue('admin@joybuy.test')
    await wrapper.find('input[type="password"]').setValue('Secret-123!')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('验证器动态码')
    expect(wrapper.find('input[autocomplete="one-time-code"]').exists()).toBe(true)
  })
})
