#!/usr/bin/env node
/*
 * Browser checks for the AI Center screen (Step 9E): providers, accounts,
 * models and routing.
 *   Not connected: data-live-wired, the note shown, the body hidden.
 *   Live:   providers, accounts and models load once each, in parallel;
 *           provider rows (adapter, or None; an unimplemented adapter marked;
 *           an unknown credential method as Unknown); account rows (disabled
 *           marked, the credential's last four, Not set, Unknown tokens); the
 *           model row (Unknown limits, the rate pair, the source label); the
 *           routing policy (name, mode label from the form's options, steps
 *           as "model on account"); Test connection sends one POST and shows
 *           the result; empty lists; a failed load; Persian over live content.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/ai-center.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-ai-center';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069), DOTS = fa(0x2022, 0x2022, 0x2022, 0x2022), EM = fa(0x2014);
const iso = (s) => FSI + s + PDI;
const FA = {
  notSet: fa(0x62A, 0x646, 0x638, 0x6CC, 0x645, 0x20, 0x646, 0x634, 0x62F, 0x647),
  test: fa(0x622, 0x632, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x627, 0x62A, 0x635, 0x627, 0x644),
  priority: fa(0x627, 0x633, 0x62A, 0x62E, 0x631, 0x20, 0x627, 0x648, 0x644, 0x648, 0x6CC, 0x62A, 0x200C, 0x62F, 0x627, 0x631, 0x20, 0x2014, 0x20, 0x628,
    0x647, 0x20, 0x62A, 0x631, 0x62A, 0x6CC, 0x628, 0x20, 0x627, 0x645, 0x62A, 0x62D, 0x627, 0x646, 0x20, 0x6A9, 0x646, 0x20, 0x648, 0x20, 0x646, 0x627,
    0x633, 0x627, 0x644, 0x645, 0x200C, 0x647, 0x627, 0x20, 0x631, 0x627, 0x20, 0x631, 0x62F, 0x20, 0x6A9, 0x646),
  onAccount: fa(0x631, 0x648, 0x6CC, 0x20, 0x62D, 0x633, 0x627, 0x628),
  unknown: fa(0x646, 0x627, 0x645, 0x634, 0x62E, 0x635),
  none: fa(0x647, 0x6CC, 0x686),
  routing: fa(0x645, 0x633, 0x6CC, 0x631, 0x6CC, 0x627, 0x628, 0x6CC),
  docs: fa(0x645, 0x633, 0x62A, 0x646, 0x62F, 0x627, 0x62A, 0x20, 0x627, 0x631, 0x627, 0x626, 0x647, 0x200C, 0x62F, 0x647, 0x646, 0x62F, 0x647),
  disabled: fa(0x28, 0x63A, 0x6CC, 0x631, 0x641, 0x639, 0x627, 0x644, 0x29),
  setPrefix: fa(0x62A, 0x646, 0x638, 0x6CC, 0x645, 0x200C, 0x634, 0x62F, 0x647, 0x20),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const DATA = {
  providers: [
    { id: 'pr1', name: 'Anthropic', adapter_key: 'anthropic', adapter_implemented: true, verification_status: 'verified', credential_method: 'api_key' },
    { id: 'pr2', name: 'Local LLM', adapter_key: 'ollama', adapter_implemented: false, verification_status: 'discovered', credential_method: null },
    { id: 'pr3', name: 'Registry only', adapter_key: null, adapter_implemented: false, verification_status: 'discovered', credential_method: null }],
  accounts: [
    { id: 'a1', provider_id: 'pr1', label: 'Main', enabled: true, credential_set: true, credential_last4: 'abcd', health_status: 'healthy', failure_count: 0, remaining_tokens: null },
    { id: 'a2', provider_id: 'pr1', label: 'Spare', enabled: false, credential_set: false, credential_last4: null, health_status: 'unknown', failure_count: 3, remaining_tokens: 500 }],
  models: [{ id: 'm1', provider_id: 'pr1', name: 'claude-x', context_window: 200000, max_input_tokens: null, max_output_tokens: 8000,
    rpm_limit: 50, tpm_limit: null, capability_source: 'official_docs' }],
  policies: [{ id: 'rp1', name: 'Default', mode: 'priority_pool', max_cost_per_job: null, currency: null,
    steps: [{ position: 0, account_id: 'a1', model: 'claude-x', stage: null }] }],
};

function installMock(data) {
  window.__requests = []; window.__data = data; window.__status = 200;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  const page = (items) => reply({ items, total: items.length, limit: 100, offset: 0 });
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (window.__status !== 200 && p.indexOf('/ai-center/providers') === 0) return reply({ error: { message: 'core offline' } }, window.__status);
    if (p === '/ai-center/providers?limit=100') return page(window.__data.providers);
    if (p === '/ai-center/accounts?limit=100') return page(window.__data.accounts);
    if (p === '/ai-center/models?limit=100') return page(window.__data.models);
    if (p === '/ai-center/routing-policies?limit=50') return page(window.__data.policies);
    if (p === '/ai-center/accounts/a1/test' && method === 'POST') return reply({ result: 'ok', http_status: 200 });
    if (p === '/ai-center/memory/semantic-backend') return reply({ status: 'not_configured', detail: 'PostgreSQL only' });
    return reply({ items: [], total: 0, limit: 25, offset: 0 });
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(250);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  const requests = (re) => page.evaluate((r) => (window.__requests || []).filter((x) => new RegExp(r).test(x)), re);
  const rows = (id) => page.evaluate((i) => Array.from(document.querySelectorAll('#' + i + ' tr')).map((tr) => Array.from(tr.cells).map((td) => td.textContent)), id);
  const view = () => page.evaluate(() => {
    const pol = document.querySelector('#aic-policies .aic-policy');
    return {
      note: document.getElementById('aic-conn-note').textContent,
      status: document.getElementById('aic-status').textContent,
      tab: document.querySelector('[data-aic-tab="routing"]').textContent.trim(),
      policy: pol ? [pol.querySelector('h3').textContent, pol.querySelector('.badge').textContent,
        Array.from(pol.querySelectorAll('.aic-steps li > span:first-child')).map((s) => s.textContent),
        Array.from(pol.querySelectorAll('.aic-steps li button')).map((b) => b.textContent)] : null,
      policiesEmpty: document.querySelector('#aic-policies .aic-note') ? document.querySelector('#aic-policies .aic-note').textContent : null,
    };
  });

  // Not connected.
  check('data-live-wired; note shown, body hidden', await page.evaluate(() => [
    document.getElementById('screen-ai-center').hasAttribute('data-live-wired'), !document.getElementById('aic-connect').hidden,
    document.getElementById('aic-body').hidden]), [true, true, true]);

  // Live.
  await page.evaluate(installMock, DATA);
  await connect();
  check('providers and models load once each', [await requests('/ai-center/providers\\?'), await requests('/ai-center/models\\?')],
    [['GET /ai-center/providers?limit=100'], ['GET /ai-center/models?limit=100']]);
  let v = await view();
  check('connected note and an empty status', [v.note, v.status], ['Connected to ' + iso('http://core.test') + '.', '']);
  check('the body stays visible in live mode (data-live-keep)', await page.evaluate(() => getComputedStyle(document.getElementById('aic-body')).display !== 'none'), true);
  check('provider rows', (await rows('aic-providers')).map((r) => r.slice(0, 4)), [
    ['Anthropic', 'anthropic', 'verified', 'api_key'],
    ['Local LLM', 'ollama (no adapter)', 'discovered', 'Unknown'],
    ['Registry only', 'None', 'discovered', 'Unknown']]);
  check('account rows: disabled marked, credential, health, failures, tokens', (await rows('aic-accounts')).map((r) => r.slice(0, 6)), [
    ['Main', 'Anthropic', 'Set ' + DOTS + iso('abcd'), 'healthy', '0', 'Unknown'],
    ['Spare (disabled)', 'Anthropic', 'Not set', 'unknown', '3', '500']]);
  check('account actions', (await rows('aic-accounts')).map((r) => r[6]), ['Test connectionDisable', 'Test connectionEnable']);
  check('model row: unknown limits, the rate pair, the source label', (await rows('aic-models')).map((r) => r.slice(0, 7)), [
    ['claude-x', 'Anthropic', '200000', 'Unknown', '8000', '50 / Unknown', 'Provider documentation']]);
  check('routing policy: name, mode label, steps, step buttons', v.policy, ['Default', 'Priority pool ' + EM + ' try in order, skipping unhealthy',
    [iso('claude-x') + ' on account ' + iso('Main (healthy)')], ['Move up', 'Move down', 'Remove']]);

  // Test connection: one POST, the result in the status line.
  let before = (await requests('/test')).length;
  await page.evaluate(() => document.querySelector('[data-aic-tab="resources"]').click());
  await page.click('#aic-accounts tr:first-child .aic-actions button'); await settle();
  check('Test connection: one POST, the result', [(await requests('/test')).slice(before), (await view()).status],
    [['POST /ai-center/accounts/a1/test'], iso('Main') + ': ' + iso('ok (HTTP 200)')]);

  // Persian over live content (an identity entry would hang here).
  await lang('fa');
  v = await view();
  const pfa = await rows('aic-providers'), afa = await rows('aic-accounts'), mfa = await rows('aic-models');
  check('fa: tab, None, Unknown', [v.tab, pfa[2][1], pfa[1][3]], [FA.routing, FA.none, FA.unknown]);
  check('fa: account disabled marker, credential, Not set, Test connection', [afa[1][0], afa[0][2], afa[1][2], afa[0][6].indexOf(FA.test) === 0],
    ['Spare ' + FA.disabled, FA.setPrefix + DOTS + iso('abcd'), FA.notSet, true]);
  check('fa: model source and an unknown limit', [mfa[0][6], mfa[0][3]], [FA.docs, FA.unknown]);
  check('fa: mode label and the step template', [v.policy[1], v.policy[2][0]], [FA.priority, iso('claude-x') + ' ' + FA.onAccount + ' ' + iso('Main (healthy)')]);
  await lang('en');
  check('back to English', (await view()).policy[1], 'Priority pool ' + EM + ' try in order, skipping unhealthy');

  // Empty lists, then a failed load.
  await page.evaluate(() => { window.__data = { providers: [], accounts: [], models: [], policies: [] }; });
  await connect();
  v = await view();
  check('empty lists say so', [(await rows('aic-providers'))[0][0], (await rows('aic-accounts'))[0][0], (await rows('aic-models'))[0][0], v.policiesEmpty],
    ['No providers registered yet.', 'No accounts yet.', 'No models registered yet. Routing still works; limits are then unknown.',
      'No routing policies yet. Create one with the form above.']);
  await page.evaluate(() => { window.__status = 500; });
  await connect();
  check('500: the load error', (await view()).status, 'Could not load: ' + iso('core offline'));

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
