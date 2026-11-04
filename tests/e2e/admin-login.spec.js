import { expect, test } from '@playwright/test'

test.describe('admin platform login', () => {
  test('admin email + password reaches the dashboard', async ({ page }) => {
    await page.goto('http://127.0.0.1:5173/login')

    await page.fill('input[type="email"]', 'admin@joybuy.test')
    await page.fill('input[type="password"]', 'Joybuy-Admin-2026!')
    await page.click('button[type="submit"]')

    const dashboardHeading = page.getByRole('heading', { name: '仪表盘' })
    await expect(dashboardHeading).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('Platform Admin', { exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: '商品目录' })).toBeVisible()

    const managementPages = [
      ['/catalog', '商品目录'],
      ['/reviews', '评价管理'],
      ['/crawlers', '爬取任务'],
      ['/cms', '内容页面'],
      ['/buyers', '买家与订单'],
    ]
    for (const [path, heading] of managementPages) {
      await page.goto(`http://127.0.0.1:5173${path}`)
      await expect(page.getByRole('heading', { name: heading })).toBeVisible()
    }
  })

  test('auditor signs in and sees no Catalog menu', async ({ page }) => {
    await page.goto('http://127.0.0.1:5173/login')
    await page.fill('input[type="email"]', 'auditor@joybuy.test')
    await page.fill('input[type="password"]', 'Joybuy-Staff-2026!')
    await page.click('button[type="submit"]')

    await expect(page.getByRole('heading', { name: '仪表盘' })).toBeVisible({ timeout: 10000 })
    // RBAC: auditor lacks catalog/crawler permissions — menus stay hidden.
    await expect(page.getByRole('link', { name: '商品目录' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: '爬虫任务' })).toHaveCount(0)
  })
})
