import {
  MOBILE_BYPASS_KEY,
  MOBILE_OVERRIDE_KEY,
  desktopCounterpartHost,
  mobileCounterpartHost,
  shouldAutoSwitch,
} from '../composables/useMobileView'

// ADR 0001: width-threshold auto switch between the desktop host and the m.
// host (<=768px -> m., >768px -> desktop), both directions keeping the full
// path. Manual footer choices (localStorage) permanently beat this rule and
// `?nomobile=1` / navigator.webdriver (Playwright e2e) disable it entirely.
export default defineNuxtPlugin(() => {
  if (typeof window === 'undefined') return

  const url = new URL(window.location.href)
  // navigator.webdriver (Playwright e2e) disables the auto switch so the
  // foundation/purchase-funnel specs can drive 375/390px viewports on the
  // desktop host without being redirected. `?mobile-auto=1` is the explicit
  // verification hook that overrides the webdriver guard for smoke tests.
  const forced = url.searchParams.get('mobile-auto') === '1'
  if (navigator.webdriver && !forced) return

  const { isMobileHost } = useMobileView()

  // Remember a ?nomobile=1 bypass for the whole tab session.
  if (url.searchParams.get('nomobile') === '1') {
    try {
      window.sessionStorage.setItem(MOBILE_BYPASS_KEY, '1')
    } catch {
      // ignore
    }
    url.searchParams.delete('nomobile')
    window.history.replaceState(null, '', url.href)
  }

  let bypass = false
  try {
    bypass = window.sessionStorage.getItem(MOBILE_BYPASS_KEY) === '1'
  } catch {
    bypass = false
  }

  function overrideValue() {
    try {
      return window.localStorage.getItem(MOBILE_OVERRIDE_KEY)
    } catch {
      return null
    }
  }

  function check() {
    if (document.hidden) return
    const mode = shouldAutoSwitch({
      width: window.innerWidth,
      isMobileHost: isMobileHost.value,
      override: overrideValue(),
      bypass,
    })
    if (!mode) return
    // Reload on the counterpart host; the m. host renders the mobile layout
    // via the global route middleware, so no client-side layout hop needed.
    const targetHost =
      mode === 'mobile'
        ? mobileCounterpartHost(window.location.host)
        : desktopCounterpartHost(window.location.host)
    if (!targetHost) return
    const { pathname, search, hash } = window.location
    window.location.assign(`${window.location.protocol}//${targetHost}${pathname}${search}${hash}`)
  }

  let timer = null
  window.addEventListener('resize', () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(check, 150)
  })
  check()
})
