import { expect, test } from '@playwright/test'

// 批次 DB（2026-11-27）：同款族列表去重 + PDP「规格 × 商家」两级 + 商家页联动。
//
// 覆盖：
// 1. 类目页全分页无同款多卡（同 family 只出一张）、卡片价 = 族内最高价；
// 2. Hypershell 族（title:d44d8a2619cb，3 个 SPU）：搜索只出 1 张卡；PDP 上
//    「型号」轴可点、整页跳到兄弟商品；商家轴存在时切商家价格跟着变；
// 3. 商家页商品按族去重；点卡片进 PDP 默认选中该商家 offer（Q10）。
const HYPER_MAX = '25885e24-9dd5-4a3c-9b9c-700215f8ca58' // 族代表（最早创建）
const HYPER_ULTRA = 'd88b76fd-432c-495e-966b-57d0aac6a150'
const CATEGORY = 'dog-toys'
// 同一 SKU 有两个商家 offer 的真实商品（HOCO 充电宝：24.19 / 4899）。
const MULTI_SELLER = 'c5130796-7145-4e59-b54c-17870608cce7'

function collectConsoleErrors(page) {
  const errors = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  return errors
}

test.describe('variant family dedupe + spec x seller', () => {
  test.setTimeout(120_000)

  test('category listing has no duplicate family cards and uses family max price', async ({
    page,
    request,
  }) => {
    const consoleErrors = collectConsoleErrors(page)
    await page.goto(`/c/${CATEGORY}`, { waitUntil: 'networkidle' })

    const api = await (
      await request.get(`/api/v1/search?market=GB&category=${CATEGORY}&page=1`)
    ).json()
    expect(api.total).toBeGreaterThan(0)

    const hrefs = await page
      .locator('.product-card__title-link')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('href') || ''))
    expect(hrefs.length).toBeGreaterThan(10)
    // 同款族只出一张卡：同一 /p/<id> 不重复
    expect(new Set(hrefs).size).toBe(hrefs.length)

    const priced = api.items.filter((item) => item.family_max_price)
    expect(priced.length).toBeGreaterThan(0)
    const firstPriced = priced[0]
    const card = page.locator(`.product-card:has(a[href*="${firstPriced.spu_public_id}"])`).first()
    const expected = Number(firstPriced.family_max_price).toFixed(2).replace('.00', '')
    await expect(card.locator('.product-card__price')).toContainText(expected.split('.')[0])

    expect(consoleErrors).toEqual([])
  })

  test('hypershell family: one card in search, spec + seller switching on PDP', async ({
    page,
    request,
  }) => {
    const consoleErrors = collectConsoleErrors(page)

    const search = await (await request.get('/api/v1/search?market=GB&q=hypershell&page=1')).json()
    expect(search.total).toBe(1)

    await page.goto(`/p/${HYPER_MAX}`, { waitUntil: 'networkidle' })

    // 型号轴：3 个兄弟 SPU，当前项高亮
    const familyButtons = page.locator('.detail__axis--family .detail__variant')
    await expect(familyButtons).toHaveCount(3)
    await expect(page.locator('.detail__axis--family .detail__variant--active')).toHaveCount(1)
    await expect(page.locator('.detail__price')).toHaveText('$1,499.00')

    // 点兄弟「Ultra S」→ 整页跳到该 SPU，价格变成 1999
    await familyButtons.filter({ hasText: 'Ultra S' }).click()
    await page.waitForURL(`**/p/${HYPER_ULTRA}**`)
    await expect(page.locator('.detail__price')).toHaveText('$1,999.00')
    await expect(page.locator('.detail__axis--family .detail__variant--active')).toContainText(
      'Ultra S',
    )

    // 商家轴：该规格有 1 个商家时不出商家轴；用多商家商品验证切换
    expect(consoleErrors).toEqual([])
  })

  test('seller axis switches price and offer on the same spec', async ({ page, request }) => {
    const consoleErrors = collectConsoleErrors(page)
    await page.goto(`/p/${MULTI_SELLER}`, { waitUntil: 'networkidle' })

    const detail = await (await request.get(`/api/v1/products/${MULTI_SELLER}?market=GB`)).json()
    const multi = detail.skus.find((sku) => (sku.offers || []).length > 1)
    expect(multi).toBeTruthy()

    const buttons = page.locator('.detail__axis--merchant .detail__variant')
    await expect(buttons).toHaveCount(multi.offers.length)
    const panel = page.locator('.detail__panel')
    const firstOffer = multi.offers[0]
    const secondOffer = multi.offers[1]
    await expect(panel).toHaveAttribute('data-offer-id', firstOffer.public_id)

    await buttons.nth(1).click()
    await expect(panel).toHaveAttribute('data-offer-id', secondOffer.public_id)
    await expect.poll(() => page.url()).toContain(`offer=${secondOffer.public_id}`)
    const expected = Number(secondOffer.price)
    const shown = Number((await page.locator('.detail__price').innerText()).replace(/[^0-9.]/g, ''))
    expect(Math.abs(shown - expected)).toBeLessThan(0.02)
    expect(consoleErrors).toEqual([])
  })

  test('merchant page dedupes families and PDP defaults to that seller offer', async ({
    page,
    request,
  }) => {
    const consoleErrors = collectConsoleErrors(page)

    const list = await (await request.get('/api/v1/merchants/search?q=source-')).json()
    let merchant = null
    for (const item of list.items) {
      const detail = await (await request.get(`/api/v1/merchants/${item.slug}`)).json()
      const products = detail.merchant?.products || []
      if (!products.length) continue
      const families = products.map((product) => product.family_key).filter(Boolean)
      if (families.length >= 3 && new Set(families).size === families.length) {
        merchant = { slug: item.slug, products }
        break
      }
    }
    expect(merchant).not.toBeNull()

    await page.goto(`/merchants/${merchant.slug}`, { waitUntil: 'networkidle' })
    const cards = page.locator('.shop-product-card')
    await expect(cards.first()).toBeVisible()
    const links = await cards.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('href') || ''),
    )
    // 同族只出一张卡：href 里的 SPU 不重复
    const spuIds = links.map((href) => (href.match(/\/p\/([^?]+)/) || [])[1])
    expect(new Set(spuIds).size).toBe(spuIds.length)

    const first = merchant.products[0]
    await page.goto(`/merchants/${merchant.slug}`, { waitUntil: 'networkidle' })
    await cards.first().click()
    await page.waitForURL(`**/p/${first.product_id}**`)
    expect(page.url()).toContain(`offer=${first.offer_id}`)
    await expect(page.locator('.detail__panel')).toHaveAttribute('data-offer-id', first.offer_id)

    expect(consoleErrors).toEqual([])
  })
})

test.describe('variant family on mobile PDP', () => {
  // 手机版是独立 host（m.localhost），不是靠 viewport 切换（见 useMobileView）。
  test.use({ viewport: { width: 390, height: 844 } })

  test('family + seller axes render without console errors', async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page)
    await page.goto(`http://m.localhost:3000/p/${HYPER_MAX}`, { waitUntil: 'networkidle' })
    await expect(page.locator('.m-pdp__axis--family')).toHaveCount(1)
    await expect(page.locator('.m-pdp__axis--family .m-pdp__variant')).toHaveCount(3)
    await page
      .locator('.m-pdp__axis--family .m-pdp__variant')
      .filter({ hasText: 'Ultra S' })
      .click()
    await page.waitForURL(`**/p/${HYPER_ULTRA}**`)
    expect(consoleErrors).toEqual([])
  })
})
