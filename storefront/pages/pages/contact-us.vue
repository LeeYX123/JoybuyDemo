<script setup>
import { computed, ref } from 'vue'

import { useLocale } from '../../composables/useLocale'
import { useBuyerAuth } from '../../composables/useBuyerAuth'

// 需求 12.1：1:1 复刻真站 discover/contact-us-for-web——
// 无品类导航的简洁顶栏（footer-page 布局）+ 左侧双 tab（联系我们 / 与 Joybuy 合作）
// + 右侧内容区切换。文案为真站实测（EN）+ 中文翻译，替换规则已生效。
definePageMeta({ layout: 'footer-page' })

const { locale, t } = useLocale()
const { isAuthenticated } = useBuyerAuth()

// 批次 CA：第二条 CTA 跳申请店铺页；未登录走登录并带 next（沿用 AppHeader 约定）。
const applyShopTarget = computed(() =>
  isAuthenticated.value
    ? '/account/apply-shop'
    : { path: '/auth/login', query: { next: '/account/apply-shop' } },
)

const T = computed(() => {
  const en = {
    tabs: ['Contact us', 'Partner with Joybuy'],
    contact: {
      title: 'Contact us',
      lead: "Got a question about your order, delivery, or products? We're here to assist you.",
      blocks: [
        {
          label: 'Email',
          text: ': Joybuyfumi@gmail.com',
        },
        {
          label: 'Live Chat',
          text: ': Available 24/7 for instant assistance. You can start a chat instantly via the Joybuy App by going to Me → Customer Service → Online Chat, or by clicking the "Customer Service" floating icon on our website.',
        },
        {
          label: 'Callback Service',
          text: ': To get help faster, our phone support has been upgraded to a callback service starting Dec 24, 2025. To request a callback, please go to Me → Customer Service → Request a Callback in the latest version of the Joybuy App. Our agent will contact you promptly.',
        },
      ],
    },
    partner: {
      title: 'Partner with Joybuy',
      lead: 'Welcome to Partner with Joybuy!',
      vendorTitle: 'Enroll as a Vendor',
      vendorText:
        'Supply products directly to Joybuy. Joybuy purchases inventory from your business and sells it to a wide customer base through the platform, helping you grow your business through greater market exposure.',
      // 批次 CA：真站该句为纯文本（仅 here 是默认蓝链接）；本页改为不可点提示 + 邮箱。
      vendorCta: 'To apply for partnership, please contact us: Joybuyfumi@gmail.com',
      sellerTitle: 'Enroll as a Seller',
      sellerText:
        "Sell your products directly to customers on the Joybuy marketplace. Create and manage your own store, control pricing and inventory, and use Joybuy's platform to reach more customers and strengthen your brand.",
      sellerCta:
        'Please click here to fill out your expression of interest and register as a platform merchant for free.',
    },
  }
  const zh = {
    tabs: ['联系我们', '与 Joybuy 合作'],
    contact: {
      title: '联系我们',
      lead: '关于订单、配送或商品有任何疑问？我们随时为您解答。',
      blocks: [
        { label: '电子邮件', text: '：Joybuyfumi@gmail.com' },
        {
          label: '在线客服',
          text: '：全天候 24/7 即时支持。您可以在 Joybuy App 中进入「我的 → 客户服务中心 → 在线客服」即时发起会话，或点击网站上的「客户服务」悬浮图标。',
        },
        {
          label: '电话回呼',
          text: '：为了让您更快获得帮助，自 2025 年 12 月 24 日起，电话支持已升级为回呼服务。请在最新版 Joybuy App 中进入「我的 → 客户服务中心 → 申请回呼」，我们的客服会尽快与您联系。',
        },
      ],
    },
    partner: {
      title: '与 Joybuy 合作',
      lead: '欢迎与 Joybuy 合作！',
      vendorTitle: '注册成为供应商',
      vendorText:
        '直接向 Joybuy 供货。Joybuy 将从贵公司采购库存，并通过平台销售给广大客户，借助更广泛的市场触达，助力您的业务快速增长。',
      // 批次 CA：改为纯文本提示（含邮箱），不再可点。
      vendorCta: '需要申请合作的请联系我们： Joybuyfumi@gmail.com',
      sellerTitle: '注册成为商家',
      sellerText:
        '通过 Joybuy 商城直接向消费者销售商品。您可以创建并管理自己的店铺，自主掌控定价和库存，在借助 Joybuy 平台拓展客源的同时提升品牌影响力。',
      sellerCta: '请点击此处填写合作意向，免费注册成为平台商家。',
    },
  }
  return locale.value === 'zh' ? zh : en
})

const activeTab = ref(0)
const title = computed(() =>
  activeTab.value === 0 ? T.value.contact.title : T.value.partner.title,
)

useHead({ title: () => `${title.value} | Joybuy` })
</script>

