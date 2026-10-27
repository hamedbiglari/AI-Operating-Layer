#!/usr/bin/env node
/*
 * Browser checks for the Document processing screen (Step 7C-6c).
 *   Sample: the rewritten sample (D32): stage states, no unbacked details, the
 *           job line in two pieces around its id; Persian for all of it.
 *   Live:   GET /documents/{id}/processing, one request per document: title,
 *           format and date line, job badge, 8 stages with rebuilt details,
 *           7 metrics, the job line; the failed-reprocess banner (E6);
 *           job=None; no id, 404, 500 with Retry; Persian, including the job
 *           status after a language switch.
 *   Entry:  the "Processing details" link in a Source detail document row.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/processing-detail.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-processing';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069), MD = fa(0xB7), SP = ' ';
const iso = (s) => FSI + s + PDI;
const FA = {
  docProcessing: fa(0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634, 0x20, 0x633, 0x646, 0x62F),
  upload: fa(0x628, 0x627, 0x631, 0x6AF, 0x630, 0x627, 0x631, 0x6CC),
  notTracked: fa(0x62F, 0x631, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x646, 0x633, 0x62E, 0x647, 0x654, 0x20, 0x633, 0x627, 0x645, 0x627, 0x646,
    0x647, 0x20, 0x631, 0x62F, 0x6CC, 0x627, 0x628, 0x6CC, 0x20, 0x646, 0x645, 0x6CC, 0x200C, 0x634, 0x648, 0x62F),
  job: fa(0x6A9, 0x627, 0x631),
  attempt: fa(0x62A, 0x644, 0x627, 0x634),
  succeeded: fa(0x645, 0x648, 0x641, 0x642),
  failed: fa(0x646, 0x627, 0x645, 0x648, 0x641, 0x642),
  tables: fa(0x62C, 0x62F, 0x648, 0x644),
  noJob: fa(0x647, 0x6CC, 0x686, 0x20, 0x6A9, 0x627, 0x631, 0x6CC, 0x20, 0x628, 0x631, 0x627, 0x6CC, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x633,
    0x646, 0x62F, 0x20, 0x62B, 0x628, 0x62A, 0x20, 0x646, 0x634, 0x62F, 0x647, 0x20, 0x627, 0x633, 0x62A, 0x2E),
  banner: fa(0x622, 0x62E, 0x631, 0x6CC, 0x646, 0x20, 0x62A, 0x644, 0x627, 0x634, 0x20, 0x646, 0x627, 0x645, 0x648, 0x641, 0x642, 0x20, 0x628,
    0x648, 0x62F, 0x61B, 0x20, 0x62F, 0x627, 0x62F, 0x647, 0x200C, 0x647, 0x627, 0x20, 0x627, 0x632, 0x20, 0x627, 0x62C, 0x631, 0x627, 0x6CC,
    0x20, 0x642, 0x628, 0x644, 0x6CC, 0x20, 0x627, 0x633, 0x62A),
  n1: fa(0x6F1), n3: fa(0x6F3),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const KEYS = ['upload', 'security', 'conversion', 'structure', 'ocr', 'chunking', 'evidence', 'knowledge'];
const stages = (over) => KEYS.map((key) => Object.assign({ key, state: 'done', detail: null },
  key === 'evidence' || key === 'knowledge' ? { state: 'not_tracked' } : {}, over[key] || {}));
const metrics = (pages) => ({ pages, tables: pages === null ? null : 3, images: pages === null ? null : 0,
  ocr_blocks: pages === null ? null : 1, chunks: 40, claims: 2, evidence: 5 });
const job = (id, status, attempts) => ({ id, status, attempts, created_at: '2026-10-23T10:00:00Z', started_at: null, completed_at: null });
const PDF = 'application/pdf', DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
// Responses by document id; "missing" is a 404, "boom" a 500.
const DOCS = {
  ok: { document_title: 'Report A.pdf', mime_type: PDF, job: job('job-ok', 'succeeded', 1), metrics: metrics(12),
    stages: stages({ structure: { detail: '3 tables' }, ocr: { detail: '1 OCR block' } }) },
  fail: { document_title: 'Scan.docx', mime_type: DOCX, job: job('job-fail', 'failed', 3), metrics: metrics(9),
    stages: stages({ conversion: { state: 'failed', detail: 'RuntimeError: converter crashed' },
      structure: { state: 'not_tracked', detail: 'not run (conversion failed)' }, ocr: { state: 'not_tracked', detail: 'not run (conversion failed)' } }) },
  first: { document_title: 'New.pdf', mime_type: PDF, job: job('job-first', 'failed', 3), metrics: metrics(null),
    stages: stages({ conversion: { state: 'failed', detail: 'boom' } }) },
  nojob: { document_title: 'Notes', mime_type: 'text/plain', job: null, metrics: metrics(null),
    stages: stages({ conversion: { state: 'pending' }, structure: { state: 'pending' }, ocr: { state: 'pending' }, chunking: { state: 'pending' } }) },
  empty: { document_title: 'Blank.pdf', mime_type: 'application/x-odd', job: job('job-empty', 'succeeded', 1), metrics: metrics(1),
    stages: stages({ conversion: { state: 'failed', detail: 'no usable text' }, structure: { detail: '0 tables' }, ocr: { detail: '0 OCR blocks' } }) },
};

function installMock(docs) {
  window.__requests = [];
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7); window.__requests.push(p);
    const m = p.match(/^\/documents\/([^/]+)\/processing$/);
    if (m) {
      const id = decodeURIComponent(m[1]);
      if (id === 'boom') return reply({}, 500);
      return docs[id] ? reply(Object.assign({ document_id: id }, docs[id])) : reply({ detail: 'Not found' }, 404);
    }
    if (p.indexOf('/sources/overview?') === 0) {
      return reply({ items: [{ id: 's', title: 'Source s', source_type: 'scientific_paper', author: null, publisher: null, publication_date: null,
        derived_status: 'completed', counts: { documents: 1, knowledge_objects: 0, claims: 0, evidence: 0 },
        last_activity_at: '2026-10-23T10:00:00Z' }], total: 1, limit: 50, offset: 0, counts_by_status: {} });
    }
    if (/^\/sources\/s\/documents\?/.test(p)) {
      return reply({ items: [{ id: 'ok', title: 'Report A.pdf', extraction_status: 'extracted', current_conversion: null, file_size: 1024,
        mime_type: 'application/pdf', updated_at: '2026-10-23T10:00:00Z' }], total: 1, limit: 50, offset: 0 });
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
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await settle(); };
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /^\/documents\//.test(r)));
  const sample = () => page.evaluate(() => {
    const s = document.getElementById('screen-processing');
    const list = s.querySelector(':scope > div:not([data-live-keep]) ol.stages');
    return {
      crumb: s.querySelector(':scope > .breadcrumbs').lastElementChild.textContent,
      stages: Array.from(list.children).map((li) => [li.dataset.state, li.querySelector('.stages__name').textContent,
        li.querySelector('.stages__detail') ? li.querySelector('.stages__detail').textContent : null]),
      job: Array.from(s.querySelectorAll(':scope > div:not([data-live-keep]) .callout p > span')).map((x) => x.textContent),
    };
  });
  const view = () => page.evaluate(() => {
    const s = document.getElementById('screen-processing'), on = (e) => !!e && getComputedStyle(e).display !== 'none';
    const grid = s.querySelector('.proc-grid'), box = s.querySelector('[data-live-keep] .know-status'), act = box && box.querySelector('button');
    const badge = s.querySelector('#h-proc-live') && s.querySelector('#h-proc-live').closest('.page-header').querySelector('.page-actions .badge');
    return {
      title: s.querySelector('#h-proc-live') ? s.querySelector('#h-proc-live').textContent : null,
      meta: s.querySelector('.proc-meta') ? s.querySelector('.proc-meta').textContent : null,
      badge: badge ? [badge.className, badge.textContent] : null,
      banner: on(s.querySelector('.proc-banner')) ? s.querySelector('.proc-banner').textContent : null,
      stages: on(grid) ? Array.from(grid.querySelectorAll('ol.stages li')).map((li) => {
        const d = li.querySelector('.stages__detail');
        return [li.dataset.state, li.querySelector('.stages__name').textContent, d ? d.textContent : null,
          d && d.querySelector('bdi') ? 'raw' : d && d.classList.contains('stages__detail--warning') ? 'warning' : ''];
      }) : null,
      metrics: on(grid) ? Array.from(grid.querySelectorAll('dl.kv dd')).map((dd) => dd.textContent) : null,
      job: on(grid) ? grid.querySelector('.proc-job p').textContent : null,
      state: box ? box.dataset.state : null, message: box ? box.querySelector('p').textContent : null, action: act && !act.hidden ? act.textContent : null,
    };
  });

  // Sample mode (before any connection).
  let s = await sample();
  check('sample: breadcrumb names the screen', s.crumb, 'Document processing');
  check('sample: stage states, names and only backed details', s.stages, [['done', 'Upload', null], ['done', 'Security validation', null],
    ['done', 'Conversion', null], ['done', 'Structure detection', '9 tables'], ['done', 'OCR', '211 OCR blocks'], ['done', 'Semantic chunking', null],
    ['not_tracked', 'Evidence extraction', 'Not tracked in this backend version'],
    ['not_tracked', 'Knowledge contribution', 'Not tracked in this backend version']]);
  check('sample: job line in two pieces around the id', s.job, ['Job', MD + ' Succeeded ' + MD + ' attempt 1']);
  await lang('fa');
  s = await sample();
  check('fa sample: breadcrumb, a stage name, not tracked', [s.crumb, s.stages[0][1], s.stages[6][2]], [FA.docProcessing, FA.upload, FA.notTracked]);
  check('fa sample: job line pieces', s.job, [FA.job, MD + SP + FA.succeeded + SP + MD + SP + FA.attempt + SP + FA.n1]);
  await lang('en');

  // Live.
  await page.evaluate(installMock, DOCS);
  await go('#screen-processing?id=ok');
  await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle();
  let v = await view();
  check('one request for the document', await requests(), ['/documents/ok/processing']);
  check('header: title, format and date, job badge', [v.title, v.meta, v.badge],
    ['Report A.pdf', iso('PDF') + ' ' + MD + ' added 23 Oct 2026', ['badge badge--success', 'Succeeded']]);
  check('stages: rows as sent, details rebuilt, not tracked spelled out', v.stages, [['done', 'Upload', null, ''], ['done', 'Security validation', null, ''],
    ['done', 'Conversion', null, ''], ['done', 'Structure detection', '3 tables', ''], ['done', 'OCR', '1 OCR block', ''], ['done', 'Semantic chunking', null, ''],
    ['not_tracked', 'Evidence extraction', 'Not tracked in this backend version', ''],
    ['not_tracked', 'Knowledge contribution', 'Not tracked in this backend version', '']]);
  check('metrics: the 7 values', v.metrics, ['12', '3', '0', '1', '40', '2', '5']);
  check('job line and no banner', [v.job, v.banner], ['Job ' + iso('job-ok') + ' ' + MD + ' ' + iso('Succeeded') + ' ' + MD + ' attempt 1', null]);

  await go('#screen-processing?id=fail');
  v = await view();
  check('failed reprocess: banner, danger badge', [v.banner, v.badge], ['Last attempt failed; data from previous run', ['badge badge--danger', 'Failed']]);
  check('failed reprocess: raw error, then "not run" as a warning', v.stages.slice(2, 5), [
    ['failed', 'Conversion', 'RuntimeError: converter crashed', 'raw'],
    ['not_tracked', 'Structure detection', 'Not run (conversion failed)', 'warning'],
    ['not_tracked', 'OCR', 'Not run (conversion failed)', 'warning']]);
  check('DOCX label', v.meta, iso('DOCX') + ' ' + MD + ' added 23 Oct 2026');
  await go('#screen-processing?id=first');
  check('a failed first attempt has no older data: no banner', (await view()).banner, null);

  await go('#screen-processing?id=nojob');
  v = await view();
  check('job=None: no badge, format only, no job record', [v.badge, v.meta, v.job], [null, 'TXT', 'No job record for this document.']);
  check('job=None: missing metrics say the stage was not reached', v.metrics,
    ['Stage not reached', 'Stage not reached', 'Stage not reached', 'Stage not reached', '40', '2', '5']);
  await go('#screen-processing?id=empty');
  v = await view();
  check('"no usable text" reads Empty; zero counts; unknown format as sent', [v.stages[2][2], v.stages[3][2], v.stages[4][2], v.meta],
    ['Empty', '0 tables', '0 OCR blocks', iso('application/x-odd') + ' ' + MD + ' added 23 Oct 2026']);

  await go('#screen-processing');
  v = await view();
  check('no id: the message, no grid', [v.state, v.message, v.stages, v.title], ['empty', 'No document selected. Open one from Source detail.', null, 'Document processing']);
  await go('#screen-processing?id=missing');
  v = await view();
  check('404: not found', [v.state, v.message, v.stages], ['empty', 'This document was not found.', null]);
  await go('#screen-processing?id=boom');
  v = await view();
  check('500: the error with Retry', [v.state, v.message, v.action], ['error', 'Could not load processing (' + iso('HTTP 500') + ').', 'Retry']);
  const before = (await requests()).length;
  await page.click('#screen-processing [data-live-keep] .know-status button'); await settle();
  check('Retry sends the same request again', (await requests()).slice(before), ['/documents/boom/processing']);

  // Entry point: the link in a Source detail document row.
  await go('#screen-detail?id=s');
  // The row needs two requests in turn (the source, then its documents).
  await page.waitForSelector('#screen-detail .src-doc-actions a', { timeout: 5000 }).catch(() => {});
  const link = await page.evaluate(() => {
    const a = document.querySelector('#screen-detail .src-doc-actions a');
    return a && [a.getAttribute('href'), a.className, a.querySelector('[aria-hidden]').textContent, a.querySelector('.visually-hidden').textContent];
  });
  check('Source detail row: a Processing details link with the title spoken', link,
    ['#screen-processing?id=ok', 'btn btn--quiet', 'Processing details', 'Processing details of ' + iso('Report A.pdf')]);
  await page.click('#screen-detail .src-doc-actions a'); await settle();
  check('the link opens the document on Document processing', [await page.evaluate(() => location.hash), (await view()).title],
    ['#screen-processing?id=ok', 'Report A.pdf']);

  // Persian.
  await go('#screen-processing?id=fail');
  await lang('fa');
  v = await view();
  check('fa: job status inside the job line is Persian', v.job,
    FA.job + ' ' + iso('job-fail') + ' ' + MD + ' ' + iso(FA.failed) + ' ' + MD + ' ' + FA.attempt + ' ' + FA.n3);
  check('fa: banner and the first stage', [v.banner, v.stages[0][1]], [FA.banner, FA.upload]);
  await go('#screen-processing?id=ok');
  v = await view();
  check('fa: rebuilt detail and not tracked', [v.stages[3][2], v.stages[6][2]], [FA.n3 + ' ' + FA.tables, FA.notTracked]);
  await go('#screen-processing?id=nojob');
  check('fa: no job record', (await view()).job, FA.noJob);
  await lang('en');
  await go('#screen-processing?id=fail');
  check('back to English, status included', (await view()).job,
    'Job ' + iso('job-fail') + ' ' + MD + ' ' + iso('Failed') + ' ' + MD + ' attempt 3');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
