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
import { openApps, openLanguage, openSettings, openUpgrade, openUsage } from './ui/panels.js';

const app = document.getElementById('app');
const LOCAL_PREFS = 'aiol.local.prefs';     // last-used language/theme, so the sign-in screen matches the account

function readLocal() { try { return JSON.parse(localStorage.getItem(LOCAL_PREFS) || '{}'); } catch { return {}; } }
function writeLocal(p) { try { localStorage.setItem(LOCAL_PREFS, JSON.stringify(p)); } catch { /* private mode */ } }

function applyAppearance(i18n, theme) {
  const root = document.documentElement;
  root.lang = i18n.lang;
  root.dir = i18n.dir;
  if (theme === 'light' || theme === 'dark') root.dataset.theme = theme; else delete root.dataset.theme;
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
  const local = readLocal();
  const i18n = createI18n(local.language || (navigator.language?.startsWith('fa') ? 'fa' : 'en'));
  applyAppearance(i18n, local.theme);
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
  let clientConfig = { links: {}, upgrade: { state: 'not_configured' }, releases: [], device_intelligence: { enabled: false } };
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
    clear(app).append(signInView({ t, session, links: clientConfig.links, openLink, onSignedIn: showApp }));
    if (message) toast(message);
  }

  async function showApp() {
    const ctx = {
      t, i18n, http, store, session, device, appInfo, toast, copy, openLink, online, apiBase: config.apiBaseUrl,
      get clientConfig() { return clientConfig; },
      preferences: { language: i18n.lang, theme: readLocal().theme ?? 'system' },
      onConversationCreated: () => shell.renderHistory(),
      onAnswered: () => refreshLimit(),
    };
    ctx.savePreferences = async (patch) => {
      try {
        const saved = await http.put('/users/me/preferences', patch);
        ctx.preferences = { language: saved.language, theme: saved.theme };
        writeLocal(ctx.preferences);
        const relang = saved.language !== i18n.lang;
        i18n.set(saved.language);
        applyAppearance(i18n, saved.theme);
        toast(t('settings.saved'));
        if (relang) await showApp(); // rebuild with the new language and direction; the server keeps the chats
      } catch (err) { toast(err.message); }
    };
    ctx.openSettings = () => openSettings(ctx);
    ctx.openUsage = () => openUsage(ctx);
    ctx.openLanguage = () => openLanguage(ctx);
    ctx.openApps = () => openApps(ctx);
    ctx.openUpgrade = () => openUpgrade(ctx);
    ctx.signOut = async () => {
      manualSignOut = true;
      await session.signOut();     // emits signed_out -> showSignIn
    };

    // Account preferences win over the local copy (server-authoritative).
    try {
      const prefs = await http.get('/users/me/preferences');
      ctx.preferences = { language: prefs.language, theme: prefs.theme };
      writeLocal(ctx.preferences);
      i18n.set(prefs.language);
      applyAppearance(i18n, prefs.theme);
    } catch { /* keep the local copy */ }

    const chat = createChatView(ctx);
    ctx.chat = chat;
    const shell = createShell(ctx);
    clear(app).append(shell.root);

    async function refreshLimit() {
      try {
        const cfg = await http.get('/chat/config');
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
