#!/usr/bin/env node
/*
 * Browser checks for the Memory Center screen (Step 9B).
 *   Not connected: data-live-wired, the note shown, the tools hidden; the
 *           export format names stay Latin identifiers.
 *   Live:   ONE request for the list (GET /memory/search), the total, the
 *           translated headers, kind labels (an unknown kind shown as sent);
 *           a filter; Versions (one request) with its heading and table;
 *           Compare (one request) with changed keys and change labels, and the
 *           identical case; export refused for a non-admin (403); a failed
 *           list; Persian over live content.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/memory-center.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-memory';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069), MD = fa(0xB7), EM = fa(0x2014);
const iso = (s) => FSI + s + PDI;
const digits = (s) => s.replace(/[0-9]/g, (d) => String.fromCharCode(0x6F0 + Number(d)));
const FA = {
  working: fa(0x62D, 0x627, 0x641, 0x638, 0x647, 0x654, 0x20, 0x6A9, 0x627, 0x631, 0x6CC),
  kind: fa(0x646, 0x648, 0x639),
  job: fa(0x6A9, 0x627, 0x631),
  writtenBy: fa(0x646, 0x648, 0x6CC, 0x633, 0x646, 0x62F, 0x647),
  jobState: fa(0x648, 0x636, 0x639, 0x6CC, 0x62A, 0x20, 0x6A9, 0x627, 0x631),
  versions: fa(0x646, 0x633, 0x62E, 0x647, 0x200C, 0x647, 0x627),
  compare: fa(0x645, 0x642, 0x627, 0x6CC, 0x633, 0x647),
  identical: fa(0x62F, 0x648, 0x20, 0x646, 0x633, 0x62E, 0x647, 0x20, 0x6CC, 0x6A9, 0x633, 0x627, 0x646, 0x200C, 0x627, 0x646, 0x62F),
  changed: fa(0x62A, 0x63A, 0x6CC, 0x6CC, 0x631, 0x6A9, 0x631, 0x62F, 0x647),
  unchanged: fa(0x628, 0x62F, 0x648, 0x646, 0x20, 0x62A, 0x63A, 0x6CC, 0x6CC, 0x631),
  items: fa(0x645, 0x648, 0x631, 0x62F, 0x20, 0x62D, 0x627, 0x641, 0x638, 0x647),
  version: fa(0x646, 0x633, 0x62E, 0x647),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const mem = (id, job, kind, version, content) => ({ id, job_key: job, kind, version, stage: null, item_key: null, created_by: 'agent:planner',
  created_at: '2026-10-30T10:00:00Z', knowledge_object_id: null, source_id: null, document_id: null, ai_execution_id: null,
  content_hash: 'h' + version, provenance: {}, content });
const ITEMS = [mem('m1', 'job-1', 'job_state', 2, { step: 3 }), mem('m2', 'job-2', 'odd_kind', 1, { x: 1 })];
const VERSIONS = [mem('v1', 'job-1', 'job_state', 1, { step: 2, summary: 'a' }), mem('m1', 'job-1', 'job_state', 2, { step: 3, summary: 'a' })];

function installMock({ items, versions }) {
  window.__requests = []; window.__status = 200; window.__identical = false;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7);
    window.__requests.push(p);
    if (p.indexOf('/memory/') !== 0) return reply({ items: [], total: 0 });
    if (p.indexOf('/memory/export.') === 0) return reply({ detail: 'admin only' }, 403);
    if (p.indexOf('/memory/search?') === 0) {
      if (window.__status !== 200) return reply({}, window.__status);
      const q = new URLSearchParams(p.slice(p.indexOf('?') + 1)), kind = q.get('kind');
      const shown = kind ? items.filter((i) => i.kind === kind) : items;
      return reply({ items: shown, total: shown.length, limit: 25, offset: 0 });
    }
    if (/\/versions$/.test(p)) return reply(versions);
    if (/\/compare\?/.test(p)) {
      const same = window.__identical;
      return reply({ job_key: 'job-1', kind: 'job_state', identical: same, changed_keys: same ? [] : ['step'],
        diff: [{ key: 'step', before: 2, after: same ? 2 : 3, change: same ? 'unchanged' : 'changed' }, { key: 'summary', before: 'a', after: 'a', change: 'unchanged' }] });
    }
    return reply({ detail: 'Not found' }, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(200);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => r.indexOf('/memory/') === 0));
  const view = () => page.evaluate(() => {
    const $ = (id) => document.getElementById(id), table = $('mc-table').querySelector('table');
    const vbox = $('mc-versions'), graph = vbox.querySelector('.rq-graph');
    return {
      // Live mode appends a "Live data" chip to the title; its own text is the first node.
      title: document.querySelector('#mc-panel .card__title').firstChild.textContent,
      total: $('mc-total').textContent,
      heads: table ? Array.from(table.querySelectorAll('th')).map((th) => th.textContent) : null,
      rows: table ? Array.from(table.querySelectorAll('tbody tr')).map((tr) => Array.from(tr.cells).slice(0, 5).map((td) => td.textContent)
        .filter((_, i) => i !== 4).concat(tr.querySelector('button').textContent)) : null,
      empty: $('mc-table').querySelector('.aic-empty') ? $('mc-table').querySelector('.aic-empty').textContent : null,
      vhead: vbox.querySelector('.mc-versions-head') ? vbox.querySelector('.mc-versions-head').textContent : null,
      vrows: vbox.querySelector('table') ? vbox.querySelectorAll('table')[0].querySelectorAll('tbody tr').length : null,
      compareBtn: vbox.querySelector('.rq-review .btn') ? vbox.querySelector('.rq-review .btn').textContent : null,
      graph: graph ? [graph.querySelector('h4').textContent, Array.from(graph.querySelectorAll('tbody tr')).map((tr) => tr.cells[1].textContent)] : null,
      msg: $('mc-msg').textContent,
    };
  });

  // Not connected.
  check('data-live-wired; the note shown, the tools hidden', await page.evaluate(() => [
    document.getElementById('screen-memory').hasAttribute('data-live-wired'), !document.getElementById('mc-note').hidden, document.getElementById('mc-body').hidden]),
    [true, true, true]);
  check('export formats are Latin identifiers', await page.$$eval('[data-mc-export] bdi.identifier', (b) => b.map((x) => x.textContent)),
    ['JSON', 'JSONL', 'CSV', 'ZIP']);

  // Live.
  await page.evaluate(installMock, { items: ITEMS, versions: VERSIONS });
  await connect();
  check('ONE request for the list', await requests(), ['/memory/search?limit=25&offset=0&sort=created_at&direction=desc']);
  let v = await view();
  check('total and headers', [v.total, v.heads], ['2 memory items', ['Job', 'Kind', 'Version', 'Written by', 'When', 'Content', '']]);
  check('rows: kind label, an unknown kind as sent, the Versions button', v.rows,
    [['job-1', 'Job state', '2', 'agent:planner', 'Versions'], ['job-2', 'odd_kind', '1', 'agent:planner', 'Versions']]);

  let before = (await requests()).length;
  await page.selectOption('#mc-kind', 'open_question'); await settle();
  v = await view();
  check('a kind filter: one request, nothing matches', [(await requests()).slice(before), v.total, v.empty],
    [['/memory/search?limit=25&offset=0&sort=created_at&direction=desc&kind=open_question'], '0 memory items',
      'Nothing matches. Memory appears once an AI job or an agent has run.']);
  await page.selectOption('#mc-kind', ''); await settle();

  before = (await requests()).length;
  await page.click('#mc-table tbody tr:first-child button'); await settle();
  v = await view();
  check('Versions: one request, heading and table', [(await requests()).slice(before), v.vhead, v.vrows, v.compareBtn],
    [['/memory/items/job-1/job_state/versions'], 'job-1 ' + MD + ' Job state ' + EM + ' 2 versions', 2, 'Compare']);
  before = (await requests()).length;
  await page.click('#mc-versions .rq-review .btn'); await settle();
  v = await view();
  check('Compare: one request, changed keys, change labels', [(await requests()).slice(before), v.graph],
    [['/memory/items/job-1/job_state/compare?left=1&right=2'], ['Changed: step', ['Changed', 'Unchanged']]]);
  await page.evaluate(() => { window.__identical = true; });
  await page.click('#mc-versions .rq-review .btn'); await settle();
  check('Compare: identical versions', (await view()).graph, ['The two versions are identical', ['Unchanged', 'Unchanged']]);

  await page.click('[data-mc-export="json"]'); await settle();
  check('export refused for a non-admin (403)', (await view()).msg, 'Only an owner or admin can export memory.');

  // Persian over live content (an identity entry would hang here).
  await page.evaluate(() => { window.__identical = false; });
  await lang('fa');
  await page.click('#mc-versions .rq-review .btn'); await settle();
  v = await view();
  check('fa: panel title, total, headers', [v.title, v.total, v.heads.slice(0, 4)], [FA.working, digits('2') + ' ' + FA.items, [FA.job, FA.kind, FA.version, FA.writtenBy]]);
  check('fa: kind label and Versions button', [v.rows[0][1], v.rows[0][4]], [FA.jobState, FA.versions]);
  check('fa: versions heading, Compare, change labels', [v.vhead, v.compareBtn, v.graph[1]],
    ['job-1 ' + MD + ' ' + FA.jobState + ' ' + EM + ' ' + digits('2') + ' ' + FA.version, FA.compare, [FA.changed, FA.unchanged]]);
  await page.evaluate(() => { window.__identical = true; });
  await page.click('#mc-versions .rq-review .btn'); await settle();
  check('fa: identical', (await view()).graph[0], FA.identical);
  await lang('en');
  check('back to English', (await view()).total, '2 memory items');

  // A failed list.
  await page.evaluate(() => { window.__status = 500; });
  await page.click('#mc-refresh'); await settle();
  check('500: the message', (await view()).msg, 'Could not load memory (' + iso('HTTP 500') + ').');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
