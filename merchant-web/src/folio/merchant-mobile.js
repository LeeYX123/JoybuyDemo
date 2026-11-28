/* eslint-disable no-undef */
// 经典脚本：current/render/go/orders 等全局绑定由 base-1..4.js 在同一词法环境声明。
(() => {
  // 接入手术：mobile-v2 / concept=folio / design=studio 三个 URL 参数已在
  // mobile.html + boot.js 烘焙（window.__JOYPLAY_MOBILE__ / __JOYPLAY_CONCEPT__），
  // 不再依赖 URL 传参；#platform-admin 保留原守卫。
  if (!window.__JOYPLAY_MOBILE__ || location.hash === '#platform-admin') return;

  // 接入手术：三个样式表已在 mobile.html 以 id 静态引入（base 与 concepts 预置
  // disabled），这里按原「js 换 CSS」机制切换 base → joyplay-mobile，并启用 folio。
  const folioBaseCss = document.getElementById('folioBaseCss');
  const folioMobileCss = document.getElementById('folioMobileCss');
  if (folioBaseCss) folioBaseCss.disabled = true;
  if (folioMobileCss) folioMobileCss.disabled = false;
  const root = document.documentElement;
  const mode = root.dataset.design;
  root.dataset.merchant = mode;
  const concept = window.__JOYPLAY_CONCEPT__ === 'folio' ? 'folio' : '';
  if (concept) {
    root.dataset.concept = concept;
    const stylesheet = document.getElementById('folioConceptsCss');
    if (stylesheet) stylesheet.disabled = false;
    conversations = conversations.filter(item => !item.demoPresale);
  }
  const app = document.getElementById('app');
  const overlay = document.getElementById('overlay');
  const header = document.querySelector('body > header');
  const readout = document.createElement('div');
  readout.setAttribute('aria-live', 'polite');
  readout.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)';
  document.body.append(readout);
  const mark = document.querySelector('.shell-mark');
  mark.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M10 5v9.5a3.5 3.5 0 0 1-7 0M14 19V5h3.5a3.5 3.5 0 1 1 0 7H14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  mark.setAttribute('aria-hidden', 'true');
  document.querySelector('.shell-brand b').textContent = 'joyplay';
  document.querySelector('.shell-brand small').textContent = '商家端';
  document.title = 'joyplay · 商家端';
  for (const key of ['orders', 'exposure', 'categories']) periods[key] = 'week';
  header.querySelector('[data-sheet="more"]')?.remove();
  header.querySelector('.shell-tools [data-route="10"]')?.remove();
  if (concept) {
    header.querySelector('.design-button')?.remove();
    previewStorefrontTools();
  }
  const homeButton = document.createElement('button');
  homeButton.type = 'button';
  homeButton.className = 'merchant-home-button';
  homeButton.setAttribute('aria-label', '返回');
  homeButton.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m15 5-7 7 7 7"/></svg>';
  header.prepend(homeButton);
  const shopIdentity = document.createElement('div');
  shopIdentity.className = 'merchant-shop-identity';
  shopIdentity.innerHTML = '<span class="identity-name"></span><button type="button" class="identity-id" aria-label="复制店铺 ID"></button><button type="button" class="identity-edit">编辑</button>';
  const [shopName, shopId, shopEdit] = shopIdentity.children;
  const avatarSlot = concept ? document.createElement('span') : null;
  if (avatarSlot) {
    avatarSlot.className = 'identity-avatar-slot';
    const identityText = document.createElement('div');
    identityText.className = 'identity-text';
    identityText.append(shopName, shopId);
    shopIdentity.prepend(avatarSlot, identityText);
  }
  shopEdit.setAttribute('aria-label', '编辑店铺资料');
  shopEdit.addEventListener('click', () => editShopProfile());
  shopId.addEventListener('click', () => copyShopId());
  if (!concept) header.querySelector('.shell-brand').after(shopIdentity);
  const baseRender = render;
  const baseGo = go;
  const baseToast = toast;
  const baseSupport = support;
  let conversationOpen = false;
  let directSupport = false;
  let previousRoute = current;
  const routeStack = [];

  function viewState() {
    return { route: current, scroll: window.scrollY, search, category, listingPage, shopProductPage,
      selected, activeConversation, conversationOpen, directSupport, orderFilter,
      merchantWalletType, merchantWalletPage, afterFilter, activityCategory, noticeType };
  }

  function restoreView(view) {
    const { route, scroll } = view;
    ({ selected, activeConversation, conversationOpen, directSupport, orderFilter,
      merchantWalletType, merchantWalletPage, afterFilter, activityCategory, noticeType } = view);
    if (concept && route === 9 && activeConversation !== -1 && !conversations[activeConversation]) {
      activeConversation = -1;
      conversationOpen = false;
    }
    if (current !== route) baseGo(route);
    ({ search, category, listingPage, shopProductPage } = view);
    render();
    window.scrollTo(0, scroll);
  }

  let browserHistory = false;
  let backPending = false;
  const reloadView = history.state?.joyplay;
  try {
    browserHistory = true;
    history.scrollRestoration = 'manual';
    if (!reloadView) history.replaceState({ joyplay: viewState(), depth: 0 }, '');
  } catch {
    browserHistory = false;
  }

  function rememberView(view) {
    if (!browserHistory) return;
    history.replaceState({ joyplay: view, depth: history.state.depth }, '');
  }

  function pushView(leaving) {
    if (browserHistory) {
      rememberView(leaving);
      history.pushState({ joyplay: viewState(), depth: history.state.depth + 1 }, '');
    } else routeStack.push(leaving);
  }

  window.addEventListener('popstate', event => {
    backPending = false;
    if (!browserHistory || !event.state?.joyplay) return;
    document.querySelector('dialog[open]')?.close();
    if (overlay.firstElementChild) closeModal();
    restoreView(event.state.joyplay);
  });

  homeButton.addEventListener('click', () => {
    if (browserHistory && history.state.depth > 0) {
      if (backPending) return;
      backPending = true;
      rememberView(viewState());
      history.back();
      return;
    }
    const previous = routeStack.pop();
    if (!previous) { baseGo(0); return; }
    restoreView(previous);
  });

  toast = function (message) {
    baseToast(message);
    readout.textContent = '';
    requestAnimationFrame(() => { readout.textContent = message; });
  };

  go = function (route) {
    if (route === current) return;
    const leaving = viewState();
    conversationOpen = false;
    directSupport = false;
    baseGo(route);
    if (current !== leaving.route) pushView(leaving);
  };

  support = function () {
    baseSupport();
    directSupport = true;
    conversationOpen = true;
    render();
    rememberView(viewState());
    homeButton.focus();
  };

  const modules = [
    [1, '店铺商品', 'jade', '<path d="M4 10h16v10H4zM3 10l2-6h14l2 6M9 20v-6h6v6"/>'],
    [2, '商品上架中心', 'blue', '<path d="m3 7 9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4m-9 4v10"/>'],
    [3, '订单管理', 'indigo', '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8m-8 4h8m-8 4h5"/>'],
    [5, '钱包管理', 'amber', '<rect x="3" y="5" width="18" height="15" rx="3"/><path d="M21 10h-7a2 2 0 0 0 0 4h7m-6-2h.01"/>'],
    [6, '保证金管理', 'blue', '<path d="m12 3 8 3v5c0 5-3 8-8 10-5-2-8-5-8-10V6zM8 12l3 3 5-6"/>'],
    [7, '售后中心', 'rose', '<path d="M9 6 4 11l5 5m-5-5h10a5 5 0 0 1 0 10h-3"/>'],
    [8, '平台活动', 'amber', '<rect x="4" y="6" width="16" height="14" rx="2"/><path d="M8 4v4m8-4v4M4 11h16"/>'],
    [9, '消息中心', 'jade', '<path d="M20 11a8 8 0 0 1-8 8H5l1.5-3A8 8 0 1 1 20 11ZM9 11h6"/>'],
    [10, '平台通知', 'indigo', '<path d="M5 17h14l-2-3v-4a5 5 0 0 0-10 0v4zm5 3h4"/>'],
    ['support', '联系平台客服', 'blue', '<path d="M4 13v-2a8 8 0 0 1 16 0v2M4 13h3v5H5a1 1 0 0 1-1-1zm16 0h-3v5h2a1 1 0 0 0 1-1zm-3 5c-1 2-2 3-5 3"/>'],
  ];

  function moduleButtons() {
    const depositAvailable = document.querySelector('#nav button[onclick="go(6)"]');
    const counts = {
      // 订单徽标用接口聚合 counts.PENDING（不是当前页条数）。
      3: Number(FolioData.counts.pending) || 0,
      9: conversations.reduce((sum, item) => sum + (item.unread || 0), 0),
      10: systemNotices.filter((_, i) => !readNotices.includes(i)).length +
        merchantProductReviews().filter((review) => !review.merchantRead).length,
    };
    return modules.filter(([route]) => route !== 6 || depositAvailable).map(([route, label, color, path]) => {
      const action = typeof route === 'number' ? `data-merchant-route="${route}"` : `data-${route}`;
      const count = counts[route];
      return `<button type="button" ${action}${count ? ` aria-label="${label}，${count} ${route === 3 ? '笔待发货' : '条未读'}"` : ''}><span class="module-icon ${color}"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${path}</svg>${count ? `<span class="module-badge" aria-hidden="true">${count > 99 ? '99+' : count}</span>` : ''}</span><span>${label}</span></button>`;
    }).join('');
  }

  function panel(title, body, action = '') {
    return `<section class="work-panel"><div class="work-heading"><h2>${title}</h2>${action}</div>${body}</section>`;
  }

  function metric(label, amount, lastIncrease = '') {
    const increase = lastIncrease
      ? `<span class="overview-follower-increase"><span class="overview-increase-label">今日最近新增</span>${esc(lastIncrease)}</span>`
      : '';
    const value = `<strong>${esc(String(amount))}</strong>`;
    return `<div class="overview-metric"><span>${label}</span>${increase ? `<div class="overview-value-row">${value}${increase}</div>` : value}</div>`;
  }

  function openOptionSheet(trigger, title, options, currentValue, onSelect) {
    const sheet = document.createElement('dialog');
    sheet.className = 'dock-sheet catalogue-sheet';
    sheet.setAttribute('aria-labelledby', 'merchant-options-title');
    sheet.innerHTML = '<div class="sheet-content"><div class="sheet-head"><h2 id="merchant-options-title"></h2><button type="button" aria-label="关闭">×</button></div><div class="catalogue-options"></div></div>';
    sheet.querySelector('h2').textContent = title;
    sheet.querySelector('.sheet-head button').onclick = () => dismiss();
    const list = sheet.querySelector('.catalogue-options');
    // 有些 Chromium 壳（含 IAB）在 dialog.close() 后不派发 close 事件，
    // 只靠 close 监听会留下不可见的 sheet 节点；这里显式移除，close 监听保留兜底。
    function dismiss() {
      if (sheet.open) sheet.close();
      if (sheet.isConnected) sheet.remove();
      if (trigger.isConnected) {
        trigger.setAttribute('aria-expanded', 'false');
        trigger.focus({ preventScroll: true });
      }
    }
    for (const option of options) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = option;
      button.setAttribute('aria-pressed', option === currentValue);
      button.autofocus = option === currentValue;
      button.onclick = () => {
        dismiss();
        onSelect(option);
      };
      list.append(button);
    }
    sheet.addEventListener('click', event => { if (event.target === sheet) dismiss(); });
    sheet.addEventListener('close', dismiss);
    trigger.setAttribute('aria-expanded', 'true');
    document.body.append(sheet);
    sheet.showModal();
  }

  function previewStorefrontTools() {
    const tools = header.querySelector('.shell-tools');
    tools.classList.add('merchant-storefront-tools');
    // 头部三件套（按用户口径）：左=返回+品牌，右=切换去商城 / 中文（多店时另带店铺切换）。
    // 原版是纯演示弹层；此处只改「行为接线」——切换去商城走真实接口，
    // 语言 sheet 只持久化偏好（静态稿没有 EN 文案，选中后界面仍为中文）。
    const LANGUAGE_KEY = 'joybuy.merchant.language';
    const SHOPS_LABEL = { '简体中文': '中文', English: 'EN' };
    let selectedLanguage = '简体中文';
    try {
      const saved = window.localStorage.getItem(LANGUAGE_KEY);
      if (saved === '简体中文' || saved === 'English') selectedLanguage = saved;
    } catch { /* ignore */ }

    const storefront = document.createElement('button');
    storefront.type = 'button';
    storefront.className = 'storefront-entry';
    storefront.textContent = '切换去商城';
    storefront.setAttribute('aria-label', '切换去商城');
    storefront.addEventListener('click', async () => {
      if (storefront.disabled) return;
      const actions = window.__JOYPLAY_ACTIONS__;
      if (!actions || !actions.switchToMall) { toast('商城地址未配置'); return; }
      storefront.disabled = true;
      storefront.setAttribute('aria-busy', 'true');
      try {
        await actions.switchToMall();
      } catch (error) {
        toast((error && error.message) || '切换失败，请稍后重试');
      } finally {
        storefront.disabled = false;
        storefront.removeAttribute('aria-busy');
      }
    });

    const language = document.createElement('button');
    language.type = 'button';
    language.className = 'language-entry';
    language.setAttribute('aria-haspopup', 'dialog');
    language.setAttribute('aria-expanded', 'false');
    language.innerHTML = '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2 2.3 3 5.1 3 8.5s-1 6.2-3 8.5c-2-2.3-3-5.1-3-8.5s1-6.2 3-8.5Z"/></svg><span></span>';
    function syncLanguage() {
      language.querySelector('span').textContent = SHOPS_LABEL[selectedLanguage] || '中文';
      language.setAttribute('aria-label', `选择语言，当前为${selectedLanguage}`);
    }
    language.addEventListener('click', () => {
      openOptionSheet(language, '选择语言', ['简体中文', 'English'], selectedLanguage, option => {
        selectedLanguage = option;
        try { window.localStorage.setItem(LANGUAGE_KEY, option); } catch { /* ignore */ }
        // 真正切换界面语言（i18n.js 由 boot.js 注入并挂在 window 上）。
        const i18n = window.__MERCHANT_I18N__;
        if (i18n && typeof i18n.setLang === 'function') i18n.setLang(option);
        syncLanguage();
        toast(option === 'English' ? '已切换为 English' : '已切换为简体中文');
        // 商品名等数据由后端按 locale 返回：切语言后重拉数据并重渲染。
        const actions = window.__JOYPLAY_ACTIONS__;
        if (actions && typeof actions.reloadData === 'function') {
          Promise.resolve(actions.reloadData()).catch(() => { /* 由页面兜底 */ });
        }
      });
    });
    syncLanguage();
    tools.append(storefront, language);

    const shops = window.__JOYPLAY_SHOPS__ || [];
    if (shops.length > 1) {
      const select = document.createElement('select');
      select.className = 'shop-switch';
      select.setAttribute('aria-label', '切换店铺');
      for (const shop of shops) {
        const option = document.createElement('option');
        option.value = shop.id;
        option.textContent = shop.name;
        select.append(option);
      }
      select.value = window.__JOYPLAY_SHOP_ID__ || (shops[0] && shops[0].id) || '';
      select.addEventListener('change', () => {
        const actions = window.__JOYPLAY_ACTIONS__;
        if (actions && actions.switchShop) actions.switchShop(select.value);
      });
      tools.append(select);
    }
  }

  function homePage() {
    const stats = app.querySelector('.six-stats');
    if (!stats) return;
    for (const control of app.querySelectorAll('.twocharts .seg, .lower-grid .seg')) {
      const week = document.createElement('span');
      week.className = 'weekly-range';
      week.textContent = '近一周';
      control.replaceWith(week);
    }
    const number = (index) => {
      const value = stats.children[index]?.querySelector('strong');
      return value?.querySelector('.follower-total')?.firstChild?.textContent.trim() || value?.textContent.trim() || '—';
    };
    const shopStatus = [...stats.children].find(card => card.querySelector('label')?.textContent.trim() === '店铺状态');
    const shopState = shopStatus?.querySelector('strong')?.textContent.trim().replace(/^●\s*/, '');
    const tools = panel('业务模块', `<nav class="merchant-module-grid" aria-label="业务模块">${moduleButtons()}</nav>`);
    const displayState = shopState || (sealed ? '已封店' : '接单中');
    const metrics = `<section class="work-panel business-overview"><div class="work-heading"><h1>经营面板</h1></div><div class="work-grid">
      <div class="overview-metric shop-status" data-active="${displayState === '接单中'}"><span>店铺状态</span><strong>${esc(displayState)}</strong></div>
      ${metric('今日订单', number(0))}
      ${metric('今日曝光', number(2))}
      ${metric('总关注', number(3), concept ? stats.children[3]?.querySelector('.follower-delta')?.textContent.trim() : '')}
      </div></section>`;
    const home = document.createElement('div');
    home.className = 'merchant-home';
    home.innerHTML = metrics + tools;
    app.querySelector('.dash-intro')?.replaceWith(home);
    app.querySelector('.lower-grid [onclick="go(10)"]')?.closest('section')?.remove();
    const details = document.createElement('details');
    details.className = 'work-panel merchant-metrics';
    details.innerHTML = '<summary>完整经营面板</summary>';
    shopStatus?.remove();
    home.firstElementChild.after(details);
    details.append(stats);
  }

  function improveProducts() {
    const heading = app.querySelector('.heading');
    const toolbar = app.querySelector('.toolbar');
    const query = toolbar?.querySelector('#query');
    if (!heading || !query) return;
    heading.querySelector('h1').textContent = current === 1 ? '店铺商品' : '商品上架中心';
    heading.querySelector('p')?.remove();
    heading.querySelector('[onclick="go(2)"]')?.remove();
    const source = toolbar.closest('section');
    const options = [...source.querySelectorAll('select option, .category-selector button')].map(option => option.textContent.trim());
    const filter = document.createElement('form');
    filter.className = 'catalogue-controls';
    filter.setAttribute('role', 'search');
    query.type = 'search';
    query.placeholder = '搜索商品';
    query.enterKeyHint = 'search';
    query.setAttribute('aria-label', '搜索商品');
    filter.append(query);
    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.textContent = '搜索';
    const categories = document.createElement('button');
    categories.type = 'button';
    categories.textContent = category === '全部品类' ? '分类' : category;
    categories.setAttribute('aria-haspopup', 'dialog');
    categories.setAttribute('aria-expanded', 'false');
    categories.setAttribute('aria-label', '商品分类，当前为' + category);
    filter.append(submit, categories);
    if (search) {
      const clear = document.createElement('button');
      clear.type = 'button';
      clear.setAttribute('aria-label', '清除搜索');
      clear.textContent = '×';
      query.after(clear);
      clear.addEventListener('click', () => applyFilters('', category));
    }
    function applyFilters(term, type) {
      search = term.trim();
      category = type;
      listingPage = shopProductPage = 1;
      // 上架中心与店铺商品都改为服务端分页/筛选：关键词+品类下推接口，回第 1 页。
      const actions = window.__JOYPLAY_ACTIONS__;
      const load = current === 2 ? actions?.searchCatalog : current === 1 ? actions?.searchListings : null;
      if (load) {
        load({ q: search, category })
          .then(() => render())
          .catch((error) => {
            toast((error && error.message) || '商品查询失败，请稍后重试');
            render();
          });
        return;
      }
      render();
    }
    filter.addEventListener('submit', event => {
      event.preventDefault();
      applyFilters(query.value, category);
    });
    categories.addEventListener('click', () => openOptionSheet(categories, '商品分类', options, category, option => {
      if (option !== category || query.value.trim() !== search) {
        applyFilters(query.value, option);
        app.querySelector('.catalogue-controls [aria-haspopup]')?.focus({ preventScroll: true });
      }
    }));
    source.replaceWith(filter);
    app.querySelector('.shop-profile-bar')?.remove();
    for (const details of app.querySelectorAll('.product .actions [onclick^="productDetail("]')) details.remove();
    const tips = app.querySelector('.banner');
    if (current === 2 && tips) tips.remove();
  }

  function improveOrders() {
    const list = app.querySelector('.tablewrap');
    // 恢复桌面版的订单搜索 + 下单日期区间（静态稿原码表单，真实订单数据本地筛选）。
    app.querySelector('.toolbar')?.classList.add('order-filters');
    if (!list) return;
    const rows = list.querySelectorAll('tbody tr');
    if (rows.length === 0 && !app.textContent.includes('暂无')) {
      list.insertAdjacentHTML('afterend', '<p class="empty-state" role="status">暂无符合条件的订单，请尝试调整筛选条件。</p>');
    }
    if (!rows.length) return;
    const cards = document.createElement('div');
    cards.className = 'merchant-order-list';
    cards.setAttribute('role', 'list');
    const byId = new Map(orders.map((order) => [order[0], order]));
    for (const row of rows) {
      const [id, , , date, , , , actions] = row.cells;
      const order = byId.get(id.textContent.trim());
      const item = products[order[1]];
      const card = document.createElement('article');
      card.className = 'merchant-order';
      card.setAttribute('role', 'listitem');
      card.innerHTML = `<div class="order-top"><span>${esc(order[0])}</span>${tag(status(order))}</div>
        <div class="order-item"><div class="order-art">${art(item[4])}</div><div><h2>${esc(item[0])}</h2><p>${esc(item[1])} · 数量 × ${qty(order)}</p><small>${esc(date.textContent.trim())}</small></div></div>
        <dl class="order-costs"><div><dt>订单金额</dt><dd>${money(totalPrice(order))}</dd></div><div><dt>发货成本</dt><dd>${money(totalCost(order))}</dd></div><div><dt>${orderIsConfirmed(order) ? '盈利' : '预估盈利'}</dt><dd>${money(totalPrice(order) - totalCost(order))}</dd></div></dl>`;
      const footer = document.createElement('div');
      footer.className = 'order-footer';
      while (actions.firstChild) footer.append(actions.firstChild);
      card.append(footer);
      cards.append(card);
    }
    list.replaceWith(cards);
  }

  function improveOrderDetail() {
    const order = orders[selected];
    const summary = app.querySelector('.od-summary');
    const info = app.querySelector('.od-information');
    let progress = app.querySelector('.od-timeline')?.closest('section');
    if (!summary || !info) return;
    const showFulfilment = concept && !orderIsConfirmed(order);
    if (showFulfilment && !progress) {
      const template = document.createElement('template');
      template.innerHTML = merchantProgressTimeline(order);
      progress = template.content.firstElementChild;
    }
    if (!concept) {
      const statusLine = document.createElement('div');
      statusLine.className = 'detail-status';
      statusLine.innerHTML = `<span>当前订单状态</span><strong>${esc(status(order))}</strong>`;
      summary.prepend(statusLine);
      summary.querySelector('.od-summary-heading .tag')?.remove();
    }
    if (progress && concept && !showFulfilment) {
      progress.remove();
      progress = null;
    }
    if (progress && showFulfilment) {
      const currentNode = progress.querySelector('.od-node.is-current') || progress.querySelector('.od-node');
      currentNode.classList.add('is-current');
      currentNode.setAttribute('aria-current', 'step');
      const currentStep = currentNode.querySelector('.od-node-heading b').textContent.trim();
      if (!currentNode.querySelector('.od-node-heading > span')) {
        const label = document.createElement('span');
        label.textContent = '当前';
        currentNode.querySelector('.od-node-heading').append(label);
      }
      const disclosure = document.createElement('details');
      disclosure.className = 'concept-order-progress';
      disclosure.dataset.orderId = order[0];
      const toggle = document.createElement('summary');
      toggle.innerHTML = `<span><span class="progress-label">订单履约进度</span><strong>${esc(currentStep)}</strong></span><span class="progress-toggle"><span class="progress-show">查看全部进度</span><span class="progress-hide">收起进度</span></span>`;
      progress.querySelector('.od-card-title h2').textContent = '全部进度';
      disclosure.append(toggle, progress);
      summary.before(disclosure);
    }
    if (progress && app.querySelector('.od-right')?.contains(info)) {
      const layout = app.querySelector('.od-layout');
      layout.prepend(info);
      if (!concept) layout.append(progress);
    }
    const shipButton = summary.querySelector('[onclick="confirmShip()"]');
    if (shipButton) {
      const actions = document.createElement('div');
      actions.className = 'merchant-detail-actions';
      actions.append(shipButton);
      app.append(actions);
    }
  }

  function improveWallet() {
    const overview = app.querySelector('.wallet-overview');
    const select = app.querySelector('#merchantWalletFilter');
    if (!overview || !select) return;
    const [balanceBlock, oldActions] = overview.children;
    const [moneyActions, securityActions] = oldActions.children;
    overview.removeAttribute('style');
    balanceBlock.className = 'wallet-balance';
    for (const child of balanceBlock.children) child.removeAttribute('style');
    moneyActions.className = 'wallet-primary-actions';
    moneyActions.querySelector('[onclick="support()"]').textContent = '充值';
    moneyActions.querySelector('[onclick="withdrawModal()"]').textContent = '提现';
    overview.append(moneyActions);
    const security = document.createElement('section');
    security.className = 'card wallet-security-row';
    security.innerHTML = '<h2>钱包安全</h2>';
    securityActions.removeAttribute('style');
    security.append(securityActions);
    overview.after(security);
    oldActions.remove();

    const section = select.closest('section');
    section.classList.add('wallet-activity');
    const options = [...select.options].map(option => option.value);
    const filter = document.createElement('button');
    filter.type = 'button';
    filter.className = 'wallet-filter';
    filter.textContent = select.value;
    filter.setAttribute('aria-haspopup', 'dialog');
    filter.setAttribute('aria-label', '资金类型，当前为' + select.value);
    filter.setAttribute('aria-expanded', 'false');
    filter.addEventListener('click', () => openOptionSheet(filter, '资金类型', options, select.value, option => {
      if (option === select.value) return;
      select.value = option;
      select.onchange();
      app.querySelector('.wallet-filter')?.focus({ preventScroll: true });
    }));
    section.querySelector('.cardhead').append(filter);
    select.closest('.toolbar').remove();

    const table = section.querySelector('.tablewrap');
    const list = document.createElement('ul');
    list.className = 'wallet-records';
    for (const row of table.querySelectorAll('tbody tr')) {
      const [time, kind, , , amount, state, action] = row.cells;
      const button = action.querySelector('button');
      const item = document.createElement('li');
      const outgoing = ['提现申请', '订单发货'].includes(kind.textContent.trim()) || /[-−]/.test(amount.textContent);
      const absolute = amount.textContent.trim().replace(/[-−]/g, '');
      const status = state.textContent.trim();
      button.className = 'wallet-record';
      button.innerHTML = `<span class="wallet-record-direction" aria-hidden="true">${outgoing ? '↑' : '↓'}</span><span class="wallet-record-main"><strong>${esc(kind.textContent.trim())}</strong><small>${esc(time.textContent.trim())}</small></span><span class="wallet-record-value"><strong>${outgoing ? '−' : '+'}${esc(absolute)}</strong><small>${esc(status)}</small></span><span class="wallet-disclosure" aria-hidden="true">›</span>`;
      item.append(button);
      list.append(item);
    }
    if (list.children.length) table.replaceWith(list);
    else table.remove();

    const pagination = section.querySelector('.pagination');
    const buttons = [...pagination.querySelectorAll('button')];
    // 服务端总分页数（pageWindow 只渲染窗口内的页码，不能用按钮个数反推）。
    const pageCount = Number(window.walletPages) || 1;
    if (pageCount <= 1) {
      pagination.remove();
    } else {
      const indicator = document.createElement('span');
      indicator.textContent = `第 ${merchantWalletPage} / ${pageCount} 页`;
      pagination.classList.add('wallet-pagination');
      pagination.replaceChildren(buttons[0], indicator, buttons.at(-1));
    }
  }

  function improveAfterSales() {
    const table = app.querySelector('.tablewrap');
    if (!table) return;
    table.closest('section').classList.add('mobile-service');
    const list = document.createElement('div');
    list.className = 'service-cases';
    for (const row of table.querySelectorAll('tbody tr')) {
      const [id, order, issue, state, progress, controls] = row.cells;
      const card = document.createElement('article');
      card.className = 'service-case';
      const title = issue.querySelector('.small')?.textContent.trim() || issue.textContent.trim();
      const type = issue.querySelector('div')?.firstChild?.textContent.trim() || '';
      card.innerHTML = `<div class="case-heading"><span>${esc(type)}</span><span class="case-status"></span></div><h2>${esc(title)}</h2><p class="case-progress">${esc(progress.textContent.trim())}</p><dl><div><dt>售后单号</dt><dd>${esc(id.textContent.trim())}</dd></div><div><dt>关联订单</dt><dd>${esc(order.textContent.trim())}</dd></div></dl><div class="case-actions"></div>`;
      card.querySelector('.case-status').append(state.querySelector('.tag') || state.textContent.trim());
      card.querySelector('.case-actions').append(...controls.querySelectorAll('button'));
      list.append(card);
    }
    if (!list.children.length) list.innerHTML = '<p class="empty-state">暂无该类型的售后记录</p>';
    table.replaceWith(list);
    const rule = app.querySelector('.banner');
    if (rule) {
      const disclosure = document.createElement('details');
      disclosure.className = 'mobile-disclosure';
      disclosure.innerHTML = '<summary>售后处理规则</summary>';
      disclosure.append(rule);
      list.after(disclosure);
    }
  }

  function improveDeposit() {
    const stats = app.querySelector('.stats');
    const demo = app.querySelector('.heading .seg');
    if (demo) {
      const disclosure = document.createElement('details');
      disclosure.className = 'mobile-disclosure';
      disclosure.innerHTML = '<summary>预览保证金状态</summary>';
      disclosure.append(demo);
      app.querySelector('.bottomnote')?.before(disclosure);
    }
    if (!stats) return;
    const summary = document.createElement('section');
    summary.className = 'deposit-summary';
    const cards = [...stats.querySelectorAll('.stat')];
    const balanceCard = cards.find(card => card.querySelector('label')?.textContent === '保证金余额');
    summary.append(balanceCard, ...cards.filter(card => card !== balanceCard));
    stats.replaceWith(summary);
    const contact = app.querySelector('#app [onclick="support()"]');
    if (contact) {
      contact.classList.add('primary', 'deposit-contact');
      summary.append(contact);
    }
    const table = app.querySelector('.tablewrap');
    if (!table) return;
    table.closest('section').classList.add('deposit-history');
    const history = document.createElement('ul');
    history.className = 'deposit-ledger';
    const headers = [...table.querySelectorAll('th')].map(cell => cell.textContent.trim());
    for (const row of [...table.querySelectorAll('tbody tr')].reverse()) {
      const values = Object.fromEntries([...row.cells].map((cell, index) => [headers[index], cell.textContent.trim()]));
      const item = document.createElement('li');
      const amount = values['金额'] || values['变动金额'];
      item.innerHTML = `<div><strong>${esc(values['类型'] || values['明细类型'] || '')}</strong><small>${esc(values['时间'] || values['记录时间'] || '')}</small></div><b>${esc(amount || '')}</b><p>${esc(values['单号'] || values['关联单号'] || '—')}${values['余额'] ? ' · 余额 ' + esc(values['余额']) : ''}${values['说明'] ? ' · ' + esc(values['说明']) : ''}</p>`;
      history.append(item);
    }
    if (!history.children.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = '暂无保证金明细';
      table.replaceWith(empty);
    } else table.replaceWith(history);
  }

  function improveActivities() {
    app.querySelector('.activity-hero')?.remove();
    const activities = [...app.querySelectorAll('article.activity')];
    for (const card of activities) {
      card.querySelector('.activityart')?.remove();
      const body = card.querySelector('.content');
      const actions = document.createElement('div');
      actions.className = 'activity-actions';
      actions.append(...card.querySelectorAll('button'));
      card.append(actions);
      body.querySelector('h2')?.removeAttribute('style');
    }
    [...app.querySelectorAll('section.card')].find(section => section.querySelector('h2')?.textContent.includes('参与记录'))?.remove();
    for (const note of app.querySelectorAll('.activity .content p.green')) {
      note.textContent = '已记录参与意向';
    }
    if (!activities.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = '暂无该类型的活动';
      app.querySelector('.tabs')?.after(empty);
    }
  }

  function improveChat() {
    const shell = app.querySelector('.chat-shell');
    if (!shell) return;
    shell.dataset.view = conversationOpen ? 'thread' : 'list';
    for (const item of shell.querySelectorAll('.conversation[onclick]')) {
      item.tabIndex = 0;
      item.setAttribute('role', 'button');
    }
    if (!concept || !conversationOpen) return;
    const title = shell.querySelector('.chat-title b');
    const heading = app.querySelector('.heading h1');
    if (title && heading) {
      const oldHeading = heading.closest('.heading');
      heading.textContent = title.textContent;
      title.replaceWith(heading);
      oldHeading.remove();
    }
    const product = shell.querySelector('.chat-product-context');
    if (activeConversation !== -1) {
      // 需求 1：右上角「关联订单」已从 base-3 删除，这里不再处理 chat-title。
      // 需求 3：商品上下文条来自会话的 context_product（买家当前商品）；没有就整条不显示。
      const conv = conversations[activeConversation];
      if (!conv?.contextProduct) {
        product?.remove();
      } else {
        product?.querySelector('div:nth-child(2) > span.small')?.remove();
      }
    }

    const composer = shell.querySelector('.chat-composer');
    const input = composer.querySelector('#chatInput');
    const send = composer.querySelector('button[onclick="sendChat()"]');
    // 需求 2：「添加图片」按钮 + 隐藏 file input 都在 controls 里，整体移到 composer
    // 末尾（不能像以前那样 remove()，否则手机端没有发图入口）。
    const controls = send.parentElement;
    input.rows = 1;
    input.placeholder = '输入消息';
    input.setAttribute('aria-label', '输入消息');
    send.textContent = '发送';
    composer.append(controls);
  }

  function improveNotices() {
    const notices = [...app.querySelectorAll('.system-notice')];
    for (const notice of notices) {
      const [content, action] = notice.children;
      if (!content || !action?.matches('button')) continue;
      action.className = 'merchant-notice-row';
      action.dataset.read = notice.classList.contains('isread');
      const trailing = document.createElement('span');
      trailing.className = 'notice-chevron';
      trailing.setAttribute('aria-hidden', 'true');
      trailing.textContent = '›';
      const summary = document.createElement('span');
      summary.className = 'notice-summary';
      for (const part of [...content.children]) {
        const text = document.createElement('span');
        text.className = part.className || 'notice-' + part.tagName.toLowerCase();
        text.append(...part.childNodes);
        summary.append(text);
      }
      if (action.dataset.read === 'false') action.setAttribute('aria-label', '未读通知：' + summary.textContent.trim());
      action.replaceChildren(summary, trailing);
      notice.replaceWith(action);
    }
  }

  function labelFields(container) {
    for (const field of container.querySelectorAll('input, select, textarea')) {
      if (field.type === 'hidden' || field.labels?.length || field.hasAttribute('aria-label')) continue;
      const label = field.previousElementSibling;
      const text = (label?.matches('label') ? label.textContent.trim() : '') || field.getAttribute('placeholder');
      if (text) field.setAttribute('aria-label', text);
    }
  }

  function tunePage() {
    homeButton.hidden = current === 0;
    shopIdentity.hidden = current !== 0;
    if (current === 0) {
      shopName.textContent = shopProfile.name;
      shopId.textContent = `ID ${immutableShopId}`;
      if (avatarSlot) avatarSlot.innerHTML = profileAvatar('identity-avatar');
    }
    app.classList.toggle('merchant-orders', current === 3);
    app.classList.toggle('merchant-chat', current === 9);
    app.classList.toggle('merchant-catalogue', current === 2);
    if (current === 0) homePage();
    if (current === 1 || current === 2) improveProducts();
    if (current === 3) improveOrders();
    if (current === 4) {
      improveOrderDetail();
      app.querySelector('.heading [onclick="go(3)"]')?.remove();
    }
    if (current === 5) improveWallet();
    if (current === 6) improveDeposit();
    if (current === 7) improveAfterSales();
    if (current === 8) improveActivities();
    if (current === 9) improveChat();
    if (current === 10) improveNotices();
    if (concept) {
      app.dataset.conceptPage = current;
      if (current === 0) enhanceConceptHome();
      if (current === 3 && concept === 'folio') {
        for (const card of app.querySelectorAll('.merchant-order')) {
          card.prepend(card.querySelector('.order-item'));
        }
      }
    }
    labelFields(app);
    if (previousRoute !== current) {
      const heading = app.querySelector('h1');
      if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
      previousRoute = current;
    }
  }

  function enhanceConceptHome() {
    const audit = app.querySelector('button[onclick="showFollowerAudit()"]');
    const auditActions = audit?.closest('.toolbar');
    audit?.remove();
    if (auditActions && !auditActions.children.length) auditActions.remove();
    for (const chart of app.querySelectorAll('.business-chart')) {
      chart.classList.add('chart-direct-values');
      // The base chart uses interactive bars. Clone it to drop those listeners in this static view.
      const readout = chart.nextElementSibling;
      if (readout?.classList.contains('chart-readout')) readout.remove();
      const plot = chart.querySelector('.plot');
      const columns = plot.cloneNode(true);
      columns.setAttribute('role', 'list');
      for (const col of columns.querySelectorAll('.column')) {
        const tooltip = col.querySelector('.tooltip');
        const [date, quantity] = tooltip.textContent.split(' · ');
        col.removeAttribute('tabindex');
        col.setAttribute('role', 'listitem');
        col.setAttribute('aria-label', `${date}，${quantity}`);
        tooltip.className = 'chart-value';
        tooltip.textContent = quantity.replace(/\s*[笔次]$/, '');
        tooltip.setAttribute('aria-hidden', 'true');
        col.querySelector('small')?.setAttribute('aria-hidden', 'true');
      }
      plot.replaceWith(columns);
    }
    const home = app.querySelector('.merchant-home');
    home.before(shopIdentity);
    const grid = home.querySelector('.merchant-module-grid');
    const groups = [
      ['商品与经营', [1, 2, 3, 8]],
      ['资金管理', [5, 6]],
      ['售后与沟通', [7, 9, 10, 'support']],
    ];
    for (const [title, routes] of groups) {
      const group = document.createElement('section');
      group.className = 'folio-module-group';
      const heading = document.createElement('h3');
      heading.textContent = title;
      group.append(heading);
      for (const route of routes) {
        const item = grid.querySelector(route === 'support' ? '[data-support]' : `[data-merchant-route="${route}"]`);
        if (item) group.append(item);
      }
      grid.append(group);
    }
  }

  app.addEventListener('click', (event) => {
    if (!conversationOpen && event.target.closest('.conversation[onclick]')) {
      const leaving = viewState();
      conversationOpen = true;
      queueMicrotask(() => pushView(leaving));
    }
  }, true);
  app.addEventListener('click', (event) => {
    const button = event.target.closest('[data-merchant-route], [data-support]');
    if (!button) return;
    if (button.hasAttribute('data-support')) support();
    if (button.dataset.merchantRoute) go(Number(button.dataset.merchantRoute));
  });
  app.addEventListener('keydown', (event) => {
    const item = event.target.closest('.conversation[onclick]');
    if (!item || !['Enter', ' '].includes(event.key)) return;
    event.preventDefault();
    item.click();
  });
  new MutationObserver(() => {
    labelFields(overlay);
    for (const error of overlay.querySelectorAll('[id$="Error"]:not([role])')) error.setAttribute('role', 'alert');
  }).observe(overlay, { childList: true });

  const connection = document.createElement('p');
  connection.className = 'merchant-connection';
  connection.setAttribute('role', 'status');
  connection.textContent = '当前离线，可查看本地记录';
  header.after(connection);
  function updateConnection() { connection.hidden = navigator.onLine; }
  window.addEventListener('online', updateConnection);
  window.addEventListener('offline', updateConnection);
  updateConnection();

  const viewport = window.visualViewport;
  if (viewport) {
    function updateViewport() {
      if (Math.abs(viewport.scale - 1) > 0.02) return;
      root.style.setProperty('--merchant-viewport', `${viewport.height}px`);
      const focused = document.activeElement;
      if (!focused?.matches('input:not([type=file]), textarea')) return;
      requestAnimationFrame(() => {
        if (focused !== document.activeElement) return;
        const bounds = focused.getBoundingClientRect();
        if (bounds.bottom > viewport.offsetTop + viewport.height - 12) {
          focused.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
        }
      });
    }
    viewport.addEventListener('resize', updateViewport);
    updateViewport();
  }

  render = function () {
    const openProgress = concept && app.querySelector('.concept-order-progress[open]')?.dataset.orderId;
    const openMetrics = concept && app.querySelector('.merchant-metrics[open]');
    baseRender();
    tunePage();
    if (openProgress) {
      const progress = app.querySelector('.concept-order-progress');
      if (progress?.dataset.orderId === openProgress) progress.open = true;
    }
    if (openMetrics && current === 0) {
      const metrics = app.querySelector('.merchant-metrics');
      if (metrics) metrics.open = true;
    }
    if (browserHistory && !backPending) rememberView(viewState());
  };
  if (reloadView && browserHistory) restoreView(reloadView);
  else tunePage();
})();
