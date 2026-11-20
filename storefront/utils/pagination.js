// Pager page list (需求 14.7): mirrors the real Joybuy /s pager windows
// (measured 2026-11-20 in var/align_search_20261120/measure_real2.json +
// measure_real3/pager range runs). The source site always renders 5 number
// slots + first/last with an ellipsis:
//   page 1..4 of 34  → 1 2 3 4 5 … 34
//   page 5..30       → 1 … 4 5 6 … 34   (current ±1)
//   page 31..34      → 1 … 30 31 32 33 34
// Pure helper so the listing component stays thin and this is unit-testable.

const EDGE = 4

/**
 * @param {number} current 1-based current page
 * @param {number} total total page count
 * @returns {Array<number|'gap'>}
 */
export function buildPageList(current, total) {
  const last = Math.max(1, Math.floor(total))
  const page = Math.min(Math.max(1, Math.floor(current)), last)
  // Small page counts render every number (no ellipsis).
  if (last <= 7) return Array.from({ length: last }, (_, index) => index + 1)

  // Near the start: first five pages, then the last page.
  if (page <= EDGE) return [1, 2, 3, 4, 5, 'gap', last]
  // Near the end: first page, then the last five pages.
  if (page >= last - EDGE + 1) {
    return [1, 'gap', last - 4, last - 3, last - 2, last - 1, last]
  }
  // In the middle: first, one sibling either side, last.
  return [1, 'gap', page - 1, page, page + 1, 'gap', last]
}
