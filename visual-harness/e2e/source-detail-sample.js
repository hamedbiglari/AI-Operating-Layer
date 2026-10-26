#!/usr/bin/env node
/*
 * Browser checks for the Source detail sample and its CI gate (Step 7B2c).
 *   Sample: the six designed-but-unbuilt items (version badge, Archive,
 *           Delete, More actions, Research projects, Knowledge gaps affected)
 *           are hidden with data-debt-hidden, the status badge is not; the
 *           two titles stay as written in <bdi dir="ltr">, DOI, SHA-256 and
 *           MarkItDown in <bdi class="identifier">; every sample string is
 *           Persian in fa, the metadata line with Hamed and v3 isolated.
 *   Live:   with no source the heading reads "Source detail" and names the
 *           section; with a source it is the source's title.
 * Runs on file:// with Cloud Core mocked in the page. Persian expectations
 * are built from code points, so this file stays ASCII and no rendering can
 * reverse them.
 *
 * Usage: node visual-harness/e2e/source-detail-sample.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-detail';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = String.fromCharCode(0x2068), PDI = String.fromCharCode(0x2069);
// [English, Persian] for the heading and the 18 sample strings (7B2c glossary)
const SAMPLE = [
  ['Source detail', fa(0x62C, 0x632, 0x626, 0x6CC, 0x627, 0x62A, 0x20, 0x645, 0x646, 0x628, 0x639)],
  ['Identity', fa(0x645, 0x634, 0x62E, 0x635, 0x627, 0x62A)],
  ['Original file', fa(0x641, 0x627, 0x6CC, 0x644, 0x20, 0x627, 0x635, 0x644, 0x6CC)],
  ['Full text', fa(0x645, 0x62A, 0x646, 0x20, 0x6A9, 0x627, 0x645, 0x644)],
  ['Accessible', fa(0x62F, 0x631, 0x20, 0x62F, 0x633, 0x62A, 0x631, 0x633)],
  ['Rights', fa(0x62D, 0x642, 0x648, 0x642)],
  ['Unknown', fa(0x646, 0x627, 0x645, 0x634, 0x62E, 0x635)],
  ['What this source contributed', fa(0x633, 0x647, 0x645, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x645, 0x646, 0x628, 0x639)],
  ['Canonical representation', fa(0x628, 0x627, 0x632, 0x646, 0x645, 0x627, 0x6CC, 0x6CC, 0x20, 0x645, 0x631, 0x62C, 0x639)],
  ['Converter', fa(0x645, 0x628, 0x62F, 0x644)],
  ['Extraction level', fa(0x633, 0x637, 0x62D, 0x20, 0x627, 0x633, 0x62A, 0x62E, 0x631, 0x627, 0x62C)],
  ['Vision model', fa(0x645, 0x62F, 0x644, 0x20, 0x628, 0x6CC, 0x646, 0x627, 0x6CC, 0x6CC)],
  ['View Markdown', fa(0x645, 0x634, 0x627, 0x647, 0x62F, 0x647, 0x654, 0x20, 0x4D, 0x61, 0x72, 0x6B, 0x64, 0x6F, 0x77, 0x6E)],
  ['Source detail sections', fa(0x628, 0x62E, 0x634, 0x200C, 0x647, 0x627, 0x6CC, 0x20, 0x62C, 0x632, 0x626, 0x6CC, 0x627, 0x62A, 0x20, 0x645, 0x646, 0x628, 0x639)],
  ['3 \u2014 OCR', fa(0x6F3, 0x20, 0x2014, 0x20, 0x4F, 0x43, 0x52)],
  ['Level 4 not run', fa(0x633, 0x637, 0x62D, 0x20, 0x6F4, 0x20, 0x627, 0x62C, 0x631, 0x627, 0x20, 0x646, 0x634, 0x62F)],
  ['Scientific paper \u00B7 uploaded by Hamed \u00B7 2 Sep 2026 \u00B7 processing version v3', fa(0x645, 0x642, 0x627, 0x644, 0x647, 0x20, 0x639, 0x644, 0x645, 0x6CC, 0x20, 0xB7, 0x20, 0x628, 0x627, 0x631, 0x6AF, 0x630, 0x627, 0x631, 0x6CC, 0x200C, 0x634, 0x62F, 0x647, 0x20, 0x62A, 0x648, 0x633, 0x637, 0x20, 0x2068, 0x48, 0x61, 0x6D, 0x65, 0x64, 0x2069, 0x20, 0xB7, 0x20, 0x6F1, 0x6F1, 0x20, 0x634, 0x647, 0x631, 0x6CC, 0x648, 0x631, 0x20, 0x6F1, 0x6F4, 0x6F0, 0x6F5, 0x20, 0xB7, 0x20, 0x646, 0x633, 0x62E, 0x647, 0x654, 0x20, 0x67E, 0x631, 0x62F, 0x627, 0x632, 0x634, 0x20, 0x2068, 0x76, 0x33, 0x2069)],
  ['31 evidence records exist. 19 are verified; 12 are still pending review and count toward nothing.', fa(0x6F3, 0x6F1, 0x20, 0x634, 0x627, 0x647, 0x62F, 0x20, 0x62B, 0x628, 0x62A, 0x20, 0x634, 0x62F, 0x647, 0x20, 0x627, 0x633, 0x62A, 0x2E, 0x20, 0x6F1, 0x6F9, 0x20, 0x645, 0x648, 0x631, 0x62F, 0x20, 0x62A, 0x623, 0x6CC, 0x6CC, 0x62F, 0x634, 0x62F, 0x647, 0x20, 0x627, 0x633, 0x62A, 0x61B, 0x20, 0x6F1, 0x6F2, 0x20, 0x645, 0x648, 0x631, 0x62F, 0x20, 0x647, 0x646, 0x648, 0x632, 0x20, 0x62F, 0x631, 0x20, 0x627, 0x646, 0x62A, 0x638, 0x627, 0x631, 0x20, 0x628, 0x631, 0x631, 0x633, 0x6CC, 0x20, 0x627, 0x633, 0x62A, 0x20, 0x648, 0x20, 0x62F, 0x631, 0x20, 0x647, 0x6CC, 0x686, 0x20, 0x634, 0x645, 0x627, 0x631, 0x6CC, 0x20, 0x62D, 0x633, 0x627, 0x628, 0x20, 0x646, 0x645, 0x6CC, 0x200C, 0x634, 0x648, 0x62F, 0x2E)],
  ['The original PDF stays authoritative. Markdown is derived, and is not knowledge.', fa(0x50, 0x44, 0x46, 0x20, 0x627, 0x635, 0x644, 0x6CC, 0x20, 0x647, 0x645, 0x686, 0x646, 0x627, 0x646, 0x20, 0x645, 0x631, 0x62C, 0x639, 0x20, 0x627, 0x633, 0x62A, 0x2E, 0x20, 0x4D, 0x61, 0x72, 0x6B, 0x64, 0x6F, 0x77, 0x6E, 0x20, 0x627, 0x632, 0x20, 0x622, 0x646, 0x20, 0x628, 0x631, 0x6AF, 0x631, 0x641, 0x62A, 0x647, 0x20, 0x634, 0x62F, 0x647, 0x20, 0x648, 0x20, 0x62F, 0x627, 0x646, 0x634, 0x20, 0x646, 0x6CC, 0x633, 0x62A, 0x2E)],
];
const HEADING = SAMPLE[0];
const DEBT = ['V5-source-detail-version-badge', 'V5-source-detail-archive', 'V5-source-detail-delete', 'V5-source-detail-more-actions',
  'V5-source-detail-research-projects', 'V5-source-detail-gaps-affected'];

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

function installMock() {
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u) => {
    const p = String(u).slice(String(u).indexOf('/api/v1') + 7);
    if (p.indexOf('/sources/overview?') === 0) {
      return reply({ items: [{ id: 'a', title: 'Source A', source_type: 'scientific_paper', author: null, publisher: null, publication_date: null,
        derived_status: 'completed', counts: { documents: 0, knowledge_objects: 0, claims: 0, evidence: 0 },
        last_activity_at: '2026-10-23T10:00:00Z' }], total: 1, limit: 50, offset: 0, counts_by_status: {} });
    }
    if (p.indexOf('/sources/a/documents?') === 0) return reply({ items: [], total: 0, limit: 50, offset: 0 });
    if (p === '/auth/me') return reply({ user: { role: 'viewer' }, organization: {} });
    return reply({}, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(150);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const go = async (h) => { await page.evaluate((x) => { location.hash = x; }, h); await settle(); };
  const on = (sel) => page.$$eval(sel, (es) => es.map((e) => getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0));
  const sample = () => page.evaluate(() => {
    const s = document.getElementById('screen-detail');
    const crumb = s.querySelector(':scope > .breadcrumbs').lastElementChild.querySelector('bdi[dir="ltr"]');
    const title = s.querySelector('#h-detail bdi[dir="ltr"]');
    const ids = Array.from(s.querySelectorAll('bdi.identifier')).map((b) => b.textContent);
    return { crumb: crumb && [crumb.textContent, getComputedStyle(crumb).direction], title: title && [title.textContent, getComputedStyle(title).direction],
      ids: ['DOI', 'SHA-256', 'MarkItDown'].filter((t) => ids.includes(t)),
      meta: s.querySelector('.page-intro p').textContent, text: s.textContent,
      tablist: s.querySelector('[role="tablist"]').getAttribute('aria-label') };
  });

  // Sample mode, English
  for (const id of DEBT) {
    const seen = await on('#screen-detail [data-debt-hidden="' + id + '"]');
    check('hidden: ' + id + ' (marked, and not shown)', [seen.length > 0, seen.some(Boolean)], [true, false]);
  }
  check('the status badge (Completed) stays visible', await on('#screen-detail #h-detail + p .badge--success'), [true]);
  let v = await sample();
  check('titles stay as written, left to right', [v.crumb, v.title],
    [['Toranjebin Scientific Review', 'ltr'], ['Toranjebin (Alhagi manna) ' + String.fromCharCode(0x2014) + ' Scientific Review 2025', 'ltr']]);
  check('DOI, SHA-256 and MarkItDown are identifiers', v.ids, ['DOI', 'SHA-256', 'MarkItDown']);
  check('en: the metadata line as written', v.meta, 'Scientific paper ' + String.fromCharCode(0xB7) + ' uploaded by Hamed ' + String.fromCharCode(0xB7) +
    ' 2 Sep 2026 ' + String.fromCharCode(0xB7) + ' processing version v3');

  // Sample mode, Persian
  await lang('fa');
  v = await sample();
  const missing = SAMPLE.slice(1).filter(([en, f]) => en !== 'Source detail sections' && !v.text.includes(f)).map(([en]) => en);
  check('fa: every sample string is Persian', missing, []);
  check('fa: the tab list is named in Persian', v.tablist, SAMPLE.find(([en]) => en === 'Source detail sections')[1]);
  check('fa: Hamed and v3 are isolated inside the Persian metadata line', [v.meta.includes(FSI + 'Hamed' + PDI), v.meta.includes(FSI + 'v3' + PDI)], [true, true]);
  check('fa: titles and identifiers stay Latin', [v.crumb && v.crumb[0], v.ids], ['Toranjebin Scientific Review', ['DOI', 'SHA-256', 'MarkItDown']]);
  await lang('en');

  // Live: the heading names the section with and without a source
  await page.evaluate(installMock);
  await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle();
  const heading = () => page.evaluate(() => {
    const s = document.getElementById('screen-detail'), h = document.getElementById(s.getAttribute('aria-labelledby'));
    return h ? [h.id, h.textContent, getComputedStyle(h.closest('.page-header')).display !== 'none'] : null;
  });
  check('no source: the heading reads Source detail, visible, and names the section', await heading(), ['h-detail-live', 'Source detail', true]);
  await lang('fa');
  check('fa: the heading in Persian', (await heading())[1], HEADING[1]);
  await lang('en');
  await go('#screen-detail?id=a');
  check('with a source: the heading is its title', await heading(), ['h-detail-live', 'Source A', true]);
  await go('#screen-detail');
  check('back to no source: Source detail again', (await heading())[1], 'Source detail');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