<template>
  <div class="contact-page">
    <div class="contact-page__inner">
      <aside class="contact-menu" aria-label="Contact menu">
        <button
          v-for="(tab, index) in T.tabs"
          :key="tab"
          class="contact-menu__item"
          :class="{ 'contact-menu__item--active': activeTab === index }"
          type="button"
          @click="activeTab = index"
        >
          {{ tab }}
        </button>
      </aside>
      <section class="contact-detail">
        <!-- Tab 1：联系我们（真站 Contact us 内容态） -->
        <div v-show="activeTab === 0" class="contact-detail__pane">
          <h1 class="contact-detail__title">{{ T.contact.title }}</h1>
          <p class="contact-detail__lead contact-detail__lead--spaced">{{ T.contact.lead }}</p>
          <p
            v-for="block in T.contact.blocks"
            :key="block.label"
            class="contact-detail__row contact-detail__row--spaced"
          >
            <strong class="contact-detail__label">{{ block.label }}</strong>
            <span>{{ block.text }}</span>
          </p>
        </div>
        <!-- Tab 2：与 Joybuy 合作（真站 Partner with Joybuy 内容态） -->
        <div v-show="activeTab === 1" class="contact-detail__pane">
          <h1 class="contact-detail__title">{{ T.partner.title }}</h1>
          <p class="contact-detail__lead">{{ T.partner.lead }}</p>
          <h2 class="contact-detail__heading">{{ T.partner.vendorTitle }}</h2>
          <p class="contact-detail__row">{{ T.partner.vendorText }}</p>
          <p class="contact-detail__row">{{ T.partner.vendorCta }}</p>
          <h2 class="contact-detail__heading">{{ T.partner.sellerTitle }}</h2>
          <p class="contact-detail__row">{{ T.partner.sellerText }}</p>
          <p class="contact-detail__row">
            <NuxtLink class="contact-detail__cta" :to="applyShopTarget">
              {{ T.partner.sellerCta }}
            </NuxtLink>
          </p>
        </div>
      </section>
    </div>
    <p class="contact-page__back">
      <NuxtLink to="/">{{ t('pagesDoc.backHome') }}</NuxtLink>
    </p>
  </div>
</template>

<style scoped>
/* 批次 CA：真站实测值（var/ca_20261126/contact_dump.json / contact_partner_dump.json）
   灰带 detail_detailWrapper：整宽 #f5f6fa、padding 32px 0；
   主体 detail_mainWrapper：max 1264、左菜单 240 + 内容 1008（间距 16）；
   左菜单：白底 radius 8、padding 4px 12px、内层 nav padding 8px 0，item padding 16px 16px 20px
   16px/400/24px、选中色 rgb(255,15,35)；
   右内容：白底 radius 8、padding 24px 36px；
   标题：32px/700/32px 无外边距；正文 16px/400/24px；段落间距 10px；
   分区小标题（原 <strong>）16px/700，与前文间距 44px。 */
.contact-page {
  background: #f5f6fa;
  padding: 32px 0;
}

.contact-page__inner {
  display: flex;
  align-items: flex-start;
  max-width: 1264px;
  margin-inline: auto;
}

.contact-menu {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 240px;
  padding: 4px 12px;
  border-radius: 8px;
  background: #fff;
}

.contact-menu__item {
  display: block;
  width: 100%;
  padding: 16px 16px 20px;
  border: 0;
  border-radius: 0;
  background: transparent;
  text-align: left;
  color: #000;
  font-size: 16px;
  font-weight: 400;
  line-height: 24px;
  cursor: pointer;
}

.contact-menu__item:hover {
  color: rgb(255, 15, 35);
}

.contact-menu__item--active {
  color: rgb(255, 15, 35);
  font-weight: 400;
}

/* 右侧内容卡（真站 detail_itemContent） */
.contact-detail {
  flex: 1;
  min-width: 0;
  margin-left: 16px;
  padding: 24px 36px;
  border-radius: 8px;
  background: #fff;
}

.contact-detail__title {
  display: flex;
  align-items: center;
  margin: 0;
  color: #000;
  font-size: 32px;
  font-weight: 700;
  line-height: 32px;
}

.contact-detail__lead {
  margin: 10px 0;
  color: #000;
  font-size: 16px;
  line-height: 24px;
}

.contact-detail__heading {
  margin: 44px 0 10px;
  color: #000;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
}

.contact-detail__row {
  display: block;
  margin: 10px 0;
  color: #000;
  font-size: 16px;
  line-height: 24px;
}

/* 联系我们 tab：真站各段之间空一行（一个 24px 空行） */
.contact-detail__lead--spaced {
  margin-bottom: 34px;
}

.contact-detail__row--spaced {
  margin-bottom: 34px;
}

.contact-detail__label {
  font-weight: 700;
}

/* 真站正文链接是浏览器默认蓝 + 下划线（实测 rgb(0,0,238)） */
.contact-detail__cta {
  color: rgb(0, 0, 238);
  text-decoration: underline;
}

.contact-page__back {
  max-width: 1264px;
  margin: 24px auto 0;
}

.contact-page__back a {
  color: var(--colour-accent);
  text-decoration: none;
}

.contact-page__back a:hover {
  text-decoration: underline;
}

@media (max-width: 1312px) {
  .contact-page__inner,
  .contact-page__back {
    padding-inline: var(--container-pad);
  }
}

@media (max-width: 48rem) {
  .contact-page__inner {
    flex-direction: column;
  }

  .contact-menu {
    width: 100%;
    flex-direction: row;
    margin-bottom: 16px;
  }

  .contact-menu__item {
    text-align: center;
  }

  .contact-detail {
    width: 100%;
    margin-left: 0;
  }
}
</style>
