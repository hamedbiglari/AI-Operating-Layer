// The signed-in shell: sidebar (brand, new chat, searchable history, account entry) + main chat area.
// Desktop: persistent sidebar with a compact mode. Narrow windows / phones: the sidebar is a drawer opened from
// the top bar, and the chat stays the primary surface (styles/app.css @media max-width: 767px).
import { h, clear } from './dom.js';
import { icon } from './icons.js';

export function createShell(ctx) {
  const { t, store, chat, session } = ctx;
  let compact = false;
  let searchTimer = null;

  const search = h('input', { type: 'search', class: 'sidebar__search', id: 'history-search', placeholder: t('nav.search'),
                              'aria-label': t('nav.search'), autocomplete: 'off' });
  const history = h('ul', { class: 'history', id: 'history', 'aria-label': t('nav.history') });
  const more = h('button', { class: 'btn btn--ghost', type: 'button', hidden: true,
                             onclick: () => store.loadList({ offset: store.items.length }).catch((e) => ctx.toast(e.message)) },
                 t('nav.load_more'));
  const collapse = h('button', { class: 'btn btn--ghost icon-btn sidebar__collapse', type: 'button',
                                 'aria-label': t('nav.collapse'), 'aria-expanded': 'true',
                                 onclick: () => setCompact(!compact) }, icon('sidebar-toggle'));
  const closeDrawerBtn = h('button', { class: 'btn btn--ghost icon-btn topbar__menu', type: 'button',
                                       'aria-label': t('nav.close_menu'), onclick: () => setDrawer(false) },
                           icon('action-close'));
  const accountBtn = h('button', { class: 'account-btn', type: 'button', id: 'account-button',
                                   'aria-haspopup': 'menu', 'aria-expanded': 'false', 'aria-controls': 'account-menu' });
  const menu = h('ul', { class: 'menu', id: 'account-menu', role: 'menu', hidden: true, 'aria-label': t('account.menu') });
  const accountArea = h('div', { class: 'sidebar__account' }, menu, accountBtn);

  const sidebar = h('nav', { class: 'sidebar', id: 'sidebar', 'aria-label': t('nav.history') },
    h('div', { class: 'sidebar__top' },
      h('span', { class: 'sidebar__brand' }, h('img', { src: './brand/aiol-logo.svg', alt: '', width: 24, height: 24 }),
        h('span', { class: 'sidebar__brand-text', text: t('app.name') })),
      collapse, closeDrawerBtn),
    h('button', { class: 'btn sidebar__new', type: 'button', id: 'new-chat', onclick: () => { newChat(); } },
      icon('action-add'), h('span', { class: 'label', text: t('nav.new_chat') })),
    search, h('h2', { class: 'sidebar__heading', text: t('nav.history') }), history, more, accountArea);

  const title = h('h1', { class: 'topbar__title', id: 'chat-title' });
  const banner = h('div', { class: 'banner', id: 'banner', hidden: true });
  const main = h('main', { class: 'main', id: 'main' },
    h('header', { class: 'topbar' },
      h('button', { class: 'btn btn--ghost icon-btn topbar__menu', type: 'button', id: 'open-drawer',
                    'aria-label': t('nav.open_menu'), 'aria-controls': 'sidebar', onclick: () => setDrawer(true) },
        icon('sidebar-toggle')),
      title),
    banner, chat.thread, chat.form);
  const scrim = h('div', { class: 'scrim', hidden: true, onclick: () => setDrawer(false) });
  const root = h('div', { class: 'shell', id: 'shell' }, sidebar, main, scrim);

  function setCompact(on) {
    compact = on;
    root.dataset.compact = String(on);
    collapse.setAttribute('aria-label', t(on ? 'nav.expand' : 'nav.collapse'));
    collapse.setAttribute('aria-expanded', String(!on));
  }

  function setDrawer(open) {
    root.dataset.drawer = open ? 'open' : 'closed';
    scrim.hidden = !open;
    if (open) search.focus(); else document.getElementById('open-drawer')?.focus();
  }

  function newChat() {
    chat.open(null);
    title.textContent = t('nav.new_chat');
    renderHistory();
    setDrawer(false);
    chat.focus();
  }

  async function openConversation(c) {
    title.textContent = c.title || t('chat.untitled');
    setDrawer(false);
    await chat.open(c.id);
    renderHistory();
  }

  function itemMenu(c, anchor) {
    const act = async (fn) => { try { await fn(); } catch (err) { ctx.toast(err.message); } };
    const options = [
      ['chat.rename', 'action-edit', () => act(async () => {
        const name = window.prompt(t('chat.rename_prompt'), c.title || '');
        if (name && name.trim()) await store.rename(c.id, name.trim().slice(0, 300));
      })],
      ['chat.archive', 'action-archive', () => act(async () => { await store.archive(c.id); if (chat.conversationId === c.id) newChat(); })],
      ['chat.delete', 'action-delete', () => act(async () => {
        if (!window.confirm(t('chat.delete_confirm'))) return;
        await store.remove(c.id);
        if (chat.conversationId === c.id) newChat();
      })],
    ];
    popup(anchor, options.map(([k, ic, fn]) => ({ label: t(k), icon: ic, run: fn })));
  }

  function renderHistory() {
    clear(history);
    if (!store.items.length) {
      history.append(h('li', { class: 'subtle', style: 'padding: var(--space-2) var(--space-3)',
                               text: t(store.query ? 'nav.no_results' : 'nav.no_chats') }));
    }
    for (const c of store.items) {
      const current = chat.conversationId === c.id;
      const moreBtn = h('button', { class: 'btn btn--ghost icon-btn history__more', type: 'button',
                                    'aria-label': `${t('chat.rename')}, ${t('chat.archive')}, ${t('chat.delete')}`,
                                    onclick: (ev) => itemMenu(c, ev.currentTarget) }, icon('action-more'));
      history.append(h('li', { class: 'history__item', 'aria-current': current ? 'page' : null },
        h('button', { class: 'history__open', type: 'button', dir: 'auto', title: c.title || t('chat.untitled'),
                      onclick: () => openConversation(c) }, c.title || t('chat.untitled')),
        moreBtn));
      if (current) title.textContent = c.title || t('chat.untitled');
    }
    more.hidden = !store.hasMore;
  }

  search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => store.loadList({ query: search.value }).catch((e) => ctx.toast(e.message)), 250);
  });

  // ---- account menu
  function renderAccount() {
    const u = session.user ?? {};
    clear(accountBtn).append(h('span', { class: 'avatar', 'aria-hidden': 'true', text: initials(u.name || u.email) }),
      h('span', { class: 'account-btn__text' }, h('span', { dir: 'auto', text: u.name || u.email || '' }),
        h('span', { class: 'subtle', dir: 'auto', text: session.organization?.name ?? '' })));
    accountBtn.setAttribute('aria-label', `${t('account.menu')}: ${u.email ?? ''}`);
  }

  function buildMenu() {
    const u = session.user ?? {};
    const links = ctx.clientConfig.links;
    const items = [
      { label: t('menu.settings'), icon: 'settings', run: ctx.openSettings, id: 'menu-settings' },
      { label: t('menu.usage'), icon: 'analytics', run: ctx.openUsage, id: 'menu-usage' },
      { label: t('menu.language'), icon: 'language', run: ctx.openLanguage, id: 'menu-language' },
      links.help && { label: t('menu.help'), icon: 'help', run: () => ctx.openLink(links.help), external: true },
      'sep',
      { label: t('menu.upgrade'), icon: 'upgrade', run: ctx.openUpgrade, id: 'menu-upgrade' },
      { label: t('menu.apps'), icon: 'apps', run: ctx.openApps, id: 'menu-apps' },
      links.learn_more && { label: t('menu.learn'), icon: 'info', run: () => ctx.openLink(links.learn_more), external: true },
      'sep',
      { label: t('menu.logout'), icon: 'logout', run: ctx.signOut, id: 'menu-logout' },
    ].filter(Boolean);
    clear(menu).append(h('li', { class: 'menu__head', role: 'none' },
      h('div', { dir: 'auto', text: u.email ?? '' }),
      h('div', { class: 'subtle', text: t('account.role', { role: u.role ?? '' }) })));
    for (const it of items) {
      if (it === 'sep') { menu.append(h('li', { class: 'menu__sep', role: 'separator' })); continue; }
      menu.append(h('li', { role: 'none' }, h('button', { class: 'menu__item', role: 'menuitem', type: 'button', id: it.id,
        tabindex: '-1', onclick: () => { closeMenu(false); it.run(); } },
        icon(it.icon), h('span', { text: it.label }), it.external ? icon('action-external') : null)));
    }
  }

  const menuItems = () => [...menu.querySelectorAll('[role="menuitem"]')];
  function openMenu() {
    buildMenu();
    menu.hidden = false;
    accountBtn.setAttribute('aria-expanded', 'true');
    menuItems()[0]?.focus();
    setTimeout(() => document.addEventListener('pointerdown', outside, { once: true }), 0);
  }
  function closeMenu(focusBack = true) {
    menu.hidden = true;
    accountBtn.setAttribute('aria-expanded', 'false');
    if (focusBack) accountBtn.focus();
  }
  function outside(ev) { if (!accountArea.contains(ev.target)) closeMenu(false); else if (!menu.hidden) document.addEventListener('pointerdown', outside, { once: true }); }
  accountBtn.addEventListener('click', () => (menu.hidden ? openMenu() : closeMenu()));
  menu.addEventListener('keydown', (ev) => {
    const items = menuItems();
    const i = items.indexOf(document.activeElement);
    if (ev.key === 'Escape') { ev.preventDefault(); closeMenu(); }
    else if (ev.key === 'ArrowDown') { ev.preventDefault(); items[(i + 1) % items.length].focus(); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    else if (ev.key === 'Home') { ev.preventDefault(); items[0].focus(); }
    else if (ev.key === 'End') { ev.preventDefault(); items[items.length - 1].focus(); }
    else if (ev.key === 'Tab') closeMenu(false);
  });
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && root.dataset.drawer === 'open') setDrawer(false); });

  store.on(renderHistory);
  setCompact(false);
  renderAccount();
  title.textContent = t('nav.new_chat');

  function setBanner(text, tone = 'warning') {
    banner.hidden = !text;
    banner.className = `banner notice notice--${tone}`;
    banner.textContent = text || '';
  }

  return { root, renderHistory, renderAccount, newChat, setBanner, title };
}

export function initials(s) {
  const parts = String(s || '?').trim().split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? '?') + (parts[1]?.[0] ?? '')).toUpperCase();
}

/** A small anchored popup menu for per-item actions. */
function popup(anchor, options) {
  document.querySelector('.menu--popup')?.remove();
  const rect = anchor.getBoundingClientRect();
  const list = h('ul', { class: 'menu menu--popup', role: 'menu',
    style: `position:fixed; inset-block-start:${Math.min(rect.bottom, window.innerHeight - 160)}px; inset-inline-start:auto;` +
           `left:${Math.max(8, Math.min(rect.left, window.innerWidth - 248))}px; inset-block-end:auto` });
  const close = () => { list.remove(); anchor.focus(); };
  for (const o of options) {
    list.append(h('li', { role: 'none' }, h('button', { class: 'menu__item', role: 'menuitem', type: 'button',
      onclick: () => { list.remove(); o.run(); } }, icon(o.icon), o.label)));
  }
  list.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') close(); });
  document.body.append(list);
  list.querySelector('button')?.focus();
  setTimeout(() => document.addEventListener('pointerdown', (ev) => { if (!list.contains(ev.target)) list.remove(); }, { once: true }), 0);
}
