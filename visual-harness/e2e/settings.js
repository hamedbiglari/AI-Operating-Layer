#!/usr/bin/env node
/*
 * Browser checks for the Settings screen (Step 13).
 *   Sample: Edit profile opens a panel that says to connect first (no
 *           verification sample); the font picker (V5-settings-font-picker), Plan & billing
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
 *           Edit profile: name and email with one PATCH /users/me, the Account
 *           card follows, 409 and empty-name messages (V5-settings-self-profile);
 *           Reset: not connected = this device only; connected = one PUT of the
 *           defaults first, then this device (V5-settings-reset-backend); Log out opens the
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
  editMine: [0x648, 0x6CC, 0x631, 0x627, 0x6CC, 0x634, 0x20, 0x646, 0x645, 0x627, 0x6CC, 0x647, 0x654, 0x20, 0x645, 0x646],
  resetDone: [0x628, 0x627, 0x632, 0x646, 0x634, 0x627, 0x646, 0x6CC, 0x20, 0x634, 0x62F, 0x2E, 0x20, 0x62A, 0x631, 0x62C, 0x6CC, 0x62D, 0x627, 0x62A, 0x20, 0x630, 0x62E, 0x6CC, 0x631, 0x647, 0x200C, 0x634, 0x62F, 0x647, 0x654, 0x20, 0x634, 0x645, 0x627, 0x20, 0x628, 0x647, 0x20, 0x67E, 0x6CC, 0x634, 0x200C, 0x641, 0x631, 0x636, 0x20, 0x628, 0x631, 0x6AF, 0x634, 0x62A, 0x2E],
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
    if (p === '/users/me' && method === 'PATCH') {
      const body = JSON.parse(opt.body);
      if (body.email && body.email.toLowerCase() === 'taken@shop.test') return reply({ error: { code: 'CONFLICT', message: 'Email is already registered' } }, 409);
      return reply({ name: body.name || 'Hamed B', email: (body.email || 'owner@shop.test').toLowerCase(), role: window.__role });
    }
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
  check('sample: font picker, billing card, factory reset (dt + dd) hidden as debt', await page.evaluate(() =>
    Array.from(document.querySelectorAll('#screen-settings [data-debt-hidden]')).map((e) => [e.getAttribute('data-debt-hidden'), getComputedStyle(e).display === 'none'])), [
    ['V5-settings-font-picker', true], ['V5-settings-billing-card', true], ['V5-settings-factory-reset', true], ['V5-settings-factory-reset', true]]);
  await page.evaluate(() => document.querySelector('[data-toggle-edit="me"]').click()); await settle();
  check('sample: Edit profile shows; its panel says to connect first and holds no verification sample', await page.evaluate(() => {
    const b = document.querySelector('[data-toggle-edit="me"]'), pnl = document.getElementById('edit-panel-me');
    return [getComputedStyle(b).display !== 'none', b.getAttribute('aria-expanded'), !pnl.hidden, pnl.querySelector('.profile-missing').textContent,
      pnl.querySelectorAll('input').length]; }), [true, 'true', true, 'Connect to AI Core to change your name or email address.', 0]);
  await page.evaluate(() => document.querySelector('[data-toggle-edit="me"]').click()); await settle();
  await page.click('#settings-reset'); await settle();
  check('sample: Reset without a connection is this device only', await text('settings-reset-msg'),
    'Reset on this device. The preferences saved to your account are unchanged.');
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
  // Edit profile (V5-settings-self-profile).
  await page.evaluate(() => document.querySelector('[data-toggle-edit="me"]').click()); await settle();
  check('Edit profile: the panel opens with the account name and email', await page.evaluate(() => [!document.getElementById('edit-panel-me').hidden,
    document.getElementById('profile-me-name').value, document.getElementById('profile-me-email').value]), [true, 'Hamed B', 'owner@shop.test']);
  const submitProfile = async (name, email) => { await page.fill('#profile-me-name', name); await page.fill('#profile-me-email', email);
    await page.evaluate(() => document.getElementById('profile-me-form').requestSubmit()); await settle(); };
  let pb = (await requests('^PATCH /users/me')).length;
  await submitProfile('Hamed B', 'owner@shop.test');
  check('nothing changed: nothing sent', [await text('profile-me-msg'), (await requests('^PATCH /users/me')).length - pb], ['Nothing to save.', 0]);
  await submitProfile('  ', 'owner@shop.test');
  check('an empty name is refused before sending', [await text('profile-me-msg'), (await requests('^PATCH /users/me')).length - pb], ['Enter your name.', 0]);
  await submitProfile('Hamed B', 'not-an-email');
  check('an invalid email is refused before sending', [await text('profile-me-msg'), (await requests('^PATCH /users/me')).length - pb], ['Enter a valid email address.', 0]);
  await submitProfile('Hamed Biglari', 'Hamed@Shop.test');
  check('save: one PATCH with only the changed fields; Saved.; the Account card follows', [(await requests('^PATCH /users/me')).slice(pb),
    await text('profile-me-msg'), await facts('#account-kv')], [['PATCH /users/me {"name":"Hamed Biglari","email":"Hamed@Shop.test"}'], 'Saved.',
    [['Name', 'Hamed Biglari'], ['Email', 'hamed@shop.test'], ['Role', 'Admin']]]);
  await submitProfile('Hamed Biglari', 'taken@shop.test');
  check('409: the address is taken; the Account card keeps the saved values', [await text('profile-me-msg'), (await facts('#account-kv'))[1]],
    ['That email address is already registered.', ['Email', 'hamed@shop.test']]);
  await lang('fa');
  check('fa: the editor title', await page.evaluate(() => document.querySelector('#edit-panel-me .card__title').textContent), F('editMine'));
  await lang('en');
  await page.evaluate(() => Array.from(document.querySelectorAll('#profile-me-form button')).find((b) => b.type === 'button').click()); await settle();
  check('Cancel closes the editor and restores the saved values', await page.evaluate(() => [document.getElementById('edit-panel-me').hidden,
    document.getElementById('profile-me-email').value]), [true, 'hamed@shop.test']);
  await page.fill('#settings-org-name', 'Toranj Co');
  await page.evaluate(() => document.querySelector('.settings-org-form').requestSubmit()); await settle();
  check('rename: one PATCH; Saved.; the name updates', [await requests('^PATCH /organizations'), await text('settings-org-msg'), (await facts('#settings-org'))[0]],
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
  check('Reset (connected): one PUT of the defaults, then the pickers (and the page language) back to defaults', [await text('settings-reset-msg'),
    (await requests('^PUT')).slice(before), await page.evaluate(() => [document.getElementById('pick-lang').value, document.getElementById('pick-theme').value,
      document.documentElement.lang]), await text('appearance-theme')], ['Reset. Your saved preferences are back to their defaults.',
    ['PUT /users/me/preferences {"language":"en","theme":"system","font":null,"notifications":{},"usage_alert_threshold":80}'], ['en', 'light', 'en'],
    'Same as the device']);
  await lang('fa');
  check('fa: the reset message', await text('settings-reset-msg'), F('resetDone'));
  await lang('en');

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
