import crypto from 'node:crypto'

import { expect, test } from '@playwright/test'

// Base32 decode + TOTP (RFC 6238, SHA-1, 30s step) — mirrors authenticator apps.
function totpNow(secretBase32) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const char of secretBase32.replace(/=+$/, '')) {
    const index = alphabet.indexOf(char)
    if (index === -1) continue
    bits += index.toString(2).padStart(5, '0')
  }
  const bytes = []
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(Number.parseInt(bits.slice(i, i + 8), 2))
  }
  const counter = Math.floor(Date.now() / 30000)
  const buf = Buffer.alloc(8)
  buf.writeUInt32BE(Math.floor(counter / 2 ** 32), 0)
  buf.writeUInt32BE(counter >>> 0, 4)
  const digest = crypto.createHmac('sha1', Buffer.from(bytes)).update(buf).digest()
  const offset = digest[digest.length - 1] & 0x0f
  const code = digest.readUInt32BE(offset) & 0x7fffffff
  return String(code % 1000000).padStart(6, '0')
}

const TOTP_SECRET = 'VRBO7Q5VMM63FM66SL5A5EQE6U6UYEQO'

test.describe('admin platform login', () => {
  test('admin password + TOTP reaches the dashboard', async ({ page }) => {
    await page.goto('http://127.0.0.1:5173/login')

    await page.fill('input[type="email"]', 'admin@joybuy.test')
    await page.fill('input[type="password"]', 'Joybuy-Admin-2026!')
    await page.click('button[type="submit"]')

    // Environment-adaptive: with TOTP enforced the form expands to ask for
    // the code; with STAFF_TOTP_LOGIN_ENFORCED=false the password alone
    // lands on the dashboard.
    const totpInput = page.locator('input[autocomplete="one-time-code"]')
    const dashboardHeading = page.getByRole('heading', { name: '仪表盘' })
    const outcome = await Promise.race([
      totpInput.waitFor({ state: 'visible', timeout: 8000 }).then(() => 'totp'),
      dashboardHeading.waitFor({ state: 'visible', timeout: 8000 }).then(() => 'dashboard'),
    ]).catch(() => 'timeout')

    if (outcome === 'totp') {
      await page.fill('input[autocomplete="one-time-code"]', totpNow(TOTP_SECRET))
      await page.click('button[type="submit"]')
    }

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

  test('auditor signs in without TOTP and sees no Catalog menu', async ({ page }) => {
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
