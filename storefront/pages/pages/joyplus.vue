<script setup>
import { computed, ref } from 'vue'

import { useLocale } from '../../composables/useLocale'

// 需求 12.1：JoyPlus = 真站 /membership（"Joybuy Plus"）落地页结构复刻：
// hero（年省 £206 + 免费试用）→ JoyPlus exclusive deals（品类 tab + Plus Price 商品卡）
// → 会员惊喜福利（£5 券）→ 专属权益（Spotify/ClassPass）→ 会员权益 4 项
// → 会员方案（£3.99/月、£19.99/年、学生 30 天试用）→ FAQs。
// EN 文案取自真站实测（measurement.md §2 #4）；商品卡取本站商品池
//（GET /api/v1/recommendations），Plus Price 按真站口径约 95 折计算，非真站同一批商品。
definePageMeta({ layout: 'footer-page' })

const { locale } = useLocale()

const T = computed(() => {
  const en = {
    hero: {
      title:
        'Spend a little, get a whole lot back with JoyPlus - with average savings of £206 per year.',
      cta: 'Try JoyPlus FREE',
    },
    deals: {
      title: 'JoyPlus exclusive deals',
      subtitle: 'Extra savings and exclusive prices every day.',
      viewAll: 'View all',
      tabs: [
        'All',
        'Sports & Outdoor',
        'Electronics',
        'Food cupboard',
        'Home Appliances',
        'Computing',
        'Gaming',
        'Cooking & Dining',
        'Furniture',
        'Housewares',
        'Home Textiles',
      ],
      plusPrice: 'Plus Price',
      payAfter: (amount) => `Pay ${amount} after promotion`,
      getBy: 'Get it by today',
      soldBy: 'Sold by Joybuy',
    },
    bonus: {
      title: 'Member Bonus',
      subtitle: 'Claim your JoyPlus offers',
      off: 'Off',
      minSpend: 'Min. spend £59.00',
      note: 'Applicable to all categories, excluding selected products',
      claim: 'Claim',
    },
    exclusive: {
      title: 'Your exclusive Benefits',
      items: [
        {
          t: 'Spotify Premium',
          d: 'Join JoyPlus to claim up to 4 months free!',
          note: 'Subject to availability. T&Cs Apply.',
        },
        {
          t: 'ClassPass',
          d: "Join JoyPlus to get 15 free classes, or 15 bonus credits if you're an existing ClassPass member.",
          note: 'New users only. T&Cs Apply.',
        },
      ],
      viewMore: 'View more',
    },
    premium: {
      title: 'Premium Benefits',
      rows: [
        { t: 'Price Match with Points', d: "Found a lower price? We'll refund the difference." },
        {
          t: 'Unlimited Free Delivery',
          d: 'Unlock free delivery on every eligible order, with fast, reliable shipping—no minimum purchase required.',
        },
        {
          t: 'Collect Joybuy Points on every order',
          d: 'Collect 1 Joybuy point on every £1 you spend and use them to save more on future orders.',
        },
        {
          t: 'Special deals on thousands of products',
          d: 'Enjoy exclusive daily deals on a huge selection of high-quality products.',
        },
      ],
    },
    plans: {
      title: 'Select your membership plan',
      subtitle: 'Ongoing subscription until cancelled',
      items: [
        { t: 'Monthly Plan', price: '£3.99/month', d: 'renews every month' },
        { t: 'Annual Plan', price: '£19.99/year', d: 'renews every year' },
        { t: 'Special offers for students', price: '30-day free trial', d: '' },
      ],
      agree: 'I agree to',
      terms: 'JoyPlus Terms & Conditions',
    },
    faq: {
      title: 'JoyPlus FAQs',
      items: [
        {
          q: 'Why was I charged when I signed up for a free trial?',
          a: 'A small verification hold may appear when you start a free trial. It is released automatically and you will not be billed during the trial period.',
        },
        {
          q: 'When will I be billed for my membership?',
          a: 'Your membership fee is billed at the start of each billing cycle (monthly or annual), and renews automatically until cancelled.',
        },
        {
          q: 'What is the JoyPlus cancellation policy? Will I be refunded?',
          a: 'You can cancel at any time in your account settings. Your benefits stay active until the end of the current billing period; remaining periods are not refunded but will not renew.',
        },
        {
          q: 'If the membership fee changes, will I be billed automatically?',
          a: 'If the membership fee changes, we will notify you in advance. Continued use after the change takes effect means the new fee applies.',
        },
      ],
    },
  }
  const zh = {
    hero: {
      title: '加入 JoyPlus 会员，锁定超值回报：年均可节省 £206。',
      cta: '立即免费试用 JoyPlus',
    },
    deals: {
      title: 'JoyPlus 优惠商品',
      subtitle: '会员专属价格商品单单省',
      viewAll: '查看全部',
      tabs: [
        '全部',
        '运动户外',
        '电子数码',
        '食品柜',
        '家用电器',
        '电脑办公',
        '游戏',
        '厨具餐具',
        '家具',
        '家居用品',
        '家纺',
      ],
      plusPrice: 'Plus Price',
      payAfter: (amount) => `到手价：${amount}`,
      getBy: '今天送达',
      soldBy: 'Joybuy 自营',
    },
    bonus: {
      title: '会员惊喜福利',
      subtitle: '领取你的 JoyPlus 专属优惠',
      off: '优惠',
      minSpend: '购物满 £59.00',
      note: '全品类（部分商品除外）',
      claim: '领取',
    },
    exclusive: {
      title: '您的专属权益',
      items: [
        {
          t: 'Spotify Premium',
          d: '加入 JoyPlus，最高免费享 4 个月 Spotify Premium 会员！',
          note: '优惠视供应情况而定。受条款及条件约束。',
        },
        {
          t: 'ClassPass',
          d: '加入 JoyPlus 可享 15 节免费课程；现有 ClassPass 会员可获得 15 个奖励积分。',
          note: '仅限新用户。须遵守条款与条件。',
        },
      ],
      viewMore: '查看更多',
    },
    premium: {
      title: '会员权益',
      rows: [
        { t: '买贵退积分', d: '发现更低价？我们退还差价。' },
        {
          t: '无限次快速免邮',
          d: '每一笔自营商品订单均可享受免费配送，快速可靠，无起送门槛限制。',
        },
        {
          t: '单单返积分',
          d: '每消费 £1 获得 1 个 Joybuy 积分，可在未来订单中抵扣，持续帮您省钱。',
        },
        { t: '千款商品会员特惠', d: '精选优质商品，享受每日会员专属优惠价。' },
      ],
    },
    plans: {
      title: '选择您的会员方案',
      subtitle: '订阅持续生效，直至取消',
      items: [
        { t: '月费会员', price: '£3.99/月', d: '每月自动续订' },
        { t: '年费会员', price: '£19.99/年', d: '每年自动续订' },
        { t: '学生专享优惠', price: '30 天免费试用', d: '' },
      ],
      agree: '我已阅读并同意',
      terms: 'JoyPlus 条款',
    },
    faq: {
      title: 'JoyPlus 常见问题',
      items: [
        {
          q: '为什么我开通试用会员的时候被扣费了？',
          a: '开通免费试用时可能出现小额验证预授权，会自动解除，试用期内不会实际扣费。',
        },
        {
          q: '会员费用会在什么时候扣款？',
          a: '会员费在每个计费周期开始时收取（按月或按年），并自动续订直至取消。',
        },
        {
          q: 'JoyPlus 的取消政策是什么？我可以申请退款吗？',
          a: '您可以随时在账户设置中取消。权益将持续到当前计费周期结束；剩余周期不予退款，且不会再续订。',
        },
        {
          q: '如果会费发生变化，会自动按新价格扣款吗？',
          a: '若会费调整，我们会提前通知您。调整生效后继续使用即表示接受新价格。',
        },
      ],
    },
  }
  return locale.value === 'zh' ? zh : en
})

