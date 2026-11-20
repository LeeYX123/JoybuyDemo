<script setup>
import { computed, ref } from 'vue'

import { useLocale } from '../../composables/useLocale'

// 需求 12.1：1:1 复刻真站 discover/contact-us-for-web——
// 无品类导航的简洁顶栏（footer-page 布局）+ 左侧双 tab（联系我们 / 与 Joybuy 合作）
// + 右侧内容区切换。文案为真站实测（EN）+ 中文翻译，替换规则已生效。
definePageMeta({ layout: 'footer-page' })

const { locale, t } = useLocale()

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
      vendorCta: 'Please click here to start your application.',
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
      vendorCta: '请点击此处开始您的入驻申请。',
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
          <p class="contact-detail__lead">{{ T.contact.lead }}</p>
          <p v-for="block in T.contact.blocks" :key="block.label" class="contact-detail__row">
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
          <p class="contact-detail__row">
            <a class="contact-detail__cta" href="#" @click.prevent>{{ T.partner.vendorCta }}</a>
          </p>
          <h2 class="contact-detail__heading">{{ T.partner.sellerTitle }}</h2>
          <p class="contact-detail__row">{{ T.partner.sellerText }}</p>
          <p class="contact-detail__row">
            <a class="contact-detail__cta" href="#" @click.prevent>{{ T.partner.sellerCta }}</a>
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
.contact-page {
  background: #f5f6fa;
  padding: var(--space-6) 0 var(--space-8);
}

.contact-page__inner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  max-width: var(--container-max);
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

/* 左侧菜单（真站 detail_menuWrapper：白色圆角卡 + 上下两个 tab） */
.contact-menu {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 216px;
  padding: var(--space-2);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.contact-menu__item {
  display: block;
  width: 100%;
  padding: var(--space-4) var(--space-3);
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  text-align: left;
  color: #1a1a1a;
  font-size: var(--font-size-md);
  cursor: pointer;
}

.contact-menu__item:hover {
  background: var(--colour-hover);
}

.contact-menu__item--active {
  color: #e1251b;
  font-weight: var(--font-weight-semibold);
}

/* 右侧内容卡（真站 detail_detailWrapper） */
.contact-detail {
  flex: 1;
  min-width: 0;
  padding: var(--space-6) var(--space-7) var(--space-7);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.contact-detail__title {
  margin: 0 0 var(--space-4);
  color: #1a1a1a;
  font-size: 32px;
  font-weight: var(--font-weight-bold);
  line-height: 1.2;
}

.contact-detail__lead {
  margin: 0 0 var(--space-6);
  color: #1a1a1a;
  line-height: 1.7;
}

.contact-detail__heading {
  margin: var(--space-6) 0 var(--space-2);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}

.contact-detail__row {
  display: block;
  margin: 0 0 var(--space-4);
  line-height: 1.7;
}

.contact-detail__label {
  font-weight: var(--font-weight-bold);
}

.contact-detail__cta {
  color: var(--colour-accent);
  text-decoration: underline;
}

.contact-page__back {
  max-width: var(--container-max);
  margin: var(--space-5) auto 0;
  padding-inline: var(--container-pad);
}

.contact-page__back a {
  color: var(--colour-accent);
  text-decoration: none;
}

.contact-page__back a:hover {
  text-decoration: underline;
}

@media (max-width: 48rem) {
  .contact-page__inner {
    flex-direction: column;
  }

  .contact-menu {
    width: 100%;
    flex-direction: row;
  }

  .contact-menu__item {
    text-align: center;
  }
}
</style>
