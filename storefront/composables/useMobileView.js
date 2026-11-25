import { computed } from 'vue'
import { useRequestURL } from '#imports'

// ---------------------------------------------------------------------------
// Mobile site (m. host) shared state — ADR 0001.
//
// Same Nuxt app serves the desktop layout on the plain host and the mobile
// layout on the "m." host (dev: m.localhost:3000 resolves to 127.0.0.1, so
// the Nuxt dev server receives the request unchanged). Cookies are host-bound
// (backend sets no Domain attribute), so the m. site intentionally keeps its
// own session/locale — see docs/adr/0001.
//
// Auto-switch behaviour (decided 2026-11-24 grill session):
//   - viewport width <= 768 on the desktop host -> jump to the m. host;
//   - width > 768 on the m. host -> jump back;
//   - both directions keep the full path/query/hash;
//   - a manual footer choice is stored in localStorage and permanently beats
//     the automatic switch until the user switches back by hand;
//   - `?nomobile=1` (or navigator.webdriver, e.g. Playwright e2e) disables
//     the automatic switch only — manual links keep working.
// ---------------------------------------------------------------------------

export const MOBILE_WIDTH_THRESHOLD = 768

// localStorage: manual override ('desktop' | 'mobile'). Null = auto.
export const MOBILE_OVERRIDE_KEY = 'joybuy-view-mode'
// sessionStorage: ?nomobile=1 sets this; auto-switch is skipped for the tab.
export const MOBILE_BYPASS_KEY = 'joybuy-nomobile'

function hostWithoutPort(host) {
  return String(host || '').split(':')[0]
}

// "m."-prefixed counterpart of a host (port preserved). IP literals have no
// mobile form — auto-switch is a no-op there; use m.localhost in dev.
export function mobileCounterpartHost(host) {
  const bare = hostWithoutPort(host)
  if (!bare || bare.startsWith('m.') || /^\d+\.\d+\.\d+\.\d+$/.test(bare)) return null
  return `m.${host}`
}

export function desktopCounterpartHost(host) {
  const bare = hostWithoutPort(host)
  if (bare.startsWith('m.')) return host.slice(2)
  return null
}

/**
 * Shared mobile-view state. SSR-safe: the host comes from useRequestURL().
 */
export function useMobileView() {
  const requestUrl = useRequestURL()
  const isMobileHost = computed(() => hostWithoutPort(requestUrl.host).startsWith('m.'))

  /**
   * Manual switch from the footer links. Stores the override permanently
   * (localStorage) and navigates to the counterpart host keeping everything
   * after the authority part of the URL.
   */
  function switchView(mode) {
    // mode: 'mobile' (desktop -> m.) or 'desktop' (m. -> desktop)
    if (typeof window === 'undefined') return
    const current = window.location.host
    const targetHost =
      mode === 'mobile' ? mobileCounterpartHost(current) : desktopCounterpartHost(current)
    if (!targetHost) return
    try {
      window.localStorage.setItem(MOBILE_OVERRIDE_KEY, mode)
    } catch {
      // storage disabled: still switch, auto rule will re-evaluate
    }
    const { pathname, search, hash } = window.location
    window.location.assign(`${window.location.protocol}//${targetHost}${pathname}${search}${hash}`)
  }

  return { isMobileHost, switchView, mobileCounterpartHost, desktopCounterpartHost }
}

/**
 * Client-side automatic width switch. Used by the client plugin; exported for
 * unit tests.
 */
export function shouldAutoSwitch({ width, isMobileHost, override, bypass }) {
  if (bypass) return null
  if (override === 'desktop' || override === 'mobile') return null
  if (isMobileHost) return width > MOBILE_WIDTH_THRESHOLD ? 'desktop' : null
  return width <= MOBILE_WIDTH_THRESHOLD ? 'mobile' : null
}
