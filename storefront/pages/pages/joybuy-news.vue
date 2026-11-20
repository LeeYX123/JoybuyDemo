<script setup>
import { computed } from 'vue'

import { useLocale } from '../../composables/useLocale'

// 需求 12.1：Joybuy news = 真站页脚外链 Newsroom 落地页的结构复刻
//（实测见 var/footer_rework_20261119/measurement.md §2 #3）。
// EN 文案取自真站实测，已按需求三规则处理（地区口径、外链域名、邮箱）。
definePageMeta({ layout: 'footer-page' })

const { locale } = useLocale()

const T = computed(() => {
  const en = {
    nav: ['News', 'Media', 'Brand images', 'News images', 'Video', 'About', 'Careers', 'Contact'],
    langs: ['De', 'Fr', 'Nl'],
    heroTitle: "JD.com's Asian Online Retail Business",
    pillars: [
      { icon: '/images/news/icon-delivery.svg', t: 'Speedy and reliable delivery service' },
      { icon: '/images/news/icon-award.svg', t: 'Brands you love, quality you can trust' },
      { icon: '/images/news/icon-support.svg', t: '24/7 dedicated customer support' },
    ],
    countriesTitle: 'JOYBUY IN YOUR COUNTRY',
    countries: [
      { flag: '/images/news/flag-gb.svg', t: 'United Kingdom' },
      { flag: '/images/news/flag-fr.svg', t: 'France' },
      { flag: '/images/news/flag-de.svg', t: 'Germany' },
      { flag: '/images/news/flag-nl.svg', t: 'Netherlands' },
      { flag: '/images/news/flag-be.svg', t: 'Belgium' },
      { flag: '/images/news/flag-lu.svg', t: 'Luxembourg' },
    ],
    highlightsTitle: 'News Highlights',
    viewAll: 'View all news',
    articles: [
      {
        date: 'November 18, 2026',
        title:
          '3D printing your own Christmas gifts to the latest foldable smartphones: Discover tech on Joybuy this Black Friday',
      },
      {
        date: 'November 17, 2026',
        title:
          'Joybuy partners with Revolut Business to bring Revolut Pay and 5x rewards to customers across Asia',
      },
      {
        date: 'November 16, 2026',
        title:
          'Time for the Winter Switch: Expert reveals six ways to make your home feel warmer before turning up the heating',
      },
    ],
    readMore: 'Read more',
    linkedinTitle: 'Joybuy on Linkedin',
    linkedinText: 'Joybuy Linkedin Account',
    resourcesTitle: 'Other resources',
    resources: [
      { t: 'Media Library', d: 'Watch videos & download images' },
      { t: 'Media Contacts', d: 'Contact details for journalists' },
    ],
    newsFooter: {
      nav: ['News', 'Media', 'About', 'Careers', 'Contact'],
      join: 'Join our list and never miss updates.',
      submit: 'Submit',
    },
    copyright: '©2026 Joybuy. All Rights Reserved',
  }
  const zh = {
    nav: ['新闻', '媒体', '品牌图库', '新闻图片', '视频', '关于', '招聘', '联系'],
    langs: ['De', 'Fr', 'Nl'],
    heroTitle: 'JD.com 亚洲线上零售业务',
    pillars: [
      { icon: '/images/news/icon-delivery.svg', t: '快捷可靠的配送服务' },
      { icon: '/images/news/icon-award.svg', t: '挚爱品牌，信赖品质' },
      { icon: '/images/news/icon-support.svg', t: '24/7 专属客户支持' },
    ],
    countriesTitle: 'JOYBUY 所在国家',
    countries: [
      { flag: '/images/news/flag-gb.svg', t: '英国' },
      { flag: '/images/news/flag-fr.svg', t: '法国' },
      { flag: '/images/news/flag-de.svg', t: '德国' },
      { flag: '/images/news/flag-nl.svg', t: '荷兰' },
      { flag: '/images/news/flag-be.svg', t: '比利时' },
      { flag: '/images/news/flag-lu.svg', t: '卢森堡' },
    ],
    highlightsTitle: '新闻精选',
    viewAll: '查看全部新闻',
    articles: [
      {
        date: '2026 年 11 月 18 日',
        title: '从 3D 打印圣诞礼物到最新折叠屏手机：Black Friday 探索 Joybuy 数码好物',
      },
      {
        date: '2026 年 11 月 17 日',
        title: 'Joybuy 携手 Revolut Business，为亚洲客户带来 Revolut Pay 与 5 倍奖励',
      },
      { date: '2026 年 11 月 16 日', title: '冬季家居切换时：专家揭示让家里更温暖的六个方法' },
    ],
    readMore: '阅读更多',
    linkedinTitle: 'Joybuy 的 Linkedin',
    linkedinText: 'Joybuy Linkedin 账号',
    resourcesTitle: '其他资源',
    resources: [
      { t: '媒体资料库', d: '观看视频并下载图片' },
      { t: '媒体联系人', d: '记者联系方式' },
    ],
    newsFooter: {
      nav: ['新闻', '媒体', '关于', '招聘', '联系'],
      join: '订阅我们的列表，不错过任何更新。',
      submit: '提交',
    },
    copyright: '©2026 Joybuy. 保留所有权利',
  }
  return locale.value === 'zh' ? zh : en
})

