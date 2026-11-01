#!/usr/bin/env node
/*
 * Real-key integration suite: the harness against a LIVE AI Core that makes
 * REAL provider calls. NOT part of CI and never run automatically: it spends
 * money on the provider account whose key you pass in.
 * Setup and every variable: docs/e2e-real-keys.md.
 *
 *   1. #screen-ai-center   add a provider, an account and its credential
 *                          through the UI, then Test connection -> PASS.
 *   2. (API)               register the model and a routing policy on that
 *                          account, so a command has somewhere to run.
 *   3. #screen-chat        new command (synthesis on AIOL_TOPIC_ID), Plan,
 *                          Run; wait until the worker finishes it.
 *   4. #screen-ai-executions  connect, and find the real execution: this
 *                          model, status succeeded, started during this run.
 *   Finally the credential is revoked (DELETE .../credential), so the real
 *   key does not stay stored in the database after the suite.
 *
 * The key is read from the environment only; it is typed into the
 * credential form and never printed, logged or written to a file.
 *
 * Usage: node visual-harness/e2e/real-keys.js
 *   ANTHROPIC_API_KEY   required: the key stored on the test account
 *   AIOL_TOKEN          required: an owner/admin access token for the org
 *   AIOL_TOPIC_ID       required: a knowledge object id in that org with
 *                       reviewed evidence (synthesis reads it)
 *   AIOL_BASE           AI Core origin, default http://127.0.0.1:8000
 *   AIOL_MODEL          provider model id, default claude-haiku-5-5
 *   AIOL_RUN_TIMEOUT_S  how long to wait for the command, default 600
 *   HARNESS_PORT        port this script serves the harness on, default 5175
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const KEY = process.env.ANTHROPIC_API_KEY, TOKEN = process.env.AIOL_TOKEN, TOPIC = process.env.AIOL_TOPIC_ID;
const BASE = (process.env.AIOL_BASE || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const MODEL = process.env.AIOL_MODEL || 'claude-haiku-5-5';
const RUN_TIMEOUT_MS = Number(process.env.AIOL_RUN_TIMEOUT_S || 600) * 1000;
const PORT = Number(process.env.HARNESS_PORT || 5175);
const missing = [['ANTHROPIC_API_KEY', KEY], ['AIOL_TOKEN', TOKEN], ['AIOL_TOPIC_ID', TOPIC]].filter((p) => !p[1]).map((p) => p[0]);
if (missing.length) { console.error('Missing: ' + missing.join(', ') + '. See docs/e2e-real-keys.md.'); process.exit(2); }

const STAMP = 'e2e-real-' + Date.now();
const startedAt = new Date();
let failures = 0;
function check(name, ok, detail) {
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail === undefined ? '' : ' | ' + String(detail).split(KEY).join('[key]')));
}

async function api(p, opt) {
  opt = opt || {};
  const r = await fetch(BASE + '/api/v1' + p, { method: opt.method || 'GET',
    headers: Object.assign({ Authorization: 'Bearer ' + TOKEN }, opt.body ? { 'Content-Type': 'application/json' } : {}),
    body: opt.body ? JSON.stringify(opt.body) : undefined });
  const text = await r.text();
  let data = null; try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
  if (!r.ok) throw new Error(opt.method + ' ' + p + ' -> HTTP ' + r.status + ' ' + JSON.stringify(data));
  return data;
}

// The harness is served over http (not file://) so AI Core's CORS list can name its origin.
function serveHarness() {
  const root = path.join(__dirname, '..');
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname).replace(/^\/+/, '') || 'index.html';
    const file = path.normalize(path.join(root, rel));
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
    const type = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' }[path.extname(file)] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': type + '; charset=utf-8' }); fs.createReadStream(file).pipe(res);
  });
  return new Promise((ok) => server.listen(PORT, '127.0.0.1', () => ok(server)));
}

(async () => {
  const me = await api('/auth/me');
  check('the token is an owner or admin', ['owner', 'admin'].includes(String(me.role).toLowerCase()), me.role);
  const server = await serveHarness();
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  let accountId = null;
  try {
    const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await page.waitForTimeout(500); };
    const text = (id) => page.evaluate((i) => (document.getElementById(i) || {}).textContent || '', id);
    const waitText = (id, pred, ms) => page.waitForFunction(([i, src]) => {
      const t = (document.getElementById(i) || {}).textContent || ''; return new Function('t', 'return ' + src)(t);
    }, [id, pred], { timeout: ms || 30000 });
    const pick = (sel, label) => page.evaluate(([s, l]) => { const e = document.querySelector(s);
      const o = Array.from(e.options).find((x) => x.textContent.indexOf(l) !== -1 || x.value === l);
      if (!o) return false; e.value = o.value; e.dispatchEvent(new Event('change', { bubbles: true })); return true; }, [sel, label]);

    await page.goto('http://127.0.0.1:' + PORT + '/index.html#screen-ai-center');
    await page.evaluate(([b, t]) => window.AIOL_LIVE_CONNECT(b, t), [BASE, TOKEN]);
    await page.waitForTimeout(1500);

    // 1. AI Center: provider, account, credential, Test connection.
    await page.evaluate(() => document.querySelector('[data-aic-tab="resources"]').click());
    const provName = 'Anthropic (' + STAMP + ')';
    await page.fill('#aic-add-provider [name="name"]', provName);
    await page.selectOption('#aic-add-provider [name="adapter_key"]', 'anthropic');
    await page.evaluate(() => document.getElementById('aic-add-provider').requestSubmit());
    await waitText('aic-status', 't === "Provider added."');
    check('provider added through the form', true);
    await page.waitForTimeout(1000);
    check('the new provider is offered for an account', await pick('#aic-provider-select', provName));
    await page.fill('#aic-add-account [name="label"]', STAMP);
    await page.evaluate(() => document.getElementById('aic-add-account').requestSubmit());
    await waitText('aic-status', 't === "Account added."');
    await page.waitForTimeout(1000);
    check('the new account is offered for a credential', await pick('#aic-account-select', STAMP));
    await page.fill('#aic-set-credential [name="secret"]', KEY);
    await page.evaluate(() => document.getElementById('aic-set-credential').requestSubmit());
    await waitText('aic-status', 't.indexOf("Credential saved") === 0');
    await page.waitForTimeout(1000);
    const accounts = await api('/ai-center/accounts?limit=200');
    const account = (accounts.items || []).find((a) => a.label === STAMP);
    accountId = account && account.id;
    check('the account reports a stored credential (and never the key)', !!(account && account.credential_set && JSON.stringify(account).indexOf(KEY) === -1));
    await page.evaluate((label) => { const tr = Array.from(document.querySelectorAll('#aic-accounts tr')).find((r) => r.cells[0] && r.cells[0].textContent.indexOf(label) !== -1);
      Array.from(tr.querySelectorAll('button')).find((b) => b.textContent === 'Test connection').click(); }, STAMP);
    await waitText('aic-status', 't.indexOf("Testing") !== 0 && t.indexOf(":") !== -1', 60000);
    const tested = await text('aic-status');
    check('Test connection against the real provider: PASS', /: PASS\b/.test(tested), tested);

    // 2. Model and routing policy on that account (API: the forms are covered by ai-center.js).
    const provider = (await api('/ai-center/providers?limit=200')).items.find((p) => p.name === provName);
    await api('/ai-center/models', { method: 'POST', body: { provider_id: provider.id, name: MODEL, capability_source: 'operator' } });
    const policy = await api('/ai-center/routing-policies', { method: 'POST', body: { name: STAMP, mode: 'manual_single', steps: [{ account_id: accountId, model: MODEL }] } });
    check('model and routing policy registered', !!policy.id);

    // 3. Chat (Command workspace): a synthesis that calls the model for real.
    let commandId = null;
    page.on('response', async (r) => { if (r.request().method() === 'POST' && /\/workspace\/commands$/.test(r.url())) {
      try { commandId = (await r.json()).id; } catch (e) { /* not JSON */ } } });
    await page.evaluate(([b, t]) => window.AIOL_LIVE_CONNECT(b, t), [BASE, TOKEN]);
    await go('#screen-chat');
    await page.waitForTimeout(1500);
    await page.evaluate(() => document.getElementById('ws-new').click());
    await page.waitForFunction(() => !document.getElementById('ws-editor').hidden, null, { timeout: 30000 });
    await page.fill('#ws-text', 'Write a short synthesis of the reviewed evidence for this topic. (' + STAMP + ')');
    check('the topic is offered', await pick('#ws-topic', TOPIC));
    check('the routing policy is offered', await pick('#ws-policy', policy.id));
    if (await page.$('#ws-intent option[value="synthesis"]')) await page.selectOption('#ws-intent', 'synthesis');
    await page.waitForTimeout(1500);
    await page.evaluate(() => document.getElementById('ws-plan').click());
    await waitText('ws-msg', 't.indexOf("Plan ready") === 0', 30000);
    check('plan: it runs a model and nothing is missing', /runs a model|model/i.test(await text('ws-plan-out')), (await text('ws-plan-out')).slice(0, 160));
    await page.evaluate(() => document.getElementById('ws-run').click());
    await waitText('ws-msg', 't.indexOf("Running on the server") === 0', 30000);
    check('Run accepted', !!commandId, commandId);
    const done = ['completed', 'completed_with_gaps', 'blocked', 'failed', 'cancelled'];
    let state = 'queued';
    for (const end = Date.now() + RUN_TIMEOUT_MS; Date.now() < end && done.indexOf(state) === -1;) {
      await new Promise((ok) => setTimeout(ok, 5000));
      const c = await api('/workspace/commands/' + commandId);
      state = (c.current && c.current.execution_state) || c.execution_state || state;
    }
    check('the command finished with a result', state === 'completed' || state === 'completed_with_gaps', state);

    // 4. AI executions: the real call is listed.
    await go('#screen-ai-executions');
    await page.fill('#aix-base', BASE); await page.fill('#aix-token', TOKEN);
    await page.click('#aix-connect-btn');
    await page.waitForFunction(() => document.getElementById('aix-state').dataset.state === 'ready', null, { timeout: 30000 });
    const rows = await page.evaluate(() => Array.from(document.querySelectorAll('#aix-rows tr')).map((tr) => tr.textContent));
    check('the execution list shows this model', rows.some((r) => r.indexOf(MODEL) !== -1), rows.slice(0, 3).join(' || '));
    const ex = await api('/ai-executions?limit=20&model=' + encodeURIComponent(MODEL) + '&status=succeeded');
    const fresh = (ex.items || []).filter((i) => new Date(i.started_at || i.created_at) >= startedAt);
    check('a succeeded execution of this model started during this run', fresh.length >= 1, fresh.length);
    check('no page errors', errors.length === 0, errors.join(' | '));
  } finally {
    if (accountId) {
      try { await api('/ai-center/accounts/' + accountId + '/credential', { method: 'DELETE' }); console.log('credential revoked for ' + STAMP); }
      catch (e) { console.error('Could not revoke the test credential; revoke it in AI Center: ' + STAMP); }
    }
    await browser.close();
    server.close();
  }
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(String(e && e.stack || e).split(KEY || 'no-key-set').join('[key]')); process.exit(2); });
