<script setup>
import { computed, ref } from 'vue'


import { useLocale } from '../composables/useLocale'

// 页脚 1:1 复刻真站 footer_jdiFooter（需求 12.1，实测见
// var/footer_rework_20261119/measurement.md）：
// 顶行 logo+口号 / 语言·货币·国家三个框；中部 订阅块+App 二维码块；
// 三列链接（Get to know us / Our policies / Let us help you，第三列无链接）；
// We support 支付行；© 行（Personalised settings / Manage cookies）；法规段落。
// 颜色/尺寸取自真站 CSS 原文（--sys-background-MainGray #F5F6FA 等）。
// /checkout 仍走需求 8-8 的极简变体。
// 需求 13.6：顶行（含语言切换按钮）注释不渲染后 toggleLocale 一并停用，避免孤儿引用。
const { t } = useLocale()

// 2026-11-28（用户拍板）：页脚全站统一——/checkout 不再走精简分支，
// 与其他页面一样展示【了解我们】【我们的政策】【帮助中心】等完整栏目。

// 需求 16.5（批次 S）：三栏内容按本轮口径调整 ——
// 了解 Joybuy 去掉 JoyPlus（页面保留，页脚不再链接）；我们的政策补销售条款与无障碍
// 声明（共 5 项，与 help 中心左栏一致）；帮助中心只保留支付和发票、退货和退款两项。
const columns = computed(() => [
  {
    title: t('footer.colKnow'),
    links: [
      { label: t('footer.linkContactUs'), to: '/pages/contact-us' },
      { label: t('footer.linkAboutUs'), to: '/pages/about-us' },
      { label: t('footer.linkNews'), to: '/pages/joybuy-news' },
    ],
  },
  {
    title: t('footer.colPolicies'),
    links: [
      { label: t('footer.linkCookiePolicy'), to: '/pages/cookie-policy' },
      { label: t('footer.linkPrivacy'), to: '/pages/privacy-policy' },
      { label: t('footer.linkTerms'), to: '/pages/terms-conditions' },
      { label: t('footer.linkTermsOfUse'), to: '/pages/terms-of-use' },
      { label: t('footer.linkAccessibility'), to: '/pages/accessibility-statement' },
    ],
  },
  {
    title: t('footer.colHelp'),
    links: [
      { label: t('footer.linkPaymentInvoice'), to: '/pages/payment-and-invoice' },
      { label: t('footer.linkReturnsRefunds'), to: '/pages/returns-and-refunds' },
    ],
  },
])

// 2026-11-28：8 个银行卡品牌 + Google Pay/PayPal/Klarna（真站结算页口径），
// 全部为官方 logo SVG（Wikimedia Commons 下载，本地托管）。
const paymentBrands = [
  { name: 'Visa', icon: '/images/pdp-services/payment-visa.svg' },
  { name: 'Mastercard', icon: '/images/pdp-services/payment-mastercard.svg' },
  { name: 'Maestro', icon: '/images/pdp-services/payment-maestro.svg' },
  { name: 'American Express', icon: '/images/pdp-services/payment-american-express.svg' },
  { name: 'Diners Club', icon: '/images/pdp-services/payment-dinersclub.svg' },
  { name: 'Discover', icon: '/images/pdp-services/payment-discover.svg' },
  { name: 'JCB', icon: '/images/pdp-services/payment-jcb.svg' },
  { name: 'UnionPay', icon: '/images/pdp-services/payment-unionpay.svg' },
  { name: 'Google Pay', icon: '/images/pdp-services/payment-google-pay.svg' },
  { name: 'PayPal', icon: '/images/pdp-services/payment-paypal.svg' },
  { name: 'Klarna', icon: '/images/pdp-services/payment-klarna.svg' },
]

const email = ref('')
const subscribed = ref(false)

function subscribe() {
  if (!email.value.trim()) return
  subscribed.value = true
}
</script>

