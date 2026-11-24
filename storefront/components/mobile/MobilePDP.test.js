import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobilePDP from './MobilePDP.vue'

// Mobile PDP (docs/20 §2): presentational component fed the resolved detail
// state from pages/p/[id].vue. Payload shape mirrors the desktop detail API
// (offer.price/promotion_label/merchant, spec_options-style variant axes).
const offer = {
  public_id: 'offer-1',
  price: '18.0000',
  is_purchasable: true,
  promotion_label: '70% off',
  merchant: { display_name: 'GROTTOTINTOM', slug: 'source-abc' },
}

function mountPdp(extraProps = {}) {
  return mount(MobilePDP, {
    props: {
      data: {
        title: 'Test crew-neck tee',
        description: 'Cotton tee for casual wear.',
      },
      error: null,
      mediaItems: [
        { key: 'image-0-a', type: 'image', url: '/media/a.jpg' },
        { key: 'image-1-b', type: 'image', url: '/media/b.jpg' },
      ],
      offer,
      price: '18.00',
      variantAxes: [
        {
          name: 'Size',
          values: [
            { value: 'S', image_url: '', sku_ids: ['sku-1'] },
            { value: 'M', image_url: '', sku_ids: ['sku-2'] },
          ],
        },
      ],
      selectedSku: { public_id: 'sku-1', specification: { Size: 'S' } },
      selectedSkuSpec: { Size: 'S' },
      isSingleSku: false,
      readonlySpec: '',
      quantity: 1,
      addState: 'idle',
      wishlisted: false,
      wishPending: false,
      contentSections: [
        {
          title: 'Product Description',
          blocks: [{ type: 'paragraph', text: 'Cotton tee for casual wear.' }],
          images: ['/media/detail-1.jpg'],
        },
      ],
      specificationTables: [
        { title: 'Specifications', rows: [{ name: 'Material', value: 'Cotton' }] },
      ],
      ...extraProps,
    },
    global: {
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('MobilePDP', () => {
  it('renders gallery, info, variants, guarantees and the purchase bar', async () => {
    const wrapper = mountPdp()

    // Gallery: two images -> two dots, first active; clicking a dot switches
    // the main image.
    const dots = wrapper.findAll('.m-pdp__dot')
    expect(dots).toHaveLength(2)
    expect(wrapper.find('.m-pdp__main-img').attributes('src')).toBe('/media/a.jpg')
    await dots[1].trigger('click')
    expect(wrapper.find('.m-pdp__main-img').attributes('src')).toBe('/media/b.jpg')

    // Info block: two-line title, promo badge, red price, seller row.
    expect(wrapper.find('.m-pdp__title').text()).toBe('Test crew-neck tee')
    expect(wrapper.find('.m-pdp__promo').text()).toBe('70% off')
    expect(wrapper.find('.m-pdp__price').text()).toBe('18.00')
    expect(wrapper.find('.m-pdp__seller').text()).toContain('GROTTOTINTOM')

    // Variant axis: pill buttons, the selected one marked active; clicking
    // emits select-variant with the axis name and raw value object.
    const variants = wrapper.findAll('.m-pdp__variant')
    expect(variants).toHaveLength(2)
    expect(variants[0].classes()).toContain('m-pdp__variant--active')
    expect(variants[1].classes()).not.toContain('m-pdp__variant--active')
    await variants[1].trigger('click')
    expect(wrapper.emitted()['select-variant']).toEqual([
      ['Size', { value: 'M', image_url: '', sku_ids: ['sku-2'] }],
    ])

    // Quantity stepper emits the same delta semantics as the desktop page.
    await wrapper.find('.m-pdp__stepper button:last-child').trigger('click')
    expect(wrapper.emitted()['change-quantity']).toEqual([[1]])
    await wrapper.find('.m-pdp__stepper button:first-child').trigger('click')
    expect(wrapper.emitted()['change-quantity'][1]).toEqual([-1])

    // Guarantee row: three items with the desktop detail.guarantee* copy.
    const guarantees = wrapper.findAll('.m-pdp__guarantee')
    expect(guarantees).toHaveLength(3)
    expect(guarantees[0].text()).toContain('30 Days Free Returns')

    // Details card collapsed by default; expanding shows spec table + images.
    expect(wrapper.find('.m-pdp__details-body').exists()).toBe(false)
    await wrapper.find('.m-pdp__details-head').trigger('click')
    const body = wrapper.find('.m-pdp__details-body')
    expect(body.exists()).toBe(true)
    expect(body.text()).toContain('Material')
    expect(body.text()).toContain('Cotton')
    expect(wrapper.findAll('.m-pdp__content-img')).toHaveLength(1)

    // Purchase bar: wishlist heart + add (outlined) + buy (solid); the two
    // purchase actions emit to the page handlers.
    expect(wrapper.find('.m-pdp__wish').exists()).toBe(true)
    await wrapper.find('.m-pdp__add').trigger('click')
    expect(wrapper.emitted()['add-to-cart']).toHaveLength(1)
    await wrapper.find('.m-pdp__buy').trigger('click')
    expect(wrapper.emitted()['buy-now']).toHaveLength(1)
    await wrapper.find('.m-pdp__wish').trigger('click')
    expect(wrapper.emitted()['toggle-wishlist']).toHaveLength(1)
  })

  it('shows the delisted error state and disables the purchase actions without an offer', () => {
    const wrapper = mountPdp({
      offer: null,
      price: '',
      error: null,
    })

    // No offer: unavailable notice + disabled bar buttons, no variant axes
    // (single-SKU fallback shows the readonly spec when provided).
    expect(wrapper.find('.m-pdp__unavailable').exists()).toBe(true)
    expect(wrapper.find('.m-pdp__add').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.m-pdp__buy').attributes('disabled')).toBeDefined()

    // API error state replaces the whole page (404 = delisted copy).
    const failed = mountPdp({ error: { statusCode: 404, message: 'Not found' } })
    const state = failed.find('.m-pdp__state')
    expect(state.exists()).toBe(true)
    expect(state.attributes('role')).toBe('alert')
    expect(state.text()).toContain('This product has been delisted')
    expect(failed.find('.m-pdp__buybar').exists()).toBe(false)
  })
})