const activeTab = ref(0)

// 商品卡数据：本站商品池（与首页推荐同源），取前 8 件。
// SSR 直连后端（dev 下 nitro 的 /api 代理只作用于入站请求，内部 $fetch 不走代理）；
// key 固定为静态字符串，否则 SSR/客户端 URL 不同会被当成两个 key，payload 不复用 → hydration mismatch。
const config = useRuntimeConfig()
const firstDealsUrl = import.meta.server
  ? `${config.apiBaseInternal}/recommendations?page=1`
  : '/api/v1/recommendations?page=1'
const { data: recoData } = await useFetch(() => firstDealsUrl, { key: 'joyplus-deals-page1' })

const currencySymbol = computed(() => recoData.value?.display_currency_symbol || '$')

function formatPrice(value) {
  const num = Number(value)
  return `${currencySymbol.value}${num.toFixed(2)}`
}

const deals = computed(() => {
  const items = (recoData.value?.items || []).slice(0, 8)
  return items.map((item) => {
    const price = Number(item.price_min || item.price_max || 0)
    // 真站 Plus Price ≈ 原价 95 折（19.99→18.99、3.32→3.15、8.98→8.53）。
    const plus = Math.round(price * 0.95 * 100) / 100
    return {
      id: item.spu_public_id,
      title: item.title,
      img: item.image_path,
      price: formatPrice(price),
      plusPrice: formatPrice(plus),
      to: `/p/${item.spu_public_id}`,
    }
  })
})

