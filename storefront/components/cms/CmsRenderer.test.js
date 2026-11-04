import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CmsRenderer from './CmsRenderer.vue'
import CmsProductPool from './CmsProductPool.vue'
import ProductCard from '../ProductCard.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

const productPool = {
  type: 'product_pool',
  position: 3,
  payload: {
    title: 'Popular right now',
    href: '/c/popular',
    products: [
      {
        public_id: 'id-1',
        title: 'Wireless Earbuds Pro',
        price: 19.99,
        currency: 'GBP',
        rating: 4.6,
        review_count: 123,
        badge: 'Flash sale',
      },
      { public_id: 'id-2', title: 'No price item' },
    ],
  },
}

function mountRenderer(modules) {
  return mount(CmsRenderer, {
    props: { modules },
    global: {
      stubs: {
        NuxtLink: RouterLinkStub,
        BaseSkeleton: true,
        BaseBadge: true,
        BaseRatingStars: true,
      },
    },
  })
}

describe('CmsRenderer', () => {
  it('renders every known module type in order', () => {
    const modules = [
      { type: 'hero', payload: { heading: 'Hi', cta_href: '/c/electronics', cta_label: 'Go' } },
      {
        type: 'campaign_grid',
        payload: {
          title: 'Offers for you',
          items: [{ title: 'Welcome Offers', subtitle: 'Shop the app', image_path: '' }],
        },
      },
      { type: 'banner', payload: { href: '/c/deals', label: 'Offer' } },
      productPool,
      { type: 'rich_text', payload: { heading: 'About', body: 'Text' } },
      {
        type: 'link_grid',
        payload: {
          title: 'Explore Joybuy',
          variant: 'quick_entries',
          items: [{ label: 'Lightning Offers', icon_path: '/media/x.png' }],
        },
      },
    ]
    const wrapper = mountRenderer(modules)
    expect(wrapper.find('.cms-hero').exists()).toBe(true)
    expect(wrapper.find('.cms-campaign').exists()).toBe(true)
    expect(wrapper.find('.cms-banner').exists()).toBe(true)
    expect(wrapper.find('.cms-pool').exists()).toBe(true)
    expect(wrapper.find('.cms-rich-text').exists()).toBe(true)
    expect(wrapper.find('.cms-link-grid').exists()).toBe(true)
  })

  it('drops campaign_grid tiles without titles and never renders a heading', () => {
    const wrapper = mountRenderer([
      {
        type: 'campaign_grid',
        payload: {
          title: 'Offers for you',
          items: [{ title: 'Welcome Offers' }, { subtitle: 'x' }],
        },
      },
    ])
    expect(wrapper.findAll('.cms-campaign__tile')).toHaveLength(1)
    // The real campaign floor has no visible heading (docs/12 target state).
    expect(wrapper.find('.cms-campaign__heading').exists()).toBe(false)
  })

  it('uses the payload background image on the campaign floor', () => {
    const wrapper = mountRenderer([
      {
        type: 'campaign_grid',
        payload: {
          title: 'Offers for you',
          background_path: '/media/cms/campaign-bg.png',
          items: [{ title: 'Welcome Offers', image_path: '' }],
        },
      },
    ])
    expect(wrapper.get('.cms-campaign').attributes('style')).toContain('/media/cms/campaign-bg.png')
  })

  it('renders discovery cards with label + image and brand logos statically', () => {
    const wrapper = mountRenderer([
      {
        type: 'link_grid',
        payload: {
          title: 'Category discovery',
          variant: 'tiles',
          items: [
            {
              label: 'Home',
              label_zh: '家居',
              icon_path: '/media/discovery/home.png',
              href: '/s?category=home-living',
            },
          ],
        },
      },
      {
        type: 'link_grid',
        payload: {
          title: 'Brands we love',
          title_zh: '心选品牌',
          variant: 'brand_logos',
          items: [{ label: 'Midea', icon_path: '/media/brands/midea.png' }],
        },
      },
    ])
    const cards = wrapper.findAll('.discovery-card')
    expect(cards).toHaveLength(1)
    expect(cards[0].find('.discovery-card__image').attributes('src')).toBe(
      '/media/discovery/home.png',
    )
    expect(cards[0].attributes('href')).toBe('/s?category=home-living')
    // Brand marquee: one animated track with the items rendered twice for the
    // seamless right→left loop; cards are static (no links).
    expect(wrapper.find('.brand-marquee__track').exists()).toBe(true)
    const brands = wrapper.findAll('.brand-card')
    expect(brands).toHaveLength(2)
    expect(brands[0].find('img').attributes('src')).toBe('/media/brands/midea.png')
    expect(brands[0].find('.brand-card__name').text()).toBe('Midea')
    expect(brands[0].find('a').exists()).toBe(false)
  })

  it('drops link_grid items without labels and renders static tiles without hrefs', () => {
    const wrapper = mountRenderer([
      {
        type: 'link_grid',
        payload: {
          title: 'Brands we love',
          items: [{ label: 'TCL' }, { label: '' }, { nope: 1 }],
        },
      },
    ])
    const grid = wrapper.get('.cms-link-grid')
    expect(grid.get('.cms-link-grid__title').text()).toBe('Brands we love')
    const tiles = grid.findAll('.cms-link-grid__tile')
    expect(tiles).toHaveLength(1)
    expect(tiles[0].text()).toBe('TCL')
    expect(tiles[0].classes()).not.toContain('cms-link-grid__tile--link')
  })

  it('degrades unknown module types to a placeholder without crashing', () => {
    const wrapper = mountRenderer([{ type: 'mystery_carousel', payload: { whatever: 1 } }])
    const placeholder = wrapper.get('.cms-unknown')
    expect(placeholder.text()).toContain('mystery_carousel')
  })

  it('degrades malformed payloads (missing fields, wrong shapes) per module', () => {
    const wrapper = mountRenderer([
      { type: 'hero', payload: {} },
      { type: 'product_pool', payload: { title: 'No products key' } },
      { type: 'rich_text', payload: null },
      productPool,
    ])
    expect(wrapper.findAll('.cms-unknown')).toHaveLength(3)
    expect(wrapper.find('.cms-pool').exists()).toBe(true)
  })

  it('renders nothing harmful for an empty module list', () => {
    const wrapper = mountRenderer([])
    expect(wrapper.findAll('section')).toHaveLength(0)
  })
})

