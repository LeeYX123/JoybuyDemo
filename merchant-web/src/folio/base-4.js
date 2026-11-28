(() => {
  const designs = {
    orbit: ['远洋蓝 · 经营总览', '订单趋势和核心指标优先'],
    flow: ['绿洲 · 履约工作台', '待发货、售后与消息优先'],
    studio: ['暖棕 · 店铺资产', '钱包余额、店铺档案与资金入口优先'],
  };
  const symbols = {
    brand: '<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4a12 12 0 0 1 0 16 12 12 0 0 1 0-16Z"/>',
    home: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    order: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8m-8 4h8m-8 4h5"/>',
    box: '<path d="m3 7 9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4m-9 4v10M8 5l9 4"/>',
    wallet: '<rect x="3" y="5" width="18" height="15" rx="3"/><path d="M21 10h-7a2 2 0 0 0 0 4h7m-6-2h.01"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    chat: '<path d="M20 11a8 8 0 0 1-8 8H5l1.5-3A8 8 0 1 1 20 11Z"/><path d="M9 11h6"/>',
    bell: '<path d="M5 17h14l-2-3v-4a5 5 0 0 0-10 0v4zm5 3h4"/>',
    store: '<path d="M3 10l2-6h14l2 6M3 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0M5 13v7h14v-7m-9 7v-5h4v5"/>',
    shield: '<path d="M12 3l8 3v5c0 5-3 8-8 10-5-2-8-5-8-10V6z"/><path d="m8 12 3 3 5-6"/>',
    event: '<rect x="4" y="6" width="16" height="14" rx="2"/><path d="M8 4v4m8-4v4M4 11h16m-12 4h3"/>',
    support: '<path d="M4 13v-2a8 8 0 0 1 16 0v2m-16 0h3v5H5a1 1 0 0 1-1-1zm16 0h-3v5h2a1 1 0 0 0 1-1zm-3 5c-1 2-2 3-5 3"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
  };
  const routes = ['home', 'store', 'box', 'order', 'order', 'wallet', 'shield', 'support', 'event', 'chat', 'bell'];
  const icon = (name) => '<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + symbols[name] + '</svg>';
  const header = document.querySelector('body > header');
  const app = document.getElementById('app');
  const overlay = document.getElementById('overlay');
  const nav = document.createElement('nav');
  const sheet = document.createElement('dialog');
  const requestedDesign = new URLSearchParams(location.search).get('design');
  let design = Object.hasOwn(designs, requestedDesign) ? requestedDesign : 'studio';
  let activeTrigger;
  let overlayTrigger;

  header.insertAdjacentHTML('beforeend', `
    <div class="shell-brand"><span class="shell-mark">${icon('brand')}</span><div><b>寰球优选</b><small>商家工作台</small></div></div>
    <div class="shell-tools">
      <button type="button" class="design-button" data-sheet="designs">设计方案</button>
      <button type="button" data-route="10" aria-label="平台通知">${icon('bell')}</button>
      <button type="button" data-sheet="more" aria-label="店铺账户和更多功能">${icon('more')}</button>
    </div>`);
  nav.className = 'mobile-nav';
  nav.setAttribute('aria-label', '商家工作台主导航');
  nav.innerHTML = [[0, '首页'], [3, '订单'], [2, '商品'], [5, '钱包']].map(([route, label]) =>
    `<button type="button" data-route="${route}">${icon(routes[route])}<span>${label}</span></button>`
  ).join('') + `<button type="button" data-sheet="more" aria-expanded="false">${icon('more')}<span>更多</span></button>`;
  sheet.className = 'dock-sheet';
  sheet.setAttribute('aria-labelledby', 'dockTitle');
  document.body.append(nav, sheet);

  function applyDesign(next, updateUrl = false) {
    design = next;
    document.documentElement.dataset.design = design;
    const button = header.querySelector('[data-sheet=designs]');
    button.setAttribute('aria-label', '切换设计方案，当前为' + designs[design][0]);
    if (updateUrl) {
      const url = new URL(location.href);
      url.searchParams.set('design', design);
      try { history.replaceState(history.state, '', url); } catch { /* Local file policy may block URL updates. */ }
    }
  }

  function showSheet(kind, trigger) {
    const comparing = kind === 'designs';
    activeTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true');
    const actualRoutes = [...document.querySelectorAll('#nav button[onclick]')]
      .map((button) => Number(button.getAttribute('onclick').match(/go\((\d+)\)/)?.[1]));
    const options = comparing
      ? Object.entries(designs).map(([key, [title, description]]) => `
          <button type="button" data-design-choice="${key}" aria-pressed="${key === design}">${title}<small>${description}</small></button>`)
      : [1, 6, 7, 8, 9, 10].filter((route) => actualRoutes.includes(route)).map((route) =>
          `<button type="button" data-route="${route}">${icon(routes[route])}${names[route]}</button>`)
        .concat('<button type="button" data-command="profile">编辑店铺资料</button>', '<button type="button" data-command="support">联系平台客服</button>');
    sheet.innerHTML = `<div class="sheet-content"><div class="sheet-head"><h2 id="dockTitle">${comparing ? '选择设计方案' : '更多功能'}</h2><button type="button" data-dismiss aria-label="关闭">${icon('close')}</button></div><div class="sheet-options">${options.join('')}</div></div>`;
    sheet.showModal();
  }

  function goFromShell(route) {
    go(route);
    const title = app.querySelector('h1');
    if (title) {
      title.tabIndex = -1;
      title.focus({ preventScroll: true });
    }
  }

  for (const root of [header, nav, sheet]) {
    root.addEventListener('click', (event) => {
      if (event.target === sheet) sheet.close();
      const button = event.target.closest('button');
      if (!button) return;
      if (button.hasAttribute('data-dismiss')) sheet.close();
      if (button.dataset.sheet) showSheet(button.dataset.sheet, button);
      if (button.dataset.route !== undefined) {
        if (sheet.open) sheet.close();
        goFromShell(Number(button.dataset.route));
      }
      if (button.dataset.designChoice) {
        sheet.close();
        applyDesign(button.dataset.designChoice, true);
        if (current === 0) enhanceDashboard();
      }
      if (button.dataset.command) {
        sheet.close();
        if (button.dataset.command === 'profile') editShopProfile();
        else support();
      }
    });
  }
  sheet.addEventListener('close', () => {
    activeTrigger?.setAttribute('aria-expanded', 'false');
  });

  const heroArt = '<svg class="dash-art" viewBox="0 0 240 240" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1"><circle cx="120" cy="120" r="105"/><ellipse cx="120" cy="120" rx="68" ry="105"/><ellipse cx="120" cy="120" rx="33" ry="105"/><path d="M16 120h208M34 63h172M34 177h172M120 15v210"/><circle cx="176" cy="63" r="5" fill="currentColor"/><circle cx="88" cy="177" r="4" fill="currentColor"/></svg>';

  function enhanceDashboard() {
    const heading = app.querySelector('.heading');
    const strip = app.querySelector('.welcome-strip');
    const stats = app.querySelector('.six-stats');
    const charts = app.querySelector('.twocharts');
    const lower = app.querySelector('.lower-grid');
    if (!stats || !charts || !lower) return;
    const actions = [...app.children].filter((node) => node.classList.contains('toolbar'));
    app.querySelector('.dash-intro')?.remove();
    const snapshot = {
      orbit: ['今日订单数量', stats.children[0].querySelector('strong').textContent, '笔', '查看订单', 3],
      flow: ['待发货订单', stats.children[1].querySelector('strong').textContent, '笔', '查看待处理订单', 3],
      studio: ['当前钱包余额', money(balance), '用于订单发货与资金管理', '查看钱包', 5],
    }[design];
    const [label, value, caption, action, route] = snapshot;
    const quickLinks = {
      orbit: [[3, '订单管理'], [2, '商品上架'], [5, '钱包管理'], [9, '消息中心']],
      flow: [[3, '待处理订单'], [7, '售后处理'], [9, '客户消息'], [2, '商品上架']],
      studio: [[1, '店铺管理'], [5, '钱包管理'], [6, '保证金'], [8, '平台活动']],
    }[design];
    const intro = document.createElement('div');
    intro.className = 'dash-intro';
    const pending = design === 'flow' ? orders.filter(unshipped).slice(0, 2) : [];
    intro.innerHTML = `<section class="dash-hero">${heroArt}<div><h1>${{ orbit: '经营看板', flow: '履约工作台', studio: '店铺与资产' }[design]}</h1><p>${label}</p><strong>${value}</strong><p>${caption}</p></div><button type="button" data-dash-route="${route}" ${design === 'flow' ? 'data-shipping' : ''}>${action}</button></section>
      <div class="dash-launch" aria-label="快捷入口">${quickLinks.map(([id, text]) => `<button type="button" data-dash-route="${id}" ${design === 'flow' && id === 3 ? 'data-shipping' : ''}>${icon(routes[id])}<span>${text}</span></button>`).join('')}</div>
      ${design === 'flow' ? `<section class="card dispatch-queue"><h2>待履约订单</h2>${pending.map((order) => `<div><span><b>${esc(products[order[1]][0])}</b><span class="small">${esc(order[0])} · ${esc(status(order))}</span></span><button type="button" data-dash-route="4" data-order="${orders.indexOf(order)}">查看详情</button></div>`).join('') || '<p class="small">当前没有待履约订单</p>'}</section>` : ''}`;
    intro.addEventListener('click', (event) => {
      const button = event.target.closest('[data-dash-route]');
      if (!button) return;
      // 2026-11-28 三态口径：待发货（含未发货 / 待出库），与 base-2/3 的 orderGroup 一致。
      if (button.hasAttribute('data-shipping')) orderFilter = '待发货';
      if (button.dataset.order !== undefined) selected = Number(button.dataset.order);
      goFromShell(Number(button.dataset.dashRoute));
    });
    heading?.remove();
    const note = app.querySelector('.bottomnote');
    const sections = design === 'flow' ? [intro, strip, stats, charts, lower]
      : design === 'studio' ? [intro, stats, strip, lower, charts]
      : [intro, strip, stats, charts, lower];
    for (const section of [...sections, ...actions].filter(Boolean)) app.insertBefore(section, note);
  }

  function enhanceTables(root) {
    for (const table of root.querySelectorAll('.tablewrap table')) {
      table.setAttribute('role', 'table');
      const headers = [...table.querySelectorAll('th')].map((cell) => cell.textContent.trim());
      for (const row of table.rows) {
        row.setAttribute('role', 'row');
        for (const [index, cell] of [...row.cells].entries()) {
          cell.setAttribute('role', cell.tagName === 'TH' ? 'columnheader' : 'cell');
          if (cell.tagName !== 'TD' || !headers[index] || cell.colSpan !== 1 || cell.hasAttribute('data-label')) continue;
          cell.dataset.label = headers[index];
          const content = document.createElement('div');
          while (cell.firstChild) content.append(cell.firstChild);
          cell.append(content);
        }
      }
    }
  }

  function enhanceCharts() {
    for (const chart of app.querySelectorAll('.business-chart')) {
      const bars = [...chart.querySelectorAll('.column')];
      if (!bars.length) continue;
      const output = document.createElement('output');
      output.className = 'chart-readout';
      output.textContent = '选择柱形查看数值';
      chart.after(output);
      for (const bar of bars) {
        const text = bar.querySelector('.tooltip').textContent;
        bar.tabIndex = 0;
        bar.setAttribute('role', 'button');
        bar.setAttribute('aria-label', text);
        const show = () => { output.textContent = text; };
        bar.addEventListener('click', show);
        bar.addEventListener('keydown', (event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          show();
        });
      }
    }
  }

  const sourceRender = render;
  function enhancePage() {
    // JOYBUY-DEV OVERRIDE: 已删除「交互原型 · 示例数据」演示声明（页面均接真实数据）。
    if (current === 0) enhanceDashboard();
    enhanceTables(app);
    enhanceCharts();
    const route = current === 4 ? 3 : current;
    for (const button of nav.querySelectorAll('[data-route]')) {
      if (Number(button.dataset.route) === route) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    }
    const more = nav.querySelector('[data-sheet=more]');
    if ([0, 2, 3, 5].includes(route)) more.removeAttribute('aria-current');
    else more.setAttribute('aria-current', 'page');
    const platform = document.getElementById('platformAdminPanel');
    if (platform) enhanceTables(platform);
  }
  render = function () {
    sourceRender();
    enhancePage();
  };
  new MutationObserver(() => {
    const dialog = overlay.querySelector('.modal');
    if (!dialog) {
      if (overlayTrigger?.isConnected) overlayTrigger.focus({ preventScroll: true });
      overlayTrigger = null;
      document.body.classList.remove('business-dialog-open');
      return;
    }
    if (dialog.dataset.enhanced) return;
    dialog.dataset.enhanced = 'true';
    overlayTrigger ||= document.activeElement;
    document.body.classList.add('business-dialog-open');
    enhanceTables(dialog);
    dialog.tabIndex = -1;
    dialog.focus({ preventScroll: true });
  }).observe(overlay, { childList: true });
  document.addEventListener('keydown', (event) => {
    const dialog = overlay.querySelector('.modal');
    if (!dialog || sheet.open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeModal();
    }
    if (event.key !== 'Tab') return;
    const controls = [...dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]')]
      .filter((element) => element.getClientRects().length);
    if (!controls.length) return;
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  applyDesign(design);
  enhancePage();
})();