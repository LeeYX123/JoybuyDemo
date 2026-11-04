import { expect, test } from '@playwright/test'

import { clickUntil } from './helpers'

// Full storefront funnel (WP-37): browse -> search -> detail -> register ->
// cart -> checkout -> pending order -> pay attempt -> region unsupported.
test.describe('purchase funnel', () => {
  test.setTimeout(90_000)
  test('browses, signs in, carts an item and places a pending order', async ({ page }) => {
    const email = `funnel-${Date.now()}@joybuy.test`

    // 1. Search finds the seeded product.
    await page.goto('/search?q=earbuds')
    await expect(page.getByRole('heading', { name: 'Wireless Earbuds Pro' }).first()).toBeVisible()

    // 2. Open the detail page from the listing.
    await page.getByRole('link', { name: 'Wireless Earbuds Pro' }).first().click()
    await expect(page.getByRole('heading', { name: 'Wireless Earbuds Pro' })).toBeVisible()
    await expect(page.getByText(/in stock/).first()).toBeVisible()

    // 3. Register through the auth flow.
    await page.goto('/auth/register')
    await page.getByLabel('Email address').fill(email)
    await page.getByRole('button', { name: 'Send code' }).click()
    await expect(page.getByText('Development mode')).toBeVisible()
    await page.getByLabel('Password').fill('Funnel-passw0rd!')
    await page.getByRole('button', { name: 'Create account' }).click()
    await expect(page.getByRole('heading', { name: 'Your account' })).toBeVisible()

    // 4. Add to cart from the detail page.
    await page.goto('/search?q=earbuds')
    await page.getByRole('link', { name: 'Wireless Earbuds Pro' }).first().click()
    // Explicitly pick a variant so a specific offer is bound.
    const whiteButton = page.getByRole('button', { name: 'White', exact: true })
    if (await whiteButton.count()) {
      await whiteButton.click()
      await page.waitForTimeout(300)
    }
    page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        console.log('BROWSER-CONSOLE', msg.type(), msg.text().slice(0, 200))
      }
    })
    page.on('response', (response) => {
      if (response.url().includes('/products/')) {
        console.log('DETAIL-DEBUG', response.status(), response.url().slice(0, 120))
      }
    })
    const addBtn = page.getByRole('button', { name: 'Add to cart' })
    await addBtn.waitFor({ state: 'visible' })
    // Dev-mode hydration can race the first click; retry until the cart
    // actually contains the line.
    for (let attempt = 0; attempt < 4; attempt += 1) {
      await addBtn.click().catch(() => {})
      await page.waitForTimeout(1200)
      const cartResponse = await page.request.get('/api/v1/cart')
      const cartBody = await cartResponse.json()
      if ((cartBody.items || []).length > 0) break
    }

    // 5. Cart shows the line (the button label reverts after 2s).
    await page.waitForTimeout(800)
    await page.goto('/cart')
    await expect(page.getByText('Wireless Earbuds Pro')).toBeVisible()

    // 6. Checkout with the docs/12 3-field address form, Save -> payment step.
    // Dev-mode hydration can reset freshly filled inputs or swallow the first
    // submit; refill + save in one self-healing loop until Pay now appears.
    test.setTimeout(150_000)
    await page.goto('/checkout')
    await clickUntil(page, page.getByRole('button', { name: 'Add a new address' }), (p) =>
      p.getByPlaceholder('First name and surname').waitFor({ state: 'visible', timeout: 800 }),
    )
    for (let attempt = 0; attempt < 6; attempt += 1) {
      await page.getByPlaceholder('First name and surname').fill('Funnel Buyer')
      await page.getByPlaceholder('Phone number').fill('+447000000123')
      await page.getByPlaceholder('Address', { exact: true }).fill('10 Downing Street')
      await page.waitForTimeout(700)
      await page
        .getByRole('button', { name: 'Save', exact: true })
        .click()
        .catch(() => {})
      try {
        await page.getByRole('button', { name: 'Pay now' }).waitFor({ timeout: 2500 })
        break
      } catch {
        // form may have been reset by late hydration; refill and retry
      }
    }
    await expect(page.getByRole('button', { name: 'Pay now' })).toBeVisible()
    await clickUntil(page, page.getByRole('button', { name: 'Pay now' }), (p) =>
      p.getByRole('heading', { name: 'Your orders' }).waitFor({ state: 'visible', timeout: 800 }),
    )
    await expect(page.getByText('Pending payment')).toBeVisible()

    // 7. Pay attempt surfaces the region-unsupported business error.
    page.once('dialog', (dialog) => {
      expect(dialog.message()).toContain('Payment is not available')
      dialog.dismiss()
    })
    await page.getByRole('button', { name: 'Pay now' }).click()
  })
})

// Visual baselines (WP-37): fixed Chromium, four acceptance widths.
// First run writes baselines; later runs compare. Update intentionally via
// `playwright test --update-snapshots`.
test.describe('visual baselines', () => {
  const widths = [1440, 1280, 390, 375]

  for (const width of widths) {
    test(`home baseline at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.goto('/')
      // The campaign floor has no heading (docs/12); its tiles carry the links.
      await expect(page.getByRole('link', { name: /Welcome Offers/ })).toBeVisible()
      await expect(page).toHaveScreenshot(`home-${width}.png`, {
        fullPage: true,
        maxDiffPixelRatio: 0.02,
      })
    })
  }
})
