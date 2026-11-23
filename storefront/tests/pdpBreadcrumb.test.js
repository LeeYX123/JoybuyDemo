import { describe, expect, it } from 'vitest'

import { normalizeCategoryName, resolveProductCategoryCrumbs } from '../utils/pdpBreadcrumb'

// 与 /api/v1/categories 同构的本地类目树（名字按 en/zh 双语）。
const categories = [
  {
    slug: 'electronics',
    name: 'Electronics',
    name_en: 'Electronics',
    name_zh: '电子产品',
    channel_code: 'UK-Mini-HP-Electronics',
    children: [
      {
        slug: 'electronics-accessories',
        name: 'Electronics Accessories',
        name_en: 'Electronics Accessories',
        name_zh: '电子配件',
      },
      { slug: 'mobile-phones', name: 'Phones', name_en: 'Phones', name_zh: '手机' },
    ],
  },
  {
    slug: 'clothing-accessories',
    name: 'Clothing & Accessories',
    name_en: 'Clothing & Accessories',
    name_zh: '服装与配饰',
    children: [
      // 先于电子产品出现在树里：全树按名字取首个会误配到这里。
      { slug: 'fashion-accessories', name: 'Accessories', name_en: 'Accessories', name_zh: '配件' },
    ],
  },
  {
    slug: 'computers-accessories',
    name: 'Computers & Accessories',
    name_en: 'Computers & Accessories',
    name_zh: '计算机与配件',
    channel_code: null,
    children: [],
  },
]

const label = (category) => category.name_zh || category.name

describe('resolveProductCategoryCrumbs', () => {
  it('prefers local_slug and builds channel links for the L1', () => {
    const crumbs = [
      { id: '1849', name: '电子产品', depth: 0, local_slug: 'electronics' },
      { id: '1801', name: '配件', depth: 1, local_slug: 'electronics-accessories' },
    ]

    expect(resolveProductCategoryCrumbs(crumbs, categories, label)).toEqual([
      { key: 'crumb-1849', label: '电子产品', to: '/minihome/UK-Mini-HP-Electronics' },
      { key: 'crumb-1801', label: '电子配件', to: '/c/electronics-accessories' },
    ])
  })

  it('falls back to /c/<slug> when the mapped root has no channel code', () => {
    const crumbs = [
      { id: '1989', name: '计算机与配件', depth: 0, local_slug: 'computers-accessories' },
    ]

    expect(resolveProductCategoryCrumbs(crumbs, categories, label)).toEqual([
      { key: 'crumb-1989', label: '计算机与配件', to: '/c/computers-accessories' },
    ])
  })

  it('uses /c/<local_slug> when the slug is not in the loaded tree', () => {
    const crumbs = [{ id: '9999', name: '隐藏类目', depth: 0, local_slug: 'hidden-root' }]

    expect(resolveProductCategoryCrumbs(crumbs, categories, label)).toEqual([
      { key: 'crumb-9999', label: '隐藏类目', to: '/c/hidden-root' },
    ])
  })

  it('matches an unmapped child inside its parent root', () => {
    const crumbs = [
      { id: '1849', name: 'Electronics', depth: 0, local_slug: null },
      { id: '1801', name: 'Electronics Accessories', depth: 1, local_slug: null },
    ]

    expect(resolveProductCategoryCrumbs(crumbs, categories, label)).toEqual([
      { key: 'crumb-1849', label: '电子产品', to: '/minihome/UK-Mini-HP-Electronics' },
      { key: 'crumb-1801', label: '电子配件', to: '/c/electronics-accessories' },
    ])
  })

  it('never falls back to a same-name child of another parent', () => {
    // 「Accessories」在服装与配饰下也有同名节点（fashion-accessories）；
    // 归属电子产品时父级下没有同名子类，只能显示无链接文案。
    const crumbs = [
      { id: '1849', name: 'Electronics', depth: 0, local_slug: null },
      { id: '1801', name: 'Accessories', depth: 1, local_slug: null },
    ]

    expect(resolveProductCategoryCrumbs(crumbs, categories, label)).toEqual([
      { key: 'crumb-1849', label: '电子产品', to: '/minihome/UK-Mini-HP-Electronics' },
      { key: 'crumb-1801', label: 'Accessories', to: '' },
    ])
  })

  it('keeps the crumb label without a link when the name matches nothing', () => {
    const crumbs = [
      { id: '8596', name: 'Automobiles, Parts & Accessories', depth: 0, local_slug: null },
    ]

    expect(resolveProductCategoryCrumbs(crumbs, categories, label)).toEqual([
      { key: 'crumb-8596', label: 'Automobiles, Parts & Accessories', to: '' },
    ])
  })

  it('does not search the whole tree for an orphan child crumb', () => {
    // 父级无法解析时，二级只允许在父级 children 里找：不能全局命中配件。
    const crumbs = [
      { id: '8596', name: 'Unknown Root', depth: 0, local_slug: null },
      { id: '1801', name: 'Accessories', depth: 1, local_slug: null },
    ]

    expect(resolveProductCategoryCrumbs(crumbs, categories, label)).toEqual([
      { key: 'crumb-8596', label: 'Unknown Root', to: '' },
      { key: 'crumb-1801', label: 'Accessories', to: '' },
    ])
  })

  it('drops a duplicate level when parent and child map to the same category', () => {
    const crumbs = [
      { id: '1171', name: 'Fresh & Chilled Food', depth: 0, local_slug: 'clothing-accessories' },
      { id: '16307', name: 'Meat & Fish', depth: 1, local_slug: 'clothing-accessories' },
    ]

    expect(resolveProductCategoryCrumbs(crumbs, categories, label)).toEqual([
      { key: 'crumb-1171', label: '服装与配饰', to: '/c/clothing-accessories' },
    ])
  })

  it('returns an empty list for missing input', () => {
    expect(resolveProductCategoryCrumbs([], categories, label)).toEqual([])
    expect(resolveProductCategoryCrumbs(null, null, label)).toEqual([])
  })

  it('normalizes names for comparison', () => {
    expect(normalizeCategoryName('  Clothing & Accessories ')).toBe('clothingaccessories')
    expect(normalizeCategoryName(null)).toBe('')
  })
})
