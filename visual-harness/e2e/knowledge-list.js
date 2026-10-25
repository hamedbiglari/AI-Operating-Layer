#!/usr/bin/env node
/*
 * Component-level browser checks for the live Knowledge list (Step 6).
 *   Part A: columns, sort headers and the Sort label, row and card content in
 *           English and Persian, the Research workspace button.
 *   Part B: search (debounce, Enter, Escape, stale replies dropped, busy
 *           cleared only by the newest), the filter panel and its chips, the
 *           sort panel, Show finished (state from the response, search kept),
 *           paging (no second request while one is out), page 1 after every
 *           control, reconnecting (wired once), and New knowledge object.
 *   Part C: a failed request leaves no rows and no pager, Retry repeats it, a
 *           slow failure that lost the race is ignored, 401/403 offer Reconnect,
 *           and the two empty states with their actions.
 * Runs on file:// with GET /knowledge/overview mocked in the page and every
 * request recorded. Persian expectations are built from code points, so this
 * file stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/knowledge-list.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');

const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-knowledge';
const fa = (...codes) => String.fromCharCode(...codes);
const DOT = ' ' + String.fromCharCode(0xB7) + ' ', FSI = String.fromCharCode(0x2068), PDI = String.fromCharCode(0x2069);
const FA = {
  knowledgeObject: fa(0x67E, 0x631, 0x648, 0x646, 0x62F, 0x647, 0x20, 0x62F, 0x627, 0x646, 0x634),
  actionNeeded: fa(0x627, 0x642, 0x62F, 0x627, 0x645, 0x20, 0x644, 0x627, 0x632, 0x645),
  plant: fa(0x6AF, 0x6CC, 0x627, 0x647),
  sevenConflicts: fa(0x6F7, 0x20, 0x62A, 0x639, 0x627, 0x631, 0x636, 0x20, 0x628, 0x631, 0x627, 0x6CC, 0x20, 0x631, 0x641, 0x639),
  twoGapsOneEvidence: fa(0x6F2, 0x20, 0x634, 0x6A9, 0x627, 0x641, 0x20, 0xB7, 0x20, 0x6F1, 0x20, 0x634, 0x627, 0x647, 0x62F),
  none: fa(0x647, 0x6CC, 0x686),
  sortName: fa(0x645, 0x631, 0x62A, 0x628, 0x200C, 0x633, 0x627, 0x632, 0x6CC, 0x3A, 0x20, 0x646, 0x627, 0x645),
  jalaliDate: fa(0x6F1, 0x20, 0x622, 0x628, 0x627, 0x646, 0x20, 0x6F1, 0x6F4, 0x6F0, 0x6F5),
  thousands: fa(0x6F1, 0x66C, 0x6F2, 0x6F3, 0x6F4),
  all: fa(0x647, 0x645, 0x647),
  showFinished: fa(0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x62A, 0x645, 0x627, 0x645, 0x200C, 0x634, 0x62F, 0x647, 0x200C, 0x647, 0x627),
  pager: fa(0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x6F1, 0x20, 0x62A, 0x627, 0x20, 0x6F2, 0x6F5, 0x20, 0x627, 0x632, 0x20, 0x6F1, 0x6F2, 0x6F0),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const ITEMS = [
  { id: 'a', canonical_name: 'Toranjebin', object_type: 'plant', status: 'in_review', updated_at: '2026-10-23T10:00:00Z',
    counts: { sources: 1234, claims: 40, claims_conflicting: 7, evidence: 20, evidence_verified: 12, evidence_pending_review: 0, gaps_open: 0 } },
  { id: 'b', canonical_name: 'Khorasan', object_type: 'region', status: 'published', updated_at: '2026-10-22T10:00:00Z',
    counts: { sources: 3, claims: 5, claims_conflicting: 0, evidence: 4, evidence_verified: 3, evidence_pending_review: 1, gaps_open: 2 } },
  { id: 'c', canonical_name: 'Thyme', object_type: 'concept', status: 'draft', updated_at: '2026-10-21T10:00:00Z',
    counts: { sources: 0, claims: 0, claims_conflicting: 0, evidence: 0, evidence_verified: 0, evidence_pending_review: 0, gaps_open: 0 } },
];

// The mock: answers /knowledge/overview from the query (a search returns one
// "<search>-result" row; window.__total fakes a long list; search=slow answers
// late, window.__delay holds every other overview reply back), echoes
// include_finished as finished_visible unless window.__forceFinished is set, and
// records every overview query and every POST body. window.__fail answers every
// overview request with that HTTP status, search=boom fails late, and
// window.__empty returns no rows.
function installMock(items) {
  window.__requests = []; window.__posts = []; window.__total = 0; window.__forceFinished = null; window.__created = null; window.__delay = 0;
  window.__fail = 0; window.__empty = false;
  const respond = (body, status, delay) => new Promise((ok) => setTimeout(() => ok(new Response(JSON.stringify(body), { status: status || 200 })), delay || 0));
  window.fetch = (u, opts) => {
    u = String(u); opts = opts || {};
    if (u.endsWith('/api/v1/knowledge') && opts.method === 'POST') {
      const body = JSON.parse(opts.body); window.__posts.push(body);
      window.__created = Object.assign({ id: 'new1', status: 'draft', updated_at: '2026-10-24T08:00:00Z' }, body);
      return respond(window.__created, 201);
    }
    if (u.includes('/knowledge/overview?')) {
      const q = new URLSearchParams(u.slice(u.indexOf('?') + 1)); window.__requests.push(q.toString());
      const limit = Number(q.get('limit')), offset = Number(q.get('offset')), search = q.get('search');
      if (search === 'boom') return respond({}, 500, 400);
      if (window.__fail) return respond({}, window.__fail, window.__delay);
      let list = items.slice();
      if (window.__created && window.__created.showOnPage !== false) {
        list = [Object.assign({ counts: items[2].counts }, window.__created)].concat(list);
      }
      if (search) list = [Object.assign({}, items[0], { id: 's-' + search, canonical_name: search + '-result' })];
      if (window.__empty) list = [];
      let total = list.length;
      if (window.__total) {
        total = window.__total;
        list = Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, i) =>
          Object.assign({}, items[i % 3], { id: 'p' + (offset + i), canonical_name: 'Item ' + (offset + i) }));
      }
      const visible = window.__forceFinished === null ? q.get('include_finished') === 'true' : window.__forceFinished;
      return respond({ items: list, total, limit, offset, finished_visible: visible }, 200, search === 'slow' ? 600 : window.__delay);
    }
    const one = items.find((i) => u.endsWith('/knowledge/' + i.id));
    if (one) return respond(one);
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
  const param = (q, k) => new URLSearchParams(q).get(k);

  // Before connecting: creating needs Cloud Core.
  check('sample mode: New knowledge object is disabled and says why', await page.$eval('#screen-knowledge .page-actions .btn--primary',
    (b) => [b.disabled, b.title]), [true, 'Connect Cloud Core to create']);

  await page.evaluate(installMock, ITEMS);
  await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok'));
  await page.waitForSelector('#know-view-table tbody tr .know-name');

  // ---------- Part A ----------
  const head = () => page.$$eval('#know-view-table thead th', (ths) => ths.map((th) => [th.textContent.trim(), th.getAttribute('aria-sort'), !!th.querySelector('button')]));
  check('six columns; three sortable; Action needed is the active sort', await head(), [
    ['Knowledge object', 'none', true], ['Sources', null, false], ['Approval', null, false],
    ['Action needed', 'descending', true], ['Updated', 'none', true], ['Research workspace', null, false]]);
  check('first request: default order, 50 rows, page 1', await requests(), ['sort=action_needed&limit=50&offset=0']);
  const sortBtn = '#screen-knowledge .toolbar [aria-controls="know-sort-panel"]';
  const sortLabel = () => page.$eval(sortBtn, (b) => b.textContent.trim());
  check('Sort button matches the active order', await sortLabel(), 'Sort: Action needed');
  check('designed screen stays visible; generic table gone', await page.evaluate(() => [
    getComputedStyle(document.getElementById('know-view-table')).display !== 'none',
    getComputedStyle(document.querySelector('#screen-knowledge .toolbar')).display !== 'none',
    !!document.querySelector('#live-screen-knowledge .live-body table')]), [true, true, false]);
  const rows = () => page.$$eval('#know-view-table tbody tr', (trs) => trs.map((tr) => {
    const td = tr.children;
    return {
      name: td[0].querySelector('.know-name').textContent, type: td[0].querySelector('.know-type').textContent,
      typeIsBdi: !!td[0].querySelector('.know-type bdi'), sources: td[1].textContent,
      approval: [td[2].textContent, td[2].querySelector('.badge').className.split(' ').pop()],
      action: [td[3].textContent, td[3].querySelector('.badge--warning') ? 'amber' : 'plain'],
      updated: td[4].textContent, workspace: [td[5].querySelector('[aria-hidden]').textContent, td[5].querySelector('.visually-hidden').textContent],
    };
  }));
  const names = async () => (await rows()).map((r) => r.name);
  const en = await rows();
  check('row names in server order', en.map((r) => r.name), ['Toranjebin', 'Khorasan', 'Thyme']);
  check('type line: approved labels, unknown type as English in <bdi>', en.map((r) => [r.type, r.typeIsBdi]), [['Plant', false], ['region', true], ['Concept', false]]);
  check('sources as plain numbers', en.map((r) => r.sources), ['1,234', '3', '0']);
  check('approval: amber only for in review and draft', en.map((r) => r.approval), [['In review', 'badge--warning'], ['Published', 'badge--success'], ['Draft', 'badge--warning']]);
  check('action needed: one phrase, joined counts, or muted None', en.map((r) => r.action), [['7 conflicts to resolve', 'amber'], ['2 gaps' + DOT + '1 evidence', 'amber'], ['None', 'plain']]);
  check('updated as a date', en[0].updated, '23 Oct 2026');
  check('workspace button: visible label and a name per row', en[0].workspace, ['Research workspace', 'Research workspace for ' + FSI + 'Toranjebin' + PDI]);
  await page.click('#know-view-table thead th:first-child button'); await settle();
  check('Name header asks the server for sort=name, page 1', await last(), 'sort=name&limit=50&offset=0');
  check('markers and Sort label follow', [(await head()).map((h) => h[1]), await sortLabel()], [['ascending', null, null, 'none', 'none', null], 'Sort: Name']);
  let before = (await requests()).length;
  await page.click('#know-view-table thead th:first-child button'); await settle();
  check('clicking the active header sends nothing', (await requests()).length, before);
  await page.selectOption('#pick-lang', 'fa'); await settle();
  const faRows = await rows();
  check('fa: header and Sort label', [(await head())[0][0], (await head())[3][0], await sortLabel()], [FA.knowledgeObject, FA.actionNeeded, FA.sortName]);
  check('fa: type label translated, unknown type left in English', [faRows[0].type, faRows[1].type], [FA.plant, 'region']);
  check('fa: action phrases and None', faRows.map((r) => r.action[0]), [FA.sevenConflicts, FA.twoGapsOneEvidence, FA.none]);
  check('fa: Jalali date and Persian digits', [faRows[0].updated, faRows[0].sources], [FA.jalaliDate, FA.thousands]);
  await page.selectOption('#pick-lang', 'en'); await settle();
  check('en restored', (await rows())[0].action[0], '7 conflicts to resolve');
  await page.click('#screen-knowledge .view-toggle__btn[data-view="grid"]');
  check('windowed view: one card per row, same names', await page.$$eval('#know-view-grid .know-card .know-name', (a) => a.map((x) => x.textContent)), ['Toranjebin', 'Khorasan', 'Thyme']);
  await page.click('#screen-knowledge .view-toggle__btn:not([data-view="grid"])');
  await page.click('#know-view-table tbody tr:first-child .research-workspace-btn');
  await page.waitForSelector('#live-screen-knowledge .live-detail .kw-workspace', { timeout: 10000 });
  check('Research workspace opens the detail with one keyword workspace', await page.$$eval('#live-screen-knowledge .live-detail .kw-workspace', (w) => w.length), 1);

  // ---------- Part B ----------
  const search = '#screen-knowledge .toolbar input[type=search]';
  await page.evaluate(() => { window.__requests = []; });
  await page.type(search, 'saf', { delay: 60 }); await settle(500);
  check('search: one request 300 ms after the last keystroke, page 1', await requests(), ['sort=name&limit=50&offset=0&search=saf']);
  await page.fill(search, 'saff'); await page.press(search, 'Enter'); await settle(60);
  check('search: Enter sends at once', await last(), 'sort=name&limit=50&offset=0&search=saff');
  await settle(400);
  check('search: the debounced copy of the same text sends nothing more', (await requests()).filter((q) => q.includes('search=saff')).length, 1);
  await page.press(search, 'Escape'); await settle();
  check('search: Escape clears it', [await page.$eval(search, (i) => i.value), param(await last(), 'search')], ['', null]);
  await page.fill(search, 'slow'); await page.press(search, 'Enter'); await settle(50);
  await page.fill(search, 'fast'); await page.press(search, 'Enter'); await settle(900);
  check('stale reply dropped: the slower, older request does not overwrite the newer one', await names(), ['fast-result']);
  // The other way round: the older reply lands first and must not clear busy
  // while the newest request is still out.
  const busy = () => page.$eval('#know-view-table table', (t) => t.getAttribute('aria-busy'));
  await page.evaluate(() => { window.__delay = 200; });
  await page.fill(search, 'quick'); await page.press(search, 'Enter');
  await page.fill(search, 'slow'); await page.press(search, 'Enter'); await settle(350);
  check('busy: an older reply does not clear it while the newest is out', [await busy(), await names()], ['true', ['fast-result']]);
  await settle(600);
  check('busy: the newest reply clears it', [await busy(), await names()], [null, ['slow-result']]);
  await page.evaluate(() => { window.__delay = 0; });
  await page.fill(search, ''); await page.press(search, 'Enter'); await settle();

  // Filter panel and chips.
  const filterBtn = '#screen-knowledge .toolbar [aria-controls="know-filter-panel"]';
  await page.click(filterBtn);
  check('Filter opens its panel', await page.$eval(filterBtn, (b) => [b.getAttribute('aria-expanded'), document.getElementById('know-filter-panel').hidden]), ['true', false]);
  const typeSel = '#know-filter-panel select >> nth=0', statusSel = '#know-filter-panel select >> nth=1';
  await page.selectOption(typeSel, 'plant'); await settle();
  check('type filter sends object_type, page 1', [param(await last(), 'object_type'), param(await last(), 'offset')], ['plant', '0']);
  const chips = () => page.$$eval('#screen-knowledge .know-chip', (c) => c.map((x) => [x.querySelector('.visually-hidden').textContent, x.textContent.replace(x.querySelector('.visually-hidden').textContent, '')]));
  check('a chip shows the active type', await chips(), [['Remove filter', 'Type: Plant']]);
  before = (await requests()).length;
  await page.selectOption(typeSel, '__other'); await settle();
  check('Other type asks for a name and sends nothing yet', (await requests()).length, before);
  await page.fill('#know-filter-panel input[type=text]', 'region'); await settle(500);
  check('other type filters by the exact name', param(await last(), 'object_type'), 'region');
  check('its chip shows the raw type in <bdi>', await page.$$eval('#screen-knowledge .know-chip bdi', (b) => b.map((x) => x.textContent)), ['region']);
  await page.selectOption(statusSel, 'draft'); await settle();
  check('status filter sends status, both filters kept', [param(await last(), 'status'), param(await last(), 'object_type')], ['draft', 'region']);
  await page.click('#screen-knowledge .know-chip >> nth=0'); await settle();
  check('removing the type chip drops object_type and keeps status', [param(await last(), 'object_type'), param(await last(), 'status'),
    await page.$eval(typeSel.split(' >> ')[0], (s) => s.value)], [null, 'draft', '']);
  await page.click('#screen-knowledge .know-chip >> nth=0'); await settle();
  check('no filters left, no chips', [param(await last(), 'status'), (await chips()).length], [null, 0]);
  await page.keyboard.press('Escape');

  // Sort panel.
  await page.click(sortBtn);
  await page.click('#know-sort-panel .know-sort-opt >> nth=2'); await settle();
  check('sort panel: Recently updated', [param(await last(), 'sort'), await sortLabel(), (await head())[4][1]], ['updated', 'Sort: Recently updated', 'descending']);
  check('sort panel closes and its choice is pressed', await page.evaluate(() => [document.getElementById('know-sort-panel').hidden,
    [...document.querySelectorAll('#know-sort-panel .know-sort-opt')].map((b) => b.getAttribute('aria-pressed'))]), [true, ['false', 'false', 'true']]);

  // Show finished.
  const fin = '#screen-knowledge .know-finished';
  await page.fill(search, 'saf'); await page.press(search, 'Enter'); await settle();
  await page.click(fin); await settle();
  check('Show finished asks for finished rows and keeps the search', [param(await last(), 'include_finished'), param(await last(), 'search'),
    await page.$eval(fin, (b) => b.getAttribute('aria-pressed'))], ['true', 'saf', 'true']);
  await page.click(fin); await settle();
  check('turning it off drops the parameter', [param(await last(), 'include_finished'), await page.$eval(fin, (b) => b.getAttribute('aria-pressed'))], [null, 'false']);
  await page.evaluate(() => { window.__forceFinished = false; });
  await page.click(fin); await settle();
  check('its pressed state comes from finished_visible, not from the click', await page.$eval(fin, (b) => b.getAttribute('aria-pressed')), 'false');
  await page.evaluate(() => { window.__forceFinished = null; });
  await page.fill(search, ''); await page.press(search, 'Enter'); await settle();

  // Paging.
  await page.evaluate(() => { window.__total = 120; });
  await page.selectOption('#screen-knowledge .know-pager select', '25'); await settle();
  const pager = () => page.$eval('#screen-knowledge .know-pager', (p) => [p.querySelector('.know-pager__text').textContent,
    p.querySelectorAll('.btn')[0].disabled, p.querySelectorAll('.btn')[1].disabled]);
  check('page size 25: limit=25, page 1', [param(await last(), 'limit'), param(await last(), 'offset')], ['25', '0']);
  check('pager text and buttons on page 1', await pager(), ['Showing 1 to 25 of 120', true, false]);
  await page.click('#screen-knowledge .know-pager .btn >> nth=1'); await settle();
  check('Next moves to offset 25', [param(await last(), 'offset'), (await pager())[0]], ['25', 'Showing 26 to 50 of 120']);
  await page.selectOption('#pick-lang', 'fa'); await settle();
  await page.click('#screen-knowledge .know-pager .btn >> nth=0'); await settle();
  check('fa: pager text with Persian digits', (await pager())[0], FA.pager);
  check('fa: control labels', await page.evaluate(() => [document.querySelector('#know-filter-panel select option').textContent,
    document.querySelector('#screen-knowledge .know-finished').textContent]), [FA.all, FA.showFinished]);
  await page.selectOption('#pick-lang', 'en'); await settle();
  // Two quick Next clicks while the first request is out: one request, no overrun.
  await page.evaluate(() => { window.__delay = 300; });
  before = (await requests()).length;
  const nextNow = () => page.$eval('#screen-knowledge .know-pager .btn >> nth=1', (b) => b.click());
  await nextNow(); await nextNow(); await settle(50);
  check('paging: both buttons are off while a request is out', [(await pager())[1], (await pager())[2]], [true, true]);
  await settle(450);
  check('paging: two quick Next clicks send one request', (await requests()).slice(before).map((q) => param(q, 'offset')), ['25']);
  check('paging: buttons back on with the reply', await pager(), ['Showing 26 to 50 of 120', false, false]);
  await page.evaluate(() => { window.__delay = 0; });

  // Every control goes back to page 1.
  // Clicking Next (outside the panel) closes the filter panel, as it should; reopen it when needed.
  const openFilter = async () => { if (await page.$eval('#know-filter-panel', (p) => p.hidden)) await page.click(filterBtn); };
  const controls = [
    ['search (Enter)', async () => { await page.fill(search, 'abc'); await page.press(search, 'Enter'); }],
    ['search cleared', async () => { await page.fill(search, ''); await page.press(search, 'Enter'); }],
    ['type filter', async () => { await openFilter(); await page.selectOption(typeSel, 'compound'); }],
    ['other type text', async () => { await openFilter(); await page.selectOption(typeSel, '__other'); await page.fill('#know-filter-panel input[type=text]', 'zone'); await settle(400); }],
    ['status filter', async () => { await openFilter(); await page.selectOption(statusSel, 'published'); await page.keyboard.press('Escape'); }],
    ['sort panel', async () => { await page.click(sortBtn); await page.click('#know-sort-panel .know-sort-opt >> nth=0'); }],
    ['sort header', async () => { await page.click('#know-view-table thead th:nth-child(4) button'); }],
    ['page size', async () => { await page.selectOption('#screen-knowledge .know-pager select', '50'); }],
    ['show finished', async () => { await page.click(fin); }],
  ];
  const resets = [];
  for (const [label, act] of controls) {
    await page.click('#screen-knowledge .know-pager .btn >> nth=1'); await settle();
    const moved = param(await last(), 'offset');
    await act(); await settle();
    resets.push([label, moved !== '0', param(await last(), 'offset')]);
  }
  check('every control goes back to page 1', resets, controls.map(([label]) => [label, true, '0']));
  await page.evaluate(() => { window.__total = 0; });

  // Reconnect (a different token): the controls are wired once, so nothing is
  // doubled. Search, filters, sort and page size carry over on purpose; the
  // reload asks for exactly what the screen was showing.
  before = (await requests()).length;
  const shownQuery = await last();
  await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok2')); await settle();
  check('reconnect: one request, with the same search, filters and sort', (await requests()).slice(before), [shownQuery]);
  check('reconnect: one filter panel, sort panel, pager and Show finished', await page.evaluate(() => ['#know-filter-panel', '#know-sort-panel',
    '#screen-knowledge .know-pager', '#screen-knowledge .know-finished'].map((s) => document.querySelectorAll(s).length)), [1, 1, 1, 1]);
  await page.click(filterBtn);
  check('reconnect: one Filter click opens the panel', await page.$eval(filterBtn, (b) => [b.getAttribute('aria-expanded'),
    document.getElementById('know-filter-panel').hidden]), ['true', false]);
  before = (await requests()).length;
  await page.selectOption(statusSel, 'draft'); await settle();
  check('reconnect: one filter change sends one request', (await requests()).slice(before).map((q) => param(q, 'status')), ['draft']);
  await page.keyboard.press('Escape');

  // New knowledge object.
  const newBtn = '#screen-knowledge .page-actions .btn--primary';
  check('live: New knowledge object is enabled', await page.$eval(newBtn, (b) => [b.disabled, b.title]), [false, '']);
  await page.click(newBtn);
  check('it opens the form and focuses the name', await page.evaluate(() => [document.getElementById('know-new-form').hidden,
    document.activeElement === document.querySelector('#know-new-form input')]), [false, true]);
  await page.click('#know-new-form button[type=submit]'); await settle();
  check('an empty form explains what is missing and sends nothing', [await page.$eval('#know-new-form .know-new__msg', (m) => m.textContent),
    (await page.evaluate(() => window.__posts)).length], ['Enter a name and a type.', 0]);
  await page.fill('#know-new-form input[type=text] >> nth=0', 'Saffron');
  await page.selectOption('#know-new-form select', 'product');
  await page.click('#know-new-form button[type=submit]'); await settle(300);
  check('it posts the name and type', await page.evaluate(() => window.__posts), [{ canonical_name: 'Saffron', object_type: 'product' }]);
  check('the new row is shown and focused, with a confirmation', await page.evaluate(() => [
    document.activeElement && document.activeElement.closest('tr') && document.activeElement.closest('tr').dataset.knowledgeId,
    document.getElementById('know-created').textContent, document.getElementById('know-new-form').hidden]),
    ['new1', 'Created ' + FSI + 'Saffron' + PDI + '.', true]);
  await page.evaluate(() => { window.__created = null; window.__createdHidden = true; });
  await page.evaluate(() => {
    const original = window.fetch;
    window.fetch = (u, o) => (String(u).endsWith('/api/v1/knowledge') && o && o.method === 'POST'
      ? original(u, o).then((r) => { window.__created.showOnPage = false; return r; }) : original(u, o));
  });
  await page.click(newBtn);
  await page.fill('#know-new-form input[type=text] >> nth=0', 'Garlic');
  await page.selectOption('#know-new-form select', 'plant');
  await page.click('#know-new-form button[type=submit]'); await settle(300);
  check('when the new object is not on this page, it says so and offers Open', await page.evaluate(() => [
    document.getElementById('know-created').textContent.replace('Open', ''), !!document.querySelector('#know-created .btn')]),
    [FSI + 'Garlic' + PDI + ' was created; it is not on this page.', true]);

  // ---------- Part C ----------
  const statusOf = () => page.$eval('#screen-knowledge .know-status', (s) => [s.dataset.state, s.querySelector('p').textContent,
    s.querySelector('.btn').hidden ? null : s.querySelector('.btn').textContent]);
  const shown = () => page.evaluate(() => [document.querySelectorAll('#know-view-table tbody tr').length, document.querySelectorAll('#know-view-grid .know-card').length]);
  const statusBtn = '#screen-knowledge .know-status .btn';
  await page.evaluate(() => { window.__created = null; window.__total = 120; });
  while ((await chips()).length) { await page.click('#screen-knowledge .know-chip >> nth=0'); await settle(); }

  // A failed sort, page and filter: nothing left over, Retry repeats the request.
  await page.evaluate(() => { window.__fail = 500; });
  await page.click('#know-view-table thead th:first-child button'); await settle();
  check('failed sort: no rows or cards left under the new headers', await shown(), [0, 0]);
  check('failed sort: headers and Sort label show the request', [(await head())[0][1], await sortLabel()], ['ascending', 'Sort: Name']);
  check('failed sort: an error with Retry, and no second message in the panel', [await statusOf(),
    await page.$eval('#live-screen-knowledge .live-state', (s) => s.hidden)], [['error', 'Could not load knowledge objects (HTTP 500).', 'Retry'], true]);
  check('failed sort: pager blank and off', await pager(), ['', true, true]);
  const failedQuery = await last();
  await page.evaluate(() => { window.__fail = 0; });
  await page.click(statusBtn); await settle();
  check('Retry sends the same request again', await last(), failedQuery);
  check('Retry: rows, pager and status back', [(await shown())[0], await pager(), (await statusOf())[0]], [50, ['Showing 1 to 50 of 120', true, false], '']);
  await page.evaluate(() => { window.__fail = 500; });
  await page.click('#screen-knowledge .know-pager .btn >> nth=1'); await settle();
  check('failed Next: asked for offset 50, no rows, pager off', [param(await last(), 'offset'), await shown(), await pager()], ['50', [0, 0], ['', true, true]]);
  await page.evaluate(() => { window.__fail = 0; });
  await page.click(statusBtn); await settle();
  check('Retry after a failed Next stays on that page', [param(await last(), 'offset'), (await pager())[0]], ['50', 'Showing 51 to 100 of 120']);
  await page.evaluate(() => { window.__fail = 500; });
  await openFilter(); await page.selectOption(statusSel, 'published'); await page.keyboard.press('Escape'); await settle();
  check('failed filter: its chip stays, no rows', [await chips(), await shown()], [[['Remove filter', 'Status: Published']], [0, 0]]);
  await page.evaluate(() => { window.__fail = 0; });
  await page.click(statusBtn); await settle();
  check('Retry keeps the filter', [param(await last(), 'status'), (await shown())[0]], ['published', 50]);
  await page.click('#screen-knowledge .know-chip >> nth=0'); await settle();

  // A slow failure that lost to a newer request changes nothing.
  await page.evaluate(() => { window.__total = 0; });
  await page.fill(search, 'boom'); await page.press(search, 'Enter'); await settle(50);
  await page.fill(search, 'fast'); await page.press(search, 'Enter'); await settle(700);
  check('a slow failure that lost to a newer request is ignored', [await names(), (await statusOf())[0]], [['fast-result'], '']);

  // 401 and 403: Reconnect reopens this panel's connect form.
  await page.evaluate(() => { window.__fail = 401; });
  await page.fill(search, ''); await page.press(search, 'Enter'); await settle();
  check('401: the token was not accepted, Reconnect offered', await statusOf(),
    ['denied', 'Cloud Core did not accept the access token (HTTP 401). It may have expired.', 'Reconnect']);
  check('Reconnect controls the collapsed connect form', await page.$eval(statusBtn, (b) => [b.getAttribute('aria-controls'),
    b.getAttribute('aria-expanded'), document.getElementById(b.getAttribute('aria-controls')).hidden]), ['live-connect-screen-knowledge', 'false', true]);
  await page.evaluate(() => { document.querySelector('#live-connect-screen-knowledge .live-token').value = 'stale'; window.scrollTo(0, 0); });
  await page.$eval(statusBtn, (b) => b.click());
  check('Reconnect: form open, URL in use kept, token cleared and focused, no scroll', await page.evaluate(() => {
    const f = document.getElementById('live-connect-screen-knowledge');
    return [f.hidden, f.querySelector('.live-base').value, f.querySelector('.live-token').value,
      document.activeElement === f.querySelector('.live-token'), window.scrollY, document.querySelector('#screen-knowledge .know-status .btn').getAttribute('aria-expanded')];
  }), [false, 'http://core.test', '', true, 0, 'true']);
  await page.evaluate(() => { window.__fail = 0; });
  await page.fill('#live-connect-screen-knowledge .live-token', 'tok3');
  await page.press('#live-connect-screen-knowledge .live-token', 'Enter'); await settle();
  check('a new token hides the form and loads the list', [await page.$eval('#live-connect-screen-knowledge', (f) => f.hidden),
    (await shown())[0], (await statusOf())[0], await page.evaluate(() => window.AIOL_LIVE_STATE().token)], [true, 3, '', 'tok3']);
  await page.evaluate(() => { window.__fail = 403; });
  await page.selectOption('#screen-knowledge .know-pager select', '25'); await settle();
  check('403: the token may not read knowledge objects, Reconnect offered', await statusOf(),
    ['denied', 'This access token is not allowed to read knowledge objects (HTTP 403).', 'Reconnect']);
  await page.evaluate(() => { window.__fail = 0; });

  // Empty: nothing at all, or nothing matching; hidden finished objects are mentioned.
  const hiddenNote = ' Finished objects are hidden; turn on Show finished to include them.';
  await page.evaluate(() => { window.__empty = true; window.__forceFinished = false; });
  await page.selectOption('#screen-knowledge .know-pager select', '50'); await settle();
  check('empty, no filters: says so and offers New knowledge object', await statusOf(),
    ['empty', 'No knowledge objects yet.' + hiddenNote, 'New knowledge object']);
  await page.click(statusBtn);
  check('its action opens the new-object form', await page.evaluate(() => [document.getElementById('know-new-form').hidden,
    document.activeElement === document.querySelector('#know-new-form input')]), [false, true]);
  await page.click('#know-new-form .know-new__actions .btn:not(.btn--primary)');
  await page.fill(search, 'zzz'); await page.press(search, 'Enter'); await settle();
  check('empty with a search: nothing matches, Clear filters offered', await statusOf(),
    ['empty', 'No knowledge objects match this search and these filters.' + hiddenNote, 'Clear filters']);
  await openFilter(); await page.selectOption(statusSel, 'draft'); await page.keyboard.press('Escape'); await settle();
  await page.click(statusBtn); await settle();
  check('Clear filters drops search, type and status', [param(await last(), 'search'), param(await last(), 'status'),
    param(await last(), 'object_type'), await page.$eval(search, (i) => i.value), (await chips()).length], [null, null, null, '', 0]);
  await page.evaluate(() => { window.__forceFinished = true; });
  await page.click(fin); await settle();
  check('with finished objects shown, the empty state does not mention them', (await statusOf())[1], 'No knowledge objects yet.');
  await page.evaluate(() => { window.__empty = false; window.__forceFinished = null; });

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