useHead({ title: () => 'Joybuy Newsroom | Company News & Updates' })
</script>

<template>
  <div class="news-page">
    <!-- 顶部导航（真站 newsroom nav） -->
    <nav class="news-nav" aria-label="Newsroom">
      <img
        class="news-nav__logo"
        src="/images/news/logo.svg"
        alt="Joybuy Newsroom"
        width="120"
        height="28"
      />
      <ul class="news-nav__links">
        <li v-for="item in T.nav" :key="item">
          <a href="#" @click.prevent>{{ item }}</a>
        </li>
      </ul>
      <span class="news-nav__langs">
        <span v-for="lang in T.langs" :key="lang">{{ lang }}</span>
      </span>
    </nav>

    <div class="news-page__inner">
      <!-- hero -->
      <section class="news-hero">
        <h1 class="news-hero__title">{{ T.heroTitle }}</h1>
        <img
          class="news-hero__img"
          src="/images/news/hero.jpg"
          alt=""
          width="480"
          height="320"
          loading="eager"
        />
      </section>

      <!-- 三支柱 -->
      <section class="news-pillars">
        <div v-for="pillar in T.pillars" :key="pillar.t" class="news-pillar">
          <img
            class="news-pillar__icon"
            :src="pillar.icon"
            alt=""
            width="40"
            height="40"
            loading="lazy"
          />
          <p class="news-pillar__t">{{ pillar.t }}</p>
        </div>
      </section>

      <!-- 国家 -->
      <section class="news-countries">
        <h2 class="news-section__title">{{ T.countriesTitle }}</h2>
        <div class="news-countries__grid">
          <div v-for="country in T.countries" :key="country.t" class="news-country">
            <img
              class="news-country__flag"
              :src="country.flag"
              alt=""
              width="48"
              height="48"
              loading="lazy"
            />
            <p class="news-country__t">{{ country.t }}</p>
          </div>
        </div>
      </section>

      <!-- 新闻精选 -->
      <section class="news-highlights">
        <div class="news-highlights__head">
          <h2 class="news-section__title">{{ T.highlightsTitle }}</h2>
          <a class="news-highlights__all" href="#" @click.prevent>{{ T.viewAll }}</a>
        </div>
        <article v-for="article in T.articles" :key="article.title" class="news-article">
          <p class="news-article__date">{{ article.date }}</p>
          <h3 class="news-article__title">{{ article.title }}</h3>
          <a class="news-article__more" href="#" @click.prevent>{{ T.readMore }}</a>
        </article>
      </section>

      <!-- Linkedin + 其他资源 -->
      <section class="news-resources">
        <div class="news-resources__card">
          <h2 class="news-section__title">{{ T.linkedinTitle }}</h2>
          <a
            class="news-resources__link"
            href="https://www.joyfumi.com"
            target="_blank"
            rel="noopener"
          >
            {{ T.linkedinText }}
          </a>
        </div>
        <div class="news-resources__card">
          <h2 class="news-section__title">{{ T.resourcesTitle }}</h2>
          <div v-for="resource in T.resources" :key="resource.t" class="news-resources__item">
            <p class="news-resources__item-t">{{ resource.t }}</p>
            <p class="news-resources__item-d">{{ resource.d }}</p>
          </div>
        </div>
      </section>
    </div>

    <!-- Newsroom 页脚（真站独立小页脚） -->
    <footer class="news-footer">
      <p class="news-footer__slogan"><strong>Joybuy</strong> · Don't just buy, Joybuy</p>
      <ul class="news-footer__nav">
        <li v-for="item in T.newsFooter.nav" :key="item">
          <a href="#" @click.prevent>{{ item }}</a>
        </li>
      </ul>
      <div class="news-footer__join">
        <span>{{ T.newsFooter.join }}</span>
        <button class="news-footer__submit" type="button">{{ T.newsFooter.submit }}</button>
      </div>
      <p class="news-footer__copy">{{ T.copyright }}</p>
    </footer>
  </div>
