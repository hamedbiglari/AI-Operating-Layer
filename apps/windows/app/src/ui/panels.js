// Settings, Usage, Language, Get apps and Upgrade, as native <dialog>s (focus trap, Esc to close, inert page).
// Every value shown is read from Cloud Core when the dialog opens; nothing is computed or assumed locally.
import { h, clear } from './dom.js';
import { icon } from './icons.js';
import { DeviceStatus } from '../core/device.js';

function dialogShell(title, t) {
  const body = h('div', { class: 'dlg__body' });
  const dlg = h('dialog', { 'aria-labelledby': 'dlg-title' },
    h('div', { class: 'dlg__head' }, h('h2', { id: 'dlg-title', text: title }),
      h('button', { class: 'btn btn--ghost icon-btn', type: 'button', 'aria-label': t('common.close'),
                    onclick: () => dlg.close() }, icon('action-close'))),
    body);
  dlg.addEventListener('close', () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  return { dlg, body };
}

function loading(t) { return h('p', { class: 'muted', role: 'status', text: t('common.loading') }); }

export async function openUsage(ctx) {
  const { t, http, i18n } = ctx;
  const { body } = dialogShell(t('usage.title'), t);
  body.append(loading(t));
  try {
    const [usage, cfg] = await Promise.all([http.get('/billing/usage'), http.get('/chat/config')]);
    clear(body);
    body.append(h('p', { class: 'subtle', text: t('usage.as_of', { time: i18n.dateTime(usage.as_of) }) }));
    const chat = h('section', { class: 'section' }, h('h3', { text: t('usage.chat_today') }));
    if (cfg.messages_per_user_per_day == null) chat.append(h('p', { class: 'muted', text: t('usage.unlimited') }));
    else {
      const pct = Math.min(1, cfg.messages_used_today / Math.max(1, cfg.messages_per_user_per_day));
      chat.append(h('p', { text: t('chat.limit', { used: cfg.messages_used_today, limit: cfg.messages_per_user_per_day }) }),
        h('div', { class: 'meter', role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': cfg.messages_per_user_per_day,
                   'aria-valuenow': cfg.messages_used_today, dataset: { state: pct >= 1 ? 'exceeded' : 'ok' } },
          h('span', { style: `inline-size:${Math.round(pct * 100)}%` })));
    }
    body.append(chat);
    for (const q of usage.quotas) {
      const s = h('section', { class: 'section', dataset: { quota: q.key } },
        h('div', { class: 'row' }, h('h3', { text: q.label }),
          h('span', { class: 'pill', dataset: { tone: q.state === 'exceeded' ? 'danger' : q.state === 'warning' ? 'warning'
                                                       : q.state === 'ok' ? 'success' : 'unknown' } },
            t(`usage.state.${q.state}`))));
      if (q.percent != null) {
        s.append(h('div', { class: 'meter', dataset: { state: q.state }, role: 'meter', 'aria-valuemin': 0,
                            'aria-valuemax': 100, 'aria-valuenow': Math.round(Math.min(q.percent, 1) * 100) },
          h('span', { style: `inline-size:${Math.round(Math.min(q.percent, 1) * 100)}%` })));
      }
      if (q.used != null && q.limit != null) s.append(h('p', { class: 'muted', text: `${i18n.number(q.used)} / ${i18n.number(q.limit)} ${q.unit}` }));
      if (q.detail) s.append(h('p', { class: 'subtle', dir: 'auto', text: q.detail }));
      if (q.resets_at) s.append(h('p', { class: 'subtle', text: t('usage.resets', { time: i18n.dateTime(q.resets_at) }) }));
      body.append(s);
    }
    body.append(h('p', { class: 'subtle', text: t('usage.tokens', { n: usage.tokens.requests }) }),
                h('p', { class: 'subtle', text: t('usage.no_plan') }));
  } catch (err) {
    clear(body);
    body.append(h('p', { class: 'error-text', role: 'alert', text: err.message }));
  }
}

export async function openSettings(ctx) {
  const { t, http, device, appInfo, clientConfig, i18n } = ctx;
  const { body } = dialogShell(t('settings.title'), t);

  const di = clientConfig.device_intelligence ?? { enabled: false, observation_retention_days: null };
  const status = h('p', { class: 'subtle', role: 'status' });
  const listEl = h('ul', { class: 'list' });
  const showStatus = () => { status.textContent = t('settings.device_status', { status: t(`device.${device.status}`) }); };
  const loadMine = async () => {
    clear(listEl);
    try {
      const { items } = await http.get('/devices/credentials');
      if (!items.length) listEl.append(h('li', { class: 'muted', text: t('settings.devices_none') }));
      for (const c of items) {
        listEl.append(h('li', { class: 'row' },
          h('span', {}, t(`platform.${platformOf(c.provenance)}`), ' · ', c.app_version ?? '', ' · ',
            h('span', { class: 'subtle', text: i18n.dateTime(c.last_seen_at) })),
          h('button', { class: 'btn btn--ghost btn--danger', type: 'button', onclick: async () => {
            try { await http.del(`/devices/credentials/${c.id}`); await loadMine(); } catch (err) { ctx.toast(err.message); }
          } }, t('settings.remove'))));
      }
    } catch (err) { listEl.append(h('li', { class: 'error-text', text: err.message })); }
  };
  const toggle = h('input', { type: 'checkbox', id: 'device-toggle', checked: device.enabled, disabled: !di.enabled,
    onchange: async (ev) => {
      ev.target.disabled = true;
      if (ev.target.checked) await device.enable({ serverEnabled: di.enabled }); else await device.disable();
      ev.target.disabled = false;
      showStatus();
      await loadMine();
    } });
  showStatus();
  body.append(h('section', { class: 'section' }, h('h3', { text: t('settings.privacy') }),
    h('label', { class: 'switch', for: 'device-toggle' }, toggle, t('settings.device')),
    h('p', { class: 'subtle', text: t('settings.device_help', { days: di.observation_retention_days ?? '—' }) }),
    h('p', { class: 'subtle', text: t('settings.this_device') }), status,
    h('h3', { text: t('settings.devices_list') }), listEl,
    clientConfig.links.privacy ? h('button', { class: 'linkish', type: 'button',
      onclick: () => ctx.openLink(clientConfig.links.privacy) }, t('settings.legal')) : null));
  if (device.status === DeviceStatus.UNAVAILABLE && !di.enabled) toggle.checked = false;
  await loadMine();

  // Signed desktop updates (ADR-140). Shown only where the shell has an updater; the check is explicit.
  if (appInfo.platform === 'windows' || appInfo.platform === 'macos') {
    const upd = h('p', { class: 'subtle', role: 'status', id: 'update-status' });
    const install = h('button', { class: 'btn btn--primary', type: 'button', hidden: true, id: 'update-install' },
                      t('settings.update_install'));
    const check = h('button', { class: 'btn', type: 'button', id: 'update-check', onclick: async () => {
      check.disabled = true;
      try {
        const r = await ctx.bridge.updateCheck(ctx.apiBase);
        upd.textContent = r.state === 'available' ? t('settings.update_available', { version: r.version })
          : r.state === 'none' ? t('settings.update_none') : t('settings.update_unavailable');
        install.hidden = r.state !== 'available';
      } catch { upd.textContent = t('settings.update_failed'); } finally { check.disabled = false; }
    } }, t('settings.check_updates'));
    install.addEventListener('click', async () => {
      install.disabled = true;
      try { await ctx.bridge.updateInstall(ctx.apiBase); } catch { upd.textContent = t('settings.update_failed'); install.disabled = false; }
    });
    body.append(h('section', { class: 'section' }, h('h3', { text: t('settings.updates') }),
      h('div', { class: 'row' }, check, install), upd));
  }

  body.append(h('section', { class: 'section' }, h('h3', { text: t('settings.about') }),
    h('p', { text: t('settings.version', { version: appInfo.version, platform: t(`platform.${appInfo.platform}`) }) }),
    h('p', { class: 'subtle', text: t('settings.server', { url: ctx.apiBase }) }),
    clientConfig.links.terms ? h('button', { class: 'linkish', type: 'button',
      onclick: () => ctx.openLink(clientConfig.links.terms) }, t('settings.terms')) : null));
}

export function platformOf(provenance) {
  return { WEB_BROWSER: 'web', WINDOWS_CLIENT: 'windows', MACOS_CLIENT: 'macos', ANDROID_CLIENT: 'android',
           IOS_CLIENT: 'ios' }[provenance] ?? 'web';
}

export function openApps(ctx) {
  const { t, clientConfig } = ctx;
  const { body } = dialogShell(t('apps.title'), t);
  const rel = clientConfig.releases ?? [];
  if (!rel.length) { body.append(h('p', { class: 'muted', text: t('apps.none') })); return; }
  body.append(h('ul', { class: 'list' }, rel.map((r) => h('li', { class: 'row' },
    h('span', {}, t(`platform.${r.platform}`), r.version ? ` · ${r.version}` : ''),
    h('span', { class: 'pill', text: t(`apps.status.${r.status}`) }),
    r.url && r.status !== 'NOT_SUPPORTED' ? h('button', { class: 'btn', type: 'button', onclick: () => ctx.openLink(r.url) },
      icon('action-download'), t('apps.download')) : null))));
}

export function openUpgrade(ctx) {
  const { t, clientConfig } = ctx;
  const { body } = dialogShell(t('upgrade.title'), t);
  const up = clientConfig.upgrade ?? { state: 'not_configured' };
  if (up.state === 'available' && up.url) {
    body.append(h('p', { class: 'muted', text: t('usage.no_plan') }),
      h('button', { class: 'btn btn--primary', type: 'button', onclick: () => ctx.openLink(up.url) },
        icon('action-external'), t('upgrade.open')));
  } else {
    body.append(h('p', { class: 'muted', text: t(up.state === 'not_offered_on_platform' ? 'upgrade.not_on_platform'
                                                                                         : 'upgrade.not_configured') }));
  }
}

/**
 * "+" in the composer: add a document to the knowledge base (POST /documents/upload). The person picks the source
 * it belongs to; Cloud Core accepts it (202) and processes it in the background. The dialog says what is true:
 * the document is not read by the next answer — it becomes answerable once processing has produced evidence.
 */
export async function openUpload(ctx) {
  const { t, http } = ctx;
  const { dlg, body } = dialogShell(t('upload.title'), t);
  if (!['owner', 'admin', 'researcher', 'editor'].includes(ctx.session?.user?.role)) {
    body.append(h('p', { class: 'muted', text: t('upload.no_permission') }));
    return dlg;
  }
  body.append(h('p', { class: 'muted', text: t('upload.explain') }), loading(t));
  let sources = [];
  try {
    sources = (await http.get('/sources/overview?limit=100')).items ?? [];
  } catch (err) { clear(body); body.append(h('p', { class: 'error-text', role: 'alert', text: err.message })); return; }
  clear(body);
  body.append(h('p', { class: 'muted', text: t('upload.explain') }));
  if (!sources.length) { body.append(h('p', { class: 'muted', text: t('upload.no_sources') })); return; }
  const select = h('select', { id: 'upload-source' }, sources.map((src) => h('option', { value: src.id, text: src.title })));
  const file = h('input', { type: 'file', id: 'upload-file', accept: '.pdf,.docx,.doc,.txt,.md,.html,.htm,.csv,.xlsx,.png,.jpg,.jpeg,.webp,.tif,.tiff,image/*' });
  const status = h('p', { class: 'subtle', role: 'status' });
  const go = h('button', { class: 'btn btn--primary', type: 'button', id: 'upload-go' }, icon('action-upload'), t('upload.go'));
  go.addEventListener('click', async () => {
    if (!file.files?.length) { status.textContent = t('upload.pick_file'); return; }
    go.disabled = true;
    status.textContent = t('common.loading');
    try {
      const form = new FormData();
      form.append('source_id', select.value);
      form.append('file', file.files[0]);
      // Text in photos and scans may be English or Persian; OCR reads both.
      form.append('ocr_languages', 'eng+fas');
      await http.upload('/documents/upload', form);
      status.textContent = t('upload.accepted');
      file.value = '';
    } catch (err) { status.textContent = err.message; } finally { go.disabled = false; }
  });
  body.append(h('label', { for: 'upload-source', text: t('upload.source') }), select,
              h('label', { for: 'upload-file', text: t('upload.file') }), file, h('div', { class: 'row' }, go), status);
  return dlg;
}