<template>
  <footer class="site-footer">
    <div class="site-footer__inner">
      <!-- 需求 13.6（2026-11-20）：顶行（logo+口号 / 语言·货币·国家）注释不渲染，
           代码保留；语言切换交互（toggleLocale）随之停用。 -->
      <div v-if="false" class="footer-top">
        <div class="footer-top__left">
          <img
            class="footer-top__logo"
            src="/images/footer/logo.png"
            alt="Joybuy"
            width="103"
            height="28"
          />
          <p class="footer-top__slogan">{{ t('footer.slogan') }}</p>
        </div>
        <div class="footer-top__intl">
          <button
            class="footer-top__box footer-top__box--button"
            type="button"
            :aria-label="t('footer.langSwitch')"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path
                d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm7.93 9h-3.02a15.7 15.7 0 0 0-1.2-5.2A8.03 8.03 0 0 1 19.93 11ZM12 4.07c.94 1.2 1.9 3.4 2.1 6.93H9.9c.2-3.53 1.16-5.73 2.1-6.93ZM4.07 13h3.02c.14 1.9.55 3.68 1.2 5.2A8.03 8.03 0 0 1 4.07 13Zm3.02-2H4.07a8.03 8.03 0 0 1 4.22-5.2 15.7 15.7 0 0 0-1.2 5.2ZM12 19.93c-.94-1.2-1.9-3.4-2.1-6.93h4.2c-.2 3.53-1.16 5.73-2.1 6.93Zm3.71-1.73c.65-1.52 1.06-3.3 1.2-5.2h3.02a8.03 8.03 0 0 1-4.22 5.2Z"
                fill="currentColor"
              />
            </svg>
            <span>{{ t('footer.langLabel') }}</span>
            <svg
              class="footer-top__caret"
              viewBox="0 0 24 24"
              width="12"
              height="12"
              aria-hidden="true"
            >
              <path d="m7 10 5 5 5-5H7Z" fill="currentColor" />
            </svg>
          </button>
          <span class="footer-top__box">{{ t('footer.currency') }}</span>
          <span class="footer-top__box">
            <img
              class="footer-top__flag"
              src="/images/footer/flag-uk.png"
              alt=""
              width="24"
              height="16"
            />
            <span>{{ t('footer.country') }}</span>
          </span>
        </div>
      </div>

      <!-- 需求 13.6：中部（订阅 + App 下载）注释不渲染，代码保留。 -->
      <div v-if="false" class="footer-middle">
        <div class="footer-middle__newsletter">
          <img
            class="footer-middle__parcel"
            src="/images/footer/parcel.png"
            alt=""
            width="130"
            height="86"
            loading="lazy"
          />
          <div class="footer-middle__newsletter-body">
            <h2 class="footer-middle__title">{{ t('footer.newsletterTitle') }}</h2>
            <p class="footer-middle__desc">{{ t('footer.newsletterDesc') }}</p>
            <form v-if="!subscribed" class="footer-middle__form" @submit.prevent="subscribe">
              <label class="visually-hidden" for="footer-email">{{
                t('footer.emailPlaceholder')
              }}</label>
              <input
                id="footer-email"
                v-model="email"
                class="footer-middle__input"
                type="email"
                name="email"
                :placeholder="t('footer.emailPlaceholder')"
                autocomplete="email"
              />
              <button class="footer-middle__subscribe" type="submit">
                {{ t('footer.subscribe') }}
              </button>
            </form>
            <p v-else class="footer-middle__thanks">{{ t('footer.subscribedThanks') }}</p>
          </div>
        </div>
        <div class="footer-middle__download">
          <img
            class="footer-middle__qr"
            src="/images/footer/app-qr.png"
            alt="QR"
            width="96"
            height="96"
            loading="lazy"
          />
          <div class="footer-middle__download-body">
            <h2 class="footer-middle__title">{{ t('footer.appTitle') }}</h2>
            <p class="footer-middle__desc">{{ t('footer.appDesc') }}</p>
            <div class="footer-middle__badges">
              <img
                src="/images/footer/badge-appstore.svg"
                alt="App Store"
                width="108"
                height="36"
                loading="lazy"
              />
              <img
                src="/images/footer/badge-googleplay.svg"
                alt="Google Play"
                width="108"
                height="36"
                loading="lazy"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 三列链接（需求 16.5：含帮助中心两项） -->
      <div class="footer-columns">
        <section v-for="column in columns" :key="column.title" class="footer-column">
          <h2 class="footer-column__title">{{ column.title }}</h2>
          <ul class="footer-column__list">
            <li v-for="link in column.links" :key="link.to">
              <NuxtLink class="footer-column__link" :to="link.to">{{ link.label }}</NuxtLink>
            </li>
          </ul>
        </section>
      </div>

      <!-- We support 支付行 -->
      <div class="footer-support">
        <span class="footer-support__label">{{ t('footer.weSupport') }}</span>
        <img
          v-for="brand in paymentBrands"
          :key="brand.name"
          class="footer-support__icon"
          :src="brand.icon"
          :alt="brand.name"
          width="38"
          height="24"
          loading="lazy"
        />
      </div>

      <!-- © 行 -->
      <div class="footer-bottom">
        <p class="footer-bottom__copyright">{{ t('footer.copyright') }}</p>
        <span class="footer-bottom__links">
          <a href="#" @click.prevent>{{ t('footer.personalised') }}</a>
          <a href="#" @click.prevent>{{ t('footer.manageCookies') }}</a>
        </span>
      </div>

      <!-- 法规段落（真站仅 EN 页脚展示）；需求 13.6：最底部【内部研究演示项目…】
           声明行去掉，中性 demo 实体法规文案保留（法律安全口径，勿回退）。 -->
      <p v-if="t('footer.legal')" class="footer-legal">{{ t('footer.legal') }}</p>
    </div>
  </footer>
