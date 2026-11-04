import { expect, test } from '@playwright/test'

// Buyer auth happy path against the dev-mode verification channel.
// The backend returns test_code in development so the code is auto-filled.
test.describe('buyer auth', () => {
  test('register, land on account and see signed-in header', async ({ page }) => {
    await page.goto('/auth/register')

    await page.getByLabel('Email address').fill(`e2e-${Date.now()}@joybuy.test`)
    await page.getByRole('button', { name: 'Send code' }).click()

    await expect(page.getByText('Development mode')).toBeVisible()

    await page.getByLabel('Password').fill('E2E-passw0rd!')
    await page.getByRole('button', { name: 'Create account' }).click()

    await expect(page.getByRole('heading', { name: 'Your account' })).toBeVisible()
    await expect(page.getByText(/Signed in as/)).toBeVisible()
    await expect(page.getByRole('link', { name: 'My account' })).toBeVisible()
  })

  test('login with a bad password shows a clear error', async ({ page }) => {
    await page.goto('/auth/login')
    await page.getByLabel('Email or phone number').fill('nobody@joybuy.test')
    await page.getByLabel('Password').fill('wrong-password-1')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page.getByRole('alert')).toBeVisible()
  })

  test('forgot password is an honest placeholder', async ({ page }) => {
    await page.goto('/auth/forgot-password')
    await expect(
      page.getByText('Password reset by email is not available in this demo build yet.'),
    ).toBeVisible()
  })
})
