#!/usr/bin/env node
/*
 * Browser checks for the Knowledge detail screen (Step 8B-2).
 *   Sample: one sample page (Toranjebin) replaces the four; the AI visibility
 *           and Evidence by kind cards are hidden as debt; the old page ids are
 *           gone from the screen picker and from every link.
 *   Live:   GET /knowledge/overview?id= and GET /knowledge/{id}/claims, two
 *           calls: the name in the heading and the breadcrumb, the description,
 *           the status badge, Trace a statement -> #screen-provenance?id=, the
 *           four stat cards from the counts, the claims with status and
 *           strength, the count line; no claims; no id; 404, 422, 500 with
 *           Retry; Persian over live content.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/knowledge-detail.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-knowledge-detail';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069), MD = fa(0xB7);
const iso = (s) => FSI + s + PDI;
const FA = {
  detail: fa(0x62C, 0x632, 0x626, 0x6CC, 0x627, 0x62A, 0x20, 0x62F, 0x627, 0x646, 0x634),
  trace: fa(0x631, 0x62F, 0x6CC, 0x627, 0x628, 0x6CC, 0x20, 0x6CC, 0x6A9, 0x20, 0x6AF, 0x632, 0x627, 0x631, 0x647),
  claims: fa(0x627, 0x62F, 0x639, 0x627, 0x647, 0x627),
  published: fa(0x645, 0x646, 0x62A, 0x634, 0x631, 0x634, 0x62F, 0x647),
  approved: fa(0x62A, 0x623, 0x6CC, 0x6CC, 0x62F, 0x634, 0x62F, 0x647),
  strong: fa(0x642, 0x648, 0x62A, 0x20, 0x6A9, 0x644, 0x6CC, 0x20, 0x634, 0x648, 0x627, 0x647, 0x62F, 0x3A, 0x20, 0x642, 0x648, 0x6CC),
  notFound: fa(0x627, 0x6CC, 0x646, 0x20, 0x67E, 0x631, 0x648, 0x646, 0x62F, 0x647, 0x20, 0x62F, 0x627, 0x646, 0x634, 0x20,
    0x67E, 0x6CC, 0x62F, 0x627, 0x20, 0x646, 0x634, 0x62F, 0x2E),
  knowledge: fa(0x62F, 0x627, 0x646, 0x634),
  sources: fa(0x645, 0x646, 0x627, 0x628, 0x639),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const counts = (o) => Object.assign({ sources: 0, claims: 0, claims_conflicting: 0, evidence: 0, evidence_verified: 0,
  evidence_pending_review: 0, gaps_open: 0 }, o);
const ko = (id, name, status, description, c) => ({ id, organization_id: 'org', canonical_name: name, slug: id, object_type: 'plant',
  category_id: null, description, status, language: 'en', confidence: null, public_visibility: true, ai_visibility: true, version: 1,
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-02T10:00:00Z', counts: counts(c), finished: false });
const claim = (id, predicate, value, status, strength) => ({ id, knowledge_object_id: 'k1', predicate, object_value: value, status,
  evidence_strength: strength });
const OBJECTS = {
  k1: [ko('k1', 'Taranjabin', 'published', 'Manna of Alhagi.', { sources: 4, claims: 3, claims_conflicting: 1, evidence: 6, evidence_verified: 2, gaps_open: 2 }),
    [claim('c1', 'contains', 'mannitol', 'approved', 'strong'), claim('c2', 'tastes', 'sweet', 'draft', 'conflicting'),
      claim('c3', 'grows_in', null, 'odd_status', 'moderate')], 5],
  k2: [ko('k2', 'Saffron', 'odd_state', null, {}), [], 0],
};

function installMock(objects) {
  window.__requests = []; window.__objects = objects;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    let m = p.match(/^\/knowledge\/overview\?id=([^&]+)$/);
    if (m) {
      const id = decodeURIComponent(m[1]), o = window.__objects[id];
      if (id === 'boom') return reply({}, 500);
      if (id === 'bad') return reply({ detail: 'invalid' }, 422);
      return o ? reply({ items: [o[0]], total: 1, limit: 50, offset: 0, finished_visible: false }) : reply({ detail: 'Not found' }, 404);
    }
    m = p.match(/^\/knowledge\/([^/]+)\/claims\?limit=200$/);
    if (m) {
      const id = decodeURIComponent(m[1]), o = window.__objects[id];
      if (id === 'boom') return reply({}, 500);
      if (id === 'bad') return reply({ detail: 'invalid' }, 422);
      return o ? reply({ items: o[1], total: o[2], limit: 200, offset: 0 }) : reply({ detail: 'Not found' }, 404);
    }
    return reply({ items: [], total: 0 });
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
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /\/knowledge\/(overview\?id=|[^/]+\/claims)/.test(r)));
  const sample = () => page.evaluate(() => {
    const s = document.getElementById('screen-knowledge-detail'), shown = (e) => getComputedStyle(e).display !== 'none';
    return {
      cards: Array.from(s.querySelectorAll(':scope > .card:not(.live-panel)')).map((c) => [c.querySelector('.card__title').textContent.trim(), shown(c), c.hasAttribute('data-debt-hidden')]),
      stats: Array.from(s.querySelectorAll(':scope > .stat-grid .stat__label')).map((l) => l.textContent),
      trace: s.querySelector(':scope > .page-header .page-actions .btn').textContent,
      oldIds: document.querySelectorAll('#screen-knowledge-taranjebin, #screen-knowledge-saffron, #screen-knowledge-garlic, #screen-knowledge-thyme').length,
      oldLinks: document.querySelectorAll('a[href^="#screen-knowledge-taranjebin"], a[href^="#screen-knowledge-saffron"], a[href^="#screen-knowledge-garlic"], a[href^="#screen-knowledge-thyme"]').length,
      oldOptions: Array.from(document.querySelectorAll('#pick-screen option')).filter((o) => /^screen-knowledge-(taranjebin|saffron|garlic|thyme)$/.test(o.value)).length,
      picker: Array.from(document.querySelectorAll('#pick-screen option')).filter((o) => o.value === 'screen-knowledge-detail').map((o) => o.textContent),
      links: document.querySelectorAll('a[href="#screen-knowledge-detail"]').length,
    };
  });
  const view = () => page.evaluate(() => {
    const s = document.getElementById('screen-knowledge-detail'), keep = s.querySelectorAll('[data-live-keep]');
    const top = keep[0], body = keep[1];
    if (!top) return null;
    const box = body.querySelector(':scope > .know-status'), act = box.querySelector('button'), card = body.querySelector(':scope > .card');
    const stats = body.querySelector(':scope > .stat-grid'), trace = top.querySelector('.page-actions a'), badge = top.querySelector('.page-actions .badge');
    const crumbs = top.querySelector('.breadcrumbs'), count = card.querySelector('.kd-count');
    return {
      crumb: [crumbs.querySelector('a').getAttribute('href'), crumbs.querySelector('a').textContent, crumbs.lastElementChild.textContent],
      title: top.querySelector('#h-know-detail-live').textContent,
      description: top.querySelector('.kd-description').textContent,
      badge: badge ? [badge.className, badge.textContent] : null,
      trace: trace ? [trace.getAttribute('href'), trace.textContent] : null,
      stats: stats.hidden ? null : Array.from(stats.children).map((x) => [x.querySelector('.stat__label').textContent, x.querySelector('.stat__value').textContent,
        x.querySelector('.stat__note') ? x.querySelector('.stat__note').textContent : null, x.classList.contains('stat--attention')]),
      cardTitle: card.hidden ? null : card.querySelector('.card__title').textContent,
      count: card.hidden || count.hidden ? null : count.textContent,
      claims: card.hidden ? null : Array.from(card.querySelectorAll('.kd-claims li')).map((li) => [li.querySelector('.kd-claim__text').textContent,
        li.querySelector('.kd-claim__meta').textContent]),
      state: box.dataset.state, message: box.querySelector('p').textContent, action: act && !act.hidden ? act.textContent : null,
      sampleShown: Array.from(s.children).some((c) => !c.hasAttribute('data-live-keep') && !c.classList.contains('live-panel')
        && getComputedStyle(c).display !== 'none'),
    };
  });

  // Sample mode (before any connection).
  const s0 = await sample();
  check('sample: the two unbacked cards are hidden as debt', s0.cards,
    [['AI visibility for ' + fa(0x62A, 0x631, 0x646, 0x62C, 0x628, 0x6CC, 0x646), false, true], ['Evidence by kind', false, true]]);
  check('sample: the stat cards and the Trace button stay', [s0.stats, s0.trace], [['Sources', 'Claims', 'Evidence', 'Conflicts'], 'Trace a statement']);
  check('the four old pages, their links and picker entries are gone; one new entry', [s0.oldIds, s0.oldLinks, s0.oldOptions, s0.picker],
    [0, 0, 0, ['Knowledge detail']]);
  check('sample links now point at the detail screen', s0.links > 0, true);
  await lang('fa');
  const s1 = await sample();
  check('fa sample: stat label and Trace', [s1.stats[0], s1.trace], [FA.sources, FA.trace]);
  await lang('en');

  // Live.
  await page.evaluate(installMock, OBJECTS);
  await go('#screen-knowledge-detail?id=k1');
  await connect();
  let v = await view();
  check('two requests: the overview row and the claims', await requests(), ['GET /knowledge/overview?id=k1', 'GET /knowledge/k1/claims?limit=200']);
  check('header: breadcrumb, name, description, status, Trace link', [v.crumb, v.title, v.description, v.badge, v.trace],
    [['#screen-knowledge', 'Knowledge', 'Taranjabin'], 'Taranjabin', 'Manna of Alhagi.', ['badge badge--success', 'Published'],
      ['#screen-provenance?id=k1', 'Trace a statement']]);
  check('stat cards from the counts', v.stats, [['Sources', '4', null, false], ['Claims', '3', null, false],
    ['Evidence', '6', 'of which 2 verified', false], ['Conflicts', '1', '2 gaps open', true]]);
  check('claims: text, status and strength; an unknown status shown as sent', [v.cardTitle, v.count, v.claims],
    ['Claims', 'Claims shown: 3 of 5', [['contains mannitol', 'Approved ' + MD + ' Aggregate strength: strong'],
      ['tastes sweet', 'Draft ' + MD + ' Aggregate strength: conflicting'], ['grows_in', 'odd_status ' + MD + ' Aggregate strength: moderate']]]);
  check('the sample content is hidden', v.sampleShown, false);

  await go('#screen-knowledge-detail?id=k2');
  v = await view();
  check('no claims: said; an unknown status and no description', [v.state, v.message, v.claims, v.count, v.badge, v.description],
    ['empty', 'This knowledge object has no claims yet.', [], null, ['badge badge--unknown', 'odd_state'], '']);
  check('zero counts: no attention', v.stats.map((x) => x[3]), [false, false, false, false]);

  await go('#screen-knowledge-detail');
  v = await view();
  check('no id: the message, nothing else', [v.state, v.message, v.title, v.stats, v.claims, v.trace, v.crumb[2]],
    ['empty', 'No knowledge object selected. Open one from Knowledge.', 'Knowledge detail', null, null, null, '']);
  await go('#screen-knowledge-detail?id=missing');
  v = await view();
  check('404: not found', [v.state, v.message, v.stats], ['empty', 'This knowledge object was not found.', null]);
  await go('#screen-knowledge-detail?id=bad');
  check('422: not found', (await view()).message, 'This knowledge object was not found.');
  await go('#screen-knowledge-detail?id=boom');
  v = await view();
  check('500: the error with Retry', [v.state, v.message, v.action],
    ['error', 'Could not load the knowledge object (' + iso('HTTP 500') + ').', 'Retry']);
  let before = (await requests()).length;
  await page.click('#screen-knowledge-detail [data-live-keep] .know-status button'); await settle();
  check('Retry sends both requests again', (await requests()).slice(before), ['GET /knowledge/overview?id=boom', 'GET /knowledge/boom/claims?limit=200']);

  // Persian over live content (an identity entry would hang here).
  await go('#screen-knowledge-detail?id=k1');
  await lang('fa');
  v = await view();
  check('fa: breadcrumb, badge, Trace, stat label, card title, a claim meta',
    [v.crumb[1], v.badge[1], v.trace[1], v.stats[0][0], v.cardTitle, v.claims[0][1], v.title],
    [FA.knowledge, FA.published, FA.trace, FA.sources, FA.claims, FA.approved + ' ' + MD + ' ' + FA.strong, 'Taranjabin']);
  await go('#screen-knowledge-detail?id=missing');
  check('fa: not found', (await view()).message, FA.notFound);
  await go('#screen-knowledge-detail');
  check('fa: no-id heading', (await view()).title, FA.detail);
  await lang('en');
  await go('#screen-knowledge-detail?id=k1');
  check('back to English', (await view()).count, 'Claims shown: 3 of 5');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
