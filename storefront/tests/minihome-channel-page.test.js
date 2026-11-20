import { mount, flushPromises } from '@vue/test-utils'
import { computed, defineComponent, h, ref, Suspense } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// The page reads the route param, resolves the channel against the shared
// category tree and fires two search pools. All three are mocked here; the
// route param is mutable per test through `routeState`.
const routeState = { params: { code: 'UK-Mini-HP-Home-Living' } }

vi.mock('#imports', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useRoute: () => ({ params: routeState.params, query: {}, path: '/minihome' }),
  }
})

const rootWithChannel = {
  slug: 'home-living',
  name_en: 'Home & Living',
  name_zh: '家居生活',
  channel_code: 'UK-Mini-HP-Home-Living',
  children: [
    { slug: 'kitchen-essentials', name_en: 'Kitchen Essentials', name_zh: '厨房用品' },
    { slug: 'bedding-textiles', name_en: 'Bedding & Textiles', name_zh: '床上用品' },
  ],
}
const rootWithoutChannel = {
  slug: 'outdoor-sports',
  name_en: 'Outdoor & Sports',
  name_zh: '户外运动',
  children: [],
}

const treeCategories = ref([rootWithChannel, rootWithoutChannel])

vi.mock('../composables/useCategoryTree', () => ({
  useCategoryTree: () => ({ categories: treeCategories, treeData: Promise.resolve() }),
}))

// 频道 banner 由管理端配置；测试里用可变 ref 模拟 0/1/N 三种情况。
const bannerItems = ref([])
vi.mock('../composables/useChannelBanners', () => ({
  useChannelBanners: () => ({ banners: bannerItems }),
}))

// 频道商品楼层（批次 H）：默认无配置走通用楼层，配置后只渲染真站楼层。
const channelModuleItems = ref([])
vi.mock('../composables/useChannelModules', () => ({
  useChannelModules: () => ({ modules: channelModuleItems }),
}))

const hotItems = [
  { spu_public_id: 'hot-1', title: 'Storage Box Set', price_min: 3.99 },
  { spu_public_id: 'hot-2', title: 'Ceramic Vase', price_min: 8.5 },
  { spu_public_id: 'hot-3', title: 'Scented Candle', price_min: 5.2 },
]
const newestItems = [{ spu_public_id: 'new-1', title: 'LED Table Lamp', price_min: 19.9 }]

vi.mock('../composables/useSearchApi', () => ({
  useSearch: (params) => ({
    data: computed(() => {
      const value = typeof params?.value === 'object' ? params.value : {}
      if (value.category === 'unknown-channel') return { items: [], total: 0 }
      return value.sort === 'newest'
        ? { items: newestItems, total: newestItems.length }
        : { items: hotItems, total: hotItems.length }
    }),
  }),
}))

import Page from '../pages/minihome/[code].vue'
import ChannelPickedForYou from '../components/ChannelPickedForYou.vue'
import ProductCard from '../components/ProductCard.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

// Pages use async setup (awaited tree + search pools), so the page mounts
// inside a Suspense boundary like the Nuxt page outlet does.
const PageHolder = defineComponent({
  setup() {
    return () => h(Suspense, null, { default: () => h(Page) })
  },
})

