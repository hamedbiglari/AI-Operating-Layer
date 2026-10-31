#!/usr/bin/env node
/*
 * Browser checks for the AI executions screen (Step 9A).
 *   Not connected: the note, the body hidden.
 *   Live: ONE request per load, GET /ai-executions?limit=20&offset=0, whose
 *         counts_by_status fills the four stat cards (no call per status);
 *         rows with status labels, tokens, cost (estimated / hidden /
 *         unknown), duration; the page line; a status filter keeps the
 *         counts; the detail (2 requests: the execution and its chain);
 *         500 and 401; Persian over live content.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/ai-executions.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-ai-executions';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069);
const iso = (s) => FSI + s + PDI;
const digits = (s) => s.replace(/[0-9]/g, (d) => String.fromCharCode(0x6F0 + Number(d)));
const FA = {
  succeeded: fa(0x645, 0x648, 0x641, 0x642),
  failed: fa(0x646, 0x627, 0x645, 0x648, 0x641, 0x642),
  executions: fa(0x627, 0x62C, 0x631, 0x627, 0x647, 0x627),
  notReported: fa(0x6AF, 0x632, 0x627, 0x631, 0x634, 0x20, 0x646, 0x634, 0x62F, 0x647),
  ms: fa(0x645, 0x6CC, 0x644, 0x6CC, 0x200C, 0x62B, 0x627, 0x646, 0x6CC, 0x647),
  hidden: fa(0x67E, 0x646, 0x647, 0x627, 0x646, 0x20, 0x28, 0x641, 0x642, 0x637, 0x20, 0x645, 0x62F, 0x6CC, 0x631, 0x29),
  detail: fa(0x62C, 0x632, 0x626, 0x6CC, 0x627, 0x62A, 0x20, 0x627, 0x62C, 0x631, 0x627),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const ex = (id, status, o) => Object.assign({ id, organization_id: 'org', user_id: null, installation_id: null, parent_type: 'visibility_run',
  visibility_run_id: 'run-1', knowledge_object_id: null, stage: 'answer', operation_type: 'chat', provider: 'anthropic', model: 'claude-x',
  model_version: null, provider_request_id: null, started_at: '2026-10-30T10:00:00Z', completed_at: '2026-10-30T10:00:01Z', duration_ms: 850,
  status, error_code: null, error_message: null, input_tokens: 100, output_tokens: 20, total_tokens: 120, attempt_reason: null,
  previous_execution_id: null, provider_cost_visible: true,
  provider_cost: { estimated_provider_cost: '0.01', actual_provider_cost: null, currency: 'USD' } }, o || {});
const ITEMS = [
  ex('e1', 'succeeded'),
  ex('e2', 'failed', { input_tokens: null, output_tokens: null, duration_ms: null, stage: null, provider_cost_visible: false, provider_cost: null,
    error_code: 'http_503', error_message: 'busy', attempt_reason: 'retry', visibility_run_id: null }),
  ex('e3', 'odd_state', { provider_cost: { estimated_provider_cost: null, actual_provider_cost: null, currency: 'USD' } }),
];
const COUNTS = { running: 0, succeeded: 5, failed: 2, timeout: 1, rate_limited: 1, cancelled: 0, abandoned: 1 };

function installMock({ items, counts }) {
  window.__requests = []; window.__status = 200;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7);
    window.__requests.push(p);
    if (p.indexOf('/ai-executions') !== 0) return reply({ items: [], total: 0 });
    if (window.__status !== 200) return reply({ detail: 'no' }, window.__status);
    const m = p.match(/^\/ai-executions\/([^/?]+)(\/chain)?$/);
    if (m) {
      const x = items.find((i) => i.id === m[1]);
      return m[2] ? reply([Object.assign({}, x, { id: 'e0', status: 'failed', attempt_reason: null }), x]) : reply(x);
    }
    const q = new URLSearchParams(p.slice(p.indexOf('?') + 1)), st = q.get('status');
    const shown = st ? items.filter((i) => i.status === st) : items;
    return reply({ items: shown, total: st ? (counts[st] || 0) : 10, limit: 20, offset: 0, counts_by_status: counts });
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(200);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => r.indexOf('/ai-executions') === 0));
  const connect = async () => {
    await page.fill('#aix-base', 'http://core.test'); await page.fill('#aix-token', 'tok');
    await page.click('#aix-connect-btn'); await settle();
  };
  const view = () => page.evaluate(() => {
    const $ = (id) => document.getElementById(id), shown = (e) => !e.hidden && getComputedStyle(e).display !== 'none';
    return {
      state: [$('aix-state').dataset.state, $('aix-state-text').textContent],
      body: shown($('aix-body')),
      stats: ['aix-s-total', 'aix-s-succeeded', 'aix-s-failed', 'aix-s-abandoned'].map((id) => $(id).textContent),
      rows: Array.from(document.querySelectorAll('#aix-rows tr')).map((tr) => Array.from(tr.cells).slice(1).map((td) => td.textContent)),
      badges: Array.from(document.querySelectorAll('#aix-rows .badge')).map((b) => b.className),
      info: $('aix-page-info').textContent,
      title: document.querySelector('#aix-body .card .card__title').textContent,
    };
  });
  const detail = () => page.evaluate(() => {
    const dl = document.getElementById('aix-detail-list'), pairs = {};
    const dts = dl.querySelectorAll('dt'); dts.forEach((dt) => { pairs[dt.textContent] = dt.nextElementSibling.textContent; });
    return { title: document.querySelector('#aix-detail .card__title').textContent, labels: Array.from(dts).map((d) => d.textContent), pairs,
      chain: Array.from(document.querySelectorAll('#aix-chain li')).map((li) => li.textContent) };
  });

  // Not connected.
  let v = await view();
  check('not connected: the note, no body', [v.state, v.body], [['idle', 'Not connected. Enter the Cloud Core URL and an access token.'], false]);

  // Live.
  await page.evaluate(installMock, { items: ITEMS, counts: COUNTS });
  await connect();
  check('ONE request per load (no call per status)', await requests(), ['/ai-executions?limit=20&offset=0']);
  v = await view();
  check('stat cards from counts_by_status: all, succeeded, failed+timeout+rate-limited, abandoned', v.stats, ['10', '5', '4', '1']);
  check('rows: status label, provider / model, stage, tokens, cost, duration', v.rows, [
    ['Succeeded', 'anthropic / claude-x', 'answer', '100 / 20', iso('USD') + ' ' + iso('0.01') + ' (estimated)', '850 ms'],
    ['Failed', 'anthropic / claude-x', '\u2014', 'Not reported', 'Hidden (admin only)', '\u2014'],
    ['odd_state', 'anthropic / claude-x', 'answer', '100 / 20', 'Unknown', '850 ms']]);
  check('badge colours; an unknown status is shown as sent', v.badges, ['badge badge--success', 'badge badge--danger', 'badge badge--unknown']);
  check('page line and ready state', [v.info, v.state[0], v.body], ['1\u20133 of 10', 'ready', true]);

  // A status filter: one request, the counts stay.
  let before = (await requests()).length;
  await page.selectOption('#aix-f-status', 'failed');
  check('status options show labels, send API values', await page.$eval('#aix-f-status option[value="rate_limited"]', (o) => o.textContent), 'Rate limited');
  await page.click('#aix-apply'); await settle();
  v = await view();
  check('filter: one request with the status', (await requests()).slice(before), ['/ai-executions?limit=20&offset=0&status=failed']);
  check('filter: rows narrowed, counts unchanged', [v.rows.length, v.stats], [1, ['10', '5', '4', '1']]);

  // Detail.
  before = (await requests()).length;
  await page.click('#aix-rows tr:first-child'); await settle();
  const d = await detail();
  check('detail: two requests', (await requests()).slice(before), ['/ai-executions/e2', '/ai-executions/e2/chain']);
  check('detail: labels', d.labels, ['Execution', 'Status', 'Operation', 'Provider', 'Model', 'Model version', 'Provider request id', 'Parent',
    'Stage', 'Started', 'Completed', 'Duration', 'Tokens in / out', 'Provider cost', 'Attempt reason', 'Error']);
  check('detail: values', [d.pairs.Status, d.pairs.Parent, d.pairs['Attempt reason'], d.pairs.Error, d.pairs['Model version'], d.pairs.Duration],
    ['Failed', 'visibility_run (deleted)', 'retry', 'http_503: busy', '\u2014', '\u2014']);
  check('detail: chain', d.chain, ['Failed \u2014 anthropic / claude-x', 'Failed \u2014 anthropic / claude-x (retry)']);

  // Persian over live content (an identity entry would hang here).
  await lang('fa');
  v = await view();
  const dfa = await detail();
  check('fa: card title, row status, tokens, cost, duration', [v.title, v.rows[0][0], v.rows[0][3], v.rows[0][4]],
    [FA.executions, FA.failed, FA.notReported, FA.hidden]);
  check('fa: detail title and status', [dfa.title, dfa.pairs[fa(0x648, 0x636, 0x639, 0x6CC, 0x62A)]], [FA.detail, FA.failed]);
  // Option text stays English in Persian: the Persian layer skips everything inside <select> (KEEP_LATIN).
  await page.selectOption('#aix-f-status', ''); await page.click('#aix-apply'); await settle();
  v = await view();
  check('fa: a duration in Persian digits, the counts too', [v.rows[0][5], v.stats], [digits('850') + ' ' + FA.ms, [digits('10'), digits('5'), digits('4'), digits('1')]]);
  await lang('en');
  check('back to English', (await view()).rows[0][0], 'Succeeded');

  // Errors.
  await page.evaluate(() => { window.__status = 500; });
  await page.click('#aix-apply'); await settle();
  v = await view();
  check('500: the error, the body hidden', [v.state, v.body], [['error',
    'Could not load AI executions: ' + iso('HTTP 500') + '. Check the URL, and that Cloud Core allows this origin (CORS_ALLOWED_ORIGINS).'], false]);
  // An error hides the body (and its Apply button); the way back is Connect.
  await page.evaluate(() => { window.__status = 401; });
  await page.click('#aix-connect-btn'); await settle();
  v = await view();
  check('401: permission denied', v.state, ['denied', 'Permission denied (HTTP 401). The token is missing, expired, or not valid for this organization.']);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
