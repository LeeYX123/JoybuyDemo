<script setup>
import { computed, ref } from 'vue'

import { useLocale } from '../../composables/useLocale'

// 需求 12.1：关于我们 = 真站 /promo/welcome（"Get to know Joybuy" 落地页）
// 的结构复刻：面包屑 + hero + 三支柱 + 8 个楼层 + T&C 手风琴。
// EN 文案取自真站实测（var/footer_rework_20261119/measurement.md §4，替换规则已生效），ZH 为翻译。
definePageMeta({ layout: 'footer-page' })

const { locale } = useLocale()

const T = computed(() => {
  const en = {
    breadcrumb: 'Welcome to Joybuy',
    heroTitle: 'Welcome to Joybuy',
    heroSign: 'Sign-in / Sign-up',
    pillarMore: 'Learn more',
    pillars: [
      {
        icon: '/images/about/icon-delivery.png',
        title: 'Fast and reliable same-day delivery',
        text: 'With JoyExpress, every order is handled with care, giving you fast, reliable delivery you can count on.',
      },
      {
        icon: '/images/about/icon-quality.png',
        title: 'Brands you love, quality you can trust',
        text: 'Every item is verified for quality. Shop confidently with verified sellers and our secure checkout.',
      },
      {
        icon: '/images/about/icon-247.png',
        title: '24/7 dedicated customer service',
        text: 'Got a question? Our support team is available around the clock to assist whenever you need us.',
      },
    ],
    floors: [
      {
        id: 'delivery',
        title: 'Fast and reliable same-day delivery',
        img: '/images/about/delivery-man.png',
        blocks: [
          {
            h: 'Super-fast shipping',
            p: 'Same-day and next-day delivery. Need it fast? Get what you need, when you need it. Complete your order by 11am for same-day delivery by 11pm, or by 11pm for next-day delivery by 3pm.',
          },
          {
            h: 'Service range',
            p: 'The super-fast delivery service currently covers Greater London, Luton, Milton Keynes and Birmingham, with more to come. In other regions, next-day or two-day delivery is available. See the product page when ordering for accurate delivery options. T&Cs apply. Service times are not guaranteed and only available in select cities, for select products.',
          },
        ],
        how: {
          title: 'How it works? Choose your delivery time',
          steps: [
            {
              icon: '/images/about/step-checkout.png',
              t: 'Go to checkout page',
              d: 'View the available delivery time slots directly on the checkout page.',
            },
            {
              icon: '/images/about/step-slot.png',
              t: 'Pick a timeslot',
              d: 'Choose the time slot that best fits your schedule.',
            },
            {
              icon: '/images/about/step-door.png',
              t: 'Enjoy your JoyExpress delivery',
              d: 'Our trusted delivery partner will deliver your order to your door.',
            },
          ],
          img: '/images/about/delivery-van.png',
        },
      },
      {
        id: 'quality',
        title: 'Brands you love, quality you can trust',
        img: '/images/about/quality-box.png',
        blocks: [
          {
            h: 'High quality products',
            p: 'Joybuy runs its own retail operation end to end, from sourcing products to delivering them, so we can ensure everything meets our quality standards. Our aim is to offer a reliable and trustworthy shopping experience, with every order handled through a professionally managed and fully compliant retail system.',
          },
        ],
        extra: {
          title: 'Happy to announce',
          h: 'Proud UEFA sponsor',
          p: 'Joybuy is proud to be the official e-commerce innovation partner of the UEFA Champions League, one of the world’s most trusted and recognised sporting competitions. Together, we’re bringing football fans closer to the action — not only on match days, but in the way they discover, shop, and engage with the products and experiences they care about most. This collaboration means a more connected experience as a fan — with special moments and tickets lucky draw inspired by the world’s biggest football stage, all brought to you in a simple and trusted way through Joybuy.',
          img: '/images/about/uefa.jpg',
        },
      },
      {
        id: 'support',
        title: '24/7 dedicated customer service',
        img: '/images/about/support-wide.png',
        blocks: [
          {
            h: 'Fast responses you can rely on',
            p: "Experience premium support with our 24/7 online customer service. No matter the time or day, we're just a click away. We will begin processing your complaint within 1 working day and respond to you within 2 working days, and follow up until a complete resolution is achieved.",
          },
        ],
        extra: {
          title: 'Your 24/7 support team',
          h: 'Contact us',
          img: '/images/about/support-agent.png',
          cards: [
            { icon: '/images/about/icon-chat.png', t: 'Chat with us', d: 'Anytime, all the time.' },
            { icon: '/images/about/icon-email.png', t: 'Email', d: 'Joybuyfumi@gmail.com' },
            {
              icon: '/images/about/icon-submit.png',
              t: 'Submit a request',
              d: 'Further questions?',
            },
          ],
        },
      },
      {
        id: 'deals',
        title: 'Smarter prices with exclusive deals',
        img: '/images/about/deals-box.png',
        blocks: [
          {
            h: 'Everyday lightning offers',
            p: "Catch new deals every single day. Each offer includes a special discount and a real-time status bar, so you can see exactly how many items are left, and spot when a popular deal is nearly sold out. Deals are refreshed daily and stock is limited. From tech and home essentials to everyday favourites, there’s always something worth discovering. See something you like? Grab it quickly before it's gone!",
          },
        ],
        cta: "Today's offers",
      },
      {
        id: 'returns',
        title: 'Easy returns within 30 days, hassle-free',
        img: '/images/about/returns.png',
        blocks: [
          {
            h: 'Return made easy',
            p: "Changed your mind? We've got you. Enjoy a full refund on returns made within 30 days. No hassle, no stress.",
          },
        ],
        how: {
          title: 'How it works? Return made easy',
          steps: [
            {
              icon: '/images/about/step-return.png',
              t: 'Return your item within 30 days',
              d: 'Click the "Return item" under the order page to select.',
            },
            {
              icon: '/images/about/step-ship.png',
              t: 'Ship back for free',
              d: "Labels are prepaid in most cases – we've got you covered!",
            },
            {
              icon: '/images/about/step-refund.png',
              t: 'Receive your refund',
              d: "It'll get back to your account within 3–5 business days once we confirm the return meets our policy.",
            },
          ],
        },
      },
      {
        id: 'payment',
        title: 'Shop securely, pay confidently',
        img: '/images/about/laptop-pay.png',
        blocks: [
          {
            h: 'Your payment, your way',
            p: 'Your safety comes first. With trusted global payment partners and encrypted technology, every purchase is protected.',
          },
        ],
        payTiles: [
          { icon: '/images/about/pay-klarna.png', t: 'Klarna', d: 'Spread the cost' },
          { icon: '/images/about/pay-paypal.png', t: 'PayPal', d: 'Pay in 3' },
          { icon: '/images/about/pay-applepay.png', t: 'Apple Pay', d: 'Pay the Apple way' },
          { icon: '/images/about/pay-googlepay.png', t: 'Google Pay', d: 'Easy checkout' },
        ],
        extra: {
          title: 'Safe, simple, and flexible',
          h: 'We accept',
          img: '/images/about/wallet.jpg',
          cards: ['American Express', 'VISA', 'Mastercard', 'Maestro'],
        },
      },
      {
        id: 'invite',
        title: 'Invite friends, Earn rewards!',
        img: '/images/about/invite.png',
        blocks: [
          {
            h: 'Bring a friend, join the party',
            p: 'Share Joybuy with your friends and earn rewards you can enjoy side by side.',
          },
        ],
        how: {
          title: 'How it works?',
          steps: [
            {
              icon: '/images/about/step-code.png',
              t: 'Share your invite code',
              d: 'Go to your Personal Profile to view your exclusive invite code. Simply copy the code or share the link directly to invite your friends.',
            },
            {
              icon: '/images/about/step-order.png',
              t: 'Your friend places an order',
              d: 'Once your friend registers a Joybuy account, they can enter your invite code on the checkout page of their first order to redeem an exclusive discount (only applicable to orders placed inside the Joybuy app).',
            },
            {
              icon: '/images/about/step-reward.png',
              t: 'Earn your reward',
              d: "Your points reward will be automatically issued once your friend's first order is successfully delivered. There is no limit to the rewards.",
            },
          ],
        },
        cta: 'Invite now',
      },
    ],
    joyplus: {
      title: 'JoyPlus, more than just a membership',
      h: 'More than just a membership',
      rows: [
        'Enjoy unlimited free shipping on millions of items – fast and reliable. No minimum spend required.',
        'Earn exclusive points. Every purchase adds up! Redeem for discounts on future orders.',
        'Extra savings and exclusive prices on new products every day.',
      ],
      cta: 'Join JoyPlus now',
    },
    tc: {
      title: 'Terms & conditions',
      items: [
        {
          q: 'Where can I find my welcome offer?',
          a: "Within 30 days of registration, visit the 'New Customer Limited-Time Benefits' zone to enjoy the exclusive new customer price on any one item of your choice! One-time use & best deal applied automatically: this benefit can be enjoyed only once per new user. Items already enjoying the new customer price cannot be combined with other coupons or promotional activities but can still use shipping coupons. App-exclusive offer: this welcome offer is only available through the app.",
        },
        {
          q: 'How do JoyPoints work?',
          a: 'JoyPoints are reward points earned on every purchase. They add up automatically and can be redeemed for discounts on future orders.',
        },
        {
          q: 'How do I make sure my payment is successful?',
          a: "We want your experience with Joybuy to be smooth and worry-free! Make sure your personal details are correct and match those registered to your bank account; if you're pre-ordering, make sure your card will still be valid on the release date and your billing address is correct; sign up to a card authentication scheme such as Visa Secure or Mastercard SecureCode. Planning a high-value order? Let your bank know in advance.",
        },
        {
          q: 'What is JoyPlus membership?',
          a: "JoyPlus is Joybuy's membership program designed to make everyday shopping more rewarding. Members enjoy unlimited free shipping and member-only prices on eligible products during their active membership period, along with automatic JoyPoints on every purchase, helping you save more the more you shop.",
        },
      ],
    },
  }
  const zh = {
    breadcrumb: '欢迎来到 Joybuy',
    heroTitle: '欢迎来到 Joybuy',
    heroSign: '登录 / 注册',
    pillarMore: '了解更多',
    pillars: [
      {
        icon: '/images/about/icon-delivery.png',
        title: '快速可靠的当日达服务',
        text: '有了 JoyExpress，您的每笔订单都会被悉心处理，为您提供快速、可靠、值得信赖的配送服务。',
      },
      {
        icon: '/images/about/icon-quality.png',
        title: '挚爱品牌，信赖品质',
        text: '每件商品均经过品质认证。在卖家认证和支付安全的保障下，您可以放心购物。',
      },
      {
        icon: '/images/about/icon-247.png',
        title: '24/7 全天候专属客服',
        text: '有疑问吗？我们的支持团队全天候待命，随时为您提供帮助。',
      },
    ],
    floors: [
      {
        id: 'delivery',
        title: '快速可靠的当日达服务',
        img: '/images/about/delivery-man.png',
        blocks: [
          {
            h: '极速配送',
            p: '当日达与次日达。需要更快？上午 11 点前下单当日 23 点前送达，晚上 11 点前下单次日 15 点前送达，按您需要的时间送达您需要的商品。',
          },
          {
            h: '服务范围',
            p: '极速配送服务目前覆盖大伦敦、卢顿、米尔顿凯恩斯和伯明翰，并将持续扩展。其他地区提供次日达或两日达服务，准确配送选项请以下单时商品页为准。条款与条件适用。服务时效不作保证，仅限指定城市的指定商品。',
          },
        ],
        how: {
          title: '使用方法：选择您的配送时段',
          steps: [
            {
              icon: '/images/about/step-checkout.png',
              t: '前往结账页',
              d: '在结账页直接查看可选的配送时段。',
            },
            {
              icon: '/images/about/step-slot.png',
              t: '选择时段',
              d: '选择最适合您日程的配送时段。',
            },
            {
              icon: '/images/about/step-door.png',
              t: '享受 JoyExpress 配送',
              d: '我们值得信赖的配送伙伴会把订单送到您家门口。',
            },
          ],
          img: '/images/about/delivery-van.png',
        },
      },
      {
        id: 'quality',
        title: '挚爱品牌，信赖品质',
        img: '/images/about/quality-box.png',
        blocks: [
          {
            h: '高品质商品',
            p: 'Joybuy 自营零售端到端运营，从商品采购到配送全链路把控，确保每件商品都达到我们的品质标准。我们的目标是提供可靠、值得信赖的购物体验，每一笔订单都通过专业管理、完全合规的零售体系处理。',
          },
        ],
        extra: {
          title: '喜讯',
          h: 'UEFA 官方合作伙伴',
          p: 'Joybuy 很荣幸成为欧冠联赛（UEFA Champions League）官方电商创新合作伙伴——全球最受信赖、最具知名度的体育赛事之一。我们让球迷更贴近赛场：不仅在比赛日，更体现在发现、购物和参与所爱产品与体验的方式上。这次合作意味着更具连接感的球迷体验——还有源自世界最大足球舞台的特别时刻与球票抽奖，均通过 Joybuy 以简单可信赖的方式带给您。',
          img: '/images/about/uefa.jpg',
        },
      },
      {
        id: 'support',
        title: '24/7 全天候专属客服',
        img: '/images/about/support-wide.png',
        blocks: [
          {
            h: '值得信赖的快速响应',
            p: '体验 24/7 在线客服的尊享支持。无论何时何地，我们都在您身边。我们将在 1 个工作日内开始处理您的投诉，并在 2 个工作日内回复，随后持续跟进直至问题完全解决。',
          },
        ],
        extra: {
          title: '您的全天候支持团队',
          h: '联系我们',
          img: '/images/about/support-agent.png',
          cards: [
            { icon: '/images/about/icon-chat.png', t: '在线客服', d: '随时、无间断。' },
            { icon: '/images/about/icon-email.png', t: '电子邮件', d: 'Joybuyfumi@gmail.com' },
            { icon: '/images/about/icon-submit.png', t: '提交请求', d: '还有其他问题？' },
          ],
        },
      },
      {
        id: 'deals',
        title: '专享优惠，价格更优',
        img: '/images/about/deals-box.png',
        blocks: [
          {
            h: '每日闪购优惠',
            p: '每天捕捉新优惠。每个优惠都包含专属折扣和实时库存进度条，您可以清楚看到剩余件数，及时发现热门优惠即将售罄。优惠每日更新，库存有限。从数码家电到居家好物，总有意想不到的值得发现。看到喜欢的？趁它还在赶紧下手！',
          },
        ],
        cta: '今日优惠',
      },
      {
        id: 'returns',
        title: '30 天内轻松退货，省心无忧',
        img: '/images/about/returns.png',
        blocks: [
          { h: '退货很简单', p: '改变主意了？没关系。30 天内退货即可享受全额退款，轻松无忧。' },
        ],
        how: {
          title: '使用方法：退货很简单',
          steps: [
            {
              icon: '/images/about/step-return.png',
              t: '30 天内提交退货',
              d: '在订单页点击「退货商品」进行选择。',
            },
            {
              icon: '/images/about/step-ship.png',
              t: '免费寄回',
              d: '大多数情况下已预付运费——有我们呢！',
            },
            {
              icon: '/images/about/step-refund.png',
              t: '收到退款',
              d: '确认退货符合政策后，退款将在 3–5 个工作日内到账。',
            },
          ],
        },
      },
      {
        id: 'payment',
        title: '安全购物，放心支付',
        img: '/images/about/laptop-pay.png',
        blocks: [
          {
            h: '您的支付，由您做主',
            p: '您的安全至上。通过受信任的全球支付伙伴和加密技术，您的每一笔消费都受到保护。',
          },
        ],
        payTiles: [
          { icon: '/images/about/pay-klarna.png', t: 'Klarna', d: '分期付款' },
          { icon: '/images/about/pay-paypal.png', t: 'PayPal', d: '三期支付' },
          { icon: '/images/about/pay-applepay.png', t: 'Apple Pay', d: 'Apple 方式支付' },
          { icon: '/images/about/pay-googlepay.png', t: 'Google Pay', d: '快捷结账' },
        ],
        extra: {
          title: '安全、简单、灵活',
          h: '我们支持',
          img: '/images/about/wallet.jpg',
          cards: ['American Express', 'VISA', 'Mastercard', 'Maestro'],
        },
      },
      {
        id: 'invite',
        title: '邀请好友，赚奖励！',
        img: '/images/about/invite.png',
        blocks: [{ h: '带上朋友，一起狂欢', p: '好友分享 Joybuy，一起赚取奖励。' }],
        how: {
          title: '使用方法',
          steps: [
            {
              icon: '/images/about/step-code.png',
              t: '分享您的邀请码',
              d: '前往个人主页查看您的专属邀请码。复制邀请码或直接分享链接给好友。',
            },
            {
              icon: '/images/about/step-order.png',
              t: '好友下单',
              d: '好友注册 Joybuy 账户后，在其首单结账页输入您的邀请码即可兑换专属折扣（仅限 Joybuy App 内订单）。',
            },
            {
              icon: '/images/about/step-reward.png',
              t: '赢取奖励',
              d: '好友首单签收成功后，积分奖励将自动发放。奖励不设上限。',
            },
          ],
        },
        cta: '立即邀请',
      },
    ],
    joyplus: {
      title: 'JoyPlus，不止是会员',
      h: '不止是会员',
      rows: [
        '百万商品不限次免邮——快速可靠，无消费门槛。',
        '专享积分。每笔消费都在累积！可在未来订单中抵扣。',
        '每日新品额外优惠与会员专享价。',
      ],
      cta: '立即加入 JoyPlus',
    },
    tc: {
      title: '条款与条件',
      items: [
        {
          q: '在哪里可以找到迎新优惠？',
          a: '注册后 30 天内，请访问「新客限时福利」专区，即可任选一件心仪商品，享受专属新客价！新客福利仅限一次，系统自动应用最优折扣；已享受新客价的商品不能与其他优惠券或促销活动叠加使用，但仍可使用运费券。App 专享优惠：此迎新优惠仅限 App 内使用。',
        },
        {
          q: 'JoyPoints 积分如何使用？',
          a: 'JoyPoints 是每笔消费均可获得的奖励积分，自动累积，可在未来订单中抵扣使用。',
        },
        {
          q: '我如何确保付款成功？',
          a: '我们希望您在 Joybuy 的体验顺畅无忧！请确保您的个人信息正确，并与您在银行预留的信息一致；如果正在预购商品，请确保银行卡在发售日当天仍然有效，并核对账单地址；注册并使用 Visa Secure 或 Mastercard SecureCode 等银行卡安全认证服务。计划大额消费？请提前告知您的银行。',
        },
        {
          q: '什么是 JoyPlus 会员？',
          a: 'JoyPlus 是 Joybuy 的会员计划，让日常购物更超值。会员在有效期内享受符合条件商品的无限次免邮和会员专享价，每笔消费自动累积 JoyPoints 积分，买得越多省得越多。',
        },
      ],
    },
  }
  return locale.value === 'zh' ? zh : en
})

