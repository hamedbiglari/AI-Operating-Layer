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
 *   Controls (7A2b): search (debounce, Enter, Escape, stale replies dropped),
 *           the filter panel with status counts, type and an exact other type,
 *           chips, the sort panel, no matches with Clear filters, status links
 *           (#screen-sources?status=...) in sample and live mode, Persian labels.
 *   Sample text (7A4): the counter, sizes, titles, the view group and the
 *           A-Z sort in English and Persian, across language switches.
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
  sortMostClaims: fa(0x645, 0x631, 0x62A, 0x628, 0x200C, 0x633, 0x627, 0x632, 0x6CC, 0x3A, 0x20, 0x628, 0x6CC, 0x634, 0x62A, 0x631, 0x6CC, 0x646, 0x20, 0x627, 0x62F, 0x639, 0x627),
  failedOne: fa(0x646, 0x627, 0x645, 0x648, 0x641, 0x642, 0x20, 0x28, 0x6F1, 0x29),
  placeholder: fa(0x62C, 0x633, 0x62A, 0x200C, 0x648, 0x62C, 0x648, 0x20, 0x628, 0x627, 0x20, 0x639, 0x646, 0x648, 0x627, 0x646, 0x60C, 0x20) + 'DOI' +
    fa(0x60C, 0x20) + 'PMID' + fa(0x20, 0x6CC, 0x627, 0x20, 0x646, 0x634, 0x627, 0x646, 0x6CC, 0x20, 0x648, 0x628, 0x2026),
  // Sample text (7A4)
  showingAll7: fa(0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x647, 0x645, 0x647, 0x654, 0x20, 0x6F7, 0x20, 0x645, 0x646, 0x628, 0x639, 0x2E),
  showing3of7: fa(0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x6F3, 0x20, 0x627, 0x632, 0x20, 0x6F7, 0x20, 0x645, 0x646, 0x628, 0x639, 0x2E),
  noMatch: fa(0x647, 0x6CC, 0x686, 0x20, 0x645, 0x646, 0x628, 0x639, 0x6CC, 0x20, 0x628, 0x627, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x62C, 0x633, 0x62A, 0x200C, 0x648, 0x62C, 0x648, 0x20, 0x645, 0x637, 0x627, 0x628, 0x642, 0x62A, 0x20, 0x646, 0x62F, 0x627, 0x631, 0x62F, 0x2E),
  status: fa(0x648, 0x636, 0x639, 0x6CC, 0x62A),
  showAll: fa(0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x647, 0x645, 0x647, 0x654, 0x20, 0x645, 0x646, 0x627, 0x628, 0x639),
  mb28: fa(0x6F2, 0x66B, 0x6F8, 0x20, 0x645, 0x6AF, 0x627, 0x628, 0x627, 0x6CC, 0x62A),
  displayMode: fa(0x62D, 0x627, 0x644, 0x62A, 0x20, 0x646, 0x645, 0x627, 0x6CC, 0x634),
  sort: fa(0x645, 0x631, 0x62A, 0x628, 0x200C, 0x633, 0x627, 0x632, 0x6CC),
  nameAZ: fa(0x646, 0x627, 0x645, 0x20, 0x28, 0x627, 0x644, 0x641, 0x20, 0x62A, 0x627, 0x20, 0x6CC, 0x29),
  nameZA: fa(0x646, 0x627, 0x645, 0x20, 0x28, 0x6CC, 0x20, 0x62A, 0x627, 0x20, 0x627, 0x644, 0x641, 0x29),
  sortedAZ: fa(0x645, 0x631, 0x62A, 0x628, 0x200C, 0x634, 0x62F, 0x647, 0x20, 0x628, 0x631, 0x20, 0x627, 0x633, 0x627, 0x633, 0x20, 0x646, 0x627, 0x645, 0x20, 0x28, 0x627, 0x644, 0x641, 0x20, 0x62A, 0x627, 0x20, 0x6CC, 0x29),
  sortedZA: fa(0x645, 0x631, 0x62A, 0x628, 0x200C, 0x634, 0x62F, 0x647, 0x20, 0x628, 0x631, 0x20, 0x627, 0x633, 0x627, 0x633, 0x20, 0x646, 0x627, 0x645, 0x20, 0x28, 0x6CC, 0x20, 0x62A, 0x627, 0x20, 0x627, 0x644, 0x641, 0x29),
  sortByNameAsc: fa(0x645, 0x631, 0x62A, 0x628, 0x200C, 0x633, 0x627, 0x632, 0x6CC, 0x20, 0x628, 0x631, 0x20, 0x627, 0x633, 0x627, 0x633, 0x20, 0x646, 0x627, 0x645, 0x60C, 0x20, 0x635, 0x639, 0x648, 0x62F, 0x6CC),
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
      const search = q.get('search');
      let list = window.__empty ? [] : items.slice(), total = list.length;
      if (window.__total) {
        total = window.__total;
        list = Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, i) =>
          Object.assign({}, items[i % items.length], { id: 'p' + (offset + i), title: 'Item ' + (offset + i) }));
      }
      // A search returns one "<search>-result" row; search=slow answers late.
      if (search && !window.__empty) { list = [Object.assign({}, items[0], { id: 's-' + search, title: search + '-result' })]; total = 1; }
      const byStatus = { failed: 1, processing: 1, completed: 1, abstract_only: 1, reference_only: 1 };
      return respond({ items: list, total, limit, offset, counts_by_status: byStatus }, 200, search === 'slow' ? 600 : window.__delay);
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
  // A status link in sample mode keeps the sample rows with that status.
  await page.evaluate(() => { location.hash = '#screen-sources?status=completed'; }); await settle();
  check('sample: a status link keeps the rows with that status', await page.$$eval('#screen-sources tbody tr:not(.is-filtered) td[data-label="Status"] .badge',
    (b) => b.map((x) => x.textContent.trim())), ['Completed', 'Completed', 'Completed']);
  await page.evaluate(() => { location.hash = '#screen-dashboard'; }); await settle();
  check('Dashboard: the Succeeded card links to completed sources', await page.$eval('#dash-stats a[data-stat="succeeded"]', (a) => a.getAttribute('href')),
    '#screen-sources?status=completed');
  await page.evaluate(() => { location.hash = '#screen-sources'; }); await settle();

  // Sample text in both languages (7A4): the counter, sizes, titles, the view
  // group and the A-Z sort, each following a language switch.
  const counter = () => page.$eval('#src-search-count', (p) => p.textContent);
  const sizes = () => page.$$eval('#screen-sources [data-sample-mb], #screen-sources [data-sample-kb]', (s) => s.map((x) => x.textContent));
  const sortState = () => page.evaluate(() => [document.getElementById('src-sort-label').textContent, document.getElementById('src-sort').getAttribute('aria-label')]);
  const isolated = async () => (await counter() + (await sizes()).join('')).split('').some((c) => c === FSI || c === PDI);
  const viewGroup = () => page.$eval('#screen-sources .page-actions [role="group"]', (g) => g.getAttribute('aria-label'));
  check('sample: counter, sizes and the view group in English', [await counter(), await sizes(), await viewGroup()],
    ['Showing all 7 sources.', ['2.8 MB', '1.1 MB', '640 KB', '88 KB', '14.2 MB'], 'Display mode']);
  check('sample: titles in <bdi dir=ltr>, DOI and PMID in bdi.identifier', await page.evaluate(() => [
    document.querySelectorAll('#screen-sources .source-cell__title > bdi[dir="ltr"]').length,
    [...document.querySelectorAll('#screen-sources .source-cell__meta bdi.identifier')].map((b) => b.textContent).filter((t) => /^(DOI|PMID) /.test(t))]),
    [6, ['DOI 10.1016/j.jep.2024.118233', 'PMID 39214477']]);
  await lang('fa');
  check('fa sample: counter, first size and the view group in Persian', [await counter(), (await sizes())[0], await viewGroup()],
    [FA.showingAll7, FA.mb28, FA.displayMode]);
  await page.fill('#src-search', 'zzz'); await settle();
  check('fa sample: a search with no match', await counter(), FA.noMatch);
  await page.fill('#src-search', ''); await settle();
  await page.evaluate(() => { location.hash = '#screen-sources?status=completed'; }); await settle();
  check('fa sample: a status link: count, Status, the badge label and Show all sources', await counter(),
    FA.showing3of7 + ' ' + FA.status + ': ' + FA.completed + '. ' + FA.showAll);
  check('no isolate marks in the counter or sizes (fa)', await isolated(), false);
  await lang('en');
  check('back to English: the whole counter, badge label included', await counter(), 'Showing 3 of 7 sources. Status: Completed. Show all sources');
  check('no isolate marks in the counter or sizes (en)', await isolated(), false);
  await page.evaluate(() => { location.hash = '#screen-sources'; }); await settle();
  await lang('fa');
  await page.click('#src-sort'); await settle();
  const az = await sortState();
  await page.click('#src-sort'); await settle();
  const za = await sortState();
  await lang('en'); await lang('fa');
  check('fa sample Sort: A-Z, Z-A, and Z-A again after a switch to English and back', [az, za, await sortState()],
    [[FA.nameAZ, FA.sortedAZ], [FA.nameZA, FA.sortedZA], [FA.nameZA, FA.sortedZA]]);
  await page.click('#src-sort'); await settle();
  const back = await sortState();
  await lang('en');
  check('Sort back to the original order: Sort by name, ascending', [back, await sortState()],
    [[FA.sort, FA.sortByNameAsc], ['Sort', 'Sort by name, ascending']]);

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
  check('live: Filter, Sort and search shown; the sample counter hidden and no longer describing search', await page.evaluate(() => [
    document.getElementById('src-sort-label').textContent, document.getElementById('src-search').getAttribute('aria-describedby'),
    document.getElementById('src-sort').getAttribute('aria-label')]).then(async (r) => [await shown('#src-filter'), await shown('#src-sort'),
    await shown('#src-search'), await shown('#src-search-count')].concat(r)), [true, true, true, false, 'Sort: Recently updated', null, null]);
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


  // ---------- Controls (7A2b) ----------
  await page.evaluate(() => { window.__fail = 0; }); await connect(); await settle();
  const titles = async () => (await rows()).map((r) => r.title);
  const param = (q, k) => new URLSearchParams(q).get(k);
  const count = async () => (await requests()).length;
  let before = await count();
  await page.fill('#src-search', 'saf'); await settle(100);
  check('search: nothing sent while typing', await count(), before);
  await settle(350);
  check('search: one request 300 ms after the last keystroke, page 1', (await requests()).slice(before), ['sort=updated&limit=25&offset=0&search=saf']);
  await page.fill('#src-search', 'saff'); await page.press('#src-search', 'Enter'); await settle(400);
  check('search: Enter sends at once, the debounced copy sends nothing more', (await requests()).filter((q) => q.includes('search=saff')).length, 1);
  await page.press('#src-search', 'Escape'); await settle();
  check('search: Escape clears it', [await page.$eval('#src-search', (i) => i.value), param(await last(), 'search')], ['', null]);
  await page.fill('#src-search', 'slow'); await page.press('#src-search', 'Enter');
  await page.fill('#src-search', 'fast'); await page.press('#src-search', 'Enter'); await settle(800);
  check('stale reply dropped: the slower, older request does not overwrite the newer one', await titles(), ['fast-result']);
  await page.press('#src-search', 'Escape'); await settle();

  await page.click('#src-filter'); await settle();
  check('Filter opens its panel; each status says what it would return', await page.evaluate(() => [
    document.getElementById('src-filter').getAttribute('aria-expanded'), document.getElementById('src-filter-panel').hidden,
    [...document.querySelectorAll('#src-filter-panel select')[0].options].map((o) => o.textContent)]),
  ['true', false, ['All (5)', 'Failed (1)', 'Processing (1)', 'Completed (1)', 'Abstract only (1)', 'Reference only (1)']]);
  const chips = () => page.$$eval('#screen-sources .know-chip', (c) => c.map((x) => [x.querySelector('.visually-hidden').textContent,
    x.textContent.replace(x.querySelector('.visually-hidden').textContent, '')]));
  await page.selectOption('#src-filter-panel select >> nth=0', 'failed'); await settle();
  check('status filter sends status, page 1; a chip shows it', [param(await last(), 'status'), param(await last(), 'offset'), await chips()],
    ['failed', '0', [['Remove filter', 'Status: Failed']]]);
  await page.selectOption('#src-filter-panel select >> nth=1', 'lab_report'); await settle();
  check('type filter sends source_type, status kept', [param(await last(), 'source_type'), param(await last(), 'status')], ['lab_report', 'failed']);
  before = await count();
  await page.selectOption('#src-filter-panel select >> nth=1', '__other'); await settle();
  check('Other type asks for a name and sends nothing yet', await count(), before);
  await page.fill('#src-filter-panel input', 'web_page'); await settle(450);
  check('other type filters by the exact name; its chip shows it in <bdi>', [param(await last(), 'source_type'),
    await page.$$eval('#screen-sources .know-chip bdi', (b) => b.map((x) => x.textContent))], ['web_page', ['web_page']]);
  await page.click('#screen-sources .know-chip >> nth=0'); await settle();
  check('removing the type chip drops source_type and keeps status', [param(await last(), 'source_type'), param(await last(), 'status'),
    (await chips()).length], [null, 'failed', 1]);
  await page.keyboard.press('Escape');

  await page.click('#src-sort'); await settle();
  check('Sort opens four server orders', await page.$$eval('#src-sort-panel button', (b) => b.map((x) => x.textContent)),
    ['Sort: Recently updated', 'Sort: Name', 'Sort: Most claims', 'Sort: Most evidence']);
  await page.click('#src-sort-panel button >> nth=2'); await settle();
  check('Most claims: sort=claims, page 1; the button and the pressed option follow', [param(await last(), 'sort'), param(await last(), 'offset'),
    await page.$eval('#src-sort-label', (l) => l.textContent), await page.$$eval('#src-sort-panel button', (b) => b.map((x) => x.getAttribute('aria-pressed')))],
  ['claims', '0', 'Sort: Most claims', ['false', 'false', 'true', 'false']]);

  await page.evaluate(() => { window.__empty = true; });
  await page.fill('#src-search', 'nothing'); await page.press('#src-search', 'Enter'); await settle();
  check('no matches: the message and Clear filters', await statusOf(), ['empty', 'No sources match this search and these filters.', 'Clear filters']);
  await page.evaluate(() => { window.__empty = false; });
  await page.click('#screen-sources .know-status button'); await settle();
  check('Clear filters drops search, type and status, keeps the sort', [await last(), await page.$eval('#src-search', (i) => i.value), (await chips()).length],
    ['sort=claims&limit=25&offset=0', '', 0]);

  await page.evaluate(() => { location.hash = '#screen-dashboard'; }); await settle();
  await page.evaluate(() => { location.hash = '#screen-sources?status=completed'; }); await settle();
  check('a status link sets the live status filter', [param(await last(), 'status'), await chips()], ['completed', [['Remove filter', 'Status: Completed']]]);
  before = await count();
  await page.evaluate(() => { location.hash = '#screen-sources'; }); await settle();
  check('the screen shown without a link keeps the filter and sends nothing', await count(), before);

  await lang('fa');
  check('fa: placeholder, Sort label and status counts', [await page.$eval('#src-search', (i) => i.placeholder),
    await page.$eval('#src-sort-label', (l) => l.textContent), await page.$eval('#src-filter-panel select', (s) => s.options[1].textContent)],
  [FA.placeholder, FA.sortMostClaims, FA.failedOne]);
  await lang('en');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
