import { describe, expect, it } from 'vitest'

import { buildPageList } from './pagination'

describe('buildPageList', () => {
  it('lists every page without ellipsis for small page counts', () => {
    expect(buildPageList(1, 1)).toEqual([1])
    expect(buildPageList(3, 7)).toEqual([1, 2, 3, 4, 5, 6, 7])
  })

  // Real site (page 1..4 of 34): 1 2 3 4 5 … 34
  it('fills the first five pages near the start', () => {
    for (const page of [1, 2, 3, 4]) {
      expect(buildPageList(page, 34)).toEqual([1, 2, 3, 4, 5, 'gap', 34])
    }
  })

  // Real site page 5 / 10 / 20: 1 … (c-1) c (c+1) … 34
  it('shows one sibling either side in the middle', () => {
    expect(buildPageList(5, 34)).toEqual([1, 'gap', 4, 5, 6, 'gap', 34])
    expect(buildPageList(10, 34)).toEqual([1, 'gap', 9, 10, 11, 'gap', 34])
    expect(buildPageList(20, 34)).toEqual([1, 'gap', 19, 20, 21, 'gap', 34])
  })

  // Real site page 31..33: 1 … 30 31 32 33 34
  it('fills the last five pages near the end', () => {
    for (const page of [31, 32, 33, 34]) {
      expect(buildPageList(page, 34)).toEqual([1, 'gap', 30, 31, 32, 33, 34])
    }
  })

  it('clamps out-of-range input', () => {
    expect(buildPageList(0, 34)).toEqual([1, 2, 3, 4, 5, 'gap', 34])
    expect(buildPageList(99, 34)).toEqual([1, 'gap', 30, 31, 32, 33, 34])
  })
})
