import { describe, expect, it } from 'vitest'

import {
  resolveVariantArchive,
  variantDetailField,
  variantGallery,
  variantQuery,
  variantReviewSummary,
  variantSoldAmount,
  variantTitleText,
} from '../utils/variantArchive'

const ARCHIVE_FULL = {
  sku: 'sku-1',
  share_metadata: false,
  gallery: [{ url: '/media/a.webp' }, { url: '/media/b.webp' }],
  title: 'Hypershell X Max S',
  review_summary: {
    average: '4.41',
    count: 249,
    distribution: { 5: 200 },
    source: 'variant_archive',
  },
  sale_amount: '6.9k+',
  detail: {
    content_sections: [{ title: 'Variant detail', blocks: [], images: [] }],
    specification_tables: [{ title: 'Spec', rows: [] }],
    ai_summary: 'variant summary',
  },
}

describe('resolveVariantArchive', () => {
  it('share_metadata=false 且 sku 命中时返回档案（整套切换）', () => {
    const payload = { variant_archive: ARCHIVE_FULL }
    expect(resolveVariantArchive(payload, 'sku-1')).toBe(ARCHIVE_FULL)
  })

  it('share_metadata=true 时返回 null（纯尺码只换价格/库存/规格）', () => {
    const payload = { variant_archive: { ...ARCHIVE_FULL, share_metadata: true } }
    expect(resolveVariantArchive(payload, 'sku-1')).toBeNull()
  })

  it('share_metadata 缺失/未知一律按 true 处理（保守，不换数据）', () => {
    expect(
      resolveVariantArchive(
        { variant_archive: { ...ARCHIVE_FULL, share_metadata: null } },
        'sku-1',
      ),
    ).toBeNull()
    expect(
      resolveVariantArchive(
        { variant_archive: { ...ARCHIVE_FULL, share_metadata: 'no' } },
        'sku-1',
      ),
    ).toBeNull()
  })

  it('sku 与当前选中不一致（切换请求还没回来）时返回 null', () => {
    expect(resolveVariantArchive({ variant_archive: ARCHIVE_FULL }, 'sku-2')).toBeNull()
    expect(resolveVariantArchive({ variant_archive: ARCHIVE_FULL }, null)).toBeNull()
  })

  it('无档案时为 null', () => {
    expect(resolveVariantArchive({}, 'sku-1')).toBeNull()
    expect(resolveVariantArchive({ variant_archive: null }, 'sku-1')).toBeNull()
    expect(resolveVariantArchive(null, 'sku-1')).toBeNull()
  })
})

describe('variantGallery', () => {
  it('档案有图用档案图', () => {
    expect(variantGallery(ARCHIVE_FULL, [{ url: '/base.webp' }])).toEqual(ARCHIVE_FULL.gallery)
  })

  it('档案缺图回退保留 SPU 的图', () => {
    expect(variantGallery({ ...ARCHIVE_FULL, gallery: [] }, [{ url: '/base.webp' }])).toEqual([
      { url: '/base.webp' },
    ])
    expect(variantGallery(null, [{ url: '/base.webp' }])).toEqual([{ url: '/base.webp' }])
  })
})

describe('variantTitleText / variantReviewSummary / variantSoldAmount', () => {
  it('标题优先档案，否则 base', () => {
    expect(variantTitleText(ARCHIVE_FULL, 'Base title')).toBe('Hypershell X Max S')
    expect(variantTitleText(null, 'Base title')).toBe('Base title')
    expect(variantTitleText(null, null)).toBe('')
  })

  it('评分快照有数据才采用，空快照回退 base', () => {
    const base = { average: '4.10', count: 10, source: 'crawler' }
    expect(variantReviewSummary(ARCHIVE_FULL, base)).toBe(ARCHIVE_FULL.review_summary)
    expect(variantReviewSummary({ review_summary: { average: null, count: 0 } }, base)).toBe(base)
    expect(variantReviewSummary({}, base)).toBe(base)
    expect(variantReviewSummary({}, null)).toBeNull()
  })

  it('已售优先档案，空串回退 base', () => {
    expect(variantSoldAmount(ARCHIVE_FULL, '1.5k+')).toBe('6.9k+')
    expect(variantSoldAmount({ sale_amount: '' }, '1.5k+')).toBe('1.5k+')
    expect(variantSoldAmount(null, null)).toBeNull()
  })
})

describe('variantDetailField', () => {
  it('档案 detail 有值才采用', () => {
    expect(variantDetailField(ARCHIVE_FULL, 'content_sections', [])).toEqual(
      ARCHIVE_FULL.detail.content_sections,
    )
    expect(variantDetailField(ARCHIVE_FULL, 'ai_summary', '')).toBe('variant summary')
  })

  it('档案没有 detail / 空数组 / 空串时回退 base（档案缺详情不把页面清空）', () => {
    expect(variantDetailField(null, 'content_sections', ['base'])).toEqual(['base'])
    expect(variantDetailField({ detail: null }, 'content_sections', ['base'])).toEqual(['base'])
    expect(
      variantDetailField({ detail: { content_sections: [] } }, 'content_sections', ['base']),
    ).toEqual(['base'])
    expect(variantDetailField({ detail: { ai_summary: '' } }, 'ai_summary', 'base')).toBe('base')
  })
})

describe('variantQuery', () => {
  it('写入 sku 并保留其它参数', () => {
    expect(variantQuery({ offer: 'o1', from: 'merchant' }, 'sku-1')).toEqual({
      offer: 'o1',
      from: 'merchant',
      sku: 'sku-1',
    })
  })

  it('sku 为空时删除该参数（回到默认规格）', () => {
    expect(variantQuery({ offer: 'o1', sku: 'sku-1' }, '')).toEqual({ offer: 'o1' })
    expect(variantQuery(undefined, null)).toEqual({})
  })
})
