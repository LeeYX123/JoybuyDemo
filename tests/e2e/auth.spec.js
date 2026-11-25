import { expect, test } from '@playwright/test'

// 登录/注册页 email-first（docs/17）：第一屏只收邮箱，后端 lookup 决定进密码页还是注册页。
// 视觉基线：docs/17 §3；这里只覆盖行为，像素比对靠 var/auth_page_20261124/ 的截图。

// 必须等水合完成再填表：SSR 出来的输入框在水合时会被 Vue 接管，
// 过早 fill 会被随后的渲染抹掉（表现为"邮箱为空 + 校验错误"）。
async function gotoHydrated(page, path) {
  await page.goto(path)
  await page.waitForFunction(() => {
    const root = document.getElementById('__nuxt')
    return Boolean(root && root.__vue_app__)
  })
}

test.describe('buyer auth (email-first)', () => {
  test('registers a new email from /auth/register and lands on the account page', async ({
    page,
  }) => {
    const email = `e2e-${Date.now()}@joybuy.test`

    await gotoHydrated(page, '/auth/register')
    await page.locator('#auth-register-email').fill(email)
    await page.locator('#auth-register-password').fill('E2E-passw0rd!')
    await page.getByRole('button', { name: 'Create account' }).click()

    // 账户页没有 "Your account" 标题，认「我的订单」与登出入口（原断言已过期）。
    await expect(page.getByText('My orders')).toBeVisible()
    await expect(page.getByText('Sign out').first()).toBeVisible()

    // 退出登录后必须回到登录页（用户要求）
    await page.getByText('Sign out').first().click()
    await expect(page).toHaveURL(/\/auth\/login/)
  })

  test('an unknown email on /auth/login switches to the create-account step', async ({ page }) => {
    await gotoHydrated(page, '/auth/login')
    await page.locator('#auth-identifier').fill(`unknown-${Date.now()}@joybuy.test`)
    await page.getByRole('button', { name: 'Continue', exact: true }).click()

    await expect(page.getByRole('heading', { name: 'Create your Joybuy account' })).toBeVisible()
    await expect(page.locator('#auth-register-password')).toBeVisible()
    // 从 lookup 带过来的邮箱是锁定态（真站行为），直达注册页才可编辑
    await expect(page.locator('#auth-register-email')).toHaveAttribute('readonly', '')
  })

  test('an existing email goes to the password step and a wrong password shows an alert', async ({
    page,
    context,
  }) => {
    const email = `e2e-login-${Date.now()}@joybuy.test`

    // 先建号，再清 cookie 回到未登录态，用同一邮箱验证「已存在 → 密码步」。
    await gotoHydrated(page, '/auth/register')
    await page.locator('#auth-register-email').fill(email)
    await page.locator('#auth-register-password').fill('E2E-passw0rd!')
    await page.getByRole('button', { name: 'Create account' }).click()
    await expect(page.getByText('My orders')).toBeVisible()

    await context.clearCookies()
    await gotoHydrated(page, '/auth/login')
    await page.locator('#auth-identifier').fill(email)
    await page.getByRole('button', { name: 'Continue', exact: true }).click()

    await expect(page.locator('#auth-password')).toBeVisible()
    await page.locator('#auth-password').fill('wrong-password-1')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
  })

  test('the login page shows Google and Facebook side by side and a language selector', async ({
    page,
  }) => {
    await gotoHydrated(page, '/auth/login')

    // 两个按钮并排出现，不藏在 View more options 后面
    const buttons = page.locator('[data-testid="oauth-button"]')
    await expect(buttons).toHaveCount(2)
    await expect(buttons.nth(0)).toContainText('Continue with Google')
    await expect(buttons.nth(1)).toContainText('Continue with Facebook')

    const google = buttons.nth(0)
    if ((await google.getAttribute('href')) !== null) {
      await expect(google).toHaveAttribute('href', /\/api\/v1\/auth\/buyer\/oauth\/google\/start/)
    }

    // 地区行显示语言名，不再显示国家名/国旗
    const region = page.locator('.auth-region')
    await expect(region).not.toContainText('United Kingdom')
  })
})
