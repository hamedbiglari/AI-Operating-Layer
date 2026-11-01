#!/usr/bin/env node
/*
 * Browser checks for the Command workspace screen (Step 9F).
 *   Not connected: data-live-wired, the note shown, the body hidden.
 *   Live:   ONE list request (GET /workspace/commands?limit=50) and one
 *           resumable request; list items with state labels (an untitled one
 *           named so); the resume banner; opening a command (one request plus
 *           its versions): title, state chip, frozen-version line, save line,
 *           plan basics (what it will do, what it acts on), result header and
 *           an empty result list, the versions list with Compare; Run sends one
 *           POST and says so; a missing-scope refusal names the fields; a
 *           failed list shows the server message; Persian over live content.
 * Runs on file:// with AI Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/command-workspace.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-chat';
const fa = (...codes) => String.fromCharCode(...codes);
const FSI = fa(0x2068), PDI = fa(0x2069), MD = fa(0xB7), EM = fa(0x2014), LQ = fa(0x201C), RQ = fa(0x201D);
const iso = (s) => FSI + s + PDI;
const digits = (s) => s.replace(/[0-9]/g, (d) => String.fromCharCode(0x6F0 + Number(d)));
const FA = {
  completed: fa(0x62A, 0x6A9, 0x645, 0x6CC, 0x644, 0x200C, 0x634, 0x62F, 0x647),
  running: fa(0x62F, 0x631, 0x20, 0x62D, 0x627, 0x644, 0x20, 0x627, 0x62C, 0x631, 0x627),
  untitled: fa(0x628, 0x6CC, 0x200C, 0x639, 0x646, 0x648, 0x627, 0x646),
  frozen: (n, next) => fa(0x646, 0x633, 0x62E, 0x647, 0x654, 0x20) + digits(n) + fa(0x20, 0xB7, 0x20, 0x627, 0x62C, 0x631, 0x627, 0x20, 0x634, 0x62F, 0x647,
    0x20, 0x648, 0x20, 0x641, 0x642, 0x637, 0x200C, 0x62E, 0x648, 0x627, 0x646, 0x62F, 0x646, 0x6CC, 0x20, 0x627, 0x633, 0x62A, 0x20, 0x2014, 0x20, 0x648, 0x6CC,
    0x631, 0x627, 0x6CC, 0x634, 0x60C, 0x20, 0x646, 0x633, 0x62E, 0x647, 0x654, 0x20) + digits(next) + fa(0x20, 0x631, 0x627, 0x20, 0x622, 0x63A, 0x627, 0x632,
    0x20, 0x645, 0x6CC, 0x200C, 0x6A9, 0x646, 0x62F),
  saved: (rev) => fa(0x62F, 0x631) + ' AI Core ' + fa(0x630, 0x62E, 0x6CC, 0x631, 0x647, 0x20, 0x634, 0x62F, 0x20, 0xB7, 0x20, 0x628, 0x627, 0x632, 0x628,
    0x6CC, 0x646, 0x6CC, 0x20) + digits(rev) + '.',
  runningMsg: fa(0x631, 0x648, 0x6CC, 0x20, 0x633, 0x631, 0x648, 0x631, 0x20, 0x62F, 0x631, 0x20, 0x62D, 0x627, 0x644, 0x20, 0x627, 0x62C, 0x631, 0x627, 0x633,
    0x62A, 0x2E, 0x20, 0x645, 0x6CC, 0x200C, 0x62A, 0x648, 0x627, 0x646, 0x6CC, 0x62F, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x635, 0x641, 0x62D, 0x647, 0x20, 0x631,
    0x627, 0x20, 0x628, 0x628, 0x646, 0x62F, 0x6CC, 0x62F, 0x61B, 0x20, 0x6A9, 0x627, 0x631, 0x20, 0x627, 0x62F, 0x627, 0x645, 0x647, 0x20, 0x645, 0x6CC, 0x200C,
    0x6CC, 0x627, 0x628, 0x62F, 0x2E),
  continueQ: fa(0x6A9, 0x627, 0x631, 0x20, 0x642, 0x628, 0x644, 0x6CC, 0x20, 0x62E, 0x648, 0x62F, 0x20, 0x631, 0x627, 0x20, 0x627, 0x62F, 0x627, 0x645, 0x647,
    0x20, 0x645, 0x6CC, 0x200C, 0x62F, 0x647, 0x6CC, 0x62F, 0x61F),
  waiting: fa(0x62F, 0x631, 0x20, 0x627, 0x646, 0x62A, 0x638, 0x627, 0x631, 0x20, 0x627, 0x62F, 0x627, 0x645, 0x647),
  archive: fa(0x628, 0x627, 0x6CC, 0x6AF, 0x627, 0x646, 0x6CC),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

const C1 = { id: 'c1', title: 'Safety review', state: 'completed', archived: false, resumable: false, last_executed_version: 2,
  knowledge_object_id: null, category_id: null,
  current: { version: 2, draft_revision: 5, frozen: true, text: 'Analyze safety studies', intent: 'evidence_research',
    plan: { intent: 'evidence_research', proposed_intent: 'synthesis', description: 'Research the evidence', missing_scope: [], scope: { knowledge_object_id: 'k1' } },
    scope: {}, budget: {}, model_config: {}, execution_state: 'completed', executed_at: '2026-10-30T10:00:00Z', finished_at: '2026-10-30T10:05:00Z',
    result: { claims: [] } } };
const LIST = [{ id: 'c1', title: 'Safety review', state: 'completed', current_version: 2, current: { text: 'Analyze safety studies' } },
  { id: 'c2', title: null, state: 'running', current_version: 1, current: { text: '' } }];
const VERSIONS = [{ version: 1, execution_state: 'draft', text: 'first try' }, { version: 2, execution_state: 'completed', text: 'Analyze safety studies' }];

function installMock(d) {
  window.__requests = []; window.__listStatus = 200; window.__planStatus = 200;
  const reply = (body, status) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200 }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push(method + ' ' + p);
    if (p.indexOf('/workspace/commands?') === 0) return window.__listStatus === 200 ? reply({ items: d.list, total: d.list.length }) : reply({ detail: 'workspace offline' }, window.__listStatus);
    if (p === '/workspace/commands/resumable') return reply([{ id: 'c2', title: null, state: 'blocked', offer: ['continue'], error: 'budget reached' }]);
    if (p === '/workspace/commands/c1' && method === 'GET') return reply(d.c1);
    if (p === '/workspace/commands/c1/versions') return reply(d.versions);
    if (p === '/workspace/commands/c1/run' && method === 'POST') return reply({});
    if (p === '/workspace/commands/c1/plan' && method === 'POST') return window.__planStatus === 200 ? reply({}) : reply({ detail: { missing_scope: ['knowledge_object_id'] } }, 422);
    return reply({ items: [], total: 0 });
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(pageUrl);
  const settle = () => page.waitForTimeout(250);
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const connect = async () => { await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok')); await settle(); };
  const requests = () => page.evaluate(() => (window.__requests || []).filter((r) => r.indexOf('/workspace/') !== -1));
  const view = () => page.evaluate(() => {
    const $ = (id) => document.getElementById(id), t = (id) => $(id).textContent;
    return {
      items: Array.from(document.querySelectorAll('#ws-items .ws-item')).map((b) => [b.querySelector('.ws-item-title').textContent, b.querySelector('.ws-item-meta').textContent]),
      empty: document.querySelector('#ws-items .aic-empty') ? document.querySelector('#ws-items .aic-empty').textContent : null,
      resume: $('ws-resume').hidden ? null : t('ws-resume-text'),
      editor: !$('ws-editor').hidden,
      head: [t('ws-title'), t('ws-state'), t('ws-ver')], save: t('ws-save'), archive: t('ws-archive'),
      plan: Array.from(document.querySelectorAll('#ws-plan-out p')).map((p) => p.textContent),
      result: Array.from(document.querySelectorAll('#ws-result > *')).map((n) => n.textContent),
      versions: Array.from(document.querySelectorAll('#ws-versions li')).map((li) => li.textContent),
      msg: t('ws-msg'),
    };
  });

  // Not connected.
  check('data-live-wired; note shown, body hidden', await page.evaluate(() => [
    document.getElementById('screen-chat').hasAttribute('data-live-wired'), !document.querySelector('#screen-chat .kx-note').hidden,
    document.querySelector('#screen-chat .kx-body').hidden]), [true, true, true]);

  // Live.
  await page.evaluate(installMock, { list: LIST, c1: C1, versions: VERSIONS });
  await connect();
  check('ONE list request and one resumable request', await requests(), ['GET /workspace/commands?limit=50', 'GET /workspace/commands/resumable']);
  let v = await view();
  check('list items: titles (untitled named), state labels', v.items, [['Safety review', 'Completed ' + MD + ' v2'], ['Untitled', 'Running ' + MD + ' v1']]);
  check('the body is visible in live mode', await page.evaluate(() => getComputedStyle(document.querySelector('#screen-chat .kx-body')).display !== 'none'), true);
  check('resume banner', v.resume, 'Continue your previous task? Untitled ' + EM + ' Waiting to continue ' + EM + ' budget reached');

  // Open a command.
  let before = (await requests()).length;
  await page.click('#ws-items .ws-item'); await settle();
  v = await view();
  check('open: the command, then its versions (and the list again)', (await requests()).slice(before),
    ['GET /workspace/commands/c1', 'GET /workspace/commands/c1/versions', 'GET /workspace/commands?limit=50']);
  check('editor header and save line', [v.editor, v.head, v.save, v.archive], [true,
    ['Safety review', 'Completed', 'Version 2 ' + MD + ' has run, read-only ' + EM + ' editing starts version 3'], 'Saved to AI Core ' + MD + ' revision 5.', 'Archive']);
  check('plan basics', v.plan, ['It will: ' + iso('Research the evidence') + ' (you chose this; the text suggested ' + LQ + iso('synthesis') + RQ + ')',
    'Acts on: ' + iso('knowledge object id = k1')]);
  check('result header and the empty claim list', [v.result[0].indexOf('Version 2 ' + MD + ' Completed ' + MD + ' started ') === 0, v.result[1]],
    [true, 'No claims recorded on this page.']);
  check('versions list with Compare on v2', v.versions, ['v1 ' + MD + ' Draft ' + MD + ' first try View Restore as a new draft',
    'v2 ' + MD + ' Completed ' + MD + ' Analyze safety studies View Restore as a new draft Compare with v1']);

  // Run: one POST, then the message.
  before = (await requests()).length;
  await page.evaluate(() => { document.getElementById('ws-run').disabled = false; });
  await page.click('#ws-run'); await settle();
  check('Run: one POST, the message', [(await requests()).slice(before)[0], (await view()).msg],
    ['POST /workspace/commands/c1/run', 'Running on the server. You can close this page; it will keep going.']);

  // A missing-scope refusal names the fields.
  await page.evaluate(() => { window.__planStatus = 422; });
  await page.click('#ws-plan'); await settle();
  check('missing scope: the fields named', (await view()).msg, 'Set ' + iso('knowledge object id') + ' first (open ' + LQ + 'Scope, model and budget' + RQ + ').');
  await page.evaluate(() => { window.__planStatus = 200; });

  // Persian over live content (an identity entry would hang here).
  await page.click('#ws-items .ws-item'); await settle();
  await page.evaluate(() => { document.getElementById('ws-run').disabled = false; });
  await page.click('#ws-run'); await settle();
  await lang('fa');
  v = await view();
  check('fa: list state and untitled', [v.items[0][1], v.items[1][0]], [FA.completed + ' ' + MD + ' v2', FA.untitled]);
  check('fa: state chip, frozen line, save line, Archive', [v.head[1], v.head[2], v.save, v.archive], [FA.completed, FA.frozen('2', '3'), FA.saved('5'), FA.archive]);
  check('fa: the Run message', v.msg, FA.runningMsg);
  check('fa: resume banner', v.resume, FA.continueQ + ' ' + FA.untitled + ' ' + EM + ' ' + FA.waiting + ' ' + EM + ' budget reached');
  await lang('en');
  check('back to English', (await view()).head[1], 'Completed');

  // A failed list shows the server message.
  await page.evaluate(() => { window.__listStatus = 500; });
  await page.selectOption('#ws-filter', 'draft'); await settle();
  check('500: the server message', (await view()).msg, iso('workspace offline'));

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
