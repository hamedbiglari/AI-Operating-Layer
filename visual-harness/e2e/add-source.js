#!/usr/bin/env node
/*
 * Browser checks for the Add source screen (Step 7E).
 *   Sample: two design cards shown (Document, Web page); Research and Supplier
 *           document hidden as debt; no Dataset or Site article card; English and Persian.
 *   Live:   GET /sources/overview?limit=100 fills the source picker; the Document
 *           card uploads a file (POST /documents/upload, multipart source_id + file),
 *           the Web page card queues a URL (POST /documents/ingest-url, JSON);
 *           success says so and opens #screen-detail?id=<source>; empty input,
 *           500, 422, 403, no sources, a failed source list with Retry; Persian.
 * Runs on file:// with Cloud Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/add-source.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-add';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069);
const iso = (s) => FSI + s + PDI;
const FA = {
  document: fa(0x633, 0x646, 0x62F),
  webPage: fa(0x635, 0x641, 0x62D, 0x647, 0x654, 0x20, 0x648, 0x628),
  research: fa(0x67E, 0x698, 0x648, 0x647, 0x634),
  supplier: fa(0x633, 0x646, 0x62F, 0x20, 0x62A, 0x623, 0x645, 0x6CC, 0x646, 0x200C, 0x6A9, 0x646, 0x646, 0x62F, 0x647),
  upload: fa(0x628, 0x627, 0x631, 0x6AF, 0x630, 0x627, 0x631, 0x6CC),
  addWebPage: fa(0x627, 0x641, 0x632, 0x648, 0x62F, 0x646, 0x20, 0x635, 0x641, 0x62D, 0x647, 0x654, 0x20, 0x648, 0x628),
  chooseFile: fa(0x627, 0x628, 0x62A, 0x62F, 0x627, 0x20, 0x6CC, 0x6A9, 0x20, 0x641, 0x627, 0x6CC, 0x644, 0x20,
    0x627, 0x646, 0x62A, 0x62E, 0x627, 0x628, 0x20, 0x6A9, 0x646, 0x6CC, 0x62F, 0x2E),
  uploadFailed: (e) => fa(0x628, 0x627, 0x631, 0x6AF, 0x630, 0x627, 0x631, 0x6CC, 0x20, 0x646, 0x627, 0x645, 0x648, 0x641, 0x642,
    0x20, 0x628, 0x648, 0x62F, 0x20, 0x28) + e + fa(0x29, 0x2E),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const SOURCES = [{ id: 'src-1', title: 'Review 2025' }, { id: 'src-2', title: 'Survey 2023' }];

function installMock(sources) {
  window.__requests = []; window.__sent = []; window.__sources = sources;
  window.__listStatus = 200; window.__uploadStatus = 202; window.__urlStatus = 202;
  const reply = (body, status) => Promise.resolve(new Response(body === null ? null : JSON.stringify(body), { status: status || 200 }));
  const accepted = (doc) => ({ job_id: 'job-1', status: 'queued', job_type: 'ingestion', job_created: true, source_hash: 'h',
    storage_path_recorded: !!doc, created_at: '2026-10-31T10:00:00Z', status_url: '/api/v1/documents/ingestion-jobs/job-1',
    document_id: doc, conversion_id: doc ? 'conv-1' : null });
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (p === '/sources/overview?limit=100') {
      if (window.__listStatus !== 200) return reply({}, window.__listStatus);
      return reply({ items: window.__sources, total: window.__sources.length, limit: 100, offset: 0, counts_by_status: {} });
    }
    if (p === '/documents/upload' && method === 'POST') {
      const body = opt.body, form = body instanceof FormData;
      window.__sent.push(form ? Array.from(body.entries()).map(([k, v]) => [k, typeof v === 'string' ? v : 'file:' + v.name])
        : 'not FormData');
      window.__sent.push(opt.headers['Content-Type'] || 'no content type');
      return window.__uploadStatus === 202 ? reply(accepted('doc-1'), 202) : reply({ detail: 'no' }, window.__uploadStatus);
    }
    if (p === '/documents/ingest-url' && method === 'POST') {
      window.__sent.push(JSON.parse(opt.body));
      return window.__urlStatus === 202 ? reply(accepted(null), 202) : reply({ detail: 'no' }, window.__urlStatus);
    }
    if (p === '/auth/me') return reply({ user: { role: 'editor' }, organization: {} });
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
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => /\/sources\/overview\?limit|\/documents\//.test(r)));
  const sent = () => page.evaluate(() => window.__sent.splice(0));
  const sample = () => page.evaluate(() => {
    const grid = document.querySelector('#screen-add > div[style*="grid"]');
    return Array.from(grid.querySelectorAll('button.card')).map((b) => [b.querySelectorAll('span')[1].textContent, getComputedStyle(b).display !== 'none']);
  });
  const view = () => page.evaluate(() => {
    const s = document.getElementById('screen-add'), body = s.querySelector('.add-live');
    const msg = (box) => (box ? [box.dataset.state, box.querySelector('p').textContent] : null);
    const form = (id) => { const f = document.getElementById(id); return f ? {
      title: f.querySelector('.card__title').textContent, button: f.querySelector('button[type=submit]').textContent,
      disabled: f.querySelector('button[type=submit]').disabled, say: msg(f.querySelector('.know-status')) } : null; };
    const st = body && body.querySelector(':scope > .know-status'), act = st && st.querySelector('button');
    return {
      hash: location.hash,
      sampleShown: getComputedStyle(s.querySelector(':scope > div[style*="grid"]')).display !== 'none',
      options: body ? Array.from(body.querySelectorAll('select option')).map((o) => [o.value, o.textContent]) : null,
      status: msg(st), action: act && !act.hidden ? act.textContent : null,
      upload: form('add-upload'), url: form('add-url'),
    };
  });
  const pickFile = () => page.setInputFiles('#add-upload input[type=file]', { name: 'report.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') });

  // Sample mode (before any connection).
  check('sample: two cards shown, two hidden, no Dataset or Site article', await sample(),
    [['Document', true], ['Web page', true], ['Research', false], ['Supplier document', false]]);
  await lang('fa');
  check('fa sample: card titles', (await sample()).map((c) => c[0]), [FA.document, FA.webPage, FA.research, FA.supplier]);
  await lang('en');

  // Live.
  await page.evaluate(installMock, SOURCES);
  await connect();
  let v = await view();
  check('one request for the source list', await requests(), ['GET /sources/overview?limit=100']);
  check('the sample cards are hidden; the picker lists the sources', [v.sampleShown, v.options],
    [false, [['src-1', 'Review 2025'], ['src-2', 'Survey 2023']]]);
  check('two live cards with their buttons', [v.upload && [v.upload.title, v.upload.button, v.upload.disabled], v.url && [v.url.title, v.url.button, v.url.disabled]],
    [['Document', 'Upload', false], ['Web page', 'Add web page', false]]);

  // Upload.
  let before = (await requests()).length;
  await page.click('#add-upload button[type=submit]'); await settle();
  v = await view();
  check('upload with no file: said, nothing sent', [v.upload.say, (await requests()).slice(before)], [['error', 'Choose a file first.'], []]);
  await page.selectOption('#screen-add .add-live select', 'src-2');
  await pickFile();
  await page.click('#add-upload button[type=submit]'); await settle();
  v = await view();
  check('upload: one multipart POST', (await requests()).slice(before), ['POST /documents/upload']);
  check('upload: source_id and the file, no JSON content type', await sent(), [[['source_id', 'src-2'], ['file', 'file:report.pdf']], 'no content type']);
  check('upload success: the message, then Source detail of that source', [v.upload.say, v.hash],
    [['done', 'Uploaded and queued for processing.'], '#screen-detail?id=src-2']);

  // Web page.
  await go('#screen-add');
  before = (await requests()).length;
  await page.click('#add-url button[type=submit]'); await settle();
  v = await view();
  check('URL empty: said, nothing sent', [v.url.say, (await requests()).slice(before)], [['error', 'Enter a web address first.'], []]);
  await page.selectOption('#screen-add .add-live select', 'src-1');
  await page.fill('#add-url input[type=url]', '  https://example.org/article  ');
  await page.click('#add-url button[type=submit]'); await settle();
  v = await view();
  check('URL: one POST with source_id and the trimmed URL', [(await requests()).slice(before), await sent()],
    [['POST /documents/ingest-url'], [{ source_id: 'src-1', url: 'https://example.org/article' }]]);
  check('URL success: the message, then Source detail', [v.url.say, v.hash], [['done', 'Web page queued for processing.'], '#screen-detail?id=src-1']);

  // Errors stay on the screen.
  await go('#screen-add');
  await page.evaluate(() => { window.__uploadStatus = 500; window.__urlStatus = 422; });
  await pickFile();
  await page.click('#add-upload button[type=submit]'); await settle();
  v = await view();
  check('upload 500: the error, no redirect, button enabled again', [v.upload.say, v.hash, v.upload.disabled],
    [['error', 'Upload failed (' + iso('HTTP 500') + ').'], '#screen-add', false]);
  await page.fill('#add-url input[type=url]', 'http://169.254.169.254/');
  await page.click('#add-url button[type=submit]'); await settle();
  v = await view();
  check('URL 422: the error, no redirect; the upload message is cleared', [v.url.say, v.hash, v.upload.say],
    [['error', 'Could not add the web page (' + iso('HTTP 422') + ').'], '#screen-add', ['', '']]);
  await page.evaluate(() => { window.__uploadStatus = 403; });
  await page.click('#add-upload button[type=submit]'); await settle();
  v = await view();
  check('upload 403: the role message', v.upload.say, ['denied', 'Your role is not allowed to add documents (HTTP 403).']);

  // Persian over live content (an identity entry would hang here).
  await page.evaluate(() => { window.__uploadStatus = 500; });
  await page.click('#add-upload button[type=submit]'); await settle();
  await lang('fa');
  v = await view();
  check('fa: card titles, buttons, the error', [v.upload.title, v.upload.button, v.url.title, v.url.button, v.upload.say[1]],
    [FA.document, FA.upload, FA.webPage, FA.addWebPage, FA.uploadFailed(iso('HTTP 500'))]);
  await lang('en');

  // No sources, then a failed list with Retry (a new connection reloads the list).
  await page.evaluate(() => { window.__sources = []; });
  await connect();
  v = await view();
  check('no sources: said, both buttons disabled', [v.status, v.options, v.upload.disabled, v.url.disabled],
    [['empty', 'No sources yet. Create one with the form above first.'], [], true, true]);
  await page.evaluate(() => { window.__listStatus = 500; });
  await connect();
  v = await view();
  check('source list 500: the error with Retry', [v.status, v.action], [['error', 'Could not load sources (' + iso('HTTP 500') + ').'], 'Retry']);
  await page.evaluate(() => { window.__listStatus = 200; window.__sources = [{ id: 'src-3', title: 'Lab panel' }]; });
  before = (await requests()).length;
  await page.click('#screen-add .add-live > .know-status button'); await settle();
  v = await view();
  check('Retry: the list again, then the picker', [(await requests()).slice(before), v.options, v.status[0]],
    [['GET /sources/overview?limit=100'], [['src-3', 'Lab panel']], '']);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
