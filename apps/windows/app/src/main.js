// AIOL client entry point (ADR-137). Same code on Windows, macOS, Android, iOS (inside the Tauri shell) and in a
// plain browser (development and end-to-end tests). The platform differences live in core/platform.js.
import { loadConfig } from './config.js';
import { Http } from './core/http.js';
import { Session } from './core/session.js';
import { Conversations } from './core/conversations.js';
import { DeviceIntelligence } from './core/device.js';
import { createI18n } from './core/i18n.js';
import { detectBridge } from './core/platform.js';
import { h, clear } from './ui/dom.js';
import { signInView } from './ui/signin.js';
import { createShell } from './ui/shell.js';
import { createChatView } from './ui/chat.js';
import { openApps, openSettings, openUpgrade, openUpload, openUsage } from './ui/panels.js';

const app = document.getElementById('app');


// The apps have one appearance: English interface, light theme, left-to-right chrome (owner decision,
// 2026-11-01). People can still write and read Persian in the chat: every message and the composer use
// dir="auto", so each paragraph takes the direction of its own text.
function applyAppearance() {
  const root = document.documentElement;
  root.lang = 'en';
  root.dir = 'ltr';
  root.dataset.theme = 'light';
}

function toast(text) {
  document.querySelector('.toast')?.remove();
  const el = h('div', { class: 'toast', role: 'status', text });
  document.body.append(el);
  setTimeout(() => el.remove(), 3500);
}

async function copy(text) {
  try { await navigator.clipboard.writeText(text); } catch { /* clipboard denied: nothing else is attempted */ }
}

async function boot() {
  const bridge = await detectBridge();
  let config;
  try {
    config = await loadConfig({ bridgeKind: bridge.kind });
  } catch (err) {
    app.textContent = `Configuration error: ${err.message}`;
    return;
  }
  const i18n = createI18n('en');
  applyAppearance();
  const t = i18n.t;

  let session;
  const http = new Http({
    baseUrl: config.apiBaseUrl,
    token: () => session.token(),
    refresh: () => session.refresh(),
    onSessionLost: () => { session.lost(); },
  });
  session = new Session({ bridge, http });
  const store = new Conversations({ http });
  const device = new DeviceIntelligence({ bridge, http });
  const appInfo = await bridge.appInfo();
  let clientConfig = { links: {}, upgrade: { state: 'not_configured' }, releases: [], device_intelligence: { enabled: false },
                       terms: null };
  try {
    clientConfig = await http.get(`/clients/config?platform=${encodeURIComponent(appInfo.platform)}`, { auth: false });
  } catch { /* offline at launch: links stay hidden until the next launch */ }

  const openLink = async (url) => {
    try { await bridge.openExternal(url); } catch { toast(t('link.unavailable')); }
  };

  let renewTimer = null;
  const online = () => navigator.onLine !== false;

  function showSignIn(message) {
    clearInterval(renewTimer);
    store.reset();
    clear(app).append(signInView({ t, session, links: clientConfig.links, openLink, onSignedIn: showApp,
                                   terms: clientConfig.terms }));
    if (message) toast(message);
  }

  async function showApp() {
    const ctx = {
      t, i18n, http, store, session, device, appInfo, toast, copy, openLink, online, apiBase: config.apiBaseUrl, bridge,
      get clientConfig() { return clientConfig; },
      preferences: { language: 'en', theme: 'light' },
      onConversationCreated: () => shell.renderHistory(),
      onAnswered: () => refreshLimit(),
    };
    ctx.onEmpty = (empty) => { shell.root.dataset.empty = String(empty); };
    ctx.openUpload = () => openUpload(ctx);
    ctx.openSettings = () => openSettings(ctx);
    ctx.openUsage = () => openUsage(ctx);
    ctx.openApps = () => openApps(ctx);
    ctx.openUpgrade = () => openUpgrade(ctx);
    ctx.signOut = async () => {
      manualSignOut = true;
      await session.signOut();     // emits signed_out -> showSignIn
    };

    const chat = createChatView(ctx);
    ctx.chat = chat;
    const shell = createShell(ctx);
    clear(app).append(shell.root);

    async function refreshLimit() {
      try {
        const cfg = await http.get('/chat/config');
        ctx.chatConfig = cfg;
        if (!cfg.enabled) { shell.setBanner(t('chat.disabled')); chat.setEnabled(false); return; }
        shell.setBanner(online() ? '' : t('common.offline'));
        chat.setEnabled(true);
        chat.setHint(cfg.messages_per_user_per_day != null
          ? t('chat.limit', { used: cfg.messages_used_today, limit: cfg.messages_per_user_per_day }) : '');
      } catch (err) { if (err.kind !== 'session_expired') shell.setBanner(err.message); }
    }

    chat.open(null);
    await Promise.all([store.loadList().catch((e) => toast(e.message)), refreshLimit()]);
    // Optional, never blocking: runs after the app is usable and its outcome only appears in Settings.
    device.ensure({ serverEnabled: clientConfig.device_intelligence?.enabled }).catch(() => {});

    clearInterval(renewTimer);
    renewTimer = setInterval(() => { if (session.needsRenewal()) session.refresh(); }, 30000);
    window.onoffline = () => shell.setBanner(t('common.offline'));
    window.ononline = () => { refreshLimit(); store.loadList().catch(() => {}); };
  }

  let manualSignOut = false;
  session.on((s) => {
    if (s.state !== 'signed_out') return;
    showSignIn(manualSignOut ? null : t('error.session_expired'));
    manualSignOut = false;
  });

  clear(app).append(h('p', { class: 'signin muted', role: 'status', text: t('signin.restoring') }));
  let restored = false;
  try { restored = await session.restore(); } catch { restored = false; }
  if (restored) await showApp(); else showSignIn();
}

boot();
