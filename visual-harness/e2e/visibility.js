#!/usr/bin/env node
/*
 * Browser checks for the Visibility screens (Step 10).
 *   Sample: the report's map, breakdown, live strip, time tabs and
 *           exports stay hidden as debt (V5-visibility-detail-aggregates);
 *           its stats and over-time chart show.
 *   Report stats: one GET /visibility/aggregates per range (28 days on
 *           visit; a range tab asks again); the four stats with their notes;
 *           one chart column per day; Not measured when no time was recorded;
 *           the breakdown cards (top countries by name in the page's language,
 *           actor types, top pages; at most 10 rows; None in this range.);
 *           the per-platform table (V5-visibility-platform-breakdown); on
 *           AI access the per-agent Access column and its warning
 *           (V5-access-agent-decision). The sample Edit/Change links say to
 *           connect first.
 *   Access rules (V5-access-policy-edit): owner/admin get Change and Delete;
 *           Change = one PUT with the rule's own subject and purpose; a bad
 *           terms link is refused before sending; Delete asks first, then one
 *           DELETE; a viewer gets no actions; 403 says who may.
 *   New rule (V5-access-policy-create): owner/admin get New rule; the same
 *           editor with a subject (actor types, then the agents seen) and a
 *           purpose, no Not configured; a subject and purpose that already
 *           have a rule are refused before sending; one PUT; Rule added.
 *   Live:   AI Visibility = GET /visibility/summary + GET /telemetry/agents;
 *           the full report = GET /visibility/observations (one call), a row
 *           opens from the loaded list with no further request; AI access =
 *           GET /telemetry/access-policies + GET /telemetry/agents. Enum
 *           labels, unknown values shown as sent, empty lists, 500 with
 *           Retry, Persian over live content.
 * Runs on file:// with AI Core mocked in the page and every request
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
  topCountries: [0x6A9, 0x634, 0x648, 0x631, 0x647, 0x627, 0x6CC, 0x20, 0x67E, 0x631, 0x62F, 0x631, 0x62E, 0x648, 0x627, 0x633, 0x62A],
  iran: [0x627, 0x6CC, 0x631, 0x627, 0x646],
  newRule: [0x642, 0x627, 0x639, 0x62F, 0x647, 0x654, 0x20, 0x62C, 0x62F, 0x6CC, 0x62F],
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
  uaClaim: [0x633, 0x631, 0x622, 0x6CC, 0x646, 0x62F, 0x20, 0x2068, 0x55, 0x73, 0x65, 0x72, 0x2D, 0x41, 0x67, 0x65, 0x6E, 0x74, 0x2069, 0x20, 0x627, 0x62F, 0x639, 0x627, 0x6CC, 0x6CC, 0x20, 0x627, 0x633, 0x62A, 0x20, 0x6A9, 0x647, 0x20, 0x62F, 0x631, 0x62E, 0x648, 0x627, 0x633, 0x62A, 0x20, 0x62F, 0x631, 0x628, 0x627, 0x631, 0x647, 0x654, 0x20, 0x62E, 0x648, 0x62F, 0x634, 0x20, 0x645, 0x6CC, 0x200C, 0x6A9, 0x646, 0x62F, 0x60C, 0x20, 0x646, 0x647, 0x20, 0x647, 0x648, 0x6CC, 0x62A, 0x6CC, 0x20, 0x62A, 0x623, 0x6CC, 0x6CC, 0x62F, 0x634, 0x62F, 0x647, 0x20, 0x2014, 0x20, 0x647, 0x631, 0x20, 0x6A9, 0x633, 0x6CC, 0x20, 0x645, 0x6CC, 0x200C, 0x62A, 0x648, 0x627, 0x646, 0x62F, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x631, 0x627, 0x20, 0x628, 0x641, 0x631, 0x633, 0x62A, 0x62F, 0x3A],
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
  aggregates: { days: 28, since: '2026-09-25T10:00:00Z', until: '2026-10-23T10:00:00Z', platform_observations: 9,
    automated_requests: 120, unclassified_requests: 3, countries_reached: 2, top_country: { country: 'IR', requests: 80 },
    requests_without_country: 5, mean_dwell_ms: 161000, dwell_samples: 704,
    by_day: [{ day: '2026-10-21', observations: 2, requests: 40 }, { day: '2026-10-22', observations: 0, requests: 80 },
      { day: '2026-10-23', observations: 7, requests: 0 }],
    by_country: [['IR', 80], ['DE', 30], ['US', 5], ['FR', 4], ['CA', 3], ['IQ', 2], ['AF', 2], ['JP', 1], ['IT', 1], ['ES', 1], ['XX', 1]]
      .map(([country, requests]) => ({ country, requests })),
    by_actor_type: [{ key: 'ai_crawler', requests: 70 }, { key: 'search_crawler', requests: 40 }, { key: 'robot_x', requests: 10 }],
    top_pages: [{ key: '/products/taranjabin', requests: 60 }, { key: '/', requests: 20 }] },
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
    window.__requests.push(method + ' ' + p + (opt && opt.body ? ' ' + opt.body : ''));
    if (p === '/auth/me') return reply({ user: { name: 'Owner', email: 'o@shop.test', role: window.__role || 'admin' }, organization: { name: 'Shop' } });
    if (p === '/telemetry/access-policies' && method === 'PUT') {
      if (window.__denyWrite) return reply({ error: { message: 'Insufficient role' } }, 403);
      return reply(Object.assign({ id: 'px', specificity: 2 }, JSON.parse(opt.body)));
    }
    if (/^\/telemetry\/access-policies\/[^/?]+$/.test(p) && method === 'DELETE') return Promise.resolve(new Response(null, { status: 204 }));
    if (window.__fail && p.indexOf(window.__fail) === 0) return reply({}, 500);
    const d = window.__data;
    if (p === '/visibility/summary') return reply(d.summary);
    const agg = p.match(/^\/visibility\/aggregates\?days=(\d+)$/);
    if (agg) return reply(Object.assign({}, d.aggregates, { days: Number(agg[1]) }));
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
  check('sample: the report\'s five no-backend blocks stay hidden as debt (exports, range tabs, live strip, map, breakdown)',
    await shown('#screen-visibility-detail [data-debt-hidden="V5-visibility-detail-aggregates"]'), [false, false, false, false, false]);
  check('sample: the stats and the over-time chart show', await page.evaluate(() => Array.from(document.querySelectorAll('#screen-visibility-detail > .stat-grid, #screen-visibility-detail > .card:not(.live-panel)'))
    .filter((e) => getComputedStyle(e).display !== 'none').map((e) => (e.querySelector('.card__title') || e.querySelector('.stat__label')).textContent.trim())),
    ['Platform observations', 'Over time']);
  check('sample: the per-platform table is hidden as debt', await shown('#screen-visibility [data-debt-hidden="V5-visibility-platform-breakdown"]'), [false]);
  check('sample: Access column (8 rows + header) and its warning hidden; no Edit/Change debt left',
    [(await shown('#screen-access [data-debt-hidden="V5-access-agent-decision"]')).filter((x) => !x).length,
      (await shown('#screen-access [data-debt-hidden="V5-access-policy-edit"]')).length,
      await page.evaluate(() => document.querySelectorAll('#screen-access [data-access-change]').length)], [10, 0, 12]);
  await page.evaluate(() => document.querySelector('#screen-access [data-access-change]').click()); await settle();
  check('sample: Change says to connect first', await page.evaluate(() => [document.getElementById('save-toast').open,
    document.getElementById('save-toast-text').textContent]), [true, 'Connect to AI Core to change access rules.']);
  await page.evaluate(() => document.getElementById('save-toast-close').click()); await settle();

  // Live: connecting loads each screen once, in parallel per screen.
  await page.evaluate(installMock, DATA);
  await connect();
  check('connect: summary + agents, observations, policies + agents', await requests(), ['GET /visibility/summary', 'GET /telemetry/agents?limit=200',
    'GET /visibility/observations?limit=50&sort_by=tested_at&sort_dir=desc', 'GET /visibility/aggregates?days=28', 'GET /telemetry/access-policies?limit=200', 'GET /telemetry/agents?limit=200']);
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
  check('report: observations and aggregates on visit (28 days)', (await requests()).slice(before),
    ['GET /visibility/observations?limit=50&sort_by=tested_at&sort_dir=desc', 'GET /visibility/aggregates?days=28']);
  const stats = () => page.evaluate(() => {
    const r = document.getElementById('vis-report');
    return { tab: (r.querySelector('[role=tab][aria-selected=true]') || {}).textContent, window: r.querySelector('.vis-note').textContent,
      stats: Array.from(r.querySelectorAll('.stat')).map((s) => [s.querySelector('.stat__label').textContent, s.querySelector('.stat__value').textContent,
        s.querySelector('.stat__note').textContent]),
      bars: Array.from(document.querySelectorAll('#vis-chart .vis-chart__day')).map((c) => [c.children[0].style.blockSize, c.children[1].style.blockSize]) };
  });
  let sv = await stats();
  check('report: the 28-day tab, the window, the four stats with their notes', [sv.tab, sv.window, sv.stats], ['28 days',
    'From 25 Sept 2026 to 23 Oct 2026. Counts of what was stored; nothing here is estimated.',
    [['Platform observations', '9', ''], ['Automated requests', '120', 'Not counted: 3 unclassified requests'],
      ['Countries reached', '2', 'Most requests: ' + iso('IR')], ['Mean time on page', '2m 41s', 'from 704 measured views']]]);
  check('report: one chart column per day, each series scaled to its own highest day', sv.bars,
    [['29%', '50%'], ['0%', '100%'], ['100%', '0%']]);
  v = await view('screen-visibility-detail');
  check('report: breakdown cards after the chart: top countries (name and code, first 10), actor types, top pages', v.cards.slice(1, 5).map((c) => [c.title, c.note, c.rows]),
    [['Over time', 'Two different sources on one timeline, each scaled to its own highest day; they are never added together.', []],
      ['Top countries', 'Without a country: 5 requests', [['Iran (' + iso('IR') + ')', '80'], ['Germany (' + iso('DE') + ')', '30'], ['United States (' + iso('US') + ')', '5'],
        ['France (' + iso('FR') + ')', '4'], ['Canada (' + iso('CA') + ')', '3'], ['Iraq (' + iso('IQ') + ')', '2'], ['Afghanistan (' + iso('AF') + ')', '2'],
        ['Japan (' + iso('JP') + ')', '1'], ['Italy (' + iso('IT') + ')', '1'], ['Spain (' + iso('ES') + ')', '1']]],
      ['Actor types', '', [['AI crawler (indexing)', '70'], ['Search crawler', '40'], ['robot_x', '10']]],
      ['Top pages', '', [['/products/taranjabin', '60'], ['/', '20']]]]);
  check('report: the three breakdown cards share one row on a wide screen', await page.evaluate(() =>
    new Set(Array.from(document.querySelectorAll('#screen-visibility-detail .vis-break')).map((c) => Math.round(c.getBoundingClientRect().top))).size), 1);
  before = (await requests()).length;
  await page.evaluate(() => { window.__data.aggregates.mean_dwell_ms = null; window.__data.aggregates.dwell_samples = 0; window.__data.aggregates.top_country = null;
    window.__data.aggregates.by_actor_type = []; window.__data.aggregates.requests_without_country = 0;
    Array.from(document.querySelectorAll('#vis-report [role=tab]')).find((t) => t.textContent === '7 days').click(); }); await settle(); await settle();
  sv = await stats();
  check('report: a range tab asks for that range; no time recorded = Not measured; no country = says so', [(await requests()).slice(before).filter((x) => /aggregates/.test(x)),
    sv.tab, sv.stats[3], sv.stats[2][2]], [['GET /visibility/aggregates?days=7'], '7 days', ['Mean time on page', 'Not measured', ''], 'No country was reported']);
  v = await view('screen-visibility-detail');
  check('report: an empty breakdown says so; no country note when every request has one', [v.cards[3].rows, v.cards[2].note], [[['None in this range.']], '']);
  check('report: rows (platform, question, signals, date)', [v.cards[5].note, v.cards[5].rows],
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
    rows: [['GPTBot', 'Any', 'Forbidden', 'No corpus collection.', 'ChangeDelete'], ['Any AI crawler', 'Training', 'Paid', 'No reason given Terms', 'ChangeDelete'],
      ['Any automated client', 'Any', 'Free', 'No reason given', 'ChangeDelete']] });
  check('access: the terms link', await page.evaluate(() => document.querySelector('#screen-access .vis-live a[target="_blank"]').href), 'https://shop.test/terms');
  check('access: every agent seen', v.cards[1], { title: 'Every agent seen', note: '2 distinct clients. There is no filter that hides unrecognised ones.',
    rows: [['GPTBotOpenAI', 'AI crawler (indexing)', 'Training', 'Detected', '412'], ['odd-botOperator unknown', 'robot_x', 'Not declared', 'Probable', '3']] });

  // Change and delete rules (V5-access-policy-edit).
  const writes = () => page.evaluate(() => window.__requests.filter((r) => /^(PUT|DELETE) /.test(r)));
  const amsg = () => page.evaluate(() => document.getElementById('access-msg').textContent);
  const ruleButton = (row, label) => page.evaluate(([r, l]) => Array.from(document.querySelectorAll('#screen-access .vis-live tbody')[0].rows[r]
    .querySelectorAll('button')).find((b) => b.textContent === l).click(), [row, label]);
  const dialogs = []; let answer = true;
  page.on('dialog', (d) => { dialogs.push(d.message()); if (answer) d.accept(); else d.dismiss(); });
  await ruleButton(1, 'Change'); await settle();
  check('Change: the editor opens with the rule (decision, terms, who and purpose)', await page.evaluate(() => {
    const f = document.getElementById('access-edit');
    return [f.hidden, document.getElementById('access-tier').value, document.getElementById('access-reason').value,
      document.getElementById('access-terms').value, f.querySelector('p.aic-hint').textContent]; }),
    [false, 'paid', '', 'https://shop.test/terms', 'Any AI crawler \u00b7 Training']);
  await page.selectOption('#access-tier', 'forbidden'); await page.fill('#access-reason', 'No training.');
  let wb = (await writes()).length; before = (await requests()).length;
  await page.evaluate(() => document.getElementById('access-edit').requestSubmit()); await settle(); await settle();
  check('save: one PUT with the rule\'s own subject and purpose; Rule saved.; the list reloads; the editor closes', [(await writes()).slice(wb),
    await amsg(), (await requests()).slice(before).filter((r) => /^GET /.test(r)), await page.evaluate(() => document.getElementById('access-edit').hidden)],
    [['PUT /telemetry/access-policies {"agent_id":null,"actor_type":"ai_crawler","purpose":"training","tier":"forbidden","reason":"No training.","terms_url":"https://shop.test/terms"}'],
      'Rule saved.', ['GET /telemetry/access-policies?limit=200', 'GET /telemetry/agents?limit=200'], true]);
  await ruleButton(0, 'Change'); await settle();
  await page.fill('#access-terms', 'ftp://shop.test/terms');
  wb = (await writes()).length;
  await page.evaluate(() => document.getElementById('access-edit').requestSubmit()); await settle();
  check('a terms link that is not a web address is refused before sending', [await amsg(), (await writes()).length - wb],
    ['The terms link must be a web address starting with https://.', 0]);
  await page.fill('#access-terms', '');
  await page.evaluate(() => { window.__denyWrite = true; document.getElementById('access-edit').requestSubmit(); }); await settle();
  check('403: who may change rules', await amsg(), 'Only an owner or admin can change access rules.');
  await page.evaluate(() => { window.__denyWrite = false; Array.from(document.querySelectorAll('#access-edit button')).find((b) => b.type === 'button').click(); }); await settle();
  answer = false; wb = (await writes()).length;
  await ruleButton(2, 'Delete'); await settle();
  check('Delete asks first; cancelled = nothing sent', [dialogs[dialogs.length - 1], (await writes()).length - wb],
    ['Delete this rule? Clients it matched fall back to the next rule that matches, or to Not configured.', 0]);
  answer = true;
  await ruleButton(2, 'Delete'); await settle(); await settle();
  check('Delete: one DELETE for that rule; Rule deleted.', [(await writes()).slice(wb), await amsg()], [['DELETE /telemetry/access-policies/p3'], 'Rule deleted.']);

  // New rule (V5-access-policy-create): the same editor, with a subject and a purpose to pick.
  const editor = () => page.evaluate(() => {
    const f = document.getElementById('access-edit'), opts = (id) => Array.from(document.getElementById(id).options).filter((o) => !o.hidden).map((o) => o.value);
    return { hidden: f.hidden, title: f.querySelector('.card__title').textContent, whoShown: !f.querySelector('p.aic-hint').hidden,
      pickShown: !document.getElementById('access-subject').closest('label').hidden, tiers: opts('access-tier'), focus: document.activeElement.id };
  });
  check('New rule: shown to an owner or admin', await page.evaluate(() => !document.getElementById('access-new').parentElement.hidden), true);
  await page.click('#access-new'); await settle();
  check('New rule: the editor opens empty with a subject and purpose to pick; no Not configured', [await editor(), await page.evaluate(() =>
    ['access-subject', 'access-purpose'].map((id) => Array.from(document.getElementById(id).options).map((o) => [o.value, o.textContent]))),
    await page.evaluate(() => [document.getElementById('access-tier').value, document.getElementById('access-reason').value, document.getElementById('access-terms').value])],
    [{ hidden: false, title: 'New rule', whoShown: false, pickShown: true, tiers: ['free', 'paid', 'forbidden'], focus: 'access-subject' },
      [[['type:human', 'Any human visitor'], ['type:search_crawler', 'Any search crawler'], ['type:ai_crawler', 'Any AI crawler'],
        ['type:ai_user_agent', 'Any AI answering a user'], ['type:agent_tool', 'Any agent acting for a user'], ['type:unknown', 'Any unrecognised client'],
        ['agent:a1', 'GPTBot'], ['agent:a2', 'odd-bot']],
       [['', 'Any'], ['training', 'Training'], ['search_indexing', 'Search indexing'], ['answering', 'Answering'], ['agent_action', 'Acting for a user'],
        ['preview', 'Link preview'], ['unknown', 'Not declared']]],
      ['forbidden', '', '']]);
  await page.selectOption('#access-subject', 'type:ai_crawler'); await page.selectOption('#access-purpose', 'training');
  wb = (await writes()).length;
  await page.evaluate(() => document.getElementById('access-edit').requestSubmit()); await settle();
  check('New rule: a subject and purpose that already have a rule are refused before sending', [await amsg(), (await writes()).length - wb],
    ['A rule for this client and purpose already exists. Use its Change button.', 0]);
  await page.selectOption('#access-subject', 'agent:a2'); await page.selectOption('#access-purpose', 'answering');
  await page.selectOption('#access-tier', 'paid'); await page.fill('#access-reason', 'Answers are licensed.');
  before = (await requests()).length;
  await page.evaluate(() => document.getElementById('access-edit').requestSubmit()); await settle(); await settle();
  check('New rule: one PUT with the picked agent and purpose; Rule added.; the list reloads; the editor closes', [(await writes()).slice(wb),
    await amsg(), (await requests()).slice(before).filter((r) => /^GET /.test(r)), await page.evaluate(() => document.getElementById('access-edit').hidden)],
    [['PUT /telemetry/access-policies {"agent_id":"a2","actor_type":null,"purpose":"answering","tier":"paid","reason":"Answers are licensed.","terms_url":null}'],
      'Rule added.', ['GET /telemetry/access-policies?limit=200', 'GET /telemetry/agents?limit=200'], true]);
  await page.click('#access-new'); await settle();
  await page.selectOption('#access-subject', 'type:search_crawler');
  wb = (await writes()).length;
  await page.evaluate(() => document.getElementById('access-edit').requestSubmit()); await settle(); await settle();
  check('New rule: an actor type for any purpose (the default decision is Forbidden)', (await writes()).slice(wb),
    ['PUT /telemetry/access-policies {"agent_id":null,"actor_type":"search_crawler","purpose":null,"tier":"forbidden","reason":null,"terms_url":null}']);
  await ruleButton(1, 'Change'); await settle();
  check('Change after New rule: its own title, who and purpose shown, no pickers, Not configured offered again', await editor(),
    { hidden: false, title: 'Change the rule', whoShown: true, pickShown: false, tiers: ['free', 'paid', 'forbidden', 'unset'], focus: 'access-tier' });
  await page.evaluate(() => Array.from(document.querySelectorAll('#access-edit button')).find((b) => b.type === 'button').click()); await settle();
  await page.evaluate(() => { window.__role = 'viewer'; }); await connect(); await go('#screen-dashboard'); await go('#screen-access'); await settle();
  check('a viewer gets no Change, Delete or New rule', await page.evaluate(() => [document.querySelectorAll('#screen-access .vis-live tbody button').length,
    document.getElementById('access-new').parentElement.hidden]), [0, true]);
  await page.evaluate(() => { window.__role = 'admin'; }); await connect(); await go('#screen-dashboard'); await go('#screen-access'); await settle();
  v = await view('screen-access');

  // Persian over live content.
  await lang('fa');
  v = await view('screen-access');
  check('fa: access rule subject, purpose, badge, reason fallback', v.cards[0].rows[1].slice(0, 4), [F('anyAiCrawler'), F('training'), F('paid'), F('noReason') + ' ' + F('terms')]);
  check('fa: access note with Persian digits', v.cards[0].note, F('rulesNote').replace('{n}', fa(0x6F3)));
  check('fa: the New rule button', await page.evaluate(() => document.getElementById('access-new').textContent), F('newRule'));
  await go('#screen-visibility');
  v = await view('screen-visibility');
  check('fa: visibility signal row and agent row', [v.cards[0].rows[0], v.cards[1].rows[0].slice(1, 3)],
    [[F('mentioned'), fa(0x6F3), fa(0x6F2), fa(0x6F2)], [F('aiCrawler'), F('detected')]]);
  check('fa: visibility card title', v.cards[0].title, F('answersTitle'));
  // A sentence split by an identifier: the Persian layer translates each text node, so each fragment is a key.
  check('fa: the text before an identifier translates on its own', await page.evaluate(() => Array.from(document.querySelectorAll('#screen-visibility .callout p'))
    .find((p) => p.querySelector('.identifier')).firstChild.nodeValue.trim()), F('uaClaim'));
  await go('#screen-visibility-detail');
  await page.click('#screen-visibility-detail tbody tr:first-child button'); await settle();
  d = await detail();
  check('fa: observation facts', [d.title, d.facts[1], d.facts[5][0]], [F('observation'), [F('test'), F('brandQuestion')], F('mentioned')]);
  v = await view('screen-visibility-detail');
  check('fa: the country card in Persian (title, country name, Persian digits)', [v.cards[2].title, v.cards[2].rows[0]],
    [F('topCountries'), [F('iran') + ' (' + iso('IR') + ')', fa(0x6F8, 0x6F0)]]);
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
