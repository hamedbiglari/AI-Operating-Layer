#!/usr/bin/env node
/*
 * Browser checks for the live Source detail documents list (Step 7B2b-3b).
 *   Rows:   GET /sources/{id}/documents, one request per page; the Status
 *           column is extraction_status, the Conversion column is the current
 *           conversion's status or "No conversion", plus "Needs human review".
 *   States: no documents, a failed request with Retry.
 *   Pager:  the Sources list's pattern: 50 a page, Previous / Next, the
 *           "Showing {from} to {to} of {total}" counter.
 *   Persian labels for all of the above.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/source-detail-documents.js
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
  document: fa(0x633, 0x646, 0x62F),
  status: fa(0x648, 0x636, 0x639, 0x6CC, 0x62A),
  conversion: fa(0x62A, 0x628, 0x62F, 0x6CC, 0x644, 0x20, 0x633, 0x646, 0x62F),
  size: fa(0x627, 0x646, 0x62F, 0x627, 0x632, 0x647),
  updated: fa(0x628, 0x647, 0x200C, 0x631, 0x648, 0x632, 0x631, 0x633, 0x627, 0x646, 0x6CC),
  extracted: fa(0x627, 0x633, 0x62A, 0x62E, 0x631, 0x627, 0x62C, 0x200C, 0x634, 0x62F, 0x647),
  succeeded: fa(0x645, 0x648, 0x641, 0x642),
  noConversion: fa(0x628, 0x62F, 0x648, 0x646, 0x20, 0x62A, 0x628, 0x62F, 0x6CC, 0x644),
  failed: fa(0x646, 0x627, 0x645, 0x648, 0x641, 0x642),
  empty: fa(0x628, 0x62F, 0x648, 0x646, 0x20, 0x645, 0x62A, 0x646),
  unsupported: fa(0x67E, 0x634, 0x62A, 0x6CC, 0x628, 0x627, 0x646, 0x6CC, 0x200C, 0x646, 0x634, 0x62F, 0x647),
  needsReview: fa(0x646, 0x6CC, 0x627, 0x632, 0x645, 0x646, 0x62F, 0x20, 0x628, 0x631, 0x631, 0x633, 0x6CC, 0x20, 0x627, 0x646, 0x633, 0x627, 0x646, 0x6CC),
  noDocuments: fa(0x627, 0x6CC, 0x646, 0x20, 0x645, 0x646, 0x628, 0x639, 0x20, 0x647, 0x646, 0x648, 0x632, 0x20, 0x633, 0x646, 0x62F, 0x6CC, 0x20, 0x646, 0x62F, 0x627, 0x631, 0x62F, 0x2E),
  documentsTitle: fa(0x627, 0x633, 0x646, 0x627, 0x62F),
  loadErrorBefore: fa(0x628, 0x627, 0x631, 0x6AF, 0x630, 0x627, 0x631, 0x6CC, 0x20, 0x627, 0x633, 0x646, 0x627, 0x62F, 0x20, 0x646, 0x627, 0x645, 0x648, 0x641, 0x642, 0x20, 0x628, 0x648, 0x62F, 0x20, 0x28),
  loadErrorAfter: fa(0x29, 0x2E),
  // "Showing {from} to {to} of {total}", split at its three numbers
  pager: [fa(0x646, 0x645, 0x627, 0x6CC, 0x634, 0x20), fa(0x20, 0x62A, 0x627, 0x20), fa(0x20, 0x627, 0x632, 0x20)],
  n1: fa(0x6F1), n50: fa(0x6F5, 0x6F0), n120: fa(0x6F1, 0x6F2, 0x6F0),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const conv = (status, needs_review) => ({ id: 'c-' + status, status, needs_review: !!needs_review });
const doc = (title, extraction_status, current_conversion, file_size) => ({ id: 'd-' + title, title, extraction_status, current_conversion,
  file_size: file_size === undefined ? 2936013 : file_size, mime_type: 'text/markdown', updated_at: '2026-10-23T10:00:00Z' });
// Documents by source id; "x" fails with a 500, "p" is a 120-document source.
const DOCS = {
  a: [doc('Report A.pdf', 'extracted', conv('succeeded')), doc('Notes', 'extracted', null, null)],
  r: [doc('Scan.pdf', 'extracted', conv('succeeded', true))],
  c: [doc('Blank.pdf', 'failed', conv('empty')), doc('Movie.mov', 'failed', conv('unsupported')), doc('Broken.pdf', 'failed', conv('failed'))],
  e: [],
};

function installMock(docs) {
  window.__requests = [];
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7); window.__requests.push(p);
    const q = new URLSearchParams(p.slice(p.indexOf('?') + 1));
    if (p.indexOf('/sources/overview?') === 0) {
      const id = q.get('id');
      return reply({ items: [{ id, title: 'Source ' + id, source_type: 'scientific_paper', author: null, publisher: null, publication_date: null,
        derived_status: 'completed', counts: { documents: 1, knowledge_objects: 0, claims: 0, evidence: 0 },
        last_activity_at: '2026-10-23T10:00:00Z' }], total: 1, limit: 50, offset: 0, counts_by_status: {} });
    }
    const m = p.match(/^\/sources\/([^/]+)\/documents\?/);
    if (m) {
      const limit = Number(q.get('limit')), offset = Number(q.get('offset'));
      if (m[1] === 'x') return reply({}, 500);
      const all = m[1] === 'p' ? Array.from({ length: 120 }, (_, i) => ({ id: 'p' + i, title: 'Doc ' + i, extraction_status: 'extracted',
        current_conversion: null, file_size: 1024, mime_type: 'text/markdown', updated_at: '2026-10-23T10:00:00Z' })) : docs[m[1]] || [];
      return reply({ items: all.slice(offset, offset + limit), total: all.length, limit, offset });
    }
    if (p === '/auth/me') return reply({ user: { role: 'viewer' }, organization: {} });
    return reply({}, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(150);
  const go = async (id) => { await page.evaluate((h) => { location.hash = h; }, '#screen-detail?id=' + id); await settle(); };
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const requests = () => page.evaluate(() => window.__requests || []);
  const docRequests = async () => (await requests()).filter((r) => /^\/sources\/[^/]+\/documents\?/.test(r));
  const list = () => page.evaluate(() => {
    const card = document.querySelector('#screen-detail .src-detail-docs');
    if (!card) return { title: null, head: null, rows: null, state: null, message: null, action: null, pager: null, prevDisabled: null, nextDisabled: null };
    const on = (e) => !!e && getComputedStyle(e).display !== 'none';
    const box = card.querySelector('.know-status'), act = box.querySelector('button');
    const prev = card.querySelector('.know-pager .btn'), next = prev && prev.nextElementSibling;
    return {
      title: card.querySelector('.card__title').textContent,
      head: Array.from(card.querySelectorAll('thead th')).map((th) => th.textContent),
      rows: on(card.querySelector('.table-wrap')) ? Array.from(card.querySelectorAll('tbody tr')).map((tr) =>
        [tr.cells[0].textContent, tr.cells[1].textContent].concat(Array.from(tr.cells[2].querySelectorAll('.badge')).map((b) => b.textContent))) : null,
      state: box.dataset.state, message: box.querySelector('p').textContent, action: act.hidden ? null : act.textContent,
      pager: on(card.querySelector('.know-pager')) ? card.querySelector('.know-pager__text').textContent : null,
      prevDisabled: prev ? prev.disabled : null, nextDisabled: next ? next.disabled : null,
    };
  });

  await page.evaluate(installMock, DOCS);
  await go('a');
  await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle();
  let v = await list();
  check('the card, its title and the five columns', [v.title, v.head], ['Documents', ['Document', 'Status', 'Conversion', 'Size', 'Updated']]);
  check('rows: extraction status and conversion status per document', v.rows,
    [['Report A.pdf', 'Extracted', 'Succeeded'], ['Notes', 'Extracted', 'No conversion']]);
  check('one documents request for the page', await docRequests(), ['/sources/a/documents?limit=50&offset=0']);
  check('no message while rows are shown', v.state, '');

  await go('r');
  check('needs_review adds "Needs human review" next to the conversion', (await list()).rows, [['Scan.pdf', 'Extracted', 'Succeeded', 'Needs human review']]);
  await go('c');
  check('empty, unsupported and failed conversions pair with failed extraction', (await list()).rows,
    [['Blank.pdf', 'Failed', 'Empty'], ['Movie.mov', 'Failed', 'Unsupported'], ['Broken.pdf', 'Failed', 'Failed']]);

  await go('e');
  v = await list();
  check('no documents: the message, no table, no pager', [v.state, v.message, v.rows, v.pager], ['empty', 'This source has no documents yet.', null, null]);

  await go('x');
  v = await list();
  check('500: the error with its status, Retry, no table', [v.state, v.message, v.action, v.rows],
    ['error', 'Could not load documents (' + FSI + 'HTTP 500' + PDI + ').', 'Retry', null]);
  const before = (await docRequests()).length;
  const retry = await page.$('#screen-detail .src-detail-docs .know-status button');
  if (retry) await retry.click();
  await settle();
  check('Retry sends the same request again', (await docRequests()).slice(before), ['/sources/x/documents?limit=50&offset=0']);

  await go('p');
  v = await list();
  check('120 documents: first 50 rows, counter, Previous off, Next on', [v.rows && v.rows.length, v.pager, v.prevDisabled, v.nextDisabled],
    [50, 'Showing 1 to 50 of 120', true, false]);
  const next = await page.$('#screen-detail .src-detail-docs .know-pager .btn + .btn');
  if (next) await next.click();
  await settle();
  v = await list();
  check('Next asks for offset 50 and shows rows 51 to 100', [(await docRequests()).slice(-1)[0], v.pager, v.rows && v.rows[0][0]],
    ['/sources/p/documents?limit=50&offset=50', 'Showing 51 to 100 of 120', 'Doc 50']);
  await go('a');
  check('another source starts on its first page', (await docRequests()).slice(-1), ['/sources/a/documents?limit=50&offset=0']);

  await lang('fa');
  v = await list();
  check('fa: title and column headers', [v.title, v.head], [FA.documentsTitle, [FA.document, FA.status, FA.conversion, FA.size, FA.updated]]);
  check('fa: statuses', v.rows && v.rows.map((r) => r.slice(1)), [[FA.extracted, FA.succeeded], [FA.extracted, FA.noConversion]]);
  await go('c');
  check('fa: conversion outcomes', ((await list()).rows || []).map((r) => r.slice(1)),
    [[FA.failed, FA.empty], [FA.failed, FA.unsupported], [FA.failed, FA.failed]]);
  await go('r');
  check('fa: needs review', ((await list()).rows || [[]])[0][3], FA.needsReview);
  await go('e');
  check('fa: no documents', (await list()).message, FA.noDocuments);
  await go('x');
  check('fa: load error', (await list()).message, FA.loadErrorBefore + FSI + 'HTTP 500' + PDI + FA.loadErrorAfter);
  await go('p');
  check('fa: counter', (await list()).pager, FA.pager[0] + FA.n1 + FA.pager[1] + FA.n50 + FA.pager[2] + FA.n120);
  await lang('en');
  check('back to English', (await list()).pager, 'Showing 1 to 50 of 120');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
