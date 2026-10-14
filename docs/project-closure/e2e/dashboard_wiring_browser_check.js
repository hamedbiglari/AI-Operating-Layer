const puppeteer = require('/home/claude/mapgen/node_modules/puppeteer');
const TOK = process.argv[2];
(async () => {
  const b = await puppeteer.launch({ headless: 'new', executablePath: '/home/claude/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome', args: ['--no-sandbox'] });
  const p = await b.newPage(); const errs = [];
  p.on('pageerror', e => errs.push('pageerror ' + e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.setViewport({ width: 1400, height: 1000 });
  const go = async id => { await p.evaluate(i => { location.hash = '#' + i; }, id); await new Promise(r => setTimeout(r, 500)); };
  await p.goto('http://localhost:8080/index.html#screen-dashboard', { waitUntil: 'networkidle0' });
  const out = {};
  out.before = await p.evaluate(() => ({ panels: document.querySelectorAll('.live-panel').length,
    note: document.querySelector('#live-screen-dashboard .live-note').textContent.slice(0, 60),
    sampleVisible: [...document.querySelectorAll('#screen-dashboard > :not(.page-header):not(.live-panel)')].some(e => e.offsetParent !== null) }));
  await p.$eval('#live-screen-dashboard .live-base', e => e.value = 'http://localhost:8000');
  await p.$eval('#live-screen-dashboard .live-token', (e, t) => e.value = t, TOK);
  await p.click('#live-screen-dashboard button[type=submit]'); await new Promise(r => setTimeout(r, 1500));
  out.overview = await p.$$eval('#live-screen-dashboard .stat', s => s.map(x => x.textContent.trim().replace(/\s+/g, ' ')));
  out.sampleHiddenWhenLive = await p.evaluate(() => [...document.querySelectorAll('#screen-dashboard > :not(.page-header):not(.live-panel):not(.breadcrumbs)')].every(e => getComputedStyle(e).display === 'none'));
  out.banner = await p.evaluate(() => { const n = [...document.querySelectorAll('div,p,aside')].find(n => /Live mode:/.test(n.textContent) && n.children.length === 0); return n ? n.textContent.slice(0, 70) : 'banner not updated'; });
  for (const id of ['screen-knowledge', 'screen-sources', 'screen-processing', 'screen-visibility', 'screen-products']) {
    await go(id); await new Promise(r => setTimeout(r, 900));
    out[id] = await p.evaluate(i => ({ rows: [...document.querySelectorAll('#live-' + i + ' tbody tr')].map(r => [...r.cells].map(c => c.textContent).slice(0, 3).join(' | ')),
      state: (document.querySelector('#live-' + i + ' .live-state') || {}).textContent }), id);
  }
  await go('screen-knowledge'); await p.click('#live-screen-knowledge tbody tr'); await new Promise(r => setTimeout(r, 900));
  out.knowledgeDetail = await p.$eval('#live-screen-knowledge .live-detail', e => e.textContent.replace(/\s+/g, ' ').slice(0, 300));
  await p.screenshot({ path: '/home/claude/p17ui/w-knowledge.png', fullPage: false });
  await go('screen-products'); await p.click('#live-screen-products tbody tr'); await new Promise(r => setTimeout(r, 900));
  out.productDetail = await p.$eval('#live-screen-products .live-detail', e => e.textContent.replace(/\s+/g, ' ').slice(0, 300));
  await go('screen-settings'); await new Promise(r => setTimeout(r, 900));
  const newName = 'Toranjebin Merchant (renamed ' + Date.now() % 10000 + ')';
  await p.$eval('#live-screen-settings .live-org-name', (e, v) => { e.value = v; }, newName);
  await p.click('#live-screen-settings .live-body button[type=submit]'); await new Promise(r => setTimeout(r, 1200));
  out.settingsSave = await p.$eval('#live-screen-settings .live-org-msg', e => e.textContent);
  await p.screenshot({ path: '/home/claude/p17ui/w-settings.png', fullPage: false });
  // full reload: new page state, reconnect, value must come back from the DB
  await p.goto('http://localhost:8080/index.html#screen-settings', { waitUntil: 'networkidle0' });
  await p.$eval('#live-screen-settings .live-token', (e, t) => e.value = t, TOK);
  await p.click('#live-screen-settings button[type=submit]'); await new Promise(r => setTimeout(r, 1200));
  out.settingsAfterReload = await p.$eval('#live-screen-settings .live-org-name', e => e.value);
  out.persisted = out.settingsAfterReload === newName;
  await go('screen-knowledge'); await p.select('#pick-lang', 'fa'); await new Promise(r => setTimeout(r, 300));
  for (const w of [390, 820]) { await p.setViewport({ width: w, height: 900 }); await new Promise(r => setTimeout(r, 300));
    out['overflow_' + w] = await p.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth); }
  await p.screenshot({ path: '/home/claude/p17ui/w-knowledge-rtl-390.png', fullPage: false });
  out.errors = errs.filter(e => !/var\(--icon-size\)|Failed to load resource/.test(e));
  console.log(JSON.stringify(out, null, 1));
  await b.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