</template>

<style scoped>
.site-footer {
  margin-top: auto;
  min-width: 0;
  background: #f5f6fa; /* 真站 --sys-background-MainGray */
  color: #1a1a1a; /* 真站 --sys-Text-Primary */
}

.site-footer__support {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

/* icon 变体：11 个官方 logo 换行排布，白色小卡底衬托官方 logo。 */
.site-footer__brand {
  padding: 2px var(--space-2);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  background: var(--colour-surface);
  color: var(--colour-text);
}

.site-footer__inner {
  max-width: 1512px; /* 真站 footer_newWidth max-width */
  margin-inline: auto;
  padding: var(--space-6) var(--container-pad) var(--space-6);
}

/* 顶行 */
.footer-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  min-height: 72px; /* 真站 footer_footerTop height:72px */
}

.footer-top__left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.footer-top__logo {
  display: block;
  height: 28px;
  width: auto;
}

.footer-top__slogan {
  margin: 0;
  font-size: 16px;
  line-height: 22px;
}

.footer-top__intl {
  display: flex;
  flex-wrap: wrap;
  gap: clamp(10px, 2vw, 30px); /* 真站 footer_internationalWrap gap */
}

.footer-top__box {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  font-size: var(--font-size-sm);
}

.footer-top__box--button {
  cursor: pointer;
  font: inherit;
  font-size: var(--font-size-sm);
}

.footer-top__box--button:hover {
  color: var(--colour-accent);
}

.footer-top__caret {
  color: var(--colour-muted);
}

.footer-top__flag {
  display: block;
  border-radius: 2px;
}

/* 中部订阅 + App */
.footer-middle {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  padding-block: var(--space-6);
  border-top: 1px solid var(--colour-border);
}

.footer-middle__newsletter {
  display: flex;
  flex: 1;
  align-items: flex-start;
  gap: var(--space-5);
  min-width: 260px;
}

.footer-middle__parcel {
  display: block;
  width: 130px;
  height: auto;
}

