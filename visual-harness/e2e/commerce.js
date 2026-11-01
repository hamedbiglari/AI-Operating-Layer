#!/usr/bin/env node
/*
 * Browser checks for the Products screen (Step 11).
 *   Sample: the Offers and Availability columns (V5-products-offer-summary)
 *           are hidden as debt; the search toolbar shows and filters the
 *           sample rows; New product opens a card that says to connect first.
 *   New product (V5-products-create-ui): connected, the slug follows the
 *           name; one POST /products with only the filled fields; the list
 *           reloads; empty name, 409 and 403 each say why.
 *   Search (V5-products-search): connected, typing asks the server once
 *           (&search=, back to the first page); no match says so.
 *   Live:   GET /products (one call, sorted by name, 50 per page); the
 *           status filter and the pager are server-side; a row opens from
 *           the loaded list and reads that product's offers (one call);
 *           unknown values shown as sent; no products; no offers; 500 with
 *           Retry; Persian over live content.
 * Runs on file:// with AI Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/commerce.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-products';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069);
const iso = (s) => FSI + s + PDI, EN = fa(0x2013);
const FA = {
  products: [0x645, 0x62D, 0x635, 0x648, 0x644, 0x627, 0x62A],
  published: [0x645, 0x646, 0x62A, 0x634, 0x631, 0x634, 0x62F, 0x647],
  draft: [0x67E, 0x6CC, 0x634, 0x200C, 0x646, 0x648, 0x6CC, 0x633],
  notLinked: [0x67E, 0x6CC, 0x648, 0x646, 0x62F, 0x20, 0x646, 0x634, 0x62F, 0x647],
  inStock: [0x645, 0x648, 0x62C, 0x648, 0x62F],
  origin: [0x62E, 0x627, 0x633, 0x62A, 0x6AF, 0x627, 0x647],
  offers: [0x67E, 0x6CC, 0x634, 0x646, 0x647, 0x627, 0x62F, 0x647, 0x627, 0x6CC, 0x20, 0x641, 0x631, 0x648, 0x634],
  condNew: [0x62C, 0x62F, 0x6CC, 0x62F],
  note: [0x7B, 0x66, 0x72, 0x6F, 0x6D, 0x7D, 0x2013, 0x7B, 0x74, 0x6F, 0x7D, 0x20, 0x627, 0x632, 0x20, 0x7B, 0x74, 0x6F, 0x74, 0x61, 0x6C, 0x7D, 0x20, 0x645, 0x62D, 0x635, 0x648, 0x644, 0x2E],
};
const F = (k) => String.fromCharCode(...FA[k]);
const D = (n) => String(n).replace(/[0-9]/g, (c) => fa(0x6F0 + Number(c)));

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const product = (id, name, sku, status, extra) => Object.assign({ id, organization_id: 'org', site_id: null, external_id: null, sku, name,
  slug: id, description: null, brand: null, category: null, origin: null, ingredients: {}, specifications: {}, certifications: {},
  images: {}, shipping: {}, returns_policy: null, status, provenance: 'merchant', knowledge_object_id: null,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-25T10:00:00Z' }, extra || {});
const DATA = {
  products: [
    product('p1', 'Saffron Negin 5g', 'SAF-5', 'published', { brand: 'Toranj', category: 'Spices', origin: 'Qaenat', knowledge_object_id: 'ko1',
      description: 'Hand-picked threads.', provenance: 'woocommerce' }),
    product('p2', 'Garlic oil', null, 'odd_status'),
  ],
  total: 120,
  offers: { p1: [{ id: 'o1', product_id: 'p1', price: 12.5, currency: 'EUR', availability: 'in_stock', stock_quantity: 40, condition: 'new' },
    { id: 'o2', product_id: 'p1', price: null, currency: null, availability: 'odd_av', stock_quantity: null, condition: 'odd_cond' }], p2: [] },
};

function installMock(data) {
  window.__requests = []; window.__data = data; window.__fail = null;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p + (method === 'POST' && opt && opt.body ? ' ' + opt.body : ''));
    if (p === '/products' && method === 'POST') {
      const body = JSON.parse(opt.body);
      if (window.__role === 'viewer') return reply({ error: { message: 'Insufficient role' } }, 403);
      if (body.slug === 'taken') return reply({ error: { code: 'CONFLICT', message: 'Duplicate slug' } }, 409);
      return reply(Object.assign({ id: 'new1', status: 'draft' }, body), 201);
    }
    if (window.__fail && p.indexOf(window.__fail) === 0) return reply({}, 500);
    const d = window.__data;
    let m = p.match(/^\/products\?limit=50&offset=(\d+)&sort_by=name&sort_dir=asc(&status=(\w+))?(&search=([^&]+))?$/);
    if (m) {
      const q = m[5] ? decodeURIComponent(m[5]).toLowerCase() : '';
      let items = m[3] ? d.products.filter((x) => x.status === m[3]) : d.products;
      if (q) items = items.filter((x) => (x.name + ' ' + (x.sku || '')).toLowerCase().indexOf(q) !== -1);
      return reply({ items, total: m[3] || q ? items.length : d.total, limit: 50, offset: Number(m[1]) });
    }
    m = p.match(/^\/products\/([^/]+)\/offers\?limit=200$/);
    if (m) { const items = d.offers[m[1]] || []; return reply({ items, total: items.length, limit: 200, offset: 0 }); }
    return reply({ detail: 'Not found' }, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(pageUrl);
  const settle = (ms) => page.waitForTimeout(ms || 150);
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await settle(); };
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /^GET \/products/.test(r)));
  const shown = (sel) => page.evaluate((s) => Array.from(document.querySelectorAll(s)).map((e) => getComputedStyle(e).display !== 'none'), sel);
  const view = () => page.evaluate(() => {
    const s = document.getElementById('screen-products'), body = s.querySelector(':scope > .vis-live');
    if (!body) return null;
    const box = body.querySelector(':scope > .know-status'), act = box.querySelector('button'), card = body.querySelector(':scope > .card:not(.vis-detail)');
    return {
      title: card.hidden ? null : card.querySelector('.card__title').textContent,
      note: card.hidden ? null : card.querySelector('.vis-note').textContent,
      rows: card.hidden ? null : Array.from(card.querySelectorAll('tbody tr')).map((tr) => Array.from(tr.cells).map((td) => td.textContent)),
      links: card.hidden ? null : Array.from(card.querySelectorAll('tbody a')).map((a) => a.getAttribute('href')),
      pager: Array.from(card.querySelectorAll('.live-pager button')).map((b) => [b.textContent, b.disabled]),
      state: box.dataset.state, message: box.querySelector('p').textContent, action: act && !act.hidden ? act.textContent : null,
      sampleShown: Array.from(s.children).some((c) => !c.hasAttribute('data-live-keep') && !c.classList.contains('live-panel')
        && !c.classList.contains('page-header') && getComputedStyle(c).display !== 'none'),
    };
  });
  const detail = () => page.evaluate(() => {
    const d = document.getElementById('prod-detail');
    if (!d || d.hidden) return null;
    return { title: d.querySelector('.card__title').textContent,
      facts: Array.from(d.querySelectorAll('dt')).map((dt) => [dt.textContent, dt.nextElementSibling.textContent]),
      description: (d.querySelector('.vis-answer') || {}).textContent || null,
      offersNote: d.querySelector('.vis-note').textContent,
      offers: Array.from(d.querySelectorAll('tbody tr')).map((tr) => Array.from(tr.cells).map((td) => td.textContent)),
      focused: document.activeElement === d };
  });

  // Sample mode.
  check('sample: Offers + Availability (3 rows + header) and New product hidden as debt; no search debt left',
    [(await shown('#screen-products [data-debt-hidden="V5-products-offer-summary"]')).filter((x) => !x).length,
      await shown('#screen-products [data-debt-hidden="V5-products-search"]'), await shown('#screen-products [data-debt-hidden="V5-products-create-ui"]')],
    [8, [], []]);
  const sampleRows = () => page.evaluate(() => Array.from(document.querySelectorAll('#screen-products .table-wrap tbody tr'))
    .filter((tr) => !tr.hidden).map((tr) => tr.cells[0].textContent.trim()));
  const allSample = await sampleRows();
  const firstWord = allSample[0].split(/\s+/)[0];
  await page.fill('#screen-products .toolbar input[type=search]', firstWord.toUpperCase()); await settle();
  const filtered = await sampleRows();
  check('sample: the toolbar filters the sample rows (case-insensitive)', [filtered.length >= 1, filtered.length < allSample.length,
    filtered.every((t) => t.toLowerCase().indexOf(firstWord.toLowerCase()) !== -1)], [true, true, true]);
  await page.fill('#screen-products .toolbar input[type=search]', ''); await settle();
  check('sample: clearing the search shows every row again', (await sampleRows()).length, allSample.length);
  await page.evaluate(() => document.getElementById('prod-new').click()); await settle();
  check('sample: New product opens a card that says to connect first; no form yet', await page.evaluate(() => {
    const c = document.getElementById('prod-new-card');
    return [!c.hidden, document.getElementById('prod-new').getAttribute('aria-expanded'), c.querySelector('.profile-missing').textContent,
      document.getElementById('prod-new-form').hidden]; }), [true, 'true', 'Connect to AI Core to add a product.', true]);
  await page.evaluate(() => document.getElementById('prod-new').click()); await settle();

  // Live.
  await page.evaluate(installMock, DATA);
  await connect();
  check('connect: one list request', await requests(), ['GET /products?limit=50&offset=0&sort_by=name&sort_dir=asc']);
  // New product (V5-products-create-ui).
  const posts = () => page.evaluate(() => window.__requests.filter((r) => /^POST \/products/.test(r)));
  const msg = () => page.evaluate(() => document.getElementById('prod-new-msg').textContent);
  const submitNew = () => page.evaluate(() => document.getElementById('prod-new-form').requestSubmit());
  await page.evaluate(() => document.getElementById('prod-new').click()); await settle();
  check('live: the form replaces the connect note', await page.evaluate(() => [document.querySelector('#prod-new-card .profile-missing').hidden,
    document.getElementById('prod-new-form').hidden]), [true, false]);
  await submitNew(); await settle();
  check('empty name: refused before sending', [await msg(), (await posts()).length], ['Enter a name.', 0]);
  await page.fill('#prod-new-name', 'Rose Water 250ml');
  check('the slug follows the name', await page.inputValue('#prod-new-slug'), 'rose-water-250ml');
  await page.fill('#prod-new-sku', 'RW-250');
  let before = (await requests()).length;
  await submitNew(); await settle(400);
  check('create: one POST with only the filled fields; Created as Draft; the list reloads', [await posts(), await msg(), (await requests()).slice(before)],
    [['POST /products {"name":"Rose Water 250ml","slug":"rose-water-250ml","sku":"RW-250"}'], 'Created ' + iso('Rose Water 250ml') + ' as Draft.',
      ['GET /products?limit=50&offset=0&sort_by=name&sort_dir=asc']]);
  check('create: the form is cleared for the next product', await page.inputValue('#prod-new-name'), '');
  await page.fill('#prod-new-name', 'Duplicate'); await page.fill('#prod-new-slug', 'taken');
  await submitNew(); await settle();
  check('409: the slug or SKU is taken', await msg(), 'A product with this slug or SKU already exists.');
  await page.evaluate(() => { window.__role = 'viewer'; });
  await page.fill('#prod-new-slug', 'other');
  await submitNew(); await settle();
  check('403: the role is named', await msg(), 'Your role cannot add products (owner, admin or editor only).');
  await page.evaluate(() => { window.__role = 'admin'; Array.from(document.querySelectorAll('#prod-new-form button')).find((x) => x.type === 'button').click(); }); await settle();
  check('Cancel closes the card', await page.evaluate(() => document.getElementById('prod-new-card').hidden), true);
  let v = await view();
  check('list: note, rows (name + SKU, category, origin, knowledge, status), unknown status as sent', [v.title, v.note, v.rows],
    ['Products', '1' + EN + '2 of 120 products.', [
      ['Saffron Negin 5gSAF-5', 'Spices', 'Qaenat', 'Linked', 'Published', 'Open'],
      ['Garlic oil', 'Not set', 'Not set', 'Not linked', 'odd_status', 'Open']]]);
  check('list: the knowledge link; sample hidden; pager', [v.links, v.sampleShown, v.pager],
    [['#screen-knowledge-detail?id=ko1'], false, [['Previous', true], ['Next', false]]]);

  before = (await requests()).length;
  await page.click('#screen-products tbody tr:first-child button'); await settle();
  let d = await detail();
  check('open: one offers request for that product', (await requests()).slice(before), ['GET /products/p1/offers?limit=200']);
  check('open: facts, description, focus', [d.title, d.facts.slice(0, 7), d.description, d.focused], ['Saffron Negin 5g',
    [['SKU', 'SAF-5'], ['Brand', 'Toranj'], ['Category', 'Spices'], ['Origin', 'Qaenat'], ['Status', 'Published'], ['Source', 'WooCommerce sync'],
      ['Knowledge', 'Linked']], 'Hand-picked threads.', true]);
  check('open: offers (price + currency, availability, stock, condition; unknowns as sent)', [d.offersNote, d.offers],
    ['', [['12.5 ' + iso('EUR'), 'In stock', '40', 'New'], ['Not set', 'odd_av', 'Not tracked', 'odd_cond']]]);
  await page.click('#screen-products tbody tr:nth-child(2) button'); await settle();
  d = await detail();
  check('open: no offers', [d.title, d.facts[0], d.description, d.offersNote, d.offers],
    ['Garlic oil', ['SKU', 'Not set'], null, 'No offers yet. A product can be fully described with no offer.', []]);

  before = (await requests()).length;
  await page.click('#screen-products .live-pager button:last-child'); await settle();
  check('Next: the next page from the server', (await requests()).slice(before), ['GET /products?limit=50&offset=50&sort_by=name&sort_dir=asc']);
  before = (await requests()).length;
  await page.selectOption('#prod-status', 'published'); await settle();
  v = await view();
  check('status filter: server-side, back to the first page', [(await requests()).slice(before), v.note, v.rows.length],
    [['GET /products?limit=50&offset=0&sort_by=name&sort_dir=asc&status=published'], '1' + EN + '1 of 1 product.', 1]);
  await page.selectOption('#prod-status', ''); await settle();
  before = (await requests()).length;
  await page.fill('#prod-search', 'saf'); await settle(700);
  v = await view();
  check('search: one server request with &search=, first page; the matching row', [(await requests()).slice(before), v.note, v.rows.length],
    [['GET /products?limit=50&offset=0&sort_by=name&sort_dir=asc&search=saf'], '1' + EN + '1 of 1 product.', 1]);
  await page.fill('#prod-search', 'zzz'); await settle(700);
  check('search: no match says so', await page.evaluate(() => document.querySelector('#screen-products .vis-live tbody').textContent.trim()),
    'No products match ' + iso('zzz') + '.');
  before = (await requests()).length;
  await page.fill('#prod-search', ''); await settle(700);
  check('search: cleared, the full list again', (await requests()).slice(before), ['GET /products?limit=50&offset=0&sort_by=name&sort_dir=asc']);
  await page.selectOption('#prod-status', 'published'); await settle(300);

  // Persian.
  await lang('fa');
  v = await view();
  check('fa: title, status badge, note with Persian digits', [v.title, v.rows[0][4], v.note],
    [F('products'), F('published'), F('note').replace('{from}', D(1)).replace('{to}', D(1)).replace('{total}', D(1))]);
  await page.click('#screen-products tbody tr:first-child button'); await settle();
  d = await detail();
  check('fa: detail facts and offer row', [d.facts[3][0], d.offers[0][1], d.offers[0][3]], [F('origin'), F('inStock'), F('condNew')]);
  await lang('en');
  check('back to English', (await detail()).facts[3][0], 'Origin');

  // Failure, Retry, empty.
  await page.evaluate(() => { window.__fail = '/products?'; });
  await go('#screen-dashboard'); await go('#screen-products');
  v = await view();
  check('500: the message and Retry', [v.state, v.message, v.action, v.title], ['error', 'Could not load products (' + iso('HTTP 500') + ').', 'Retry', null]);
  await page.evaluate(() => { window.__fail = null; window.__data.products = []; window.__data.total = 0; });
  await page.selectOption('#prod-status', ''); await settle();
  v = await view();
  check('no products', [v.state, v.note, v.rows], ['', '0' + EN + '0 of 0 products.', [['No products yet.']]]);
  check('no page errors', errors, []);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
