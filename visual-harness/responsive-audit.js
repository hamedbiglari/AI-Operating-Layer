// Responsive layout audit: every screen x viewport. Reports page overflow, elements escaping
// their card/container, undersized touch targets, and clipped text.
const puppeteer = require('/home/claude/mapgen/node_modules/puppeteer');
const WIDTHS = (process.argv[2] || '360,390,768,1024,1400').split(',').map(Number);
const DIR = process.argv[3] || 'ltr';
(async () => {
  const b = await puppeteer.launch({ headless: 'new', executablePath: '/home/claude/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto('file://' + require('path').resolve(__dirname, 'index.html') + '', { waitUntil: 'networkidle0' });
  if (DIR === 'rtl') { await p.select('#pick-lang', 'fa'); }
  const ids = await p.$$eval('section.screen', s => s.map(x => x.id));
  const report = {};
  for (const w of WIDTHS) {
    await p.setViewport({ width: w, height: 900 });
    for (const id of ids) {
      await p.evaluate(i => { location.hash = '#' + i; }, id); await new Promise(r => setTimeout(r, 120));
      const r = await p.evaluate(() => {
        const screen = document.querySelector('section.screen.is-active') || document.querySelector('section.screen:target');
        const out = { pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, escapes: [], small: [], clipped: [] };
        if (!screen) return out;
        const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
        const scrollsX = e => { const s = getComputedStyle(e); return /(auto|scroll|hidden)/.test(s.overflowX); };
        for (const e of screen.querySelectorAll('*')) {
          if (!e.offsetParent && getComputedStyle(e).position !== 'fixed') continue;
          const rc = e.getBoundingClientRect(); if (!rc.width || !rc.height) continue;
          // nearest clipping/scroll ancestor or card/screen
          let a = e.parentElement, box = null;
          while (a && a !== screen.parentElement) { if (scrollsX(a) || a.classList.contains('card') || a === screen) { box = a; break; } a = a.parentElement; }
          if (box && !scrollsX(box)) { const br = box.getBoundingClientRect();
            if (rc.right > br.right + 2 || rc.left < br.left - 2) out.escapes.push(sel(e) + ' in ' + sel(box) + ' by ' + Math.round(Math.max(rc.right - br.right, br.left - rc.left)) + 'px'); }
          if (e.matches('button, a.btn, input:not([type=hidden]), select, [role=button]') && (rc.height < 24 || rc.width < 24)) out.small.push(sel(e) + ' ' + Math.round(rc.width) + 'x' + Math.round(rc.height));
          const s = getComputedStyle(e);
          if (e.children.length === 0 && e.textContent.trim() && s.overflow !== 'visible' && s.textOverflow !== 'ellipsis' && e.scrollWidth > e.clientWidth + 2 && !scrollsX(e.parentElement)) out.clipped.push(sel(e));
        }
        out.escapes = [...new Set(out.escapes)].slice(0, 8); out.small = [...new Set(out.small)].slice(0, 6); out.clipped = [...new Set(out.clipped)].slice(0, 6);
        return out;
      });
      if (r.pageOverflow > 0 || r.escapes.length || r.small.length || r.clipped.length) (report[id] = report[id] || {})[w] = r;
    }
  }
  console.log(JSON.stringify({ screens: ids.length, widths: WIDTHS, dir: DIR, problems: report }, null, 0));
  await b.close();
})();