async function mountPage() {
  const wrapper = mount(PageHolder, {
    global: {
      components: { ProductCard },
      stubs: { NuxtLink: RouterLinkStub, BaseSkeleton: true, BaseRatingStars: true },
    },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  routeState.params = { code: 'UK-Mini-HP-Home-Living' }
  bannerItems.value = []
  channelModuleItems.value = []
})

describe('minihome channel page', () => {
  it('renders the channel head, hero placeholder and L2 tile area on /minihome/<code>', async () => {
    const wrapper = await mountPage()
    expect(wrapper.get('h1.channel-title').text()).toBe('Home & Living')
    // Banner 位是本地渐变占位（无 CDN、无伪造图片素材）。
    expect(wrapper.get('.channel-hero').classes()).toContain('channel-hero')
    // 没有配置 banner 时显示渐变占位，不出现任何图片。
    expect(wrapper.findAll('.channel-hero__img')).toHaveLength(0)
    expect(wrapper.get('.channel-hero__name').text()).toBe('Home & Living')
    const tiles = wrapper.findAll('.category-tile')
    expect(tiles).toHaveLength(2)
    expect(tiles[0].attributes('href')).toBe('/c/kitchen-essentials')
    expect(tiles[1].attributes('href')).toBe('/c/bedding-textiles')
    // 二级不超限时没有「查看全部品类」入口。
    expect(wrapper.find('.channel-tiles__more-link').exists()).toBe(false)
  })

  // 需求 16.4：频道页底部【精选好物】按钮文案为【更多 / More】（en）。
  it('hands the「More」label to the channel picked-for-you module', async () => {
    const wrapper = await mountPage()
    const picked = wrapper.findComponent(ChannelPickedForYou)
    expect(picked.exists()).toBe(true)
    expect(picked.props('moreLabel')).toBe('More')
    expect(picked.props('categorySlug')).toBe('home-living')
  })

  it('shows a single configured banner as a static image without arrows', async () => {
    bannerItems.value = [{ id: 'b1', image_url: '/media/cms/only.png', href: '/c/kitchen' }]
    const wrapper = await mountPage()
    const images = wrapper.findAll('.channel-hero__img')
    expect(images).toHaveLength(1)
    expect(images[0].attributes('src')).toBe('/media/cms/only.png')
    expect(wrapper.find('.channel-hero__link').attributes('href')).toBe('/c/kitchen')
    expect(wrapper.find('.channel-hero__arrow').exists()).toBe(false)
    expect(wrapper.find('.channel-hero__dot').exists()).toBe(false)
  })

  it('turns three configured banners into a carousel with arrows and dots', async () => {
    bannerItems.value = [
      { id: 'b1', image_url: '/media/cms/1.png', href: '/c/one' },
      { id: 'b2', image_url: '/media/cms/2.png', href: '' },
      { id: 'b3', image_url: '/media/cms/3.png', href: 'https://example.com/promo' },
    ]
    const wrapper = await mountPage()
    expect(wrapper.findAll('.channel-hero__img')).toHaveLength(3)
    expect(wrapper.findAll('.channel-hero__arrow')).toHaveLength(2)
    expect(wrapper.findAll('.channel-hero__dot')).toHaveLength(3)

    const track = wrapper.get('.channel-hero__track')
    expect(track.attributes('style')).toContain('translateX(-0%)')
    await wrapper.findAll('.channel-hero__arrow')[1].trigger('click')
    expect(track.attributes('style')).toContain('translateX(-100%)')
    await wrapper.findAll('.channel-hero__dot')[2].trigger('click')
    expect(track.attributes('style')).toContain('translateX(-200%)')
    // 第三张是外链：target/rel 防钓鱼；第二张无 href 时整张不可点。
    const links = wrapper.findAll('.channel-hero__link')
    expect(links[2].attributes('target')).toBe('_blank')
    expect(links[2].attributes('rel')).toBe('noopener')
    expect(links[1].attributes('href')).toBeUndefined()
  })

  it('fires two product floors off the channel root category', async () => {
    const wrapper = await mountPage()
    const pools = wrapper.findAll('.cms-pool')
    expect(pools).toHaveLength(2)
    expect(pools[0].get('.cms-pool__title').text()).toBe('Hot picks')
    expect(pools[0].get('.cms-pool__more').attributes('href')).toBe('/s?category=home-living')
    expect(pools[1].get('.cms-pool__title').text()).toBe('New arrivals')
    expect(wrapper.findAll('.product-card').map((card) => card.text())).toEqual([
      expect.stringContaining('Storage Box Set'),
      expect.stringContaining('Ceramic Vase'),
      expect.stringContaining('Scented Candle'),
      expect.stringContaining('LED Table Lamp'),
    ])
  })

  it('renders configured real-site modules with a More link to the category listing', async () => {
    channelModuleItems.value = [
      {
        public_id: 'm1',
        title: 'Best sellers',
        href: '/c/home-living',
        products: [hotItems[0]],
      },
    ]
    const wrapper = await mountPage()
    const pools = wrapper.findAll('.cms-pool')
    expect(pools).toHaveLength(1)
    expect(pools[0].get('.cms-pool__title').text()).toBe('Best sellers')
    expect(pools[0].get('.cms-pool__more').attributes('href')).toBe('/c/home-living')
    expect(pools[0].get('.cms-pool__more').text()).toBe('More')
    expect(pools[0].text()).toContain('Storage Box Set')
  })

  it('caps the tile area at 22 tiles and links the overflow to the results page', async () => {
    rootWithChannel.children = Array.from({ length: 23 }, (_, index) => ({
      slug: `child-${index}`,
      name_en: `Child ${index}`,
      name_zh: `子类 ${index}`,
    }))
    try {
      const wrapper = await mountPage()
      expect(wrapper.findAll('.category-tile')).toHaveLength(22)
      const more = wrapper.get('.channel-tiles__more-link')
      expect(more.attributes('href')).toBe('/s?category=home-living')
      expect(more.text()).toBe('View all categories')
    } finally {
      rootWithChannel.children = [
        { slug: 'kitchen-essentials', name_en: 'Kitchen Essentials', name_zh: '厨房用品' },
        { slug: 'bedding-textiles', name_en: 'Bedding & Textiles', name_zh: '床上用品' },
      ]
    }
  })

  // 13.1②：行数/每行个数/名称宽度由频道配置驱动（utils/channelTiles.js）。
  it('renders the channel tile grid with the configured variant, rows and name width', async () => {
    const wrapper = await mountPage()
    const carousel = wrapper.get('.channel-tiles__carousel')
    expect(carousel.find('.category-tiles--channel').exists()).toBe(true)
    // 家居生活：2 行、6 字宽 → 140px 图容器。
    expect(carousel.get('.category-tiles').attributes('style')).toContain('--tile-size: 140px')
    // 模块楼层走 13.1④ 的单行横滑 + 去外框形态。
    expect(wrapper.findAll('.cms-pool__row').length).toBeGreaterThan(0)
    expect(wrapper.get('.cms-pool--flat').exists()).toBe(true)
  })

  it('shows the Category Navigation title only for the health channel', async () => {
    // 家居生活：无标题。
    const homeWrapper = await mountPage()
    expect(homeWrapper.find('.channel-tiles__title').exists()).toBe(false)
    // 健康保健：标题在卡片区上方。
    routeState.params = { code: 'UK-Mini-HP-Health-and-Wellness' }
    treeCategories.value = [
      {
        slug: 'health-wellness',
        name_en: 'Health & Wellness',
        name_zh: '健康保健',
        channel_code: 'UK-Mini-HP-Health-and-Wellness',
        children: [{ slug: 'vitamins', name_en: 'Vitamins', name_zh: '维生素' }],
      },
    ]
    try {
      const wrapper = await mountPage()
      expect(wrapper.get('.channel-tiles__title').text()).toBe('Category Navigation')
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  it('hides the configured tile (other animals) only on the pets channel', async () => {
    routeState.params = { code: 'UK-Mini-HP-Pets' }
    treeCategories.value = [
      {
        slug: 'pet-supplies',
        name_en: 'Pets',
        name_zh: '宠物',
        channel_code: 'UK-Mini-HP-Pets',
        children: [
          { slug: 'cat-food', name_en: 'Cat Food', name_zh: '猫粮' },
          { slug: 'other-animals', name_en: 'Other Animals', name_zh: '其他动物用品' },
          { slug: 'dog-food', name_en: 'Dog Food', name_zh: '狗粮' },
        ],
      },
    ]
    try {
      const wrapper = await mountPage()
      const slugs = wrapper.findAll('.category-tile').map((tile) => tile.attributes('href'))
      expect(slugs).toEqual(['/c/cat-food', '/c/dog-food'])
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  it('shows the fallback state for an unknown channel code', async () => {
    routeState.params = { code: 'UK-Mini-HP-Nowhere' }
    const wrapper = await mountPage()
    expect(wrapper.find('.channel-unavailable').exists()).toBe(true)
    expect(wrapper.get('.channel-unavailable').text()).toContain('This channel is not available.')
    expect(wrapper.get('.channel-unavailable__home').attributes('href')).toBe('/')
    expect(wrapper.find('.category-tiles').exists()).toBe(false)
    expect(wrapper.find('.cms-pool').exists()).toBe(false)
  })
})
