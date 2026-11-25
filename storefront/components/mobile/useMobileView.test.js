import { describe, expect, it } from 'vitest'

import { MOBILE_WIDTH_THRESHOLD, shouldAutoSwitch } from '../../composables/useMobileView'

// ADR 0001 auto-switch rule: <=768 on desktop -> mobile, >768 on m. ->
// desktop; manual override and the ?nomobile=1 bypass always win.
describe('shouldAutoSwitch', () => {
  it('jumps to mobile at or below the threshold on the desktop host', () => {
    expect(
      shouldAutoSwitch({
        width: MOBILE_WIDTH_THRESHOLD,
        isMobileHost: false,
        override: null,
        bypass: false,
      }),
    ).toBe('mobile')
    expect(
      shouldAutoSwitch({
        width: MOBILE_WIDTH_THRESHOLD - 1,
        isMobileHost: false,
        override: null,
        bypass: false,
      }),
    ).toBe('mobile')
  })

  it('stays on the desktop host above the threshold', () => {
    expect(
      shouldAutoSwitch({
        width: MOBILE_WIDTH_THRESHOLD + 1,
        isMobileHost: false,
        override: null,
        bypass: false,
      }),
    ).toBe(null)
  })

  it('jumps back to desktop above the threshold on the m. host', () => {
    expect(
      shouldAutoSwitch({
        width: MOBILE_WIDTH_THRESHOLD + 1,
        isMobileHost: true,
        override: null,
        bypass: false,
      }),
    ).toBe('desktop')
    expect(
      shouldAutoSwitch({
        width: MOBILE_WIDTH_THRESHOLD,
        isMobileHost: true,
        override: null,
        bypass: false,
      }),
    ).toBe(null)
  })

  it('never switches when a manual override is stored', () => {
    expect(
      shouldAutoSwitch({ width: 375, isMobileHost: false, override: 'desktop', bypass: false }),
    ).toBe(null)
    expect(
      shouldAutoSwitch({ width: 1200, isMobileHost: true, override: 'mobile', bypass: false }),
    ).toBe(null)
  })

  it('never switches when the nomobile bypass is active', () => {
    expect(
      shouldAutoSwitch({ width: 375, isMobileHost: false, override: null, bypass: true }),
    ).toBe(null)
  })
})
