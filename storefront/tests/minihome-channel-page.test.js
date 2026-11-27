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
    // 【精选好物】首屏走 useFetch；给一条带品牌/评分的推荐商品，让频道页的
    // 卡片 props（无评分/无品牌/零售价口径）能落到真实 DOM 上断言。
    useFetch: () => ({
      data: {
        value: {
          items: [
            {
              spu_public_id: 'reco-1',
              title: 'Recommended thing',
              brand: 'ACME',
              price_min: 3,
              rating_average: '4.5',
              rating_count: 5,
            },
          ],
        },
      },
    }),
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

// 活动卡片（13.2）：接口按「组」返回（2026-11-23 契约）。
// groups 给组顺序/布局，items 给组内卡片；空数组时整块不渲染。
const pageCardItems = ref([])
const pageCardGroups = ref([])
vi.mock('../composables/useChannelPageCards', () => ({
  useChannelPageCards: async () => ({ items: pageCardItems, groups: pageCardGroups }),
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
import BaseRatingStars from '../components/BaseRatingStars.vue'
import ChannelPickedForYou from '../components/ChannelPickedForYou.vue'
import ProductCard from '../components/ProductCard.vue'
import { orderChannelTiles } from '../utils/channelTiles'
import { channelTileList } from '../utils/channelTileLists'

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
      components: { ProductCard, BaseRatingStars },
      // 评分组件用真实实现：频道楼层「不显示评分行」的断言需要真实 DOM
      //（ProductCard 在 Nuxt 里是自动导入评分组件的，测试里显式注册）。
      stubs: { NuxtLink: RouterLinkStub, BaseSkeleton: true },
    },
  })
  await flushPromises()
  return wrapper
}

// 活动卡片批次：count 张；groups 给布局，items 带 group_index/sort_order。
function cardBatch(count, { layout = 'row3', groupIndex = 0 } = {}) {
  return Array.from({ length: count }, (_, index) => ({
    id: `card-${groupIndex}-${index}`,
    image_url: `/media/cards/${groupIndex}-${index}.webp`,
    link_url: `https://example.com/promo-${groupIndex}-${index}`,
    sort_order: index,
    layout,
    group_index: groupIndex,
  }))
}

// 不带 layout/group_index 的旧契约批次（用来验证「groups 缺失按张数推断」）。
function plainBatch(count) {
  return cardBatch(count).map((item) => ({
    id: item.id,
    image_url: item.image_url,
    link_url: item.link_url,
    sort_order: item.sort_order,
  }))
} // 每组渲染出的布局 class（row2 / row3 / row3_scroll）。
function groupLayouts(wrapper) {
  return wrapper
    .findAll('.channel-cards__group')
    .map((group) => group.classes().find((name) => name.startsWith('channel-card-group--')))
}

// 页面模块顺序（活动卡片位置断言用）。
function moduleOrder(wrapper) {
  return [...wrapper.element.querySelectorAll('.channel-tiles, .channel-cards, .cms-pool')].map(
    (element) => element.classList[0],
  )
}

