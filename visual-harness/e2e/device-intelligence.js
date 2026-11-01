#!/usr/bin/env node
/*
 * Browser checks for the Device Intelligence admin screen (ADR-138).
 *   Not connected: data-live-wired, the note and the form shown, the body hidden.
 *   Live:   ONE request fills the table: reference, platform label (macOS and unknown values as sent),
 *           app version, status badge, evidence-category badges, linked-account count; the total line;
 *           the state filter (one request); Details (one audited request) fills the detail with linked
 *           accounts and observations showing only short references and signal states; Revoke (confirm,
 *           POST, reload); 403 says owners/admins only; 500 says why; no installations; Persian over live
 *           content (an identity FA entry would hang here).
 * Runs on file:// with AI Core mocked in the page and every request recorded. Persian expectations are
 * built from code points, so this file stays ASCII.
 *
 * Usage: node visual-harness/e2e/device-intelligence.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-device-intel';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069);
const iso = (s) => FSI + s + PDI;
const digits = (s) => s.replace(/[0-9]/g, (d) => String.fromCharCode(0x6F0 + Number(d)));
const FA = {
  title: fa(0x647, 0x648, 0x634, 0x20, 0x62F, 0x633, 0x62A, 0x6AF, 0x627, 0x647),
  windows: fa(0x648, 0x6CC, 0x646, 0x62F, 0x648, 0x632),
  sameInstall: fa(0x647, 0x645, 0x627, 0x646, 0x20, 0x646, 0x635, 0x628, 0x20, 0x62B, 0x628, 0x62A, 0x200C, 0x634, 0x62F, 0x647),
  shared: fa(0x645, 0x62D, 0x6CC, 0x637, 0x20, 0x645, 0x634, 0x62A, 0x631, 0x6A9, 0x20, 0x627, 0x62D, 0x62A, 0x645, 0x627, 0x644, 0x6CC, 0x20, 0x628, 0x631, 0x646, 0x627, 0x645, 0x647),
  insufficient: fa(0x634, 0x648, 0x627, 0x647, 0x62F, 0x20, 0x646, 0x627, 0x6A9, 0x627, 0x641, 0x6CC),
  details: fa(0x62C, 0x632, 0x626, 0x6CC, 0x627, 0x62A),
  denied: fa(0x641, 0x642, 0x637, 0x20, 0x645, 0x627, 0x644, 0x6A9, 0x627, 0x646, 0x20, 0x648, 0x20, 0x645, 0x62F, 0x6CC, 0x631, 0x627, 0x646, 0x20, 0x645, 0x6CC, 0x200C, 0x62A, 0x648, 0x627, 0x646, 0x646, 0x62F, 0x20, 0x646, 0x635, 0x628, 0x200C, 0x647, 0x627, 0x20, 0x631, 0x627, 0x20, 0x628, 0x628, 0x6CC, 0x646, 0x646, 0x62F, 0x2E),
  revoked: fa(0x646, 0x635, 0x628, 0x20, 0x628, 0x627, 0x637, 0x644, 0x20, 0x634, 0x62F, 0x2E),
  installations: fa(0x646, 0x635, 0x628),
  verified: fa(0x627, 0x645, 0x636, 0x627, 0x20, 0x62A, 0x623, 0x6CC, 0x6CC, 0x62F, 0x20, 0x634, 0x62F)
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const assess = (cats, accounts) => ({ categories: cats, reason_codes: cats[0] === 'INSUFFICIENT_EVIDENCE' ? [] : ['multiple_accounts_proved_possession_of_one_key'],
  algorithm_version: 'di-assess-v2', evidence: { active_linked_accounts: accounts } });
const cred = (id, ref, prov, status, cats, accounts) => ({ id, reference: ref, provenance: prov, key_storage_claimed: 'os_keystore',
  app_version: '0.1.0', os_family: 'windows', os_version: '11', status, revoked_reason: null, revoked_at: null,
  first_seen_at: '2026-10-30T10:00:00Z', last_seen_at: '2026-10-31T10:00:00Z', last_verified_at: '2026-10-31T10:00:00Z',
  assessment: assess(cats, accounts) });
const ITEMS = [
  cred('c1', 'a1b2c3d4e5f6', 'WINDOWS_CLIENT', 'active', ['SAME_REGISTERED_INSTALLATION', 'LIKELY_SHARED_CLIENT_ENVIRONMENT'], 2),
  cred('c2', '0f0e0d0c0b0a', 'MACOS_CLIENT', 'active', ['INSUFFICIENT_EVIDENCE'], 1),
  cred('c3', '99aa88bb77cc', 'ODD_CLIENT', 'revoked', ['DEVICE_CREDENTIAL_REVOKED'], 0),
];
const DETAIL = Object.assign({}, ITEMS[0], {
  linked_accounts: [{ user_id: 'u1', email: 'owner@example.dev', first_linked_at: '2026-10-30T10:00:00Z', last_verified_at: null, unlinked_at: null },
                    { user_id: 'u2', email: 'member@example.dev', first_linked_at: '2026-10-30T11:00:00Z', last_verified_at: null, unlinked_at: null }],
  observations: [{ kind: 'verified', reason_code: null, provenance: 'WINDOWS_CLIENT', network_ref: '1a2b3c4d5e', os_install_ref: '9f8e7d6c5b',
                   signal_states: { machine_guid: 'observed', gdid: 'unsupported' }, app_version: '0.1.0', at: '2026-10-31T10:00:00Z' }],
});

function installMock(fx) {
  const items = fx.items, detail = fx.detail;
  window.__requests = []; window.__status = 200; window.__items = items; window.__detail = detail;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    if (p.indexOf('/devices/') !== 0) return reply({ items: [], total: 0 });
    window.__requests.push(method + ' ' + p);
    if (window.__status !== 200) return reply({ error: { message: 'devices offline' } }, window.__status);
    if (/\/revoke$/.test(p) && method === 'POST') { window.__detail = Object.assign({}, window.__detail, { status: 'revoked' }); return reply(window.__detail); }
    if (p.indexOf('/devices/admin/credentials?') === 0) {
      const q = new URLSearchParams(p.slice(p.indexOf('?') + 1)), st = q.get('state');
      const shown = st ? window.__items.filter((x) => x.status === st) : window.__items;
      return reply({ items: shown, total: shown.length, limit: 20, offset: Number(q.get('offset')) });
    }
    if (p.indexOf('/devices/admin/credentials/') === 0) return reply(window.__detail);
    return reply({});
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('dialog', (d) => d.accept());
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(200);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  const requests = () => page.evaluate(() => window.__requests || []);
  const view = () => page.evaluate(() => {
    const $ = (id) => document.getElementById(id), shown = (e) => !e.hidden && getComputedStyle(e).display !== 'none';
    return {
      body: shown($('di-body')), note: $('di-conn-note').textContent, total: $('di-total').textContent,
      rows: Array.from(document.querySelectorAll('#di-rows tr')).map((tr) => Array.from(tr.cells).slice(0, 7).map((td, i) =>
        i === 5 ? Array.from(td.querySelectorAll('.badge')).map((b) => b.textContent) : td.textContent)),
      detail: shown($('di-detail')),
      accounts: Array.from(document.querySelectorAll('#di-accounts li')).map((li) => li.querySelector('bdi').textContent),
      obs: Array.from(document.querySelectorAll('#di-obs tr')).map((tr) => Array.from(tr.cells).slice(1).map((td) => td.textContent)),
      action: $('di-action').textContent, revokeDisabled: $('di-revoke').disabled,
      html: $('screen-device-intel').textContent,
    };
  });

  check('data-live-wired; note and form shown, body hidden', await page.evaluate(() => [
    document.getElementById('screen-device-intel').hasAttribute('data-live-wired'), !document.getElementById('di-connect').hidden,
    document.getElementById('di-body').hidden]), [true, true, true]);

  await page.evaluate(installMock, { items: ITEMS, detail: DETAIL });
  await connect();
  check('ONE request for the list', await requests(), ['GET /devices/admin/credentials?limit=20&offset=0']);
  let v = await view();
  check('connected note; body shown', [v.body, v.note], [true, 'Connected to ' + iso('http://core.test') + '.']);
  check('total', v.total, '3 installations');
  check('rows: reference, platform (macOS and unknown as sent), version, status, categories, accounts', v.rows.map((r) => [r[0], r[1], r[2], r[4], r[5], r[6]]), [
    ['a1b2c3d4e5f6', 'Windows', '0.1.0', 'Active', ['Same registered installation', 'Likely shared client environment'], '2'],
    ['0f0e0d0c0b0a', 'MACOS_CLIENT', '0.1.0', 'Active', ['Insufficient evidence'], '1'],
    ['99aa88bb77cc', 'ODD_CLIENT', '0.1.0', 'Revoked', ['Device credential revoked'], '0']]);

  let before = (await requests()).length;
  await page.selectOption('#di-state', 'revoked'); await settle();
  check('state filter: one request', (await requests()).slice(before), ['GET /devices/admin/credentials?limit=20&offset=0&state=revoked']);
  check('state filter: one row', (await view()).rows.map((r) => r[0]), ['99aa88bb77cc']);
  await page.selectOption('#di-state', ''); await settle();

  before = (await requests()).length;
  await page.click('#di-rows tr:first-child button'); await settle();
  v = await view();
  check('Details: one request', (await requests()).slice(before), ['GET /devices/admin/credentials/c1']);
  check('detail: accounts and observations with short references and signal states only', [v.detail, v.accounts, v.obs], [true,
    ['owner@example.dev', 'member@example.dev'], [['Signature verified', '1a2b3c4d5e', '9f8e7d6c5b', 'machine_guid: observed, gdid: unsupported']]]);
  check('the word "person" appears nowhere on the screen', /\bperson\b/i.test(v.html.replace(/never people/, '')), false);

  before = (await requests()).length;
  await page.click('#di-revoke'); await settle();
  v = await view();
  check('Revoke: POST, list reload, detail reload', (await requests()).slice(before),
    ['POST /devices/admin/credentials/c1/revoke', 'GET /devices/admin/credentials?limit=20&offset=0', 'GET /devices/admin/credentials/c1']);
  check('Revoke: said, button disabled', [v.action, v.revokeDisabled], ['Installation revoked.', true]);

  await lang('fa');
  v = await view();
  check('fa: total, platform, categories', [v.total, v.rows[0][1], v.rows[0][5][0], v.rows[0][5][1], v.rows[1][5][0]],
    [digits('3') + ' ' + FA.installations, FA.windows, FA.sameInstall, FA.shared, FA.insufficient]);
  check('fa: macOS and unknown values stay as sent', [v.rows[1][1], v.rows[2][1]], ['MACOS_CLIENT', 'ODD_CLIENT']);
  check('fa: observation event and revoke message', [v.obs[0][0], v.action], [FA.verified, FA.revoked]);
  check('fa: heading', await page.evaluate(() => document.getElementById('h-device-intel').textContent), FA.title);
  await lang('en');
  check('back to English', (await view()).total, '3 installations');

  await page.evaluate(() => { window.__status = 403; });
  await page.selectOption('#di-state', 'active'); await settle();
  check('403: owners and administrators only', (await view()).total, 'Only owners and administrators can see installations.');
  await page.evaluate(() => { window.__status = 500; });
  await page.selectOption('#di-state', ''); await settle();
  check('500: the message', (await view()).total, 'Could not load installations (' + iso('devices offline') + ').');
  await page.evaluate(() => { window.__status = 200; window.__items = []; });
  await page.selectOption('#di-state', 'active'); await settle();
  check('no installations: said', (await view()).total,
    'No installations yet. An installation appears after an official AIOL app signs in with installation verification on.');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