.footer-middle__newsletter-body {
  flex: 1;
  min-width: 0;
  max-width: 546px; /* 真站 footer_oldEmailContainer width */
}

.footer-middle__title {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 700;
  line-height: 20px;
}

.footer-middle__desc {
  margin: 0 0 var(--space-4);
  color: #505259; /* 真站 --sys-Text-Secondary */
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.footer-middle__form {
  display: flex;
  gap: var(--space-4);
}

.footer-middle__input {
  flex: 1;
  min-width: 0;
  min-height: 44px;
  padding: var(--space-2) var(--space-4);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: rgba(0, 16, 71, 0.059); /* 真站 footer_emailInput 背景 */
  font-size: var(--font-size-sm);
}

.footer-middle__input:focus {
  outline: none;
  border-color: #1a1a1a;
}

.footer-middle__subscribe {
  min-height: 44px;
  padding: var(--space-2) var(--space-6);
  border: 0;
  border-radius: var(--radius-sm);
  background: #1a1a1a;
  color: var(--colour-surface);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
}

.footer-middle__subscribe:hover {
  background: #000;
}

.footer-middle__thanks {
  margin: 0;
  color: var(--colour-success);
  font-size: var(--font-size-sm);
}

.footer-middle__download {
  display: flex;
  flex: 1;
  align-items: flex-start;
  gap: var(--space-5);
  min-width: 260px;
}

.footer-middle__qr {
  display: block;
  width: 96px;
  height: 96px;
}

.footer-middle__download-body {
  min-width: 0;
}

.footer-middle__badges {
  display: flex;
  gap: var(--space-3);
}

.footer-middle__badges img {
  display: block;
  height: 36px;
  width: auto;
}

/* 三列链接 */
.footer-columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-8);
  padding-block: var(--space-6);
  border-top: 1px solid var(--colour-border);
}

.footer-column__title {
  margin: 0 0 8px; /* 真站 footer_title margin-bottom:8px */
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
}

/* 需求 17.4：三栏条目间距按真站收紧（footer_jdiFooter CSS 原文实测：
   .footer_links___k1TA{font-size:14px} + li{margin-bottom:16px}，全局
   html line-height:1.5 → 行盒 21px，相邻链接 y 差 = 21 + 16 = 37px）。
   旧值 min-height 44px + gap 8px → 52px，偏大。只动条目行距，不影响
   支付行 / © 行 / 法规段。 */
.footer-column__list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.footer-column__link {
  display: inline-block;
  color: #1a1a1a;
  text-decoration: none;
  font-size: var(--font-size-md);
  line-height: 1.5;
}

.footer-column__link:hover {
  color: var(--colour-accent);
  text-decoration: underline;
}

/* We support 行 */
.footer-support {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding-block: var(--space-5);
  font-size: var(--font-size-sm);
}

.footer-support__icon {
  display: block;
  height: 24px;
  width: auto;
}

/* © 行 + 法规段落 */
.footer-bottom {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--space-2) var(--space-6);
  font-size: 12px;
  color: #6e7078; /* 真站 --Text_Tertiary */
}

.footer-bottom__copyright {
  margin: 0;
}

.footer-bottom__links {
  display: inline-flex;
  gap: var(--space-6);
}

.footer-bottom__links a {
  color: #6e7078;
  text-decoration: none;
}

.footer-bottom__links a:hover {
  text-decoration: underline;
}

.footer-legal {
  margin: var(--space-4) 0 0;
  color: #6e7078;
  text-align: center;
  font-size: 12px;
  line-height: 1.6;
}

/* 390/375: 全部块纵向堆叠。 */
@media (max-width: 30rem) {
  .footer-top,
  .footer-middle__newsletter,
  .footer-middle__download {
    flex-direction: column;
    align-items: flex-start;
  }

  .footer-columns {
    grid-template-columns: 1fr;
    gap: var(--space-6);
  }

  .footer-middle__form {
    flex-direction: column;
  }
}
</style>
