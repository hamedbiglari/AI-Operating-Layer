#!/usr/bin/env node
/*
 * Browser checks for the AI Catalog screen (Step 9D).
 *   Not connected: data-live-wired, the note and the connection form shown,
 *           the catalog hidden.
 *   Live:   ONE request (GET /ai-center/discovery) fills the cards: the name,
 *           type and status badges labelled as in the filters (an unknown value
 *           shown as sent), the official link; the total; the catalog stays
 *           visible in live mode (data-live-keep); a filter (one request);
 *           no results; the pager; Import initial list; a failed load;
 *           Persian over live content.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/ai-catalog.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-ai-catalog';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069);
const iso = (s) => FSI + s + PDI;
const digits = (s) => s.replace(/[0-9]/g, (d) => String.fromCharCode(0x6F0 + Number(d)));
const FA = {
  researchTool: fa(0x627, 0x628, 0x632, 0x627, 0x631, 0x20, 0x67E, 0x698, 0x648, 0x647, 0x634, 0x6CC),
  provider: fa(0x627, 0x631, 0x627, 0x626, 0x647, 0x200C, 0x62F, 0x647, 0x646, 0x62F, 0x647),
  discovered: fa(0x6A9, 0x634, 0x641, 0x200C, 0x634, 0x62F, 0x647),
  official: fa(0x645, 0x646, 0x628, 0x639, 0x20, 0x631, 0x633, 0x645, 0x6CC, 0x20, 0x631, 0x627, 0x633, 0x62A, 0x6CC, 0x200C, 0x622, 0x632, 0x645,
    0x627, 0x6CC, 0x6CC, 0x200C, 0x634, 0x62F, 0x647),
  total: fa(0x645, 0x646, 0x628, 0x639, 0x20, 0x62F, 0x631, 0x20, 0x641, 0x647, 0x631, 0x633, 0x62A),
  none: fa(0x628, 0x627, 0x20, 0x641, 0x6CC, 0x644, 0x62A, 0x631, 0x647, 0x627, 0x6CC, 0x20, 0x6A9, 0x646, 0x648, 0x646, 0x6CC, 0x20, 0x646, 0x62A,
    0x6CC, 0x62C, 0x647, 0x200C, 0x627, 0x6CC, 0x20, 0x67E, 0x6CC, 0x62F, 0x627, 0x20, 0x646, 0x634, 0x62F, 0x2E),
  importList: fa(0x648, 0x627, 0x631, 0x62F, 0x20, 0x6A9, 0x631, 0x62F, 0x646, 0x20, 0x641, 0x647, 0x631, 0x633, 0x62A, 0x20, 0x627, 0x648, 0x644, 0x6CC, 0x647),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const entry = (id, name, types, status, official) => ({ id, name, canonical_name: name.toLowerCase(), proposed_types: types, status,
  official_url: official || null, api_url: null, documentation_url: null, classification_basis: 'owner list', discovery_source: 'seed',
  verification_notes: null, last_verified_at: null, created_at: '2026-10-30T10:00:00Z', updated_at: '2026-10-30T10:00:00Z' });
const ENTRIES = [
  entry('d1', 'Elicit', ['RESEARCH_TOOL', 'SEARCH_TOOL'], 'discovered'),
  entry('d2', 'Anthropic', ['PROVIDER', 'ODD_TYPE'], 'official_source_verified', 'https://www.anthropic.com'),
  entry('d3', 'Mystery', [], 'odd_status'),
];

function installMock(entries) {
  window.__requests = []; window.__status = 200; window.__entries = entries; window.__total = null;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (p === '/ai-center/discovery/import-seed' && method === 'POST') return reply({ received: 70, inserted: 3, already_present: 67 });
    if (p.indexOf('/ai-center/discovery?') === 0) {
      if (window.__status !== 200) return reply({ error: { message: 'catalog offline' } }, window.__status);
      const q = new URLSearchParams(p.slice(p.indexOf('?') + 1)), type = q.get('type');
      const shown = type ? window.__entries.filter((e) => e.proposed_types.indexOf(type) !== -1) : window.__entries;
      return reply({ items: shown, total: window.__total || shown.length, limit: 48, offset: Number(q.get('offset')) });
    }
    return reply({ items: [], total: 0 });
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(200);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  // AI Center reads its own discovery tab on connect (limit=25); only this screen's requests (limit=48) and the import count.
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /discovery\?limit=48|import-seed/.test(r)));
  const view = () => page.evaluate(() => {
    const $ = (id) => document.getElementById(id), shown = (e) => !e.hidden && getComputedStyle(e).display !== 'none';
    return {
      body: shown($('cat-body')), note: $('cat-conn-note').textContent, total: $('cat-total').textContent,
      cards: Array.from(document.querySelectorAll('#cat-grid .cat-card')).map((c) => [c.querySelector('.cat-card__name').textContent,
        Array.from(c.querySelectorAll('.badge')).map((b) => b.textContent),
        c.querySelector('.cat-card__url a') ? c.querySelector('.cat-card__url a').getAttribute('href') : null]),
      badgeClasses: Array.from(document.querySelectorAll('#cat-grid .cat-card .badge')).map((b) => b.className),
      empty: document.querySelector('#cat-grid .aic-empty') ? document.querySelector('#cat-grid .aic-empty').textContent : null,
      pager: $('cat-pager').querySelector('span') ? [$('cat-pager').querySelector('span').textContent,
        Array.from($('cat-pager').querySelectorAll('button')).map((b) => [b.textContent, b.disabled])] : null,
      seed: $('cat-seed').textContent,
    };
  });

  // Not connected.
  check('data-live-wired; note and form shown, catalog hidden', await page.evaluate(() => [
    document.getElementById('screen-ai-catalog').hasAttribute('data-live-wired'), !document.getElementById('cat-connect').hidden,
    document.getElementById('cat-body').hidden]), [true, true, true]);

  // Live.
  await page.evaluate(installMock, ENTRIES);
  await connect();
  check('ONE request for the catalog', await requests(), ['GET /ai-center/discovery?limit=48&offset=0']);
  let v = await view();
  check('the catalog stays visible in live mode; the note says connected', [v.body, v.note], [true, 'Connected to ' + iso('http://core.test') + '.']);
  check('total and cards: name, type and status labels as in the filters, the link', [v.total, v.cards], ['3 resources in catalog', [
    ['Elicit', ['Research tool', 'Search tool', 'Discovered'], null],
    ['Anthropic', ['Provider', 'ODD_TYPE', 'Official source verified'], 'https://www.anthropic.com'],
    ['Mystery', ['odd_status'], null]]]);
  check('badge colours follow the value', v.badgeClasses.slice(2, 3), ['badge badge--unknown']);

  // A type filter: one request; no results.
  let before = (await requests()).length;
  await page.selectOption('#cat-type', 'PROVIDER'); await settle();
  v = await view();
  check('type filter: one request, one card', [(await requests()).slice(before), v.cards.map((c) => c[0])],
    [['GET /ai-center/discovery?limit=48&offset=0&type=PROVIDER'], ['Anthropic']]);
  await page.selectOption('#cat-type', 'AUDIO_TOOL'); await settle();
  v = await view();
  check('no results: said, total 0', [v.total, v.empty], ['0 resources in catalog', 'No results matching the current filters.']);
  await page.selectOption('#cat-type', ''); await settle();

  // The pager appears past 48.
  await page.evaluate(() => { window.__total = 100; });
  await page.click('#cat-refresh'); await settle();
  check('pager past 48', (await view()).pager, ['1\u20133 of 100', [['Previous', true], ['Next', false]]]);
  await page.evaluate(() => { window.__total = null; });

  // Import initial list: POST, then the catalog reloads.
  before = (await requests()).length;
  await page.click('#cat-seed'); await settle();
  check('import: POST then one reload', (await requests()).slice(before), ['POST /ai-center/discovery/import-seed', 'GET /ai-center/discovery?limit=48&offset=0']);

  // Persian over live content (an identity entry would hang here).
  await lang('fa');
  v = await view();
  check('fa: total, type and status labels, Import button', [v.total, v.cards[0][1], v.cards[1][1][0], v.cards[1][1][2], v.seed],
    [digits('3') + ' ' + FA.total, [FA.researchTool, fa(0x627, 0x628, 0x632, 0x627, 0x631, 0x20, 0x62C, 0x633, 0x62A, 0x200C, 0x648, 0x62C, 0x648),
      FA.discovered], FA.provider, FA.official, FA.importList]);
  check('fa: an unknown type stays as sent', v.cards[1][1][1], 'ODD_TYPE');
  await page.selectOption('#cat-type', 'AUDIO_TOOL'); await settle();
  check('fa: no results', (await view()).empty, FA.none);
  await page.selectOption('#cat-type', ''); await settle();
  await lang('en');
  check('back to English', (await view()).total, '3 resources in catalog');

  // A failed load.
  await page.evaluate(() => { window.__status = 500; });
  await page.click('#cat-refresh'); await settle();
  check('500: the message', (await view()).total, 'Could not load the catalog (' + iso('catalog offline') + ').');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
