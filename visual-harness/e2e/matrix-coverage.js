#!/usr/bin/env node
/*
 * Browser checks for Categories & matrix (Step 8C) and Coverage audit (Step 8D).
 *   Sample: both screens are data-live-wired; until connected they say so and
 *           keep their tools hidden; their static text in English and Persian.
 *   Live:   the matrix (GET /categories, /categories/{id}/matrix,
 *           /section-propagations): summary, topic headers, section rows, cells;
 *           the coverage audit for a topic (GET /knowledge/{id}/coverage and
 *           /coverage-audits): dimension cards, headline values, unknowns, history.
 *           Persian over live content: static labels translate, live data stays,
 *           and the page does not hang. Live text built by the scripts stays
 *           English (debt V5-matrix-coverage-runtime-fa).
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/matrix-coverage.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-matrix';
const fa = (...codes) => String.fromCharCode(...codes);
const FA = {
  matrix: fa(0x62F, 0x633, 0x62A, 0x647, 0x200C, 0x647, 0x627, 0x20, 0x648, 0x20, 0x645, 0x627, 0x62A, 0x631, 0x6CC, 0x633, 0x20,
    0x627, 0x635, 0x644, 0x6CC, 0x20, 0x645, 0x648, 0x636, 0x648, 0x639, 0x627, 0x62A),
  category: fa(0x62F, 0x633, 0x62A, 0x647),
  refresh: fa(0x62A, 0x627, 0x632, 0x647, 0x200C, 0x633, 0x627, 0x632, 0x6CC),
  proposals: fa(0x67E, 0x6CC, 0x634, 0x646, 0x647, 0x627, 0x62F, 0x647, 0x627, 0x6CC, 0x20, 0x62F, 0x631, 0x20, 0x627, 0x646, 0x62A,
    0x638, 0x627, 0x631, 0x20, 0x62A, 0x635, 0x645, 0x6CC, 0x645),
  coverage: fa(0x645, 0x645, 0x6CC, 0x632, 0x6CC, 0x20, 0x67E, 0x648, 0x634, 0x634),
  scope: fa(0x62F, 0x627, 0x645, 0x646, 0x647),
  run: fa(0x627, 0x62C, 0x631, 0x627, 0x6CC, 0x20, 0x645, 0x645, 0x6CC, 0x632, 0x6CC),
  history: fa(0x62A, 0x627, 0x631, 0x6CC, 0x62E, 0x686, 0x647),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const MATRIX = { topics: [{ id: 't1', name: 'Taranjabin' }, { id: 't2', name: 'Saffron' }], sections: 2, pending_cross_topic_evaluations: 1,
  rows: [
    { title: 'Composition', in_schema: true, origin: 'schema', cells: [
      { exists: true, status: 'documented', label: 'documented', claims: 3, evidence: 2, conflicts: 0, rationale: null, section_id: 's1' },
      { exists: true, status: 'conflicting', label: 'conflicting', claims: 2, evidence: 2, conflicts: 1, rationale: null, section_id: 's2' }] },
    { title: 'Dosage', in_schema: true, origin: 'discovered', cells: [{ exists: false }, { exists: false }] }] };
const AUDIT = { state: 'current', message: '', audit: { audit_version: 3, finished_at: '2026-10-30T10:00:00Z', duration_ms: 12, scope: 'topic',
  dimensions: { source: { percent_full_text: 50, total: 4 }, processing: { percent_extracted: null, note: 'No document yet.' },
    knowledge: { percent_reviewed: 25 }, evidence: { percent_supported: 40 }, section: { percent_documented: 50 }, publication: { citation_coverage: null } } } };

function installMock({ matrix, audit }) {
  window.__requests = [];
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (p === '/knowledge?limit=100') return reply({ items: [{ id: 't1', canonical_name: 'Taranjabin' }, { id: 't2', canonical_name: 'Saffron' }], total: 2 });
    if (p === '/categories?limit=100') return reply({ items: [{ id: 'c1', name: 'Plants', schema_version: 2 }], total: 1 });
    if (p === '/categories/c1/matrix') return reply(matrix);
    if (p === '/knowledge/t1/coverage') return reply(audit);
    if (p === '/coverage-audits?limit=10&knowledge_object_id=t1') return reply({ items: [
      { audit_version: 3, status: 'succeeded', trigger: 'manual', finished_at: '2026-10-30T10:00:00Z', failure_reason: null }], total: 1 });
    if (/^\/(claims|publications|section-propagations|knowledge-gaps)\?/.test(p)) return reply({ items: [], total: 0 });
    return reply({ detail: 'Not found' }, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(200);
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await settle(); };
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  const requests = (re) => page.evaluate((r) => (window.__requests || []).filter((x) => new RegExp(r).test(x)), re);
  const shown = (sel) => page.evaluate((s) => { const e = document.querySelector(s); return !!e && !e.hidden && getComputedStyle(e).display !== 'none'; }, sel);
  const text = (sel) => page.evaluate((s) => { const e = document.querySelector(s); return e ? e.textContent.trim() : null; }, sel);
  const statics = () => page.evaluate(() => ({
    matrix: [document.getElementById('h-screen-matrix').textContent, document.querySelector('#mx-cat').closest('label').querySelector('.field__label').textContent,
      document.getElementById('mx-refresh').textContent, document.querySelector('#mx-props').previousElementSibling.previousElementSibling.textContent],
    coverage: [document.getElementById('h-screen-coverage').textContent, document.querySelector('#cv-scope').closest('label').querySelector('.field__label').textContent,
      document.getElementById('cv-run').textContent, document.querySelector('#cv-history').previousElementSibling.textContent],
  }));
  const matrix = () => page.evaluate(() => {
    const t = document.querySelector('#mx-grid table');
    return {
      summary: document.getElementById('mx-summary').textContent,
      topics: t ? Array.from(t.querySelectorAll('thead th bdi')).map((b) => b.textContent) : null,
      rows: t ? Array.from(t.querySelectorAll('tbody tr')).map((tr) => [tr.querySelector('th').textContent,
        Array.from(tr.querySelectorAll('.kx-cell')).map((c) => [c.dataset.s, c.textContent])]) : null,
    };
  });
  const coverage = () => page.evaluate(() => ({
    banner: document.querySelector('#cv-state .kx-banner') ? document.querySelector('#cv-state .kx-banner').dataset.s : null,
    dims: Array.from(document.querySelectorAll('#cv-dims .kx-dim')).map((d) => [d.querySelector('h4').textContent,
      (d.querySelector('.kx-big') || d.querySelector('.kx-unknown')).textContent]),
    history: Array.from(document.querySelectorAll('#cv-history tbody tr')).map((tr) => tr.children[0].textContent + ' ' + tr.children[1].textContent),
  }));

  // Sample mode (before any connection).
  check('both screens are data-live-wired', await page.evaluate(() => ['screen-matrix', 'screen-coverage']
    .map((id) => document.getElementById(id).hasAttribute('data-live-wired'))), [true, true]);
  check('not connected: the note shows, the tools stay hidden', [await shown('#screen-matrix .kx-note'), await shown('#screen-matrix .kx-body'),
    await shown('#screen-coverage .kx-note'), await shown('#screen-coverage .kx-body')], [true, false, true, false]);
  check('static text in English', await statics(), {
    matrix: ['Categories & Master Topic Matrix', 'Category', 'Refresh', 'Proposals waiting for a decision'],
    coverage: ['Coverage audit', 'Scope', 'Run the audit', 'History'] });
  await lang('fa');
  check('static text in Persian', await statics(), { matrix: [FA.matrix, FA.category, FA.refresh, FA.proposals],
    coverage: [FA.coverage, FA.scope, FA.run, FA.history] });
  await lang('en');

  // Live: the matrix.
  await page.evaluate(installMock, { matrix: MATRIX, audit: AUDIT });
  await connect();
  // The Command workspace also reads /categories on connect, so only the matrix call is counted exactly.
  check('matrix requests: the first category matrix, once', await requests('/matrix'), ['GET /categories/c1/matrix']);
  check('connected: note hidden, tools and panel shown', [await shown('#screen-matrix .kx-note'), await shown('#screen-matrix .kx-body'),
    await shown('#screen-matrix .live-panel')], [false, true, true]);
  let m = await matrix();
  check('matrix: summary, topics, rows and cells', m, {
    summary: '2 topic(s) ' + fa(0xD7) + ' 2 section(s) ' + fa(0xB7) + ' 1 proposal(s) waiting',
    topics: ['Taranjabin', 'Saffron'],
    rows: [['Composition', [['documented', 'documented'], ['conflicting', 'conflicting']]], ['Dosage (discovered)', [['none', 'not yet'], ['none', 'not yet']]]] });

  // Live: the coverage audit for a topic.
  await go('#screen-coverage');
  await page.selectOption('#cv-scope', 'topic');
  await page.selectOption('#cv-target', 't1');
  await settle();
  check('coverage requests: the audit and its history', await requests('coverage'),
    ['GET /knowledge/t1/coverage', 'GET /coverage-audits?limit=10&knowledge_object_id=t1']);
  let c = await coverage();
  check('coverage: banner, six dimensions, unknowns not zero, history', c, { banner: 'current',
    dims: [['Sources', '50%'], ['Processing', 'Unknown'], ['Knowledge', '25%'], ['Evidence', '40%'], ['Sections', '50%'], ['Publication', 'Unknown']],
    history: ['v3 succeeded'] });

  // Persian over live content (an identity entry would hang here).
  await lang('fa');
  const s = await statics();
  check('fa live: static labels translate', [s.matrix[1], s.coverage[1], s.coverage[2]], [FA.category, FA.scope, FA.run]);
  c = await coverage();
  check('fa live: the coverage data stays on screen', [c.banner, c.dims.length, c.dims[0][1], c.history.length], ['current', 6, '50%', 1]);
  await go('#screen-matrix');
  m = await matrix();
  check('fa live: the matrix data stays on screen', [m.topics, m.rows.length], [['Taranjabin', 'Saffron'], 2]);
  await lang('en');
  check('back to English', (await statics()).matrix[0], 'Categories & Master Topic Matrix');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