const openFaq = ref(-1)

function toggleFaq(index) {
  openFaq.value = openFaq.value === index ? -1 : index
}

useHead({ title: () => 'Joybuy Plus' })
</script>

<template>
  <div class="plus-page">
    <div class="plus-page__inner">
      <!-- hero -->
      <section class="plus-hero">
        <div class="plus-hero__text">
          <img
            class="plus-hero__logo"
            src="/images/joyplus/plus-logo.png"
            alt="Joybuy Plus"
            width="140"
            height="36"
          />
          <h1 class="plus-hero__title">{{ T.hero.title }}</h1>
          <button class="plus-hero__cta" type="button">{{ T.hero.cta }}</button>
        </div>
        <img
          class="plus-hero__bg"
          src="/images/joyplus/member-bg.png"
          alt=""
          width="220"
          height="252"
          loading="lazy"
        />
      </section>

      <!-- JoyPlus exclusive deals -->
      <section class="plus-deals">
        <div class="plus-deals__head">
          <div>
            <h2 class="plus-deals__title">{{ T.deals.title }}</h2>
            <p class="plus-deals__subtitle">{{ T.deals.subtitle }}</p>
          </div>
          <a class="plus-deals__all" href="#" @click.prevent>{{ T.deals.viewAll }}</a>
        </div>
        <div class="plus-deals__tabs" role="tablist">
          <button
            v-for="(tab, index) in T.deals.tabs"
            :key="tab"
            class="plus-deals__tab"
            :class="{ 'plus-deals__tab--active': activeTab === index }"
            type="button"
            @click="activeTab = index"
          >
            {{ tab }}
          </button>
        </div>
        <div class="plus-deals__grid">
          <NuxtLink v-for="item in deals" :key="item.id" class="plus-card" :to="item.to">
            <img class="plus-card__img" :src="item.img" :alt="item.title" loading="lazy" />
            <p class="plus-card__title">{{ item.title }}</p>
            <p class="plus-card__price">{{ item.price }}</p>
            <p class="plus-card__plus">{{ T.deals.plusPrice }}</p>
            <p class="plus-card__pay">{{ T.deals.payAfter(item.plusPrice) }}</p>
            <p class="plus-card__meta">{{ T.deals.getBy }}</p>
            <p class="plus-card__meta">{{ T.deals.soldBy }}</p>
          </NuxtLink>
        </div>
      </section>

      <!-- 会员惊喜福利 -->
      <section class="plus-bonus">
        <h2 class="plus-section__title">{{ T.bonus.title }}</h2>
        <p class="plus-bonus__subtitle">{{ T.bonus.subtitle }}</p>
        <div class="plus-bonus__voucher">
          <span class="plus-bonus__amount">£5.00</span>
          <span class="plus-bonus__off">{{ T.bonus.off }}</span>
          <div class="plus-bonus__terms">
            <p class="plus-bonus__min">{{ T.bonus.minSpend }}</p>
            <p class="plus-bonus__note">{{ T.bonus.note }}</p>
          </div>
          <button class="plus-bonus__claim" type="button">{{ T.bonus.claim }}</button>
        </div>
      </section>

      <!-- 专属权益 -->
      <section class="plus-exclusive">
        <h2 class="plus-section__title">{{ T.exclusive.title }}</h2>
        <div class="plus-exclusive__grid">
          <div v-for="item in T.exclusive.items" :key="item.t" class="plus-exclusive__card">
            <p class="plus-exclusive__t">{{ item.t }}</p>
            <p class="plus-exclusive__d">{{ item.d }}</p>
            <p class="plus-exclusive__note">{{ item.note }}</p>
            <button class="plus-exclusive__more" type="button">{{ T.exclusive.viewMore }}</button>
          </div>
        </div>
      </section>

      <!-- 会员权益 -->
      <section class="plus-premium">
        <h2 class="plus-section__title">{{ T.premium.title }}</h2>
        <div class="plus-premium__grid">
          <div v-for="row in T.premium.rows" :key="row.t" class="plus-premium__row">
            <p class="plus-premium__t">{{ row.t }}</p>
            <p class="plus-premium__d">{{ row.d }}</p>
          </div>
        </div>
      </section>

      <!-- 会员方案 -->
      <section class="plus-plans">
        <h2 class="plus-section__title">{{ T.plans.title }}</h2>
        <p class="plus-plans__subtitle">{{ T.plans.subtitle }}</p>
        <div class="plus-plans__grid">
          <div v-for="plan in T.plans.items" :key="plan.t" class="plus-plan">
            <p class="plus-plan__t">{{ plan.t }}</p>
            <p class="plus-plan__price">{{ plan.price }}</p>
            <p v-if="plan.d" class="plus-plan__d">{{ plan.d }}</p>
          </div>
        </div>
        <p class="plus-plans__agree">
          {{ T.plans.agree }}
          <a class="plus-plans__terms" href="#" @click.prevent>{{ T.plans.terms }}</a>
        </p>
      </section>

      <!-- FAQs -->
      <section class="plus-faq">
        <h2 class="plus-section__title">{{ T.faq.title }}</h2>
        <div v-for="(item, index) in T.faq.items" :key="item.q" class="plus-faq__item">
          <button
            class="plus-faq__q"
            type="button"
            :aria-expanded="openFaq === index"
            @click="toggleFaq(index)"
          >
            {{ item.q }}
            <span class="plus-faq__chevron" aria-hidden="true">{{
              openFaq === index ? '−' : '+'
            }}</span>
          </button>
          <p v-show="openFaq === index" class="plus-faq__a">{{ item.a }}</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.plus-page {
  background: var(--colour-surface);
  padding: var(--space-6) 0 var(--space-8);
}

