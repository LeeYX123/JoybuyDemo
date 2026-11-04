import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const cssDir = resolve(dirname(fileURLToPath(import.meta.url)), '../assets/css')

// The four visual acceptance widths from docs/01 §9 must all exist as
// breakpoint tokens so layouts can never drift onto ad-hoc media queries.
describe('design tokens', () => {
  const tokensCss = readFileSync(resolve(cssDir, 'tokens.css'), 'utf-8')

  it('declares the four acceptance breakpoints', () => {
    for (const [token, value] of [
      ['--bp-wide', '90rem'],
      ['--bp-desktop', '80rem'],
      ['--bp-mobile', '24.375rem'],
      ['--bp-mobile-sm', '23.4375rem'],
    ]) {
      expect(tokensCss).toContain(`${token}: ${value}`)
    }
  })

  it('keeps the container capped at the 1440 design width', () => {
    expect(tokensCss).toContain('--container-max: 90rem')
  })

  it('defines a local system font stack with no remote source', () => {
    expect(tokensCss).toContain('--font-stack:')
    expect(tokensCss).not.toMatch(/url\(\s*['"]?https?:/)
    expect(tokensCss).not.toContain('@font-face')
  })

  it('never references an external CDN in any stylesheet', () => {
    for (const name of ['tokens.css', 'base.css', 'main.css']) {
      const css = readFileSync(resolve(cssDir, name), 'utf-8')
      expect(css).not.toMatch(/https?:\/\//)
    }
  })
})
