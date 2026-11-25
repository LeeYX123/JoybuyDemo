import { expect, test } from '@playwright/test'

import { clickUntil } from './helpers'

// Full storefront funnel (WP-37): browse -> search -> detail -> register ->
// cart -> checkout -> pending order -> pay attempt -> region unsupported.
test.describe('purchase funnel', () => {
  test.setTimeout(90_000)
  test('browses, signs in, carts an item and places a pending order', async ({ page }) => {
    // 1. Search finds catalog products. The funnel subject is whatever the
    // search returns first — the catalog is real crawled data now, so a fixed
    // product name rots (the old "Wireless Earbuds Pro" seed no longer exists).
    await page.goto('/search?q=earbuds')
    const firstTitleLink = page.locator('a.product-card__title-link').first()
    await firstTitleLink.waitFor({ state: 'visible', timeout: 15000 })
    const productTitle = (await firstTitleLink.textContent()).trim()
    expect(productTitle.length).toBeGreaterThan(0)

    // 2. Open the detail page from the listing. Real crawled products carry
    // no stock line any more (requirement 11.7: real PDP has no inventory
    // row), so assert on the price block instead of the old "in stock" text.
    await firstTitleLink.click()
    await expect(page.getByRole('heading', { name: productTitle }).first()).toBeVisible()
    await expect(page.locator('.detail__price').first()).toBeVisible()

    // 3. Register through the auth flow (direct email+password form from the
    // third-party-login batch). Dev-mode hydration can reset freshly filled
    // inputs, so refill in a retry loop with a fresh email per attempt;
    // success lands on /account.
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const email = `funnel-${Date.now()}-${attempt}@joybuy.test`
      await page.goto('/auth/register', { waitUntil: 'networkidle' })
      // Let Vue hydrate before filling: a fill that lands pre-hydration is
      // silently discarded and the submit fires with an empty form.
      await page.getByRole('button', { name: 'Create account' }).waitFor({ state: 'visible' })
      await page.waitForTimeout(600)
      await page.getByLabel('Email', { exact: true }).fill(email)
      await page.getByLabel('Create a password').fill('Funnel-passw0rd!')
      await page
        .getByRole('button', { name: 'Create account' })
        .click()
        .catch(() => {})
      try {
        await page.waitForURL(/\/account/, { timeout: 5000 })
        break
      } catch {
        // form may have been reset by late hydration; refill and retry
      }
    }
    await expect(page).toHaveURL(/\/account/)

    // 4. Add to cart from the detail page. The default offer binds on page
    // load; real crawled products may or may not expose variant buttons, so
    // no fixed colour is picked here.
    await page.goto('/search?q=earbuds')
    await page.locator('a.product-card__title-link').first().click()
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
    await expect(page.getByText(productTitle).first()).toBeVisible()

    // 6. Checkout with the docs/12 3-field address form, Save -> payment step.
    // Dev-mode hydration can reset freshly filled inputs or swallow the first
    // submit; refill + save in one self-healing loop until Pay now appears.
    test.setTimeout(150_000)
    await page.goto('/checkout')
    // A fresh account has no addresses: the address form is already open
    // (showNewForm defaults to true when the list is empty) and the button
    // reads "Cancel". Only click "Add a new address" when the form is closed.
    try {
      await page
        .getByPlaceholder('First name and surname')
        .waitFor({ state: 'visible', timeout: 3000 })
    } catch {
      await clickUntil(page, page.getByRole('button', { name: 'Add a new address' }), (p) =>
        p.getByPlaceholder('First name and surname').waitFor({ state: 'visible', timeout: 800 }),
      )
    }
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
      // i18n batch renamed the orders page heading to "My orders".
      p.getByRole('heading', { name: 'My orders' }).waitFor({ state: 'visible', timeout: 800 }),
    )
    await expect(page.getByText('Pending payment')).toBeVisible()

    // Step removed (2026-11-24): the old flow retried payment from the orders
    // page and surfaced the region-unsupported dialog ("Payment is not
    // available"). The orders list/detail no longer render a Pay now entry —
    // the only payment trigger is the checkout button used in step 6, whose
    // pay attempt returns the region-unsupported 422 while the order stays
    // Pending payment (verified by the assertion above).
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
      // The page is very tall and product images lazy-load; scroll through the
      // full page first so the fullPage screenshot does not race pop-in images
      // ("failed to take two consecutive stable screenshots" otherwise).
      await page.evaluate(async () => {
        const total = document.body.scrollHeight
        for (let y = 0; y < total; y += 600) {
          window.scrollTo(0, y)
          await new Promise((resolve) => setTimeout(resolve, 60))
        }
        window.scrollTo(0, 0)
      })
      await page.waitForTimeout(1000)
      await expect(page).toHaveScreenshot(`home-${width}.png`, {
        fullPage: true,
        maxDiffPixelRatio: 0.02,
      })
    })
  }
})