const openFaq = ref(0)

function toggleFaq(index) {
  openFaq.value = openFaq.value === index ? -1 : index
}

useHead({ title: () => `Get to know Joybuy | Fast Delivery, Trust Brands & Everyday Deals` })
</script>

<template>
  <div class="about-page">
    <div class="about-page__inner">
      <!-- 面包屑 + hero（真站 home / Welcome to Joybuy） -->
      <nav class="about-breadcrumb" aria-label="Breadcrumb">
        <NuxtLink to="/">{{ locale === 'zh' ? '首页' : 'home' }}</NuxtLink>
        <span aria-hidden="true">/</span>
        <span>{{ T.breadcrumb }}</span>
      </nav>
      <section class="about-hero">
        <div class="about-hero__text">
          <h1 class="about-hero__title">{{ T.heroTitle }}</h1>
          <NuxtLink class="about-hero__sign" to="/auth/login">{{ T.heroSign }}</NuxtLink>
        </div>
        <img
          class="about-hero__img"
          src="/images/about/hero-door.png"
          alt=""
          width="360"
          height="180"
          loading="eager"
        />
      </section>

      <!-- 三支柱 -->
      <section class="about-pillars">
        <article v-for="pillar in T.pillars" :key="pillar.title" class="about-pillar">
          <img
            class="about-pillar__icon"
            :src="pillar.icon"
            alt=""
            width="40"
            height="40"
            loading="lazy"
          />
          <h2 class="about-pillar__title">{{ pillar.title }}</h2>
          <p class="about-pillar__text">{{ pillar.text }}</p>
          <a class="about-pillar__more" href="#about-floors" @click.prevent>{{ T.pillarMore }}</a>
        </article>
      </section>

      <!-- 楼层 -->
      <div id="about-floors">
        <section v-for="floor in T.floors" :key="floor.id" class="about-floor">
          <h2 class="about-floor__title">{{ floor.title }}</h2>
          <div class="about-floor__media">
            <img class="about-floor__img" :src="floor.img" :alt="floor.title" loading="lazy" />
            <div class="about-floor__blocks">
              <div v-for="block in floor.blocks" :key="block.h" class="about-block">
                <h3 class="about-block__h">{{ block.h }}</h3>
                <p class="about-block__p">{{ block.p }}</p>
              </div>
              <button v-if="floor.cta" class="about-floor__cta" type="button">
                {{ floor.cta }}
              </button>
            </div>
          </div>
          <div v-if="floor.how" class="about-how">
            <h3 class="about-how__title">{{ floor.how.title }}</h3>
            <div class="about-how__steps">
              <div v-for="step in floor.how.steps" :key="step.t" class="about-step">
                <img
                  class="about-step__icon"
                  :src="step.icon"
                  alt=""
                  width="72"
                  height="72"
                  loading="lazy"
                />
                <p class="about-step__t">{{ step.t }}</p>
                <p class="about-step__d">{{ step.d }}</p>
              </div>
            </div>
            <img
              v-if="floor.how.img"
              class="about-how__img"
              :src="floor.how.img"
              alt=""
              loading="lazy"
            />
          </div>
          <!-- 支付方式瓦片（真站 Klarna/PayPal/Apple Pay/Google Pay，位于 We accept 之前） -->
          <div v-if="floor.payTiles" class="about-tiles">
            <div v-for="tile in floor.payTiles" :key="tile.t" class="about-tile">
              <img
                class="about-tile__icon"
                :src="tile.icon"
                alt=""
                width="56"
                height="56"
                loading="lazy"
              />
              <p class="about-tile__t">{{ tile.t }}</p>
              <p class="about-tile__d">{{ tile.d }}</p>
            </div>
          </div>
          <div v-if="floor.extra" class="about-extra">
            <div class="about-extra__body">
              <p class="about-extra__title">{{ floor.extra.title }}</p>
              <h3 class="about-extra__h">{{ floor.extra.h }}</h3>
              <p v-if="floor.extra.p" class="about-extra__p">{{ floor.extra.p }}</p>
              <div
                v-if="Array.isArray(floor.extra.cards) && typeof floor.extra.cards[0] === 'string'"
                class="about-extra__cards"
              >
                <p v-for="card in floor.extra.cards" :key="card" class="about-extra__card">
                  {{ card }}
                </p>
              </div>
            </div>
            <img
              v-if="floor.extra.img"
              class="about-extra__img"
              :src="floor.extra.img"
              alt=""
              loading="lazy"
            />
          </div>
          <!-- 客服联系卡（真站 Your 24/7 support team 三卡） -->
          <div v-if="floor.id === 'support'" class="about-cards">
            <div v-for="card in floor.extra.cards" :key="card.t" class="about-card">
              <img
                class="about-card__icon"
                :src="card.icon"
                alt=""
                width="64"
                height="64"
                loading="lazy"
              />
              <p class="about-card__t">{{ card.t }}</p>
              <p class="about-card__d">{{ card.d }}</p>
            </div>
          </div>
        </section>
      </div>

      <!-- JoyPlus 楼层 -->
      <section class="about-joyplus">
        <h2 class="about-floor__title">{{ T.joyplus.title }}</h2>
        <h3 class="about-joyplus__h">{{ T.joyplus.h }}</h3>
        <ul class="about-joyplus__rows">
          <li v-for="row in T.joyplus.rows" :key="row" class="about-joyplus__row">{{ row }}</li>
        </ul>
        <button class="about-floor__cta about-floor__cta--primary" type="button">
          {{ T.joyplus.cta }}
        </button>
      </section>

      <!-- T&C 手风琴 -->
      <section class="about-tc">
        <h2 class="about-floor__title">{{ T.tc.title }}</h2>
        <div v-for="(item, index) in T.tc.items" :key="item.q" class="about-tc__item">
          <button
            class="about-tc__q"
            type="button"
            :aria-expanded="openFaq === index"
            @click="toggleFaq(index)"
          >
            {{ item.q }}
            <span class="about-tc__chevron" aria-hidden="true">{{
              openFaq === index ? '−' : '+'
            }}</span>
          </button>
          <p v-show="openFaq === index" class="about-tc__a">{{ item.a }}</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.about-page {
  background: var(--colour-surface);
  padding: var(--space-6) 0 var(--space-8);
}