.plus-page__inner {
  max-width: var(--container-max);
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

.plus-section__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}

/* hero */
.plus-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-6);
  padding: var(--space-6);
  border-radius: var(--radius-md);
  background: linear-gradient(120deg, #efe7ff 0%, #f5f6fa 70%);
}

.plus-hero__logo {
  display: block;
  height: 36px;
  width: auto;
}

.plus-hero__title {
  margin: var(--space-3) 0 var(--space-4);
  max-width: 560px;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  line-height: 1.3;
}

.plus-hero__cta {
  min-height: 44px;
  padding: var(--space-2) var(--space-6);
  border: 0;
  border-radius: 999px;
  background: #1a1a1a;
  color: var(--colour-surface);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.plus-hero__bg {
  display: block;
  height: auto;
  max-width: 220px;
}

/* deals */
.plus-deals {
  margin-top: var(--space-8);
}

.plus-deals__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
}

.plus-deals__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}

.plus-deals__subtitle {
  margin: var(--space-1) 0 0;
  color: #505259;
  font-size: var(--font-size-sm);
}

.plus-deals__all {
  color: var(--colour-accent);
  font-size: var(--font-size-sm);
  text-decoration: underline;
}

.plus-deals__tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.plus-deals__tab {
  min-height: 36px;
  padding: var(--space-1) var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: 999px;
  background: var(--colour-surface);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.plus-deals__tab--active {
  border-color: #1a1a1a;
  background: #1a1a1a;
  color: var(--colour-surface);
}

.plus-deals__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.plus-card {
  display: block;
  padding: var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  text-decoration: none;
  color: inherit;
}

.plus-card:hover {
  border-color: #1a1a1a;
}

.plus-card__img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: #f5f6fa;
}

.plus-card__title {
  display: -webkit-box;
  overflow: hidden;
  margin: var(--space-2) 0 0;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font-size: var(--font-size-sm);
  line-height: 1.4;
}

.plus-card__price {
  margin: var(--space-2) 0 0;
  font-weight: var(--font-weight-bold);
}

.plus-card__plus {
  margin: var(--space-1) 0 0;
  color: #6e7078;
  font-size: var(--font-size-xs);
}

