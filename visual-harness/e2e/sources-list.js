#!/usr/bin/env node
/*
 * Component-level browser checks for the live Sources list (Step 7A2a).
 *   Sample mode: the 7 designed rows with the five real statuses, no Export or
 *           More actions, in English and Persian.
 *   Live:   the rows are replaced (never mixed back in when the screen is shown
 *           again), seven columns, each meta-line form, badges, counts, date,
 *           the Open link's name, Persian rows; Filter and Sort wait for 7A2b.
 *   States: Loading on the first load, empty with Add source, an error with
 *           Retry repeating the request, 401/403 with Reconnect.
 *   Pager and the grid view.
 * Runs on file:// with GET /sources/overview mocked in the page and every
 * request recorded. Persian expectations are built from code points, so this
 * file stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/sources-list.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-sources';
const fa = (...codes) => String.fromCharCode(...codes);
const DOT = ' ' + String.fromCharCode(0xB7) + ' ', FSI = String.fromCharCode(0x2068), PDI = String.fromCharCode(0x2069);
const FA = {
  completed: fa(0x62A, 0x6A9, 0x645, 0x6CC, 0x644, 0x200C, 0x634, 0x62F, 0x647),
  processing: fa(0x62F, 0x631, 0x20, 0x62D, 0x627, 0x644, 0x20, 0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634),
  abstractOnly: fa(0x641, 0x642, 0x637, 0x20, 0x686, 0x6A9, 0x6CC, 0x62F, 0x647),
  failed: fa(0x646, 0x627, 0x645, 0x648, 0x641, 0x642),
  referenceOnly: fa(0x641, 0x642, 0x637, 0x20, 0x627, 0x631, 0x62C, 0x627, 0x639),
  scientificPaper: fa(0x645, 0x642, 0x627, 0x644, 0x647, 0x20, 0x639, 0x644, 0x645, 0x6CC),
  seventyFour: fa(0x6F7, 0x6F4),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const counts = (documents, knowledge_objects, claims, evidence) => ({ documents, knowledge_objects, claims, evidence });
const ITEMS = [
  { id: 'a', title: 'Toranjebin review', source_type: 'scientific_paper', doi: '10.1/x', pmid: null, url: null, derived_status: 'completed',
    counts: counts(1, 3, 74, 31), last_activity_at: '2026-10-23T10:00:00Z', file_size: 2936013, mime_type: 'application/pdf' },
  { id: 'b', title: 'Saffron lab series', source_type: 'lab_report', doi: null, pmid: null, url: null, derived_status: 'processing',
    counts: counts(3, 1, 0, 0), last_activity_at: '2026-10-22T10:00:00Z', file_size: 90112, mime_type: null },
  { id: 'c', title: 'Mannitol in Alhagi exudates', source_type: 'scientific_paper', doi: '10.1016/j.jep.2024.118233', pmid: '39214477',
    url: null, derived_status: 'abstract_only', counts: counts(0, 2, 9, 4), last_activity_at: '2026-10-21T10:00:00Z', file_size: null, mime_type: null },
  { id: 'd', title: 'toranjebin.ir product page', source_type: 'web_page', doi: null, pmid: null, url: 'https://toranjebin.ir/p',
    derived_status: 'reference_only', counts: counts(0, 1, 4, 2), last_activity_at: '2026-10-20T10:00:00Z', file_size: null, mime_type: null },
  { id: 'e', title: 'Herbal review draft', source_type: 'user_upload', doi: null, pmid: null, url: null, derived_status: 'failed',
    counts: counts(1, 0, 0, 0), last_activity_at: '2026-10-19T10:00:00Z', file_size: 14889779, mime_type: 'application/msword' },
];

// The mock: answers /sources/overview with the items above, records every
// query, and fakes a long list (window.__total), a slow reply (window.__delay),
// a failure (window.__fail = HTTP status) or an empty organization (window.__empty).
function installMock(items) {
  window.__requests = []; window.__total = 0; window.__delay = 0; window.__fail = 0; window.__empty = false;
  const respond = (body, status, delay) => new Promise((ok) => setTimeout(() => ok(new Response(JSON.stringify(body), { status: status || 200 })), delay || 0));
  window.fetch = (u) => {
    u = String(u);
    if (u.includes('/sources/overview?')) {
      const q = new URLSearchParams(u.slice(u.indexOf('?') + 1)); window.__requests.push(q.toString());
      const limit = Number(q.get('limit')), offset = Number(q.get('offset'));
      if (window.__fail) return respond({}, window.__fail, window.__delay);
      let list = window.__empty ? [] : items.slice(), total = list.length;
      if (window.__total) {
        total = window.__total;
        list = Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, i) =>
          Object.assign({}, items[i % items.length], { id: 'p' + (offset + i), title: 'Item ' + (offset + i) }));
      }
      return respond({ items: list, total, limit, offset, counts_by_status: {} }, 200, window.__delay);
    }
    return respond({ items: [], total: 0, limit: 20, offset: 0 }, u.includes('/users/me/preferences') ? 404 : 200);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', (e) => { failures++; console.log('PAGE ERROR ' + e.message); });
  await page.goto(pageUrl);
  const settle = (ms) => page.waitForTimeout(ms || 150);
  const requests = () => page.evaluate(() => window.__requests);
  const last = async () => (await requests()).slice(-1)[0];
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = () => page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok'));
  const badges = () => page.$$eval('#screen-sources tbody td[data-label="Status"] .badge', (b) => b.map((x) => [x.textContent.trim(), x.className.replace('badge ', '')]));
  const statusOf = () => page.$eval('#screen-sources .know-status', (s) => {
    const b = s.querySelector('button');
    return [s.dataset.state, s.querySelector('p').textContent, b.hidden ? null : b.textContent];
  });
  const shown = (sel) => page.$eval(sel, (n) => getComputedStyle(n).display !== 'none');

  // ---------- Sample mode ----------
  check('sample: 7 designed rows, the five real statuses', await badges(), [
    ['Completed', 'badge--success'], ['Processing', 'badge--processing'], ['Abstract only', 'badge--warning'], ['Completed', 'badge--success'],
    ['Completed', 'badge--success'], ['Failed', 'badge--danger'], ['Reference only', 'badge--unknown']]);
  check('sample: no Export, no More actions; Filter and Sort shown', await page.evaluate(() => [
    [...document.querySelectorAll('#screen-sources .page-actions .btn')].some((b) => b.textContent.trim() === 'Export'),
    document.querySelectorAll('#screen-sources [aria-label="More actions for this source"]').length]).then(async (r) => r.concat(
    [await shown('#src-filter'), await shown('#src-sort')])), [false, 0, true, true]);
  await lang('fa');
  check('fa sample: the same 7 rows, statuses in Persian', (await badges()).map((b) => b[0]),
    [FA.completed, FA.processing, FA.abstractOnly, FA.completed, FA.completed, FA.failed, FA.referenceOnly]);
  await lang('en');

  // ---------- First load ----------
  await page.evaluate(installMock, ITEMS);
  await page.evaluate(() => { window.__delay = 300; });
  await connect();
  await settle(100);
  check('first load: sample rows gone, Loading where the rows go', await page.evaluate(() => [
    document.querySelectorAll('#screen-sources tbody tr').length]).then(async (r) => r.concat(await statusOf())),
  [0, 'loading', 'Loading' + String.fromCharCode(0x2026), null]);
  await page.evaluate(() => { window.__delay = 0; });
  await page.waitForSelector('#screen-sources tbody tr[data-source-id]');
  check('first request: newest first, 50 rows, page 1', await requests(), ['sort=updated&limit=50&offset=0']);
  check('Loading clears with the reply', await statusOf(), ['', '', null]);

  // ---------- Rows ----------
  check('seven columns; the last is for screen readers only', await page.$$eval('#screen-sources thead th', (ths) => ths.map((th) =>
    [th.textContent.trim(), !!th.querySelector('.visually-hidden')])),
  [['Source', false], ['Status', false], ['Knowledge', false], ['Claims', false], ['Evidence', false], ['Updated', false], ['Open', true]]);
  // Sample rows have no data-source-id and no hidden Open name: they read as null, so a mix fails a check instead of the run.
  const rows = () => page.$$eval('#screen-sources tbody tr', (trs) => trs.map((tr) => {
    const t = (l) => tr.querySelector('td[data-label="' + l + '"]').textContent.trim();
    const spoken = tr.querySelector('a.btn .visually-hidden');
    return { id: tr.dataset.sourceId || null, title: tr.querySelector('.source-cell__title').textContent, meta: tr.querySelector('.source-cell__meta').textContent,
      counts: [t('Knowledge'), t('Claims'), t('Evidence')], updated: t('Updated'),
      open: [tr.querySelector('a.btn').getAttribute('href'), spoken ? spoken.textContent : null] };
  }));
  const en = await rows();
  check('live rows replace the sample, in server order', en.map((r) => r.id), ['a', 'b', 'c', 'd', 'e']);
  check('meta: one document, its size and file type', en[0].meta, 'Scientific paper' + DOT + '2.8 MB' + DOT + 'application/pdf');
  check('meta: several documents, their size, no file type', en[1].meta, 'Lab report' + DOT + '3 documents' + DOT + '88 KB');
  check('meta: no document, DOI and PMID', en[2].meta, 'Scientific paper' + DOT + 'DOI 10.1016/j.jep.2024.118233' + DOT + 'PMID 39214477');
  check('meta: no document, URL; an unknown type as sent', en[3].meta, 'web_page' + DOT + 'https://toranjebin.ir/p');
  check('meta: identifiers in <bdi dir=ltr>', await page.$$eval('#screen-sources tbody tr[data-source-id="c"] .source-cell__meta bdi',
    (b) => b.map((x) => [x.textContent, x.dir])), [['10.1016/j.jep.2024.118233', 'ltr'], ['39214477', 'ltr']]);
  check('status badges', await badges(), [['Completed', 'badge--success'], ['Processing', 'badge--processing'],
    ['Abstract only', 'badge--warning'], ['Reference only', 'badge--unknown'], ['Failed', 'badge--danger']]);
  check('counts and date', [en[0].counts, en[0].updated], [['3', '74', '31'], '23 Oct 2026']);
  check('Open: the detail screen, named after the source', en[0].open, ['#screen-detail', 'Open ' + FSI + 'Toranjebin review' + PDI]);
  check('Filter and Sort hidden until 7A2b', [await shown('#src-filter'), await shown('#src-sort')], [false, false]);
  await lang('fa');
  const faRow = (await rows())[0];
  check('fa: badge, type label and digits in Persian', [(await badges())[0][0], faRow.meta.split(DOT)[0], faRow.counts[1]],
    [FA.completed, FA.scientificPaper, FA.seventyFour]);
  await lang('en');

  // Showing the screen again must not bring the sample rows back.
  await page.evaluate(() => { location.hash = '#screen-dashboard'; }); await settle();
  await page.evaluate(() => { location.hash = '#screen-sources'; }); await settle();
  check('screen shown again: live rows only', (await rows()).map((r) => r.id), ['a', 'b', 'c', 'd', 'e']);

  // ---------- Grid view ----------
  await page.click('#src-view-grid'); await settle(300);
  check('grid view: same rows as cards', await page.evaluate(() => [document.querySelector('#screen-sources .table-wrap').classList.contains('is-grid'),
    document.querySelectorAll('#screen-sources tbody tr[data-source-id]').length]), [true, 5]);
  await page.click('#src-view-list'); await settle(300);

  // ---------- Pager ----------
  const pagerState = () => page.evaluate(() => {
    const pg = document.querySelector('#screen-sources .know-pager'), b = pg.querySelectorAll('button');
    return [pg.querySelector('.know-pager__text').textContent, b[0].disabled, b[1].disabled];
  });
  check('one page: Showing 1 to 5 of 5, both buttons off', await pagerState(), ['Showing 1 to 5 of 5', true, true]);
  await page.evaluate(() => { window.__total = 120; }); await connect(); await settle();
  check('a later connect reloads, wired once: one status box, one pager', await page.evaluate(() =>
    [document.querySelectorAll('#screen-sources .know-status').length, document.querySelectorAll('#screen-sources .know-pager').length]), [1, 1]);
  check('long list: page 1 of 120', await pagerState(), ['Showing 1 to 50 of 120', true, false]);
  await page.click('#screen-sources .know-pager button:nth-of-type(2)'); await settle();
  check('Next: offset 50', [await last(), (await pagerState())[0]], ['sort=updated&limit=50&offset=50', 'Showing 51 to 100 of 120']);
  await page.click('#screen-sources .know-pager button:nth-of-type(2)'); await settle();
  check('last page: Next off', await pagerState(), ['Showing 101 to 120 of 120', false, true]);
  await page.click('#screen-sources .know-pager button:nth-of-type(1)'); await settle();
  check('Previous: offset 50', await last(), 'sort=updated&limit=50&offset=50');
  await page.selectOption('#screen-sources .know-pager select', '25'); await settle();
  check('rows per page: 25, back to page 1', [await last(), (await pagerState())[0]], ['sort=updated&limit=25&offset=0', 'Showing 1 to 25 of 120']);

  // ---------- Empty ----------
  await page.evaluate(() => { window.__total = 0; window.__empty = true; }); await connect(); await settle();
  check('empty: no rows, the message and Add source', [(await rows()).length, await statusOf()], [0, ['empty', 'No sources yet.', 'Add source']]);
  await page.click('#screen-sources .know-status button'); await settle();
  check('Add source opens the Add source screen', await page.evaluate(() => location.hash), '#screen-add');
  await page.evaluate(() => { location.hash = '#screen-sources'; window.__empty = false; }); await settle();

  // ---------- Error and Retry ----------
  await page.evaluate(() => { window.__fail = 500; }); await connect(); await settle();
  const failedQuery = await last();
  check('error: no rows, no pager text, the error and Retry', [(await rows()).length, (await pagerState())[0], await statusOf()],
    [0, '', ['error', 'Could not load sources (' + FSI + 'HTTP 500' + PDI + ').', 'Retry']]);
  await page.evaluate(() => { window.__fail = 0; });
  await page.click('#screen-sources .know-status button'); await settle();
  check('Retry sends the same request again and the rows return', [await last(), (await rows()).length, (await statusOf())[0]], [failedQuery, 5, '']);

  // ---------- 401 and 403 ----------
  await page.evaluate(() => { window.__fail = 401; }); await connect(); await settle();
  check('401: the token was not accepted, Reconnect offered', await statusOf(),
    ['denied', 'Cloud Core did not accept the access token (HTTP 401). It may have expired.', 'Reconnect']);
  await page.click('#screen-sources .know-status button'); await settle();
  check('Reconnect opens this panel\'s connect form at the token', await page.evaluate(() => {
    const f = document.querySelector('#live-screen-sources .live-connect');
    return [f.hidden, document.activeElement === f.querySelector('.live-token'), f.querySelector('.live-base').value];
  }), [false, true, 'http://core.test']);
  await page.evaluate(() => { window.__fail = 403; }); await connect(); await settle();
  check('403: sources may not be read, Reconnect offered', await statusOf(),
    ['denied', 'This access token is not allowed to read sources (HTTP 403).', 'Reconnect']);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