.about-page__inner {
  max-width: var(--container-max);
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

.about-breadcrumb {
  display: flex;
  gap: var(--space-2);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.about-breadcrumb a {
  color: var(--colour-muted);
  text-decoration: none;
}

.about-breadcrumb a:hover {
  color: var(--colour-accent);
}

/* hero */
.about-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-6);
  margin-top: var(--space-5);
}

.about-hero__title {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
}

.about-hero__sign {
  color: var(--colour-accent);
  text-decoration: underline;
  font-weight: var(--font-weight-semibold);
}

.about-hero__img {
  display: block;
  height: auto;
  max-width: 420px;
  border-radius: var(--radius-md);
}

/* 三支柱 */
.about-pillars {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-5);
  margin-top: var(--space-7);
}

.about-pillar {
  padding: var(--space-5);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.about-pillar__icon {
  display: block;
  width: 40px;
  height: 40px;
}

.about-pillar__title {
  margin: var(--space-3) 0 var(--space-2);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}

.about-pillar__text {
  margin: 0 0 var(--space-3);
  color: #505259;
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.about-pillar__more {
  color: var(--colour-accent);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

/* 楼层 */
.about-floor {
  margin-top: var(--space-8);
  padding-top: var(--space-6);
  border-top: 1px solid var(--colour-border);
}

.about-floor__title {
  margin: 0 0 var(--space-5);
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
}

.about-floor__media {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  align-items: flex-start;
}

.about-floor__img {
  display: block;
  flex-shrink: 0;
  width: min(46%, 560px);
  height: auto;
  border-radius: var(--radius-md);
}

.about-floor__blocks {
  flex: 1;
  min-width: 260px;
}

.about-block__h {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}

.about-block__p {
  margin: 0 0 var(--space-4);
  color: #505259;
  line-height: 1.7;
}

.about-floor__cta {
  min-height: 44px;
  padding: var(--space-2) var(--space-6);
  border: 1px solid #1a1a1a;
  border-radius: var(--radius-sm);
  background: var(--colour-surface);
  color: #1a1a1a;
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.about-floor__cta--primary {
  background: #1a1a1a;
  color: var(--colour-surface);
}

.about-floor__cta:hover {
  background: #000;
  color: var(--colour-surface);
}

/* How it works 步骤 */
.about-how {
  margin-top: var(--space-6);
  padding: var(--space-5);
  border-radius: var(--radius-md);
  background: #f5f6fa;
}

.about-how__title {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}

.about-how__steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-5);
}

.about-step__icon {
  display: block;
  width: 72px;
  height: 72px;
}

.about-step__t {
  margin: var(--space-2) 0 var(--space-1);
  font-weight: var(--font-weight-bold);
}

.about-step__d {
  margin: 0;
  color: #505259;
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.about-how__img {
  display: block;
  width: 100%;
  max-height: 320px;
  margin-top: var(--space-5);
  border-radius: var(--radius-md);
}

/* 楼层内附块（UEFA / We accept 等） */
.about-extra {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  align-items: flex-start;
  margin-top: var(--space-6);
  padding: var(--space-5);
  border-radius: var(--radius-md);
  background: #f5f6fa;
}

.about-extra__body {
  flex: 1;
  min-width: 260px;
}

.about-extra__title {
  margin: 0 0 var(--space-1);
  color: var(--colour-accent);
  font-weight: var(--font-weight-bold);
}

.about-extra__h {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}

.about-extra__p {
  margin: 0;
  color: #505259;
  line-height: 1.7;
}

.about-extra__cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.about-extra__card {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  background: var(--colour-surface);
  font-weight: var(--font-weight-semibold);
}

.about-extra__img {
  display: block;
  width: min(40%, 420px);
  height: auto;
  border-radius: var(--radius-md);
}

/* 联系卡 / 支付瓦片 */
.about-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-5);
  margin-top: var(--space-5);
}

/* 真站支付瓦片为 Klarna / PayPal / Apple Pay / Google Pay 一行四个 */
.about-tiles {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-5);
}

