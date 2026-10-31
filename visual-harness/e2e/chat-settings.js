#!/usr/bin/env node
/*
 * Browser checks for the Chat settings screen (Step 9C).
 *   Not connected: data-live-wired, the note shown, the form hidden.
 *   Live:   GET /chat/settings fills the form (one settings request), the
 *           policy list and the topic checkboxes; the state line (ON, with
 *           the no-resource warning; saved but OFF; never configured); a
 *           missing required field sends nothing; Save sends ONE PUT with the
 *           form's values and repaints from the reply; a server refusal shows
 *           its own message; no topics; Persian over live content.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/chat-settings.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-chat-settings';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069);
const iso = (s) => FSI + s + PDI;
const FA = {
  on: fa(0x6AF, 0x641, 0x62A, 0x200C, 0x648, 0x6AF, 0x648, 0x6CC, 0x20, 0x648, 0x628, 0x200C, 0x633, 0x627, 0x6CC, 0x62A, 0x20, 0x631, 0x648, 0x634, 0x646,
    0x20, 0x627, 0x633, 0x62A, 0x2E),
  savedOff: fa(0x630, 0x62E, 0x6CC, 0x631, 0x647, 0x20, 0x634, 0x62F, 0x60C, 0x20, 0x627, 0x645, 0x627, 0x20, 0x6AF, 0x641, 0x62A, 0x200C, 0x648, 0x6AF,
    0x648, 0x6CC, 0x20, 0x648, 0x628, 0x200C, 0x633, 0x627, 0x6CC, 0x62A, 0x20, 0x62E, 0x627, 0x645, 0x648, 0x634, 0x20, 0x627, 0x633, 0x62A, 0x2E),
  saved: fa(0x630, 0x62E, 0x6CC, 0x631, 0x647, 0x20, 0x634, 0x62F, 0x2E, 0x20, 0x6AF, 0x641, 0x62A, 0x200C, 0x648, 0x6AF, 0x648, 0x6CC, 0x20, 0x648, 0x628,
    0x200C, 0x633, 0x627, 0x6CC, 0x62A, 0x20, 0x627, 0x632, 0x20, 0x67E, 0x631, 0x633, 0x634, 0x20, 0x628, 0x639, 0x62F, 0x6CC, 0x20, 0x627, 0x6CC, 0x646,
    0x20, 0x62A, 0x646, 0x638, 0x6CC, 0x645, 0x627, 0x62A, 0x20, 0x631, 0x627, 0x20, 0x628, 0x647, 0x20, 0x6A9, 0x627, 0x631, 0x20, 0x645, 0x6CC, 0x200C,
    0x628, 0x631, 0x62F, 0x2E),
  chatLabel: fa(0x6AF, 0x641, 0x62A, 0x200C, 0x648, 0x6AF, 0x648, 0x20, 0x62F, 0x631, 0x20, 0x648, 0x628, 0x200C, 0x633, 0x627, 0x6CC, 0x62A),
};
const WARN = 'No AI resource is chosen, so questions are answered as "provider unavailable" rather than guessed.';

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const SETTINGS = { enabled: true, allowed_knowledge_object_ids: ['k1'], online_research: 'ask_every_time', show_citations: true,
  collect_feedback: false, routing_policy_id: null, max_output_tokens: 800, context_token_budget: 12000, retention_days: null,
  messages_per_user_per_day: 20, max_cost_per_message: 0.05, configured: true, updated_at: '2026-10-30T10:00:00Z' };

function installMock(settings) {
  window.__requests = []; window.__sent = []; window.__settings = settings; window.__putStatus = 200;
  window.__topics = [{ id: 'k1', canonical_name: 'Taranjabin', object_type: 'plant' }, { id: 'k2', canonical_name: 'Saffron', object_type: 'plant' }];
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (p === '/chat/settings' && method === 'GET') return reply(window.__settings);
    if (p === '/chat/settings' && method === 'PUT') {
      const body = JSON.parse(opt.body); window.__sent.push(body);
      if (window.__putStatus !== 200) return reply({ detail: 'max_output_tokens must be at most 32000' }, window.__putStatus);
      window.__settings = Object.assign({}, window.__settings, body, { configured: true });
      return reply(window.__settings);
    }
    if (p.indexOf('/ai-center/routing-policies?') === 0) return reply({ items: [{ id: 'p1', name: 'Cheap first', mode: 'fallback' }], total: 1 });
    if (p === '/knowledge?limit=200') return reply({ items: window.__topics, total: window.__topics.length });
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
  const settingsRequests = () => page.evaluate(() => (window.__requests || []).filter((r) => / \/chat\/settings$/.test(r)));
  const sent = () => page.evaluate(() => window.__sent.splice(0));
  const view = () => page.evaluate(() => {
    const $ = (id) => document.getElementById(id);
    return {
      form: ['cs-enabled', 'cs-research', 'cs-policy', 'cs-daily', 'cs-out', 'cs-ctx', 'cs-cost', 'cs-retention', 'cs-citations', 'cs-feedback'].map((id) => $(id).value),
      policies: Array.from($('cs-policy').options).map((o) => o.value),
      topics: Array.from(document.querySelectorAll('#cs-topics .cs-topic')).map((c) => [c.value, c.checked, c.nextElementSibling.textContent]),
      noTopics: document.querySelector('#cs-topics .aic-empty') ? document.querySelector('#cs-topics .aic-empty').textContent : null,
      state: $('cs-state').textContent,
      msg: [$('cs-msg').textContent, $('cs-msg').className],
      label: document.querySelector('#screen-chat-settings .kx-form .field__label').textContent,
    };
  });

  // Not connected.
  check('data-live-wired; the note shown, the form hidden', await page.evaluate(() => [
    document.getElementById('screen-chat-settings').hasAttribute('data-live-wired'),
    !document.querySelector('#screen-chat-settings .cs-note').hidden, document.querySelector('#screen-chat-settings .cs-body').hidden]),
    [true, true, true]);

  // Live.
  await page.evaluate(installMock, SETTINGS);
  await connect();
  check('one settings request', await settingsRequests(), ['GET /chat/settings']);
  let v = await view();
  check('the form shows the settings', v.form, ['true', 'ask_every_time', '', '20', '800', '12000', '0.05', '', 'true', 'false']);
  check('policies and topics (an allowed topic is checked)', [v.policies, v.topics],
    [['', 'p1'], [['k1', true, 'Taranjabin (plant)'], ['k2', false, 'Saffron (plant)']]]);
  check('state: ON, with the no-resource warning', v.state, 'The website chat is ON. ' + WARN);

  // A missing required field sends nothing.
  await page.fill('#cs-out', '');
  await page.click('#cs-save'); await settle();
  check('missing answer length: said, no PUT', [(await view()).msg, await sent()],
    [['The answer length and the knowledge budget are both required.', 'otp-message otp-message--error'], []]);

  // Save: one PUT with the form's values, then the reply repaints the form.
  await page.fill('#cs-out', '1000');
  await page.selectOption('#cs-enabled', 'false');
  await page.check('#cs-topics .cs-topic[value="k2"]');
  await page.fill('#cs-retention', '30');
  let before = (await settingsRequests()).length;
  await page.click('#cs-save'); await settle();
  check('Save: ONE PUT', (await settingsRequests()).slice(before), ['PUT /chat/settings']);
  check('the PUT body', await sent(), [{ enabled: false, online_research: 'ask_every_time', routing_policy_id: null,
    allowed_knowledge_object_ids: ['k1', 'k2'], messages_per_user_per_day: 20, max_output_tokens: 1000, context_token_budget: 12000,
    max_cost_per_message: 0.05, retention_days: 30, show_citations: true, collect_feedback: false }]);
  v = await view();
  check('saved: the message and the state', [v.msg, v.state],
    [['Saved. The website chat uses these settings from the next question.', 'otp-message'], 'Saved, but the website chat is OFF.']);
  check('Save is enabled again', await page.$eval('#cs-save', (b) => b.disabled), false);

  // A server refusal shows the server's own message.
  await page.evaluate(() => { window.__putStatus = 422; });
  await page.click('#cs-save'); await settle();
  check('422: the server message', (await view()).msg, [iso('max_output_tokens must be at most 32000'), 'otp-message otp-message--error']);
  await page.evaluate(() => { window.__putStatus = 200; });

  // Never configured, and a workspace with no topics (Refresh reloads both).
  await page.evaluate(() => { window.__settings = Object.assign({}, window.__settings, { configured: false, enabled: false }); window.__topics = []; });
  await page.click('#cs-refresh'); await settle();
  v = await view();
  check('never configured; no topics', [v.state, v.noTopics, v.msg[0]], ['Never configured: the website chat is OFF for this workspace.',
    'This workspace has no knowledge topics yet. Add sources and build a topic first.', '']);

  // Persian over live content (an identity entry would hang here).
  await page.evaluate(() => { window.__settings = Object.assign({}, window.__settings, { configured: true, enabled: true, routing_policy_id: 'p1' }); });
  await page.click('#cs-refresh'); await settle();
  await lang('fa');
  v = await view();
  check('fa: a field label and the state', [v.label, v.state], [FA.chatLabel, FA.on]);
  await page.selectOption('#cs-enabled', 'false');
  await page.click('#cs-save'); await settle();
  v = await view();
  check('fa: saved message and state', [v.msg[0], v.state], [FA.saved, FA.savedOff]);
  await lang('en');
  check('back to English', (await view()).state, 'Saved, but the website chat is OFF.');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
