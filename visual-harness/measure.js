#!/usr/bin/env node
/*
 * Rendered verification for the §95 visual gate.
 *
 * This is the file that decides whether the visual gate is PASS or FAIL.
 * `check.js` reads source; this one renders and measures, across the full
 * matrix the checkpoint requires (§78): every critical screen x
 * {English LTR, Persian RTL} x {light, dark} x {390, 834, 1280, 1600}.
 *
 * It asserts rather than screenshots-and-hopes. Screenshots are written too,
 * because a human still has to look at them — but the exit code comes from
 * measurements, so "it rendered" cannot be mistaken for "it is correct".
 *
 * ENVIRONMENT
 *   Requires a Chromium binary. In an offline build container there is none,
 *   and this script exits 2 with ENVIRONMENT BLOCKED. Exit 2 means UNKNOWN.
 *   It must never be recorded as a pass.
 *
 * Usage:
 *   npm install puppeteer && npx puppeteer browsers install chrome
 *   node visual-harness/measure.js
 */

const path = require('path');
const fs = require('fs');

const SCREENS = [
  'screen-dashboard', 'screen-sources', 'screen-add', 'screen-processing',
  'screen-detail', 'screen-provenance', 'screen-knowledge', 'screen-states',
];
const WIDTHS = [390, 834, 1280, 1600];
const LOCALES = [{ lang: 'en', dir: 'ltr' }, { lang: 'fa', dir: 'rtl' }];
const THEMES = ['light', 'dark'];

const OUT = path.join(__dirname, 'out');

(async () => {
  let puppeteer;
  try {
    puppeteer = require('puppeteer');
  } catch {
    console.error('ENVIRONMENT BLOCKED: puppeteer is not installed. Visual gate = UNKNOWN, not PASS.');
    process.exit(2);
  }

  let browser;
  try {
    browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  } catch (e) {
    console.error('ENVIRONMENT BLOCKED: no Chromium binary available (' + e.message + ').');
    console.error('Visual gate = UNKNOWN, not PASS.');
    process.exit(2);
  }

  fs.mkdirSync(OUT, { recursive: true });
  const page = await browser.newPage();
  const url = 'file://' + path.join(__dirname, 'index.html');
  const failures = [];
  let measured = 0;

  for (const theme of THEMES) {
    for (const loc of LOCALES) {
      for (const width of WIDTHS) {
        await page.setViewport({ width, height: 1200, deviceScaleFactor: 1 });
        await page.goto(url, { waitUntil: 'networkidle0' });
        await page.evaluate((t, l) => {
          document.documentElement.setAttribute('data-theme', t);
          document.documentElement.lang = l.lang;
          document.documentElement.dir = l.dir;
        }, theme, loc);

        for (const screen of SCREENS) {
          await page.evaluate((id) => {
            document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('is-active', s.id === id));
            window.scrollTo(0, 0);
          }, screen);

          const m = await page.evaluate(() => {
            const de = document.documentElement;
            const overflow = de.scrollWidth - de.clientWidth;
            let clipped = 0, tiny = 0, lowContrast = 0;

            const lum = (c) => {
              const [r, g, b] = c.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number)
                .map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
              return 0.2126 * r + 0.7152 * g + 0.0722 * b;
            };
            const bgOf = (el) => {
              let n = el;
              while (n && n !== document.documentElement) {
                const bg = getComputedStyle(n).backgroundColor;
                if (bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) return bg;
                n = n.parentElement;
              }
              return getComputedStyle(document.body).backgroundColor;
            };

            document.querySelectorAll('.screen.is-active *').forEach((el) => {
              if (el.scrollWidth > el.clientWidth + 1) clipped++;
              const cs = getComputedStyle(el);
              const fs = parseFloat(cs.fontSize);
              const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
              if (!hasText) return;
              if (fs && fs < 12) tiny++;
              try {
                const l1 = lum(cs.color), l2 = lum(bgOf(el));
                const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
                const large = fs >= 18.66 || (fs >= 14 && parseInt(cs.fontWeight, 10) >= 700);
                if (ratio < (large ? 3 : 4.5)) lowContrast++;
              } catch { /* colour not parseable; skipped rather than guessed */ }
            });

            const targets = [...document.querySelectorAll('.screen.is-active :is(button,a.btn,input,select)')]
              .map((el) => Math.round(el.getBoundingClientRect().height)).filter((h) => h > 0);

            return { overflow, clipped, tiny, lowContrast, minTarget: targets.length ? Math.min(...targets) : null };
          });

          measured++;
          const tag = `${screen}-${loc.lang}-${theme}-${width}`;
          if (m.overflow > 0) failures.push(`${tag}: horizontal overflow ${m.overflow}px`);
          if (m.clipped > 0) failures.push(`${tag}: ${m.clipped} clipped element(s)`);
          if (m.tiny > 0) failures.push(`${tag}: ${m.tiny} text node(s) under 12px`);
          if (m.lowContrast > 0) failures.push(`${tag}: ${m.lowContrast} element(s) below WCAG AA contrast`);
          if (m.minTarget !== null && m.minTarget < 32) failures.push(`${tag}: interactive target ${m.minTarget}px`);

          if (width === 390 || width === 1280) {
            await page.screenshot({ path: path.join(OUT, tag + '.png'), fullPage: true });
          }
        }
      }
    }
  }

  // Focus ring, measured rather than assumed.
  await page.setViewport({ width: 1280, height: 900 });
  await page.goto(url, { waitUntil: 'networkidle0' });
  const focus = await page.evaluate(() => {
    const el = document.querySelector('.screen.is-active a, .screen.is-active button');
    el.focus();
    const s = getComputedStyle(el);
    return { style: s.outlineStyle, width: s.outlineWidth };
  });
  if (focus.style === 'none' || parseFloat(focus.width) < 1) {
    failures.push('focus ring is not visible on the first interactive element');
  }

  await browser.close();

  console.log(`\n${measured} screen/locale/theme/width combinations measured.`);
  console.log(`Screenshots: ${OUT}`);
  if (failures.length) {
    console.log('\nVISUAL GATE: FAIL');
    failures.forEach((f) => console.log('  ' + f));
    process.exit(1);
  }
  console.log('\nVISUAL GATE: measurements pass.');
  console.log('A human must still review the screenshots — measurement is a floor, not taste.');
})();
