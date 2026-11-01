#!/usr/bin/env node
/*
 * Browser checks for the website screens (Step 12B): blog, page sections and
 * newsletter subscribers (ADR-118 script, now translated).
 *   Live:   connecting reads GET /website/posts, /website/sections and
 *           /website/subscribers (one call each); blog rows (language and
 *           status labels, version, date); Edit reads the post and its
 *           revisions; Publish says when; a section toggle PATCHes and
 *           names the section; the subscriber count; Erase asks first, then
 *           DELETEs; a failed load shows the server's message; Persian over
 *           live content (headers, labels, the count, the confirm question)
 *           and each control's translated name.
 * Runs on file:// with AI Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/website.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-site-blog';
const fa = (...codes) => String.fromCharCode(...codes);
const iso = (s) => fa(0x2068) + s + fa(0x2069);
const D = (n) => String(n).replace(/[0-9]/g, (c) => fa(0x6F0 + Number(c)));
const FA = {
  title: [0x639, 0x646, 0x648, 0x627, 0x646],
  published: [0x645, 0x646, 0x62A, 0x634, 0x631, 0x634, 0x62F, 0x647],
  count: [0x7B, 0x6E, 0x7D, 0x20, 0x645, 0x634, 0x62A, 0x631, 0x6A9],
  show: [0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x7B, 0x6C, 0x61, 0x62, 0x65, 0x6C, 0x7D],
  hiding: [0x7B, 0x6C, 0x61, 0x62, 0x65, 0x6C, 0x7D, 0x20, 0x67E, 0x646, 0x647, 0x627, 0x646, 0x20, 0x645, 0x6CC, 0x200C, 0x634, 0x648, 0x62F, 0x2E],
  erase: [0x7B, 0x65, 0x6D, 0x61, 0x69, 0x6C, 0x7D, 0x20, 0x628, 0x647, 0x200C, 0x637, 0x648, 0x631, 0x20, 0x6A9, 0x627, 0x645, 0x644, 0x20, 0x67E, 0x627, 0x6A9, 0x20, 0x634, 0x648, 0x62F, 0x61F, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x6A9, 0x627, 0x631, 0x20, 0x628, 0x631, 0x6AF, 0x634, 0x62A, 0x200C, 0x67E, 0x630, 0x6CC, 0x631, 0x20, 0x646, 0x6CC, 0x633, 0x62A, 0x2E],
};
const F = (k) => String.fromCharCode(...FA[k]);

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const post = (id, lang, status, title, version, extra) => Object.assign({ id, lang, slug: id, title, excerpt: null, author_name: 'Hamed',
  status, published_at: status === 'published' ? '2026-10-19T09:00:00Z' : null, updated_at: '2026-10-20T09:00:00Z', created_at: '2026-10-01T09:00:00Z',
  version, tags: [], translation_group: null, body: 'Body text.', references: [] }, extra || {});
const DATA = {
  posts: [post('p1', 'en', 'published', 'Why indirect stays indirect', 2), post('p2', 'fa', 'draft', 'Saffron grading', 1)],
  revisions: [{ version: 1, note: 'First draft', changed_at: '2026-10-01T09:00:00Z' }],
  sections: [{ id: 's1', section_key: 'hero', label: 'Hero', heading: null, enabled: true, position: 0 },
    { id: 's2', section_key: 'products', label: 'Products', heading: 'Our range', enabled: true, position: 1 }],
  subscribers: [{ id: 'n1', email: 'reader@shop.test', status: 'subscribed', lang: 'fa', source: 'footer', consented_at: '2026-10-10T09:00:00Z' },
    { id: 'n2', email: 'gone@shop.test', status: 'unsubscribed', lang: 'en', source: 'blog', consented_at: '2026-09-01T09:00:00Z' }],
};

function installMock(data) {
  window.__requests = []; window.__data = data; window.__fail = null;
  const reply = (body, status) => Promise.resolve(new Response(body === null ? null : JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    const d = window.__data;
    if (window.__fail && p.indexOf(window.__fail) === 0) return reply({ error: { message: 'core offline' } }, 500);
    if (p === '/website/posts?limit=100') return reply({ items: d.posts, total: d.posts.length, limit: 100, offset: 0 });
    let m = p.match(/^\/website\/posts\/([^/]+)$/);
    if (m) return reply(d.posts.find((x) => x.id === m[1]));
    if (/^\/website\/posts\/[^/]+\/revisions$/.test(p)) return reply(d.revisions);
    m = p.match(/^\/website\/posts\/([^/]+)\/publish$/);
    if (m) { const x = d.posts.find((y) => y.id === m[1]); x.status = 'published'; x.published_at = '2026-10-30T09:00:00Z'; x.version += 1; return reply(x); }
    if (p === '/website/sections?page=home&lang=en') return reply(d.sections);
    m = p.match(/^\/website\/sections\/([^/]+)$/);
    if (m && method === 'PATCH') { const s = d.sections.find((y) => y.id === m[1]); Object.assign(s, JSON.parse(opt.body)); return reply(s); }
    if (p === '/website/subscribers?limit=100') return reply({ items: d.subscribers, total: d.subscribers.length, limit: 100, offset: 0 });
    m = p.match(/^\/website\/subscribers\/([^/]+)$/);
    if (m && method === 'DELETE') { d.subscribers = d.subscribers.filter((y) => y.id !== m[1]); return reply(null, 204); }
    return reply({ detail: 'Not found' }, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, timezoneId: 'UTC' });
  const errors = [], dialogs = []; let answer = true;
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('dialog', async (d) => { dialogs.push(d.message()); if (answer) await d.accept(); else await d.dismiss(); });
  await page.goto(pageUrl);
  const settle = (ms) => page.waitForTimeout(ms || 200);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(300); };
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /\/website\//.test(r)));
  const rows = (id) => page.evaluate((i) => Array.from(document.querySelectorAll('#' + i + ' tbody tr')).map((tr) => Array.from(tr.cells).map((td) => td.textContent)), id);
  const heads = (id) => page.evaluate((i) => Array.from(document.querySelectorAll('#' + i + ' thead th')).map((th) => th.textContent), id);
  const text = (id) => page.evaluate((i) => document.getElementById(i).textContent, id);
  const nameOf = (sel) => page.evaluate((s) => { const n = document.querySelector(s); return document.getElementById(n.getAttribute('aria-labelledby')).textContent; }, sel);

  await page.evaluate(installMock, DATA);
  await connect();
  check('connect: posts, sections and subscribers, one call each', await requests(),
    ['GET /website/posts?limit=100', 'GET /website/sections?page=home&lang=en', 'GET /website/subscribers?limit=100']);
  check('blog: headers and rows (language, status, version, date)', [await heads('wb-list'), await rows('wb-list')], [
    ['Title', 'Language', 'Status', 'Version', 'Updated', ''],
    [['Why indirect stays indirect', 'English', 'Published', 'v2', '20 Oct 2026', 'Edit'], ['Saffron grading', 'Persian', 'Draft', 'v1', '20 Oct 2026', 'Edit']]]);

  let before = (await requests()).length;
  await page.evaluate(() => document.querySelector('#wb-list tbody tr:nth-child(2) button').click()); await settle(300);
  check('Edit: the post and its history', [(await requests()).slice(before), await text('wb-form-title'), await rows('wb-history')],
    [['GET /website/posts/p2', 'GET /website/posts/p2/revisions'], 'Edit: ' + iso('Saffron grading'), [['v1', 'First draft', '1 Oct 2026, 09:00']]]);
  await page.click('#wb-publish'); await settle(300);
  check('Publish: when it was published', await text('wb-msg'), 'Published on 30 Oct 2026.');

  check('sections: rows; the hero cannot be hidden; each control named', [(await rows('ws-list')).map((r) => [r[0], r[1]]),
    await page.evaluate(() => document.querySelector('#ws-list tbody tr:first-child input[type=checkbox]').disabled),
    await nameOf('#ws-list tbody tr:nth-child(2) input[type=checkbox]')], [[['1', 'Hero'], ['2', 'Products']], true, 'Show ' + iso('Products')]);
  before = (await requests()).length;
  await page.evaluate(() => document.querySelector('#ws-list tbody tr:nth-child(2) input[type=checkbox]').click()); await settle();
  check('section toggle: one PATCH; the message names it', [(await requests()).slice(before), await text('ws-msg')],
    [['PATCH /website/sections/s2'], 'Hiding ' + iso('Products') + '.']);

  check('subscribers: the count and rows', [await text('wn-total'), (await rows('wn-list')).map((r) => r.slice(0, 5))],
    ['2 subscribers', [['reader@shop.test', 'Subscribed', 'Persian', 'footer', '10 Oct 2026'], ['gone@shop.test', 'Unsubscribed', 'English', 'blog', '1 Sept 2026']]]);
  answer = false;
  await page.evaluate(() => Array.from(document.querySelectorAll('#wn-list tbody tr:first-child button')).find((b) => b.textContent === 'Erase').click()); await settle();
  check('Erase asks first; cancelling sends nothing', [dialogs.slice(-1)[0], (await requests()).filter((r) => r.indexOf('DELETE') === 0)],
    ['Erase ' + iso('reader@shop.test') + ' completely? This cannot be undone.', []]);
  answer = true;
  await page.evaluate(() => Array.from(document.querySelectorAll('#wn-list tbody tr:first-child button')).find((b) => b.textContent === 'Erase').click()); await settle(300);
  check('Erase: one DELETE; Erased.; the count drops', [(await requests()).filter((r) => r.indexOf('DELETE') === 0), await text('wn-msg'), await text('wn-total')],
    [['DELETE /website/subscribers/n1'], 'Erased.', '1 subscriber']);

  // Persian over live content.
  await lang('fa');
  check('fa: blog header and status label; subscriber count', [(await heads('wb-list'))[0], (await rows('wb-list'))[0][2], await text('wn-total')],
    [F('title'), F('published'), F('count').replace('{n}', D(1))]);
  check('fa: the section control name and the toggle message', [await nameOf('#ws-list tbody tr:nth-child(2) input[type=checkbox]'), await text('ws-msg')],
    [F('show').replace('{label}', iso('Products')), F('hiding').replace('{label}', iso('Products'))]);
  answer = false;
  await page.evaluate(() => document.querySelector('#wn-list tbody tr:first-child button:last-of-type').click()); await settle();
  check('fa: the Erase question', dialogs.slice(-1)[0], F('erase').replace('{email}', iso('gone@shop.test')));
  answer = true;
  await lang('en');
  check('back to English', (await heads('wb-list'))[0], 'Title');

  // A failed load.
  await page.evaluate(() => { window.__fail = '/website/posts'; });
  await page.click('#wb-refresh'); await settle();
  check('500: the server message', await text('wb-msg'), iso('core offline'));
  check('no page errors', errors, []);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
