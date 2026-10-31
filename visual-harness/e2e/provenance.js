#!/usr/bin/env node
/*
 * Browser checks for the Provenance screen (Step 7D-2).
 *   Sample: the two design cards stay as they are, in English and Persian.
 *   Live:   GET /knowledge/{id}/provenance, one request per object: the object's
 *           name, the claim count, each claim with its status and aggregate
 *           strength, each link with its relation, the evidence summary and
 *           the source title from the response's maps; a claim with no links;
 *           remove a link (confirm, DELETE /claim-evidence/{link_id}, reload),
 *           a cancelled confirm, a 403; no remove button for a viewer;
 *           no id, 404, 500 with Retry, no claims; Persian.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/provenance.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-provenance';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069), MD = fa(0xB7);
const iso = (s) => FSI + s + PDI;
const FA = {
  provenance: fa(0x645, 0x646, 0x634, 0x623),
  claim: fa(0x627, 0x62F, 0x639, 0x627),
  supports: fa(0x62D, 0x645, 0x627, 0x6CC, 0x62A, 0x20, 0x645, 0x6CC, 0x200C, 0x6A9, 0x646, 0x62F),
  contradicts: fa(0x646, 0x642, 0x636, 0x20, 0x645, 0x6CC, 0x200C, 0x6A9, 0x646, 0x62F),
  approved: fa(0x62A, 0x623, 0x6CC, 0x6CC, 0x62F, 0x634, 0x62F, 0x647),
  moderate: fa(0x642, 0x648, 0x62A, 0x20, 0x6A9, 0x644, 0x6CC, 0x20, 0x634, 0x648, 0x627, 0x647, 0x62F, 0x3A, 0x20, 0x645, 0x62A, 0x648, 0x633, 0x637),
  pending: fa(0x62F, 0x631, 0x20, 0x627, 0x646, 0x62A, 0x638, 0x627, 0x631, 0x20, 0x628, 0x631, 0x631, 0x633, 0x6CC),
  indirect: fa(0x63A, 0x6CC, 0x631, 0x645, 0x633, 0x62A, 0x642, 0x6CC, 0x645),
  count: fa(0x627, 0x62F, 0x639, 0x627, 0x647, 0x627, 0x6CC, 0x20, 0x646, 0x645, 0x627, 0x6CC, 0x634, 0x200C, 0x62F, 0x627, 0x62F, 0x647, 0x200C, 0x634, 0x62F, 0x647, 0x3A, 0x20, 0x6F3, 0x20, 0x627, 0x632, 0x20, 0x6F5),
  noLinks: fa(0x647, 0x6CC, 0x686, 0x20, 0x634, 0x627, 0x647, 0x62F, 0x6CC, 0x20, 0x628, 0x647, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x627, 0x62F, 0x639, 0x627, 0x20, 0x67E, 0x6CC, 0x648, 0x646, 0x62F, 0x20, 0x62F, 0x627, 0x62F, 0x647, 0x20, 0x646, 0x634, 0x62F, 0x647, 0x20, 0x627, 0x633, 0x62A, 0x2E),
  notFound: fa(0x627, 0x6CC, 0x646, 0x20, 0x67E, 0x631, 0x648, 0x646, 0x62F, 0x647, 0x20, 0x62F, 0x627, 0x646, 0x634, 0x20, 0x67E, 0x6CC, 0x62F, 0x627, 0x20, 0x646, 0x634, 0x62F, 0x2E),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const evidence = (id, status, directness, summary, sourceId) => ({ id, status, directness, basis: null, subject_tested: null, summary,
  source_id: sourceId, document_id: null, chunk_id: null, page_number: null });
const link = (id, evidenceId, relation) => ({ link_id: id, evidence_id: evidenceId, relation, weight: null });
const claim = (id, text, status, strength, links) => ({ id, text, predicate: text.split(' ')[0], object_value: text.split(' ').slice(1).join(' '),
  status, evidence_strength: strength, links });
const object = (id, claims, evidenceMap, sources, total) => ({ knowledge_object: { id, canonical_name: 'Taranjabin', status: 'published' },
  claims, evidence: evidenceMap, sources, documents: {}, total_claims: total, total_evidence: Object.keys(evidenceMap).length });
// Responses by knowledge object id; "missing" is a 404, "boom" a 500.
const OBJECTS = {
  ko: object('ko', [
    claim('c1', 'contains mannitol', 'approved', 'moderate', [link('link-a', 'ev-1', 'supports'), link('link-b', 'ev-2', 'contradicts')]),
    claim('c2', 'contains sucrose', 'odd_status', 'unverified', [link('link-c', 'ev-1', 'supports')]),
    claim('c3', 'tastes sweet', 'draft', 'unverified', []),
  ], {
    'ev-1': evidence('ev-1', 'verified', 'direct', 'Mannitol measured at 40%.', 'src-1'),
    'ev-2': evidence('ev-2', 'pending_review', 'indirect', 'Not found in a related species.', 'src-2'),
  }, {
    'src-1': { id: 'src-1', title: 'Review 2025', doi: null, full_text_accessed: true },
    'src-2': { id: 'src-2', title: 'Survey 2023', doi: null, full_text_accessed: false },
  }, 5),
  empty: object('empty', [], {}, {}, 0),
};

function installMock(objects) {
  window.__requests = []; window.__objects = objects; window.__role = 'editor'; window.__deleteStatus = 204;
  const reply = (body, status) => Promise.resolve(new Response(body === null ? null : JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    let m = p.match(/^\/knowledge\/([^/]+)\/provenance\?limit=200$/);
    if (m) {
      const id = decodeURIComponent(m[1]);
      if (id === 'boom') return reply({}, 500);
      return window.__objects[id] ? reply(window.__objects[id]) : reply({ detail: 'Not found' }, 404);
    }
    m = p.match(/^\/claim-evidence\/([^/]+)$/);
    if (m && method === 'DELETE') {
      if (window.__deleteStatus !== 204) return reply({ detail: 'no' }, window.__deleteStatus);
      Object.values(window.__objects).forEach((o) => o.claims.forEach((c) => { c.links = c.links.filter((l) => l.link_id !== m[1]); }));
      return reply(null, 204);
    }
    if (p === '/auth/me') return reply({ user: { role: window.__role }, organization: {} });
    return reply({}, 404);
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
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /\/provenance\?|\/claim-evidence\//.test(r)));
  const sample = () => page.evaluate(() => {
    const s = document.getElementById('screen-provenance');
    const fan = s.querySelector(':scope > div:not([data-live-keep]) .trail--fan');
    return {
      crumb: s.querySelector(':scope > .breadcrumbs').lastElementChild.textContent,
      fan: Array.from(fan.children).map((li) => [li.dataset.kind, li.querySelector('.trail__kind').textContent, !!li.querySelector('button')]),
      converter: s.querySelector('[data-kind="document"] .trail__meta').textContent,
    };
  });
  const view = () => page.evaluate(() => {
    const s = document.getElementById('screen-provenance'), list = s.querySelector('.prov-claims');
    const on = (e) => !!e && getComputedStyle(e).display !== 'none';
    const boxes = s.querySelectorAll('[data-live-keep] .know-status'), box = boxes[0], say = boxes[1], act = box && box.querySelector('button');
    const count = s.querySelector('.prov-count'), crumb = s.querySelector('[data-live-keep] .breadcrumbs a');
    return {
      crumb: crumb ? [crumb.getAttribute('href'), crumb.textContent] : null,
      title: s.querySelector('#h-prov-live') ? s.querySelector('#h-prov-live').textContent : null,
      count: count && !count.hidden ? count.textContent : null,
      claims: on(list) ? Array.from(list.children).map((card) => ({
        rows: Array.from(card.querySelectorAll('ol > li')).map((li) => [li.dataset.kind, li.querySelector('.trail__kind').textContent,
          li.querySelector('.trail__value').textContent, li.querySelector('.trail__meta').textContent, !!li.querySelector('button')]),
        none: card.querySelector('.prov-none') ? card.querySelector('.prov-none').textContent : null,
      })) : null,
      sourceLinks: on(list) ? Array.from(list.querySelectorAll('.trail__meta a')).map((a) => a.getAttribute('href')) : null,
      button: on(list) && list.querySelector('li button') ? [list.querySelector('li button').getAttribute('aria-label'), list.querySelector('li button').title] : null,
      state: box ? box.dataset.state : null, message: box ? box.querySelector('p').textContent : null, action: act && !act.hidden ? act.textContent : null,
      said: say ? [say.dataset.state, say.querySelector('p').textContent] : null,
    };
  });

  // Sample mode (before any connection).
  let s = await sample();
  check('sample: breadcrumb, the fan rows and their remove buttons', [s.crumb, s.fan], ['Provenance', [['claim', 'Claim', false],
    ['evidence', 'Supports', true], ['evidence', 'Supports', true], ['evidence', 'Supports', true], ['conflict', 'Contradicts', true]]]);
  await lang('fa');
  s = await sample();
  check('fa sample: breadcrumb, relations; the converter stays Latin', [s.crumb, s.fan[0][1], s.fan[1][1], s.fan[4][1], s.converter],
    [FA.provenance, FA.claim, FA.supports, FA.contradicts, 'MarkItDown 0.1.7']);
  await lang('en');

  // Live.
  await page.evaluate(installMock, OBJECTS);
  await go('#screen-provenance?id=ko');
  await connect();
  let v = await view();
  check('one request for the object', await requests(), ['GET /knowledge/ko/provenance?limit=200']);
  check('header: back to Knowledge, the name, the count', [v.crumb, v.title, v.count],
    [['#screen-knowledge', 'Knowledge'], 'Taranjabin', 'Claims shown: 3 of 5']);
  check('claim 1: header and both links, looked up in the maps', v.claims[0].rows, [
    ['claim', 'Claim', 'contains mannitol', 'Approved ' + MD + ' Aggregate strength: moderate', false],
    ['evidence', 'Supports', 'Mannitol measured at 40%.', 'Review 2025 ' + MD + ' Verified ' + MD + ' Direct', true],
    ['conflict', 'Contradicts', 'Not found in a related species.', 'Survey 2023 ' + MD + ' Pending review ' + MD + ' Indirect', true]]);
  check('claim 2: an unknown status shown as sent; shared evidence reused', v.claims[1].rows, [
    ['claim', 'Claim', 'contains sucrose', 'odd_status ' + MD + ' Aggregate strength: unverified', false],
    ['evidence', 'Supports', 'Mannitol measured at 40%.', 'Review 2025 ' + MD + ' Verified ' + MD + ' Direct', true]]);
  check('claim 3: no links', [v.claims[2].rows.length, v.claims[2].none], [1, 'No evidence is linked to this claim.']);
  check('source titles link to Source detail', v.sourceLinks, ['#screen-detail?id=src-1', '#screen-detail?id=src-2', '#screen-detail?id=src-1']);
  check('remove button: spoken name and tooltip', v.button,
    ['Remove this evidence link from the claim ' + fa(0x2014) + ' the evidence record itself is kept', 'Remove this evidence link']);

  // Remove a link: cancel, then accept.
  let before = (await requests()).length;
  page.once('dialog', (d) => d.dismiss());
  await page.click('.prov-claims li[data-fan] button'); await settle();
  check('a cancelled confirm sends nothing', (await requests()).slice(before), []);
  page.once('dialog', (d) => d.accept());
  await page.click('.prov-claims li[data-fan] button'); await settle();
  v = await view();
  check('accept: DELETE the link, then one reload', (await requests()).slice(before),
    ['DELETE /claim-evidence/link-a', 'GET /knowledge/ko/provenance?limit=200']);
  check('after removal: the message and the claim without that link', [v.said, v.claims[0].rows.map((r) => r[2])],
    [['done', 'Evidence link removed.'], ['contains mannitol', 'Not found in a related species.']]);
  await page.evaluate(() => { window.__deleteStatus = 403; });
  page.once('dialog', (d) => d.accept());
  await page.click('.prov-claims li[data-fan] button'); await settle();
  v = await view();
  check('403: said, and the button stays', [v.said, v.claims[0].rows[1][4]],
    [['denied', 'Your role is not allowed to remove evidence links (HTTP 403).'], true]);
  await page.evaluate(() => { window.__deleteStatus = 204; });

  // A viewer sees no remove button (the role is read on connect).
  await page.evaluate(() => { window.__role = 'viewer'; });
  await connect();
  v = await view();
  check('viewer: no remove buttons, and an earlier message is cleared', [v.claims.flatMap((c) => c.rows.map((r) => r[4])), v.said[1]],
    [[false, false, false, false, false], '']);

  await go('#screen-provenance');
  v = await view();
  check('no id: the message, no claims', [v.state, v.message, v.claims, v.title, v.count],
    ['empty', 'No knowledge object selected. Open one from Knowledge.', null, 'Provenance', null]);
  await go('#screen-provenance?id=missing');
  v = await view();
  check('404: not found', [v.state, v.message, v.claims], ['empty', 'This knowledge object was not found.', null]);
  await go('#screen-provenance?id=boom');
  v = await view();
  check('500: the error with Retry', [v.state, v.message, v.action], ['error', 'Could not load provenance (' + iso('HTTP 500') + ').', 'Retry']);
  before = (await requests()).length;
  await page.click('#screen-provenance [data-live-keep] .know-status button'); await settle();
  check('Retry sends the same request again', (await requests()).slice(before), ['GET /knowledge/boom/provenance?limit=200']);
  await go('#screen-provenance?id=empty');
  v = await view();
  check('no claims: the message, no count', [v.title, v.state, v.message, v.count, v.claims],
    ['Taranjabin', 'empty', 'This knowledge object has no claims yet.', null, []]);

  // Persian over live content (an identity entry would hang here).
  await go('#screen-provenance?id=ko');
  await lang('fa');
  v = await view();
  check('fa: count, relations, claim status and strength', [v.count, v.claims[0].rows[0][3], v.claims[0].rows[1][1], v.claims[0].rows[1][3]],
    [FA.count, FA.approved + ' ' + MD + ' ' + FA.moderate, FA.contradicts, 'Survey 2023 ' + MD + ' ' + FA.pending + ' ' + MD + ' ' + FA.indirect]);
  check('fa: no links', v.claims[2].none, FA.noLinks);
  await go('#screen-provenance?id=missing');
  check('fa: not found', (await view()).message, FA.notFound);
  await lang('en');
  await go('#screen-provenance?id=ko');
  check('back to English', (await view()).count, 'Claims shown: 3 of 5');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