describe('CmsProductPool', () => {
  const mountPool = () =>
    mount(CmsProductPool, {
      props: { payload: productPool.payload },
      global: {
        stubs: { NuxtLink: RouterLinkStub },
        components: { ProductCard },
      },
    })

  it('renders product prices with the US dollar symbol', () => {
    const wrapper = mountPool()
    const prices = wrapper.findAll('.product-card__price').map((node) => node.text())
    expect(prices).toHaveLength(1)
    expect(prices[0]).toContain('$19.99')
  })

  it('suppresses delivery-estimate badges on product cards', () => {
    const payload = {
      ...productPool.payload,
      products: [{ public_id: 'id-3', title: 'Delivery badge item', badge: 'Arrives today' }],
    }
    const wrapper = mount(CmsProductPool, {
      props: { payload },
      global: {
        stubs: { NuxtLink: RouterLinkStub },
        components: { ProductCard },
      },
    })
    expect(wrapper.findAll('.base-badge')).toHaveLength(0)
  })

  it('omits the price element when the source has no price', () => {
    const wrapper = mountPool()
    const cards = wrapper.findAll('.product-card')
    expect(cards).toHaveLength(2)
    expect(cards[1].get('.product-card__title').text()).toBe('No price item')
  })

  it('labels the section accessibly and renders the title', () => {
    const wrapper = mountPool()
    expect(wrapper.get('section').attributes('aria-label')).toBe('Popular right now')
    expect(wrapper.get('.cms-pool__title').text()).toBe('Popular right now')
  })
})
