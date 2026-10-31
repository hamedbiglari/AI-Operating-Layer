#!/usr/bin/env node
/*
 * Browser checks for the Knowledge gap screen (Step 8A).
 *   Sample: the "What has already been checked" card is hidden as debt
 *           (V5-gap-history); "Close this gap" stays.
 *   Live:   with ?id=, GET /knowledge-gaps/{id} then GET /knowledge/{object}/gaps
 *           (two calls): the description, the object's name, type and
 *           priority, the status badge, the object's other open gaps as links;
 *           no other open gaps; no id: one GET /knowledge-gaps?status=open with
 *           each row's object name; no open gaps; 404, 422, 500 with Retry;
 *           Persian over live content.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/gap.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-gap';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069), MD = fa(0xB7);
const iso = (s) => FSI + s + PDI;
const FA = {
  knowledge: fa(0x62F, 0x627, 0x646, 0x634),
  gaps: fa(0x634, 0x6A9, 0x627, 0x641, 0x200C, 0x647, 0x627, 0x6CC, 0x20, 0x62F, 0x627, 0x646, 0x634),
  evidenceGap: fa(0x634, 0x6A9, 0x627, 0x641, 0x20, 0x634, 0x648, 0x627, 0x647, 0x62F),
  sourceGap: fa(0x634, 0x6A9, 0x627, 0x641, 0x20, 0x645, 0x646, 0x628, 0x639),
  high: fa(0x627, 0x648, 0x644, 0x648, 0x6CC, 0x62A, 0x20, 0x628, 0x627, 0x644, 0x627),
  low: fa(0x627, 0x648, 0x644, 0x648, 0x6CC, 0x62A, 0x20, 0x67E, 0x627, 0x6CC, 0x6CC, 0x646),
  stillOpen: fa(0x647, 0x646, 0x648, 0x632, 0x20, 0x628, 0x627, 0x632),
  others: fa(0x62F, 0x6CC, 0x6AF, 0x631, 0x20, 0x634, 0x6A9, 0x627, 0x641, 0x200C, 0x647, 0x627, 0x6CC, 0x20, 0x628, 0x627, 0x632, 0x20,
    0x627, 0x6CC, 0x646, 0x20, 0x67E, 0x631, 0x648, 0x646, 0x62F, 0x647, 0x20, 0x62F, 0x627, 0x646, 0x634),
  notFound: fa(0x627, 0x6CC, 0x646, 0x20, 0x634, 0x6A9, 0x627, 0x641, 0x20, 0x67E, 0x6CC, 0x62F, 0x627, 0x20, 0x646, 0x634, 0x62F, 0x2E),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const gap = (id, ko, name, type, priority, status, description) => ({ id, organization_id: 'org', knowledge_object_id: ko,
  knowledge_object_name: name, gap_type: type, description, priority, status, recommended_action: null,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:00:00Z' });
const GAPS = [
  gap('g1', 'ko1', 'Taranjabin', 'evidence_gap', 'high', 'open', 'Human clinical evidence'),
  gap('g2', 'ko1', 'Taranjabin', 'source_gap', 'low', 'open', 'No supplier certificate'),
  gap('g3', 'ko1', 'Taranjabin', 'conflict_gap', 'medium', 'resolved', 'Chemotype conflict'),
  gap('g4', 'ko2', 'Saffron', 'odd_gap', 'medium', 'open', 'Saffron origin'),
];

function installMock(gaps) {
  window.__requests = []; window.__gaps = gaps;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (p === '/knowledge-gaps?status=open&limit=100') {
      if (window.__listStatus) return reply({}, window.__listStatus);
      const items = window.__gaps.filter((g) => g.status === 'open');
      return reply({ items, total: items.length, limit: 100, offset: 0 });
    }
    let m = p.match(/^\/knowledge-gaps\/([^/?]+)$/);
    if (m) {
      const id = decodeURIComponent(m[1]);
      if (id === 'boom') return reply({}, 500);
      if (id === 'bad') return reply({ detail: 'invalid' }, 422);
      const g = window.__gaps.find((x) => x.id === id);
      return g ? reply(g) : reply({ detail: 'Knowledge gap not found' }, 404);
    }
    m = p.match(/^\/knowledge\/([^/]+)\/gaps\?limit=100$/);
    if (m) {
      const items = window.__gaps.filter((g) => g.knowledge_object_id === decodeURIComponent(m[1]));
      return reply({ items, total: items.length, limit: 100, offset: 0 });
    }
    return reply({ detail: 'Not found' }, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(150);
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await settle(); };
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  // The Research screen reads its own open gaps on connect (?limit=20&status=open); those are not this screen's.
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /gaps/.test(r) && !/limit=20&status=open/.test(r)));
  const sample = () => page.evaluate(() => {
    const s = document.getElementById('screen-gap'), shown = (e) => getComputedStyle(e).display !== 'none';
    return Array.from(s.querySelectorAll(':scope > div:not([data-live-keep]) .card > .card__title'))
      .map((h) => [h.textContent, shown(h.parentElement), h.parentElement.hasAttribute('data-debt-hidden')]);
  });
  const view = () => page.evaluate(() => {
    const s = document.getElementById('screen-gap'), keep = s.querySelectorAll('[data-live-keep]');
    const top = keep[0], body = keep[1];
    if (!top) return null;
    const box = body.querySelector(':scope > .know-status'), act = box.querySelector('button'), card = body.querySelector(':scope > .card');
    const badge = top.querySelector('.page-actions .badge');
    return {
      crumb: [top.querySelector('.breadcrumbs a').getAttribute('href'), top.querySelector('.breadcrumbs a').textContent],
      title: top.querySelector('#h-gap-live').textContent,
      meta: top.querySelector('.gap-meta').textContent,
      badge: badge ? [badge.className, badge.textContent] : null,
      card: card.hidden ? null : card.querySelector('.card__title').textContent,
      rows: card.hidden ? null : Array.from(card.querySelectorAll('li')).map((li) => [li.querySelector('a').getAttribute('href'),
        li.querySelector('a').textContent, li.querySelector('.gap-list__meta').textContent]),
      state: box.dataset.state, message: box.querySelector('p').textContent, action: act && !act.hidden ? act.textContent : null,
      // Everything but the live panel and the live content is hidden, the sample breadcrumbs and header included.
      sampleShown: Array.from(s.children).some((c) => !c.hasAttribute('data-live-keep') && !c.classList.contains('live-panel')
        && getComputedStyle(c).display !== 'none'),
    };
  });

  // Sample mode (before any connection).
  check('sample: "What has already been checked" hidden as debt; the other cards shown', await sample(), [
    ['What has already been checked', false, true], ['Close this gap', true, false]]);

  // Live: one gap.
  await page.evaluate(installMock, GAPS);
  await go('#screen-gap?id=g1');
  await connect();
  let v = await view();
  check('two requests: the gap, then its object\'s gaps', await requests(), ['GET /knowledge-gaps/g1', 'GET /knowledge/ko1/gaps?limit=100']);
  check('header: back to Knowledge, the description, object, type and priority, the status', [v.crumb, v.title, v.meta, v.badge],
    [['#screen-knowledge', 'Knowledge'], 'Human clinical evidence', 'Taranjabin ' + MD + ' Evidence gap ' + MD + ' High priority',
      ['badge badge--warning', 'Still open']]);
  check('other open gaps: this one and the resolved one left out', [v.card, v.rows, v.state],
    ['Other open gaps on this knowledge object', [['#screen-gap?id=g2', 'No supplier certificate', 'Source gap ' + MD + ' Low priority']], '']);
  check('the sample content is hidden', v.sampleShown, false);
  await page.click('#screen-gap .gap-list a'); await settle();
  v = await view();
  check('a link opens that gap', [v.title, v.badge[1], v.rows.map((r) => r[0])], ['No supplier certificate', 'Still open', ['#screen-gap?id=g1']]);
  await go('#screen-gap?id=g3');
  v = await view();
  check('a resolved gap; its object has other open gaps', [v.badge, v.rows.length], [['badge badge--success', 'Resolved'], 2]);
  await go('#screen-gap?id=g4');
  v = await view();
  check('no other open gaps; an unknown type is shown as sent', [v.meta, v.rows, v.state, v.message],
    ['Saffron ' + MD + ' odd_gap ' + MD + ' Medium priority', [], 'empty', 'No other open gaps on this knowledge object.']);

  // No id: the open gaps, each naming its object, in one request.
  let before = (await requests()).length;
  await go('#screen-gap');
  v = await view();
  check('no id: one request for the open gaps', (await requests()).slice(before), ['GET /knowledge-gaps?status=open&limit=100']);
  check('no id: the heading and the rows with their object names', [v.title, v.card, v.badge, v.rows], ['Knowledge gaps', 'Open gaps', null, [
    ['#screen-gap?id=g1', 'Human clinical evidence', 'Taranjabin ' + MD + ' Evidence gap ' + MD + ' High priority'],
    ['#screen-gap?id=g2', 'No supplier certificate', 'Taranjabin ' + MD + ' Source gap ' + MD + ' Low priority'],
    ['#screen-gap?id=g4', 'Saffron origin', 'Saffron ' + MD + ' odd_gap ' + MD + ' Medium priority']]]);
  await page.evaluate(() => { window.__gaps = window.__gaps.filter((g) => g.status !== 'open'); });
  await connect();
  v = await view();
  check('no open gaps: said', [v.state, v.message, v.rows], ['empty', 'No open gaps.', []]);
  await page.evaluate((g) => { window.__gaps = g; }, GAPS);

  // Errors.
  await go('#screen-gap?id=missing');
  v = await view();
  check('404: not found, no list', [v.state, v.message, v.card, v.title], ['empty', 'This gap was not found.', null, 'Knowledge gaps']);
  await go('#screen-gap?id=bad');
  check('422: not found', (await view()).message, 'This gap was not found.');
  await go('#screen-gap?id=boom');
  v = await view();
  check('500: the error with Retry', [v.state, v.message, v.action], ['error', 'Could not load the gap (' + iso('HTTP 500') + ').', 'Retry']);
  before = (await requests()).length;
  await page.click('#screen-gap [data-live-keep] .know-status button'); await settle();
  check('Retry sends the same request again', (await requests()).slice(before), ['GET /knowledge-gaps/boom']);

  // Persian over live content (an identity entry would hang here).
  await go('#screen-gap?id=g1');
  await lang('fa');
  v = await view();
  check('fa: breadcrumb, meta, badge, card title, row meta', [v.crumb[1], v.meta, v.badge[1], v.card, v.rows[0][2]],
    [FA.knowledge, 'Taranjabin ' + MD + ' ' + FA.evidenceGap + ' ' + MD + ' ' + FA.high, FA.stillOpen, FA.others, FA.sourceGap + ' ' + MD + ' ' + FA.low]);
  await go('#screen-gap?id=missing');
  check('fa: not found', (await view()).message, FA.notFound);
  await go('#screen-gap');
  check('fa: no-id heading', (await view()).title, FA.gaps);
  await lang('en');
  await go('#screen-gap?id=g1');
  check('back to English', (await view()).meta, 'Taranjabin ' + MD + ' Evidence gap ' + MD + ' High priority');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
