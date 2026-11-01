#!/usr/bin/env node
/*
 * Browser checks for the Visibility screens (Step 10).
 *   Sample: the report's charts, map, live strip, stats, time tabs and
 *           exports are hidden as debt (V5-visibility-detail-aggregates);
 *           the per-platform table (V5-visibility-platform-breakdown); on
 *           AI access the per-agent Access column and its warning
 *           (V5-access-agent-decision) and the Edit/Change links
 *           (V5-access-policy-edit).
 *   Live:   AI Visibility = GET /visibility/summary + GET /telemetry/agents;
 *           the full report = GET /visibility/observations (one call), a row
 *           opens from the loaded list with no further request; AI access =
 *           GET /telemetry/access-policies + GET /telemetry/agents. Enum
 *           labels, unknown values shown as sent, empty lists, 500 with
 *           Retry, Persian over live content.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/visibility.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-visibility';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069);
const iso = (s) => FSI + s + PDI;
const FA = {
  anyAiCrawler: [0x647, 0x631, 0x20, 0x62E, 0x632, 0x646, 0x62F, 0x647, 0x654, 0x20, 0x647, 0x648, 0x634, 0x20, 0x645, 0x635, 0x646, 0x648, 0x639, 0x6CC],
  training: [0x622, 0x645, 0x648, 0x632, 0x634, 0x20, 0x645, 0x62F, 0x644],
  paid: [0x67E, 0x648, 0x644, 0x6CC],
  noReason: [0x62F, 0x644, 0x6CC, 0x644, 0x6CC, 0x20, 0x62F, 0x627, 0x62F, 0x647, 0x20, 0x646, 0x634, 0x62F, 0x647],
  terms: [0x634, 0x631, 0x627, 0x6CC, 0x637],
  rulesNote: [0x7B, 0x6E, 0x7D, 0x20, 0x642, 0x627, 0x639, 0x62F, 0x647, 0x2E, 0x20, 0x646, 0x62E, 0x633, 0x62A, 0x6CC, 0x646, 0x20, 0x642, 0x627, 0x639, 0x62F, 0x647, 0x200C, 0x627, 0x6CC, 0x20, 0x6A9, 0x647, 0x20, 0x645, 0x646, 0x637, 0x628, 0x642, 0x20, 0x634, 0x648, 0x62F, 0x20, 0x627, 0x639, 0x645, 0x627, 0x644, 0x20, 0x645, 0x6CC, 0x200C, 0x634, 0x648, 0x62F, 0x20, 0x648, 0x20, 0x627, 0x631, 0x632, 0x6CC, 0x627, 0x628, 0x6CC, 0x20, 0x645, 0x62A, 0x648, 0x642, 0x641, 0x20, 0x645, 0x6CC, 0x200C, 0x634, 0x648, 0x62F, 0x61B, 0x20, 0x6A9, 0x644, 0x627, 0x6CC, 0x646, 0x62A, 0x6CC, 0x20, 0x6A9, 0x647, 0x20, 0x628, 0x627, 0x20, 0x647, 0x6CC, 0x686, 0x20, 0x642, 0x627, 0x639, 0x62F, 0x647, 0x200C, 0x627, 0x6CC, 0x20, 0x645, 0x646, 0x637, 0x628, 0x642, 0x20, 0x646, 0x634, 0x648, 0x62F, 0x20, 0x627, 0x62C, 0x627, 0x632, 0x647, 0x20, 0x645, 0x6CC, 0x200C, 0x6CC, 0x627, 0x628, 0x62F, 0x20, 0x648, 0x20, 0x628, 0x647, 0x200C, 0x639, 0x646, 0x648, 0x627, 0x646, 0x20, 0xAB, 0x67E, 0x6CC, 0x6A9, 0x631, 0x628, 0x646, 0x62F, 0x6CC, 0x200C, 0x646, 0x634, 0x62F, 0x647, 0xBB, 0x20, 0x62B, 0x628, 0x62A, 0x20, 0x645, 0x6CC, 0x200C, 0x634, 0x648, 0x62F, 0x2E],
  mentioned: [0x646, 0x627, 0x645, 0x20, 0x628, 0x631, 0x62F, 0x647, 0x20, 0x634, 0x62F],
  aiCrawler: [0x62E, 0x632, 0x646, 0x62F, 0x647, 0x654, 0x20, 0x647, 0x648, 0x634, 0x20, 0x645, 0x635, 0x646, 0x648, 0x639, 0x6CC, 0x20, 0x28, 0x646, 0x645, 0x627, 0x6CC, 0x647, 0x200C, 0x633, 0x627, 0x632, 0x6CC, 0x29],
  detected: [0x634, 0x646, 0x627, 0x633, 0x627, 0x6CC, 0x6CC, 0x200C, 0x634, 0x62F, 0x647],
  answersTitle: [0x633, 0x6A9, 0x648, 0x647, 0x627, 0x6CC, 0x20, 0x647, 0x648, 0x634, 0x20, 0x645, 0x635, 0x646, 0x648, 0x639, 0x6CC, 0x20, 0x62F, 0x631, 0x628, 0x627, 0x631, 0x647, 0x654, 0x20, 0x634, 0x645, 0x627, 0x20, 0x686, 0x647, 0x20, 0x67E, 0x627, 0x633, 0x62E, 0x6CC, 0x20, 0x645, 0x6CC, 0x200C, 0x62F, 0x647, 0x646, 0x62F],
  observation: [0x645, 0x634, 0x627, 0x647, 0x62F, 0x647],
  test: [0x622, 0x632, 0x645, 0x648, 0x646],
  brandQuestion: [0x67E, 0x631, 0x633, 0x634, 0x20, 0x62F, 0x631, 0x628, 0x627, 0x631, 0x647, 0x654, 0x20, 0x628, 0x631, 0x646, 0x62F],
};
const F = (k) => String.fromCharCode(...FA[k]);

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const sig = (present, absent, notChecked) => ({ present, absent, not_checked: notChecked, checked: present + absent });
const DATA = {
  summary: { observation_count: 7, as_of: '2026-10-30T10:00:00Z', by_collection_method: { manual_paste: 7 },
    signals: { mentioned: sig(3, 2, 2), cited: sig(1, 4, 2), recommended: sig(0, 5, 2), product_present: sig(2, 3, 2), url_present: sig(0, 0, 7) },
    caveats: ['Only the prompts listed were asked.'] },
  agents: [
    { id: 'a1', signature: 'GPTBot', display_name: 'GPTBot', vendor: 'OpenAI', actor_type: 'ai_crawler', declared_purpose: 'training',
      confidence: 'detected', observation_count: 412 },
    { id: 'a2', signature: 'odd-bot', display_name: 'odd-bot', vendor: null, actor_type: 'robot_x', declared_purpose: 'unknown',
      confidence: 'probable', observation_count: 3 },
  ],
  policies: [
    { id: 'p1', agent_id: 'a1', actor_type: null, purpose: null, tier: 'forbidden', specificity: 3, reason: 'No corpus collection.', terms_url: null },
    { id: 'p2', agent_id: null, actor_type: 'ai_crawler', purpose: 'training', tier: 'paid', specificity: 2, reason: null,
      terms_url: 'https://shop.test/terms' },
    { id: 'p3', agent_id: null, actor_type: null, purpose: null, tier: 'free', specificity: 0, reason: null, terms_url: null },
  ],
  observations: [
    { id: 'o1', platform: 'chatgpt', test_type: 'brand_query', prompt: 'What is taranjabin?', response: 'A manna from Iran.',
      mentioned: 'present', cited: 'absent', recommended: 'not_checked', product_present: 'present', url_present: 'not_checked',
      collection_method: 'manual_paste', platform_model: 'gpt-x', tested_at: '2026-10-20T09:00:00Z' },
    { id: 'o2', platform: 'other', test_type: 'odd_test', prompt: 'Best saffron?', response: null,
      mentioned: 'absent', cited: 'absent', recommended: 'absent', product_present: 'absent', url_present: 'absent',
      collection_method: 'imported', platform_model: null, tested_at: '2026-10-21T09:00:00Z' },
  ],
};

function installMock(data) {
  window.__requests = []; window.__data = data; window.__fail = null;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  const page = (items) => reply({ items, total: items.length, limit: 200, offset: 0 });
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (window.__fail && p.indexOf(window.__fail) === 0) return reply({}, 500);
    const d = window.__data;
    if (p === '/visibility/summary') return reply(d.summary);
    if (p === '/telemetry/agents?limit=200') return page(d.agents);
    if (p === '/telemetry/access-policies?limit=200') return page(d.policies);
    if (p === '/visibility/observations?limit=50&sort_by=tested_at&sort_dir=desc') return reply({ items: d.observations, total: 9, limit: 50, offset: 0 });
    return reply({ detail: 'Not found' }, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(150);
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await settle(); };
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /\/visibility\/|\/telemetry\/(agents|access-policies)/.test(r)));
  const shown = (sel) => page.evaluate((s) => Array.from(document.querySelectorAll(s)).map((e) => getComputedStyle(e).display !== 'none'), sel);
  // A live screen: its cards (title, note, rows as cell texts), the message, whether any sample content shows.
  const view = (id) => page.evaluate((id) => {
    const s = document.getElementById(id), body = s.querySelector(':scope > .vis-live');
    if (!body) return null;
    const box = body.querySelector(':scope > .know-status'), act = box.querySelector('button');
    return {
      cards: Array.from(body.querySelectorAll(':scope > .card:not(.vis-detail)')).filter((c) => !c.hidden).map((c) => ({
        title: c.querySelector('.card__title').textContent,
        note: (c.querySelector('.vis-note') || {}).textContent,
        rows: Array.from(c.querySelectorAll('tbody tr')).map((tr) => Array.from(tr.cells).map((td) => td.textContent)),
      })),
      state: box.dataset.state, message: box.querySelector('p').textContent, action: act && !act.hidden ? act.textContent : null,
      caveats: Array.from(body.querySelectorAll('.vis-caveats li')).map((li) => li.textContent),
      sampleShown: Array.from(s.children).some((c) => !c.hasAttribute('data-live-keep') && !c.classList.contains('live-panel')
        && !c.classList.contains('page-header') && !c.classList.contains('breadcrumbs') && getComputedStyle(c).display !== 'none'),
    };
  }, id);
  const detail = () => page.evaluate(() => {
    const d = document.getElementById('vis-observation');
    if (!d || d.hidden) return null;
    return { title: d.querySelector('.card__title').textContent, question: d.querySelector('.vis-question').textContent,
      facts: Array.from(d.querySelectorAll('dt')).map((dt) => [dt.textContent, dt.nextElementSibling.textContent]),
      answer: (d.querySelector('.vis-answer') || d.querySelector('p.not-available')).textContent, focused: document.activeElement === d };
  });

  // Sample mode (before any connection).
  check('sample: the report\'s seven no-backend blocks are hidden as debt',
    await shown('#screen-visibility-detail [data-debt-hidden="V5-visibility-detail-aggregates"]'), [false, false, false, false, false, false, false]);
  check('sample: the per-platform table is hidden as debt', await shown('#screen-visibility [data-debt-hidden="V5-visibility-platform-breakdown"]'), [false]);
  check('sample: Access column (8 rows + header) and its warning hidden; Edit/Change hidden',
    [(await shown('#screen-access [data-debt-hidden="V5-access-agent-decision"]')).filter((x) => !x).length,
      (await shown('#screen-access [data-debt-hidden="V5-access-policy-edit"]')).filter((x) => !x).length], [10, 12]);

  // Live: connecting loads each screen once, in parallel per screen.
  await page.evaluate(installMock, DATA);
  await connect();
  check('connect: summary + agents, observations, policies + agents', await requests(), ['GET /visibility/summary', 'GET /telemetry/agents?limit=200',
    'GET /visibility/observations?limit=50&sort_by=tested_at&sort_dir=desc', 'GET /telemetry/access-policies?limit=200', 'GET /telemetry/agents?limit=200']);
  let v = await view('screen-visibility');
  check('visibility: the answers card (count, signals; no score)', v.cards[0], { title: 'How AI platforms answer about you',
    note: '7 observations recorded. Each signal is counted on its own; there is no combined score.',
    rows: [['Mentioned', '3', '2', '2'], ['Cited', '1', '4', '2'], ['Recommended', '0', '5', '2'], ['Product shown', '2', '3', '2'], ['URL present', '0', '0', '7']] });
  check('visibility: caveats shown as sent', v.caveats, ['Only the prompts listed were asked.']);
  check('visibility: agents (operator, type, confidence, count; unknown type as sent)', v.cards[1], { title: 'Who is actually visiting your site',
    note: '2 automated clients seen. Human visitors are never listed here.',
    rows: [['GPTBotOpenAI', 'AI crawler (indexing)', 'Detected', '412'], ['odd-botOperator unknown', 'robot_x', 'Probable', '3']] });
  check('visibility: the sample content is hidden, no message', [v.sampleShown, v.state], [false, '']);

  // The full report: one list call; a row opens from the loaded list.
  let before = (await requests()).length;
  await go('#screen-visibility-detail');
  check('report: one request on visit', (await requests()).slice(before), ['GET /visibility/observations?limit=50&sort_by=tested_at&sort_dir=desc']);
  v = await view('screen-visibility-detail');
  check('report: rows (platform, question, signals, date)', [v.cards[0].note, v.cards[0].rows],
    ['The latest 2 of 9 observations. Open one to read the question and the answer as recorded.',
      [['ChatGPT', 'What is taranjabin?', 'Present', 'Absent', 'Not checked', '20 Oct 2026', 'Open'],
        ['Other platform', 'Best saffron?', 'Absent', 'Absent', 'Absent', '21 Oct 2026', 'Open']]]);
  before = (await requests()).length;
  await page.click('#screen-visibility-detail tbody tr:first-child button'); await settle();
  let d = await detail();
  check('report: Open shows the observation, focused, with no request', [d.title, d.question, d.facts.slice(0, 4), d.facts.slice(5), d.answer, d.focused,
    (await requests()).length - before], ['Observation', 'What is taranjabin?',
    [['Platform', 'ChatGPT'], ['Test', 'Brand question'], ['Collected', 'Pasted by hand'], ['Model', 'gpt-x']],
    [['Mentioned', 'Present'], ['Cited', 'Absent'], ['Recommended', 'Not checked'], ['Product shown', 'Present'], ['URL present', 'Not checked']],
    'A manna from Iran.', true, 0]);
  await page.click('#screen-visibility-detail tbody tr:nth-child(2) button'); await settle();
  d = await detail();
  check('report: no answer, no model, an unknown test as sent', [d.facts[1], d.facts[3], d.answer],
    [['Test', 'odd_test'], ['Model', 'Not recorded'], 'No answer was recorded.']);

  // AI access.
  before = (await requests()).length;
  await go('#screen-access');
  check('access: policies + agents on visit', (await requests()).slice(before), ['GET /telemetry/access-policies?limit=200', 'GET /telemetry/agents?limit=200']);
  v = await view('screen-access');
  check('access: rules in the order sent (agent, actor type, catch-all)', v.cards[0], { title: 'Rules, most specific first',
    note: '3 rules. The first rule that matches wins and evaluation stops; a client no rule matches is allowed and recorded as Not configured.',
    rows: [['GPTBot', 'Any', 'Forbidden', 'No corpus collection.'], ['Any AI crawler', 'Training', 'Paid', 'No reason given Terms'],
      ['Any automated client', 'Any', 'Free', 'No reason given']] });
  check('access: the terms link', await page.evaluate(() => document.querySelector('#screen-access .vis-live a[target="_blank"]').href), 'https://shop.test/terms');
  check('access: every agent seen', v.cards[1], { title: 'Every agent seen', note: '2 distinct clients. There is no filter that hides unrecognised ones.',
    rows: [['GPTBotOpenAI', 'AI crawler (indexing)', 'Training', 'Detected', '412'], ['odd-botOperator unknown', 'robot_x', 'Not declared', 'Probable', '3']] });

  // Persian over live content.
  await lang('fa');
  v = await view('screen-access');
  check('fa: access rule subject, purpose, badge, reason fallback', v.cards[0].rows[1], [F('anyAiCrawler'), F('training'), F('paid'), F('noReason') + ' ' + F('terms')]);
  check('fa: access note with Persian digits', v.cards[0].note, F('rulesNote').replace('{n}', fa(0x6F3)));
  await go('#screen-visibility');
  v = await view('screen-visibility');
  check('fa: visibility signal row and agent row', [v.cards[0].rows[0], v.cards[1].rows[0].slice(1, 3)],
    [[F('mentioned'), fa(0x6F3), fa(0x6F2), fa(0x6F2)], [F('aiCrawler'), F('detected')]]);
  check('fa: visibility card title', v.cards[0].title, F('answersTitle'));
  await go('#screen-visibility-detail');
  await page.click('#screen-visibility-detail tbody tr:first-child button'); await settle();
  d = await detail();
  check('fa: observation facts', [d.title, d.facts[1], d.facts[5][0]], [F('observation'), [F('test'), F('brandQuestion')], F('mentioned')]);
  await lang('en');
  check('back to English', (await detail()).title, 'Observation');

  // Failure, Retry, empty lists.
  await page.evaluate(() => { window.__fail = '/telemetry/access-policies'; });
  await go('#screen-access');
  v = await view('screen-access');
  check('500: the message and Retry; no cards', [v.state, v.message, v.action, v.cards.length],
    ['error', 'Could not load AI access (' + iso('HTTP 500') + ').', 'Retry', 0]);
  await page.evaluate(() => { window.__fail = null; window.__data.policies = []; window.__data.agents = []; });
  await page.click('#screen-access .vis-live > .know-status button'); await settle();
  v = await view('screen-access');
  check('Retry reloads; empty lists say so', [v.state, v.cards.map((c) => c.rows)], ['', [[['No rules yet.']], [['No automated clients seen yet.']]]]);
  check('no page errors', errors, []);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