.plus-card__pay {
  margin: 0;
  color: #e1251b;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.plus-card__meta {
  margin: var(--space-1) 0 0;
  color: #6e7078;
  font-size: var(--font-size-xs);
}

/* 会员惊喜福利 */
.plus-bonus {
  margin-top: var(--space-8);
}

.plus-bonus__subtitle {
  margin: var(--space-1) 0 var(--space-4);
  color: #505259;
  font-size: var(--font-size-sm);
}

.plus-bonus__voucher {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-5);
  border: 1px dashed var(--colour-accent);
  border-radius: var(--radius-md);
  background: #fdecee;
}

.plus-bonus__amount {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: #e1251b;
}

.plus-bonus__off {
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  background: #e1251b;
  color: var(--colour-surface);
  font-size: var(--font-size-xs);
}

.plus-bonus__terms {
  flex: 1;
  min-width: 200px;
}

.plus-bonus__min {
  margin: 0;
  font-weight: var(--font-weight-semibold);
}

.plus-bonus__note {
  margin: 0;
  color: #505259;
  font-size: var(--font-size-xs);
}

.plus-bonus__claim {
  min-height: 44px;
  padding: var(--space-2) var(--space-6);
  border: 0;
  border-radius: 999px;
  background: #e1251b;
  color: var(--colour-surface);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

/* 专属权益 */
.plus-exclusive {
  margin-top: var(--space-8);
}

.plus-exclusive__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.plus-exclusive__card {
  padding: var(--space-5);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: #f5f6fa;
}

.plus-exclusive__t {
  margin: 0 0 var(--space-2);
  font-weight: var(--font-weight-bold);
}

.plus-exclusive__d {
  margin: 0;
  line-height: 1.6;
}

.plus-exclusive__note {
  margin: var(--space-2) 0 0;
  color: #6e7078;
  font-size: var(--font-size-xs);
}

.plus-exclusive__more {
  min-height: 36px;
  margin-top: var(--space-3);
  padding: var(--space-1) var(--space-4);
  border: 1px solid #1a1a1a;
  border-radius: 999px;
  background: var(--colour-surface);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

/* 会员权益 */
.plus-premium {
  margin-top: var(--space-8);
}

.plus-premium__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.plus-premium__row {
  padding: var(--space-5);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
}

.plus-premium__t {
  margin: 0 0 var(--space-2);
  font-weight: var(--font-weight-bold);
}

.plus-premium__d {
  margin: 0;
  color: #505259;
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

/* 会员方案 */
.plus-plans {
  margin-top: var(--space-8);
}

.plus-plans__subtitle {
  margin: var(--space-1) 0 var(--space-4);
  color: #505259;
  font-size: var(--font-size-sm);
}

.plus-plans__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.plus-plan {
  padding: var(--space-5);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: #f5f6fa;
  text-align: center;
}

.plus-plan__t {
  margin: 0 0 var(--space-2);
  font-weight: var(--font-weight-semibold);
}

.plus-plan__price {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: #e1251b;
}

.plus-plan__d {
  margin: var(--space-1) 0 0;
  color: #6e7078;
  font-size: var(--font-size-xs);
}

.plus-plans__agree {
  margin: var(--space-4) 0 0;
  font-size: var(--font-size-sm);
}

.plus-plans__terms {
  color: var(--colour-accent);
  text-decoration: underline;
}

/* FAQs */
.plus-faq {
  margin-top: var(--space-8);
}

.plus-faq__item {
  border-bottom: 1px solid var(--colour-border);
}

.plus-faq__q {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  width: 100%;
  min-height: 56px;
  padding: var(--space-3) 0;
  border: 0;
  background: transparent;
  text-align: left;
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.plus-faq__chevron {
  color: var(--colour-muted);
  font-size: var(--font-size-xl);
}

.plus-faq__a {
  margin: 0 0 var(--space-4);
  color: #505259;
  line-height: 1.7;
}

@media (max-width: 48rem) {
  .plus-deals__grid,
  .plus-exclusive__grid,
  .plus-premium__grid,
  .plus-plans__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 30rem) {
  .plus-deals__grid,
  .plus-exclusive__grid,
  .plus-premium__grid,
  .plus-plans__grid {
    grid-template-columns: 1fr;
  }
}
</style>
