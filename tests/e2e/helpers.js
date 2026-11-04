// Dev-mode hydration can swallow the first click on an SSR page; retry a
// click until its expected effect appears (production builds hydrate
// synchronously and are not affected).
export async function clickUntil(page, locator, effect, { attempts = 5, delayMs = 800 } = {}) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    await locator.click().catch(() => {})
    try {
      await effect(page, { timeout: delayMs })
      return true
    } catch {
      // effect not observed yet; click again
    }
  }
  await effect(page, { timeout: 3000 })
  return false
}
