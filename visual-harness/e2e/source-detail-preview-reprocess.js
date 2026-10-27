#!/usr/bin/env node
/*
 * Browser checks for Source detail text preview and Reprocess (Step 7B2b-4).
 *   Text:      "Show text" reads GET /documents/{id}/markdown once and shows it
 *              with textContent in a <pre> (markup stays text); closing and
 *              reopening asks nothing again; no text (empty or 404); an error
 *              with Retry.
 *   Reprocess: only for owner/admin/researcher/editor (GET /auth/me); confirm,
 *              then POST /documents/{id}/reprocess, the job id, and the
 *              documents list read again; cancel sends nothing; 500; a 403
 *              leaves the button in place.
 *   Persian labels for all of the above.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/source-detail-preview-reprocess.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-detail';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = String.fromCharCode(0x2068), PDI = String.fromCharCode(0x2069);
const iso = (s) => FSI + s + PDI;
const FA = {
  showText: fa(0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x645, 0x62A, 0x646),
  hideText: fa(0x67E, 0x646, 0x647, 0x627, 0x646, 0x20, 0x6A9, 0x631, 0x62F, 0x646, 0x20, 0x645, 0x62A, 0x646),
  showTextOf: [fa(0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20, 0x645, 0x62A, 0x646, 0x20), fa()],
  hideTextOf: [fa(0x67E, 0x646, 0x647, 0x627, 0x646, 0x20, 0x6A9, 0x631, 0x62F, 0x646, 0x20, 0x645, 0x62A, 0x646, 0x20), fa()],
  noText: fa(0x627, 0x6CC, 0x646, 0x20, 0x633, 0x646, 0x62F, 0x20, 0x647, 0x646, 0x648, 0x632, 0x20, 0x645, 0x62A, 0x646, 0x6CC, 0x20, 0x646, 0x62F, 0x627, 0x631, 0x62F, 0x2E),
  textError: [fa(0x628, 0x627, 0x631, 0x6AF, 0x630, 0x627, 0x631, 0x6CC, 0x20, 0x645, 0x62A, 0x646, 0x20, 0x646, 0x627, 0x645, 0x648, 0x641, 0x642, 0x20, 0x628, 0x648, 0x62F, 0x20, 0x28), fa(0x29, 0x2E)],
  reprocess: fa(0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634, 0x20, 0x645, 0x62C, 0x62F, 0x62F),
  reprocessOf: [fa(0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634, 0x20, 0x645, 0x62C, 0x62F, 0x62F, 0x20), fa()],
  ask: fa(0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634, 0x20, 0x645, 0x62C, 0x62F, 0x62F, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x633, 0x646, 0x62F, 0x20, 0x627, 0x646, 0x62C, 0x627, 0x645, 0x20, 0x634, 0x648, 0x62F, 0x61F, 0x20, 0x627, 0x633, 0x62A, 0x62E, 0x631, 0x627, 0x62C, 0x20, 0x641, 0x639, 0x644, 0x6CC, 0x20, 0x62A, 0x627, 0x20, 0x632, 0x645, 0x627, 0x646, 0x6CC, 0x20, 0x645, 0x639, 0x62A, 0x628, 0x631, 0x20, 0x627, 0x633, 0x62A, 0x20, 0x6A9, 0x647, 0x20, 0x627, 0x633, 0x62A, 0x62E, 0x631, 0x627, 0x62C, 0x20, 0x62C, 0x62F, 0x6CC, 0x62F, 0x20, 0x645, 0x648, 0x641, 0x642, 0x20, 0x634, 0x648, 0x62F, 0x2E),
  queued: [fa(0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634, 0x20, 0x645, 0x62C, 0x62F, 0x62F, 0x20, 0x62F, 0x631, 0x20, 0x635, 0x641, 0x20, 0x642, 0x631, 0x627, 0x631, 0x20, 0x6AF, 0x631, 0x641, 0x62A, 0x20, 0x28, 0x634, 0x646, 0x627, 0x633, 0x647, 0x654, 0x20, 0x6A9, 0x627, 0x631, 0x3A, 0x20), fa(0x29, 0x2E)],
  startError: [fa(0x634, 0x631, 0x648, 0x639, 0x20, 0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634, 0x20, 0x645, 0x62C, 0x62F, 0x62F, 0x20, 0x646, 0x627, 0x645, 0x648, 0x641, 0x642, 0x20, 0x628, 0x648, 0x62F, 0x20, 0x28), fa(0x29, 0x2E)],
  denied: fa(0x646, 0x642, 0x634, 0x20, 0x634, 0x645, 0x627, 0x20, 0x627, 0x62C, 0x627, 0x632, 0x647, 0x654, 0x20, 0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634, 0x20, 0x645, 0x62C, 0x62F, 0x62F, 0x20, 0x627, 0x633, 0x646, 0x627, 0x62F, 0x20, 0x631, 0x627, 0x20, 0x646, 0x62F, 0x627, 0x631, 0x62F, 0x20, 0x28, 0x2068, 0x48, 0x54, 0x54, 0x50, 0x20, 0x34, 0x30, 0x33, 0x2069, 0x29, 0x2E),
  retry: fa(0x62A, 0x644, 0x627, 0x634, 0x20, 0x645, 0x62C, 0x62F, 0x62F),
};
const wrap = (pair, v) => pair[0] + v + pair[1];

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const XSS = '<script>alert(1)</script># hi <img src=x onerror="window.__pwned=1">';
// Markdown by document id: a string is the text (200), a number is an HTTP status.
const TEXT = { d1: '# Title\nbody', d2: XSS, d3: '', d4: 404, d5: 500 };
const DOCS = [['d1', 'Report'], ['d2', 'Markup'], ['d3', 'Blank'], ['d4', 'Missing'], ['d5', 'Broken']].map(([id, title]) => ({
  id, title, extraction_status: 'extracted', current_conversion: { id: 'c-' + id, status: 'succeeded', needs_review: false },
  file_size: 1024, mime_type: 'text/markdown', updated_at: '2026-10-23T10:00:00Z' }));

// window.__role is what GET /auth/me says; window.__reprocess is 'ok' or an HTTP status;
// window.__confirm is the answer to window.confirm, and window.__asked records the question.
function installMock(arg) {
  window.__requests = []; window.__role = 'editor'; window.__reprocess = 'ok'; window.__confirm = true; window.__asked = [];
  window.confirm = (q) => { window.__asked.push(q); return window.__confirm; };
  const reply = (body, status, text) => Promise.resolve(new Response(text ? body : JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opts) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opts && opts.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (p.indexOf('/sources/overview?') === 0) {
      return reply({ items: [{ id: 'a', title: 'Source A', source_type: 'scientific_paper', author: null, publisher: null, publication_date: null,
        derived_status: 'completed', counts: { documents: 5, knowledge_objects: 0, claims: 0, evidence: 0 },
        last_activity_at: '2026-10-23T10:00:00Z' }], total: 1, limit: 50, offset: 0, counts_by_status: {} });
    }
    if (p.indexOf('/sources/a/documents?') === 0) return reply({ items: arg.docs, total: arg.docs.length, limit: 50, offset: 0 });
    let m = p.match(/^\/documents\/([^/]+)\/markdown$/);
    if (m) { const t = arg.text[m[1]]; return typeof t === 'number' ? reply({}, t) : reply(t, 200, true); }
    m = p.match(/^\/documents\/([^/]+)\/reprocess$/);
    if (m && method === 'POST') {
      return window.__reprocess === 'ok' ? reply({ job_id: 'job-1', conversion_id: 'conv-2', status_url: '/x', note: 'n' }, 202) : reply({}, window.__reprocess);
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
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const requests = () => page.evaluate(() => window.__requests || []);
  const count = async (re) => (await requests()).filter((r) => re.test(r)).length;
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  // Each document row: its two buttons' visible and spoken labels, and the text row under it.
  const rows = () => page.evaluate(() => Array.from(document.querySelectorAll('#screen-detail .src-detail-docs tbody tr:not(.src-doc-text)')).map((tr) => {
    const btns = Array.from(tr.querySelectorAll('.src-doc-actions button'));
    const label = (b) => b && [b.children[0].textContent, b.children[1].textContent];
    const t = tr.nextElementSibling && tr.nextElementSibling.classList.contains('src-doc-text') ? tr.nextElementSibling : null;
    const pre = t && t.querySelector('pre'), box = t && t.querySelector('.know-status');
    return { title: tr.cells[0].querySelector('bdi').textContent, show: label(btns[0]), expanded: btns[0] ? btns[0].getAttribute('aria-expanded') : null,
      reprocess: label(btns[1]) || null, open: !!t && !t.hidden,
      pre: pre && !pre.hidden ? pre.textContent : null, preElements: pre ? pre.childElementCount : null,
      message: box ? box.querySelector('p').textContent : null, action: box && !box.querySelector('button').hidden ? box.querySelector('button').textContent : null };
  }));
  const row = async (i) => (await rows())[i] || {};   // {} on a page without the list
  const action = () => page.evaluate(() => {
    const boxes = document.querySelectorAll('#screen-detail .src-detail-docs > .know-status');
    return boxes[1] ? [boxes[1].dataset.state, boxes[1].querySelector('p').textContent] : [null, null];
  });
  const press = async (i, which) => {
    const b = await page.$$('#screen-detail .src-detail-docs tbody tr:not(.src-doc-text)');
    const btn = b[i] && await b[i].$('.src-doc-actions button' + (which === 'reprocess' ? ':nth-of-type(2)' : ':nth-of-type(1)'));
    if (btn) await btn.click();
    await settle();
  };

  await page.evaluate(installMock, { docs: DOCS, text: TEXT });
  await page.evaluate(() => { location.hash = '#screen-detail?id=a'; }); await settle();
  await connect();

  // Text preview
  let r = await row(0);
  check('each row: Show text, named after the document', [r.show, r.expanded], [['Show text', 'Show text of ' + iso('Report')], 'false']);
  await press(0, 'show');
  r = await row(0);
  check('Show text: one GET for its markdown, shown as text in a <pre>', [await count(/^GET \/documents\/d1\/markdown$/), r.pre, r.open],
    [1, '# Title\nbody', true]);
  check('the button now hides the text', [r.show, r.expanded], [['Hide text', 'Hide text of ' + iso('Report')], 'true']);
  await press(0, 'show');
  r = await row(0);
  check('Hide text: the row closes, nothing is asked', [r.open, r.show && r.show[0], await count(/markdown$/)], [false, 'Show text', 1]);
  await press(0, 'show');
  check('reopening shows the same text without asking again', [(await row(0)).pre, await count(/markdown$/)], ['# Title\nbody', 1]);
  await press(1, 'show');
  r = await row(1);
  check('markup in the text stays text: no elements, nothing ran', [r.pre, r.preElements, await page.evaluate(() => !!window.__pwned)], [XSS, 0, false]);
  check('no script or img element came from the text', await page.$$eval('#screen-detail .src-doc-text script, #screen-detail .src-doc-text img', (e) => e.length), 0);
  await press(2, 'show');
  await press(3, 'show');
  check('empty text and 404: no text yet', [(await row(2)).message, (await row(3)).message, (await row(2)).pre],
    ['This document has no text yet.', 'This document has no text yet.', null]);
  await press(4, 'show');
  r = await row(4);
  check('500: the error with its status, and Retry', [r.message, r.action], ['Could not load the text (' + iso('HTTP 500') + ').', 'Retry']);

  // Reprocess
  check('editor: every row offers Reprocess, named after the document', (await rows()).map((x) => x.reprocess),
    DOCS.map((d) => ['Reprocess', 'Reprocess ' + iso(d.title)]));
  const docsBefore = await count(/^GET \/sources\/a\/documents/);
  await page.evaluate(() => { window.__confirm = false; });
  await press(0, 'reprocess');
  check('cancel: the question was asked, nothing sent, the list not read again',
    [await page.evaluate(() => window.__asked.slice(-1)[0]), await count(/^POST /), await count(/^GET \/sources\/a\/documents/)],
    ['Reprocess this document? The current extraction stays in force until the new one succeeds.', 0, docsBefore]);
  await page.evaluate(() => { window.__confirm = true; });
  await press(0, 'reprocess');
  check('confirm: POST /documents/d1/reprocess, the job id, the list read again',
    [(await requests()).filter((x) => x.startsWith('POST ')), await action(), await count(/^GET \/sources\/a\/documents/)],
    [['POST /documents/d1/reprocess'], ['done', 'Reprocessing queued (job ' + iso('job-1') + ').'], docsBefore + 1]);
  await page.evaluate(() => { window.__reprocess = 500; });
  await press(1, 'reprocess');
  check('500: the start error with its status', await action(), ['error', 'Could not start reprocessing (' + iso('HTTP 500') + ').']);
  await page.evaluate(() => { window.__reprocess = 403; });
  await press(1, 'reprocess');
  check('403 mid-session: the role sentence, and the button stays', [await action(), (await row(1)).reprocess && (await row(1)).reprocess[0]],
    [['denied', 'Your role is not allowed to reprocess documents (HTTP 403).'], 'Reprocess']);

  await page.evaluate(() => { window.__role = 'viewer'; });
  await connect();
  check('viewer: no Reprocess on any row, the text toggle stays', (await rows()).map((x) => [x.reprocess, x.show && x.show[0]]),
    DOCS.map(() => [null, 'Show text']));

  // Persian
  await page.evaluate(() => { window.__role = 'editor'; window.__reprocess = 'ok'; });
  await connect();
  await lang('fa');
  r = await row(0);
  check('fa: the two buttons and their spoken names', [r.show, r.reprocess],
    [[FA.showText, wrap(FA.showTextOf, iso('Report'))], [FA.reprocess, wrap(FA.reprocessOf, iso('Report'))]]);
  await press(0, 'show');
  check('fa: Hide text', (await row(0)).show, [FA.hideText, wrap(FA.hideTextOf, iso('Report'))]);
  await press(2, 'show');
  await press(4, 'show');
  check('fa: no text yet, and the load error with Retry', [(await row(2)).message, (await row(4)).message, (await row(4)).action],
    [FA.noText, wrap(FA.textError, iso('HTTP 500')), FA.retry]);
  await press(0, 'reprocess');
  check('fa: the question and the queued job', [await page.evaluate(() => window.__asked.slice(-1)[0]), (await action())[1]],
    [FA.ask, wrap(FA.queued, iso('job-1'))]);
  await page.evaluate(() => { window.__reprocess = 500; });
  await press(0, 'reprocess');
  check('fa: the start error', (await action())[1], wrap(FA.startError, iso('HTTP 500')));
  await page.evaluate(() => { window.__reprocess = 403; });
  await press(0, 'reprocess');
  check('fa: the 403 sentence', (await action())[1], FA.denied);
  await lang('en');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
