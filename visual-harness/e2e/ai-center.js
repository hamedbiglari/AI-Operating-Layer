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
 *   9E-2:   Delete (providers, accounts, models) and Revoke credential shown to
 *           owner/admin only; a cancelled confirm sends nothing; 409 shows the
 *           server's message, 403 and 401 their own; a deleted model's row
 *           goes after the reload; a revoked credential reads Not set; step
 *           buttons are named by a translated label; the job panel, discovery
 *           rows and pager, package counts and verdicts and the Walrus line in
 *           English and Persian; the confirm question in Persian.
 * Runs on file:// with AI Core mocked in the page and every request
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
const FA2 = {
  del: [0x62D, 0x630, 0x641],
  revoke: [0x628, 0x627, 0x637, 0x644, 0x20, 0x6A9, 0x631, 0x62F, 0x646, 0x20, 0x627, 0x639, 0x62A, 0x628, 0x627, 0x631, 0x646, 0x627, 0x645, 0x647],
  askProvider: [0x627, 0x631, 0x627, 0x626, 0x647, 0x200C, 0x62F, 0x647, 0x646, 0x62F, 0x647, 0x654, 0x20, 0x7B, 0x6E, 0x61, 0x6D, 0x65, 0x7D, 0x20, 0x62D, 0x630, 0x641, 0x20, 0x634, 0x648, 0x62F, 0x61F, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x6A9, 0x627, 0x631, 0x20, 0x628, 0x631, 0x6AF, 0x634, 0x62A, 0x200C, 0x67E, 0x630, 0x6CC, 0x631, 0x20, 0x646, 0x6CC, 0x633, 0x62A, 0x2E],
  askAccount: [0x62D, 0x633, 0x627, 0x628, 0x20, 0x7B, 0x6C, 0x61, 0x62, 0x65, 0x6C, 0x7D, 0x20, 0x62D, 0x630, 0x641, 0x20, 0x634, 0x648, 0x62F, 0x61F, 0x20, 0x627, 0x639, 0x62A, 0x628, 0x627, 0x631, 0x646, 0x627, 0x645, 0x647, 0x654, 0x20, 0x622, 0x646, 0x20, 0x647, 0x645, 0x20, 0x67E, 0x627, 0x6A9, 0x20, 0x645, 0x6CC, 0x200C, 0x634, 0x648, 0x62F, 0x2E],
  askModel: [0x645, 0x62F, 0x644, 0x20, 0x7B, 0x6E, 0x61, 0x6D, 0x65, 0x7D, 0x20, 0x62D, 0x630, 0x641, 0x20, 0x634, 0x648, 0x62F, 0x61F, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x6A9, 0x627, 0x631, 0x20, 0x628, 0x631, 0x6AF, 0x634, 0x62A, 0x200C, 0x67E, 0x630, 0x6CC, 0x631, 0x20, 0x646, 0x6CC, 0x633, 0x62A, 0x2E],
  deletedModel: [0x645, 0x62F, 0x644, 0x20, 0x7B, 0x6E, 0x61, 0x6D, 0x65, 0x7D, 0x20, 0x62D, 0x630, 0x641, 0x20, 0x634, 0x62F, 0x2E],
  paused: [0x645, 0x62A, 0x648, 0x642, 0x641, 0x200C, 0x634, 0x62F, 0x647],
  pause: [0x62A, 0x648, 0x642, 0x641],
  stopReason: [0x62F, 0x644, 0x6CC, 0x644, 0x20, 0x62A, 0x648, 0x642, 0x641],
  newClaim: [0x627, 0x62F, 0x639, 0x627, 0x6CC, 0x20, 0x62A, 0x627, 0x632, 0x647],
  nOfTotal: [0x7B, 0x6E, 0x7D, 0x20, 0x627, 0x632, 0x20, 0x7B, 0x74, 0x6F, 0x74, 0x61, 0x6C, 0x7D],
  verdicts: [0x631, 0x623, 0x6CC, 0x200C, 0x647, 0x627],
  moveUp: [0x627, 0x646, 0x62A, 0x642, 0x627, 0x644, 0x20, 0x6AF, 0x627, 0x645, 0x20, 0x7B, 0x6E, 0x7D, 0x20, 0x628, 0x647, 0x20, 0x628, 0x627, 0x644, 0x627],
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
  window.__requests = []; window.__data = data; window.__status = 200; window.__del = {};
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
    if (p === '/auth/me') return reply(window.__role ? { user: { role: window.__role } } : {});
    if (method === 'DELETE') {
      const d = window.__data, f = window.__del[p]; let m;
      if (f) return reply(f[1], f[0]);
      if ((m = p.match(/^\/ai-center\/accounts\/([^/]+)\/credential$/))) {
        const a = d.accounts.find((x) => x.id === m[1]); a.credential_set = false; a.credential_last4 = null; return reply(a);
      }
      if ((m = p.match(/^\/ai-center\/(providers|accounts|models)\/([^/]+)$/))) {
        d[m[1]] = d[m[1]].filter((x) => x.id !== m[2]); return Promise.resolve(new Response(null, { status: 204 }));
      }
    }
    if (p === '/ai-center/jobs/job-1') return reply({ job_key: 'job-1', goal: 'Extract findings', status: 'paused', stop_reason: null, stage: null,
      completed: 2, pending: 1, failed: 0, total: 3 });
    if (p === '/ai-center/discovery?limit=25&offset=0') return reply({ items: [{ id: 'd1', name: 'Mistral', proposed_types: ['PROVIDER', 'odd_type'],
      status: 'discovered', last_verified_at: null, api_url: null }], total: 30, limit: 25, offset: 0 });
    const ktp = { id: 'k1', created_at: '2026-10-30T10:00:00Z', job_key: 'job-1', item_key: 'doc-001', submitted_by: null, status: 'partially_reconciled',
      validation: { claims: [{ local_id: 'c1', accepted: true }, { local_id: 'c2', accepted: false, reason: 'no source' }] },
      reconciliation: { claims: [{ local_id: 'c1', outcome: 'new_claim', evidence_created: 2, links_created: 1 }] } };
    if (p === '/knowledge-transfer/packages?limit=25&offset=0') return reply({ items: [ktp], total: 1, limit: 25, offset: 0 });
    if (p === '/knowledge-transfer/packages/k1') return reply(ktp);
    if (/^\/ai-center\/jobs\/job-1\/handoff$/.test(p)) return reply({ error: { message: 'none' } }, 404);
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

  // 9E-2: deletes (owner/admin only), revoke, and the advanced tabs, in English and Persian.
  const dialogs = []; let answer = true;
  page.on('dialog', async (d) => { dialogs.push(d.message()); if (answer) await d.accept(); else await d.dismiss(); });
  const F2 = (k) => String.fromCharCode(...FA2[k]);
  const D = (n) => String(n).replace(/[0-9]/g, (c) => fa(0x6F0 + Number(c)));
  const danger = () => page.evaluate(() => ['aic-providers', 'aic-accounts', 'aic-models'].map((id) => Array.from(document.querySelectorAll('#' + id + ' tr'))
    .map((tr) => Array.from(tr.querySelectorAll('.btn--danger')).map((b) => b.textContent))));
  const clickDanger = async (id, rowIdx, label) => {
    await page.evaluate(([i, r, l]) => { const b = Array.from(document.querySelectorAll('#' + i + ' tr')[r].querySelectorAll('.btn--danger')).find((x) => x.textContent === l); b.click(); }, [id, rowIdx, label]);
    await settle();
  };
  await page.evaluate(installMock, JSON.parse(JSON.stringify(DATA)));
  await page.evaluate(() => { window.__role = 'viewer'; });
  await connect();
  check('viewer: no Delete or Revoke anywhere', await page.evaluate(() => document.querySelectorAll('#aic-body .btn--danger').length), 0);
  await page.evaluate(() => { window.__role = 'admin'; });
  await connect();
  check('admin: Delete on every provider, account and model; Revoke only where a credential is set', await danger(),
    [[['Delete'], ['Delete'], ['Delete']], [['Revoke credential', 'Delete'], ['Delete']], [['Delete']]]);

  answer = false; let n = (await requests('^DELETE')).length;
  await clickDanger('aic-providers', 0, 'Delete');
  check('cancelled confirm: the question names the provider; nothing is sent', [dialogs[dialogs.length - 1], (await requests('^DELETE')).length - n],
    ['Delete provider ' + iso('Anthropic') + '? This cannot be undone.', 0]);
  answer = true;
  await page.evaluate(() => { window.__del['/ai-center/providers/pr1'] = [409, { error: { code: 'CONFLICT', message: 'Cannot delete provider: 2 accounts and 1 models exist. Delete them first.' } }]; });
  await clickDanger('aic-providers', 0, 'Delete');
  check('409: one DELETE; the server message; the row stays', [(await requests('^DELETE')).slice(n), (await view()).status, (await rows('aic-providers')).length],
    [['DELETE /ai-center/providers/pr1'], iso('Cannot delete provider: 2 accounts and 1 models exist. Delete them first.'), 3]);
  await page.evaluate(() => { window.__del['/ai-center/providers/pr2'] = [403, { error: { message: 'Insufficient role' } }];
    window.__del['/ai-center/providers/pr3'] = [401, { error: { message: 'expired' } }]; });
  await clickDanger('aic-providers', 1, 'Delete');
  check('403: the role message', (await view()).status, 'Your role is not allowed to delete (HTTP 403).');
  await clickDanger('aic-providers', 2, 'Delete');
  check('401: the session message', (await view()).status, 'Your session expired. Please reconnect.');
  await clickDanger('aic-models', 0, 'Delete');
  check('model deleted: the message; the row is gone after the reload', [dialogs[dialogs.length - 1], (await view()).status, (await rows('aic-models'))[0][0]],
    ['Delete model ' + iso('claude-x') + '? This cannot be undone.', 'Deleted model ' + iso('claude-x') + '.',
      'No models registered yet. Routing still works; limits are then unknown.']);
  await clickDanger('aic-accounts', 0, 'Revoke credential');
  check('revoke: DELETE on the credential; the account stays, now Not set, with Delete only', [(await requests('credential$')).slice(-1), (await view()).status,
    (await rows('aic-accounts'))[0].slice(0, 3), (await danger())[1][0]],
    [['DELETE /ai-center/accounts/a1/credential'], 'Credential revoked for ' + iso('Main') + '.', ['Main', 'Anthropic', 'Not set'], ['Delete']]);
  check('routing steps are named by a translated label', await page.evaluate(() => { const b = document.querySelector('#aic-policies .aic-steps li button');
    return document.getElementById(b.getAttribute('aria-labelledby')).textContent; }), 'Move step 1 up');

  // Job panel, discovery, packages and the Walrus line.
  await page.evaluate(() => { const f = document.getElementById('aic-job-lookup'); f.elements.job_key.value = 'job-1'; f.requestSubmit(); }); await settle();
  const job = () => page.evaluate(() => ({ facts: Array.from(document.querySelectorAll('#aic-job dt')).map((dt) => [dt.textContent, dt.nextElementSibling.textContent]),
    buttons: Array.from(document.querySelectorAll('#aic-job .aic-actions button')).map((b) => b.textContent), handoff: document.querySelector('#aic-job pre').textContent }));
  let j = await job();
  check('job: labels, a status label, Unknown for none, counts; Pause/Resume/Cancel', [j.facts.slice(1, 3), j.facts[4], j.buttons.slice(0, 3), j.handoff],
    [[['Status', 'Paused'], ['Stop reason', 'Unknown']], ['Completed', '2'], ['Pause', 'Resume', 'Cancel'], 'No handoff yet ' + EM + ' the job has not switched resources.']);
  check('discovery: type and status labels, Not verified, Unknown, the pager', [(await rows('aic-discovery'))[0], await page.evaluate(() => document.getElementById('aic-disc-info').textContent)],
    [['Mistral', 'Provider, odd_type', 'Discovered', 'Not verified', 'Unknown'], '1' + fa(0x2013) + '1 of 30']);
  const ktp = (await rows('aic-ktp'))[0];
  check('packages: source, status label, accepted count, outcomes, Verdicts', ktp.slice(1),
    ['job-1 / doc-001', 'Partly reconciled', '1 of 2', 'New claim: 1', 'Verdicts']);
  await page.evaluate(() => document.querySelector('#aic-ktp button').click()); await settle();
  check('verdicts: accepted with counts and outcome; rejected with the reason', await page.evaluate(() => Array.from(document.querySelectorAll('#aic-ktp-detail li')).map((li) => li.textContent)),
    ['c1: Accepted ' + EM + ' 2 new evidence, 1 new links ' + fa(0xB7) + ' New claim', 'c2: Rejected ' + EM + ' ' + iso('no source')]);
  check('Walrus line', await page.evaluate(() => document.getElementById('aic-walrus').textContent), 'Walrus: ' + iso('not_configured') + ' ' + EM + ' ' + iso('PostgreSQL only'));

  await lang('fa');
  j = await job();
  check('fa: delete buttons, job facts and actions, package counts', [(await danger())[0][0][0], j.facts[2][0], j.facts[1][1], j.buttons[0],
    (await rows('aic-ktp'))[0][3], (await rows('aic-ktp'))[0][4].indexOf(F2('newClaim')) === 0, (await rows('aic-ktp'))[0][5]],
    [F2('del'), F2('stopReason'), F2('paused'), F2('pause'), F2('nOfTotal').replace('{n}', D(1)).replace('{total}', D(2)), true, F2('verdicts')]);
  check('fa: the step label', await page.evaluate(() => { const b = document.querySelector('#aic-policies .aic-steps li button');
    return document.getElementById(b.getAttribute('aria-labelledby')).textContent; }), F2('moveUp').replace('{n}', D(1)));
  answer = false;
  await clickDanger('aic-accounts', 1, F2('del'));
  check('fa: the confirm question is Persian', dialogs[dialogs.length - 1], F2('askAccount').replace('{label}', iso('Spare')));
  await lang('en');
  answer = true;

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
