#!/usr/bin/env node
/*
 * Browser checks for the Settings screen (Step 13).
 *   Sample: the self-profile editor and its button (V5-settings-self-profile),
 *           the font picker (V5-settings-font-picker), Plan & billing
 *           (V5-settings-billing-card) and the factory reset row
 *           (V5-settings-factory-reset) are hidden as debt; static text in
 *           Persian.
 *   Live:   the Settings cards stay visible (data-live-keep) and the generic
 *           panel steps aside; Appearance shows the saved theme and
 *           language; the preference status names the last change; one
 *           GET /auth/me fills the Account card (name, email, role) and the
 *           Organization card; an admin renames the organization with one
 *           PATCH; a viewer is told only an owner or admin can; the top-bar
 *           language button saves the language (V5-topbar-lang-save-bug);
 *           Reset works on this device without saving; Log out opens the
 *           login page with no token left; Persian over live content.
 * Runs on file:// with AI Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/settings.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-settings';
const fa = (...codes) => String.fromCharCode(...codes);
const iso = (s) => fa(0x2068) + s + fa(0x2069);
const FA = {
  appearance: [0x646, 0x645, 0x627, 0x6CC, 0x20, 0x638, 0x627, 0x647, 0x631, 0x6CC],
  danger: [0x645, 0x646, 0x637, 0x642, 0x647, 0x654, 0x20, 0x62E, 0x637, 0x631],
  dark: [0x62A, 0x6CC, 0x631, 0x647],
  role: [0x646, 0x642, 0x634],
  org: [0x633, 0x627, 0x632, 0x645, 0x627, 0x646],
  savedAt: [0x62F, 0x631, 0x20, 0x62D, 0x633, 0x627, 0x628, 0x20, 0x634, 0x645, 0x627, 0x20, 0x630, 0x62E, 0x6CC, 0x631, 0x647, 0x20, 0x634, 0x62F, 0x20, 0x28, 0x7B, 0x64, 0x7D, 0x29, 0x2E],
};
const F = (k) => String.fromCharCode(...FA[k]);

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

function installMock(role) {
  window.__requests = []; window.__role = role;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p + (opt && opt.body && typeof opt.body === 'string' ? ' ' + opt.body : ''));
    if (p === '/auth/me') return reply({ user: { name: 'Hamed B', email: 'owner@shop.test', role: window.__role },
      organization: { name: 'Toranj', slug: 'toranj', status: 'active' } });
    if (p === '/users/me/preferences' && method === 'GET') return reply({ language: 'en', theme: 'dark', font: null,
      notifications: { processing_failures: true, weekly_summary: false, ai_budget_warnings: true, security_alerts: true },
      usage_alert_threshold: 80, persisted: true, updated_at: '2026-10-30T10:00:00Z' });
    if (p === '/users/me/preferences' && method === 'PUT') return reply(Object.assign({ theme: 'dark', notifications: {}, persisted: true,
      updated_at: '2026-10-31T08:00:00Z', language: 'en' }, JSON.parse(opt.body)));
    if (p === '/organizations/me' && method === 'PATCH') return reply({ name: JSON.parse(opt.body).name, slug: 'toranj', status: 'active' });
    if (p === '/agent-network/memory-profiles' || p === '/agent-network/background-policies') return reply([]);
    return reply({ items: [], total: 0, limit: 100, offset: 0 });
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, timezoneId: 'UTC' });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(pageUrl);
  const settle = (ms) => page.waitForTimeout(ms || 250);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(400); };
  const requests = (re) => page.evaluate((r) => (window.__requests || []).filter((x) => new RegExp(r).test(x)), re);
  const shown = (sel) => page.evaluate((s) => Array.from(document.querySelectorAll(s)).map((e) => getComputedStyle(e).display !== 'none'), sel);
  const text = (id) => page.evaluate((i) => document.getElementById(i).textContent, id);
  const facts = (sel) => page.evaluate((s) => Array.from(document.querySelectorAll(s + ' dt')).map((d) => [d.textContent, d.nextElementSibling.textContent]), sel);

  // Sample mode.
  check('sample: self-profile (button + editor), font picker, billing card, factory reset (dt + dd) hidden as debt', await page.evaluate(() =>
    Array.from(document.querySelectorAll('#screen-settings [data-debt-hidden]')).map((e) => [e.getAttribute('data-debt-hidden'), getComputedStyle(e).display === 'none'])), [
    ['V5-settings-font-picker', true], ['V5-settings-self-profile', true], ['V5-settings-self-profile', true], ['V5-settings-billing-card', true],
    ['V5-settings-factory-reset', true], ['V5-settings-factory-reset', true]]);
  await lang('fa');
  check('fa (sample): Appearance and Danger zone titles', await page.evaluate(() => Array.from(document.querySelectorAll('#screen-settings .card__title'))
    .map((h) => h.textContent.trim()).filter((t) => t)).then((t) => [t.indexOf(F('appearance')) !== -1, t.indexOf(F('danger')) !== -1]), [true, true]);
  await lang('en');

  // Live, as an admin.
  await page.evaluate(installMock, 'admin');
  await connect();
  check('live: the settings cards stay; the generic panel steps aside', [await shown('#settings-preferences, #settings-shared-memory, #settings-bg-processing'),
    await shown('#live-screen-settings')], [[true, true, true], [false]]);
  check('Appearance: the saved theme and language', [await text('appearance-theme'), await text('appearance-lang')], ['Dark', 'English']);
  check('preferences: the last change', await text('pref-status'), 'Saved to your account (last change 30 Oct 2026, 10:00).');
  check('one GET /auth/me; the Account card', [await requests('^GET /auth/me$'), await facts('#account-kv')],
    [['GET /auth/me'], [['Name', 'Hamed B'], ['Email', 'owner@shop.test'], ['Role', 'Admin']]]);
  check('the Organization card', await facts('#settings-org'), [['Name', 'Toranj'], ['Slug', 'toranj'], ['Status', 'Active']]);
  await page.fill('#settings-org-name', 'Toranj Co');
  await page.evaluate(() => document.querySelector('.settings-org-form').requestSubmit()); await settle();
  check('rename: one PATCH; Saved.; the name updates', [await requests('^PATCH'), await text('settings-org-msg'), (await facts('#settings-org'))[0]],
    [['PATCH /organizations/me {"name":"Toranj Co"}'], 'Saved.', ['Name', 'Toranj Co']]);

  let before = (await requests('^PUT')).length;
  await page.click('#topbar-lang'); await settle();
  check('top-bar language: the page switches and the choice is saved', [await page.evaluate(() => document.documentElement.lang),
    (await requests('^PUT')).slice(before)], ['fa', ['PUT /users/me/preferences {"language":"fa"}']]);
  check('fa: Account role label and value, Organization title, Appearance theme, the preference status', [
    (await facts('#account-kv'))[2][0], await page.evaluate(() => document.querySelector('#settings-org .card__title').textContent),
    await text('appearance-theme'), await text('pref-status')],
    [F('role'), F('org'), F('dark'), F('savedAt').replace('{d}', await page.evaluate(() => AIOL_I18N.date('2026-10-31T08:00:00Z', 'datetime', 'fa')))]);
  before = (await requests('^PUT')).length;
  await page.click('#settings-reset'); await settle();
  check('Reset: this device only; nothing saved; the pickers (and the page language) back to defaults', [await text('settings-reset-msg'),
    (await requests('^PUT')).length - before, await page.evaluate(() => [document.getElementById('pick-lang').value, document.getElementById('pick-theme').value,
      document.documentElement.lang])], ['Reset on this device. The preferences saved to your account are unchanged.', 0, ['en', 'light', 'en']]);

  // A viewer may not rename.
  await page.evaluate(installMock, 'viewer');
  await connect();
  check('viewer: no rename form; the reason', [await page.evaluate(() => !!document.getElementById('settings-org-name')),
    await page.evaluate(() => document.querySelector('#settings-org .aic-hint').textContent)], [false, 'Only an owner or admin can rename the organization.']);

  // Log out.
  await Promise.all([page.waitForEvent('load'), page.click('#screen-settings [data-logout]')]); await settle();
  check('Log out: the login page, no token', await page.evaluate(() => [location.hash, window.AIOL_LIVE_STATE()]), ['#screen-login', null]);
  check('no page errors', errors, []);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