</template>

<style scoped>
.news-page {
  background: var(--colour-surface);
  padding-bottom: 0;
}

.news-nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-5);
  max-width: var(--container-max);
  margin-inline: auto;
  padding: var(--space-4) var(--container-pad);
  border-bottom: 1px solid var(--colour-border);
}

.news-nav__logo {
  display: block;
  height: 28px;
  width: auto;
}

.news-nav__links {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.news-nav__links a {
  color: #1a1a1a;
  text-decoration: none;
  font-size: var(--font-size-sm);
}

.news-nav__links a:hover {
  color: var(--colour-accent);
}

.news-nav__langs {
  display: flex;
  gap: var(--space-2);
  margin-left: auto;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.news-page__inner {
  max-width: var(--container-max);
  margin-inline: auto;
  padding: var(--space-6) var(--container-pad) var(--space-8);
}

/* hero */
.news-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-6);
}

.news-hero__title {
  margin: 0;
  max-width: 560px;
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  line-height: 1.2;
}

.news-hero__img {
  display: block;
  height: auto;
  max-width: 480px;
  border-radius: var(--radius-md);
}

/* 三支柱 */
.news-pillars {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-5);
  margin-top: var(--space-7);
}

.news-pillar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: #f5f6fa;
}

.news-pillar__icon {
  display: block;
  width: 40px;
  height: 40px;
}

.news-pillar__t {
  margin: 0;
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
}

.news-section__title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}

/* 国家 */
.news-countries {
  margin-top: var(--space-8);
}

.news-countries__grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.news-country {
  padding: var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  text-align: center;
}

.news-country__flag {
  display: block;
  width: 48px;
  height: 48px;
  margin: 0 auto var(--space-2);
}

.news-country__t {
  margin: 0;
  font-size: var(--font-size-sm);
}

/* 新闻精选 */
.news-highlights {
  margin-top: var(--space-8);
}

.news-highlights__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.news-highlights__all {
  color: var(--colour-accent);
  text-decoration: underline;
  font-size: var(--font-size-sm);
}

.news-article {
  padding: var(--space-5) 0;
  border-bottom: 1px solid var(--colour-border);
}

.news-article__date {
  margin: 0 0 var(--space-1);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.news-article__title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  line-height: 1.4;
}

.news-article__more {
  color: var(--colour-accent);
  font-size: var(--font-size-sm);
  text-decoration: underline;
}

/* 资源区 */
.news-resources {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-5);
  margin-top: var(--space-8);
}

.news-resources__card {
  padding: var(--space-5);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: #f5f6fa;
}

.news-resources__link {
  display: inline-block;
  margin-top: var(--space-3);
  color: var(--colour-accent);
  text-decoration: underline;
  font-size: var(--font-size-sm);
}

.news-resources__item {
  margin-top: var(--space-3);
}

.news-resources__item-t {
  margin: 0;
  font-weight: var(--font-weight-semibold);
}

.news-resources__item-d {
  margin: 0;
  color: #505259;
  font-size: var(--font-size-sm);
}

/* newsroom 页脚 */
.news-footer {
  padding: var(--space-6) var(--container-pad);
  border-top: 1px solid var(--colour-border);
  background: #f5f6fa;
  text-align: center;
}

.news-footer__slogan {
  margin: 0 0 var(--space-3);
  font-weight: var(--font-weight-bold);
}

.news-footer__slogan strong {
  color: #e1251b;
}

.news-footer__nav {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-4);
  margin: 0 0 var(--space-3);
  padding: 0;
  list-style: none;
}

.news-footer__nav a {
  color: #1a1a1a;
  text-decoration: none;
  font-size: var(--font-size-sm);
}

.news-footer__join {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  font-size: var(--font-size-sm);
}

.news-footer__submit {
  min-height: 36px;
  padding: var(--space-1) var(--space-4);
  border: 0;
  border-radius: var(--radius-sm);
  background: #1a1a1a;
  color: var(--colour-surface);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.news-footer__copy {
  margin: 0;
  color: #6e7078;
  font-size: var(--font-size-xs);
}

@media (max-width: 48rem) {
  .news-pillars,
  .news-countries__grid,
  .news-resources {
    grid-template-columns: 1fr;
  }

  .news-hero__img {
    max-width: 100%;
  }
}
</style>
