#!/usr/bin/env node
/*
 * Browser regression checks for the Knowledge screen fixes in 399db40:
 *   1. The card grid stays hidden until "Windowed view" is chosen (its layout
 *      must not override [hidden]), and the toggle works both ways.
 *   2. "Research again" adds one version row and one version card per click,
 *      without cloning its own button.
 *   3. The live detail renders the keyword workspace exactly once.
 * Runs against visual-harness/index.html from file://; Cloud Core is mocked
 * in the page, so no server is needed.
 *
 * Usage: node visual-harness/e2e/knowledge-quickfix.js
 *   PLAYWRIGHT_CORE  path to a playwright-core package (default: resolve 'playwright-core')
 *   PW_EXE           optional browser executable (default: Playwright's own)
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');

const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-knowledge';

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', (e) => { failures++; console.log('PAGE ERROR ' + e.message); });
  await page.goto(pageUrl);
  const display = () => page.evaluate(() =>
    ['know-view-table', 'know-view-grid'].map((id) => getComputedStyle(document.getElementById(id)).display));

  // 1. Table and card grid never render together.
  check('load: table shown, grid hidden', await display(), ['block', 'none']);
  await page.click('#screen-knowledge .view-toggle__btn[data-view="grid"]');
  check('windowed view: table hidden, grid shown', await display(), ['none', 'grid']);
  check('grid keeps its columns and gap', await page.evaluate(() => {
    const s = getComputedStyle(document.getElementById('know-view-grid'));
    return [s.gridTemplateColumns.split(' ').length > 1, s.columnGap];
  }), [true, '16px']);
  await page.click('#screen-knowledge .view-toggle__btn:not([data-view="grid"])');
  check('rows view again: table shown, grid hidden', await display(), ['block', 'none']);

  // 2. Research again: one version per click, one button per row and card.
  for (let i = 0; i < 2; i++) await page.click('#know-view-table .research-again-btn[data-entity="taranjebin"] >> nth=0');
  const versions = await page.evaluate(() => {
    const table = document.getElementById('know-view-table'), grid = document.getElementById('know-view-grid');
    const rows = [...table.querySelectorAll('tr[data-entity="taranjebin"]')];
    const cards = [...grid.querySelectorAll('.card[data-entity="taranjebin"]')];
    const last = rows[rows.length - 1].querySelector('.updated-cell');
    return {
      rows: rows.length, cards: cards.length,
      versions: rows.map((r) => r.dataset.version),
      tags: rows.map((r) => (r.querySelector('.version-tag') || {}).textContent),
      buttonsPerRow: rows.map((r) => r.querySelectorAll('.research-again-btn').length),
      buttonsPerCard: cards.map((c) => c.querySelectorAll('.research-again-btn').length),
      newest: last && last.textContent,
      others: ['saffron', 'garlic', 'thyme'].map((e) => table.querySelectorAll('tr[data-entity="' + e + '"]').length),
    };
  });
  check('2 clicks give 3 rows and 3 cards', [versions.rows, versions.cards], [3, 3]);
  check('versions 1..3 and tags v1..v3', [versions.versions, versions.tags], [['1', '2', '3'], ['v1', 'v2', 'v3']]);
  check('one button per row and per card', [versions.buttonsPerRow, versions.buttonsPerCard], [[1, 1, 1], [1, 1, 1]]);
  check('newest version is stamped Just now', versions.newest, 'Just now');
  check('other objects untouched', versions.others, [1, 1, 1]);

  // 3. The live detail renders one keyword workspace (Cloud Core mocked).
  await page.evaluate(() => {
    const ko = { id: 'k1', canonical_name: 'Toranjebin', object_type: 'plant', status: 'draft', version: 1, slug: 'toranjebin',
      language: 'fa', updated_at: '2026-10-23T10:00:00Z', created_at: '2026-10-23T10:00:00Z' };
    const counts = { sources: 0, claims: 0, claims_conflicting: 0, evidence: 0, evidence_verified: 0, evidence_pending_review: 0, gaps_open: 0 };
    window.fetch = (u) => {
      u = String(u);
      const body = /\/knowledge\/overview\?/.test(u) ? { items: [Object.assign({ counts, finished: false }, ko)], total: 1, limit: 50, offset: 0, finished_visible: false }
        : /\/knowledge\/k1(\?|$)/.test(u) ? ko
        : { items: [], total: 0, limit: 20, offset: 0 };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    };
    window.AIOL_LIVE_CONNECT('http://core.test', 'tok');
  });
  await page.waitForSelector('#know-view-table tbody .know-name', { timeout: 10000 });
  // A name now opens #screen-knowledge-detail (8B-3); the workspace opens from its own button.
  await page.click('#know-view-table tbody .research-workspace-btn');
  await page.waitForSelector('#live-screen-knowledge .kw-workspace', { timeout: 10000 });
  await page.waitForTimeout(500);
  check('detail shows exactly one keyword workspace',
    await page.evaluate(() => document.querySelectorAll('#live-screen-knowledge .kw-workspace').length), 1);
  check('it is the current workspace (REQ-KW-001..004)',
    await page.evaluate(() => document.querySelector('#live-screen-knowledge .kw-workspace h4').textContent), 'Keyword & query workspace');

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
