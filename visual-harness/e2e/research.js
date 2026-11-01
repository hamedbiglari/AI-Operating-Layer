#!/usr/bin/env node
/*
 * Browser checks for the Research engine card on Settings (polish phase 1).
 *   Rule 17 (V5-research-sources-n-plus-one): after a search the card reads
 *   the run's sources with ONE GET /research/sources/summaries?ids=..., never
 *   one /detail call per source.
 *   Runtime text (V5-settings-research-runtime-fa): the run title, the run
 *   summary and the messages are templates that follow the language switch.
 * Runs on file:// with AI Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/research.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-settings';
const fa = (...codes) => String.fromCharCode(...codes);
const iso = (s) => fa(0x2068) + s + fa(0x2069), EM = fa(0x2014);
const D = (n) => String(n).replace(/[0-9]/g, (c) => fa(0x6F0 + Number(c)));
const FA = {
  results: [0x646, 0x62A, 0x627, 0x6CC, 0x62C, 0x20, 0x62C, 0x633, 0x62A, 0x200C, 0x648, 0x62C, 0x648],
  query: [0x67E, 0x631, 0x633, 0x634, 0x3A, 0x20, 0x7B, 0x71, 0x75, 0x65, 0x72, 0x79, 0x7D, 0x20, 0x2014, 0x20, 0x7B, 0x75, 0x6E, 0x69, 0x71, 0x75, 0x65, 0x7D, 0x20, 0x645, 0x646, 0x628, 0x639, 0x20, 0x6CC, 0x6A9, 0x62A, 0x627, 0x60C, 0x20, 0x7B, 0x6E, 0x65, 0x77, 0x7D, 0x20, 0x62A, 0x627, 0x632, 0x647, 0x60C, 0x20, 0x7B, 0x6D, 0x65, 0x72, 0x67, 0x65, 0x64, 0x7D, 0x20, 0x6CC, 0x627, 0x641, 0x62A, 0x647, 0x654, 0x20, 0x62A, 0x6A9, 0x631, 0x627, 0x631, 0x6CC, 0x20, 0x627, 0x62F, 0x63A, 0x627, 0x645, 0x20, 0x634, 0x62F, 0x2E],
  subject: [0x6CC, 0x6A9, 0x20, 0x645, 0x648, 0x636, 0x648, 0x639, 0x20, 0x644, 0x627, 0x632, 0x645, 0x20, 0x627, 0x633, 0x62A, 0x2E],
};
const F = (k) => String.fromCharCode(...FA[k]);

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : ' | got ' + JSON.stringify(got) + ' | want ' + JSON.stringify(want)));
}

function installMock() {
  window.__requests = [];
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  const SRC = { s1: { id: 's1', title: 'Mannitol as a laxative', doi: '10.1/a', pmid: '111', content_access: 'abstract_only', review_status: 'not_reviewed' },
    s2: { id: 's2', title: 'Manna of Alhagi', doi: null, pmid: '222', content_access: 'metadata_only', review_status: 'not_reviewed' } };
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (p === '/research/federated/keyword-search' || p === '/research/federated/search') return reply({ query: 'Taranjabin', unique_sources: 2, new_sources: 2, merged_duplicates: 1,
      providers: [{ provider: 'crossref', status: 'ok', result_count: 2, error: null }], source_ids: ['s1', 's2'] }, 201);
    const m = p.match(/^\/research\/sources\/summaries\?ids=(.+)$/);
    if (m) return reply(m[1].split(',').map((i) => SRC[i]).filter(Boolean));
    if (/\/research\/sources\/[^/]+\/detail$/.test(p)) return reply(SRC[p.split('/')[3]]);
    return reply({ items: [], total: 0 });
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(pageUrl);
  const settle = (ms) => page.waitForTimeout(ms || 300);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const research = () => page.evaluate(() => window.__requests.filter((r) => r.indexOf('/research/sources') !== -1));
  const run = () => page.evaluate(() => { const b = document.getElementById('rq-run');
    return { title: (b.querySelector('h3') || {}).textContent, line: (b.querySelector('p.aic-hint') || {}).textContent }; });
  const msg = () => page.evaluate(() => document.getElementById('rq-msg').textContent);

  await page.evaluate(installMock);
  await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(500);
  await page.evaluate(() => { const k = document.getElementById('rq-kws'); k.appendChild(new Option('Taranjabin', 'k1', true, true)); document.getElementById('rq-kw-form').requestSubmit(); });
  await settle(600);
  check('one summaries read for the run; no per-source detail calls', await research(), ['GET /research/sources/summaries?ids=s1,s2']);
  const r = await run();
  check('the run: title and summary line', [r.title, r.line], ['Search results',
    'Query: ' + iso('Taranjabin') + ' ' + EM + ' 2 unique sources, 2 new, 1 duplicate hit merged.']);
  check('the sources are listed', await page.evaluate(() => ['Mannitol as a laxative', 'Manna of Alhagi'].map((t) => document.getElementById('rq-run').textContent.indexOf(t) !== -1)), [true, true]);
  await lang('fa');
  const f = await run();
  check('fa: the run title and the summary line follow the language switch', [f.title, f.line],
    [F('results'), F('query').replace('{query}', iso('Taranjabin')).replace('{unique}', D(2)).replace('{new}', D(2)).replace('{merged}', D(1))]);
  await page.evaluate(() => { document.getElementById('rq-subject').value = ''; document.getElementById('rq-q-form').requestSubmit(); }); await settle();
  check('fa: a message is a template', await msg(), F('subject'));
  await lang('en');
  check('back to English', [await msg(), (await run()).title], ['A subject is required.', 'Search results']);
  check('no page errors', errors, []);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
