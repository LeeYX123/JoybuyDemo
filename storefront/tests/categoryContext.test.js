import { describe, expect, it } from 'vitest'

import { resolveCategoryContext } from '../utils/categoryContext'

const categories = [
  {
    slug: 'electronics',
    name_zh: '电子产品',
    children: [
      { slug: 'mobile-phones', name_zh: '手机' },
      { slug: 'tablets', name_zh: '平板电脑' },
    ],
  },
  {
    slug: 'pet-supplies',
    name_zh: '宠物用品',
    children: [{ slug: 'cat-food', name_zh: '猫粮' }],
  },
]

describe('resolveCategoryContext', () => {
  it('resolves an L2 slug to its parent root and the child itself', () => {
    const context = resolveCategoryContext(categories, 'mobile-phones')
    expect(context.root?.slug).toBe('electronics')
    expect(context.child?.slug).toBe('mobile-phones')
  })

  it('resolves an L1 slug to that root with no child (nothing selected)', () => {
    const context = resolveCategoryContext(categories, 'electronics')
    expect(context.root?.slug).toBe('electronics')
    // The trail stops at the L1 and the sidebar must not expand children.
    expect(context.child).toBeNull()
  })

  it('returns an empty context for unknown or missing slugs', () => {
    expect(resolveCategoryContext(categories, 'not-a-category')).toEqual({
      root: null,
      child: null,
    })
    expect(resolveCategoryContext(categories, '')).toEqual({ root: null, child: null })
    expect(resolveCategoryContext(undefined, 'electronics')).toEqual({
      root: null,
      child: null,
    })
  })
})
