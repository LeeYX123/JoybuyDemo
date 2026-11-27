import { expect, test } from '@playwright/test'

import { clickUntil } from './helpers'

// 批次 DA：PDP 切规格换整套数据（变体档案）。
//
// 用两个真实合并族：
// - B2-0478 火盆（share_metadata=false）：切 "22.83 inch/58" 后标题/价格/评分/
//   已售/画廊/图文详情全变；URL 带 ?sku=，刷新保持一致，后退离开 PDP、前进
//   回到变体（切换用 router.replace，不为每个规格新增历史记录）。
// - A-0103 胶原蛋白粉（share_metadata=true，纯尺码 140g/300g/600g）：切 300g
//   只变价格，画廊/评分/已售/详情不变。
const FIRE_PIT = 'd0cac3f8-df76-4093-9b20-6578cfa6391d'
const FIRE_PIT_VARIANT = 'b76fd123-e821-486f-8631-02d923ffcc9d'
const COLLAGEN = '07aff65c-6521-4b58-84f7-e1182a3e9354'

test.describe('PDP variant archive switch', () => {
  test.setTimeout(90_000)

  test('share_metadata=false: gallery/rating/sold/detail/title/price all switch', async ({
    page,
  }) => {
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    // 先停在首页，再进 PDP：给「后退」留一个可回的页面。
    await page.goto('/')
    await page.goto(`/p/${FIRE_PIT}`, { waitUntil: 'networkidle' })

    const title = page.locator('h1.detail__title')
    const price = page.locator('.detail__price')
    const rating = page.locator('.detail__rating-average')
    const sold = page.locator('[data-testid="pdp-sold"]')
    const mainImage = page.locator('.detail__image img').first()
    const firstParagraph = page.locator('.detail__content-paragraph').first()

    await expect(title).toHaveText('Fire Bowl Fire Pit Campfire Diameter')
    await expect(price).toHaveText('$199.99')
    await expect(rating).toHaveText('4.4')
    await expect(sold).toContainText('1.4k+')
    await expect(page.locator('.detail__thumb')).toHaveCount(12)
    await expect(firstParagraph).toContainText('Around a Real Fire')
    const baseImage = await mainImage.getAttribute('src')

    // 切到 22.83 inch/58：URL 写入 ?sku=，整套数据切换。
    await clickUntil(
      page,
      page.getByRole('button', { name: '22.83 inch/58', exact: true }),
      async () => {
        await expect(page).toHaveURL(new RegExp(`sku=${FIRE_PIT_VARIANT}`), { timeout: 3000 })
      },
    )
    await expect(title).toContainText('22.83 inch/58 cm')
    await expect(price).toHaveText('$69.99')
    await expect(rating).toHaveText('5.0')
    await expect(sold).toContainText('100+')
    await expect(page.locator('.detail__thumb')).toHaveCount(10)
    await expect(firstParagraph).not.toContainText('Around a Real Fire')
    const variantImage = await mainImage.getAttribute('src')
    expect(variantImage).not.toBe(baseImage)

    // 刷新：SSR 按 URL 的 ?sku= 还原变体。
    await page.reload({ waitUntil: 'networkidle' })
    await expect(page).toHaveURL(new RegExp(`sku=${FIRE_PIT_VARIANT}`))
    await expect(price).toHaveText('$69.99')
    await expect(title).toContainText('22.83 inch/58 cm')
    await expect(page.locator('.detail__thumb')).toHaveCount(10)

    // router.replace 不新增历史：后退离开 PDP，前进回到变体 URL + 变体内容。
    await page.goBack({ waitUntil: 'networkidle' })
    await expect(page).toHaveURL('http://127.0.0.1:3000/')
    await page.goForward({ waitUntil: 'networkidle' })
    await expect(page).toHaveURL(new RegExp(`sku=${FIRE_PIT_VARIANT}`))
    await expect(price).toHaveText('$69.99')
    await expect(title).toContainText('22.83 inch/58 cm')

    expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
  })

  test('share_metadata=true (pure size): price + own gallery switch, metadata stays', async ({
    page,
  }) => {
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    await page.goto(`/p/${COLLAGEN}`, { waitUntil: 'networkidle' })
    const title = page.locator('h1.detail__title')
    const price = page.locator('.detail__price')
    const rating = page.locator('.detail__rating-average')
    const sold = page.locator('[data-testid="pdp-sold"]')
    const mainImage = page.locator('.detail__image img').first()
    const firstParagraph = page.locator('.detail__content-paragraph').first()

    await expect(price).toHaveText('$14.99')
    await expect(rating).toHaveText('4.5')
    await expect(sold).toContainText('5.9k+')
    await expect(page.locator('.detail__thumb')).toHaveCount(11)
    const baseTitle = await title.textContent()
    const baseImage = await mainImage.getAttribute('src')
    const baseParagraph = (await firstParagraph.textContent()).trim()

    await clickUntil(page, page.getByRole('button', { name: '300g', exact: true }), async () => {
      await expect(price).toHaveText('$22.99', { timeout: 3000 })
    })

    // 用户口径（2026-11-27）：画廊按该 SKU 是否自带图判定，纯尺码规格
    // 也有自己的整套图（300g 档案 5 张）→ 换画廊。
    await expect(page).toHaveURL(/sku=/)
    await expect(price).toHaveText('$22.99')
    await expect(page.locator('.detail__thumb')).toHaveCount(5)
    expect(await mainImage.getAttribute('src')).not.toBe(baseImage)

    // 剩下的「整套元数据」仍按 share_metadata=true 保持 SPU 级。
    await expect(title).toHaveText(baseTitle)
    await expect(rating).toHaveText('4.5')
    await expect(sold).toContainText('5.9k+')
    expect((await firstParagraph.textContent()).trim()).toBe(baseParagraph)

    // 切回 140g（档案没有自带图）：画廊回到 SPU 基础画廊，不空。
    await page.getByRole('button', { name: '140g', exact: true }).click()
    await expect(page.locator('.detail__thumb')).toHaveCount(11)
    expect(await mainImage.getAttribute('src')).not.toBe('')

    expect(consoleErrors, consoleErrors.join('\n')).toEqual([])
  })
})
