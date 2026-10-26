#!/usr/bin/env node
/*
 * Browser checks for the live Source detail header (Step 7B2b-2).
 *   Sample: the designed header is shown and nothing is requested.
 *   Live:   #screen-detail?id=<id> reads GET /sources/overview?id=<id> once,
 *           with no list filters; the sample breadcrumbs and header give way
 *           to the source's title, status badge, the four counts and its
 *           metadata. GET /auth/me is read once per connection.
 *   States: no id, 404 (no server text shown), 500 with Retry, 403 with
 *           Reconnect; English and Persian.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/source-detail.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-detail';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = String.fromCharCode(0x2068), PDI = String.fromCharCode(0x2069);
const FA = {
  notSelected: fa(0x647, 0x6CC, 0x686, 0x20, 0x645, 0x646, 0x628, 0x639, 0x6CC, 0x20, 0x627, 0x646, 0x62A, 0x62E, 0x627, 0x628, 0x20, 0x646, 0x634, 0x62F, 0x647, 0x20, 0x627, 0x633, 0x62A, 0x2E, 0x20, 0x6CC, 0x6A9, 0x6CC, 0x20, 0x631, 0x627, 0x20, 0x627, 0x632, 0x20, 0xAB, 0x645, 0x646, 0x627, 0x628, 0x639, 0x20, 0x648, 0x20, 0x627, 0x633, 0x646, 0x627, 0x62F, 0xBB, 0x20, 0x628, 0x627, 0x632, 0x20, 0x6A9, 0x646, 0x6CC, 0x62F, 0x2E),
  notFound: fa(0x627, 0x6CC, 0x646, 0x20, 0x645, 0x646, 0x628, 0x639, 0x20, 0x67E, 0x6CC, 0x62F, 0x627, 0x20, 0x646, 0x634, 0x62F, 0x2E),
  couldNotLoadBefore: fa(0x628, 0x627, 0x631, 0x6AF, 0x630, 0x627, 0x631, 0x6CC, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x645, 0x646, 0x628, 0x639, 0x20, 0x646, 0x627, 0x645, 0x648, 0x641, 0x642, 0x20, 0x628, 0x648, 0x62F, 0x20, 0x28),
  couldNotLoadAfter: fa(0x29, 0x2E),
  documents: fa(0x627, 0x633, 0x646, 0x627, 0x62F),
  knowledgeObjects: fa(0x67E, 0x631, 0x648, 0x646, 0x62F, 0x647, 0x200C, 0x647, 0x627, 0x6CC, 0x20, 0x62F, 0x627, 0x646, 0x634),
  claims: fa(0x627, 0x62F, 0x639, 0x627, 0x647, 0x627),
  evidence: fa(0x634, 0x648, 0x627, 0x647, 0x62F),
  sourceType: fa(0x646, 0x648, 0x639, 0x20, 0x645, 0x646, 0x628, 0x639),
  author: fa(0x646, 0x648, 0x6CC, 0x633, 0x646, 0x62F, 0x647),
  publisher: fa(0x646, 0x627, 0x634, 0x631),
  publicationDate: fa(0x62A, 0x627, 0x631, 0x6CC, 0x62E, 0x20, 0x627, 0x646, 0x62A, 0x634, 0x627, 0x631),
  lastActivity: fa(0x622, 0x62E, 0x631, 0x6CC, 0x646, 0x20, 0x641, 0x639, 0x627, 0x644, 0x6CC, 0x62A),
  retry: fa(0x62A, 0x644, 0x627, 0x634, 0x20, 0x645, 0x62C, 0x62F, 0x62F),
  completed: fa(0x62A, 0x6A9, 0x645, 0x6CC, 0x644, 0x200C, 0x634, 0x62F, 0x647),
  scientificPaper: fa(0x645, 0x642, 0x627, 0x644, 0x647, 0x20, 0x639, 0x644, 0x645, 0x6CC),
  seventyFour: fa(0x6F7, 0x6F4),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const ITEM = { id: 'a', title: 'Toranjebin review', source_type: 'scientific_paper', author: 'A. Author', publisher: 'J Ethnopharm',
  publication_date: '2025-03-01', doi: '10.1/x', pmid: null, url: null, derived_status: 'completed',
  counts: { documents: 1, knowledge_objects: 3, claims: 74, evidence: 31 }, last_activity_at: '2026-10-23T10:00:00Z',
  file_size: 2936013, mime_type: 'application/pdf' };

// The mock: id "a" is the item above; "missing" is a 404 whose body carries a
// server message the page must not show; "boom" is a 500; "deny" a 403.
function installMock(item) {
  window.__requests = [];
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7); window.__requests.push(p);
    if (p.indexOf('/sources/overview?') === 0) {
      const id = new URLSearchParams(p.slice(p.indexOf('?') + 1)).get('id');
      if (id === 'a') return reply({ items: [item], total: 1, limit: 50, offset: 0, counts_by_status: {} });
      if (id === 'missing') return reply({ error: { message: 'Source not found' } }, 404);
      if (id === 'deny') return reply({}, 403);
      return reply({}, 500);
    }
    if (p === '/auth/me') return reply({ user: { role: 'editor' }, organization: {} });
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
  const requests = () => page.evaluate(() => window.__requests || []);
  const shown = (e) => !!e && getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0;
  const view = () => page.evaluate((shownSrc) => {
    const shown = new Function('return ' + shownSrc)();
    const s = document.getElementById('screen-detail'), h1 = document.getElementById('h-detail-live');
    const box = s.querySelector('[data-live-keep] .know-status'), act = box && box.querySelector('button');
    const dls = Array.from(s.querySelectorAll('.src-detail-facts dl'));
    const pairs = (dl) => Array.from(dl.querySelectorAll('dt')).map((dt) => [dt.textContent, dt.nextElementSibling.textContent]);
    return {
      sampleHeader: shown(document.getElementById('h-detail')), liveTitle: shown(h1) ? h1.textContent : null,
      crumb: h1 ? s.querySelector('[data-live-keep] .breadcrumbs').lastElementChild.textContent : null,
      badge: shown(h1) && s.querySelector('#h-detail-live + p .badge') ? s.querySelector('#h-detail-live + p .badge').textContent : null,
      counts: dls[0] && shown(dls[0]) ? pairs(dls[0]) : null, about: dls[1] && shown(dls[1]) ? pairs(dls[1]).map((p) => p[0]) : null,
      aboutValues: dls[1] && shown(dls[1]) ? pairs(dls[1]).slice(0, 3).map((p) => p[1]) : null,
      state: box ? box.dataset.state : null, message: box ? box.querySelector('p').textContent : null,
      action: act && !act.hidden ? act.textContent : null, labelledby: s.getAttribute('aria-labelledby'),
    };
  }, shown.toString());

  // Sample mode
  let v = await view();
  check('sample: the designed header shows, no live header', [v.sampleHeader, v.liveTitle], [true, null]);
  check('sample: nothing is requested', await requests(), []);

  // Live: the header is the overview row
  await page.evaluate(installMock, ITEM);
  await go('#screen-detail?id=a');
  await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle();
  v = await view();
  check('live: sample header hidden, live title, breadcrumb and badge', [v.sampleHeader, v.liveTitle, v.crumb, v.badge],
    [false, 'Toranjebin review', 'Toranjebin review', 'Completed']);
  check('live: the four counts', v.counts, [['Documents', '1'], ['Knowledge objects', '3'], ['Claims', '74'], ['Evidence', '31']]);
  check('live: metadata labels', v.about, ['Source type', 'Author', 'Publisher', 'Publication date', 'Last activity']);
  check('live: metadata values (type, author, publisher)', v.aboutValues, ['Scientific paper', 'A. Author', 'J Ethnopharm']);
  check('live: no status message, section named by the live title', [v.state, v.labelledby], ['', 'h-detail-live']);
  // The Sources list loads on connect too; the detail's requests are the ones with an id.
  check('live: one overview request, the id only (no list filters)', (await requests()).filter((r) => r.startsWith('/sources/overview?id=')),
    ['/sources/overview?id=a']);

  // States
  await go('#screen-detail');
  v = await view();
  check('no id: the message, the generic heading, no facts', [v.state, v.message, v.liveTitle, v.counts, v.action],
    ['empty', 'No source selected. Open one from Sources & Documents.', 'Source detail', null, null]);   // 7B2c: the heading still names the section
  await go('#screen-detail?id=missing');
  v = await view();
  check('404: one sentence, the generic heading', [v.state, v.message, v.liveTitle, v.action], ['empty', 'This source was not found.', 'Source detail', null]);
  check('404: the server message is not shown', (await page.$eval('#screen-detail', (s) => s.textContent)).includes('Source not found'), false);
  await go('#screen-detail?id=boom');
  v = await view();
  check('500: the error with its status, and Retry', [v.state, v.message, v.action],
    ['error', 'Could not load this source (' + FSI + 'HTTP 500' + PDI + ').', 'Retry']);
  const before = (await requests()).length;
  const retry = await page.$('#screen-detail [data-live-keep] .know-status button');
  if (retry) await retry.click();
  await settle();
  check('Retry sends the same request again', (await requests()).slice(before), ['/sources/overview?id=boom']);
  await go('#screen-detail?id=deny');
  v = await view();
  check('403: the read-sources sentence and Reconnect', [v.state, v.message, v.action],
    ['denied', 'This access token is not allowed to read sources (HTTP 403).', 'Reconnect']);
  check('GET /auth/me read once for the connection', (await requests()).filter((r) => r === '/auth/me').length, 1);

  // Persian
  await lang('fa');
  await go('#screen-detail');
  check('fa: no id', (await view()).message, FA.notSelected);
  await go('#screen-detail?id=missing');
  check('fa: 404', (await view()).message, FA.notFound);
  await go('#screen-detail?id=boom');
  v = await view();
  check('fa: 500 and Retry', [v.message, v.action], [FA.couldNotLoadBefore + FSI + 'HTTP 500' + PDI + FA.couldNotLoadAfter, FA.retry]);
  await go('#screen-detail?id=a');
  v = await view();
  check('fa: count labels and a Persian count', [v.counts && v.counts.map((p) => p[0]), v.counts && v.counts[2][1]],
    [[FA.documents, FA.knowledgeObjects, FA.claims, FA.evidence], FA.seventyFour]);
  check('fa: metadata labels', v.about, [FA.sourceType, FA.author, FA.publisher, FA.publicationDate, FA.lastActivity]);
  check('fa: badge and source type; the title stays as written', [v.badge, v.aboutValues && v.aboutValues[0], v.liveTitle],
    [FA.completed, FA.scientificPaper, 'Toranjebin review']);
  await lang('en');
  check('back to English: labels in English again', (await view()).about, ['Source type', 'Author', 'Publisher', 'Publication date', 'Last activity']);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