beforeEach(() => {
  routeState.params = { code: 'UK-Mini-HP-Home-Living' }
  bannerItems.value = []
  channelModuleItems.value = []
  pageCardItems.value = []
  pageCardGroups.value = []
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
  // 2026-11-24：精选好物卡片与楼层卡同款——频道页显式传 hide-rating/零售价口径。
  it('hands the「More」label and floor-card props to the channel picked-for-you module', async () => {
    const wrapper = await mountPage()
    const picked = wrapper.findComponent(ChannelPickedForYou)
    expect(picked.exists()).toBe(true)
    expect(picked.props('moreLabel')).toBe('More')
    expect(picked.props('categorySlug')).toBe('home-living')
    // ADR-0003（2026-11-27）：minihome 卡与真站一致显示评分行，不再隐藏。
    expect(picked.props('showRating')).toBe(true)
    expect(picked.props('useRetailPrice')).toBe(true)
    expect(picked.props('showBrand')).toBe(false)
  })

  // 2026-11-24 作用域收紧：楼层容器有专属 .channel-floor 类，精选好物只有
  // .channel-picked（不再靠共用 .channel-pool 被动继承楼层样式）。
  it('marks the product floors with the floor-only class', async () => {
    const wrapper = await mountPage()
    const pools = wrapper.findAll('.cms-pool')
    expect(pools).toHaveLength(2)
    for (const pool of pools) {
      expect(pool.classes()).toContain('channel-floor')
    }
    const picked = wrapper.get('.channel-picked')
    expect(picked.classes()).toContain('channel-pool')
    expect(picked.classes()).not.toContain('channel-floor')
    // ADR-0003：精选好物卡与楼层卡同款——有评分行（真站 minihome 卡带评分已售）、
    // 无品牌行。
    expect(picked.find('.product-card__star').exists()).toBe(true)
    expect(picked.find('.product-card__brand').exists()).toBe(false)
    // 推荐接口不带 retail_price → 回退 price_min。
    expect(picked.get('.product-card__price').text()).toBe('£3.00')
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
    expect(wrapper.findAll('.cms-pool .product-card').map((card) => card.text())).toEqual([
      expect.stringContaining('Storage Box Set'),
      expect.stringContaining('Ceramic Vase'),
      expect.stringContaining('Scented Candle'),
      expect.stringContaining('LED Table Lamp'),
    ])
  })

  it('renders configured real-site modules with a View More link to the category listing', async () => {
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
    // 截图对比 2026-11-23 第 7 条：真站文案 View More + › 箭头（走频道页 key）。
    expect(pools[0].get('.cms-pool__more').text()).toContain('View More')
    expect(pools[0].get('.cms-pool__more-arrow').text()).toBe('›')
    expect(pools[0].text()).toContain('Storage Box Set')
  })

  // 13.1②：没有精选清单的频道（清单返回 null）保持后端树顺序，且按
  // maxVisible（22）截断、余量给「查看全部品类」。
  it('caps the tile area at 22 tiles and links the overflow to the results page', async () => {
    // 用一个 channelTileLists 未收录的一级类目，避免被精选清单过滤。
    treeCategories.value = [
      {
        slug: 'mystery-channel',
        name_en: 'Mystery',
        name_zh: '未清单频道',
        channel_code: 'UK-Mini-HP-Home-Living',
        children: Array.from({ length: 23 }, (_, index) => ({
          slug: `child-${index}`,
          name_en: `Child ${index}`,
          name_zh: `子类 ${index}`,
        })),
      },
    ]
    try {
      const wrapper = await mountPage()
      expect(wrapper.findAll('.category-tile')).toHaveLength(22)
      const more = wrapper.get('.channel-tiles__more-link')
      expect(more.attributes('href')).toBe('/s?category=mystery-channel')
      expect(more.text()).toBe('View all categories')
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  // 2026-11-24 缺陷修复：有精选清单时清单长度即展示数，不再被 maxVisible
  // 截断（母婴页真站清单 24 条，此前被 maxVisible=22 切掉 2 条）。
  it('renders the whole curated list when one exists (no maxVisible truncation)', async () => {
    const slugs = channelTileList('baby-toddler')
    expect(slugs.length).toBeGreaterThan(22)
    routeState.params = { code: 'UK-Mini-HP-Baby-Toddler' }
    treeCategories.value = [
      {
        slug: 'baby-toddler',
        name_en: 'Baby & Toddler',
        name_zh: '母婴',
        channel_code: 'UK-Mini-HP-Baby-Toddler',
        children: slugs.map((slug) => ({ slug, name_en: slug, name_zh: slug })),
      },
    ]
    try {
      const wrapper = await mountPage()
      expect(wrapper.findAll('.category-tile')).toHaveLength(slugs.length)
      // 清单全量展示 → 没有「查看全部品类」余量入口。
      expect(wrapper.find('.channel-tiles__more-link').exists()).toBe(false)
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
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
      const slugs = wrapper
        .findAll('.category-tile')
        .map((tile) => tile.attributes('href'))
        .sort()
      // 顺序由精选清单决定（另一批次），这里只断言「其他动物用品」被隐藏。
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

  // 13.2 活动卡片：groups 缺失时按张数推断布局（真站实测 2 → 两列、
  // 3 → 三列、≥4 → 一屏三张可滑，measurement.md §B.1）。
  it('switches the activity-card layout by card count when groups are missing', async () => {
    pageCardItems.value = plainBatch(2)
    let wrapper = await mountPage()
    expect(groupLayouts(wrapper)).toEqual(['channel-card-group--row2'])
    expect(wrapper.findAll('.channel-card')).toHaveLength(2)
    wrapper.unmount()

    pageCardItems.value = plainBatch(3)
    wrapper = await mountPage()
    expect(groupLayouts(wrapper)).toEqual(['channel-card-group--row3'])
    expect(wrapper.findAll('.channel-card')).toHaveLength(3)
    wrapper.unmount()

    pageCardItems.value = plainBatch(5)
    wrapper = await mountPage()
    expect(groupLayouts(wrapper)).toEqual(['channel-card-group--row3_scroll'])
    expect(wrapper.findAll('.channel-card')).toHaveLength(5)
    wrapper.unmount()
  })

  // groups 缺失时按 items[].layout 分桶（组顺序 = 首次出现顺序）。
  it('buckets cards by their own layout when groups are missing', async () => {
    pageCardItems.value = [
      ...cardBatch(4, { layout: 'row3_scroll', groupIndex: 0 }).map((item) => ({
        ...item,
        group_index: undefined,
      })),
      ...cardBatch(2, { layout: 'row2', groupIndex: 1 }).map((item) => ({
        ...item,
        group_index: undefined,
      })),
    ]
    const wrapper = await mountPage()
    expect(groupLayouts(wrapper)).toEqual([
      'channel-card-group--row3_scroll',
      'channel-card-group--row2',
    ])
    expect(wrapper.findAll('.channel-card')).toHaveLength(6)
  })

  // row2 = 一行 2 张大卡（620×200、gap 24）：组内两张都渲染。
  it('renders the row2 group with both of its large cards', async () => {
    pageCardGroups.value = [{ group_index: 0, layout: 'row2', count: 2 }]
    pageCardItems.value = cardBatch(2, { layout: 'row2' })
    const wrapper = await mountPage()
    const group = wrapper.get('.channel-card-group--row2')
    expect(group.findAll('.channel-card')).toHaveLength(2)
    expect(group.findAll('.channel-cards__item')).toHaveLength(2)
  })

  // 多组：按 group_index 升序渲染各组，组内按 sort_order 升序。
  it('renders the declared groups in group_index order with sort_order inside each', async () => {
    pageCardGroups.value = [
      { group_index: 0, layout: 'row3_scroll', count: 3 },
      { group_index: 1, layout: 'row2', count: 2 },
    ]
    pageCardItems.value = [
      ...cardBatch(3, { layout: 'row3_scroll', groupIndex: 0 }),
      ...cardBatch(2, { layout: 'row2', groupIndex: 1 }),
    ].reverse()
    const wrapper = await mountPage()
    expect(groupLayouts(wrapper)).toEqual([
      'channel-card-group--row3_scroll',
      'channel-card-group--row2',
    ])
    const groups = wrapper.findAll('.channel-cards__group')
    expect(groups[0].findAll('.channel-card')).toHaveLength(3)
    expect(groups[1].findAll('.channel-card')).toHaveLength(2)
    expect(groups[0].findAll('.channel-card').map((card) => card.attributes('href'))).toEqual([
      'https://example.com/promo-0-0',
      'https://example.com/promo-0-1',
      'https://example.com/promo-0-2',
    ])
    expect(groups[1].findAll('.channel-card').map((card) => card.attributes('href'))).toEqual([
      'https://example.com/promo-1-0',
      'https://example.com/promo-1-1',
    ])
  })

  it('renders no activity-card module (and no placeholder) when the channel has no cards', async () => {
    const wrapper = await mountPage()
    expect(wrapper.find('.channel-cards').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('No cards')
  })

  // 13.8：外链新窗口 + noopener、站内路径走 NuxtLink、空链接整张不可点。
  it('routes activity-card links by the external-link rule', async () => {
    pageCardItems.value = [
      { id: 'c1', image_url: '/media/1.webp', link_url: 'https://example.com/a', sort_order: 0 },
      { id: 'c2', image_url: '/media/2.webp', link_url: '/c/kitchen', sort_order: 1 },
      { id: 'c3', image_url: '/media/3.webp', link_url: '', sort_order: 2 },
    ]
    const wrapper = await mountPage()
    const cards = wrapper.findAll('.channel-card')
    expect(cards).toHaveLength(3)
    expect(cards[0].attributes('target')).toBe('_blank')
    expect(cards[0].attributes('rel')).toBe('noopener')
    expect(cards[0].attributes('href')).toBe('https://example.com/a')
    expect(cards[1].attributes('href')).toBe('/c/kitchen')
    expect(cards[2].element.tagName).toBe('SPAN')
    for (const image of wrapper.findAll('.channel-card__img')) {
      expect(image.attributes('loading')).toBe('lazy')
    }
  })

  it('places the activity cards after the tile area and before the first product floor', async () => {
    pageCardItems.value = cardBatch(3)
    const wrapper = await mountPage()
    expect(moduleOrder(wrapper)).toEqual(['channel-tiles', 'channel-cards', 'cms-pool', 'cms-pool'])
  })

  // 真站实测 §B.3：宠物页两个组都放在第一个商品楼层「Black Friday Deals」
  // 之后、第二个楼层之前，组#0 与组#1 上下排列。
  it('renders both pets card groups after the first product floor', async () => {
    routeState.params = { code: 'UK-Mini-HP-Pets' }
    pageCardGroups.value = [
      { group_index: 0, layout: 'row3_scroll', count: 4 },
      { group_index: 1, layout: 'row2', count: 2 },
    ]
    pageCardItems.value = [
      ...cardBatch(4, { layout: 'row3_scroll', groupIndex: 0 }),
      ...cardBatch(2, { layout: 'row2', groupIndex: 1 }),
    ].reverse()
    treeCategories.value = [
      {
        slug: 'pet-supplies',
        name_en: 'Pets',
        name_zh: '宠物',
        channel_code: 'UK-Mini-HP-Pets',
        children: [{ slug: 'cat-food', name_en: 'Cat Food', name_zh: '猫粮' }],
      },
    ]
    try {
      const wrapper = await mountPage()
      expect(moduleOrder(wrapper)).toEqual([
        'channel-tiles',
        'cms-pool',
        'channel-cards',
        'cms-pool',
      ])
      expect(groupLayouts(wrapper)).toEqual([
        'channel-card-group--row3_scroll',
        'channel-card-group--row2',
      ])
      const groups = wrapper.findAll('.channel-cards__group')
      expect(groups[0].findAll('.channel-card')).toHaveLength(4)
      expect(groups[1].findAll('.channel-card')).toHaveLength(2)
      // 组#0 在组#1 之前（上下排列）。
      expect(groups[0].element.nextElementSibling).toBe(groups[1].element)
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  // 母婴页：两个组都在品类卡下方紧邻排列（第一个楼层之前）。
  it('renders both baby card groups right under the tile area', async () => {
    routeState.params = { code: 'UK-Mini-HP-Toys-Baby-and-Kids' }
    pageCardGroups.value = [
      { group_index: 0, layout: 'row2', count: 2 },
      { group_index: 1, layout: 'row2', count: 2 },
    ]
    pageCardItems.value = [
      ...cardBatch(2, { layout: 'row2', groupIndex: 0 }),
      ...cardBatch(2, { layout: 'row2', groupIndex: 1 }),
    ]
    treeCategories.value = [
      {
        slug: 'baby-toddler',
        name_en: 'Toys, Baby & Kids',
        name_zh: '母婴玩具',
        channel_code: 'UK-Mini-HP-Toys-Baby-and-Kids',
        children: [{ slug: 'baby-care', name_en: 'Baby Care', name_zh: '婴儿护理' }],
      },
    ]
    try {
      const wrapper = await mountPage()
      expect(moduleOrder(wrapper)).toEqual([
        'channel-tiles',
        'channel-cards',
        'cms-pool',
        'cms-pool',
      ])
      expect(groupLayouts(wrapper)).toEqual([
        'channel-card-group--row2',
        'channel-card-group--row2',
      ])
      expect(wrapper.findAll('.channel-cards .channel-card')).toHaveLength(4)
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  // 游戏页后端已无启用卡片：空数据自然不渲染，不写频道特例。
  it('renders no card container on a channel with no enabled cards (gaming)', async () => {
    routeState.params = { code: 'UK-Mini-HP-Gaming' }
    treeCategories.value = [
      {
        slug: 'games-accessories',
        name_en: 'Gaming',
        name_zh: '游戏',
        channel_code: 'UK-Mini-HP-Gaming',
        children: [{ slug: 'consoles', name_en: 'Consoles', name_zh: '游戏主机' }],
      },
    ]
    try {
      const wrapper = await mountPage()
      expect(wrapper.find('.channel-cards').exists()).toBe(false)
      expect(wrapper.find('.channel-cards__group').exists()).toBe(false)
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  // 价格口径（2026-11-23）：优先后台零售价 retail_price，缺失回退 price_min；
  // 不显示划线原价（<s>）与折扣红。
  it('shows retail_price on channel floors, falling back to price_min without a strikethrough', async () => {
    channelModuleItems.value = [
      {
        public_id: 'm1',
        title: 'Best sellers',
        href: '/c/home-living',
        products: [
          {
            spu_public_id: 'retail-1',
            title: 'Retail priced',
            price_min: 10,
            retail_price: '25.00',
            original_price: 40,
          },
          {
            spu_public_id: 'retail-2',
            title: 'No retail price',
            price_min: 8.5,
            retail_price: null,
          },
        ],
      },
    ]
    const wrapper = await mountPage()
    const prices = wrapper.findAll('.cms-pool .product-card__price')
    expect(prices).toHaveLength(2)
    expect(prices[0].text()).toBe('£25.00')
    expect(prices[1].text()).toBe('£8.50')
    expect(wrapper.findAll('.cms-pool s')).toHaveLength(0)
    expect(wrapper.find('.cms-pool .product-card__price--discount').exists()).toBe(false)
  })

  // 真站楼层卡没有评分行（截图对比 2026-11-23 第 5 条）；首页/搜索卡不变。
  it('hides the rating row on channel floor cards only', async () => {
    const rated = {
      spu_public_id: 'rated-1',
      title: 'Rated thing',
      price_min: 5,
      rating_average: 4.5,
      rating_count: 9,
    }
    const shared = mount(ProductCard, {
      props: { product: rated },
      global: {
        components: { BaseRatingStars },
        stubs: { NuxtLink: RouterLinkStub, BaseSkeleton: true },
      },
    })
    expect(shared.find('.product-card__rating-row').exists()).toBe(true)
    shared.unmount()

    channelModuleItems.value = [
      { public_id: 'm1', title: 'Best sellers', href: '/c/home-living', products: [rated] },
    ]
    const wrapper = await mountPage()
    expect(wrapper.findAll('.cms-pool .product-card')).toHaveLength(1)
    expect(wrapper.find('.cms-pool .rating-stars').exists()).toBe(false)
  })

  // ADR-0003（2026-11-27）评分口径：卡片行 = 星级 + 评分数值 + 已售快照
  // （真站 starRating：★5.0 · 60+ sold）；评价数不再展示；全空整行不渲染，
  // 自营徽标默认显示。
  it('renders rating value with sold snapshot and hides empty rows', () => {
    function mountCard(product, props = {}) {
      return mount(ProductCard, {
        props: { product, ...props },
        global: {
          components: { BaseRatingStars },
          stubs: { NuxtLink: RouterLinkStub, BaseSkeleton: true },
        },
      })
    }

    const rated = mountCard({
      spu_public_id: 'rated-count',
      title: 'Rated with count',
      price_min: 5,
      rating_average: '4.37',
      rating_count: 970,
      sold_amount: '1.5k+',
    })
    expect(rated.get('.product-card__rating-value').text()).toBe('4.4')
    expect(rated.get('.product-card__rating-value').text()).toBe('4.4')
    expect(rated.get('.product-card__sold').text()).toBe('1.5k+ sold')
    // 自营徽标默认显示（i18n 文案）。
    expect(rated.get('.product-card__self-operated').text()).toBe('Sold by Joybuy')
    // 评价数行不再渲染（真站展示的是已售）。
    expect(rated.find('.product-card__rating-divider').exists()).toBe(true)
    rated.unmount()

    const soldOnly = mountCard({
      spu_public_id: 'sold-only',
      title: 'No rating but sold',
      price_min: 5,
      rating_average: null,
      sold_amount: '60+',
    })
    expect(soldOnly.find('.product-card__star').exists()).toBe(false)
    expect(soldOnly.get('.product-card__sold').text()).toBe('60+ sold')
    soldOnly.unmount()

    // 评分与已售全空 → 整行不渲染；商家页（showSelfOperated=false）无徽标。
    const plain = mountCard({
      spu_public_id: 'plain',
      title: 'No data',
      price_min: 5,
      rating_average: null,
      sold_amount: null,
    })
    expect(plain.find('.product-card__rating-row').exists()).toBe(false)
    expect(plain.get('.product-card__self-operated').text()).toBe('Sold by Joybuy')
    plain.unmount()

    const merchant = mountCard(
      {
        spu_public_id: 'merchant-card',
        title: 'Merchant card',
        price_min: 5,
        rating_average: '4.9',
        sold_amount: '300+',
      },
      { showSelfOperated: false },
    )
    expect(merchant.get('.product-card__rating-row').exists()).toBe(true)
    expect(merchant.find('.product-card__self-operated').exists()).toBe(false)
    merchant.unmount()
  })

  // 品类卡行距：fill='row'（家居/宠物/母婴）32px，fill='column'（电子/家电）20px。
  it('uses the 32px row gap only on fill=row channels', async () => {
    const homeWrapper = await mountPage()
    expect(homeWrapper.get('.category-tiles').classes()).toContain('category-tiles--fill-row')
    homeWrapper.unmount()

    routeState.params = { code: 'UK-Mini-HP-Electronics' }
    treeCategories.value = [
      {
        slug: 'electronics',
        name_en: 'Electronics',
        name_zh: '电子',
        channel_code: 'UK-Mini-HP-Electronics',
        children: [{ slug: 'phones', name_en: 'Phones', name_zh: '手机' }],
      },
    ]
    try {
      const wrapper = await mountPage()
      expect(wrapper.get('.category-tiles').classes()).not.toContain('category-tiles--fill-row')
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  it('reports the per-row cap so 8 small tiles fill one screen', async () => {
    const wrapper = await mountPage()
    const style = wrapper.get('.channel-tiles__carousel .category-tiles').attributes('style')
    expect(style).toContain('--tile-size: 140px')
    expect(style).toContain('--tiles-per-row: 8')
  })

  // 有序清单重排：按清单顺序取、清单里没有的 slug 跳过；null 保持原顺序。
  it('orders tiles by the ordered slug list and skips unknown slugs', () => {
    const children = [
      { slug: 'a', name_en: 'A', name_zh: 'A' },
      { slug: 'b', name_en: 'B', name_zh: 'B' },
      { slug: 'c', name_en: 'C', name_zh: 'C' },
    ]
    // 全局索引（Map）解析，跨一级 slug 也能取到。
    const index = new Map(children.map((child) => [child.slug, child]))
    expect(orderChannelTiles(['c', 'a'], index)).toEqual([children[2], children[0]])
    const onMissing = vi.fn()
    expect(orderChannelTiles(['missing', 'b'], index, onMissing)).toEqual([children[1]])
    expect(onMissing).toHaveBeenCalledWith('missing')
    // 数组 lookup 也支持（本频道 children）。
    expect(orderChannelTiles(['b'], children)).toEqual([children[1]])
    // 没有清单 → null，调用方保持后端树顺序。
    expect(orderChannelTiles(null, index)).toBeNull()
    expect(orderChannelTiles([], index)).toBeNull()
  })

  // 清单文件给出的顺序就是页面渲染顺序（未列出的后端节点不渲染）；
  // 清单里的跨一级 slug 也能从全树索引解析出来（真站家居页挂 diy-tools 等）。
  // 家居生活 2 行走 fill=row：DOM 顺序是列优先（[0,2,1,3]），视觉第一行是 [0,1]。
  it('renders the tile area in channelTileLists order', async () => {
    const ordered = (channelTileList('home-living') || []).slice(0, 4)
    expect(ordered.length).toBe(4)
    rootWithChannel.children = [
      { slug: 'unlisted-child', name_en: 'Unlisted', name_zh: '未列出' },
      // 第 1 个清单项故意挂在别的一级下，模拟真站的跨一级精选。
      { slug: ordered[0], name_en: 'Cross-level', name_zh: '跨一级' },
    ]
    rootWithoutChannel.children = ordered.slice(1).map((slug) => ({
      slug,
      name_en: `Listed ${slug}`,
      name_zh: `清单 ${slug}`,
    }))
    try {
      const wrapper = await mountPage()
      const hrefs = wrapper.findAll('.category-tile').map((tile) => tile.attributes('href'))
      expect(hrefs).toEqual([ordered[0], ordered[2], ordered[1], ordered[3]].map((s) => `/c/${s}`))
    } finally {
      rootWithoutChannel.children = []
      rootWithChannel.children = [
        { slug: 'kitchen-essentials', name_en: 'Kitchen Essentials', name_zh: '厨房用品' },
        { slug: 'bedding-textiles', name_en: 'Bedding & Textiles', name_zh: '床上用品' },
      ]
    }
  })

  // 批次 BA（2026-11-24）：户外页真站 5 张二级卡，清单按真站顺序映射到本地
  // 节点，其中 2 个挂在别的一级下（Sports Nutrition / Smartwatches），靠全树
  // 索引解析。此前清单只写 1 条 → 页面只出 1 张。
  it('renders all five outdoor-sports tiles in real-site order', async () => {
    const ordered = channelTileList('outdoor-sports')
    expect(ordered).toEqual([
      'sports-apparel-shoes',
      'fitness-training',
      'outdoor-gear',
      'sports-nutrition-performance',
      'wearables',
    ])
    routeState.params = { code: 'mini-hp-nl-sports-outdoor' }
    treeCategories.value = [
      {
        slug: 'outdoor-sports',
        name_en: 'Outdoor & Sports',
        name_zh: '户外运动',
        channel_code: 'mini-hp-nl-sports-outdoor',
        children: [
          { slug: 'outdoor-gear', name_en: 'Outdoors', name_zh: '户外' },
          { slug: 'sports-apparel-shoes', name_en: 'Sports Apparel', name_zh: '运动服装' },
          { slug: 'fitness-training', name_en: 'Sports & Leisure', name_zh: '体育与休闲' },
        ],
      },
      {
        slug: 'health-wellness',
        name_en: 'Health',
        name_zh: '健康',
        channel_code: 'UK-Mini-HP-Health-and-Wellness',
        children: [
          {
            slug: 'sports-nutrition-performance',
            name_en: 'Sports Nutrition',
            name_zh: '运动 & 体能',
          },
        ],
      },
      {
        slug: 'electronics',
        name_en: 'Electronics',
        name_zh: '电子',
        channel_code: 'UK-Mini-HP-Electronics',
        children: [{ slug: 'wearables', name_en: 'Wearables', name_zh: '可穿戴设备' }],
      },
    ]
    try {
      const wrapper = await mountPage()
      const hrefs = wrapper.findAll('.category-tile').map((tile) => tile.attributes('href'))
      expect(hrefs).toEqual(ordered.map((slug) => `/c/${slug}`))
      expect(hrefs).toHaveLength(5)
      // 清单全量展示（5 张 = 清单长度），没有横滑余量入口。
      expect(wrapper.find('.channel-tiles__more-link').exists()).toBe(false)
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  // 2026-11-24 批次：home-living 真站 22 张，本地可映射 17 张（汽车/节庆装饰
  // 本地无节点；Watering & Garden Tools 提升映射到 outdoor-sports/garden）。
  // 顺序严格按真站，跨根 garden 靠全树索引解析；2 行 fill=row → DOM 列优先。
  it('renders all seventeen home-living tiles in real-site order', async () => {
    const expected = [
      'kitchen-essentials',
      'home-storage',
      'bedding-textiles',
      'bath',
      'home-decor',
      'party-decorations',
      'home-arts-craft-supplies',
      'gift-wrap-cards',
      'furniture',
      'garden',
      'diy-tools',
      'fitness-training',
      'outdoor-gear',
      'notebooks-pads-paper',
      'pens-pencils',
      'school-office-accessories',
      'mailing-supplies',
    ]
    expect(channelTileList('home-living')).toEqual(expected)
    const asNode = (slug) => ({ slug, name_en: slug, name_zh: slug })
    const crossRoot = ['garden', 'diy-tools', 'fitness-training', 'outdoor-gear']
    treeCategories.value = [
      {
        slug: 'home-living',
        name_en: 'Home & Living',
        name_zh: '家居生活',
        channel_code: 'UK-Mini-HP-Home-Living',
        children: expected.filter((slug) => !crossRoot.includes(slug)).map(asNode),
      },
      {
        slug: 'outdoor-sports',
        name_en: 'Outdoor & Sports',
        name_zh: '户外运动',
        channel_code: 'mini-hp-nl-sports-outdoor',
        children: crossRoot.map(asNode),
      },
    ]
    try {
      const wrapper = await mountPage()
      const hrefs = wrapper.findAll('.category-tile').map((tile) => tile.attributes('href'))
      // fill=row + rows=2：DOM 按列刷，视觉第一行是清单前 9 个。
      const columnCount = Math.ceil(expected.length / 2)
      const domOrder = []
      for (let column = 0; column < columnCount; column += 1) {
        for (let index = 0; index < expected.length; index += 1) {
          if (index % columnCount === column) domOrder.push(expected[index])
        }
      }
      expect(hrefs).toEqual(domOrder.map((slug) => `/c/${slug}`))
      expect(hrefs).toHaveLength(17)
      expect(wrapper.find('.channel-tiles__more-link').exists()).toBe(false)
    } finally {
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  // 2026-11-24 批次：games 真站 9 张，本地可映射 7 张（Gaming Keyboards /
  // Gaming Mice 本地只有合并的 peripherals，跳过；Monitors 跨根解析）。
  it('renders all seven games tiles in real-site order', async () => {
    const expected = [
      'controllers',
      'console-games',
      'consoles',
      'gaming-memory-storage',
      'gaming-pc-components',
      'monitors',
      'steering-wheels',
    ]
    expect(channelTileList('games-accessories')).toEqual(expected)
    const asNode = (slug) => ({ slug, name_en: slug, name_zh: slug })
    treeCategories.value = [
      {
        slug: 'games-accessories',
        name_en: 'Gaming',
        name_zh: '游戏',
        channel_code: 'UK-Mini-HP-Gaming',
        children: expected.filter((slug) => slug !== 'monitors').map(asNode),
      },
      {
        slug: 'computers-accessories',
        name_en: 'Computers & Accessories',
        name_zh: '计算机与配件',
        channel_code: 'UK-Mini-HP-Electronics',
        children: [asNode('monitors')],
      },
    ]
    try {
      routeState.params = { code: 'UK-Mini-HP-Gaming' }
      const wrapper = await mountPage()
      const hrefs = wrapper.findAll('.category-tile').map((tile) => tile.attributes('href'))
      // games 1 行（rows=1，按列刷 = 清单顺序）。
      expect(hrefs).toEqual(expected.map((slug) => `/c/${slug}`))
      expect(hrefs).toHaveLength(7)
    } finally {
      routeState.params = { code: 'UK-Mini-HP-Home-Living' }
      treeCategories.value = [rootWithChannel, rootWithoutChannel]
    }
  })

  // 批次 BA 通用兜底：清单解析后不足 2 张时回退该品类树 children（过滤 nav
  // 隐藏项与该频道的 hiddenTiles），避免其他频道再出现「只剩 1 张」。
  it('falls back to the category tree children when the curated list resolves to one tile', async () => {
    rootWithChannel.children = [
      // 清单里只有 kitchen-essentials 能解析到 → 解析后 1 张，触发兜底。
      { slug: 'kitchen-essentials', name_en: 'Kitchen Essentials', name_zh: '厨房用品' },
      { slug: 'cat-food', name_en: 'Cat Food', name_zh: '猫粮' },
      { slug: 'nav-hidden-child', name_en: 'Hidden', name_zh: '导航隐藏', visible_in_nav: false },
    ]
    try {
      const wrapper = await mountPage()
      const hrefs = wrapper.findAll('.category-tile').map((tile) => tile.attributes('href'))
      expect(hrefs).toEqual(['/c/kitchen-essentials', '/c/cat-food'])
    } finally {
      rootWithChannel.children = [
        { slug: 'kitchen-essentials', name_en: 'Kitchen Essentials', name_zh: '厨房用品' },
        { slug: 'bedding-textiles', name_en: 'Bedding & Textiles', name_zh: '床上用品' },
      ]
    }
  })
})
