// ENGLISH_LOCALE_AUDIT: in English mode, find visible text containing Persian script.
// Splits hits into (a) UI chrome: labels, buttons, headings, placeholders, options, tooltips;
// (b) content: sample tenant data (names of products, sources, knowledge) rendered inside <bdi>/table cells.
const puppeteer = require('/home/claude/mapgen/node_modules/puppeteer');
(async () => {
  const b = await puppeteer.launch({ headless: 'new', executablePath: '/home/claude/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome', args: ['--no-sandbox'] });
  const p = await b.newPage(); await p.setViewport({ width: 1400, height: 900 });
  await p.goto('file://' + require('path').resolve(__dirname, 'index.html') + '', { waitUntil: 'networkidle0' });
  const ids = await p.$$eval('section.screen', s => s.map(x => x.id)); const ui = {}, content = {};
  for (const id of ids) { await p.evaluate(i => location.hash = '#' + i, id); await new Promise(r => setTimeout(r, 60));
    const r = await p.evaluate(() => { const fa = /[\u0600-\u06FF]/; const U = [], C = [];
      const scr = document.querySelector('section.screen.is-active');
      scr.querySelectorAll('input[placeholder], [title], [aria-label]').forEach(e => { ['placeholder', 'title', 'aria-label'].forEach(a => { const v = e.getAttribute(a); if (v && fa.test(v)) U.push(a + ': ' + v.slice(0, 40)); }); });
      const walker = document.createTreeWalker(scr, NodeFilter.SHOW_TEXT); let n;
      while ((n = walker.nextNode())) { const t = n.textContent.trim(); if (!t || !fa.test(t)) continue; const el = n.parentElement; if (!el.offsetParent) continue;
        const isContent = el.closest('bdi, td, dd, .identifier, [lang="fa"], .kw-list, option[data-sample]');
        const isChrome = el.closest('button, label, h1, h2, h3, th, legend, .field__label, .badge, nav, .page-intro, option');
        (isChrome && !isContent ? U : C).push(t.slice(0, 40)); }
      return { U: [...new Set(U)], C: [...new Set(C)].length }; });
    if (r.U.length) ui[id] = r.U.slice(0, 5); if (r.C) content[id] = r.C; }
  console.log(JSON.stringify({ screens: ids.length, ui_chrome_hits: ui, content_hits_per_screen: content }, null, 1)); await b.close();
})();
