import { expect, test } from '@playwright/test'

test.describe('frontend foundations', () => {
  test('storefront renders the published CMS home page', async ({ page }) => {
    const response = await page.goto('/')

    expect(response?.status()).toBe(200)
    // The campaign floor has no heading (docs/12); its tiles carry the links.
    await expect(page.getByRole('link', { name: /Welcome Offers/ })).toBeVisible()
    // Product floors live inside the Bestsellers floor (category tabs), not
    // as standalone headings.
    await expect(page.getByRole('heading', { name: /Bestsellers|畅销榜单/ })).toBeVisible()
    await expect(page.locator('.home-bestsellers__tab').first()).toBeVisible()
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute(
      'href',
      '#main-content',
    )
  })

  test('storefront exposes the global 404 page', async ({ page }) => {
    const response = await page.goto('/missing-route')

    expect(response?.status()).toBe(404)
    await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  })

  test('storefront layout holds at the four acceptance widths', async ({ page }) => {
    // docs/01 §9: 1440 / 1280 / 390 / 375 must show header, footer and main
    // content without horizontal overflow (structural, not pixel-exact).
    for (const width of [1440, 1280, 390, 375]) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto('/')

      await expect(page.locator('.site-header')).toBeVisible()
      await expect(page.locator('.site-footer')).toBeVisible()
      await expect(page.locator('#main-content')).toBeVisible()

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(1)
    }
  })

  test('admin redirects unauthenticated visitors to staff login', async ({ page }) => {
    const response = await page.goto('http://127.0.0.1:5173/')

    expect(response?.status()).toBe(200)
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole('heading', { name: '平台管理登录' })).toBeVisible()
    await expect(page.getByRole('link', { name: '跳转到主要内容' })).toHaveAttribute(
      'href',
      '#main-content',
    )
  })

  test('admin router renders its 404 state after staff sign-in', async ({ page }) => {
    await page.goto('http://127.0.0.1:5173/login')
    await page.fill('input[type="email"]', 'auditor@joybuy.test')
    await page.fill('input[type="password"]', 'Joybuy-Staff-2026!')
    await page.click('button[type="submit"]')
    await expect(page.getByRole('heading', { name: '仪表盘' })).toBeVisible({ timeout: 10000 })

    const response = await page.goto('http://127.0.0.1:5173/missing-route')
    expect(response?.status()).toBe(200)
    await expect(page.getByRole('heading', { name: '页面不存在。' })).toBeVisible()
  })
})
