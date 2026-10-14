const puppeteer = require('puppeteer');
const path = require('path');
(async () => {
  const browser = await puppeteer.launch({args:['--no-sandbox','--disable-dev-shm-usage']});
  const page = await browser.newPage();
  const url = 'file://' + path.resolve('harness.html');
  const widths = [375, 768, 1024, 1440];
  const results = [];
  for (const w of widths) {
    await page.setViewport({width: w, height: 1200, deviceScaleFactor: 1});
    await page.goto(url, {waitUntil: 'networkidle0'});
    await page.screenshot({path: `out/admin-${w}.png`, fullPage: true});
    // Real measurements, not eyeballing.
    const m = await page.evaluate(() => {
      const de = document.documentElement;
      const overflow = de.scrollWidth - de.clientWidth;
      let clipped = 0, tiny = 0;
      document.querySelectorAll('.aiol-wrap *').forEach(el => {
        if (el.scrollWidth > el.clientWidth + 1) clipped++;
        const fs = parseFloat(getComputedStyle(el).fontSize);
        if (el.textContent.trim() && fs && fs < 12) tiny++;
      });
      const targets = [...document.querySelectorAll('.aiol-wrap .button, .aiol-wrap input, .aiol-wrap select')]
        .map(el => Math.round(el.getBoundingClientRect().height));
      return {overflow, clipped, tiny, minTarget: targets.length ? Math.min(...targets) : null,
              docWidth: de.scrollWidth, viewport: de.clientWidth};
    });
    results.push({width: w, ...m});
  }
  // Focus visibility, measured.
  await page.setViewport({width: 1440, height: 1000});
  await page.goto(url, {waitUntil:'networkidle0'});
  const focus = await page.evaluate(() => {
    const el = document.querySelector('.aiol-wrap input');
    el.focus();
    const s = getComputedStyle(el, null);
    return {outlineWidth: s.outlineWidth, outlineStyle: s.outlineStyle};
  });
  console.log(JSON.stringify({results, focus}, null, 2));
  await browser.close();
})();
