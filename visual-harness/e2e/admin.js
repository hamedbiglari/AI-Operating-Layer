#!/usr/bin/env node
/*
 * Browser checks for the admin screens (Step 14A/14C).
 *   Sample: the five sample user pages are one template
 *           (#screen-admin-user-detail); Organizations exists; billing
 *           (Plan and Wallet columns, the AI spend stat, the billing nav)
 *           and the trash are hidden as debt (V5-admin-billing,
 *           V5-admin-trash).
 *   Live:   an organization admin (is_platform_admin false) reads GET /users
 *           and never calls /admin; the platform-only nav is hidden; the
 *           overview says only platform admins can see it; a user opens in
 *           the template from GET /users/{id}. A platform admin reads
 *           GET /admin/users (with the organization column and a
 *           server-side search), the detail from GET /admin/users/{id}, the
 *           overview and the organizations; a 403 from /admin is reported;
 *           Persian over live content. Grants (V5-admin-grant): Make admin
 *           POSTs /admin/grant {user_id}, Revoke asks and DELETEs
 *           /admin/grant/{id}, a platform admin's own row has no Revoke,
 *           Grant admin... prompts for an email, an unknown one is reported.
 * Runs on file:// with AI Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/admin.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-admin-users';
const fa = (...codes) => String.fromCharCode(...codes);
const iso = (s) => fa(0x2068) + s + fa(0x2069);
const D = (n) => String(n).replace(/[0-9]/g, (c) => fa(0x6F0 + Number(c)));
const FA = {
  onlyPlatform: [0x641, 0x642, 0x637, 0x20, 0x645, 0x62F, 0x6CC, 0x631, 0x627, 0x646, 0x20, 0x67E, 0x644, 0x62A, 0x641, 0x631, 0x645, 0x20, 0x645, 0x6CC, 0x200C, 0x62A, 0x648, 0x627, 0x646, 0x646, 0x62F, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x635, 0x641, 0x62D, 0x647, 0x20, 0x631, 0x627, 0x20, 0x628, 0x628, 0x6CC, 0x646, 0x646, 0x62F, 0x2E],
  yourUsers: [0x6A9, 0x627, 0x631, 0x628, 0x631, 0x627, 0x646, 0x20, 0x633, 0x627, 0x632, 0x645, 0x627, 0x646, 0x20, 0x634, 0x645, 0x627, 0x3A, 0x20, 0x7B, 0x6E, 0x7D, 0x20, 0x6A9, 0x627, 0x631, 0x628, 0x631, 0x2E],
  orgs: [0x633, 0x627, 0x632, 0x645, 0x627, 0x646, 0x200C, 0x647, 0x627],
  joined: [0x67E, 0x6CC, 0x648, 0x633, 0x62A, 0x646],
  active: [0x7B, 0x6E, 0x7D, 0x20, 0x641, 0x639, 0x627, 0x644],
};
const F = (k) => String.fromCharCode(...FA[k]);

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const user = (id, name, email, role, status, org) => ({ id, name, email, role, status, organization_id: 'o-' + org,
  organization_name: org, created_at: '2026-09-01T09:00:00Z', updated_at: '2026-10-01T09:00:00Z' });
const MINE = [Object.assign(user('u-1', 'Hamed B', 'owner@shop.test', 'owner', 'active', 'Alpha'), { is_platform_admin: true }),
  user('u-2', 'Vic', 'vic@shop.test', 'viewer', 'invited', 'Alpha')];
const ALL = MINE.concat([user('u-3', 'Bea', 'bea@beta.test', 'editor', 'suspended', 'Beta')]);

function installMock(me) {
  window.__requests = []; window.__me = me; window.__denied = false;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  const page = (items, total) => reply({ items, total: total === undefined ? items.length : total, limit: 50, offset: 0 });
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p + (opt && opt.body ? ' ' + opt.body : ''));
    if (p === '/admin/grant' && method === 'POST') {
      const body = JSON.parse(opt.body), x = window.__all.find((y) => y.id === body.user_id || y.email === body.email);
      if (!x) return reply({ error: { message: 'User not found.' } }, 404);
      x.is_platform_admin = true; return reply(x);
    }
    let g = p.match(/^\/admin\/grant\/([^/]+)$/);
    if (g && method === 'DELETE') {
      if (g[1] === 'u-1') return reply({ error: { message: 'own' } }, 409);
      window.__all.find((y) => y.id === g[1]).is_platform_admin = false; return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (p === '/auth/me') return reply({ user: { id: 'u-1', name: 'Hamed B', email: 'owner@shop.test', role: window.__me.role },
      organization: { name: 'Alpha', slug: 'alpha', status: 'active' }, is_platform_admin: window.__me.platform });
    if (p.indexOf('/admin/') === 0 && window.__denied) return reply({ error: { message: 'Platform administrators only' } }, 403);
    if (p === '/users?limit=50&offset=0') return page(window.__users || []);
    let m = p.match(/^\/users\/([^/?]+)$/);
    if (m) { const x = (window.__users || []).find((y) => y.id === m[1]); return x ? reply(x) : reply({ detail: 'nope' }, 404); }
    m = p.match(/^\/admin\/users\?limit=50&offset=0(&q=(.*))?$/);
    if (m) { const q = m[2] ? decodeURIComponent(m[2]).toLowerCase() : ''; const items = window.__all.filter((x) => !q || (x.email + x.name + x.organization_name).toLowerCase().indexOf(q) !== -1); return page(items); }
    m = p.match(/^\/admin\/users\/([^/?]+)$/);
    if (m) return reply(window.__all.find((y) => y.id === m[1]));
    if (p === '/admin/overview') return reply({ organizations: { total: 12, active: 10 }, users: { total: 40, active: 25 },
      failed_sync_jobs_24h: 2, failed_ai_jobs_24h: 1, as_of: '2026-10-31T10:00:00Z' });
    if (p === '/admin/organizations?limit=50&offset=0') return page([{ id: 'o-Alpha', name: 'Alpha', slug: 'alpha', status: 'active', user_count: 2,
      created_at: '2026-08-01T09:00:00Z', updated_at: '2026-08-01T09:00:00Z' }, { id: 'o-Beta', name: 'Beta', slug: 'beta', status: 'suspended', user_count: 1,
      created_at: '2026-08-02T09:00:00Z', updated_at: '2026-08-02T09:00:00Z' }]);
    return reply({ items: [], total: 0, limit: 50, offset: 0 });
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, timezoneId: 'UTC' });
  const errors = [], dialogs = []; let answer = null;
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('dialog', async (d) => { dialogs.push(d.message()); if (answer === false) await d.dismiss(); else await d.accept(typeof answer === 'string' ? answer : undefined); });
  await page.goto(pageUrl);
  const settle = (ms) => page.waitForTimeout(ms || 300);
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await settle(); };
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(500); };
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /^GET \/(users(?!\/me)|admin)/.test(r)));
  const view = (id) => page.evaluate((i) => {
    const s = document.getElementById(i), body = s.querySelector(':scope > .vis-live');
    if (!body) return null;
    const box = body.querySelector(':scope > .know-status'), card = body.querySelector(':scope > .card');
    return { state: box.dataset.state, message: box.querySelector('p').textContent, cardShown: !card.hidden,
      note: (card.querySelector('.vis-note') || {}).textContent || null,
      heads: Array.from(card.querySelectorAll('thead th')).map((t) => t.textContent),
      rows: Array.from(card.querySelectorAll('tbody tr')).map((tr) => Array.from(tr.cells).map((td) => td.textContent)),
      facts: Array.from(card.querySelectorAll('dt')).map((d) => [d.textContent, d.nextElementSibling.textContent]),
      stats: Array.from(card.querySelectorAll('.stat')).map((x) => Array.from(x.children).map((c) => c.textContent)),
      search: (body.querySelector('.prod-bar') || {}).hidden };
  }, id);
  const navShown = () => page.evaluate(() => Array.from(document.querySelectorAll('[data-platform-only]')).map((a) => getComputedStyle(a).display !== 'none'));

  // Sample mode.
  check('sample: one user template and an Organizations screen; the five sample pages are gone', await page.evaluate(() => [
    !!document.getElementById('screen-admin-user-detail'), !!document.getElementById('screen-admin-orgs'),
    document.querySelectorAll('[id^="screen-admin-user-u"]').length]), [true, true, 0]);
  check('sample: billing (Plan, Wallet, AI spend, billing nav) and the trash hidden as debt', await page.evaluate(() => [
    Array.from(document.querySelectorAll('[data-debt-hidden="V5-admin-billing"]')).every((e) => getComputedStyle(e).display === 'none'),
    document.querySelectorAll('#screen-admin-users [data-debt-hidden="V5-admin-billing"]').length,
    getComputedStyle(document.getElementById('admin-trash')).display]), [true, 12, 'none']);
  check('sample: the platform-only nav is shown', await navShown(), [true, true]);

  // An organization admin.
  await page.evaluate(installMock, { role: 'owner', platform: false });
  await page.evaluate((u) => { window.__users = u; }, MINE);
  await connect();
  let v = await view('screen-admin-users');
  check('org admin: GET /users only, never /admin', await requests(), ['GET /users?limit=50&offset=0']);
  check('org admin: the users of the organization, no Organization column, no search', [v.note, v.heads, v.rows, v.search],
    ['Users of your organization: 2 users.', ['Name', 'Email', 'Role', 'Status', 'Joined'],
      [['Hamed B', 'owner@shop.test', 'Owner', 'Active', '1 Sept 2026'], ['Vic', 'vic@shop.test', 'Viewer', 'Invited', '1 Sept 2026']], true]);
  check('org admin: the platform-only nav is hidden', await navShown(), [false, false]);
  await go('#screen-admin-overview');
  v = await view('screen-admin-overview');
  check('org admin: the overview says who may see it; nothing requested', [v.state, v.message, v.cardShown, (await requests()).filter((r) => r.indexOf('/admin') !== -1)],
    ['empty', 'Only platform administrators can see this screen.', false, []]);
  await go('#screen-admin-users');
  let before = (await requests()).length;
  await page.evaluate(() => document.querySelector('#screen-admin-users .vis-live tbody tr:nth-child(2) a').click()); await settle();
  v = await view('screen-admin-user-detail');
  check('org admin: a user opens in the template from GET /users/{id}', [(await requests()).slice(before).filter((r) => r.indexOf('/users/') !== -1), v.facts],
    [['GET /users/u-2'], [['Name', 'Vic'], ['Email', 'vic@shop.test'], ['Role', 'Viewer'], ['Status', 'Invited'], ['Joined', '1 Sept 2026']]]);
  await lang('fa');
  await go('#screen-admin-overview');
  check('fa: the overview message', (await view('screen-admin-overview')).message, F('onlyPlatform'));
  await go('#screen-admin-users');
  v = await view('screen-admin-users');
  check('fa: the users note and the Joined column', [v.note, v.heads[4]], [F('yourUsers').replace('{n}', D(2)), F('joined')]);
  await lang('en');

  // A platform admin.
  await page.evaluate(installMock, { role: 'owner', platform: true });
  await page.evaluate((a) => { window.__all = a; }, ALL);
  await go('#screen-admin-user-detail');
  await connect();
  check('platform admin: /admin/users, /admin/overview, /admin/organizations once each; never /users', (await requests()).sort(),
    ['GET /admin/organizations?limit=50&offset=0', 'GET /admin/overview', 'GET /admin/users?limit=50&offset=0']);
  await go('#screen-admin-users');
  v = await view('screen-admin-users');
  check('platform admin: every user, with the organization and the admin column; search shown', [v.note, v.heads, v.rows[2], v.rows[0][6], v.search],
    ['Every user on the platform: 3 users.', ['Name', 'Email', 'Organization', 'Role', 'Status', 'Joined', 'Platform admin'],
      ['Bea', 'bea@beta.test', 'Beta', 'Editor', 'Suspended', '1 Sept 2026', 'Make admin'], 'Platform admin', false]);
  check('platform admin: the platform-only nav is shown', await navShown(), [true, true]);
  before = (await requests()).length;
  await page.fill('#admin-users-q', 'beta'); await page.dispatchEvent('#admin-users-q', 'change'); await settle();
  check('search: server-side, one request', [(await requests()).slice(before), (await view('screen-admin-users')).rows.map((r) => r[0])],
    [['GET /admin/users?limit=50&offset=0&q=beta'], ['Bea']]);
  // Grants (V5-admin-grant): the list is filtered to Bea here.
  const writes = () => page.evaluate(() => window.__requests.filter((r) => /^(POST|DELETE) /.test(r)));
  const usersMsg = () => page.evaluate(() => document.querySelector('#screen-admin-users .vis-live > .know-status p').textContent);
  await page.evaluate(() => Array.from(document.querySelectorAll('#screen-admin-users .vis-live tbody button')).find((b) => b.textContent === 'Make admin').click()); await settle();
  check('Make admin: one POST with the user id; the list re-read; the message', [await writes(), (await view('screen-admin-users')).rows[0][6], await usersMsg()],
    [['POST /admin/grant {"user_id":"u-3"}'], 'Platform adminRevoke', 'Platform admin granted to ' + iso('bea@beta.test') + '.']);
  answer = true;
  await page.evaluate(() => Array.from(document.querySelectorAll('#screen-admin-users .vis-live tbody button')).find((b) => b.textContent === 'Revoke').click()); await settle();
  check('Revoke: asks, then one DELETE; the message', [dialogs.slice(-1)[0], (await writes()).slice(-1), await usersMsg()],
    ['Revoke platform admin from ' + iso('bea@beta.test') + '?', ['DELETE /admin/grant/u-3'], 'Platform admin revoked from ' + iso('bea@beta.test') + '.']);
  answer = 'nobody@example.test';
  await page.evaluate(() => document.getElementById('admin-grant').click()); await settle();
  check('Grant admin...: prompts, POSTs the email; an unknown one is reported', [(await writes()).slice(-1), await usersMsg()],
    [['POST /admin/grant {"email":"nobody@example.test"}'], 'No user or platform admin matches that.']);
  answer = null;
  await page.evaluate(() => document.querySelector('#screen-admin-users .vis-live tbody a').click()); await settle();
  check('platform admin: the detail from /admin/users/{id}, with the organization', (await view('screen-admin-user-detail')).facts,
    [['Name', 'Bea'], ['Email', 'bea@beta.test'], ['Organization', 'Beta'], ['Role', 'Editor'], ['Status', 'Suspended'], ['Joined', '1 Sept 2026']]);
  await go('#screen-admin-overview');
  check('overview: the platform counts', (await view('screen-admin-overview')).stats, [
    ['Organizations', '12', '10 active'], ['Users', '40'], ['Active users (30d)', '25', 'With recorded activity in the last 30 days'],
    ['Failed jobs (24h)', '3', 'Sync 2 ' + fa(0xB7) + ' AI 1']]);
  await go('#screen-admin-orgs');
  v = await view('screen-admin-orgs');
  check('organizations: rows (name, slug, status, users, created)', [v.note, v.rows],
    ['2 organizations on the platform.', [['Alpha', 'alpha', 'Active', '2', '1 Aug 2026'], ['Beta', 'beta', 'Suspended', '1', '2 Aug 2026']]]);
  await lang('fa');
  check('fa: the Organizations card and an active count', [await page.evaluate(() => document.querySelector('#screen-admin-orgs .vis-live .card__title').textContent),
    (await go('#screen-admin-overview'), (await view('screen-admin-overview')).stats[0][2])], [F('orgs'), F('active').replace('{n}', D(10))]);
  await lang('en');

  // The server refuses (a revoked grant): the screen says so.
  await page.evaluate(() => { window.__denied = true; });
  await go('#screen-admin-orgs'); await go('#screen-admin-users');
  v = await view('screen-admin-users');
  check('403 from /admin: the error is shown', [v.state, v.message], ['error', 'Could not load the users (' + iso('Permission denied (HTTP 403)') + ').']);
  check('no page errors', errors, []);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
