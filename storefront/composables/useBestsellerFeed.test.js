import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useBestsellerFeed } from './useBestsellerFeed'

// The feed reads `market`/`locale` from the market-locale composable; a
// controllable mock keeps the cookies (and therefore the reactive part) real
// without a Nuxt runtime.
const localeMock = vi.hoisted(() => ({ market: 'GB', locale: 'en-GB' }))

vi.mock('./useMarketLocale', async () => {
  const { computed, ref } = await import('vue')
  const market = ref(localeMock.market)
  const locale = ref(localeMock.locale)
  localeMock.setMarket = (code) => {
    market.value = code
  }
  localeMock.setLocale = (code) => {
    locale.value = code
  }
  return {
    useMarketLocale: () => ({
      apiQuery: computed(() => ({ market: market.value, locale: locale.value })),
    }),
  }
})

// `useBestsellerFeed` uses the global `$fetch` and the `#imports` stub for
// runtime config, so no Nuxt runtime is needed here.
const fetchMock = vi.fn(async (url) => responses[url] ?? { items: [] })
vi.stubGlobal('$fetch', fetchMock)

let responses = {}

function product(id) {
  return {
    spu_public_id: id,
    title: `Product ${id}`,
    image_path: `/media/products/${id}.jpg`,
    retail_price: '9.99',
    price_min: '9.99',
    is_family_representative: true,
  }
}

const page = (ids) => ({ items: ids.map(product) })
// Every request carries market + locale (same shape as `useSearchApi`).
const search = (slug, locale = 'en-GB', market = 'GB') =>
  `/api/v1/search?category=${slug}&sort=newest&page=1&market=${market}&locale=${locale}`

describe('useBestsellerFeed', () => {
  beforeEach(() => {
    fetchMock.mockClear()
    responses = {}
    vi.restoreAllMocks()
    localeMock.setMarket?.('GB')
    localeMock.setLocale?.('en-GB')
  })

  it('keeps one request for tabs without a curation rule', async () => {
    responses[search('electronics')] = page(['e1', 'e2'])
    const { loadTabItems } = useBestsellerFeed()
    await expect(loadTabItems('electronics')).resolves.toHaveLength(2)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('fetches both sub-categories in parallel for a curated tab', async () => {
    responses[search('furniture')] = page(['f1', 'f2', 'f3', 'f4'])
    responses[search('bedding-textiles')] = page(['b1', 'b2'])
    const { loadTabItems } = useBestsellerFeed()
    const items = await loadTabItems('home-living')
    expect(items.map((item) => item.spu_public_id)).toEqual(['f1', 'f2', 'f3', 'b1', 'b2'])
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('falls back to the tab list when the sub-categories cannot fill the row', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    responses[search('nutrition-supplements')] = page(['n1'])
    responses[search('sports-nutrition-performance')] = page(['s1'])
    responses[search('health-wellness')] = page(['h1', 'h2', 'h3', 'h4', 'h5'])

    const { loadTabItems } = useBestsellerFeed()
    const items = await loadTabItems('health-wellness')

    expect(items.map((item) => item.spu_public_id)).toEqual(['h1', 'h2', 'h3', 'h4', 'h5'])
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock).toHaveBeenLastCalledWith(search('health-wellness'))
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('health-wellness'))
  })

  it('falls back to the tab list when a sub-category request fails', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { loadTabItems } = useBestsellerFeed()
    responses[search('home-living')] = page(['h1', 'h2', 'h3', 'h4', 'h5'])
    fetchMock.mockImplementationOnce(async () => {
      throw new Error('boom')
    })

    const items = await loadTabItems('home-living')

    expect(items.map((item) => item.spu_public_id)).toEqual(['h1', 'h2', 'h3', 'h4', 'h5'])
    expect(warn).toHaveBeenCalledTimes(1)
  })

  it('follows the market/locale in both the request URL and the cache key', async () => {
    const feed = useBestsellerFeed()
    expect(feed.localeKey.value).toBe('GB-en-GB')

    responses[search('electronics')] = page(['e1'])
    await feed.loadTabItems('electronics')
    expect(fetchMock).toHaveBeenLastCalledWith(search('electronics'))
    expect(feed.searchUrl('furniture')).toBe(
      '/api/v1/search?category=furniture&sort=newest&page=1&market=GB&locale=en-GB',
    )

    localeMock.setLocale('zh-CN')
    expect(feed.localeKey.value).toBe('GB-zh-CN')

    responses[search('electronics', 'zh-CN')] = page(['z1'])
    await feed.loadTabItems('electronics')
    expect(fetchMock).toHaveBeenLastCalledWith(search('electronics', 'zh-CN'))
    // Curated sub-category requests follow the switch as well.
    responses[search('furniture', 'zh-CN')] = page(['f1', 'f2', 'f3'])
    responses[search('bedding-textiles', 'zh-CN')] = page(['b1', 'b2'])
    await feed.loadTabItems('home-living')
    expect(fetchMock).toHaveBeenCalledWith(search('furniture', 'zh-CN'))
    expect(fetchMock).toHaveBeenCalledWith(search('bedding-textiles', 'zh-CN'))
  })
})