.about-card,
.about-tile {
  padding: var(--space-5);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  text-align: center;
}

.about-card__icon,
.about-tile__icon {
  display: block;
  width: 64px;
  height: 64px;
  margin: 0 auto var(--space-3);
}

.about-card__t,
.about-tile__t {
  margin: 0 0 var(--space-1);
  font-weight: var(--font-weight-bold);
}

.about-card__d,
.about-tile__d {
  margin: 0;
  color: #505259;
  font-size: var(--font-size-sm);
}

/* JoyPlus 楼层 */
.about-joyplus {
  margin-top: var(--space-8);
  padding: var(--space-6);
  border-radius: var(--radius-md);
  background: #f5f6fa;
}

.about-joyplus__h {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}

.about-joyplus__rows {
  margin: 0 0 var(--space-5);
  padding-left: var(--space-5);
}

.about-joyplus__row {
  margin-bottom: var(--space-2);
  color: #505259;
  line-height: 1.6;
}

/* T&C 手风琴 */
.about-tc {
  margin-top: var(--space-8);
}

.about-tc__item {
  border-bottom: 1px solid var(--colour-border);
}

.about-tc__q {
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
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.about-tc__chevron {
  color: var(--colour-muted);
  font-size: var(--font-size-xl);
}

.about-tc__a {
  margin: 0 0 var(--space-4);
  color: #505259;
  line-height: 1.7;
}

@media (max-width: 48rem) {
  .about-pillars,
  .about-how__steps,
  .about-cards,
  .about-extra__cards {
    grid-template-columns: 1fr;
  }

  .about-tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .about-floor__img,
  .about-extra__img {
    width: 100%;
  }
}
</style>
